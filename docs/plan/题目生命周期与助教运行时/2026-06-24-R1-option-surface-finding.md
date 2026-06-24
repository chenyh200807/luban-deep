# R1 选项重排判分 — 精确根因 + 修复点（追到底）

> 状态：**主路径已修（unit 4+202 passed，零回归）** —— `_fill_missing_mcq_authority`（题库恢复路径=g1 粘贴选项重排场景）按 VALUE 投影到学生面 + fail-safe。⏳ live≥3 未验（skill 强制，需新 context 跑 g1 序列）；grading_key/active_object 其余路径若复现再补（见下 gap 清单）。

## 一句话根因
判分时**没有题库 options**，结构上无法投影；R1 必须在**存储 grading authority 的上游**把 `correct_answer` 投影到学生当前题面后再存——投影方法已存在，只是部分存储路径没接。

## 事实链（grep + 单元复现实证）
1. 复现：`answers_match("A","D",{options:当前面5%在A})` = False（倒诬学生）；correct_answer 投影到 A 后 = True。
2. 投影需 (题库options + 题库correct_answer + 学生options) 三者同在。`answers_match` / question_followup 判分处只有学生 options → 无法投影。
3. 投影方法 `_project_mcq_exact_question_to_query_surface`（supabase.py:2487）已存在，已接在 **supabase RAG 检索(supabase.py:1089) + tutorbot loop(loop.py:2544)**。
4. **gap 路径（存题库裸字母、判分时无法补救）**：
   - `grading_key.correct_answer` lift（`deep_question.py:531 _grading_key_correct_answer`）只 lift 字母不投影。
   - `active_object` 持久化的 correct_answer（若来源未投影）。
   - 非 supabase 的 RAG pipeline（如 KB v5）若不走 1089 投影。

## 修复方向（多写者收口，非判分层补丁）
在**每个存储 grading authority 的路径**，存前调 `_project_mcq_exact_question_to_query_surface`（或 `_project_to_query_option_surface`），保证存进 grading_key/active_object 的 `correct_answer` 已是**学生当前题面字母**。判分层（answers_match）不动——它治不了本（无题库 options）。

## 验证门
- 单元：去掉 `test_r1_option_surface_grading.py` 的 xfail，转 green；补每条修复路径的投影单测。
- **live ≥3 轮**（skill 强制）：复现 g1 序列（粘贴选项重排题→作答→判分），断言答对判对。

## 红线
- 别在 answers_match 加补丁（无题库 options，治标）。
- 别新建第二套投影/识别层——复用 `_project_mcq_exact_question_to_query_surface`。
- 多路径逐个接 = 多写者收口；理想是收到"存 grading authority 必经一个投影 chokepoint"。
