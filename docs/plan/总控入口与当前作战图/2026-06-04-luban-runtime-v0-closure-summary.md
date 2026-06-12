# 鲁班评分引擎 runtime v0 收口 —— 六线并行交付总结（2026-06-04）

> Status: `landed (QA-gated / dry_run / candidate_only)`。**未改 `CaseGradingSkillKernel`、未新增数据库表、RAG 未进评分 authority、未接 production grading authority / production default、未写真实用户/生产库、未把未复核 AI-Draft 写入 Learning Brain、未重跑大规模 485/QWK/consensus。**
> 本文档只覆盖本轮（runtime v0 收口）六条线交付与验收。**Registry/runtime-gate 的单一权威冲突已收口**（见 §单一权威收口）：现在只有一条 canonical 链路 `QuestionGradingArtifact Registry v0 → ArtifactRuntimeGate → RuntimeShadowAdapter → QA/test real-chain shadow`，不再有双 authority。历史上曾有并行会话的另一版实现（`2026-06-04-luban-grading-engine-ai-draft-test-ab-plan.md`）与本轮口径并存，现已统一。
> **模型分工**：当前打造期主引擎是 `Best-Quality 4-model jury`（GPT5.5 + Opus4.8 + DeepSeek + Qwen3.7），用于拉高评分/证据/teacher-review draft 的质量上限；`DeepSeek production-cost grader` 只是未来低成本单模型自动写权候选。DeepSeek gate 不得阻塞 Best-Quality QA、teacher-final 写回、Learning Brain synthesis 或 GBrain 个性化 pack 建设。

## 三原则落实

- **Thin wrappers, fat skills**：评分/裁决/发布门/写回转换/学情合成全部在 service/skill 层；router/前端零规则。B(pilot)、D(synthesis)、A(registry) 均复用既有 `ai_draft_shadow` guards / `build_learning_evidence_payload` / `best_quality_for_golden`，未另造第二套逻辑。
- **First principles**：一次学生作答 → Best-Quality draft → teacher review → writeback(dry_run) → Learning Brain readback → weakness/mastery/suggestion，端到端在 pilot 中真实跑通（5 份准真实样本）。
- **Less is more**：无新表、无新 endpoint、无大平台；B 直接复用 D 的 `synthesize_learner_profile`（签名匹配，未退化为内联聚合）。

## 六线交付

| 线 | 类型 | 产物 | 测试 | 结果 |
|---|---|---|---|---|
| A 发布门 Registry | code | `question_grading_registry.py`（`build_registry`/`get_question_grading_artifact`/`auto_certification_allowed`/`_refine_status` 新增 blocked）、`scripts/build_luban_question_grading_registry_v0.py` | `test_question_grading_registry.py` 19 | ✅ published=18/draft=1/blocked=1（Q15-NA 0 auto+high_risk→blocked；Q20 0 auto 无 high_risk→draft） |
| B teacher-review pilot | code+artifacts | `teacher_review_pilot.py`、`scripts/run_luban_teacher_review_pilot.py`、`artifacts/.../teacher_review_pilot_20260604/`（5 样本 + `learning_brain_synthesis.json` + FINDING） | `test_luban_teacher_review_pilot.py` 8 | ✅ teacher-final 覆盖 AI、high_risk 未确认不写 mastery、weakness 4 / mastered 6 / suggestions 4，准真实标注 `reviewer_is_synthetic=true` |
| C 真实链路接入设计 | planning | `2026-06-04-luban-real-answer-runtime-test-integration-plan.md` | planning-only | ✅ 逐行核验生产入口 + `grading_engine_runtime_test` flag 设计 + 回滚 + fail-closed |
| D 学情合成 adapter | code | `learning_brain_synthesis.py`（`synthesize_learner_profile`） | `test_learning_brain_synthesis.py` 9 | ✅ weakness/mastery/suggestion；mastery 单一权威只读 `mastery_eligible`，high_risk 未确认绝不计 mastery |
| E 蒸馏样本准备 | code+artifacts | `scripts/build_luban_distillation_samples_v0.py`、`artifacts/.../distillation_samples_v0_20260604/`（485 样本 JSONL + manifest） | `test_build_luban_distillation_samples_v0.py` 6 | ✅ gold=418/pending=66/unsupported=1；未确认 high_risk 当 gold 正确 = 0；纪律分层 exact_required_discipline=73/list_rule_partial=53 |
| F 性能与异步 UX 方案 | planning | `2026-06-04-luban-grading-async-ux-runtime-plan.md` | planning-only | ✅ 复用既有 BackgroundTasks+TaskIDManager+SSE 三件套（无需新队列）；cached-replay 单题裁决 median 7.5ms / live 四模型 p50 8-20s 估算；submit/poll/stream 接口草案 + Fast vs Best 场景划分 |

