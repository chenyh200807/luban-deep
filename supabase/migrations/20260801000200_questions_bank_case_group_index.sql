-- rls-exempt: 只加索引，未新建任何 public.* 表（Gate B 豁免）
-- 方案 C / C3：题级组取全查询的支撑索引。
--
-- C2 (20260801000100) 只加列不加索引，把索引形状留给 C3 的真实查询决定。
-- C3 的热查询恰好只有一条形状（deeptutor/services/rag/pipelines/supabase.py
-- `_fetch_case_group_rows`）：
--     questions_bank?case_group_id=eq.<组键>
--                   &case_row_canonical=not.is.false
--                   &question_type=eq.case_study
--                   &limit=12
-- 因此建 partial index：谓词与查询恒等（`case_group_id is not null`），
-- 只索引 383/4635 行（8%），不为 1574 行误标 case_study 的教材题付索引代价。
create index if not exists questions_bank_case_group_id_idx
  on public.questions_bank (case_group_id)
  where case_group_id is not null;

comment on index public.questions_bank_case_group_id_idx is
  '方案C/C3 题级组取全查询支撑索引（partial，只覆盖已建题级归属的行）。'
  '消费方=SupabasePipeline._fetch_case_group_rows；合同见 contracts/rag.md §45。';
