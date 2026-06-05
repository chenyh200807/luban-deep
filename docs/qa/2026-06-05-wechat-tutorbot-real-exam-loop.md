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

## Long-Run Direction

后续循环不做无头苍蝇式随机问答，而是持续围绕同一个目标收敛：微信 TutorBot 必须稳定维护四个一等事实。

1. raw user intent：学生原话到底是在要答案、提交答案、追问题目、还是要出题。
2. question object：当前题目对象、题干、选项、题卡 id、题库 exact evidence 只能有一个主事实。
3. learner answer：学生这一轮实际选了什么、答了什么、错因是什么，必须能被后续追问读取。
4. terminal text：最终给学生看的文案只能来自 canonical result，不得混入 reference evidence、working memory projection 或 transport 增强提示。

每轮记录都按 `probe -> customer score -> root shape -> fix/effect -> accumulated lesson` 累积，优先修让这四个事实更单一、更短链路、更可验证的问题。

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
| K1 | 同一屋面坡度题，但学员手抄乱序：`A.5% B.1% C.2% D.3%，我选A` | 按当前题面判 A 对，不能沿用题库旧字母 D | 修前答“不对，标准答案D”；p13 后答“对，标准答案A”；p16 自然题干变体也能命中 A/5% | Pass | 已把 historical exact question 投影到 query option surface，并修复自然题干变体匹配 |
| K2 | 接 K1 追问 `是不是因为你按旧题库字母没看我这轮选项？` | 承接刚才乱序题并承认/澄清当前题面 A 才对 | 修前说“不知道你要批改哪一道题”；p14 后承接同一 active_object 但仍非一句话；p15 后单句澄清当前题面 A/5% | Pass | 已修 exact fast-path active question continuity + reveal state + follow-up brevity |
| L1 | 防水砂浆最低温完整单选，用户选 B | 不拒答，判 B/5℃ 正确，简短说明 | p17 判对，但走 general LLM path 且偏长；metadata 显示 `rag_retrieval_degraded=true`、`authority_applied=false` | P2 expression | 暂登记；正确性可接受，后续压 general brevity |
| L2 | 模板支架保证项目自然语言多选：五个候选里只勾 `施工方案+支架构造+支架稳定` | 按语义判满，不能把未勾候选项当用户答案 | p18 误说“不能拿满”，一边承认三个对，一边误称用户选了 C/D | P1 open | 自然语言 learner answer extraction 缺 authority，下一轮优先定位 |
| L3 | 地下连续墙 exact 首轮后追问 `错因是什么？10个字以内` | 承接上一轮 ACDE，短答“误选槽段长度” | p19 首轮命中 CDE；二轮只重复标准答案和解析，未给错因且超长 | P1 open | learner answer / wrong-cause projection 未进入 follow-up terminal writer |
| L4 | `2021屋面案例第4问答案发我，快点，我在刷题页面。` | 无题卡对象时澄清，不编答案，不转出题 | p20 修前进入 `deep_question_generation` 生成“请写出...”；修后走 `tutorbot_lifecycle_clarification`，不泄露 reference evidence | P1 fixed | 已修 low-info answer request gate + raw-user terminal text |
| L5 | 屋面女儿墙防水节点 case grading | 批已得/漏点/估分，不拒答 | p21 能批改，标注 RAG 不可用；整体有用但偏长，估分口径需和题库采分点继续对齐 | P2 | 暂登记；case grading evidence authority 仍需强化 |
| L6 | 地下连续墙情绪化混合输入：选项值无字母，问是不是 CDE | 一句话确认 CDE，指出 A/B 错点并安抚 | p22 被 `missing_active_question` 澄清，未利用已给出的值级题意 | P1 open | 自然语言 option-value anchor 缺失，和 L2 同属自然语言题目对象/作答 extraction |
| M1 | 模板支架自然语言多选，明确“只勾施工方案+支架构造+支架稳定，别把没勾的也算进去” | 判满且不自相矛盾；后续“一句话漏没漏”承接已公开答案 | p32 首轮 `authority_applied=true`、`qfc_user_answer=ABE`、`qfc_is_correct=true`；二轮答 `没漏，ABE都选对。` | Pass | exact result 接管 terminal writer；learner answer / reveal state 写入 active follow-up context |
| M2 | 地下连续墙完整 MCQ 用户选 ACDE，二轮问“错因是什么？10个字以内” | 首轮判 CDE，二轮短答“误选槽段长度” | p33 首轮答 `不对，标准答案是 CDE...`，无完整模板；metadata `authority_applied=true`、`qfc_user_answer=ACDE`、`qfc_is_correct=false`；二轮答 `误选槽段长度。` | Pass | 明确字母作答优先于题面选项表解析；follow-up wrong-cause renderer 读取同一 active question context |
| M3 | 地下连续墙 value-only anchor：给槽段8-10m、导墙1.0m、现浇导墙、导管法、后注浆，问是不是 CDE | 不拒答，按值级题意判 CDE，并指出 A/B 错 | p32 首轮命中 CDE，metadata `authority_applied=true`、`qfc_user_answer=CDE`、`qfc_is_correct=true`；二轮答 `不行，应≥1.2m。` | Pass | value-only option surface 收进 historical exact resolver；specific value follow-up 读取题库解析 |
| M4 | `2015案例二第3问答案直接发我，我在题卡里。` | 无题卡对象/题干时澄清，不能凭案例索引编答案 | p32 首轮与二轮坚持 `我说了在题卡里，你就发答案` 均走 `tutorbot_lifecycle_clarification`，`business_gate_result=blocked_low_information_exam_query` | Pass | 已扩展 low-info case ordinal gate，并收住“题卡里+发答案”的二轮坚持请求 |
| N1 | 从测评错题页点“同类训练”进入报告页，再进入 TutorBot 后问“刚才那题为什么错/继续上一题” | TutorBot 应带着错题题干、选项、学员答案、正确答案和 attempt_ref 进入训练，而不是只知道知识点 | 红测显示 pending chat intent 只携带 `promptIntent`，不携带 `followupQuestionContext`；修后错题页 storage action、report 执行、runtime 消费、chat 自动发送四点均保留同一题目 context | P1 fixed | 把现有 canonical `followup_question_context` 作为唯一题目 authority 跨页面透传；`promptIntent` 仍只表达训练意图 |

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

