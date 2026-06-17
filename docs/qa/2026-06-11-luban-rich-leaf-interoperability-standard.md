# 鲁班 RichLeaf 编译互操作标准 v0

状态：`candidate workbench standard`

日期：2026-06-11

最近更新：2026-06-12，补入 fail-open guard diagnostic、nearline retrieval projection A/B、live-runtime A/B preflight、fail-closed live A/B runner、near-live local adapter smoke、50-case near-live shadow A/B、shadow residual work orders、shadow residual review packets、shadow residual review decision validation、shadow residual review decision seed、AI-council shadow review decisions、shadow residual audit record、shadow residual guard patch plan、shadow residual guard review packets、shadow residual guard review decisions、shadow residual guard review decision validation、shadow residual guard audit record、Learning Evidence candidate bridge、PCP/NBA candidate projection、test-learner sandbox readback gate、authorized writeback preflight、test-learner writeback authorization package、dry-run manifest、execution gate、current-standard compat audit 与 external-source closure，并将 interop audit 覆盖面提升到 49 个 workbench 产物。

本文档是当前 RichLeaf 编译工作的统一标准。它不是 release truth，也不是 runtime default 授权；它只规定候选编译产物如何互相配合、如何被审计、以及哪些边界不能跨越。

机器可执行 authority 在：

- `deeptutor/services/construction_grading/rich_leaf_artifacts.py`：RichLeafArtifact / CompiledContextPack 的字段级 validator 与 pack contract。
- `deeptutor/services/construction_grading/rich_leaf_workbench_contracts.py`：所有 workbench stage name、schema id、顺序和 claim ceiling 的单一注册表。
- `scripts/run_luban_rich_leaf_interop_audit.py`：从上述注册表读取 schema，并审计 49 个 workbench 产物之间的 join keys、source lane、review-only 状态和 safety flags。

后续新增任何编译步骤，必须先补 `rich_leaf_workbench_contracts.py` 与 interop audit 测试，再生成产物；不得在单个 runner 里私自创造 schema 或把 Markdown 当唯一标准。

统一标准的短定义：

```text
RichLeaf workbench 只允许沿一个 schema flow 传递字段级 claim；
只允许用 source_lane + claim_status 决定字段能否进入 task-specific context pack；
只允许把 near-live shadow rows 投影为 review-only learning_evidence candidate，不允许写 learner memory；
只允许把 learning_evidence candidate 投影为 PCP/NBA dry-run candidate，不允许生成正式 PersonalizationContextPack、training_intent 或 NextBestAction；
只允许把候选 evidence 写入 artifact-only sandbox JSONL 并读回验证过滤，不允许调用 LearnerStateService 写真实 memory；
只允许把 test-learner writeback 前置条件渲染成 authorization preflight，不允许把 preflight 当授权；
只允许把授权评审材料渲染成 authorization package，不允许把 package 当授权结果或写入器；
只允许把未来写回批次渲染成 dry-run manifest，不允许绑定真实 learner 或执行写入；
只允许把真实写回执行门渲染成 blocked execution gate，不允许在缺签名授权时继续执行；
只允许审计 RichLeaf candidate 是否符合当前 Learning Brain 标准读回，不允许把 candidate 加进 `learning_synthesis` 或写 learner memory；
只允许对 `needs_external_source` 记录做 review-only 重检索或保留 `external_source_required`，不允许把题库上下文硬塞成教材/规范/讲义支撑；
只允许把 shadow residual audit record 渲染成 review-only guard patch plan，不允许生成 patch 或执行 runtime guard；
只允许把 guard patch plan 渲染成 reviewer 输入包，不允许记录 reviewer decision 或执行 guard；
只允许把 guard review packets 渲染成 AI-council shadow decisions，不允许声称人类/治理签署或执行 guard；
只允许校验 guard review decisions 的覆盖率、合法性、重复/stale 与越权，不允许生成 audit record、patch 或执行 runtime guard；
只允许把 validated guard review decisions 固化为 review-only guard audit record，不允许生成 patch、修改 source_ref 或执行 runtime guard；
只允许由 interop audit 判断产物之间是否可配合；
任何 projection/offline/nearline A/B 都不能升级为 release truth 或 production default。
```

## 1. 一等业务事实

RichLeaf 编译层维护的唯一业务事实是：

```text
某个 canonical leaf 的某个字段级知识 claim，是否有可追溯 source evidence 支撑，并处于什么审核状态。
```

它不维护：

- 官方评分真相。
- 学生长期画像真相。
- runtime 默认知识供给。
- 生产 DB 写入状态。

这些事实分别属于评分治理、Learning Brain、runtime supply registry 和生产发布链路。

## 2. 单一 Authority 分层

