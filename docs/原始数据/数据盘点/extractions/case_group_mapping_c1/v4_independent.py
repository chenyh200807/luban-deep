"""V4-strong: recompute the background fingerprint PER ROW straight from live stem text and ask
how many distinct backgrounds each case_group_id actually contains. C1's stored
case_group_fingerprint is a per-group value, so it can never falsify a bad merge — this can."""
import difflib, hashlib, json, os, re
from collections import defaultdict
import sbclient as S
OUT = os.path.dirname(os.path.abspath(__file__))
rows = S.select_all('questions_bank',
    'id,exam_year,original_id,case_group_id,case_subquestion_index,case_row_granularity,case_row_canonical,stem',
    filt={'case_group_id': 'not.is.null'})
def bgtext(stem):
    return re.split(r'【\s*问题\s*】|###\s*问题|\n问题[:：]', stem or '', 1)[0]
def hard(s): return re.sub(r'[^一-鿿0-9]', '', s or '')
byg = defaultdict(list)
for r in rows:
    r['_bg'] = hard(bgtext(r['stem']))
    r['_fp'] = hashlib.md5(r['_bg'].encode()).hexdigest()[:16]
    byg[r['case_group_id']].append(r)

report = []
for g, rs in sorted(byg.items()):
    fps = defaultdict(list)
    for r in rs: fps[r['_fp']].append(r['id'])
    if len(fps) == 1:
        continue
    longest = max(rs, key=lambda r: len(r['_bg']))['_bg']
    sims = {f: round(difflib.SequenceMatcher(None, longest, next(x for x in rs if x['_fp'] == f)['_bg']).ratio(), 3)
            for f in fps}
    subset = {f: (next(x for x in rs if x['_fp'] == f)['_bg'] in longest) for f in fps}
    report.append({'case_group_id': g, 'rows': len(rs), 'distinct_backgrounds': len(fps),
                   'min_similarity_to_longest': min(sims.values()),
                   'all_are_substrings_of_longest': all(subset.values()),
                   'variants': [{'fp': f, 'ids': ids, 'sim_to_longest': sims[f],
                                 'is_substring_of_longest': subset[f],
                                 'bg_len': len(next(x for x in rs if x['_fp'] == f)['_bg'])}
                                for f, ids in fps.items()]})
report.sort(key=lambda r: r['min_similarity_to_longest'])
json.dump(report, open(os.path.join(OUT, 'v4_independent_background_variants.json'), 'w'),
          ensure_ascii=False, indent=1)
print('groups total          :', len(byg))
print('groups w/ >1 raw bg   :', len(report))
print('  of which every variant is a SUBSTRING of the longest (OCR truncation, benign):',
      sum(1 for r in report if r['all_are_substrings_of_longest']))
print('  NOT substring (genuinely different background text) :',
      sum(1 for r in report if not r['all_are_substrings_of_longest']))
for r in report[:8]:
    print('  ', r['case_group_id'], 'rows=%d' % r['rows'], 'variants=%d' % r['distinct_backgrounds'],
          'min_sim=%.3f' % r['min_similarity_to_longest'], 'all_substr=%s' % r['all_are_substrings_of_longest'])