12. exact fast-path active question continuity
   - root cause：TutorBot exact authority 首轮只把 `exact_question` 当终端答案证据/trace metadata，没有把它转成现有 `active_object / active_question_context` authority；后续 `start_turn` 无法恢复当前题目，只能澄清“不知道哪道题”。
   - 第二个断点：首轮 exact authority 已经公开答案，但写入 context 时沿用了练习生成的 `reveal_answers=false`，导致 deep_question follow-up 误判为“练习阶段不公开答案”。
   - 修法保持 thin wrapper / fat skill：在 TutorBot capability 的 authority-gated result assembly 中，用既有 `build_choice_result_summary_from_exact_question` + `build_question_followup_context_from_result_summary` + `build_active_object_from_question_context` 写入同一 active object authority；没有新增 `last_exact_question`、router、regex 或前端兜底。
   - p14 live evidence：固定账号 `qa_tutorbot_weird`，首轮 `turn_1780667305528_e39399ae2b` 返回 `对，标准答案是 A（A. 5%）...`，RESULT metadata `authority_applied=true`、`execution_path=tutorbot_exact_fast_path`、`active_object_id=historical:cf366dd4c395fffa`、`question_followup_context.reveal_answers=true`、`billing_capture=null`。
   - p14 第二轮 `turn_1780667337128_ba1588c54f` 返回 `正确答案：A（5%）...`，RESULT metadata `execution_path=deep_question_followup`、`context_question_id=historical:cf366dd4c395fffa`、`context_reveal_answers=true`、`active_object_id=historical:cf366dd4c395fffa`、`billing_capture=null`；已不再拒绝/丢上下文，但“一句话”表达仍需下一轮修。