| 层 | Authority | 允许写什么 | 不允许写什么 |
|---|---|---|---|
| schema/validator | `deeptutor/services/construction_grading/rich_leaf_artifacts.py` | RichLeafArtifact v0、CompiledContextPack v0、字段级校验 | canonical truth / official score |
| sampler | `scripts/run_luban_rich_leaf_phase1_sampler.py` | deterministic sample manifest | runtime supply |
| skeleton compiler | `scripts/run_luban_rich_leaf_skeleton_compiler.py` | candidate skeleton RichLeafArtifact batch | rich semantic fields 的 source-backed claim |
| source-gap finder | `scripts/run_luban_rich_leaf_source_gap_candidates.py` | review-only source candidates | 安装 source_ref |
| candidate patch generator | `scripts/run_luban_rich_leaf_candidate_patch_generator.py` | review-only add_source_ref_candidate patch | 自动 apply patch |
| patch evidence auditor | `scripts/run_luban_rich_leaf_patch_evidence_audit.py` | review-only machine precheck audit | 自动接受 patch 或安装 runtime |
| rejected patch feedback | `scripts/run_luban_rich_leaf_rejected_patch_feedback.py` | review-only rejected patch work orders | 复用 rejected source_ref 或提升到 runtime |
| semantic audit packet generator | `scripts/run_luban_rich_leaf_semantic_audit_packets.py` | AI/人类 semantic evidence audit 输入包 | 记录 semantic verdict 或安装 runtime |
| weak refinement | `scripts/run_luban_rich_leaf_weak_source_refinement.py` | source authority gap work order | 把 weak/no-candidate 升级为 strong |
| source-evidence agent | `scripts/run_luban_rich_leaf_source_evidence_agent.py` | review-only lane-matched source evidence candidates for weak work orders | 把候选证据写成 source truth 或 runtime supply |
| semantic audit queue | `scripts/run_luban_rich_leaf_semantic_audit_queue.py` | 统一审核队列，合并 patch semantic packets 与 source-evidence candidates | 记录 accepted/rejected verdict 或安装 runtime |
| semantic review shards | `scripts/run_luban_rich_leaf_semantic_review_shards.py` | 将 semantic audit queue 切成 reviewer 可并行处理的输入分片 | 记录 reviewer 决策或改变 queue/record |
| semantic review suggestions | `scripts/run_luban_rich_leaf_semantic_review_suggestions.py` | 为 reviewer 生成 suggestion-only triage hints，暴露 exact-leaf、parent-only、pollution 风险 | 作为正式 decision 被 validation/audit record 消费 |
| semantic decision seed | `scripts/run_luban_rich_leaf_semantic_decision_seed.py` | 仅对无 `source_candidate` 的 unresolved source gap 生成 `needs_external_source` 决策种子 | 接受、拒绝或改写任何有候选 source_ref 的语义项 |
| semantic review decision validation | `scripts/run_luban_rich_leaf_semantic_review_decision_validation.py` | 收集并校验 shard reviewer 决策文件，输出合并 decisions 与覆盖报告 | 将非法/缺失决策写成 accepted/rejected，或绕过 audit record |
| semantic evidence audit record | `scripts/run_luban_rich_leaf_semantic_evidence_audit_record.py` | review-only semantic decision record；无 reviewer 决策时标 not_exercised | 升级为 release truth、official score 或 runtime supply |
| reviewed candidate builder | `scripts/run_luban_rich_leaf_reviewed_candidate_builder.py` | 仅把 recorded + accept_source_ref_candidate 的 semantic audit record 转成 reviewed source_ref candidates | 从 not_exercised/invalid/rejected 记录生成候选，或安装 runtime |
| runtime supply candidate builder | `scripts/run_luban_rich_leaf_runtime_supply_candidate_builder.py` | 将 reviewed source_ref candidates 打包为可回归评测的 versioned runtime_supply candidate | 写入 `runtime_supply/`、canonical pointer、production default 或 official score |
| runtime supply regression gate | `scripts/run_luban_rich_leaf_runtime_supply_regression.py` | 对 runtime_supply candidate 做静态任务投影、安全不变量和 question-lane 污染回归检查 | 安装 runtime supply、写 canonical pointer、证明 semantic runtime win |
| rich field candidate compiler | `scripts/run_luban_rich_leaf_field_candidate_compiler.py` | 仅从已审核 source_ref span 中抽取 review-only rich field candidates | 组装 RichLeafArtifact、把 question lane 当知识原文、写 runtime/default |
| artifact candidate assembler | `scripts/run_luban_rich_leaf_artifact_candidate_assembler.py` | 将 review-only rich field candidates 组装成可由 `rich_leaf_artifacts.py` validator 检查的 RichLeafArtifact candidates | 把 candidate-only 字段升级为 source_backed、安装 runtime/default |
| field promotion review | `scripts/run_luban_rich_leaf_field_promotion_review.py` | 按 source lane / field family taxonomy 将 validator-clean artifact candidate 的字段归类为 `source_backed`、`assessment_evidence` 或继续 `candidate_only` | 写 runtime/default、宣称 release truth、把 question lane 升成 source-backed knowledge |
| context pack smoke | `scripts/run_luban_rich_leaf_context_pack_smoke.py` | 调用 `build_compiled_context_pack()` 验证 promoted fields 的 task-specific 投影、source_ref 追溯和 question-lane 隔离 | 证明线上效果、安装 runtime/default、绕过胖内核直接读 workbench JSON |
| fail-open guard diagnostic | `scripts/run_luban_rich_leaf_fail_open_guard_diagnostic.py` | 从 field promotion review 与 context pack smoke 渲染 review-only 诊断，列出 candidate `negative_evidence` 最密集的 leaves、source lanes、record ids 与 guard suggestion | 证明 runtime fail-open 已降低、允许 quality claim、安装 runtime/default、写 learner memory |
| context pack projection A/B | `scripts/run_luban_rich_leaf_context_pack_projection_ab.py` | 对比 candidate-only baseline 与 promoted treatment 的 task-pack 字段覆盖、source_ref 追溯和污染风险 | 宣称 accuracy/latency/token semantic win、允许 quality claim、安装 runtime/default |
| semantic runtime offline A/B | `scripts/run_luban_rich_leaf_semantic_runtime_offline_ab.py` | 用确定性 offline adapter 检查 promoted context 是否能为 source-backed eval cases 提供带 citation 的 answer，同时 baseline 空上下文 fail-closed abstain | 调用 live LLM、证明线上 accuracy/latency/token、写 runtime/default |
| semantic runtime nearline A/B | `scripts/run_luban_rich_leaf_semantic_runtime_nearline_ab.py` | 用本地 lexical retrieval proxy 对比 empty baseline / current RAG projection / promoted context pack，检查 answerable、citation、token proxy、fail-open | 代表生产 RAG、调用 live LLM、证明线上 accuracy/latency/token、写 runtime/default |
| semantic runtime live A/B preflight | `scripts/run_luban_rich_leaf_semantic_runtime_live_ab_preflight.py` | 校验 field promotion 与 nearline A/B 是否满足进入真实 runtime A/B 的前置条件，并产出 planned arms / runtime_entry / provider_call_policy / not_exercised_by_layer | 执行 provider、执行生产 RAG、记录 live win、允许 quality claim、写 runtime/default |
| semantic runtime live A/B | `scripts/run_luban_rich_leaf_semantic_runtime_live_ab.py` | fail-closed live A/B runner contract；默认阻止 provider/生产 RAG，要求显式授权后才能执行真实 runtime arms | 把 preflight/nearline 指标升级为 live win、绕过 provider 授权、允许 quality claim、写 runtime/default |
| semantic runtime near-live smoke | `scripts/run_luban_rich_leaf_semantic_runtime_near_live_smoke.py` | 用 `local_compiled_context_adapter` 真实构建 `CompiledContextPack` 并跑 10 条本地 runtime-facing smoke，检查 answer/citation/fail-open/question-lane citation | 代表生产 RAG、调用 live LLM、记录真实线上 latency/token、允许 quality claim、写 runtime/default |
| semantic runtime near-live shadow A/B | `scripts/run_luban_rich_leaf_semantic_runtime_near_live_shadow_ab.py` | 将 local adapter smoke 扩展为 50-case shadow，对比 `current_rag_lexical_proxy` 与 `rich_leaf_local_adapter` 的 answerable/citation/token/fail-open | 代表生产 RAG、调用 live LLM、证明线上 accuracy/latency/token、允许 quality claim、写 runtime/default |
| shadow residual work orders | `scripts/run_luban_rich_leaf_shadow_residual_work_orders.py` | 将 near-live shadow 的可追溯 runtime residual 与 fail-open guard diagnostic 转成 review-only compiler work orders，并把无 leaf_id 的 residual 留作 non-joinable 诊断 | 生成 patch、修改 source_ref、执行 runtime guard、允许 quality claim、写 learner memory |
| shadow residual review packets | `scripts/run_luban_rich_leaf_shadow_residual_review_packets.py` | 将 shadow residual work orders 渲染为 reviewer 输入包，包含 trace、review questions 和 allowed decisions | 记录 reviewer decision、生成 patch、修改 source_ref、执行 runtime guard、允许 quality claim |
| shadow residual review decision validation | `scripts/run_luban_rich_leaf_shadow_residual_review_decision_validation.py` | 校验 shadow residual review decisions 是否覆盖当前 packets、决策值是否合法、是否存在越权或 stale decisions | 生成 audit record、生成 patch、修改 source_ref、执行 runtime guard、允许 quality claim |
| shadow residual review decision seed | `scripts/run_luban_rich_leaf_shadow_residual_review_decision_seed.py` | 对缺 reviewer decision 的 shadow residual review packets 生成 suggestion-only 决策种子，帮助 reviewer/AI council 审核 | 记录正式 decision、回灌 validation、生成 patch、修改 source_ref、执行 runtime guard、允许 quality claim |
| shadow residual review decisions | `scripts/run_luban_rich_leaf_shadow_residual_review_decision_materializer.py` | 将已生成 seed 与 packets 合成为 `ai_council_shadow_only` 的 review decisions，供 validation 读取 | 人类/治理签署、生成 patch、修改 source_ref、执行 runtime guard、允许 quality claim |
| shadow residual audit record | `scripts/run_luban_rich_leaf_shadow_residual_audit_record.py` | 将 validated shadow decisions 固化为 review-only audit records，并把后续动作分类为 guard/source-ref/retaxonomy/dismissal | 生成 patch、修改 source_ref、执行 runtime guard、允许 quality claim、写 learner memory |
| shadow residual guard patch plan | `scripts/run_luban_rich_leaf_shadow_residual_guard_patch_plan.py` | 仅把 `guard_review_required` audit records 转成 review-only guard plan items，并保留 source-ref/retaxonomy/dismissal 统计 | 生成 patch、修改 source_ref、执行 runtime guard、安装 runtime、允许 quality claim、写 learner memory |
| shadow residual guard review packets | `scripts/run_luban_rich_leaf_shadow_residual_guard_review_packets.py` | 将 guard plan items 渲染为 reviewer 输入包，包含 allowed decisions、review questions 和 evidence trace | 记录 reviewer decision、生成 patch、修改 source_ref、执行 runtime guard、安装 runtime、允许 quality claim、写 learner memory |
| shadow residual guard review decisions | `scripts/run_luban_rich_leaf_shadow_residual_guard_review_decisions.py` | 将 guard review packets materialize 为 `ai_council_shadow_only` decisions，供后续 validation 读取 | 人类/治理签署、生成 patch、修改 source_ref、执行 runtime guard、安装 runtime、允许 quality claim、写 learner memory |
| shadow residual guard review decision validation | `scripts/run_luban_rich_leaf_shadow_residual_guard_review_decision_validation.py` | 校验 guard review decisions 是否覆盖当前 packets、决策值是否合法、是否重复/stale/越权 | 生成 audit record、生成 patch、修改 source_ref、执行 runtime guard、安装 runtime、允许 quality claim、写 learner memory |
| shadow residual guard audit record | `scripts/run_luban_rich_leaf_shadow_residual_guard_audit_record.py` | 将 validated guard review decisions 固化为 review-only guard audit records，并记录下一步 compiler action 分类 | 生成 patch、修改 source_ref、执行 runtime guard、安装 runtime、允许 quality claim、写 learner memory |
| learning evidence candidate bridge | `scripts/run_luban_rich_leaf_learning_evidence_candidate_bridge.py` | 将 near-live shadow 的 local adapter rows 投影为 `memory_kind=learning_evidence` / `event_type=learning_evidence` 的 review-only candidate payload | 写 `learner_memory_events`、生成 canonical learner truth、生成 PersonalizationContextPack/NextBestAction、宣称学习效果 |
| PCP/NBA candidate projection | `scripts/run_luban_rich_leaf_pcp_nba_candidate_projection.py` | 将 `learning_evidence` candidates 投影为 `PersonalizationContextPackCandidate` 与 `next_action_candidate` dry-run 形状 | 触发 `learning_synthesis`、生成正式 `PersonalizationContextPack` readback、创建 `training_intent`、生成正式 NextBestAction |
| test-learner sandbox readback gate | `scripts/run_luban_rich_leaf_test_learner_sandbox_readback_gate.py` | 将 candidate evidence 写入 artifact-only sandbox JSONL，读回为 `LearnerStateEvent` shape，并用 dry-run synthesis 验证不会进入 observed/compiled truth | 调用 `append_memory_event`、写真实 `MEMORY_EVENTS.jsonl`/outbox/DB、生成 canonical learner truth |
| authorized writeback preflight | `scripts/run_luban_rich_leaf_authorized_writeback_preflight.py` | 汇总 sandbox/readback/PCP-NBA candidate 结果，声明进入真实 test-learner writeback 前缺哪些授权 | 执行 test learner 写回、把授权字段翻 true、写 canonical truth、写生产 DB |
| test-learner writeback authorization package | `scripts/run_luban_rich_leaf_test_learner_writeback_authorization_package.py` | 将 preflight 结果整理为待用户/治理审查的授权决策包，明确候选范围、rollback 草案和仍缺授权 | 记录用户已授权、执行写回、批准 rollback、写 canonical truth、写生产 DB |
| test-learner writeback dry-run manifest | `scripts/run_luban_rich_leaf_test_learner_writeback_dry_run_manifest.py` | 从 sandbox readback 与 authorization package 生成 artifact-only 写回批次预演、幂等键和 rollback selector | 绑定真实 learner、调用写入服务、允许 rollback、写 canonical truth、写生产 DB |
| test-learner writeback execution gate | `scripts/run_luban_rich_leaf_test_learner_writeback_execution_gate.py` | 在无签名授权、无具体 test learner、rollback 未批准时输出 blocked execution gate | 把 dry-run ready 升级成可写、执行 learner memory 写入、写 canonical truth、写生产 DB |
| Learning Evidence current-standard compat audit | `scripts/run_luban_rich_leaf_learning_evidence_current_standard_compat_audit.py` | 只读审计 RichLeaf candidate events / PCP candidates / sandbox / dry-run / execution gate 是否仍未进入当前 Learning Brain 标准读回 | 把 `rich_leaf_shadow_candidate` 加入正式 source_feature、触发 `learning_synthesis`、生成正式 PCP/NBA、写 learner memory、写 canonical truth |
| external-source closure | `scripts/run_luban_rich_leaf_external_source_closure.py` | 对 semantic audit record 中的 `needs_external_source` 做 review-only source 复检，找到候选则仍待审核，找不到则保留 `external_source_required` | 把 question context 当支撑 source_ref、写 source truth、修改 source_ref、安装 runtime、允许 quality claim |
| runtime supply | `deeptutor/services/construction_grading/runtime_supply/` | signed/versioned runtime bundles | 接受未审核 workbench candidate |

