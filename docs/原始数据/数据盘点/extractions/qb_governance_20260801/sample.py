import gzip, json, random, re, sys
rows=[json.loads(l) for l in gzip.open("backup_task22_rows.jsonl.gz","rt")]
by={}
for r in rows: by.setdefault(r['source_type'],[]).append(r)
random.seed(20260801)
out=[]
for st in ["TEXTBOOK_ASSESSMENT","textbook_exercise","LECTURE_NOTE_ASSESSMENT","TEXTBOOK"]:
    grp=sorted(by[st],key=lambda x:x['id'])
    pick=random.sample(grp,10)
    for r in sorted(pick,key=lambda x:x['id']):
        out.append(r)
        stem=(r.get('question_stem') or r.get('stem') or '')
        ans=json.dumps(r.get('correct_answer'),ensure_ascii=False) if r.get('correct_answer') is not None else 'NULL'
        opts=r.get('options')
        print(f"--- [{st}] id={r['id']} orig={r['original_id']} year={r['exam_year']} node={r['node_code']} opts={('n='+str(len(opts)) if isinstance(opts,list) and opts else 'NONE')}")
        print("STEM:", re.sub(r'\s+',' ',stem)[:400])
        print("ANS :", re.sub(r'\s+',' ',ans)[:260])
        print("ANLZ:", re.sub(r'\s+',' ',(r.get('analysis') or ''))[:160])
        print("BG  :", re.sub(r'\s+',' ',(r.get('background_context') or ''))[:120])
json.dump([r['id'] for r in out], open("sample_ids.json","w"))
