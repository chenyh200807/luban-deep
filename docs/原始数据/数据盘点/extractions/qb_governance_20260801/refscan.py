import json, sbclient as S
SQL = """
with refs as (
  select 'assessment_forms:'||f.status as holder, (it->>'source_question_id') as qid
  from public.assessment_forms f, lateral jsonb_array_elements(coalesce(f.items_json,'[]'::jsonb)) it
  union all
  select 'assessment_sessions:client', (it->>'source_question_id')
  from public.assessment_sessions s, lateral jsonb_array_elements(coalesce(s.client_questions_public,'[]'::jsonb)) it
  union all
  select 'assessment_sessions:private', (it->>'source_question_id')
  from public.assessment_sessions s, lateral jsonb_array_elements(coalesce(s.session_questions_private,'[]'::jsonb)) it
  union all
  select 'assessment_sessions:report', (it->>'source_question_id')
  from public.assessment_sessions s, lateral jsonb_array_elements(
       case when jsonb_typeof(s.result_report_json->'items')='array' then s.result_report_json->'items' else '[]'::jsonb end) it
  union all
  select 'active_questions', a.question_id from public.active_questions a
  union all
  select 'learner_mistake_book_items', m.question_id from public.learner_mistake_book_items m
  union all
  select 'knowledge_question_links', k.question_id::text from public.knowledge_question_links k
  union all
  select 'question_intelligence', qi.question_id::text from public.question_intelligence qi
)
select holder, qid, count(*) n from refs
where qid is not null and qid ~ '^[0-9]+$'
group by 1,2;
"""
st, rows, _ = S.mgmt_sql(SQL)
print("status", st, "ref rows", len(rows))
json.dump(rows, open("refs_raw.json","w"))
import collections
held = collections.defaultdict(set)
for r in rows: held[int(r['qid'])].add(r['holder'])
json.dump({str(k): sorted(v) for k,v in held.items()}, open("refs_by_qid.json","w"), ensure_ascii=False)
print("distinct referenced qids", len(held))
print(collections.Counter(r['holder'] for r in rows))
# dangling
import gzip
live = {json.loads(l)['id'] for l in gzip.open("qb_full_snapshot.jsonl.gz","rt")}
dang = sorted(q for q in held if q not in live)
print("DANGLING refs (qid not in questions_bank):", len(dang))
print(dang)
json.dump(dang, open("dangling_refs.json","w"))
