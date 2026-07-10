# v_members 摘除死表 chat_conversations 派生列 — 待执行生产变更

> 状态：**待执行**（代码侧已于 `fix/p3-bi-honest-metrics` 分支先行弃读，视图变更可独立择期执行）。
> 执行环境：Supabase 主项目（kb_chunks 所在项目）SQL Editor 或 psql（5432 会话池）。
> 权限：service_role / postgres。执行人需有生产写权限——AI agent 无生产写权限，本文件是变更说明与验收清单。

## 背景（为什么）

- Postgres `chat_conversations` 是死表：2026-07-10 活体查证近 14 天全库 0 行；真实对话在宿主机容器内 SQLite `chat_history.db`（`sessions`/`turns`）。
- `v_members` 视图 join 了 `chat_conversations`，其派生列 `first_chat_at` / `last_chat_at` / `total_conversations` / `total_messages` / `has_chat_history` 全是空壳或陈旧值，一直在误导 BI 会员面板与任何直接查视图的人。
- 代码侧已完成弃读（`deeptutor/services/member_console/directory.py` 不再 select 这些列，也不再用 `last_chat_at` 排序/派生 `last_active_at`）；BI 的对话活跃事实统一从 SQLite sessions 派生（`MemberConsoleService._merge_session_activity_for_member_list`）。
- 原则：宁缺毋假。视图不应继续对人（SQL 直查）撒谎。

## 前置校验（执行前必做，只读）

```sql
-- 1. 确认 chat_conversations 仍是死表（近 14 天 0 行）
select count(*) as recent_rows
from public.chat_conversations
where created_at > now() - interval '14 days';
-- 预期：0。若 > 0，停止执行并回报（说明表复活了，本变更前提失效）。

-- 2. 抓取当前视图完整定义（留档，回滚依据）
select pg_get_viewdef('public.v_members'::regclass, true);

-- 3. 检查依赖（是否有其他视图/物化视图依赖 v_members 的 chat 列）
select dependent_ns.nspname as dependent_schema, dependent_view.relname as dependent_view
from pg_depend
join pg_rewrite on pg_depend.objid = pg_rewrite.oid
join pg_class as dependent_view on pg_rewrite.ev_class = dependent_view.oid
join pg_namespace dependent_ns on dependent_view.relnamespace = dependent_ns.oid
where pg_depend.refobjid = 'public.v_members'::regclass
  and dependent_view.relname != 'v_members';
-- 预期：空。若非空，逐个确认依赖方是否读 chat 列。

-- 4. 确认仓库内已知的 v_members 读取方兼容：
--    - deeptutor/services/member_console/directory.py（已弃读 chat 列，只读
--      user_id,identifier,phone,display_name,profession,exam_target,plan_id,
--      balance_micros,frozen_micros,wallet_created_at,wallet_updated_at,
--      has_user_record,has_wallet,has_profile）
--    - scripts/bi_reconciliation/business_source.py（只 select=user_id，兼容）
```

## 变更（DROP + CREATE，Postgres 的 CREATE OR REPLACE VIEW 不允许删列）

以步骤 2 抓到的现行定义为底稿，删除：

1. 对 `chat_conversations` 的 join / 子查询；
2. 输出列 `first_chat_at`、`last_chat_at`、`total_conversations`、`total_messages`、`has_chat_history`。

```sql
begin;

-- 用步骤 2 的定义改写。骨架示意（以实际定义为准，勿盲抄）：
drop view public.v_members;
create view public.v_members as
select
  u.id as user_id,
  u.identifier,
  -- … 保留现有非 chat 派生列：phone / display_name / profession / exam_target /
  --    plan_id / balance_micros / frozen_micros / wallet_created_at / wallet_updated_at /
  --    has_user_record / has_wallet / has_profile …
  -- ❌ 不再输出：first_chat_at / last_chat_at / total_conversations / total_messages / has_chat_history
from public.users u
-- ❌ 删除: left join public.chat_conversations …
left join public.wallets w on …
left join public.profiles p on …;

-- 视图权限按原样恢复（步骤 2 留档时同时抓 grants）：
-- select grantee, privilege_type from information_schema.role_table_grants
--   where table_name = 'v_members';

commit;
```

## 回滚

用步骤 2 留档的 `pg_get_viewdef` 输出原样 `drop view` + `create view` 恢复即可（纯视图，无数据丢失风险）。

