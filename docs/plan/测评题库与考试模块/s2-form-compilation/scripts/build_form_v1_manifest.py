#!/usr/bin/env python3
"""主表单 v1 manifest 生成:声明式表单结构 + 从源资产回填 content_sha256/难度/锚。
只读源资产;唯一写盘对象 form_v1_manifest.json。可重跑、确定性。"""
import hashlib, json, os, re, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '../../../../..'))
PRACTICE_DIR = os.path.join(ROOT, 'deeptutor/services/luban_lesson/compiled')

def sha(s):
    return hashlib.sha256(unicodedata.normalize('NFKC', re.sub(r'\s+', '', s)).encode()).hexdigest()

def practice_item(pid, qtag):
    d = json.load(open(os.path.join(PRACTICE_DIR, f'{pid.lower()}.practice.authority.json')))
    for q in d['items']:
        if re.search(rf'-{qtag}-', q.get('variant_id', '')):
            return q, d
    raise KeyError(f'{pid} {qtag}')

def exam_item(year, anchor, typ):
    p = os.path.join(ROOT, f'docs/原始数据/考点原料/题库快照/FINAL_CLEANED_EXAM_V{year}.json')
    d = json.load(open(p))
    for ch in d['chunks']:
        sm = ch.get('source_meta') or {}
        if re.sub(r'\s+', '', sm.get('original_anchor') or '') != anchor:
            continue
        for e in ch.get('exercises', []):
            if e['type'] == typ:
                return e, f'docs/原始数据/考点原料/题库快照/FINAL_CLEANED_EXAM_V{year}.json'
    raise KeyError(f'{year} {anchor}')

TASKS = []

def add(task_id, kind, family, pack, dimension, answer_type, confidence=False, **kw):
    TASKS.append(dict(task_id=task_id, kind=kind, family=family, pack_id=pack,
                      dimension=dimension, answer_type=answer_type,
                      confidence_input=confidence, **kw))

# ---- 3 备考上下文(profile_probe 形,不计分) ----
for pid_, (probe, ask) in {
    'P1': ('prep_attempt_history', '第几次备考实务?上次实务成绩落在哪个分数带?(不计分,用于备考画像)'),
    'P2': ('prep_passed_subjects', '已通过科目及通过年份(管理/经济/法规)?(不计分,喂给滚动作废提醒)'),
    'P3': ('prep_weekly_hours', '每周有效学习时长?(不计分,只影响可行性/节奏,不影响分数带)'),
}.items():
    add(pid_, 'profile_probe', None, None, 'prep_feasibility(独立字段,禁入分数带)', 'single_choice',
        probe_id=probe, prompt=ask, scored=False)

# ---- T1–T4 真题客观题(照录) ----
e, f = exam_item('2015', '第10题', 'single_choice')
add('T1', 'real_exam_objective', '主体结构', 'C04', 'core_knowledge', 'single_choice', confidence=True,
    scored=True, source={'kind': 'real_exam', 'year': 2015, 'exam_anchor': '第10题', 'file': f,
                         'sidecar': 'docs/原始数据/考点原料/_C04_exam_evidence.json'},
    difficulty=e['question_data'].get('difficulty'), exam_score=e['question_data'].get('score'),
    stem=e['question_data']['stem'], options=e['question_data'].get('options'),
    answer_key=e['question_data']['correct_answer'], content_sha256=sha(e['question_data']['stem']))
e, f = exam_item('2016', '第13题', 'single_choice')
add('T2', 'real_exam_objective', '安全', 'S05', 'core_knowledge', 'single_choice',
    scored=True, source={'kind': 'real_exam', 'year': 2016, 'exam_anchor': '第13题', 'file': f,
                         'sidecar': 'docs/原始数据/考点原料/_S05_exam_evidence.json'},
    difficulty=e['question_data'].get('difficulty'), exam_score=e['question_data'].get('score'),
    stem=e['question_data']['stem'], options=e['question_data'].get('options'),
    answer_key=e['question_data']['correct_answer'], content_sha256=sha(e['question_data']['stem']))
e, f = exam_item('2020', '第30题', 'multiple_choice')
add('T3', 'real_exam_objective', '质量验收', 'A02', 'core_knowledge', 'multiple_choice',
    scored=True, source={'kind': 'real_exam', 'year': 2020, 'exam_anchor': '第30题', 'file': f,
                         'sidecar': 'docs/原始数据/考点原料/_A02_exam_evidence.json'},
    difficulty=e['question_data'].get('difficulty'), exam_score=e['question_data'].get('score'),
    stem=e['question_data']['stem'], options=e['question_data'].get('options'),
    answer_key=e['question_data']['correct_answer'], content_sha256=sha(e['question_data']['stem']))
