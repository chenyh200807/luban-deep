import json, sbclient as S
q = lambda s: S.mgmt_sql(s)[1]
print("== constraints on questions_bank ==")
for r in q("""select con.conname, con.contype, pg_get_constraintdef(con.oid) def
from pg_constraint con join pg_class c on c.oid=con.conrelid
join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relname='questions_bank';"""):
    print(r)
print("\n== distinct question_type x source_type ==")
for r in q("""select question_type, source_type, count(*) n from public.questions_bank
group by 1,2 order by 1,2;"""):
    print(f"{str(r['question_type']):24s} {str(r['source_type']):24s} {r['n']}")
print("\n== total ==", q("select count(*) n from public.questions_bank")[0])
