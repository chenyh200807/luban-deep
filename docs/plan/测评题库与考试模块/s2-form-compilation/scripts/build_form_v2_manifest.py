#!/usr/bin/env python3
"""主表单 v2 manifest 生成:声明式表单结构 + 从源资产回填 content_sha256/锚/审签状态。

复用 E 线 v1(build_form_v1_manifest.py)模式。只读源资产;
唯一写盘对象 form_v2_manifest.json。可重跑、确定性。

供给面:
- 20 单选 = 编译轻练 practice authority(eligible ∧ signed,零真题原题);
- 10 多选 = qb_multi_snapshot_v2.json(第三方练习册过渡题,v2.1 换真变式);
- 6 案例题 = E 线 v1 三段案例的变式化改写(原题锚+基题 variant_id 逐一登记);
- 3 备考上下文沿用 v1。
"""
import hashlib
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '../../../../..'))
PRACTICE_DIR = os.path.join(ROOT, 'deeptutor/services/luban_lesson/compiled')
SNAPSHOT = os.path.join(HERE, '..', 'qb_multi_snapshot_v2.json')


def sha(s):
    return hashlib.sha256(unicodedata.normalize('NFKC', re.sub(r'\s+', '', s)).encode()).hexdigest()


_PRACTICE_CACHE = {}


def practice_item(pid, qtag):
    if pid not in _PRACTICE_CACHE:
        _PRACTICE_CACHE[pid] = json.load(
            open(os.path.join(PRACTICE_DIR, f'{pid.lower()}.practice.authority.json')))
    for q in _PRACTICE_CACHE[pid]['items']:
        if re.search(rf'-{qtag}-', q.get('variant_id', '')):
            return q
    raise KeyError(f'{pid} {qtag}')


TASKS = []


def add(task_id, kind, family, pack, dimension, answer_type, confidence=False, **kw):
    TASKS.append(dict(task_id=task_id, kind=kind, family=family, pack_id=pack,
                      dimension=dimension, answer_type=answer_type,
                      confidence_input=confidence, **kw))


# ---- 3 备考上下文(沿用 v1,profile_probe 形,不计分) ----
for pid_, (probe, ask) in {
    'P1': ('prep_attempt_history', '第几次备考实务?上次实务成绩落在哪个分数带?(不计分,用于备考画像)'),
    'P2': ('prep_passed_subjects', '已通过科目及通过年份(管理/经济/法规)?(不计分,喂给滚动作废提醒)'),
    'P3': ('prep_weekly_hours', '每周有效学习时长?(不计分,只影响可行性/节奏,不影响分数带)'),
}.items():
    add(pid_, 'profile_probe', None, None, 'prep_feasibility(独立字段,禁入分数带)', 'single_choice',
        probe_id=probe, prompt=ask, scored=False)