Thin wrapper 规则：CLI 只负责读写 JSON 和参数，业务判断必须在可测试函数内完成。

## 3. 统一 Schema 流

当前 RichLeaf workbench 的合法产物流如下：

```text
sample_manifest
-> rich_leaf_skeleton_candidates
-> source_gap_candidates
-> candidate_patches
-> patch_evidence_audit
-> rejected_patch_feedback for machine_reject rows
-> semantic_audit_packets for machine_precheck_pass rows
-> semantic_audit_queue
-> semantic_review_shards
-> semantic_review_suggestions for reviewer triage only
-> semantic_decision_seed for deterministic unresolved source gaps
-> semantic_review_decision_validation
-> semantic_evidence_audit_record
-> reviewed rich artifact candidate
-> versioned runtime_supply candidate
-> runtime_supply static regression
-> rich field candidate compilation
-> RichLeafArtifact candidate assembly
-> field promotion review
-> CompiledContextPack smoke
-> fail-open guard diagnostic
-> context pack projection A/B
-> semantic runtime offline A/B
-> semantic runtime nearline A/B
-> semantic runtime live A/B preflight
-> semantic runtime live A/B
-> semantic runtime near-live smoke
-> semantic runtime near-live shadow A/B
-> shadow residual work orders
-> shadow residual review packets
-> shadow residual review decision validation
-> shadow residual review decision seed for missing packet triage only
-> shadow residual review decisions as AI-council shadow-only decisions
-> shadow residual review decision validation rerun
-> shadow residual audit record for action classification only
-> shadow residual guard patch plan for review-only guard planning
-> shadow residual guard review packets for reviewer input only
-> shadow residual guard review decisions as AI-council shadow-only decisions
-> shadow residual guard review decision validation
-> shadow residual guard audit record for action classification only
-> learning evidence candidate bridge
-> PCP/NBA candidate projection
-> test-learner sandbox readback gate
-> authorized writeback preflight
-> test-learner writeback authorization package
-> test-learner writeback dry-run manifest
-> test-learner writeback execution gate
-> Learning Evidence current-standard compat audit
-> external-source closure
-> regression A/B
-> controlled default decision
```

并行诊断流：

```text
source_gap_candidates
-> weak_source_refinement_work_orders
-> source-evidence agent 扩语料/重检索/拆 leaf
-> source_evidence_agent_candidates
-> semantic_audit_queue
-> semantic_review_shards
-> semantic_review_suggestions for reviewer triage only
-> semantic_decision_seed for deterministic unresolved source gaps
-> semantic_review_decision_validation
-> semantic_evidence_audit_record
-> reviewed rich artifact candidate
```

任何流程不得跳过 `reviewed rich artifact candidate -> runtime_supply candidate -> regression A/B`。

## 4. 互操作 Join Keys

所有产物必须保留以下 join keys：

| Key | 用途 |
|---|---|
| `leaf_id` | 对齐 canonical taxonomy leaf |
| `artifact_id` | 对齐 skeleton / source gap / patch / work order |
| `missing_lane` | 表示缺失的 source lane |
| `source_lane` | 表示候选证据自身 lane，必须等于 `missing_lane` 才能作为 support candidate |
| `record_id` | 源记录可追溯 ID |
| `span` | 可审查原文片段 |
| `span_hash` / `hash` | 原文片段稳定 hash |
| `candidate_only` | 明确候选状态 |
| `install_allowed` / `apply_allowed` / `runtime_install_allowed` | 必须默认 false |

禁止靠 `name_path`、`snippet` 或 `matched_terms` 单独 join。它们只辅助 reviewer，不是稳定 ID。

## 5. Source Lane Taxonomy

当前合法 source lanes：

```text
textbook | standard | lecture | question
```

含义：

| Lane | 可支持什么 | 不可支持什么 |
|---|---|---|
| `textbook` | 教材原文、教材型 source clause | 真题解析、练习题、考生答卷 |
| `standard` | 规范/标准条文原文 | 标准答案解析 |
| `lecture` | 讲义/课件原文 | 学生答题材料 |
| `question` | 真题、练习题、答案解析、学生答卷、考试趋势 | 不能作为 textbook/standard/lecture support evidence |

Practice / exam / MCQ / 答案解析材料的规则：

```text
只要 source 形态显示为 exercise/question/MCQ/practice/必刷/千题/题斩/考证宝典/真题/答案解析/学生答卷，
即使 metadata 写着 source_type=TEXTBOOK，也必须降级为 question lane。
```

`question` 可以作为 query context，说明“这个 leaf 被考过 / 学生如何作答”，但不能作为教材、规范、讲义 source support。

## 6. 状态 Taxonomy

### Candidate Status

RichLeafArtifact 顶层：

```text
candidate | reviewed_candidate | release_candidate | superseded
```

### Field Claim Status

字段级 claim：

```text
source_backed | learner_evidence | assessment_evidence | candidate_only | needs_review | hypothesis
```

### Workbench Output Status

source-gap:

```text
strong_candidate_sources_found | weak_candidate_sources_found | no_candidate_sources_found
```

patch:

```text
pending_review
```

patch evidence audit:

```text
machine_precheck_pass | machine_reject | needs_semantic_review
```

rejected patch feedback:

```text
rejected_patch_feedback
```

weak refinement:

```text
source_authority_gap
```

## 7. 安全不变量

所有 workbench 产物必须满足：

```json
{
  "candidate_only": true,
  "review_only": true,
  "canonical_truth_written": false,
  "official_score_allowed": false,
  "installed_runtime_supply": false,
  "production_write_count": 0,
  "release_truth_claimed": false
}
```

术语约定：`sample_manifest` 与 `skeleton` 阶段可使用 `review_required=true` 表达同一条 review-only discipline；进入 source-gap、patch、weak-refinement 以后统一使用 `review_only=true`。两者都不表示可 runtime install 或 release truth。

Patch / work order 额外必须满足：

```json
{
  "apply_allowed": false,
  "patches_apply_allowed": false,
  "work_orders_apply_allowed": false,
  "runtime_install_allowed": false,
  "promotion_allowed": false
}
```

## 8. RichLeaf Core Field Families

最终 RichLeafArtifact 的目标字段族是：

```json
{
  "concepts": [],
  "definitions": [],
  "rules": [],
  "procedures": [],
  "numeric_constraints": [],
  "common_mistakes": [],
  "exam_patterns": [],
  "source_refs": [],
  "negative_evidence": [],
  "teaching_cards": [],
  "rubric_link_index": [],
  "learner_memory_event_templates": []
}
```

