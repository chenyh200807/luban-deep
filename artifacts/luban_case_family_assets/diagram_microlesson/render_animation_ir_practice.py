#!/usr/bin/env python3
"""Render an interactive practice page from animation_ir.v0.

The practice page is intentionally deterministic: the IR supplies card facts
and key points, while this renderer owns the quiz state machine.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def js_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def key_points(ir: dict[str, Any]) -> list[str]:
    points = list((ir.get("ai_context") or {}).get("key_points") or [])
    fallback = [
        "先判对象",
        "再判条件",
        "写判断依据",
        "落采分句",
    ]
    for item in fallback:
        if len(points) >= 4:
            break
        points.append(item)
    return [str(item) for item in points[:4]]


EXPLANATION_MARKERS = ["因为", "不是", "不能", "要", "先", "必须", "阅卷", "扣分", "采分"]


def has_explanation_marker(value: Any) -> bool:
    text = str(value or "")
    return any(marker in text for marker in EXPLANATION_MARKERS)


def explain(value: Any, suffix: str = "因为这一步会影响采分。") -> str:
    text = str(value or "").strip()
    if not text:
        return suffix
    return text if has_explanation_marker(text) else f"{text}{suffix}"


def visual_items(visual: dict[str, Any]) -> list[str]:
    for key in ("items", "after", "before", "labels"):
        items = [str(item) for item in visual.get(key, []) if item is not None]
        if len(items) >= 3:
            return items[:4]
    return ["看现场对象", "找错误动作", "补采分句"]


def normalize_blueprint_questions(blueprint: list[Any]) -> list[dict[str, Any]]:
    questions = json.loads(json.dumps(blueprint, ensure_ascii=False))
    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            continue
        question.setdefault("id", f"q{index + 1}")
        question.setdefault("stageLabel", question.get("skill") or f"第{index + 1}题")
        question.setdefault("skill", question.get("stageLabel") or "采分动作")
        question.setdefault("student", "学生准备作答。")
        question.setdefault("stem", "哪一个动作最能拿分？")
        visual = question.setdefault("visual", {})
        if isinstance(visual, dict):
            items = visual_items(visual)
            visual["items"] = items
            hot_index = visual.get("hotIndex", 0)
            if not isinstance(hot_index, int):
                hot_index = 0
            visual["hotIndex"] = max(0, min(hot_index, len(items) - 1))
        question["correct"] = explain(question.get("correct"), "因为这句话把现场对象写成了采分动作。")
        question["wrong"] = explain(question.get("wrong"), "因为它没有补齐阅卷要看的采分动作。")
        feedback = question.setdefault("optionFeedback", {})
        if isinstance(feedback, dict):
            for option in question.get("options", []):
                option_id = option.get("id")
                if option_id and option_id != question.get("answer"):
                    feedback[option_id] = explain(
                        feedback.get(option_id),
                        "因为漏掉这个动作会扣分，正确答案要补完整采分句。",
                    )
    return questions


def build_s01_questions() -> list[dict[str, Any]]:
    """S01 needs scenario diagnosis, not key-point label recognition."""
    return [
        {
            "id": "q1",
            "stageLabel": "看答案缺口",
            "skill": "验收项目说清",
            "student": "学生答:“脚手架验收合格，可以投入使用。”",
            "stem": "这句话看着像结论，但阅卷最可能扣在哪里？",
            "answer": "check_items",
            "visual": {
                "items": ["对象:脚手架", "检查项目:没有写", "结论:可以使用"],
                "hotIndex": 1,
            },
            "options": [
                {
                    "id": "threshold",
                    "label": "只补高度、跨度、荷载数值，说明它是不是高大模板。",
                    "reason": "这是分档动作，但这句答案已经卡在验收项目没交代。",
                },
                {
                    "id": "check_items",
                    "label": "补“材料、支承固定、搭设质量、技术资料”验收合格。",
                    "reason": "把空泛合格变成可给分的验收四件套。",
                },
                {
                    "id": "responsibility",
                    "label": "补施工单位、监理单位各自责任，强调谁来负责。",
                    "reason": "责任主体不是这道题最直接的采分缺口。",
                },
                {
                    "id": "strong",
                    "label": "改成“搭设牢固，可以使用”，让结论更肯定。",
                    "reason": "牢固仍是口语结论，不能替代验收项目。",
                },
            ],
            "correct": "对。这句只写了“合格”，没写“验收验了哪些项目”。要补材料、支承固定、搭设质量、技术资料，阅卷才知道你的合格从哪里来。",
            "wrong": "这里不是让结论更漂亮，而是补证据。只写“合格/牢固/可以使用”都太薄，必须把验收四件套写出来。",
            "optionFeedback": {
                "threshold": "取数分档是第一道门，但这道题给的是一段学生答案。它的问题是“合格”没有证据，不是少一个数值。",
                "responsibility": "责任主体可能会考，但这句答案最直接的扣分点是没写验收项目。先补四件套，再谈谁签字。",
                "strong": "“搭设牢固”听起来更肯定，但仍然没有材料、支承固定、搭设质量、技术资料，阅卷还是没法给足分。",
            },
        },
        {
            "id": "q2",
            "stageLabel": "先定口径",
            "skill": "取数分档",
            "student": "题干给出:模板支架高度 8m、跨度 18m、施工总荷载 15kN/㎡。",
            "stem": "你下笔前，第一步应该先做什么？",
            "answer": "take_numbers",
            "visual": {
                "items": ["题干数据", "分档门", "后续验收"],
                "hotIndex": 1,
            },
            "options": [
                {
                    "id": "structure_first",
                    "label": "先检查扫地杆、剪刀撑、连墙件，判断现场稳不稳。",
                    "reason": "这是第二步；口径没定，检查对象容易跑偏。",
                },
                {
                    "id": "take_numbers",
                    "label": "先提取高度、跨度、荷载，判断进入哪一档风险口径。",
                    "reason": "先知道按普通、危大还是高大模板去验收。",
                },
                {
                    "id": "record_first",
                    "label": "先看验收表有没有签字，有签字就说明可以放行。",
                    "reason": "签字不是免检牌；前面分档和构造仍要成立。",
                },
                {
                    "id": "conclusion_first",
                    "label": "先写“验收合格后方可使用”，再补其他内容。",
                    "reason": "结论不能先行；先判题目走哪条验收口径。",
                },
            ],
            "correct": "对。第一笔不是背构造项，而是把 H、跨度、荷载拿出来分档。口径定错，后面构造和验收都会写散。",
            "wrong": "这题先别急着看构造或签字。题干给了高度、跨度、荷载，就是提醒你先取数分档，确定按哪一类风险口径作答。",
            "optionFeedback": {
                "structure_first": "你跳到第二步了。构造稳定要查，但先要知道这套支架属于什么风险档。",
                "record_first": "验收记录是证据，不是第一刀。没有分档，记录也不知道按什么标准验。",
                "conclusion_first": "“合格后方可使用”是最后一句，不是开头。先取数分档，再往下验收。",
            },
        },
        {
            "id": "q3",
            "stageLabel": "查稳定门",
            "skill": "构造稳定",
            "student": "已经确认是高风险模板支架。学生说:“有验收表，应该能用。”",
            "stem": "你最应该追问哪一类现场事实？",
            "answer": "stability",
            "visual": {
                "items": ["已分档", "构造是否稳", "验收证据"],
                "hotIndex": 1,
            },
            "options": [
                {
                    "id": "material",
                    "label": "材料品牌是否统一，外观看起来是否比较新。",
                    "reason": "材料要验，但外观新旧不能替代稳定构造。",
                },
                {
                    "id": "stability",
                    "label": "立杆支承、扫地杆、剪刀撑或拉结等稳定措施是否到位。",
                    "reason": "高风险支架能不能放行，核心看失稳风险有没有被控制。",
                },
                {
                    "id": "signature",
                    "label": "验收表有没有签字；只要签了字就不用再写构造。",
                    "reason": "签字是结果证据，不是构造本身。",
                },
                {
                    "id": "progress",
                    "label": "施工进度是否着急，是否需要尽快进入下一道工序。",
                    "reason": "进度不能压过安全放行条件。",
                },
            ],
            "correct": "对。高风险支架不是“有表就能用”，要说明立杆支承、扫地杆、剪刀撑或拉结等把失稳风险控制住了。",
            "wrong": "这里问的是能不能安全放行。签字、材料、进度都不能替代构造稳定；要把支承、连接、侧向约束这些稳定措施说清楚。",
            "optionFeedback": {
                "material": "材料是验收四件套之一，但这一步问现场为什么能稳住。要看支承、拉结和侧向约束，只看新旧不够。",
                "signature": "签字只能证明有人确认过，不能替你说明为什么稳。答案里仍要写构造稳定。",
                "progress": "进度再急也不能替代安全条件。这是安全放行题，不是赶工题。",
            },
        },
        {
            "id": "q4",
            "stageLabel": "补证据链",
            "skill": "验收四件套",
            "student": "现场看起来不晃。学生准备写:“构造稳定，可以使用。”",
            "stem": "这句话还缺哪一段，才能从“看着稳”变成“验收可放行”？",
            "answer": "acceptance_chain",
            "visual": {
                "items": ["构造稳定", "验收四件套", "放行结论"],
                "hotIndex": 1,
            },
            "options": [
                {
                    "id": "acceptance_chain",
                    "label": "补材料、支承固定、搭设质量、技术资料验收合格并形成记录。",
                    "reason": "把现场判断变成可追溯证据。",
                },
                {
                    "id": "height_again",
                    "label": "再把高度、跨度、荷载重复写一遍，越详细越好。",
                    "reason": "分档已经完成；重复数值不能替代验收证据。",
                },
                {
                    "id": "safe_phrase",
                    "label": "只补“符合安全要求”，避免答案写得太长。",
                    "reason": "安全要求太泛，仍然没有说明验收对象。",
                },
                {
                    "id": "use_now",
                    "label": "直接写“可以投入使用”，因为构造已经稳定。",
                    "reason": "放行结论必须建立在验收证据上。",
                },
            ],
            "correct": "对。构造稳定只是说明风险被控制，要靠验收四件套说明证据齐了：材料、支承固定、搭设质量、技术资料验收合格并有记录。",
            "wrong": "“看着稳”还不是验收放行。要把材料、支承固定、搭设质量、技术资料这些证据补上，否则答案仍然像现场口头判断。",
            "optionFeedback": {
                "height_again": "重复数值会显得认真，但不能补验收证据。现在缺的是四件套，不是更多数字。",
                "safe_phrase": "“符合安全要求”太空。阅卷需要看到你具体验了什么。",
                "use_now": "这正是常见丢分写法，因为结论冲太快，证据链没写出来。要先补验收四件套再放行。",
            },
        },
        {
            "id": "q5",
            "stageLabel": "落采分句",
            "skill": "采分句输出",
            "student": "现在要把前面三步压成答题纸上的一句话。",
            "stem": "下面哪句话最像能拿分的最终表达？",
            "answer": "score_sentence",
            "visual": {
                "items": ["对象", "四项验收", "方可使用"],
                "hotIndex": 2,
            },
            "options": [
                {
                    "id": "score_sentence",
                    "label": "脚手架或模板支架经材料、支承固定、搭设质量和技术资料验收合格后，方可使用。",
                    "reason": "对象、验收项目、放行条件都交代了。",
                },
                {
                    "id": "short_sentence",
                    "label": "脚手架验收合格后，可以使用。",
                    "reason": "有结论，但采分颗粒太少。",
                },
                {
                    "id": "structure_only",
                    "label": "支架搭设牢固、构造稳定后，可以直接使用。",
                    "reason": "有构造，但漏了验收证据和资料。",
                },
                {
                    "id": "approval_only",
                    "label": "经项目负责人同意后，脚手架即可投入使用。",
                    "reason": "同意不是验收四件套。",
                },
            ],
            "correct": "对。这句话把对象、四项验收和“合格后方可使用”都写出来了，才像答题纸上的采分句。",
            "wrong": "最终句不能只写“合格/牢固/同意”。能拿分的表达要有对象、四项验收和放行条件。",
            "optionFeedback": {
                "short_sentence": "这句话方向对，但太短。阅卷看不出验收了材料、支承固定、搭设质量和技术资料。",
                "structure_only": "构造稳定是中间依据，不是完整验收放行句。还要补材料和技术资料等证据。",
                "approval_only": "项目负责人同意不能替代验收四件套。考试要写验收合格后方可使用。",
            },
        },
    ]


def build_s02_questions() -> list[dict[str, Any]]:
    """S02 practice follows the Deep Pack: gates, thresholds, and failure fixes."""
    return [
        {
            "id": "q1",
            "stageLabel": "门槛分层",
            "skill": "危大两层门",
            "student": "学生答:“单件 12kN 已经算起重吊装危大，所以直接写专家论证。”",
            "stem": "这句话错在把哪两道门合并了？",
            "answer": "two_level_gate",
            "visual": {
                "kind": "s02_danger_gate",
                "lead": "单件 12kN",
                "before": ["第1道门", "第2道门"],
                "after": ["≥10kN:危大/专项方案", "100/300/200:论证另判"],
                "hotIndex": 0,
            },
            "options": [
                {
                    "id": "two_level_gate",
                    "label": "12kN 先判危大和专项方案；专家论证还要另看非常规且100kN、总重300kN或高度200m。",
                    "reason": "把“危大下限”和“超危大论证线”分开。",
                },
                {
                    "id": "expert_direct",
                    "label": "只要超过 10kN，就直接写专家论证，越保守越稳。",
                    "reason": "这是把两层门槛压成一层。",
                },
                {
                    "id": "safe_no_plan",
                    "label": "因为还没到100kN，所以不算危大，也不用专项方案。",
                    "reason": "把专家论证线误当成危大下限。",
                },
                {
                    "id": "accident_first",
                    "label": "先看现场有没有事故；没事故就只写加强管理。",
                    "reason": "安全题看规范门槛，不等事故发生才判断。",
                },
            ],
            "correct": "对。12kN 过的是 10kN 一般危大线，所以要写危大和专项方案；但专家论证是第二层门，还要另比非常规且100kN、总重300kN或高度200m。",
            "wrong": "这里不是越保守越好，也不是不到100kN就没事。阅卷看两层门是否分清：10kN 是危大下限，100/300/200 才是专家论证线。",
            "optionFeedback": {
                "expert_direct": "这正是高频错法。因为 10kN 只让它进入危大和专项方案，不等于自动专家论证。",
                "safe_no_plan": "不到专家论证线，不代表不属于危大。12kN 已经过了10kN危大线，专项方案不能漏。",
                "accident_first": "事故有没有发生不是判断依据。题干给了规范数值，就要按红线判，不是按结果判。",
            },
        },
        {
            "id": "q2",
            "stageLabel": "看题干动词",
            "skill": "风线口径",
            "student": "题干A:露天塔机作业遇6级风。题干B:大型起重机械安拆，最高处风速9.5m/s。",
            "stem": "两题都问是否应停止，第一笔最稳抓什么？",
            "answer": "verb_threshold",
            "visual": {
                "kind": "s02_wind_gate",
                "before": ["露天作业", "安装/拆卸"],
                "after": ["6级及以上停", ">9.0m/s或低能见度停"],
                "hotIndex": 0,
            },
            "options": [
                {
                    "id": "verb_threshold",
                    "label": "先看动作动词：露天塔机作业看6级及以上，安装拆卸看>9.0m/s和低能见度。",
                    "reason": "动作不同，调用的红线不同。",
                },
                {
                    "id": "one_wind_rule",
                    "label": "统一写6级风停工，所有起重场景都按一条线处理。",
                    "reason": "简单但会把安拆场景套错。",
                },
                {
                    "id": "weather_feel",
                    "label": "先看现场经验，风不算特别大就可以继续干。",
                    "reason": "安全题不能用感觉替代规范阈值。",
                },
                {
                    "id": "speed_only",
                    "label": "只要题里出现m/s，就不再考虑风级和作业类别。",
                    "reason": "单位不能替代场景动词。",
                },
            ],
            "correct": "对。先抓题干动词。露天吊装作业是 6 级及以上停；安装拆卸是 >9.0m/s 或低能见度停，两个阈值不能互换。",
            "wrong": "这里不是背一条“风大停工”。要先看动作，因为露天吊装和安拆调用不同阈值，套错动词就会扣分。",
            "optionFeedback": {
                "one_wind_rule": "这会漏掉安拆口径。因为安拆更危险，题干写安拆时要看 >9.0m/s 和低能见度。",
                "weather_feel": "阅卷不看现场感觉。因为题目给的是规范红线，必须按风级或风速判断。",
                "speed_only": "看见单位只是线索，不是判断本体。先抓“露天作业”还是“安拆”，再调用对应阈值。",
            },
        },
        {
            "id": "q3",
            "stageLabel": "试吊先动作",
            "skill": "90%试吊",
            "student": "题干给出起吊达到额定 95%。学生写:“安排专人盯着，缓慢正式起吊。”",
            "stem": "这句话漏掉的固定动作链是什么？",
            "answer": "trial_lift_check",
            "visual": {
                "kind": "s02_trial_lift",
                "load": "95%额定",
                "before": ["吊物", "地面", "检查点"],
                "after": ["离地200～500mm", "机械/制动/平稳/绑扎"],
                "hotIndex": 1,
            },
            "options": [
                {
                    "id": "trial_lift_check",
                    "label": "先吊离地 200～500mm，再查机械状况、制动性能、重物平稳和绑扎牢固。",
                    "reason": "90% 以上不是态度题，是固定前置动作加四查。",
                },
                {
                    "id": "slow_lift",
                    "label": "写缓慢起吊并加强旁站，说明管理人员重视安全。",
                    "reason": "旁站不能替代离地试吊和四项检查。",
                },
                {
                    "id": "expert_meeting",
                    "label": "先组织专家论证，论证通过后再继续正式起吊。",
                    "reason": "这题触发的是试吊检查，不是论证判断。",
                },
                {
                    "id": "finish_first",
                    "label": "先完成吊装，吊装结束后再集中检查机械和绑扎。",
                    "reason": "顺序倒了；检查必须发生在正式起吊前。",
                },
            ],
            "correct": "对。95% 已经触发 90% 及以上的前置动作：先吊离地 200～500mm，再查机械、制动、平稳和绑扎，合格后才正式起吊。",
            "wrong": "不是写“慢一点、盯紧点”就能拿分。因为 90% 以上有固定动作和四查清单，顺序错就扣分。",
            "optionFeedback": {
                "slow_lift": "加强旁站听起来安全，但阅卷要的是先离地试吊和四项检查。态度词不能替代动作词。",
                "expert_meeting": "专家论证属于危大层级判断。这里题眼是 95% 额定起吊，必须先写试吊检查。",
                "finish_first": "检查不能放到吊装结束后。题干触发的是正式起吊前的离地试吊和四查。",
            },
        },
        {
            "id": "q4",
            "stageLabel": "绝对禁令",
            "skill": "限位不替代",
            "student": "现场操作机构失灵。学生答:“可暂时用限位装置代替操作，先把吊装完成。”",
            "stem": "这类判断题应该怎么改，才像安全题答案？",
            "answer": "limit_never_replace",
            "visual": {
                "kind": "s02_limit_gate",
                "before": ["操作机构失灵", "限位装置顶替"],
                "after": ["停止使用", "排除故障", "复查后作业"],
                "hotIndex": 0,
            },
            "options": [
                {
                    "id": "limit_never_replace",
                    "label": "判不妥；限位装置严禁代替操作机构，应停止使用，排除故障后再作业。",
                    "reason": "抓住“代替/顶替”这个绝对禁令词。",
                },
                {
                    "id": "temporary_replace",
                    "label": "可以临时代替，但要降低速度并安排专人监护。",
                    "reason": "把禁令误写成管理加强。",
                },
                {
                    "id": "check_after",
                    "label": "可以先完成吊装，吊装结束后再检查限位装置。",
                    "reason": "故障设备不能先用后查。",
                },
                {
                    "id": "only_record",
                    "label": "把这个情况记录在安全日志里，不影响本次吊装。",
                    "reason": "记录不能替代停用排故。",
                },
            ],
            "correct": "对。出现“用限位代替操作机构”就是不妥。要写停止使用、排除故障、保护装置完整灵敏后再作业。",
            "wrong": "这不是加强管理能化解的风险。因为规范是绝对禁令，限位装置不能代替操作机构，必须停用修复。",
            "optionFeedback": {
                "temporary_replace": "这会把禁令改成可管理风险。因为“代替操作机构”本身就不允许，不能靠慢速和监护补救。",
                "check_after": "先用后查顺序错了。因为故障已经出现，必须先停用排故，再恢复作业。",
                "only_record": "安全日志是记录，不是控制措施。故障已经影响操作，必须停用和排故。",
            },
        },
        {
            "id": "q5",
            "stageLabel": "落采分句",
            "skill": "安全采分链",
            "student": "题干同时出现:单件12kN、露天6级风、95%额定起吊。",
            "stem": "如果要求“指出不妥并改正”，哪句话最像完整采分闭环？",
            "answer": "score_chain",
            "visual": {
                "kind": "s02_answer_scan",
                "before": ["门槛", "条件", "试吊", "放行"],
                "after": ["危大/专项方案", "6级风停作业", "离地四查", "合格后起吊"],
                "hotIndex": 3,
            },
            "options": [
                {
                    "id": "score_chain",
                    "label": "单件12kN属危大应编专项方案；露天6级风应停止作业；95%额定应先离地200～500mm四查，合格后方可起吊。",
                    "reason": "把对象、条件、程序和放行结论连成采分链。",
                },
                {
                    "id": "safe_general",
                    "label": "起重吊装应加强安全管理，相关人员认真检查后可以施工。",
                    "reason": "太泛，缺门槛、阈值和具体动作。",
                },
                {
                    "id": "only_expert",
                    "label": "凡是起重吊装工程，都应组织专家论证后再起吊。",
                    "reason": "把危大和专家论证混成一层。",
                },
                {
                    "id": "trial_only",
                    "label": "95%额定时先试吊检查，其他内容可不写。",
                    "reason": "只命中一个点，漏掉危大门槛和6级风停作业。",
                },
            ],
            "correct": "对。最终采分句要把三道闸串起来：先判门槛，再查作业条件，90% 以上先离地四查，合格后才正式起吊。",
            "wrong": "最终句不能只写安全管理或专家论证。要把门槛、气象/基础/索具/吊点、试吊检查和放行条件写成一条采分链。",
            "optionFeedback": {
                "safe_general": "这句话像口号。因为没有写 10kN/论证门槛、风线、试吊四查等采分动作，容易不给分。",
                "only_expert": "专家论证不是所有起重吊装都要。因为要先分危大和超危大两层，不能一刀切。",
                "trial_only": "90%试吊很关键，但这道题还给了12kN和6级风。漏一个题干事实，就漏一个采分点。",
            },
        },
    ]


def build_questions(points: list[str], title: str, ir: dict[str, Any]) -> list[dict[str, Any]]:
    blueprint = ir.get("practice_blueprint")
    if isinstance(blueprint, list) and blueprint:
        return normalize_blueprint_questions(blueprint)
    card_id = str(ir.get("card_id") or "")
    if card_id.endswith("S01") or "脚手架/高大模板支架验收" in title:
        return build_s01_questions()
    if card_id.endswith("S02") or "起重吊装安全" in title:
        return build_s02_questions()
    opts = [
        {"id": f"k{i}", "label": f"把“{label}”写成具体判断动作", "reason": "不是背词，要能转成采分表达。"}
        for i, label in enumerate(points)
    ]
    return [
        {
            "id": "q1",
            "focusIndex": min(2, len(points) - 1),
            "student": "学生答:“验收合格，可以使用。”",
            "stem": "这份答案最可能漏掉哪一段采分动作？",
            "answer": opts[min(2, len(opts) - 1)]["id"],
            "options": opts,
            "correct": f"对，先别只写结论，要把「{points[min(2, len(points)-1)]}」补出来，阅卷人才知道你验收了什么。",
            "wrong": f"先别急。这题不是找一句好听结论，而是看答案有没有交代「{points[min(2, len(points)-1)]}」。",
        },
        {
            "id": "q2",
            "focusIndex": 0,
            "student": f"题干出现「{title}」，你准备先下笔。",
            "stem": "第一笔最稳应该先抓什么？",
            "answer": opts[0]["id"],
            "options": opts,
            "correct": f"对，先抓「{points[0]}」。对象和口径错了，后面的依据会跟着散。",
            "wrong": f"这一步先抓「{points[0]}」。不要一上来背散点，先把题目归到正确口径。",
        },
        {
            "id": "q3",
            "focusIndex": 1,
            "student": "题干问搭设或放行前有没有安全隐患。",
            "stem": "这时最该用哪一段去解释“为什么能/不能放行”？",
            "answer": opts[1]["id"],
            "options": opts,
            "correct": f"对，用「{points[1]}」解释风险有没有被控制住。",
            "wrong": f"这里要回到「{points[1]}」。判断安全题，不能只给结论，要给控制风险的依据。",
        },
        {
            "id": "q4",
            "focusIndex": 3,
            "student": "你已经判断完对象、条件和依据，准备写最后一句。",
            "stem": "最后落到答题纸上，应该交付什么？",
            "answer": opts[3]["id"],
            "options": opts,
            "correct": f"对，最后必须落成「{points[3]}」，这才是阅卷能直接给分的句子。",
            "wrong": f"最后要交付「{points[3]}」。中间推理再清楚，不落成采分句也容易丢分。",
        },
        {
            "id": "q5",
            "focusIndex": 2,
            "student": "学生把依据写得很散：材料、构造、资料各写一点。",
            "stem": "你要提醒他把散点收成哪一类检查？",
            "answer": opts[2]["id"],
            "options": opts,
            "correct": f"对，把散点收进「{points[2]}」，答案就从背条文变成采分链。",
            "wrong": f"这里要收进「{points[2]}」。散点不是越多越好，关键是服务于采分链。",
        },
    ]


def render_html(ir: dict[str, Any]) -> str:
    card_id = ir.get("card_id") or Path(ir.get("source_refs", {}).get("ir", "card")).stem
    title = (ir.get("display") or {}).get("title") or ir.get("title") or card_id
    points = key_points(ir)
    data = {
        "cardId": card_id,
        "title": title,
        "kicker": (ir.get("display") or {}).get("kicker") or "鲁班深母题 · 独立闯关",
        "previewHref": (ir.get("render_contract") or {}).get("html_preview") or f"{card_id}.animation_ir_preview.html",
        "aiContext": ir.get("ai_context") or {},
        "mainExamAction": ir.get("main_exam_action") or "",
        "keyPoints": points,
        "questions": build_questions(points, str(title), ir),
    }
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><link rel="icon" href="data:,"><title>{esc(title)} · 闯关</title>
<style>
*{{box-sizing:border-box}}html,body{{margin:0;max-width:100%;overflow-x:hidden}}body{{background:#eef5fb;color:#132033;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}}button{{font:inherit}}.practice{{max-width:430px;margin:0 auto;min-height:100dvh;padding:10px 10px calc(24px + env(safe-area-inset-bottom))}}header{{display:grid;grid-template-columns:auto minmax(0,1fr);gap:10px;align-items:center;margin-bottom:10px}}header a{{min-height:42px;display:flex;align-items:center;border:1px solid #c9d9e8;border-radius:999px;background:#fff;color:#176b7a;text-decoration:none;font-size:12px;font-weight:900;padding:0 12px;white-space:nowrap}}header span{{font-size:11px;color:#176b7a;font-weight:900}}h1{{margin:2px 0 0;font-size:19px;line-height:1.18;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.progress{{height:6px;border-radius:99px;background:#d8e5f0;overflow:hidden;margin:10px 0 12px}}.progress i{{display:block;width:0;height:100%;background:#ff7a1a;transition:width .2s ease}}.card{{background:#fff;border:1px solid #cdddeb;border-radius:20px;padding:13px;box-shadow:0 16px 40px rgba(30,58,87,.12)}}.qtop{{display:flex;justify-content:space-between;gap:10px;color:#176b7a;font-size:12px;font-weight:900}}.qtop em{{font-style:normal;color:#60758c;text-align:right;max-width:58%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.diagram{{margin:10px 0 12px;background:#fffdf7;border:2px solid #eadfcb;border-radius:18px;padding:13px;overflow:hidden}}.flow{{display:grid;grid-template-columns:1fr;gap:8px}}.practiceVisual{{width:100%;height:auto;display:block;max-height:260px}}.practiceVisual text{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}}.dot{{min-height:46px;border:2px solid #c9d9e8;border-radius:14px;display:flex;align-items:center;justify-content:center;text-align:center;font-size:14px;font-weight:900;line-height:1.25;padding:8px 10px;background:#f8fafc;color:#24364b}}.dot.hot{{border-color:#ff7a1a;background:#fff7ed;color:#b45309;box-shadow:0 0 0 3px rgba(249,115,22,.1)}}.student{{border-left:4px solid #f97316;background:#fff7ed;border-radius:13px;padding:9px 10px;margin-bottom:10px}}.student b{{display:block;color:#176b7a;font-size:12px}}.student p{{margin:4px 0 0;font-size:15px;line-height:1.45;font-weight:900}}.stem{{font-size:18px;line-height:1.38;font-weight:900;margin:0 0 12px}}.options{{display:grid;gap:9px}}.option{{width:100%;min-height:56px;text-align:left;border:1px solid #d6e2ed;border-radius:15px;background:#fff;padding:10px 12px;color:#172437;display:grid;grid-template-columns:30px minmax(0,1fr);gap:8px;align-items:center}}.option b{{width:30px;height:30px;border-radius:999px;background:#eef4f8;color:#176b7a;display:grid;place-items:center;font-size:14px}}.option span{{font-size:15px;line-height:1.32;font-weight:900;overflow-wrap:anywhere}}.option small{{display:block;color:#60758c;font-size:12px;line-height:1.3;margin-top:3px;font-weight:800}}.option.correct{{border-color:#73c596;background:#ecf9f2}}.option.correct b{{background:#16a34a;color:#fff}}.option.wrong{{border-color:#fb923c;background:#fff3e9}}.option.wrong b{{background:#f97316;color:#fff}}.option:disabled{{opacity:1}}.feedback{{display:none;margin-top:10px;border-radius:14px;padding:11px 12px;font-size:14px;font-weight:850;line-height:1.55}}.feedback.show.correct{{display:block;background:#ecf9f2;border:1px solid #73c596;color:#0f6b4f}}.feedback.show.wrong{{display:block;background:#fff3e9;border:1px solid #fb923c;color:#9a3412}}.feedback.show.wait{{display:block;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412}}.done{{display:none;background:#fff;border:1px solid #d2dee9;border-radius:20px;padding:16px;box-shadow:0 14px 32px rgba(31,41,55,.08)}}.done.show{{display:block}}.done h2{{font-size:24px;margin:0 0 10px;text-align:center;color:#176b7a}}.scoreBox{{border:1px solid #cfe0ee;background:#f8fbfe;border-radius:16px;padding:12px;margin-bottom:12px}}.scoreBox p{{margin:0;color:#1d2f44;font-size:15px;line-height:1.5;font-weight:900}}.scoreBadge{{display:inline-flex;align-items:center;min-height:30px;border-radius:999px;background:#fff7ed;color:#b45309;border:1px solid #fed7aa;padding:4px 10px;margin-top:8px;font-size:12px;font-weight:900}}.resultBlock{{margin-top:12px}}.resultBlock h3{{margin:0 0 8px;color:#176b7a;font-size:15px;line-height:1.3}}.analysisGrid{{display:grid;gap:8px}}.insight{{border-left:4px solid #176b7a;background:#f7fafc;border-radius:12px;padding:9px 10px}}.insight.warn{{border-left-color:#f97316;background:#fff7ed}}.insight b{{display:block;font-size:12px;color:#60758c;margin-bottom:3px}}.insight p{{margin:0;font-size:14px;line-height:1.45;font-weight:900;color:#223248}}.reviewList{{display:grid;gap:7px}}.reviewItem{{border:1px solid #d8e4ef;border-radius:12px;padding:9px 10px;background:#fff}}.reviewItem.good{{background:#f0fdf4;border-color:#bbf7d0}}.reviewItem.miss{{background:#fff7ed;border-color:#fed7aa}}.reviewItem b{{display:block;font-size:13px;line-height:1.35;color:#1d2f44}}.reviewItem small{{display:block;margin-top:4px;color:#60758c;font-size:12px;line-height:1.4;font-weight:800}}.resultActions{{display:grid;gap:9px;margin:14px 0}}.resultActions button,.done a{{min-height:46px;border-radius:14px;font-weight:900;text-decoration:none}}.resultActions button{{border:1px solid #cdddeb;background:#fff;color:#24364b}}.resultActions .ask{{background:#176b7a;color:#fff;border-color:#176b7a}}.resultActions .drill{{background:#ff7a1a;color:#fff;border-color:#ff7a1a}}.done a{{display:flex;align-items:center;justify-content:center;background:#fff;color:#176b7a;border:1px solid #c9d9e8}}.aiPanel{{display:none;border:1px solid #d6e2ed;border-radius:16px;background:#0f1e2d;color:#eaf2fb;padding:12px;margin-top:10px}}.aiPanel.show{{display:block}}.aiStatus{{margin:0 0 8px;color:#fed27a;font-size:12px;font-weight:900}}.aiResult{{font-size:14px;line-height:1.55;font-weight:850}}.aiResult p{{margin:0 0 8px}}.aiResult ul{{margin:6px 0 0;padding-left:18px}}.atoms{{display:grid;gap:7px;margin:12px 0}}.atoms span{{border-left:3px solid #176b7a;background:#f7fafc;border-radius:10px;padding:8px 10px;font-size:13px;font-weight:900;color:#34465b}}nav{{position:sticky;bottom:0;width:min(430px,calc(100% - 20px));margin:12px auto 0;display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:10px 12px calc(10px + env(safe-area-inset-bottom));background:rgba(255,255,255,.97);border:1px solid #d2dee9;border-bottom:0;border-radius:18px 18px 0 0;box-shadow:0 -10px 28px rgba(31,41,55,.12)}}nav button{{min-height:48px;border-radius:14px;border:1px solid #cfdae6;background:#fff;color:#24364b;font-weight:900}}nav button.primary{{background:#176b7a;color:#fff;border-color:#176b7a}}nav button:disabled{{background:#eef4f8;color:#7b8da1;border-color:#cfdae6}}nav button.blocked{{border-color:#fb923c;background:#fff7ed;color:#9a3412}}@media(orientation:landscape){{.practice{{max-width:920px;padding-bottom:24px}}.card{{display:grid;grid-template-columns:minmax(280px,1fr) minmax(340px,.85fr);gap:14px;align-items:start}}.qtop{{grid-column:1/-1}}.diagram{{margin:0}}.flow{{grid-template-columns:1fr 1fr}}.flow:has(.practiceVisual){{grid-template-columns:1fr}}.student,.stem,.options,.feedback{{grid-column:2}}.done{{max-width:760px;margin:0 auto}}.analysisGrid{{grid-template-columns:1fr 1fr}}.resultActions{{grid-template-columns:1fr 1fr 1fr}}nav{{width:min(720px,calc(100% - 20px));grid-template-columns:180px 1fr}}}}
</style></head><body><main class="practice" data-practice-shell="animation-ir-practice"><header><a id="backLink" href="{esc(data['previewHref'])}">返回讲解</a><div><span>{esc(data['kicker'])}</span><h1>{esc(title)}</h1></div></header><div class="progress" aria-hidden="true"><i id="progressBar"></i></div><section class="card" id="quizCard"><div class="qtop"><span id="qCount"></span><em id="qFocus"></em></div><div class="diagram"><div class="flow" id="flow"></div></div><div class="student"><b>学生答</b><p id="studentAnswer"></p></div><p class="stem" id="stem"></p><div class="options" id="options"></div><div class="feedback" id="practiceFeedback" role="status"></div></section><section class="done" id="done"><h2>闯关完成</h2><div class="scoreBox"><p id="scoreText"></p><span class="scoreBadge" id="levelBadge"></span></div><div class="resultBlock"><h3>表现分析</h3><div class="analysisGrid" id="insights"></div></div><div class="resultBlock"><h3>逐题复盘</h3><div class="reviewList" id="reviewList"></div></div><div class="resultActions"><button class="ask" id="aiCoachBtn" type="button" data-answer-action="ask-luban-followup">带着疑问问鲁班</button><button class="drill" id="drillBtn" type="button" data-answer-action="drill-weak-points">继续补练薄弱点</button><a href="{esc(data['previewHref'])}">回看白板讲解</a></div><div class="aiPanel" id="aiPanel"><p class="aiStatus" id="aiStatus"></p><div class="aiResult" id="aiResult"></div></div><div class="atoms" id="atoms"></div></section></main><nav><button id="prevBtn" type="button">上一题</button><button id="primaryBtn" class="primary" type="button" data-answer-action="submit-or-next">先作答</button></nav><script type="application/json" id="practiceData">{js_json(data)}</script><script>
const DATA=JSON.parse(document.getElementById('practiceData').textContent);
const $=id=>document.getElementById(id);
const els={{card:$('quizCard'),done:$('done'),progress:$('progressBar'),qCount:$('qCount'),qFocus:$('qFocus'),flow:$('flow'),student:$('studentAnswer'),stem:$('stem'),options:$('options'),feedback:$('practiceFeedback'),prev:$('prevBtn'),primary:$('primaryBtn'),score:$('scoreText'),level:$('levelBadge'),insights:$('insights'),review:$('reviewList'),aiCoach:$('aiCoachBtn'),drill:$('drillBtn'),aiPanel:$('aiPanel'),aiStatus:$('aiStatus'),aiResult:$('aiResult'),atoms:$('atoms')}};
let index=0;
const answers=new Array(DATA.questions.length).fill(null);
function safe(s){{return String(s??'').replace(/[&<>"']/g,ch=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));}}
function current(){{return DATA.questions[index];}}
function answered(){{return answers[index];}}
function setFeedback(kind,text){{els.feedback.className='feedback show '+kind;els.feedback.textContent=text;}}
function clearFeedback(){{els.feedback.className='feedback';els.feedback.textContent='';}}
function renderDots(items,hotIndex){{return (items||[]).map((p,i)=>`<div class="dot ${{i===hotIndex?'hot':''}}">${{safe(p)}}</div>`).join('');}}
function svgChip(text,x,y,w,fill='#f8fafc',stroke='#cbd5e1',color='#24364b',size=14){{return `<rect x="${{x}}" y="${{y}}" width="${{w}}" height="42" rx="13" fill="${{fill}}" stroke="${{stroke}}" stroke-width="2.5"/><text x="${{x+w/2}}" y="${{y+27}}" text-anchor="middle" font-size="${{size}}" font-weight="900" fill="${{color}}">${{safe(text)}}</text>`;}}
function renderVisual(q,a){{const visual=q.visual||{{}};const v=visual;const answered=!!a;const before=Array.isArray(v.before)?v.before:[];const after=Array.isArray(v.after)?v.after:before;const labels=answered?after:before;const hotIndex = a ? Number(visual.hotIndex) : -1;const hot=hotIndex;
  if(v.kind==='answer_scan'){{const rows=[0,1,2,3];return `<svg class="practiceVisual" viewBox="0 0 360 238" role="img" aria-label="${{safe(v.title||'答题纸扫描图')}}"><rect x="28" y="20" width="304" height="198" rx="18" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><text x="56" y="52" font-size="15" font-weight="900" fill="#176b7a">${{safe(v.title||'答题纸扫描')}}</text><path d="M310 60 V184" stroke="${{answered?'#ff7a1a':'#94a3b8'}}" stroke-width="5" stroke-linecap="round" stroke-dasharray="${{answered?'0':'10 7'}}"/><circle cx="310" cy="${{answered?80+(Math.max(0,hot))*32:66}}" r="${{answered?8:5}}" fill="${{answered?'#ff7a1a':'#94a3b8'}}"/><text x="302" y="55" text-anchor="end" font-size="11" font-weight="900" fill="${{answered?'#9a3412':'#64748b'}}">${{answered?'扫描命中':'答前不泄题'}}</text>${{rows.map(i=>`<rect x="52" y="${{70+i*32}}" width="236" height="24" rx="8" fill="${{answered?(i===hot?'#fff7ed':'#ecfdf5'):'#f8fafc'}}" stroke="${{answered?(i===hot?'#f97316':'#10b981'):'#cbd5e1'}}" stroke-width="2"/><text x="64" y="${{87+i*32}}" font-size="12" font-weight="900" fill="${{answered?(i===hot?'#9a3412':'#047857'):'#334155'}}">${{safe((answered?after:before)[i]||'')}}</text>`).join('')}}<text x="180" y="206" text-anchor="middle" font-size="12" font-weight="900" fill="${{answered?'#9a3412':'#64748b'}}">${{answered?'把漏格补成采分动作':'先选动作，再揭示补写格'}}</text></svg>`;}}
  if(v.kind==='process_flow'&&v.mode==='hidden_sample_objects'){{return `<svg class="practiceVisual" viewBox="0 0 360 238" role="img" aria-label="${{safe(v.title||'材料样品隐蔽验收对象图')}}"><rect x="16" y="18" width="328" height="202" rx="20" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><text x="180" y="48" text-anchor="middle" font-size="16" font-weight="900" fill="#176b7a">${{safe(v.title||'材料样品过闸')}}</text><path d="M48 139 H312" stroke="${{answered?'#10b981':'#cbd5e1'}}" stroke-width="7" stroke-linecap="round"/><path d="M300 130 L316 139 L300 148" stroke="${{answered?'#10b981':'#94a3b8'}}" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/><rect x="34" y="76" width="42" height="56" rx="7" fill="#eff6ff" stroke="${{answered?'#60a5fa':'#cbd5e1'}}" stroke-width="4"/><path d="M46 98 H66 M46 112 H62" stroke="${{answered?'#2563eb':'#94a3b8'}}" stroke-width="4" stroke-linecap="round"/><circle cx="67" cy="122" r="8" fill="${{answered?'#93c5fd':'#e2e8f0'}}" stroke="${{answered?'#1d4ed8':'#94a3b8'}}" stroke-width="3"/><text x="55" y="158" text-anchor="middle" font-size="10" font-weight="900" fill="${{answered?'#1d4ed8':'#334155'}}">${{safe(labels[0]||'合格证')}}</text><rect x="92" y="103" width="58" height="28" rx="10" fill="#ecfdf5" stroke="${{answered?'#10b981':'#cbd5e1'}}" stroke-width="4"/><rect x="103" y="80" width="16" height="24" rx="4" fill="#d9b88f" stroke="#8b7355" stroke-width="3"/><circle cx="132" cy="92" r="13" fill="#d1fae5" stroke="${{answered?'#047857':'#94a3b8'}}" stroke-width="3"/><text x="121" y="158" text-anchor="middle" font-size="10" font-weight="900" fill="${{answered?'#047857':'#334155'}}">${{safe(labels[1]||'材料样品')}}</text><path d="M167 134 V73 M215 134 V73" stroke="${{answered?'#f59e0b':'#cbd5e1'}}" stroke-width="7" stroke-linecap="round"/><rect x="174" y="88" width="34" height="40" rx="8" fill="#fff7ed" stroke="${{answered?'#f97316':'#cbd5e1'}}" stroke-width="4"/><circle cx="181" cy="101" r="4" fill="${{answered?'#10b981':'#94a3b8'}}"/><circle cx="181" cy="115" r="4" fill="${{answered?'#10b981':'#94a3b8'}}"/><path d="M188 101 H201 M188 115 H198" stroke="${{answered?'#f97316':'#94a3b8'}}" stroke-width="4" stroke-linecap="round"/><text x="191" y="158" text-anchor="middle" font-size="10" font-weight="900" fill="${{answered?'#9a3412':'#334155'}}">${{safe(labels[2]||'复验闸')}}</text><rect x="226" y="78" width="46" height="54" rx="11" fill="#fff7ed" stroke="${{answered?'#f97316':'#cbd5e1'}}" stroke-width="4"/><circle cx="249" cy="96" r="10" fill="#fed7aa" stroke="${{answered?'#f97316':'#94a3b8'}}" stroke-width="3"/><path d="M238 118 H260 M233 129 H266" stroke="${{answered?'#9a3412':'#94a3b8'}}" stroke-width="5" stroke-linecap="round"/><text x="249" y="158" text-anchor="middle" font-size="10" font-weight="900" fill="${{answered?'#9a3412':'#334155'}}">${{safe(labels[3]||'见证章')}}</text><rect x="286" y="84" width="48" height="62" rx="10" fill="#f8fafc" stroke="${{answered?'#94a3b8':'#cbd5e1'}}" stroke-width="4"/><rect x="293" y="95" width="34" height="9" rx="3" fill="#cbd5e1"/><rect x="293" y="108" width="34" height="9" rx="3" fill="#a7f3d0"/><rect x="293" y="121" width="34" height="9" rx="3" fill="#fde68a"/><path d="M286 72 H334" stroke="${{answered?'#10b981':'#ef4444'}}" stroke-width="5" stroke-linecap="round" stroke-dasharray="${{answered?'0':'8 7'}}"/><text x="310" y="158" text-anchor="middle" font-size="10" font-weight="900" fill="${{answered?'#047857':'#334155'}}">${{safe(labels[4]||'隐蔽剖面')}}</text><text x="180" y="206" text-anchor="middle" font-size="12" font-weight="900" fill="${{answered?'#047857':'#64748b'}}">${{answered?'复验、见证、覆盖前验收依次亮起':'答前只看现场对象，不提前给答案'}}</text></svg>`;}}
  if(v.kind==='process_flow'){{const cols=[46,142,238];return `<svg class="practiceVisual" viewBox="0 0 360 238" role="img" aria-label="${{safe(v.title||'流程对象纠正图')}}"><rect x="16" y="18" width="328" height="202" rx="20" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><text x="180" y="48" text-anchor="middle" font-size="16" font-weight="900" fill="#176b7a">${{safe(v.title||'角色箭头纠正')}}</text><path d="M90 112 H270" stroke="${{answered?'#10b981':'#cbd5e1'}}" stroke-width="7" stroke-linecap="round"/><path d="M259 102 L276 112 L259 122" stroke="${{answered?'#10b981':'#94a3b8'}}" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/><path d="M90 150 H270" stroke="${{answered?'#f97316':'#ef4444'}}" stroke-width="5" stroke-linecap="round" stroke-dasharray="8 7" opacity="${{answered?'.35':'.75'}}"/><text x="180" y="78" text-anchor="middle" font-size="12" font-weight="900" fill="${{answered?'#047857':'#64748b'}}">${{answered?'正确角色链亮起':'答前只看题干错位'}}</text>${{[0,1,2].map(i=>svgChip((answered?after:before)[i]||['对象A','对象B','对象C'][i],cols[i],92,78,answered?(i===hot?'#fff7ed':'#ecfdf5'):'#f8fafc',answered?(i===hot?'#f97316':'#10b981'):'#cbd5e1',answered?(i===hot?'#9a3412':'#047857'):'#24364b',11)).join('')}}<text x="180" y="190" text-anchor="middle" font-size="12" font-weight="900" fill="${{answered?'#9a3412':'#64748b'}}">${{answered?'错误箭头退出，保留组织/实施/见证链':'先判断谁组织，谁实施，谁见证'}}</text></svg>`;}}
  if(v.kind==='formula_chain'){{return `<svg class="practiceVisual" viewBox="0 0 360 238" role="img" aria-label="${{safe(v.title||'公式链图')}}"><rect x="16" y="18" width="328" height="202" rx="20" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><text x="180" y="48" text-anchor="middle" font-size="16" font-weight="900" fill="#176b7a">${{safe(v.title||'数值进入判据')}}</text><path d="M56 110 H304" stroke="${{answered?'#10b981':'#cbd5e1'}}" stroke-width="7" stroke-linecap="round"/><path d="M292 100 L308 110 L292 120" stroke="${{answered?'#10b981':'#94a3b8'}}" stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>{{c0}}{{c1}}{{c2}}{{c3}}<text x="180" y="174" text-anchor="middle" font-size="13" font-weight="900" fill="${{answered?'#9a3412':'#64748b'}}">${{answered?'先亮双阈值，再代入回判':'答前不要提前给出判定链'}}</text><text x="180" y="196" text-anchor="middle" font-size="12" font-weight="900" fill="${{answered?'#047857':'#64748b'}}">${{answered?'不能直接拿平均值比设计值':'选完后揭示公式、代入、回判'}}</text></svg>`.replace('{{c0}}',svgChip(labels[0]||'数值1',34,82,76,answered?'#ecfdf5':'#f8fafc',answered?'#10b981':'#cbd5e1',answered?'#047857':'#24364b',11)).replace('{{c1}}',svgChip(labels[1]||'判据1',112,82,92,answered?'#fff7ed':'#f8fafc',answered?'#f97316':'#cbd5e1',answered?'#9a3412':'#24364b',10)).replace('{{c2}}',svgChip(labels[2]||'数值2',210,82,62,answered?'#ecfdf5':'#f8fafc',answered?'#10b981':'#cbd5e1',answered?'#047857':'#24364b',11)).replace('{{c3}}',svgChip(labels[3]||'判据2',276,82,56,answered?'#fff7ed':'#f8fafc',answered?'#f97316':'#cbd5e1',answered?'#9a3412':'#24364b',10));}}
  if(v.kind==='s02_danger_gate'){{return `<svg class="practiceVisual" viewBox="0 0 360 238" role="img" aria-label="危大两层门判断图"><rect x="16" y="18" width="328" height="202" rx="20" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><text x="180" y="48" text-anchor="middle" font-size="17" font-weight="900" fill="#176b7a">${{safe(v.lead||'题干重量')}}</text><path d="M180 64 V91" stroke="#94a3b8" stroke-width="4"/><path d="M82 112 H278" stroke="#cbd5e1" stroke-width="8" stroke-linecap="round"/>${{svgChip(labels[0]||'第1道门',42,92,128,answered?'#ecfdf5':'#f8fafc',answered?'#10b981':'#cbd5e1',answered?'#047857':'#24364b',answered?11:14)}}${{svgChip(labels[1]||'第2道门',190,92,128,answered?'#fff7ed':'#f8fafc',answered?'#f97316':'#cbd5e1',answered?'#9a3412':'#24364b',answered?11:14)}}<text x="180" y="174" text-anchor="middle" font-size="14" font-weight="900" fill="${{answered?'#9a3412':'#64748b'}}">${{answered?'先过危大门，不自动过论证门':'先判断两道门，不要直接跳结论'}}</text><circle cx="${{hot===0?106:254}}" cy="113" r="${{answered?8:0}}" fill="#ff7a1a"/></svg>`;}}
  if(v.kind==='s02_wind_gate'){{return `<svg class="practiceVisual" viewBox="0 0 360 238" role="img" aria-label="风线分场景图"><rect x="16" y="18" width="328" height="202" rx="20" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><text x="180" y="50" text-anchor="middle" font-size="17" font-weight="900" fill="#176b7a">先看题干动词</text><path d="M180 64 V86 M104 86 H256" stroke="#94a3b8" stroke-width="4" fill="none"/>{{left}} {{right}}<text x="180" y="184" text-anchor="middle" font-size="13" font-weight="900" fill="${{answered?'#9a3412':'#64748b'}}">${{answered?'露天作业和安拆不是同一条风线':'答前先分场景，答后再看红线'}}</text></svg>`.replace('{{left}}',svgChip(labels[0]||'露天作业',36,94,136,answered?'#eff6ff':'#f8fafc',answered?'#60a5fa':'#cbd5e1',answered?'#1d4ed8':'#24364b',answered?12:14)).replace('{{right}}',svgChip(labels[1]||'安装/拆卸',188,94,136,answered?'#fff7ed':'#f8fafc',answered?'#f97316':'#cbd5e1',answered?'#9a3412':'#24364b',answered?11:14));}}
  if(v.kind==='s02_trial_lift'){{return `<svg class="practiceVisual" viewBox="0 0 360 238" role="img" aria-label="90%试吊动作图"><rect x="16" y="18" width="328" height="202" rx="20" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><text x="180" y="48" text-anchor="middle" font-size="17" font-weight="900" fill="#176b7a">${{safe(v.load||'额定荷载')}}</text><rect x="70" y="64" width="220" height="14" rx="7" fill="#dbe7f1"/><rect x="70" y="64" width="${{answered?209:150}}" height="14" rx="7" fill="#ff7a1a" opacity=".86"/><path d="M279 55 V88" stroke="#f97316" stroke-width="4" stroke-linecap="round"/><rect x="128" y="${{answered?112:136}}" width="104" height="34" rx="9" fill="#ecfdf5" stroke="#10b981" stroke-width="3"/><text x="180" y="${{answered?134:158}}" text-anchor="middle" font-size="14" font-weight="900" fill="#047857">吊物</text><path d="M72 178 H288" stroke="#94a3b8" stroke-width="6" stroke-linecap="round"/><text x="180" y="102" text-anchor="middle" font-size="13" font-weight="900" fill="${{answered?'#9a3412':'#64748b'}}">${{answered?safe((after[0]||'离地200～500mm')):'先别正式起吊'}}</text><text x="180" y="204" text-anchor="middle" font-size="13" font-weight="900" fill="${{answered?'#047857':'#64748b'}}">${{answered?safe((after[1]||'机械/制动/平稳/绑扎')):'答后揭示四查清单'}}</text></svg>`;}}
  if(v.kind==='s02_limit_gate'){{return `<svg class="practiceVisual" viewBox="0 0 360 238" role="img" aria-label="限位禁令对照图"><rect x="16" y="18" width="328" height="202" rx="20" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><text x="180" y="50" text-anchor="middle" font-size="17" font-weight="900" fill="#176b7a">限位不是操作手柄</text>${{svgChip(before[0]||'操作机构失灵',42,78,128,'#fff7ed','#f97316','#9a3412',12)}}${{svgChip(before[1]||'限位顶替',190,78,128,'#fff7ed','#f97316','#9a3412',12)}}<path d="M165 99 H195" stroke="#ef4444" stroke-width="6" stroke-linecap="round"/><path d="M180 84 V114" stroke="#ef4444" stroke-width="6" stroke-linecap="round"/><text x="180" y="142" text-anchor="middle" font-size="15" font-weight="900" fill="${{answered?'#047857':'#64748b'}}">${{answered?safe(after.join(' → ')):'选完后看正确处置链'}}</text><path d="M92 164 H268" stroke="${{answered?'#10b981':'#cbd5e1'}}" stroke-width="7" stroke-linecap="round"/></svg>`;}}
  if(v.kind==='s02_answer_scan'){{return `<svg class="practiceVisual" viewBox="0 0 360 238" role="img" aria-label="答题纸采分扫描图"><rect x="28" y="22" width="304" height="194" rx="18" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><text x="56" y="54" font-size="15" font-weight="900" fill="#176b7a">答题纸闭环</text>${{[0,1,2,3].map(i=>`<rect x="54" y="${{72+i*32}}" width="252" height="24" rx="8" fill="${{answered?(i===hot?'#fff7ed':'#ecfdf5'):'#f8fafc'}}" stroke="${{answered?(i===hot?'#f97316':'#10b981'):'#cbd5e1'}}" stroke-width="2"/><text x="66" y="${{89+i*32}}" font-size="12" font-weight="900" fill="${{answered?(i===hot?'#9a3412':'#047857'):'#334155'}}">${{safe((answered?after:before)[i]||'')}}</text>`).join('')}}<text x="180" y="204" text-anchor="middle" font-size="12" font-weight="900" fill="${{answered?'#9a3412':'#64748b'}}">${{answered?'把题干事实逐个落到采分句':'先判断，别提前背答案'}}</text></svg>`;}}
  if(v.kind==='s05_power_tree'){{return `<svg class="practiceVisual" viewBox="0 0 360 238" role="img" aria-label="三级配电供电树"><rect x="16" y="18" width="328" height="202" rx="20" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><text x="180" y="46" text-anchor="middle" font-size="16" font-weight="900" fill="#176b7a">${{safe(v.title||'现场供电树')}}</text><path d="M62 118 H298" stroke="${{answered?'#10b981':'#cbd5e1'}}" stroke-width="6" stroke-linecap="round"/><path d="M66 168 H294" stroke="${{answered?'#16a34a':'#cbd5e1'}}" stroke-width="4" stroke-linecap="round" stroke-dasharray="8 6"/><text x="180" y="186" text-anchor="middle" font-size="12" font-weight="900" fill="${{answered?'#047857':'#64748b'}}">${{answered?'TN-S PE线贯通，漏保随配电层级看':'答前只看现场对象，不提前高亮答案'}}</text>${{[0,1,2,3].map((i)=>{{const xs=[52,126,200,274], names=labels.length?labels:['总配电箱','分配电箱','开关箱','设备'];const fill=answered?(i===3?'#fff7ed':'#ecfdf5'):'#f8fafc';const stroke=answered?(i===3?'#f97316':'#10b981'):'#cbd5e1';const color=answered?(i===3?'#9a3412':'#047857'):'#24364b';return svgChip(names[i]||'',xs[i]-32,96,64,fill,stroke,color,11);}}).join('')}}${{answered?`<text x="52" y="82" text-anchor="middle" font-size="11" font-weight="900" fill="#b45309">漏保</text><text x="200" y="82" text-anchor="middle" font-size="11" font-weight="900" fill="#b45309">漏保</text>`:''}}</svg>`;}}
  if(v.kind==='s05_shared_switch'){{return `<svg class="practiceVisual" viewBox="0 0 360 238" role="img" aria-label="一箱控多机诊断图"><rect x="16" y="18" width="328" height="202" rx="20" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><text x="180" y="46" text-anchor="middle" font-size="16" font-weight="900" fill="#176b7a">${{answered?'拆成“一机一闸”':'题干现场:共用开关箱'}}</text><path d="M68 118 H186" stroke="#94a3b8" stroke-width="5" stroke-linecap="round"/><path d="M218 118 C238 92 258 84 288 84" stroke="${{answered?'#10b981':'#ef4444'}}" stroke-width="5" fill="none"/><path d="M218 118 C238 144 258 154 288 154" stroke="${{answered?'#10b981':'#ef4444'}}" stroke-width="5" fill="none"/>${{svgChip(labels[0]||'分配箱',38,98,78,'#eff6ff','#60a5fa','#1d4ed8',12)}}${{svgChip(labels[1]||'开关箱',152,98,78,answered?'#ecfdf5':'#fff7ed',answered?'#10b981':'#f97316',answered?'#047857':'#9a3412',12)}}${{svgChip(labels[2]||'设备A',252,64,72,answered?'#ecfdf5':'#fff7ed',answered?'#10b981':'#f97316',answered?'#047857':'#9a3412',12)}}${{svgChip(labels[3]||'设备B',252,134,72,answered?'#ecfdf5':'#fff7ed',answered?'#10b981':'#f97316',answered?'#047857':'#9a3412',12)}}<text x="180" y="198" text-anchor="middle" font-size="13" font-weight="900" fill="${{answered?'#047857':'#b91c1c'}}">${{answered?'每台设备专用开关箱，不得一箱控两台及以上':'错法先出现，答后再改成专用箱'}}</text></svg>`;}}
  if(v.kind==='s05_sequence'){{return `<svg class="practiceVisual" viewBox="0 0 360 238" role="img" aria-label="停送电顺序图"><rect x="16" y="18" width="328" height="202" rx="20" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><text x="180" y="48" text-anchor="middle" font-size="16" font-weight="900" fill="#176b7a">${{answered?'送电和停电是反向链':'先判断当前动作是送电还是停电'}}</text><path d="M70 100 H290" stroke="${{answered?'#10b981':'#cbd5e1'}}" stroke-width="6" stroke-linecap="round"/><path d="M290 148 H70" stroke="${{answered?'#60a5fa':'#cbd5e1'}}" stroke-width="6" stroke-linecap="round"/><path d="M278 92 L294 100 L278 108 M82 140 L66 148 L82 156" stroke="${{answered?'#334155':'#94a3b8'}}" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>${{['总','分','开'].map((n,i)=>svgChip(n+'箱',[50,150,250][i],74,58,answered?'#ecfdf5':'#f8fafc',answered?'#10b981':'#cbd5e1',answered?'#047857':'#24364b',13)).join('')}}${{['开','分','总'].map((n,i)=>svgChip(n+'箱',[50,150,250][i],154,58,answered?'#eff6ff':'#f8fafc',answered?'#60a5fa':'#cbd5e1',answered?'#1d4ed8':'#24364b',13)).join('')}}<text x="180" y="128" text-anchor="middle" font-size="13" font-weight="900" fill="${{answered?'#047857':'#64748b'}}">${{answered?'送电:总→分→开；停电:开→分→总':'答前不标方向，先看题干动词'}}</text></svg>`;}}
  if(v.kind==='s05_voltage_cable'){{return `<svg class="practiceVisual" viewBox="0 0 360 238" role="img" aria-label="安全电压与电缆剖面图"><rect x="16" y="18" width="328" height="202" rx="20" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><text x="180" y="46" text-anchor="middle" font-size="16" font-weight="900" fill="#176b7a">${{answered?'参数要落到现场对象':'先看环境和电缆剖面'}}</text>${{[0,1,2].map((i)=>svgChip((answered?after:before)[i]||['潮湿/隧道','易触及','金属容器'][i],[34,132,230][i],66,94,answered?['#eff6ff','#fffbeb','#fff7ed'][i]:'#f8fafc',answered?['#60a5fa','#f59e0b','#f97316'][i]:'#cbd5e1',answered?['#1d4ed8','#b45309','#9a3412'][i]:'#24364b',11)).join('')}}<rect x="72" y="150" width="216" height="42" rx="12" fill="#d9c8a5" stroke="#8b7355" stroke-width="3"/><path d="M94 158 H266" stroke="#334155" stroke-width="6" stroke-linecap="round"/><text x="180" y="210" text-anchor="middle" font-size="13" font-weight="900" fill="${{answered?'#047857':'#64748b'}}">${{answered?'电缆直接埋地深度≥0.7m；N蓝、PE黄绿':'答后揭示深度与标识色'}}</text></svg>`;}}
  if(v.kind==='s05_answer_scan'){{return `<svg class="practiceVisual" viewBox="0 0 360 238" role="img" aria-label="临时用电答题纸扫描图"><rect x="28" y="22" width="304" height="194" rx="18" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><text x="56" y="54" font-size="15" font-weight="900" fill="#176b7a">答题纸扫描</text>${{[0,1,2,3].map(i=>`<rect x="50" y="${{72+i*31}}" width="260" height="24" rx="8" fill="${{answered?(i===hot?'#fff7ed':'#ecfdf5'):'#f8fafc'}}" stroke="${{answered?(i===hot?'#f97316':'#10b981'):'#cbd5e1'}}" stroke-width="2"/><text x="62" y="${{89+i*31}}" font-size="12" font-weight="900" fill="${{answered?(i===hot?'#9a3412':'#047857'):'#334155'}}">${{safe((answered?after:before)[i]||'')}}</text>`).join('')}}<text x="180" y="210" text-anchor="middle" font-size="12" font-weight="900" fill="${{answered?'#9a3412':'#64748b'}}">${{answered?'不是口号，必须交付可给分动作':'先写答案，答后扫描命中点'}}</text></svg>`;}}
  const visualItems=Array.isArray(v.items)&&v.items.length?v.items:DATA.keyPoints;
  return renderDots(visualItems,hot);
}}
function paintChoiceState(){{const q=current(), a=answered();[...els.options.querySelectorAll('[data-option-id]')].forEach(btn=>{{const id=btn.dataset.optionId;btn.classList.toggle('correct',!!a&&id===q.answer);btn.classList.toggle('wrong',!!a&&id===a.choice&&id!==q.answer);btn.disabled=!!a;}});}}
function render(){{const q=current(), a=answered();document.documentElement.dataset.practiceIndex=String(index+1);document.documentElement.dataset.practiceState=a?'answered':'waiting';els.card.style.display='grid';els.done.classList.remove('show');els.qCount.textContent=`第 ${{index+1}}/${{DATA.questions.length}} 问`;els.qFocus.textContent=q.stageLabel||q.skill||'本题练习';els.progress.style.width=`${{((index+(a?1:0))/DATA.questions.length)*100}}%`;els.flow.innerHTML=renderVisual(q,a);els.student.textContent=q.student;els.stem.textContent=q.stem;els.options.innerHTML=q.options.map((o,i)=>`<button class="option" type="button" data-option-id="${{safe(o.id)}}"><b>${{String.fromCharCode(65+i)}}</b><span>${{safe(o.label)}}<small>${{safe(o.reason)}}</small></span></button>`).join('');els.options.querySelectorAll('[data-option-id]').forEach(btn=>btn.addEventListener('click',()=>choose(btn.dataset.optionId)));els.prev.disabled=index===0;els.primary.textContent=a?(index===DATA.questions.length-1?'看结果':'下一题'):'先作答';els.primary.classList.remove('blocked');if(a){{const feedbackText=a.correct?q.correct:((q.optionFeedback&&q.optionFeedback[a.choice])||q.wrong);setFeedback(a.correct?'correct':'wrong',feedbackText);}}else{{clearFeedback();}}paintChoiceState();}}
function choose(choice){{const q=current();if(answered())return;const correct=choice===q.answer;answers[index]={{choice,correct}};render();}}
function goNext(){{if(!answered()){{els.primary.classList.add('blocked');setFeedback('wait','先选一个判断，再进入下一题。');document.documentElement.dataset.practiceState='blocked';return;}}if(index<DATA.questions.length-1){{index+=1;render();return;}}showDone();}}
function optionText(q,id){{const hit=q.options.find(o=>o.id===id);return hit?hit.label:'未作答';}}
function answerRows(){{return DATA.questions.map((q,i)=>{{const a=answers[i];const ok=!!(a&&a.correct);const missFeedback=a&&q.optionFeedback?q.optionFeedback[a.choice]:'';return {{index:i+1,questionId:q.id,focus:q.skill||q.stageLabel||DATA.keyPoints[q.focusIndex]||'',stem:q.stem,student:q.student,selected:optionText(q,a&&a.choice),correct:optionText(q,q.answer),isCorrect:ok,feedback:ok?q.correct:(missFeedback||q.wrong)}};}});}}
function buildDiagnosis(){{const rows=answerRows();const total=rows.length||1;const score=rows.filter(r=>r.isCorrect).length;const misses=rows.filter(r=>!r.isCorrect);const rate=score/total;const strong=[...new Set(rows.filter(r=>r.isCorrect).map(r=>r.focus).filter(Boolean))];const weak=[...new Set(misses.map(r=>r.focus).filter(Boolean))];let level='可以进入下一卡';let action='本卡基本过关，可以进入下一张，但建议把采分句再口述一遍。';if(rate<0.6){{level='需要补讲 + 补练';action='先回看白板，把错题对应的采分链补上，再重做薄弱题。';}}else if(misses.length){{level='建议补练薄弱点';action='主线已经成型，但薄弱点还会丢采分句，建议继续补练错题。';}}return {{rows,total,score,misses,rate,strong,weak,level,action,needsDrill:misses.length>0}};}}
function renderDiagnosis(d){{els.level.textContent=d.level;els.score.textContent=`你答对 ${{d.score}}/${{d.total}} 题。${{d.action}}`;const weakText=d.weak.length?d.weak.join('、'):'没有明显薄弱点';const strongText=d.strong.length?d.strong.join('、'):'还需要形成稳定命中点';els.insights.innerHTML=[`<div class="insight"><b>已经掌握</b><p>${{safe(strongText)}}</p></div>`,`<div class="insight ${{d.needsDrill?'warn':''}}"><b>需要盯住</b><p>${{safe(weakText)}}</p></div>`,`<div class="insight"><b>下一步</b><p>${{safe(d.needsDrill?'继续做薄弱点，不要急着跳卡。':'可以进入下一卡，也可以问鲁班做延伸。')}}</p></div>`].join('');els.review.innerHTML=d.rows.map(r=>`<div class="reviewItem ${{r.isCorrect?'good':'miss'}}"><b>第${{r.index}}问 · ${{safe(r.focus)}} · ${{r.isCorrect?'命中':'未命中'}}</b><small>你选：${{safe(r.selected)}}；标准：${{safe(r.correct)}}。${{safe(r.feedback)}}</small></div>`).join('');els.drill.textContent=d.needsDrill?'继续补练薄弱点':'再刷一遍巩固';}}
function buildAskPayload(d,question='我还有点不明白，帮我按采分点讲一下。'){{return {{type:'luban_practice_diagnosis',source:'animation_ir_practice',cardId:DATA.cardId,title:DATA.title,contextId:(DATA.aiContext&&DATA.aiContext.context_id)||DATA.cardId,mainExamAction:DATA.mainExamAction,keyPoints:DATA.keyPoints,aiContext:DATA.aiContext||{{}},score:{{correct:d.score,total:d.total,rate:d.rate,level:d.level,needsDrill:d.needsDrill}},weakPoints:d.weak,strongPoints:d.strong,answers:d.rows,question,expectedUse:'把本卡采分点、易错点、学生作答轨迹带给 TutorBot / 鲁班答疑，不跳转 chat 首页。'}};}}
function notifyLuban(payload){{document.documentElement.dataset.aiAskStatus='posted';try{{window.wx&&window.wx.miniProgram&&window.wx.miniProgram.postMessage({{data:payload}});}}catch(e){{}}try{{if(window.parent&&window.parent!==window)window.parent.postMessage(payload,'*');}}catch(e){{}}try{{window.dispatchEvent(new CustomEvent('luban-practice-diagnosis',{{detail:payload}}));}}catch(e){{}}}}
function localLubanPreview(d){{const weak=d.weak.length?d.weak.join('、'):'暂无明显薄弱点';const firstMiss=d.misses[0];return `<p><b>鲁班预诊断：</b>${{safe(d.level)}}。</p><p>这次不是简单看分数，而是看采分链稳不稳。薄弱点：${{safe(weak)}}。</p>${{firstMiss?`<p>最该追问的是第${{firstMiss.index}}问：你选了「${{safe(firstMiss.selected)}}」，标准应落到「${{safe(firstMiss.correct)}}」。可以问：为什么这一步会影响采分？</p>`:''}}<ul><li>想搞清楚：直接问“我为什么错在这个采分点？”</li><li>想多练：点“继续补练薄弱点”。</li><li>想拔高：问鲁班要一个同类变式题。</li></ul>`;}}
function askLuban(){{const d=buildDiagnosis();renderDiagnosis(d);const payload=buildAskPayload(d);notifyLuban(payload);els.aiPanel.classList.add('show');els.aiStatus.textContent='已带上本卡采分点、易错点和你的答题记录。小程序接入后会直接进入鲁班答疑；当前先显示预诊断。';els.aiResult.innerHTML=localLubanPreview(d);}}
function startDrill(){{const target=answers.findIndex(a=>a&&!a.correct);if(target>=0){{answers[target]=null;index=target;}}else{{answers.fill(null);index=0;}}els.primary.disabled=false;render();}}
function showDone(){{const diagnosis=buildDiagnosis();els.card.style.display='none';els.done.classList.add('show');els.progress.style.width='100%';document.documentElement.dataset.practiceState='done';document.documentElement.dataset.practiceScore=String(diagnosis.score);document.documentElement.dataset.practiceNeedsDrill=String(diagnosis.needsDrill);renderDiagnosis(diagnosis);els.atoms.innerHTML=DATA.keyPoints.map(p=>`<span>${{safe(p)}}</span>`).join('');els.primary.textContent='已完成';els.primary.disabled=true;els.prev.disabled=false;}}
els.primary.addEventListener('click',goNext);
els.prev.addEventListener('click',()=>{{if(els.done.classList.contains('show')){{els.primary.disabled=false;index=DATA.questions.length-1;render();return;}}if(index>0){{index-=1;render();}}}});
els.aiCoach.addEventListener('click',askLuban);
els.drill.addEventListener('click',startDrill);
render();
</script></body></html>"""


def render_practice(ir_path: Path) -> Path:
    ir = json.loads(ir_path.read_text(encoding="utf-8"))
    card_id = ir.get("card_id") or ir_path.name.replace(".animation_ir.v0.json", "")
    out = ir_path.with_name(f"{card_id}.practice.html")
    out.write_text(render_html(ir), encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: render_animation_ir_practice.py <card.animation_ir.v0.json>", file=sys.stderr)
        return 2
    out = render_practice(Path(argv[1]))
    print(f"rendered practice: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
