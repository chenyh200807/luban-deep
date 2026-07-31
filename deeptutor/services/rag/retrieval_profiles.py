"""Retrieval-depth profiles — the single naming authority for `retrieval_profile`.

一个 profile 只声明「这一轮的调用方消费什么」，不声明第二条检索入口：统一
`RAGService` → pipeline 依旧是唯一 grounding 入口（contracts/rag.md §单一控制面），
pipeline 在**同一条管线内**按 profile 短路，不分叉出平行检索函数。

常量单独成模块（而不是挂在 `pipelines/supabase.py` 上），是为了让 TutorBot
agent loop 能在模块顶层引用它，而不必把 Supabase pipeline 提前拉进 import 图
——loop.py 对该 pipeline 一直是函数内惰性 import。
"""

from __future__ import annotations

# 案例判分直通轮的身份检索（L1 瘦身检索，2026-08-01）。
#
# 调用方（`AgentLoop._run_case_grading_direct`）只消费 `exact_question`：
# 题目身份 + `covered_subquestions` / `covered_indexes`（判分分母）。检索正文与
# `sources` 在该轮被穷举证实零消费者——直通轮不传 on_tool_call/on_tool_result，
# 正文只会落进 `role:tool` 消息，而 `session/manager.stable_messages()` 丢弃一切
# 非 user/assistant 角色、永不回放；fell-through 后外层重建 messages 且幂等闸拦住
# 二次 prefetch，正文整块弃置。
#
# 该 profile 裁剪的只是**产物加工**：全文水合、rerank、doc 多样性、ranking trace、
# 正文拼装、source_items、questions_bank 以外的 source 检索。
# 必须保留的身份/分母命脉（砍任何一条都会让 tier3 回落或 P0 满分病复发）：
#   ① exact 文本探针 `_search_exact_question_text_batch`
#   ② `_search_questions` bank 向量检索 + 由它客户端派生的 `question_exact_vector`
#   ③ case_like 强制 second pass（`covered_subquestions` 的主要来源 = 判分分母）
#   ④ `_extract_exact_question_payload` / `_augment_case_exact_question_with_query`
#      / `_project_mcq_exact_question_to_query_surface` 三件套
RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY = "case_grading_identity"

__all__ = ["RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY"]
