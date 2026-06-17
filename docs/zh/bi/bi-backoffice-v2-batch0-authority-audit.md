# BI 会员经营后台 v2 — Batch 0 Authority Audit

状态：Batch 0 交付物 v1
日期：2026-05-23
关联计划：`docs/plan/会员钱包计费与经营后台/2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md`

本文档是 Batch 0 的核心交付物，输出三件事：

1. 字段矩阵（每个一等事实 → 唯一 authority + 可信等级 + P0 可用性）
2. 账务异常检测规则草案
3. 性能风险与 5 主区原型的浏览器验收清单

> Batch 0 不引入产品 flag，不写业务事实；仅生成审计、字段矩阵、检测规则草案、`/bi-vnext` 静态原型。

## 1. Authority 与字段矩阵

### 1.1 会员身份与状态

| 字段 | Authority | 来源代码 / 表 | 可信等级 | P0 可用性 |
| --- | --- | --- | --- | --- |
| `user_id` | `MemberConsoleService` | `deeptutor/services/member_console/service.py` | A | 只读 + 检索 |
| `phone` | `MemberConsoleService` + auth identity | 同上 | A | 只读（脱敏可控） |
| `tier` (trial / vip / svip) | `MemberConsoleService` | `service.py:1394, 1677` | A | 只读 |
| `tier_expires_at` | `MemberConsoleService` | 同上 | A | 只读 |
| `risk_score` | `MemberConsoleService` 聚合 | 同上 | B | 只读，hover 必标可信等级 |
| `latest_session_at` | session store + `MemberConsoleService` | session_store | B | 只读 |
| `paid_at_first` / `paid_at_last` | wallet ledger + member_console | wallet_ledger 充值条目 | B | 只读，需对账确认 A 级 |

> `MemberConsoleService` 体量 4880 行，是事实唯一 authority。BI 前端只读不写。

### 1.2 钱包、充值与扣点

| 字段 | Authority | 来源 | 可信等级 | P0 可用性 |
| --- | --- | --- | --- | --- |
| `wallet_balance_points` | `WalletService` | `deeptutor/services/wallet/service.py:201 list_wallet_ledger` 聚合 | A | 只读，不在前端再算 |
| `ledger_event_id` | `WalletService` | `wallet_ledger` 表 | A | 只读 |
| `ledger_kind`（credit/debit/refund/manual） | `WalletService` | 同上 | A | 只读 |
| `idempotency_key` | `WalletService` | `service.py:177, 240, 350, 384` | A | 必须显示，用于异常去重 |
| `created_at` / `effective_at` | `WalletService` | 同上 | A | 只读 |
| `session_id` / `usage_event_id`（扣点上下文） | `WalletService` 元数据 | 同上 | B | 只读，缺失视为异常 |
| `refund_origin_ledger_id` | `WalletService` 元数据 | 同上 | B | P0 只读，P1 接退款工作流 |

### 1.3 套餐 catalog 与订单

| 字段 | Authority | 来源 | 可信等级 | P0 可用性 |
| --- | --- | --- | --- | --- |
| `package_id` / `name` / `points` / `price` | `MemberConsoleService._default_packages()` | `service.py:529` **hardcoded** | C | 只读，**P0 禁止生产编辑** |
| `package_features` | 同上 | 同上 | C | 只读 |
| `order_id` / `paid_amount` / `channel` | wallet_ledger 充值条目 + idempotency_key 元数据 | wallet_ledger | B | 只读，需 P1 拆出独立 `payment_orders` 表 |
| `invoice_status` | 未确认 canonical 表 | 待 audit | D | P0 隐藏入口或显示「尚未对账」 |
| `refund_status` | wallet_ledger refund 条目 | 同上 | B | 只读 |

> **关键风险**：套餐定义当前是后端默认 hardcoded，没有独立 `packages` 表。订单也没独立 `payment_orders`，全部在 wallet_ledger 中。Batch 0 决定：P0 套餐和订单全部**只读**，编辑入口禁用并显示「P1 实装中」。

### 1.4 会员对话

| 字段 | Authority | 来源 | 可信等级 | P0 可用性 |
| --- | --- | --- | --- | --- |
| `session_summary` | session store + summarizer | session_store | B | 默认展示 |
| `message_full_text` | session store | 同上 | A（事实层面） | **默认折叠**，查看必须选原因 + audit |
| `view_audit_record` | `member_console` 审计 | `member.py:336 /{user_id}/conversations/{session_id}/view-audit` | A | 必须写入 |

### 1.5 学习事实

