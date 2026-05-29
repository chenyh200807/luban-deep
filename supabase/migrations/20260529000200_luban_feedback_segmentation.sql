-- 鲁班智考 · 内测回访问卷：补充「被访者背景」分层维度
-- 目的：让回访数据可按「考试次数 / 距考时间 / 使用频次」分群解读
--      （NPS=7 的一战考生 vs 二战考生含义截然不同）。
-- 与既有列一致：text not null default ''，匿名友好、可空（空串）。
-- ADD COLUMN ... DEFAULT '' 对现有行安全（建表初始为空，且 0 业务行）。

alter table public.luban_feedback
  add column if not exists attempt_count text not null default '',     -- first / second / third_plus
  add column if not exists exam_timeframe text not null default '',    -- within_1m / 1to3m / 3to6m / over_6m / passed
  add column if not exists usage_frequency text not null default '';   -- rarely / 1to2 / 3to5 / daily

-- 分层统计常用维度，建索引便于 GROUP BY 查询
create index if not exists idx_luban_feedback_attempt_count
  on public.luban_feedback (attempt_count);

create index if not exists idx_luban_feedback_usage_frequency
  on public.luban_feedback (usage_frequency);
