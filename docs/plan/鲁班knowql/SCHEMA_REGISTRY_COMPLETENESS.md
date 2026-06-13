# Schema Registry 完整闭环 — Three-Tier Closure of All 173 Schema Identifiers

> Status: `Closed (candidate / review-only)` — 2026-06-13
> 角色：单一权威「登记才能用」机器闸门 **完整闭环** 工程师。
> 目标：把全库每一个 schema-version 标识符 **逐个有交代**（登记 / 显式运行时登记 / Tier3 规则豁免），
> 不再有「没登记就用」的漏网。一次性做到位。
> 权威依据：`AGENTS.md` §0 / §5.6 / §5.7（单一权威硬门槛）；蓝图 `KNOWQL_BUILDOUT_BLUEPRINT.md` 禁区 D2（禁止第三套 schema）。
> 配套审计：`REGISTRATION_COVERAGE_AUDIT.md`（G1：闸已造好未通电）。本文是它的 **闭环补完**——把登记表从「9 个判分对象」扩成「全集 173 个标识符逐个有 tier 裁决」。
>
> 代码权威（本文不复制字段表，全由代码/测试派生）：
> - 登记表：`contracts/schema_registry.yaml`（T1 `schemas:` + `tier2_canonical_contracts:` + `tier3_carve_out:` + `completeness_closure:`）
> - 闭环重生成 + 校验：`scripts/check_schema_registry.py::collect_all_schema_identifiers / classify_identifier / closure_report`
> - 闭环测试：`tests/scripts/test_schema_registry.py::test_full_set_is_closed_three_tier`（+ 计数/分类断言）
> - 一键校验：`python scripts/check_schema_registry.py --closure`
>
> 本文 **不** 改判分语义、不开 transport、不授任何 official-score / canonical-write 权。它只是把「谁有权用哪个 schema」做成机器闭环。

---

## 0. 一句话结论

全库 schema-version 标识符 **全集 = 173 个**（不是任务起点 grep 的 152——见 §1）。
全部 **逐个落入唯一一层**：

| Tier | 含义 | 数量 | 登记形态 |
|---|---|---:|---|
| **T1** | 判分 typed object（point-level 字段契约，单一 canonical + 8 deprecated adapter-only） | **9** | `schemas:` 逐个登记 |
| **T2** | 运行时消费的 canonical 契约（serving/grading/learner-brain 真读回，漂移会崩跨消费方或造第二权威） | **19** | `tier2_canonical_contracts:` 逐个登记（带 `canonical_for` + `consumed_by` 证据） |
| **T3** | 一次性工件（audit/eval/ab/gate/report/packet/candidate/…，写一次不被运行时当契约读回） | **145** | `tier3_carve_out:` 一条规则 + 模式列表覆盖，**非逐个登记** |
| | **合计** | **173** | 9 + 19 + 145，无遗漏、无重叠、无 orphan |

闭环不变量（测试断言、CLI 可跑）：
**全集（从源码 **重新扫描** 得到，不是手抄）== T1 ∪ T2 ∪ T3，三层互斥且穷尽，零 orphan。**
任何人新增第 174 个 schema 而不登记、且名字不匹配 T3 模式 → 闭环测试报 orphan → 红。这就是「没登记就用」的最后一道堵漏。

---

## 1. 为什么是 173 不是 152（漏网的根因）

任务起点 grep 只匹配三种字面量形态：

```
SCHEMA = "…"      "schema": "…"      schema_version": "…"
```

它 **漏了** 这些等价形态：`SCHEMA_ID = "…"`、`schema_id: "…"`、`*_SCHEMA_VERSION = "…"`（如 `SESSION_SCHEMA_VERSION`）、`artifact_schema: "…"`、`typed_artifact_schema: "…"`、`"kind": "…"`（observability record）。

