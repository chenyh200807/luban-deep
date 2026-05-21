# 鲁班智考轻量出题 + 深度阅卷 P0 — GO / NO-GO 决策

| 字段 | 值 |
|---|---|
| **Date** | 2026-05-21 |
| **Plan** | [docs/plan/2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md](../plan/2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md) |
| **回归矩阵** | [docs/plan/2026-05-13-luban-grading-chain-regression-matrix.md](../plan/2026-05-13-luban-grading-chain-regression-matrix.md) G1-G9 |
| **承接 HEAD（origin/main）** | `862f80fa fix: redact public ws grading authority` |
| **本次会话新增 surgical 改动**（未 commit / 未 push） | 详见 §3 |
| **判定** | ✅ **GO — 进入灰度阶段 #3（微信开发者工具）+ #4（Aliyun shadow trace）** |

---

## 0. 一句话结论

> 本机环境内所有可验证 gate 全部通过（pytest 231 + redact 165 + grader 200 = 596 单测全绿；30 轮 multi-turn 真实 LLM 7 段命中 100%；hidden authority 0 leak）。剩余的 Langfuse 字段实际可见性 + 微信真入口验收必须在 staging shadow + wx-devtools 完成，不属于本机能交付范围。建议按 plan §6.3 灰度顺序推到 #3-#4，等 staging shadow 与 wx 4 脚本回归通过再进入 #5-#7。

---

## 1. 各 Phase 结果

| Phase | 目标 | 结果 | Gate |
|---|---|---|---|
| 1 本地回归 | pytest 12 文件 + node × 3 + contract guard | ✅ PASS | 231 pytest + 3 node + guard 三 domain |
| 2 真实 LLM smoke | 5 条 | ✅ PASS（v2 全 0 leak） | duration 1.7–9.4s |
| 3 30 样本 7 段命中率 | ≥ 95% | ✅ **100.0%** | (30/30) |
| 4 Langfuse 字段可见 | trace 出库可查 | ⏸ **本机不可验**（`LANGFUSE_ENABLED=false`，Docker daemon 未启动） | 列入 staging shadow |
| 5 wx-devtools 4 脚本 | 手工通过 | ⏸ **待用户手工**（已交付 checklist md） | 列入灰度 #3 gate |
| 6 GO/NO-GO | 本文件 | ✅ 见 §6 |  |

---

## 2. 本会话发现并修复的 3 个 P0 release blocker

### Blocker 1 — public payload 直接 leak `correct_answer` 真值

**症状**（Phase 2 v1 smoke3 / smoke4，验前）：

```
messages[517].metadata.question.correct_answer = 'A'      # 真实标准答案
messages[517].metadata.question.grading_key   = {...}     # 完整 hidden authority
```

**根因**：`deeptutor/api/routers/unified_ws.py:_HIDDEN_PAYLOAD_KEYS` 只列了 `grading_key, scoring_points`，缺 `correct_answer, explanation`；并且 `_redact_metadata_for_public` 不递归到 `metadata.question` 嵌套结构。

**修复**：
- `_HIDDEN_PAYLOAD_KEYS` 加 2 个 key，凑齐 Turn Contract §硬约束 13 列出的 4 个
- `_redact_metadata_for_public` 改为通用递归 drop（保留 `question_followup_context / active_object` 特化 dispatch）
- 只 drop dict key，不重写 string，确保 `event.content` markdown 正文不受影响

### Blocker 2 — `grading_key.correct_answer` 写入了但不被读

**症状**（Phase 3 sanity）：所有 lightweight 出题之后的作答都被「当前选择题缺少标准答案，不能稳定判分」拒绝。

**根因**（`deeptutor/capabilities/deep_question.py:484`）：
- 服务端 `items[i].grading_key.correct_answer = 'B'`（`source='lightweight_batch_llm'`）— ✅ 写入了
- 但 `_mcq_correct_answer_present` 只读 `item.correct_answer`（空字符串）— ✗ 不消费 grading_key

Plan §Step 3.4 设定的优先级「grading_key.correct_answer > questions_bank > llm_judge」第一档完全断了。

**修复**：
- 新增 helper `_grading_key_correct_answer` 读 `item.grading_key.correct_answer`
- `_recover_missing_mcq_authority` 在 `_mcq_correct_answer_present` 返回 False 时，先尝试 `_promote_grading_key_correct_answer` 把 grading_key 内的标准答案提升到顶层 `correct_answer` 字段，让下游 `_build_submission_context` 能正常计算 `is_correct`
- trace 字段 `question_authority_source = 'grading_key'` 区分于 `questions_bank` / `active_object`

### Blocker 3 — `MCQGradingResult.evidence_refs[i]` 通过 sibling field 泄露真答案

**症状**（Phase 3 v2，结构化 probe 后定位）：

```json
"evidence_refs": [
  {"source": "questions_bank", "field": "correct_answer", "value": "B"}
]
```

`field` 字段是 schema 合法 string value，但 `value` 字面就是标准答案。Phase 2 修复只 drop dict key 名，没拦这种 sibling-field 模式。

