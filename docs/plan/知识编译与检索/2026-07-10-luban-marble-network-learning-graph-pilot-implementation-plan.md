# Luban Marble 式网络计划学习图效果试跑 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不接入 runtime、评分或 LearnerState 的前提下，用同一模型对 20 个冻结网络计划补救案例做 baseline/graph 成对测试，报告 Marble 式 prerequisite projection 是否带来可复现的补救选择提升。

**Architecture:** 先冻结 source pack、8 个 topic-local 微目标、4 条 active hard edge + 2 条 active soft edge和 20 个无标签案例；再用同一 DeepSeek 模型、同一 prompt、同一参数分别运行 baseline 与 graph。ground truth 在模型输出完成前密封，最后由确定性 scorer 解密并计算严格准确率、paired lift、Wilson 区间、bootstrap 区间和安全门。

**Tech Stack:** Python 3.11、标准库 `json/hashlib/statistics/random/urllib`、OpenAI-compatible DeepSeek Chat API、pytest；所有产物落在 `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/`。

## Global Constraints

- 只写 `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/`、`docs/原始数据/数据盘点/scripts/run_learning_graph_pilot_ab.py` 和 `tests/scripts/test_learning_graph_pilot_ab.py`；不改 runtime、TutorBot、评分、LearnerState、数据库或路由。
- active graph 只包含 `01->02`、`02->03`、`05->07`、`06->08` hard，以及 `03->04`、`05->06` soft；`04->05` pending、`06->07` 和 `07->08` rejected 不得注入。
- baseline 与 graph 的 topic definitions、source pack、system prompt、model、参数、max tokens 完全一致；唯一差异是 prerequisite block。
- 运行需要 `LUBAN_LEARNING_GRAPH_PILOT_LIVE=1` 与 `.env` 中的 `DEEPSEEK_API_KEY`；缺少任一条件时只允许跑 shape tests，不得伪造 live 结果。
- 每个 case 必须是独立请求；不复用对话状态、memory、tool result 或 KV cache；模型只能选择一个 topic 或 abstain。
- 试跑产物必须包含输入 hash、prompt hash、model fingerprint、调用数量、原始响应 hash 和 `db_write_count=0`；不得把 exploratory result 写成 runtime/release truth。
- 遵守当前仓库不经用户明确请求不提交 Git 的规则；每个 task 用 `git diff --check` 和指定 pytest/脚本验证，不创建 commit。

---

### Task 1: Freeze source pack, candidate graph, challenge cases and gold commitment

**Files:**
- Create: `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/topics.jsonl`
- Create: `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/dependencies.jsonl`
- Create: `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/source_pack.json`
- Create: `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/cases.jsonl`
- Create: `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/gold.jsonl`
- Create: `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/manifest.json`
- Modify: `docs/plan/INDEX.md`

**Interfaces:**
- `topics.jsonl` 每行字段：`topic_id`、`name`、`mastery_evidence`、`source_refs`；topic id 固定为 `np01` 到 `np08`。
- `dependencies.jsonl` 每行字段：`src`、`dst`、`strength`、`status`、`reason`、`evidence_refs`；只允许 6 条 active edge，另记录 3 条 non-active edge 及拒绝原因。
- `cases.jsonl` 每行字段：`case_id`、`stratum`、`probe_type`、`target_topic_id`、`learner_evidence`、`task`、`source_refs`、`held_out_item=true`。
- `gold.jsonl` 每行字段：`case_id`、`gold_action`、`acceptable_topic_ids`、`forbidden_topic_ids`、`gold_rationale`、`gold_status`；gold 在 A/B 输出冻结前不得被 scorer 读取。

固定 20 个 case，五个 strata 每 4 个：

| Case | Stratum | Probe | Gold action / topic |
|---|---|---|---|
| NP-01 | drawing_virtual_work | prerequisite_needed | select `np01` |
| NP-02 | drawing_virtual_work | prerequisite_needed | select `np02` |
| NP-03 | drawing_virtual_work | prerequisite_needed | select `np01` |
| NP-04 | drawing_virtual_work | teach_target_directly | direct `np02` |
| NP-05 | time_parameters | prerequisite_needed | select `np03` |
| NP-06 | time_parameters | prerequisite_needed | select `np04` |
| NP-07 | time_parameters | prerequisite_needed | select `np03` |
| NP-08 | time_parameters | insufficient_evidence | ask_for_evidence |
| NP-09 | critical_paths | prerequisite_needed | select `np05` |
| NP-10 | critical_paths | prerequisite_needed | select `np02` |
| NP-11 | critical_paths | teach_target_directly | direct `np06` |
| NP-12 | critical_paths | insufficient_evidence | ask_for_evidence |
| NP-13 | delay_claims | prerequisite_needed | select `np05` |
| NP-14 | delay_claims | prerequisite_needed | select `np06` with narrow “affected-work criticality” rationale |
| NP-15 | delay_claims | teach_target_directly | direct `np07` |
| NP-16 | delay_claims | insufficient_evidence | ask_for_evidence |
| NP-17 | optimization | prerequisite_needed | select `np06` |
| NP-18 | optimization | prerequisite_needed | select `np06` |
| NP-19 | optimization | teach_target_directly | direct `np08` |
| NP-20 | optimization | insufficient_evidence | ask_for_evidence |

