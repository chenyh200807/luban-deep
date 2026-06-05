# 2026-06-05 WeChat TutorBot 真题对话循环 QA

## Scope

- 入口：微信小程序同构链路，`/api/v1/wechat/mp/login` -> `/api/v1/chat/start-turn` -> `/api/v1/ws subscribe_turn`。
- Bot：`capability=tutorbot`，`interaction_profile=tutorbot`，`knowledge_bases=["construction-exam"]`。
- 题库来源：`/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库/`。
- 评分口径：客户满意度优先，同时看正确性、语言理解、表达质量、上下文承接、拒答是否合理。

## Root Shape

这轮复现的共同失败不是单一题目不会做，而是“题目对象 authority”在多条链路间没有完全收敛：

- Orchestrator / question lifecycle 可能还持有上一题 active object。
- 普通 TutorBot 可以收到完整新题，但旧 active context 仍可能偷走本轮。
- Deep question / question review / TutorBot 使用不同状态投影时，题干、选项、用户答案、题库 exact evidence 没有同一个主事实。
- RAG degraded / empty-index 只进入工具事件、日志或观测，未进入最终回答的 authority，导致模型在证据不足时仍自信改判或掉到空白兜底。

## Probe Results

| ID | 学员模拟输入 | 期望 | 实际 | 评级 | 处理 |
| --- | --- | --- | --- | --- | --- |
| A1 | `2025年一建建筑实务防水那道真题，直接告诉我答案...别让我再复制题干` | 不编答案，说明题卡/题干缺失 | 不再进 RAG 错误，但文案像“不知道你要做什么” | P2 UX | 已改成明确提示“小程序未传题卡对象/题干/选项” |
| A2 | 防水砂浆温度完整单选题 | 答 C. 5℃ | 答 C，但 RAG 不可用时措辞信心摇摆 | P2 | 暂登记 |
| B1 | 海洋钢筋锈蚀错选 D | 批错并讲氯盐 | 正确，能解释硫酸盐 vs 氯盐 | Pass | 保留 |
| B2 | 追问“硫酸盐也腐蚀吧” | 承接上一题 | 正确承接并解释边界 | Pass | 保留 |
| C1 | 地下连续墙完整多选，用户选 ACDE | 期望 CDE，A/B 错 | 早期错判 B 正确；修 guard 后一度空白兜底；p06 live 在 Supabase 404 后命中历史题库 exact question，答 CDE 并讲 A/B 错 | Pass with P1 rollout caveat | 已接入历史题库 exact authority；仍需生产题库 artifact/前端题卡对象闭环 |
| C2 | 接 C1 追问 `guide wall height >=1.0m is OK? yes/no` | No，应按 1.2m | 早期回 Yes；最新 live 回 `No, ≥1.2m` | Pass with caveat | 事实答复已恢复；仍受 RAG empty-index 影响 |
| D1 | `我选BD，快批，别问太多。` | 无题干时合理澄清 | 正确澄清缺题目 | Pass | 保留 |
| E1 | 模板支架保证项目完整题，紧凑选项 `A施工方案 B支架构造...我选ABCE对吗` | 识别完整题并批改，答案 ABE | 起初拒绝“还不知道哪道题”；p05 后又被 clarification active_object 阻断 RAG；修后可走 RAG 并答 ABE | P0 fixed | 已修 compact MCQ anchor + clarification active_object 不再禁用新题 RAG |
| F1 | `2023地下连续墙多选答案是不是CDE？别装不知道。` | 没有 exact evidence 时不能否定/乱编 | RAG 不可用仍自信说“不是 CDE” | P1 fixed guard | 已加 degraded exact-answer 保护，WS metadata 透传 guard/degraded |
| G1 | 屋面防水卷材上翻高度案例 | 答 250mm，按“一句话” | 答案正确但过长 | P2 expression | 暂登记 |
| H1 | 情绪化记忆口诀请求 | 安抚并给短口诀 | 有帮助但仍偏长 | P2 expression | 暂登记 |
| I1 | 压型金属板屋面坡度完整单选，用户选 C 并要求 `别展开，一句话` | 批错、给 D/5%，一句话 | 修前 exact fast-path 输出完整教学模板；p11 后返回一句话 | Pass | 已把用户表达约束传入 exact authority builder |
| J1 | 固定 QA 号 `qa_tutorbot_mcq` 走移动端 login/profile/start-turn | 不人工注册、不收费、不被 wallet 读卡住 | 修前 `/auth/profile` 因 wallet 404/503 中断 smoke | Pass | 内部 QA profile 钱包读返回 `internal_qa` 快照 |
| K1 | 同一屋面坡度题，但学员手抄乱序：`A.5% B.1% C.2% D.3%，我选A` | 按当前题面判 A 对，不能沿用题库旧字母 D | 修前答“不对，标准答案D”；p13 后答“对，标准答案A” | Pass with follow-up caveat | 已把 historical exact question 投影到 query option surface |
| K2 | 接 K1 追问 `是不是因为你按旧题库字母没看我这轮选项？` | 承接刚才乱序题并承认/澄清当前题面 A 才对 | 仍说“不知道你要批改哪一道题” | P1 context continuity | 新登记，待查 exact fast-path 后 active question continuity |