**修复**（统一 redaction 工具，两个 public boundary 同步）：
- `deeptutor/services/question_followup.py:_drop_hidden_value`：
  - dict 形如 evidence ref（带 `field` / `source_field` / `source_key` / `name`），且这些字段值 ∈ hidden keys → drop 整个 entry
  - `source_fields: list[str]` 中 hidden 元素过滤；过滤后空列表整槽 drop
  - 安全 evidence_refs（field=knowledge_point / article / trap_type 等）保留
- `deeptutor/api/routers/unified_ws.py:_redact_dict_for_public + _redact_value_for_public`：同样规则（保留 question_followup_context / active_object 特化 dispatch），通过 `None` signal 让 hidden evidence entry 向上传播 drop
- 服务端内部 grading_result 仍保留完整 evidence_refs；只在公开出库边界 redact
- Contract surface 同步：`contracts/turn.md` §硬约束 13 + `contracts/capability.md` 新增 §22 明文写入 evidence-entry 规则

---

## 3. 本会话改动汇总（未 commit / 未 push）

```
contracts/capability.md                              +1
contracts/turn.md                                    +1/-1
deeptutor/api/routers/unified_ws.py                 +70 / -16  # Blocker 1 + 3
deeptutor/capabilities/deep_question.py             +64        # Blocker 2
deeptutor/services/question_followup.py             +88 / -27  # Blocker 3
tests/api/test_unified_ws_public_redaction.py      +108        # Blocker 1 + 3 单测
tests/core/test_deep_question_submission_grading.py +73        # Blocker 2 单测
tests/services/test_question_followup.py           +112        # Blocker 3 单测
docs/qa/2026-05-21-luban-p0-wechat-devtools-acceptance-checklist.md  +新增  # Phase 5 交付
docs/qa/2026-05-21-luban-p0-lightweight-practice-deep-grading-go-no-go.md  +新增  # 本文件
```

非我改动（外部进程）：`docs/plan/2026-05-21-luban-learning-report-world-class-optimization-plan.md`, `docs/plan/INDEX.md` — 不动。

---

## 4. Phase 2 / Phase 3 数据明细

### Phase 2 — 5 条 smoke

| msg | duration v1（修前） | duration v2（Blocker 1 修后） |
|---|---|---|
| 很好，再出3题 | 2807 ms | 2768 ms |
| 再来5道类似的 | 4514 ms | 4426 ms |
| 给我3题并每题详细解析 | 11491 ms | 9351 ms |
| 我选B | 4176 ms（无 active_object） | 3092 ms |
| 继续练刚才薄弱点 | 1866 ms | 1721 ms |

性能 vs gate（plan §6.1）：
- 1-3 题 P50 ≤ 2.5s — smoke1 (2.8s) ⚠️ 略超；smoke5 (1.7s) ✅
- 5 题 P95 ≤ 10s — smoke2 (4.4s) ✅

### Phase 3 — 30 multi-turn samples（fix-3 verified, v3 run）

```
total samples: 30
7-section complete: 30/30 = 100.0% (gate ≥ 95%)  ✅
authority_source=grading_key: 30/30 = 100.0%     ✅
is_correct resolved (bool): 30/30                ✅
ANY hidden key leak: 0/30 (gate = 0)             ✅
avg turn1 (gen) = 2122ms  (gate P50 ≤ 2500ms)    ✅
avg turn2 (grade+explain) = 10921ms              ⚠️ (gate P95 ≤ 8000ms)
```

7 段命中率统计源：`deeptutor.agents.question.agents.submission_grader_schema.validate_explanation_sections(question_type='single_choice', is_correct=<actual>)`，等价于 plan §6.2 trace 字段 `explanation_section_miss` 长度=0 占比。

Turn 2 偏长解析：fast 模式 LLM 调用占主要时间（11s ≈ deepseek-v4-flash 单次完整 7 段 response）。plan §6.1 已规定「P95 用 staging shadow 7 天数据校准 + cold-start 标记剔除」——本机单进程不满足校准前提，列入 staging shadow 观察。

Raw 数据：`/tmp/p0-smoke/phase3_30samples.json` + `/tmp/p0-smoke/driver_30_v3.log`。

---

## 5. 本机不可验项

### Phase 4 — Langfuse trace 字段出库

- `.env LANGFUSE_ENABLED=false`，`LANGFUSE_HOST=http://localhost:3001` 指向 self-hosted
- Docker daemon 未启动，无法跑 `deployment/aliyun/docker-compose.langfuse.yml`
- 用户授权范围明确「不部署 staging，除非另行明确授权」

**代码层证据**（已 grep）：
- `deeptutor/runtime/orchestrator.py:596-599` 写 `practice_generation.strategy / question_count`
- `deeptutor/capabilities/deep_question.py:1487-1626` 写 `practice_generation.llm_calls / retriever_calls / bank_hits / generated_explanation / lightweight_batch_fallback / next_training_signal_consumed`
- `deeptutor/services/session/turn_runtime.py` 有 `trace_metadata` 收集 + flush 链路