| 字段 | Authority | 来源 | 可信等级 | P0 可用性 |
| --- | --- | --- | --- | --- |
| `learner_state` | learner state read model | `member.py:131 /{user_id}/learner-state` | A | 只读 |
| `mastery_summary` | construction grading read model | `deeptutor/services/learner_state/` | A | 只读 |
| `learning_evidence` | learning evidence read model | `deeptutor/services/construction_grading/learning_evidence.py` | A | 只读 |
| `heartbeat_jobs` | `member_console` | `member.py:139` | A | 只读 + 暂停/恢复（已存在） |

> BI 严禁写学习事实。任何"调整掌握度"都必须经 learner state authority。

### 1.6 反馈（多源）

| 来源 | Authority | 表 / Store | 可信等级 | P0 可用性 |
| --- | --- | --- | --- | --- |
| AI 消息反馈 | `FeedbackService` | `feedback_service.py` Supabase REST | A | **P0 接入** |
| 内测申请 | `InviteTestApplicationStore` | `public.invite_test_applications` | A | 已在 `/bi/invite-test/*` 路由 |
| 运营备注 | `MemberConsoleService` notes | `member.py:289 /{user_id}/notes` | A | 已存在写路径，P0 只读列表汇总 |
| 教研反馈 | 未确认 canonical | 待 P1 audit | D | P0 隐藏 |
| 系统质量事件 | observability / Langfuse | `bi_service.py` 汇总 | B | P0 只读 + 可信标 |

> 反馈中心 P0 仅接 AI 消息反馈 + 内测申请 + 运营备注汇总；不创建第二套反馈真相表。

### 1.7 操作审计与权限

| 字段 | Authority | 来源 | 可信等级 | P0 可用性 |
| --- | --- | --- | --- | --- |
| `audit_log` | `MemberConsoleService` audit | `member.py:382 /audit-log` | A | 只读 + 筛选 |
| `actor_id` | bi-admin-auth identity | `web/lib/bi-admin-auth.ts` | A | 必须随每个写动作传 |
| `idempotency_key`（admin write） | 待统一 middleware | 现仅 wallet 层有 | B | P0 写动作必须预留 header |
| `etag` / `version` | 待添加 | 当前无 | D | P0 写动作禁用直到补齐 |
| `undo_token` | 待添加 | 当前无 | D | P0 危险动作禁用 |

> 计划 §3.5 admin write safety 三条硬约束（idempotency_key / etag / undo_window）当前仅 wallet 有 idempotency；etag/version 与 undo 缺失。**Batch 0 结论：P0 只放低风险写（备注、跟进、AI 反馈 triage）；开通/撤销/补点等危险动作禁用**。

## 2. 账务异常检测规则草案

每条规则字段：`detected_rule_id`、`severity`、`detection_query`、`run_frequency`、`owner`、`p0_visibility`。

| `detected_rule_id` | severity | detection（SQL / service 入口） | 频率 | owner | P0 |
| --- | --- | --- | --- | --- | --- |
| `WALLET_DEBIT_WITHOUT_CONTEXT` | high | `wallet_ledger where ledger_kind='debit' and (session_id is null and usage_event_id is null)` 近 24h | hourly | wallet team | 顶部行动条 |
| `WALLET_CREDIT_WITHOUT_ORDER` | high | `wallet_ledger where ledger_kind='credit' and idempotency_key not like 'order:%' and metadata->>'channel' is null` 近 7d | hourly | finance ops | 行动条 |
| `WALLET_NEGATIVE_BALANCE` | critical | `sum(amount) group by user_id having < 0` | hourly | wallet team | 顶部行动条 + 阻断 |
| `WALLET_DUPLICATE_IDEMPOTENCY` | critical | `wallet_ledger group by idempotency_key having count(distinct amount) > 1` | hourly | wallet team | 行动条 |
| `MEMBER_TIER_EXPIRED_BUT_ACTIVE` | medium | `member where tier_expires_at < now() and status='active'` | daily | growth ops | 队列 |
| `PACKAGE_GRANT_WITHOUT_AUDIT` | medium | `wallet_ledger where ledger_kind='manual' and id not in (select target_id from audit_log)` 近 30d | daily | finance ops | 队列 |
| `REFUND_WITHOUT_REVERSAL` | high | `wallet_ledger refund 标记 但 refund_origin_ledger_id 对应原条目缺反向 debit` 近 30d | daily | finance ops | 队列 |
| `MANUAL_CREDIT_NO_OPERATOR` | high | `wallet_ledger where ledger_kind='manual' and metadata->>'actor_id' is null` 近 30d | hourly | wallet team | 顶部行动条 |
| `SESSION_NO_FEEDBACK_HIGH_COST` | low | `bi_service cost > X and session has no feedback` 近 7d | daily | quality ops | 反馈中心 |
| `INVITE_TEST_DUPLICATE_PHONE` | medium | `invite_test_applications group by phone having count > 1` 近 30d | daily | growth ops | 反馈中心 |

