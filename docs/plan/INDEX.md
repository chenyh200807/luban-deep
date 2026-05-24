# DeepTutor 计划目录索引

> 本目录是 DeepTutor 的计划、PRD、实施计划、设计稿、验收清单的统一地图。以后新增、修改、审查 PRD 或模块改造计划前，先读本文件，再进入具体计划文档。

## 使用规则

1. 先从本索引确认当前模块属于哪条计划主线，不要只按文件名猜。
2. 涉及 `turn/session/stream/replay/resume`、聊天入口、TutorBot、trace/observability 的改动，仍必须先读根目录 `CONTRACT.md` 与 `contracts/index.yaml`。
3. 新增计划文件统一放在 `docs/plan/`，命名格式为 `YYYY-MM-DD-<domain>-<topic>-<type>.md`。
4. 每个新增计划至少要说明：目标、非目标、单一 authority、实施阶段、验收标准、相关代码入口。
5. 如果一个新计划只是已有计划的补充，优先在本索引中挂到原主线下，不要并行制造第二套主线。
6. 计划状态必须写清楚：`Proposed`、`Draft`、`Implemented`、`Done`、`Superseded` 或 `Historical`。

## 当前整理原则

当前先采用轻量整理：保留现有文件名和物理位置，用本索引建立清晰地图，避免大规模移动文件导致历史链接断裂。后续如果某条主线继续膨胀，再按本索引的领域分组拆子目录。

## 主线总览

| 主线 | 先读文件 | 适用场景 |
| --- | --- | --- |
| TutorBot 与统一聊天入口 | [2026-04-15-unified-ws-full-tutorbot-prd.md](2026-04-15-unified-ws-full-tutorbot-prd.md) | `/api/v1/ws`、TutorBot 完整 runtime、轻量 TutorBot 歧义清理 |
| 上游能力吸收 | [2026-05-12-upstream-p0-absorption-status.md](2026-05-12-upstream-p0-absorption-status.md) / [2026-05-12-upstream-p1-knowledge-absorption-status.md](2026-05-12-upstream-p1-knowledge-absorption-status.md) / [2026-05-12-upstream-p2-request-snapshot-contract.md](2026-05-12-upstream-p2-request-snapshot-contract.md) | HKUDS/DeepTutor v1.3.7-v1.3.10 runtime/stability、knowledge/RAG、request snapshot 能力选择性吸收 |
| 学员长期状态 | [2026-04-15-learner-state-memory-guided-learning-prd.md](2026-04-15-learner-state-memory-guided-learning-prd.md) | learner state、summary/profile/memory、Guided Learning、Heartbeat |
| 学习事实编译 / Evidence-first Memory | [2026-05-18-luban-learning-brain-gbrain-absorption-prd.md](2026-05-18-luban-learning-brain-gbrain-absorption-prd.md) / [2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md](2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md) / [2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md](2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md) / [2026-05-18-deeptutor-learning-fact-retrieval-gap-closure-plan.md](2026-05-18-deeptutor-learning-fact-retrieval-gap-closure-plan.md) / [2026-05-20-luban-learning-report-read-model-execution-plan.md](2026-05-20-luban-learning-report-read-model-execution-plan.md) / [2026-05-21-luban-learning-report-system-review.md](2026-05-21-luban-learning-report-system-review.md) / [2026-05-21-luban-learning-report-world-class-optimization-plan.md](2026-05-21-luban-learning-report-world-class-optimization-plan.md) / [2026-05-22-luban-learning-state-inference-engine-transformation-plan.md](2026-05-22-luban-learning-state-inference-engine-transformation-plan.md) / [2026-05-23-luban-learning-history-evidence-closed-loop-plan.md](2026-05-23-luban-learning-history-evidence-closed-loop-plan.md) | 吸收 GBrain 的 compiled truth + timeline、typed graph、evidence-first memory、nightly synthesis，并把召回升级为带 query plan、source-aware ranking、provenance 与 compiled truth source group 的学习事实召回；学习事实编译主 PRD 已本地实现并通过 `/wechat-harness` live visible-chain 验证，学情页 read model 已完成本地 acceptance gate，把页面读法收敛到 `learning_evidence` 事实 ledger，仍待生产 14 天观察门槛；2026-05-21 系统审查指出下一轮 P0 应收权错题集、attempt detail、训练 intent 与双端 view model，world-class 优化计划已拆成可执行任务；2026-05-22 在 world-class 计划之上叠加学习状态推断引擎改造计划，吸收深度调研报告并经 V3 现实校准：把学情模块定位升级为学习状态推断与个性化训练引擎，先在 Phase −1 落 rubric 覆盖率遥测+LLM grounding、错码登记表、`training_intent`/`study_plan` 单一权威调和、synthesis 性能基线，再分 Batch A-D 推进案例题 rubric 证据、三层学习画像、处方 intent v2、采分点漏分地图、复测闭环与证据链 projection；2026-05-23 追加历史对话证据闭环计划，明确作答复盘必须优先还原历史模块里的完整系统解析，学情页的弱点/错因/处方必须能点回具体历史错题和当时解释。 |
| Bot-Learner Overlay | [2026-04-15-bot-learner-overlay-prd.md](2026-04-15-bot-learner-overlay-prd.md) | 多 Bot 对同一学员的局部状态、promotion、仲裁 |
| 佑森小程序融合 | [2026-04-15-yousen-deeptutor-fusion-prd.md](2026-04-15-yousen-deeptutor-fusion-prd.md) | Yousen 原生入口、workspace shell、包内路由与页面体验 |
| 微信结构化渲染 | [2026-04-16-wechat-structured-teaching-renderer-prd.md](2026-04-16-wechat-structured-teaching-renderer-prd.md) / [2026-05-13-wechat-renderer-markdown-authority-implementation-plan.md](2026-05-13-wechat-renderer-markdown-authority-implementation-plan.md) | 小程序题卡、表格、公式、图表、教学 block 渲染、Markdown fallback 单一 authority 与 golden corpus |
| 上下文与语义连续性 | [2026-04-16-tutorbot-context-orchestration-prd.md](2026-04-16-tutorbot-context-orchestration-prd.md) | 每轮上下文包、预算、选择性加载、route 稳定性 |
| Active Object 与语义路由 | [2026-04-18-llm-native-active-object-semantic-router-prd.md](2026-04-18-llm-native-active-object-semantic-router-prd.md) | follow-up、当前题、当前对象、多对象切换、语义 route |
| 钱包与会员 authority | [2026-04-19-supabase-wallet-single-authority-prd.md](2026-04-19-supabase-wallet-single-authority-prd.md) | Supabase wallet、积分、会员、支付状态、身份归一化 |
| BI / 会员经营后台 | [2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md](2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md) | `/bi`、`/member`、经营总览、会员运营 CRM、套餐权益、充值账务、对话回顾、反馈中心、系统运维、成本质量、经营审计；把旧 BI / 会员后台草案收敛为“经营判断 -> 会员定位 -> 证据查看 -> 执行动作 -> 审计回看”的统一后台主线。 |
| 生产部署 | [2026-04-19-deeptutor-50000-member-deployment-prd.md](2026-04-19-deeptutor-50000-member-deployment-prd.md) / [2026-05-17-deeptutor-active-turn-capacity-implementation-plan.md](2026-05-17-deeptutor-active-turn-capacity-implementation-plan.md) / [2026-05-19-web-settings-bundle-budget-regression.md](2026-05-19-web-settings-bundle-budget-regression.md) | 5 万会员部署、50-120 active turn Phase 1 扩容、上线稳健性；`/settings` 路由 bundle 超 budget 50% 的 pre-existing regression 已记录待修 |
| 联网搜索能力 | [2026-05-03-deeptutor-web-search-stack-prd.md](2026-05-03-deeptutor-web-search-stack-prd.md) / [2026-05-03-deeptutor-web-search-stack-implementation-plan.md](2026-05-03-deeptutor-web-search-stack-implementation-plan.md) | SearXNG、`web_search` fail-closed enablement、搜索 provider/runtime 验收 |
| Observability 与 release gate | [2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md](2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md) / [2026-05-18-deeptutor-launch-readiness-dashboard-implementation-plan.md](2026-05-18-deeptutor-launch-readiness-dashboard-implementation-plan.md) | OM/ARR/AAE/OA、trace、surface ACK、release gate、上线 readiness 面板 |
| 鲁班智考个性化教学 | [2026-04-20-luban-adaptive-teaching-intelligence-prd.md](2026-04-20-luban-adaptive-teaching-intelligence-prd.md) / [2026-05-02-luban-assessment-blueprint-prd.md](2026-05-02-luban-assessment-blueprint-prd.md) / [2026-05-13-luban-case-grading-error-map-prd.md](2026-05-13-luban-case-grading-error-map-prd.md) / [2026-05-13-luban-case-grading-error-map-implementation-plan.md](2026-05-13-luban-case-grading-error-map-implementation-plan.md) / [2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md](2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md) / [2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md](2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md) / [2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md](2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md) / [2026-05-24-deeptutor-hermes-edu-skills-booster-plan.md](2026-05-24-deeptutor-hermes-edu-skills-booster-plan.md) | 因材施教、Learner Core、Teaching Policy、显性诊断、摸底测评蓝图、案例题 AI 阅卷与错因变式训练；P0 执行优先读 Skill-first 薄外壳计划，出题性能与答后解释质量收口读轻量出题与深度阅卷解释计划；2026-05-24 追加题目生命周期 skill authority 计划，要求 `deep_question`、TutorBot、follow-up、grading 共用 native skills，并明确当前 main 需要补齐 construction 场景 skill pack；同日新增 Hermes Edu Skills Booster 计划，将外部 188 个教育 Skill 转成只读 inventory、DeepTutor skill registry、validator、Hermes/Weixin sandbox 和未来可导出鲁班 construction skill pack，而不是引入第二套 production authority。 |
| 鲁班智考反馈 Top10 修复 | [2026-04-25-luban-feedback-top10-issue-register.md](2026-04-25-luban-feedback-top10-issue-register.md) / [2026-04-24-luban-feedback-top10-root-cause-fix-plan.md](2026-04-24-luban-feedback-top10-root-cause-fix-plan.md) | 运营反馈问题注册表、Langfuse/后台证据、Top10 root-cause 分批修复 |
| Benchmark 主脊梁 | [2026-04-23-deeptutor-benchmark-single-spine-prd.md](2026-04-23-deeptutor-benchmark-single-spine-prd.md) | benchmark、daily/gate/incident、质量单一主脊梁 |
| 建筑实务 AI 互动课堂 | [../openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md](../openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md) | OpenMAIC 体验对标、Lesson IR、微信小程序主表面、互动课堂生成、审核、导出、质量工厂 |
| 上游能力吸收 | [2026-05-03-upstream-absorption-status.md](2026-05-03-upstream-absorption-status.md) | HKUDS/DeepTutor 能力吸收状态、适用/不适用判断、验证证据 |
| 上游产品表面评审 | [2026-05-03-upstream-product-surface-review-intake.md](2026-05-03-upstream-product-surface-review-intake.md) | Book / Space / Co-writer / TutorBot channels 先做产品评审，不直接进入工程吸收队列 |