**合并测试**：本轮新测 + 关键回归 `98 passed`；`construction_grading` 全量 `154 passed` 无回归。三脚本均确定性可复现（artifacts/ 已 gitignore）。

## 验收问题逐一回答

1. **全题库 artifact 发布系统是否已有 v0？** 有。Registry v0（A）把 20 题机制升级为 published/draft/blocked 发布门 + runtime helper。**尚非"全题库"**——目前只覆盖 20 题 golden，全题库放量是下一步。
2. **20 题 published/draft/blocked 各多少？** 单一来源 runtime gate 口径：**published=18 / draft=1（Q20-1A413000）/ blocked=1（Q15-NA）**（已收口，见 §单一权威收口）。
3. **真实/准真实 teacher-review pilot 是否打通？** 打通（B）。5 份准真实样本（exact_required 近义 / list_rule 不全 / calculation 错 / 基本正确 / penalty override）走完 draft→review→writeback(dry_run)→readback；明确标注准真实，未写真实用户。
4. **Learning Brain 是否能读回 weakness/mastery？** 能（D+B）。pilot 读回 weakness 4（E09×3/E03×5/E02×1/E12×1）、mastered 6、suggestions 4。
5. **真实答题链路 runtime 接入点在哪里？** 已定位（C）：生产热路径 `/api/v1/ws`→`deep_question.py`→`deep_question_adapter.py:64`→`case_kernel.py:27 grade()`；写回唯一口 `writeback.py:17`（生产触发 `deep_question.py:1421`）。接入点 = harness 层 `grading_engine_runtime_test` flag，**不挂生产热路径**。
6. **Best-Quality 蒸馏样本是否准备好？** 准备好（E）：485 条 JSONL，含 question/artifact/answer/adjudicated point_result/evidence_span/rationale/high_risk_reason/model_votes，纪律分层标注；未训练、未接生产。
7. **性能/异步方案是什么？** F：复用既有进程内异步范式（BackgroundTasks+TaskIDManager+SSE），submit/poll/stream + timeout(20s)/partial/fail-closed；Fast=实时低成本同步，Best=异步强制（老师工作台/高价值高争议题）。
8. **下一步是否可进入真实答题链路 runtime test？** 可以。Registry/gate 单一权威已收口（见 §单一权威收口），`runtime_shadow_adapter` 已进入 QA/test-only live hook：`DeepQuestionCapability._emit_grading_result` 在 legacy `construction_grading_result` 之后按 `grading_engine_runtime_shadow` / `grading_engine_runtime_shadow_mode` 旁路 append `luban_grading_engine_shadow`。默认关闭，不替换 legacy，不写 Learning Brain，可进入 QA 用户真实提交 shadow 小批。
9. **是否没有新增表？** 没有。
10. **是否没有改 kernel / RAG / production runtime？** 没有。

## 单一权威收口（2026-06-04，已完成）

之前 Registry/runtime-gate 一度双轨（两份产物目录 + 脚本写旧目录），现已收成一套单一权威：

