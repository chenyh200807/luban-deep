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

**daily（机制已建，未激活）**。调度机制（`scripts/quality_gate/scheduled_run.py` +
`.github/workflows/accuracy-gate-scheduled.yml`）已经落地，但 workflow 里的
`schedule:` cron 行**当前保持注释**，只留 `workflow_dispatch` 可手动触发——因为
plan doc §V2.5 定的两个调度触发条件**截至本次更新都还没满足**：①从未有过一次
三方 SHA 对齐的 `--runs 3` 全量 `GO`（唯一一次三方对齐的全量跑 `content_truth`
复现 → `BLOCK`）；②`metrics/accuracy.jsonl` 目前样本量不足以看趋势。owner 需要
先拿到一次真 `GO` 证据，再手动取消 workflow 里的 cron 注释。详见下面「调度
(Scheduled Runs)」小节 + plan doc §V2.6。

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

## 调度 (Scheduled Runs)

持续质量飞轮 V2 第二步。`scripts/quality_gate/scheduled_run.py` 是 `accuracy_gate.py`
的薄封装：① SHA 门前置检查(不齐 -> `skipped:misaligned`, 不跑任何探针, 不花钱)
② 对齐则 subprocess 跑 `accuracy_gate.py --runs 3` ③ 读 `gate_summary.json` 产
WEAK-GO 报告(`artifacts/quality_gate/scheduled/<ts>/report.md`, 六维矩阵 + 趋势,
样本不足如实说不足) ④ 给本文件同目录的 `LOG.md` 追加一行。判定逻辑单一权威仍在
`accuracy_gate.py`，本脚本不重新实现任何判据，退出码原样透传(`0`=结构 GO 待人盖
封板 / `2`=SHA 门不齐 STOP / `3`=复现阻断 BLOCK / `4`=无法判定)。

`.github/workflows/accuracy-gate-scheduled.yml` 是外层调度器：`workflow_dispatch`
可随时手动触发；`schedule:` cron 行**当前注释**，取消注释前请先确认上面 Cadence
段说的两个触发条件已经满足。exit 2(misaligned)只打 warning 不算失败；exit 3
(BLOCK)job 失败 + 告警(webhook 或开 issue，只报告不自动修)；exit 4(inconclusive)
job 失败但不告警(避免把"判不出"和"真的红"混进同一通知噪声)。**自动化只到产出
WEAK-GO 报告，封板 = 人在环，workflow 不会、也不应该自动宣布"调度成功"。**

### Secrets 清单(需要 owner 去 GitHub repo secrets 里加)

| Secret | 必需? | 用途 | 缺失时的行为 |
|---|---|---|---|
| `WECHAT_QA_USERNAME` / `WECHAT_QA_PASSWORD` | 必需 | 映射成 `DEEPTUTOR_QA_USERNAME`/`DEEPTUTOR_QA_PASSWORD`，探针登录用 | 登录失败 -> exit 4(无法判定) |
| `ALIYUN_SSH_PRIVATE_KEY` / `ALIYUN_SSH_HOST` | 必需 | SHA 三方门要 SSH 读 host `.env` + container env(别名 `Aliyun-ECS-2`) | workflow 直接 `::error::` 停在配置步骤 |
| `DEEPSEEK_API_KEY` / `BIGMODEL_API_KEY` | 可选 | 异源判官(附加，非主裁) | 缺则 `JUDGE_DEGRADED` 降级，不阻断门 |
| `QUALITY_GATE_WEBHOOK_URL` | 可选 | BLOCK 时飞书/企微 webhook 告警 | 缺则退化为 `gh issue create`(用默认 `GITHUB_TOKEN`，不需要额外配) |
| `DEEPTUTOR_QA_BASE_URL` | 可选 | 覆盖探针打的 base url | 缺则用 `accuracy_gate.py` 默认值 `https://test2.yousenjiaoyu.com` |

**不需要 `DEEPTUTOR_EVAL_BYPASS_KEY`**：核实过 `accuracy_gate.py`/`probes/` 当前
不读这个变量(它是小程序真机 automator 场景绕 billing 用的，和这条走公网 HTTP
探针的门是两条不同路径)，除非未来新增探针要用，否则不必配。

### post-deploy 集成(可选，默认不接)

`scripts/deploy_aliyun.sh` 跑完后，owner 可以手动或在自己的发布流程里另起一步做
"部署即复核"：

```bash
cd <repo>; set -a; source .env; set +a
export DEEPTUTOR_QA_USERNAME="$WECHAT_QA_USERNAME" DEEPTUTOR_QA_PASSWORD="$WECHAT_QA_PASSWORD"
python scripts/quality_gate/scheduled_run.py --runs 3
```

**不修改 `deploy_aliyun.sh` 本身**——每次部署自动跑门会拖慢发布 + 产生额外 billable
调用，是否接入由 owner 决定。

## 红线（飞轮自身也守）

1. **LLM 仅附加非主裁**：metrics 写的全是确定性主裁的数；异源 judge 降级即 `JUDGE_DEGRADED` 不计 pass/fail。
2. **封板 = WEAK-GO，人盖 GO**：门只挡「确定性可复现的红」；GO 是结构判定，最终封板由人裁。
3. **隔离盒只 eval 不碰生产**：飞轮只读 `/messages` 终态 + 写本目录文件，绝不写 TutorBot 运行时 authority。
4. **narrow add 防并发扫**：飞轮的所有写都是纯新增（domains/ + metrics jsonl + LOG），不 `git add -A`。
5. **治本设计人在环**：metrics 的「红」是内容生产需求清单；回灌内容飞轮（采分点/教材编译）的设计由人裁，飞轮只暴露缺口。