## 按领域索引

### 1. TutorBot / 聊天入口 / 模式

| 文件 | 类型 | 状态 | 说明 |
| --- | --- | --- | --- |
| [2026-04-15-unified-ws-full-tutorbot-prd.md](2026-04-15-unified-ws-full-tutorbot-prd.md) | PRD | Done v1 | 统一 `/api/v1/ws` 接入完整 TutorBot，清理轻量 TutorBot 歧义。 |
| [2026-04-16-tutorbot-context-orchestration-prd.md](2026-04-16-tutorbot-context-orchestration-prd.md) | PRD | Draft v1 | 每轮最小必要上下文包、预算、选择性加载与上下文编排。 |
| [2026-04-19-tutorbot-mode-policy-unified-authority-prd.md](2026-04-19-tutorbot-mode-policy-unified-authority-prd.md) | PRD | 未标注 | 三种回答模式统一挂载 TutorBot authority，模式只决定表达策略。 |
| [2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md](2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md) | Execution Plan | Proposed v2.1 (2026-05-24) | 把 TutorBot scene skills 升级为 DeepTutor 题目生命周期共享 skill library：TutorBot 负责教学身份与自由文本场景，`deep_question` 负责可提交题目生成/答题/批改，二者通过同一 `question_lifecycle_skill_context` 使用场景规则。v2 修订（§0 Revision Log 详列 R1-R12）：补 §5.0 Karpathy Gate worksheet；§5.1 把 scene 判定权收到 `ChatOrchestrator` 唯一一处，禁止下游再检测；§5.2 给旧 `ConstructionExamScene` Literal 设 alias map + 删除条件；新增 Task 2.5 在任何 wiring 前先把 `teaching_modes.get_construction_exam_skill_instruction` 这条绕开 `SkillsLoader` 的第二条 skill 加载路径收成 thin shim，杜绝第三条 loader 出现；§6.7 用 5 阶段灰度 + kill-switch drill 替换 v1 的“config switch”一句话；§6.1 把 `learning-evidence-story`/`study-assistant`/`learning-support` 三个 narration skill 约束为表达层 only（CI grep 禁止字段名/阈值/SQL），并预留合并成单一 `construction-learner-state-narration` 的选项；§6.5 增加 mixed-turn / resume / sticky-reveal / adversarial-prompt / dialect-fallback 5 类失败模式；§9 manual checks 加同 turn 提交+生成、断线重连、对抗 prompt 三条；§10 决策多学科扩展用 `(subject, scene)` 双键签名预留而本计划不实现第二学科；§11 完成清单加 v2-C1..C6 单一权威 grep / 灰度证据 / alias 删除条件六条 release gate。 |
| [2026-05-12-upstream-p0-absorption-status.md](2026-05-12-upstream-p0-absorption-status.md) | Evidence | Implemented locally | HKUDS/DeepTutor v1.3.7-v1.3.10 第一批 runtime/stability 能力吸收状态与跳过项。 |
| [2026-05-12-upstream-p1-knowledge-absorption-status.md](2026-05-12-upstream-p1-knowledge-absorption-status.md) | Evidence | Implemented locally | HKUDS/DeepTutor 第二批 knowledge/RAG 后端能力吸收状态与跳过项。 |
| [2026-05-12-upstream-p2-request-snapshot-contract.md](2026-05-12-upstream-p2-request-snapshot-contract.md) | Contract comparison | Draft / implementation target | 第三批 request snapshot / `metadata_json` 吸收边界，明确只归属 turn/session read model，不写 learner state。 |
| [2026-05-03-upstream-absorption-status.md](2026-05-03-upstream-absorption-status.md) | Evidence | Implemented | 上游 v1.3.5/v1.3.6 可用能力吸收状态、单一 authority 判断与验证证据。 |
| [2026-05-03-upstream-product-surface-review-intake.md](2026-05-03-upstream-product-surface-review-intake.md) | Intake | Proposed | 上游 Book / Space / Co-writer / TutorBot channels 进入产品评审，不直接搬代码。 |

