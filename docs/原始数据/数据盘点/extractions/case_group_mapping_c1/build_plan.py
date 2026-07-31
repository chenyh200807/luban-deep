"""C2: build the deterministic write plan (no DB access). Output: plan.jsonl + plan_summary.json."""
import json, os
from collections import defaultdict, Counter
from ids import A, B, C, AFFECTED

OUT = os.path.dirname(os.path.abspath(__file__))
def tb(x): return str(x) == 'True'

# --- 主控裁决 1: canonical 世代优先序 (新 > 旧) ---
GEN_RANK = {'g3_exam_year': 0, 'g2_exam_chunk': 1, 'g1_auto': 2, 'g0_xw': 3}

plan = {}   # row_id -> dict of column values (only keys present are written)

# batch 1: A class, high+medium (low 2 rows skipped per directive)
skipped_low = []
for r in A:
    if r['confidence'] == 'low':
        skipped_low.append(r); continue
    plan[r['row_id']] = {'batch': 'B1_A_high_medium',
                         'case_group_id': r['case_group_id'],
                         'case_subquestion_index': r['idx'],
                         'case_row_granularity': 'subquestion'}
# batch 2: B class whole-question rows
for r in B:
    plan[r['row_id']] = {'batch': 'B2_B_whole_question',
                         'case_group_id': r['case_group_id'],
                         'case_subquestion_index': None,
                         'case_row_granularity': 'whole_question'}
# batch 3: C class group-only
for r in C:
    plan[r['row_id']] = {'batch': 'B3_C_group_only',
                         'case_group_id': r['case_group_id'],
                         'case_subquestion_index': None,
                         'case_row_granularity': 'subquestion'}

# batch 4: canonical over the A-class (group,index) cells
cells = defaultdict(list)
for r in A:
    if r['confidence'] == 'low':
        continue
    cells[(r['case_group_id'], r['idx'])].append(r)

canon = {'true': 0, 'false': 0, 'null_conflict': 0}
conflict_cells = []
for key, rows in cells.items():
    if any(tb(r['index_answer_conflict']) for r in rows):
        conflict_cells.append((key, rows))
        canon['null_conflict'] += len(rows)
        continue                                   # 72 行留 NULL，交人审
    winner = sorted(rows, key=lambda r: (GEN_RANK.get(r['gen'], 9), r['row_id']))[0]
    for r in rows:
        is_w = r['row_id'] == winner['row_id']
        plan[r['row_id']]['case_row_canonical'] = is_w
        plan[r['row_id']]['canonical_cell_size'] = len(rows)
        canon['true' if is_w else 'false'] += 1

summary = {
    'affected_rows_total': len(AFFECTED),
    'plan_rows_total': len(plan),
    'batches': dict(Counter(v['batch'] for v in plan.values())),
    'skipped_low_confidence_ids': sorted(int(r['row_id']) for r in skipped_low),
    'canonical': canon,
    'canonical_cells_total': len(cells),
    'canonical_cells_singleton': sum(1 for v in cells.values() if len(v) == 1),
    'canonical_cells_multi_resolved': sum(1 for k, v in cells.items() if len(v) > 1 and not any(tb(r['index_answer_conflict']) for r in v)),
    'canonical_cells_conflict': len(conflict_cells),
    'gen_priority': GEN_RANK,
}
with open(os.path.join(OUT, 'plan.jsonl'), 'w') as f:
    for rid in sorted(plan):
        f.write(json.dumps({'row_id': rid, **plan[rid]}, ensure_ascii=False) + '\n')
with open(os.path.join(OUT, 'plan_summary.json'), 'w') as f:
    json.dump(summary, f, ensure_ascii=False, indent=1)
with open(os.path.join(OUT, 'conflict_cells.json'), 'w') as f:
    json.dump([{'case_group_id': k[0], 'subquestion_index': k[1],
                'row_ids': sorted(int(r['row_id']) for r in rows),
                'gens': {int(r['row_id']): r['gen'] for r in rows}}
               for k, rows in sorted(conflict_cells)], f, ensure_ascii=False, indent=1)
print(json.dumps(summary, ensure_ascii=False, indent=1))