e, f = exam_item('2016', '第27题', 'multiple_choice')
add('T4', 'real_exam_objective', '防水', 'F02', 'core_knowledge', 'multiple_choice',
    scored=True, source={'kind': 'real_exam', 'year': 2016, 'exam_anchor': '第27题', 'file': f,
                         'sidecar': 'docs/原始数据/考点原料/_F02_exam_evidence.json'},
    difficulty=e['question_data'].get('difficulty'), exam_score=e['question_data'].get('score'),
    stem=e['question_data']['stem'], options=e['question_data'].get('options'),
    answer_key=e['question_data']['correct_answer'], content_sha256=sha(e['question_data']['stem']),
    transcription_note='原题干「房面」为源数据笔误,呈现时订正为「屋面」,其余照录')

# ---- 案例材料(转写 ≤150 字) ----
MAT_A = ('某新建高层住宅工程,地下1层,地上12层,二层以下为现浇钢筋混凝土结构。'
         '项目部编制的《后浇带施工专项方案》确定:模板独立支设;剔除模板用钢丝网;'
         '因设计无要求,基础底板后浇带10d后封闭。监理工程师审查后要求整改。')
MAT_B = ('某新建住宅小区,各单位在工程质量检测管理中做了以下工作:①建设单位委托具有相应资质的'
         '检测机构负责本工程质量检测;②监理对混凝土试件制作与送样见证,试验员如实记录取样、'
         '现场检测情况并制作见证记录;③试样送检时,试验员向检测机构填报检测委托单;'
         '④总包项目部按建设单位要求,每月向检测机构支付当期检测费用。')
MAT_C = ('某新建商品住宅项目由两栋结构类型与建筑规模完全相同的单体组成。项目部针对四个施工过程'
         '拟采用四个专业施工队组织流水施工,流水节拍依次为3、3、6、3个月。建设单位要求缩短工期,'
         '项目部决定增加相应的专业施工队,组织成倍节拍流水施工。')

MATERIALS = {
    'CASE_A': {'text': MAT_A, 'chars': len(MAT_A), 'family': '主体结构', 'pack_id': 'C01',
               'source': {'kind': 'real_exam_case', 'year': 2018, 'exam_anchor': '案例分析(三)',
                          'sidecar': 'docs/原始数据/考点原料/_C01_exam_evidence.json'},
               'note': '忠实原题干措辞截取(方案三措施逐字保留);背景压缩,未添加任何事实'},
    'CASE_B': {'text': MAT_B, 'chars': len(MAT_B), 'family': '质量验收', 'pack_id': 'A02',
               'source': {'kind': 'real_exam_case', 'year': 2023, 'exam_anchor': '案例一',
                          'sidecar': 'docs/原始数据/考点原料/_A02_exam_evidence.json'},
               'note': '四项工作逐字保留(仅压缩定语);未添加任何事实'},
    'CASE_C': {'text': MAT_C, 'chars': len(MAT_C), 'family': '进度', 'pack_id': 'N03',
               'source': {'kind': 'real_exam_case', 'year': 2023, 'exam_anchor': '第2题',
                          'sidecar': 'docs/原始数据/考点原料/_N03_exam_evidence.json'},
               'note': '节拍3、3、6、3由官方答案「专业对数1+1+2+1=5、K=3」反推,与答案'
                       '「基础施工3个月;上部结构6个月」一致;施工段M=2=两栋;需教研复核'},
}

# ---- T5 案例A指错(转写多选) ----
add('T5', 'case_error_correction', '主体结构', 'C01', 'construction_logic', 'multiple_choice',
    scored=True, material='CASE_A',
    source={'kind': 'real_exam_case', 'year': 2018, 'exam_anchor': '案例分析(三)问题3',
            'sidecar': 'docs/原始数据/考点原料/_C01_exam_evidence.json'},
    stem='指出《后浇带施工专项方案》中的不妥之处。(多选;多答不得分)',
    options=[
        {'key': 'A', 'value': '模板独立支设', 'correct': True, 'cause': 'condition_misread',
         'source': '官方答案不妥之处①'},
        {'key': 'B', 'value': '剔除模板用钢丝网', 'correct': True, 'cause': 'knowledge_gap',
         'source': '官方答案不妥之处②(应保留)'},
        {'key': 'C', 'value': '基础底板后浇带10d后封闭', 'correct': True, 'cause': 'knowledge_gap',
         'source': '官方答案不妥之处③(应≥28d)'},
        {'key': 'D', 'value': '后浇带采用微膨胀混凝土浇筑', 'correct': False, 'cause': 'concept_boundary',
         'source': '官方答案技术措施(3)——正确做法作干扰项'},
        {'key': 'E', 'value': '后浇带混凝土保持至少14d湿润养护', 'correct': False, 'cause': 'concept_boundary',
         'source': '官方答案技术措施(5)——正确做法作干扰项'},
    ],
    answer_key='ABC', content_sha256=sha(MAT_A + 'T5'),
    difficulty='真题2018案例锚(案例分析(三)问题3,score 5.5)')