要命的是：**9 个 T1 判分对象里有 8 个只在这些被漏掉的形态里声明**（只有 `luban_m31_governed_objective_pointer.v1` 落进 152）。也就是说，如果以 152 为闭环基线，登记表连自己的 9 个 T1 对象都覆盖不全——正是任务警告的「漏网」。

闭环扫描器 `collect_all_schema_identifiers()` 因此 union 了 **所有** schema-marker 形态（任意以 `schema` / `schema_id` / `schema_version` / `_schema` / `_SCHEMA[_ID|_VERSION]` 结尾的 key/var + `kind`），再用「带版本后缀（`.vN` / `.mNN` / `_vN`）且属于已知 typed-object 命名空间」过滤掉 `public`（Postgres schema）、`learning_evidence`（event_type）这类非 typed-object 噪声。结果稳定 = **173**。

> `completeness_closure.full_set_count = 173`，`primary_grep_baseline = 152`——两个数都写进登记表，把「152 是不完整基线」这件事固化成文档。

---

## 2. Tier 1 · 判分 typed object（9，已登记，本任务核对无遗漏）

唯一 canonical `luban_grading_object.v1` + 8 套 deprecated（全部 adapter-only，map 进 canonical）。字段契约 / drift map / authority 词表见 `UNIFIED_GRADING_OBJECT_SCHEMA.md` 与 `schemas:` 块，本文不复制。

| schema | status |
|---|---|
| `luban_grading_object.v1` | canonical |
| `case_grading_artifact.v1` | deprecated |
| `luban.rich_leaf_artifact.v0` | deprecated |
| `luban_scoring_point_assets.v0.1` | deprecated |
| `luban_m31_governed_objective_pointer.v1` | deprecated |
| `luban_arbitration_gold_panel.v1` | deprecated |
| `m35_ai_governed_gold.v1` | deprecated |
| `compact_scoring_artifact.v1` | deprecated |
| `luban_per_question_grading_object.v1` | deprecated |

> 核对：闭环扫描确认这 9 个全部出现在源码并被 `classify_identifier` 归为 `tier1`，与 `schemas:` 列一一对应（`test_closure_counts_match_registry_declaration` 断言 `len(tier1)==9`）。

---

## 3. Tier 2 · 运行时消费的 canonical 契约（19，本任务新登记）

判别口径（`scope_rule.must_register_if_any`）：被 **不同于生产方** 的运行时 serving/grading/learner-brain 路径真读回 **或** 持久化成别的 run 读的输入 **或** 运行时按字段名绑定。**逐个读代码确认 `consumed_by`，不凭名字猜。**

字段级 canonical 暂未全部冻结——本任务 **诚实标 `needs_field_canonicalization: true`**（不硬造字段表）。guard 因此对 T2 **不跑** drift/authority 字段检查（避免假字段集），只做两件事：(1) 认它是已登记、不误报「unregistered」；(2) 当 T2 文件被改且字段未冻结时，发 **非阻塞 warning** 提醒后续把字段钉死。