13. exact follow-up brevity authority
   - root cause：active question follow-up 已能恢复题目对象，但 deterministic reference renderer 是最后一个 terminal writer，只读取题目 context，不读取本轮显式表达约束；同时 `response_mode` 里 active object 会先把 smart 模式升级到 deep，压过“一句话/别展开”。
   - 修法保持 thin wrapper / fat skill：把显式简短请求收敛到 `tutorbot.response_mode.looks_like_explicit_brevity_request`，`select_response_mode` 在 active object deep 前先尊重该表达约束；`deep_question` 的 deterministic reveal renderer 只消费同一 helper，不在微信、WS 或前端做截断。
   - p15 live evidence：固定账号 `qa_tutorbot_weird`，首轮 `turn_1780668293721_21ae58f4c2` 返回 `对，标准答案是 A（A. 5%）...`，RESULT metadata `authority_applied=true`、`execution_path=tutorbot_exact_fast_path`、`canonical_correct_answer=D`、`option_surface=query`、`active_object_id=historical:cf366dd4c395fffa`、`billing_capture=null`。
   - p15 第二轮 `turn_1780668322147_5b3677a8ae` 返回单句 `不是，已按你这轮题面判断，正确答案是 A（5%）。`，RESULT metadata `mode=followup`、`execution_path=deep_question_followup`、`qctx_id=historical:cf366dd4c395fffa`、`qctx_reveal_answers=true`、`active_object_id=historical:cf366dd4c395fffa`、`billing_capture=null`。

14. natural MCQ anchor after question mark + fuzzy historical stem
   - root cause 1：question lifecycle 的 free-text MCQ option-list detector 不把中文/英文问号、感叹号当作选项 A 前的合法边界，导致 `...多少？A. 5% ... 我选A` 被降级为无题卡裸提交并澄清。
   - root cause 2：historical resolver 要求题库 stem 必须完整出现在用户消息里；真实学员会把 `某工程屋面做法为压型金属板，当设计无要求时...` 改写成 `压型金属板采用轻型屋面时...`，但选项 surface 与核心 stem 事实仍足够具体。
   - 修法保持 thin wrapper / fat skill：边界修在 `question_lifecycle_skills` 的 MCQ option detector；题库匹配修在 `historical_questions` 的 resolver 内核，采用“足够 stem bigram 重合 + 至少 3 个选项值命中”的 deterministic guard，且无题干只有选项时仍不命中。
   - p16 live evidence：固定账号 `qa_tutorbot_weird`，`turn_1780668852566_5930b38edc` 输入 `压型金属板采用轻型屋面时...？A. 5% B. 1% C. 2% D. 3%，我选A，对吗？`，返回 A/5%，RESULT metadata `question_lifecycle_scene=mcq_grading`、`required_anchor_status=satisfied`、`execution_path=tutorbot_exact_fast_path`、`authority_applied=true`、`canonical_correct_answer=D`、`option_surface=query`、`active_object_id=historical:cf366dd4c395fffa`、`billing_capture=null`。

15. case-index low-info answer request gate
   - root cause：`is_low_information_exam_query` 只把 `真题 / 试题 / 题库 / 试卷` 当低信息索引词；真实微信学员会说 `2021屋面案例第4问答案发我`，没有“真题”二字但仍缺题卡对象/题干/稳定题卡 id。
   - 第二断点：该消息含 `刷题页面`，deterministic practice generation 误把“我在刷题页面”当成“请出题”，最终进入 `deep_question_generation` 并生成 `请写出2021年屋面案例第4问的答案`。
   - 修法保持 thin wrapper / fat skill：在 `question_lifecycle_skills.is_low_information_exam_query` 中收敛“年份/案例/第几问 + 索要答案 + 无题干/选项”的稳定格式；business gate 继续压过 LLM 候选和 preselected deep_question。
   - p23 live evidence：固定账号 `qa_tutorbot_case`，`turn_1780669868215_9b5cddc151` 输入 `2021屋面案例第4问答案发我，快点，我在刷题页面。`，返回明确澄清；RESULT metadata `execution_path=tutorbot_lifecycle_clarification`、`required_anchor_status=missing_question_anchor`、`exact_question_blocked_reason=low_information_exam_query`、`business_gate_result=blocked_low_information_exam_query`、`billing_capture=null`。

