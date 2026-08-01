import json,gzip,sbclient as S
COLS=("id,original_id,question_type,node_code,question_stem,stem,options,correct_answer,analysis,"
      "grading_rubric,parent_id,background_context,source_type,exam_year,exam_session,source,"
      "source_chunk_id,source_meta,attributes,based_on_version,content_hash,structured_rules,"
      "grading_keywords,logic_rule,difficulty,tags,testing_focus,trap_type,option_reasoning,"
      "case_group_id,case_subquestion_index,case_row_granularity,case_row_canonical,"
      "related_image,image_url,related_image_path,cited_standard_codes,taxonomy_confidence,error_rate")
rows=S.select_all("questions_bank",COLS)
print("qb rows",len(rows))
with gzip.open("qb_full_snapshot.jsonl.gz","wt") as f:
    for r in rows: f.write(json.dumps(r,ensure_ascii=False)+"\n")
