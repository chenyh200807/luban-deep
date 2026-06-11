# 鲁班系统技术介绍：给 AI 升级工作的架构总览

- 日期：2026-06-11
- 状态：Active reference
- 范围：鲁班智考 / DeepTutor 当前产品化主线、技术架构、核心链路、authority 边界、升级方向
- 目标读者：接手后续升级、排障、规划、实现、QA、发布的 AI agent / 工程师
- 本文定位：系统技术总览和升级导航，不替代 contract、PRD、release gate 或具体实施计划

## 0. 给 AI 的读取方式

如果你是后续接手鲁班系统的 AI，不要先按文件名猜系统结构。请按这个顺序读：

1. 先读本文，建立全局地图。
2. 再读根 contract：
   - [CONTRACT.md](../../CONTRACT.md)
   - [contracts/index.yaml](../../contracts/index.yaml)
3. 如果涉及鲁班评分 / Learning Brain / GBrain，继续读：
   - [2026-06-04-luban-grading-engine-master-control-plan.md](2026-06-04-luban-grading-engine-master-control-plan.md)
   - [2026-06-09-learner-memory-lifecycle-execution-plan.md](2026-06-09-learner-memory-lifecycle-execution-plan.md)
4. 如果涉及微信端真实体验，必须区分：
   - `wx_miniprogram`：开发/影子验证面
   - `yousenwebview`：微信开发者工具 project root
   - `yousenwebview/packageDeeptutor`：目标分包，不是 project root
5. 如果涉及 Web / BI / 前端 / 浏览器 / 截图，先执行 AGENTS.md 中的内存安全 preflight，不要让 Codex Desktop 或其他 AI agent 托管长时间 `next dev`。

本文的核心用途不是“背概念”，而是防止后续升级时犯四类错误：

1. 把 wrapper 当业务 authority。
2. 把 RAG / registry / 前端 projection 当 canonical truth。
3. 把本地 shadow / harness pass 写成真实微信或 production pass。
4. 在没有 contract / gate 的情况下新增第二套聊天入口、第二套 learner memory、第二套评分真相。

## 1. 一句话总览

鲁班智考是 DeepTutor 当前最重要的产品化落点：一个面向中国建筑实务考试的移动优先 AI 学习教练。

它不是普通聊天机器人，也不是只会出题的题库系统。它的主链路是：

```text
测 / 练 / 答
  -> 评分与诊断
  -> 结构化学习证据
  -> Learning Brain 长期画像与弱点 claim
  -> 个性化下一步训练
  -> 复测验证变化
```

当前最重要的业务闭环是：

```text
assess -> grade -> remember -> train -> retest
```

对应到鲁班语境：

```text
摸底测评 / 练题 / 案例作答
  -> 客观题判错 + 案例题点级评分
  -> learner_memory_events.learning_evidence
  -> learning_synthesis / LearnerClaim / PersonalizationContextPack
  -> NextBestAction / training_intent / 今日任务
  -> 复测结果进入下一轮证据
```

最高层职责切分：

| 组件 | 核心问题 | 不能做什么 |
| --- | --- | --- |
| 鲁班评分引擎 | 这次作答哪里对、哪里错、为什么错 | 不写长期学习真相，不替代 Learning Brain |
| Learning Brain / GBrain-inspired learner state | 这个学生长期是什么状态，下一步怎么教 | 不重新评分，不伪造题库答案 |
| RAG / 编译知识 | 教材、规范、真题、章节、证据在哪里 | 不判分，不覆盖标准答案 |
| TutorBot / deep_question | 组织一次对话、练题、讲评、批改体验 | 不新增第二套聊天入口或题目 authority |
| BI / Observability | 经营、行为、质量、成本、发布是否可见 | 不成为 learner-state 或 wallet truth |

## 2. 当前系统层级图

```text
用户表面
  - 微信小程序 / yousenwebview/packageDeeptutor
  - Web workspace / BI / member / intro / invite-test / wechat-harness
  - CLI / Python SDK / scripts / automation

入口适配层
  - /api/v1/ws                 统一聊天与 turn 流式入口
  - mobile HTTP adapters       登录、测评、学习报告、钱包、错题、start-turn bootstrap
  - REST routers               BI、observability、knowledge、photo-answer、settings 等
  - WeChat DevTools / harness  真入口和影子入口验证

控制面
  - TurnRuntimeManager + SQLiteSessionStore
  - ChatOrchestrator + QuestionLifecycleDecision
  - CapabilityRegistry + request_contracts.py
  - RAGService
  - LearnerStateService
  - Config Runtime

能力内核
  - deep_question
  - tutorbot runtime
  - construction_grading
  - assessment services
  - compiled_knowledge
  - learner_state read/write models
  - observability / release gate / BI services
  - photo_answer OCR input layer

数据与证据
  - Supabase / Postgres: questions_bank、assessment_sessions、wallet、member、RAG KB v5 等
  - SQLite/local files: session store、learner-state fallback、observability artifacts、behavior DB
  - learner_memory_events: 学习证据 append-only ledger
  - artifacts/luban_grading_artifacts: release / shadow / benchmark / gate 证据
  - Langfuse / control-plane JSON: trace、cost、quality、release observability
```

## 3. 技术栈

### 3.1 后端

| 类型 | 技术 |
| --- | --- |
| 语言 | Python 3.11+ |
| API | FastAPI, Uvicorn, WebSocket |
| 数据模型 | Pydantic v2, dataclasses |
| CLI | Typer, Rich, prompt_toolkit |
| HTTP / async | httpx, aiohttp, websockets |
| 配置 | python-dotenv, pydantic-settings, custom config runtime |
| 数据库 | Supabase / Postgres, SQLite local stores, JSONL fallback |
| LLM / Embedding | OpenAI-compatible providers, DeepSeek, Qwen/DashScope, Anthropic, Gemini, Ollama, LM Studio, vLLM 等 |
| 可观测性 | Langfuse, control-plane artifacts, release gate scripts |
| 测试 | pytest, contract guards, integration scripts |

### 3.2 前端 / Web

| 类型 | 技术 |
| --- | --- |
| Web 框架 | Next.js 16, React 19 |
| 样式 | Tailwind CSS |
| 可视化 | ECharts, Chart.js, Cytoscape, Mermaid |
| 交互 | framer-motion, lucide-react |
| Markdown | react-markdown, remark-gfm, rehype-katex |
| 自动化 | Playwright |

