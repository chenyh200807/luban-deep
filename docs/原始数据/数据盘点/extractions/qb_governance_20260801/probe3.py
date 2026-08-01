import sbclient as S
q = lambda s: S.mgmt_sql(s)[1]
for r in q("select p.proname, pg_get_functiondef(p.oid) def from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and p.proname like 'qb_%';"):
    print("=====", r['proname']); print(r['def'])