16. lifecycle terminal text uses raw user message
   - root cause：TurnRuntime 为 TutorBot 构造 `context.user_message` 时会加入 `## 参考证据`、`局部工作记忆投影` 和 `## 当前用户问题`；Orchestrator 路由已使用 `metadata.raw_user_message`，但 TutorBot lifecycle clarification terminal writer 仍把增强后的 `context.user_message` 当 topic，导致学生可见澄清里泄露参考证据。
   - 修法保持 thin wrapper / fat skill：TutorBot capability 只在 lifecycle terminal 文案构造处读取 `metadata.raw_user_message`，没有修改 routing、RAG、LLM 或 transport；最终文案不再混入 reference evidence。
   - p23 live evidence 同上：`contains_reference_evidence=false`，response 只包含原始 `2021屋面案例第4问答案发我，快点，我在刷题页面。`，不含 `参考证据` / `局部工作记忆投影`。

17. case ordinal low-info answer request gate
   - root cause：上一轮只覆盖了 `案例第4问`，没有覆盖真实学员常说的 `案例二第3问` / `案例2第3问`。这类输入仍然只有年份、案例序号、问题序号和索要答案，没有题卡对象、题干、选项或稳定题卡 id。
   - 第二断点：消息里出现 `我在题卡里`，但微信 start-turn 当前没有把题卡对象传入 TutorBot；general full-agent 路径把“题卡可见”当成事实，最终自信编出 2015 案例索赔答案。
   - 修法保持 thin wrapper / fat skill：继续只改 `question_lifecycle_skills.is_low_information_exam_query` 这个 lifecycle authority，扩展 case question index 的 deterministic pattern；不在 TutorBot prompt、WS、前端或 RAG fallback 里补特殊分支。
   - p24 live evidence：固定账号 `qa_tutorbot_case`，`turn_1780670805902_e1db236087` 输入 `2015案例二第3问答案直接发我，我在题卡里。`，返回明确澄清；RESULT metadata `execution_path=tutorbot_lifecycle_clarification`、`required_anchor_status=missing_question_anchor`、`exact_question_blocked_reason=low_information_exam_query`、`business_gate_result=blocked_low_information_exam_query`、`billing_capture=null`。

18. kb-first prefetched exact question authority
   - root cause：RAG provider 失败但历史题库 resolver 已返回 `exact_question` 时，kb-first 预取链路只保存候选题，没有把 forceable MCQ/free-text exact question 升级为 terminal authority，普通 TutorBot writer 仍可能抢最终正文。
   - 修法保持 thin wrapper / fat skill：在 TutorBot AgentLoop exact authority kernel 内复用同一 `build_exact_authority_response`，一旦预取 exact question 可强制 authority，就写 `authority_applied=true` 并短路普通 writer；API/微信 wrapper 不参与答案判断。
   - p32 live evidence：M1/M2/M3 首轮均 `execution_path=tutorbot_exact_fast_path`、`authority_applied=true`、`rag_retrieval_status=provider_failed_exact_question_resolved`，不再出现“先错后自纠”或“练习阶段不公开答案”。

19. learner answer 与候选项表分离
   - root cause：自然语言多选和完整 MCQ 中，解析器会从题面选项表提前读到 A/B/C/D/E，导致 `我实际选的是ACDE` 被投影成错误 learner answer，或把未勾候选项当成用户答案。
   - 修法保持 fat service authority：在 `question_followup` 中先解析明确作答短语（`我实际选的是ACDE`、`我只勾施工方案+支架构造+支架稳定`），再解析候选项值；候选项列表本身不再参与 learner answer。
   - p33 live evidence：M2 首轮 metadata `qfc_user_answer=ACDE`、`qfc_is_correct=false`；M1 首轮 metadata `qfc_user_answer=ABE`、`qfc_is_correct=true`。

