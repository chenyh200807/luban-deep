# PRD：Supabase 钱包唯一权威体系

## 1. 文档信息

- 文档名称：Supabase 钱包唯一权威体系 PRD
- 文档路径：`/doc/plan/2026-04-19-supabase-wallet-single-authority-prd.md`
- 创建日期：2026-04-19
- 状态：Draft v3
- 适用范围：
  - `deeptutor/api/routers/mobile.py`
  - `deeptutor/services/member_console/service.py`
  - `deeptutor/services/learner_state/service.py`
  - `deeptutor/services/learner_state/supabase_store.py`
  - `wx_miniprogram/`
  - `yousenwebview/`
  - Supabase `users` / `wallets` / 新增 `wallet_ledger`
- 关联文档：
  - [2026-04-15-yousen-deeptutor-fusion-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/plan/2026-04-15-yousen-deeptutor-fusion-prd.md)
  - [deeptutor-bi-data-blueprint.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/zh/bi/deeptutor-bi-data-blueprint.md)

## 2. 执行摘要

本 PRD 的结论只有一句话：

**DeepTutor 会员积分系统的唯一权威，应收敛为 Supabase `users.id` UUID + `wallets` + `wallet_ledger`。**

具体定义如下：

1. `users.id` 是唯一用户主键。
2. `wallet_ledger` 是唯一积分事实源。
3. `wallets` 是唯一余额投影。
4. `user_profiles.attributes.points` 只能是展示性字段或迁移遗留字段，不能再参与余额决策。
5. `member_console.points_balance` 只能退化为本地 mock / 迁移输入，不得再作为生产真钱包 authority。

本 PRD 要解决的不是“某个页面显示错了”，而是：

**同一个业务事实当前被多套身份、多套存储、多套读写链路重复表达，导致积分系统没有唯一权威。**

本 PRD 推荐的最终形态不是“单字段拍脑袋收权”，而是成熟的钱包系统：

1. append-only 的积分流水
2. 可快速读取的余额投影
3. 单一身份主键
4. 单一写入口
5. 幂等、并发控制、回放和对账能力

在当前条件下，本 PRD 选择的**最优、稳健、可交付路径**不是一步到位重写全会员体系，而是：

1. 复用现有 Supabase `users` 与 `wallets`
2. 先补 `wallet_ledger`
3. 在现有 Python 服务端引入统一 wallet service
4. 先完成身份归一化，再切钱包读链，再切钱包写链
5. 通过 shadow compare 与对账脚本收线，而不是靠长期双写维持

这里必须强调：

**当前条件下最优解是“应用层统一 wallet service + 数据库唯一约束 + Supabase 作为唯一持久化 authority”。**

而不是：

1. 继续让多个 Python service 各自写钱包
2. 直接把 `user_profiles.points` 扶正
3. 先做 UI 展示修补，再晚些统一身份
4. 用长期双写和兜底 fallback 掩盖 authority 漂移

## 3. 背景

当前 Deeptutor 积分体系已经出现了典型的 authority drift：

1. 小程序页面显示会读 `/billing/points`、`/billing/wallet`。
2. 当前后端这两个接口仍然从 `member_console` 返回余额。
3. `LearnerStateService` 会把 `member_console.get_profile()` 投影写入 `user_profiles`。
4. Supabase 侧已经存在真实 `wallets` 与 `v_members` 数据。
5. 同一业务用户同时存在真实 UUID 用户与影子用户 ID。

这意味着当前系统里至少同时存在三种“点数表达”：

1. `member_console.points_balance`
2. `user_profiles.attributes.points`
3. `wallets.balance_micros`

这三者不是主从关系，而是并行存在。并行存在本身就是根因。

## 3.1 当前已确认事实（2026-04-19）

以下事实已被当前仓库与 Supabase 实查确认：

1. Supabase `wallets` 表真实存在，并已有线上数据。
2. Supabase `wallet_ledger` 当前不存在，直接查询返回 404。
3. Supabase `v_members` 已把 `users`、`wallets`、聊天统计等聚合到同一只读视图。
4. `chenyh2008` 当前存在真实 UUID 用户：
   - `users.id = 2d9eac15-5d26-4e93-941b-9ec6345ce6d9`
   - `identifier = chenyh2008`
   - `v_members.has_wallet = true`
5. 同时还存在影子用户：
   - `user_id = user_2008`
   - `has_user_record = false`
   - `has_wallet = false`
6. 当前移动端 `/billing/points`、`/billing/wallet` 仍然读取 `member_console.get_wallet()`，不是 Supabase `wallets`。
7. 当前微信登录在 `member_console` 里先生成或命中本地 `user_id`，并不是先归一化到 Supabase `users.id`。
8. 当前仓库内 `supabase/migrations/` 还没有 `wallets` / `wallet_ledger` 的受控 migration，说明钱包 schema 还未纳入本仓显式治理。
9. 当前 `.env` 里确认有 `SUPABASE_URL`、`SUPABASE_KEY`，但未确认 `SUPABASE_SERVICE_ROLE_KEY`，说明生产写链权限模型必须单独验清。

这说明：

1. 目标方向是对的
2. 但身份归一化是钱包收权前的硬前置
3. 而 `wallet_ledger` 是当前缺失但必须补上的事实层

## 4. 问题定义

### 4.1 真正的一等业务事实

积分系统真正要保证的业务事实不是“页面上有个数字”，而是：