# ---- S01–S20 编译轻练单选(变式池,全签发;五族配额 5/4/3/4/4) ----
# (task_id, pack, qtag, family, dimension, confidence, retest_pair, pair_note)
SINGLES = [
    ('S01', 'C01', 'q6',  '主体结构', 'construction_logic', False, ('C01', 'q18'), '同fact施工缝处理工序;backup q9'),
    ('S02', 'J01', 'q13', '安全',   'core_knowledge',     False, ('J01', 'q16'), '同fact同锚exam:2019:第2题,纠错→诊断换面'),
    ('S03', 'E05', 'q7',  '进度',   'construction_logic', False, ('E05', 'q8'),  '同fact同指标SPI,问法换面(理想平行)'),
    ('S04', 'A02', 'q7',  '质量验收', 'core_knowledge',     False, ('A02', 'q8'),  '同fact复验触发,屋面→墙体换面(理想平行)'),
    ('S05', 'F02', 'q7',  '防水',   'construction_logic', False, ('F02', 'q2'),  '同fact同锚exam:2016:第27题,场景换面'),
    ('S06', 'C04', 'q4',  '主体结构', 'construction_logic', True,  ('C04', 'q5'),  '同fact强度阈值,边界→全表换面'),
    ('S07', 'R01', 'q11', '安全',   'core_knowledge',     False, ('R01', 'q12'), '同fact动火审批,相邻子点(审批主体↔动火证规则);backup q15'),
    ('S08', 'N01', 'q1',  '进度',   'core_knowledge',     False, ('N01', 'q5'),  '同fact零时差判据,判据→应用换面;backup q8'),
    ('S09', 'G01', 'q9',  '质量验收', 'core_knowledge',     False, ('G01', 'q10'), '同fact深基坑开挖,相邻子点(分层厚度↔预留土层)'),
    ('S10', 'F03', 'q4',  '防水',   'core_knowledge',     False, ('F03', 'q16'), '同fact倒置式层序,整链→相邻层换面'),
    ('S11', 'C05', 'q6',  '主体结构', 'construction_logic', False, ('C05', 'q7'),  '同fact接头位置,梁→柱换面'),
    ('S12', 'S05', 'q3',  '安全',   'core_knowledge',     False, ('S05', 'q18'), '包含配对:q18诊断②即一机一闸同采分点'),
    ('S13', 'N03', 'q13', '进度',   'construction_logic', False, ('N03', 'q12'), '同fact判型,节拍组换面(理想平行)'),
    ('S14', 'G02', 'q6',  '质量验收', 'construction_logic', False, ('G02', 'q7'),  '同fact压实参数,振动碾→平碾换面(理想平行);backup q16'),
    ('S15', 'F05', 'q5',  '防水',   'construction_logic', False, ('F05', 'q16'), '同fact穿墙管治理,流程→诊断换面;backup q6'),
    ('S16', 'C07', 'q10', '主体结构', 'construction_logic', False, ('C07', 'q15'), '包含配对:q15诊断①即兼作安装螺栓同采分点;backup q9'),
    ('S17', 'S06', 'q1',  '安全',   'construction_logic', False, ('S06', 'q5'),  '同fact临边防护,相邻子点(触发判定↔栏杆封闭);backup q14'),
    ('S18', 'G04', 'q7',  '质量验收', 'construction_logic', False, ('G04', 'q17'), '包含配对:q17诊断③即换填接缝同采分点;backup q6'),
    ('S19', 'F16', 'q2',  '防水',   'construction_logic', False, ('F16', 'q8'),  '同fact同锚exam:2017:案例二,正序→乱序换面(理想平行)'),
    ('S20', 'Q01', 'q1',  '主体结构', 'core_knowledge',     False, ('Q01', 'q6'),  '包含配对:q6抗渗墙7d纠错即养护矩阵子点;backup q10'),
]
for tid, pid, qtag, fam, dim, conf, pair, pair_note in SINGLES:
    q = practice_item(pid, qtag)
    rv = q.get('review') or {}
    assert q.get('eligible') and rv.get('status') == 'signed' and not q.get('revoked'), f'{pid} {qtag} 非签发'
    assert q.get('answer_type') == 'single_choice', f'{pid} {qtag} 非单选'
    pq = practice_item(*pair)
    add(tid, 'compiled_practice_item', fam, pid, dim, 'single_choice', confidence=conf,
        scored=True,
        source={'kind': 'compiled_practice_authority',
                'file': f'deeptutor/services/luban_lesson/compiled/{pid.lower()}.practice.authority.json',
                'variant_id': q['variant_id'], 'source_anchor': q.get('source_anchor'),
                'review_status': rv.get('status'),
                'sidecar': f'docs/原始数据/考点原料/_{pid}_exam_evidence.json'},
        stem=q['stem'], rule_group=q.get('rule_group'), fact_id=q.get('fact_id'),
        answer_key='(见 authority 文件 options.is_correct;本 manifest 不复制全部选项文)',
        distractor_error_codes=[o.get('source_error_code') for o in q['options'] if not o.get('is_correct')],
        content_sha256=q.get('content_sha256'),
        retest_pair={'variant_id': pq['variant_id'], 'fact_id': pq.get('fact_id'),
                     'source_anchor': pq.get('source_anchor'), 'note': pair_note})

# ---- M01–M10 过渡多选(第三方练习册,非真题原题、非变式;v2.1 换真变式) ----
snap = json.load(open(SNAPSHOT))
SNAP_ROWS = {r['id']: r for r in snap['rows']}


def norm_options(row):
    out = []
    for i, o in enumerate(row['options'] or []):
        if isinstance(o, dict):
            out.append({'key': o.get('key'), 'value': o.get('value')})
        else:
            m = re.match(r'^\s*([A-F])[\.、\s]\s*(.*)$', str(o))
            out.append({'key': m.group(1) if m else chr(65 + i),
                        'value': m.group(2) if m else str(o)})
    return out