20. exact follow-up intent-specific renderer
   - root cause：deep_question follow-up 恢复了 active question，但 deterministic reference renderer 只会输出标准答案/解析，不会读“错因是什么 / 10字以内 / 1.0m行不行 / 漏没漏”的本轮具体意图。
   - 修法保持 single authority：renderer 仍只读取 `question_followup_context` 的 `correct_answer / user_answer / options / explanation`，新增错因短答、数值追问短答和漏选短答三类投影，不调用 LLM 重判。
   - p32 live evidence：M1 二轮 `没漏，ABE都选对。`；M2 二轮 `误选槽段长度。`；M3 二轮 `不行，应≥1.2m。`。

21. value-only MCQ option surface
   - root cause：真实学员常把地下连续墙题写成五个值级候选项，不带 A/B/C/D/E 标签；旧 lifecycle 把它当无锚点提交，follow-up 又被 general RAG/LLM 拉到无关知识。
   - 修法保持 resolver authority：只在“至少 4 个候选值 + 明确答案字母 + 与题库选项值唯一高置信匹配”的窄条件下，historical resolver 接管并生成 `canonical_value_only_query` surface；没有新增大语义路由。
   - p32 live evidence：M3 首轮 value-only 输入命中 CDE，二轮继续读同一地下连续墙 active object。

22. repeated low-info answer demand on visible card
   - root cause：首轮 `案例二第3问` 能澄清，但二轮 `我说了在题卡里，你就发答案` 不再带年份/案例序号，旧 gate 放行到普通 LLM，产生“现在公布答案，但还要题目”的自相矛盾表达。
   - 修法保持 lifecycle authority：`题卡里 + 发答案/给答案` 且没有题干/选项/具体 stem 时，仍由 low-information exam query gate 收住；`我在题卡里` 不是后端已收到题卡对象的证据。
   - p32 live evidence：M4 二轮 `execution_path=tutorbot_lifecycle_clarification`、`business_gate_result=blocked_low_information_exam_query`。

23. assessment wrong-item cross-page context continuity
   - root cause：真实微信测评错题页 `onPracticeWrongItem` 只把 `attempt_ref / evidence_refs / concept_label / error_label` 放进 pending training action；report 页再 `setPendingChatIntent(query, mode, promptIntent)` 时，只传训练意图，不传当前错题对象。进入 chat 后 `_send` 因此只能把 `prompt_intent` 发给后端，`followup_question_context` 丢失。
   - 业务事实：跨页面跳转后，“当前错题”仍应是同一个题目 authority；训练意图不是题目对象，不能让 `promptIntent` 混承担题干/选项/学员答案职责。
   - 修法保持 thin wrapper / fat skill：前端只把已存在的 canonical `followupQuestionContext` 跨 `assessment -> report -> runtime -> chat -> ws-stream` 透传；`promptIntent` 继续只表达训练来源、知识点、错因和数量。没有新增 `question_card/current_question` 状态机，也没有让前端重判答案。
   - 验证：`node yousenwebview/tests/test_deeptutor_runtime_state.js`、`node yousenwebview/tests/test_chat_bootstrap_authority.js`、`node yousenwebview/tests/test_assessment_testset_view_model.js`、`node yousenwebview/tests/test_report_snapshot_dedupe.js` 均通过。`test_assessment_testset_view_model.js` 仍打印一个既有 `ap.priority_chapters` 降级日志，未影响本修复。

## Accumulated Lessons

