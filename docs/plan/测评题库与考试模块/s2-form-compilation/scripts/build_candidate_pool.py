#!/usr/bin/env python3
"""S2 候选池生成器 — 诊断表单选材(只读源资产,唯一写盘对象是本目录 candidate_pool_v0.json)。

数据源(全部 repo 内确定性资产):
  - 11 年真题:          docs/原始数据/考点原料/题库快照/FINAL_CLEANED_EXAM_V{2015..2025}.json
  - 考点↔真题实证 sidecar: docs/原始数据/考点原料/_<PID>_exam_evidence.json
  - 章节题库:            docs/原始数据/2026_副本/题库/{864考证宝典ZL,章节千题斩SMR}/FINAL_CLEANED_*.json
                         (主 checkout 只读回退:worktree 内无该 gitignored 目录时读主 checkout)
  - pack 注册表:         docs/原始数据/考点原料/成品/_pack_taxonomy_registry.v0.json
  - 编译练习权威:        deeptutor/services/luban_lesson/compiled/<pid>.practice.authority.json
  - 签发变体池:          docs/原始数据/考点原料/成品/_<PID>_variant_bank.v0.json
  - canonical taxonomy:  deeptutor/services/taxonomy/compiled/construction_2026_taxonomy.compiled.json

选材约束(指挥官裁决 2026-08-05,叠加计划 §6/§11):
  - 排除包:C02/E01/K01(合同索赔全族)、S01/S02、C06/F04/Q03/S07(coarse_review 治理冲突)、D14;
  - A01 缺 _A01_exam_evidence 难度锚 → 仅标记 needs_anchor,默认不入计分题;
  - E05 sidecar 存在但 0 条实证(本次盘点新发现)→ 同 needs_anchor 处理;
  - 每道候选计分题必须给出复测配对可行性判定(签发变体池优先,practice eligible 次之,章节题库兜底)。
"""
import json, os, re, sys, unicodedata
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '../../../../..'))
MAIN_CHECKOUT = '/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor'

EXAM_GLOB_DIR = os.path.join(ROOT, 'docs/原始数据/考点原料/题库快照')
SIDE_DIR = os.path.join(ROOT, 'docs/原始数据/考点原料')
PACK_DIR = os.path.join(ROOT, 'docs/原始数据/考点原料/成品')
PRACTICE_DIR = os.path.join(ROOT, 'deeptutor/services/luban_lesson/compiled')
TAXONOMY = os.path.join(ROOT, 'deeptutor/services/taxonomy/compiled/construction_2026_taxonomy.compiled.json')

def chapter_bank_path(rel):
    p = os.path.join(ROOT, rel)
    if os.path.exists(p):
        return p
    return os.path.join(MAIN_CHECKOUT, rel)

FAMILY_ELIGIBLE = {
    '主体结构': ['C01', 'C04', 'C05', 'C07', 'Q01', 'Q02'],
    '安全': ['J01', 'R01', 'S05', 'S06'],
    '进度': ['N01', 'N02', 'N03'],          # E05 sidecar 0 实证 → 移出默认计分源
    '质量验收': ['A02', 'G01', 'G02', 'G03', 'G04'],
    '防水': ['F02', 'F03', 'F05', 'F16'],
    '装饰备': ['D11', 'D12', 'D13'],
}
NEEDS_ANCHOR = {'A01': '质量验收', 'E05': '进度'}
EXCLUDED = {
    'C02': 'EXCLUSION-01 合同索赔族', 'E01': 'EXCLUSION-01/02 合同索赔族+无lesson/practice',
    'K01': 'EXCLUSION-01 合同索赔族', 'S01': 'EXCLUSION-03 缺作答层+缺考试实证',
    'S02': 'EXCLUSION-03 缺作答层+缺考试实证', 'Q03': 'EXCLUSION-04 注册表禁production',
    'C06': '治理冲突 coarse_review published(指挥官保守排除,待教研裁决 alignment)',
    'F04': '治理冲突 coarse_review published(同上)', 'S07': '治理冲突 coarse_review published(同上)',
    'D14': '缺作答层(与C06/F04同列)',
}