**唯一 canonical 链路**：
`QuestionGradingArtifact Registry v0`（`question_grading_registry.py`，权威源 = golden fixture 投影，不依赖产物目录）
→ `ArtifactRuntimeGate`（`artifact_runtime_gate.py`，**唯一** runtime auto-certification gate，只 import registry）
→ `AI-Draft / Best-Quality`（`build_ai_draft` 通过 `apply_runtime_artifact_gate` 应用门；`best_quality_draft` 转发 `artifact_gate`，**不复制门规则**）
→ `RuntimeShadowAdapter`（`runtime_shadow_adapter.py`，只 `resolve_runtime_artifact_gate` 消费门，不复制、无 kernel/RAG/DB）
→ `QA/test real-chain shadow`（`deep_question.py` 只读 QA/test flag 并 append shadow payload，零评分规则；route/前端只薄传递 + 展示 gate 状态）。

- **canonical 产物目录**：`artifacts/luban_grading_artifacts/registry_v0_20260604/`（`question_grading_artifacts.jsonl` / `question_grading_registry.json` / `publish_report.json` / `registry_report.json` / `FINDING_*.md`）。
- **superseded 产物目录**：`artifacts/luban_consensus_gold/question_grading_registry_v0_20260604/`（保留为陈旧快照，已写 `SUPERSEDED.md`；代码/脚本/文档不再当 authority）。
- `scripts/build_luban_question_grading_registry_v0.py` 默认输出与 `--out-dir` 默认均改为 canonical；并在旧目录写 `SUPERSEDED.md`。
- **runtime status（单一来源）**：published=18 / draft=1 / blocked=1（Q15-NA→blocked `zero_auto_certifiable_with_high_risk`；Q20-1A413000→draft `no_auto_certifiable_points`；Q17-1A433000→published；UNKNOWN→artifact_missing）。weak source 点恒 `auto_certifiable=False`，绝不伪造教材锚点。
- **职责边界**：artifact gate 管 auto-certification；QA/test live shadow 只 append 非正式 payload；teacher-final 管 Learning Brain 写入；三者不混（teacher-review/learning_evidence 不反向决定 artifact status，shadow 不写成绩或 memory）。
- 测试：指定 6 文件子集 73 passed；`construction_grading` 全量 162 passed 无回归。无新表 / 未改 kernel / RAG 未进评分 authority / 未接 production runtime。

## /api/v1/ws QA runtime-shadow smoke（2026-06-04，canonical = 真实 WS TestClient turn smoke）

**唯一 canonical runtime-shadow 证据** = 真实 FastAPI TestClient `/api/v1/ws` 帧级 smoke：
`tests/api/test_luban_ws_runtime_shadow_turn_smoke.py` + `scripts/run_luban_ws_runtime_shadow_turn_smoke.py`，产物 `artifacts/luban_consensus_gold/ws_runtime_shadow_turn_smoke_20260604/`。

- **真实层级（turn_smoke）**：REAL = FastAPI TestClient `/api/v1/ws` 帧 → `TurnRuntimeManager.start_turn`（temp SQLite session store）→ `ChatOrchestrator.handle` → `DeepQuestionCapability.run` → `_emit_grading_result` 顶层 RESULT metadata append → `RuntimeShadowAdapter` + Registry v0 + ArtifactRuntimeGate；SIMULATED = LLM/SubmissionGraderAgent 文本、memory/learner-state、Best-Quality 引擎调用；NO-WRITE = Learning Brain 写回被 monkeypatch 仅记 legacy 调用，shadow `writeback_performed=false`。
- **外部 flag 传入**：`payload.config.grading_engine_runtime_shadow=true`（可选 `..._engine`）→ `request_config=dict(payload["config"])` → `UnifiedContext.config_overrides`，**无需改 wrapper**；student_id 经 `metadata.billing_context.user_id`（绑定认证用户）；adapter 仅接受 `qa_`/`test_` 前缀。
- **结论**：flag off→客户端 RESULT 帧无 shadow；flag on（QA）→帧含 `luban_grading_engine_shadow`，legacy `construction_grading_result` 逐样本字节不变（`legacy_equal=true`）、`writeback_performed=false`；published/draft artifact_status 与 registry 单一来源一致、missing→`artifact_missing`、non-QA→`qa_student_required` 不跑引擎；positive point 带 evidence_span。canonical FINDING：`artifacts/luban_consensus_gold/ws_runtime_shadow_turn_smoke_20260604/FINDING_ws_runtime_shadow_canonical_20260604.md`。
- **superseded（仅 debug evidence，不作验收引用）**：capability.run RESULT-event 级的 `ws_runtime_shadow_smoke_20260604/`（已写 `SUPERSEDED.md`；其脚本/测试已删除）——低于真实 `/api/v1/ws` TestClient 层一级。
- **下一步（teacher-review 真实写回小批）可谨慎进入**，但需先定 shadow 引擎对新鲜 QA 作答的**预测来源**：(a) 经 submission 透传 `ai_draft_predictions`，或 (b) 为 QA 学生开 live provider 通道——当前 WS hook 对新鲜作答按设计 fail-closed。

