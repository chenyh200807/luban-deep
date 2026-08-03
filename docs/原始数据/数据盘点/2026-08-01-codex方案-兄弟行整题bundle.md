# 兄弟行整题 bundle：只读代码测绘、方案评估与可证伪切片

- 日期：2026-08-01
- 调查方式：只读当前 checkout、只读 `origin/main`、既有只读生产审计档案；未执行数据库写入、git 写入或代码修改。
- 代码基线：当前 `HEAD=8cdbacb35d9dd176dbb74fb811d9d3676167daf1`；调查时 `origin/main=27d9165a308d8dd248b8562af176643bf42a16f0`。当前 HEAD 是 origin/main 的祖先；两者在本文涉及的评分修复代码上没有差异，origin/main 另多两份文档。
- 数据证据边界：本进程没有 `DB_URL` / `QUESTIONS_BANK_DB_URL` / Supabase key，无法重跑 live SELECT。下文数据分布引用仓库内 2026-07-30 的只读 Supabase 审计快照；它是 E3 历史证据，不冒充 2026-08-01 当前实时快照。用户给出的“46 处跨年冲突”已被该快照独立核到 46 处（`docs/原始数据/数据盘点/2026-07-30-复合qid唯一性与E索引权威审计.md:56-59`）。
- 总裁决：**“方案 A：命中后按 `source_chunk_id + exam_year` 回查兄弟行”在当前数据上 NO-GO，不应直接实现。** 不是查询代码难写，而是 join 前提不成立：可建键的 354 条 case 行按这两个字段分组时 354 组、零个多行组；真正的后续小问大量 `source_chunk_id` 为 NULL 或各自拥有不同 chunk。推荐先落显式 `case_group_id + subquestion_index`（本文方案 C），再复用 A 的“命中一行后按组取全量”运行时形态。若 owner 仍要 A，只能作为 fail-closed 实验切片，必须先让指定生产家族通过组键数据前置断言。

## 1. 现状测绘

### 1.1 `questions_bank` 的行粒度与相关字段

RAG 对 `questions_bank` 的投影列在 `_QUESTION_SELECT` 中明确列出：`id, original_id, question_type, stem, question_stem, options, correct_answer, analysis, grading_keywords, grading_rubric, option_reasoning, node_code, source_type, exam_year, background_context, parent_id, source_chunk_id, structured_rules, logic_rule`（`deeptutor/services/rag/pipelines/supabase.py:54-59`）。归一化后，题干来自 `stem/question_stem`，答案来自 `correct_answer`，年份暂时投到普通结果的 `page_num`，并透传 `parent_id/source_chunk_id`（`deeptutor/services/rag/pipelines/supabase.py:2438-2476`）。

案例题的实际粒度不是“一行一整题”，而是“一行一个小问答案钥匙”。生产家族 17371–17374 分别对应问题 1–4，9559 是问题 1 的污染重复行；该事实来自真实入口验证档案 `origin/main:docs/原始数据/数据盘点/2026-08-01-P0关闭验证与宣传门扩场景.md:73-87`。代码没有读取一个持久化 `display_index` 列；它从每行 `stem/question_stem` 文本解析第 N 问（`deeptutor/services/rag/pipelines/supabase.py:2704-2719`），所以 `display_index` 是运行时投影，不是数据库 authority。

数据库字段是否存在的证据边界如下：

| 候选字段 | 代码/数据事实 | 能否作为兄弟组键 |
| --- | --- | --- |
| `source_chunk_id` | 被查询与透传（`supabase.py:54-59,2469-2471`）；只读快照中 1961 条 case 里 945 条为 NULL（`2026-07-30-复合qid唯一性与E索引权威审计.md:49-54`） | **不能单独用**；NULL 覆盖差，且它是文档内局部编号，不跨文档唯一（`2026-07-30-questions_bank系统污染盘点与分批清洗计划.md:263-269`） |
| `exam_year + source_chunk_id` | 可消除已知 46 处跨年碰撞；但 354 条可建键 case 行得到 354 个组，组大小全部为 1（`2026-07-30-复合qid唯一性与E索引权威审计.md:56-59`） | **当前不能找兄弟**；“唯一”来自兄弟行丢 chunk，而非组键正确 |
| `parent_id` | RAG 只透传（`supabase.py:2467-2471`），全表 4635 行快照全部 NULL（`2026-07-30-questions_bank系统污染盘点与分批清洗计划.md:275-280`） | **不可用** |
| `display_index` | 从题干正则解析、临时写 `_display_index`（`supabase.py:2704-2719`）；数据库没有 `subquestion_index` authority（`2026-07-30-复合qid唯一性与E索引权威审计.md:136-139`） | 只能排组内顺序，不能回答“属于哪道题” |
| `original_id` | 在列投影和归一化里存在（`supabase.py:54-58,2451-2453`） | 本轮未找到任何按它聚合兄弟行的生产代码，也没有数据分布查询，**未验证，不得假定可用** |
| `background_context` | 被选取但没有进入归一化返回体（选择列见 `supabase.py:54-59`，归一化返回见 `:2450-2476`） | 文本可能共享，但未核唯一性/规范化；不能直接当 identity |

