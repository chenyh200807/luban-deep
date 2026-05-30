# ACTION_LOOP 采分点空态——根因诊断 + 止血 runbook + 赚回路径

| 字段 | 值 |
| --- | --- |
| 日期 | 2026-05-30 |
| 类型 | Diagnosis + Runbook（只读核验产物） |
| 状态 | v1 |
| 核验方式 | **纯只读**：生产 Supabase 仅 `SET default_transaction_read_only=on` + SELECT；本地 codegraph/grep/Read 代码；阿里云未写。**未翻 flag、未写库、未部署。** |
| 凭证来源 | `FastAPI20251222/.env` 的 `DB_URL`（host=`aws-1-ap-southeast-1.pooler.supabase.com:6543` 生产 pooler，明文未打印） |
| 纪律 | AGENTS §5 根因（从空态向上游追，禁止症状端补丁）+ §3.7（阿里云写边界，本任务全程只读） |
| 上游 | [2026-05-30-prod-state-and-flag-flip-decision.md](2026-05-30-prod-state-and-flag-flip-decision.md) §4 |

---

## 0. 执行摘要（结论先行）

**根因判定：主因是 source 内容缺口（content gap），次因是被故意 gate 的编译管线——不是 pipeline bug。**

1. **次因（grading_rubric 0%）**：`questions_bank.grading_rubric` 的唯一写入 authority 是 2026 source compiler，而 `scripts/apply_2026_compiler_backfill.py:9` **硬拒绝 `--apply`**（"Refusing --apply until Task 13…"）。即填充管线已建好但**从未对生产 apply**——是审慎 gate，不是 bug。
2. **主因（map_eligible 48.7% 天花板）**：生产实测 **1001/1961（51%）case 题 `grading_keywords` 完全为空**；`map_eligible=955` 恰好等于 `grading_keywords≥2` 的数量（`structured_rules` 不贡献任何增量）。即采分点可投性 100% 由 source 标注丰度决定——这是**教研对源题的标注债**。
3. **再被收窄**：projected_rubric 只对 8 个 audited cluster 白名单可见，这 8 簇只覆盖 **401/1961（20%）case 题**。所以"靠 questions_bank 出来的可见采分点"上限 ≤ 20%，远低于 48.7%。
4. **跑 compiler 也救不了 map_eligible**：`compile_rubric_candidate` 的 `rubric_points` 取自 `grading_keywords or testing_focus`（`overwrite_only_if_empty`）。它能把 projected 档升级成 curated 档**标签**，但对 grading_keywords 为空的 1001 题**产生不出新采分点**。所以 Task 13 apply 只抬 `grading_rubric` 的 presence，不抬 map_eligible。

**对"止血"的诚实修正**：经核验，所谓"空态"**是优雅占位、不是破 UI**（"本题暂无可拆采分点，已先按审题要点收集"）。且关掉 `ACTION_LOOP_STAGE` **不是干净止血**——它会干净隐藏"学习状态推断引擎"卡，但**留下独立的"采分点怎么补"占位 section**，同时**砍掉 deep_question 练习产生的真采分点（`grading_key` 档，与 questions_bank 0% 无关）**。因此 §5 纪律下不推荐"一刀切关 flag 当止血"；真正的根治在覆盖率（§3 给出诚实选项，§4 给赚回路径）。

---

## 1. §5 四层根因分析

### 1.1 业务事实
学生做完案例题后，"采分点怎么补"应能列出他反复漏掉的 ≥2 个具体采分点（带漏分次数与下一步训练），而不是一句泛化占位。

### 1.2 Authority（谁该写采分点信号）
采分点 map（`scoring_point_map_read_model.py`）**render 时读 `learner_memory_events.learning_evidence` 的 `payload.rubric.rubric_mode`**，不直接读 questions_bank。每条 grading event 的 `rubric_mode` 由阅卷 kernel 决定（`case_kernel.py:50-63` 优先级）：

