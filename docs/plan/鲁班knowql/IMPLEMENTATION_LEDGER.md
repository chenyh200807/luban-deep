# 鲁班 KnowQL Implementation Ledger

> Status: `Active ledger / implementation truth map` — 2026-06-15
> Scope: 只记录 `docs/plan/鲁班knowql/` 与 M35 Nexus-like scoring artifact 主线的计划项落地状态。
> Non-goal: 本文件不新增架构、不授予 production default、不替代 `CONTRACT.md`、`contracts/index.yaml` 或 M35 master plan。

## 0. 为什么需要这份 ledger

之前的 KnowQL 讨论把两件事混在了一起：

1. **计划覆盖度**：我们是否已经把 Nexus / KnowQL 的关键机制、风险、阶段和 gate 想清楚。
2. **实现成熟度**：某个计划项是否已经从文档、stub、local code、runtime consumption、shadow、live readback 一直走到 production authorization。

这两者不能互相替代。计划写得完整，不等于 runtime 已消费；local 测试绿，不等于 live readback；canary GO，不等于 broad production GO。

本 ledger 的作用是给后续 agent 一个单一事实表：每个 KnowQL 计划项现在停在哪一档，下一步 promotion gate 是什么，禁止把哪一档冒充成哪一档。

## 1. 状态词表

| 状态 | 定义 | 不允许冒充 |
|---|---|---|
| `planned` | 只有计划、设计、审计或蓝图；没有对应实现入口。 | 不能写成已实现。 |
| `stub` | 有最小代码或 demo，但只服务 fixture / in-memory / shape proof；没有接真实 runtime artifact 或真实 consumer。 | 不能写成 runtime 可用。 |
| `landed-local` | 代码、测试或脚本已落本地，并能在本仓库聚焦测试中通过。 | 不能写成线上、live 或默认路径。 |
| `runtime-consumed` | 已有 runtime/service consumer 通过稳定入口消费该产物；可默认 off、flagged 或 slot-gated。 | 不能写成已 shadow 验证或可 broad flip。 |
| `shadow-verified` | 已通过 shadow/canary/offline gate 验证，且安全字段显示 no production write / no canonical truth write / default off。 | 不能写成 live readback 或 production authorized。 |
| `live-readback` | 通过真实 `/api/v1/ws`、远端 QA WS、真实 DevTools/小程序入口或线上 readback 证明链路发生。 | 不能写成 production authorized。 |
| `production-authorized` | 用户/owner 明确授权 production default、published registry、canonical truth write、远端写或 broad rollout，并有 rollback/stop condition。 | 不能由测试、canary、脚本 exit 0 自动推导。 |

## 2. 当前总览

| Area | 当前状态 | 一句话判断 |
|---|---|---|
| Nexus / KnowQL 机制吸收 | `landed-local` | 研究与蓝图完整，已翻译进本地 artifact-first / single-authority 体系。 |
| KnowQL Phase A: canonical typed object | `runtime-consumed` | `luban_grading_object.v1` 已被 `rubric_grader_v1.canonicalize_rubric_points -> validate_grading_object` 非阻塞消费；仍非 production authorization。 |
| KnowQL Phase B: PGO grading contract / anti-over-credit | `shadow-verified` | PGO 合约、judge helpers、A/B、canary gate 已证明 review-only 能力；broad flip 仍 blocked。 |
| KnowQL Phase C: query language / executor | `live-readback` | `retrieve_rubric` 已被 PGO shadow review-only runtime consumer 调用，并通过本地真实 `/api/v1/ws` TestClient result event 读回。 |
| PGO runtime supply | `shadow-verified` | `case_rubric_scored_pgo` 已 hash-pinned、default off、published false、no minted scores。 |
| PGO Grading-to-Brain closure | `live-readback` | 本地真实 `/api/v1/ws` TestClient 已闭合 PGO same-attempt artifact_version -> point verdict -> preview learning_evidence -> learner_memory_event -> scoring-point read-model -> NextBestAction；仍 `canonical_truth_written=false`，不是 production authorization。 |
| Production default / canonical learner truth | `planned` | 没有授权，不得宣称 production ready。 |

