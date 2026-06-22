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
            "stageLabel": "先分两层",
            "skill": "危大门槛",
            "student": "学生答:“单件 12kN 已经算起重吊装危大，所以直接写专家论证。”",
            "stem": "这份答案最危险的扣分点是什么？",
            "answer": "two_level_gate",
            "visual": {
                "items": ["单件 12kN", "危大线:≥10kN", "论证线:100/300/200"],
                "hotIndex": 1,
            },
            "options": [
                {
                    "id": "two_level_gate",
                    "label": "判为危大先写专项方案；专家论证还要再看非常规且100kN、总重300kN或高度200m。",
                    "reason": "把“危大下限”和“超危大论证线”分开。",
                },
                {
                    "id": "expert_direct",
                    "label": "只要超过 10kN，就直接写专家论证，越保守越稳。",
                    "reason": "这是把两层门槛压成一层。",
                },
                {
                    "id": "safe_no_plan",
                    "label": "如果现场没有事故，可以先不写危大和专项方案。",
                    "reason": "考试判规范红线，不等事故发生才判。",
                },
            ],
            "correct": "对。这里因为 12kN 已过 10kN，所以先写危大、专项方案；但不能直接跳到专家论证，必须再比 100kN、300kN、200m 等论证线。",
            "wrong": "不是越保守越好。阅卷看的是两层门槛是否分清：10kN 是危大下限，100/300/200 才是专家论证线。",
            "optionFeedback": {
                "expert_direct": "这正是高频错法。因为 10kN 只让它进入危大和专项方案，不等于自动专家论证。",
                "safe_no_plan": "事故有没有发生不是判断依据。因为题干给了规范数值，已经触发危大口径，必须写专项方案。",
            },
        },
        {
            "id": "q2",
            "stageLabel": "看题干动词",
            "skill": "风线口径",
            "student": "学生答:“风大就按 6 级处理；安拆和正常吊装都差不多。”",
            "stem": "遇到风速/风级题，第一步应该先抓什么？",
            "answer": "verb_threshold",
            "visual": {
                "items": ["露天吊装作业", "安装/拆卸", "红线不同"],
                "hotIndex": 2,
            },
            "options": [
                {
                    "id": "verb_threshold",
                    "label": "先看动作动词：露天吊装作业看 6 级风，安装拆卸看 >9.0m/s 和低能见度。",
                    "reason": "动作不同，调用的红线不同。",
                },
                {
                    "id": "one_wind_rule",
                    "label": "统一写 6 级风停工，所有起重场景都按一条线处理。",
                    "reason": "简单但会把安拆场景套错。",
                },
                {
                    "id": "weather_feel",
                    "label": "先看现场经验，风不算特别大就可以继续干。",
                    "reason": "安全题不能用感觉替代规范阈值。",
                },
            ],
            "correct": "对。先抓题干动词。露天吊装作业是 6 级及以上停；安装拆卸是 >9.0m/s 或低能见度停，两个阈值不能互换。",
            "wrong": "这里不是背一条“风大停工”。要先看动作，因为露天吊装和安拆调用不同阈值，套错动词就会扣分。",
            "optionFeedback": {
                "one_wind_rule": "这会漏掉安拆口径。因为安拆更危险，题干写安拆时要看 >9.0m/s 和低能见度。",
                "weather_feel": "阅卷不看现场感觉。因为题目给的是规范红线，必须按风级或风速判断。",
            },
        },
        {
            "id": "q3",
            "stageLabel": "试吊先动作",
            "skill": "90%试吊",
            "student": "题干给出起吊达到额定 95%。学生写:“安排专人盯着，缓慢正式起吊。”",
            "stem": "这句话最可能漏掉哪一段采分动作？",
            "answer": "trial_lift_check",
            "visual": {
                "items": ["95% 额定", "先离地 200-500mm", "机械/制动/平稳/绑扎"],
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
            ],
            "correct": "对。95% 已经触发 90% 及以上的前置动作：先吊离地 200～500mm，再查机械、制动、平稳和绑扎，合格后才正式起吊。",
            "wrong": "不是写“慢一点、盯紧点”就能拿分。因为 90% 以上有固定动作和四查清单，顺序错就扣分。",
            "optionFeedback": {
                "slow_lift": "加强旁站听起来安全，但阅卷要的是先离地试吊和四项检查。态度词不能替代动作词。",
                "expert_meeting": "专家论证属于危大层级判断。这里题眼是 95% 额定起吊，必须先写试吊检查。",
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
                "items": ["操作机构失灵", "限位装置", "停止/修复"],
                "hotIndex": 2,
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
            ],
            "correct": "对。出现“用限位代替操作机构”就是不妥。要写停止使用、排除故障、保护装置完整灵敏后再作业。",
            "wrong": "这不是加强管理能化解的风险。因为规范是绝对禁令，限位装置不能代替操作机构，必须停用修复。",
            "optionFeedback": {
                "temporary_replace": "这会把禁令改成可管理风险。因为“代替操作机构”本身就不允许，不能靠慢速和监护补救。",
                "check_after": "先用后查顺序错了。因为故障已经出现，必须先停用排故，再恢复作业。",
            },
        },
        {
            "id": "q5",
            "stageLabel": "落采分句",
            "skill": "安全采分链",
            "student": "现在要把这类题压成答题纸上的一句话。",
            "stem": "下面哪句话最像能拿分的最终表达？",
            "answer": "score_chain",
            "visual": {
                "items": ["先判门槛", "再查条件", "合格后起吊"],
                "hotIndex": 2,
            },
            "options": [
                {
                    "id": "score_chain",
                    "label": "先判危大/论证门槛；作业前核查气象、基础、吊索具和吊点，90%以上先离地检查，合格后方可起吊。",
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
            ],
            "correct": "对。最终采分句要把三道闸串起来：先判门槛，再查作业条件，90% 以上先离地四查，合格后才正式起吊。",
            "wrong": "最终句不能只写安全管理或专家论证。要把门槛、气象/基础/索具/吊点、试吊检查和放行条件写成一条采分链。",
            "optionFeedback": {
                "safe_general": "这句话像口号。因为没有写 10kN/论证门槛、风线、试吊四查等采分动作，容易不给分。",
                "only_expert": "专家论证不是所有起重吊装都要。因为要先分危大和超危大两层，不能一刀切。",
            },
        },
    ]