| # | schema（fact） | canonical_for | 消费方（cross-consumer 证据） | 字段级 |
|---|---|---|---|---|
| 1 | `luban_canonical_knowledge_manifest.v1` | runtime-supply lane 总清单（content_hash 钉每条签名 lane shard） | `canonical_knowledge_manifest.py::verify_manifest`（fail-closed 闸所有 lane） | 待办 |
| 2 | `luban_canonical_knowledge_graph.v1` | tutor runtime 的前置/相关边 | `canonical_knowledge_runtime.py::_load_graph` → `resolve_canonical_knowledge` → `capabilities/deep_question.py` | 待办 |
| 3 | `luban_canonical_taxonomy_index.v1` | key→canonical-code 解析脊（concept_id/题节点/自由文本） | `canonical_resolution.py::_index`（运行时 `resolve()`，被 deep_question 读） | 待办 |
| 4 | `luban_canonical_unified_knowledge.v1` | 逐节点统一教学上下文（教材/标准/讲义/题 merge 在 canonical 脊上） | `canonical_knowledge_runtime.py::_load` → `resolve_canonical_knowledge`（deep_question + general_knowledge） | 待办 |
| 5 | `luban_canonical_unified_knowledge_source_alignment_repairs.v1` | runtime resolve 时的 source-filter 修复 overlay | `canonical_knowledge_runtime.py::_load_source_alignment_repairs`（按 source_bundle_content_hash 绑定） | 待办 |
| 6 | `luban_standard_clauses.v1` | 外规逐条 verbatim 权威 lane（持久在 manifest） | `canonical_knowledge_manifest.py::enum_shards`（v_standard_clauses lane，content_hash 钉） | 待办 |
| 7 | `luban_concept_registry.v3` | 持久 concept 身份（concept_id/alias/merged+deprecated）——防 concept_id 跨 learner-state 重写断裂 | `canonical_resolution.py::_registry`（运行时 `resolve_code_to_canonical` / `is_deprecated`，deep_question 读） | 待办 |
| 8 | `compiled_knowledge_registry.v2` | 由 canonical_pointer 钉的签名编译答案/上下文 bundle（grader + context-pack builder 用） | `compiled_registry_resolver.py::verify_bundle/load_supply`（运行时 resolve_question/resolve_node，fail-closed） | 待办 |
| 9 | `luban_full_knowledge_compiler.m30` | m30 编译知识 bundle 的 stamp，运行时 resolver 加载 | `compiled_registry_resolver.py`（import full_knowledge_compiler，运行时 resolve bundle） | 待办 |
| 10 | `luban_context_pack.v1` | 跨消费方编译教学/判分上下文 pack（所有 surface 的单一权威） | `deep_question.py` + `compiled_registry_resolver.py` + `deep_question_adapter.py` + `objective_runtime_adapter.py` + `open_world_diagnostic.py` | 待办 |
| 11 | `luban.compiled_context_pack.rich_leaf.v0` | rich-leaf 任务级编译上下文 pack（case 判分/AI 复核的字段选择） | `rich_leaf_artifacts.py` builder + case-grading flow（任务级投影） | 待办 |
| 12 | `luban_rich_leaf_runtime_token_pack.v2.3` | 冻结 rich-leaf runtime token pack（serving runtime 钉的版本） | `rich_leaf_runtime.py::PACK_SCHEMA`（schema-pin 读；rich_leaf_runtime 被 deep_question 读） | 待办 |
| 13 | `luban_rich_leaf_context_bundle.v1` | 由 token pack 派生的 runtime 上下文 bundle（serving 查找索引） | `rich_leaf_runtime.py::BUNDLE_SCHEMA` + `_load_index`（serving via deep_question） | 待办 |
| 14 | `luban_runtime_grading_packet.v1` | 递给 LLM 裁决器的运行时判分决策 packet（point_ids/student_answer/schema_version） | `runtime_llm_adjudicator.py` 裁决循环 + 安全 validator（运行时判分） | 待办 |
| 15 | `luban_objective_answer_key.v2_release_candidate` | 运行时 extractor 绑定的治理客观答案 key release（namespace objective_answer_key_governed） | `objective_governed_registry_extractor.py::SCHEMA_VERSION`（运行时治理-registry 抽取） | 待办 |
| 16 | `question_grading_artifact.v0` | 运行时自动认证闸绑定的逐题 published-artifact 状态 | `artifact_runtime_gate.py`（via question_grading_registry；闸输入由 case_kernel / runtime_shadow_adapter 构造） | 待办 |
| 17 | `luban_artifact_first_llm_judge_result.v1` | artifact-first LLM judge verdict shape（下游判分 enrichment 消费） | `judge_point_enrichment.py` + `m35_artifact_shadow.py`（运行时判分消费方） | 待办 |
| 18 | `assessment_session_v1` | 持久评测 session 行，跨设备 resume 重读（DB repository 契约） | `assessment/session_repository.py::get_session_for_resume`（持久 + schema_version 校验重读） | 待办 |
| 19 | `causal_oa_v1` | causal-OA 可观测 record shape（producer→runner 跨消费方）；**在判分脊之外** | `observability/oa_runner.py`（emit kind=causal_oa_v1；跨消费方可观测契约） | 待办 |

