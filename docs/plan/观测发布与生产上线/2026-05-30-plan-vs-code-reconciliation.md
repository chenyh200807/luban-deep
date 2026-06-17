# 2026-05-30 Plan-vs-Code 对照报告

- **标题**: DeepTutor 计划自述 vs 代码事实对照报告（18 簇核验快照）
- **日期**: 2026-05-30
- **类型**: Reconciliation Report
- **状态**: v1
- **主线归属**: 生产部署 / Observability 与 release gate（挂 [INDEX.md](../INDEX.md) §7）

> **单一权威声明**：本报告是 2026-05-30 一轮 18 簇 plan-vs-code 核验的**快照**，**不替代各计划正文的 authority**，只记录核验当时（2026-05-30）的代码事实，用来消除"计划自述 vs 实际落地"的偏差，避免后续 agent 误判进度而重复修补。任何与本报告冲突的后续代码变更，以代码为准；任何方向/设计的 authority 仍在各计划正文。各计划的 PRD / Implementation Plan 仍是该主线的单一权威；本报告只做事实对照，不引入第二套方向。

---

## §1 总体结论

18 簇核验里，代码事实与文档自述的关系分布：

- **9 簇 `ahead_of_doc`（代码领先文档）**：统一聊天入口、学习事实编译、学情页 read model、钱包/会员/身份、摸底测评/Assessment、微信渲染外两簇（注：渲染簇判 matches）、佑森融合+Active Object、上线前清单 SR1-SR6、Web Search + RAG 诊断。
- **6 簇 `matches`（代码与自述一致）**：学员长期状态/Memory/Overlay、学习事实召回（RAG provenance/compiled truth）、学情顶级优化三计划、学情工作台新方向、案例题阅卷/错因图谱、微信结构化渲染、Observability 面板、反馈 Top10/Hermes/OpenMAIC（注：内部含局部 ahead）。
- **2 簇 `behind_doc`（自述比代码乐观/滞后）**：BI 后台 + 高危动作安全 + 反馈接入（高危动作零代码、BI v2 默认灰度关、反馈接入 Draft 滞后于已合 main）、Benchmark 主脊梁 + Harness 9+（gate 有牙但未接 CI PR 门禁）。

**核心判断**：绝大多数主线**代码已真实落地且接线进生产主链路**，内测可用性达标，不需要为"补功能"返工。真正的缺口收敛为三类：

1. **开关决策（flag flip）**：多条体验增强默认 OFF（合规安全姿态），需主动决策翻到哪个 stage——`DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED`、`LEARNING_STATE_INFERENCE_V2`、RAG `provenance_boost/compiled_truth`、`semantic_router` primary-vs-shadow、`ASSESSMENT_SESSIONS_USE_SUPABASE`。
2. **人工 / 运营 release gate**：真机回归、观察期指标、生产 migration apply 实证、kill-switch drill、cohort A/B 报告——代码无法自证，必须人工签字。
3. **真缺口 + 文档失真**：少数真未落地（Track A/B lifecycle fixture、presentation_type 契约、高危动作安全栏杆、harness gate 接 CI、nightly synthesis 调度器、RAG golden set），叠加多份"已上线/已落地"计划自述仍停在 Draft（钱包、上线前清单、反馈 BI、Assessment durability）违反单一权威纪律。

---

## §2 18 簇对照总表

证据符号取自核验 output 每簇 evidence 字段（file:line 为核验当时位置，索引滞后写入约 1s，以代码为准）。

