# Implementation Plan：Supabase 钱包唯一权威体系

> 2026-04-19 实施注记：
> 上游 PRD 中的“`users.id` UUID”在当前线上库不能机械理解为 `public.users.id`，因为该字段实际是 legacy `text`。
> 本实施计划统一以 `public.wallets.user_id` 代表 canonical wallet user UUID，并围绕这条主键链落库。

## 1. 文档信息

- 文档名称：Supabase 钱包唯一权威体系 Implementation Plan
- 文档路径：`/doc/plan/2026-04-19-supabase-wallet-single-authority-implementation-plan.md`
- 创建日期：2026-04-19
- 状态：Draft v1
- 上游 PRD：
  - [2026-04-19-supabase-wallet-single-authority-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/plan/2026-04-19-supabase-wallet-single-authority-prd.md)

## 2. 目标

这份 implementation plan 的目标不是再次讨论方向，而是把上游 PRD 拆成**可以实际执行的工程任务序列**。

本计划只回答四类问题：

1. 先做什么，后做什么
2. 每一步改哪些文件
3. 每一步如何验证
4. 哪些 gate 不过就绝不能进入下一步

## 3. 执行原则

1. 先收身份 authority，再切钱包读链，再切钱包写链。
2. 不允许为了“先跑起来”长期保留新旧两套真钱相源并行写。
3. 灰度期允许 shadow compare，不允许静默 fallback 到旧 authority。
4. 所有生产级钱包写入都必须带 `idempotency_key`。
5. 所有阶段都必须留下证据产物，不能靠口头判断“应该没问题”。

## 4. 总体执行顺序

严格按以下顺序执行：

1. `WP1 Schema 与权限基线`
2. `WP2 身份归一化层`
3. `WP3 统一 wallet service`
4. `WP4 移动端读链切换`
5. `WP5 写链切换与旧 authority 退役`

任何跳步执行都视为高风险。

## 5. 当前基线事实

实施前必须承认以下现实：

1. Supabase `wallets` 真实存在，且已有线上数据。
2. Supabase `wallet_ledger` 当前不存在。
3. 当前移动端 `/billing/points`、`/billing/wallet`、`/billing/ledger` 仍走 `member_service`。
4. 当前鉴权直接信 token 内的 `uid/sub`，没有 alias -> UUID 归一化层。
5. 当前会话、notebook、learner_state、heartbeat 等状态仍大量按 legacy `user_id` 挂接。
6. 小程序本地仍缓存 `auth_token` 和 `auth_user_id`。

因此这不是单纯的钱包表改造，而是：

**身份归一化 + 钱包 authority 收权 + 状态所有权迁移**

## 6. 工作包总览

| WP | 目标 | 主落点 | 退出门槛 |
| --- | --- | --- | --- |
| `WP1` | 把钱包 schema 和权限纳入受控治理 | `supabase/migrations/`, wallet store | `wallet_ledger` 可安全读写 |
| `WP2` | 让鉴权边界稳定产出 UUID 用户 | auth dependency, mobile auth, identity layer | alias 全部稳定映射 |
| `WP3` | 建立唯一 wallet service | `deeptutor/services/wallet/` | 幂等/并发/事务能力通过 |
| `WP4` | 先统一读链，完成 shadow compare | mobile router + 小程序页面 | 新旧读链 diff 达 gate |
| `WP5` | 再切写链，退役旧 authority | 充值/扣点/后台补点入口 | 所有生产写入只经 ledger |

## 7. WP1：Schema 与权限基线

### 7.1 目标

把钱包 schema、索引、唯一约束、权限模型纳入本仓显式治理，并为后续 wallet service 提供可验证的持久化基线。

### 7.2 前置条件

1. 已确认生产 Supabase 项目和 schema。
2. 已获取 schema 只读快照能力。
3. 已确认 staging 或影子环境可用于 dry-run。

### 7.3 任务拆解

#### T1.1 导出现有钱包基线

落点：

1. 新增脚本：`scripts/export_wallet_preflight_snapshot.py`

产物：

1. `preflight_snapshot.sql`
2. `schema_snapshot.sql`
3. `wallets_sample.json`

验证：

1. 能导出 `wallets`
2. 能导出 `users`
3. 能导出 `v_members`

#### T1.2 建立受控 migration

落点：

1. 新增 migration：`supabase/migrations/20260419xxxxxx_wallet_authority_phase1.sql`

内容：

1. 创建 `wallet_ledger`
2. 给 `wallets` 补齐必要约束
3. 补索引
4. 补注释和最小审计字段

验证：

1. migration 可在影子环境执行成功
2. 重复执行不会破坏已有表

#### T1.3 确认权限与 RLS

落点：

1. 新增文档或附录：`doc/plan/2026-04-19-supabase-wallet-rls-appendix.md`
2. 如需脚本，新增：`scripts/dump_wallet_rls.py`

内容：

