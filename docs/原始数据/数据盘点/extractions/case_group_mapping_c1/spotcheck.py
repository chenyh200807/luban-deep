"""Human-readable cross-question contamination spot check: 1 group per exam year, read live from DB."""
import json, os, random, re, difflib
from collections import defaultdict
import sbclient as S
OUT = os.path.dirname(os.path.abspath(__file__))
rows = S.select_all('questions_bank',
    'id,exam_year,original_id,case_group_id,case_subquestion_index,case_row_granularity,case_row_canonical,stem,correct_answer',
    filt={'case_group_id': 'not.is.null'})
byg = defaultdict(list)
for r in rows: byg[r['case_group_id']].append(r)
byyear = defaultdict(list)
for g in byg: byyear[int(g.split('-')[0])].append(g)

def bg(stem):
    s = re.split(r'【\s*问题\s*】|###\s*问题|\n问题[:：]', stem or '', 1)[0]
    return re.sub(r'\s+', '', s)
def hard(s): return re.sub(r'[^一-鿿0-9]', '', s or '')

random.seed(20260801)
lines, machine = [], []
for y in sorted(byyear):
    g = sorted(byyear[y])[random.randrange(len(byyear[y]))]
    rs = sorted(byg[g], key=lambda r: (r['case_subquestion_index'] or 99, r['id']))
    base = hard(bg(rs[0]['stem']))
    sims = [round(difflib.SequenceMatcher(None, base, hard(bg(r['stem']))).ratio(), 3) for r in rs]
    lines.append(f"\n===== {g}  ({len(rs)} 行)  背景相似度 min={min(sims)} =====")
    lines.append(f"  背景(前 110 字): {bg(rs[0]['stem'])[:110]}")
    for r, s in zip(rs, sims):
        ca = r['correct_answer']
        ca = '\n'.join(ca) if isinstance(ca, list) else str(ca)
        lines.append(f"  id={r['id']:<6} idx={str(r['case_subquestion_index']):<4} gran={r['case_row_granularity']:<14} "
                     f"canon={str(r['case_row_canonical']):<5} bg_sim={s:<5} oid={r['original_id']}")
        lines.append(f"      问面: {re.sub(chr(92)+'s+',' ', (r['stem'] or ''))[-160:]}")
        lines.append(f"      答案: {re.sub(chr(92)+'s+',' ', ca)[:150]}")
    machine.append({'exam_year': y, 'case_group_id': g, 'rows': len(rs),
                    'min_background_similarity': min(sims),
                    'row_ids': [r['id'] for r in rs]})
txt = '\n'.join(lines)
open(os.path.join(OUT, 'spotcheck_one_group_per_year.txt'), 'w').write(txt)
json.dump(machine, open(os.path.join(OUT, 'spotcheck_one_group_per_year.json'), 'w'), ensure_ascii=False, indent=1)
print(json.dumps(machine, ensure_ascii=False, indent=1))
print('\nworst min background similarity across the 11 sampled groups:',
      min(m['min_background_similarity'] for m in machine))