# (task_id, qb_id, family, family_basis, retest_pair, pair_note, six_gate_note)
MULTIS = [
    ('M01', 14783, '主体结构', 'leaf 1A413030_103 施工缝位置→C01', ('C01', 'q1'),
     '同采分点(构件×施工缝位置枚举);backup q5/q17', '锚:C01 q1 同点真题 exam:2021:第8题'),
    ('M02', 14326, '安全', 'leaf 1A431011_015 安全电压→S05', ('S05', 'q9'),
     '同fact安全电压分档,多选场所枚举→单选分档对应换面;backup q8', '锚:S05 同点真题 exam:2016:第13题'),
    ('M03', 14429, '进度', 'leaf 1A435020_095 挣值法→E05', ('E05', 'q6'),
     'CONDITIONAL 相邻子点:CPI∈四评价指标;backup qb#14418(三值构成)', '锚:E05 挣值链 ca:1A435020_095_0156'),
    ('M04', 14167, '质量验收', 'leaf 1A413030_092-093 桩基检测→G03', ('G03', 'q12'),
     '同采分点(检测方法↔检测目的匹配);backup q13', '锚:G03 exam_evidence sidecar(2015–2024 七锚)'),
    ('M05', 14216, '防水', 'leaf 1A413030_122 屋面基本要求→F03', ('F03', 'q3'),
     '同采分点(屋面防水基本要求),数值面↔口径面换面', '锚:F03 sidecar 2019/2020 直考屋面防水'),
    ('M06', 14767, '主体结构', 'leaf 1A413030_095-096 大体积温控→Q02', ('Q02', 'q1'),
     '同采分点(防裂技术措施骨架);backup 无(登记)', '锚:Q02 大体积真题群(2019案例一/2021/2023)', ),
    ('M07', 14511, '安全', 'leaf 1A437000_146 灭火器配置→R01', ('R01', 'q3'),
     '同采分点(每100㎡ 2只10L 配置数值);backup q4', '锚:R01 sidecar exam:2018:第5题/2016:案例5'),
    ('M08', 14428, '进度', 'leaf 1A435020 价值工程(成本控制方法)', ('QB', '14416'),
     '③章节题库配对:同书同点单选(提高价值途径);难度锚依据=2018真题案例考价值工程(qb REAL_EXAM #9172)',
     '锚:2018 实务真题案例直考价值工程'),
    ('M09', 14903, '质量验收', 'leaf 1A413000_084 基坑开挖(质量通病)→G01', ('G01', 'q11'),
     'CONDITIONAL 相邻子点:降排水失效是塌方四成因之一', '锚:G01 降水/开挖 kc 锚+2019:第7题族'),
    ('M10', 18224, '防水', 'leaf 1A413030 地下卷材防水→F02', ('F02', 'q5'),
     '同采分点(地下卷材铺设与工法),锚 exam:2018:第14题', '锚:F02 q5 同点真题 exam:2018:第14题'),
]
for entry in MULTIS:
    tid, qbid, fam, basis, pair, pair_note, gate_note = entry[:7]
    r = SNAP_ROWS[qbid]
    assert r['question_type'] == 'multi_choice' and r['source_type'] in ('TEXTBOOK', 'textbook_exercise')
    pair_ref = ({'kind': 'questions_bank_row', 'qb_id': int(pair[1])} if pair[0] == 'QB'
                else {'kind': 'compiled_practice_item',
                      'variant_id': practice_item(*pair)['variant_id'],
                      'source_anchor': practice_item(*pair).get('source_anchor')})
    pair_ref['note'] = pair_note
    add(tid, 'bank_transitional_multi', fam, None, 'core_knowledge', 'multiple_choice',
        confidence=(tid == 'M06'),
        scored=True, transitional=True,
        transitional_note='过渡题:第三方练习册原题(非真题原题、非变式)。v2.1 由变体拼装器+双签的真变式多选替换。',
        family_basis=basis,
        source={'kind': 'questions_bank', 'qb_id': qbid, 'source_type': r['source_type'],
                'book': r.get('source'), 'node_code': r.get('node_code'),
                'db_content_hash': r.get('content_hash'),
                'snapshot': 'docs/plan/测评题库与考试模块/s2-form-compilation/qb_multi_snapshot_v2.json'},
        stem=r['question_stem'], options=norm_options(r),
        answer_key=str(r['correct_answer']).strip().upper(),
        analysis=r.get('analysis'),
        difficulty_anchor=gate_note,
        content_sha256=sha(r['question_stem'] + json.dumps(norm_options(r), ensure_ascii=False)),
        retest_pair=pair_ref)