更强的反证是：64 个能按 `(exam_year, source_chunk_id)` 对上原始案例的组，每组只有第 1 问那一行；第 2–N 问确实存在，但 chunk 为 NULL。另一些真实兄弟小问各自有独立 chunk（`...P0019_01 / ...P0020_02 / ...P0017_01`），不能把首行 chunk 机械复制给它们（`2026-07-30-复合qid唯一性与E索引权威审计.md:81-101`；`2026-07-30-questions_bank系统污染盘点与分批清洗计划.md:275-280`）。

### 1.2 四个 coverage/bundle 概念的完整运行时数据流

主链如下：

1. TutorBot 的案例直批先把整段提交切成 `_probe_stem` 与 `_probe_answer`，调用 RAG 时用 `tool_query_override=_probe_stem`（`deeptutor/tutorbot/agent/loop.py:2284-2313`）；覆写最终落到 RAG tool 的 `preview_args["query"]`（`loop.py:3306-3346`）。
2. Supabase pipeline 用该 query 做形状分类和小问解析（`deeptutor/services/rag/pipelines/supabase.py:840-907`），并从 exact-text、exact-vector、普通 `questions_bank` 计划收集案例候选（`supabase.py:2598-2699`）。
3. **构造点一**：候选行先按“解析出的 `display_index`，否则 prompt”去重；同 key 只留相似度较高行，再按序号/相似度排序（`supabase.py:2701-2726`）。这里会改写候选集合：`seen_by_index` 是一次 dedup，且 key 中没有题级 group identity。
4. `selected_row = ordered_rows[0]` 在 `supabase.py:2727`。它决定顶层 `id/question_id/source_chunk_id/exam_year/stem/correct_answer/analysis/options`（`supabase.py:2740-2766`）。因此“第一行”确实决定 tier-2 顶层参考钥匙；但需精确补充：`covered_subquestions` 并非只含第一行，而是对当轮已召回的全部 `ordered_rows` 逐行构造（`supabase.py:2728-2739`）。当候选只召回一行时 bundle 才退化成单问；候选召回多行时 bundle 可多问，但仍不保证同题。
5. **构造点二**：顶层 `covered_subquestions`、`covered_indexes`、`coverage_state` 与嵌套 `case_bundle` 同时写入（`supabase.py:2766-2775`）。非多候选路径会由 `_build_case_authority_bundle` 只取解析出的第一个小问，写 `single_subquestion_only`（`supabase.py:2492-2524`），再投到 payload（`supabase.py:2778-2821`）。
6. **构造/改写点三**：`_augment_case_exact_question_with_query` 从学生 query 再解析 `query_subquestions`，按 `display_index` 与 `covered_subquestions` 对账，原地写 `query_subquestion_count/missing_subquestions/coverage_ratio/coverage_state`，并同步改写嵌套 `case_bundle` 的这些字段（`supabase.py:3057-3113`）。`coverage_state` 因而不是静态入库字段，而是“召回候选集合 × 本轮 query 小问集合”的派生状态。
7. pipeline 把 exact payload 写进 evidence bundle（`supabase.py:1151-1165,1239-1245`）；RAG tool 直接把 `result["exact_question"]` 放进 `_last_trace_metadata`（`deeptutor/tutorbot/agent/tools/deeptutor_tools.py:183-216`）。`consume_trace_metadata()` 只是浅拷贝字典并清空 slot（`deeptutor_tools.py:249-252`），未发现序列化展开/增加小问。
8. TutorBot prefetch 取出 `merged_metadata["exact_question"]`，写 `runtime_metadata["_prefetched_exact_question"]`（`loop.py:3361-3408`）。这里仅 MCQ 会做 option-surface 投影；case payload 不经过该投影的改写分支（`loop.py:3384-3399`；MCQ gate 在 `supabase.py:2839-2843`）。
9. **消费点一（权威可用性）**：`case_bundle` 或 `covered_subquestions` 中只要存在答案证据，就被认定为案例判分 authority（`deeptutor/services/construction_grading/case_output_policy.py:141-170`）。
10. **消费/过滤点二（真正进入判分的参考）**：`_current_case_reference_from_context` 不直接吃全部 bundle；它拿 `user_stem` 与每项 `question/question_stem/stem/surface/prompt` 做 containment 匹配，只拼接匹配项的答案并产出 `matched_indexes`（`loop.py:1564-1663`）。这就是“payload 说 4 行，但实际采纳可能 1 问”的第二道集合变换。
11. `_build_v1_case_ctx` 从 `_prefetched_exact_question` 读取 `covered_subquestions`（`loop.py:1665-1756`），把实际采纳的 `matched_indexes` 优先作为覆盖分子；为空才回退顶层 `covered_indexes`（`loop.py:1824-1842`）。它把 `case_reference_covered_count` 和从学生题面解析出的 `case_stem_subquestion_count` 写入评分 ctx（`loop.py:1844-1858`）。
12. **消费点三（评分通道与缩放）**：共享评分核先按 qid 查 compiled rubric（tier-1）；无 points 且有 `correct_answer/reference` 时走 tier-2 `on_the_fly_reference`，无 reference 但有 stem 时走 tier-3 `derived_from_stem`（`deeptutor/capabilities/deep_question.py:2474-2537,2537-2579`）。tier-2 用 `covered_count / stem_subquestion_count` 缩放点池，并写 `partial_scope`（`deep_question.py:2546-2558,2684-2699`）。
13. **其他消费者**：`extract_exact_question_authority_from_metadata` 优先用 `case_bundle.covered_subquestions/coverage_state` 归一化案例 authority（`deeptutor/services/rag/exact_authority.py:86-126`）；Chat pipeline 把覆盖/缺失小问拼进模型合同（`deeptutor/agents/chat/agentic_pipeline.py:2317-2385`）；案例直出渲染遍历 `covered_subquestions`（`exact_authority.py:546-572`）；benchmark 要求所有 covered answer 出现在回复中（`deeptutor/services/benchmark/quality_scoring.py:55-83`）。`covered_indexes` 的生产评分决策消费者是上述 `loop.py:1831-1852`；agentic pipeline 另把它作为 trace 摘要输出（`agentic_pipeline.py:3344-3360`）。