def norm(s):
    if not s:
        return ''
    s = unicodedata.normalize('NFKC', str(s))
    return re.sub(r'\s+', '', s)

def load_exams():
    """year -> list of {anchor, type, node, qd, chunk_node}"""
    out = {}
    for fn in sorted(os.listdir(EXAM_GLOB_DIR)):
        m = re.match(r'FINAL_CLEANED_EXAM_V(\d{4})\.json$', fn)
        if not m:
            continue
        year = m.group(1)
        d = json.load(open(os.path.join(EXAM_GLOB_DIR, fn)))
        items = []
        for ch in d['chunks']:
            cnode = (ch.get('taxonomy') or {}).get('node_code')
            anchor = (ch.get('source_meta') or {}).get('original_anchor')
            for e in ch.get('exercises', []):
                items.append({
                    'anchor': anchor,
                    'type': e['type'],
                    'node': e.get('predicted_node') or cnode,
                    'qd': e['question_data'],
                    'option_reasoning': e.get('option_reasoning'),
                    'stem_norm': norm(e['question_data'].get('stem'))[:60],
                })
        out[year] = items
    return out

def load_side(pid):
    p = os.path.join(SIDE_DIR, f'_{pid}_exam_evidence.json')
    if not os.path.exists(p):
        return None
    return json.load(open(p)).get('evidence', [])

def load_practice(pid):
    p = os.path.join(PRACTICE_DIR, f'{pid.lower()}.practice.authority.json')
    if not os.path.exists(p):
        return None
    d = json.load(open(p))
    items = [q for q in d.get('items', []) if q.get('eligible') and not q.get('revoked')]
    groups = Counter(q.get('rule_group') for q in items)
    return {'eligible_count': len(items), 'rule_groups': dict(groups),
            'sha256': None, 'items': items}

def load_variant_bank(pid):
    p = os.path.join(PACK_DIR, f'_{pid}_variant_bank.v0.json')
    if not os.path.exists(p):
        return None
    d = json.load(open(p))
    groups = Counter(v.get('rule_group') for v in d.get('variants', []))
    return {'status': d.get('status'), 'variant_count': len(d.get('variants', [])),
            'rule_groups': dict(groups)}

def load_chapter_banks():
    """node -> [ {bank, chunk_id, idx, type, difficulty, stem60, has_analysis} ]"""
    banks = {
        'ZL500': 'docs/原始数据/2026_副本/题库/864考证宝典ZL/FINAL_CLEANED_ZL500.json',
        'QIANTIZAN': 'docs/原始数据/2026_副本/题库/章节千题斩SMR/FINAL_CLEANED_QIANTIZAN.json',
    }
    by_node = defaultdict(list)
    for bank, rel in banks.items():
        p = chapter_bank_path(rel)
        if not os.path.exists(p):
            print(f'WARN: chapter bank missing: {rel}', file=sys.stderr)
            continue
        d = json.load(open(p))
        for ch in d['chunks']:
            cid = ch.get('chunk_id')
            for i, e in enumerate(ch.get('exercises', [])):
                node = e.get('predicted_node')
                if not node:
                    continue
                qd = e['question_data']
                by_node[node].append({
                    'bank': bank, 'chunk_id': cid, 'idx': i, 'type': e['type'],
                    'difficulty': qd.get('difficulty'),
                    'stem60': qd.get('stem', '')[:60],
                    'answer': qd.get('correct_answer'),
                    'has_analysis': bool(qd.get('analysis')),
                })
    return by_node

