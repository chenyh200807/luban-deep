# FOLLOWUP 意图判定器延迟收口 — Phase 2a 调查报告（重试根因 + fallback 安全 + 长尾构成）

- 日期: 2026-06-29
- 分支: `codex/scene-classifier-nonblocking`（worktree, rebased 到 `origin/main`=eee044661）
- 性质: **read-only 调查**。无逻辑改动。
- 前置: [③稳定性 Phase 1 证伪报告](2026-06-29-scene-classifier-nonblocking-phase1-bottleneck-falsified.md)
  已证 scene 分类器非瓶颈，再定位到 FOLLOWUP 意图判定器
  `interpret_question_followup_action`(`question_followup.py:769`)。
- 结论: **STOP 等 owner 批 2b 方向。** Phase 2a 又一次核出隐含假设站不住：
  **"砍重试杀长尾"的前提被证伪——长尾不是重试主导，是单次调用本身慢。**

## Q1. 为什么重试 3 次？重试在恢复什么？

`interpret_question_followup_action` 调 `factory.complete()`，用默认
`max_retries=3`（`settings.retry.max_retries`，base_delay=1.0，指数退避 max=120s）。

`complete()` 的 tenacity 重试条件（`factory.py:341` + `_is_retriable_error:163`）**只**覆盖
**transient 基础设施失败**：`LLMTimeoutError` / `LLMRateLimitError`(429) / 5xx / 网络连接错误。
**不重试**：invalid/empty JSON、低置信、4xx(除 429)、auth/config 错误——这些 caller 直接
`_parse_followup_action_payload`→None，**不触发重试**。

→ **重试恢复的是 provider 抖动，不是裁决准确性。** 一次重试成功返回的裁决与首次成功
**完全相同**（同 prompt/temperature=0/同 model）。**砍重试不会让分类变差**，只是在 provider
真抖动时更快放弃 → 落 fallback。

## Q2. 重试耗尽后的 fallback 是什么？对 SEV 安全吗？

`interpret_question_followup_action` 失败/耗尽 → 返回 `None`。在 QTPK
(`question_turn_policy.py:893,974`)里，LLM 是**确定性 gate 全失败后的最后兜底**：

- 干净作答（"我选B"）被 `_submission_action_for_user_message` **确定性截获**（:950/:979），
  **根本不到 LLM**。
- 确定性 followup 被 `_deterministic_followup_action_for_user_message` 截获（:967/:887）。
- LLM 只处理**确定性检测器都判不出的歧义残渣**。

interpret 返回 None 时 → `normalized_action=None` → turn **不被判为 submission/followup/practice**
→ 落 `(context, None)` / `(None, None)` → 降级到普通聊天/under-act。

**这是 SEV fail-safe**：
- **不破倒诬**：None → 不判为 submission → 不判分 → 不会用错选项面误判。
- **不破回指**：None → 不绑 followup → 不会绑错题。
- 代价 = 歧义 turn **少识别一次** followup（under-act，降级为普通聊天），**不是误路由（mis-act）**。

干净作答/确定性 followup 不依赖 LLM，故 fallback **不伤硬约束 40 / 倒诬 / 回指**。

## Q3. 长尾（p99 17–19s）是重试主导还是单次调用慢？（量化）

2502 个生产 FOLLOWUP `llm.complete` 观测，延迟直方图（2s 桶）：

```
0-2     37
2-4    844  ████████████████████████
4-6    931  █████████████████████████  ← 主峰
6-8    350  ██████████
8-10   143  ████
10-12   76  ██
12-14   58  █
14-16   25
16-18   20
18-20    8
20-22    5
22-24    2
26-28    3
p50=4.6  p90=9.0  p95=11.8  p99=16.9  max=27.3
```

**分布平滑单峰，无重试离散次峰。** 若重试主导，应在 ~11s(1 retry=5+1+5)、~18s(2 retry) 见明显
次峰；实际是平滑衰减尾。

**token 相关性**：慢调用(≥12s, n=121)平均 input **2056 token** vs 快调用(<8s)**1416 token**
（大 45%）。→ 长尾**主要是单次调用本身慢**（更大 prompt + provider 生成方差），**非重试**。
只有 ~0.5%(13/2502) 调用 >18s（重试可能区）。

**结论：砍 `max_retries` 是 SEV-safe（Q1/Q2）但几乎不动 p95（Q3，p95=11.8s 是单次慢非重试）。**
单独砍重试 = 低风险但低价值，不值一个专项。

## 2b 方向选项（据 2a 真相，等 owner 批，不提前实施）

真正的延迟成本 = **单次调用本身**，落在每个到达 LLM 的歧义 active-question turn 上
（p50=4.6s 是这些 turn 的 TTFT 地板）。可选杠杆，**风险/价值各异**：