## Fixed This Loop

1. 新完整题覆盖旧 active object
   - 完整 free-text MCQ answer request 不再被旧题卡 active context 偷走。
   - 紧凑选项格式 `A施工方案 B支架构造` 可识别为题目锚点。

2. 低信息真题答案请求
   - `2025防水那道真题直接告诉答案` 不进入题目讲评/生成链路。
   - 澄清文案明确指出当前微信链路没有传入题卡对象/题干/选项，而不是泛泛说不知道。

3. RAG degraded 后自信改判
   - RAG trace metadata 现在写回本轮 runtime metadata。
   - 若用户问“某组选项是不是答案”，且 RAG degraded、无 exact question，不允许最终输出自信否定或改成另一个答案。
   - fast policy 风险场景下不转发错误前缀流，最终只发保护后的可见回答。
   - full-agent 风险场景也抑制未 guard 的模型流式正文，最终 WS 只展示保护后的答案。
   - WS result metadata 透传 `rag_retrieval_degraded`、`rag_retrieval_status`、`degraded_exact_answer_guard_applied`。

4. clarification active_object 不再伪装成题目对象
   - `question_lifecycle_clarification` active_object 不再让 TutorBot 判断“已有题目流”。
   - 新发完整 MCQ grading 题可以继续触发 RAG prefetch / 多轮工具，而不是被上一轮澄清对象阻断。

5. RAG empty-index 现在进入 degraded authority
   - LlamaIndex 返回 `No documents indexed` / `No relevant documents found` 且无 sources 时，RAGAdapterTool 不再把它当普通答案。
   - trace metadata 标记 `retrieval_degraded=true`、`retrieval_status=empty_index`、`error_type=RAGEmptyIndex`。
   - 完整 MCQ grading 在 RAG empty-index 且无 exact question 时，不再掉到“模型没有返回可见答案”，也不伪称“题库标准答案确认”。
   - WS result metadata 透传 `degraded_mcq_grading_guard_applied=true`。

6. 历史题库 exact authority 接入 RAGService
   - 新增历史题库 resolver：只在用户消息已经包含完整 MCQ 题干和至少两个选项文本时，从 `DEEPTUTOR_HISTORICAL_QUESTION_BANK_DIR` 配置的题库 JSON 中解析 canonical exact question。
   - Supabase / RAG provider 失败时，如果完整题能命中历史题库，RAGService 返回 `exact_question`、`canonical_question_context`、`evidence_bundle` 和 `retrieval_status=provider_failed_exact_question_resolved`。
   - TutorBot final 继续走现有 exact fast path；wrapper 只做入口/异常边界，题目标准答案 authority 放在 RAG fat service 侧。
   - p06 live evidence：`turn_1780661116386_217dc55edf`，RESULT metadata `authority_applied=true`、`exact_question.source_group=historical_question_bank`、`correct_answer=CDE`、`rag_retrieval_degraded=true`、`degraded_mcq_grading_guard_applied=false`。
   - 对外 metadata 不再包含本机 `source_path`；live RESULT event 检查未发现 `/Users/yehongchen` 路径泄露。