1. 每个用户只有一个真钱包身份。
2. 每次积分变化都可解释。
3. 余额永远可由历史事实推导。
4. 并发扣减不会出现脏写。
5. 重试不会重复扣费或重复发放。
6. 出现错误时可以回滚、补偿、对账、审计。

### 4.2 当前根因

当前问题不是某个接口取错字段，而是四个更上游的结构问题：

1. 身份 authority 不唯一
2. 钱包 authority 不唯一
3. 写入链路不唯一
4. 读取链路不唯一

其中最危险的不是显示错误，而是：

**当前 auth token 解析出来的 `uid`，未必就是 Supabase `users.id`。**

如果这个前提不成立，那么：

1. `wallets` 再正确也可能被查错人
2. 钱包切换后会继续出现“真实钱包有余额，但当前接口显示 0”
3. 所有账务一致性努力都会被身份漂移重新破坏

### 4.3 当前失败形状

当前系统最容易出现以下失败形状：

1. 同一个人同时拥有 `users.id` UUID 和 `user_2008` 这类影子 ID。
2. Supabase `wallets` 里有真钱包，但小程序仍显示 0。
3. `user_profiles.attributes.points` 与真实余额漂移。
4. 本地 `member_console` 改了，但 Supabase 没变。
5. Supabase 改了，但移动端接口没读到。
6. 同一次扣费请求重试后可能二次扣减。
7. 后台无法准确回答“这个余额为什么变成这样”。

### 4.4 结论

问题本体不是“字段选错”，而是：

**同一业务事实被多个系统同时持有写权限与解释权。**

所以这次改造的本质是收权，不是补同步。

进一步说：

**这次改造不是单纯的钱包改造，而是“身份归一化 + 钱包收权”的组合改造。**

## 5. 产品目标

### 5.1 最终目标

建立一套可长期上线运行的钱包系统，满足：

1. 最稳
2. 最成熟
3. 最好用
4. 唯一权威

### 5.2 业务目标

1. 小程序、Web、后台、运营工具读取同一份余额。
2. 用户充值、赠送、扣费、退款、冻结、解冻都走同一体系。
3. 任何余额异常都能通过流水定位原因。
4. 迁移完成后不再允许积分事实分叉。

### 5.3 技术目标

1. 主键统一为 `users.id` UUID。
2. 钱包读链路统一。
3. 钱包写链路统一。
4. 钱包流水具备幂等能力。
5. 钱包余额具备版本控制和并发安全。
6. 身份解析在鉴权边界完成，不再把 alias 带入钱包层。
7. 切换过程具备 shadow compare、对账、回滚方案。

## 6. 非目标

本 PRD 不做以下事情：

1. 不把 `user_profiles` 升级成钱包系统。
2. 不继续增强 `member_console` 为生产钱包。
3. 不允许前端直写余额。
4. 不允许多个后端模块各自修改余额。
5. 不在本次设计里引入复杂的跨账户转账能力。
6. 不把积分系统与 LLM usage ledger 混成一张表。

## 7. 第一性原理与设计原则

### 7.1 Single Authority

一个业务事实只能有一个一等权威。

在积分场景中：

1. 用户身份权威是 `users.id`
2. 积分事实权威是 `wallet_ledger`
3. 积分余额权威是 `wallets`

### 7.2 Facts First, Projection Second

先有事实，再有余额。

也就是说：

1. 每次积分变化必须先形成一条 durable fact
2. 余额只是 fact 的投影结果
3. 投影可以重建，事实不能丢

### 7.3 Auth Boundary Normalization

用户名、手机号、微信 openid、unionid、display_name 都只能是登录入口的识别材料。

它们可以帮助找到用户，但不能直接成为钱包主键。

### 7.4 Idempotency by Default

支付回调、积分发放、扣费请求、失败补偿、后台重试默认都可能重复送达。

因此所有写操作必须自带幂等键，而不是依赖“调用方不会重试”。

### 7.5 Less Is More

不再增加第四套积分 truth。

最终允许存在的层次只有：

1. `wallet_ledger` 事实层
2. `wallets` 投影层
3. `v_members` / API DTO / 页面 state 读取层

### 7.6 No Hidden Fallback

一旦钱包 authority 完成切换，生产主链路不得保留“旧系统查询失败就退回 member_console”的静默 fallback。

允许存在的只有：

1. 灰度期间的 shadow read compare
2. 运维排障时的只读对比工具

不允许存在：

1. 线上扣费失败时偷偷改旧余额
2. 新链路取不到值时页面静默回退旧 truth
3. 两套 authority 长期并行以“提高稳定性”为名共存

## 8. 目标架构

## 8.1 一条身份主链

唯一主键：

- `users.id`

所有以下对象都必须只认这个 UUID：

1. 钱包
2. 钱包流水
3. 订单与会员发放
4. AI 扣点
5. 后台补点
6. 账单页
7. 我的页面点数展示

### 8.1.1 登录与别名处理

`chenyh2008`、手机号、微信身份、历史 `user_2008` 等都只能在鉴权边界做一次归一化：

1. 入口接收 alias
2. 解析到唯一 `users.id`
3. 之后所有钱包相关逻辑只带 UUID 向后传递

归一化之后，影子 ID 不得再参与钱包查询与余额决策。

### 8.1.2 当前条件下的最优身份方案

当前最优方案不是把钱包逻辑继续塞进 `member_console`，而是：

