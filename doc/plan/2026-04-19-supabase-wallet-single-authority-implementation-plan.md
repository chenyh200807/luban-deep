# Implementation Plan：Supabase 钱包唯一权威体系

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

### 8.4 建议新增/修改文件

1. `scripts/audit_wallet_identity_inventory.py`
2. `scripts/migrate_wallet_identity_ownership.py`
3. `deeptutor/services/wallet/identity.py`
4. `deeptutor/api/dependencies/auth.py`
5. `deeptutor/api/routers/mobile.py`
6. `deeptutor/services/member_console/service.py`
7. `deeptutor/services/session/sqlite_store.py`
8. `deeptutor/api/routers/sessions.py`
9. `deeptutor/api/routers/question_notebook.py`
10. `deeptutor/api/routers/unified_ws.py`
11. `deeptutor/services/learner_state/service.py`
12. `deeptutor/services/learner_state/runtime.py`
13. `yousenwebview/app.js`
14. `yousenwebview/packageDeeptutor/utils/auth.js`
15. `yousenwebview/packageDeeptutor/pages/login/login.js`
16. `wx_miniprogram/` 对应 auth/login 相关文件

### 8.5 最容易漏掉的点

1. 旧 session owner_key
2. notebook owner_key
3. 本地 `auth_user_id`
4. learner_state 本地目录
5. 多 issuer token

### 8.6 最小验证

1. alias -> UUID 错绑数为 0
2. 影子 ID 不再进入钱包主链
3. 旧历史记录和 learner state 在 UUID 下仍可访问

### 8.7 退出门槛

1. canary alias 归一化通过
2. owner_key 访问 diff 达标
3. learner_state 并档失败数为 0
4. 客户端旧 token 刷新策略通过

## 9. WP3：统一 wallet service

### 9.1 目标

建立唯一的钱包读写服务，替代 `member_console` 作为生产真钱包 authority。

### 9.2 前置条件

1. `WP1` 完成
2. `WP2` 身份解析链稳定

### 9.3 任务拆解

#### T3.1 建立 wallet store

落点：

1. 新增：`deeptutor/services/wallet/store.py`
2. 新增：`deeptutor/services/wallet/__init__.py`

内容：

1. 读写 `wallets`
2. 读写 `wallet_ledger`
3. 处理版本更新和基础事务

验证：

1. staging 上可读写
2. 版本冲突可检测

#### T3.2 建立 wallet service

落点：

1. 新增：`deeptutor/services/wallet/service.py`

内容：

1. `get_wallet`
2. `list_wallet_ledger`
3. `grant_points`
4. `debit_points`
5. `refund_points`
6. `freeze_points`
7. `unfreeze_points`
8. `resolve_wallet_user_id`
9. `rebuild_wallet_projection`

验证：

1. API 契约稳定
2. 幂等规则稳定

#### T3.3 接入观测与 shadow compare 基础

落点：

1. 新增：`deeptutor/services/wallet/observability.py`
2. 或在 service 内最小实现

内容：

1. 记录 ledger event
2. 记录 idempotency conflict
3. 记录 version conflict
4. 记录 shadow compare 样本

验证：

1. 可导出 `wallet_service_contract.json`
2. 可导出 `idempotency_report.json`

### 9.4 建议新增/修改文件

1. `deeptutor/services/wallet/__init__.py`
2. `deeptutor/services/wallet/store.py`
3. `deeptutor/services/wallet/service.py`
4. `deeptutor/services/wallet/observability.py`

### 9.5 最容易漏掉的点

1. `balance_micros` 的单位换算只在展示层做
2. `idempotency_key` 规则必须覆盖支付、扣费、退款、迁移
3. 事务失败时不得留下半落库状态

### 9.6 最小验证

1. grant/debit/refund 都可跑通
2. 幂等重试不重复入账
3. projection 重算结果正确

### 9.7 退出门槛

1. wallet service 单测通过
2. staging 集成验证通过
3. projection consistency 为 0 diff

## 10. WP4：移动端读链切换

### 10.1 目标

先把展示和查询链路统一到新钱包 authority，同时通过 shadow compare 验证稳定性。

### 10.2 前置条件

1. `WP2` 完成
2. `WP3` 完成

### 10.3 任务拆解

#### T4.1 切 API 读链

落点：

1. 修改：[mobile.py](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/deeptutor/api/routers/mobile.py)

内容：

1. `/billing/points` 改读 wallet service
2. `/billing/wallet` 改读 wallet service
3. `/billing/ledger` 改读 wallet service
4. `/auth/profile.points` 改由 wallet 投影填充

验证：

1. `/billing/*` 和 `/auth/profile` 数值一致

#### T4.2 适配前端页面

落点：