注意：因为历史内存事故，不要由 AI agent 长时间托管 `next dev`。Web/BI work 必须先跑 AGENTS.md 的 preflight，并由人工 Terminal/tmux 托管 dev server。

### 3.3 微信端

| 路径 | 角色 |
| --- | --- |
| `wx_miniprogram/` | 独立小程序开发与测试面 |
| `yousenwebview/` | 微信开发者工具 project root |
| `yousenwebview/packageDeeptutor/` | 鲁班目标分包 |
| `web/app/wechat-harness` | Web shadow QA 入口，不能替代真实微信入口 |

涉及微信体验时，证据必须拆开写：

```text
devtools_project_root = yousenwebview
target_subpackage = packageDeeptutor
target_page = 具体页面
entry_flow = 具体动作链路
auth_state = logged_in / qa_token / auth_blocked / unknown
auth_mode = real_wechat / local_dev_wechat / manual_token / none
```

### 3.4 主要命令与测试入口

常见后端测试：

```bash
python -m pytest tests/api/test_unified_ws_turn_runtime.py -q
python -m pytest tests/services/learner_state -q
python -m pytest tests/services/construction_grading -q
python -m pytest tests/services/rag -q
python -m pytest tests/api/test_mobile_router.py -q
```

常见 contract / guard：

```bash
python scripts/check_contract_guard.py
python scripts/ci/check_websocket_route_allowlist.py
python scripts/run_release_gate.py
```

常见前端 / 小程序 shadow：

```bash
cd web && npm run test:wechat-harness
node wx_miniprogram/tests/test_ws_stream.js
node wx_miniprogram/tests/test_report_view_model.js
```

真实微信入口需要微信开发者工具 CLI：

```bash
WX_DEVTOOLS_CLI=/Applications/wechatwebdevtools.app/Contents/MacOS/cli
$WX_DEVTOOLS_CLI islogin
$WX_DEVTOOLS_CLI open --project /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview --lang zh
$WX_DEVTOOLS_CLI auto --project /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview --auto-port 9420
```

`islogin` 和 `open --project` 只算环境预检，不算真实业务场景通过。

## 4. 仓库关键目录

| 路径 | 说明 |
| --- | --- |
| `deeptutor/api/routers/` | FastAPI HTTP/WS routers，adapter 层，不应承担业务 truth |
| `deeptutor/contracts/` | 机器可读 contract schema，如 unified turn、bot defaults |
| `contracts/` | 人类可读 contract 文档和 machine-readable index |
| `deeptutor/runtime/` | Capability registry、orchestrator、runtime mode |
| `deeptutor/services/session/` | turn runtime、session store、context builder、context routing |
| `deeptutor/capabilities/` | chat、tutorbot、deep_question、deep_solve、research、visualize 等 capability |
| `deeptutor/services/construction_grading/` | 鲁班评分、rubric、runtime adjudication、artifact governance、compiled context |
| `deeptutor/services/learner_state/` | LearnerStateService、learning_synthesis、learning report、mistake book、PCP、NBA |
| `deeptutor/services/rag/` | RAGService 与 retrieval pipelines |
| `deeptutor/services/compiled_knowledge/` | M34 一般知识 compiled teaching context |
| `deeptutor/services/assessment/` | Assessment/TestSet/blueprint 相关服务 |
| `deeptutor/services/photo_answer/` | 拍照识题 OCR 输入层 |
| `deeptutor/services/observability/` | ARR/AAE/OA/ReleaseGate/Langfuse/behavior/cost 观测控制面 |
| `deeptutor/services/member_console/` | BI / 会员 / external auth / admin-facing 操作 |
| `deeptutor/services/wallet/` | 钱包、余额、扣费、usage ledger |
| `deeptutor/tutorbot/` | TutorBot runtime、skills、channels、heartbeat |
| `deeptutor/tutorbot/skills/` | runtime skills，不等同 agent workflow skills |
| `agent-skills/` | 开发/QA workflow skills，不得移动到 TutorBot runtime skills |
| `web/` | Next.js Web、BI、wechat-harness |
| `wx_miniprogram/` | 小程序开发/测试面 |
| `yousenwebview/` | 真实微信宿主项目 root |
| `docs/plan/` | PRD、implementation plan、gate checklist 的统一地图 |
| `artifacts/luban_grading_artifacts/` | 鲁班评分、发布、shadow、benchmark、授权包证据 |
| `tmp/observability/control_plane/` | 本地观测控制面最新/历史 run |

## 5. 单一 authority 矩阵

后续 AI 做任何修改前，先定位“这次真正要维护的一等业务事实是什么”，再查下表。

| 业务事实 | 唯一 authority | 常见竞争者 / 禁止项 |
| --- | --- | --- |
| 聊天/流式 turn | `/api/v1/ws` + `TurnRuntimeManager` + `SQLiteSessionStore` | 新增聊天 WS、mobile/web 自建 pending truth |
| turn schema / trace vocabulary | `deeptutor/contracts/unified_turn.py` + `contracts/turn.md` | 不同入口自定义 `message/text`、trace 字段漂移 |
| capability 路由 | `ChatOrchestrator` | router、mobile adapter、前端 hint 直接决定 capability |
| question lifecycle scene | `QuestionLifecycleDecision` / `question_lifecycle_skills.py` | chat/tutorbot/deep_question 各自重判 scene |
| capability request config | `deeptutor/capabilities/request_contracts.py` | 旧字段 alias 深入运行时继续参与决策 |
| TutorBot 业务身份 | `TutorBot` runtime + bot defaults contract | `mini_tutor`、entry role、source/product_surface 升级成身份 |
| 默认知识链 | `bot_runtime_defaults.py` | router 散落默认 KB/tool 配置 |
| 知识召回 | `RAGService` | tool/agent 旁路直连第二套 retrieval |
| KB v5 | RAGService 后面的只读 provider | 直接写 KB、把 KB 当评分 authority |
| 客观题标准答案 | canonical answer_key / governed question registry | LLM/RAG/model vote 改写正确答案 |
| 案例题评分 | compiled rubric + runtime LLM adjudicator + deterministic validator | RAG 知识、普通模型常识、前端暗示生成官方分 |
| 正式评分可见分数 | active case / exact case / signed rubric / governed scoring event | open_skill 诊断伪装官方分 |
| scoring artifact lifecycle | M35 artifact governance + release gate | client status、legacy `published` 字段直接授予 official score |
| 学习证据 ledger | `learner_memory_events.learning_evidence` | product behavior、chat raw text、front-end local state 直接写学情 |
| 短期学习记忆 | `learning_synthesis.observed_candidates` | 单轮弱信号直接升长期画像 |
| 稳定 learner claims | `learning_synthesis.weak_points` + claim lifecycle | teacher_final 旧字段未经过 trusted adjudication |
| canonical learner truth | `LearnerStateService` + `canonical_truth_promotion_decision()` | shadow、preview、模拟复测、UI projection 写长期真相 |
| 学情页 read model | `learning_report_read_model.py` | route/frontend 自行重组 mastery 或 textbook progress |
| 单次作答详情 | `attempt_detail_read_model.py` | 暴露 raw event_id 或 list 后 filter |
| 错题集 | `mistake_book.py` | 前端页面 key 缓存 bookmark truth |
| 训练处方 | `training_intent.py` / training_prescription projection | home dashboard / UI 自己推 next action |
| 账户凭证 | `MemberConsoleService -> external_auth` | learner-state 保存密码、验证码、token |
| 钱包/扣费 | wallet snapshot / wallet ledger / `DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED` | capability route、learner profile、turn payload 变余额 truth |
| 行为智能 | `surface-events -> product_behavior_events` | Langfuse 或第三方 analytics 成为唯一行为 truth |
| BI 会员运营 | phone-backed identity aliases + v_members read model | member-console JSON 当生产会员池 |
| OCR 送批改文本 | `confirmed_text` | raw OCR / LLM 猜测 / 自动替换成为答案 truth |
| OCR 图片资产 | attachment store + photo_answer session store | OCR 层直接写 learner memory |
| Observability release | control-plane run history + release gate payload | shell exit code 误当 readiness truth |

