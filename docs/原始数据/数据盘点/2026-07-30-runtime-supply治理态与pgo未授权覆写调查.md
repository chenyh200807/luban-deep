# runtime_supply 治理态与 pgo 未授权覆写调查

- **日期**: 2026-07-30
- **状态**: `read_only_investigation`（本地仓库只读 + 生产容器只读 `docker exec` 取证，零写操作）
- **提问口径**: `canonical_pointer.json` 里 `published:false` 是"漏签一步（补签发即可）"还是"如实记录治理状态"？
- **结论一句话**: 是后者 —— 在这条 lane 里 **`published:false` 是硬不变量**（多处反向门控：`published=true` 反而会被拒绝），真正越界的是生产那行 `LUBAN_CASE_RUBRIC_BANK_SLOT=pgo` env；**pgo bank 在未获授权状态下对 100% 案例判分流量服役约六周**，装载面只验 hash 不读治理态，所以红线拦不住。

---

## 范围与方法

| 项 | 值 |
|---|---|
| 本地仓库 | `/Users/yehongchen/orca/workspaces/deeptutor/gar`（当日快照） |
| 生产 | Aliyun-ECS-2，容器 `deeptutor`（取证时 Up 19 min, healthy），**只读 `docker exec` 读 env / 读文件 / 重算哈希** |
| 方法 | ① 读装载函数逐行确认读了哪些字段 → ② 全仓 grep `published` 的消费点，判定语义方向 → ③ 查治理账本与红线记录 → ④ 生产容器逐字节比对 pointer 与 bank、按同一口径重算 content_hash → ⑤ grep canary env 是否有任何消费者 |
| 写操作 | **0**（调查阶段）；后续整改另立 PR，见文末订正 |

---

## 关键发现

### 1. 装载面根本不读 `published`

`deeptutor/services/construction_grading/rubric_grader_v1.py:1221-1299` `_rubric_bank()`（`lru_cache(maxsize=1)`，进程级）当日形态：

| 行 | 行为 |
|---|---|
| L1233 | `raw_slot = os.getenv("LUBAN_CASE_RUBRIC_BANK_SLOT", "legacy")` |
| L1235 | slot → `_RUBRIC_BANK_SLOTS[slot]` → `(slot_dir, bank_name)` |
| L1252-1256 | 校验 records 的 sha256 == `manifest.content_hash` |
| L1257-1263 | 读 `canonical_pointer.json` |
| L1264-1268 | **只校验 `expected_content_hash`（或 `content_hash`）== actual_hash** |
| 全函数 | **无任何 `published` / `status` 读取** |

→ `published:false` 完全不拦装载。**两道闸都是完整性闸（hash），没有一道是授权闸。**

当日两份 pointer 内容：

- `v_case_rubric_scored_pgo/canonical_pointer.json`：`status=release_candidate`、`published=false`、`expected_content_hash=1d48bf1a…`、`rollback_pointer="LUBAN_CASE_RUBRIC_BANK_SLOT=legacy"`
- `v_case_rubric_scored/canonical_pointer.json`（legacy）：`status=release_candidate`、`published=false`、`expected_content_hash=59ddec24…`

注意：**在服的 legacy 自己也是 `published:false`** —— 所以"published=false 说明没上线"这个直觉在这条 lane 里是错的。

### 2. `published:false` 是硬不变量 —— 反向门控清单

`published=true` 会被以下消费者**拒绝/阻断**（即"补签发"会把系统弄坏）：

| 位置 | 行为 |
|---|---|
| `deeptutor/services/construction_grading/case_rubric_pgo_supply.py:364-365` | `validate_pgo_runtime_supply`：`if manifest.get("published") is not False: blockers.append("published_must_be_false")`；写盘函数 `write_pgo_runtime_supply`(L389-393) 校验失败直接 raise → **published=true 的 pgo bank 根本写不出来** |
| `deeptutor/services/construction_grading/m35_artifact_query.py:205-206` | `_load_pgo_supply`：`published is not False → blockers.append("published_not_false")` → `status=blocked` |
| `deeptutor/services/construction_grading/compiled_registry_resolver.py:36-37` | `verify_bundle`：`published is True → status_gate_failed` |
| `deeptutor/services/construction_grading/beta_shadow_loader.py:425-426` | `published is True → ReleaseCandidateUnavailable` |
| `tests/services/construction_grading/test_m30r_canonical_pointer.py:35` | `assert p["published"] is False` |

