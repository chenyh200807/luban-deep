# canonical-431 上服 Lane 2：tier-1 键接线 + 逐问真实满分封顶

- 日期：2026-08-01
- 分支：`chenyh200807/feat-canonical431-wire`（从 `origin/main` 起，独立 worktree `~/worktrees/c431-wire`）
- 前置：Lane 1（PR #648）—— [`2026-08-01-canonical431上服Lane1.md`](./2026-08-01-canonical431上服Lane1.md)
- 阶段：**Lane 2 = 只接线**。**没有切生产**：没翻 `production_authorized`、没改 env、没部署、没发 turn。
- claim level：**E2（接线面可读 + 单测 224 绿 + contract guard 全绿）**。
  **不是**「判得准已改善」——本轮同样没跑过一次真判分，判分质量一个数都没测。

---

## 0. 一句话结论

Lane 1 把 321 个采分点编成了 governed bank，但**判分核从来不用它的键**，装上去命中率是 0。
Lane 2 接的就是那条键路径：`{case_group_id}::E{n}` 逐小问查库 → 每问拿到**真实满分** →
`min(Σ命中, 真实满分)` 逐问封顶。

**这一刀真正换掉的是分母，不是封顶。** Lane 1 §9③ 实测推翻了「池>满分是常态」（95% 是精确
相等），所以封顶本身几乎不触发；杠杆全在「每问名义满分」从 `整题满分 ÷ 小问数` 的**均分**
换成**记录里的真值**。`2024-case1` 真实是 `5/4/4/3/4`，均分给每问 4.0 —— E1 少 1 分、E4 多 1 分。

---

## 1. 接线面（四处，逐处说清楚改了什么）

### 1.1 `deep_question._canonical_case_rubric_lookup`（新，纯函数）

```
{case_group_id} + [1-based 索引集]  →  (points, {"q{n}": 真实满分}, "命中/尝试")
```

逐小问 `load_rubric(f"{group}::E{n}")`，把命中问的采分点铺平成一张 points 表，同时产出
逐问封顶表。记录自带 `subquestion_index` / `question_no`（都是 1-based），所以
`_question_group_key` 走**显式字段**分桶，不会掉进那个把 0-based E 序数当问号读的
`::E(\d+)` 正则兜底 —— 这是本 bank 相对 legacy 的一个直接修复。

**四条 fail-closed**（任一不满足 → 返回空，调用方逐字节回落既有平查）：

| # | 条件 | 理由 |
|---|---|---|
| 1 | 组键或索引集缺失 → 一次库都不查 | 不可证的索引不许构键（§1.3） |
| 2 | slot 未命中（legacy/pgo 在服） | canonical 键在它们库里恒为空 → **未授权 slot 下行为零变化** |
| 3 | `nominal_authority_disputed` 的小问**整问剔除** | 2024-case3 Σ=22 / 2025-case5 Σ=28.5 与卷面结构对不上；拿走样的满分去封顶比不封顶更危险 |
| 4 | 分母 ≤ 0 的小问剔除 | 没有可信分母就没有封顶依据；留着它的点会被别的问的 cap 漏掉 = 等于无封顶 |

### 1.2 `_grade_one_case_v1` tier-1 分支

```python
canonical_points, canonical_caps, canonical_key_hit = _canonical_case_rubric_lookup(ctx, _G)
points = canonical_points or (_G.load_rubric(qid) if qid else [])   # ← 未命中即旧路径
canonical_nominal = round(sum(canonical_caps.values()), 2) if canonical_points else 0.0
```

命中时进 finalize（此前 tier-1 被**显式排除**在 finalize 之外）：

```python
elif canonical_nominal > 0:
    _G.finalize_case_score(event, nominal_full_score=canonical_nominal,
                           scope_ratio=1.0, subquestion_caps=subquestion_caps)
```

排除的原话是「`cg.max_score` 出自 V0 文本解析，可靠性不足」。**那条理由到此为止**：
分母不再需要从题面解析，它就在记录里。三条要点原样落实（Lane 1 §4.3）：