# ---- 三段案例(E 线 v1 变式化改写:保留考法与采分点,换表面参数/情境/数值) ----
MAT_A = ('某新建高层办公楼工程,地下2层,地上16层,主体为现浇钢筋混凝土结构。项目部编制的'
         '《后浇带施工专项方案》载明:①采用微膨胀混凝土浇筑;②模板独立支设;③剔除模板用钢丝网;'
         '④因设计无要求,基础底板后浇带12d后封闭;⑤浇筑后保持至少14d湿润养护。监理工程师审查后要求整改。')
MAT_B = ('某办公楼工程,各单位在质量检测管理中做了以下工作:①建设单位委托具有相应资质的'
         '检测机构负责本工程质量检测;②试样送检时,试验员向检测机构填报检测委托单;③监理对混凝土'
         '试件制作与送样见证,试验员如实记录取样、现场检测情况并制作见证记录;④总包项目部按建设'
         '单位要求,按季度向检测机构支付当期检测费用。')
MAT_C = ('某新建教学楼项目由两栋结构类型与建筑规模完全相同的单体组成。项目部针对四个施工过程'
         '拟采用四个专业施工队组织流水施工,流水节拍依次为4、4、8、4个月。建设单位要求缩短工期,'
         '项目部决定增加相应的专业施工队,组织成倍节拍流水施工。')

MATERIALS = {
    'CASE_A': {'text': MAT_A, 'chars': len(MAT_A), 'family': '主体结构', 'pack_id': 'C01',
               'origin': {'kind': 'real_exam_case_variant', 'year': 2018, 'exam_anchor': '案例分析(三)',
                          'v1_material': 'CASE_A(form_v1_manifest.json)',
                          'sidecar': 'docs/原始数据/考点原料/_C01_exam_evidence.json'},
               'rewrite_note': ('变式化改写:住宅→办公楼、12层→16层、10d→12d(仍<28d,不妥性质不变);'
                                '三处不妥句(②独立支设/③剔钢丝网/④提前封闭)逐字保留原题措辞;'
                                '①⑤为官方答案技术措施(3)(5)原文并入方案作干扰,零自造事实')},
    'CASE_B': {'text': MAT_B, 'chars': len(MAT_B), 'family': '质量验收', 'pack_id': 'A02',
               'origin': {'kind': 'real_exam_case_variant', 'year': 2023, 'exam_anchor': '案例一',
                          'v1_material': 'CASE_B(form_v1_manifest.json)',
                          'sidecar': 'docs/原始数据/考点原料/_A02_exam_evidence.json'},
               'rewrite_note': ('变式化改写:住宅小区→办公楼、工作项①②③④重排序(原②③互换)、'
                                '每月→按季度(付费主体不妥性质不变);四项工作内容逐字保留;零自造事实')},
    'CASE_C': {'text': MAT_C, 'chars': len(MAT_C), 'family': '进度', 'pack_id': 'N03',
               'origin': {'kind': 'real_exam_case_variant', 'year': 2023, 'exam_anchor': '第2题',
                          'v1_material': 'CASE_C(form_v1_manifest.json)',
                          'sidecar': 'docs/原始数据/考点原料/_N03_exam_evidence.json'},
               'rewrite_note': ('变式化改写:住宅→教学楼、节拍3,3,6,3→4,4,8,4(等比换数,gcd 结构不变:'
                                'K=4、队数1+1+2+1=5、T=(2+5−1)×4=24个月);考法与四步采分链不变;'
                                'M=2(两栋)保留;全部数值机械推导,零自造事实')},
}
for m in MATERIALS.values():
    assert m['chars'] <= 150, f"案例材料超 150 字: {m['chars']}"

