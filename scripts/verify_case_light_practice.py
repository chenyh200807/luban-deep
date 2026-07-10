#!/usr/bin/env python3
"""案例题轻练 · 一键眼见为实验证。

一条命令,把每个判分引擎喂**真题金标**,打印"引擎算出的 == 官方答案";再把 F16
起鼓割补整条链(采分点→出题→RTG门→判分)跑一遍,复现 live 验证的分数。
纯本地、确定性(生成侧用 dev stub 干扰项);要真 LLM 见 scripts/aliyun_probes/。

    python scripts/verify_case_light_practice.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deeptutor.services.construction_grading.case_calc_dag import CalcRole, CalcStep, solve_calc_dag
from deeptutor.services.construction_grading.case_cpm_solver import Activity, solve_cpm
from deeptutor.services.construction_grading.case_flaw_correction import (
    FlawCorrectionPair, judge_flaw_correction,
)
from deeptutor.services.construction_grading.case_light_practice_contract import (
    AcceptableVariant, LubanCaseScoringPoint, PointType, SourceRef, score_conjunction_group,
)
from deeptutor.services.construction_grading.case_light_practice_generator import (
    generate_point_select_item, load_dev_fixture,
)
from deeptutor.services.construction_grading.case_load_combination import (
    SetMembershipPoint, grade_set_membership,
)
from deeptutor.services.construction_grading.case_process_ordering import OrderingSpec, grade_ordering

_OK, _BAD = "✅", "❌"


def _line(name, got, expected, ok):
    print(f"  {_OK if ok else _BAD} {name}: 算出={got}  官方金标={expected}")


def verify_engines() -> bool:
    ok = True
    print("\n【1】每个判分引擎 vs 真题金标(引擎算出的 == 官方答案)")

    # CPM —— N01 网络官方 SVG:关键线路 开始-A-C-E-结束,总工期 10
    net = [Activity("START", 0, ()), Activity("A", 3, ("START",)), Activity("B", 2, ("START",)),
           Activity("C", 4, ("A",)), Activity("D", 2, ("A", "B")), Activity("E", 3, ("C", "D")),
           Activity("END", 0, ("E",))]
    r = solve_cpm(net)
    cp = "-".join(r.critical_paths[0]); dur = r.project_duration
    good = cp == "START-A-C-E-END" and dur == 10
    _line("CPM关键线路/总工期(N01真题)", f"{cp} 总工期{dur}", "START-A-C-E-END 总工期10", good); ok &= good

    # DAG+ECF —— 真题造价链 EXAM_1A432000_P0016_02 小问3:合同价 64539.54
    steps = [
        CalcStep("Q1", "48000", (), 0.01, 2, 1, CalcRole.PROCESS),
        CalcStep("Q2", "Q1*0.15", ("Q1",), 0.01, 2, 1, CalcRole.PROCESS),
        CalcStep("Q3", "1500+1200+1200*0.03", (), 0.01, 2, 1, CalcRole.PROCESS),
        CalcStep("Q4", "(Q1+Q2+Q3)*0.022", ("Q1", "Q2", "Q3"), 0.01, 2, 1, CalcRole.PROCESS),
        CalcStep("Q5", "(Q1+Q2+Q3+Q4)*0.09", ("Q1", "Q2", "Q3", "Q4"), 0.01, 2, 1, CalcRole.PROCESS),
        CalcStep("Q6", "Q1+Q2+Q3+Q4+Q5", ("Q1", "Q2", "Q3", "Q4", "Q5"), 0.01, 2, 1, CalcRole.RESULT),
    ]
    v = solve_calc_dag(steps, {})
    good = abs(v["Q6"] - 64539.54) < 1e-6 and abs(v["Q4"] - 1274.59) < 1e-6
    _line("DAG+ECF造价链(EXAM_1A432000_P0016_02)", f"合同价{v['Q6']} 规费{v['Q4']}",
          "合同价64539.54 规费1274.59", good); ok &= good

    # 荷载组合 —— 真题 EXAM_1A434020_P0009_01:底面模板{G1,G2,G3,Q1}
    pts = [SetMembershipPoint("底面模板", frozenset({"G1", "G2", "G3", "Q1"}), 1.0),
           SetMembershipPoint("立杆", frozenset({"G1", "G2", "G3", "Q4"}), 1.0)]
    gr = grade_set_membership(pts, {"底面模板": ["G1", "G2", "G3", "Q1"], "立杆": ["G1", "G2", "G3", "Q4"]})
    wrong = grade_set_membership(pts, {"底面模板": ["G1", "G2", "G3", "Q1", "Q2"], "立杆": ["G1", "G2", "G3", "Q4"]})
    good = gr.total_awarded == 2.0 and wrong.total_awarded == 1.0
    _line("荷载组合集合判分(EXAM_1A434020_P0009_01)", f"全对={gr.total_awarded} 多选一个={wrong.total_awarded}",
          "全对2.0 多选一个1.0(多选那项0)", good); ok &= good

    # 工序排序 —— 真题 EXAM_1A434000_P0010_02 工艺流程
    spec = OrderingSpec.from_sequence(["清理表面", "支设模板", "洒水湿润", "涂抹混凝土界面剂"])
    right = grade_ordering(spec, ["清理表面", "支设模板", "洒水湿润", "涂抹混凝土界面剂"]).correct
    swapped = grade_ordering(spec, ["支设模板", "清理表面", "洒水湿润", "涂抹混凝土界面剂"]).correct
    good = right and not swapped
    _line("工序排序判分(EXAM_1A434000_P0010_02)", f"正确序={right} 换序={swapped}", "正确序对/换序错", good); ok &= good

    # 合取门 —— 找错∧改正
    ref = SourceRef("exam_reference_answer", "判断改正")
    def _m(pid): return LubanCaseScoringPoint(pid, "1", "q::s1", "q::s1", f"s{pid}", "official_answer",
        PointType.CONJUNCTION_MEMBER, (), (AcceptableVariant("v", ref),), 0.5, (ref,), "official_answer", conjunction_group="g")
    pair = FlawCorrectionPair(_m("flaw"), _m("fix"))
    both = judge_flaw_correction(pair, flaw_hit=True, correction_hit=True).awarded_score
    only = judge_flaw_correction(pair, flaw_hit=True, correction_hit=False).awarded_score
    good = both == 1.0 and only == 0.0
    _line("合取门(找错∧改正)", f"都对={both} 只找错={only}", "都对1.0 只找错0(不得分)", good); ok &= good
    return ok


def verify_f16_chain() -> bool:
    print("\n【2】F16 起鼓割补整条链(采分点→出题→RTG门→判分),复现 live 验证")
    qid, points = load_dev_fixture("F16_qigu_gebu")
    stub = lambda _p: json.dumps({"distractors": [
        {"text": "喷灯烘烤后直接重贴不剥开", "error_code": "E06"},
        {"text": "用水泥砂浆抹平鼓泡即可", "error_code": "E01"},
        {"text": "整片屋面铲除重做防水层", "error_code": "E05"}]})
    gen = generate_point_select_item(points, complete_fn=stub, target_point_id="a5", dev_fixture=True)
    print(f"  出题: {gen.item['stem']}")
    print(f"    ✓正确(采分点原文): {gen.item['correct_options'][0]['text']}")
    for d in gen.item["distractors"]:
        print(f"    ✗干扰: {d['text']} [{d['error_code']}]")
    print(f"  RTG1-8 门裁决: {gen.status.value}(生成状态)")

    all_ids = {p.point_id for p in points}
    a = score_conjunction_group(points, all_ids - {"a5"})   # 漏分层剥开
    b = score_conjunction_group(points, all_ids)            # 全命中
    total = sum(p.max_score for p in points)
    good = abs(a - 1.2) < 1e-6 and abs(b - 1.5) < 1e-6
    print(f"  {_OK if good else _BAD} 判分: 作答A漏『分层剥开』={round(a,2)} / 作答B写了={round(b,2)}(满分{total})")
    print("     ← 复现 live 验证:漏关键点判出更低分(污染rubric虚高被治好的证据)")
    return good


def main() -> int:
    print("=" * 68)
    print("案例题轻练 · 判分引擎 + 全链路 眼见为实验证(纯本地确定性)")
    print("=" * 68)
    e = verify_engines()
    c = verify_f16_chain()
    print("\n" + "=" * 68)
    print(f"结果: 引擎金标={'全对' if e else '有不符'} · F16全链路={'跑通且分数对' if c else '不符'}")
    print("要真 LLM 生成/异源实测 → scripts/aliyun_probes/ ;跑全部单测 → pytest tests/services/construction_grading/")
    print("=" * 68)
    return 0 if (e and c) else 1


if __name__ == "__main__":
    raise SystemExit(main())