- `scope_ratio=1.0` —— 分母已经只算实际采纳的小问了，再乘一次覆盖比 = 双重缩放
  （P0 兜底满分那一族的病根形态）。
- `normalize_points_to_nominal` **在这条链上从不调用** —— canonical 的点分是真值，
  缩放只会毁掉它（那正是「全中即满分是结构性必然」的成因）。
- **写分者仍只有 `finalize_case_score` 一个**（多写者收敛不变）。

复用的是 OD-005 已在服的逐问机制（`subquestion_caps` → `_sum_awarded_with_subquestion_caps`
分桶封顶 → 外层整题范围封顶串联），**只把均分换成真值**，没有新造第二条封顶链。

### 1.3 `loop._build_v1_case_ctx` 导出（索引来源必须可证）

新增两个只读导出：`case_group_id`、`case_canonical_subquestion_indexes`。

索引集 = **本轮实际采纳的小问** ∩ **DB 权威索引**，两者缺一即整条留空：

```python
_db_authored_indexes = {  # coverage=="case_group_exact" 是唯一可证来源
    s["display_index"] for s in covered if s.get("coverage") == "case_group_exact"
}
_canonical_subq_indexes = [int(x) for x in eq_current["matched_indexes"].split(",")
                           if x in _db_authored_indexes]
```

`_assemble_case_group_bundle`（`supabase.py`）是全仓**唯一**把 DB 列 `case_subquestion_index`
投成 `display_index` 的地方，它给每个条目盖 `coverage="case_group_exact"`。其它路径的
`display_index` 出自题干正则解析或 `index+1` 序数。

**这条不是洁癖。** `loop.py` 历史上构造过 `{exam_year}::{source_chunk_id}::E{n}`，模拟建键
命中 **23/354、语义正确 0 条**，全部错绑到相邻小问的 rubric —— 拿错采分点判分**且不报错**。
索引来源不可证就不构键。

### 1.4 `rubric_grader_v1`：slot 注册 + 白名单

- `_RUBRIC_BANK_SLOTS` 注册 `canonical431`。**注册 ≠ 授权**：`_load_bank_slot` 的
  `production_authorized` 闸一字未动，本 lane **不翻 true**。
- by_q 白名单加 `case_group_id` / `nominal_authority_disputed`。白名单外的字段是**静默丢弃**的
  （Lane 1 §1.3 就是被这条逼着复用 `official_total_score` 而不新造字段名）—— 丢了
  `nominal_authority_disputed`，§1.1 的第 3 条 fail-closed 就整线解除武装。
- 白名单投影提成 `_project_bank_records_to_points` 纯函数：白名单是判分能力的硬边界，
  必须能被直接断言，而不是只能透过一个受治理闸 + 进程级缓存包住的装载器间接观察。

---

## 2. 发声：`case_canonical_key_hit`

形如 `"4/4"`、`"3/4"`、`"0/5:disputed5"`（分母 = 尝试构键的小问数）。
已进 `CASE_GRADING_AUTHORITY_EXPORT_KEYS` 单一白名单（→ 判分事件 → turn metadata → trace 全 sink），
**降级/失败返回上也带**（`no_reference` / `unavailable` / `degraded`）。

它回答的是既有 `case_rubric_bank_slot`（`"canonical431:authorized:96"`）**回答不了**的那个问题：
库到底有没有被**用上**。没有它，「slot 切了但键没接通、零命中」和「切了且命中」在 trace 上
长得一模一样 —— 那正是 Lane 1 §9① 指出的洞。`0/5:disputed5` 则让「拒用走样分母」与
「压根没这个库」区分得开。

---

## 3. slot 切换 runbook（主控执行，本 lane 一件都没做）

三道闸的现状（`rubric_grader_v1._load_bank_slot`）：