# ---- T6/T10/T11/T12 生产签发练习题(逐字取用) ----
for tid, pid, qtag, fam, note in [
    ('T6', 'C01', 'q13', '主体结构', '后浇带·技术措施——结构化采分点识别(§6.2 判分辨析族)'),
    ('T10', 'N03', 'q15', '进度', '采分句输出·末题——案例C的采分句任务'),
    ('T11', 'J01', 'q16', '安全', '采分诊断·末题——判分辨析任务(§6.2 answer-scoring discrimination)'),
    ('T12', 'F03', 'q10', '防水', '地下·一级做法——结构化采分点识别(替代自由作答,§6.2)'),
]:
    q, auth = practice_item(pid, qtag)
    add(tid, 'compiled_practice_item', fam, pid, 'case_scoring_point', q['answer_type'],
        scored=True, material=('CASE_C' if tid == 'T10' else None),
        source={'kind': 'compiled_practice_authority',
                'file': f'deeptutor/services/luban_lesson/compiled/{pid.lower()}.practice.authority.json',
                'variant_id': q['variant_id'], 'source_anchor': q.get('source_anchor'),
                'review_status': (q.get('review') or {}).get('status'),
                'sidecar': f'docs/原始数据/考点原料/_{pid}_exam_evidence.json'},
        stem=q['stem'], answer_key='(见 authority 文件 options.is_correct;本 manifest 不复制全部选项文)',
        rule_group=q.get('rule_group'), fact_id=q.get('fact_id'),
        content_sha256=q.get('content_sha256'), note=note)

# ---- T7/T8 案例B转写 ----
add('T7', 'case_error_correction', '质量验收', 'A02', 'construction_logic', 'multiple_choice',
    scored=True, material='CASE_B',
    source={'kind': 'real_exam_case', 'year': 2023, 'exam_anchor': '案例一问题1',
            'sidecar': 'docs/原始数据/考点原料/_A02_exam_evidence.json'},
    stem='指出工程施工质量检测管理工作中的不妥之处。(本问题2项不妥,多答不得分;多选)',
    options=[
        {'key': 'A', 'value': '工作①(建设单位委托有资质检测机构)', 'correct': False, 'cause': 'concept_boundary',
         'source': '案例原文,官方答案未列为不妥'},
        {'key': 'B', 'value': '工作②(试验员记录取样、现场检测情况并制作见证记录)', 'correct': True,
         'cause': 'knowledge_gap', 'source': '官方答案不妥①:应由见证人员记录并制作见证记录'},
        {'key': 'C', 'value': '工作③(试验员向检测机构填报检测委托单)', 'correct': False, 'cause': 'concept_boundary',
         'source': '案例原文,官方答案未列为不妥'},
        {'key': 'D', 'value': '工作④(总包项目部每月向检测机构支付当期检测费用)', 'correct': True,
         'cause': 'knowledge_gap', 'source': '官方答案不妥②:检测费用应由建设单位单独列支并按约支付'},
    ],
    answer_key='BD', content_sha256=sha(MAT_B + 'T7'), difficulty='真题2023案例锚(案例一问题1,score 7.0)')
add('T8', 'case_scoring_point_recognition', '质量验收', 'A02', 'case_scoring_point', 'multiple_choice',
    confidence=True, scored=True, material='CASE_B',
    source={'kind': 'real_exam_case', 'year': 2023, 'exam_anchor': '案例一问题1',
            'sidecar': 'docs/原始数据/考点原料/_A02_exam_evidence.json'},
    stem='混凝土试件制作与取样的见证记录内容,除取样情况外还应包括哪些?(多选)',
    options=[
        {'key': 'A', 'value': '制样', 'correct': True, 'cause': None, 'source': '官方答案:记录内容还包括制样'},
        {'key': 'B', 'value': '标识、封志', 'correct': True, 'cause': None, 'source': '官方答案:标识、封志'},
        {'key': 'C', 'value': '送检情况', 'correct': True, 'cause': None, 'source': '官方答案:送检'},
        {'key': 'D', 'value': '现场检测情况', 'correct': True, 'cause': None, 'source': '官方答案:现场检测'},
        {'key': 'E', 'value': '检测费用支付情况', 'correct': False, 'cause': 'condition_misread',
         'source': '案例材料④的元素,官方答案记录内容不含——干扰项取自材料本身'},
        {'key': 'F', 'value': '检测委托单编号', 'correct': False, 'cause': 'condition_misread',
         'source': '案例材料③的元素,官方答案记录内容不含——干扰项取自材料本身'},
    ],
    answer_key='ABCD', content_sha256=sha(MAT_B + 'T8'), difficulty='真题2023案例锚(同上)')