命名边界：业务讨论里的 `grading_relevance` 不作为 RichLeaf 顶层字段存在。评分相关性统一由 `rubric_link_index` 表达，且只存 scoring artifact / rubric / scoring point 引用，不复制 rubric policy、不生成第二套评分 authority。

当前已落地的是 Phase 0/1 workbench：schema/validator、sample、skeleton、source-gap、candidate patch、weak work order。Rich semantic fields 的全量抽取尚未完成，不能把 skeleton 当作完整 rich leaf。

## 9. Runtime Consumption 标准

Runtime 只能消费 `CompiledContextPack` 或 signed/versioned runtime supply candidate，不能直接消费：

- `source_gap_candidates.json`
- `candidate_patches.json`
- `patch_evidence_audit.json`
- `rejected_patch_feedback_work_orders.json`
- `semantic_audit_packets.json`
- `source_evidence_agent_candidates.json`

Source-evidence agent 不得维护第二套源材料分类规则。源材料读取、路径/metadata lane
识别、practice/question 污染源识别必须复用 `run_luban_rich_leaf_source_gap_candidates.py`
的 source record loader；`record_count_by_lane` 只允许出现 `textbook`、`standard`、
`lecture`、`question`。`residual`、`unknown` 或任何临时 lane 进入
`source_evidence_agent_candidates.json` 都是 interop blocker，而不是可忽略 warning。

Semantic review decision validation 必须只合并当前 shard audit ids 的决策。历史
audit queue 产生的旧 `audit_item_id` 不得进入 `merged_semantic_audit_decisions.json`；
它们必须落入 `stale_decisions_ignored` 并计入 `stale_decision_count`。这类 stale
隔离不是 accept/reject，不允许补足 coverage；真正缺少当前决策时 verdict 只能是
`INCOMPLETE`，非法或重复决策仍为 `FAIL`。
- `semantic_audit_queue.json`
- `semantic_review_shards_manifest.json`
- `semantic_review_suggestions.json`
- `semantic_decision_seed_unresolved.json`
- `semantic_review_decision_validation.json`
- `merged_semantic_audit_decisions.json`
- `semantic_evidence_audit_record.json`
- `reviewed_rich_leaf_candidates.json`
- `rich_leaf_runtime_supply_candidate.json`
- `runtime_supply_regression.json`
- `rich_leaf_field_candidates.json`
- `rich_leaf_artifact_candidates.json`
- `field_promotion_review.json`
- `context_pack_smoke.json`
- `fail_open_guard_diagnostic.json`
- `context_pack_projection_ab.json`
- `semantic_runtime_offline_ab.json`
- `semantic_runtime_nearline_ab.json`
- `live_ab_preflight.json`
- `near_live_smoke.json`
- `near_live_shadow_ab.json`
- `shadow_residual_work_orders.json`
- `shadow_residual_review_packets.json`
- `shadow_residual_review_decision_validation.json`
- `shadow_residual_review_decision_seed.json`
- `ai_council_shadow_review_decisions.json`
- `shadow_residual_audit_record.json`
- `shadow_residual_guard_patch_plan.json`
- `shadow_residual_guard_review_packets.json`
- `shadow_residual_guard_review_decisions.json`
- `shadow_residual_guard_review_decision_validation.json`
- `shadow_residual_guard_audit_record.json`
- `merged_shadow_residual_review_decisions.json`
- `merged_shadow_residual_guard_review_decisions.json`
- `learning_evidence_candidate_bridge.json`
- `pcp_nba_candidate_projection.json`
- `test_learner_sandbox_readback_gate.json`
- `sandbox_memory_events.jsonl`
- `authorized_writeback_preflight.json`
- `test_learner_writeback_authorization_package.json`
- `test_learner_writeback_dry_run_manifest.json`
- `test_learner_writeback_execution_gate.json`
- `current_standard_compat_audit.json`
- `weak_source_refinement_work_orders.json`
- 未审核 skeleton batch

Context pack 必须按任务裁剪字段：

| Task | 允许字段 |
|---|---|
| grading | `rubric_link_index`, `rules`, `numeric_constraints`, `negative_evidence`, `source_refs` |
| tutoring | `concepts`, `definitions`, `procedures`, `teaching_cards`, `rules`, `source_refs`, `common_mistakes` |
| rag_answer | `definitions`, `rules`, `procedures`, `source_refs` |
| next_action | `teaching_cards`, `exam_patterns`, `common_mistakes`, `learner_memory_event_templates`, `source_refs` |
| review | 全字段候选视图 |

`source_refs` 只能随已消费字段追溯进入 pack。禁止把同一 artifact 的全部 source_refs 无差别带入任务 pack；这会让 question-lane evidence 通过 source_ref 旁路污染 RAG / tutoring / grading。

`review` task 是唯一例外：它可以显示 `candidate_only` / `needs_review` / `hypothesis` 字段及其 source_ref，用于 evidence auditor 和 reviewer 查看错 leaf、污染源、待审模板等候选材料。该视图不是 positive runtime context；不得被 `grading`、`tutoring`、`rag_answer` 或 `next_action` 复用为学生可见事实。

### 9.1 Learning Brain Bridge 标准

`learning_evidence_candidate_bridge` 只能证明 RichLeaf runtime-facing shadow rows 能被下游 Learning Brain 识别为候选 evidence payload。它必须保持：

```json
{
  "memory_kind": "learning_evidence",
  "event_type": "learning_evidence",
  "candidate_only": true,
  "preview_only": true,
  "claim_promotion_allowed": false,
  "canonical_truth_written": false,
  "quality": {
    "writeback_eligible": false,
    "progress_countable": false,
    "truth_eligible": false,
    "stable_truth_eligible": false
  }
}
```

该桥接不调用 `LearnerStateService.append_memory_event`，不写 `learner_memory_events`，不触发 `synthesize_learning_truth`，不生成正式 `PersonalizationContextPack` 或 `NextBestAction`。这些步骤必须显式标记为 `not_exercised`，直到真实 learner evidence、治理签署和 readback 验证完成。

### 9.2 PCP/NBA Candidate Projection 标准

`pcp_nba_candidate_projection` 只能证明候选 evidence 的字段形状足以继续投影到个性化候选，不代表 Learning Brain 已经读回或生成处方。它必须保持：

```json
{
  "source": "PersonalizationContextPackCandidate",
  "candidate_only": true,
  "readback_verified": false,
  "authority": {
    "evidence": "learning_evidence_candidate_bridge",
    "claims": "candidate_projection_not_learning_synthesis",
    "prescription": "not_exercised_training_intent"
  }
}
```

`next_action_candidates` 只能使用 `prescription_authority=not_exercised_training_intent` 和 `status=candidate_not_prescription`。不得写 `training_intent`、不得声称 `PersonalizationContextPack` 已 readback、不得把 candidate action 当正式 NextBestAction。

### 9.3 Test-Learner Sandbox Readback 标准

`test_learner_sandbox_readback_gate` 只允许写 artifact-only sandbox JSONL：

```json
{
  "execution_mode": "artifact_only_sandbox_readback",
  "sandbox": {
    "write_scope": "artifact_only"
  },
  "summary": {
    "synthesis_observed_candidate_count": 0,
    "synthesis_compiled_object_count": 0,
    "learner_memory_write_count": 0
  }
}
```

该 gate 可以把 candidate payload 读回成 `LearnerStateEvent` shape，并用 dry-run synthesis 验证候选证据被防线排除；不得调用 `LearnerStateService.append_memory_event`，不得写 `MEMORY_EVENTS.jsonl`、outbox、Supabase 或 canonical learner truth。

### 9.4 Authorized Writeback Preflight 标准

`authorized_writeback_preflight` 只允许表达“进入 test learner 写回前还需要什么”，不能表达“已经授权”。必须保持：

```json
{
  "verdict": "READY_FOR_AUTHORIZATION_REVIEW",
  "authorization": {
    "explicit_user_authorization_required": true,
    "test_learner_writeback_authorized": false,
    "allowed_write_scope": "none_without_authorization",
    "canonical_truth_authorized": false,
    "production_db_authorized": false
  },
  "summary": {
    "writeback_executed": false,
    "learner_memory_write_count": 0,
    "canonical_truth_write_count": 0
  }
}
```

若未来用户明确授权真实 test learner 写回，也必须进入新的独立 gate；本 preflight 不能被原地改造成写入器。

### 9.5 Test-Learner Writeback Authorization Package 标准

`test_learner_writeback_authorization_package` 只允许表达“等待用户/治理做授权决策的材料包”，不能表达“已授权”。它还必须和 `authorized_writeback_preflight` 交叉校验 candidate count，避免变成第二套事实来源。

```json
{
  "verdict": "READY_FOR_USER_AUTHORIZATION_DECISION",
  "execution_mode": "authorization_package_only",
  "authorization_decision": {
    "explicit_user_authorization_required": true,
    "user_authorization_recorded": false,
    "test_learner_writeback_authorized": false,
    "allowed_write_scope": "none_without_signed_authorization",
    "canonical_truth_authorized": false,
    "production_db_authorized": false
  },
  "rollback_plan": {
    "plan_status": "draft_review_required",
    "pre_write_snapshot_required": true,
    "delete_by_source_feature_required": true
  },
  "summary": {
    "writeback_executed": false,
    "learner_memory_write_count": 0,
    "canonical_truth_write_count": 0
  }
}
```