| 主线（簇） | 自述状态 | 代码事实 | 关键证据符号 | 产品影响 | 上线关键 | 主要缺口 |
| --- | --- | --- | --- | --- | --- | --- |
| 统一聊天入口 + 题目生命周期 authority 收权 | PRD Done v1 / Consolidation Active v1 / 4-week Proposed v1 | ahead_of_doc | `/api/v1/ws`=唯一聊天 ws（`main.py:619`），竞争 ws 在 `_legacy_routers_enabled()` 门内生产默认 OFF（`main.py:119-123,581-593`）；`resolve_question_lifecycle_scene_decision`（`orchestrator.py:188-244`）前门裁判；kill-switch `QUESTION_LIFECYCLE_DECISION_AUTHORITY` default=True（`orchestrator.py:329`）；下游收权 `loop.py:760-762/1997/2640-2643`；`check_contract_guard.py:280` 单写者门禁；Track C/D `check_secure_routers.sh`/`check_rls_on_create_table.sh` 已接 `tests.yml:113-116` | 5 | 是 | Track A lifecycle red-line fixture/replay 未落（P1）；Track B `presentation_type` 显式契约全仓缺失（P1）；Task 7 真机 canary（P2） |
| 学员长期状态 / Memory / Bot-Learner Overlay | PRD Partially Implemented v1 / completion-evidence 已收口 | matches | `LearnerStateService`（`learner_state/service.py:137`）11 处调用；`BotLearnerOverlayService.apply_promotions`（`overlay_service.py:733`）被 `turn_runtime.py:2032-2036`；`main.py:281` 无 flag 启动 runtime；migration `20260415000100/000200/20260419000100` 三件齐 | 4 | 否 | 生产 migration/RLS apply 独立验收（P1）；heartbeat 频控/退订闭环（P1）；promotion 质量抽检/5万压测（P2） |
| 学习事实编译（Learning Brain / GBrain） | Implemented locally all phases / live verified；部署 deferred | ahead_of_doc | `build_learning_evidence_payload`（`learning_evidence.py`）→ `write_grading_error_events`（`writeback.py:17`）← `deep_question.py:2336`；`synthesize_learning_truth`（`learning_synthesis.py:26`）；`read_compiled_learning_truth`（`service.py:378`）；nightly `scripts/run_learning_synthesis.py`；mobile `learning-brain/projection`（`mobile.py:2144`） | 4 | 否 | nightly synthesis 无自动调度器（仅手动/外部 cron 触发，P1）；线上 Langfuse trace 关联 deferred（P2） |
| 学习事实召回增强（RAG query plan/provenance/compiled truth/typed graph） | Implemented + controlled live gate / Phase D flag off | matches | `build_retrieval_plan`（`retrieval_plan.py:108`）；`materialize_compiled_truth_documents`（`compiled_truth_source.py:306`）；`apply_provenance_ranking`+`build_ranking_trace`（`provenance.py:66/114`）；exact authority 双护栏 `provenance.py:102-110`+`_pin_exact_question_results`（`supabase.py:661`）；`COMPILED_TRUTH_ENABLED`/`PROVENANCE_BOOST_ENABLED` 默认 False（`supabase.py:1675/1688`，git 433e8eef） | 4 | 否 | Phase D 终态仍默认 OFF，shadow-only，学生未感知个性化召回（P1，设计上的安全门非缺陷）；live-gate 仅单次窗口无观察期（P2） |
| 学情页 read model 收敛（learning-report-read-model） | Local Acceptance Gate Passed — Pending Production Observation | ahead_of_doc | `GET /mobile/learning-report`（`mobile.py:2161-2181`）→ `build_learning_report_read_model`（`learning_report_read_model.py:139`）；`progress_source` 硬编码 `learner_memory_events.learning_evidence`（:311）；旧 projection 降级为 `legacy_compat` 输入源；超文档：`schema_version=2`/`scoring_point_map`/`revalidation_queue`/mistake_book 路由已落地 | 5 | 否 | §定量删除门槛 14 天生产观察未启动（P2）；真机 wx-devtools E2E §D 回填空（P2）；P0-4 双端 shared view-model 未抽（P1） |
| 学情顶级优化 + 学习状态推断引擎 + 历史证据闭环（05-21/05-22/05-23） | Proposed/Re-evaluated；Implemented locally through Batch D；Tasks 1-5 | matches | flag `_LSI_FLAG="LEARNING_STATE_INFERENCE_V2"`（`learning_report_read_model.py:126`）默认 OFF（`experiments/cohort.py:19-20`，全仓无 .env 配置）；Batch B/C/D 模块全在（`learning_state_projection.py`/`scoring_point_map_read_model.py`/`prescription_outcome_read_model.py`/`revalidation_queue.py`/`evidence_story_read_model.py`）；`attempt_detail_read_model.py` 历史回放+`_sanitize_history_text`；migration `20260521000100_learner_mistake_book_items.sql`（RLS owner policy） | 5 | 否 | 生产 flag 未开+migration apply 未确认（P1，学生侧 0 可见）；scoring_point_map map_eligible 仅 48.7%<70% 门槛（P1，数据/教研 backlog）；release promotion gate 全 pending（P2） |
| 学情工作台 笔记/日历 + 考点地图（新方向） | PRD Proposed v0.4 / P0A v0.1 / 设计 v0.1 | matches | `NotebookCardService`/`learner_notebook_cards`/`notebook_card` codegraph 全 No results；无 notebook cards writer 路由、无 knowledge-map 端点、无相关 migration（与 Proposed 自述一致）；既有锚点真实存在：`record_notebook_writeback`（`service.py:1340`）、`_writeback_learner_state`（`notebook/service.py:242`） | 3 | 否 | NotebookCardService+表+RLS 零代码（P2，新方向）；既有 notebook 手动收藏仍走重路径污染 learner-state（P1，需核实线上是否已暴露入口）；考点地图端点未实现（P2） |
| 钱包 / 会员 / 身份 single authority | INDEX PRD Draft v3 / Impl Draft v1 / RLS Appendix Draft（自述"尚未动工"） | ahead_of_doc | `SupabaseWalletService`+`debit/grant/refund/record_usage_points`（`wallet/service.py`）经 `_mutate_points:525`→RPC；migration `20260419000300_wallet_mutation_rpc.sql`（`for update` 行锁+ledger+projection 单事务+幂等键+P0001）；硬余额门 `mobile.py:577`；`DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED` 默认 OFF（`service.py:28`）；读链已切 wallet（`mobile.py:1996/2014/2048`）；AI 扣点 `turn_runtime.py:2206-2232`；#81 `audit_wallet_projection_consistency.py:43` Σdelta；RLS migration `20260530000100_rls_harden_wallets.sql` | 5 | 是 | INDEX/正文自述严重落后于代码（P1，文档治理，本报告 C档#12 已回写）；WP2 身份归一化层（`identity.py`/影子ID hard-fail/owner_key 迁移）落地未确认（P1）；写链 cutover release gate 人工/观察期（P2） |
| BI 经营后台 + 高危动作安全 + 反馈接入（三计划合并） | Plan1 Batch0-7 完成 v1 / Plan2 Proposed 只规划 / Plan3 Draft | behind_doc | Plan3 反馈已活跃：`LubanFeedbackStore`（`luban_feedback_store.py:187`）+ 路由 `bi.py:374/393/401`（`require_bi_admin`）+ `BiLubanFeedbackTab`（`BiPageClient.tsx:1220`）；Plan1 built-but-dark：6 个 `BI_*_V2` flag default false（`bi-feature-flags.ts:59-64`）；Plan2 零代码：无 `revoke_subscription_v2`/`undo_token`/`subscription_version`，线上 `/api/v1/member/revoke`/`/grant`（`member.py:518/548`）仍 v1 无保护 | 3 | 是 | 高危动作无 ETag/version/undo_token/dry-run（**P0**，Plan2 整套零代码，2026-05-24 QA 已判 B-P1-8 blocker）；Plan1 自述 Batch0-7 完成但 v2 全默认灰度关（P1）；Plan3 Draft 滞后于已 merge 31a4482d（P2） |
| 摸底测评 / Assessment TestSet / 2026 源知识编译 | Blueprint Implemented locally；TestSet v0.3 durability"P0A BLOCKED until table exists"；P0A migration applied；P0B/P1 Implemented locally；compiler PR-1/2/3 | ahead_of_doc | migration `20260524000100_assessment_sessions.sql`（RLS owner + submit_idempotency 唯一索引 + active-session 唯一索引，PR #42 6a5dad2e）；`session_repository.py` InMemory+Supabase 双实现；`_build_assessment_session_repository`（`service.py:544`）production/`ASSESSMENT_SESSIONS_USE_SUPABASE=true` 走 durable；逐题 `AssessmentWritebackService.writeback`（`writeback.py:15`）；`apply_2026_compiler_backfill.py:9` 硬 REFUSAL 拒 `--apply` | 5 | 是 | WeChat DevTools 真机手动门 P0A+P0B（**P0**，真实学生出卷-答卷-计分链路）；错题"练 3 道同类题"训练闭环未落代码（P1）；TestSet v0.3 正文 durability"BLOCKED"段脱节（P2，本报告 C档#12 已回写）；生产需实证 `ASSESSMENT_SESSIONS_USE_SUPABASE` 避免静默回落 InMemory（P1） |
| 案例题阅卷 / 错因图谱 / 轻量出题+深度解释 | PRD Proposed v1.7 / 薄外壳 v3 / 轻量出题 v3 | matches | `process_batch_lightweight`（`generator.py:45`）公开 `correct_answer=""`、隐藏 `grading_key.scoring_points`（`generator.py:157-162`）；`CaseGradingSkillKernel.grade`（`case_kernel.py:26`）4 档 authority；`grade_mcq_submission`（`mcq.py:64`）；`SubmissionGraderAgent.process`（`submission_grader_agent.py:35`）；`write_grading_error_events`（`writeback.py:17`）；`_extract_latest_next_training_signal`（`deep_question.py:1407`） | 5 | 是 | 个性化变式训练推荐器（priority_score/weakness_score）不存在（P2，P1 增强）；`VariantValidator` 不存在（P2）；命名漂移 `grade_choice`→`grade_mcq_submission`（P2，纯命名） |
| 微信结构化教学渲染 + Markdown authority + harness visible_sections | PRD P0-P3 闭环 P2/P3 真机待 / Markdown Implemented P0-P1 / Harness Draft | matches | `build_canonical_presentation`（`render_presentation.py:1020`）四处调用（`tutorbot.py:510`/`deep_question.py:1995`/`sqlite_store.py:607`/`mobile.py:1679`）；双端 `render-schema.js` 字节级一致（23784B）；`test_renderer_authority.js` 17 PASS / golden corpus 82 PASS / parity 11 PASS；harness `visible_sections`（`learning_brain_read_model.py:79`）+ `WechatHarnessClient.tsx:409` | 5 | 是 | P2/P3 真机 gate（公式/表格/图表窄屏可读性，**P1**，唯一 launch-critical 缺口）；harness P1 生产门 flag 分叉（`page.tsx` 用不同 env flag，P2）；公式渲染主路径真机不确定（P2） |
| 佑森融合 + Active Object 语义路由 | 融合 PRD Draft v1 / Active Object Implemented v1 | ahead_of_doc | `semantic_router.py`（`resolve_turn_semantic_decision:594` 等）；orchestrator primary/shadow/disabled 三态（`orchestrator.py:204-311`）；`_semantic_router_enabled` 默认 `default=True`（`orchestrator.py:490`）=primary 默认 ON（比文档建议的渐进灰度更激进）；`scripts/run_semantic_router_eval.py`/`report_semantic_router_rollout.py`；佑森 `app.json` 注册 `packageDeeptutor` 14 页分包 | 5 | 是 | semantic_router primary 默认 ON 跳过 shadow 灰度顺序（P1，需确认生产 .env + eval 基线）；佑森融合真机编译/login→chat 打透/后台开关联调（P1，人工 gate）；lesson_topic 未升级独立 active_object（P2，有意收敛） |
| Observability ARR/AAE/OA/OM + 上线 readiness 面板 | PRD Proposed / Dashboard Implemented locally P0-P2 | matches | `build_launch_readiness_dashboard`（`launch_readiness.py:524`）missing→NOT_RUN；路由 `GET /launch-readiness`（`observability.py:97`）；`ObservabilityControlPlaneStore`（`control_plane_store.py:87`）；全套 runner service 在；21 个测试文件 | 2 | 否 | CI/部署无 job 调用 `run_readiness_check`/`run_release_gate`/`run_observability_daily`，生产 control_plane store 不被自动写入（P1，计划 Current Risks #1 已点名）；ClickHouse 后端零实现（P2）；readiness_checks 以文件目录为 store 非 Postgres（P2，合规过渡） |
| Benchmark 主脊梁 + Harness 世界级 9+ | single-spine Proposed Phase1 / harness 窄 P0 active / 9plus ~7 H1/H4/H5 已上线 | behind_doc | `services/benchmark/` cassette/llm_replay/rag_replay/exam_quality_eval 全在；`check_harness_authority.py` AST import-graph；`eval/gates.yaml` 定义 harness gate；fixtures+ledger 齐；**证伪**：`.github/workflows/` 对 `run_eval_gate`/`check_harness_authority`/`exam_quality` 全 0 命中，gate 有牙但不在 PR 上自动咬 | 3 | 否 | harness gate 未接任何 workflow（P1，`run_eval_gate.py` CI 零调用，与"接 CI"自述不符=behind_doc 根因）；single-spine PRD §16 6 问未完整落地（P2）；H2/H3/H6/H7 未落地（P2，诚实标注资源受限） |
| 部署 / 规模化 / 上线前清单（SR1-SR6 + active-turn-capacity） | prelaunch Draft v2.1 G1-G9 未标 Done / active-turn-capacity Proposed | ahead_of_doc | SR1 `_secure_router.py`+`check_secure_routers.sh` 接 `tests.yml:113`；SR2 `check_rls_on_create_table.sh` 接 `tests.yml:116`+#75/#82 RLS；SR3 `route_rate_limit`+`enforce_websocket_rate_limit`；SR4 `openai_http_client.py` 三 factory；SR5 `/readyz`；SR6 `runtime/safety.py` 接 `main.py`+`tests.yml:124`；active-turn-capacity 0 行代码（Proposed 属实） | 5 | 是 | `runtime_route_inventory.py`（Layer B 真边界）存在但未接 CI（P1）；`supabase/schema_baselines/` 目录不存在（P2，债务）；prelaunch 文件头仍 Draft v2.1 无验收日期（P1，文档失真，本报告 C档#12 已回写）；23 处 bare APIRouter 待迁（P2，分批） |
| 联网搜索 + RAG 诊断优先 | Web Search Proposed v1 / RAG 诊断 v3.2 T1/T2/T4 完成 | ahead_of_doc | `is_web_search_runtime_available()`（`search/__init__.py:193`）fail-closed 门 12 处接线；`SearxngProvider`（`searxng.py:27`）无 silent fallback；RAG 两 FF 默认 OFF（`supabase.py:1675/1688`，git 433e8eef）；`eval/gates.yaml:70` `rag_retrieval_quality` 注册+self-skip | 3 | 否 | SearXNG 部署+P0 硬验收未跑通（P1，未部署=学生联网工具被过滤）；RAG golden set 仅 template scaffold（P1，T3 双盲标注未做）；RAG baseline+T8 报告未产出（P2）；两 FF staging delta 未验证（P2，默认 OFF 合规） |
| 反馈 Top10 + 反馈中心 + Hermes + OpenMAIC | Top10 Batch1-4/A-H Implemented locally / 反馈中心 Draft / Hermes Proposed / OpenMAIC Canonical | matches（含局部 ahead） | `coerce_user_visible_answer`（`user_visible_output.py:130`）被 `guard_output`/`manager.send_message:780`；`exam_track.py` normalizer 全套；反馈中心已落地（store+路由+migration `20260529000100`+survey，commit ed7e07f7/ba81af1d/225bd9a1）；Hermes 仅 scripts inventory 无 runtime；OpenMAIC 零代码（`exam_classroom`/`LessonIRService` 全 No results） | 4 | 否 | Top10 真机 iOS/Android smoke pending（P2，人工 gate）；练题结构化 config 未完全收敛（P2）；真实微信支付链路不存在（P1，内测可不靠支付）；反馈中心 Draft 滞后于代码（P2，本报告 C档#12 已回写）；OpenMAIC Canonical 易误读为已落地（P2）；Hermes 无 runtime（P2，正确） |