# ---- T9 案例C计算判断(转写单选) ----
add('T9', 'case_calc_judgment', '进度', 'N03', 'construction_logic', 'single_choice',
    confidence=True, scored=True, material='CASE_C',
    source={'kind': 'real_exam_case', 'year': 2023, 'exam_anchor': '第2题',
            'sidecar': 'docs/原始数据/考点原料/_N03_exam_evidence.json',
            'distractor_source': 'N03 practice q2/q3 已签发错误选项(E07/E09 带 loss_reason)'},
    stem='组织成倍节拍流水施工,流水步距K与专业施工队总数分别为多少?选出算式与依据都正确的一项。(单选)',
    options=[
        {'key': 'A', 'value': 'K取各节拍最大公约数=3个月;各过程队数=节拍÷K,共1+1+2+1=5个',
         'correct': True, 'cause': None, 'source': '官方答案(4):K=3;专业对数1+1+2+1=5'},
        {'key': 'B', 'value': 'K取最大节拍=6个月;四个施工过程共4个专业队(每过程1队)',
         'correct': False, 'cause': 'knowledge_gap', 'source': 'N03-q2 E09 选项+q3 E07 选项'},
        {'key': 'C', 'value': 'K=(3+3+6+3)÷4=3.75个月;队数按施工过程数取4个',
         'correct': False, 'cause': 'knowledge_gap', 'source': 'N03-q2 E09(平均值)选项'},
        {'key': 'D', 'value': 'K取最小节拍=3个月以保证咬合;队数=总节拍÷K=(3+3+6+3)÷3=5个',
         'correct': False, 'cause': 'concept_boundary',
         'source': 'N03-q2 E07+q3 E07 选项——数值碰巧对但依据错,考「依据」辨析'},
    ],
    answer_key='A', content_sha256=sha(MAT_C + 'T9'), difficulty='真题2023案例锚(第2题,score 6.0)')

manifest = {
    'schema': 'luban_s2_diagnostic_form.v1',
    'form_id': 'pass_readiness_form_main_v1',
    'blueprint': 'pass_readiness_architecture_v1',
    'date': '2026-08-05',
    'interaction_contract': '纯点选(single/multi letter tap);答案线格式 dict[str,str];无自由文本/拖拽',
    'written_expression': 'not_measured(计划 §6.2 无条件降级;分数带走 §7.2 更宽阶梯)',
    'checkpoint_after_task': 'T6',
    'checkpoint_rule': '6题粗带:超宽带宽(≥30)+evidence_coverage=low,不出证据屏不点名弱点(§6.2)',
    'confidence_tasks': ['T1', 'T8', 'T9'],
    'context_probes': ['P1', 'P2', 'P3'],
    'ordering': ['P1', 'P2', 'P3', 'T1', 'T2', 'T3', 'T4', 'T5', 'T6',
                 'T7', 'T8', 'T9', 'T10', 'T11', 'T12'],
    'dimension_matrix': {
        'core_knowledge': ['T1', 'T2', 'T3', 'T4'],
        'construction_logic': ['T5', 'T7', 'T9'],
        'case_scoring_point': ['T6', 'T8', 'T10', 'T11', 'T12'],
        'answer_expression': [],
        'prep_feasibility_context_only': ['P1', 'P2', 'P3'],
    },
    'family_matrix': {
        '主体结构': ['T1', 'T5', 'T6'], '安全': ['T2', 'T11'], '进度': ['T9', 'T10'],
        '质量验收': ['T3', 'T7', 'T8'], '防水': ['T4', 'T12'],
    },
    'materials': MATERIALS,
    'tasks': TASKS,
}
dst = os.path.join(HERE, '..', 'form_v1_manifest.json')
json.dump(manifest, open(dst, 'w'), ensure_ascii=False, indent=1)
print('OK tasks=', len(TASKS), 'materials chars:',
      {k: v['chars'] for k, v in MATERIALS.items()})
