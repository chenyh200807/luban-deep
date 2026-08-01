import json, gzip, sys, sbclient as S
FAIL=[]
def check(name, got, want):
    ok = got==want
    print(("PASS " if ok else "FAIL ")+f"{name}: got={got} want={want}")
    if not ok: FAIL.append(name)

go=set(json.load(open("go_ids.json"))); skip=set(json.load(open("skip_ids.json")))
counts=S.mgmt_sql("select question_type, source_type, count(*) n from public.questions_bank group by 1,2 order by 1,2;")[1]
cs={(r['question_type'],r['source_type']):r['n'] for r in counts}
tot=lambda qt: sum(v for k,v in cs.items() if k[0]==qt)

# A1 grand total unchanged (relabel, not delete)
check("A1 grand_total", sum(cs.values()), 4635)
# A2 essay == 627, exactly the two GO sources
check("A2 essay_total", tot('essay'), 627)
check("A2 essay_TEXTBOOK", cs.get(('essay','TEXTBOOK'),0), 112)
check("A2 essay_textbook_exercise", cs.get(('essay','textbook_exercise'),0), 515)
check("A2 essay_other_sources", sum(v for k,v in cs.items() if k[0]=='essay' and k[1] not in ('TEXTBOOK','textbook_exercise')), 0)
# A3 case_study remainder = 1959-627 = 1332, and the REAL_EXAM slice is untouched
check("A3 case_study_total", tot('case_study'), 1332)
check("A3 case_study_REAL_EXAM(真题案例,须不变)", cs.get(('case_study','REAL_EXAM'),0), 412)
check("A3 case_study_TEXTBOOK_ASSESSMENT(跳过批)", cs.get(('case_study','TEXTBOOK_ASSESSMENT'),0), 662)
check("A3 case_study_LECTURE_NOTE(跳过批)", cs.get(('case_study','LECTURE_NOTE_ASSESSMENT'),0), 258)
check("A3 case_study_TEXTBOOK(应清零)", cs.get(('case_study','TEXTBOOK'),0), 0)
check("A3 case_study_textbook_exercise(应清零)", cs.get(('case_study','textbook_exercise'),0), 0)
# A4 the exact id set that now holds 'essay' == go_ids
essay_ids={r['id'] for r in S.select_all("questions_bank","id",{"question_type":"eq.essay"})}
check("A4 essay_id_set == go_ids", essay_ids==go, True)
# A5 skipped batch untouched
skip_still={r['id'] for r in S.select_all("questions_bank","id",{"question_type":"eq.case_study","source_type":"in.(TEXTBOOK_ASSESSMENT,LECTURE_NOTE_ASSESSMENT)"})}
check("A5 skip_batch_still_case_study", skip_still==skip, True)
# A6 no other column moved: compare all non-question_type fields against the pre-write backup
old={json.loads(l)['id']: json.loads(l) for l in gzip.open("backup_task22_rows.jsonl.gz","rt")}
COLS="id,original_id,question_type,question_stem,options,correct_answer,analysis,source_type,source_chunk_id,case_group_id,case_subquestion_index,case_row_granularity,case_row_canonical,node_code,exam_year,content_hash"
new=S.select_all("questions_bank",COLS,{"id":"in.(%s)"%",".join(map(str,sorted(go)))})
drift=[]
for r in new:
    o=old[r['id']]
    for c in COLS.split(','):
        if c=='question_type': continue
        if r.get(c)!=o.get(c): drift.append((r['id'],c,o.get(c),r.get(c)))
check("A6 non_question_type_column_drift", len(drift), 0)
if drift: print("  drift sample:", drift[:5])
# A7 case_* columns still NULL on the relabeled set (they never belonged to a case group)
check("A7 case_group_id_all_null", sum(1 for r in new if r.get('case_group_id') is not None), 0)
# A8 dangling downstream refs unchanged (72) - relabel must not create or heal any
dang_before=set(json.load(open("dangling_refs.json")))
q=S.mgmt_sql("""select count(*) n from (select distinct (it->>'source_question_id')::bigint qid
 from public.assessment_forms f, lateral jsonb_array_elements(coalesce(f.items_json,'[]'::jsonb)) it
 where (it->>'source_question_id') ~ '^[0-9]+$') x where qid not in (select id from public.questions_bank);""")[1]
check("A8 dangling_form_refs", q[0]['n'], 1)
check("A8 dangling_total_baseline", len(dang_before), 72)
# A9 spot read-back 10 rows, human readable
import random; random.seed(7)
spot=sorted(random.sample(sorted(go),10))
_,rows,_=S.rest("questions_bank",params={"select":"id,question_type,source_type,question_stem,correct_answer","id":"in.(%s)"%",".join(map(str,spot)),"order":"id.asc"})
print("\n--- A9 抽 10 回读 ---")
for r in rows:
    ca=r['correct_answer']; ca=ca if isinstance(ca,str) else json.dumps(ca,ensure_ascii=False)
    print(f"  {r['id']} [{r['question_type']}/{r['source_type']}] {r['question_stem'][:46]} => {ca[:46]}")
check("A9 spot_all_essay", all(r['question_type']=='essay' for r in rows), True)

print("\n"+("ALL ASSERTIONS PASSED" if not FAIL else "FAILED: "+", ".join(FAIL)))
sys.exit(1 if FAIL else 0)