即便未来用户明确授权 test learner 写回，该授权也只覆盖 test learner 的 `learning_evidence` 写入实验，不自动授权 canonical learner truth、production DB、PersonalizationContextPack readback、training_intent 或 NextBestAction。

### 9.6 Test-Learner Writeback Dry-Run Manifest 标准

`test_learner_writeback_dry_run_manifest` 只允许表达“如果未来获得签名授权，计划写哪些 candidate event”。它可以生成 `batch_id`、event-level idempotency key 和 rollback selector，但必须保持 target learner 未绑定：

```json
{
  "verdict": "DRY_RUN_READY_FOR_SIGNED_AUTHORIZATION",
  "execution_mode": "dry_run_manifest_only",
  "target_scope": {
    "target_user_id": "not_bound_without_authorization",
    "target_memory_kind": "learning_evidence",
    "target_source_feature": "rich_leaf_authorized_test_writeback"
  },
  "write_batch_candidate": {
    "write_allowed": false
  },
  "rollback_selector": {
    "target_user_id": "not_bound_without_authorization",
    "rollback_allowed": false
  },
  "summary": {
    "writeback_executed": false,
    "learner_memory_write_count": 0,
    "canonical_truth_write_count": 0
  }
}
```

该 manifest 必须与 sandbox readback count 和 authorization package candidate count 交叉校验。任何真实 learner id、`write_allowed=true`、`rollback_allowed=true`、写计数非零，均为 interop blocker。

### 9.7 Test-Learner Writeback Execution Gate 标准

`test_learner_writeback_execution_gate` 是真实写回前的 fail-closed 门禁。在当前无签名授权、无具体 test learner id、rollback plan 未批准的状态下，它的正确 verdict 是 blocked：

```json
{
  "verdict": "BLOCKED_PENDING_SIGNED_AUTHORIZATION",
  "execution_mode": "execution_gate_only",
  "execution_decision": {
    "writeback_allowed": false,
    "writeback_executed": false,
    "target_user_id_bound": false,
    "signed_authorization_recorded": false,
    "rollback_plan_approved": false
  },
  "blocking_reasons": [
    "signed_user_authorization_missing",
    "target_user_unbound",
    "rollback_plan_not_approved"
  ],
  "summary": {
    "writeback_executed": false,
    "learner_memory_write_count": 0,
    "canonical_truth_write_count": 0
  }
}
```

该 gate 的目的不是“放行”，而是防止把 `DRY_RUN_READY_FOR_SIGNED_AUTHORIZATION` 误读为真实写回授权。只有用户另行明确授权具体 test learner scope 后，才能新增独立写入 gate；本 gate 不得被原地改写成 writer。

## 10. 当前落盘产物

