import json, gzip, sbclient as S
COLS = "id,original_id,question_type,node_code,question_stem,stem,options,correct_answer,analysis,grading_rubric,parent_id,background_context,source_type,exam_year,exam_session,source,source_chunk_id,source_meta,attributes,based_on_version,testing_focus,trap_type,content_hash,case_group_id,case_subquestion_index,case_row_granularity,case_row_canonical,tags,difficulty,structured_rules,grading_keywords,logic_rule,option_reasoning"
rows = S.select_all("questions_bank", COLS,
    {"question_type": "eq.case_study", "source_type": "in.(TEXTBOOK_ASSESSMENT,textbook_exercise,LECTURE_NOTE_ASSESSMENT,TEXTBOOK)"})
print("pulled", len(rows))
from collections import Counter
print(Counter(r['source_type'] for r in rows))
with gzip.open("backup_task22_rows.jsonl.gz", "wt") as f:
    for r in sorted(rows, key=lambda x: x['id']):
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
json.dump(sorted(r['id'] for r in rows), open("task22_ids.json","w"))
# cross-check vs C1 unassignable.csv
import csv
c1 = {int(x['row_id']) for x in csv.DictReader(open('../case_group_mapping_c1/unassignable.csv')) if x['source_type']!='REAL_EXAM'}
live = {r['id'] for r in rows}
print("c1_nonrealexam", len(c1), "live", len(live), "identical", c1==live, "only_c1", len(c1-live), "only_live", len(live-c1))