---

## §3 上线必做清单（三档）

### A 档 — 上线前硬门槛（不过不能开放注册）

| # | 项目 | severity | reason |
| --- | --- | --- | --- |
| A1 | BI 后台**保持只读**，不开放任何高危写入口（撤销会员/补点/改套餐）；若必须开放写，先落地 Plan2 的 ETag/version + undo_token + dry-run（目前零代码） | P0 | 高危写动作无安全栏杆直接改付费用户权益与钱包；线上 `/api/v1/member/revoke`/`/grant` 仍 v1 无保护，2026-05-24 QA 已判 B-P1-8 blocker |
| A2 | Assessment WeChat DevTools 真入口手动门（P0A/P0B 共用）：验 deferred feedback 无答案泄露 + 断网恢复 + 提交幂等 | P0 | 内测面向真实学生，出卷-答卷-计分链路真机缺陷会直接污染学情 |
| A3 | 生产侧实证 `ASSESSMENT_SESSIONS_USE_SUPABASE` 已生效、migration `20260524000100` 已 apply | P1（接近 P0） | `_build_assessment_session_repository` 在 Supabase 未配置且非 production 时**静默回落 InMemory**，正式测评 session 随重启丢失 |
| A4 | 微信渲染 P2/P3 真机抽样（iPhone+Android 中/低端机窄屏：公式/表格/图表 block 可读性 + 降级） | P1（唯一 launch-critical 渲染缺口） | API 单测通过≠小程序入口体验合格；公式 SVG/中文混排真机清晰度无法从代码判定 |
| A5 | 确认生产 Supabase 已 apply learner-state 三个 migration（尤其 RLS），含 `learner_mistake_book_items` | P1 | RLS/权限若未正确 apply，含学情数据的表存在越权读风险 |

