import json, sbclient as S
ids = json.load(open("go_ids.json"))
idlist = ",".join(map(str, ids))
# 1) DB-side backup table (id + old question_type), idempotent-safe name
ddl = f"""
create table if not exists public.questions_bank_qtype_backup_20260801 as
select id, question_type as old_question_type, source_type, now() as captured_at
from public.questions_bank where id in ({idlist});
select count(*) n, count(distinct old_question_type) k, min(old_question_type) v
from public.questions_bank_qtype_backup_20260801;
"""
st, rows, _ = S.mgmt_sql(ddl)
print("backup table:", st, rows)
# 2) baseline counts
base = S.mgmt_sql("""select question_type, source_type, count(*) n from public.questions_bank
group by 1,2 order by 1,2;""")[1]
json.dump(base, open("baseline_counts.json","w"), ensure_ascii=False, indent=1)
print("baseline case_study total:", sum(r['n'] for r in base if r['question_type']=='case_study'))
print("baseline essay total:", sum(r['n'] for r in base if r['question_type']=='essay'))
print("baseline grand total:", sum(r['n'] for r in base))
