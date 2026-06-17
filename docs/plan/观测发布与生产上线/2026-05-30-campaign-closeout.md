# 2026-05-30 上线就绪与系统成熟度战役 — 收线纪要

> **类型**：Campaign Closeout（收尾纪要）
> **状态**：Main campaign Done（2026-05-30）。剩余为 backlog 排期 + 人工/生产动作。
> **单一权威**：本文件只做"已闭环清单 + 审合链 + backlog 指针"的地图，不复制各计划正文；细节回各主线文档。

## 0. 一句话

从"上线前审查裁决 **NO-GO**"一路推到 **main HEAD `8269c527`**：上线前必清全部清零并落 main，系统成熟度从 **≈L1.67/5 升到 ≈L2**。剩下的全是 backlog 排期 + 人工门（P4 微信、go-live 翻计费 flag），无新的大仗。

## 1. 已闭环并落 main

| 域 | 内容 | 证据 |
| --- | --- | --- |
| 上线前必清（质量审计 BLOCKER/HIGH） | B1 计费原子化扣费（走 `apply_wallet_mutation` RPC，挂 `DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED` **默认 OFF**）、H3 start-turn 硬余额门、H4 Σdelta 对账交叉校验、H1/H2 vision 第二聊天 WS 物理下线 + 反射式 websocket 白名单 guard、H9 mobile `/chat/start-turn` 长度上界+限流、H10 撤 `public.wallets` 的 anon/authenticated DML grant | PR #75–#82 + 后续；详见 [2026-05-30-system-maturity-audit.md](2026-05-30-system-maturity-audit.md) |
| 生产 RLS 加固（已 apply 生产） | P5 `user_profiles`/`user_stats` 的 `USING(true) TO public` 收口为 owner-scoped + service_role-only、撤 anon/auth grant（28→0 行）；H10 `public.wallets` grant 14→0 | live RLS audit 已验证；记忆 [[luban-prelaunch-gate-status]] |
| 计费上线 runbook | dry-run 验证完备、flag 默认 OFF（内测零变动）；86 个历史污染钱包待 go-live 当天按 `balance=Σdelta` 校正（净 +8928 点，已定豁免追扣） | [../../runbook/2026-05-30-billing-go-live-runbook.md](../../runbook/2026-05-30-billing-go-live-runbook.md) |
| 语义路由可观测 | 误切率基线（暴露 instrumentation gap，裁决维持 primary、未证实安全）+ 决策遥测补码（就地捕获 raw_input / drove_route / is_default_template，闭合 3 断点） | 基线 results.md + runbook（INDEX 生产部署线）；遥测 PR #84 |
| 系统成熟度接线批 | 12 维审计（≈L1.67/5）+ 本周低成本接线落地 | 见 §2 审合链 |

## 2. 成熟度接线批 — 审合链（strict 全程，无跳红灯/无 force-merge）

| 序 | PR | 内容 | squash | 提级 |
| --- | --- | --- | --- | --- |
| 1 | #88 | W1：test-summary yousen gate + `docs/**` trigger + security-scan(advisory) | `25980c99` | M9/M10 L1→L2、M6 |
| 2 | #87 | 系统成熟度审计报告 doc | `c849599d` | — |
| 3 | #85 | W2 deploy-gate + W3 wallet Σdelta 每日 cron + W6 flag 快照补全 | `9d8a0153` | M6 L1→L2、M3/M5/M7 +0.5 |
| 4 | #86 | W4 readiness hook（写 control_plane）+ W5a 启动 env fail-fast + W5b 删 legacy chat WS | `8269c527` | M1/M11 +1、M8 +0.5、M12 +0.5 |

闭环验证：#88 先合让 `docs/**` 进 paths → #87（docs-only）随后自动触发 required check 并通过，**不再需 admin-override**——正是 W1 要堵的 trigger-path 缺口。

## 3. 待办 backlog（按处置分类）

**A — 自主引擎可做（已派自主 backlog workflow）**：M10 安全债 triage（41 个 pre-existing bandit B310/B324/B608，修真项 / `# nosec` 假阳性，清完把 security-scan 翻 blocking）、`test_training_loop_uses_latest_attempt` IndexError §5 根因、低风险接线/死代码/naive datetime/config 收口。

**B — 结构性投资（需排期，自主引擎只出计划文档）**：M4 容量横扩（全局 admission + Postgres session store + 多 worker + 压测基线，见 active-turn-capacity 计划）、M5 Supabase PITR + 恢复演练 + migration down、M1 真实 Prometheus/Alertmanager + 分位 + 生产开 Langfuse。

**C — 单独谨慎一轮（高风险）**：W1 全量 pytest 树（smoke allowlist → pytest 全目录，需逐一甄别 ~280 测试外部依赖失败 + marker 隔离 + no-silent-cap log）。

**D — 人工/生产授权（代码无法替）**：
- **P4 微信**：旧基础库（2.32.2）真机回归 onLaunch 不崩 + MP 后台提交《用户隐私保护指引》审核（appid `wx6d4fbd3776ea7d4d`）。
- **Go-live 当天**：按计费 runbook S0→S5——先 `balance=Σdelta` 校正 86 钱包 → audit 归零 → 翻 `DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED=true` + `docker compose up -d --force-recreate`（`docker restart` 不重载 env_file）→ 真机扣费 smoke → 异常翻回 OFF 回滚。
- 在飞：关注线 PRD（Task5 订正→复测 + Task7 confidence 门@assessment 边界 + G3/Task4 intent 选择器，单独窗口）。

**待审合 PR**：#84（router 遥测，turn/route 链路，draft 转 ready 后审）、#89（docs-reconciliation，#88 后已解封）。

## 4. 关键记忆指引

- [[luban-prelaunch-gate-status]] — 上线前 gate + 无数据泄露/越权 BLOCKER 结论
- [[luban-maturity-audit]] — 成熟度 L1.67/5 记分卡 + 路线图
- [[aliyun-fast-reload-rebuilds-frontend]] — `redeploy_aliyun_fast.sh` 实测重建前端；`deeptutor/.env` 来源
- [[luban-kb-prod-access]] — Supabase DB_URL 直连边界

## 5. 纪律红线（本战役全程遵守，后续继续）

单一权威（`/api/v1/ws` 唯一聊天 WS、TutorBot 唯一执行身份、计费唯一原子 RPC 权威）；§3 surgical；§5 根因；PR 不自动合并、敏感改动指挥官审；生产写仅限授权动作（RLS migration / 翻 flag 走 runbook）；§3.7 阿里云写边界 `/root/deeptutor`。
