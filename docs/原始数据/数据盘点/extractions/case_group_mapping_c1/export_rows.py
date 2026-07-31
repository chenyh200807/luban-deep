#!/usr/bin/env python3
"""只读导出 questions_bank case 行 -> raw_case_rows.jsonl"""
import json, os, re, sys
import psycopg2

ENV = "/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.env"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_case_rows.jsonl")

db = None
for line in open(ENV, encoding="utf-8"):
    if line.startswith("DB_URL="):
        db = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
assert db, "no DB_URL"

SQL = """
select id, original_id, question_type, node_code, source_type, source, exam_year, exam_session,
       source_chunk_id, source_meta::text, content_hash, parent_id,
       coalesce(stem, question_stem, '') as stem_text,
       (correct_answer is not null and correct_answer::text not in ('null','""','[]','{}')) as has_answer,
       jsonb_typeof(correct_answer) as ans_type,
       length(coalesce(correct_answer::text,'')) as ans_len,
       correct_answer::text as ans_text,
       (analysis is not null and length(analysis)>0) as has_analysis,
       (grading_rubric is not null and grading_rubric::text not in ('null','[]','{}')) as has_rubric,
       (grading_keywords is not null and grading_keywords::text not in ('null','[]','{}')) as has_keywords
from public.questions_bank
where question_type = 'case_study'
order by id
"""

conn = psycopg2.connect(db)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor()
cur.execute(SQL)
cols = [d[0] for d in cur.description]
n = 0
with open(OUT, "w", encoding="utf-8") as f:
    for row in cur:
        d = dict(zip(cols, row))
        d["source_meta"] = json.loads(d["source_meta"]) if d["source_meta"] else {}
        f.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
        n += 1
print("rows:", n, "->", OUT)