| rubric_mode | 来源 authority | 是否产生可见采分点 |
| --- | --- | --- |
| `grading_key` | deep_question 出题时生成的隐藏评分点（**与 questions_bank 无关**） | ✅ 真采分点（练习链路） |
| `curated_rubric` | `questions_bank.grading_rubric` | ✅ 真采分点——**但该字段 0%→永不可达** |
| `projected_rubric` | 从 `grading_keywords`/`structured_rules` 投射 | 🟡 仅对 8 audited cluster 可见（"审题要点"） |
| `open_skill` | 无结构信号兜底 | ❌ 不贡献 map |

**结论**：questions_bank 路线的两个高保真档里，`curated_rubric` 因 grading_rubric=0% 完全不可达，`projected_rubric` 受 source 标注 + cluster 白名单双重限制。

### 1.3 断点（事实在哪层丢的）——证据

**断点 A：curated 档的写入 authority 被 gate（codegraph/grep 证据）**
- `grading_rubric` 全仓**无任何 INSERT/UPDATE 写入点**（`rg grading_rubric --type py` 命中全是读：`case_kernel.py:210` 读、`audit.py:97` 读、`rag/.../supabase.py:2114` 读）。
- 唯一候选写者 `deeptutor/services/source_compiler/rubric_compiler.py:compile_rubric_candidate` 只产 candidate JSONL。
- `scripts/apply_2026_compiler_backfill.py:9` `REFUSAL="Refusing --apply until Task 13…"`，`:20-21` 见 `--apply` 直接退出。→ **管线建好、apply 被锁，0% 是预期。**

**断点 B：projected 档的可投性受 source 标注限制（SQL 证据，生产实测 2026-05-30）**
```
questions_bank: total=4638, case_study=1961
grading_rubric 非空 = 0            (0.0%)   ← curated 档不可达
grading_keywords ≥2 = 955         (48.7%)  ← = map_eligible 全部来源
grading_keywords =1 = 5
grading_keywords =0 = 1001         (51.0%)  ← 过半 case 题零采分点信号
map_eligible (sr≥2 OR gk≥2) = 955 (48.7%)  ← 与 gk≥2 完全相等→structured_rules 零增量
8 审计 cluster 覆盖 case 题 = 401  (20.4%)  ← projected 可见上限
```
抽样 8 条 case 题：`has_rubric=f`（全无）、`gk_n=4~10`、`sr_n=1`。即有标注的题 keywords 还算丰富，但 grading_rubric 全空、structured_rules 普遍只有 1 条。

**断点 C：compiler 即使 apply 也救不了 map_eligible（代码证据）**
`compile_rubric_candidate` 的 `rubric_points = capsule.get("grading_keywords") or capsule.get("testing_focus")`——派生自已有 keywords。对 1001 道零 keyword 题无源可派生。

### 1.4 修法类型
- **不是收权 / 删重复判断**——authority 链是干净的（map 读 learning_evidence、kernel 定 rubric_mode、compiler 是唯一 rubric 写者）。
- **不是 flag 配置错**——flag 全开是有意的；空态是优雅的。
- **是"新增能力 / 补内容"**：给 1001 道零信号 case 题补 ≥2 采分点（教研标注或真正从标准/教材抽取的编译，而非从已有 keywords 再派生）。**这是 content/authoring backlog，不是 pipeline bug。**

---

## 2. 关键澄清：当前"空态"不是破 UI

- 后端 `_empty_scoring_point_map(reason)`（`learning_report_read_model.py:386`）恒返回 `empty_state="rubric_pending"`，`blocked_reason=reason`。
- 前端 `scoringPointMapEmptyLabel("rubric_pending")` 返回 "本题暂无可拆采分点，已先按审题要点收集"（`learning-report-view-model.js:1101`）——**优雅占位**。
- 新用户无作答 → `empty_state="no_evidence"` → "完成一次案例题批改后生成采分点地图"——合理引导。
- **结论**：这是"低价值"而非"破损"体验。over-claim 成"翻车空态"会误导处置方向。

---

## 3. 止血 Runbook：ACTION_LOOP_STAGE 收回（**诚实标注：非干净止血**）