# CA1 案例A指错(五句方案指错;键 BCD)
add('CA1', 'case_error_correction_variant', '主体结构', 'C01', 'construction_logic', 'multiple_choice',
    scored=True, material='CASE_A',
    source={'kind': 'real_exam_case_variant', 'year': 2018, 'exam_anchor': '案例分析(三)问题3',
            'v1_task': 'T5', 'sidecar': 'docs/原始数据/考点原料/_C01_exam_evidence.json'},
    stem='指出《后浇带施工专项方案》①~⑤中的不妥之处。(多选;多答不得分)',
    options=[
        {'key': 'A', 'value': '①采用微膨胀混凝土浇筑', 'correct': False, 'cause': 'concept_boundary',
         'source': '官方答案技术措施(3)——正确做法并入方案作干扰'},
        {'key': 'B', 'value': '②模板独立支设', 'correct': True, 'cause': 'condition_misread',
         'source': '官方答案不妥之处①(原题措辞逐字保留)'},
        {'key': 'C', 'value': '③剔除模板用钢丝网', 'correct': True, 'cause': 'knowledge_gap',
         'source': '官方答案不妥之处②(应保留钢丝网)'},
        {'key': 'D', 'value': '④基础底板后浇带12d后封闭', 'correct': True, 'cause': 'knowledge_gap',
         'source': '官方答案不妥之处③(应≥28d;10d→12d 换数不改性质)'},
        {'key': 'E', 'value': '⑤浇筑后保持至少14d湿润养护', 'correct': False, 'cause': 'concept_boundary',
         'source': '官方答案技术措施(5)——正确做法并入方案作干扰'},
    ],
    answer_key='BCD', content_sha256=sha(MAT_A + 'CA1'),
    difficulty='真题2018案例锚(案例分析(三)问题3,score 5.5)',
    retest_pair={'variant_id': practice_item('C01', 'q12')['variant_id'],
                 'source_anchor': practice_item('C01', 'q12').get('source_anchor'),
                 'note': '封闭时间子点;backup vbank D-postpour(14变体)覆盖模板/钢丝网子点'})

# CA2 案例A采分点(C01 q13 变式化改写;键 B)
_q13 = practice_item('C01', 'q13')
add('CA2', 'case_scoring_point_variant', '主体结构', 'C01', 'case_scoring_point', 'single_choice',
    scored=True, material='CASE_A',
    source={'kind': 'compiled_practice_item_variant', 'base_variant_id': _q13['variant_id'],
            'base_content_sha256': _q13.get('content_sha256'),
            'base_source_anchor': _q13.get('source_anchor'),
            'rewrite': '保留六环采分链(整理钢筋→冲洗→微膨胀→提高一级→≥14d养护→接缝按施工缝处理)与四选项错误码结构,选项表面重写',
            'sidecar': 'docs/原始数据/考点原料/_C01_exam_evidence.json'},
    stem='针对该工程基础底板后浇带,写出后浇带混凝土施工的主要技术措施,选出最完整、能得分的作答。',
    options=[
        {'key': 'A', 'value': '把好材料关与工序关,浇筑前后精心组织、加强养护管理,确保后浇带部位一次验收合格。',
         'correct': False, 'cause': 'E04 口号化表达', 'source': 'q13 E04 选项换面(空话无采分点)'},
        {'key': 'B', 'value': '先整理外露钢筋、冲洗松动石子,采用微膨胀混凝土,强度比原结构提高一级,浇后≥14d湿润养护,接缝按施工缝处理。',
         'correct': True, 'cause': None, 'source': 'q13 正确项换面(官方六环采分链齐全)'},
        {'key': 'C', 'value': '采用与两侧底板同强度等级的混凝土连续浇筑、振捣密实,表面清理干净后覆盖并浇水养护。',
         'correct': False, 'cause': 'E07 概念混淆', 'source': 'q13 E07 选项换面(把后浇带当普通缝)'},
        {'key': 'D', 'value': '整理外露钢筋、选用微膨胀混凝土并保证≥14d湿润养护,其余环节按常规混凝土工艺执行。',
         'correct': False, 'cause': 'E02 采分点遗漏', 'source': 'q13 E02 选项换面(漏冲洗/提高一级/接缝处理)'},
    ],
    answer_key='B', content_sha256=sha(MAT_A + 'CA2'),
    difficulty='真题2018案例锚(同上)',
    retest_pair={'variant_id': practice_item('C01', 'q11')['variant_id'],
                 'source_anchor': practice_item('C01', 'q11').get('source_anchor'),
                 'note': '强度等级子点;backup q10(材料)/q15(采分诊断)'})

