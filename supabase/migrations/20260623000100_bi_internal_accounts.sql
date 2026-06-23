-- bi_internal_accounts: BI 内部账号标记的不可删改审计流水。
-- 语义：每一行是一次"标记/取消标记"操作，当前状态 = 该 user_id 最新一行的 is_internal 值。
-- 所有写入必须附带 operator_id（操作人）和 reason（原因），防止下面人以内部名义做手脚。
-- 只有 service_role 可访问（BI 后端使用 service_role key）。

begin;

create table if not exists public.bi_internal_accounts (
  id          uuid        default gen_random_uuid() primary key,
  user_id     text        not null,
  is_internal boolean     not null,
  operator_id text        not null,
  reason      text        not null check (char_length(trim(reason)) >= 5),
  created_at  timestamptz default now() not null
);

create index if not exists bi_internal_accounts_user_id_created_at_idx
  on public.bi_internal_accounts (user_id, created_at desc);

create index if not exists bi_internal_accounts_created_at_idx
  on public.bi_internal_accounts (created_at desc);

-- RLS: 无公开策略 = 仅 service_role 绕过 RLS 访问；anon/authenticated 一律拒绝
alter table public.bi_internal_accounts enable row level security;
alter table public.bi_internal_accounts force row level security;

commit;