### 3.0 先回答"收回干净吗"——核验结论：**不干净**
- ✅ 关 `ACTION_LOOP_STAGE` 会**干净隐藏**"学习状态推断引擎"卡：`engineEvidenceVisible` 计算含 `featureFlags.action_loop === false → blocked=true → isVisible=false`（`learning-report-view-model.js:815-821`，wxml `report.wxml:71` 父级 `wx:if="{{engineEvidenceVisible}}"`）。
- ⚠️ 但**"采分点怎么补" section 是引擎面板的同级兄弟**（`report.wxml:182` 与 `:71` 同 depth，面板已闭合），它的渲染条件是 `wx:if="{{scoringPointMapItems.length || scoringPointMapEmptyLabel}}"`。关 flag → 后端返 `empty_state="rubric_pending"` → label 非空 → **该 section 仍渲染占位，不隐藏**。
- ⚠️ 关 flag 还会**砍掉 deep_question 练习产生的真采分点**（`grading_key` 档），这部分与 questions_bank 0% 无关、本是正向价值。

> **因此本 runbook 不把"关 flag"当推荐止血动作。** 见 §3.3 推荐选项。若仍要执行关 flag，按 §3.1/§3.2，但须接受上述半截状态。

### 3.1 关 ACTION_LOOP 的 ops 步骤（仅在产品明确决定时执行，本只读单不执行）
> 目标路径 `/root/deeptutor/.env`，落在 AGENTS §3.7 可写边界内。机制同计费 runbook：`docker restart` **不重载 `env_file`**，必须 `up -d --force-recreate`。

| 步 | 动作 | 授权 | 验证 | 回滚 |
| --- | --- | --- | --- | --- |
| 1 | 备份 `.env`：`cp /root/deeptutor/.env /root/deeptutor/.env.bak.20260530` | 写边界内 | `ls -l .env.bak.20260530` | 删备份 |
| 2 | 改键：`LEARNING_STATE_INFERENCE_V2_ACTION_LOOP_STAGE=on` → `off`（**只改这一行；其余三门不动**） | 写边界内 | `grep ACTION_LOOP_STAGE .env` 显示 `=off` | 从 .bak 还原该行 |
| 3 | 重建容器加载新 env：`cd /root/deeptutor && docker compose up -d --force-recreate <api-service>` | 写边界内 | 容器 healthy；`GET /api/v1/mobile/learning-report` 返回 `learning_state_inference.action_loop=false` | `git checkout .env.bak` + 再 `up -d --force-recreate` |
| 4 | 真机/DevTools 复核 | — | 学情页"学习状态推断引擎"卡消失；**确认"采分点怎么补"占位是否可接受**（不可接受则需 §3.3 选项 B 的前端补丁） | 同步 3 |

### 3.2 只动一个子门（硬约束）
**只收 `ACTION_LOOP_STAGE`；`*_EVIDENCE_STAGE` / `*_STATE_PROJECTION_STAGE` / `*_VERIFICATION_STAGE` 维持 `on`**——它们有数据、体验正向、RLS 已验证安全（见决策单 §4）。误关会同时砍掉历史证据/三层画像/复测闭环。

### 3.3 推荐选项（§5 根因优先于症状）
- **选项 A（推荐）——不关 flag，按内容债处理**：空态优雅、练习链路的 `grading_key` 真采分点正常、audited cluster 学生有价值。把它当 §4 的覆盖率赚回，不要为"看起来空"去砍掉正在工作的部分。
- **选项 B（产品坚持隐藏才做）——前端 1 处补丁干净隐藏**：若产品判定"采分点怎么补占位"对多数人是负体验，**干净隐藏需改前端**——让 `scoringPointMapEmptyLabel` 在 `blocked_reason==="feature_flag_off"`（或后端给一个 `empty_state="feature_off"`）时返回 `""`，从而 section 整体不渲染。这是单点表达层改动，比关 flag 干净，且不影响 `grading_key` 真采分点（仅在确实要全局隐藏时）。**本诊断只指出落点，不在此实现。**

---

## 4. 赚回路径：把 map_eligible 抬到 ≥70% 后重开

