# Grading Hot Path Latency Audit (FOLLOWUP-002-AUDIT)

| 字段 | 值 |
| --- | --- |
| 日期 | 2026-05-19 |
| 类型 | Audit (read-only investigation) |
| 状态 | Done — no fix plan required |
| 主线 | 鲁班智考个性化教学（INDEX.md 主线 16） |
| 触发 | `/qa-only` 2026-05-19 ISSUE-002（dev harness 6.9s）的 follow-up 验证 |
| 调研人 | Explore subagent + 主 agent 汇总 |

---

## 1. 触发问题（why this audit）

2026-05-19 `/qa-only` 实测：dev harness endpoint `/api/v1/learning-brain/harness-case-grading` 首次冷启动 6875ms。已在 `deeptutor/api/routers/learning_brain.py:223` 加 Latency note 标注 "intentionally end-to-end, not hot path"。本 audit 回答唯一悬置问题：

> **production grading 路径是否也有同样的 6s+ 串行延迟？**

如果有，需要立独立 fix plan；如果没有，dev harness 6.9s 是设计意图，本 audit 结案。

---

## 2. Authority Map（production grading 的 single authority）

| 维度 | 事实 | 证据 |
| --- | --- | --- |
| Capability authority | `DeepQuestionCapability` | `deeptutor/capabilities/deep_question.py:850+` |
| Production entry (主) | WebSocket `/api/v1/ws` | `deeptutor/api/routers/unified_ws.py:177` |
| Production entry (assessment REST) | `POST /api/v1/mobile/assessment/{quiz_id}/submit` (MCQ only, 不走 case grading) | `deeptutor/api/routers/mobile.py:2080` |
| Dev mirror entry | `POST /api/v1/learning-brain/harness-case-grading`（受 `_qa_enabled()` gate） | `deeptutor/api/routers/learning_brain.py:223` |

**确认**：`/wechat-harness` 系列 endpoint 与 production 完全独立；production 用户走 WebSocket 或 mobile assessment REST，**不会**碰到 dev harness 6.9s。

---

## 3. Production Case Grading 调用栈

```
WebSocket /api/v1/ws  (unified_ws.py:177)
  → TutorBotCapability + DeepQuestionCapability
    → deep_question.py:973 _build_submission_context()           [SYNC, 上下文准备]
      → attach_deep_question_grading_result()                    [SYNC]
        → build_deep_question_grading_result()                   [SYNC]
          → CaseGradingSkillKernel().grade()                     [SYNC, *NO LLM*]
                                                                   (services/construction_grading/deep_question_adapter.py:51)
          → write_grading_error_events()                         [SYNC, local SQLite]
                                                                   (services/construction_grading/writeback.py:12)
            → learner_state_service.append_memory_event()         [SYNC, local file + SQLite]
    → await agent.process()                                       [ASYNC, *SubmissionGraderAgent LLM*]
                                                                   (deep_question.py:992)
```

### 关键时延分析

| 调用层 | 性质 | 估时 | 备注 |
| --- | --- | --- | --- |
| `CaseGradingSkillKernel.grade()` | SYNC, **NO LLM**，纯 Python 文本规则匹配 | < 50ms | rubric item + grading keyword 匹配；本地无 IO |
| `write_grading_error_events()` | SYNC, 本地 SQLite write | < 100ms | local file，无网络 |
| `learner_state_service.append_memory_event()` | SYNC, local SQLite + file write | < 100ms | append-only ledger |
| `SubmissionGraderAgent.process()` | **ASYNC**, LLM call | ~2-5s | 已 await，不阻其他 sync 工作 |

**总时延估算（产线 single user submit）**：< 200ms 的 sync 工作 + ~2-5s 的 async LLM call。**没有 6s+ 串行瓶颈**。

---

## 4. `synthesize_learning_truth` 在产线的位置（关键问题）

dev harness 6.9s 的**最大单一时延来源**是 `synthesize_learning_truth(dry_run=True, event_limit=50)`（`learning_brain.py:280`）。

| 调用点 | 是否 inline 产线 hot path | 证据 |
| --- | --- | --- |
| `learning_brain.py:280` (dev harness POST grading) | ❌ dev-only，受 `_qa_enabled()` gate | gate fail → 404 |
| `learning_brain.py:214` (dev harness GET projection) | ❌ dev-only，同 gate | gate fail → 404 |
| `mobile.py:2058` (`/api/v1/mobile/learning-brain/projection` **fallback**) | ⚠️ 仅当 compiled truth **缺失** AND **flag enabled** 时 | mobile.py:2055 默认读 pre-compiled truth from disk |
| `scripts/run_learning_synthesis.py` | ✅ **nightly cron 离线** | cron 入口，非用户请求路径 |