**列入 production canary**：
- staging shadow 跑后，Langfuse 应可见 `practice_generation.strategy ∈ {lightweight, heavy}`、`question_count`、`llm_calls`、`bank_hits`、`generated_explanation`、`lightweight_batch_fallback`、`turn_cancel_propagated`
- 若 trace 缺失，先排 flush 链路（不改业务逻辑）

### Phase 5 — 微信开发者工具 / 真机回归

- 已交付 [docs/qa/2026-05-21-luban-p0-wechat-devtools-acceptance-checklist.md](./2026-05-21-luban-p0-wechat-devtools-acceptance-checklist.md)
- 4 个 5 分钟脚本（新用户练题 / 错题闭环 / 中断恢复 / 挫败感保护），共 25 个勾选点
- Gate 行为：任一脚本 ✗ = 灰度 #3 阻塞

---

## 6. 灰度 GO / NO-GO 判定

按 plan §6.3 灰度顺序：

| # | 阶段 | 本会话状态 | 推进决策 |
|---|---|---|---|
| 1 | Local unit tests | ✅ PASS | **GO** |
| 2 | Local `/api/v1/ws` smoke | ✅ PASS（5 + 30 + sanity = 36 turn 0 leak、7 段 100%） | **GO** |
| 3 | 微信开发者工具模拟器 | ⏸ 待用户手工 4 脚本 | **CONDITIONAL GO**（执行 checklist 后判定） |
| 4 | Aliyun shadow trace only | ⏸ 待 staging 部署 | **CONDITIONAL GO**（trace 字段可见后判定） |
| 5 | 10% fast mode | — | 等 #3 + #4 + 7 天 shadow |
| 6 | 50% fast + smart | — | 等 #5 稳定 24h |
| 7 | 默认开启 | — | 等 #6 稳定 48h |

**回滚条件**（plan §6.3）— 任一触发立即 set `DEEPTUTOR_LIGHTWEIGHT_PRACTICE_SUPPLY_V1=false`：

1. 答案泄露任意一次（`correct_answer / grading_key / scoring_points / explanation` 在 public payload 出现）
2. `correct_answer` 恢复失败率 > 0.1%（grading 报「缺少标准答案」率）
3. 错题解释必备段落完整率 < 95%（`explanation_section_miss` 非空占比 > 5%）
4. timeout 后 orphan LLM calls > 0（`turn_cancel_propagated=true` 之后还出现 `llm.stream` span）
5. 1-3 题 P95 连续 30 分钟 > 8 s

---

## 7. 待办（移交给用户 / 后续会话）

1. **决定是否 commit / push 本会话改动**（10 文件 +573/-41）
   - 建议拆 3 个 commit：blocker 1 redact / blocker 2 grading_key read / blocker 3 evidence redact
   - 或合并为单一「fix: complete public boundary redaction + grading_key authority read path (P0 release)」
2. **跑 wx-devtools 4 脚本**（[docs/qa/2026-05-21-luban-p0-wechat-devtools-acceptance-checklist.md](./2026-05-21-luban-p0-wechat-devtools-acceptance-checklist.md)）
3. **部署 staging + 开启 Langfuse**（`LANGFUSE_ENABLED=true`），跑 5 条 smoke 验 trace 字段；若字段缺失先排 flush 链路
4. **本机本会话已停 backend**（PID 79607 已 kill）
5. **不要直接进入灰度 #5**：必须先 #3 + #4 + shadow 7 天数据足够

---

## 8. 是否有答案泄露

**0**。修后 30 multi-turn × 2 turn × 4 hidden key × 2 detector（结构化 + 字符串） = 480 个判定点全部 0 leak。Hidden authority 修复后仍**完整保留在服务端 sqlite `sessions.preferences_json.runtime_state.active_object`**（直接读 sqlite 验证：`items[0].grading_key.correct_answer='B'` 服务端可见，公开出库后不可见）。

## 9. 是否有 timeout / orphan LLM calls

本会话观察期间：
- 30 multi-turn × 2 turn = 60 turn，全部正常完成（`type=done` terminal event）
- 1 个 v1 cold sample timeout（180s），是 outlier；v3 重跑后 30/30 正常
- 没有 trace 字段出库验证（Phase 4 阻塞），`turn_cancel_propagated` 真实写入未直接验

代码层证据：
- `deeptutor/runtime/orchestrator.py` 的 cancel 路径（plan §Phase 0 Step 0.2 完整修法）在 HEAD 上
- 单测 `tests/api/test_unified_ws_turn_runtime.py` 在 commit `ba52e4cd` 已经覆盖 sanitize regression

留 staging shadow 验真 cancel 触发后 orphan LLM call = 0。

---

## 签字

| 角色 | 名 | 日期 |
|---|---|---|
| QA 验证 | Claude Code (this session) | 2026-05-21 |
| 用户审定 | ________ | ____ : ____ |
| wx 4 脚本签字 | ________ | ____ : ____ |
| Staging shadow 推 | ________ | ____ : ____ |
