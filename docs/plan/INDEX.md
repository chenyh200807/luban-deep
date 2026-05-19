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
| 学习事实编译 / Evidence-first Memory | [2026-05-18-luban-learning-brain-gbrain-absorption-prd.md](2026-05-18-luban-learning-brain-gbrain-absorption-prd.md) / [2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md](2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md) / [2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md](2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md) / [2026-05-18-deeptutor-learning-fact-retrieval-gap-closure-plan.md](2026-05-18-deeptutor-learning-fact-retrieval-gap-closure-plan.md) | 吸收 GBrain 的 compiled truth + timeline、typed graph、evidence-first memory、nightly synthesis，并把召回升级为带 query plan、source-aware ranking、provenance 与 compiled truth source group 的学习事实召回；学习事实编译主 PRD 已本地实现并通过 `/wechat-harness` live visible-chain 验证，学习事实召回子计划已完成本地实现与受控 live gate，Phase D final-source 仍保持默认关闭、按开关渐进启用。 |
| Bot-Learner Overlay | [2026-04-15-bot-learner-overlay-prd.md](2026-04-15-bot-learner-overlay-prd.md) | 多 Bot 对同一学员的局部状态、promotion、仲裁 |
| 佑森小程序融合 | [2026-04-15-yousen-deeptutor-fusion-prd.md](2026-04-15-yousen-deeptutor-fusion-prd.md) | Yousen 原生入口、workspace shell、包内路由与页面体验 |
| 微信结构化渲染 | [2026-04-16-wechat-structured-teaching-renderer-prd.md](2026-04-16-wechat-structured-teaching-renderer-prd.md) / [2026-05-13-wechat-renderer-markdown-authority-implementation-plan.md](2026-05-13-wechat-renderer-markdown-authority-implementation-plan.md) | 小程序题卡、表格、公式、图表、教学 block 渲染、Markdown fallback 单一 authority 与 golden corpus |
| 上下文与语义连续性 | [2026-04-16-tutorbot-context-orchestration-prd.md](2026-04-16-tutorbot-context-orchestration-prd.md) | 每轮上下文包、预算、选择性加载、route 稳定性 |
| Active Object 与语义路由 | [2026-04-18-llm-native-active-object-semantic-router-prd.md](2026-04-18-llm-native-active-object-semantic-router-prd.md) | follow-up、当前题、当前对象、多对象切换、语义 route |
| 钱包与会员 authority | [2026-04-19-supabase-wallet-single-authority-prd.md](2026-04-19-supabase-wallet-single-authority-prd.md) | Supabase wallet、积分、会员、支付状态、身份归一化 |
| 生产部署 | [2026-04-19-deeptutor-50000-member-deployment-prd.md](2026-04-19-deeptutor-50000-member-deployment-prd.md) / [2026-05-17-deeptutor-active-turn-capacity-implementation-plan.md](2026-05-17-deeptutor-active-turn-capacity-implementation-plan.md) | 5 万会员部署、50-120 active turn Phase 1 扩容、上线稳健性 |
| 联网搜索能力 | [2026-05-03-deeptutor-web-search-stack-prd.md](2026-05-03-deeptutor-web-search-stack-prd.md) / [2026-05-03-deeptutor-web-search-stack-implementation-plan.md](2026-05-03-deeptutor-web-search-stack-implementation-plan.md) | SearXNG、`web_search` fail-closed enablement、搜索 provider/runtime 验收 |
| Observability 与 release gate | [2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md](2026-04-19-deeptutor-top-tier-observability-arr-aae-oa-om-prd.md) / [2026-05-18-deeptutor-launch-readiness-dashboard-implementation-plan.md](2026-05-18-deeptutor-launch-readiness-dashboard-implementation-plan.md) | OM/ARR/AAE/OA、trace、surface ACK、release gate、上线 readiness 面板 |
| 鲁班智考个性化教学 | [2026-04-20-luban-adaptive-teaching-intelligence-prd.md](2026-04-20-luban-adaptive-teaching-intelligence-prd.md) / [2026-05-02-luban-assessment-blueprint-prd.md](2026-05-02-luban-assessment-blueprint-prd.md) / [2026-05-13-luban-case-grading-error-map-prd.md](2026-05-13-luban-case-grading-error-map-prd.md) / [2026-05-13-luban-case-grading-error-map-implementation-plan.md](2026-05-13-luban-case-grading-error-map-implementation-plan.md) / [2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md](2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md) | 因材施教、Learner Core、Teaching Policy、显性诊断、摸底测评蓝图、案例题 AI 阅卷与错因变式训练；P0 执行优先读 Skill-first 薄外壳计划 |
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