Source rules:

- `np01` 使用讲义 `page_13_13.json::$[0].content_markdown`；`np02` 使用 `page_17_17.json::$[1]`、`page_18_18.json::$[0]`、`page_19_19.json::$[0]` 四 span bundle。
- `np03` 使用 `page_20_20.json::$[0]`；`np04` 只能标为 source-gap candidate，使用 `page_21_21.json::$[0]` 并记录缺“终点项目工期边界/紧后取小”。
- `np05/np06` 使用教材 `FINAL_CLEANED_BOOK2026-222-382_fixed.json::$.content_blocks[84].content_markdown` 与讲义 `page_20_20.json::$[0]`。
- `np07` 使用讲义 `page_24_24.json::$[0]` 与教材 `$[67].content_markdown`；`np08` 使用教材 `content_blocks[84|85]` 与讲义 `page_27_27.json/page_28_28.json`。
- 真题只作 assessment：2021、2023 可用 `ordinal_match`；2022、2024、2025 只能标 `case_level_only`，不能进入 gold rationale 作为 prerequisite authority。
- 不读取 `keywords`、`synthetic_queries`、`taxonomy_backup_json`、generated rubric、N01 `question_data.expected` 作为 gold source。

执行步骤：

- [ ] 用 `apply_patch` 写入 8 topic records、6 active edge records、3 non-active edge records和 20 case records；每条 source ref 包含 repo path、JSONPath/page、file SHA-256。
- [ ] 将 `gold.jsonl` canonicalize 后计算 plaintext SHA-256；使用 `gpg --symmetric --cipher-algo AES256` 生成 `gold.sealed.jsonl.gpg`，运行 operator 只保留密文和 commitment hash。
- [ ] `manifest.json` 记录 `experiment_id=np_graph_ab_20260710_v1`、`randomization_seed=20260710`、source/topic/graph/case/gold commitment hashes、`published=false`、`runtime_consumable=false`、`db_write_count=0`。
- [ ] 运行 `python -m json.tool source_pack.json`、逐行 JSON parse、source path existence check；预期 20 cases、8 topics、6 active edges、3 non-active edges、0 generated-only refs。
- [ ] 更新 `docs/plan/INDEX.md`，登记本 implementation plan 与 source-only 试跑边界。

### Task 2: TDD deterministic scorer and validity gates

**Files:**
- Create: `tests/scripts/test_learning_graph_pilot_ab.py`
- Create: `docs/原始数据/数据盘点/scripts/run_learning_graph_pilot_ab.py`

**Interfaces:**
- `canonical_json(value) -> str`：UTF-8、sorted keys、compact separators。
- `sha256_jsonl(path) -> str`：按 canonical JSONL 计算 hash。
- `parse_model_response(text) -> dict`：只接受一个 JSON object、一个 decision、最多一个 selected topic；无效/多选返回 `parse_status=invalid`。
- `score_prediction(case, gold, prediction) -> dict`：输出 `correct`、`reason`、`unsupported_claim_count`、`authority_drift`。
- `compare_pairs(rows) -> dict`：输出 `baseline_accuracy`、`graph_accuracy`、`paired_lift_pp`、`graph_wins`、`baseline_wins`、`tie_both_correct`、`tie_both_wrong`、Wilson 95% CI、bootstrap 95% CI、exact McNemar p-value。
- CLI 子命令：`validate`、`run-live`、`score`；`run-live` 无 live flag 或 env flag 时退出码 2。

先写 RED 测试：

- [ ] 测试多选 JSON 被判 invalid，而不是人工挑一个答案。
- [ ] 测试 `select_prerequisite` 只有 selected topic 命中 acceptable 才得分。
- [ ] 测试 `teach_target_directly` 选择任意 prerequisite 必错。
- [ ] 测试 `ask_for_evidence` 只有 abstain/询问才正确。
- [ ] 测试 20 个 pair 中 graph 多答对 3 个得到 `paired_lift_pp=15.0`，并区分 `tie_both_correct` 与 `tie_both_wrong`。
- [ ] 测试 active edge 之外的 `pending/rejected` topic 不允许进入 graph context。

运行：`pytest tests/scripts/test_learning_graph_pilot_ab.py -q`；预期先因函数缺失失败。

最小实现：

- [ ] 只实现上述函数和标准库统计，不引入数据库、框架或新的 graph service。
- [ ] Wilson 区间按二项式 `n` 计算；bootstrap 固定 seed `20260710`、对 20 个 pair 重采样 10,000 次；40 个单独输出不得当作独立样本。
- [ ] scorer 校验 `manifest` 中所有输入 hash 和 output hash；不一致返回 `INVALID`，不继续算效果。
- [ ] authority gate 固定检查 `release_truth`、`answer_key_authority`、`official_score_allowed`、`required_terms` 未被 response 改写；实验产物写入计数固定为 0。