1. `yousenwebview/packageDeeptutor/pages/chat/chat.js`
2. `yousenwebview/packageDeeptutor/pages/profile/profile.js`
3. `yousenwebview/packageDeeptutor/pages/billing/*`
4. `yousenwebview/packageDeeptutor/utils/api.js`
5. `wx_miniprogram/pages/chat/chat.js`
6. `wx_miniprogram/pages/profile/profile.js`
7. `wx_miniprogram/pages/billing/*`
8. `wx_miniprogram/utils/api.js`

内容：

1. 页面显示来自统一 authority
2. 灰度期允许 shadow compare
3. 不允许静默 fallback 到旧 authority

验证：

1. 首页、我的、账单页一致
2. 切账号后 UUID 刷新正确

#### T4.3 接入 shadow compare

落点：

1. `deeptutor/services/wallet/service.py`
2. `deeptutor/api/routers/mobile.py`
3. 必要时新增 `scripts/export_wallet_shadow_diff.py`

内容：

1. 记录 `request_id / legacy_user_id / resolved_uuid / balance_micros / display_points / diff_type`
2. 支持 canary 窄流量

验证：

1. 产出 `shadow_compare_summary.csv`
2. 产出 `shadow_compare_samples.jsonl`

### 10.4 建议新增/修改文件

1. `deeptutor/api/routers/mobile.py`
2. `yousenwebview/packageDeeptutor/pages/chat/chat.js`
3. `yousenwebview/packageDeeptutor/pages/profile/profile.js`
4. `yousenwebview/packageDeeptutor/pages/billing/*`
5. `yousenwebview/packageDeeptutor/utils/api.js`
6. `wx_miniprogram/pages/chat/chat.js`
7. `wx_miniprogram/pages/profile/profile.js`
8. `wx_miniprogram/pages/billing/*`
9. `wx_miniprogram/utils/api.js`
10. `scripts/export_wallet_shadow_diff.py`

### 10.5 最容易漏掉的点

1. 页面上多个 points 字段兼容逻辑
2. 灰度期的 shadow 允许，不等于允许 fallback
3. `/auth/profile` 和 `/billing/wallet` 的口径不一致

### 10.6 最小验证

1. 三个 API 口径一致
2. 小程序首页、我的、账单一致
3. shadow compare 达到连续窗口要求

### 10.7 退出门槛

1. 错绑差异为 0
2. 余额差异率达阈值
3. 高价值用户 diff 为 0

## 11. WP5：写链切换与旧 authority 退役

### 11.1 目标

让所有生产积分变化都只通过 wallet service 和 `wallet_ledger` 发生，并停止旧 authority 参与生产决策。

### 11.2 前置条件

1. `WP4` 完成
2. shadow compare 达 gate

### 11.3 任务拆解

#### T5.1 梳理旧写入口

落点：

1. 全仓 grep 与清单化
2. 输出 `legacy_write_grep.txt`

内容：

1. 找到所有 points_balance 改写点
2. 找到所有旧充值/扣点/补点入口

验证：

1. 旧写入口清单完整

#### T5.2 切充值/扣点/补点到 wallet service

落点：

1. `deeptutor/services/member_console/service.py`
2. `deeptutor/services/session/turn_runtime.py`
3. 其他找到的写入口

内容：

1. 充值发放切新写链
2. AI 扣点切新写链
3. 后台补点切新写链

验证：

1. 所有生产写事件都有 `ledger_event_id`
2. `idempotency_key` 全覆盖

#### T5.3 关闭旧 authority

落点：

1. `deeptutor/services/member_console/service.py`
2. `deeptutor/services/learner_state/service.py`
3. 小程序端旧 fallback 逻辑

内容：

1. 停止 `member_console.points_balance` 生产读写
2. 停止 `user_profiles.attributes.points` 生产读写
3. 仅保留 mock / 迁移输入 / 审计对比

验证：

1. runtime legacy write count 为 0
2. legacy production read count 为 0

#### T5.4 切换后全量审计

落点：

1. 新增脚本：`scripts/audit_wallet_projection_consistency.py`
2. 新增脚本：`scripts/audit_wallet_cutover_postcheck.py`

内容：

1. 重算 `wallet_ledger`
2. 对比 `wallets`
3. 出具补偿清单

验证：

1. `post_cutover_audit.csv`
2. `compensation_ledger_report.json`

### 11.4 建议新增/修改文件

1. `deeptutor/services/member_console/service.py`
2. `deeptutor/services/session/turn_runtime.py`
3. `deeptutor/services/learner_state/service.py`
4. `scripts/audit_wallet_projection_consistency.py`
5. `scripts/audit_wallet_cutover_postcheck.py`

### 11.5 最容易漏掉的点

1. member_console 中残留的点数写入口
2. turn runtime 里的扣费链
3. 小程序侧静默 legacy fallback