| 产物 | 路径 | 当前用途 |
|---|---|---|
| Phase 1 sample | `artifacts/luban_grading_artifacts/rich_leaf_phase1_sampler_20260611/sample_manifest.json` | 50 leaf deterministic sample |
| Skeleton candidates | `artifacts/luban_grading_artifacts/rich_leaf_skeleton_candidates_20260611/rich_leaf_skeleton_candidates.json` | candidate RichLeaf skeleton |
| Skeleton report | `artifacts/luban_grading_artifacts/rich_leaf_skeleton_candidates_20260611/skeleton_report.json` | validation summary |
| Source-gap candidates | `artifacts/luban_grading_artifacts/rich_leaf_source_gap_candidates_20260611/source_gap_candidates.json` | review-only source evidence candidates |
| Candidate patches | `artifacts/luban_grading_artifacts/rich_leaf_candidate_patches_20260611/candidate_patches.json` | review-only source_ref patch queue |
| Patch evidence audit | `artifacts/luban_grading_artifacts/rich_leaf_patch_evidence_audit_20260611/patch_evidence_audit.json` | review-only machine precheck for candidate patches |
| Rejected patch feedback | `artifacts/luban_grading_artifacts/rich_leaf_rejected_patch_feedback_20260612/rejected_patch_feedback_work_orders.json` | review-only work orders for machine-rejected patches |
| Semantic audit packets | `artifacts/luban_grading_artifacts/rich_leaf_semantic_audit_packets_20260612/semantic_audit_packets.json` | review-only AI/人类 semantic evidence audit input packets |
| Source-evidence agent candidates | `artifacts/luban_grading_artifacts/rich_leaf_source_evidence_agent_20260612/source_evidence_agent_candidates.json` | review-only source evidence candidates for weak work orders |
| Semantic audit queue | `artifacts/luban_grading_artifacts/rich_leaf_semantic_audit_queue_20260612/semantic_audit_queue.json` | review-only unified queue for semantic evidence review |
| Semantic review shards | `artifacts/luban_grading_artifacts/rich_leaf_semantic_review_shards_20260612/semantic_review_shards_manifest.json` | review-only reviewer input shards; no decisions recorded |
| Semantic review suggestions | `artifacts/luban_grading_artifacts/rich_leaf_semantic_review_suggestions_20260612/semantic_review_suggestions.json` | review-only suggestion hints for reviewer triage; not a decision file |
| Semantic decision seed | `artifacts/luban_grading_artifacts/rich_leaf_semantic_review_decisions_20260612/semantic_decision_seed_unresolved.json` | review-only deterministic seed for source-authority failures; current run records 4 `needs_external_source` decisions |
| Semantic review decision validation | `artifacts/luban_grading_artifacts/rich_leaf_semantic_review_decision_validation_20260612/semantic_review_decision_validation.json` | review-only decision coverage/validity report; current run is `INCOMPLETE` with 181/186 current decisions, 5 missing decisions, and 8 stale decisions ignored |
| Merged semantic audit decisions | `artifacts/luban_grading_artifacts/rich_leaf_semantic_review_decision_validation_20260612/merged_semantic_audit_decisions.json` | current-shard-only validated decisions for record builder; stale audit ids are excluded |
| Semantic evidence audit record | `artifacts/luban_grading_artifacts/rich_leaf_semantic_evidence_audit_record_20260612/semantic_evidence_audit_record.json` | review-only semantic audit record; current run has 181 recorded decisions and 5 not_exercised items |
| Reviewed candidates | `artifacts/luban_grading_artifacts/rich_leaf_reviewed_candidates_20260612/reviewed_rich_leaf_candidates.json` | review-only accepted source_ref candidate batch; current run has 33 reviewed candidates |
| Runtime supply candidate | `artifacts/luban_grading_artifacts/rich_leaf_runtime_supply_candidate_20260612/rich_leaf_runtime_supply_candidate.json` | review-only versioned supply candidate bundle; current run status is `candidate_ready_for_regression`, with 33 supply units |
| Runtime supply regression | `artifacts/luban_grading_artifacts/rich_leaf_runtime_supply_regression_20260612/runtime_supply_regression.json` | static regression gate over task projections; current run PASS with 33 input units and 0 blockers |
| Rich field candidates | `artifacts/luban_grading_artifacts/rich_leaf_field_candidates_20260612/rich_leaf_field_candidates.json` | review-only rich-field candidate batch; current run PASS with 237 field candidates from 33 reviewed candidates and rejected semantic audit records |
| RichLeafArtifact candidates | `artifacts/luban_grading_artifacts/rich_leaf_artifact_candidates_20260612/rich_leaf_artifact_candidates.json` | review-only RichLeafArtifact candidate batch; current run PASS with 41 validator-clean artifact candidates |
| Field promotion review | `artifacts/luban_grading_artifacts/rich_leaf_field_promotion_review_20260612/field_promotion_review.json` | review-only field claim promotion batch; current run PASS with 41 promoted artifact candidates, 94 `source_backed` fields, 9 `assessment_evidence` exam-pattern fields, 134 fields still `candidate_only`, and 0 validation failures |
| Context pack smoke | `artifacts/luban_grading_artifacts/rich_leaf_context_pack_smoke_20260612/context_pack_smoke.json` | review-only task-pack projection smoke; current run PASS with 5 task packs, 0 blockers, and 0 question-lane source_refs in knowledge tasks |
| Fail-open guard diagnostic | `artifacts/luban_grading_artifacts/rich_leaf_fail_open_guard_diagnostic_20260612/fail_open_guard_diagnostic.json` | review-only candidate negative-evidence diagnostic; current run PASS with 86 candidate `negative_evidence` fields across 30 leaves, 110 review-visible candidate fields, `quality_claim_allowed=false`, and runtime enforcement marked `not_exercised` |
| Context pack projection A/B | `artifacts/luban_grading_artifacts/rich_leaf_context_pack_projection_ab_20260612/context_pack_projection_ab.json` | review-only candidate-only baseline vs promoted treatment projection A/B; current run PASS with 4/5 positive-consumption tasks gaining fields, review task exposing candidate-only audit fields, 0 knowledge-task question-lane leaks, `quality_claim_allowed=false`, `verdict_ceiling=PROJECTION_ONLY` |
| Semantic runtime offline A/B | `artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_offline_ab_20260612/semantic_runtime_offline_ab.json` | review-only deterministic offline adapter A/B; current run PASS with 50 eval cases, treatment answerable/citation/term-hit rates 1.0, treatment fail-open 0.0, `quality_claim_allowed=false`, `verdict_ceiling=OFFLINE_ADAPTER_ONLY` |
| Semantic runtime nearline A/B | `artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_nearline_ab_20260612/semantic_runtime_nearline_ab.json` | review-only nearline retrieval projection A/B; compares empty baseline / lexical current-RAG proxy / promoted context pack; `quality_claim_allowed=false`, `verdict_ceiling=NEARLINE_RETRIEVAL_PROJECTION` |
| Semantic runtime live A/B preflight | `artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_live_ab_preflight_20260612/live_ab_preflight.json` | review-only live-runtime A/B readiness gate; current run must keep `execution_mode=preflight_only`, `runtime_exercised=false`, `provider_call_count=0`, `quality_claim_allowed=false`, `verdict_ceiling=PREFLIGHT_ONLY` |
| Semantic runtime live A/B | `artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_live_ab_20260612/semantic_runtime_live_ab.json` | fail-closed live-runtime A/B runner contract; current run verdict is `BLOCKED_PROVIDER_AUTHORIZATION_REQUIRED`, with all arms `not_exercised`, `provider_call_count=0`, `quality_claim_allowed=false`, `verdict_ceiling=LIVE_RUNTIME_NOT_EXERCISED` |
| Semantic runtime near-live smoke | `artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_near_live_smoke_20260612/near_live_smoke.json` | review-only local adapter smoke; current run must keep `execution_mode=near_live_runtime`, `runtime_entry=local_compiled_context_adapter`, `provider_call_count=0`, `quality_claim_allowed=false`, `verdict_ceiling=NEAR_LIVE_LOCAL_ADAPTER_ONLY` |
| Semantic runtime near-live shadow A/B | `artifacts/luban_grading_artifacts/rich_leaf_semantic_runtime_near_live_shadow_ab_20260612/near_live_shadow_ab.json` | review-only local adapter shadow A/B; current run must keep `execution_mode=near_live_shadow`, arms=`current_rag_lexical_proxy`/`rich_leaf_local_adapter`, `provider_call_count=0`, `quality_claim_allowed=false`, `verdict_ceiling=NEAR_LIVE_SHADOW_LOCAL_ADAPTER_ONLY` |
| Shadow residual work orders | `artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_work_orders_20260612/shadow_residual_work_orders.json` | review-only residual feedback queue; current run PASS with 30 preventive guard-review work orders, 0 joinable local-adapter runtime residual work orders, and 8 non-joinable current-RAG proxy residuals kept out of compiler patches |
| Shadow residual review packets | `artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_packets_20260612/shadow_residual_review_packets.json` | review-only reviewer input packets; current run PASS with 30 packets from 30 work orders, 8 non-joinable residuals retained for diagnostics, decisions not recorded, and patch generation marked `not_exercised` |
| Shadow residual review decision seed | `artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_decision_seed_20260612/shadow_residual_review_decision_seed.json` | suggestion-only decision seeds for missing packets; current run PASS with 30 seeds, `decisions_recorded=false`, and patch/runtime marked `not_exercised` |
| Shadow residual review decisions | `artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_decisions_20260612/ai_council_shadow_review_decisions.json` | AI-council shadow-only review decisions; current run PASS with 30 decisions, no human/governance signoff, and patch/runtime marked `not_exercised` |
| Shadow residual review decision validation | `artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_review_decision_validation_20260612/shadow_residual_review_decision_validation.json` | review-only decision coverage validator; current run PASS with 30 packets, 30 decisions, 0 missing/invalid/duplicate/stale decisions, and patch generation marked `not_exercised` |
| Shadow residual audit record | `artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_audit_record_20260612/shadow_residual_audit_record.json` | review-only residual audit records; current run PASS with 30 records, all classified as `guard_review_required`, patch/source mutation/runtime guard marked `not_exercised` |
| Shadow residual guard patch plan | `artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_patch_plan_20260612/shadow_residual_guard_patch_plan.json` | review-only guard patch plan; current run PASS with 30 plan items, no patch/source/runtime authority granted |
| Shadow residual guard review packets | `artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_review_packets_20260612/shadow_residual_guard_review_packets.json` | review-only reviewer input packets for guard plan items; current run PASS with 30 packets and no decisions recorded |
| Shadow residual guard review decisions | `artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_review_decisions_20260612/shadow_residual_guard_review_decisions.json` | AI-council shadow-only guard review decisions; current run PASS with 30 decisions, no human/governance signoff, and patch/runtime marked `not_exercised` |
| Shadow residual guard review decision validation | `artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_review_decision_validation_20260612/shadow_residual_guard_review_decision_validation.json` | review-only guard decision coverage validator; current run PASS with 30 packets, 30 decisions, 0 missing/invalid/duplicate/stale decisions, and runtime guard enforcement marked `not_exercised` |
| Shadow residual guard audit record | `artifacts/luban_grading_artifacts/rich_leaf_shadow_residual_guard_audit_record_20260612/shadow_residual_guard_audit_record.json` | review-only guard audit records; current run PASS with 30 records, all classified as `guard_patch_candidate_review_required`, patch/source mutation/runtime guard marked `not_exercised` |
| Learning Evidence candidate bridge | `artifacts/luban_grading_artifacts/rich_leaf_learning_evidence_candidate_bridge_20260612/learning_evidence_candidate_bridge.json` | review-only bridge from local adapter shadow rows to `learning_evidence` candidate payloads; current run must keep `learner_memory_write_count=0`, `claim_promotion_allowed=false`, `writeback_eligible=false`, and PCP/NBA/readback marked `not_exercised` |
| PCP/NBA candidate projection | `artifacts/luban_grading_artifacts/rich_leaf_pcp_nba_candidate_projection_20260612/pcp_nba_candidate_projection.json` | review-only dry-run projection from `learning_evidence` candidates to `PersonalizationContextPackCandidate` and `next_action_candidate`; current run must keep `pcp_readback_count=0`, `training_intent_write_count=0`, `next_best_action_write_count=0` |
| Test-learner sandbox readback gate | `artifacts/luban_grading_artifacts/rich_leaf_test_learner_sandbox_readback_gate_20260612/test_learner_sandbox_readback_gate.json` | artifact-only sandbox write/readback gate; current run must keep `sandbox_event_write_count>0`, `synthesis_observed_candidate_count=0`, `synthesis_compiled_object_count=0`, and `learner_memory_write_count=0` |
| Authorized writeback preflight | `artifacts/luban_grading_artifacts/rich_leaf_authorized_writeback_preflight_20260612/authorized_writeback_preflight.json` | review-only authorization preflight for possible future test-learner writeback; current run must keep `test_learner_writeback_authorized=false`, `writeback_executed=false`, `learner_memory_write_count=0`, and `canonical_truth_write_count=0` |
| Test-learner writeback authorization package | `artifacts/luban_grading_artifacts/rich_leaf_test_learner_writeback_authorization_package_20260612/test_learner_writeback_authorization_package.json` | review-only authorization decision package; current run must keep `user_authorization_recorded=false`, `test_learner_writeback_authorized=false`, rollback `plan_status=draft_review_required`, `writeback_executed=false`, and all write counts at 0 |
| Test-learner writeback dry-run manifest | `artifacts/luban_grading_artifacts/rich_leaf_test_learner_writeback_dry_run_manifest_20260612/test_learner_writeback_dry_run_manifest.json` | artifact-only writeback batch dry run; current run must keep `target_user_id=not_bound_without_authorization`, `write_allowed=false`, `rollback_allowed=false`, `writeback_executed=false`, and all write counts at 0 |
| Test-learner writeback execution gate | `artifacts/luban_grading_artifacts/rich_leaf_test_learner_writeback_execution_gate_20260612/test_learner_writeback_execution_gate.json` | fail-closed execution gate; current run must keep verdict `BLOCKED_PENDING_SIGNED_AUTHORIZATION`, `writeback_allowed=false`, `target_user_id_bound=false`, and all write counts at 0 |
| Learning Evidence current-standard compat audit | `artifacts/luban_grading_artifacts/rich_leaf_learning_evidence_current_standard_compat_audit_20260612/current_standard_compat_audit.json` | read-only current-standard compatibility audit; current run PASS with 50 candidate events, all `not_current_standard_payload`, 0 accepted current source features, 0 PCP/training/NBA readback, and 0 learner memory writes |
| External-source closure | `artifacts/luban_grading_artifacts/rich_leaf_external_source_closure_20260612/external_source_closure.json` | review-only closure search for `needs_external_source`; current run PASS with 4 unresolved records retained as `external_source_required`, 0 source truth writes, and 0 runtime installs |
| Weak refinement | `artifacts/luban_grading_artifacts/rich_leaf_weak_source_refinement_20260611/weak_source_refinement_work_orders.json` | source authority gap work orders |