## E2E 闭环 smoke v1（2026-06-04，已通；blocker 按裁决方案 B 收口）

把真实 WS shadow 与 teacher-final 真实写回串成一条端到端 QA 链路：
`真实 /api/v1/ws shadow → teacher-review payload → teacher-final 真实写回 MEMORY_EVENTS.jsonl → readback → Learning Brain synthesis → next suggestion`。

- 脚本 `scripts/run_luban_e2e_runtime_teacher_review_smoke.py` + 测试 `tests/integration/test_luban_e2e_runtime_teacher_review_smoke.py`（1 passed）；产物 `artifacts/luban_consensus_gold/e2e_runtime_teacher_review_smoke_20260604/`。
- 实测：`entry_layer=fastapi_testclient_ws`、`ws_shadow_count=3`、`legacy_unchanged=true`、`shadow_writeback_performed=false`、`teacher_final_writeback_count=3`、`memory_events_jsonl_count=3`、`has_weakness=true`、`has_next_suggestion=true`、`teacher_reviewed_false_writeback_count=0`。
- **blocker 收口（裁决方案 B）**：原 blocker 是测试不变式语义矛盾，**非 `teacher_review_writeback` bug**（其 `_mastery` 对 teacher override→hit 返回 `teacher_override_hit` 为有意为之）。artifact gate / high_risk / unsupported 只限制 **AI auto-certification**；teacher-final override 是更高 authority，可升级 mastery；未复核 / 非 override 的 high_risk/unsupported 仍不得 mastery。测试断言由 `high_risk_or_unsupported_mastery_ids==[]` 改为三不变式：`non_override_high_risk_or_unsupported_mastery_ids==[]` + `unreviewed_high_risk_or_unsupported_mastery_ids==[]` + `teacher_override_high_risk_or_unsupported_mastery` 每项 `authority=="teacher_override"`（记录 source/evidence_span）。summary/artifact 补出这三字段；`teacher_review_writeback.py` 权威规则未改；`main()` 直调 `run_smoke` 无 NameError。
- 正向 override→mastery 权威由现有 `tests/integration/test_luban_teacher_review_real_writeback.py::test_mastery_gating_and_override_authority`（`authority=="teacher_override"`）覆盖。
- 回归：闭环组合 11 passed；`construction_grading` + 两个 integration + ws-turn 广回归 182 passed 无回归。预测来源仍诚实标注为 deterministic fixture（live provider 留 v2）。

## Canonical Evidence Map

`docs/plan/INDEX.md` 只做导航；鲁班评分引擎 runtime v0 的详细证据以本表为权威入口（INDEX 不再承载历史流水账）。

