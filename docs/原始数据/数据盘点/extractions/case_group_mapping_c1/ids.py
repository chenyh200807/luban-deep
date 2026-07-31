import json, os
MAP = "/Users/yehongchen/worktrees/deeptutor-planc-c2/docs/原始数据/数据盘点/extractions/case_group_mapping_c1"
def load(n): return [json.loads(l) for l in open(os.path.join(MAP, n))]
A = load('mapping.jsonl'); B = load('mapping_whole_case_rows.jsonl'); C = load('mapping_group_only.jsonl')
for r in A + B + C:
    r['row_id'] = int(r['row_id'])
    r['idx'] = int(r['idx']) if str(r['idx']).isdigit() else None
def tb(x): return str(x) == 'True'
AFFECTED = sorted({r['row_id'] for r in A + B + C})
