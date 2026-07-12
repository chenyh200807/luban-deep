# 能力分支融合审计 — 哪些进了统一对话、哪些旁路、还剩什么可优化

> 背景:owner 问"你特别关注 tutorbot,deep_question 等分支留意了吗?都融进统一对话了吗?还有可优化的吗"。
> 方法:只读测绘 agent 对 main 逐文件取证(全部结论带 file:line,行号基于 2026-07-12 main)。
> 过程见 `2026-07-12-battle2-compressed-train-operations-log.md` 事件 7。

## 一、能力清单与融合状态

**orchestrator 真 capability 只有 7 个**(`runtime/bootstrap/builtin_capabilities.py:3-11`):
`chat, tutorbot, deep_solve, deep_question, deep_research, math_animator, visualize`

**mcq_grading/case_grading/轻练出题/复习讲题不是独立分支,而是 lifecycle scene 复用**(已融合进统一 turn 管道,`runtime/orchestrator.py`):
- `question_review`→deep_question(:366);`practice_generation`→deep_question(:422);`case_grading`→deep_question/tutorbot(:424-433);`mcq_grading`→语义路由 fall-through→deep_question route_to_grading(:468-472)。
- 统一管道每轮恰好一次 selection:`turn_runtime.py:5703-5707` → `handle(preselected_capability)`(:5826)——Battle1 路由单跑对**所有**上述分支生效。

**REST 旁路(不经 orchestrator/turn_runtime,设计如此)**,全在 `api/routers/mobile.py` + `luban_lesson.py`:
| 模块 | 端点 | 最重一跳 |
|---|---|---|
| 摸底/首跑 | /assessment/create、/report、/items/{id}/explain | LLM 组卷;deep_explanation **直连 LLM**(member_console/service.py:8077) |
| 学情报告 | /mobile/learning-report | 多 service 聚合+事件线性扫(event_limit 500) |
| 错题本 | /mobile/mistake-book* | DB CRUD,无 LLM |
| 轻练/复习进度 | /practice/today-progress 等 | 纯 DB 读 |
| 鲁班课程/复习 | /luban/lessons、/review-due | 独立 router |

**账本写入**:learner_state 账本只经 `refresh_from_turn`(唯一实质调用点 turn_runtime.py:2712)+notebook/tutor_state 两个 service 写回路径;摸底/报告/练习进度旁路**不写账本**(摸底写自己的 assessment session;首跑完成度是从 learner_state **投影读**,mobile.py:3460)。

## 二、旁路 × 底座收益矩阵(谁没吃到 Battle1/2 的刀)

底座分两类:**turn 专属**(走 /api/v1/ws 才有)vs **service 共享**(谁调谁吃到)。

| 旁路 | TTFVT埋点 | 摘要门控 | turn批量落库 | 判分输出收紧 | RAG 6s/统一RPC | SQLite单写 |
|---|---|---|---|---|---|---|
| 摸底/explain | ✗ | ✗ | ✗ | ✗(自建LLM讲解,不经submission_grader) | ✓ | ✓ |
| 学情报告 | ✗ | N/A | ✗ | N/A | N/A | ✓ |
| 错题本/轻练进度 | ✗ | N/A | ✗ | N/A | N/A | ✓ |
| 统一 turn 的全部能力 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

**判读**:旁路模块多为 DB 读写(错题本/进度),缺 turn 底座影响小;真正值得注意的是**摸底 deep_explanation 直连 LLM**——无 TTFVT 观测、无输出收紧、无门控,是观测盲区+潜在慢点。

## 三、残余可优化点(按性价比排序)

1. **【零成本,开闸即得】followup 判定器 flag-off 白付冗长 rationale**:每 followup turn 仍阻塞首答 1 次 LLM,输出 5 键 schema 含长 reason(p50≈216 tok≈3.3s),slim 模式已实现被 `LUBAN_FOLLOWUP_FAST_TIER_ENABLED`(question_followup.py:2882 默认关)挡住。**这是灰度序 T+3d 那一档,开了就拿。**
2. **【同病兄弟①】memory_service.refresh_from_turn 无门控双 LLM**(services/memory/service.py:197-219):每轮顺序两跳 `_rewrite_one("profile")+_rewrite_one("summary")`(各 max_tokens=900)——正是 learner_state 摘要门控修掉的形状,此处未修(user_id 为空路径,turn_runtime.py:2795)。修法=照搬 S1 计数门。
3. **【同病兄弟②】JSONL 每 turn 双次全文件线性读**(learner_state/service.py:669-676 整份逐行 json.loads;:1709 门控扫一遍、:1741-1750 build_summary_source 再扫一遍):重度用户事件累积后 O(N)×2/实质 turn。修法=尾读游标或单次扫共享。
4. **判分 repair 跳重发全量 payload**(submission_grader_agent.py:151-155):repair prompt=完整 user_prompt 原样重拼——条件跳(仅缺段时),但触发时白付整份上下文重传。修法=repair 只带缺段所需最小上下文。
5. **摸底 deep_explanation 收编**:直连 LLM(member_console/service.py:8077)无观测/无收紧/无门控。修法=至少加 TTFT 观测与输出上限;长期可评估是否路由进统一管道。
6. **学情报告读模型**:事件线性扫聚合(mobile.py:3200-3234),当前 event_limit=500 兜底,量级尚可,重度用户前不紧急。

**明确不建议动的**:出题链检索已是 1 跳(idea_agent.py:123),idea→generator 是数据依赖串行不可并行;construction 判分复核由确定性 rubric 承担(rubric_grader_v1.py:119,无 LLM)——这些没有可省的肉。

**未证实项(诚实边界)**:generator 是否每题一 LLM 未逐行确认;摸底 create_assessment 是否可能命中题库短路未展开。

## 结论一句话

对话类分支(含 mcq/case 判分、轻练出题、复习讲题)**都已融合**在统一 turn 管道并自动吃到 Battle1/2 全部底座;五模块 REST 旁路是**设计性分离**(多为 DB 读写,损失有限),真正的残余机会=开 followup flag(白拿)+ 两个同病兄弟(memory_service 门控/JSONL 线性读)+ 摸底讲解收编观测。