1. 记录 `wallets` / `wallet_ledger` 的 RLS policy
2. 明确服务端写入凭证模型
3. 明确是否必须引入 `SUPABASE_SERVICE_ROLE_KEY`

验证：

1. 产出 `rls_policy_dump.sql`
2. 产出 `wallet_write_probe.json`
3. 产出 `rollback_probe.json`

#### T1.4 建立 staging 级事务探针

落点：

1. 临时脚本：`scripts/probe_wallet_transaction.py`

内容：

1. 测试一笔“插 ledger + 更新 wallet”的原子事务
2. 测试失败回滚

验证：

1. 事务成功时 wallet 与 ledger 同步变化
2. 事务失败时两者都不落脏数据

### 7.4 建议新增/修改文件

1. `supabase/migrations/20260419xxxxxx_wallet_authority_phase1.sql`
2. `scripts/export_wallet_preflight_snapshot.py`
3. `scripts/dump_wallet_rls.py`
4. `scripts/probe_wallet_transaction.py`
5. `doc/plan/2026-04-19-supabase-wallet-rls-appendix.md`

### 7.5 最小验证

1. `wallet_ledger` 在影子环境存在
2. `wallets` 约束、索引、更新时间策略被确认
3. 服务端具备安全稳定写入路径

### 7.6 退出门槛

1. `wallet_ledger` 可读写
2. RLS/权限模型明确
3. 事务探针通过
4. dry-run 环境准备就绪

## 8. WP2：身份归一化层

### 8.1 目标

让所有后续钱包相关请求在进入业务层之前，都被归一化到唯一 `users.id` UUID。

### 8.2 前置条件

1. `WP1` 已完成
2. 已确认 token issuer 基线
3. 已确认 alias 字段来源

### 8.3 任务拆解

#### T2.1 盘点身份来源

落点：

1. 新增脚本：`scripts/audit_wallet_identity_inventory.py`

内容：

1. 汇总 `identifier / phone / wx_openid / wx_unionid / legacy user_id / external_auth_user_id`
2. 生成 alias 冲突清单

产物：

1. `identity_inventory.csv`
2. `alias_coverage.csv`
3. `alias_conflicts.csv`

验证：

1. 活跃用户样本有完整映射报告
2. 高价值用户有专项清单

#### T2.2 明确 identity store 方案

落点：

1. 若现有 `users` 足够，更新设计说明
2. 若不足，新增 migration：`supabase/migrations/20260419xxxxxx_user_identity_aliases.sql`

内容：

1. 决定是否引入 `user_identity_aliases`
2. 写死冲突规则与人工复核条件

验证：

1. alias -> UUID 可唯一解析
2. 冲突用户自动阻断，不自动迁移

#### T2.3 建立服务端 identity resolution 层

落点：

1. 新增：`deeptutor/services/wallet/identity.py`
2. 修改：[auth.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deeptutor/api/dependencies/auth.py)
3. 修改：[mobile.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deeptutor/api/routers/mobile.py)

内容：

1. 将 legacy token `uid/sub` 解析为 UUID
2. 对影子 ID 命中做 hard fail
3. 统一服务端 user resolution 入口

验证：

1. canary 用户 token 解析结果只出现 UUID
2. 影子 ID 命中被阻断

#### T2.4 token 重签发与客户端刷新

落点：

1. 修改：[service.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deeptutor/services/member_console/service.py)
2. 修改：[auth.js](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview/packageDeeptutor/utils/auth.js)
3. 修改：[app.js](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview/app.js)
4. 修改：[login.js](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview/packageDeeptutor/pages/login/login.js)
5. 对应修改 `wx_miniprogram/` 同类文件

内容：

1. 登录成功后只签发 UUID token
2. 定义旧 token 兼容窗口
3. 定义强制刷新或强制重登策略
4. 统一 `auth_user_id` 的 UUID 语义

验证：

1. 新登录用户本地只缓存 UUID
2. 旧 token 用户能被正确刷新或被要求重登

#### T2.5 迁移 owner_key 与本地状态

落点：

1. 修改：[sqlite_store.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deeptutor/services/session/sqlite_store.py)
2. 修改：[sessions.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deeptutor/api/routers/sessions.py)
3. 修改：[question_notebook.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deeptutor/api/routers/question_notebook.py)
4. 修改：[unified_ws.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deeptutor/api/routers/unified_ws.py)
5. 修改：[service.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deeptutor/services/learner_state/service.py)
6. 修改：[runtime.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deeptutor/services/learner_state/runtime.py)
7. 必要时新增脚本：`scripts/migrate_wallet_identity_ownership.py`

内容：

1. 迁移 session owner_key
2. 迁移 notebook owner_key
3. 并档 learner_state 本地目录
4. 并档 heartbeat / 学习计划引用

验证：

1. 迁移前后历史会话可访问性一致
2. learner_state / heartbeat / 计划不丢失
