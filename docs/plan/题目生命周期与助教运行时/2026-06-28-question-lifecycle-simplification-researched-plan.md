# 题目生命周期简化 — 调研充分的执行计划（先验实 premise 再动手）

> **状态**: owner 拍板"砍最大复杂源"。两份 ground truth 调研（I1 倒诬可行性 + capability fork/4状态充分性）已验实/纠正 FSM 设计的关键 premise。**本计划的每个动作 premise 都已 ground truth 验过，不再"动手才发现假设错"。** 基线 6e467b2ce。
> **为什么写这份**: 用户反馈"修了很久一直原地打转"——根因=先动手再发现 premise 错。这次反过来：premise 验实才写可执行步骤。

## 调研验实/纠正的关键结论（embedded，供执行时不再重新发现）

### ✅ 验实
- **倒诬只发生在 TutorBot 自由文本路径**（deep_question 确定性渲染路径呈现面==state_snapshot，天然不倒诬）。bot 重排在 final_response 自由生成新序，`extract_choice_result_summary_from_text`(tutorbot.py:512)**已把新序解析成结构化**，但被硬约束26**故意丢弃**（free-text 不喂 state），state_snapshot 钉死旧序。判分 `answers_match`(question_followup.py:1245)纯字母相等读 state_snapshot 旧序→学生新面 C ≠ 旧面 C =倒诬。
- **M2（object_type 拆题型/非题型）成立必要**：非题型(open_chat_topic/guide_page/study_plan)与题型在 orchestrator.py:904/turn_runtime.py:4338 等 if-链混判；抽取器对非题型返 None 非崩（静默空 fall-through）。
- **E8 套题防塌 + task#14 回指守卫本就在 turn-END/turn-START，不在 capability**——合成 capability 写回不触碰它们（安全）。

### ⚠️ 纠正（原 FSM 设计的假设错，已修正）
1. **I1 不需要新增 presented_surface 字段（原设计过度设计）**。真相：呈现面**已被解析出来**（free_text_render_summary），缺的只是"判分前把 correct_answer 投影到那个已解析的呈现面"。降级 I1 为：**判分入口无条件把 correct_answer 投影到学生提交时刻的实际呈现面，fail-safe**。复用已有 `_project_correct_answer_to_target_surface`(deep_question.py:821) + `_project_to_query_option_surface`(historical_questions.py:262)。
2. **capability fork 不是"逐行重复"（M3 premise 部分证伪）**。真相：tutorbot=**PRESENTING-only**（hardcode decision，从不判分，硬约束26 authority-gate）；deep_question=**PRESENTING+GRADING 双相位**（真 canonical decision + 判分态 `recent_outcomes` 5-滑窗 deep_question.py:4992）。合成必须**保留 deep_question 判分态特殊行为**，不是简单删重复。
3. **4 状态不够（充分性证伪）**——需补 2 维 load-bearing（非 edge）：①**套题 per-item**（一个 set object 装不下"item2 GRADED item1 未答"=E8 所在）②**open_world graded-pending**（is_correct=None 待 RAG 判=ATTEMPTED 与 GRADED 间子态）。
4. **lifecycle_state 纯派生有第六 fact 风险**：SUSPENDED/PRESENTED 可派生，GRADED 多数可，但**套题 per-item 进度派生不出**→要么 per-item 派生要么真持有=第六 fact（触 QTPK god-object 红线）。

### ❓ 仍需 live 验（执行时必做，不许跳）
- **M4(i) 唯一真实风险=解析鲁棒性**：`extract_choice_result_summary_from_text` 对 bot 真实重排文本（可能无规整 A/B/C/D 行）的解析成功率未实测。**执行 M4 前必 live dump 真实 final_response 验解析命中率**。
- **g1 T6 判分 code path**：MEMORY 记的 live 失败 turn 是否真走 answers_match（而非 construction_grading/open-world 别的分支）——否则 M4(i) 接 answers_match 够不到。**live dump 该 turn 判分 code path。**
- **M4(i) 单一汇点**：判分有多入口(deep_question.py:5636/question_followup.py:868/913/944/1225)，投影必须放**单一前置 normalizer**（answers_match 内部或唯一前置），不在 4 处打补丁（否则又打地鼠）。**执行前定位单一汇点。**

