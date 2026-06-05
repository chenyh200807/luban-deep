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
| C1 | 地下连续墙完整多选，用户选 ACDE | 期望 CDE，A/B 错 | 早期错判 B 正确；修 guard 后一度空白兜底；最新 live 不再空白，标记 RAG `empty_index` 并拒绝伪称标准答案 | P1 factual authority / P0 blank fixed | 已修空白与乱改判保护；未修 exact evidence 命中 |
| C2 | 接 C1 追问 `guide wall height >=1.0m is OK? yes/no` | No，应按 1.2m | 早期回 Yes；最新 live 回 `No, ≥1.2m` | Pass with caveat | 事实答复已恢复；仍受 RAG empty-index 影响 |
| D1 | `我选BD，快批，别问太多。` | 无题干时合理澄清 | 正确澄清缺题目 | Pass | 保留 |
| E1 | 模板支架保证项目完整题，紧凑选项 `A施工方案 B支架构造...我选ABCE对吗` | 识别完整题并批改，答案 ABE | 起初拒绝“还不知道哪道题”；p05 后又被 clarification active_object 阻断 RAG；修后可走 RAG 并答 ABE | P0 fixed | 已修 compact MCQ anchor + clarification active_object 不再禁用新题 RAG |
| F1 | `2023地下连续墙多选答案是不是CDE？别装不知道。` | 没有 exact evidence 时不能否定/乱编 | RAG 不可用仍自信说“不是 CDE” | P1 fixed guard | 已加 degraded exact-answer 保护，WS metadata 透传 guard/degraded |
| G1 | 屋面防水卷材上翻高度案例 | 答 250mm，按“一句话” | 答案正确但过长 | P2 expression | 暂登记 |
| H1 | 情绪化记忆口诀请求 | 安抚并给短口诀 | 有帮助但仍偏长 | P2 expression | 暂登记 |

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

## Open Problems

- P1：地下连续墙真题标准答案仍未根治。C1 现在不空白、不乱改判，但仍没有命中题库 exact question；需要题库 exact question / source evidence 成为唯一答案 authority，不能让闭卷 LLM 或降级文案替代真题标准批改。
- P1：题卡 id / 当前题面对象没有从微信前端稳定传进 TutorBot 时，系统只能澄清，无法兑现“我在小程序刷题，别让我复制题干”的体验。
- P2：用户明确要求“一句话/别废话”时，TutorBot 仍常输出完整教学模板，表达质量影响满意度。
- P2：RAG unavailable 的措辞需要更稳定：可以给候选判断，但不能说成题库标准确认。
- P2：本地 `/api/v1/wechat/mp/login` 缺 `WECHAT_MP_APP_ID/WECHAT_MP_APP_SECRET` 时返回 502；当前 QA 通过注册登录绕过，只验证 `/api/v1/chat/start-turn` + `/api/v1/ws`。

## Next Loop Probes

- Shuffled options：同一题乱序后，答案必须按当前用户选项语义判断，不能按历史字母。
- Context object continuity：先给题卡，再连续问“为什么不是 B”“那 1.0m 对吗”，看是否读取同一个题目对象。
- Missing stem：只说“2015案例5第2问答案”时必须澄清，不得 hallucinate。
- Full case grading：检查采分点、易错点、估分、学习记忆是否同一份 evidence。