## 6. 核心控制面

### 6.1 Turn Contract

Turn contract 管：

- `/api/v1/ws`
- turn / session / stream / replay / resume
- HTTP bootstrap adapter
- turn trace 字段
- TutorBot 接入方式

关键事实：

- 聊天与流式只有一个稳定入口：`/api/v1/ws`。
- mobile HTTP 可以 bootstrap，但不能定义第二套 streaming 协议。
- `result.metadata.response` 是 canonical final answer。
- 中间 `content` delta 只是展示增量，不能被拼成历史最终答案。
- public stream event 必须经过 hidden grading authority redaction。
- resume / mobile background recovery 必须回到 session/message store，而不是客户端 pending flag。

关键代码：

- `deeptutor/api/routers/unified_ws.py`
- `deeptutor/services/session/turn_runtime.py`
- `deeptutor/services/session/sqlite_store.py`
- `deeptutor/contracts/unified_turn.py`

### 6.2 Capability Contract

Capability contract 管：

- capability 路由
- request config schema
- orchestrator 选择规则
- registry 唯一入口

关键事实：

- `ChatOrchestrator` 是 capability 选择 authority。
- adapter 只能传 hints / auth / metadata。
- `capability` request 字段只是 hint，最终 turn capability 必须 runtime-resolved。
- `requested_response_mode` 是公开响应风格字段，`teaching_mode` 只能入口兼容归一化。
- semantic router / shadow mode 也属于 orchestrator 控制面，不能下沉到 router。

关键代码：

- `deeptutor/runtime/orchestrator.py`
- `deeptutor/runtime/registry/capability_registry.py`
- `deeptutor/capabilities/request_contracts.py`
- `deeptutor/runtime/bootstrap/builtin_capabilities.py`

内置 capabilities：

```text
chat
tutorbot
deep_solve
deep_question
deep_research
math_animator
visualize
```

### 6.3 RAG Contract

RAG contract 管：

- `RAGService` 统一 grounding 入口
- provider / pipeline / strategy 边界
- exact-question
- authority correction
- retrieval trace / evidence bundle
- compiled learning truth 的只读召回语义

关键事实：

- RAG 只提供 retrieval / context / source expansion，不判分。
- `rag` 是唯一知识召回工具。
- KB v5 可以作为 RAGService 后面的只读 provider，但不能成为第二套入口。
- exact-question 必须稳定输出 metadata。
- `compiled_learning_truth` 和 `PersonalizationContextPack` 只能只读进入 RAG，不能写 learner-state。
- 引用展示 authority 是结构化 `citation_bundle.refs / footer_text`，不是正文里随手拼 citation marker。

关键代码：

- `deeptutor/services/rag/service.py`
- `deeptutor/services/rag/pipelines/`
- `deeptutor/tools/rag_tool.py`
- `deeptutor/services/compiled_knowledge/general_knowledge.py`

### 6.4 Learner State Contract

Learner state contract 管：

- 学员长期状态
- Summary / Profile / Progress / Goals / Memory Events / Heartbeat
- Guided Learning / Notebook / TutorBot 写回边界
- Supabase 表与本地 fallback 的职责

关键事实：

- 第一阶段长期学员状态主键是 `user_id`。
- `LearnerStateService` 是统一长期 learner truth service。
- `learner_memory_events` 是唯一学习证据 append-only ledger。
- `TutorBot workspace memory` 不是长期学习真相。
- `LearnerWorkspace` 是用户资产空间，不是学习事实判断系统。
- `BotProfile`、`SessionStore`、`RuntimeSandbox` 不能承担长期 profile/progress/weak point truth。

五个一等概念：

| 概念 | 职责 |
| --- | --- |
| `LearnerState` | 学习证据、画像、弱点、掌握度、复测变化、next action 长期 truth |
| `SessionStore` | 聊天/session 历史、turn replay、conversation continuity |
| `BotProfile` | TutorBot 人格、教学风格、技能绑定、channel 绑定 |
| `LearnerWorkspace` | 学员可见资产：笔记、附件、收藏、导出、学习页 projection |
| `RuntimeSandbox` | 工具执行隔离、临时文件、debug artifact |

关键代码：

- `deeptutor/services/learner_state/service.py`
- `deeptutor/services/learner_state/learning_synthesis.py`
- `deeptutor/services/learner_state/memory_lifecycle.py`
- `deeptutor/services/learner_state/canonical_truth_policy.py`
- `deeptutor/services/learner_state/personalization_context.py`
- `deeptutor/services/learner_state/next_best_action.py`

### 6.5 Learning Report Contract

Learning report contract 管：

- learning report read model
- attempt detail read model
- mistake book
- training intent
- home personalization
- conversation evidence 枚举

关键事实：

