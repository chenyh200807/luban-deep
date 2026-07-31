"""Export the answer-conflict human-review list (B0 lane). Sourced from the B0 full backup,
so it carries the exact pre-C2 answer text of every conflicting row."""
import difflib, json, os, re
from collections import defaultdict
from ids import A
OUT = os.path.dirname(os.path.abspath(__file__))
def tb(x): return str(x) == 'True'

back = {r['id']: r for r in (json.loads(l) for l in open(os.path.join(OUT, 'backup_rows_before_c2.full.jsonl')))}
plan = {p['row_id']: p for p in (json.loads(l) for l in open(os.path.join(OUT, 'plan.jsonl')))}

def ans_text(ca):
    if ca is None: return ''
    if isinstance(ca, list): return '\n'.join(str(x) for x in ca)
    if isinstance(ca, (dict,)): return json.dumps(ca, ensure_ascii=False)
    return str(ca)
def norm(s):  return re.sub(r'[^一-鿿A-Za-z0-9]', '', s)

cells = defaultdict(list)
for r in A:
    if tb(r['index_answer_conflict']):
        cells[(r['case_group_id'], r['idx'])].append(r)

recs = []
for (gid, idx), rows in sorted(cells.items()):
    rows = sorted(rows, key=lambda r: r['row_id'])
    texts = {r['row_id']: ans_text(back[r['row_id']].get('correct_answer')) for r in rows}
    base_id = rows[0]['row_id']
    for r in rows:
        t = texts[r['row_id']]
        bt = texts[base_id]
        sim = difflib.SequenceMatcher(None, norm(bt), norm(t)).ratio()
        diff = [] if r['row_id'] == base_id else [
            l for l in difflib.unified_diff(bt.splitlines(), t.splitlines(),
                                            lineterm='', n=0) if l[:1] in '+-' and l[:3] not in ('+++', '---')][:12]
        recs.append({
            'row_id': r['row_id'], 'case_group_id': gid, 'subquestion_index': idx,
            'gen': r['gen'], 'original_id': r['original_id'],
            'answer_type': type(back[r['row_id']].get('correct_answer')).__name__,
            'answer_len': len(t),
            'answer_excerpt': t[:400],
            'is_diff_baseline': r['row_id'] == base_id,
            'baseline_row_id': base_id,
            'norm_similarity_vs_baseline': round(sim, 4),
            'diff_vs_baseline': diff,
            'cell_row_ids': [x['row_id'] for x in rows],
            'cell_gens': {x['row_id']: x['gen'] for x in rows},
            'c2_backfilled': r['row_id'] in plan,
            'c2_case_row_canonical': None,
            'review_reason': 'same (case_group_id, subquestion_index) carries >1 distinct answer text; '
                             'generation priority NOT applied — canonical left NULL pending human adjudication',
        })
p = os.path.join(OUT, 'answer_conflict_review.jsonl')
with open(p, 'w') as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print('rows', len(recs), 'cells', len(cells),
      'groups', len({r['case_group_id'] for r in recs}),
      'not_backfilled', sum(1 for r in recs if not r['c2_backfilled']))
print(p)