### 1.3 当前集合改写点与“幽灵小问”边界

已找到的明确集合/题面变换有四处：

- RAG 的 `extract_case_subquestion_items` 会按正则切小问，并用 `if item not in items` 去重（`deeptutor/services/rag/pipelines/supabase_strategy.py:634-662`）。
- exact payload 会按 `display_index/prompt` 去重候选行（`supabase.py:2701-2726`）。
- `_augment_case_exact_question_with_query` 会原地重算 query/coverage 集合（`supabase.py:3057-3113`）。
- `_current_case_reference_from_context` 会按 `user_stem` 过滤实际采纳的参考项（`loop.py:1564-1663`）。

评分分母并不读取 `case_bundle.query_subquestion_count`，而是 `_extract_case_question_titles_for_scope()` 调用 rubric 核的 `_extract_case_question_titles()`（`loop.py:91-100,1842-1852`）。该函数先截取第一个 `【问题】` 后的文本，再按统一作答 marker 切掉作答区，最后把行首“第 N 问 / 问题 N / (N) / N.”收进以 N 为 key 的 dict（`deeptutor/services/construction_grading/rubric_grader_v1.py:589-624`）。代码注释明确记录过：作答切割失败时，作答里的编号会被数成幽灵问题 5/6（`rubric_grader_v1.py:593-602`）。

但是，本次只读测绘**没有找到**一个能解释“同一存档文本离线=4、真实运行稳定=5”的确定改写点。`msg.content` 在 AgentLoop 入口直接成为 `current_message`，`raw_user_message` 只用于持久化，不替换它（`loop.py:4399-4401`）；RAG payload 的上述变换也不会改 `user_stem`。生产档案已排除本地/容器函数源码差异，并指出只有在计数器收到“不含 `【问题】`、仍含背景编号列表”的 surface 时才可能稳定数出 5（`origin/main:docs/原始数据/数据盘点/2026-08-01-P0关闭验证与宣传门扩场景.md:110-123`）。因此诚实结论是：**未在只读测绘范围内定位到题面在计数器之前被改写的确定位置，需要逐跳运行时插桩确认；不能把上述任一可疑点直接宣布为根因。**

## 2. 方案 A（推荐候选）的评估

方案 A 的运行时形态合理：先用现有 exact identity 命中 seed，再以稳定 group key 取完整组；问题是当前提议的 group key 不是 group key。

### 2.1 可行性与唯一性

**当前数据上不可行。** `(exam_year, source_chunk_id)` 解决的是“同一局部 chunk 跨年份碰撞”，不能表达“同一案例的多个小问”。历史只读快照显示：

- 1961 条 case 中 `source_chunk_id IS NULL` 945 条，`exam_year IS NULL` 1290 条，任一缺失而不能建键的共 1607 条（`2026-07-30-复合qid唯一性与E索引权威审计.md:49-54`）。
- 可建键的 354 行得到 354 个 `(year, chunk)` 组，没有一个多行 case 组（同文件 `:56-59`）。
- 64 个能回查到源案例的组，每组只有首问；后续问的 chunk 为 NULL，或拥有独立 chunk（同文件 `:81-101`）。

