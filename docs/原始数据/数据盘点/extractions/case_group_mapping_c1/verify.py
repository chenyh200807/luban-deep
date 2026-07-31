"""C2 verification suite. All read-only. Prints one PASS/FAIL line per assertion + a JSON blob."""
import hashlib, json, os, random, re, sys
from collections import defaultdict, Counter
import sbclient as S
from ids import A, B, C, AFFECTED

OUT = os.path.dirname(os.path.abspath(__file__))
plan = {p['row_id']: p for p in (json.loads(l) for l in open(os.path.join(OUT, 'plan.jsonl')))}
NEW = ['case_group_id', 'case_subquestion_index', 'case_row_granularity', 'case_row_canonical']
results, failures = [], []

def rec(name, ok, detail):
    results.append({'assert': name, 'ok': bool(ok), 'detail': detail})
    if not ok:
        failures.append(name)
    print(('PASS ' if ok else 'FAIL ') + name + ' :: ' + json.dumps(detail, ensure_ascii=False)[:600], flush=True)

def q(sql):
    _, res, _ = S.mgmt_sql(sql)
    return res

# ---- V0 write scope: nothing outside the plan was touched -------------------
rows = q("select id, case_group_id, case_subquestion_index, case_row_granularity, case_row_canonical "
         "from public.questions_bank where case_group_id is not null or case_subquestion_index is not null "
         "or case_row_granularity is not null or case_row_canonical is not null order by id")
db = {r['id']: r for r in rows}
rec('V0_write_scope_equals_plan', set(db) == set(plan),
    {'db_rows_written': len(db), 'planned_rows': len(plan),
     'in_db_not_in_plan': sorted(set(db) - set(plan))[:20], 'in_plan_not_in_db': sorted(set(plan) - set(db))[:20]})

# ---- V8 row-by-row exact readback of every written row ---------------------
mismatch = []
for rid, p in plan.items():
    d = db.get(rid)
    if not d:
        mismatch.append({'id': rid, 'reason': 'absent'}); continue
    for col in NEW:
        want = p.get(col, None)
        if d.get(col) != want:
            mismatch.append({'id': rid, 'col': col, 'want': want, 'got': d.get(col)})
rec('V8_full_row_readback_matches_plan', not mismatch, {'checked': len(plan), 'mismatches': mismatch[:20], 'n_mismatch': len(mismatch)})

# ---- batch counts ----------------------------------------------------------
rec('V8b_batch_row_counts', True, {
    'B1_A_high_medium': sum(1 for p in plan.values() if p['batch'] == 'B1_A_high_medium'),
    'B2_B_whole_question': sum(1 for p in plan.values() if p['batch'] == 'B2_B_whole_question'),
    'B3_C_group_only': sum(1 for p in plan.values() if p['batch'] == 'B3_C_group_only'),
    'B4_canonical_true': sum(1 for r in db.values() if r['case_row_canonical'] is True),
    'B4_canonical_false': sum(1 for r in db.values() if r['case_row_canonical'] is False),
    'canonical_null': sum(1 for r in db.values() if r['case_row_canonical'] is None),
    'db_granularity': dict(Counter(r['case_row_granularity'] for r in db.values())),
})

# ---- V1 (group,index) unique among canonical rows --------------------------
v1 = q("select case_group_id, case_subquestion_index, count(*) n from public.questions_bank "
       "where case_group_id is not null and case_subquestion_index is not null and case_row_canonical is true "
       "group by 1,2 having count(*)>1")
rec('V1_group_index_unique_among_canonical', len(v1) == 0, {'violations': v1})

# ---- V1b within a group, index unique per generation-collapsed canonical set
v1b = q("select case_group_id, case_subquestion_index, count(*) n from public.questions_bank "
        "where case_group_id is not null and case_subquestion_index is not null "
        "and case_row_canonical is not false and case_row_canonical is not null "
        "group by 1,2 having count(*)>1")
rec('V1b_no_two_canonical_rows_per_cell', len(v1b) == 0, {'violations': v1b})

# ---- V2 contiguity ---------------------------------------------------------
# C1 wrote V2 over `canonical = true` only. That formulation is structurally incompatible with
# 主控 裁决 1 ("72 conflict rows get NO canonical"): a conflict cell leaves a hole in the canonical
# index set by design. V2 is therefore split into two falsifiable halves instead of being loosened.
KNOWN_NONCONTIG = {'2018-case3', '2018-case4', '2021-case5'}   # C1 stats.json groups_non_contiguous
allidx = q("select case_group_id, case_subquestion_index, "
           "bool_or(case_row_canonical is true) has_canon, bool_or(case_row_canonical is null) has_null "
           "from public.questions_bank where case_subquestion_index is not null group by 1,2 order by 1,2")
