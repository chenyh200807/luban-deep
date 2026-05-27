# Migration Template + Checklist

> 新增 / 修改 public schema 之前必读。偏离任何条目必须在 PR description 写明 reason。本 README 是 markdown，不会被 supabase CLI apply（CLI 只扫 `*.sql`）。

本目录是 DeepTutor / 鲁班智考的数据 authority 入口之一。当前产品会把账户事实、钱包事实、Assessment TestSet、学习证据、错题、学习报告、会员经营后台和观测审计都落到 Supabase 相关表里；migration 不是“建表脚本仓库”，而是防止同一业务事实长出第二份未受 RLS / policy / comment 约束真相的边界。

项目级原则：

- 账户事实与学习事实分权：wallet / member authority 不能写进 learner profile 当第二份余额或会员真相。
- 学习事实以 `learning_evidence` 及其 read model 为主脊梁；新增表必须说明它是 canonical writer、projection、outbox、audit 还是临时 staging。
- Assessment / Topic Catalog / form bank 相关表默认 service-role only，除非 PR 明确证明客户端读写边界安全。
- 任何 public schema 新表都必须在同一 migration 内启 RLS，并写清楚默认 stance。

## 命名

- 文件名：`YYYYMMDDHHMMSS_<verb>_<noun>.sql`，14 位时间戳 + 下划线 + 小写蛇形
- 时间戳必须 ≥ `ls supabase/migrations/*.sql | tail -1` 的 prefix（Gate A 校验）
- 不允许复用别人的时间戳（即使后续部分不同）

## 新建 public.* 表 checklist

- [ ] `create table if not exists public.<X> (...)`
- [ ] **同一 migration 内** `alter table public.<X> enable row level security;`（Gate B 校验）
- [ ] **默认 stance 选 1**（必须显式）：
  - [ ] **service_role only**：`revoke all on public.<X> from anon; revoke all on public.<X> from authenticated;` + `comment on table public.<X> is '... Service-role only ...';`
  - [ ] **owner self-access**：
    ```sql
    create policy <X>_owner_select for select to authenticated using (auth.uid()::text = user_id);
    create policy <X>_owner_insert for insert to authenticated with check (auth.uid()::text = user_id);
    create policy <X>_owner_update for update to authenticated using (auth.uid()::text = user_id);
    create policy <X>_owner_delete for delete to authenticated using (auth.uid()::text = user_id);
    ```
  - [ ] **public read**（极少用，必须 PR reviewer 二次签字）
- [ ] 高频查询列建 index：`create index if not exists ...`
- [ ] `comment on table public.<X> is '...';` 说明业务用途 + RLS 设计
- [ ] 测试 `tests/supabase/test_<X>_rls.py` 验证 anon role 行为（0 行 / 401）

## 反模式（禁用）

- ❌ `enable row level security` 但 0 policy 又无 `comment` 说明意图（debug 时无法判断是 service-role-only 还是配置错误）
- ❌ `grant ... to anon` 不写显式理由
- ❌ 跨 user 数据没有 `auth.uid()::text = user_id` 之类 owner 检查
- ❌ 审计 / 日志表给 `authenticated` 读权限（合规反模式：审计应不可被审计者读）
- ❌ 修改既有 migration 的内容（migrations are append-only；prod 已 apply 不能 mutate）

## CI gate

- **Gate A**：`scripts/ci/check_migration_uniqueness.sh` —— timestamp 唯一性 + 单调
- **Gate B**：`scripts/ci/check_rls_on_create_table.sh` —— 新表必启 RLS
- 豁免：文件首行写 `-- rls-exempt: <reason>`（partition 子表、view、ext schema bridge）
- 跑 live audit 对照：`SUPABASE_DB_URL=... bash scripts/ci/live_rls_audit.sh > /tmp/post.json` + diff `docs/audit/rls_audit.json`

## 与 AGENTS.md 的关系

- 任何"加 router / classifier / wrapper / state" 冲动 → 先读 `AGENTS.md` §0 / §5.6 / §5.7
- 任何"顺手 refactor 邻近表" → `AGENTS.md` §3 Surgical Changes，禁止；本 PR 只动 explicitly-listed 表

## 历史教训（v2.1 SR2）

- 2026-04-19 同 timestamp `20260419000100_*.sql` × 2 (learner_state_rls + wallet_authority_phase1)：Supabase CLI apply 顺序未定义 → PR-2 修复 = 文件 rename 为 `20260419000110_wallet_authority_phase1.sql` + 各环境手工 `update schema_migrations.version`
- 2026-05-03 `assessment_forms` 建表时漏 enable RLS → anon 可读全部题库（PR-0 live audit 揭示）
- 2026 累积：27 张 public.* 表 RLS=off + anon grants 存在；本模板上线后 Gate B 防止再次发生