所以按 A 查询，最常见结果不是“4 个兄弟”，而是“仍然只有 seed 这一行”；NULL 时则连安全查询都不能发。A 只有在先完成数据 backfill、让真实兄弟共享一个**题级**键后才成立；那个键不应复用当前**小问/文档片段级** `source_chunk_id`。

### 2.2 性能

若未来有可靠 group key，额外一次 PostgREST SELECT 的网络 RTT 和 JSON 解析是主要成本；每组通常 4–6 行，行数本身很小。当前 exact-text 已对 `question_stem` 与 `stem` 各发一个 SELECT 并并行（`supabase.py:2213-2233`），普通题库检索走 `search_questions_bank_vector/text` RPC（`supabase.py:2260-2278,2346-2357`）。组回查既没有被这些 RPC 保证返回，也没有现成 group lookup 可直接合并，因此“零额外查询”目前不成立。

本仓未找到 `questions_bank(exam_year, source_chunk_id)` 的迁移或索引定义；没有 live `pg_indexes` 权限，本轮**未验证生产是否有复合索引**。没有索引时每个 exact turn 可能触发全表过滤。上线前必须只读核 `pg_indexes`；若缺索引，应使用 case partial composite index，而不是接受表扫。若改 RPC 让 seed 与 siblings 同次返回，可省 RTT，但那会扩大数据库函数改动和回滚面，不适合作为最小切片。

### 2.3 命中随机性是否消失

必须分两种随机性：

1. **seed 行随机、group 正确且完整**：若任何 seed 都映射到同一个稳定 group，回查结果按显式 `subquestion_index,id` 排序，bundle 内容与 seed 无关，则“抽到 17371 还是 9559”不会改变参考集合；这部分随机性可以消失。
2. **当前 A 的真实数据**：不同 seed 的 `(year, source_chunk_id)` 是 NULL、不同值或污染重复值，回查集合仍不同；随机性不会消失，只是从“top-k 抽行”搬到“错误 group key”。

此外，当前 payload 在所有 candidate plan 之间仅按 `display_index` 去重，没有题级隔离（`supabase.py:2693-2726`）。若不同案例的“问题 1”同时入候选，较高 similarity 会夺位。A 若只在 payload 组装后补查，必须先锁定 seed group，再丢弃组外 candidate；把回查行与现有 `ordered_rows` 无条件 union 会保留污染面。

### 2.4 identity 闸副作用

风险比表面更高：`exact_question_identity_corresponds` 虽是 MCQ/计算题的唯一 identity adjudicator（`deeptutor/services/rag/pipelines/supabase_strategy.py:954-997`），但对 case 类型当前直接 `return True`，注释写明 case identity 收权推迟（同文件 `:999-1003`）。也就是说，案例 seed 本身没有强 identity 闸；若再用弱 group key扩展成整题，单个假命中会获得 4–6 行官方答案，错误 authority 的爆炸半径变大。

因此 A/A' 的硬门应是：seed 通过可证伪的 case identity；group key 非空；查询行全部 `question_type=case_study`、同 group、`subquestion_index` 唯一且在合理范围；重复 index/超组大小/跨 source 时 fail closed 回原单行止血路径并发 authority marker。不得把“查到多行”本身当 identity 证明。

### 2.5 对 MCQ 零影响的条件证明

当前代码天然分层：只有 `question_type` 含 `case` 的行会进入 `case_rows` 聚合（`supabase.py:2693-2700`）；MCQ 走 `selected_plan/results[0]` 的非 case payload（`supabase.py:2778-2821`），并且 option surface 投影有明确 `answer_kind == "mcq"` 门（`supabase.py:2823-2882`）。

所以只要 sibling hydration helper 同时满足：入口 `answer_kind == case_study`；查询硬过滤 `question_type=eq.case_study`；返回继续走现有 case bundle builder；不改 `_project_mcq_exact_question_to_query_surface`，MCQ 路径可做到代码级隔离。验收还必须运行既有 MCQ type-consistency 测试（`tests/services/rag/test_exact_authority_type_consistency.py:54` 附近）和 option projection 测试；“理论上有 if”不等于零回归证据。

### 2.6 新生产实证①：tier 随作答变化

**A 不足以根治，且以当前键实现时连稳定 bundle 都得不到。** tier 的直接裁决在共享评分核：有 compiled qid → tier-1；否则有 reference → tier-2；否则有 stem → tier-3（`deep_question.py:2492-2579`）。学生答案 `answer` 在这里用于后续 judge，不直接参与 tier if/else（`deep_question.py:2483-2491,2645-2647`）。

当前 origin/main 的案例直批也已经显式只把 `_probe_stem` 喂给 RAG（`loop.py:2303-2313`），RAG 侧看到的 query override 在 `loop.py:3337-3346`。因此静态源码不支持“当前直批 RAG 明确把 learner answer 作为 query”的断言。

仍然存在两个真实的作答依赖面：

