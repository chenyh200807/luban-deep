-- 方案 C / C2：questions_bank 题级归属列（增量、可空、非破坏）
-- 只 ADD COLUMN；不加约束、不加索引（索引待 C3 按真实查询形状决定）。
alter table public.questions_bank
  add column if not exists case_group_id          text,
  add column if not exists case_subquestion_index smallint,
  add column if not exists case_row_granularity   text,
  add column if not exists case_row_canonical     boolean;

comment on column public.questions_bank.case_group_id is
  '题级组 id，形如 {exam_year}-case{N}。一经写入不可变；新组只追加 max(N)+1，绝不重排。见 contracts/rag.md §case_group_id 合同。';
comment on column public.questions_bank.case_subquestion_index is
  '案例小问序号（1..N）。仅 case_row_granularity=subquestion 且有原文序号证据时写；整题行必须为 NULL。';
comment on column public.questions_bank.case_row_granularity is
  '行粒度：subquestion=一行一小问；whole_question=一行含该案例全部小问。';
comment on column public.questions_bank.case_row_canonical is
  '同 (case_group_id, case_subquestion_index) 多入库世代时的收权位。NULL=未裁决（答案冲突，待人审），不得当 false 用。';