### B 档 — 决定最佳体验的开关决策与真缺口

| # | 项目 | severity | reason |
| --- | --- | --- | --- |
| B1 | **flag flip 决策**（详见 `2026-05-30-prod-state-and-flag-flip-decision.md`）：billing enforcement（翻 ON 前先确认 WP2 身份归一化）、`LEARNING_STATE_INFERENCE_V2` 开到哪个 stage、`semantic_router` 确认 primary 还是收回 shadow、RAG 两 FF 是否翻 | P1 | 这些是体验增强/计费启用的总闸，默认 OFF/激进 ON 都需主动决策，不能默认漂移 |
| B2 | `semantic_router` primary 默认 ON：用 `report_semantic_router_rollout.py` 跑基线确认误切率/shadow_disagreement_rate 可接受，否则把默认收回 shadow | P1 | 新路由当主判断 authority 上内测，误切对象/答非所问会直接打到核心聊天体验，缺默认 shadow 安全垫 |
| B3 | Track B `presentation_type` 显式契约（`contracts/turn.md` + writer 显式设置 + renderer 只读） | P1 | 讲评卡被误当可提交练习卡→学员误提交污染数据 |
| B4 | Track A lifecycle red-line fixture + replay + CI gate | P1 | 红线回归只靠人工维护的 acceptance 测试，lifecycle authority drift 无 CI 阻断 |
| B5 | heartbeat 主动触达频控/退订兜底闭环 | P1 | 主动 heartbeat 无频控在内测真人面前可能造成骚扰式触达 |
| B6 | 核实线上 notebook 手动收藏入口是否已暴露；若暴露，优先把 `_writeback_learner_state` 重路径对主观笔记收权 | P1 | 主观笔记走重路径（refresh_from_turn summary 改写 + patch_overlay）会污染学情判断真相 |
| B7 | scoring_point_map map_eligible 仅 48.7%<70%：维持 honest empty state，待教研 normalization 把覆盖率抬到 70% 再开 action_loop 子门 | P1 | 现在开 action_loop 多数案例题学生只会看到空态 |