# CB1 案例B指错(键 CD)
add('CB1', 'case_error_correction_variant', '质量验收', 'A02', 'construction_logic', 'multiple_choice',
    scored=True, material='CASE_B',
    source={'kind': 'real_exam_case_variant', 'year': 2023, 'exam_anchor': '案例一问题1',
            'v1_task': 'T7', 'sidecar': 'docs/原始数据/考点原料/_A02_exam_evidence.json'},
    stem='指出工程施工质量检测管理工作中的不妥之处。(本问题2项不妥,多答不得分;多选)',
    options=[
        {'key': 'A', 'value': '工作①(建设单位委托有资质检测机构)', 'correct': False, 'cause': 'concept_boundary',
         'source': '案例原文,官方答案未列为不妥'},
        {'key': 'B', 'value': '工作②(试样送检时试验员向检测机构填报检测委托单)', 'correct': False,
         'cause': 'concept_boundary', 'source': '案例原文,官方答案未列为不妥(重排序后位置②)'},
        {'key': 'C', 'value': '工作③(试验员记录取样、现场检测情况并制作见证记录)', 'correct': True,
         'cause': 'knowledge_gap', 'source': '官方答案不妥①:应由见证人员记录并制作见证记录'},
        {'key': 'D', 'value': '工作④(总包项目部按季度向检测机构支付当期检测费用)', 'correct': True,
         'cause': 'knowledge_gap', 'source': '官方答案不妥②:检测费用应由建设单位单独列支并按约支付(每月→按季度换面,付费主体不妥不变)'},
    ],
    answer_key='CD', content_sha256=sha(MAT_B + 'CB1'),
    difficulty='真题2023案例锚(案例一问题1,score 7.0)',
    retest_pair={'variant_id': practice_item('A02', 'q11')['variant_id'],
                 'source_anchor': practice_item('A02', 'q11').get('source_anchor'),
                 'note': '见证主体同采分点'})

# CB2 案例B采分点(键 ACEF;选项重排换面)
add('CB2', 'case_scoring_point_variant', '质量验收', 'A02', 'case_scoring_point', 'multiple_choice',
    scored=True, material='CASE_B',
    source={'kind': 'real_exam_case_variant', 'year': 2023, 'exam_anchor': '案例一问题1',
            'v1_task': 'T8',
            'rewrite': '正确项即官方记录内容清单(不可换面);变式=情境换面+选项重排+干扰项措辞对齐新材料',
            'sidecar': 'docs/原始数据/考点原料/_A02_exam_evidence.json'},
    stem='混凝土试件制作与取样的见证记录内容,除取样情况外还应包括哪些?(多选)',
    options=[
        {'key': 'A', 'value': '制样情况', 'correct': True, 'cause': None, 'source': '官方答案:制样'},
        {'key': 'B', 'value': '检测委托单编号', 'correct': False, 'cause': 'condition_misread',
         'source': '案例材料②的元素,官方记录内容不含——干扰项取自材料本身'},
        {'key': 'C', 'value': '标识、封志情况', 'correct': True, 'cause': None, 'source': '官方答案:标识、封志'},
        {'key': 'D', 'value': '检测费用支付情况', 'correct': False, 'cause': 'condition_misread',
         'source': '案例材料④的元素,官方记录内容不含——干扰项取自材料本身'},
        {'key': 'E', 'value': '送检情况', 'correct': True, 'cause': None, 'source': '官方答案:送检'},
        {'key': 'F', 'value': '现场检测情况', 'correct': True, 'cause': None, 'source': '官方答案:现场检测'},
    ],
    answer_key='ACEF', content_sha256=sha(MAT_B + 'CB2'),
    difficulty='真题2023案例锚(同上)',
    retest_pair={'variant_id': practice_item('A02', 'q12')['variant_id'],
                 'source_anchor': practice_item('A02', 'q12').get('source_anchor'),
                 'note': '见证规则相邻子点;backup q21(采分句,exam:2017:第13题)'})

