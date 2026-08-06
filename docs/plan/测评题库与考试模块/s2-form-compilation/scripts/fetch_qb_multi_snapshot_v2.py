#!/usr/bin/env python3
"""表单 v2 过渡多选题快照:从 Supabase questions_bank 只读拉取入选的 10 道
第三方练习册多选题 + 2 道题库配对单选题,落盘为可审计快照 JSON。

只读脚本(仅 REST GET);唯一写盘对象是 qb_multi_snapshot_v2.json。
入选题号由主表单 v2 选编定稿(2026-08-06-主表单v2.md §4)固定,可重跑、确定性。

用法::

    python3 fetch_qb_multi_snapshot_v2.py
"""
import json
import os
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_CANDIDATES = [
    os.path.abspath(os.path.join(HERE, '../../../../..', '.env')),
    '/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/.env',
]

# 主表单 v2 入选的 10 道过渡多选(五族 × 2)
SELECTED_MULTI = [14783, 14767, 14326, 14511, 14429, 14428, 14167, 14903, 14216, 18224]
# 复测配对表动用的题库行(③章节题库配对供给 + backup)
PAIR_ROWS = [14416, 14418]

COLS = (
    'id,source_type,question_type,node_code,question_stem,options,correct_answer,'
    'analysis,option_reasoning,source,exam_year,content_hash,based_on_version,tags'
)


def _load_env():
    for path in ENV_CANDIDATES:
        if os.path.exists(path):
            values = {}
            for raw in open(path, encoding='utf-8'):
                line = raw.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                values[k.strip()] = v.strip().strip("'").strip('"')
            return values
    raise SystemExit('.env 未找到')


def main():
    env = _load_env()
    url = env['SUPABASE_URL'].rstrip('/')
    key = env.get('SUPABASE_SERVICE_ROLE_KEY') or env.get('SUPABASE_KEY')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    ids = sorted(SELECTED_MULTI + PAIR_ROWS)
    q = urllib.parse.urlencode({
        'select': COLS,
        'id': 'in.({})'.format(','.join(map(str, ids))),
        'order': 'id.asc',
    })
    req = urllib.request.Request(
        f'{url}/rest/v1/questions_bank?{q}',
        headers={'apikey': key, 'Authorization': f'Bearer {key}'},
    )
    with opener.open(req, timeout=60) as resp:
        rows = json.loads(resp.read().decode('utf-8') or '[]')
    assert len(rows) == len(ids), f'期望 {len(ids)} 行,实得 {len(rows)}'
    snapshot = {
        'schema': 'luban_form_v2_qb_multi_snapshot.v0',
        'note': ('表单 v2 过渡题快照:10 道第三方练习册多选(非真题原题、非变式,'
                 '标注过渡,v2.1 由变体拼装器+双签替换)+ 2 道题库配对单选。'
                 '来源 Supabase public.questions_bank 只读拉取。'),
        'selected_multi_ids': SELECTED_MULTI,
        'pair_row_ids': PAIR_ROWS,
        'rows': rows,
    }
    dst = os.path.join(HERE, '..', 'qb_multi_snapshot_v2.json')
    json.dump(snapshot, open(dst, 'w'), ensure_ascii=False, indent=1)
    print('OK rows=', len(rows), '->', os.path.normpath(dst))


if __name__ == '__main__':
    main()
