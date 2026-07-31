"""C2 backfill writer. One batch per invocation. Every PATCH is id-pinned + type-guarded,
touches ONLY the 4 new columns, and is verified by return=representation before moving on."""
import json, os, sys, time
from collections import defaultdict
import sbclient as S

OUT = os.path.dirname(os.path.abspath(__file__))
NEWCOLS = ['case_group_id', 'case_subquestion_index', 'case_row_granularity', 'case_row_canonical']

def load_plan():
    return [json.loads(l) for l in open(os.path.join(OUT, 'plan.jsonl'))]

def patch(ids, values, dry):
    """PATCH the given ids with `values`. Guarded by question_type/source_type so a bad id cannot
    reach a non-case row. Returns the rows PostgREST actually wrote."""
    assert ids and set(values) <= set(NEWCOLS), values
    if dry:
        return [{'id': i, **values} for i in ids]
    _, rows, _ = S.rest('questions_bank', method='PATCH', body=values,
                        params={'id': 'in.(%s)' % ','.join(map(str, sorted(ids))),
                                'question_type': 'eq.case_study',
                                'source_type': 'eq.REAL_EXAM',
                                'select': 'id,' + ','.join(NEWCOLS)},
                        prefer='return=representation')
    return rows

def run(batch, dry=False):
    plan = load_plan()
    if batch == 'B4_canonical':
        rows = [p for p in plan if 'case_row_canonical' in p]
        cells = defaultdict(list)
        for p in rows:
            cells[bool(p['case_row_canonical'])].append(p['row_id'])
        units = [(ids, {'case_row_canonical': v}) for v, ids in sorted(cells.items())]
        expected = len(rows)
    else:
        rows = [p for p in plan if p['batch'] == batch]
        cells = defaultdict(list)
        for p in rows:
            key = (p['case_group_id'], p['case_subquestion_index'], p['case_row_granularity'])
            cells[key].append(p['row_id'])
        units = [(ids, {'case_group_id': k[0], 'case_subquestion_index': k[1],
                        'case_row_granularity': k[2]}) for k, ids in sorted(cells.items(), key=lambda kv: str(kv[0]))]
        expected = len(rows)

    print(f'batch={batch} dry={dry} rows_planned={expected} patch_units={len(units)}', flush=True)
    written, log, t0 = [], [], time.time()
    for n, (ids, values) in enumerate(units, 1):
        got = patch(ids, values, dry)
        if len(got) != len(ids):
            print(json.dumps({'FATAL': 'patch touched %d rows, expected %d' % (len(got), len(ids)),
                              'ids': ids, 'values': values, 'returned': got}, ensure_ascii=False))
            sys.exit(2)
        for g in got:
            for k, v in values.items():
                if g.get(k) != v:
                    print(json.dumps({'FATAL': 'readback mismatch', 'id': g['id'], 'col': k,
                                      'want': v, 'got': g.get(k)}, ensure_ascii=False))
                    sys.exit(3)
        written.extend(g['id'] for g in got)
        log.append({'ids': sorted(ids), 'values': values, 'returned': len(got)})
        if n % 25 == 0 or n == len(units):
            print(f'  unit {n}/{len(units)} rows_written={len(written)} {time.time()-t0:.1f}s', flush=True)

    assert len(written) == expected, f'wrote {len(written)} != planned {expected}'
    assert len(set(written)) == len(written), 'a row was written twice inside one batch'
    res = {'batch': batch, 'dry': dry, 'rows_written': len(written), 'patch_units': len(units),
           'ids': sorted(written), 'elapsed_s': round(time.time() - t0, 1)}
    if not dry:
        with open(os.path.join(OUT, f'writelog_{batch}.json'), 'w') as f:
            json.dump({**res, 'units': log}, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != 'ids'}, ensure_ascii=False))

if __name__ == '__main__':
    run(sys.argv[1], dry='--dry' in sys.argv)