7. 后台 observer 能看见 exact authority
   - `turn_observation` terminal event 现在从同一份 final RESULT metadata 投影出 `authority_applied`、`execution_path`、`exact_question` 摘要、`rag_retrieval_status` 和 degraded guard 字段。
   - observer exact question 摘要只保留 `id / answer_kind / question_type / source_group / correct_answer / source_file / content_hash`，不携带题库本机路径或完整选项长文本。
   - p07 live evidence：`turn_1780661568387_2bbd0b106a`，observer JSONL 记录 `exact_question.correct_answer=CDE`、`rag_retrieval_status=provider_failed_exact_question_resolved`、`authority_applied=true`，未发现 `source_path` 或 `/Users/yehongchen`。

8. 内部 QA billing bypass
   - 新增 `DEEPTUTOR_INTERNAL_QA_BILLING_BYPASS=true`，且仅非 production runtime + 内部 QA 身份前缀生效；生产误设也不会绕过收费。
   - `DEEPTUTOR_RUNTIME_ENV=production` 已纳入 runtime authority，避免只设置 runtime env 时误判为 local。
   - bypass 覆盖三处 QA 噪音：auth wallet bootstrap、start-turn quota gate、turn 完成后的 wallet capture。
   - `scripts/run_luban_local_test_backend.sh` 默认启用该内部模式，banner 显示 `billing-bypass=internal-qa`。
   - 新增固定内部测试号 seed：`qa_tutorbot_mcq / qa_tutorbot_followup / qa_tutorbot_weird / qa_tutorbot_case`，默认密码 `QaTutorbot2026`；后续微信链路 loop 固定使用这些账号，不再临时注册一次性账号。
   - p08 live evidence：`turn_1780662356729_362ed493d6`，注册、建会话、start-turn 日志未再出现 wallet bootstrap/quota/capture；RESULT metadata `billing_capture=null`，题库 exact answer 仍命中 D。
   - p09 live evidence：`turn_1780663489181_60d9becf0e`，Langfuse 本地 trace 可用；RESULT metadata `billing_capture=null`、`exact_question.correct_answer=D`、`rag_retrieval_status=provider_failed_exact_question_resolved`。
   - p10 live evidence：固定账号 `qa_tutorbot_mcq` 登录后跑微信同构链路，`turn_1780663947405_edeabd6e1d` completed；RESULT metadata `billing_capture=null`、`exact_question.correct_answer=D`、`authority_applied=true`。

9. exact authority 尊重明确简短表达约束
   - `AgentLoop` 在 exact authority override 和 exact RAG fast-path 两处，把本轮用户原话传入同一个 `build_exact_authority_response`。
   - MCQ exact authority builder 只在用户明确要求 `一句话 / 别展开 / 只说答案 / 不用解析` 等场景切到简短答案；默认完整教学模板保持不变。
   - 这是 expression projection，不是新的答案 authority：标准答案、选项文本、解析依据仍来自 `exact_question`。
   - p11 live evidence：固定账号 `qa_tutorbot_mcq`，`turn_1780665484309_6172b5c2f1` completed，内容为 `不对，标准答案是 D（D. 5%），题库解析依据是：屋面最小坡度：压型金属板：5%。`；RESULT metadata `billing_capture=null`、`authority_applied=true`、`exact_question.correct_answer=D`。

10. 内部 QA profile 钱包读 bypass
   - 真实微信链路前置 `/api/v1/auth/profile` 也纳入内部 QA billing bypass；固定 QA 号不再因钱包 Supabase 404/503 中断 smoke。
   - bypass 仍只由 `internal_qa_billing_bypass_allowed` 判定，非 production + QA 身份前缀才生效；非 QA 钱包失败测试保持 fail-closed。
   - p12 live evidence：`qa_tutorbot_mcq` 登录后 `/api/v1/auth/profile` 返回 `user_id=7465c84a-d1d6-4ff8-82d8-22945addbf86`、`points=120`、`wallet.plan_id=internal_qa`。