### 2. Learner State / Memory / Overlay

| 文件 | 类型 | 状态 | 说明 |
| --- | --- | --- | --- |
| [2026-04-15-learner-state-memory-guided-learning-prd.md](2026-04-15-learner-state-memory-guided-learning-prd.md) | PRD | Partially Implemented v1 | 学员级长期状态、持久记忆、Guided Learning、Heartbeat 的主 PRD；repo foundation 已有，产品目的未全关。 |
| [2026-04-15-learner-state-service-design.md](2026-04-15-learner-state-service-design.md) | 设计稿 | Implemented foundation v1 | `LearnerStateService` 服务边界、读写模型、实施顺序。 |
| [2026-04-15-learner-state-supabase-schema-appendix.md](2026-04-15-learner-state-supabase-schema-appendix.md) | 附录 | Implemented foundation v1 | Learner State 的 Supabase schema 与迁移方案；生产实例执行未验收。 |
| [2026-04-15-bot-learner-overlay-prd.md](2026-04-15-bot-learner-overlay-prd.md) | PRD | Partially Implemented v1 | 跨 Bot learner overlay 的产品与架构主线；多 Bot 产品闭环未全关。 |
| [2026-04-15-bot-learner-overlay-service-design.md](2026-04-15-bot-learner-overlay-service-design.md) | 设计稿 | Implemented foundation v1 | `BotLearnerOverlayService` 服务设计。 |
| [2026-04-24-learner-state-overlay-completion-evidence.md](2026-04-24-learner-state-overlay-completion-evidence.md) | 复审证据 | Gap Review v1 | Learner State / Overlay 的 repo foundation 证据、未完成目标和下一步 gate。 |
| [2026-05-18-luban-learning-brain-gbrain-absorption-prd.md](2026-05-18-luban-learning-brain-gbrain-absorption-prd.md) | PRD | Implemented locally all phases + Web live verified | 将 GBrain 启发收敛为鲁班智考学习事实编译层：`learner_memory_events` 作 evidence ledger、`learner_summaries.summary_structured_json.learning_brain` 作 compiled truth projection、typed graph 作 JSON projection、nightly synthesis 离线生成教学事实；`/wechat-harness` 已完成 live visible-chain 验证。 |
| [2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md](2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md) | Implementation Plan | Implemented locally all phases + Web live verified | 把学习事实编译 PRD 拆成可执行任务：`learning_evidence` canonical payload、learner-state synthesis、typed graph projection/query、dry-run nightly script、deep_question 消费 compiled signal、Web QA handoff；已记录本地验证证据。 |
| [2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md](2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md) | Implementation Plan | Implemented + controlled live gate verified / Phase D flag off by default | 学习事实召回增强子计划：在现有 `RAGService` / `SupabasePipeline` 内实现显式 query plan、compiled truth source group、provenance-aware ranking、typed graph expansion、maintenance dry-run 与 eval gate；已通过 direct RAG、公共 `/api/v1/ws`、Langfuse / ClickHouse trace 证明 weak-point-only final-source 和 exact authority 不冲突，不新增第二套 RAG 或聊天入口。 |
| [2026-05-18-deeptutor-learning-fact-retrieval-gap-closure-plan.md](2026-05-18-deeptutor-learning-fact-retrieval-gap-closure-plan.md) | Gap Closure Plan | Completed / controlled live gate verified | 针对 learning-fact retrieval 子计划剩余差距做收口：live gate、Phase D 弱点召回生产验收、graph expansion 接入 RAG、TutorBot/runtime/fast-path compiled truth 传播、maintenance dry-run workflow、contract guard 与计划状态；生产开关已在验收后恢复默认关闭。 |
| [2026-05-20-luban-learning-report-read-model-execution-plan.md](2026-05-20-luban-learning-report-read-model-execution-plan.md) | Execution Plan | Local Acceptance Gate Passed — Pending Production Observation | 将小程序学情页读法收敛到 `GET /api/v1/mobile/learning-report`，完成数从 `learner_memory_events.learning_evidence` 聚合，旧 today-progress / mastery / assessment / learning-brain projection 接口保留后台兼容但不参与页面决策。Open Gaps G1-G7（attempt 口径、`source_status/degraded/degraded_sources`、`unknown_date_count`、`attempt_count/*_unique_questions/window_truncated`、yousen 入口收口、测试矩阵、INDEX 状态）已在本批次代码 + 测试关闭，并通过本地 API + 微信开发者工具 CLI acceptance gate；但 §定量删除门槛 未启动观察期（连续 14 天 5xx<0.1% / p95<800ms / degraded<1% + deprecated 接口 RPS=0 7 天），未达 Done。详见计划 §Local Acceptance Evidence / §Open Gaps。 |
| [2026-05-21-luban-learning-report-system-review.md](2026-05-21-luban-learning-report-system-review.md) | System Review | Review v1 / Optimization Backlog Proposed | 对学情模块作为核心产品系统做全面审查：当前 read model 方向正确且自动化基线通过，但仍存在 P0 缺口，包括错题集本机缓存、作答证据不可点击回放、下一步训练泛跳、wx/yousen 双端漂移、单次观察与稳定结论混杂。建议下一轮按 attempt detail、云端错题集、training intent、shared view model、掌握度 estimator 分阶段收口。 |
| [2026-05-22-luban-learning-state-inference-engine-transformation-plan.md](2026-05-22-luban-learning-state-inference-engine-transformation-plan.md) | Implementation Plan | Implemented locally through Batch D — Pending Manual / Production Release Gates | 在 world-class 学情页优化计划之上叠加的学习状态推断引擎改造计划，吸收《鲁班智考一建建筑实务学情诊断模块深度调研报告》。V3 现实校准后产出 4 个 Phase −1 前置任务：(0.A) `scripts/rubric_coverage_report.py` 测出 case_study `grading_rubric` 覆盖 0%、`grading_keywords` 49%、`structured_rules` 34%、map-eligible 48.7%，并把策略翻转为"normalize 现有字段 → projected scoring_points"+按 `node_code` 簇灰度点亮；(0.B) 落 `docs/contracts/error_code_registry.md`，统一 `E0X` (case) / `M0X` (MCQ) 错码与 ability_dimension 映射，新 rule type 没注册 contract guard 必须失败；(0.C) `study_plan` 改为读取 `active_training_intent`，杜绝双 prescription authority；(0.D) `scripts/bench_learning_synthesis.py` + p95≤200ms@2000-event 性能基线，windowing flag 带 `truncated=true`。Batch A-D 已本地实现案例题 rubric evidence、知识/能力/行为三层画像、tiered `DECAY_PROFILES` 与 ARRS 复测、`training_intent` v2、采分点漏分 per-cluster gate、prescription 验证 outcome、教师/销售证据链 projection、frontend inference audit、scenario matrix、release readiness 证据。当前剩余项是不可由本地代码伪造的 release promotion gates：教研 normalization preview sign-off、教研 graph seed review、WeChat DevTools 手工视觉/交互验收、cohort_10/cohort_50 A/B 报告、7 天生产指标、kill-switch drill 截图、合并回源工作区与 push/deploy。Feature flag `LEARNING_STATE_INFERENCE_V2` 走 internal→cohort_10→cohort_50→cohort_100→sticky_100；A/B 走 sequential gate（cohort_10 +3pp p<0.10、cohort_50 +5pp p<0.05）。同步 `docs/qa/2026-05-22-rubric-coverage-baseline.md` 真实基线表 + 60 天 authoring backlog。 |
| [2026-05-23-luban-learning-history-evidence-closed-loop-plan.md](2026-05-23-luban-learning-history-evidence-closed-loop-plan.md) | Implementation Plan | Implemented locally Tasks 1-5 / Metrics Deferred | 针对真实 trace 中"历史对话解析很完整，但作答复盘只显示泛化错因"的断点，补齐历史对话证据闭环：`attempt_detail_read_model` 通过 `turn_id/session_id` 回查既有历史模块 assistant 消息并优先展示完整系统解析，且历史 assistant 内容已通过 `_sanitize_history_text` 去除 `[History Context]`、内部标识、PII；小程序作答复盘将阅卷结论、为什么错、知识点、易错点、口诀、下一步结构化呈现；学情页错题证据卡展示具体历史作答与 attempt detail 入口；首页 prompt / training intent 继续只读后端处方。Operational replay/degraded 指标统一并入 2026-05-22 学习状态推断引擎计划的 release-readiness gate，本批次不阻塞。 |
| [2026-05-21-luban-learning-report-world-class-optimization-plan.md](2026-05-21-luban-learning-report-world-class-optimization-plan.md) | Implementation Plan | Proposed P0-P2 / Round 2 Re-evaluated | 针对系统审查报告形成的顶级学情页优化实施计划：把学情页升级为"学习复盘 + 作答证据 + 云端错题集 + 下一步训练 intent + 对话首页个性化"的学习操作系统。2026-05-21 第一轮专家复评后将 `Learning Evidence Quality Gate` 提升为 Task 0；同日第二轮（Round 2）基于代码实证发现 8 个 BLOCKER 并 inline 修订：(1) 系统答疑解析改用 `learner_memory_events.learning_evidence` with `evidence_source=conversation_synthesis` + `learning_signal_type=...`（不新建 event_type 大类，supabase_writer 白名单零修改）；(2) 修正 `deeptutor/capabilities/deep_question.py` 为单文件路径；(3) 新增 Task 0.5 强制同步 `contracts/index.yaml` + `contracts/learning-report.md`，且 Task 0.5 已补入第一批执行顺序；(4) `?schema_version=2` 双发 + Stage 5 v1 退役流程；(5) `attempt_ref` secret prod fail-closed + kid 字段；(6) home dashboard 通过 `home_personalization` projection 缓存避免 p95 击穿；(7) `LearnerStateService.read_learning_evidence_event` 索引读硬约束；(8) `learner_mistake_book_items` migration 自带 RLS + subject_id 跨学科隔离 + mastered/review 字段。同时补 12 项 high-priority gap（training_intent_id 持久化、prompt click dedupe、PII redact、etag 多端一致、starter pool、Langfuse trace 三键、需 i18n_keys 等）。Stage 3 灰度前需通过 §10 Round 2 Verification Gate 的全部 BLOCKER；Stage 4 100% rollout 前必须通过全部 high-priority gap；文档中的 `conversation_learning_evidence` 只允许作为 forbidden anti-pattern 或 negative assertion 出现。 |
| [2026-05-19-wechat-harness-visible-sections-contract-fix-plan.md](2026-05-19-wechat-harness-visible-sections-contract-fix-plan.md) | Fix Plan | Draft | 接 /qa-only 2026-05-19 报告：把 Next.js `/wechat-harness` 的 visible-chain 从绕过 contract 直接消费 internal projection 改回消费 `learning_brain_read_model.visible_sections`（authority restoration），并对齐 `_qa_enabled()` 加 production gate；single PR 治本 ISSUE-001 + ISSUE-003，ISSUE-002 明确 no-fix（dev harness 设计意图）。 |