构建面固定写 false：`case_rubric_pgo_supply.py:324`（manifest）、`:348`（pointer `build_pgo_runtime_supply_pointer`）都硬编码 `"published": False`；pointer 自带 `"rollback_pointer": "LUBAN_CASE_RUBRIC_BANK_SLOT=legacy"`（L338/L350）—— **env slot 是 pointer 自己登记的回滚杠杆，两者是同一套账**。

pgo 工具链（`scripts/`）全部 read-only、明确"不翻 slot"：

- `scripts/build_luban_pgo_runtime_supply.py:1-6` — "does not flip `LUBAN_CASE_RUBRIC_BANK_SLOT`"
- `scripts/verify_luban_pgo_runtime_supply.py:1-7` — "Read-only gate … verifies release-candidate/default-off status … does not flip"
- `scripts/run_luban_pgo_stage5_canary_gate.py:1-8` — "does not flip production defaults"

→ **整条 pgo 工具链里没有任何 publish/promote 步骤**；翻 slot 就是设计里的最后一步（且被红线禁掉）。

唯一的 publish 脚本 `scripts/publish_all_runtime_supply_bundles.py`：`TARGETS`(L32-42) 含 `v_case_rubric_scored`(legacy)、**不含** `v_case_rubric_scored_pgo`；文件头 L8-12 明确列出"必须保持 `published=False`"的 bundle 清单。

历史痕迹：`b875c4b66`(2026-06-08) 曾把 legacy 翻成 `published=True`，后续重编译（`scripts/run_luban_rubric_compile.py:94-96` 无条件写 `published:false`）又翻回 false；pgo pointer 只有一个 commit：`a5661d715 Install KnowQL PGO release-candidate bank`。

### 3. 治理账本白纸黑字写着「pgo 未获授权」

| 出处 | 内容 |
|---|---|
| `docs/plan/鲁班knowql/IMPLEMENTATION_LEDGER.md:55` | Slot-aware PGO bank reader = `shadow-verified`；Stage5 canary fresh-process loader 读到 `slot=pgo` / `question_count=179` / `scoring_point_count=1384`，**同一份报告仍写 `production_default_flip_allowed=false` 和 `actual_worker_restarted=false`**；备注"仍需 owner 授权和 live worker restart 证据，不能默认 pgo" |
| `docs/plan/鲁班移动端提分闭环/implementation-notes.md:428`（2026-07-11 异源终审后） | **红线立即生效：`LUBAN_CASE_RUBRIC_BANK_SLOT=pgo` 禁止拨**；"差一脚 env"的建议全部撤回；PGO 停留 shadow，重建必须走 canonical rubric 路线。原因：PGO 库有 **A 级判分错误入库**、**评分对象边界坍塌**（多小问压进一个 qid）、`score=None` 靠切分粒度隐式计分、**authority 冒牌**（源文件 `NOT_official=true` 却标 `official_answer_verbatim`） |
| `implementation-notes.md:452` + `methodology-log.md:609-620`（2026-07-12） | 生产实测 `=pgo`，与红线冲突，**非该次部署引入**：host `.env` 备份 06-19 / 07-05 / 07-06 全是 pgo，已存活约 3 周；部署 agent 取证后未擅动，列为 owner 待裁决项 |

→ `published:false` 不是"漏签一步"，它**如实记录了治理状态：这份资产从未获得生产默认授权**。越界的是生产那行 env。

### 4. 生产只读核实：pgo 确实在服役，两道哈希闸全过

容器 `deeptutor` env（只读 `docker exec` 取证）：