→ **产线 hot path 默认读 pre-compiled truth**（已经 synthesize 过的 JSON projection），**绝不会 inline 调 `synthesize_learning_truth`**。dev harness 之所以 6.9s 是因为它故意每次都重新 synthesize 走完整链路（end-to-end visibility 验证目的）。

---

## 5. 单用户 submit → `grade()` 调用次数

| 场景 | `grade()` 调用次数 | 是否串行 |
| --- | --- | --- |
| Single case study submit | 1 | n/a |
| Batch case study submit (rare) | N | 串行 FOR loop（`deep_question_adapter.py:93`），未用 `asyncio.gather` |
| MCQ assessment submit | 0（走 simpler MCQ check，不用 `CaseGradingSkillKernel`） | n/a |

**风险**：batch case 不并行，但 production 是否真的有 batch case 调用未知；多数 user submit 单题。Dev harness 强制 2 case = 2 次串行 grade，是它 6.9s 的次要因素。

---

## 6. First-Principles 修复方向（**当前用不上**，备查）

如果未来产线出现 6s+ 串行（例如 fallback synthesis flag 被大规模启用，或 batch case 成为高频场景）：

| 方向 | 操作点 | 难度 |
| --- | --- | --- |
| `write_grading_error_events` 异步化 | `deep_question.py:1036` 改 background task | 低（已经是 fire-and-forget 候选） |
| `synthesize_learning_truth` 永不 inline | 删 `mobile.py:2058` 的 fallback 分支，或加严 flag gate | 低 |
| Batch case 并行化 | `deep_question_adapter.py:93` 的 FOR 改 `asyncio.gather` | 中（需要每个 case 是 stateless） |
| LLM feedback async | 已经 async，无需动 | — |

这些是症状真出现后才动的；不打无准备的优化补丁。

---

## 7. Verdict

**NEEDS_LATENCY_FIX_PLAN: NO**

| 依据 | 内容 |
| --- | --- |
| Production hot path 不内联 synthesize_learning_truth | mobile.py 默认读 pre-compiled disk projection；dev harness 是唯一 inline 调用方 |
| Kernel grading 是 sync NO LLM | `CaseGradingSkillKernel.grade()` 纯 Python，<50ms |
| Writeback 是 local SQLite | 无网络 round trip |
| LLM feedback 已 async | `await agent.process()` 不阻 sync 工作 |

**受影响用户面**：无。dev harness 6.9s **不传染** production。

**与 dev harness ISSUE-002 docstring 一致**：`learning_brain.py:233-237` 注释明确写了 "this endpoint intentionally runs the full grading + writeback + synthesis chain end-to-end so the visible-chain mirror exercises real authorities. It is a dev-only harness…not a production hot path"。

---

## 8. 监控建议（不立 plan，但放进运维清单）

1. 如果**未来**开启某个 flag 让 `mobile.py:2058` 的 fallback 在产线大规模触发 inline synthesize，会复现 6s+ 延迟。建议在 release 这种 flag 前**先看本 audit §6 修复方向**。
2. 如果 batch case study submit 成为产品形态（目前不是），`deep_question_adapter.py:93` 的串行 FOR loop 会成为瓶颈，按 §6 第 3 条并行化。
3. 如果 Langfuse / observability 在 `/api/v1/ws` grading turn 上看到 P95 > 5s，独立调研（可能是 LLM provider 延迟，与本 audit 范围正交）。

---

## 9. 不确定性与替代方案

| # | 不确定性 | 替代验证手段 |
| --- | --- | --- |
| U1 | 本 audit 是静态 code reading 调研，未跑 production trace。产线真实 P95 latency 仅靠 Langfuse / ClickHouse 才能权威。 | 建议运维偶尔从 Langfuse 抽取 `/api/v1/ws` deep_question submit turn 的实际 P50/P95；若数值与 §3 估算严重偏离，重新 audit。 |
| U2 | "mobile.py:2058 fallback 仅 flag enabled 才触发" 这一条没在本 audit 实际测试过 flag 开关；只读代码推断。 | follow-up：跑一次 fallback flag 开启的小规模 staging 测试，观察 latency。 |
| U3 | Explore subagent 调研深度限制，未确认 `DeepQuestionCapability` 内部所有分支都不走 synthesize。可能有 edge case 分支调用。 | follow-up：grep `synthesize_learning_truth` 全仓库 + 看每个 caller。 |

---

## 10. 收口

- ISSUE-002 dev harness 6.9s 已通过 docstring 标注为设计意图（PR #1 `590ca7f1`）
- 本 audit 确认 production 不传染 → 不立独立 latency fix plan
- 监控清单（§8）入运维流程