### 3. 小程序 / 佑森 / 渲染

| 文件 | 类型 | 状态 | 说明 |
| --- | --- | --- | --- |
| [2026-04-15-yousen-deeptutor-fusion-prd.md](2026-04-15-yousen-deeptutor-fusion-prd.md) | PRD | Draft v1 | 佑森小程序与 DeepTutor 原生融合，包含已完成/未完成状态。 |
| [2026-04-16-wechat-structured-teaching-renderer-prd.md](2026-04-16-wechat-structured-teaching-renderer-prd.md) | PRD | Draft v3 | 微信结构化教学渲染体系升级，P0-P3 计划与 gate。 |
| [2026-05-13-wechat-renderer-markdown-authority-implementation-plan.md](2026-05-13-wechat-renderer-markdown-authority-implementation-plan.md) | Implementation Plan | Implemented locally for P0-P1 / Proposed for P2-P3 | 将 Markdown fallback 从单点修补升级为 renderer contract、single authority gate、wx/WebView parity、golden corpus 与后续 CommonMark/GFM parser 评估。 |
| [2026-05-13-wechat-markdown-parser-evaluation.md](2026-05-13-wechat-markdown-parser-evaluation.md) | Evaluation | Decision accepted locally | 对 `micromark` / `markdown-it` / 当前自研 parser 做包体与 golden corpus 行为评估，结论是本批不替换 parser，保留当前单一 Markdown fallback authority。 |
| [2026-04-16-wechat-structured-renderer-devtools-runbook.md](2026-04-16-wechat-structured-renderer-devtools-runbook.md) | Runbook | 执行清单 | 微信开发者工具验证流程。 |
| [2026-04-16-wechat-structured-renderer-p2-gate-checklist.md](2026-04-16-wechat-structured-renderer-p2-gate-checklist.md) | Gate checklist | 执行清单 | P2 真机 gate 清单。 |
| [2026-04-16-wechat-structured-renderer-p3-gate-checklist.md](2026-04-16-wechat-structured-renderer-p3-gate-checklist.md) | Gate checklist | 执行清单 | P3 真机 gate 清单。 |