11. 乱序选项的 current-surface answer authority
   - historical question resolver 现在只把题库原题作为“正确值/解析”的 authority；如果用户当前消息里给出了完整选项表，则把 canonical correct answer 投影到当前题面字母。
   - 这避免题库旧字母抢走学员当前题面选项语义：同一道题原题 `D=5%`，若用户当前题面写成 `A=5%`，本轮标准答案应显示为 `A（A. 5%）`。
   - provenance 保留在 metadata：`canonical_correct_answer=D`、`option_surface=query`；最终判题和展示使用 query surface。
   - p13 live evidence：固定账号 `qa_tutorbot_weird`，`turn_1780666512262_e4afb5dabe` completed，内容为 `对，标准答案是 A（A. 5%），题库解析依据是：屋面最小坡度：压型金属板：5%。`；RESULT metadata `billing_capture=null`、`authority_applied=true`、`execution_path=tutorbot_exact_fast_path`、`exact_question.correct_answer=A`、`exact_question.options[0]=A.5%`、`exact_question.metadata.canonical_correct_answer=D`。

## Team Monitoring Notes

- 主代理：负责真实小程序同构链路复现、最小代码修复、测试与 scoped commit。
- 微信链路审计子代理：确认微信主链路应保持 `/api/v1/chat/start-turn` + `/api/v1/ws`，不要新增专用 TutorBot WS；同时标出 `deep_question` 外部预选和 start-turn bootstrap capability 不是最终 authority 的风险。
- 题目 authority 子代理：确认旧问题不是单题不会做，而是 exact question / active object / RAG evidence 在多个模块间投影不一致；建议把标准答案对象收敛为 canonical question context。
- 题库探针子代理：提供地下连续墙、屋面上翻高度、危大、见证取样、模板支架、抹灰等 diverse probe 池，用于后续循环。
- 后台/Langfuse 子代理：确认本地 `.env` 中 `LANGFUSE_ENABLED=false`，当前 live 证据主要来自后端日志和 WS RESULT metadata；Langfuse 还不是本轮真实 trace authority。

## Open Problems

- P1：历史题库 resolver 目前是 full-MCQ vertical slice，不是生产题库总闭环。还需要把签名/可部署的题库 artifact、题卡 id、前端题面对象和 Supabase/KB source evidence 收敛成同一个 canonical question authority。
- P1：题卡 id / 当前题面对象没有从微信前端稳定传进 TutorBot 时，系统只能澄清，无法兑现“我在小程序刷题，别让我复制题干”的体验。
- P1：exact fast-path 首轮命中后，下一轮对“刚才那道题/这轮选项”的追问仍可能丢失 active question continuity；p13 第二轮 `turn_1780666569540_d42be278b9` 仍返回“不知道你要批改哪一道题”。
- P2：exact MCQ 首答的一句话模板问题已修；但 follow-up/general LLM 路径仍可能在用户要求“一句话/别废话”时偏长，例如 p11 第二轮解释 C 为什么不对时输出了两句较长文本。
- P2：RAG unavailable 的措辞需要更稳定：可以给候选判断，但不能说成题库标准确认。
- P2：本地 `/api/v1/wechat/mp/login` 缺 `WECHAT_MP_APP_ID/WECHAT_MP_APP_SECRET` 时返回 502；当前 QA 通过注册登录绕过，只验证 `/api/v1/chat/start-turn` + `/api/v1/ws`。
- P2：正式 billing/wallet 链路仍要单独做生产对账；本轮 bypass 只服务内部 QA，不作为真实收费链路证据。
- P2：Langfuse 本地默认未启用；若要把“拒答/降级/exact authority”纳入日常监控，需要显式启用并定义 turn-level trace 字段。
- P2：WS live probe 偶发 keepalive timeout；本次 turn 后端和 DB 都完成，但客户端未稳定收到 close/done，需要后续按 transport/replay 层单独压测。

## Next Loop Probes

- Shuffled options：同一题乱序后，答案必须按当前用户选项语义判断，不能按历史字母。
- Context object continuity：先给题卡，再连续问“为什么不是 B”“那 1.0m 对吗”，看是否读取同一个题目对象。
- Exact fast-path continuity：首轮 exact MCQ 命中后，连续追问“刚才那题为什么不是 X / 你是不是按旧字母了”，必须读取上一轮 exact question surface。
- Missing stem：只说“2015案例5第2问答案”时必须澄清，不得 hallucinate。
- Full case grading：检查采分点、易错点、估分、学习记忆是否同一份 evidence。