1. 保留现有移动端 token 入口形式
2. 在服务端鉴权边界把 token 内的 legacy `uid` 归一化到真实 `users.id`
3. 之后所有钱包与会员接口只认 UUID

如果现有 `users` 表不足以稳定承载以下身份材料：

1. `identifier`
2. `phone`
3. `wx_openid`
4. `wx_unionid`

则应引入一个**最小身份映射层**，例如：

- `user_identity_aliases`

仅用于 `alias -> users.id` 归一化。

注意：

1. 这不是第二套用户系统
2. 它只是 auth boundary 的 lookup 表
3. 如果现有 `users` 结构已足够，则不新增该表

### 8.1.3 token 语义与重签发策略

必须明确：

1. 鉴权边界谁负责把 legacy token 中的 `uid/sub` 归一化成真实 `users.id`
2. 归一化后何时签发新的 UUID 语义 token
3. 旧 token 如何进入兼容期、刷新期和强制失效期

推荐策略：

1. 登录成功后，服务端只签发 UUID 语义 token
2. 对旧 token 只允许短暂兼容读取，不允许长期继续作为生产身份真相
3. 一旦请求命中影子 ID，必须进入：
   - 重新映射
   - 重签 token
   - 或强制重登

禁止：

1. 让客户端长期同时持有 legacy user_id 和 UUID 两套身份语义
2. 服务端在命中影子 ID 时静默继续跑业务

### 8.1.4 alias 冲突规则

PRD 必须把以下冲突场景写死：

1. 一个手机号对应多个 legacy user_id
2. 一个用户名对应多个 legacy user_id
3. openid / unionid 与手机号归属不一致
4. 密码登录链、微信登录链、绑手机链指向不同候选用户

处理规则：

1. 若能唯一判定，则映射到唯一 UUID
2. 若不能唯一判定，则进入人工复核
3. 冲突用户不得自动迁移
4. 高价值用户优先人工确认

### 8.1.5 owner_key 与本地状态并档

身份从 legacy user_id 切到 UUID 时，不仅要切钱包，还必须迁移以下所有权：

1. chat session owner_key
2. notebook / 访问授权 owner_key
3. learner_state 本地目录
4. heartbeat job
5. 学习计划与相关本地索引

否则会出现：

1. 余额正确，但历史会话 404
2. 余额正确，但 learner_state / 学情 / 心跳像换了人

因此身份迁移必须至少包含：

1. owner_key 迁移方案
2. learner_state 并档方案
3. 回迁与补救策略

## 8.2 一条写入主链

所有积分变化都必须经过统一 wallet service。

统一 wallet service 至少覆盖以下动作：

1. `grant`
2. `debit`
3. `refund`
4. `freeze`
5. `unfreeze`
6. `expire`
7. `admin_adjust`

任何业务模块都不能自己写 `wallets.balance_micros`。

### 8.2.1 当前条件下的最优写入位置

当前条件下最优写入位置是：

**现有 Python 服务端内的统一 wallet service。**

原因：

1. 当前生产读写主链已经在 Python 服务端
2. 迁移成本低于立刻把全部逻辑推到 Supabase RPC / trigger
3. 更容易复用现有业务上下文、鉴权、日志、回滚与灰度机制

数据库侧仍需负责：

1. 唯一约束
2. 外键约束
3. 非负约束
4. 版本字段

后续如果未来出现多写入方，再考虑把部分规则下沉为数据库 RPC；但这不是当前条件下的最优第一步。

## 8.3 一条读取主链

对外读取规则如下：

1. 页面与移动端接口读取 `wallets` 或基于其构造的只读视图
2. 账单页读取 `wallet_ledger`
3. 运营聚合读取 `v_members` 这类读模型
4. `user_profiles` 不再承担余额 authority

## 9. 数据模型

## 9.1 `users`

角色：

- 唯一身份主表

关键要求：

1. `id` 为 UUID
2. 钱包永远外键指向 `users.id`
3. 任何非 UUID 标识都不再作为钱包主键

## 9.2 `wallets`

角色：

- 单用户单钱包余额投影

建议字段：

1. `user_id uuid primary key`
2. `balance_micros bigint not null`
3. `frozen_micros bigint not null`
4. `plan_id text`
5. `version int not null`
6. `created_at timestamptz not null`
7. `updated_at timestamptz not null`

单位约束：

1. 本表使用 `micros` 作为最小单位
2. 产品展示层再换算为“点数”
3. 所有业务计算必须在整数微单位上完成，不允许使用浮点

约束：

1. `user_id` 唯一
2. `balance_micros >= 0`
3. `frozen_micros >= 0`
4. `frozen_micros <= balance_micros`

说明：

1. 本表是余额投影，不是事实流水。
2. 当前既有 `wallets` 表可直接复用，不建议再发明第二张余额表。
3. 当前从线上样本看，系统很可能采用 `1 point = 1_000_000 micros` 的比例，但这点必须在切换前正式验证，不能凭截图与样本值直接上线。

## 9.3 `wallet_ledger`

角色：

- 唯一积分事实源

建议字段：

1. `id uuid primary key`
2. `user_id uuid not null`
3. `event_type text not null`
4. `delta_micros bigint not null`
5. `balance_after_micros bigint not null`
6. `frozen_after_micros bigint not null`
7. `reference_type text`
8. `reference_id text`
9. `reason text not null`
10. `idempotency_key text not null`
11. `operator_type text not null`
12. `operator_id text`
13. `metadata jsonb not null default '{}'::jsonb`
14. `created_at timestamptz not null`