### 4. 语义连续性 / Active Object / Router

| 文件 | 类型 | 状态 | 说明 |
| --- | --- | --- | --- |
| [2026-04-18-llm-native-active-object-semantic-router-prd.md](2026-04-18-llm-native-active-object-semantic-router-prd.md) | PRD | Implemented v1 | Active Object、当前轮语义决策、多对象切换与旧概念清退。 |

### 5. 钱包 / 会员 / 身份

| 文件 | 类型 | 状态 | 说明 |
| --- | --- | --- | --- |
| [2026-04-19-supabase-wallet-single-authority-prd.md](2026-04-19-supabase-wallet-single-authority-prd.md) | PRD | Draft v3 | Supabase 钱包唯一权威体系。 |
| [2026-04-19-supabase-wallet-single-authority-implementation-plan.md](2026-04-19-supabase-wallet-single-authority-implementation-plan.md) | Implementation Plan | Draft v1 | WP1-WP4 钱包实施计划。 |
| [2026-04-19-supabase-wallet-rls-appendix.md](2026-04-19-supabase-wallet-rls-appendix.md) | Appendix | Draft | 钱包 RLS / RPC / migration 审查补充。 |

### 5.5 BI / 会员经营后台

| 文件 | 类型 | 状态 | 说明 |
| --- | --- | --- | --- |
| [2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md](2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md) | Implementation Plan | Batch 0-7 完成 v1 (2026-05-23) · 灰度待启动 | 将 `/bi` 从经营看板升级为“会员经营后台 + BI 决策系统”：一级主区收敛为经营总览、会员运营、商品账务、反馈中心、系统运维。已实装：BiAppShell / BiTopBar / BiSideNav / BiDataTable / BiSidePanel / BiStatusPill / BiMoneyCell 7 个核心组件；6 个 feature flag 集中在 `web/lib/bi-feature-flags.ts`；client metric registry 镜像 `bi_metrics.py`；overview 接真实 `/api/v1/bi/overview` + `active-trend` + `anomalies`（dev 无 admin token 自动 fallback 到 mock + 红色 banner）；会员 CRM 7 默认列 + 11 列可配置 + 5 常用筛选 + 高级筛选 + 私有保存视图（`useSyncExternalStore` + localStorage）+ 学员 360 抽屉 + 对话回顾必须选原因 + audit；商品账务异常顶部行动条 + 订单/钱包/套餐 tabs + 自然月/渠道/发票筛选；反馈中心 AI/内测/备注三源 + open/triaged/ignored + owner 分组 + 处理结果 audit；系统运维 6 tile + 操作审计五维筛选（操作人 IME / 目标 IME / 分类 / 敏感级别 / 时间）+ 导出任务异步/脱敏/限频。pytest 58 个 100% 通过；Playwright `bi_v2_release_gate.mjs` 18 张截图（6 路径 × 3 视口）+ CRM 交互 smoke + 关 flag rollback smoke 全部通过。剩余风险与灰度顺序见 `docs/zh/bi/bi-backoffice-v2-rollout-runbook.md`。 |

### 6. Observability / Benchmark / Release Gate

| 文件 | 类型 | 状态 | 说明 |
| --- | --- | --- | --- |
| [2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md](2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md) | PRD | Proposed | 顶尖观测体系主 PRD，覆盖 OM/ARR/AAE/OA。 |
| [2026-04-19-deeptutor-observability-original-intent-mapping-audit.md](2026-04-19-deeptutor-observability-original-intent-mapping-audit.md) | Audit appendix | 未标注 | 对观测体系原设计意图的映射审计。 |
| [2026-04-19-deeptutor-observability-m0-m1-implementation-plan.md](2026-04-19-deeptutor-observability-m0-m1-implementation-plan.md) | Implementation Plan | 未标注 | Observability M0/M1 第一批实施计划。 |
| [2026-04-19-deeptutor-observability-surface-ack-implementation-plan.md](2026-04-19-deeptutor-observability-surface-ack-implementation-plan.md) | Implementation Plan | 未标注 | Phase 2 Surface ACK 最小可交付实施计划。 |
| [2026-04-19-deeptutor-observability-arr-lite-implementation-plan.md](2026-04-19-deeptutor-observability-arr-lite-implementation-plan.md) | Implementation Plan | 未标注 | Phase 3 ARR Lite 实施计划。 |
| [2026-04-23-deeptutor-benchmark-single-spine-prd.md](2026-04-23-deeptutor-benchmark-single-spine-prd.md) | PRD | Proposed | Benchmark 作为 daily/gate/incident 的单一质量主脊梁。 |
| [2026-05-18-deeptutor-launch-readiness-dashboard-implementation-plan.md](2026-05-18-deeptutor-launch-readiness-dashboard-implementation-plan.md) | Implementation Plan | Implemented locally P0-P2 | 借鉴 gstack review readiness dashboard，把 contract guard、benchmark、OA/ARR/AAE、Playwright、微信 DevTools、Langfuse 汇总成单一“能不能发”读模型。 |

### 7. 部署 / 规模化

| 文件 | 类型 | 状态 | 说明 |
| --- | --- | --- | --- |
| [2026-04-19-deeptutor-50000-member-deployment-prd.md](2026-04-19-deeptutor-50000-member-deployment-prd.md) | PRD | 未标注 | 5 万会员规模下的部署、容量、稳健性设计。 |
| [2026-05-17-deeptutor-active-turn-capacity-implementation-plan.md](2026-05-17-deeptutor-active-turn-capacity-implementation-plan.md) | Implementation Plan | Proposed | 将现网从单容器单进程推进到 `50-120 active turn` Phase 1 能力的执行计划，覆盖 capacity gate、terminal timeout、Redis admission、event stream、worker split、Postgres store 与阿里云验收。 |

