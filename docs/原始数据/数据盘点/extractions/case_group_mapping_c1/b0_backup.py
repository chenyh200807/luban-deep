"""C2 / B0: back up every affected row (full column dump) before any write."""
import gzip, hashlib, json, os, sys
import sbclient as S
from ids import A, B, C, AFFECTED

OUT = os.path.dirname(os.path.abspath(__file__))
assert len(AFFECTED) == 385, f"expected 385 affected ids, got {len(AFFECTED)}"

rows = []
CH = 25
for i in range(0, len(AFFECTED), CH):
    chunk = AFFECTED[i:i + CH]
    _, got, _ = S.rest('questions_bank', params={
        'select': '*', 'id': 'in.(%s)' % ','.join(map(str, chunk)), 'order': 'id.asc', 'limit': 1000})
    rows.extend(got)
    print(f'  fetched {len(rows)}/{len(AFFECTED)}', flush=True)

assert len(rows) == 385, f"backup fetched {len(rows)} rows, expected 385"
assert sorted(r['id'] for r in rows) == AFFECTED, "backup id set != affected id set"

full = os.path.join(OUT, 'backup_rows_before_c2.full.jsonl')
with open(full, 'w') as f:
    for r in sorted(rows, key=lambda r: r['id']):
        f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n')

# repo-safe digest: id + per-row sha256 of the canonical JSON + the 4 new columns' pre-state
digest = os.path.join(OUT, 'backup_rows_before_c2.jsonl')
NEW = ['case_group_id', 'case_subquestion_index', 'case_row_granularity', 'case_row_canonical']
with open(digest, 'w') as f:
    for r in sorted(rows, key=lambda r: r['id']):
        blob = json.dumps(r, ensure_ascii=False, sort_keys=True).encode()
        f.write(json.dumps({
            'id': r['id'],
            'original_id': r.get('original_id'),
            'exam_year': r.get('exam_year'),
            'source_type': r.get('source_type'),
            'question_type': r.get('question_type'),
            'row_sha256': hashlib.sha256(blob).hexdigest(),
            'pre_c2_new_cols': {k: r.get(k, '<column-absent>') for k in NEW},
        }, ensure_ascii=False) + '\n')
with open(digest, 'rb') as fi, gzip.open(digest + '.gz', 'wb') as fo:
    fo.writelines(fi)

print('full backup :', full, os.path.getsize(full), 'bytes')
print('digest      :', digest + '.gz', os.path.getsize(digest + '.gz'), 'bytes')
print('rows        :', len(rows))
print('columns/row :', len(rows[0]))