- `build_learning_report_read_model()` 是 Learning Report 唯一 producer。
- `build_learning_brain_read_model()` 是 Learning Brain read model producer。
- `build_attempt_detail_read_model()` 是单次 attempt 详情 producer。
- read model 是只读 projection，不写持久化状态。
- v2 schema 通过 `?schema_version=2` 或 Accept header 显式协商，不能同 PR 删除 v1。

关键代码：

- `deeptutor/services/learner_state/learning_report_read_model.py`
- `deeptutor/services/learner_state/learning_brain_read_model.py`
- `deeptutor/services/learner_state/attempt_detail_read_model.py`
- `deeptutor/services/learner_state/mistake_book.py`
- `deeptutor/services/learner_state/training_intent.py`
- `deeptutor/services/learner_state/home_personalization.py`

### 6.6 Config Runtime Contract

Config runtime contract 管：

- `.env` / catalog / persisted settings 优先级
- provider runtime 解析
- LLM、embedding、search、RAG provider 的统一语义

关键事实：

- 业务模块不能各自读取 `.env` 并解释 provider。
- `tools.web_search.enabled` 是联网搜索唯一总开关。
- search provider 未配置、缺 key、缺 base_url 时不得隐式 fallback。

关键代码：

- `deeptutor/services/config/`
- `deeptutor/services/config/provider_runtime.py`
- `deeptutor/services/config/env_store.py`
- `deeptutor/services/runtime_env.py`

## 7. 鲁班评分引擎

### 7.1 定位

鲁班评分引擎的定位是“诊断仪”：

```text
这次答题哪里对
哪里错
为什么错
对应哪个知识点 / 采分点 / 错因
下一步如何训练
```

它产出高质量学习证据，但不直接成为长期 learner truth。

master plan 的当前 canonical 表述：

```text
鲁班评分引擎 = 高质量学习证据生产器
Learning Brain/GBrain = 长期个性化学习决策器
RAG/知识编译 = 教材、规范、真题、章节与证据供应器
DeepSeek/Qwen = 在线批改与教学执行模型
```

### 7.2 三种 runtime 模式

| 模式 | 触发 | 产出 | 禁止 |
| --- | --- | --- | --- |
| Official grading mode | 命中 canonical question / signed answer_key / signed rubric / governed registry | 正式或受控评分、点级命中、evidence_span、Learning Brain evidence draft | LLM/RAG/model vote 改写标准答案或 signed rubric |
| Open-world diagnostic mode | 未命中题库但仍是建筑实务问题 | 教学诊断、可解释建议、unverified evidence draft、compiler feedback candidate | 输出官方分、声称标准答案、写 canonical truth |
| Compiler feedback mode | 高价值未命中、review queue、LLM 分歧、RAG 新证据 | question/answer/rubric/source candidate 和 work_order | candidate 直接当 release truth |

### 7.3 全题型分层

| 题型 lane | 评分 authority | LLM 角色 | deterministic 角色 | Learning Brain 输出 |
| --- | --- | --- | --- | --- |
| objective_choice | canonical `answer_key` / option metadata / official question bank | 解释错因、定位知识点、组织依据 | 判对错、多选集合比较、tamper fail-closed | objective evidence event、错因标签、复测计划 |
| case_question | compiled rubric + source/spec/list authority + runtime LLM adjudication | 理解学生自然语言，点级 accept/partial/reject/needs_review | validator 防 false-positive、source laundering、fail-closed | point-level claim draft、review queue、study card |
| open_world_teaching | RAG / compiled context / TutorBot teaching context | 讲清知识、诊断思路、生成候选 work order | 不授予 official score | preview evidence / candidate，不升 mastery |

### 7.4 案例题评分链路

高层链路：

```text
user answer
  -> deep_question
  -> construction_grading
  -> rubric / artifact / runtime adjudicator
  -> deterministic validator
  -> construction_grading_result
  -> learning_evidence event draft
  -> LearnerStateService.append_memory_event(...)
  -> learning_synthesis
  -> PCP / NextBestAction / report projection
```

核心模块：

| 模块 | 职责 |
| --- | --- |
| `schema.py` | MCQ / Case result dataclass，evidence refs，error events |
| `case_kernel.py` | 案例题 skill kernel，curated/projected/open_skill 分层 |
| `rubric_grader_v1.py` | 点级 rubric 评分，LLM 判点、deterministic 汇总 |
| `runtime_llm_adjudicator.py` | runtime LLM adjudication |
| `case_output_policy.py` | 无评分 authority 时降级为诊断，不硬估标准分 |
| `learning_evidence.py` | 把 grading result 转为 learning evidence |
| `teacher_review_writeback.py` | teacher-final / trusted writeback 边界 |
| `m35_artifact_governance.py` | artifact runtime-consumable gate |
| `m35_status.py` | M35 status mapping、shadow block、kill switch |

`rubric_grader_v1.py` 的核心设计：

- 每个 scoring point 独立判定 `hit / partial / miss`。
- LLM 只做 per-point semantic adjudication。
- 总分由 deterministic sum 计算。
- `official_score_allowed` 默认 false，需 governed gate 才能升级。
- 输出映射到 learner-state learning_evidence schema。

### 7.5 M35 scoring artifact

M35 的重点是把 Nexus-like scoring artifacts 接回鲁班评分最有价值的主线。

当前 artifact lifecycle：

```text
candidate
  -> reviewed
  -> shadow_candidate
  -> release_candidate
  -> controlled_default
  -> superseded
```

但 `controlled_default` 只是 lifecycle status，不自动授予 official score。

runtime-consumable artifact 必须有：

- `owner_role`
- `review_authority`
- `supersede_policy`
- `rollback_policy`
- `artifact_version`
- `source_refs`
- `quality_gates`

硬边界：

- artifact 是全局/versioned。
- attempt 只引用 `artifact_version / point_id`。
- attempt 不复制 artifact 成第二套 learner memory。
- client-supplied status 不授予 official score。
- legacy `published` 不等于生产 published registry。

## 8. Learning Brain / GBrain-inspired Learner State

### 8.1 定位

Learning Brain 是“长期主治医生”：

```text
这个学生长期是什么画像
哪些弱点是真反复出现
哪些只是一次观察
复测后有没有改善
下一步最该练什么
什么证据可以升 canonical truth
```

它不重新评分，也不替代题库答案。它消费评分、作答、复测、对话、笔记等结构化学习证据。

### 8.2 四阶段生命周期

当前 learner memory lifecycle：