| 闸 | 状态 |
|---|---|
| `manifest.content_hash == _sha256_hex(records)` | ✅ |
| `canonical_pointer.expected_content_hash == actual` | ✅ |
| `pointer.production_authorized is True` | ❌ **故意为 false** |

**步骤**

1. **前置确认**（不做这步等于盲切）：接线已合 main，且 `_RUBRIC_BANK_SLOTS` 里有
   `canonical431`。验证：`python3 -c "from deeptutor.services.construction_grading import rubric_grader_v1 as G; print(G._load_bank_slot('canonical431')[1])"` → 期望 `unauthorized`
   （**不是** `unknown_slot` / `hash_mismatch`；后两者说明 Lane 1 产物被改坏了）。
2. **翻授权**：改
   `deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored_canonical431/canonical_pointer.json`
   的 `production_authorized: false → true`，并把 `authorization_note` 换成授权注记
   （谁、何时、依据哪一轮 live 回归）。这是一次**显式提交**，不许夹在别的 PR 里带过去。
   连带把 `manifest.production_authorized` 一并翻（两处一致，否则 §5 的断言会红）。
3. **切 slot**：`LUBAN_CASE_RUBRIC_BANK_SLOT=canonical431`。
   `_rubric_bank` 是 `lru_cache(maxsize=1)` 且进程级 —— **必须重启 worker**，不重启不生效
   （这是刻意的：避免进程内混合权威）。
4. **装载核验**（重启后立刻查，不要等 live 轮）：判分事件的
   `case_rubric_bank_slot` 应为 `canonical431:authorized:96`。
   若出现 `legacy:fallback_from:canonical431:174` = 第 2 步没生效，**停**。
5. **命中核验**：跑 §4 的 live 判据，看 `case_canonical_key_hit`。
   `0/N` = slot 装上了但键没接通（组键或索引来源不可证）—— 这是**接线问题不是授权问题**，
   翻回去无济于事，去查 `case_bundle_source` 是不是 `group_query`。

**回滚**：`LUBAN_CASE_RUBRIC_BANK_SLOT=legacy` + 重启。若来不及改 env，把 pointer 的
`production_authorized` 翻回 `false` + 重启也能回落（治理闸会拒装并大声回落 legacy），
但那条路径会在日志里留 ERROR，作为紧急止血用、不作为常规回滚。

---

## 4. live 判据（主控切 slot 后跑，本 lane 未跑）

**判据题必须选 nominal 非均分的组**，否则测不出东西：

> ⚠ 任务书原写「2023-case3 整卷全答」—— 实测 `2023-case3` 的四问 nominal 是 `5/5/5/5`，
> **恰好等于均分 20/4=5**。它无法区分「真值封顶」与「均分封顶」，**不能当判据题**。

可用判据题（全部 100% 可达、无争议标）：

| 组 | 可达 E | 真实 nominal | 均分 | 判别力 |
|---|---|---|---|---|
| `2023-case4` | 1-5（E6 不可达） | 2/5/5/6/6 | 5.0 | **最强**（E1 真值 2.0 vs 均分 5.0） |
| `2025-case4` | 1-5 | 4/8/5/7/6 | 6.0 | 强 |
| `2023-case1` | 1-4 | 7/3/5/5 | 5.0 | 强 |
| `2025-case5` | 1-5 | — | — | **反向判据**：全组 disputed，必须 `0/5:disputed5` 且不进封顶 |

**通过条件（三轮一致）**

1. `case_rubric_bank_slot == "canonical431:authorized:96"`；
2. `case_canonical_key_hit == "N/N"`（N = 该组可达小问数）；
3. `rubric_provenance == "compiled_rubric"`；
4. `case_subq_score_caps` 逐问等于真实 nominal（`2023-case4` → `q1:2.0,q2:5.0,q3:5.0,q4:6.0,q5:6.0`），
   **不是**每问 5.0；
5. `max_score` == Σ真实 nominal（`2023-case4` 前五问 = 24.0），`scoring_scope_max` 与之相等
   （证明 `scope_ratio=1.0`、没有双重缩放）；