| 选项 | 做法 | SEV 风险 | 价值 | 字节一致 |
|---|---|---|---|---|
| **B1 砍重试长尾** | `max_retries` 3→1 + 缩 backoff | 低（fallback fail-safe） | **低**（只动 ~0.5% 调用，不移 p95） | 裁决字节一致（仅 transient 失败更快落 fallback） |
| **B2 缩 prompt** | 精简 followup prompt（history 800→更短 / 规则压缩） | 中（改输入→可能改裁决） | 中（降单次延迟） | **否**（需 differential parity 证等价，非字节一致） |
| **B3 deterministic-first 扩面** | 把更多高置信歧义 turn 用确定性规则截在 LLM 前 | **高**（残渣本就是确定性判不出的，扩面易误判→SEV） | 高（跳过整次 LLM） | 需逐 case parity + 3-SEV |
| **B4 换更快模型** | followup 分类专用更小/快模型 | 中（换 model→改裁决） | 中–高 | **否**（需 differential parity） |

**工程建议（待 owner 拍板）**：
1. **B1 顺手做但别当主菜**——它低风险（可与任何主菜捆绑），但别指望它移 p95。
2. **主菜在 B2/B4（降单次延迟）**：followup prompt ~1400 token、规则冗长，是单次慢的直接来源；
   但任何 prompt/model 改动**改变裁决**，必须用 differential parity（覆盖 answer/revise/followup/
   ask_other/回指/倒诬）证**等价**（非字节一致）+ 3-SEV live≥3，门槛高、需 eval-design。
3. **B3 最高价值也最高 SEV 风险**——残渣是确定性判不出的歧义，扩确定性覆盖容易误判破倒诬/回指，
   除非有强 eval 证据，否则不碰。
4. **诚实定调**：followup 分类器的单次延迟是 active-question turn 的**结构性 TTFT 成本**
   （LLM 必须先裁 relation/next_action 才能路由），与 deep_question 的 model-bound 同类——
   "慢"与"对"共用同一次 LLM 裁决，不能廉价分离。这与 Task6 对 deep_question 的结论同构。

## Phase 2b 实施结果（owner 选 B1：砍重试 + STOP，2026-06-29）

owner 拍板 **B1**（明确定性"诚实的小清理，不假装是性能解"）。

**改动（surgical，1 处 kwarg）**：`question_followup.py` 的
`interpret_question_followup_action` 给 `complete()` 显式传 `max_retries=1`（原吃全局默认 3）。
- 保留对单次 provider blip 的一次廉价重试（比 scene 分类器的 `max_retries=0` 略保守——followup
  裁决更 consequential：它 gate submission/grading，值一次重试再落 under-act）。
- 不再堆 3 层指数退避（1s+2s+4s）→ cap 掉 ~0.5% 的重试驱动极端尾（>18s）。

**为什么 SEV-safe + 字节一致**：
- 重试只针对 transient infra 失败（Q1），重试成功 = 首次成功（同 prompt/temperature=0）→ **裁决不变**。
- 唯一行为 delta：provider 真抖动时少 2 次重试 → 更快落 **fail-safe None**（under-act 不 mis-act，Q2）。
- happy path（无 transient 失败）只发**一次**调用，与 max_retries 无关 → **p50/p95 不变**。

**诚实定性**：这是 **极端尾 cap + 清理**，不是 p50/p95 性能解（单次慢才是 p95 主因，B1 不碰）。

**验证**（本地全绿）：
- TDD: `test_followup_classifier_caps_retries_to_one`（RED→GREEN，断言 `max_retries==1`）。
- `tests/services/test_question_followup.py` 164 passed；注册 domain + 上游 caller
  (question_followup_case_submission / context_derivation_audit / qtpk_lifecycle_state /
  resolve_reveal_decision) 212 passed。
- byte-identical parity: `test_qtpk_differential.py` + `test_qtpk_grading_patch.py` 20 passed；
  semantic_router + qtpk_lifecycle 52 passed。
- contract guards: `check_contract_guard.py` + `check_control_plane_writer_allowlist.py --check` 全 passed。
- 差分 parity 由构造保证：max_retries 不碰决策逻辑，无 decision 变化可验。
- live SEV army（倒诬/回指）对 max_retries-only 改动跑的是**不变的裁决**，非差分有意义；
  正常运行行为与改前等价。建议部署后随①forward 的 live 回归一并核终态即可，不单独 billable army run。

## 验证命令（复核者可复跑）

```bash
# 调查复核
ssh -fN -L 3001:localhost:3001 Aliyun-ECS-2
python3 scratchpad/lf_phase2a.py 2500   # 长尾构成 + token 相关性
# 2b/B1 回归
pytest tests/services/test_question_followup.py -q
pytest tests/services/test_qtpk_differential.py tests/services/test_qtpk_grading_patch.py -q
python3 scripts/check_contract_guard.py && python3 scripts/check_control_plane_writer_allowlist.py --check
```