### 8. Web Search / 联网能力

| 文件 | 类型 | 状态 | 说明 |
| --- | --- | --- | --- |
| [2026-05-03-deeptutor-web-search-stack-prd.md](2026-05-03-deeptutor-web-search-stack-prd.md) | PRD | Aliyun validated v1 | 自部署 SearXNG + DeepTutor `web_search` 显式启用、fail-closed provider/runtime authority、UI/turn 验收。 |
| [2026-05-03-deeptutor-web-search-stack-implementation-plan.md](2026-05-03-deeptutor-web-search-stack-implementation-plan.md) | Implementation Plan | Aliyun validated v1 | `/opt/deeptutor-stack` 或既有 `/root/deeptutor` Compose、SearXNG JSON、DeepTutor runtime enablement、acceptance script、备份升级与故障排查。 |

### 9. 鲁班智考 / 因材施教

| 文件 | 类型 | 状态 | 说明 |
| --- | --- | --- | --- |
| [2026-04-20-luban-adaptive-teaching-intelligence-prd.md](2026-04-20-luban-adaptive-teaching-intelligence-prd.md) | PRD | 未标注 | 因材施教智能体、显性个性化导师、Teaching Policy。 |
| [2026-04-20-teaching-methods-matrix-prd.md](2026-04-20-teaching-methods-matrix-prd.md) | PRD | Draft v1 | Teaching Methods Matrix，定义“施教层”的方法选择。 |
| [2026-05-02-luban-assessment-blueprint-prd.md](2026-05-02-luban-assessment-blueprint-prd.md) | PRD | Implemented locally | Assessment Blueprint，定义 Supabase 题库抽样、心理/学习习惯/教学偏好 probes、计分分层与 release gate；P0-P3 代码与定向验证已完成，尚未 push / 部署到线上。 |
| [2026-05-13-luban-case-grading-error-map-prd.md](2026-05-13-luban-case-grading-error-map-prd.md) | PRD | Proposed v1.7 | 建筑实务题目阅卷、Rubric 校准、错因图谱、个性化变式训练；新增 live-audited `construction-mcq-grading` 与 `construction-case-grading` TutorBot Skill，确认线上 `questions_bank.grading_rubric` 当前为空，因此 P0 以 `projected_rubric / open_skill` 为主，并复用 `kb_chunks.metadata / standard_articles / syllabus_tree` 证据链。 |
| [2026-05-13-luban-case-grading-error-map-implementation-plan.md](2026-05-13-luban-case-grading-error-map-implementation-plan.md) | Implementation Plan | Draft v1.7 | 将 live-audited 题目阅卷 PRD 拆成 P0/P1 可执行任务：TutorBot `mcq_grading` / `case_grading` Skill surface、readiness audit、源数据与 Supabase 对账、LLM structured matcher、`CaseGradingSkillKernel`、内部质量门控、learner writeback、题库优先推荐、`deep_question` 接入和验证 gate。 |
| [2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md](2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md) | Execution Plan | Active P0 | 对上一份大实施计划做减法收口：不新增 Rubric 中台、不新增路由、不新增 learner state；用现有 `deep_question`、`construction_grading_result`、阅卷 Skill、learner memory event 和题库优先推荐完成主观题阅卷、错因沉淀与个性化训练闭环。 |
| [2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md](2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md) | Execution Plan | Proposed v3 | 将“轻量出题”和“答后深度解释”拆成两段：`deep_question` 仍是题目 lifecycle authority，出题阶段只生成题面与隐藏评分要点，跳过 heavy ideation/长解析；用户作答后再由 `construction_grading`、RAG grounding 与 `SubmissionGraderAgent` 输出知识点、采分点、易错点、记忆口诀、为什么错和下一步训练，并写回 learner memory；v3 在 v2 真实场景矩阵、P0/P1/P2 切分和不确定性验证基础上，补充顶尖产品体验复审、移动端丝滑标准、留存/喜爱指标和 P0 真入口体验验收脚本。 |
| [2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md](2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md) | Execution Plan | Proposed v2.1 (2026-05-24) | 在轻量出题与深度阅卷计划之上补 skill-native 收口：把 `deeptutor/tutorbot/skills` 视为 DeepTutor runtime skill library，补齐 `construction-question-supply`、`construction-question-review`、`construction-learning-evidence-story`、`construction-study-assistant`、`construction-learning-support` 场景 skill，用共享 `question_lifecycle_skill_context` 让 `deep_question`、TutorBot、`question_followup` 和 `construction_grading` 共用同一场景 skill matrix；同时把开发者回归 skill 从 TutorBot 专项升级为 question lifecycle authority review，覆盖出题、答题、解析、answer reveal、active object 与 learning evidence。v2 修订要点：新增 Task 2.5 先把 `teaching_modes.get_construction_exam_skill_instruction` 这条绕开 `SkillsLoader` 的第二条 skill 加载路径收成 thin shim 再 wiring（杜绝第三条 loader）；§5.1 把 scene 判定权收到 `ChatOrchestrator` 唯一一处；§5.2 给旧 `ConstructionExamScene` Literal 设 alias map + 删除条件；§6.7 用 5 阶段灰度 + kill-switch drill 替换 v1 的“config switch”一句话；§6.5 增加 mixed-turn / resume / sticky-reveal / adversarial-prompt / dialect-fallback 5 类失败模式；§11 加 v2-C1..C6 单一权威 grep / 灰度证据 / alias 删除条件六条 release gate。完整 diff 见计划 §0 Revision Log R1-R12。 |
| [2026-05-24-deeptutor-hermes-edu-skills-booster-plan.md](2026-05-24-deeptutor-hermes-edu-skills-booster-plan.md) | Execution Plan | Implemented locally P0 + P1 guardrails + P2 schema/doctor (2026-05-24) | 将 `zhongweiv/hermes-edu-skills` 从外部教育 Skill Pack 转成 DeepTutor booster：只读 upstream inventory、吸收评分、DeepTutor skill registry、strict validator、5 个 construction 场景 skill pack、`question_lifecycle_skills` builder、trace metadata propagation、Hermes+Weixin sandbox、teacher/internal ops booster、未来 `luban-construction-skills` 导出包。P1 已补 upstream fetch/check weekly sentinel 与 sandbox PII scanner；P2 已补 `export_eligible` 显式 schema 和 inventory-to-catalog doctor gap report。硬边界：不全量安装 188 个 Skill、不用外部 router 决定 production scene、不让 Skill markdown 计算分数/学情/推荐、不新增聊天入口或 learner memory。 |
| [2026-05-15-luban-website-invite-test-landing-execution-plan.md](2026-05-15-luban-website-invite-test-landing-execution-plan.md) | Execution Plan | Proposed v1 | 将 `/intro` 官网介绍页、`/invite-test` 内测说明页与 `/invite-test/apply` 独立申请页收口成一条完整转化链：痛点共鸣、产品亮点、真实小程序展示、申请内测、邮箱等信息收集、申请数据 authority、漏斗埋点和内测任务闭环。 |
| [2026-05-13-luban-grading-chain-regression-matrix.md](2026-05-13-luban-grading-chain-regression-matrix.md) | Regression Matrix | Active | 阅卷链路事故回归矩阵：覆盖生成 5 题不泄露答案、题型 alias 交互、redacted context 恢复服务端标准答案、q1/q2/q5 批量判分、结构化 grading result 优先、答完后继续出题不重批、Skill 使用边界和发布前最小命令。 |
| [2026-05-18-luban-learning-brain-gbrain-absorption-prd.md](2026-05-18-luban-learning-brain-gbrain-absorption-prd.md) | PRD | Implemented locally all phases + Web live verified | 在案例题阅卷和 learner state 之间补学习事实编译层，把题目、知识点、采分点、错因、作答、下一题训练沉淀为带证据和时间线的 compiled learning truth；`/wechat-harness` 已完成 live visible-chain 验证。 |
| [2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md](2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md) | Implementation Plan | Implemented locally all phases + Web live verified | 基于现有 `construction_grading`、`LearnerStateService`、outbox、`deep_question` 链路执行学习事实编译，不创建平行 memory、RAG 或聊天入口；已完成本地后端闭环、graph query、Teaching Policy 消费和 Web live visible-chain。 |
| [2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md](2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md) | Implementation Plan | Implemented + controlled live gate verified / Phase D flag off by default | 把 GBrain 的 query understanding、hybrid/RRF、compiled truth boost、provenance、typed graph、dream cycle 和 maintenance skills 映射成 DeepTutor 学习事实召回计划，明确 authority 顺序：exact 题库事实 > 标准/教材证据 > compiled learning truth > 普通语义 chunk；已完成 query plan trace、compiled truth source group、provenance trace、graph expansion、runtime propagation 与 weak-point-only enablement 验证。 |
| [2026-05-18-deeptutor-learning-fact-retrieval-gap-closure-plan.md](2026-05-18-deeptutor-learning-fact-retrieval-gap-closure-plan.md) | Gap Closure Plan | Completed / controlled live gate verified | 学习事实召回剩余差距收口计划，覆盖 graph-aware compiled truth docs、TutorBot/RAG/fast-path propagation、maintenance dry-run、contract guard、live direct RAG / public WS / Langfuse evidence；生产开关已恢复默认关闭。 |
| [2026-04-25-luban-feedback-top10-issue-register.md](2026-04-25-luban-feedback-top10-issue-register.md) | Issue register | Draft | 从 DOCX/PPTX 原始使用反馈合并出的 Top10 问题域，用作后续分组修复的用户反馈 authority。 |
| [2026-04-24-luban-feedback-top10-root-cause-fix-plan.md](2026-04-24-luban-feedback-top10-root-cause-fix-plan.md) | Root-cause fix plan | Draft | 运营反馈与线上证据汇总出的 Top10 问题；Batch 1-4、2026-04-25 Batch A-H 已实施，继续收口练题结构化 config、SMS 真实送达、干净 DevTools/真机慢请求取消和移动端交互矩阵。 |