### C 档 — 低成本兑现 + 文档治理

| # | 项目 | severity | reason |
| --- | --- | --- | --- |
| C1 | harness 三个 quick gate（authority_guard + authority_baseline + trajectory_replay）接进 `tests.yml`（一行 `python scripts/run_eval_gate.py --category quick`） | P1 | 已建好且有牙的网在 PR 上自动咬，低成本直接兑现"单一权威强制 + 防重判复发"承诺 |
| C2 | `run_readiness_check`/`run_release_gate`/`run_observability_daily` 接入部署或定时 job | P1 | 否则生产 control_plane store 永远空，go/no-go 散落人工脚本（约半天工作量） |
| C3 | `run_learning_synthesis.py` 接真实定时触发（cron/scheduler） | P1 | 否则 compiled truth 不自动刷新，"反复漏点"诊断与降权不自动出现 |
| C4 | `runtime_route_inventory.py`（Layer B 真边界）接进 CI 跑；补 `supabase/schema_baselines/` dump | P1/P2 | SR1 只装 Layer A（grep）等于回到"靠自觉"；schema_baselines 为审计对照档 |
| C5 | 错题"练 3 道同类题"训练闭环（flywheel §507） | P1 | "测完→针对性复练"闭环断在错题集，训练处方侧未补齐（计划内未到非倒退） |
| C6 | SearXNG 部署 + 显式 enabled + P0 验收（按 ROI 上线后推进） | P1 | 未部署=联网工具被 fail-closed 过滤，功能等于不存在（内测非核心） |
| ... | （C7-C11 其余 P2：harness gate flag 分叉对齐、RAG golden 标注、active-turn-capacity 维持 Proposed、命名漂移、真机 E2E 回填） | P2 | 详见 §2 各簇缺口列 | |
| **C12** | **文档失真状态回写（本报告同批已执行）**：(1) 钱包 INDEX 三行 + PRD/Impl 正文 §3.1/§5 已标"代码已实现 enforcement OFF / WP2 待确认"；(2) prelaunch 文件头 + INDEX 行已标"SR1-SR6 已落 main+接 CI，人工 gate 待补，G1-G9 验收日期待人工填"；(3) 反馈 BI 集成 INDEX 行已回写"Implemented"；(4) Assessment PRD §0.2/§10.4 durability"BLOCKED"段已标"migration `20260524000100` 已落 main，生产 apply 待实证"。 | P1 | 多份"已上线/已落地"计划自述停在 Draft，违反单一权威纪律，后续 agent 读 Draft 会误判"还没做"而重复修补 |

