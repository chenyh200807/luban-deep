# Scene 分类器非阻塞化 ③稳定性专项 — Phase 1 复核报告（前提证伪 / STOP）

- 日期: 2026-06-29
- 分支: `codex/scene-classifier-nonblocking`（worktree, 从 `origin/main` = ccd5731eb）
- 性质: **read-only 复核**。无逻辑改动。
- 结论: **STOP。前提被活体生产数据证伪。** scene 分类器在当前 main 上**不是** TTFT 阻塞瓶颈；不应建 Phase 2 fast-path（会优化 <1% 的 turn 换 ~0 收益 = "用错轴"）。

## 1. 专项假设（来自 06-26/06-29 memory + 任务交底）

> 首答前阻塞 LLM scene 分类器 `_llm_question_lifecycle_scene_proposal`
> (`question_lifecycle_skills.py:1546`, 调 `llm_factory.complete`, ~6-8s),
> 仅 scene=None 普通聊天才跑, 是普通聊天 TTFT 的 dominant 阻塞 / 满意度最差维度
> (稳定性 2.50) / 8× 超长延迟 (~97s) 的来源。

这是一个**基于代码路径的专家假设**（scene 分类器确实是 pre-first-content 的一次 LLM 调用），
但任务 Phase 1 显式要求"执行时 Langfuse 复核仍是当前 main 瓶颈"，并给了 STOP 条件
"颈已转移, STOP报告"。本报告即该复核。

## 2. 代码真相：scene 分类器已被窄 gate（2026-05-25 起，非近期）

`resolve_question_lifecycle_scene_decision` 只在以下**全部**满足时调 LLM scene 分类器：

- 确定性 `derive_question_lifecycle_scene(ctx)` 返回 `None`，**且**
- `_should_use_llm_scene_proposal(ctx)` 为真，它要求：
  - 消息非空，**且**
  - `metadata` 里**无** `active_object` 且**无** `question_followup_context`
    （即**不在** SEV 活跃题路径上），**且**
  - 消息含考试 hint 词（题/真题/练/考/讲解/掌握/学情/…）。

→ 含 active_object/followup 的 **SEV 活跃题 turn 本来就跳过 scene 分类器**。
gate（`56390d835` / `dddc6b8dd`）落地于 **2026-05-25**，距今一月有余，不是近期收窄。
说明假设是"代码里有这条 LLM 路径"的推断，从未对**活体 trace 分布**验证过它的发生频率。

`_llm_question_lifecycle_scene_proposal` 本身：`max_retries=0`、`max_tokens=300`、temperature=0、
conf<0.72 → scene=None。单次、轻量、无重试长尾。

## 3. 活体证据（生产 Langfuse, environment=production, 2026-06-29）

隧道 `localhost:3001` → `jgzk-langfuse`。三个独立切面，全部互相印证。

### 切面 A — 首答前阻塞 llm.complete 分类器的延迟分布（两个独立窗口）

| 分类器 | 签名 | 占比(1500窗) | 占比(1200窗) | p50 | p95 | p99 |
|---|---|---:|---:|---:|---:|---:|
| **FOLLOWUP** 意图判定器 | `题目 follow-up 判定器` | **79.9%** | **78.5%** | 4.9s | **13.6–13.9s** | **17.4–19.4s** |
| other | — | 14.1% | 16.2% | 2.7s | 7.8s | 13.6s |
| GRADING 判分 | `逐题批改/采分` | 4.2% | 3.2% | 6.2s | 27.5–33s | 41.6–43.7s |
| **SCENE** 分类器（本专项目标） | `生命周期语义候选/allowed_scenes` | **1.7%** | **2.0%** | 4.0s | 8.2s | 9.7s |

scene 分类器占全部阻塞分类器调用的 **1.7–2.0%**，累计耗时 ~113–120s vs FOLLOWUP 的 ~5800–7200s。

### 切面 B — turn 级 TTFT 分解（220 个真实 turn，按 mode/cap 分段）

- **scene 分类器只在 2/220 = 0.9% 的 turn 上运行**；对每段 TTFT 各百分位贡献 ≈ **0.0s**。
- 首答前阻塞(blk)被 FOLLOWUP 主导：
  - `fast/deep_question` blk_p95 = 20.5s，**全部**来自 followup (fu_p95=20.5)。
  - `fast/tutorbot` blk_p95 = 13.2s，fu_p95=6.7。
  - `deep/tutorbot` blk_p95 = 35.3s，fu_p95=15.5。

### 切面 C — 最慢 turn 的归因（379 个 >20s turn，top5 分解）

最慢 turn 由 **GRADING（案例判分，单次 59s）、`learner_state.refresh`（21s）、FOLLOWUP（22.8s）** 主导。
**scene 分类器在最慢 turn 中一次都没出现。**
（注：trace `latency` 含 idle/wall-clock gap，3605s/1804s 是会话挂起非计算耗时；计算分量看 observation 分解。）

## 4. 结论与再定位

1. **scene 分类器非阻塞化对 TTFT 几乎无收益**（命中 <1% turn，对延迟分布贡献 ≈0）。
   建 Phase 2 fast-path 是"用错轴"——正是 [[satisfaction-drags-map...]] 元教训
   ("reactive 非测绘全 + 用错轴")要避免的。**本专项到此 STOP，不进 Phase 2。**

2. **真正的首答前阻塞 LLM = FOLLOWUP 意图判定器** `interpret_question_followup_action`
   (`deeptutor/services/question_followup.py:769`)：
   - 跑在 **SEV 活跃题路径**上（裁决 answer_questions / revise_answers / ask_followup /
     ask_other_question → 直接喂**倒诬 / 回指 SEV 真相**）。
   - 用默认 `max_retries=3`（观测 metadata 证实），解析失败重试 ×3 → p99 ~17–19s 长尾。
   - 占阻塞分类器调用 ~79%。**这是 TTFT 的真瓶颈。**

3. 其余两个大头（同属再定位候选，部分在 Task6 scope 内）：
   - `learner_state.refresh`（pre-first-content ~7–21s）— Task6 已列"不应阻塞 fast first useful"目标。
   - 案例 GRADING（p99 ~42s）— 高风险 deep 路径，不应伪非阻塞但可给 ack/first verdict。

## 5. 对真瓶颈（followup 分类器）的纪律要求（若 owner 决定再定位）

followup 分类器**和 scene 分类器一样在 SEV 路径上**，故同样的硬纪律适用：
- 任何 fast-path/非阻塞化必须保证 answer_questions/revise/followup/ask_other 的裁决**字节一致**
  （倒诬 M4(i) / 回指 / 泄露 3SEV 不可破）。
- 优先低风险减法：先消 `max_retries=3` 的重试长尾（p99 主要来自重试，单次 p50 仅 4.9s），
  再考虑高置信确定性 backstop（代码里 `submission_confidence` 已是确定性 backstop 的雏形）。
- 这是一个**独立于本专项的、更大收益的 scoped 专项**，需单独授权 + 3-SEV live 回归 + eval-design。

## 验证命令（复核者可复跑）

```bash
# 隧道
ssh -fN -L 3001:localhost:3001 Aliyun-ECS-2
# keys: docker exec deeptutor printenv | grep LANGFUSE_{PUBLIC,SECRET}_KEY
python3 scratchpad/lf_phase1.py 1500     # 切面 A
python3 scratchpad/lf_phase1b.py 220     # 切面 B
```
（脚本在本会话 scratchpad；read-only，仅查 Langfuse public API。）