## 修正后的执行序（风险升序，每步 premise 已验，每步 live gate）

### 🥇 M4(i)：倒诬根治——判分前无条件面投影（优先做，高价值低风险）
- **为什么优先**：这是当前唯一 active SEV（误判学生），且调研证实**可行+最小+无条件**（非我失败 2 次的意图检测短路）。**直接回应"原地打转"**——这是结构修法不是补丁。
- **one fact**：判分比对的 option-letter↔value 面 = 学生提交时刻真实呈现面。
- **修法**：判分单一汇点（先定位，answers_match 前置 normalizer），当 question_context 来自 bot 文本面时，用已解析的 free_text_render_summary 当呈现面 + `_project_correct_answer_to_target_surface` 把 correct_answer 投影到呈现面再比；解析失败/值歧义→fail-safe（沿用现状保留旧字母）。**纯增量复用 4 既有函数，不加字段，不碰 state 写入，不破硬约束26（只喂判分投影非 state 语义）。**
- **为什么不会重蹈 2 次失败**：不检测意图、不短路；**无条件**在判分比对前投影，firing 点在 answers_match 紧邻（context 一定齐）。
- **gate**：①live dump 真实重排 final_response 验解析命中 ②live≥3 bot出题→对话内重排→答字母→判分对（核持久化终态非流式）③DeepSeek 异源核判分对象 ④粘贴路径 test_r1 8/8 回归不破。**单独 PR/FF 可回滚。**

### M1：显式 lifecycle_state 派生 + shadow（诊断价值，零行为）
- 在 QTPK TurnPolicyDecision 加只读 lifecycle_state 派生（题型 object_type），**含 per-item 维度 + graded-pending 子态**（调研纠正：非 4 flat 状态）。assert-only + shadow trace 对照隐式判定一致率。
- **第六 fact 风险处置**：套题 per-item 进度若派生不出，**用 per-item 派生（读 items[].construction_grading_result）不新持有**——执行时验派生输入够不够，不够则停（不强行成第六 fact）。
- **gate**：零行为，differential parity 全绿 + shadow 一致率，无需 live。

### M2：object_type 题型/非题型分流（低风险）
- 混判点(orchestrator.py:904/turn_runtime.py:4338/semantic_router.py:1370)改 family-first 分流；lifecycle_state 只在题型定义，非题型返 None。
- **gate**：回归（非题型不被误判题状态）+ 静默空 fall-through 点核查。无 live。

### M3：capability fork 写回收 turn-END 单点（中风险，必 live≥3）
- 把 tutorbot PRESENTING 写回 + deep_question PRESENTING 写回收 turn-END 单点；**保留 deep_question 判分态 recent_outcomes 滑窗 + authority-gate + 真 canonical decision vs tutorbot hardcode 的统一**（调研标这是真工作量非纯删）。
- **红线**：不碰 turn-START demote（task#14 回指 SEV-1，owner 已拒 turn_runtime.py:4266）；E8 turn-END merge 一字不动。
- **gate**：live≥3（套题判不塌/tutorbot 答完切 deep_question 身份不丢/判分态持久化终态）。

## 减复杂度量化（调研修正后）
- object_type 题状态输入 6→3（M2）✓
- capability 写回 2→1（M3，但保留判分态特殊行为，非纯删）
- 倒诬不变量从"失败的意图短路补丁"→"判分前无条件面投影结构修法"（M4i）✓
- 状态显式化（M1，含 per-item + graded-pending，比原设计 4 flat 更准）
- **相位不减**（owner 红线，task#14/E8）

## 红线（owner 已拍板 + 调研确认）
不动三相位 / 不碰 ③canonical 签发 / lifecycle_state 只读派生不成第六 fact（套题 per-item 派生不持有）/ 安全带搬迁不丢（unresolved-switch/mcq_bypass/preselect demote/submission_confidence chokepoint/E8/task#14）/ M4 不破硬约束26（只喂判分投影）/ 判分类必 live≥3 核持久化终态非流式 + 异源核。

## 预估
M4(i) 一会话（优先，倒诬根治，单独 PR + 异源核 + live≥3）；M1+M2 一会话（零/低风险）；M3 一会话（必 live≥3）。约 3 会话。**最危险=M4 解析鲁棒性（执行前 live dump 验）+ M3 capability 统一。最高价值+先做=M4(i)。**