## 执行后验收

```sql
-- 列已消失
select column_name from information_schema.columns
where table_schema = 'public' and table_name = 'v_members';
-- 预期：不含 first_chat_at/last_chat_at/total_conversations/total_messages/has_chat_history

-- 行数与执行前一致（视图行覆盖不因删列变化）
select count(*) from public.v_members;
```

应用侧回归（生产部署了 fix/p3-bi-honest-metrics 之后）：

- [ ] `/api/v1/bi/member/list` 正常返回，`last_active_at` 非空（来自 SQLite 会话合并或钱包时间回退）；
- [ ] `/api/v1/bi/members`（get_member_stats）dashboard 正常；
- [ ] `new_30d_count` 落入量级带 60±10（canonical 基线口径见下方待办，不用死数）。

## 关联生产验收待办（本次 P3 全量）

> 口径裁定（指挥官 2026-07-10）：部署验收**不用死数**（61/62 都不用）。canonical 基线 =
> 基线取证用的 phone-alias 复算脚本本身；验收时用**同一脚本同一时点**重跑 before/after。

0. **【可选双保险，非硬前置】P5 QA 账号标记**：
   P5 live 验证账号 `qa_eval_claude_code_p5honesty`（合成手机号 19900000731，
   canonical uid `9d603677-bb1c-4fd7-867e-865cab268b61`）已形成
   `phone_verification` 可信 phone alias（2026-07-10T02:47Z）。
   已活体验证：其 alias metadata 带全套机器身份标记
   （account_kind=eval_runner / actor_type=machine / is_internal_test=true），
   既有 eligibility 层（`_has_explicit_non_human_identity`）在最坏情况（UUID 显示名、
   无 qa_ 前缀可抓）下也会排除它，**不影响**基线。指挥官终裁（2026-07-10）：
   本标记从"数字读取前必须执行"降级为**可选**——审计表排除与 eligibility 兜底是
   两个不同事实层的 decider，非同一事实的双权威；若想让待办 2 的差值归因少一个
   变量，可先执行（审计表 append-only，重复执行只多一行同值流水，无副作用）：

   ```sql
   insert into public.bi_internal_accounts (user_id, is_internal, operator_id, reason)
   values (
     '9d603677-bb1c-4fd7-867e-865cab268b61',
     true,
     'claude_code_p3_acceptance_20260710',
     'P5 live 验证 QA 账号 qa_eval_claude_code_p5honesty（合成手机号 19900000731，eval_runner 机器身份），防止污染 P3 部署验收基线'
   );
   ```

1. **【顺序依赖】先执行 P4 迁移 `--apply`**：存量 1351 条 tutorbot 镜像行在迁移前仍带旧身份戳，
   会继续污染 `_merge_session_activity_for_member_list` 的会话派生；P3 会话派生类数字验收必须在
   P4 `--apply` 之后读取。P4+P3 合并部署后抽 3 名会员核 `last_active_at` 只来自 canonical 会话。
2. 部署 `fix/p3-bi-honest-metrics` 后调 `/api/v1/bi/members?days=30`：用基线取证的 phone-alias
   复算脚本同一时点重跑 before/after，断言 `dashboard.new_30d_count` 落入量级带 **60±10**，
   且 before/after 差值可由三个已命名部件完全解释：
   (a) 被排除的 bi_internal_accounts 内部账号数；(b) P5 qa 账号是否已被待办 0 标记；
   (c) 窗口内新增自然注册数。不能解释的残差 = 验收不通过，先归因再放行；
3. `/api/v1/bi/member-ops/internal-accounts` 端点仍能列出 426+ 条标记（展示端点复用同一读取核，不受影响）；
4. 增长漏斗 `registered_members` 步与留存 cohort 数量同步收缩（同一 `_load_all_members` 收口，无需单独口径）;
5. 执行本视图变更并跑上面的执行后验收；
6. 观察一个整点内 BI 面板无 5xx；fail-open 告警实体已验证：logger
   `deeptutor.services.bi_service`，WARNING 级，格式
   `internal account exclusion unavailable, fail-open: <原因>`（这是容器 log 实体，
   未接 Prometheus metric——验收期若看到该行，说明标记表读取在抖动，数字口径可能临时回退到未清洗）。