# CC1 案例C计算(键 A;干扰项结构复用 v1 T9 = N03 q2/q3 签发错误选项,数面换 4,4,8,4)
add('CC1', 'case_calc_judgment_variant', '进度', 'N03', 'construction_logic', 'single_choice',
    confidence=True, scored=True, material='CASE_C',
    source={'kind': 'real_exam_case_variant', 'year': 2023, 'exam_anchor': '第2题',
            'v1_task': 'T9',
            'distractor_source': 'N03 q2/q3 已签发错误选项结构(E07/E09 带 loss_reason),数值按 4,4,8,4 机械重算',
            'sidecar': 'docs/原始数据/考点原料/_N03_exam_evidence.json'},
    stem='组织成倍节拍流水施工,流水步距K与专业施工队总数分别为多少?选出算式与依据都正确的一项。(单选)',
    options=[
        {'key': 'A', 'value': 'K取各节拍最大公约数=4个月;各过程队数=节拍÷K,共1+1+2+1=5个',
         'correct': True, 'cause': None, 'source': '官方解法结构(K=gcd;队数=节拍÷K逐过程拆队),数面换算'},
        {'key': 'B', 'value': 'K取最大节拍=8个月;四个施工过程共4个专业队(每过程1队)',
         'correct': False, 'cause': 'knowledge_gap', 'source': 'N03-q2 E09(K取最大节拍)+q3 E07(不拆队)选项结构'},
        {'key': 'C', 'value': 'K=(4+4+8+4)÷4=5个月;队数按施工过程数取4个',
         'correct': False, 'cause': 'knowledge_gap', 'source': 'N03-q2 E09(平均值步距)选项结构'},
        {'key': 'D', 'value': 'K取最小节拍=4个月以保证紧凑衔接;队数=总节拍÷K=(4+4+8+4)÷4=5个',
         'correct': False, 'cause': 'concept_boundary',
         'source': 'N03-q2 E07+q3 E07 选项结构——数值碰巧对但依据错,考「依据」辨析'},
    ],
    answer_key='A', content_sha256=sha(MAT_C + 'CC1'),
    difficulty='真题2023案例锚(第2题,score 6.0)',
    retest_pair={'variant_id': practice_item('N03', 'q14')['variant_id'],
                 'source_anchor': practice_item('N03', 'q14').get('source_anchor'),
                 'note': '同fact成倍节拍拆队队数,数面 3,3,9,6,6(exam:2019:第2题)——理想平行'})

# CC2 案例C四步采分句(N03 q15 变式化改写;键 B)
_q15 = practice_item('N03', 'q15')
add('CC2', 'case_scoring_point_variant', '进度', 'N03', 'case_scoring_point', 'single_choice',
    scored=True, material='CASE_C',
    source={'kind': 'compiled_practice_item_variant', 'base_variant_id': _q15['variant_id'],
            'base_content_sha256': _q15.get('content_sha256'),
            'base_source_anchor': _q15.get('source_anchor'),
            'rewrite': '保留四步采分链(判型→K→队数→工期)与选项错误码结构(E02/E09/E07),数面 4,4,8,4 机械重算',
            'sidecar': 'docs/原始数据/考点原料/_N03_exam_evidence.json'},
    stem='按阅卷采分点写全答案(判型→K→队数→工期),选出四步采分句最完整的作答。(单选)',
    options=[
        {'key': 'A', 'value': '直接报结果:流水步距K=4个月、专业队5个、总工期24个月,三个数值一次给全。',
         'correct': False, 'cause': 'E02 采分点遗漏', 'source': 'q15 E02 选项换面(漏判型理由)'},
        {'key': 'B', 'value': '①节拍成倍数→等步距异节奏;②K=gcd(4,8)=4个月;③队数=节拍÷K=1+1+2+1=5,拆队后队数>工序数;④T=(M+N′−1)×K=(2+5−1)×4=24个月。',
         'correct': True, 'cause': None, 'source': 'q15 正确项换面(四步采分句齐全,数面机械重算)'},
        {'key': 'C', 'value': '判型等步距异节奏;K=4个月;队数4个(每工序1队);工期=4+4+8+4=20个月,四步依次写出。',
         'correct': False, 'cause': 'E09 计算错误', 'source': 'q15 E09 选项换面(未拆队+工期机械相加)'},
        {'key': 'D', 'value': '判型等节奏流水;K=t=4个月;队数=工序数4个;工期按等节奏公式T=(2+4−1)×4=20个月。',
         'correct': False, 'cause': 'E07 概念混淆', 'source': 'q15 E07 选项换面(判型地基错,连锁未拆队)'},
    ],
    answer_key='B', content_sha256=sha(MAT_C + 'CC2'),
    difficulty='真题2023案例锚(同上)',
    retest_pair={'variant_id': practice_item('N03', 'q3')['variant_id'],
                 'source_anchor': practice_item('N03', 'q3').get('source_anchor'),
                 'note': '同fact队数子点(exam:2023:第2题);backup q4(工期子点,v1 先例)'})