| 能力 / 环节 | canonical 代码 | canonical 产物 / 测试 | 状态 |
|---|---|---|---|
| 题目级发布门 Registry v0 | `deeptutor/services/construction_grading/question_grading_registry.py` | `artifacts/luban_grading_artifacts/registry_v0_20260604/`（含 FINDING）；`tests/services/construction_grading/test_question_grading_registry.py` | ✅ published=18 / draft=1（Q20）/ blocked=1（Q15-NA） |
| Runtime 自动认证门 | `deeptutor/services/construction_grading/artifact_runtime_gate.py`（唯一 gate；`build_ai_draft`/`best_quality_draft` 透传 `artifact_gate` 不复制） | `tests/services/construction_grading/test_artifact_runtime_gate.py` | ✅ published 才 auto；只降级不升级 |
| WS runtime-shadow smoke | `scripts/run_luban_ws_runtime_shadow_turn_smoke.py` | `artifacts/luban_consensus_gold/ws_runtime_shadow_turn_smoke_20260604/`（含 `FINDING_ws_runtime_shadow_canonical_20260604.md`）；`tests/api/test_luban_ws_runtime_shadow_turn_smoke.py` | ✅ canonical（真实 `/api/v1/ws` 帧）；capability.run 级 `ws_runtime_shadow_smoke_20260604/` 已 `SUPERSEDED` |
| Teacher-review 真实文件后端写回 v2 | `deeptutor/services/construction_grading/teacher_review_writeback.py` | `artifacts/luban_consensus_gold/teacher_review_real_writeback_v2_20260604/`；`tests/integration/test_luban_teacher_review_real_writeback.py` | ✅ 真实 `LearnerStateService` 写 `MEMORY_EVENTS.jsonl` |
| E2E 闭环 smoke v1 | `scripts/run_luban_e2e_runtime_teacher_review_smoke.py` | `artifacts/luban_consensus_gold/e2e_runtime_teacher_review_smoke_20260604/`；`tests/integration/test_luban_e2e_runtime_teacher_review_smoke.py` | ✅ WS shadow → teacher-final 写回 → readback → next suggestion（blocker 按方案 B 收口） |
| 学情合成 | `deeptutor/services/learner_state/service.py::synthesize_learning_truth` + `learning_brain_synthesis.py` | E2E 产物 `learning_brain_synthesis.json` / `next_suggestion_preview.json` | ✅ |
| 方法学 / 历史指标 | — | `docs/plan/2026-06-03-luban-consensus-gold-protocol.md` §14–17（485 / QWK / 选择性弃权） | 历史只读 |

**当前真实瓶颈（2026-06-04 更正）**：早前「全题库 v1 数据不足 / data_blocked」结论**错误**——只扫了当前 repo，漏掉同级 `FastAPI20251222/docs/2026/题库`（2015–2025 一建建筑实务真题，**218 道 case_study**）+ `2026教材/第二次加强/FINAL_CLEANED_BOOK2026-*_fixed.json`（650 content_blocks，verbatim 教材锚源）。**Registry v1 阻塞点是采分点结构化 + 教材逐字锚定 + 复核 pipeline 未放量，不是题目数据缺失。** M3 已对首批 30 道结构化（138 采分点 / 28 verbatim 教材锚 / 16 published_candidate_not_final / 14 draft，见 `artifacts/luban_grading_artifacts/case_rubric_structuring_m3_20260604/`）；题库 explanation/official_answer 只作 weak source，textbook verified 仅来自 2026 教材。
**下一步两条并行主线**：(1) 全题库案例题采分点 / 知识编译数据扩产；(2) QA 产品测试真实化（Best-Quality live jury 优先 + 老师工作台真人复核 + outbox→Supabase sync），并行把 Best-Quality 裁决蒸馏/压缩到 DeepSeek production-cost grader。

## 红线确认

Best-Quality 是当前打造期能力天花板；DeepSeek 是未来生产成本线，不是当前主线 blocker；teacher-final 才是 Learning Brain 写入 authority；artifact published 才能 auto_certified；high_risk/unsupported 不自动变 mastery（teacher override 例外，作为更高 authority）。