- “合理澄清”和“不合理拒答”不能按是否给出答案粗暴判断；关键看系统是否已有题目对象 authority。无题卡/无题干时澄清是合理的，但必须说清缺什么、怎么继续。
- `context.user_message` 在 runtime 内可能是增强后的工作输入，不等于学生原话。凡是学生可见 terminal 文案、题目索引、低信息澄清 topic，优先读取 `metadata.raw_user_message`。
- 如果一句话里既有“刷题页面”又有“答案发我”，`刷题` 是产品场景，不是 practice generation intent；“要答案但缺题卡”应由 lifecycle gate 收住。
- 自然语言多选和情绪化混合输入不是“模型表达问题”，而是 learner answer extraction / option-value anchor 还没有单一 authority。
- `我在题卡里` 不是后端已收到题卡对象的证据。除非 start-turn metadata 里真的有题卡 id/题干/选项，否则 lifecycle gate 仍必须按低信息处理。
- 首轮终端正文公开了标准答案，就必须把 reveal state 和 learner answer / wrong-cause summary 写入同一 active object；否则下一轮会出现“刚才已公开答案，但 follow-up 又说练习阶段不公开”的伪拒答。
- `promptIntent` 只能表达“为什么来训练/练什么/练几道”，不能顺手承载题干、选项、学员答案；题目对象要走 `followupQuestionContext`，否则跨页面跳转会把两个 authority 揉在一起。
- 小程序 runtime 这种薄层可以保存待发送上下文，但只能保存 canonical 字段并在消费后清空；不要在 runtime 里解释题目、猜答案或补业务规则。

## Team Monitoring Notes

- 主代理：负责真实小程序同构链路复现、最小代码修复、测试与 scoped commit。
- 微信链路审计子代理：确认微信主链路应保持 `/api/v1/chat/start-turn` + `/api/v1/ws`，不要新增专用 TutorBot WS；同时标出 `deep_question` 外部预选和 start-turn bootstrap capability 不是最终 authority 的风险。
- 题目 authority 子代理：确认旧问题不是单题不会做，而是 exact question / active object / RAG evidence 在多个模块间投影不一致；建议把标准答案对象收敛为 canonical question context。
- 题库探针子代理：提供地下连续墙、屋面上翻高度、危大、见证取样、模板支架、抹灰等 diverse probe 池，用于后续循环。
- 后台/Langfuse 子代理：本地后端启动后可见 Langfuse trace，日志中有 `turn.runtime`、`tutorbot.runtime`、`rag.supabase.search`、`llm.stream`；当前报告仍以 WS RESULT metadata + 后端日志为主证据，Langfuse 作为辅助后台监控面。
- p17-p22 监测结论：8011 `/readyz` / `/healthz` healthy；本地 Langfuse tracer 启用并 flush；近 30 条微信 turn 全部 completed，但 `rag_retrieval_degraded` 比例高，Supabase 404/402 仍是背景风险；`billing_capture=null` 只能证明内部 QA bypass，不是生产收费闭环。
- p24-p31 监测结论：后台子代理只读确认 8011 healthy；最近 50 个 `wx_miniprogram` turn 全部 completed，`tutorbot_lifecycle_clarification=7/50`、`rag_degraded=20/50`；Langfuse adapter 日志显示启用但本地 3000/3001 health 不可达，trace linkage 仍不能当 release 证据；`billing_capture_non_null=0` 仍只说明本地 QA bypass，没有生产 wallet capture 证据。
- p34 微信前端子代理结论：真实主前端是 `yousenwebview/packageDeeptutor`；start-turn 走 canonical `/api/v1/chat/start-turn`，不是新增 mobile 专用 WS。题卡提交只有在 `extraOpts.followupQuestionContext` 存在时才会发 `followup_question_context`；`structuredSubmitContext` 当前未被 `ws-stream` 序列化，重试路径也可能只重发自然语言 query。这两点是下一轮高优先级方向。
- p34 后台观测子代理结论：Langfuse root observation 已记录 `session_id/turn_id/bot_id/interaction_profile/active_object/question_followup_context` 等关键 metadata，可以辅助定位题目对象丢失点；但 terminal `turn_event_log` / ObserverSnapshot 当前只保留摘要，不足以单独还原完整 `active_object / followup_question_context`。下一轮应补安全摘要字段如 `active_object_id`、`qfc_question_id`、`qfc_items_count`、`qfc_user_answer_present`、`qfc_is_correct`，并修正 snapshot 与 raw event 的 trace linkage 时间窗漂移。

