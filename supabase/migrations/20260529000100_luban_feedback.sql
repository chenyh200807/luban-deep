-- 鲁班智考 · 内测回访问卷 (luban-html-js-wechat-required) 答卷存储
-- 与 public.invite_test_applications 同构：服务端 pg 直连写入，
-- 开启 RLS 且不建任何策略 => anon/authenticated 均无权限，仅 service-role/直连可写。
-- 匿名友好：除 id/created_at/raw_payload 外字段均可空（带默认值），不强制身份。

create table if not exists public.luban_feedback (
  id uuid primary key,
  created_at timestamptz not null default now(),
  source_page text not null default '',
  survey_version text not null default '',
  -- 关键量化指标（提为一等列，便于直接统计；全量答案见 raw_payload）
  nps smallint,
  overall_satisfaction smallint,
  most_valuable text not null default '',
  will_continue text not null default '',
  pay_willingness text not null default '',
  would_recommend text not null default '',
  revisit_willingness text not null default '',
  -- 关键开放题
  top_suggestion text not null default '',
  unsolved_pain text not null default '',
  -- 选填身份（仅回访用）
  phone text not null default '',
  wechat_id text not null default '',
  -- 元信息与运营
  user_agent text not null default '',
  status text not null default 'submitted',
  operator_note text not null default '',
  raw_payload jsonb not null default '{}'::jsonb,
  -- 取值约束：nps 0-10，满意度 1-5（允许为空）
  constraint luban_feedback_nps_range check (nps is null or (nps between 0 and 10)),
  constraint luban_feedback_satisfaction_range check (overall_satisfaction is null or (overall_satisfaction between 1 and 5))
);

alter table public.luban_feedback enable row level security;

create index if not exists idx_luban_feedback_created_at
  on public.luban_feedback (created_at desc);

create index if not exists idx_luban_feedback_nps
  on public.luban_feedback (nps);

create index if not exists idx_luban_feedback_will_continue
  on public.luban_feedback (will_continue);

create index if not exists idx_luban_feedback_phone
  on public.luban_feedback (phone);