运行：`pytest tests/scripts/test_learning_graph_pilot_ab.py -q`；预期全部通过。

### Task 3: Freeze paired prompts and execute 40 isolated model calls

**Files:**
- Create: `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/prompts/baseline.md`
- Create: `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/prompts/graph.md`
- Create: `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/runs/`

**Interfaces:**
- 两个 prompt 只允许在 `<prerequisite_projection>` block 有差异；system scaffold、JSON schema、source pack、case text、max tokens一致。
- response schema 固定为：`decision` (`select_prerequisite|teach_target_directly|ask_for_evidence`)、`selected_topic_id` (`np01..np08|null`)、`confidence`、`citations`、`teaching_response`、`material_claims`。

执行步骤：

- [ ] 用 `random.Random(20260710)` 洗牌 case 顺序，10 个 pair 为 baseline→graph，10 个为 graph→baseline；生成 `allocations.sealed.jsonl`。
- [ ] 用 `.env` 中 DeepSeek key 运行：
  `LUBAN_LEARNING_GRAPH_PILOT_LIVE=1 python docs/原始数据/数据盘点/scripts/run_learning_graph_pilot_ab.py run-live --model deepseek-chat --temperature 0 --max-output-tokens 1200`。
- [ ] 每个请求创建新 client/session，禁止 conversation reuse；记录 provider fingerprint、usage、prompt hash、raw response hash、错误但不重写 response。
- [ ] 输出 `outputs.internal.jsonl`（含 arm）和 `outputs.blinded.jsonl`（不含 arm）；40 个 pair 不完整、fingerprint 变化、context truncation 或 hash mismatch 时整轮 `run_invalid`。
- [ ] 运行 operator 不读取 `gold.sealed.jsonl.gpg` 的明文，不在输出前修改 cases、topics、source pack 或 graph。

### Task 4: Blind review, reveal gold, calculate and publish effect report

**Files:**
- Create: `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/reviews.blinded.jsonl`
- Create: `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/paired_results.revealed.jsonl`
- Create: `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/evaluation.json`
- Create: `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/report.md`

执行步骤：

- [ ] 先将 `outputs.blinded.jsonl` 交给不知道 arm 的独立 reviewer，只标 `unsupported_material_claims` 与 `semantic_authority_drift`；reviewer 不得读取 graph block、prompt 文件名或 pair allocation。
- [ ] reviewer 结束后才解密 gold；运行 `score` 生成每 case 的 baseline/graph correctness、pair outcome 和安全指标。
- [ ] 报告同时列出全部 20 个 case、graph wins、baseline wins、两个 tie、五 strata 分布；不得只展示 graph wins。
- [ ] 依据以下门输出唯一 verdict：
  - `INVALID`：任一 hash、40-call、gold-seal、模型 fingerprint 或 prompt sole-difference gate 失败。
  - `STOP`：authority drift>0、unsupported material claim>0、negative controls graph<8/8。
  - `INCONCLUSIVE_POSITIVE_SIGNAL`：valid/safe，但 graph<16/20 或 paired lift<15pp。
  - `SIGNAL_PASS`：valid/safe、graph≥16/20、paired lift≥15pp、baseline_wins≤1、五 strata 无净负向。
  - `CONFIRMATORY_PASS`：在 SIGNAL_PASS 上另加 paired lift bootstrap 95% CI 下界>0 且 exact McNemar p<0.05；否则不得写 confirmatory。
- [ ] 将真实结果写回 `evaluation.json/report.md`，明确这是“补救选择效用”而非学员学习增益，也不能区分图结构收益与额外结构化文字收益。

### Task 5: Final verification and user-facing decision

**Files:**
- Modify: `docs/plan/INDEX.md` only if final report path needs registration.

验证命令：

- [ ] `pytest tests/scripts/test_learning_graph_pilot_ab.py -q`，记录 0 failures。
- [ ] `python docs/原始数据/数据盘点/scripts/run_learning_graph_pilot_ab.py validate`，记录 8 topics、6 active edges、20 cases、all hashes valid。
- [ ] `python docs/原始数据/数据盘点/scripts/run_learning_graph_pilot_ab.py score`，读取完整 `evaluation.json` 与 `report.md`。
- [ ] `git diff --check`；`rg -n 'TODO|TBD|PLACEHOLDER'` 对新增文档与脚本无输出；`git status --short` 确认没有 runtime/评分/LearnerState 文件被改动。

最终答复必须直接告诉用户：baseline/graph 各自准确率、paired lift、graph wins/baseline wins、是否过 SIGNAL_PASS、主要提升和退化 case、是否值得继续；若 INVALID/STOP，明确不能把结果写成效果证明。