## 3. 计划项落地表

| # | 计划项 | Authority / 文件 | 当前状态 | 证据 | 下一 promotion gate |
|---:|---|---|---|---|---|
| 1 | Nexus essence research | `nexus_essence_research.md` | `landed-local` | 明确公开可学机制：typed/governed artifacts、KnowQL JSON primitives、compile loop、shape/ground/budget。 | 不需要生产 gate；作为设计约束继续被 ledger 引用。 |
| 2 | KnowQL gap + second-authority audit | `current_state_gap_and_second_authority_audit.md` | `landed-local` | 四支柱成熟度、R1-R5、D1-D7 禁区已固化。 | 每次新增 query/executor/shape 前复核 D1-D7。 |
| 3 | Phase A canonical typed object | `UNIFIED_GRADING_OBJECT_SCHEMA.md`; `unified_grading_object.py`; `grading_object_adapters.py`; `rubric_grader_v1.canonicalize_rubric_points` | `runtime-consumed` | `canonicalize_rubric_points` 在 live scoring helper 中调用 `to_canonical_grading_object` + `validate_grading_object`，但 validation 当前是 non-blocking warning。 | 把更多 PGO output 直接 emit/validate 成 canonical schema；后续决定哪些路径从 non-blocking 升 fail-closed。 |
| 4 | Schema registry completeness | `SCHEMA_REGISTRY_COMPLETENESS.md`; `contracts/schema_registry.yaml`; `scripts/check_schema_registry.py` | `landed-local` | 173 schema identifiers 三层闭环，T1/T2/T3 分类已建。 | 确保 schema-registry guard 在 CI/contract guard 中持续执行，不只本地可跑。 |
| 5 | PGO deterministic compiler | `per_question_grading_object.py`; `test_per_question_grading_object.py` | `landed-local` | 官方答案 verbatim slice、per-point score null、must-not-mint、supporting citation 降级。 | 继续扩大真实题 coverage，并处理 key-validity / accepted variants。 |
| 6 | PGO grading contract | `build_grading_contract`; `validate_grading_contract` | `landed-local` | judge-ready contract 只给 official slices；textbook citations 进 supporting，不进 scoring authority。 | 被统一 query/executor 和 grader runtime 消费，而不是各自读 dict。 |
| 7 | PGO judge helpers / over-credit gate | `per_question_grading_judge.py`; `test_per_question_grading_judge.py` | `landed-local` | `runtime_points_from_grading_contract`、coverage score、`detect_over_credit`。 | 与 production grader 的 slot/canary 路径保持一致；避免并行判分逻辑。 |
| 8 | A/B and five-arm evaluation | `run_luban_per_question_grading_ab.py`; `KNOWQL_BUILDOUT_BLUEPRINT.md` §8-10 | `shadow-verified` | B atomic contract 在 review-only eval 中 anti-over-credit 和 MAE 表现强；RAG 判分被证明有噪声风险。 | 用独立人工 gold / scaled gold / real student flow 区分局部优势与 broad default。 |
| 9 | PGO runtime supply packaging | `case_rubric_pgo_supply.py`; `build_luban_pgo_runtime_supply.py`; `verify_luban_pgo_runtime_supply.py` | `shadow-verified` | `case_rubric_scored_pgo` 179 questions / 1384 points，hash pointer，published false，production_default off，no minted scores。 | Broad flip 前必须过 human-boundary blocker、worker restart evidence、rollback drill。 |
| 10 | Slot-aware PGO bank reader | `rubric_grader_v1._rubric_bank`; `LUBAN_CASE_RUBRIC_BANK_SLOT` | `shadow-verified` | Stage5 canary fresh-process loader reads `slot=pgo`, `question_count=179`, `scoring_point_count=1384`; same report still says `production_default_flip_allowed=false` and `actual_worker_restarted=false`。 | 仍需 owner 授权和 live worker restart 证据，不能默认 pgo。 |
| 11 | DeepQuestion PGO shadow attachment | `deep_question.py::_maybe_attach_pgo_shadow`; `test_deep_question_case_rubric_v1.py`; `test_luban_pgo_knowql_ws_readback.py` | `live-readback` | `_maybe_attach_pgo_shadow` is wired in `deep_question` runtime path, gated by request flag + env + qa/test/operator cohort, and local real `/api/v1/ws` TestClient result event reads back `luban_case_rubric_pgo_shadow` with no production grade/write flags。验证：`pytest tests/integration/test_luban_pgo_knowql_ws_readback.py -q`。 | 远端 QA WS / DevTools true-entry readback；仍不得写 learner canonical truth。 |
| 12 | Narrow KnowQL in-memory query stub | `m35_artifact_query.retrieve_m35_scoring_context` | `stub` | 可从传入 `artifact_store` 返回 shape/ground/confidence/budget，无 raw chunks。 | 保留为 fixture helper；不要把它当真实 runtime supply executor。 |
| 13 | PGO-backed `retrieveRubric` executor | `m35_artifact_query.retrieve_rubric`; `deep_question._maybe_attach_pgo_shadow`; `test_m35_artifact_query.py`; `test_deep_question_case_rubric_v1.py`; `test_luban_pgo_knowql_ws_readback.py` | `live-readback` | 读取 hash-pinned PGO supply；校验 bank hash / pointer / namespace / default off / record-level no official score + no canonical write；按 question_id deterministic filter；PGO shadow review-only consumer 通过 query contract 调用，并只挂 `knowql_query` 安全摘要；本地真实 `/api/v1/ws` TestClient result event 读回 `runtime_consumed=true`、known qid `found=true`、missing qid `fail_open=true`、非 QA 用户无 shadow。验证：`pytest tests/services/construction_grading/test_m35_artifact_query.py -q`、`pytest tests/core/test_deep_question_case_rubric_v1.py::test_pgo_shadow_consumes_retrieve_rubric_without_leaking_official_slice tests/core/test_deep_question_case_rubric_v1.py::test_pgo_shadow_consumes_real_hash_pinned_supply_as_safe_summary tests/core/test_deep_question_case_rubric_v1.py::test_pgo_shadow_records_retrieve_rubric_fail_open_without_mutating_legacy -q`、`pytest tests/integration/test_luban_pgo_knowql_ws_readback.py -q`。 | 远端 QA WS / DevTools true-entry readback，再进入 PGO same-attempt Grading-to-Brain readback；不能因此升 production。 |
| 14 | Shape-specific query projection | `retrieveRubric(... shape=...)`; `m35_artifact_query._project_pgo_record` | `landed-local` | `grading/rubric_table` 保留 teacher-only 内部 scoring projection；`explanation/review_action` 返回 learner-safe projection 并标记 `teacher_only_fields_redacted=true`，不返回 `official_slice`、score authority 或 answer-key authority。验证：`pytest tests/services/construction_grading/test_m35_artifact_query.py::test_retrieve_rubric_explanation_projection_hides_teacher_only_fields -q`。 | 继续为 `point_matches` / `review_plan` 补真实 consumer，不得把 learner-safe projection 用作 grader authority。 |
| 15 | Ground as runtime gate | `ground` primitive / citation_required | `landed-local` | PGO executor 当前把 official_slice 计作 ground；旧 stub 统计 source_refs。 | 区分 score-bearing official slices、supporting textbook refs、unsourced/pending points；无 ground 的 scoring shape fail open。 |
| 16 | Budget primitive | `budget_tier` | `stub` | query 返回 budget tier；PGO executor 标记 deterministic runtime。 | 接入 token/latency/cost metrics，证明不再每次 broad retrieval。 |
| 17 | Explanation/review-plan KnowQL consumer | report / learner-facing explanation | `planned` | 计划存在，但当前没有稳定 consumer 通过 `retrieve_rubric` 拿 explanation/review fields。 | 先建 review-only projection，不泄露官方答案逐字文本到微信端。 |
| 18 | Learning evidence from PGO point verdicts | `construction_grading.writeback.record_pgo_shadow_to_brain`; `test_pgo_grading_to_brain_writeback.py`; `test_luban_pgo_knowql_ws_readback.py`; `contracts/learner-state.md` | `live-readback` | PGO shadow `shadow_status=ok` 时，经现有 `LearnerStateService.append_memory_event(memory_kind="learning_evidence")` 写入 preview-only evidence；payload 带 `artifact_version=case_rubric_scored_pgo`、point verdicts、coverage 摘要，且断言不持久化逐字 official slice、`claim_promotion_allowed=false`、`canonical_truth_written=false`。验证：`pytest tests/services/construction_grading/test_pgo_grading_to_brain_writeback.py tests/integration/test_luban_pgo_knowql_ws_readback.py -q`。 | 远端 QA/DevTools true-entry readback；再扩真实 point-verdict producer，而不是测试 monkeypatch。 |
| 19 | Scoring point map / weakness read-model | `learner_state.scoring_point_map_read_model`; `record_pgo_shadow_to_brain`; `test_luban_pgo_knowql_ws_readback.py` | `live-readback` | 同一 `/api/v1/ws` attempt 产生的 PGO learning_evidence 可由 `build_scoring_point_map_read_projection` 读回，PGO point_id `P2` 成为 weakness item，authority 保持 `learner_memory_events.learning_evidence`。 | 验证 point_id namespace / alias table，避免 PGO epoch 与旧 bank 弱点重复计数。 |
| 20 | PersonalizationContextPack / NextBestAction from PGO evidence | `learner_state.next_best_action.build_next_best_actions`; `public_grading_to_brain_meta`; `test_pgo_grading_to_brain_writeback.py`; `test_luban_pgo_knowql_ws_readback.py` | `live-readback` | G3 readback 从 scoring-point map 的 `next_action.intent` 派生 `NextBestAction` 安全投影，下发 metadata 只含展示字段与 `prescription_authority=training_intent`，不下发内部 intent/evidence graph。 | PCP rich projection 与 PGO retest outcome 仍未闭合；下一步做 #21 retest delta。 |
| 21 | Retest condition/result loop | Grading-to-Brain loop | `planned` | 只在目标链路中定义；PGO specific retest evidence 未闭合。 | 同一 learner 的 retest delta 回读，不能靠 hermetic trace 冒充。 |
| 22 | Teacher review / compiler feedback flywheel | `compiler_feedback.py`; teacher review plans | `planned` | 计划要求 teacher override / source conflict 只产 candidate/work_order。 | PGO low-confidence / override 进入 compiler feedback，不直接改 release truth。 |
| 23 | Production default / published registry / canonical truth | M33/M35 authorization gates | `planned` | 当前 PGO supply default off、published false；canary gate也不授权 broad default。 | 用户/owner 明确授权 + rollback + live observability + no broad blocker。 |