约束：

1. `idempotency_key` 全局唯一，或在 `user_id + event_type` 范围内唯一
2. `user_id` 外键指向 `users.id`
3. `delta_micros` 可正可负，但不能为 0

设计说明：

1. `grant`、`debit`、`refund`、`expire` 都只是不同的 `event_type`
2. 钱包系统回答“为什么余额是这个数”时，必须能完全依赖本表
3. `balance_after_micros` 与 `frozen_after_micros` 是为了快速审计和对账，不是替代 `wallets`

建议的最小 `event_type` 枚举：

1. `migration_opening_balance`
2. `purchase_grant`
3. `manual_grant`
4. `session_debit`
5. `refund`
6. `freeze`
7. `unfreeze`
8. `expire`
9. `admin_adjust`

建议的幂等键规则：

1. 支付发放：`purchase:{provider}:{order_id}`
2. AI 扣费：`session_debit:{conversation_id}:{turn_id}:{pricing_version}`
3. 退款补偿：`refund:{source_ledger_id}`
4. 后台调整：`admin_adjust:{ticket_id}`
5. 迁移开账：`migration_opening_balance:{user_id}:{migration_batch}`

## 9.4 只读视图

可以保留或新增只读视图，例如：

1. `v_members`
2. `v_member_wallet_summary`

但这些视图必须遵守一个原则：

**只做读模型，不做写 authority。**

## 10. 核心场景设计

## 10.1 新用户注册

流程：

1. 入口完成身份归一化，拿到 `users.id`
2. 若不存在 `wallets` 记录，则初始化一个钱包
3. 若存在新手礼包，则写入一条 `wallet_ledger(grant)`
4. 同事务内更新 `wallets`

要求：

1. 初始化可重试
2. 不得因重复注册导致重复送积分
3. 初始化完成后必须能立刻查询到 `wallets`

## 10.2 登录后首页显示余额

流程：

1. 登录态恢复后解析出唯一 UUID
2. `/billing/wallet` 直接读取 `wallets`
3. 页面展示用统一换算后的余额值

要求：

1. 不能再从 `user_profiles.attributes.points` 回填 UI
2. 不能再从本地 `member_console` 当真值读余额
3. 客户端若持有旧 token，必须按既定策略刷新或强制重登

## 10.3 AI 对话扣点

流程：

1. 业务层生成一次扣费请求
2. 请求携带 `idempotency_key`
3. wallet service 在事务中：
   - 校验余额
   - 写入 `wallet_ledger(debit)`
   - 更新 `wallets`
4. 返回新的余额快照

要求：

1. 同一个 turn 或同一个计费事件只能扣一次
2. 网络重试不能导致重复扣费
3. 扣费结果必须附带本次 ledger event id
4. 若余额不足，必须返回明确的业务错误，而不是静默返回 0

## 10.4 AI 失败补偿

流程：

1. 若本次扣点应回滚，则生成一个新的补偿事件
2. 写入 `wallet_ledger(refund)`
3. 更新 `wallets`

要求：

1. 不直接覆盖旧 ledger
2. 不做“静默把余额改回去”这种无痕修复

## 10.5 充值购买

流程：

1. 订单支付成功
2. 回调事件进入 wallet service
3. 通过 `reference_type=order`、`reference_id=order_id` 和 `idempotency_key` 去重
4. 写入 `wallet_ledger(grant)`
5. 更新 `wallets`

要求：

1. 支付平台重复回调不重复加点
2. 后续可通过订单号完整追账
3. 订单状态与 wallet ledger 能双向追溯

## 10.6 后台人工补点

流程：

1. 管理后台调用 wallet service
2. 必须记录操作者、原因、备注
3. 写入 `wallet_ledger(admin_adjust)`
4. 更新 `wallets`

要求：

1. 后台不能直接改余额字段
2. 必须保留审计证据

## 10.7 到期、冻结与解冻

设计原则：

1. 冻结余额进入 `frozen_micros`
2. 余额可用额度按 `balance_micros - frozen_micros` 判定
3. 解冻与过期都走 ledger 事件，而不是直接改显示字段

## 11. API 与服务边界

## 11.1 统一 wallet service

建议引入统一服务边界，例如：

1. `get_wallet(user_id)`
2. `list_wallet_ledger(user_id, limit, offset)`
3. `grant_points(...)`
4. `debit_points(...)`
5. `refund_points(...)`
6. `freeze_points(...)`
7. `unfreeze_points(...)`
8. `resolve_wallet_user_id(...)`
9. `rebuild_wallet_projection(...)`

要求：

1. 所有写入必须经由该服务
2. 所有服务内部使用事务
3. 服务内部负责幂等与版本控制
4. 服务返回值必须同时携带：
   - `user_id`
   - `balance_micros`
   - `frozen_micros`
   - `version`
   - `ledger_event_id`

### 11.1.1 推荐的事务策略

当前条件下建议采用：

1. 先锁定或原子更新 `wallets` 当前行
2. 校验余额与版本
3. 写入 `wallet_ledger`
4. 更新 `wallets`
5. 一次事务提交

如果当前技术栈难以稳定实现显式行锁，则至少要保证：

1. `version` 条件更新
2. 更新失败时自动重试有限次数
3. 幂等键可以抵御重试副作用