def main():
    taxonomy = json.load(open(TAXONOMY))['nodes_by_code']
    exams = load_exams()
    chapter_by_node = load_chapter_banks()

    # 真题条目全量索引(按 stem 前缀归并),用于把 sidecar 实证 join 回原题拿 difficulty/option_reasoning
    stem_index = defaultdict(list)
    for year, items in exams.items():
        for it in items:
            stem_index[(year, it['stem_norm'])].append(it)

    def join_raw(year, stem):
        key = (str(year), norm(stem)[:60])
        hits = stem_index.get(key, [])
        return hits[0] if hits else None

    candidates = []
    for fam, packs in FAMILY_ELIGIBLE.items():
        for pid in packs:
            side = load_side(pid)
            if side is None:
                continue
            practice = load_practice(pid)
            vbank = load_variant_bank(pid)
            for e in side:
                raw = join_raw(e.get('year'), e.get('stem'))
                qd = raw['qd'] if raw else {}
                node = (raw or {}).get('node')
                node_in_tax = bool(node and node in taxonomy)
                # chapter-bank pairing pool: same node exact + same node section (7-char prefix)
                same_node = chapter_by_node.get(node, []) if node else []
                sec = node[:7] if node else None
                same_sec = []
                if sec:
                    for n2, lst in chapter_by_node.items():
                        if n2.startswith(sec):
                            same_sec.extend(lst)
                cand = {
                    'candidate_id': f"{pid}-{e.get('year')}-{norm(e.get('题号'))}",
                    'family': fam,
                    'pack_id': pid,
                    'source': {
                        'kind': 'real_exam',
                        'year': e.get('year'),
                        'exam_anchor': e.get('题号'),
                        'file': f"docs/原始数据/考点原料/题库快照/FINAL_CLEANED_EXAM_V{e.get('year')}.json",
                        'sidecar': f"docs/原始数据/考点原料/_{pid}_exam_evidence.json",
                    },
                    'type': e.get('type'),
                    'taxonomy_node': node,
                    'taxonomy_node_resolves': node_in_tax,
                    'taxonomy_node_name': (taxonomy.get(node) or {}).get('name') if node else None,
                    'difficulty': qd.get('difficulty'),
                    'score': e.get('score', qd.get('score')),
                    'stem_120': (e.get('stem') or '')[:120],
                    'answer_present': bool(e.get('correct_answer')),
                    'analysis_present': bool(e.get('analysis')),
                    'has_option_reasoning': bool((raw or {}).get('option_reasoning')),
                    'joined_raw_exam': bool(raw),
                    'pairing': {
                        'variant_bank': ({'status': vbank['status'], 'variant_count': vbank['variant_count'],
                                          'rule_groups': vbank['rule_groups']} if vbank else None),
                        'practice_eligible_count': practice['eligible_count'] if practice else 0,
                        'practice_rule_groups': practice['rule_groups'] if practice else {},
                        'chapter_bank_same_node': len(same_node),
                        'chapter_bank_same_section': len(same_sec),
                        'chapter_bank_same_node_by_difficulty': dict(Counter(
                            x['difficulty'] for x in same_node)),
                    },
                }
                candidates.append(cand)

    out = {
        'schema': 'luban_s2_candidate_pool.v0',
        'generated_from': 'scripts/build_candidate_pool.py (deterministic, read-only)',
        'family_eligible': FAMILY_ELIGIBLE,
        'excluded_packs': EXCLUDED,
        'needs_anchor_packs': NEEDS_ANCHOR,
        'total_candidates_scanned': len(candidates),
        'candidates': candidates,
    }
    dst = os.path.join(HERE, '..', 'candidate_pool_v0.json')
    with open(dst, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=False)
    # summary
    c = Counter((x['family'], x['type']) for x in candidates)
    joined = sum(1 for x in candidates if x['joined_raw_exam'])
    print(f'total sidecar evidence rows scanned: {len(candidates)}; joined to raw exam: {joined}')
    for k in sorted(c):
        print(k, c[k])

if __name__ == '__main__':
    main()