---

## §4 现在不要做（明确排除）

以下属新方向、运营层或资源受限项，内测（邀请制 <100 DAU）**不投入代码**，避免分散上线焦点：

- **学情工作台新方向**（`NotebookCardService` / `learner_notebook_cards` / 考点地图 `knowledge-map` 端点）：self-declared Proposed 与代码现实一致，零代码属实；内测体验不依赖，待核心闭环稳定后再排期。
- **OpenMAIC 互动课堂**：全主线零代码（无表/无 service/无路由），INDEX 标 Canonical/Accepted 是文档 authority 等级**不是实现状态**；排在出题/阅卷主链路稳定之后。
- **Hermes 增长代理运营**：故意不进 runtime（只有 scripts inventory/哨兵），硬边界明确不做阅卷/学情/会员/runtime authority；无需落代码。
- **active-turn-capacity 50-120**：0 行代码（admission/redis_admission/event_stream/worker/postgres_store 全部不存在），Proposed 属实；内测 <100 DAU 不构成阻塞，规模化前置项。
- **RAG 两 FF（provenance_boost / compiled_truth）翻 ON**：默认 OFF 符合 contract `rag.md` §20/§22，是安全态；翻开需先在 staging 跑完 P0-1 baseline 比对 true-vs-false delta，**不要在上线前贸然翻 flag**。