## 11.2 移动端接口收口

以下接口必须改为读取 Supabase 钱包系统：

1. `/billing/points`
2. `/billing/wallet`
3. `/billing/ledger`
4. `/auth/profile` 中的积分字段

要求：

1. 页面上同一时刻看到的余额必须来自同一 authority
2. 不允许一个接口读 `wallets`，另一个接口读 `member_console`
3. 所有接口统一返回微单位原值和页面展示值，避免前端各自猜测换算规则

## 11.3 `user_profiles` 定位调整

`user_profiles` 只保留学习画像语义，例如：

1. `display_name`
2. `exam_date`
3. `focus_topic`
4. `daily_target`
5. `difficulty_preference`

`points` 不再作为业务 authority。

最稳妥做法：

1. 先停止读它
2. 再停止写它
3. 最后删除或保留为只读兼容字段

## 11.4 观测与审计

钱包系统必须具备最小观测能力：

1. 每次钱包写操作记录：
   - `user_id`
   - `event_type`
   - `idempotency_key`
   - `reference_type`
   - `reference_id`
   - `before_balance`
   - `after_balance`
   - `result`
2. 对所有幂等冲突、版本冲突、余额不足单独计数
3. 提供按用户和按订单号的检索路径

## 11.5 身份归一化观测

身份切换期间必须额外观测：

1. legacy token 命中次数
2. 影子 ID 命中次数
3. alias 冲突命中次数
4. owner_key 访问失败次数
5. learner_state 并档失败次数

## 12. 迁移方案

## 12.1 Phase 0：宣布唯一权威

上线前先明确制度：

1. 从本 PRD 批准起，钱包 authority 定义为 `users.id + wallets + wallet_ledger`
2. 禁止新增任何新的 points truth
3. 禁止再让新功能直接接入 `member_console.points_balance`

## 12.2 Phase 1：引入 `wallet_ledger`

动作：

1. 在 Supabase 创建 `wallet_ledger`
2. 给 `wallets` 补齐必要约束与索引
3. 实现统一 wallet service

交付结果：

1. 钱包具备事实层
2. 后续所有写入有统一入口
3. 现有 `wallets` 约束与字段口径被正式确认
4. staging 或影子环境已完成一次完整 dry-run

## 12.3 Phase 2：统一身份映射

动作：

1. 梳理历史 alias 到 `users.id` 的映射
2. 把 `user_2008` 这类影子 ID 对齐到真实 UUID
3. 鉴权边界统一只向后传 UUID
4. 明确 token 重签发与强制重登策略
5. 迁移 session owner_key、notebook owner_key、learner_state、heartbeat、学习计划等 user_id 所有权

交付结果：

1. 钱包查询不再因 alias 漂移
2. 用户不会再命中假钱包
3. token 解析链路已能稳定落到真实 UUID

放行门禁：

1. canary 用户集 alias -> UUID 错绑数必须为 `0`
2. 高价值用户人工复核清单必须清零
3. 未映射活跃用户数必须为 `0`，否则不得切读链
4. 新 token 解析命中 UUID 成功率必须达到预设阈值
5. 任一请求命中影子 ID 时必须 hard fail 并告警，不允许静默兜底
6. owner_key 访问错误数必须达到放行阈值以内
7. learner_state 并档失败数必须清零

## 12.4 Phase 3：先切读链路

动作：

1. `/billing/wallet` 读 `wallets`
2. `/billing/ledger` 读 `wallet_ledger`
3. `/auth/profile.points` 改为由 `wallets` 投影填充
4. 灰度期同时保留旧链路只做 shadow compare，不回退展示

交付结果：

1. 小程序先不再读旧点数字段
2. 页面显示与真钱包对齐
3. 新旧链路差异可观测、可统计

放行门禁：

1. shadow compare 字段必须至少包含：
   - `user_id`
   - `balance_micros`
   - `display_points`
   - `source`
2. 差异必须按三类单独统计：
   - 用户错绑差异
   - 余额绝对值差异
   - 单位换算差异
3. shadow compare 必须连续观察至少一个明确窗口，建议 `48 小时`
4. 真实请求量必须达到预设下限后才允许放量
5. 用户错绑差异必须为 `0`
6. 余额差异率必须低于预设阈值；当前建议阈值为 `< 0.01%`

## 12.5 Phase 4：再切写链路

动作：

1. 充值发放切到 wallet service
2. AI 扣点切到 wallet service
3. 后台补点切到 wallet service

交付结果：

1. 不再有并行写入口
2. 所有生产写事件都有 ledger id 与 idempotency key

放行门禁：

1. 必须在低峰窗口或短暂写冻结窗口执行
2. 所有旧写路径必须完成 grep 级确认清单
3. 切写时顺序必须是：
   - 先关闭旧写入口
   - 再打开新写入口
4. 上线后旧入口写入计数必须为 `0`
5. 任一 residual write 命中旧链即自动 no-go

## 12.6 Phase 5：退役旧 authority

动作：

1. 停止把 `member_console.points_balance` 作为生产余额
2. 停止写 `user_profiles.attributes.points`
3. 保留兼容期监控
4. 最终删除旧逻辑

交付结果：

1. 钱包 authority 完成收权
2. 旧字段只保留只读兼容或被删除

## 12.7 Phase Gate 与回滚条件

每个阶段都必须有 go / no-go 条件：