> 全部 19 个的 `needs_field_canonicalization=true`——这是一份诚实的字段级待办清单，不是已完成项。Phase B 把字段逐个钉死后改成 `false` 并补 `canonical_fields`，guard 即可对该 T2 项开 drift 检查。

---

## 4. Tier 3 · 一次性工件（145，规则 + 模式覆盖，非逐个登记）

T3 = audit / eval / ab / gate / report / packet / record / work_orders / review / smoke / diagnostic / probe / closure / decision / analysis / preflight / dry_run / spot_check / trace / seed / validation / shard / candidate / fixture / manifest（candidate 类）/ … 写一次、不被运行时当契约读回。**逐个登记会官僚**，所以用一条规则 + 模式列表覆盖（`tier3_carve_out`）。

**carve-out 规则**：一个 schema-version 字面量，若 **不是** 已登记 T1 判分对象、**不是** 已登记 T2 运行时契约，则当其名匹配 `artifact_name_patterns` 之一时即为允许的一次性工件，**无需逐个登记**，guard 的「未登记名」失败规则对它 **不触发**。闭环测试断言这些模式 **100% 覆盖** 非-T1/非-T2 余集，所以 carve-out 不会静默留洞。

### 4.1 名字像 canonical 但实为 T3 的三个（逐个读代码确认无运行时 reader，显式点名）

避免「名字唬人就当 Tier2」：

- **`luban_topic_shard.v1`** — 只被 `canonical_knowledge_manifest.py::enumerate_shards` 当 manifest lane 枚举，**无运行时 resolver 消费 topic-shard 专属 payload**。→ T3（`_topic_shard` 模式）。
- **`luban_runtime_supply_bundle.v1`** — `build_luban_runtime_supply_bundle_m21s.py` 一次性产出（M21 血统），**无 back-reader**。→ T3（`runtime_supply_bundle` 模式）。
- **`luban_v1_canonical_promotion_registry.m33`** — `run_luban_canonical_promotion_arm_release_gate_m33.py` 写本地 learner-state（无远端/生产），**无运行时契约 reader**。→ T3（`_promotion_registry` 模式）。
- 另：**`grading_artifact.v1`** 是 `build_luban_human_validation_slice.py` 的一次性切片，**不是** T1 的 `case_grading_artifact.v1`——显式列入 carve-out 防混淆。

### 4.2 T3 全表（145 个）

<details>
<summary>展开 145 个 Tier3 标识符</summary>

