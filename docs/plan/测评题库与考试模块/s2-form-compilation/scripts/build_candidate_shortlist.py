#!/usr/bin/env python3
"""S2 候选池收窄:从 candidate_pool_v0.json(1,527 行 sidecar×真题 join)收窄出主题吻合、
六闸可判、配对可行的 60–80 候选,写 candidate_shortlist_v1.json + markdown 表。

主题吻合判据:题干/解析命中 pack 主题关键词(显式声明,非语义猜测)。
命中≠入选:最终 12 计分题为逐题人核;其余候选标 `machine_screened`,供备份表单/第二三套
选材时逐题人核,宁缺毋滥。
"""
import json, os, re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
POOL = os.path.join(HERE, '..', 'candidate_pool_v0.json')

PACK_KEYWORDS = {
    'C01': ['施工缝', '后浇带'],
    'C04': ['拆模', '模板拆除', '拆除底模', '底模', '快拆'],
    'C05': ['钢筋连接', '机械连接', '焊接接头', '绑扎搭接', '套筒'],
    'C07': ['钢结构', '高强螺栓', '焊缝'],
    'Q01': ['养护', '混凝土裂缝', '裂缝防治'],
    'Q02': ['大体积', '温控', '水化热', '入模温度'],
    'J01': ['危大', '专项方案', '专家论证', '危险性较大'],
    'R01': ['动火', '灭火', '消防', '防火'],
    'S05': ['临时用电', '配电', '漏电', '照明电压', '开关箱', '安全电压'],
    'S06': ['高处作业', '临边', '洞口', '安全网', '防护栏', '安全带'],
    'N01': ['网络计划', '关键线路', '总时差', '双代号', '自由时差'],
    'N02': ['工期优化', '赶工', '压缩'],
    'N03': ['流水', '节拍', '步距'],
    'A02': ['复验', '见证', '取样', '进场检验', '隐蔽'],
    'G01': ['基坑', '降水', '支护', '土钉'],
    'G02': ['回填', '压实'],
    'G03': ['桩', '灌注桩', '沉桩'],
    'G04': ['验槽', '地基处理', '换填'],
    'F02': ['卷材', '搭接', '铺贴'],
    'F03': ['防水等级', '设防', '抗渗', '构造层次', '防水混凝土', '倒置式'],
    'F05': ['渗漏', '堵漏', '防水堵漏'],
    'F16': ['起鼓', '割补', '鼓泡'],
    'D11': ['抹灰'],
    'D12': ['饰面砖', '空鼓', '粘结强度'],
    'D13': ['幕墙'],
}
PER_FAMILY_CAP = {'主体结构': 16, '安全': 12, '进度': 12, '质量验收': 14, '防水': 14, '装饰备': 8}

def main():
    pool = json.load(open(POOL))
    cands = pool['candidates']
    picked = defaultdict(list)
    seen = set()
    for c in cands:
        pid = c['pack_id']
        kws = PACK_KEYWORDS.get(pid, [])
        text = c['stem_120']
        if not any(k in text for k in kws):
            continue
        if not (c['answer_present'] and c['joined_raw_exam']):
            continue
        key = (c['source']['year'], re.sub(r'\s+', '', c['stem_120'])[:40])
        if key in seen:
            continue
        seen.add(key)
        fam = c['family']
        if len(picked[fam]) >= PER_FAMILY_CAP.get(fam, 12):
            continue
        vb = c['pairing']['variant_bank']
        prac = c['pairing']['practice_eligible_count']
        chap = c['pairing']['chapter_bank_same_section']
        pairing_verdict = ('vbank_first' if vb else
                          'practice_pool' if prac >= 7 else
                          'chapter_bank' if chap > 0 else 'FAIL_swap_item')
        gates = {
            'G1_syllabus': 'PASS(pack注册表锚定)' if not c['taxonomy_node_resolves']
                           else f"PASS({c['taxonomy_node']})",
            'G2_exam_source': 'PASS(11年真题)',
            'G3_ability': {'single_choice': '知识边界/条件判断', 'multiple_choice': '多选风险/知识边界',
                           'case_study': '案例识别/采分点(需纯点选转写)'}[c['type']],
            'G4_difficulty_anchor': (c['difficulty'] or 'MISSING') + '/真题实证sidecar',
            'G5_scoring': 'PASS(答案+解析非空)' if c['analysis_present'] else 'CONDITIONAL(解析空)',
            'G6_coverage': '表单级一题一维绑定(编制时定)',
        }
        picked[fam].append({
            'candidate_id': c['candidate_id'], 'family': fam, 'pack_id': pid,
            'type': c['type'], 'year': c['source']['year'],
            'exam_anchor': c['source']['exam_anchor'],
            'taxonomy_node': c['taxonomy_node'],
            'difficulty': c['difficulty'], 'score': c['score'],
            'stem_60': c['stem_120'][:60].replace('\n', ' '),
            'gates': gates,
            'pairing_verdict': pairing_verdict,
            'pairing_detail': {'vbank': vb['variant_count'] if vb else 0,
                               'practice_eligible': prac, 'chapter_same_section': chap},
            'screen_level': 'machine_screened',
            'source_refs': [c['source']['file'], c['source']['sidecar']],
        })
    total = sum(len(v) for v in picked.values())
    out = {
        'schema': 'luban_s2_candidate_shortlist.v1',
        'method': 'pack关键词主题吻合 + 答案/join质量过滤 + 族内去重限额;计分题终选逐题人核另列',
        'pack_keywords': PACK_KEYWORDS,
        'total': total,
        'by_family': {k: len(v) for k, v in picked.items()},
        'candidates': [x for v in picked.values() for x in v],
    }
    dst = os.path.join(HERE, '..', 'candidate_shortlist_v1.json')
    json.dump(out, open(dst, 'w'), ensure_ascii=False, indent=1)
    print('total', total, dict(out['by_family']))
    for fam, lst in picked.items():
        print('==', fam)
        for x in lst:
            print(f"  {x['candidate_id']} {x['type']} diff={x['difficulty']} pair={x['pairing_verdict']} | {x['stem_60'][:50]}")

if __name__ == '__main__':
    main()