## 4. 当前最容易被误报的地方

1. `retrieve_rubric` 现在只在本地 TestClient `/api/v1/ws` 达到 `live-readback`，不是 grader default、不是 remote QA readback、不是 production authorization。
2. PGO supply 是 `shadow-verified`，不是 `production-authorized`。`production_default=off` 和 `published=false` 是设计内的安全事实。
3. Grading-to-Brain 对 PGO 已达本地 `live-readback`，但只限 review-only preview evidence；不能写成 remote QA、DevTools true-entry、production default 或 canonical learner truth。
4. `canary_go` 只能说明 QA/operator canary 可继续，不代表 broad default。
5. `landed-local` 的代码若在 dirty `main` 中尚未提交，不能被汇报成 origin/main 或线上事实。

## 4.1 2026-06-15 校准记录

本 ledger 首版之后做过一次证据校准，避免状态偏乐观：

- C1 更新：PGO shadow review-only runtime consumer `deep_question._maybe_attach_pgo_shadow` 调用 `retrieve_rubric`，并把结果压缩成 `knowql_query` 安全摘要；当时 #13 只升到 `runtime-consumed`，不代表 production authorization。
- G2 更新：`tests/integration/test_luban_pgo_knowql_ws_readback.py` 通过本地真实 `/api/v1/ws` TestClient result event 读回 PGO shadow `knowql_query.runtime_consumed=true`；known qid `found=true`，missing qid `fail_open=true`，non-QA user blocked；因此 #11/#13 可升 `live-readback`，但仍不是 remote/production。
- G3 更新：`record_pgo_shadow_to_brain` 接到 `deep_question._maybe_attach_pgo_shadow` 的 `shadow_status=ok` 分支；同一 `/api/v1/ws` attempt 写入现有 `learner_memory_events.learning_evidence`，再由 scoring-point read-model 和 `build_next_best_actions` 读回。所有证据保持 preview-only、无 official slice 持久化、无 official score、`claim_promotion_allowed=false`、`canonical_truth_written=false`。
- `to_canonical_grading_object` 调用搜索结果：`rubric_grader_v1.canonicalize_rubric_points` 在 runtime helper 中调用 `validate_grading_object`，但 validation 是 non-blocking warning；因此 Phase A 可保留 `runtime-consumed`，但不能写 fail-closed。
- `deep_question._maybe_attach_pgo_shadow` 已在 runtime path 接线，但必须满足 request flag、env kill switch、qa/test/operator cohort；因此是 `runtime-consumed`，不是 `live-readback`。
- `scripts/run_luban_pgo_stage5_canary_gate.py` 当前结果是 `qa_operator_canary_go`，同时明确 `production_default_flip_allowed=false`、`canonical_write_allowed=false`、`remote_write_allowed=false`、`actual_worker_restarted=false`，且 human-boundary gold PO slice 标 `broad_flip_blocker=true`。因此 PGO supply/slot reader 最高只到 `shadow-verified`。
- learner read-model / NextBestAction 已有 PGO-specific same-attempt closure；PCP rich projection、retest delta 和 remote true-entry 仍未闭合。