- lifecycle 决策读取整段 `ctx.user_message`（`deeptutor/services/question_lifecycle_skills.py:246-350,1215-1315`）；确定性规则未命中时，LLM scene proposal 也把完整 `user_message` 放进 prompt（同文件 `:1606-1665`）。scene 是否为 `case_grading` 决定直批及其 prefetch 是否执行（`loop.py:1889-1899,2255-2268`）。
- `_split_full_case_answer_submission_components` 收集题面之后的所有作答 marker，并用**最后一个 marker**切 stem/answer（`question_lifecycle_skills.py:1550-1568`）。如果作答正文自身又出现“答案：/作答：”，换作答内容会改变 `_probe_stem`，继而改变检索。当前生产样本是否命中此形状，本轮没有原始 payload 可逐字验证。

这两处是需要插桩的候选，不是已证实根因。生产 9 轮 tier-3 与 4 轮 tier-2 的现象、且题面 diff 为空，记录于 `origin/main:docs/原始数据/数据盘点/2026-08-01-P0关闭验证与宣传门扩场景.md:65-70,89-119`；现有静态链无法唯一解释。结论必须是：**未定位到确定根因，需要运行时逐跳插桩；方案 A 最多在“已经 exact 命中且 group 正确”后稳定 reference，不能修 scene 选择、切割或 RAG query 泄漏。**

最小插桩应同一 turn 导出不可逆 hash/长度而非全文：`raw_user_message`、`msg.content/current_message`、split 后 stem/answer、`preview_args.query`、RAG service `query`、exact candidate ids、最终 `ctx.correct_answer`、`rubric_provenance`。判据是同题面两份不同答案从 split-stem hash 到 RAG-query hash必须逐跳相同；第一次分叉就是根因层。

## 3. 方案 B、方案 C及取舍对比

### 方案 B：读取时对现有召回候选做后置合并

不额外查 DB，沿用当前 `case_rows → seen_by_index → ordered_rows`，但增加题级一致性过滤，例如共同背景 hash/来源元数据，再生成 bundle。优点是无 schema 变更、无额外 RTT；缺点是 top-k 没召回的兄弟永远补不回来，且当前行上没有已验证可靠的共同题级字段。它只能减少误混，不能保证整题完整。

### 方案 C：新增显式 `case_group_id + subquestion_index`，回源回填（推荐）

从原始年度真题的一道 case / `exercises[]` authority 生成稳定 `case_group_id`，每个小问落 0-based 或 1-based、全链统一的 `subquestion_index`。运行时命中任意行后按 `case_group_id` 一次取全组，按显式 index 排序。`source_chunk_id` 继续表达源 chunk，不再被迫兼任题级 parent。该方案需要 schema 与一次性数据回填，但它修的是一等事实：“这些小问属于哪一道题、顺序是什么”。

### 方案 D：写入时改成一行整题，冗余 `subquestions[]` JSON

重新入库时不按小问拆行：题面、答案、rubric 以一个 versioned bundle 存储，小问作为数组元素；旧行保留只读兼容或迁移后退役。读取最简单、不会二次 group query，但会影响 assessment、检索 embedding、历史 question_id 引用、去重和内容治理；迁移面最大。

| 方案 | 可行性 | 改动范围 | 主要风险 | 性能 | 数据回填 | 能否根治随机 reference |
| --- | --- | --- | --- | --- | --- | --- |
| A：`year + source_chunk_id` 回查 | **当前 NO-GO** | RAG pipeline + 可选索引 | join 前提错误；NULL；弱 identity 扩权 | 多 1 RTT；索引未知 | 若不回填则无效 | 否 |
| B：候选后置合并 | 中低 | RAG payload 组装 | top-k 漏兄弟；无可靠题级键；污染混入 | 最低，无额外查询 | 否 | 只能缓解 |
| C：显式 `case_group_id + subquestion_index` | **高，推荐** | schema、入库/回填、RAG query、契约测试 | 回填错组；新旧双读期 authority 分裂 | 多 1 个小查询，可索引；稳定 | **是** | 是，前提是回填与 identity 闸通过 |
| D：整题单行 + subquestions JSON | 中 | 入库、检索、assessment、引用迁移 | question_id/下游引用大迁移，回滚复杂 | 读取最好；embedding 体积变大 | **是，重** | 是 |

最终推荐 C，不推荐把 A 的字段组合直接上线。C 完成后，运行时实现可复用 A 的控制流，因此不是否定“命中后组装 bundle”，而是先把错误 join key 换成真正的题级 authority。

## 4. 风险清单