---

## §5 关联文件（本报告引用到的计划）

- [INDEX.md](../INDEX.md)（计划目录索引）
- [2026-05-30-prod-state-and-flag-flip-decision.md](2026-05-30-prod-state-and-flag-flip-decision.md)（生产核验 + flag 翻转决策单，配套）
- [2026-04-15-unified-ws-full-tutorbot-prd.md](../题目生命周期与助教运行时/2026-04-15-unified-ws-full-tutorbot-prd.md) / [2026-05-26-deeptutor-question-lifecycle-authority-consolidation-plan.md](../题目生命周期与助教运行时/2026-05-26-deeptutor-question-lifecycle-authority-consolidation-plan.md) / [2026-05-28-luban-4-week-critical-path-hardening-execution-plan.md](2026-05-28-luban-4-week-critical-path-hardening-execution-plan.md)
- [2026-04-15-learner-state-memory-guided-learning-prd.md](../学习脑与学员记忆/2026-04-15-learner-state-memory-guided-learning-prd.md) / [2026-04-15-bot-learner-overlay-prd.md](../学习脑与学员记忆/2026-04-15-bot-learner-overlay-prd.md) / [2026-04-24-learner-state-overlay-completion-evidence.md](../学习脑与学员记忆/2026-04-24-learner-state-overlay-completion-evidence.md)
- [2026-05-18-luban-learning-brain-gbrain-absorption-prd.md](../学习脑与学员记忆/2026-05-18-luban-learning-brain-gbrain-absorption-prd.md) / [2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md](../学习脑与学员记忆/2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md) / [2026-05-18-deeptutor-learning-fact-retrieval-gap-closure-plan.md](../学习脑与学员记忆/2026-05-18-deeptutor-learning-fact-retrieval-gap-closure-plan.md)
- [2026-05-20-luban-learning-report-read-model-execution-plan.md](../学习脑与学员记忆/2026-05-20-luban-learning-report-read-model-execution-plan.md) / [2026-05-21-luban-learning-report-system-review.md](../学习脑与学员记忆/2026-05-21-luban-learning-report-system-review.md) / [2026-05-21-luban-learning-report-world-class-optimization-plan.md](../学习脑与学员记忆/2026-05-21-luban-learning-report-world-class-optimization-plan.md) / [2026-05-22-luban-learning-state-inference-engine-transformation-plan.md](../学习脑与学员记忆/2026-05-22-luban-learning-state-inference-engine-transformation-plan.md) / [2026-05-23-luban-learning-history-evidence-closed-loop-plan.md](../学习脑与学员记忆/2026-05-23-luban-learning-history-evidence-closed-loop-plan.md)
- [2026-05-26-luban-learner-workspace-notebook-calendar-prd.md](../学习脑与学员记忆/2026-05-26-luban-learner-workspace-notebook-calendar-prd.md) / [2026-05-26-luban-learner-workspace-notebook-calendar-p0a-execution-plan.md](../学习脑与学员记忆/2026-05-26-luban-learner-workspace-notebook-calendar-p0a-execution-plan.md) / [2026-05-26-luban-syllabus-knowledge-map-design.md](../学习脑与学员记忆/2026-05-26-luban-syllabus-knowledge-map-design.md)
- [2026-04-19-supabase-wallet-single-authority-prd.md](../会员钱包计费与经营后台/2026-04-19-supabase-wallet-single-authority-prd.md) / [2026-04-19-supabase-wallet-single-authority-implementation-plan.md](../会员钱包计费与经营后台/2026-04-19-supabase-wallet-single-authority-implementation-plan.md) / [2026-04-19-supabase-wallet-rls-appendix.md](../会员钱包计费与经营后台/2026-04-19-supabase-wallet-rls-appendix.md) / [../../runbook/2026-05-30-billing-go-live-runbook.md](../../runbook/2026-05-30-billing-go-live-runbook.md)
- [2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md](../会员钱包计费与经营后台/2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md) / [2026-05-24-bi-high-risk-actions-safety-contract-plan.md](../会员钱包计费与经营后台/2026-05-24-bi-high-risk-actions-safety-contract-plan.md)
- [2026-05-24-luban-assessment-testset-module-prd.md](../测评题库与考试模块/2026-05-24-luban-assessment-testset-module-prd.md) / [2026-05-24-luban-assessment-testset-p0a-execution-plan.md](../测评题库与考试模块/2026-05-24-luban-assessment-testset-p0a-execution-plan.md) / [2026-05-25-luban-assessment-testset-p0b-p1-production-flywheel-execution-plan.md](../测评题库与考试模块/2026-05-25-luban-assessment-testset-p0b-p1-production-flywheel-execution-plan.md) / [2026-05-24-luban-2026-source-knowledge-compiler-execution-plan-v0-2.md](../知识编译与检索/2026-05-24-luban-2026-source-knowledge-compiler-execution-plan-v0-2.md)
- [2026-05-13-luban-case-grading-error-map-prd.md](../题目生命周期与助教运行时/2026-05-13-luban-case-grading-error-map-prd.md) / [2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md](../题目生命周期与助教运行时/2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md) / [2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md](../题目生命周期与助教运行时/2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md)
- [2026-04-16-wechat-structured-teaching-renderer-prd.md](../微信小程序与结构化渲染/2026-04-16-wechat-structured-teaching-renderer-prd.md) / [2026-05-13-wechat-renderer-markdown-authority-implementation-plan.md](../微信小程序与结构化渲染/2026-05-13-wechat-renderer-markdown-authority-implementation-plan.md) / [2026-05-19-wechat-harness-visible-sections-contract-fix-plan.md](../微信小程序与结构化渲染/2026-05-19-wechat-harness-visible-sections-contract-fix-plan.md)
- [2026-04-15-yousen-deeptutor-fusion-prd.md](../微信小程序与结构化渲染/2026-04-15-yousen-deeptutor-fusion-prd.md) / [2026-04-18-llm-native-active-object-semantic-router-prd.md](../题目生命周期与助教运行时/2026-04-18-llm-native-active-object-semantic-router-prd.md)
- [2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md](2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md) / [2026-05-18-deeptutor-launch-readiness-dashboard-implementation-plan.md](2026-05-18-deeptutor-launch-readiness-dashboard-implementation-plan.md)
- [2026-04-23-deeptutor-benchmark-single-spine-prd.md](../回归测试工程与质量门/2026-04-23-deeptutor-benchmark-single-spine-prd.md) / [2026-05-27-luban-harness-engineering-single-authority-world-class-execution-plan.md](../回归测试工程与质量门/2026-05-27-luban-harness-engineering-single-authority-world-class-execution-plan.md) / [2026-05-27-luban-harness-world-class-9plus-roadmap.md](../回归测试工程与质量门/2026-05-27-luban-harness-world-class-9plus-roadmap.md)
- [2026-05-25-prelaunch-readiness-checklist.md](2026-05-25-prelaunch-readiness-checklist.md) / [2026-04-19-deeptutor-50000-member-deployment-prd.md](2026-04-19-deeptutor-50000-member-deployment-prd.md) / [2026-05-17-deeptutor-active-turn-capacity-implementation-plan.md](2026-05-17-deeptutor-active-turn-capacity-implementation-plan.md)
- [2026-05-03-deeptutor-web-search-stack-prd.md](../知识编译与检索/2026-05-03-deeptutor-web-search-stack-prd.md) / [2026-05-28-rag-diagnostic-first-prd.md](../知识编译与检索/2026-05-28-rag-diagnostic-first-prd.md)
- [2026-04-24-luban-feedback-top10-root-cause-fix-plan.md](../用户反馈与体验闭环/2026-04-24-luban-feedback-top10-root-cause-fix-plan.md) / [2026-05-29-luban-feedback-bi-integration-plan.md](../会员钱包计费与经营后台/2026-05-29-luban-feedback-bi-integration-plan.md) / [2026-05-27-hermes-growth-agency-master-plan.md](../增长运营/2026-05-27-hermes-growth-agency-master-plan.md) / [../../openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md](../../openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md)