## 11. 当前阶段裁决

当前标准下，RichLeaf 编译工作处于：

```text
candidate workbench GO
runtime default NO-GO
release truth NO-GO
```

原因：

- Phase 0/1 互操作骨架已形成。
- candidate-only / review-only / safety invariants 已由测试和审计覆盖。
- source authority contamination 已加入防线。
- rich semantic field extraction 尚未全量完成。
- candidate patches 已有 machine precheck evidence audit；option-marker 污染已在 source-gap 上游修复，当前 `machine_reject=0`；47 个通过项已打包为 semantic audit input packets，并已进入 unified semantic review queue。
- weak source refinement 已由独立 source-evidence agent 对本地 `docs/2026` 语料执行一轮 review-only 召回；该 agent 现复用 `source_gap_candidates` 的统一 source loader。50 个 lane work orders 中 46 个找到 lane-matched 候选，4 个保持 unresolved，12 个 question-context 候选只作为上下文；这些仍是 candidate evidence，不是 source truth。
- semantic audit queue 已合并 47 个 patch semantic packets、135 个 source-evidence candidates 和 4 个 unresolved work orders，形成 186 个 review-only 审核项；该队列不记录 accepted/rejected verdict。
- semantic review shards 已将 186 个审核项切成 8 个 reviewer 输入分片；分片只定义允许输出的 decision schema，不记录 reviewer 决策。
- semantic review suggestions 已对 186 个审核项生成 suggestion-only triage：9 个 suggested accept、166 个 suggested reject、7 个 manual review、4 个 needs external source；这些数字只是 reviewer hints，不进入 `semantic_review_decision_validation`。
- semantic decision seed 已对当前 8 个 shard 执行：186 个审核项中 4 个无 `source_candidate` 的 unresolved source gap 被确定性标为 `needs_external_source`。
- codex semantic review 已逐条审查 19 个 suggested accept：8 个 accepted source_ref，11 个 reject_wrong_leaf_source；该 review 仍是 shadow/review-only，不是 release truth。
- codex semantic review 已逐条审查 13 个 manual-review required 项：5 个 accepted source_ref，8 个 reject_wrong_leaf_source；该 review 仍是 shadow/review-only，不是 release truth。
- codex semantic review 已逐条审查 30 个 suggested reject batch2：9 个 accepted source_ref，21 个 reject_wrong_leaf_source；该 review 仍是 shadow/review-only，不是 release truth。
- codex semantic review 已逐条审查 30 个 suggested reject batch3：4 个 accepted source_ref，26 个 reject_wrong_leaf_source；该 review 仍是 shadow/review-only，不是 release truth。
- codex semantic review 已逐条审查 30 个 suggested reject batch4：9 个 accepted source_ref，21 个 reject_wrong_leaf_source；该 review 仍是 shadow/review-only，不是 release truth。
- codex semantic review 已逐条审查 30 个 suggested reject batch5：0 个 accepted source_ref，30 个 reject_wrong_leaf_source；该 review 仍是 shadow/review-only，不是 release truth。
- codex semantic review 已逐条审查剩余 33 个审核项：1 个 accepted source_ref，32 个 reject_wrong_leaf_source；该 review 仍是 shadow/review-only，不是 release truth。
- semantic review decision validation 已对当前 decisions 执行：verdict=`INCOMPLETE`，`decision_count=181`，`missing_decision_count=5`，`stale_decision_count=8`，非法/重复决策均为 0。stale 决策不会进入 merged decisions。
- semantic evidence audit record 已生成当前真实记录：186 个审核项中 181 个 `recorded`，5 个 `not_exercised`；这不是 release truth。
- reviewed candidate builder 已对当前 semantic evidence audit record 执行：`audit_record_count=186`，`accepted_source_ref_count=33`，`reviewed_candidate_count=33`。
- runtime supply candidate builder 已对当前 reviewed candidates 执行：`status=candidate_ready_for_regression`，`supply_unit_count=33`，没有写 `runtime_supply/`，没有写 canonical pointer，也没有允许 production default。
- runtime supply regression gate 已对 33 个 supply units 执行静态任务投影回归：verdict=`PASS`，`blocker_count=0`；grading 投影 33 个，rag_answer/tutoring 各投影 24 个，9 个 question-lane unit 被排除在 rag_answer/tutoring 外，next_action 投影 0 个 source_ref，避免题库 evidence 污染知识回答或个性化动作。
- rich field candidate compiler 已对 33 个 reviewed source_ref candidates 和 semantic audit rejected records 执行确定性抽取：生成 237 个 review-only field candidates，其中 concepts=24、definitions=11、rules=15、procedures=17、numeric_constraints=3、teaching_cards=24、common_mistakes=24、negative_evidence=86、exam_patterns=9、learner_memory_event_templates=24；9 个 question-lane 只生成 exam_patterns，不生成 concepts/definitions/rules/procedures/numeric/teaching/common_mistakes/template knowledge fields。86 个 negative_evidence 来自 `reject_wrong_leaf_source` 且只使用 non-question source lanes。
- artifact candidate assembler 已将 237 个 field candidates 组装为 41 个 RichLeafArtifact candidates，`validation_failure_count=0`；其中 24 个 common_mistakes 进入 `hypothesized_mistakes`，不进入 `observed_mistakes`；86 个 negative_evidence 记录错 leaf/source pollution 候选，不进入 positive knowledge。该阶段的 rich fields 仍为 `candidate_only`，不能作为 runtime positive context、learner evidence 或 release truth。
- field promotion review 已对 41 个 RichLeafArtifact candidates 执行字段级归类：237 个字段中 94 个 textbook/standard/lecture 来源知识字段被标为 `source_backed`，9 个 question-lane `exam_patterns` 被标为 `assessment_evidence`，24 个 `common_mistakes`、24 个 `learner_memory_event_templates` 和 86 个 `negative_evidence` 保持 `candidate_only`；`validation_failure_count=0`。该产物仍是 review-only candidate，不写 runtime/default/release truth。
- context pack smoke 已对 promoted artifacts 构建 5 个 task-specific `CompiledContextPack`：`blocker_count=0`，知识任务中的 question-lane source_ref 数为 0。pack 只带已消费字段实际引用的 source_refs。
- fail-open guard diagnostic 已把 86 个 candidate `negative_evidence` 聚合为 30 个 leaf 级 review-only guard 诊断，确认这些候选风险可通过 review pack 暴露（`review_candidate_field_count=110`）；它只给出 `block_positive_context_until_source_ref_reviewed` 这类审核建议，不证明 runtime fail-open 已降低，`quality_claim_allowed=false`。
- context pack projection A/B 已对 candidate-only control 与 promoted treatment 执行 task-pack 对比：4/5 positive-consumption tasks 字段覆盖提升；review task 现在可显示 candidate-only audit 字段及其 source_ref；grading/tutoring/rag_answer 的 treatment source lanes 仅为 textbook/standard/lecture；next_action 可携带 question-lane `assessment_evidence`；`quality_claim_allowed=false`，`verdict_ceiling=PROJECTION_ONLY`。该产物不证明 accuracy/latency/token semantic win。
- semantic runtime offline A/B 已用确定性 adapter 对 50 个 source-backed eval cases 执行 baseline-empty-context vs rich-leaf-promoted-context：baseline abstention=1.0、fail-open=0.0；treatment answerable=1.0、evidence citation=1.0、term hit=1.0、fail-open=0.0。该产物仍然不调用 live LLM，不证明 production RAG retrieval、live latency、live token 或 learner outcome。
- semantic runtime nearline A/B 已接入统一标准：它把 empty baseline、current RAG lexical proxy、promoted context pack 放入同一张效果表；当前 50-case projection 中 current RAG answerable=0.94、treatment answerable=1.0、treatment fail-open=0、treatment token proxy delta=-421.9。该产物仍然不是生产 RAG、不是 live LLM，不证明线上 accuracy/latency/token。
- semantic runtime live A/B preflight 已接入统一标准：它不执行 provider 或生产 RAG，只确认进入真实 runtime A/B 的前置证据是否齐备，并把 `runtime_not_exercised` 与 `release_not_exercised` 分层记录，避免把 reviewer not_exercised 与 runtime not_exercised 混成一个 PASS。
- semantic runtime live A/B runner 已接入统一标准：当前 verdict=`BLOCKED_PROVIDER_AUTHORIZATION_REQUIRED`，四个 planned arms 全部 `not_exercised`，`provider_call_count=0`，`quality_claim_allowed=false`。这证明 runner 角色完整且 fail-closed，但不证明 live semantic win。
- semantic runtime near-live smoke 已接入统一标准：它通过本地 `local_compiled_context_adapter` 构建并消费 `CompiledContextPack`，当前只验证 10 条 local fixture 级 smoke 的 answer/citation/fail-open/question-lane discipline；它仍然不调用生产 RAG 或 live LLM，不记录真实线上 latency/token。
- semantic runtime near-live shadow A/B 已接入统一标准：它将 local adapter 扩展到 50-case shadow，并把 `current_rag_lexical_proxy` 与 `rich_leaf_local_adapter` 放进同一效果表；该产物仍然不是生产 RAG、不是 live LLM、不证明真实 latency/token。
- shadow residual work orders 已接入统一标准：当前 local adapter 50-case shadow 没有 joinable runtime residual（`runtime_residual_work_order_count=0`），但 fail-open guard diagnostic 生成 30 个 leaf 级预防性 guard-review work orders；current-RAG proxy 的 8 个 residual 因缺 `leaf_id` 只能保留为 `non_joinable_residuals`，不得硬塞成 compiler patch。
- shadow residual review packets 已接入统一标准：它把 30 个 work orders 渲染为 30 个 reviewer 输入包，保留 work_order trace、review questions 与 allowed decisions；它不记录 reviewer decision，不生成 patch，不修改 source_ref，不执行 runtime guard，`quality_claim_allowed=false`。
- shadow residual review decision seed 已接入统一标准：当前对 30 个 missing packets 生成 30 个 suggestion-only seeds，`decisions_recorded=false`、`patch_generation_allowed=false`、`runtime_install_allowed=false`、`quality_claim_allowed=false`；它只能帮助 reviewer/AI council 写正式 decision 文件，不能被 validation 当作正式决策消费。
- shadow residual review decisions 已接入统一标准：当前把 30 个 seeds 合成为 30 个 `ai_council_shadow_only` decisions，`human_reviewer_signoff` 与 `governance_signoff` 仍为 `not_exercised`，patch/runtime/source mutation 全部禁用；它是 AI review shadow，不是 release truth。
- shadow residual review decision validation 已接入统一标准：重跑后 verdict=`PASS`，`packet_count=30`、`decision_count=30`、`missing_decision_count=0`、invalid/duplicate/stale 均为 0；这只证明 AI-council shadow decisions 覆盖当前 packets，不授权 patch generation 或 runtime guard enforcement。
- shadow residual audit record 已接入统一标准：当前把 30 条 validated shadow decisions 固化为 30 条 review-only audit records，全部分类为 `guard_review_required`；这只产生后续 compiler review action 分类，不生成 patch、不修改 source_ref、不执行 runtime guard、不写 learner memory。
- shadow residual guard patch plan 已接入统一标准：当前把 30 条 `guard_review_required` audit records 渲染为 30 条 review-only guard plan items，计划动作均为 `block_positive_context_until_source_ref_reviewed`；它仍不生成 patch、不修改 source_ref、不执行 runtime guard、不安装 runtime、不允许 quality claim。
- shadow residual guard review packets 已接入统一标准：当前把 30 条 guard plan items 渲染为 30 条 reviewer 输入包，`decision_count=0`、`decisions_recorded=false`；它只暴露 allowed decisions、review questions 和 evidence trace，不记录正式 decision、不生成 patch、不修改 source_ref、不执行 runtime guard、不允许 quality claim。
- shadow residual guard review decisions 已接入统一标准：当前把 30 条 guard review packets materialize 为 30 条 `ai_council_shadow_only` decisions，默认决策为 `confirm_guard_patch_candidate`；`human_reviewer_signoff=false`、`governance_signoff=false`，patch/source/runtime/quality 仍全部禁用，后续必须经过 validation 后才能进入更下游候选层。
- shadow residual guard review decision validation 已接入统一标准：当前校验 30 条 guard review packets 与 30 条 shadow decisions，verdict=`PASS`，missing/invalid/duplicate/stale 均为 0；它只证明当前 guard shadow decisions 覆盖且合法，不生成 audit record、不生成 patch、不修改 source_ref、不执行 runtime guard、不允许 quality claim。
- shadow residual guard audit record 已接入统一标准：当前把 30 条 validated guard shadow decisions 固化为 30 条 review-only guard audit records，全部分类为 `guard_patch_candidate_review_required`；它只记录下一步 compiler action，不生成 patch、不修改 source_ref、不执行 runtime guard、不允许 quality claim。
- learning evidence candidate bridge 已接入统一标准：它只把 local adapter shadow rows 转成 review-only `learning_evidence` candidate payload，保持 `learner_memory_write_count=0`、`claim_promotion_allowed=false`、`writeback_eligible=false`；它不是 Learning Brain canonical truth、不是 PCP/NBA readback、不是学习效果证明。
- PCP/NBA candidate projection 已接入统一标准：它只生成 `PersonalizationContextPackCandidate` 与 `next_action_candidate` dry-run 形状，保持 `pcp_readback_count=0`、`training_intent_write_count=0`、`next_best_action_write_count=0`；它不是正式 `PersonalizationContextPack`、不是正式 `training_intent`、不是正式 NextBestAction。
- test-learner sandbox readback gate 已接入统一标准：它只写 artifact-only sandbox JSONL 并读回验证 candidate 事件不会进入 dry-run synthesis observed/compiled truth；它不调用 `append_memory_event`，不写真实 learner memory，不触发 outbox/DB。
- authorized writeback preflight 已接入统一标准：它只声明真实 test-learner writeback 前缺 `explicit_user_authorization`、test learner scope、治理审查、rollback plan 与独立 canonical truth 授权；它不是授权本身，也不执行写回。
- test-learner writeback authorization package 已接入统一标准：它只把 preflight 结果整理成等待用户/治理决策的材料包，保持 `user_authorization_recorded=false`、`test_learner_writeback_authorized=false`、rollback 草案未批准，并与 preflight candidate count 交叉校验；它不是写回器。
- test-learner writeback dry-run manifest 已接入统一标准：它只从 artifact-only sandbox JSONL 生成计划写入候选、幂等键和 rollback selector，保持真实 learner 未绑定、`write_allowed=false`、`rollback_allowed=false`，并与 sandbox readback 与 authorization package count 交叉校验；它不是写回器。
- test-learner writeback execution gate 已接入统一标准：它在当前无签名授权、无具体 test learner id、rollback 未批准时必须输出 `BLOCKED_PENDING_SIGNED_AUTHORIZATION`；它不是写回器，也不允许把 dry-run ready 升级为可写。
- Learning Evidence current-standard compat audit 已接入统一标准：当前 50 条 RichLeaf learning evidence candidates 全部标为 `not_current_standard_payload`，`standard_accepted_source_feature_count=0`，`current_standard_readback_verified=false`，PCP/training/NBA readback 与 learner memory 写入均为 0；它只证明候选产物仍未进入当前 Learning Brain 标准权威，不把 candidate 加进 `learning_synthesis`。
- external-source closure 已接入统一标准：当前 4 个 `needs_external_source` 复检后仍无 lane-matched textbook/standard/lecture 支撑，全部保留为 `external_source_required`；它不把 question context 当 source support，不写 source truth，不修改 source_ref，不安装 runtime。
- interop audit 当前覆盖 49 个产物，要求 schema、source lane、claim status、review-only/runtime 禁入、fail-open guard diagnostic、projection/preflight/live-runner/local-adapter/shadow ceiling、shadow residual work orders、shadow residual review packets、shadow residual review decision validation、shadow residual review decision seed、AI-council shadow review decisions、shadow residual audit record、shadow residual guard patch plan、shadow residual guard review packets、shadow residual guard review decisions、shadow residual guard review decision validation、shadow residual guard audit record、provider_call_policy、runtime_entry、learning-evidence candidate bridge、PCP/NBA candidate projection、sandbox readback gate、authorized writeback preflight、authorization package、dry-run manifest、execution gate、current-standard compat audit、external-source closure 与 not_exercised_by_layer 合同一致；这只证明 workbench 产物互操作与安全边界合规，不证明 RichLeafArtifact 已可安装为 runtime default，也不证明 live semantic runtime A/B 已胜出。

## 12. 下一阶段标准

下一阶段只能做四类事：

1. `live semantic runtime A/B`：在 offline/nearline projection A/B、live A/B preflight、10 条 near-live local smoke 与 50-case near-live shadow A/B 通过后，再接真实 runtime entry；比较 baseline RAG / legacy / promoted compiled pack / artifact-first + LLM judge 的 accuracy、token、latency、evidence/citation、fail-open。未跑真实 runtime entry、真实 provider 或真实 token/latency 前必须保持 `quality_claim_allowed=false`。
2. `runtime supply decision package`：若 A/B 证明有效，只生成受控 default decision input；不得自动写 runtime/default。
3. `source-evidence`：对 1 个 `needs_external_source` 决策继续扩语料、重检索或保留 external-source-required，不得硬塞 question context。
4. `source-evidence`：若后续再出现 rejected patch feedback work orders，先修 source-gap 上游污染或重跑 leaf-specific source search，不得复用 rejected source_ref。

禁止：

- 直接把 patch 写入当前 `canonical_unified_knowledge.json`。
- 直接让 runtime 读取 workbench JSON。
- 把 question/practice evidence 当 textbook/standard/lecture support。
- 把 AI council / candidate patch 写成 release truth。