1. **跨年 chunk 冲突（已知 46 处）**：只用 `source_chunk_id` 必然跨年混题。加 `exam_year` 能规避本次已核的 46 处（全表 46、case 16，`2026-07-30-复合qid唯一性与E索引权威审计.md:56-68`），但仍没有证明同年同 chunk 是“同一道案例的兄弟”。设计上至少要锁 `(source_document_id, exam_year, case_group_id)`；`exam_year` 只能是 namespace，不是 parent identity。
2. **`source_chunk_id IS NULL`**：A 必须 fail closed，不得发 `eq.null` 式宽查询，也不得按 year 拉全年度。退化行为应保留现有单行/候选 bundle和已上线比例缩放，并写 `case_bundle_hydration="skipped:null_group_key"` marker；它不会彻底失败，但仍是“局部参考、非官方分”。快照里 945/1961 case 为 NULL，故这不是边角路径（同文件 `:49-54`）。
3. **污染行混入**：17371 与 9559 已是问题 1 重复；当前 `seen_by_index` 会按 similarity 只留一个（`supabase.py:2701-2719`），但没有内容 hash/authority/version 裁决。若 group key 过宽，不同案例相同 index 会互相夺位，随后被 case identity 的无条件放行放大。组装前必须断言 group 全同源、index 唯一；同 index 多行若答案 hash 不同应整体 fail closed，而不是任选高 similarity。
4. **`parent_id` 假后路**：全 NULL 快照说明不能“改用 parent_id 就好”。若未来回填，应定义它是 self-parent、root row id 还是稳定外部 id；直接用可删除的 row id 会把物理行当业务 identity。
5. **聚合后 coverage 变 4/4 与止血缩放**：如果完整 bundle 的 4 个答案都被 `_current_case_reference_from_context` 实际采纳，`case_reference_covered_count=4`、题面计数=4，缩放系数 1 是正确结果——完整参考本就不应扣覆盖分（`loop.py:1831-1852`; `deep_question.py:2546-2558`）。但不能把“DB 查回 4 行”直接当 4/4：当前修复已明确优先采用 `matched_indexes`，只在采纳集为空时回退 payload `covered_indexes`（`loop.py:1831-1841`）。若污染 bundle 恰好凑齐 index 1–4，ratio=1 会把错误隐藏成 full coverage。因此验收必须同时断言“实际进入 reference 的 answer hashes 与 group 的 4 个 authority answers 一一对应”，不能只看 ratio。
6. **覆盖状态与评分覆盖不是同一事实**：RAG `coverage_state` 按召回行 index 算（`supabase.py:3080-3112`）；评分缩放按实际采纳 indexes 算（`loop.py:1831-1852`）；渲染层又从 scoring points 推 `case_subq_coverage`（`rubric_grader_v1.py:671-707`）。三者分母/分子不同。整题 bundle 修复后如果只让其中一个变绿，仍会出现“metadata 4/4、渲染仅问1”分裂。
7. **缓存与陈旧 bundle**：rubric cache key 包含 reference 与 stem hash，缓存值是 scoring points 深拷贝（`rubric_grader_v1.py:80-117`）；完整 reference 会自然生成新 key，不会复用旧单问 points。但 RAG/HTTP 上游是否有 CDN/PostgREST 缓存，本轮未验证；上线需在 trace 中导出 bundle group/version/hash，不能只看 question_id。
8. **索引与放大查询**：未核生产 composite index。extra SELECT 若无索引会把每个案例提交变成表扫；错误的 NULL/fuzzy fallback 更会成为大范围数据外泄面。禁止 `ilike background_context` 作为生产 fallback。
9. **tier 翻转不会被 A 自动证明消失**：A 只在 exact hit 后执行；gold v2 那 9 轮 tier-3 若根本没有 exact payload，A 没有触发机会。必须把“RAG query hash 与答案无关”作为独立 gate。
10. **幽灵小问不会被 bundle 自动修好**：最终分母来自 `user_stem` 标题解析，不来自 bundle（`loop.py:1842-1852`）。即使 reference 完整，运行时 surface 若仍丢 `【问题】`，4/5 仍可发生，甚至用错误 ratio 把完整参考降权。

## 5. 最小可验证切片与可证伪验收判据

### 5.1 最小切片（验证 A，不宣称可上线）

目的不是先写完整框架，而是用一个 fail-closed spike 证伪/证实“指定家族是否真的能被 `(exam_year, source_chunk_id)` 取全”。

1. 在 `deeptutor/services/rag/pipelines/supabase.py:2171-2258` 附近新增一个私有只读 helper，例如 `_search_case_sibling_rows(client, seed, config)`：仅当 seed `question_type` 是 case、year/chunk 都非空时，SELECT `_QUESTION_SELECT`，过滤 `question_type=eq.case_study AND exam_year=eq.<year> AND source_chunk_id=eq.<chunk>`，limit 8；NULL/超限/HTTP 错误返回空并写降级 marker。
2. 在 `supabase.py:1151-1164` 的 exact payload 构造后、写 evidence bundle 前调用 hydration；只有查询结果通过“同 key、唯一 display index、组大小 2–8、无答案冲突”时，才用**同一套** `covered_subquestions/case_bundle` builder 替换 seed 的局部 bundle。不得另写第二套答案抽取规则。
3. 第一刀不改 schema、不改 RPC、不改 MCQ、不删现有比例缩放。其上线前置不是单测绿，而是指定生产家族的只读 SQL 先返回 4 个有效兄弟；按当前历史快照，这个前置预计会红，从而证伪 A 的数据假设。