```
LUBAN_CASE_RUBRIC_BANK_SLOT=pgo
LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED=true
LUBAN_CASE_RUBRIC_BANK_SLOT_CANARY_ENABLED=false
LUBAN_CASE_RUBRIC_BANK_SLOT_CANARY_COHORT=qa_,operator_
```

- 容器内两份 `canonical_pointer.json` 与本地仓库**逐字节一致**（pgo：`published=false`、`expected_content_hash=1d48bf1a…`、`rollback_pointer=…=legacy`；legacy：`published=false`、`59ddec24…`）。
- 容器内 bank manifest 实测：`status=release_candidate`、`published=False`、`production_default=off`、`question_count=179`、`scoring_point_count=1384`、`content_hash=1d48bf1a…`。
- 按 `full_knowledge_compiler._sha256_hex` 口径在容器内重算 records 哈希 = `1d48bf1a…`，**match=True**。

→ 两道哈希闸全过，**pgo bank 在生产确实装载并服役，`published:false` 全程没参与判断**。

**服役时长**：按 host `.env` 备份（06-19 / 07-05 / 07-06 全为 pgo）+ 07-12 生产实测 + 07-30 本次复核 → **约六周未授权覆写**，覆盖 100% 案例判分流量。

### 5. canary 结构是幻觉（安慰性证据不成立）

- `LUBAN_CASE_RUBRIC_BANK_SLOT_CANARY_ENABLED` / `..._COHORT` 在**整个仓库零引用**（全仓 grep 无命中，`contracts/env_registry.yaml` 也未登记）→ 两个**孤儿 env**。
- `_rubric_bank()` 只读 `LUBAN_CASE_RUBRIC_BANK_SLOT`，**无任何 cohort 分流**。
- 故 pgo 对 **100% 案例判分流量**生效，不是"限 `qa_`/`operator_` 的金丝雀"。2026-07-12 部署 agent 汇报里"带 canary 结构"这条安慰性证据**不成立**。

---

## 结论（调查当时）

**方向 B（未获授权的覆写），不是 A（补签发）。绝对不要执行"补签发"。** 翻 `published=true` 会：

1. 让 `m35_artifact_query._load_pgo_supply` 报 `published_not_false` → M35 artifact query `status=blocked`；
2. 让 `validate_pgo_runtime_supply` 报 `published_must_be_false` → 下次 build/write 直接 raise；
3. 违反 2026-07-11 已生效的红线（PGO 有 A 级判分错误入库）。

正确方向是**回滚 env 到 legacy** + **把治理态接进装载面**（见下节订正）。

---

## 订正留痕：本调查的结论已被后续整改推进（同日 2026-07-30）

> 按盘点纪律第 6 条，显式记录本文档"关键发现 §1"（装载面只验 hash、不读治理态）**已不再是当前代码形态**。

**PR #601「护栏③——bank 装载治理闸 + slot 身份逐轮导出」已合入 main**（实现 commit `b1dbd125f`，merge commit `5d25f2401`）。红线口径：**content_hash 只证完整性、不证授权 —— 完整的赝品仍是赝品。**

落地三件：

1. **pointer 授权位 `production_authorized`**
   - `runtime_supply/v_case_rubric_scored/canonical_pointer.json`：`production_authorized: true`，注记"2026-07-30 owner 拍板回滚 pgo 后确立 legacy 为生产授权 lane（六月生产脊柱）"。
   - `runtime_supply/v_case_rubric_scored_pgo/canonical_pointer.json`：`production_authorized: false`，注记"2026-07-11 异源终审红线「=pgo 禁止拨」（A级判分错误入库/评分对象边界坍塌/authority冒牌）；翻 true 须经 PGO 重晋级治理批+owner 拍板"。
   - 构建器 `case_rubric_pgo_supply.py:352` 重建默认写 `production_authorized: False` —— **翻 true 必须是显式治理动作，不随 build 自动获得**。