## 5. 下一步排序

按收益和风险，后续应按这个顺序推进：

1. **补远端 QA / DevTools true-entry readback**：把本地 TestClient G2/G3 证据推进到远端 QA WS 或微信 DevTools 真实入口，但仍不授权 production default。
2. **补 PGO retest delta (#21)**：同一 learner 的 PGO weakness -> targeted retest -> improvement/readback，仍保持 `canonical_truth_written=false`，不能靠 hermetic trace 冒充。
3. **扩展 learner-safe consumer**：report preview / explanation / review plan 可读 `retrieve_rubric` 的 safe projection，但不得把 learner-safe projection 反向用作 grader authority。
4. **再谈 production authorization**：只有 live readback、human-boundary blocker、rollback、worker restart、observability 都闭合后，才进入 default flip 授权讨论。

## 6. 更新规则

每次推进 KnowQL 相关工作，必须同步更新本 ledger：

- 修改状态时写明 evidence 文件、测试命令或 gate 报告。
- 禁止跳级：`planned -> production-authorized`、`landed-local -> live-readback` 这类都必须有中间证据。
- 如果某计划项被证明不该做，状态改为 `planned` 并在下一步写 `delete / demote`，不要留成永远 pending。
- 若新增新 schema / query shape / consumer，先确认它不违反 `current_state_gap_and_second_authority_audit.md` 的 D1-D7。
