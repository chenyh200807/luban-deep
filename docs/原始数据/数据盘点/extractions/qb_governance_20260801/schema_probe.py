import json, sbclient as S
sql = """
select column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema='public' and table_name='questions_bank'
order by ordinal_position;
"""
st, rows, _ = S.mgmt_sql(sql)
print("STATUS", st)
for r in rows:
    print(f"{r['column_name']:32s} {r['data_type']:28s} null={r['is_nullable']:3s} def={r['column_default']}")
