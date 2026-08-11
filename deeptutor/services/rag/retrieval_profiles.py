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

# 低信息真题查询锁权轮的题面供给收口（2026-08-11，live 防冒充钉 3/3 红实证）。
#
# 声明点唯一 = TutorBot `RAGAdapterTool.execute`：当本轮 runtime metadata 带
# `exact_question_blocked_reason=low_information_exam_query`（学员指代的题无法
# 锚定，exact 题目权威被 lifecycle gate 拒绝武装）且调用方未显式声明其他
# profile 时，供给边界替本轮声明「不消费题目面材料」。pipeline 在同一条管线内
# 短路：questions_bank 检索族（bank 向量、exact 文本探针、question_exact_vector
# 派生、case second pass、`exact_question` payload）与 exam 卷面 chunk 两条
# 题目面通道整轮不武装；textbook/standard 通道照常。模型手里没有任何题库题面
# /【答案】/【解析】，便无法把相似题冒充学员点名的某年某题（prompt hint 与
# in-loop sink 补丁均已被 live 证伪为非终局权威——供给层没给的东西才真正泄露不了）。
RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY = "unanchored_exam_query"


def resolve_turn_retrieval_profile(
    runtime_metadata: dict | None,
    declared_profile: str | None = "",
) -> str:
    """本轮 retrieval profile 的**唯一决策权威**（纯函数，per-turn 传参）。

    复审 F3/F4（2026-08-11）后的形态：
    - **不吃共享可变状态**——判据只来自调用点闭包里的本轮 runtime_metadata
      （RAGAdapterTool._runtime_context 会被并发轮的 _set_tool_context 覆盖，
      在那里推导 = 竞态；旧 sink 的 per-turn 传递方式是对的，材料错了但管道对）。
    - **服务端推导压过一切调用方声明**——锁权事实是 lifecycle gate 唯一写的
      数据面否决，任何 caller/model 声明的 profile 都不是逃生舱。
    - 非锁权轮调用方显式声明原样透传（案例直通身份轮），都没有返回空串 = 全量。
    """
    metadata = runtime_metadata if isinstance(runtime_metadata, dict) else {}
    if (
        str(metadata.get("exact_question_blocked_reason") or "").strip()
        == "low_information_exam_query"
    ):
        return RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY
    return str(declared_profile or "").strip()


__all__ = [
    "RETRIEVAL_PROFILE_CASE_GRADING_IDENTITY",
    "RETRIEVAL_PROFILE_UNANCHORED_EXAM_QUERY",
    "resolve_turn_retrieval_profile",
]
