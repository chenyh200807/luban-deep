# PRD：Supabase 钱包唯一权威体系

## 1. 文档信息

- 文档名称：Supabase 钱包唯一权威体系 PRD
- 文档路径：`/doc/plan/2026-04-19-supabase-wallet-single-authority-prd.md`
- 创建日期：2026-04-19
- 状态：Draft v2
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

## 12.3 Phase 2：统一身份映射

动作：

1. 梳理历史 alias 到 `users.id` 的映射
2. 把 `user_2008` 这类影子 ID 对齐到真实 UUID
3. 鉴权边界统一只向后传 UUID

交付结果：

1. 钱包查询不再因 alias 漂移
2. 用户不会再命中假钱包
3. token 解析链路已能稳定落到真实 UUID

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

## 12.5 Phase 4：再切写链路

动作：

1. 充值发放切到 wallet service
2. AI 扣点切到 wallet service
3. 后台补点切到 wallet service

交付结果：

1. 不再有并行写入口
2. 所有生产写事件都有 ledger id 与 idempotency key

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

## 14.7 当前已知不确定性与验证方案

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

## 17. 最终结论

如果目标是“最稳、最成熟、最好用，而且唯一权威”，最终方案只能是：

**以 Supabase `users.id` UUID 为唯一身份主键，以 `wallet_ledger` 为唯一积分事实源，以 `wallets` 为唯一余额投影。**

这不是可选优化，而是积分系统从“多份快照拼凑”升级到“生产级钱包系统”的必要条件。