### 11.6 最小验证

1. 所有生产写事件生成 ledger
2. 旧写入口计数为 0
3. post-cutover audit 为 0 diff

### 11.7 退出门槛

1. `member_console.points_balance` 不再参与生产决策
2. `user_profiles.attributes.points` 不再参与生产决策
3. projection consistency 为 0 diff

## 12. 自动化测试清单

### 12.1 新增测试

1. `tests/services/wallet/test_store.py`
2. `tests/services/wallet/test_service.py`
3. `tests/services/wallet/test_identity_resolution.py`
4. `tests/scripts/test_wallet_migration_dry_run.py`
5. `tests/api/test_wallet_cutover_shadow.py`
6. `yousenwebview/tests/test_auth_uuid_refresh.js`

### 12.2 扩展测试

1. `tests/api/test_auth_dependency.py`
2. `tests/api/test_mobile_router.py`
3. `tests/api/test_sessions_router_auth.py`
4. `tests/api/test_notebook_router.py`
5. `tests/services/learner_state/test_service.py`
6. `tests/services/learner_state/test_runtime.py`
7. `tests/services/learner_state/heartbeat/test_service.py`
8. `yousenwebview/tests/test_chat_points_sync.js`
9. `yousenwebview/tests/test_profile_points_sync.js`

### 12.3 必测场景

1. 首次建钱包
2. 重复建钱包幂等
3. alias -> UUID 归一化
4. 影子用户 hard fail
5. owner_key 迁移后历史访问不丢
6. learner_state 并档后仍命中同一用户
7. grant/debit/refund 幂等
8. 并发扣费
9. 并发退款
10. 支付重复回调
11. 事务失败整体回滚
12. migration batch 重复执行
13. `/billing/*` 与 `/auth/profile` 一致
14. 小程序首页/我的/账单/切账号真机回归

## 13. 灰度与 runbook

### 13.1 Preflight

执行顺序：

1. 导出 `wallets/users/v_members` 快照
2. 生成 alias 覆盖率与冲突清单
3. 抽样旧 token issuer
4. 确认 `balance_micros -> 点数` 常量
5. 完成 staging dry-run

证据产物：

1. `preflight_snapshot.sql`
2. `identity_inventory.csv`
3. `unit_constant.md`
4. `dry_run_summary.json`

### 13.2 Read Cutover

执行顺序：

1. 部署 `WP1-WP3`
2. 页面仍读旧链
3. 后台记录 shadow compare
4. 连续观察至少 `48 小时`
5. canary 放量

证据产物：

1. `shadow_compare_samples.jsonl`
2. `shadow_compare_summary.csv`
3. `canary_gate_report.md`
4. `vip_user_checklist.csv`

### 13.3 Write Cutover

执行顺序：

1. 选择低峰窗口
2. 先关闭旧写入口
3. 再打开新 wallet service 写入口
4. 实时监控 `ledger writes / idempotency conflicts / version conflicts / insufficient balance / legacy write count`
5. 立即跑 projection audit

证据产物：

1. `cutover_timeline.md`
2. `metrics_export.json`
3. `projection_audit_after_cutover.csv`
4. `no_go_decision.md`

### 13.4 回滚

#### 读链回滚

1. 关闭新读链开关
2. 恢复旧展示链路
3. 保留 shadow compare 数据继续分析

证据：

1. `rollback_flag_snapshot.json`
2. `post_rollback_shadow_report.csv`

#### 写链回滚

1. 停止新写
2. 不删除 `wallet_ledger`
3. 必要时进入只读保护
4. 通过补偿而不是回滚事实层

证据：

1. `write_stop_event.md`
2. `affected_requests.jsonl`
3. `compensation_plan.csv`
4. `post_rollback_reconciliation.csv`

## 14. 完成定义

### 14.1 工程完成定义

1. `WP1-WP5` 全部完成
2. 新测试全部通过
3. 真机回归完成
4. 灰度门禁全部达到
5. post-cutover projection diff 为 0

### 14.2 业务完成定义

1. 同一用户在首页、我的、账单页、后台看到同一余额
2. 同一账号跨端只命中一个 UUID
3. 历史会话、notebook、learner_state、heartbeat 不因 UUID 切换而丢失
4. 所有生产积分变更都可在 `wallet_ledger` 中追溯

## 15. 建议执行节奏

建议按以下节奏推进：

1. 先完成 `WP1 + WP2` 并收一次 gate
2. 再完成 `WP3` 并收一次 gate
3. 再完成 `WP4` 和 shadow compare
4. 最后执行 `WP5` 与正式切换

不要把 `WP2-WP5` 混成一个大改动。  
最稳的方式是：**身份先收权，钱包再收权。**