```text
Evidence Ledger
  -> Short-Term Learning Memory
  -> Stable Learner Claims
  -> Canonical Learner Truth
```

对应代码常量：

```text
evidence_ledger
short_term_learning_memory
stable_learner_claim
canonical_learner_truth
```

阶段解释：

| 阶段 | 含义 | 是否长期 truth |
| --- | --- | --- |
| Evidence Ledger | 原始学习信号发生，append-only 记录 | 否 |
| Short-Term Learning Memory | 单次观察形成候选记忆 | 否 |
| Stable Learner Claims | 重复出现、已确认或复测验证的弱点/进步 claim | 接近 truth，但仍需 gate |
| Canonical Learner Truth | 通过 promotion gate 后写入长期真相 | 是 |

证据等级：

| 等级 | 语义 |
| --- | --- |
| `L0_observed` | 单次观察，只能短期使用 |
| `L1_repeated` | 同概念同错误重复出现 |
| `L2_confirmed` | trusted adjudication 确认 |
| `L2_real_retest` | 真实复测验证改善/退步 |
| `L3_mastery_signal` | 可作为更强掌握信号 |

### 8.3 canonical truth promotion

生产环境写 canonical learner truth 受 `canonical_truth_promotion_decision()` 控制。

必须满足的典型条件：

- production write flag 打开。
- 用户属于 `qa_` / `operator_` 等受控 cohort，或 broad trusted adjudication gate 已开启。
- trusted source 可信，例如：
  - `certified_grading_policy`
  - `human_teacher`
  - `golden_label`
  - `operator`
  - `teacher_final` 兼容字段
  - `ai_jury` / `model_jury` / `best_quality_4model`，但需 confidence 与 conflict gate
- conflict 已 resolved / no_conflict。
- `requires_human=false`。
- 至少有 stable learner claim。

禁止：

- shadow / preview 证据直接写 canonical truth。
- L0-only projection 带伪 trusted block 后写 truth。
- 模拟复测当真实复测。
- teacher-final 旧字段绕过 trusted adjudication。

### 8.4 PersonalizationContextPack 与 NextBestAction

`PersonalizationContextPack` 是实时 turn 可以读取的只读个性化上下文。

来源：

- claims: `learning_synthesis`
- evidence: `learner_memory_events.learning_evidence`
- prescription: `training_intent`

它可以影响：

- 讲解语气
- 错因复盘深度
- 下一步训练提示
- 复测改善跟进

它不能：

- 写 learner-state
- 自己生成新 claim
- 覆盖评分结果
- 成为第二套推荐 authority

`NextBestAction` 从 `training_intent` 和 typed graph 生成行动卡。它解释“为什么现在练这个”，但处方 authority 仍是 `training_intent`。

## 9. Assessment / TestSet

### 9.1 定位

Assessment/TestSet 是鲁班“测”的入口，不是聊天里随机多出几道题。

核心业务事实：

```text
一次测评是一组服务端组装、版本化、可恢复、可提交、可计分的 assessment session。
每一道题的作答都是 learning evidence。
测评报告只是该 session 的 read model，不是新的学情 authority。
```

### 9.2 Canonical path

```text
User selects assessment type
  -> Mobile assessment API
  -> AssessmentBlueprintService chooses blueprint/form
  -> assessment_sessions stores public card + hidden answer/rubric
  -> Mini program renders full paper with local draft autosave
  -> User submits answers
  -> deterministic scorer / construction_grading
  -> result report
  -> per-item learning_evidence
  -> attempt detail / mistake book / learning report
```

### 9.3 关键 authority

| 事实 | authority |
| --- | --- |
| 题目资产 | `questions_bank` + canonical `QuestionArtifact` |
| 正式组卷蓝图 | `AssessmentBlueprintService` / `AssessmentBlueprint` |
| 预构建卷面 | `assessment_forms` |
| 学员一次答卷 | `assessment_sessions` |
| 客观题答案 | server-side hidden `answer_key` |
| 案例题/rubric | `construction_grading` |
| 长期学习事实 | `learner_memory_events.learning_evidence` |
| 学情展示 | learning report / attempt detail / mistake book read model |

### 9.4 当前状态

根据计划索引和 PRD：

- Assessment Blueprint 状态为 implemented locally，但线上闭环仍需按 release gate 验证。
- Assessment TestSet 已从“聊天出几道题”收敛为 session + result + report。
- P0A 推荐从防水或防水/装饰/机电专题小卷切入，先打穿端到端，再扩展真题样式与 mastery check。

## 10. Photo Answer OCR 输入层

### 10.1 定位

拍照识题不是批改系统，而是纸面答案进入现有批改链路的输入层。

核心业务事实：

```text
confirmed_text 是唯一送批改答案文本。
raw OCR 只是证据附件。
OCR 层不写 learning_evidence，不改评分内核，不新建聊天入口。
```

### 10.2 数据流

```text
小程序拍照
  -> 上传原图
  -> 创建 photo_answer session / OCR job
  -> L0/L1/L2 OCR routing
  -> suspicion spans / paragraph reconstruction
  -> 确认页
  -> confirmed_text
  -> 既有批改链路
  -> photo provenance 随 grading writeback 进入 canonical schema
```

### 10.3 成本与治理

OCR 计划的排序目标：

```text
成本控制 > 体验性能 > 识别能力上限
```

核心机制：

- L0 主识别：百度手写文字识别。
- L1 交叉校验：qwen-vl-ocr。
- L2 疑难升级：阿里 RecognizeHandwriting。
- cost ledger 使用 micros 单位。
- 所有付费动作走 `reserve -> provider_call -> settle/refund`。
- 单题自动路由软顶 0.1 元，用户主动重识别硬顶 0.3 元。

### 10.4 当前状态

根据计划：

- 服务端 `photo_answer` 包、REST 六端点、小程序 capture/confirm 子包已本地实现。
- feature flag 默认 off。
- M0 实测仍 blocked-on-user：需要用户开通 provider API key 并组织三分法样本。
- provenance schema contract、真实小程序回归仍是关键待办。

## 11. RAG / 编译知识 / Compiled Context

### 11.1 定位

RAG 和编译知识是证据供应器，不是最终判题器。

它们回答：

```text
教材哪里说过
规范条文在哪里
真题/题库证据在哪里
这个概念属于哪章哪节
哪些上下文应该进入 LLM 判题或教学
```

它们不回答：

```text
学生这题最终得几分
标准答案是否可以被改写
学生长期是否掌握
```

### 11.2 KB v5

