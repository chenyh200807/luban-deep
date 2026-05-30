# 在途 PR/分支盘点 + 可合并队列 + 解纠缠方案

| 字段 | 值 |
| --- | --- |
| 日期 | 2026-05-30 |
| 类型 | Consolidation / Merge Queue（只读盘点 + 安全合并） |
| 状态 | v1 |
| 纪律 | AGENTS §3 Surgical + §3.6 分支纪律；**不 force-rewrite 共享分支、不擅自合敏感 PR（turn/route/财务/契约/runtime/deploy 留指挥官）** |
| main 分支保护 | required checks = `Contract Guard` + `Test Summary`，strict=true，required reviews=0 |

---

## 0. 执行摘要
4 个开着的 PR：#84（我的，draft，sensitive）、#85/#86（并发会话，CI 绿但触发 deploy/wallet/runtime 敏感链路）、#87（并发会话，纯 docs 但 BLOCKED——docs-only 未触发 required checks）。**按 strict 纪律，本轮安全自动合并数 = 0**：sensitive 的留指挥官，#87 BLOCKED 不做 admin override。远端 `docs/plan-reconciliation` 实为干净 docs；"关注线代码"是并发会话**未推送**的本地工作，不碰。

---

## 1. 开着的 PR 全景

| PR | 分支 | base | draft | CI | 改了什么 | 风险 | 处置 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **#84** | feat/semantic-router-decision-telemetry | main | DRAFT | BLOCKED(draft) | semantic_router 决策遥测（orchestrator 捕获 + turn_runtime 落 internal event + report --telemetry + 纯函数）；212 回归绿 | **高（turn/route 链路）** | **指挥官审**，转 ready 后合 |
| **#85** | maturity/ci-gates-w2w3w6 | main | ready | **CLEAN/全绿** | `.github/workflows/deploy-gate.yml`、`wallet-consistency-cron.yml`、`release_lineage.py`(flag snapshot)、test | **中（deploy gate + wallet audit cron）** | **指挥官审**（碰发布门 + 财务域 audit）；附加 CI/观测，可快批 |
| **#86** | maturity/runtime-w4w5 | main | ready | **CLEAN/全绿** | `deeptutor/api/main.py`(readiness hook + startup env fail-fast)、`scripts/redeploy_aliyun_fast.sh` | **中-高（runtime 启动 + deploy 脚本）** | **指挥官审**（改 runtime 启动行为 + 部署脚本） |
| **#87** | docs/maturity-audit-report | main | ready | **BLOCKED（0 checks）** | `docs/plan/2026-05-30-system-maturity-audit.md` + `INDEX.md`(1行) | **低（纯 docs）** | 内容低风险，但 **BLOCKED**：docs-only 未触发 `Contract Guard`/`Test Summary`，strict 门下永久 BLOCKED。**不 admin override**；建议指挥官 override 合并或让 CI 对 docs 路径放行 |

> 另：`docs/plan-reconciliation-2026-05-30` 已 push（2 个 docs commit：`beca10a6` reconciliation/decision/runbook/diagnosis、`5bb26cd5` sr baseline runbook/results）但**尚无 PR**。纯 docs，建议开 PR（同样会因 docs-only 命中 BLOCKED 门）。

## 2. 可合并队列（建议指挥官审合顺序）

1. **#85**（CI/观测/audit 附加，全绿）— 最独立、最易审；合前确认 deploy-gate.yml 不会卡住既有发布流程、wallet-consistency-cron 是只读 audit（非财务写）。
2. **#86**（runtime readiness + startup fail-fast）— 改 `main.py` 启动路径，需确认 fail-fast 不会误杀正常启动；deploy 脚本改动需对照 §3.7。
3. **#87 + docs/plan-reconciliation**（纯 docs）— 两者都改 `INDEX.md`（#87 改 1 行、reconciliation 改 15 行，**不同区域、大概率自动可合**）。建议先合 reconciliation 再合 #87（或反之，第二个 rebase）。docs BLOCKED 门需 override 或 CI 放行。
4. **#84**（semantic_router 遥测）— 转 ready 后审；212 回归证明判决零变化、additive、PII 安全。

## 3. 分支解纠缠方案

**现状澄清**：远端 `docs/plan-reconciliation-2026-05-30` 实为**干净 docs**（仅我 2 commit）。此前观察到的"docs + 关注线代码 + 他会话 commit 混合"是**本地视图**——并发会话的关注线代码（`88c9400b` notebook G1 轻路径、`0b5392a4`/`1b9e283b` 关注线加权/read-side、`85f40b09`/`e62ff422` 学员画像 v0.2 docs+mockup）**未推送到任何远端分支**，存在于并发会话本地工作树。

**方案（推荐给并发会话执行，本窗口不碰其未推工作）**：
- 关注线代码（Task2/3/G1）→ 用 **#84 同款 cherry-pick-to-clean-base 手法**：从 `origin/main` 起独立 `feat/learner-state-focus-line` 分支，cherry-pick 关注线 commit，开独立 PR；学员画像 docs/mockup 留独立 docs PR。每块可独立审/回滚。
- **铁律**：cherry-pick 只从**已 push** 的 commit 摘；并发会话未推的工作树由该会话自己整理，本窗口不动、不 force-push 任何共享分支。
- #84 已完成此解纠缠（已从被并发 commit 污染的栈 cherry-pick 到 clean base `b6baa050`，force-push 仅作用于我自己刚建、无人协作的分支）。

**陈旧分支（merged/stale，cleanup 候选，留 owner 决定，本窗口不删他人分支）**：
`fix/billing-enforcement-b1-h3`、`fix/h4-billing-audit-and-h9-mobile-limits`、`fix/orphaned-turn-startup-sweep`、`fix/resource-amplification-hardening`、`fix/retire-vision-ws-and-ws-guard`、`fix/rls-harden-user-tables`、`fix/rls-harden-wallets`（均对应已合 main 的 #75–#82，内容已在 main，分支可清）；`codex/*` 6 个分支落后 88–135 commit、无 PR，陈旧。

## 4. 本轮已执行的安全项
**安全自动合并数 = 0。** 理由：#85/#86 CI 绿但触发敏感链路（deploy/wallet/runtime）→ 留指挥官；#87 与 docs-reconciliation 纯 docs 但 **BLOCKED**（docs-only 未满足 strict required checks）→ 不做 admin override。无 PR 同时满足"CI绿 ∧ 独立低风险 ∧ 非敏感 ∧ mergeable"，故按纪律不合。

## 5. Backlog（登记，先不修）
- **预存红测试**：`tests/services/learner_state/test_learning_report_read_model.py:667` `test_training_loop_uses_latest_attempt_not_any_past_correct_signal`（IndexError）。与本轮改动无关的既有失败，登记待修，不在本 consolidation 范围内处理。

---

## 6. 给指挥官的建议审合顺序
**#85 → #86 → (docs-reconciliation + #87) → #84**。理由：先落最独立的 CI/观测附加（#85），再审 runtime 启动改动（#86），docs 两条一起处理 INDEX 顺序，最后审 turn/route 的 #84。docs 的 BLOCKED 门需你 override 或调 CI 对 `docs/**` 路径放行。

*本报告为只读盘点产物；未 force-push 共享分支、未合并敏感 PR、未触碰并发会话未推送的工作。*