- `assessment_p0a_coverage_v1`
- `grading_artifact.v1`
- `luban.registry_candidate_staging.m202.v1`
- `luban_case_rubric_audit_packet.v0`
- `luban_compiler_hard_gate_rules.v0`
- `luban_distillation_sample.v0`
- `luban_docs2026_runtime_reconciliation.v1`
- `luban_four_arm_scoring_ab.v1`
- `luban_four_arm_split_analysis.v1`
- `luban_grading_verdict_ab.v1`
- `luban_judge_grading_to_brain_trace.v1`
- `luban_kb_v5_export.v1`
- `luban_knowledge_compiler_crosscheck.v1`
- `luban_lecture_compiler.v1`
- `luban_m35_ai_governed_gold_labeling.v1`
- `luban_m35_deepseek_adversarial_probe.v1`
- `luban_m35_fastapi_case_fixture.v1`
- `luban_m35_fastapi_mcq_fixture.v1`
- `luban_m35_scoring_artifact_ab.v1`
- `luban_m35_three_model_blind_ab.v1`
- `luban_nexus_compilation_decision.v1`
- `luban_objective_answer_key.v2_candidate`
- `luban_objective_answer_key.v2_real_candidate`
- `luban_p0_leaf_source_reanchor_candidates.v1`
- `luban_p0_reanchor_candidate_patch.v1`
- `luban_p1_strong_go_gate.v1`
- `luban_p2_live_readback_gate.v1`
- `luban_p3_api_readback_gate.v1`
- `luban_p4_ws_readback_gate.v1`
- `luban_p5_real_wechat_package_readback_gate.v1`
- `luban_qwen_blind_residual_audit.v1`
- `luban_r6_release_decision_package.v1`
- `luban_rich_leaf_ai_council_manual_review_packets.v1`
- `luban_rich_leaf_artifact_candidate_batch.v1`
- `luban_rich_leaf_authorized_writeback_preflight.v1`
- `luban_rich_leaf_batch_relink_candidates.v1`
- `luban_rich_leaf_batch_relink_live_spot_check.v1`
- `luban_rich_leaf_candidate_patch_batch.v1`
- `luban_rich_leaf_case_question_typed_ab.v2`
- `luban_rich_leaf_compiler_status_ledger.v1`
- `luban_rich_leaf_context_pack_projection_ab.v1`
- `luban_rich_leaf_context_pack_smoke.v1`
- `luban_rich_leaf_controlled_default_authorization_package.v1`
- `luban_rich_leaf_external_source_closure.v1`
- `luban_rich_leaf_fail_open_guard_diagnostic.v1`
- `luban_rich_leaf_field_candidate_batch.v1`
- `luban_rich_leaf_field_promotion_review.v1`
- `luban_rich_leaf_frozen_full_compile.v1`
- `luban_rich_leaf_frozen_v11_deployment_eval.v1`
- `luban_rich_leaf_frozen_v1_full_learning_brain_closure.v1`
- `luban_rich_leaf_frozen_v1_live_ab.v1`
- `luban_rich_leaf_frozen_v1_live_residual_work_orders.v1`
- `luban_rich_leaf_interop_audit.v1`
- `luban_rich_leaf_leaf_evidence_recompile.v1`
- `luban_rich_leaf_learning_evidence_candidate_bridge.v1`
- `luban_rich_leaf_learning_evidence_current_standard_compat_audit.v1`
- `luban_rich_leaf_legacy_compilation_quality_audit.v1`
- `luban_rich_leaf_llm_deep_compile_packets.v1`
- `luban_rich_leaf_llm_deep_compile_runner.v1`
- `luban_rich_leaf_manual_review_packets.v1`
- `luban_rich_leaf_operator_signature_record.v1`
- `luban_rich_leaf_patch_evidence_audit.v1`
- `luban_rich_leaf_pcp_nba_candidate_projection.v1`
- `luban_rich_leaf_phase0_validator_report.v1`
- `luban_rich_leaf_phase1_sample_manifest.v1`
- `luban_rich_leaf_real_world_three_arm_eval.v1`
- `luban_rich_leaf_rejected_patch_feedback.v1`
- `luban_rich_leaf_release_governance_review_packet.v1`
- `luban_rich_leaf_reviewed_candidate_batch.v1`
- `luban_rich_leaf_runtime_default_gate.v1`
- `luban_rich_leaf_runtime_pack_semantic_quality_audit.v1`
- `luban_rich_leaf_runtime_supply_candidate_bundle.v1`
- `luban_rich_leaf_runtime_supply_regression.v1`
- `luban_rich_leaf_runtime_token_pack.v1`
- `luban_rich_leaf_runtime_token_pack.v2`
- `luban_rich_leaf_runtime_token_pack_streaming_ab.v1`
- `luban_rich_leaf_scoring_point_before_after.v1`
- `luban_rich_leaf_scoring_point_compile.v1`
- `luban_rich_leaf_semantic_audit_decisions.v1`
- `luban_rich_leaf_semantic_audit_packets.v1`
- `luban_rich_leaf_semantic_audit_queue.v1`
- `luban_rich_leaf_semantic_evidence_audit_record.v1`
- `luban_rich_leaf_semantic_review_decision_validation.v1`
- `luban_rich_leaf_semantic_review_shard.v1`
- `luban_rich_leaf_semantic_review_shards.v1`
- `luban_rich_leaf_semantic_review_suggestions.v1`
- `luban_rich_leaf_semantic_runtime_live_ab.v1`
- `luban_rich_leaf_semantic_runtime_live_ab_preflight.v1`
- `luban_rich_leaf_semantic_runtime_live_ab_results.v1`
- `luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1`
- `luban_rich_leaf_semantic_runtime_near_live_smoke.v1`
- `luban_rich_leaf_semantic_runtime_nearline_ab.v1`
- `luban_rich_leaf_semantic_runtime_offline_ab.v1`
- `luban_rich_leaf_shadow_residual_audit_record.v1`
- `luban_rich_leaf_shadow_residual_guard_audit_record.v1`
- `luban_rich_leaf_shadow_residual_guard_patch_plan.v1`
- `luban_rich_leaf_shadow_residual_guard_review_decision_validation.v1`
- `luban_rich_leaf_shadow_residual_guard_review_decisions.v1`
- `luban_rich_leaf_shadow_residual_guard_review_packets.v1`
- `luban_rich_leaf_shadow_residual_review_decision_seed.v1`
- `luban_rich_leaf_shadow_residual_review_decision_validation.v1`
- `luban_rich_leaf_shadow_residual_review_decisions.v1`
- `luban_rich_leaf_shadow_residual_review_packets.v1`
- `luban_rich_leaf_shadow_residual_work_orders.v1`
- `luban_rich_leaf_signed_authorization_template.v1`
- `luban_rich_leaf_skeleton_batch.v1`
- `luban_rich_leaf_skeleton_report.v1`
- `luban_rich_leaf_source_corpus_coverage_gate.v1`
- `luban_rich_leaf_source_corpus_inventory.v1`
- `luban_rich_leaf_source_evidence_agent.v1`
- `luban_rich_leaf_source_gap_candidates.v1`
- `luban_rich_leaf_terminal_leaf_completion.v1`
- `luban_rich_leaf_terminal_leaf_completion_work_orders.v1`
- `luban_rich_leaf_test_learner_sandbox_readback_gate.v1`
- `luban_rich_leaf_test_learner_writeback_authorization_package.v1`
- `luban_rich_leaf_test_learner_writeback_dry_run_manifest.v1`
- `luban_rich_leaf_test_learner_writeback_execution_gate.v1`
- `luban_rich_leaf_v23_learning_brain_candidate_closure.v1`
- `luban_rich_leaf_v23_live_provider_shadow_ab.v1`
- `luban_rich_leaf_v23_live_residual_work_orders.v1`
- `luban_rich_leaf_v23_near_live_shadow_ab.v1`
- `luban_rich_leaf_v23_residual_repair_manifest.v1`
- `luban_rich_leaf_v23_residual_source_repair.v1`
- `luban_rich_leaf_v2_taxonomy_leaf_linking.v1`
- `luban_rich_leaf_v2_taxonomy_shadow_review.v1`
- `luban_rich_leaf_weak_source_refinement.v1`
- `luban_rubric_compiler.v1`
- `luban_runtime_supply_bundle.v1`
- `luban_scoring_point_assets_backfill.v0.1`
- `luban_student_answer_grading_shadow_eval.v1`
- `luban_taxonomy_book_derived_rebuild.v1`
- `luban_taxonomy_coverage_expansion.v1`
- `luban_taxonomy_dedup_rehome_candidate.v1`
- `luban_taxonomy_skeleton_repair.v1`
- `luban_topic_shard.v1`
- `luban_typed_policy.v0.1`
- `luban_unified_knowledge_leaf_coverage_work_orders.v1`
- `luban_v1_canonical_promotion_registry.m33`
- `question_grading_artifact.v1_beta_shadow`
- `question_grading_artifact.v1_candidate_dry_run`
- `question_grading_artifact.v1_council_hardened_candidate`
- `question_grading_registry.v1_candidate_dry_run`
- `question_grading_registry.v1_release_candidate`
- `rich_leaf_deep_compile_candidate.v1`
- `rich_leaf_typed_artifact.v1`