ORDER = (['P1', 'P2', 'P3']
         + [s[0] for s in SINGLES]
         + [m[0] for m in MULTIS]
         + ['CA1', 'CA2', 'CB1', 'CB2', 'CC1', 'CC2'])

manifest = {
    'schema': 'luban_s2_diagnostic_form.v2',
    'form_id': 'pass_readiness_form_main_v2',
    'blueprint': 'pass_readiness_architecture_v2',
    'date': '2026-08-06',
    'supersedes': 'pass_readiness_form_main_v1(form_v1_manifest.json)',
    'owner_decisions': ['题量对齐真题卷面:20单选+10多选+案例点选', '变式优先,真题只做锚(零真题原题)'],
    'interaction_contract': '纯点选(single/multi letter tap);答案线格式 dict[str,str];无自由文本/拖拽',
    'written_expression': 'not_measured(计划 §6.2 无条件降级;分数带走 §7.2 更宽阶梯)',
    'band_policy_note': '每维观察数翻倍,带宽阶梯可下调一档(V1 ≥20 → v2 待定 ≥15),band_policy_version 需 bump(代码侧)',
    'checkpoints': {
        'after_S10': '第10计分题粗带:coverage=low,超宽带宽,不出证据屏不点名弱点(§6.2-v2 两级检查点第一级)',
        'after_M10': '第30计分题客观带:客观题带宽档,仍不出案例采分点证据',
        'completion': '39交互全部完成:精带+证据屏',
    },
    'confidence_tasks': ['S06', 'M06', 'CC1'],
    'context_probes': ['P1', 'P2', 'P3'],
    'ordering': ORDER,
    'dimension_matrix': {
        'core_knowledge': [t['task_id'] for t in TASKS if t.get('scored') and t['dimension'] == 'core_knowledge'],
        'construction_logic': [t['task_id'] for t in TASKS if t.get('scored') and t['dimension'] == 'construction_logic'],
        'case_scoring_point': [t['task_id'] for t in TASKS if t.get('scored') and t['dimension'] == 'case_scoring_point'],
        'answer_expression': [],
        'prep_feasibility_context_only': ['P1', 'P2', 'P3'],
    },
    'family_matrix': {fam: [t['task_id'] for t in TASKS if t.get('family') == fam]
                      for fam in ('主体结构', '安全', '进度', '质量验收', '防水')},
    'transitional_tasks': [m[0] for m in MULTIS],
    'materials': MATERIALS,
    'tasks': TASKS,
}

# 结构自检
assert len([t for t in TASKS if t.get('scored')]) == 36, '计分题应为 36'
assert len(ORDER) == 39 and len(TASKS) == 39
fam_quota = {f: len([t for t in TASKS if t.get('family') == f and t['answer_type'] == 'single_choice'
                     and t['kind'] == 'compiled_practice_item'])
             for f in ('主体结构', '安全', '进度', '质量验收', '防水')}
assert fam_quota == {'主体结构': 5, '安全': 4, '进度': 3, '质量验收': 4, '防水': 4}, fam_quota

dst = os.path.join(HERE, '..', 'form_v2_manifest.json')
json.dump(manifest, open(dst, 'w'), ensure_ascii=False, indent=1)
print('OK tasks=', len(TASKS), 'scored=', len([t for t in TASKS if t.get('scored')]),
      'materials chars:', {k: v['chars'] for k, v in MATERIALS.items()})
print('dimension counts:', {k: len(v) for k, v in manifest['dimension_matrix'].items()})
print('family quota singles:', fam_quota)