1. Phase 2 未完成，不允许切读链
2. Phase 3 shadow diff 未收敛，不允许切写链
3. Phase 4 幂等与并发测试未过，不允许下线旧 authority

允许的回滚：

1. 代码回滚到旧接口实现
2. 灰度关闭新读链

不允许的回滚：

1. 回滚期间继续双写新旧两套真钱包
2. 事后人工猜测余额并直接覆盖生产数据

### 12.7.1 分级回滚策略

必须区分三类回滚：

1. 读链回滚
   - 关闭新读链灰度
   - 页面回到旧展示口径
   - 保留 shadow compare 数据继续分析
2. 写链回滚
   - 停止新写入口
   - 不删除已写入的 `wallet_ledger`
   - 通过补偿事件修正错误，不回滚事实层
3. 全量停写保护
   - 若出现无法快速归因的错绑或余额异常，进入只读保护窗口
   - 禁止人工直接改余额

### 12.7.2 回滚后的强制动作

任何回滚后都必须执行：

1. projection consistency audit
2. alias -> UUID 映射复核
3. 补偿事件清单确认
4. 回滚窗口内所有写事件的审计复盘

## 13. 对账与回放

系统必须支持以下能力：

1. 根据 `wallet_ledger` 重算单用户余额
2. 对比 `wallets.balance_micros` 与重算值
3. 扫描幂等键重复事件
4. 扫描没有钱包记录但有 profile 的用户
5. 扫描 alias 未归一化用户

建议提供定时或手动执行的对账脚本：

1. `rebuild_wallet_balance_from_ledger`
2. `audit_wallet_projection_consistency`
3. `backfill_legacy_points_to_wallets`
4. `audit_identity_alias_to_uuid_consistency`

## 13.1 开账迁移规则

历史系统如果无法提供完整积分流水，则必须允许一次且仅一次“开账事件”：

- `migration_opening_balance`

规则：

1. 每个用户最多一条
2. 必须带 `migration_batch`
3. 必须能追溯导入来源：
   - `wallets`
   - `member_console`
   - `user_profiles`
   - 人工修正

最稳妥策略：

1. 优先以现有 Supabase `wallets` 为开账基础
2. 对冲突用户单独人工复核
3. 对 `wallets` 不存在、但 legacy 有余额的用户生成专项迁移清单

## 13.2 Dry-run 迁移产物

在正式迁移前，必须先完成一次 dry-run，并产出以下固定产物：

1. `migration_batch_id`
2. 开账来源优先级规则
3. 冲突用户人工复核队列
4. 无钱包用户清单
5. 迁移前后汇总 diff：
   - 用户数
   - 总余额
   - 冲突数
   - 无映射数
6. dry-run 重复执行幂等结果
7. owner_key 迁移前后可访问性 diff
8. learner_state / heartbeat / 学习计划并档结果清单

## 14. 风险与缓解

### 14.1 历史数据映射错误

风险：

- 旧账号别名可能错误映射到错误 UUID

缓解：

1. 迁移前做用户名、手机号、微信身份三重校验
2. 高风险账号人工确认

### 14.2 并行写入窗口

风险：

- 新旧写链同时存在时可能继续分叉

缓解：

1. 切写时必须设置明确开关
2. 开关切换后立刻监控对账

### 14.3 历史点数无法完整追溯

风险：

- 旧系统的部分余额只有快照，没有完整流水

缓解：

1. 允许一次性导入 `migration_opening_balance`
2. 明确这是一笔迁移起始事件
3. 从该事件之后要求所有变化都有真实 ledger

### 14.4 页面缓存导致短时旧值

风险：

- 小程序本地缓存可能短时展示旧点数

缓解：

1. 余额页以服务端返回为准
2. 完成关键写操作后主动刷新钱包接口

### 14.5 微单位口径错误

风险：

- `balance_micros` 与“点数”的换算规则若理解错误，会造成整站显示与扣费比例错误

缓解：

1. 在切读链前用真实订单、真实赠送、真实扣费样本验证换算比例
2. 在 PRD 执行前明确写成配置常量和测试用例

### 14.6 身份归一化信息不全

风险：

- 若无法稳定把微信登录、手机号、用户名统一映射到 `users.id`，新钱包 authority 仍会查错人

缓解：

1. 先完成身份盘点与映射验证
2. 对高价值用户先人工校验
3. 映射未收敛前，不进入钱包切换

### 14.7 token 语义切换不完整

风险：

- 客户端继续拿旧 token 自动登录，服务端或页面在灰度期继续命中 legacy user_id

缓解：

1. 明确 token 兼容窗口
2. 上线后强制走 token 刷新或重签发
3. 影子 ID 命中即告警并阻断主链

## 14.8 当前已知不确定性与验证方案

当前仍存在以下不确定性，必须先验证：

1. `balance_micros` 与“点数”的正式换算比例是否确认为 `1:1_000_000`
   - 验证方式：抽取真实订单、赠送、消费样本核对
   - 替代方案：若现有口径不统一，则引入显式 `point_scale` 常量并一次性校正
2. 微信登录所用 openid / unionid 当前应落在 `users` 还是独立 alias 表
   - 验证方式：盘点现有 `users` schema 与登录链需求
   - 替代方案：若 `users` 不宜扩列，则新增最小 `user_identity_aliases`
3. 当前 `wallets.version` 是否已在任何生产写链路被正确维护
   - 验证方式：审查现有写入方和 version 变化样本
   - 替代方案：若未稳定维护，则由新 wallet service 接管 version 递增