当前 RAG authority 已识别为 KB v5：

- schema: `kb_v5`
- RPC: `public.search_chunks_v2`
- embedding: DashScope `text-embedding-v3` dim 1024
- source defaults: 2026 教材、标准、讲义、真题

KB v5 只能作为 `RAGService` 后面的只读 provider。禁止重建 legacy schema 作为捷径。

### 11.3 M34 compiled-knowledge dividend

M34 的目标是把编译知识红利从“做题才有”扩展到“一般建筑实务知识对话也能用”。

核心模块：

- `deeptutor/services/compiled_knowledge/general_knowledge.py`
- 复用 `canonical_resolution`
- 复用 `canonical_knowledge_runtime`
- 只输出 teaching-tier metadata
- 低置信、域外、active question 场景 fail-open

硬边界：

- 不是 official grading key。
- 不生成 answer key。
- 不写 canonical learner truth。
- 不新建第二套 RAG / KB / taxonomy / learner memory。

当前状态：

- capability GO。
- test2 shadow cohort bridge verified。
- system-wide default 当前 NO-GO，需 50/100+ online shadow 和 compiler pollution repair 后再裁决。

## 12. TutorBot 与 question lifecycle

### 12.1 TutorBot 是业务身份

`TutorBot` 是唯一业务身份，不能再创建第二套 tutor 身份。

TutorBot 可以承载：

- persona / teaching style
- tools / skills / knowledge base bindings
- channel bindings
- heartbeat
- runtime sandbox

TutorBot 不承担：

- 第二套聊天 transport
- 第二套 learner state
- 第二套 question authority
- 第二套 scoring authority

### 12.2 construction-exam-coach defaults

当前建筑实务 TutorBot 默认：

```text
bot_id = construction-exam-coach
execution_engine = tutorbot_runtime
default_tools = ["rag"]
default_knowledge_bases = ["construction-exam"]
```

这由 `bot_runtime_defaults.py` 统一治理，adapter 不应散落配置。

### 12.3 QuestionLifecycleDecision

题目生命周期 scene 是出题、批改、讲评、answer reveal、低信息真题查询、active question follow-up 的核心 authority。

关键原则：

- orchestrator 先裁决 scene，再决定 capability。
- TutorBot 请求 hint 不能绕过 lifecycle。
- 无 active question 的“我选B”必须澄清，不能猜。
- 多题上下文中未带题号的单选答案必须澄清。
- 低信息“2025真题答案”不能输出所谓官方答案。
- 明确“出题 / 考我 / 测我”属于 practice_generation，不能被低信息真题 guard 阻断。
- 练题生成必须由 `deep_question` 产出 canonical active object 和 hidden grading authority。

## 13. BI / Product Behavior / Observability

### 13.1 BI 定位

DeepTutor / 鲁班的 BI 不是普通用户数与充值数看板，而是覆盖：

- 经营总览
- 用户增长与留存
- 学习行为与转化漏斗
- Agent 能力与工具效果
- 知识库与内容资产
- 成本、质量与可观测性
- 会员、积分与营收
- Learner 360 / TutorBot 360

### 13.2 Product Behavior Intelligence

产品行为智能的一等事实：

```text
学员在真实产品表面上，对哪些学习模块产生了访问、停留、深入、行动和回访行为。
```

canonical path：

```text
真实产品表面
  -> surface-telemetry helper
  -> POST /api/v1/observability/surface-events
  -> SurfaceEventStore ACK snapshot
  -> product behavior persistence writer
  -> product_behavior_events
  -> BI_METRICS / BI read model
  -> BI 看板 / 运营分群 / 产品复盘
```

P0 最重要的 6 条路径：

| 路径 | 起点 | 终点 |
| --- | --- | --- |
| 历史使用 | `history.module_viewed` | `history.module_exited` |
| 学情使用 | `learning_report.module_viewed` | `learning_report.module_exited` |
| 学情 section | `learning_report.section_viewed` | `section_expanded` |
| 学情到训练 | `next_action.section_viewed` | `learning_action_started:start_training` |
| 历史到复盘 | `history.object_opened` | `learning_action_started:start_review` |
| 训练到复测 | `learning_action_completed:training` | `learning_action_started:start_retest` |

禁止：

- 行为事件写 learner-state。
- 行为事件包含完整聊天正文、主观题全文、验证码、密码、支付凭证。
- Langfuse trace 当产品行为唯一来源。
- 第三方 analytics 成为 canonical truth。

### 13.3 Observability control plane

观测控制面包括：

- OM
- ARR
- AAE
- ObserverSnapshot
- ChangeImpactRun
- OA
- ReleaseGate
- Benchmark
- Failed Turn Promotion

本地默认目录：

```text
tmp/observability/control_plane/
```

一键 pre-release 顺序：

```text
OM -> ARR -> AAE -> ObserverSnapshot -> ChangeImpactRun -> OA -> ReleaseGate
```

重要纪律：

- release readiness 看 payload `final_status / recommendation / blockers`，不是 shell exit code。
- fresh artifact 不等于 release closure。
- local pass 不等于线上闭环。
- release gate 没消费历史失败信号时，结论要降级。

## 14. Wallet / Member / Auth 边界

### 14.1 账户凭证

账号密码、手机号验证码、密码找回只能由：

```text
MemberConsoleService -> external_auth
```

管理。

这些事实不得写入：

- learner-state
- turn/session runtime
- capability payload

`/api/v1/auth/reset-password` 成功后：

- 更新 external auth 密码
- 消费验证码
- 失效旧 session
- 不返回 token
- 不自动登录
- 不写学习事实

### 14.2 钱包 / 用量

钱包事实与学习事实分权。

| 场景 | authority |
| --- | --- |
| 余额、冻结余额 | wallet snapshot |
| 真实扣费与用量 | wallet ledger |
| 内测非财务展示 | MemberUsageMeter |
| 是否启用扣费 | `DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED` |

当前内测可用量展示：

- billing enforcement 关闭时不扣钱包。
- MemberUsageMeter 可提供非财务 usage display。
- 450 turns 可作为内部 beta 100% 基准。
- 对外展示百分比，不直接展示剩余次数。

禁止：

- learner profile 保存钱包事实。
- capability route 根据余额做语义决策。
- wallet ledger 失败导致学习报告或聊天系统误写学情。

## 15. 当前主线状态摘要

以下是 2026-06-11 读本文时最重要的状态边界。后续如计划更新，以 `docs/plan/INDEX.md` 和具体 plan 最新段落为准。