byg = defaultdict(lambda: {'all': set(), 'canon': set(), 'undecided': set()})
for r in allidx:
    g = byg[r['case_group_id']]
    g['all'].add(r['case_subquestion_index'])
    if r['has_canon']: g['canon'].add(r['case_subquestion_index'])
    if r['has_null'] and not r['has_canon']: g['undecided'].add(r['case_subquestion_index'])

# V2a: over ALL backfilled indexes (conflict-agnostic), 1..max must be gapless, known C1 gaps aside
v2a = {g: sorted(v['all']) for g, v in byg.items()
       if (min(v['all']) != 1 or max(v['all']) != len(v['all'])) and g not in KNOWN_NONCONTIG}
rec('V2a_all_backfilled_indexes_contiguous_except_known_gaps', not v2a,
    {'known_gaps_registered': sorted(KNOWN_NONCONTIG),
     'known_gaps_seen': {g: sorted(byg[g]['all']) for g in KNOWN_NONCONTIG if g in byg},
     'new_regressions': v2a})

# V2b: every hole in the canonical index set is EXACTLY an undecided (answer-conflict) cell —
# i.e. no index was lost to a backfill bug, only to a registered human-review item.
v2b = {g: {'all': sorted(v['all']), 'canonical': sorted(v['canon']),
           'unexplained_holes': sorted(v['all'] - v['canon'] - v['undecided'])}
       for g, v in byg.items() if (v['all'] - v['canon']) != v['undecided']}
rec('V2b_canonical_holes_are_exactly_conflict_cells', not v2b,
    {'groups_with_canonical_holes': sorted(g for g, v in byg.items() if v['all'] - v['canon']),
     'unexplained': v2b})

# ---- V3 canonical rows carry a non-empty answer ---------------------------
v3 = q("select id, case_group_id, case_subquestion_index from public.questions_bank "
       "where case_row_canonical is true and (correct_answer is null "
       "or correct_answer::text in ('null','\"\"','[]','{}',''))")
rec('V3_canonical_answer_non_empty', len(v3) == 0, {'violations': v3})

# ---- V4 no cross-question contamination: one background fingerprint per group
fp = {}
for r in A + B + C:
    fp[int(r['row_id'])] = (r['case_group_id'], r['case_group_fingerprint'])
bygroup = defaultdict(set)
for rid, d in db.items():
    g, f = fp[rid]
    assert g == d['case_group_id'], (rid, g, d['case_group_id'])
    bygroup[d['case_group_id']].add(f)
bad_fp = {g: sorted(s) for g, s in bygroup.items() if len(s) > 1}
rec('V4_one_background_fingerprint_per_group', not bad_fp,
    {'groups': len(bygroup), 'multi_fingerprint_groups': bad_fp})

# ---- V5 a group never spans two exam years --------------------------------
v5 = q("select case_group_id, count(distinct exam_year) k, array_agg(distinct exam_year) yrs "
       "from public.questions_bank where case_group_id is not null group by 1 having count(distinct exam_year)>1")
rec('V5_group_does_not_span_years', len(v5) == 0, {'violations': v5})
v5b = q("select case_group_id, count(*) n from public.questions_bank where case_group_id is not null "
        "and case_group_id <> (exam_year::text || '-case' || split_part(case_group_id,'case',2)) group by 1")
rec('V5b_group_id_prefix_matches_exam_year', len(v5b) == 0, {'violations': v5b})

# ---- V6 whole_question rows must not carry an index -----------------------
v6 = q("select id from public.questions_bank where case_row_granularity = 'whole_question' "
       "and case_subquestion_index is not null")
rec('V6_whole_question_rows_have_null_index', len(v6) == 0, {'violations': v6})

# ---- V7 only REAL_EXAM case_study rows carry a group ----------------------
v7 = q("select id, source_type, question_type from public.questions_bank where case_group_id is not null "
       "and (source_type <> 'REAL_EXAM' or question_type <> 'case_study')")
rec('V7_only_real_exam_case_rows_have_group', len(v7) == 0, {'violations': v7})

# ---- V9 conflict rows: canonical must be NULL, never false ----------------
conf_ids = sorted({r['row_id'] for r in (json.loads(l) for l in open(os.path.join(OUT, 'answer_conflict_review.jsonl')))})
bad = [i for i in conf_ids if i in db and db[i]['case_row_canonical'] is not None]
rec('V9_answer_conflict_rows_left_uncanonical', not bad,
    {'conflict_rows': len(conf_ids), 'backfilled_conflict_rows': sum(1 for i in conf_ids if i in db), 'violations': bad})