### 4.1 真正的杠杆 = 给零信号 case 题补采分点（content authoring）
- **范围**：1001 道 `grading_keywords=0` 的 case 题是缺口主体；另有大量有 keywords 但不在 8 audited cluster 的题需扩白名单。
- **为什么不是"跑 compiler"**：§1.3 断点 C——compiler 从已有 keywords 派生，对零 keyword 题无源。除非 Task 13 的 apply executor 配上**真正从 `standard_articles`/`kb_chunks`/教材抽取新采分点**的能力（而非 re-derive），否则 apply 只动 presence、不动 map_eligible。
- **两条可选执行线**：
  1. **教研标注线**：按 `node_code` 簇优先给高频考点簇的 case 题补 `grading_keywords`/`structured_rules`（≥2 点），每补一簇就把该簇 prefix 加进 `_PROJECTED_RUBRIC_ELIGIBLE_CLUSTER_PREFIXES`（当前仅 8 簇）。
  2. **编译抽取线**：实现 Task 13 apply executor + 一个真·采分点抽取器（从标准条文/教材，非 re-derive keywords），过 source-owner sign-off 后 `--apply`。

### 4.2 如何量化覆盖率爬升（可复跑、只读）
- 权威脚本：`scripts/rubric_coverage_report.py`（查 `questions_bank`/`rubrics`/`question_intelligence`，产 raw_rubric / legacy_signal / map_eligible 覆盖）。
- 等价只读 SQL（本诊断所用）：见 §1.3 断点 B 的查询；核心指标 `map_eligible = COUNT(gk≥2 OR sr≥2)/COUNT(case_study)`。
- 真实可见率还要叠加 8 簇白名单——建议同时报 `gk≥2 ∩ audited_cluster` 的交集数，作为"render 可见采分点"的真上限。

### 4.3 重开 ACTION_LOOP 的客观门槛与验证
| 门槛 | 测法 |
| --- | --- |
| `map_eligible ≥ 70%`（计划自设） | `rubric_coverage_report.py` 或 §1.3 SQL |
| audited cluster 覆盖 case 题 ≥ 70% | `node_code` 簇分布 SQL + 白名单同步 |
| 重开后抽样真机：多数 case 题"采分点怎么补"出 ≥2 真采分点而非占位 | DevTools/真机回归 |
| `grading_key` 练习链路不回归 | deep_question 练习一题→学情页采分点出真点 |

> 若先走选项 B 的前端隐藏，则覆盖率达标后**先撤前端隐藏补丁、再确认 action_loop 仍 on**，避免双重 gate 留死代码。

---

## 5. 关联文件 / 代码入口
- 决策单：[2026-05-30-prod-state-and-flag-flip-decision.md](2026-05-30-prod-state-and-flag-flip-decision.md)
- 对照报告：[2026-05-30-plan-vs-code-reconciliation.md](2026-05-30-plan-vs-code-reconciliation.md)
- 学情推断引擎计划：[2026-05-22-luban-learning-state-inference-engine-transformation-plan.md](2026-05-22-luban-learning-state-inference-engine-transformation-plan.md)
- 采分点基线：`docs/qa/2026-05-22-rubric-coverage-baseline.md`
- 代码入口：`deeptutor/services/learner_state/scoring_point_map_read_model.py`（map 投射 + 8 cluster 白名单 + rubric_mode 分档）、`deeptutor/services/learner_state/learning_report_read_model.py:283-302/386`（action_loop gate + `_empty_scoring_point_map`）、`deeptutor/services/construction_grading/case_kernel.py:50-63`（rubric_mode 优先级）、`deeptutor/services/source_compiler/rubric_compiler.py`（candidate 生成）、`scripts/apply_2026_compiler_backfill.py:9`（`--apply` REFUSAL）、`wx_miniprogram/utils/learning-report-view-model.js:815/1101`、`wx_miniprogram/pages/report/report.wxml:71/182`
- 覆盖率脚本：`scripts/rubric_coverage_report.py`

---

*本诊断为 2026-05-30 只读核验快照。所有 ops 步骤待人工在独立"调 flag/部署"步骤中执行；本单未改任何 flag/库/部署。*