6. 只答一问的对照卷：该问的得分 ≤ 该问真实 nominal（`2023-case4` 只答 E1 → ≤ 2.0，
   均分实现会给到 5.0）。

**未切时的零变化判据**（同样三轮）：`case_canonical_key_hit` 缺席或 `0/N`，
且分数三字段与切换前逐字段相等。

---

## 5. 测试证据

| 面 | 文件 | 断言要点 |
|---|---|---|
| 逐问真实满分封顶 | `tests/core/test_deep_question_case_rubric_v1.py` | 只答问 4（池 6.0）→ **3.0**（真值）而非 4.0（均分）；caps 串 `q1:5.0,q2:4.0,q3:4.0,q4:3.0,q5:4.0` |
| 分母只算采纳问 | 同上 | 采纳 [2,4] → `max_score=7.0`、`scoring_scope_max=7.0`（无双重缩放） |
| disputed fail-closed | 同上 | 全组打标 → `0/5:disputed5`、不进封顶、退回非 tier-1 |
| **未授权 slot 零变化** | 同上 | 同一 ctx 带/不带组键两跑，`awarded_score`/`max_score`/`rubric_provenance` 逐字段相等 |
| 2022 不可命中 | 同上 + `test_rubric_grader_v1.py` | 运行时零命中；bank records 内 2022 = 0 且 quarantined 非空 |
| 不可证索引不构键 | `tests/tutorbot/test_agent_loop_case_rubric_v1.py` | `coverage != "case_group_exact"` 的索引被剔；无组键 → 双空 |
| 治理闸未被翻 | `tests/services/construction_grading/test_rubric_grader_v1.py` | `_load_bank_slot("canonical431")` → `unauthorized`；env 切 slot → 回落 `fallback_from:canonical431` |
| 白名单穿透 | 同上 | `official_total_score` / `case_group_id` / `nominal_authority_disputed` 三字段可达 |
| marker 上 sink | `test_agent_loop_case_rubric_v1.py` | `case_canonical_key_hit` ∈ 单一导出白名单 + turn metadata |

三个测试文件全量 **224 passed**；`scripts/check_contract_guard.py` 全绿。

**防三坑**：①未授权 slot 零变化有对照跑（不是口头保证）；②2022 隔离在编译期与运行时**两侧**
各有断言；③索引来源可证性有正反例（`case_group_exact` 通过、`similarity_sibling` 被拒）。

---

## 6. 金标 Q2024-03 满分订正（22.0 → 20.0，独立 commit）

**依据**：Lane 1 §3.4。原分母 = Σ佑森逐点分值 —— 佑森是该 pack 唯一分值来源，自己校自己
等于没校。Lane 1 引入的外部锚（一建·建筑实务卷面结构：案例一~三各 20 分、四~五各 30 分）
压 20 个案例组，**18 组精确吻合、2 组走样**，`2024-case3`（= `Q2024-03`）Σ=22.0 多 2.0。

| | 原 | 现 |
|---|---|---|
| `rubric_total_score` | 22.0 | **20.0**（`_authority = official_paper_structure_1a_jianzhu`） |
| Σ点分 | （无字段） | `rubric_point_pool_total = 22.0` |
| 争议标 | 无 | `nominal_authority_disputed: true` + `nominal_dispute_detail` |
| high / mid / low | 0.864 / 0.682 / 0.273 | **0.950 / 0.750 / 0.300** |

**改的是生成器不只是产物**：`build_v2.py` 加 `OFFICIAL_PAPER_CASE_TOTALS` 锚表，产物由重跑
`build_v2.py` 生成。确定性证据：`leakage_check.json` 重跑后**逐字节不变**，只有意图内的字段动了。

**per-小问 `sub_q_total_score` 一个字没动**（仍 5/4/4/5/4，Σ=22）：哪一问多了 2.0 是未裁决的
（Lane 1 `nominal_drift_pending_adjudication`），编一个分配方案会把「不知道」伪装成「知道」，
比留着不一致更危险。副作用已写进 README：**本题全中会算出 110%**，那是走样本身不是计算错误。