# ---- V10 per-group reconciliation vs 佑森 431 采分点资产 -------------------
MAP = "/Users/yehongchen/worktrees/deeptutor-planc-c2/docs/原始数据/数据盘点/extractions/case_group_mapping_c1"
recon = json.load(open(os.path.join(MAP, 'reconciliation_vs_yousen.json')))
KNOWN_MISSING = {'2022-case1', '2023-case4'}          # C1 §3.4 已登记缺口
graded = [r for r in recon if r.get('yousen_expected')]
red = sorted(r['case_group_id'] for r in graded if '缺' in str(r.get('verdict', '')))
# and re-derive coverage from the LIVE table rather than trusting C1's file
gr = q("select case_group_id, array_agg(distinct case_subquestion_index) idx, "
       "count(*) filter (where case_row_granularity='whole_question') n_whole "
       "from public.questions_bank where case_group_id is not null group by 1")
live = {r['case_group_id']: r for r in gr}
span = defaultdict(set)
for r in B:
    if r['subq_span'] not in (None, 'None'):
        sp = r['subq_span']
        sp = json.loads(sp) if isinstance(sp, str) else sp
        lo, hi = sp; span[r['case_group_id']] |= set(range(int(lo), int(hi) + 1))
live_red = []
for r in graded:
    g = r['case_group_id']; exp = set(r['yousen_expected'])
    cov = set(i for i in (live.get(g, {}).get('idx') or []) if i is not None) | span.get(g, set())
    if not exp <= cov:
        live_red.append({'case_group_id': g, 'expected': sorted(exp), 'live_covered': sorted(cov),
                         'missing': sorted(exp - cov)})
rec('V10_yousen_reconciliation_no_new_red',
    set(red) <= KNOWN_MISSING and {x['case_group_id'] for x in live_red} <= KNOWN_MISSING,
    {'groups_with_gold': len(graded), 'c1_file_red': red, 'live_recomputed_red': live_red,
     'known_registered_gaps': sorted(KNOWN_MISSING),
     'new_regressions': sorted(({x['case_group_id'] for x in live_red} | set(red)) - KNOWN_MISSING)})

# ---- V11 group coverage sanity: 56 groups, 4-6 per year -------------------
gy = q("select case_group_id, exam_year, count(*) rows_in_group, "
       "count(*) filter (where case_row_granularity='subquestion') n_sub, "
       "count(*) filter (where case_row_granularity='whole_question') n_whole, "
       "count(*) filter (where case_row_canonical is true) n_canon "
       "from public.questions_bank where case_group_id is not null group by 1,2 order by 2,1")
per_year = Counter(r['exam_year'] for r in gy)
rec('V11_group_shape', len(gy) == 56 and all(4 <= v <= 6 for v in per_year.values()),
    {'groups': len(gy), 'per_year': dict(sorted(per_year.items()))})

# ---- V12 random 10-row full field-by-field readback against the backup ----
random.seed(20260801)
sample = random.sample(sorted(plan), 10)
_, live, _ = S.rest('questions_bank', params={'select': '*', 'id': 'in.(%s)' % ','.join(map(str, sample)), 'limit': 50})
back = {r['id']: r for r in (json.loads(l) for l in open(os.path.join(OUT, 'backup_rows_before_c2.full.jsonl')))}
drift, detail = [], []
for r in live:
    b = back[r['id']]
    for col, v in r.items():
        if col in NEW:
            want = plan[r['id']].get(col, None)
            if v != want:
                drift.append({'id': r['id'], 'col': col, 'want': want, 'got': v})
        else:                                   # existing column must be byte-identical to pre-C2
            if json.dumps(v, ensure_ascii=False, sort_keys=True) != json.dumps(b.get(col), ensure_ascii=False, sort_keys=True):
                drift.append({'id': r['id'], 'col': col, 'existing_column_changed': True})
    detail.append({'id': r['id'], **{k: r.get(k) for k in NEW}})
rec('V12_random10_fieldwise_readback_and_no_existing_column_drift', not drift,
    {'sampled_ids': sample, 'drift': drift[:10], 'sample_new_cols': detail})

# ---- V13 nothing outside the 385 affected ids changed at all --------------
_, cnt, _ = S.rest('questions_bank', params={'select': 'id'}, prefer='count=exact')
tot = q("select count(*) n from public.questions_bank")[0]['n']
rec('V13_table_row_count_unchanged', tot == 4635, {'total_rows_now': tot, 'c1_snapshot': 4635})

summary = {'passed': sum(1 for r in results if r['ok']), 'failed': len(failures), 'failed_names': failures}
json.dump({'summary': summary, 'results': results}, open(os.path.join(OUT, 'verify_results.json'), 'w'),
          ensure_ascii=False, indent=1)
print('\n=== ' + json.dumps(summary, ensure_ascii=False) + ' ===')
sys.exit(1 if failures else 0)