4. 现有 `v_members` 是否足够支撑后台读取，还是需要新增只读 view
   - 验证方式：核对后台所需字段
   - 替代方案：新增 `v_member_wallet_summary`
5. 当前服务端是否具备可安全写 Supabase 钱包表的权限模型
   - 验证方式：确认 `SUPABASE_SERVICE_ROLE_KEY`、RLS policy、写入凭证与最小权限边界
   - 替代方案：若当前运行时不能稳定直写，则先补专用 server-side wallet writer，再切主链
6. `users.identifier`、`users.phone` 以及未来微信身份字段是否具备唯一约束
   - 验证方式：检查 schema 与脏数据样本
   - 替代方案：若唯一性不足，则先清洗数据并补唯一索引，必要时引入最小 alias 表

7. 线上现有 token 是否全部由同一 issuer 签发
   - 验证方式：抽样核对 token issuer 与 payload 结构
   - 替代方案：若存在多 issuer，则先补多 issuer 收口层

## 14.9 实施前置检查清单

在进入任何代码实现前，以下检查必须完成：

1. 确认 Supabase 生产环境中 `wallets` 的真实 schema、索引、约束、RLS policy。
2. 确认 `wallet_ledger` 是否确实不存在于生产，还是仅当前 key 无法访问。
3. 确认服务端生产运行环境是否具备安全可控的钱包写权限。
4. 确认 `users` 表是否能稳定承载：
   - `identifier`
   - `phone`
   - 微信身份字段或其替代映射
5. 确认 `balance_micros -> 点数` 的正式换算口径。
6. 拉取活跃用户样本，完成 alias -> UUID 映射审计。
7. 产出迁移前快照：
   - `wallets`
   - `v_members`
   - 旧 `member_console`
   - 关键用户清单
8. 抽样确认旧 token issuer、旧 owner_key 与本地 learner_state 路径分布。

如果上述任一项未完成，不得进入读链切换。

## 15. 验收标准

以下条件全部满足，才算收线：

1. 同一用户在小程序首页、我的页面、账单页、后台页看到同一余额。
2. 真实钱包用户只能命中一个 `users.id`。
3. `/billing/wallet`、`/billing/points`、`/auth/profile.points` 全部来自同一钱包 authority。
4. 重复支付回调不会重复加点。
5. 重复扣费请求不会重复扣点。
6. 任何一次余额变化都能在 `wallet_ledger` 中查到。
7. `wallet_ledger` 可重算出的余额与 `wallets` 一致。
8. `user_profiles.attributes.points` 不再参与生产决策。
9. `member_console.points_balance` 不再参与生产决策。
10. 任意一个 alias 登录后都能归一化命中同一个 UUID 钱包。
11. 幂等重试、并发扣费、支付重复回调都有自动化测试。
12. shadow compare 在灰度窗口内差异率达到预设阈值以内。

## 15.1 推荐的测试矩阵

至少覆盖以下测试：

1. 单用户首次建钱包
2. 重复建钱包幂等
3. 单次扣费成功
4. 同一 `idempotency_key` 重试不重复扣费
5. 并发扣费下余额不为负
6. 支付回调重复发放不重复加点
7. 退款补偿正确恢复余额
8. `migration_opening_balance` 每用户只允许一次
9. alias 登录统一命中同一 UUID
10. `/billing/wallet`、`/billing/points`、`/auth/profile` 返回一致
11. 支付回调乱序、重复、超时重试
12. ledger 已写成功但响应失败后的重试幂等
13. wallets 更新失败时事务整体回滚
14. 并发扣费与并发退款交叉
15. migration batch 重复执行幂等
16. 小程序真机回归：
   - 登录
   - 首页余额
   - 我的页面余额
   - 账单页
   - 切账号
   - 扣点后刷新一致

## 15.2 建议的量化门禁

若要从“可测”进入“可灰度”，建议采用以下量化门禁：

1. canary 用户集中的 alias -> UUID 映射错误数必须为 `0`。
2. canary 用户集中的 `/billing/wallet` shadow compare 差异数必须为 `0`。
3. 全量 shadow compare 若存在差异，必须：
   - 差异率低于 `0.1%`
   - 且所有差异都有明确归因清单
4. 并发扣费与重复回调测试必须全绿。
5. `wallet_ledger` 重算结果与 `wallets` 投影差异必须为 `0`。

## 15.3 上线演练要求

正式切换前必须完成至少一次上线演练，覆盖：

1. read cutover 演练
2. write cutover 演练
3. 回滚演练
4. 对账演练

如果未完成演练，不得进入正式切换窗口。

说明：

1. `0.1%` 是当前建议阈值，不是绝对标准。
2. 如果业务体量较小，建议直接以“差异数为 0”作为正式放量门槛。

## 16. 当前代码基线下的改造重点

本仓当前最需要收口的不是 UI，而是 authority：

1. `deeptutor/api/routers/mobile.py` 当前 `/billing/*` 仍走旧 member service。
2. `deeptutor/services/member_console/service.py` 当前仍把 `points_balance` 当真钱包。
3. `deeptutor/services/learner_state/service.py` 当前会把 member profile 投影成 `user_profiles`。
4. 小程序页面当前会兼容多种 points 字段，说明上游 authority 尚未收敛。
5. 微信登录当前先命中本地 `member_console` 身份，不是直接命中 Supabase UUID 用户。
6. Supabase `wallet_ledger` 当前尚未存在，说明事实层必须先补表再改链路。

