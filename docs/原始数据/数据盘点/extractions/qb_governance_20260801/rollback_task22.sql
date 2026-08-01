-- Rollback Task#22 relabel (SQL form, equivalent to rollback_task22.py).
-- Restores question_type from the DB-side backup table captured before the write.
-- Idempotent: the essay guard makes a second run a no-op.
update public.questions_bank q
set question_type = b.old_question_type
from public.questions_bank_qtype_backup_20260801 b
where q.id = b.id
  and q.question_type = 'essay'
  and q.source_type in ('TEXTBOOK', 'textbook_exercise');

-- assert: 627 rows back to case_study, 0 essay left
select question_type, count(*) from public.questions_bank
where id in (select id from public.questions_bank_qtype_backup_20260801)
group by 1;
