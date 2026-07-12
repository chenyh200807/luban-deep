#!/usr/bin/env python3
"""
Battle2 S2-T3 — mcq_feedback_ab 冻结语料生成器（do-once，语料以 cases.jsonl 为准）。

设计约束（eval-design 臂公平）：
  * graded_context 与 grounding_context 全部冻结进 fixture——两臂吃同一份检索结果，
    消检索方差；判分裁决字段（is_correct/score/correct_answer）在 fixture 里就是
    服务端 authority 已算定的终态，agent 只做讲评。
  * gold.correct_letters 一律按"学员题面 Options"的字母（题面字母对齐硬约束）。
  * open_world 用例 correct_answer=""/is_correct=None（deep_question
    _apply_open_world_grading_state 清占位后的形状），gold 由冻结 grounding 的教材
    原文决定；gold_source 标注 fixture_frozen_grounding，billable 定级前须 owner
    按教材原文人工核定（可证伪）。

重跑：python eval/fixtures/mcq_feedback_ab/build_cases.py  （幂等覆盖 cases.jsonl）
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent / "cases.jsonl"


def mcq(
    case_id: str,
    scenario: str,
    question: str,
    options: dict[str, str],
    correct: str,
    user: str,
    *,
    question_type: str = "choice",
    explanation: str = "",
    grounding: str = "",
    user_message: str | None = None,
    trap_type: str = "",
) -> dict:
    is_correct = sorted(user.upper()) == sorted(correct.upper()) if correct else None
    context: dict = {
        "question_id": f"qab_{case_id}",
        "question_type": question_type,
        "question": question,
        "options": options,
        "user_answer": user,
        "correct_answer": correct,
        "is_correct": is_correct,
        "explanation": explanation,
    }
    if correct:
        context["construction_grading_result"] = {
            "question_id": f"qab_{case_id}",
            "question_type": question_type,
            "user_answer": user,
            "correct_answer": correct,
            "is_correct": is_correct,
            "score_awarded": 1.0 if is_correct else 0.0,
            "max_score": 1.0,
            "grading_source": "questions_bank",
            "evidence_refs": (
                [{"source": "questions_bank", "field": "trap_type", "value": trap_type}]
                if trap_type
                else []
            ),
        }
    else:
        context["diagnosis"] = "OPEN_WORLD"
        context["is_correct"] = None
    return {
        "case_id": case_id,
        "scenario": scenario,
        "arm_input": {
            "user_message": user_message or f"我选{user}",
            "question_context": context,
            "history_context": "",
            "grounding_context": grounding,
        },
        "gold": {
            "authority": "questions_bank" if correct else "open_world",
            "correct_letters": sorted(correct.upper()) if correct else [],
            "wrong_selected": sorted(set(user.upper()) - set(correct.upper())) if correct else [],
            "gold_source": "bank_row_frozen" if correct else "fixture_frozen_grounding",
        },
    }


CASES: list[dict] = [
    # ── 单选错（生产 LLM 判分轮主流形态）×8 ─────────────────────────────────
    mcq(
        "sw01", "single_wrong",
        "双扇防火门的关闭方式，正确的是？",
        {"A": "同时关闭", "B": "按顺序关闭", "C": "自动关闭", "D": "手动关闭"},
        "B", "C",
        explanation="双扇防火门应装顺序器，保证先后按顺序关闭。",
        grounding="【教材要点 L1】双扇防火门应具有按顺序自行关闭的功能，顺序器用于保证先后关闭。",
        trap_type="顺序关闭与自动关闭混淆",
    ),
    mcq(
        "sw02", "single_wrong",
        "直接接触土体浇筑的混凝土构件，其保护层厚度不应小于（　）mm。",
        {"A": "40", "B": "50", "C": "65", "D": "70"},
        "C", "B",
        explanation="直接接触土体浇筑的构件，保护层厚度不应小于65mm。",
        grounding="【教材要点 L1】混凝土结构中直接接触土体浇筑的构件，其保护层厚度不应小于65mm。",
    ),
    mcq(
        "sw03", "single_wrong",
        "关于超过一定规模的危大工程专项施工方案，正确的做法是？",
        {"A": "项目经理审批后实施", "B": "组织专家论证", "C": "监理审批后实施", "D": "建设单位备案即可"},
        "B", "A",
        explanation="超过一定规模的危大工程专项施工方案应组织专家论证。",
        grounding="【教材要点 L1】超过一定规模的危险性较大的分部分项工程，施工单位应当组织召开专家论证会。",
        trap_type="专家论证程序与内部审批混淆",
    ),
    mcq(
        "sw04", "single_wrong",
        "混凝土采用硅酸盐水泥时，浇水养护时间不得少于（　）天。",
        {"A": "3", "B": "7", "C": "14", "D": "28"},
        "B", "C",
        explanation="硅酸盐水泥、普通硅酸盐水泥拌制的混凝土浇水养护不得少于7d。",
        grounding="【教材要点 L1】采用硅酸盐水泥、普通硅酸盐水泥或矿渣硅酸盐水泥拌制的混凝土，浇水养护时间不得少于7d；掺缓凝型外加剂或有抗渗要求的混凝土不得少于14d。",
        trap_type="7d 与 14d（掺外加剂/抗渗）适用条件混淆",
    ),
    mcq(
        "sw05", "single_wrong",
        "屋面卷材防水层施工时，卷材铺贴方向正确的是？",
        {"A": "屋面坡度小于3%时宜垂直屋脊铺贴", "B": "屋面坡度小于3%时宜平行屋脊铺贴", "C": "任何坡度均垂直屋脊铺贴", "D": "任何坡度均平行屋脊铺贴"},
        "B", "A",
        explanation="屋面坡度小于3%时，卷材宜平行屋脊铺贴。",
        grounding="【教材要点 L1】卷材防水层施工：屋面坡度小于3%时宜平行屋脊铺贴；坡度在3%~15%时可平行或垂直屋脊铺贴。",
    ),
    mcq(
        "sw06", "single_wrong",
        "施工现场临时用电，TN-S 系统的特征是？",
        {"A": "工作零线与保护零线合一", "B": "专用保护零线与工作零线分开设置", "C": "不设保护零线", "D": "保护零线可重复利用作相线"},
        "B", "A",
        explanation="TN-S 系统即三相五线制，专用保护零线 PE 与工作零线 N 分开。",
        grounding="【教材要点 L1】施工现场临时用电应采用 TN-S 接零保护系统，设置专用保护零线，保护零线与工作零线分开。",
        trap_type="TN-S 与 TN-C 系统特征混淆",
    ),
    mcq(
        "sw07", "single_wrong",
        "基坑验槽通常应以哪种方法为主？",
        {"A": "钎探法", "B": "轻型动力触探", "C": "观察法", "D": "洛阳铲探法"},
        "C", "A",
        explanation="验槽应以观察法为主，辅以钎探等方法。",
        grounding="【教材要点 L1】基坑验槽以观察法为主，钎探法为辅。",
    ),
    mcq(
        "sw08", "single_wrong",
        "砌体结构中，砖砌体的水平灰缝砂浆饱满度不得低于（　）。",
        {"A": "70%", "B": "80%", "C": "90%", "D": "95%"},
        "B", "C",
        explanation="砖砌体水平灰缝砂浆饱满度不得低于80%。",
        grounding="【教材要点 L1】砖砌体水平灰缝的砂浆饱满度不得低于80%；竖向灰缝不得出现透明缝、瞎缝和假缝。",
    ),
    # ── 单选对 ×3 ────────────────────────────────────────────────────────────
    mcq(
        "sr01", "single_right",
        "压型金属板采用轻型屋面时，屋面最小坡度宜为多少？",
        {"A": "5%", "B": "1%", "C": "2%", "D": "3%"},
        "A", "A",
        explanation="压型金属板屋面最小坡度 5%。",
        grounding="【教材要点 L1】压型金属板轻型屋面的最小坡度为5%。",
    ),
    mcq(
        "sr02", "single_right",
        "主体结构分部工程包含下列哪一项？",
        {"A": "地基基础", "B": "建筑屋面", "C": "装饰装修", "D": "钢结构"},
        "D", "D",
        explanation="钢结构是主体结构分部的子分部工程。",
        grounding="【教材要点 L1】主体结构分部工程包括混凝土结构、砌体结构、钢结构、钢管混凝土结构、型钢混凝土结构、铝合金结构、木结构等子分部。",
    ),
    mcq(
        "sr03", "single_right",
        "大体积混凝土养护时，里表温差不宜超过（　）℃。",
        {"A": "15", "B": "20", "C": "25", "D": "30"},
        "C", "C",
        explanation="大体积混凝土里表温差不宜大于25℃。",
        grounding="【教材要点 L1】大体积混凝土浇筑体的里表温差不宜大于25℃，表面与大气温差不宜大于20℃。",
    ),
    # ── 多选漏选 ×3 ──────────────────────────────────────────────────────────
    mcq(
        "mm01", "multi_missed",
        "关于模板支架搭设的说法，正确的有（　）。",
        {"A": "立杆底部应设置垫板", "B": "可采用碗扣式与扣件式混搭", "C": "应按专项方案搭设", "D": "拆除时应先支后拆", "E": "随意留设扫地杆"},
        "ACD", "AC",
        question_type="multi_choice",
        explanation="立杆设垫板、按专项方案搭设、先支后拆均正确；混搭与随意留设扫地杆错误。",
        grounding="【教材要点 L1】模板支架应按专项施工方案搭设，立杆底部设置垫板；拆除遵循先支后拆、后支先拆。",
        trap_type="漏选程序性正确项（先支后拆）",
    ),
    mcq(
        "mm02", "multi_missed",
        "施工现场消防安全管理中，动火作业审批正确的有（　）。",
        {"A": "一级动火由项目负责人审批", "B": "二级动火由项目负责人审批", "C": "三级动火由班组负责人审批", "D": "动火证当日有效", "E": "动火证可跨区域使用"},
        "BD", "B",
        question_type="multi_choice",
        explanation="二级动火作业由项目责任人审批；动火证当日有效，一个动火点一张证。",
        grounding="【教材要点 L1】二级动火作业由项目责任人审批；动火许可证当日有效且限定动火地点，不得跨区域使用。",
    ),
    mcq(
        "mm03", "multi_missed",
        "关于基坑监测，说法正确的有（　）。",
        {"A": "一级基坑必须实施监测", "B": "监测方案由建设单位编制", "C": "达到报警值应立即报告", "D": "监测点应避开支护结构受力关键部位", "E": "监测应委托第三方"},
        "ACE", "AE",
        question_type="multi_choice",
        explanation="一级基坑必须监测、达报警值立即报告、委托第三方均正确。",
        grounding="【教材要点 L1】开挖深度超过5m的基坑工程应实施第三方监测；监测数据达到报警值时必须立即报告。",
    ),
    # ── 多选错选 ×2 ──────────────────────────────────────────────────────────
    mcq(
        "me01", "multi_extra",
        "关于脚手架连墙件设置，正确的有（　）。",
        {"A": "宜靠近主节点设置", "B": "应从底层第一步纵向水平杆处开始设置", "C": "可采用仅有拉筋的柔性连墙件用于高层", "D": "应优先采用刚性连墙件", "E": "连墙件可随意拆除后补装"},
        "ABD", "ABCD",
        question_type="multi_choice",
        explanation="高层脚手架严禁采用仅有拉筋的柔性连墙件。",
        grounding="【教材要点 L1】连墙件宜靠近主节点设置，应从底层第一步纵向水平杆处开始；高度24m以上的双排脚手架应采用刚性连墙件，严禁使用仅有拉筋的柔性连墙件。",
        trap_type="柔性连墙件适用范围误扩到高层",
    ),
    mcq(
        "me02", "multi_extra",
        "钢筋进场验收应检查的项目有（　）。",
        {"A": "出厂合格证", "B": "力学性能复验报告", "C": "外观质量", "D": "焊工上岗证", "E": "重量偏差"},
        "ABCE", "ABCDE",
        question_type="multi_choice",
        explanation="焊工上岗证属焊接作业管理，不是钢筋进场验收项目。",
        grounding="【教材要点 L1】钢筋进场时应检查出厂合格证、按批抽取试件做力学性能和重量偏差检验，并进行外观质量检查。",
    ),
    # ── 判断题 ×2 ────────────────────────────────────────────────────────────
    mcq(
        "jd01", "judge",
        "判断：掺缓凝型外加剂的混凝土，浇水养护时间不得少于7d。",
        {"A": "对", "B": "错"},
        "B", "A",
        question_type="judge",
        explanation="掺缓凝型外加剂或有抗渗要求的混凝土养护不得少于14d，7d 是普通硅酸盐水泥口径。",
        grounding="【教材要点 L1】掺缓凝型外加剂或有抗渗要求的混凝土，浇水养护时间不得少于14d。",
        trap_type="7d/14d 适用口径搬错",
    ),
    mcq(
        "jd02", "judge",
        "判断：施工升降机安装完毕后，经安装单位自检合格即可投入使用。",
        {"A": "对", "B": "错"},
        "B", "A",
        question_type="judge",
        explanation="还须经有资质的检验检测机构监督检验合格，并组织验收。",
        grounding="【教材要点 L1】施工升降机安装完毕，应经安装单位自检、检验检测机构监督检验合格，并经使用单位组织验收后方可投入使用。",
    ),
    # ── 组合选项 ×1 ──────────────────────────────────────────────────────────
    mcq(
        "co01", "combo_option",
        "关于悬挑脚手架的说法，正确的是：①型钢锚固段长度不应小于悬挑段的1.25倍；②悬挑梁宜采用槽钢；③锚固位置设置在楼板上时应验算楼板承载力；④架体高度可不受限制。",
        {"A": "①③", "B": "①②③", "C": "②③④", "D": "①②④"},
        "A", "B",
        explanation="悬挑梁应采用工字钢（双轴对称截面），槽钢说法错误；架体分段高度不宜超过20m。",
        grounding="【教材要点 L1】悬挑式脚手架的悬挑钢梁宜采用双轴对称截面的型钢（工字钢）；锚固段长度不应小于悬挑段长度的1.25倍；每段架体搭设高度不宜超过20m。",
        trap_type="槽钢/工字钢截面要求混入组合项",
    ),
    # ── OCR 噪声作答 ×1 ──────────────────────────────────────────────────────
    mcq(
        "on01", "ocr_noise",
        "填充墙砌体与主体结构间的空隙部位施工，正确的做法是？",
        {"A": "砌完后立即嵌填", "B": "至少间隔7d后嵌填", "C": "至少间隔14d后嵌填", "D": "无需嵌填"},
        "C", "A",
        explanation="填充墙砌至接近梁底、板底时应留空隙，至少间隔14d后再将其补砌挤紧。",
        grounding="【教材要点 L1】填充墙砌至接近梁、板底时，应留一定空隙，待填充墙砌筑完并应至少间隔14d后，再将其补砌挤紧。",
        user_message="我 选 Ａ。（拍照识别：选顶Ａ 立即嵌填）",
    ),
    # ── open_world（无题库标准答案 authority）×2 ─────────────────────────────
    mcq(
        "ow01", "open_world",
        "水泥砂浆防水层每层宜连续施工，必须留槎时应采用（　）。",
        {"A": "平槎", "B": "阶梯坡形槎", "C": "垂直槎", "D": "企口槎"},
        "", "A",
        explanation="",
        grounding="【教材要点 L1】水泥砂浆防水层各层应紧密结合，每层宜连续施工；必须留槎时应采用阶梯坡形槎，接槎要依层次顺序操作、层层搭接紧密。",
        user_message="我选A",
    ),
    mcq(
        "ow02", "open_world",
        "地下工程混凝土结构主体防水应采用的混凝土是（　）。",
        {"A": "普通混凝土", "B": "防水混凝土", "C": "轻骨料混凝土", "D": "纤维混凝土"},
        "", "B",
        explanation="",
        grounding="【教材要点 L1】地下工程主体结构防水应采用防水混凝土，并根据防水等级要求采取其他防水措施。",
        user_message="我选B",
    ),
]


def batch_case(case_id: str, sub: list[dict], user_message: str) -> dict:
    items = []
    for entry in sub:
        context = dict(entry["arm_input"]["question_context"])
        items.append(context)
    wrong = [c for c in items if c.get("is_correct") is False]
    top: dict = {
        "question_id": f"qab_{case_id}",
        "question_type": "choice",
        "question": items[0]["question"],
        "options": items[0]["options"],
        "user_answer": "",
        "correct_answer": "",
        "is_correct": all(c.get("is_correct") for c in items),
        "explanation": "",
        "items": items,
    }
    grounding = "\n".join(
        entry["arm_input"]["grounding_context"] for entry in sub if entry["arm_input"]["grounding_context"]
    )
    return {
        "case_id": case_id,
        "scenario": "batch_4",
        "arm_input": {
            "user_message": user_message,
            "question_context": top,
            "history_context": "",
            "grounding_context": grounding,
        },
        "gold": {
            "authority": "questions_bank",
            "correct_letters": sorted(
                {letter for c in items for letter in str(c["correct_answer"]).upper()}
            ),
            "wrong_selected": sorted(
                {
                    letter
                    for c in wrong
                    for letter in set(str(c["user_answer"]).upper()) - set(str(c["correct_answer"]).upper())
                }
            ),
            "per_item_correct_letters": [sorted(str(c["correct_answer"]).upper()) for c in items],
            "gold_source": "bank_row_frozen",
        },
    }


# 批量 4 题 ×2（复用上面的冻结单题，题面与 grounding 不变）
CASES.append(
    batch_case("bt01", [CASES[0], CASES[1], CASES[8], CASES[6]], "1.C 2.B 3.A 4.A")
)
CASES.append(
    batch_case("bt02", [CASES[2], CASES[3], CASES[9], CASES[7]], "1.A 2.C 3.D 4.C")
)


def main() -> None:
    # 批量用例的 per-item user_answer 需与 user_message 对齐（冻结时已由单题携带）。
    with OUT.open("w", encoding="utf-8") as handle:
        for case in CASES:
            handle.write(json.dumps(case, ensure_ascii=False) + "\n")
    scenarios: dict[str, int] = {}
    for case in CASES:
        scenarios[case["scenario"]] = scenarios.get(case["scenario"], 0) + 1
    print(f"wrote {len(CASES)} cases -> {OUT}")
    print(json.dumps(scenarios, ensure_ascii=False))


if __name__ == "__main__":
    main()
