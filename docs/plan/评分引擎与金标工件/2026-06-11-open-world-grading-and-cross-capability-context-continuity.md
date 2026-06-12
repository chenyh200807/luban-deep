# 开放世界判分回退 + 跨能力对话上下文连续性（系统性根因修复）

- 日期：2026-06-11
- 状态：Implemented locally（2026-06-11；两修复落地，36+3+22 项定向测试与 contract-guard 全绿，未 push）
- 触发事件：生产学员提交"我选A"被拒答"当前选择题缺少标准答案，不能稳定判分"（多次复现，
  Langfuse session `unified_1781144635640_6a9df503` / `unified_1781145921069_c4bf1b84`，
  bot `construction-exam-coach`）；以及路由从 deep_question 切到 tutorbot 后丢失前文。

## 根因（已完成四阶段调查）

### Bug 1：选择题答卷被"缺少标准答案"拒判

完整证据链：

1. TutorBot 自由文本出题（contracts/capability.md §硬约束 26）只发 rendering-only
   `presentation`，**故意不写** `question_followup_context` / `active_object`（无判分 authority）。
2. 小程序端 `chat.js _composeMcqSubmission` 把可见题卡（题干+选项，无 `correct_answer`）
   组装成 `followup_question_context` 回传，提交文案正是 `我选A`（chat.js:1894）。
3. `deep_question._recover_missing_mcq_authority` 三路兜底全失败：
   active_object 无 → grading_key 无 → questions_bank metadata 匹配不到 LLM 生成的题。
4. `_prepare_grading_context_or_emit_blocked` fail-closed，发出
   `_render_missing_mcq_authority_feedback()` 拒答（deep_question.py:878）。

系统性矛盾：出题路径允许"无 authority 的题"流向学生（presentation 缝隙），判分路径却假设
必须有 authority。底层 MCQ 内核 `grade_mcq_submission` 本来就预留了
`grading_source="llm_judge"`（"留给上游 grader agent 解析"），但 fail-closed 门把这条路堵死。
另外 `answers_match(user, "")` 返回 False，意味着绕过门后若不显式处理会把学生误判为错误/0 分。

### Bug 2：路由切换（deep_question → tutorbot）丢失对话上下文

1. TutorBot agent loop 的 LLM 历史只来自 bot-side session
   （`session.get_history`，key=bot_id+conversation_id+user_id）；其它 capability 的轮次只写
   统一 session store，不进 bot session。
2. 统一 runtime 已把跨能力 `conversation_context_text` 传进
   `UnifiedContext.metadata` → `session_metadata`（tutorbot.py:187），但 loop 里只有
   `build_continuity_anchor_instruction` 消费它，且被 `_looks_like_continuity_request`
   字面门控（用户必须说"继续/接着讲"才注入）。普通追问（如刚做完题问"为什么"）不命中 → 失忆。

## 修复方案（治本）

### Fix 1：开放世界判分回退（不拒答、不冒充题库标准答案）

依据：产品决策"不能以缺少标准答案为由拒绝判分；不回答的体验差于回答错误"；
与既有原则一致（V1 评分开放世界、编译库是弹药不是门槛；
`answer_key_authority=context_supplied_unverified` 诚实溯源链路已存在）。

改动（全部在 `deeptutor/capabilities/deep_question.py` + grader agent 渲染）：

1. `_prepare_grading_context_or_emit_blocked`：authority 缺失时不再 emit blocked；
   改为对 graded_context 应用 `_apply_open_world_grading_state`：
   - 缺 `correct_answer` 的条目：`is_correct=None`、去掉 `score`、`diagnosis="OPEN_WORLD"`；
   - 弹掉 `grading_source=="llm_judge"` 的占位 `construction_grading_result`
     （避免 grader agent 把无 authority 的 is_correct=False 当 final authority）；
   - `authority_source="open_world"` 写入 trace（`question_authority_source`）。
2. `SubmissionGraderAgent._render_question_context`：无 authoritative grading 且无
   `correct_answer` 时附加开放世界裁决指令：基于 grounding 证据+专业推理先裁决正确答案，
   明确判定学员答案并给依据；明示判分依据来源；禁止声称"题库标准答案/真题官方答案"。
3. `_emit_grading_result` 不需改流向：`_should_use_deterministic_grading_feedback` 对
   is_correct=None 自然返回 False → 走既有 RAG grounding + SubmissionGraderAgent 路径。
4. 删除死代码：`_render_missing_mcq_authority_feedback` / `_emit_missing_mcq_authority_result`
   / `_clear_blocked_grading_state`（唯一调用方是被改掉的门）。
5. `contracts/capability.md` 增补条款：判分入口不得以"缺少标准答案"拒答；无 authority 时必须
   降级为 open-world 裁决（trace 标 `question_authority_source=open_world`，
   不得声称题库标准答案）。硬约束 26/35 不变（出题侧 authority 纪律保持）。

### Fix 2：TutorBot 无条件注入跨能力对话上下文

1. `teaching_modes.py` 新增 `build_cross_capability_context_instruction(text)`：
   非空即注入（防御性截断），明示"这是同一会话内其它模式的最近对话上下文，必须延续，
   不得声称不知道前文"。
2. `loop.py` `runtime_instruction_parts` 加入该指令（不再依赖"继续/接着讲"字面匹配；
   `build_continuity_anchor_instruction` 原样保留，仍做显式延续请求的锚点强化）。

## 测试与契约

- 重写 `tests/core/test_deep_question_submission_grading.py` 中钉死拒答行为的用例
  （`test_deep_question_fail_closed_when_choice_answer_authority_missing` 等）为开放世界期望：
  不 blocked、`question_authority_source=="open_world"`、`is_correct is None`、
  响应来自 grader agent、拒答文案消失；questions_bank 可恢复时仍走确定性判分（既有用例不变）。
- `tests/services/test_tutorbot_teaching_modes.py` 增加跨能力上下文指令用例。
- `contracts/index.yaml` capability 域 `test_files` 登记
  `tests/core/test_deep_question_submission_grading.py`（deep_question.py 是 protected 文件）。
- 合并前本地跑 `check_contract_guard.py` + 相关 pytest。

## 回滚

单 commit 粒度回滚即可；无 schema/DB 变更，无 env flag。