### 10. 建筑实务 AI 互动课堂 / OpenMAIC 对标

| 文件 | 类型 | 状态 | 说明 |
| --- | --- | --- | --- |
| [../openmaic/README.md](../openmaic/README.md) | Index | Canonical | OpenMAIC 文档层级、authority、supporting/historical 边界。 |
| [../openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md](../openmaic/建筑实务AI互动课堂_架构与实施收口_v1.2.md) | Canonical spec | Canonical v1.2 | Lesson IR、transport、微信小程序主表面、状态机、P0/P1/P2、release gate 的唯一收口。 |
| [../openmaic/建筑实务AI互动课堂_Implementation_Plan_v1.2.md](../openmaic/建筑实务AI互动课堂_Implementation_Plan_v1.2.md) | Implementation Plan | Live v1.2 | 可派工实施计划，含微信小程序 Player、质量工厂、一键生成 gate、P0.5 体验切片。 |
| [../openmaic/ADR-001-lesson-ir-authority.md](../openmaic/ADR-001-lesson-ir-authority.md) | ADR | Accepted | `LessonIRService`、唯一 writer、revision / CAS、projection 规则。 |
| [../openmaic/ADR-002-classroom-turn-transport.md](../openmaic/ADR-002-classroom-turn-transport.md) | ADR | Accepted | 课堂问答统一 `/api/v1/ws`，thin adapter 和 grounding context。 |
| [../openmaic/ADR-003-quality-evaluation-release-gate.md](../openmaic/ADR-003-quality-evaluation-release-gate.md) | ADR | Accepted | `LessonQualityEvaluator`、质量分、review gate、发布规则。 |
| [../openmaic/ADR-004-source-ingestion-provenance.md](../openmaic/ADR-004-source-ingestion-provenance.md) | ADR | Accepted | `SourceManifest`、source chunk、citation、copyright gate。 |
| [../openmaic/ADR-005-mini-program-surface-renderer-contract.md](../openmaic/ADR-005-mini-program-surface-renderer-contract.md) | ADR | Accepted | 微信小程序主表面、Scene Runtime Core、wx renderer、job progress、socket、上传、宿主包同步。 |
| [../openmaic/ADR-006-supabase-knowledge-base-reuse.md](../openmaic/ADR-006-supabase-knowledge-base-reuse.md) | ADR | Accepted | 现有 Supabase RAG 知识库复用，`kb_chunks / questions_bank` evidence 到 `source_manifest` 的映射和知识覆盖 gate。 |
| [../openmaic/package-deeptutor-sync-manifest.yaml](../openmaic/package-deeptutor-sync-manifest.yaml) | Sync contract | Draft | `wx_miniprogram -> yousenwebview/packageDeeptutor` selective sync 边界。 |
| [../openmaic/banned-v1.1-patterns.md](../openmaic/banned-v1.1-patterns.md) | Checklist | Active | v1.1 冲突模式禁用清单，可作为 PR review gate。 |

## 按文档类型索引

### PRD