由于 A 当前数据前提为假，这个切片最多是 `experiment/no-rollout`。若前置 SQL 红，停止编码并转方案 C；不要为了让测试绿而退化到 `background_context ILIKE`、相似度聚组或把首行 chunk 复制给兄弟。

### 5.2 origin/main 红、修复后绿的测试设计

测试文件：`tests/services/rag/test_rag_pipelines.py`，紧邻现有单问与多候选案例测试（现有单问断言在 `:1680-1759`，多候选 covered indexes 断言在 `:1940-2020`）。

测试大意：

- fake `_run_query_plan` 只返回随机 seed 中的一行，且 seed 带同一 `exam_year/source_chunk_id`；fake PostgREST group SELECT 返回 4 行，顺序每次打乱，display index 为 1–4、答案分别 A1–A4。
- 调用公开 `pipeline.search()`，不直接测私有 builder。
- 断言最终 `covered_indexes == ["1","2","3","4"]`、四个 `authoritative_answer` 都在、`matched_question_ids` 恰为四行、`coverage_state == multi_subquestion_exact`、`case_bundle.raw_subquestion_count == 4`。
- 参数化 seed 为第 1/2/4 行，并打乱 group 返回顺序；三次结果剔除 seed id 后仍应具有相同 bundle hash，证明输出与初始命中行无关。
- 再放一个 MCQ seed，断言 sibling SELECT 调用次数为 0，MCQ payload/correct_answer 与基线逐字相同。
- 放 NULL key、重复 index 且答案冲突、超过 8 行三组反例，均断言 fail closed 到原单行 bundle并有 marker，绝不任选或扩权。

为什么它在当前 origin/main 必红：当前 pipeline 没有 group hydration 调用，payload 只从 `all_plans` 中已有的 `case_rows` 构造（`supabase.py:2693-2739`）。当 fake plan 只供 1 个 seed 时，现代码必得 `covered_indexes=[seed_index]` 与 `single_subquestion_only`（`supabase.py:2766-2775`），不可能凭 fake group SELECT 得到四行。因此红不是人为 `xfail`，而是公开行为断言击中缺失能力。

### 5.3 数据前置、自动化与真实入口验收

可证伪判据按层分开：

**数据前置（不满足即 A 判死，不进入发布）：**

```sql
select exam_year, source_chunk_id,
       count(*) as n,
       count(distinct /* 未来显式列；当前只能临时解析，不可上线 */ subquestion_index) as dn
from public.questions_bank
where question_type = 'case_study'
  and exam_year = :target_year
  and source_chunk_id = :target_chunk
group by exam_year, source_chunk_id;
```

必须 `n=dn=题面小问数`，所有答案非空。当前 schema 没有 `subquestion_index`，这条本身会红，正好暴露 A 的结构性前置未满足；实验阶段可在客户端解析 index 作诊断，但不能把解析结果冒充数据库 authority。

**单元/集成：**

- 任意 seed/任意返回顺序 → bundle canonical hash 相同。
- 组内 index 集合严格等于题面 index 集合；缺/重/越界 → fail closed，不写 full coverage。
- sibling 查询最多 1 次；case NULL key=0 次；MCQ=0 次。
- exact candidate 来自另一组时不得混入，即 `matched_question_ids` 全部属于锁定 group。
- 同题面、至少三份不同作答：mock/trace 中 `split_stem_hash == preview_query_hash` 且三份完全一致；tier 可因“有无完整 authority”变化，但不得因 answer hash 变化。
- 4 问题面进入 `_build_v1_case_ctx` 后 `case_stem_subquestion_count == 4`；无论 tier-2/tier-3 均不得出现 5。

**真实入口（E4，才有资格说现象消失）：**

- 同一题面 × high/mid/low 三份答案 × 各 3 轮，共 9 轮；`rag_query_hash` 全同、bundle hash 全同、exact group/id 集合全同、`grading_rubric_provenance` 全同。
- 指定 4 问家族每轮 reference 实际采纳 index 恰为 `{1,2,3,4}`；`partial_scope` 不应出现；若只得局部 bundle则必须保持 `official_score_allowed=false`。
- 幽灵小问独立断言：逐跳 `raw/split/query/ctx` surface hash 和长度可对账，计数始终 4；任何一跳变为 5 当轮判红并保留首个分叉层。

### 5.4 插桩是两个新生产问题的最小先手

在实施 bundle 前，优先加只含 hash/长度/marker 的 trace 字段；它比猜缓存或中间件便宜，也同时回答 tier 翻转与幽灵问题：