| 主线 | 当前状态 | 后续 AI 不能误写成 |
| --- | --- | --- |
| M32 Grading-to-Brain waterproof vertical slice | GO | 不等于全量 production default |
| M33 canonical promotion arm | GO for `qa_`/`operator_` 1% governed promotion arm | 不等于 broad canonical learner truth write |
| M34 compiled-knowledge dividend | capability GO + test2 shadow bridge verified | system-wide default 仍 NO-GO |
| M35 scoring artifact production decision | decision package 曾为 NO-GO；GO 路线 active，需 AI-governed gold / cached A/B / decision flip | 不等于 real-student official score default |
| Learner memory lifecycle | 四阶段 vocabulary 和 test2 remote proof 已建立 | 不等于 broad production canonical writes |
| Assessment Blueprint / TestSet | 本地实现和计划主线清晰，需真实发布/环境 gate | 不等于所有微信真入口已闭环 |
| Product Behavior Intelligence | P0 locally implemented，WeChat DevTools/真机与 production observation pending | 不等于 production behavior BI 已完全可信 |
| Photo Answer OCR | M1+M2 code locally implemented，feature flag off；M0 provider key/sample blocked | 不等于可给真实用户默认开启 |
| RAG KB v5 | 正确 authority 已只读确认，dev legacy adapter 有过 schema drift | 不等于 RAG 可判分 |
| Release / Aliyun | 远端/DB/published registry 需独立授权 | 不得自动写远端或 flip default |

## 16. 典型业务链路

### 16.1 普通聊天 / TutorBot 知识问答

```text
client
  -> /api/v1/ws start_turn
  -> TurnRuntimeManager creates turn/session records
  -> context build: session history + learner-state compact context + active object + RAG hints
  -> ChatOrchestrator selects capability
  -> TutorBot / ChatCapability
  -> RAGService if grounded
  -> LLM response
  -> StreamEvent content/result
  -> hidden authority redaction at public boundary
  -> SQLiteSessionStore persists canonical final answer
  -> optional conversation learning evidence writeback
```

### 16.2 练题生成

```text
user asks "出几道题 / 考我 / 继续练"
  -> /api/v1/ws
  -> QuestionLifecycleDecision: practice_generation
  -> ChatOrchestrator resolves deep_question
  -> deep_question builds QuestionArtifact / active_object
  -> hidden grading authority stored server-side
  -> public presentation redacts answer/rubric
  -> later answer submission uses same active object
```

### 16.3 客观题作答

```text
user submits answer
  -> active question / exact question context
  -> canonical answer_key comparison
  -> deterministic correctness and option diff
  -> LLM/RAG may explain why
  -> objective evidence event
  -> learner_memory_events
  -> learning report / mistake book / next training
```

### 16.4 案例题作答

```text
user submits case answer
  -> deep_question / construction_grading
  -> rubric points / runtime adjudication
  -> deterministic validator
  -> point-level result:
       accept / partial / reject / needs_review
       evidence_span
       score candidate
       mistake_type
  -> official_score_allowed gate
  -> learning_evidence draft
  -> LearnerStateService append
  -> learning_synthesis
  -> PersonalizationContextPack / NextBestAction
```

### 16.5 Assessment session

```text
user enters assessment
  -> assessment blueprint/form
  -> assessment_sessions
  -> public redacted paper
  -> local draft autosave only
  -> submit
  -> deterministic/objective + construction_grading
  -> report read model
  -> per-item learning_evidence
  -> attempt detail / mistake book / learning report
```

### 16.6 Photo answer

```text
question page
  -> photo-answer session
  -> page upload
  -> OCR job
  -> suspicion spans
  -> confirm page
  -> confirmed_text
  -> existing answer submission / grading
  -> provenance fields included only through canonical writeback schema
```

### 16.7 Behavior intelligence

```text
surface event
  -> surface-telemetry helper
  -> /api/v1/observability/surface-events
  -> event catalog / persistence
  -> product_behavior_events
  -> indexed raw read model / BI_METRICS
  -> member-ops / Member360 / product decisions
```

## 17. AI 后续升级的工作法

每次非平凡改动先写清：

1. `one business fact`：这次真正维护的业务事实是什么。
2. `one authority`：谁唯一写、存、恢复、读。
3. `competing authorities`：哪些字段、模块、fallback、adapter、projection 在抢权。
4. `canonical path`：从 writer 到 persistence / routing / assembly / reader 的主链路。
5. `delete or demote`：这次准备删除、降级或归一化哪些 mirror state / bypass reader / alias。
6. `verification target`：用什么测试、harness、DevTools、trace、release gate 证明。

推荐流程：

```text
pwd -P
git status --short --branch
read AGENTS.md / CONTRACT.md / contracts/index.yaml / docs/plan/INDEX.md
locate current plan authority
identify contract domain
inspect code authority, preferably structural lookup when available
write failing/targeted tests for authority behavior
make surgical change
run targeted tests + contract guard
if frontend/wechat: run /wechat-harness then real DevTools evidence when required
report changed files, verification, remaining risk
```

## 18. 禁止模式清单

后续 AI 如果想做下面任何事，默认先停下来重新做 authority 分析：

1. 新增 `/api/v1/mobile/tutorbot/ws/...` 或任何聊天 WebSocket。
2. 让 mobile router 直接决定 capability。
3. 在前端根据文案推断 score、mastery、next action。
4. 用 RAG chunk、LLM 常识或相似题经验生成官方分。
5. 把 shadow / preview / dry-run 写成 canonical learner truth。
6. 把 `teacher_final` 当主生产 authority，而不是 compatibility trusted adjudication。
7. 让 OCR raw text 自动替代学生确认稿。
8. 让行为事件进入 learner_memory_events。
9. 把 Langfuse cost 当官方成本账本。
10. 用 local JSON / member-console cache 当生产会员池。
11. 以 `/wechat-harness` 绿灯替代 `yousenwebview/packageDeeptutor` 真入口。
12. 在未授权情况下写 Aliyun `/root/deeptutor` 之外路径。
13. 在未授权情况下 flip production default、published registry、canonical write、远端 DB 写。
14. 把 `next dev --webpack` 当内存问题已修复。
15. 为一次性需求新增大型 framework、第二套 router、第二套状态机。

## 19. 升级方向建议

这些不是立即执行命令，而是后续升级时的优先级判断。

### 19.1 最高价值主线：让学习闭环变得可感知