</details>

---

## 5. 闭环校验（是否 173 全覆盖）

```text
$ python scripts/check_schema_registry.py --closure
schema-registry-closure: full_set=173 tier1=9 tier2=19 tier3=145 orphans=0
schema-registry-closure: CLOSED — every schema id has a tier verdict
```

测试断言（`tests/scripts/test_schema_registry.py`，21 passed）：
- `test_full_set_is_closed_three_tier`：full_set（**重新扫描**）== T1 ∪ T2 ∪ T3，零 orphan，三层互斥穷尽。
- `test_closure_counts_match_registry_declaration`：登记表声明的 `tier_counts` == 实时扫描计数（防文档与代码脱节）。
- `test_full_set_scan_is_deterministic_and_versioned`：扫描纯函数、确定性，结果只含带版本后缀的 id（`public` / `learning_evidence` 被滤掉）。
- `test_classify_t1_t2_t3_examples`：逐层抽样分类正确；未登记且无 carve-out 的新名 → `orphan`（即被堵住）。
- `test_guard_tier2_contract_is_recognized_not_unregistered` / `test_guard_tier2_drift_word_not_failed`：guard 认 T2、不误报、不对 T2 跑判分字段检查，并发非阻塞 canonicalization warning。

**结论：173 全覆盖、零 orphan、闭环成立。**