> 上述全部为草案。Batch 4 商品账务上线前，每条规则必须落到 `deeptutor/services/bi_service.py` 或 `member_console` 的 audit 函数中，并补对应 pytest。

## 3. 性能风险与样本压测计划

### 3.1 已识别巨石

| 文件 | 行数 | 风险 | Batch 2 处理 |
| --- | --- | --- | --- |
| `web/app/(workspace)/bi/BiPageClient.tsx` | 1109 | 一个文件挂 24 个组件，rerender 雪崩 | Batch 1 拆 shell；Batch 2 单独 CRM page |
| `deeptutor/services/bi_service.py` | 2772 | 多端口聚合，单点慢查询牵连 | 不动 authority，Batch 3 加 read model 缓存 |
| `deeptutor/services/member_console/service.py` | 4880 | 默认 packages hardcoded；audit 写在同文件 | 不拆，标 owner |

### 3.2 5 万会员查询风险（待 EXPLAIN ANALYZE）

需要在 Batch 0 末或 Batch 2 起跑：

- `member_console.list_members` 14 维筛选（tier / risk / paid_at / last_active / region / etc）的 p95。
- 全局手机号 `LIKE '%xxx%'` 查询是否走 trigram 索引。
- 单会员对话全文消息量上限（取 P99 会员）。

降级方案：若 p95 > 1s，则禁用部分高维度筛选，并加 cursor pagination + 列裁剪。

### 3.3 overview API 性能要求

计划 §Batch 3 验收：**overview API p95 不得走 `get_member_360()`**。Batch 0 已确认 `bi.py:49 /overview` 与 `member.py:123 /{user_id}/360` 是两条路径。Batch 3 实装时：

- overview 走 `bi_service` 预聚合，不进 `get_member_360`。
- 学员 360 抽屉单独按需调用。

## 4. /bi-vnext 静态原型验收清单

`/bi-vnext` 是 Batch 0 的静态原型路由，**不接真实业务数据**，仅用于：

- 5 主区信息架构评审：经营总览 / 会员运营 / 商品账务 / 反馈中心 / 系统运维。
- 桌面 1440×900、iPad 横屏 1024×768、移动 375×812 视觉评审。
- 顶部全局搜索、侧边导航、卡片密度、表格密度、抽屉、风险队列的形态评审。

验收点：

- [ ] 5 个一级导航固定顺序：经营总览 → 会员运营 → 商品账务 → 反馈中心 → 系统运维。
- [ ] 对话回顾归在「会员运营 → 学员 360」抽屉，不作为一级 tab。
- [ ] 账务异常作为「商品账务」顶部行动条 + 右侧队列，不作为普通 tab。
- [ ] 系统运维含成本质量、数据可信、操作审计、权限审计、上线面板。
- [ ] 无卡片套卡片。
- [ ] 桌面高密度（默认表 7 列、行高 ≤ 40px）。
- [ ] 移动只保留：经营总览快照、会员搜索、风险队列入口。
- [ ] icon-only 按钮含 aria-label（用 prototype 数据假数据演示）。
- [ ] 关闭原型 flag（不上线）后 `/bi` 旧入口不受影响。

## 5. 不确定项与 P0/P1 切分结论

| 模块 | P0 | P1 |
| --- | --- | --- |
| 套餐 catalog | 只读 | 编辑流 + 历史快照 |
| 订单 / 充值 | 只读 + 异常队列 | 独立 `payment_orders` 表 + 对账工作流 |
| 钱包 | 只读 + 低风险 manual credit（需补 etag/undo） | 全量退款 / 补偿工作流 |
| 对话 | 摘要展示 + 全文审计查看 | 跨会话搜索、批量审计 |
| 反馈 | AI 反馈 + 内测 + 备注 | 教研、运营、质量四源聚合 |
| 会员动作 | 备注、跟进、加入队列、AI 反馈 triage | 开通/撤销/补点（需 etag+undo） |
| 系统运维 | 成本只读、可信中心、操作审计、导出审计 | 复杂权限矩阵、暗色模式、自助 BI |

## 6. Batch 0 完成判定

- [x] 字段矩阵覆盖 1.1 ~ 1.7。
- [x] 账务异常规则草案 ≥ 10 条，含 owner 与频率。
- [x] 性能风险与样本压测计划列出。
- [x] /bi-vnext 静态原型路由验收清单输出。
- [ ] /bi-vnext 路由落地（见 Batch 0 代码任务）。
- [ ] 桌面 / iPad / 移动浏览器截图评审（见 Batch 1 visual smoke 联调）。

> 真实压测（EXPLAIN ANALYZE / 全文消息量）放到 Batch 2 开始时落地，不阻塞 Batch 0 / Batch 1 的 UI 推进。