用户真正感知价值的不是“系统有评分模块”，而是：

```text
我这次丢了哪些采分点
为什么丢
这对应哪章哪节
系统记住了
下一题确实针对这个弱点
复测后系统能看出我进步了
```

所以升级优先级应围绕：

- 学员可见的 point-level evidence。
- `learning_evidence -> claim -> PCP -> NBA -> retest` 的可视化。
- 复测变化和错因趋势。
- 学情首页 / 今日任务 / 错题 / 采分点手册的同一 truth projection。

### 19.2 鲁班评分引擎：从 candidate 到 governed quality

不要只堆离线 artifact。更关键的是：

- AI-governed gold 的 source validity 与 label ceiling。
- cached A/B 对比旧 human-vs-artifact 红灯。
- runtime LLM adjudication 的 evidence_span 与 false-positive guard。
- official score 与 teaching diagnosis 的边界。
- review queue / teacher packet / compiler feedback flywheel。

### 19.3 M34 compiled knowledge：先 online shadow，再 default

M34 一般知识教学红利已经接线，但 default 不能急。

下一步应先补：

- 50/100+ online shadow。
- wrong path / source validity / answer improvement / regression 指标。
- compiler pollution repair 的真实部署和复测。
- low-confidence fail-open 的可观测性。

### 19.4 Photo answer：先 M0 实测，不要直接上线

拍照答案是高价值入口，但风险很集中：

- OCR 错会污染批改可信度。
- 成本若不钉死会破坏套餐毛利。
- 图片隐私、EXIF、retention、provider 数据使用条款必须上线前确定。
- provenance schema 未闭合前，photo 路径批改只能 preview，不写长期证据。

### 19.5 BI / behavior：从“看见点击”升级到“能做运营动作”

行为智能不是热图，核心价值是：

- 哪些用户高频看学情但不训练。
- 哪些用户训练后不复测。
- 哪些用户只聊天不进入学习闭环。
- 哪些模块带来复盘、错题、训练和留存。

落点应在 BI `会员运营` / `Member360`，不要新造平行后台。

### 19.6 微信真入口闭环

Web harness 很有价值，但真实用户在微信端。

前端/微信升级必须最终能回答：

- `yousenwebview` project root 是否可打开。
- `packageDeeptutor` 目标页面是否可进入。
- auth 状态是否明确。
- 真实页面是否完成目标场景。
- 证据是否区分 shadow / partial / real_wechat_package。

## 20. 关键术语表

| 术语 | 含义 |
| --- | --- |
| DeepTutor | agent-native learning engine，鲁班智考背后的主架构 |
| 鲁班智考 | 建筑实务考试 AI 陪考产品 |
| TutorBot | 唯一业务 tutor 身份，完整持久 runtime |
| deep_question | 题目生命周期核心 capability，负责出题、批改、讲评等 |
| `/api/v1/ws` | 唯一聊天/turn WebSocket |
| TurnRuntimeManager | turn/session/stream/replay/resume 运行时 |
| ChatOrchestrator | capability 路由 authority |
| QuestionLifecycleDecision | 题目 scene / skill / route 的裁判 |
| RAGService | 唯一知识召回入口 |
| exact_question | 高置信题库/题面命中 metadata |
| Learning Brain | 长期学习事实、弱点、claim、next action 的综合层 |
| learner_memory_events | 学习证据 append-only ledger |
| learning_evidence | 结构化学习证据事件 |
| PersonalizationContextPack | 实时 turn 可读的个性化上下文投影 |
| NextBestAction | 基于 training_intent 的下一步行动卡 |
| canonical learner truth | 通过 promotion gate 后的长期学习真相 |
| compiled context | 编译知识/评分上下文 pack，服务 LLM 与 teaching |
| official score | 受 governed authority 允许的正式/受控分数 |
| open_skill | 无官方评分 truth 时的提分诊断模式 |
| shadow | 不改变 legacy / production truth 的影子验证 |
| release gate | 发布前质量、观测、contract、风险裁决 |
| `yousenwebview` | 微信开发者工具 project root |
| `packageDeeptutor` | 鲁班微信目标分包 |
| `/wechat-harness` | Web shadow QA，不等于真实微信入口 |

## 21. 最小查找索引

| 想了解 | 先看 |
| --- | --- |
| 总 contract | [CONTRACT.md](../../CONTRACT.md), [contracts/index.yaml](../../contracts/index.yaml) |
| 鲁班主线现状 | [docs/plan/INDEX.md](INDEX.md) 的“鲁班评分引擎总控入口” |
| 评分引擎目标 | [2026-06-04-luban-grading-engine-master-control-plan.md](2026-06-04-luban-grading-engine-master-control-plan.md) |
| Learner memory lifecycle | [2026-06-09-learner-memory-lifecycle-execution-plan.md](2026-06-09-learner-memory-lifecycle-execution-plan.md) |
| Turn / WS | [contracts/turn.md](../../contracts/turn.md) |
| Capability 路由 | [contracts/capability.md](../../contracts/capability.md) |
| RAG | [contracts/rag.md](../../contracts/rag.md) |
| Learner state | [contracts/learner-state.md](../../contracts/learner-state.md) |
| Learning report | [contracts/learning-report.md](../../contracts/learning-report.md) |
| Config runtime | [contracts/config-runtime.md](../../contracts/config-runtime.md) |
| Assessment | [2026-05-24-luban-assessment-testset-module-prd.md](2026-05-24-luban-assessment-testset-module-prd.md) |
| Photo answer | [2026-06-10-luban-photo-answer-ocr-input-layer-implementation-plan.md](2026-06-10-luban-photo-answer-ocr-input-layer-implementation-plan.md) |
| Product behavior | [2026-06-02-luban-product-behavior-intelligence-prd.md](2026-06-02-luban-product-behavior-intelligence-prd.md) |
| BI | [../zh/bi/README.md](../zh/bi/README.md) |
| Observability | [../zh/guide/observability-control-plane.md](../zh/guide/observability-control-plane.md) |

## 22. 最后提醒

鲁班系统的难点不是“功能不够多”，而是已经有很多高能力模块，后续最容易错在 authority 漂移。

未来每次升级都要问：

```text
这是不是同一个业务事实的第二个名字？
这是不是在 wrapper 里偷做业务判断？
这是不是把 shadow 当 production？
这是不是让用户看见了一个系统无法长期兑现的承诺？
```

如果答案有任何一个是“可能”，先回到 contract 和 master plan，不要继续 patch。