| 边界 | 必记字段 | 证伪问题 |
| --- | --- | --- |
| manager → AgentLoop | `raw_user_hash`, `msg_content_hash`, len | 入口前是否已改写 |
| split | `stem_hash/len`, `answer_hash/len`, `marker_count`, `chosen_marker_offset` | 作答内容是否改变题干 |
| RAG tool | `preview_query_hash/len` | override 是否真的生效 |
| Supabase pipeline | `service_query_hash`, query item indexes | 工具层到 provider 是否漂移 |
| exact payload | seed id、candidate ids、group key、bundle hash | 哪一步产生随机集合 |
| V1 ctx | `user_stem_hash`, reference hash、covered count、stem count | 幽灵与 tier 首次出现在哪层 |

这些字段需进入现有 authority export 白名单；不记录全文，避免题面/作答泄露。

## 6. 你没问但我必须说

1. **case identity 闸目前实际上是开门。** `exact_question_identity_corresponds()` 对 case 直接返回 True（`supabase_strategy.py:999-1003`）。先聚合再补 identity 会把一个假命中升级成整题错误答案；修复顺序应是“题级 identity/group authority → bundle”，不是“先把候选拼多”。
2. **当前 `seen_by_index` 在不同题之间共享命名空间。** key 只有 `display_index or prompt`（`supabase.py:2701-2719`），没有 group id；两个案例的“问题1”可互相覆盖。这不只是完整性 bug，也是 cross-question authority contamination。即使暂不做方案 C，也应把它纳入红测分母。
3. **历史脏数据决定设计，不是清洗后自然消失。** 9559/17371 重复家族说明同一个 index 可能有多条；删除污染行又可能影响已有引用。bundle 组装必须对“同 index 多答案冲突”fail closed，并导出 conflict ids，不能以相似度静默裁决官方答案。
4. **其它调用方可能依赖顶层 `selected_row`。** 顶层 `question_id/stem/correct_answer` 当前仍是 `ordered_rows[0]`（`supabase.py:2727-2766`），而 `covered_subquestions` 是集合。直接把顶层 correct_answer 改成整题拼接会影响 `case_output_policy` 的 authority 判断、follow-up qid、trace 与可能的下游显示。更安全的收权是：顶层保留 seed provenance，整题 reference 只从 canonical `case_bundle` 读取；随后逐个迁移消费者，最终删除顶层答案的案例评分语义。
5. **并发不是主要竞态，缓存版本才是。** 查询全是只读，但一次 turn 的 seed query 与 sibling query 之间可能遇到数据批次切换，得到跨版本集合。未来 group 表/字段需要 `bundle_version/content_hash`，单次响应断言全组同版本；否则“多一次 SELECT”会引入读时撕裂。
6. **`source_chunk_id + exam_year` 的 46 处只是已知反例，不是唯一性证明。** 快照只证明加 year 消掉这批跨年冲突；没有 `source_document_id` 时，同年不同试卷/来源仍可能撞。唯一性必须用全量反例 SQL与明确 namespace contract 证明，不能靠“目前查到 0 冲突”。
7. **幽灵第 5 问与 bundle 是两条独立故障线。** bundle 修完整只能改变 reference；分母取自 `user_stem`。如果把两者塞进一个 PR，只看最终分数，很容易因 4/5 与 4/4 的数值变化互相抵消，制造假绿。测试与发布 gate 必须分别持有“reference 集合正确”和“题面计数正确”两条断言。

## 收口与证据等级

- claim level：E1（静态代码/既有测试形状与历史 E3 审计支持的设计裁决），不是“已修复/已上线”。
- evidence level：代码位置为当前 checkout 直查；数据分布为 2026-07-30 只读生产快照；两个新现象来自 2026-08-01 真实入口档案，但根因仍是未定位。
- 分母：测绘了 Supabase exact payload、RAG tool metadata、TutorBot prefetch/context、V1 tier/coverage、既有测试与两份数据审计；未覆盖 API 网关/WS 入站到 `msg.content` 的每个中间件运行时值、生产缓存实际配置、live `pg_indexes`、当前数据库最新分布。
- 真正坏掉的一等业务事实：系统没有持久化且可靠的“哪些小问属于同一道案例、顺序是什么”的唯一 authority。
- 争夺 authority 的位置：`source_chunk_id` 被误当题级键；运行时 `display_index` 文本解析代替 DB index；RAG `covered_indexes`、评分实际采纳 indexes、渲染 point attribution 三套覆盖事实并存。
- 为什么推荐方案更接近单一 authority：`case_group_id + subquestion_index + bundle_version` 让归属、顺序、版本由一处写入和读取；A/B 当前都在检索结果上事后猜关系，只会增加第二层解释器。
- 未做/被阻塞：没有可用只读 DB 凭据，未重跑 live SQL；按用户安全边界没有修改代码、运行 pytest、创建临时仓库文件或执行任何 git 写操作。