## Open Problems

- P1：历史题库 resolver 目前是 full-MCQ vertical slice，不是生产题库总闭环。还需要把签名/可部署的题库 artifact、题卡 id、前端题面对象和 Supabase/KB source evidence 收敛成同一个 canonical question authority。
- P1：题卡 id / 当前题面对象从微信前端传进 TutorBot 仍未总闭环。测评错题训练跨页面链路已修复 `followupQuestionContext` 透传；但 AI 题卡 `structuredSubmitContext` 未序列化、题卡缺 `followupContext` 的 fallback、以及 retry 重发仍可能退化为自然语言 query。
- P2：自然语言多选 learner answer extraction 已覆盖明确作答短语，但还没有做“任意自由文本候选 + 无标准题库 exact hit”的泛化语义解析；本轮刻意不扩，避免制造第二套题目 authority。
- P2：value-only option surface 已覆盖地下连续墙这类 4+ 候选值 + 明确答案字母的窄场景；弱锚点、无答案字母、候选边界不清的输入仍应澄清。
- P2：exact MCQ 首答与 exact follow-up deterministic reveal 的一句话模板问题已修；general TutorBot LLM 路径仍可能在用户要求“一句话/别废话”时偏长，p15 负例里 general fast policy 仍输出多段解析。
- P2：p16 已修 historical resolver 对自然问句格式 `...多少？A. 5% B. 1%...我选A` 的漏识别；但还需要继续用更多自然题干变体压测，避免过宽 fuzzy match 或漏掉其他标点/换行格式。
- P2：RAG unavailable 的措辞需要更稳定：可以给候选判断，但不能说成题库标准确认。
- P2：本地 `/api/v1/wechat/mp/login` 缺 `WECHAT_MP_APP_ID/WECHAT_MP_APP_SECRET` 时返回 502；当前 QA 通过注册登录绕过，只验证 `/api/v1/chat/start-turn` + `/api/v1/ws`。
- P2：正式 billing/wallet 链路仍要单独做生产对账；本轮 bypass 只服务内部 QA，不作为真实收费链路证据。
- P2：Langfuse 本地默认未启用；若要把“拒答/降级/exact authority”纳入日常监控，需要显式启用并定义 turn-level trace 字段。
- P2：WS live probe 偶发 keepalive timeout；本次 turn 后端和 DB 都完成，但客户端未稳定收到 close/done，需要后续按 transport/replay 层单独压测。
- P2：测评页测试暴露既有 `ap.priority_chapters` 非数组时 render failed 的降级日志；本次不混修，后续可作为 assessment report robustness 单独处理。

## Next Loop Probes

- Shuffled options：同一题乱序后，答案必须按当前用户选项语义判断，不能按历史字母。
- Context object continuity：先给题卡，再连续问“为什么不是 B”“那 1.0m 对吗”，看是否读取同一个题目对象。
- Follow-up brevity：首轮 exact MCQ 命中后，连续追问“刚才那题为什么不是 X / 你是不是按旧字母了，一句话”，必须读取上一轮 exact question surface，并按显式简短约束回答。
- Missing stem：只说“2015案例5第2问答案”时必须澄清，不得 hallucinate。
- Full case grading：检查采分点、易错点、估分、学习记忆是否同一份 evidence。
- Natural learner answer：不用 ABCDE，只说“我勾了施工方案+支架构造+支架稳定”，系统必须提取实际学员答案，而不是把候选项列表全当作已选。
- Value-only MCQ anchor：给出 `槽段8-10m、导墙1.0m、现浇导墙...我是不是CDE` 时，系统应识别足够题意并按题库值锚定，不应直接澄清缺题。
- Structured submit serialization：AI 题卡作答时，如果 `structuredSubmitContext` 已经有 questions/answers，但 `followupContext` 缺失，不能让它死在前端边界；要决定是删除这条半成品，还是收敛进 `followup_question_context.items`。
- Retry continuity：对题卡判题轮点击重试时，应恢复同一 `followupQuestionContext`，不能只重发用户文本。