def build_questions(points: list[str], title: str, ir: dict[str, Any]) -> list[dict[str, Any]]:
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
*{{box-sizing:border-box}}html,body{{margin:0;max-width:100%;overflow-x:hidden}}body{{background:#eef5fb;color:#132033;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}}button{{font:inherit}}.practice{{max-width:430px;margin:0 auto;min-height:100dvh;padding:10px 10px calc(92px + env(safe-area-inset-bottom))}}header{{display:grid;grid-template-columns:auto minmax(0,1fr);gap:10px;align-items:center;margin-bottom:10px}}header a{{min-height:42px;display:flex;align-items:center;border:1px solid #c9d9e8;border-radius:999px;background:#fff;color:#176b7a;text-decoration:none;font-size:12px;font-weight:900;padding:0 12px;white-space:nowrap}}header span{{font-size:11px;color:#176b7a;font-weight:900}}h1{{margin:2px 0 0;font-size:19px;line-height:1.18;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.progress{{height:6px;border-radius:99px;background:#d8e5f0;overflow:hidden;margin:10px 0 12px}}.progress i{{display:block;width:0;height:100%;background:#ff7a1a;transition:width .2s ease}}.card{{background:#fff;border:1px solid #cdddeb;border-radius:20px;padding:13px;box-shadow:0 16px 40px rgba(30,58,87,.12)}}.qtop{{display:flex;justify-content:space-between;gap:10px;color:#176b7a;font-size:12px;font-weight:900}}.qtop em{{font-style:normal;color:#60758c;text-align:right;max-width:58%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.diagram{{margin:10px 0 12px;background:#fffdf7;border:2px solid #eadfcb;border-radius:18px;padding:13px;overflow:hidden}}.flow{{display:grid;grid-template-columns:1fr;gap:8px}}.dot{{min-height:46px;border:2px solid #c9d9e8;border-radius:14px;display:flex;align-items:center;justify-content:center;text-align:center;font-size:14px;font-weight:900;line-height:1.25;padding:8px 10px;background:#f8fafc;color:#24364b}}.dot.hot{{border-color:#ff7a1a;background:#fff7ed;color:#b45309;box-shadow:0 0 0 3px rgba(249,115,22,.1)}}.student{{border-left:4px solid #f97316;background:#fff7ed;border-radius:13px;padding:9px 10px;margin-bottom:10px}}.student b{{display:block;color:#176b7a;font-size:12px}}.student p{{margin:4px 0 0;font-size:15px;line-height:1.45;font-weight:900}}.stem{{font-size:18px;line-height:1.38;font-weight:900;margin:0 0 12px}}.options{{display:grid;gap:9px}}.option{{width:100%;min-height:56px;text-align:left;border:1px solid #d6e2ed;border-radius:15px;background:#fff;padding:10px 12px;color:#172437;display:grid;grid-template-columns:30px minmax(0,1fr);gap:8px;align-items:center}}.option b{{width:30px;height:30px;border-radius:999px;background:#eef4f8;color:#176b7a;display:grid;place-items:center;font-size:14px}}.option span{{font-size:15px;line-height:1.32;font-weight:900;overflow-wrap:anywhere}}.option small{{display:block;color:#60758c;font-size:12px;line-height:1.3;margin-top:3px;font-weight:800}}.option.correct{{border-color:#73c596;background:#ecf9f2}}.option.correct b{{background:#16a34a;color:#fff}}.option.wrong{{border-color:#fb923c;background:#fff3e9}}.option.wrong b{{background:#f97316;color:#fff}}.option:disabled{{opacity:1}}.feedback{{display:none;margin-top:10px;border-radius:14px;padding:11px 12px;font-size:14px;font-weight:850;line-height:1.55}}.feedback.show.correct{{display:block;background:#ecf9f2;border:1px solid #73c596;color:#0f6b4f}}.feedback.show.wrong{{display:block;background:#fff3e9;border:1px solid #fb923c;color:#9a3412}}.feedback.show.wait{{display:block;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412}}.done{{display:none;background:#fff;border:1px solid #d2dee9;border-radius:20px;padding:16px;box-shadow:0 14px 32px rgba(31,41,55,.08)}}.done.show{{display:block}}.done h2{{font-size:24px;margin:0 0 10px;text-align:center;color:#176b7a}}.scoreBox{{border:1px solid #cfe0ee;background:#f8fbfe;border-radius:16px;padding:12px;margin-bottom:12px}}.scoreBox p{{margin:0;color:#1d2f44;font-size:15px;line-height:1.5;font-weight:900}}.scoreBadge{{display:inline-flex;align-items:center;min-height:30px;border-radius:999px;background:#fff7ed;color:#b45309;border:1px solid #fed7aa;padding:4px 10px;margin-top:8px;font-size:12px;font-weight:900}}.resultBlock{{margin-top:12px}}.resultBlock h3{{margin:0 0 8px;color:#176b7a;font-size:15px;line-height:1.3}}.analysisGrid{{display:grid;gap:8px}}.insight{{border-left:4px solid #176b7a;background:#f7fafc;border-radius:12px;padding:9px 10px}}.insight.warn{{border-left-color:#f97316;background:#fff7ed}}.insight b{{display:block;font-size:12px;color:#60758c;margin-bottom:3px}}.insight p{{margin:0;font-size:14px;line-height:1.45;font-weight:900;color:#223248}}.reviewList{{display:grid;gap:7px}}.reviewItem{{border:1px solid #d8e4ef;border-radius:12px;padding:9px 10px;background:#fff}}.reviewItem.good{{background:#f0fdf4;border-color:#bbf7d0}}.reviewItem.miss{{background:#fff7ed;border-color:#fed7aa}}.reviewItem b{{display:block;font-size:13px;line-height:1.35;color:#1d2f44}}.reviewItem small{{display:block;margin-top:4px;color:#60758c;font-size:12px;line-height:1.4;font-weight:800}}.resultActions{{display:grid;gap:9px;margin:14px 0}}.resultActions button,.done a{{min-height:46px;border-radius:14px;font-weight:900;text-decoration:none}}.resultActions button{{border:1px solid #cdddeb;background:#fff;color:#24364b}}.resultActions .ask{{background:#176b7a;color:#fff;border-color:#176b7a}}.resultActions .drill{{background:#ff7a1a;color:#fff;border-color:#ff7a1a}}.done a{{display:flex;align-items:center;justify-content:center;background:#fff;color:#176b7a;border:1px solid #c9d9e8}}.aiPanel{{display:none;border:1px solid #d6e2ed;border-radius:16px;background:#0f1e2d;color:#eaf2fb;padding:12px;margin-top:10px}}.aiPanel.show{{display:block}}.aiStatus{{margin:0 0 8px;color:#fed27a;font-size:12px;font-weight:900}}.aiResult{{font-size:14px;line-height:1.55;font-weight:850}}.aiResult p{{margin:0 0 8px}}.aiResult ul{{margin:6px 0 0;padding-left:18px}}.atoms{{display:grid;gap:7px;margin:12px 0}}.atoms span{{border-left:3px solid #176b7a;background:#f7fafc;border-radius:10px;padding:8px 10px;font-size:13px;font-weight:900;color:#34465b}}nav{{position:fixed;left:50%;bottom:0;transform:translateX(-50%);width:min(430px,100%);display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:10px 12px calc(10px + env(safe-area-inset-bottom));background:rgba(255,255,255,.96);border-top:1px solid #d2dee9;box-shadow:0 -10px 28px rgba(31,41,55,.12)}}nav button{{min-height:48px;border-radius:14px;border:1px solid #cfdae6;background:#fff;color:#24364b;font-weight:900}}nav button.primary{{background:#176b7a;color:#fff;border-color:#176b7a}}nav button:disabled{{background:#eef4f8;color:#7b8da1;border-color:#cfdae6}}nav button.blocked{{border-color:#fb923c;background:#fff7ed;color:#9a3412}}@media(orientation:landscape){{.practice{{max-width:920px;padding-bottom:78px}}.card{{display:grid;grid-template-columns:minmax(280px,1fr) minmax(340px,.85fr);gap:14px;align-items:start}}.qtop{{grid-column:1/-1}}.diagram{{margin:0}}.flow{{grid-template-columns:1fr 1fr}}.student,.stem,.options,.feedback{{grid-column:2}}.done{{max-width:760px;margin:0 auto}}.analysisGrid{{grid-template-columns:1fr 1fr}}.resultActions{{grid-template-columns:1fr 1fr 1fr}}nav{{width:min(720px,100%);grid-template-columns:180px 1fr}}}}
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
function paintChoiceState(){{const q=current(), a=answered();[...els.options.querySelectorAll('[data-option-id]')].forEach(btn=>{{const id=btn.dataset.optionId;btn.classList.toggle('correct',!!a&&id===q.answer);btn.classList.toggle('wrong',!!a&&id===a.choice&&id!==q.answer);btn.disabled=!!a;}});}}
function render(){{const q=current(), a=answered();const visual=q.visual||{{}};const visualItems=Array.isArray(visual.items)&&visual.items.length?visual.items:DATA.keyPoints;const hotIndex=a?Number(visual.hotIndex):-1;document.documentElement.dataset.practiceIndex=String(index+1);document.documentElement.dataset.practiceState=a?'answered':'waiting';els.card.style.display='grid';els.done.classList.remove('show');els.qCount.textContent=`第 ${{index+1}}/${{DATA.questions.length}} 问`;els.qFocus.textContent=q.stageLabel||q.skill||'本题练习';els.progress.style.width=`${{((index+(a?1:0))/DATA.questions.length)*100}}%`;els.flow.innerHTML=visualItems.map((p,i)=>`<div class="dot ${{i===hotIndex?'hot':''}}">${{safe(p)}}</div>`).join('');els.student.textContent=q.student;els.stem.textContent=q.stem;els.options.innerHTML=q.options.map((o,i)=>`<button class="option" type="button" data-option-id="${{safe(o.id)}}"><b>${{String.fromCharCode(65+i)}}</b><span>${{safe(o.label)}}<small>${{safe(o.reason)}}</small></span></button>`).join('');els.options.querySelectorAll('[data-option-id]').forEach(btn=>btn.addEventListener('click',()=>choose(btn.dataset.optionId)));els.prev.disabled=index===0;els.primary.textContent=a?(index===DATA.questions.length-1?'看结果':'下一题'):'先作答';els.primary.classList.remove('blocked');if(a){{const feedbackText=a.correct?q.correct:((q.optionFeedback&&q.optionFeedback[a.choice])||q.wrong);setFeedback(a.correct?'correct':'wrong',feedbackText);}}else{{clearFeedback();}}paintChoiceState();}}
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
    print(f"rendered practice: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
