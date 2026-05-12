# Supabase 钱包 RLS 与写入凭证附录

## 1. 目标

这份附录只回答一件事：

**为了让 `users.id + wallets + wallet_ledger` 成为唯一钱包 authority，哪些角色可以读，哪些角色可以写，以及生产写链到底应该拿什么凭证。**

## 2. 当前建议结论

在当前条件下，最稳妥的方案是：

1. `wallets` / `wallet_ledger` 不允许客户端直写。
2. 小程序和 Web 前端只调用 Deeptutor 后端 API，不直接拿 Supabase key 操作钱包表。
3. 生产钱包写链由服务端统一 wallet service 发起。
4. 服务端真正的原子写入路径优先使用 `DATABASE_URL` / `SUPABASE_DB_URL` 直连 Postgres 事务。
5. `SUPABASE_SERVICE_ROLE_KEY` 作为服务端 admin 能力使用，用于 schema 核查、影子对账、应急读写或只走 REST 的运维工具；它不是客户端能力。

## 3. 为什么不能只靠 REST admin key

只靠 `SUPABASE_SERVICE_ROLE_KEY + PostgREST` 做两次请求：

1. 先插 `wallet_ledger`
2. 再更 `wallets`

这两步之间没有数据库级原子事务保证。

这意味着：

1. 网络抖动时可能只成功一半。
2. 重试时会把问题变成幂等和补偿判断，不是根治。
3. 即使 ledger 设计正确，也会因为写链不是单事务而留下不一致窗口。

所以：

**`SUPABASE_SERVICE_ROLE_KEY` 是必要的 admin 凭证，但不是完整的钱包事务方案。**

## 4. 推荐权限模型

### 4.1 客户端

客户端：

1. 不直接访问 `wallets`
2. 不直接访问 `wallet_ledger`
3. 不持有 service-role key

### 4.2 Deeptutor 服务端

服务端：

1. 负责解析身份并归一化到 `users.id`
2. 负责所有余额增减
3. 负责所有 ledger 查询 DTO
4. 负责幂等和错误语义

### 4.3 Supabase

Supabase：

1. `wallet_ledger` 承担唯一事实层
2. `wallets` 承担唯一余额投影
3. RLS 默认对非服务端主体收紧
4. 约束、索引、外键和 check 负责守住底线

## 5. RLS 实施建议

### 5.1 `wallet_ledger`

建议：

1. 开启 RLS
2. 默认不向 anon/authenticated 暴露写权限
3. 如果未来确需前台自助账单查询，也应通过 Deeptutor 后端代查，而不是直接放开表级 select

### 5.2 `wallets`

建议：

1. 保持余额表只作为投影层
2. 不向客户端开放 update/insert/delete
3. 是否允许直接 select，需要以真实流量依赖审计为前提；在审计完成前不要贸然假设线上没有直连读

## 6. 写入凭证分层

### 6.1 必选

1. `DATABASE_URL` 或 `SUPABASE_DB_URL`
   - 用于服务端钱包事务
   - 这是验证“ledger + wallet 同事务”的关键前提

### 6.2 强烈建议保留

1. `SUPABASE_SERVICE_ROLE_KEY`
   - 用于 admin 只读核查
   - 用于 Preflight / RLS / Shadow Compare / Break-glass 操作

### 6.3 不应作为生产真钱包写链唯一依赖

1. 仅 `SUPABASE_KEY`
2. 仅前端 token
3. 仅多次 REST 请求拼接的“伪事务”

## 7. 当前不确定性与验证方法

当前仍需验证的点：

1. 线上 `wallets` 现有 RLS policy 是否已被其他表面直接依赖
2. 线上是否已有任何生产写链维护 `wallets.version`
3. 线上 `wallets` 是否已存在违反 `frozen_micros <= balance_micros` 的脏数据

验证方式：

1. 运行 `scripts/dump_wallet_rls.py`
2. 运行 `scripts/export_wallet_preflight_snapshot.py`
3. 在 staging 或影子环境运行 `scripts/probe_wallet_transaction.py --execute --user-id <uuid>`

## 8. 结论

当前条件下最稳、最成熟、最好用、且唯一权威的钱包权限模型是：

1. 钱包 authority 固定为 `users.id + wallet_ledger + wallets`
2. 客户端不直接写钱包表
3. 服务端统一 wallet service 收权
4. 真实事务写链走 Postgres 直连
5. service-role key 作为 admin 能力保留，但不把它误当成事务系统
