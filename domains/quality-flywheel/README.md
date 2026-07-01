# Domain: quality-flywheel · TutorBot 准确性封板

> Shared brain（持续质量飞轮 V2）。本目录把散件按 loop-engineer-template 的
> shared-brain 结构落地：**charter（本文件）+ signals（去重/频次）+ metrics（确定性时序）
> + LOG（活动流）**。它**不是**第二套质量门 authority——门的代码 authority 仍在
> `scripts/quality_gate/accuracy_gate.py`，本目录只做「记录 + 复利」。

## Goal

把「TutorBot 准确性回归」从一次性手跑探针，固化为「换 SHA 一键复核六维、红即阻断」的
**可复利封板循环**：每次 eval 的 6 维 fail_rate 不再跑完就丢，而是写成确定性时序
（`metrics/accuracy.jsonl`），bug 模式按**复发频次**排优先级（`signals.md`），活动倒灌成
append-only 活动流（`LOG.md`）。

非目标（沿用 v1 plan §1）：不做满意度均值；不替代人在环复核；不在飞轮里改任何
TutorBot 运行时 authority（飞轮是观测者 + 记账者，不是 writer）。

## Cadence

**manual**（本阶段刻意不接调度）。先把门做到「确定性可信」（反自证三方 SHA 门 +
确定性主裁 + 异源判官降级），**调度是第二步**：门确定性可信后才接 `schedule` /
GitHub Action，否则把假绿放大违「反自证 > 一切」。详见 plan doc §V2 调度边界。

## Layout（shared brain 四层）

| 层 | 文件 | 作用 |
|---|---|---|
| charter | `domains/quality-flywheel/README.md`（本文件） | goal / cadence / 入口索引 / 红线 |
| metrics | `domains/quality-flywheel/metrics/accuracy.jsonl` | 确定性 collector 写的 6 维 fail_rate 时序（append-only） |
| signals | `domains/quality-flywheel/signals.md` | bug 模式去重 + 复发频次 → 边际杠杆排序 |
| LOG | `domains/quality-flywheel/LOG.md` | append-only 活动流（header 行 + 结论先行 + Refs） |

> 四件全部落在 `domains/quality-flywheel/`（committable，非 gitignored）。注意：门**运行时**
> 写的逐维证据 JSON（`*_result.json` / `gate_summary.json`）仍落 `artifacts/quality_gate/<ts>/`，
> 那是 gitignored 的运行产物，与本目录的 committed shared brain 区分开。

## metrics/accuracy.jsonl 契约（确定性 collector）

`accuracy_gate.py` 跑完每维 append 一行（脚本自算的数，**非 LLM**，pure observer，
失败也绝不影响门判定/退出码）。每行：

```json
{"ts": "<datetime.now isoformat>", "deployed_sha": "<container/origin sha>",
 "dim": "<daowu|huizhi|leak_boundary|sev_regression|forward_liveness|content_truth>",
 "fail_rate": <float|null>, "reproduced": <bool>, "conclusive": <bool>,
 "gate_verdict": "GO|BLOCK|INCONCLUSIVE"}
```

`gate_verdict` 与 `accuracy_gate.main()` 封板口径**完全一致的纯派生**（reproduced→BLOCK；
否则 conclusive→GO；全 inconclusive→INCONCLUSIVE），不是第二判定 authority。

## 入口索引（links）

代码门 authority（飞轮观测的对象，不在本目录）：
- `scripts/quality_gate/accuracy_gate.py` — 一键门（三方 SHA 反自证 + 6 维编排 + 封板判据 + 退出码）+ 本目录 metrics collector。
- `scripts/quality_gate/probes/_probe_common.py` — 共享基座（login/turn/终态读取/异源判官 + DEGRADED 降级契约）。
- `scripts/quality_gate/probes/dim_*.py` — 6 个确定性探针（daowu/huizhi/leak_boundary/sev_regression/forward_liveness/content_truth）。

方法论 / 历史（飞轮的上游）：
- `agent-skills/tutorbot-student-army-eval-loop/SKILL.md` — 学员军团 eval 闭环（§4 反自证元门、§6 维护协议、§7 模式库=signals 源）。
- `docs/plan/题目生命周期与助教运行时/2026-06-30-continuous-quality-flywheel-v1.md` — plan doc（含 V2 段：shared brain / 五红线闸 / 调度第二步）。

相关 memory（`[[slug]]` 双链，复利索引）：
- `[[false-success-root-cause-self-attestation-trap]]` — 反自证元门母原则（成功声明只信独立可证伪可重复终态）。
- `[[release-gate-runner-attest-only-what-it-exercises]]` — 只 attest 真实跑到的，别 borrowed-coverage。
- `[[dont-stop-at-handoff-continue-to-actual-fix-and-verify-live-final]]` — 核 live 终态非 unit 绿。
- `[[student-army-live-eval-method-and-findings]]` — 学员军团活体 eval 法。

## 红线（飞轮自身也守）

1. **LLM 仅附加非主裁**：metrics 写的全是确定性主裁的数；异源 judge 降级即 `JUDGE_DEGRADED` 不计 pass/fail。
2. **封板 = WEAK-GO，人盖 GO**：门只挡「确定性可复现的红」；GO 是结构判定，最终封板由人裁。
3. **隔离盒只 eval 不碰生产**：飞轮只读 `/messages` 终态 + 写本目录文件，绝不写 TutorBot 运行时 authority。
4. **narrow add 防并发扫**：飞轮的所有写都是纯新增（domains/ + metrics jsonl + LOG），不 `git add -A`。
5. **治本设计人在环**：metrics 的「红」是内容生产需求清单；回灌内容飞轮（采分点/教材编译）的设计由人裁，飞轮只暴露缺口。