连带更新：`extractions/gold_pack_v2/README.md §4`、`2026-08-01-判分金标v2重造.md §3.3`。

---

## 7. 诚实边界

- **判分质量一个数都没测。** 没跑判分器、没发 turn、没建账号、没部署。
- **可达率 52% 是天花板**（Lane 1 §2.4）：46 个小问卡在「整题行 index 必须留空」的 C2 契约上，
  **2024 全年 25 个小问一个都够不着**。本 lane 只服务那 50 个可达小问，
  整题行 bundle（Lane 1 §4.4）是独立一战，刻意没与本刀同批做。
- **分值权威仍是佑森培训机构解析、`NOT_official`。** 接线不改变这一点。
- **`official_total_score` 这个字段名带 "official" 而权威是佑森**（Lane 1 §9⑤ 的妥协）：
  本 lane 沿用了它、**没有**顺手迁移到 `subquestion_nominal_score`——那是一次白名单 +
  编译器 + 消费面的三点同改，夹在接线里做会让「零变化」不可证。这条债原样留着。
- **可达性用的是 C1 的 2026-08-01 只读快照**，本进程无 DB 凭据，未核 live DB。
- **`case_denominator_source` 在 tier-1 canonical 轮上是 `canonical_rubric`**（见 §8 调和），
  与 R2 阶梯的 `canonical`（结构小问数）刻意用不同取值 —— 两者是不同级的权威。

---

## 8. 与并行分支的调和（#651 R1R2 / #652 narration）

三条分支同期改同一批文件，主控裁定 **#651 → #652 → 本 lane** 串行落地。调和口径记在这里，
免得下一个人以为是两套权威打架：

| 面 | #651（R2） | 本 lane | 调和 |
|---|---|---|---|
| `_RUBRIC_BANK_SLOTS` 注册 | 已注册（为分母读者） | 已注册（为判分内容） | **同一条目**，注释合并；`_CANONICAL_DENOMINATOR_SLOT` 保留 |
| `_load_bank_slot` 授权闸 | 加 `require_production_authorization=False` 逃生口 | 不碰签名 | 逃生口**只给结构读者**；判分内容走默认 `True`，一步不减 |
| canonical 读者 | `canonical_case_subquestion_counts()` 读 `nominal_table`/`whole_case_index`，**绝不读 records** | `load_rubric()` 读 `records`，需 `production_authorized` | **不合并**：两者是不同级的权威（见下） |
| `case_group_id` 读取 | `_case_group_id_from_ctx(ctx)` | 原本自读 `ctx["case_group_id"]` | **收权**：本 lane 改吃 #651 的读者 |
| `CASE_GRADING_AUTHORITY_EXPORT_KEYS` | `case_denominator_source` | `case_canonical_key_hit` | **双方保留** |
| 分母来源发声 | 阶梯 `canonical`/`bundle`/`stem`/`reference_fallback` | tier-1 canonical 命中 | 本 lane 补发 `case_denominator_source="canonical_rubric"`（**独立取值**） |

**为什么分母读者不能合并成一个**（这条是本次调和唯一需要判断力的地方）：

- #651 的 `canonical_case_subquestion_counts()` 取的是**结构事实**——「这道案例有几问」，
  一个整数。它刻意走 `require_production_authorization=False` 的逃生口，理由是
  「分母是结构、采分点才是分值权威，两者不同级」。
- 本 lane 要的是**每问真实满分**——一个**分值**，属于佑森估分（`NOT_official`），
  正是治理闸要管的东西。它必须走默认 `True` 的授权路径。

把后者接到前者的读者上，等于让分值从治理旁路进场 —— 那正是 pgo 未授权覆写服役六周
那一族的病。**所以这里保持两个读者是收权，不是重复。** 合并的是 `case_group_id` 的读取
（真重复），不是 bank 的读取（假重复）。