- [2026-04-15-unified-ws-full-tutorbot-prd.md](2026-04-15-unified-ws-full-tutorbot-prd.md)
- [2026-04-15-learner-state-memory-guided-learning-prd.md](2026-04-15-learner-state-memory-guided-learning-prd.md)
- [2026-04-15-bot-learner-overlay-prd.md](2026-04-15-bot-learner-overlay-prd.md)
- [2026-04-15-yousen-deeptutor-fusion-prd.md](2026-04-15-yousen-deeptutor-fusion-prd.md)
- [2026-04-16-tutorbot-context-orchestration-prd.md](2026-04-16-tutorbot-context-orchestration-prd.md)
- [2026-04-16-wechat-structured-teaching-renderer-prd.md](2026-04-16-wechat-structured-teaching-renderer-prd.md)
- [2026-04-18-llm-native-active-object-semantic-router-prd.md](2026-04-18-llm-native-active-object-semantic-router-prd.md)
- [2026-04-19-supabase-wallet-single-authority-prd.md](2026-04-19-supabase-wallet-single-authority-prd.md)
- [2026-04-19-tutorbot-mode-policy-unified-authority-prd.md](2026-04-19-tutorbot-mode-policy-unified-authority-prd.md)
- [2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md](2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md)
- [2026-04-19-deeptutor-50000-member-deployment-prd.md](2026-04-19-deeptutor-50000-member-deployment-prd.md)
- [2026-04-20-luban-adaptive-teaching-intelligence-prd.md](2026-04-20-luban-adaptive-teaching-intelligence-prd.md)
- [2026-04-20-teaching-methods-matrix-prd.md](2026-04-20-teaching-methods-matrix-prd.md)
- [2026-04-23-deeptutor-benchmark-single-spine-prd.md](2026-04-23-deeptutor-benchmark-single-spine-prd.md)
- [2026-04-24-luban-feedback-top10-root-cause-fix-plan.md](2026-04-24-luban-feedback-top10-root-cause-fix-plan.md)
- [2026-05-02-luban-assessment-blueprint-prd.md](2026-05-02-luban-assessment-blueprint-prd.md)
- [2026-05-13-luban-case-grading-error-map-prd.md](2026-05-13-luban-case-grading-error-map-prd.md)
- [2026-05-03-deeptutor-web-search-stack-prd.md](2026-05-03-deeptutor-web-search-stack-prd.md)
- [2026-05-18-luban-learning-brain-gbrain-absorption-prd.md](2026-05-18-luban-learning-brain-gbrain-absorption-prd.md)

### Service Design / Schema Appendix

- [2026-04-15-learner-state-service-design.md](2026-04-15-learner-state-service-design.md)
- [2026-04-15-bot-learner-overlay-service-design.md](2026-04-15-bot-learner-overlay-service-design.md)
- [2026-04-15-learner-state-supabase-schema-appendix.md](2026-04-15-learner-state-supabase-schema-appendix.md)

### Implementation Plan

- [2026-04-19-supabase-wallet-single-authority-implementation-plan.md](2026-04-19-supabase-wallet-single-authority-implementation-plan.md)
- [2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md](2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md)
- [2026-04-19-deeptutor-observability-m0-m1-implementation-plan.md](2026-04-19-deeptutor-observability-m0-m1-implementation-plan.md)
- [2026-04-19-deeptutor-observability-surface-ack-implementation-plan.md](2026-04-19-deeptutor-observability-surface-ack-implementation-plan.md)
- [2026-04-19-deeptutor-observability-arr-lite-implementation-plan.md](2026-04-19-deeptutor-observability-arr-lite-implementation-plan.md)
- [2026-05-03-deeptutor-web-search-stack-implementation-plan.md](2026-05-03-deeptutor-web-search-stack-implementation-plan.md)
- [2026-05-18-deeptutor-launch-readiness-dashboard-implementation-plan.md](2026-05-18-deeptutor-launch-readiness-dashboard-implementation-plan.md)
- [2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md](2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md)
- [2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md](2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md)
- [2026-05-18-deeptutor-learning-fact-retrieval-gap-closure-plan.md](2026-05-18-deeptutor-learning-fact-retrieval-gap-closure-plan.md)
- [2026-05-13-luban-case-grading-error-map-implementation-plan.md](2026-05-13-luban-case-grading-error-map-implementation-plan.md)
- [2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md](2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md)
- [2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md](2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md)
- [2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md](2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md)
- [2026-05-24-deeptutor-hermes-edu-skills-booster-plan.md](2026-05-24-deeptutor-hermes-edu-skills-booster-plan.md)
- [2026-05-13-wechat-renderer-markdown-authority-implementation-plan.md](2026-05-13-wechat-renderer-markdown-authority-implementation-plan.md)
- [2026-05-17-deeptutor-active-turn-capacity-implementation-plan.md](2026-05-17-deeptutor-active-turn-capacity-implementation-plan.md)
- [../openmaic/建筑实务AI互动课堂_Implementation_Plan_v1.2.md](../openmaic/建筑实务AI互动课堂_Implementation_Plan_v1.2.md)

### Evaluation

- [2026-05-13-wechat-markdown-parser-evaluation.md](2026-05-13-wechat-markdown-parser-evaluation.md)

### Audit / Runbook / Checklist

- [2026-04-19-deeptutor-observability-original-intent-mapping-audit.md](2026-04-19-deeptutor-observability-original-intent-mapping-audit.md)
- [2026-04-24-learner-state-overlay-completion-evidence.md](2026-04-24-learner-state-overlay-completion-evidence.md)
- [2026-04-25-luban-feedback-top10-issue-register.md](2026-04-25-luban-feedback-top10-issue-register.md)
- [2026-04-16-wechat-structured-renderer-devtools-runbook.md](2026-04-16-wechat-structured-renderer-devtools-runbook.md)
- [2026-04-16-wechat-structured-renderer-p2-gate-checklist.md](2026-04-16-wechat-structured-renderer-p2-gate-checklist.md)
- [2026-04-16-wechat-structured-renderer-p3-gate-checklist.md](2026-04-16-wechat-structured-renderer-p3-gate-checklist.md)
- [2026-05-03-upstream-absorption-status.md](2026-05-03-upstream-absorption-status.md)
- [2026-05-03-upstream-product-surface-review-intake.md](2026-05-03-upstream-product-surface-review-intake.md)

## 计划修改工作流

1. 先读本索引，确认是否已有主线。
2. 读对应主线的 PRD，再读 service design / implementation plan / checklist。
3. 如果要新增计划，先判断它是新主线、子计划、附录，还是旧计划的替代版。
4. 如果是替代版，必须在新旧文档里标明 `Supersedes` / `Superseded by`，并更新本索引。
5. 如果计划已经实施，必须补充实际代码入口、测试入口、验证证据和剩余风险。
6. 完成任何计划文件变更后，至少执行一次链接/路径检查，例如：

```bash
rg -n "deeptutor/d[o]c/plan|`/d[o]c/plan|d[o]c/plan/[0-9]|d[o]cs/d[o]cs/plan" docs/plan contracts/index.yaml AGENTS.md
```