---

## 6. guard 对 T2 的新感知（用了 T2 schema 但漂移其 canonical 字段 → 可选告警）

`scripts/check_schema_registry.py` 现在认识 T2：
- T2 名 **不再** 被误报「unregistered」。
- 对 T2 **不跑** drift/authority 字段检查（T2 字段尚未冻结，不硬造字段集）。
- 当改动触及一个 `needs_field_canonicalization=true` 的 T2 文件 → 输出 **非阻塞 warning**，提示「该运行时契约字段未钉死，漂移不会被抓，建议钉字段」。这是把 T2 的字段级 canonical 化做成可见 backlog，而不是假装已完成。

字段冻结后（Phase B），把对应 T2 项的 `needs_field_canonicalization` 改 `false` 并补字段列，guard 即可升级为对该项的硬 drift 检查。

---

## 7. 范围声明 / 不做什么

- **不通电进 CI**：`check_schema_registry.py` 接进 `check_contract_guard.py` 的「PENDING HUNK」属于另一个有未提交并行 WIP 的文件（`scripts/check_contract_guard.py`），本任务 **不碰、不夹带**（见 G1 协调项）。本任务只把登记表做到 **完整闭环**，通电是独立的一步。
- **不改判分语义 / 不开 transport / 不授 official-score 或 canonical-write 权**。
- **T2 字段级 canonical 暂为待办**（19 个全部 `needs_field_canonicalization: true`），诚实标注，不硬造。

---

## 附录 · 证据索引（绝对路径）

- 登记表：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/contracts/schema_registry.yaml`
- 闭环代码：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/scripts/check_schema_registry.py`（`collect_all_schema_identifiers` / `classify_identifier` / `closure_report` / `--closure`）
- 闭环测试：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/tests/scripts/test_schema_registry.py`
- T1 字段权威：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/docs/plan/鲁班knowql/UNIFIED_GRADING_OBJECT_SCHEMA.md`
- 配套缺口审计：`/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/docs/plan/鲁班knowql/REGISTRATION_COVERAGE_AUDIT.md`（G1）
