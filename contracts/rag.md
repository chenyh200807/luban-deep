# RAG Contract

## 范围

这一份 contract 管：

- `RAGService` 作为统一 grounding 入口
- provider / pipeline / strategy 的边界
- exact-question 命中
- authority correction 语义
- retrieval trace 字段

## 单一控制面

- 单一 RAG 入口：`deeptutor/services/rag/service.py`
- provider / pipeline 可以多实现，但必须挂在统一 RAG 入口之后
- exact-question 与 authority metadata 必须以统一字段进入上层 agent
- TutorBot 默认知识链只能由统一 runtime defaults 注入到 `tools/knowledge_bases`

## 硬约束

1. agent、router、tool 不得绕过 `RAGService` 私自直连另一个 retrieval 主入口。
2. 如果 exact-question 参与决策，必须稳定输出统一 metadata，而不是入口各写一套字段。
3. authority correction 只能建立在统一 retrieval metadata 之上，不能靠 prompt 猜测。
4. provider 可以替换，但上层消费到的语义契约必须稳定。
5. retrieval trace 命名必须统一，不得为同一语义创造平行字段。
6. 需要默认 grounding 的 TutorBot 业务身份，必须注册进统一 profile contract，而不是散落在 router 中。
7. 对于注册过的 grounded TutorBot profile，当模型本轮放弃工具时，agent 必须执行统一的 server-side RAG fallback，不能把 grounding 是否发生完全交给模型偶然发挥。
8. `exact_question` 不能再默认等同于选择题；案例题必须带 `answer_kind/case_bundle/coverage_state` 这类题型感知字段。
9. 当案例题 exact hit 只覆盖部分小问时，系统必须显式标记 partial coverage，并继续做补充检索；不能因为命中 exact 就直接跳过第二轮检索。

## 当前统一语义

- `exact_question`
- `exact_question.answer_kind`
- `exact_question.case_bundle`
- `exact_question.coverage_state`
- `authoritative_answer`
- `corrected_from`
- `knowledge_chain_profile`
- `knowledge_chain_source`

## 必测项

- `tests/services/rag/test_rag_pipelines.py`
- `tests/services/rag/test_supabase_strategy.py`
- `tests/agents/chat/test_agentic_parallel_tools.py`