因此实现顺序必须是：

1. 先收身份
2. 再收读链
3. 再收写链
4. 最后删旧 truth

如果顺序反过来，例如先切钱包读链、后收身份，系统会继续把真实钱包查错人，表面上看像“wallets 也不稳”，本质上仍是身份 authority 没收干净。

## 16.1 推荐的实施工作包

为避免再次陷入 patch spiral，本 PRD 推荐按以下工作包执行：

### WP1：Schema 与权限基线

目标：

1. 把钱包 schema 纳入本仓显式治理
2. 确认写权限与 RLS 边界

建议落点：

1. `supabase/migrations/` 新增钱包相关 migration
2. 新增钱包 schema 说明或 appendix

最小交付：

1. `wallet_ledger` 建表 SQL
2. `wallets` 约束/索引补齐 SQL
3. RLS / server-side writer 策略说明

### WP2：身份归一化层

目标：

1. 让鉴权边界稳定产出真实 `users.id`

建议落点：

1. `deeptutor/services/member_console/service.py`
2. `deeptutor/api/routers/mobile.py`
3. 必要时新增 `deeptutor/services/wallet/identity.py`

最小交付：

1. token `uid` 到 UUID 的解析路径
2. alias 查找策略
3. 影子用户命中保护
4. token 重签发策略
5. owner_key 迁移策略
6. learner_state / heartbeat / 学习计划并档策略

### WP3：统一 wallet service

目标：

1. 在 Python 服务端建立唯一写入口

建议落点：

1. 新增 `deeptutor/services/wallet/service.py`
2. 新增 `deeptutor/services/wallet/store.py`
3. 相关测试目录新增 `tests/services/wallet/`

最小交付：

1. `get_wallet`
2. `list_wallet_ledger`
3. `grant_points`
4. `debit_points`
5. `refund_points`
6. `resolve_wallet_user_id`

### WP4：移动端读链切换

目标：

1. 让展示链路先统一读新 authority

建议落点：

1. `deeptutor/api/routers/mobile.py`
2. `yousenwebview/packageDeeptutor/pages/chat/chat.js`
3. `yousenwebview/packageDeeptutor/pages/profile/profile.js`
4. `wx_miniprogram/` 对应页面与 `utils/api.js`

最小交付：

1. `/billing/points`、`/billing/wallet`、`/billing/ledger` 新链路
2. `/auth/profile.points` 新链路
3. 页面不再依赖旧 points truth

### WP5：写链切换与旧 authority 退役

目标：

1. 所有真实积分变化统一进入 wallet service

建议落点：

1. 充值/发放入口
2. AI 扣费入口
3. 后台补点入口
4. 旧 `member_console` 调用点清理

最小交付：

1. 生产写事件全部生成 ledger
2. 旧写入口下线或只保留 mock

## 16.2 建议的执行顺序

建议严格按以下顺序推进：

1. `WP1 Schema 与权限基线`
2. `WP2 身份归一化层`
3. `WP3 统一 wallet service`
4. `WP4 移动端读链切换`
5. `WP5 写链切换与旧 authority 退役`

任何跳步执行都必须被视为高风险操作。

## 16.3 每个工作包的完成定义

### WP1 完成定义

1. schema 已纳入本仓 migration
2. 写权限模型已验证
3. `wallet_ledger` 可被服务端安全读写

### WP2 完成定义

1. canary 用户 alias 登录后全部命中唯一 UUID
2. 影子 ID 不再进入钱包查询链
3. 旧 session / notebook / learner_state 在 UUID 下可继续访问
4. 客户端旧 token 刷新策略完成验证

### WP3 完成定义

1. wallet service 自动化测试通过
2. 幂等与并发行为可重复验证

### WP4 完成定义

1. 小程序展示与后台展示一致
2. shadow compare 达到门禁

### WP5 完成定义

1. 所有生产写事件均写入 `wallet_ledger`
2. `member_console.points_balance` 不再参与生产决策
3. `user_profiles.attributes.points` 不再参与生产决策

## 16.4 最小上线 Runbook

建议采用以下最小上线顺序：

1. 备份当前 `wallets` 与关键用户快照
2. 部署 schema 变更
3. 部署身份归一化与 wallet service
4. 开启 shadow read compare
5. canary 放量
6. 观察门禁指标
7. 切正式读链
8. 切正式写链
9. 关闭旧 authority
10. 运行对账与重算脚本

## 16.5 回滚 Runbook

若灰度阶段发现问题，允许的回滚动作只有：

1. 关闭新读链灰度
2. 回滚到旧接口实现
3. 暂停新写入口
4. 保留已写入的 `wallet_ledger` 作为审计事实
5. 用对账脚本评估是否需要补偿事件

明确禁止：

1. 直接手改生产余额掩盖问题
2. 无审计地删除 ledger
3. 长期维持新旧两套真钱包并行写入

## 17. 最终结论

如果目标是“最稳、最成熟、最好用，而且唯一权威”，最终方案只能是：

**以 Supabase `users.id` UUID 为唯一身份主键，以 `wallet_ledger` 为唯一积分事实源，以 `wallets` 为唯一余额投影。**

这不是可选优化，而是积分系统从“多份快照拼凑”升级到“生产级钱包系统”的必要条件。