2. **装载治理闸**：`rubric_grader_v1._rubric_bank()` 现读治理态，`pointer.get("production_authorized") is not True` → 记 ERROR 级日志 `POINTER NOT PRODUCTION-AUTHORIZED (governance gate)` 并返回 `unauthorized`，**回落到授权默认 slot（legacy），全程发声、绝不静默**。完整性类失败（unknown slot / missing / hash 不符）维持既有 fail-closed 法条**不回落**（打错 slot 名静默换权威比空 bank 更危险）。
3. **slot 身份逐轮导出**：判分事件携带 `case_rubric_bank_slot="slot:governance:qid_count"`，经单源常量 `CASE_GRADING_AUTHORITY_EXPORT_KEYS` 自动上全 sink（chat metadata / trace summary / jsonl）—— "slot 漂移无人知"的洞用导出封死。

测试证据（PR #601）：治理闸专测 2 例（未授权回落 + 默认 lane 也未授权时拒绝）+ 事件身份导出 domain test + fixture 授权位；899 passed（construction_grading + core + tutorbot + observer 全套）；contract guard passed。

**仍然成立、未被订正的结论**：`published:false` 在这条 lane 里依旧是硬不变量（§2 反向门控清单未改动，不要去翻）；治理账本红线（`=pgo` 禁止拨）依旧有效；两个 canary env 依旧是孤儿（§5）。

---

## 缺口与诚实边界

1. **两个孤儿 env 未清理**：`LUBAN_CASE_RUBRIC_BANK_SLOT_CANARY_ENABLED` / `..._COHORT` 仍在生产 env 里、仍零消费者、仍未登记 `contracts/env_registry.yaml`。留着就会继续制造"有 canary 保护"的错觉，**建议单独一批删除或补真实实现**。
2. **本文档不含 pgo bank 内容质量复核**：A 级判分错误、评分对象边界坍塌等定性来自 2026-07-11 异源终审记录，本次未重跑。
3. **生产回滚动作的事后核验不在本文档口径内**：本调查止于取证与整改方案；env 回滚到 `legacy` 后的 live 回归证据应另行落 implementation-notes，**本文档不据此宣称"已修好"**。
4. **未覆盖**：其他 runtime_supply namespace（非 case rubric lane）是否存在同型"只验 hash 不验授权"的装载面，未逐一排查。

---

## 数据来源路径（可复查）

| 内容 | 路径 |
|---|---|
| 装载函数 | `deeptutor/services/construction_grading/rubric_grader_v1.py`（`_rubric_bank()`，当日 L1221-1299；护栏③后含治理闸 L1275+） |
| pgo 构建/校验 | `deeptutor/services/construction_grading/case_rubric_pgo_supply.py`（L324 / L338-352 / L364-365 / L389-393） |
| 反向门控消费者 | `m35_artifact_query.py:205-206`、`compiled_registry_resolver.py:36-37`、`beta_shadow_loader.py:425-426`、`tests/services/construction_grading/test_m30r_canonical_pointer.py:35` |
| pointer / bank | `deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored{,_pgo}/canonical_pointer.json`、`case_rubric_scored_pgo.json`、`manifest.json` |
| 工具链 | `scripts/build_luban_pgo_runtime_supply.py`、`scripts/verify_luban_pgo_runtime_supply.py`、`scripts/run_luban_pgo_stage5_canary_gate.py`、`scripts/publish_all_runtime_supply_bundles.py`、`scripts/run_luban_rubric_compile.py:94-96` |
| 治理账本 | `docs/plan/鲁班knowql/IMPLEMENTATION_LEDGER.md:55`、`docs/plan/鲁班移动端提分闭环/implementation-notes.md:428,452`、同目录 `methodology-log.md:609-620` |
| 整改 | PR #601（`b1dbd125f` 实现 / `5d25f2401` merge），治理闸测试 `tests/services/construction_grading/test_rubric_grader_v1.py:1731-1780` |
| 历史 commit | `b875c4b66`(2026-06-08 legacy 曾 published=true)、`a5661d715`(pgo pointer 唯一 commit) |

---

> 产物工作副本曾位于 session scratchpad（`canonical_pointer_investigation.md`），**正式归档以本文档为准**。
