#!/usr/bin/env python3
"""Render an independent practice page from a mother-question master JSON.

This renderer is presentation-only: it reads variants/scoring terms and renders
a self-check challenge page. It does not infer answers, scoring authority, or
learner-state conclusions.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path
from typing import Any


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def js_json(obj: object) -> str:
    return (
        json.dumps(obj, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_card(master_path: Path, master: dict[str, Any]) -> dict[str, Any]:
    lesson_ref = master.get("teaching_lesson_ref")
    if not lesson_ref:
        return {}
    lesson_path = master_path.parent / str(lesson_ref)
    if not lesson_path.exists():
        return {}
    lesson = _load_json(lesson_path)
    card_ref = lesson.get("derived_from")
    if not card_ref:
        return {}
    card_path = master_path.parent / str(card_ref)
    return _load_json(card_path) if card_path.exists() else {}


def _score_terms(card: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for sp in card.get("scoring_points", []):
        for term in sp.get("keywords", []):
            text = str(term).strip()
            if text and text not in seen:
                seen.add(text)
                out.append(text)
    return out


def _first_metric_threshold(text: str) -> float:
    values = [float(x) for x in re.findall(r"[≥>=]\s*(\d+(?:\.\d+)?)\s*m", text)]
    return values[0] if values else 0.0


def _scenario_specs(master: dict[str, Any]) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    for item in master.get("R3_scenario_templates", []):
        scenario_id = str(item.get("id", ""))
        if not scenario_id:
            continue
        danger = str(item.get("danger_threshold", ""))
        over = str(item.get("over_scale_threshold", ""))
        specs[scenario_id] = {
            "label": str(item.get("engineering") or scenario_id),
            "danger": _first_metric_threshold(danger),
            "over": _first_metric_threshold(over),
        }
    return specs


def _variant_visual(master: dict[str, Any], variant: dict[str, Any]) -> str:
    if not master.get("R3_scenario_templates"):
        return _process_variant_visual(master, variant)
    stem = str(variant.get("stem", ""))
    basis = str(variant.get("basis", ""))
    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)m", stem + " " + basis)]
    value = nums[0] if nums else 0
    scenario = _scenario_specs(master).get(str(variant.get("scenario_id", "")), {})
    obj = str(scenario.get("label") or variant.get("scenario_id") or "本工程")
    g1 = float(scenario.get("danger") or 0)
    g2 = float(scenario.get("over") or 0)
    unit = "m"
    first = value >= g1
    second = value >= g2
    c1 = "hot" if first else "soft"
    c2 = "hot" if second else "soft"
    value_label = f"{value:g}"
    return f"""<svg viewBox="0 0 390 220" role="img" aria-label="{esc(obj)}判断图">
  <rect x="18" y="18" width="354" height="184" rx="18" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/>
  <text x="42" y="50" fill="#176b7a" font-size="16" font-weight="900">{esc(obj)} · {esc(value_label)}{unit}</text>
  <g class="gate {c1}">
    <rect x="42" y="72" width="136" height="68" rx="14"/>
    <text x="110" y="99" text-anchor="middle" font-size="15" font-weight="900">第一道闸</text>
    <text x="110" y="122" text-anchor="middle" font-size="14" font-weight="900">≥{g1}{unit} 危大</text>
  </g>
  <g class="gate {c2}">
    <rect x="212" y="72" width="136" height="68" rx="14"/>
    <text x="280" y="99" text-anchor="middle" font-size="15" font-weight="900">第二道闸</text>
    <text x="280" y="122" text-anchor="middle" font-size="14" font-weight="900">≥{g2}{unit} 超规模</text>
  </g>
  <path d="M178 106 H212" stroke="#8aa0b6" stroke-width="5" stroke-linecap="round"/>
  <text x="195" y="174" text-anchor="middle" fill="#24364b" font-size="15" font-weight="900">{esc(basis)}</text>
</svg>"""


def _process_variant_visual(master: dict[str, Any], variant: dict[str, Any]) -> str:
    text = " ".join(str(variant.get(k, "")) for k in ("stem", "basis", "judged_outcome", "tier_tag"))
    outcome = str(variant.get("judged_outcome", ""))
    if "closure" in outcome or "附加层" in text or "搭接" in text or "闭合" in text:
        active = "add"
        note = "漏防水闭合层"
    elif "test" in outcome or "检验" in text or "蓄水" in text or "淋水" in text:
        active = "test"
        note = "漏检验闭环"
    elif "direct" in outcome or "直接" in text or "盖住" in text:
        active = "dry"
        note = "错在直接覆盖"
    elif "transfer" in outcome or "卫生间" in text:
        active = "transfer"
        note = "换场景仍走闭环"
    else:
        active = "cut"
        note = "先治病因"
    steps = [
        ("cut", "割开放气", 54),
        ("dry", "干燥清基", 138),
        ("add", "附加封严", 222),
        ("test", "试水闭环", 306),
    ]
    items = []
    for sid, label, x in steps:
        hot = sid == active or (active == "transfer" and sid in {"cut", "dry", "add", "test"})
        cls = "hot" if hot else "soft"
        items.append(
            f"""<g class="step {cls}">
    <rect x="{x - 34}" y="56" width="68" height="36" rx="18"/>
    <text x="{x}" y="79" text-anchor="middle" font-size="12" font-weight="900">{esc(label)}</text>
  </g>"""
        )
    return f"""<svg viewBox="0 0 390 220" role="img" aria-label="起鼓割补流程图">
  <rect x="18" y="18" width="354" height="184" rx="18" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/>
  <text x="42" y="46" fill="#176b7a" font-size="16" font-weight="900">起鼓割补 · 先治因再闭合</text>
  <path d="M88 74 H272" stroke="#b7c5d3" stroke-width="6" stroke-linecap="round"/>
  {''.join(items)}
  <g class="roof" transform="translate(42 124)">
    <rect x="0" y="48" width="306" height="28" rx="4" fill="#6b7280"/>
    <rect x="0" y="36" width="306" height="12" fill="#b9ad8e"/>
    <path d="M118 36 Q153 4 188 36 Z" fill="#334155" opacity=".26"/>
    <path d="M150 34 L150 14 M146 21 L150 12 L154 21" stroke="#f97316" stroke-width="2" fill="none"/>
    <rect x="92" y="28" width="128" height="8" rx="2" fill="#15803d" opacity=".78"/>
    <rect x="74" y="18" width="164" height="8" rx="2" fill="#2563eb" opacity=".66"/>
  </g>
  <text x="195" y="118" text-anchor="middle" fill="#f97316" font-size="15" font-weight="900">{esc(note)}</text>
</svg>"""


def _wrong_basis(option_text: str) -> str:
    if "病害识别" in option_text:
        return "错因：题干已经识别起鼓，真正漏的是后续闭合措施"
    if "施工单位" in option_text or "责任" in option_text:
        return "错因：本题考施工修补工序，不是责任主体"
    if "品牌" in option_text or "型号" in option_text:
        return "错因：考试要写工序和采分动作，不是卷材品牌型号"
    if "直接" in option_text or "盖住" in option_text or "重铺地砖" in option_text or "表面再刷" in option_text:
        return "错因：直接覆盖没有先处理气、水汽和基层病因"
    if "已经恢复" in option_text or "可以" in option_text:
        return "错因：铺贴完成还缺蓄水或淋水检验闭环"
    if "整片" in option_text or "全部铲除" in option_text or "一整层" in option_text:
        return "错因：过度处理，题目问的是局部起鼓割补闭环"
    if "非危大" in option_text:
        return "错因：第一道危大阈值没过清"
    if "无需专家论证" in option_text or "无需论证" in option_text:
        return "错因：漏看第二道超规模阈值"
    if "需专家论证" in option_text or "需要专家论证" in option_text:
        return "错因：把危大和超规模混成一档"
    return "错因：没有按本题不变量完整判断"


def _option_text(variant: dict[str, Any], option: dict[str, Any]) -> str:
    text = str(option.get("text", ""))
    if option.get("id") == variant.get("answer"):
        basis = str(variant.get("basis", "")).replace("、", "；")
        return f"{text}；判断依据：{basis}"
    return f"{text}；{_wrong_basis(text)}"


def _option_feedback(variant: dict[str, Any], option: dict[str, Any]) -> str:
    if option.get("id") == variant.get("answer"):
        return str(variant.get("feedback", ""))
    return _wrong_basis(str(option.get("text", "")))


def _extract_student_answer(stem: object) -> tuple[str, str]:
    text = str(stem or "")
    match = re.search(r"学生答[:：]?[\"“](.+?)[\"”]\s*(.*)", text)
    if not match:
        return "", text
    answer = match.group(1).strip()
    question = match.group(2).strip()
    return answer, question or text


def _short_prompt(stem: object, variant: dict[str, Any], process_mode: bool) -> str:
    student_answer, question = _extract_student_answer(stem)
    if process_mode and student_answer and "漏掉" in question:
        return "这份答案漏掉哪一段采分动作?"
    if process_mode and "这样做对吗" in question:
        return "这个做法错在哪一步?"
    if process_mode and "可以收工" in question:
        return "收尾还差哪一步?"
    if process_mode and "核心修补思路" in question:
        return "换场景后,闭环还成立吗?"
    text = question or str(stem or "")
    return text if len(text) <= 34 else text[:32] + "?"


def _choice_label(option: dict[str, Any]) -> str:
    text = str(option.get("text", "")).strip()
    text = re.split(r"[;；。]", text, maxsplit=1)[0].strip()
    return text if len(text) <= 24 else text[:23] + "…"


def render(master_path: Path) -> str:
    master = _load_json(master_path)
    card = _load_card(master_path, master)
    terms = _score_terms(card)
    variants = master.get("variants", [])
    process_mode = not master.get("R3_scenario_templates")
    practice = []
    sections: list[str] = []
    for i, variant in enumerate(variants, 1):
        qid = f"q{i}"
        opts = []
        buttons = []
        details = []
        for option in variant.get("options", []):
            oid = str(option.get("id", ""))
            text = _option_text(variant, option)
            label = _choice_label(option)
            opts.append({"id": oid, "text": text, "feedback": _option_feedback(variant, option)})
            buttons.append(
                f'<button type="button" class="option" data-opt="{esc(oid)}"><b>{esc(oid)}</b><span>{esc(label)}</span></button>'
            )
            details.append(
                f'<li><b>{esc(oid)}.</b> {esc(text)}</li>'
            )
        student_answer, original_question = _extract_student_answer(variant.get("stem", ""))
        short_prompt = _short_prompt(variant.get("stem", ""), variant, process_mode)
        student_answer_html = (
            f'<div class="student-answer"><span>学生答</span><p>{esc(student_answer)}</p></div>'
            if student_answer
            else ""
        )
        practice.append(
            {
                "id": qid,
                "answer": variant.get("answer"),
                "correct_feedback": variant.get("feedback", ""),
                "basis": variant.get("basis", ""),
                "tier": variant.get("tier_tag", ""),
                "options": opts,
            }
        )
        sections.append(
            f"""<section class="q" data-practice-id="{esc(qid)}" data-qid="{esc(qid)}">
  <div class="qtop"><span>第 {i}/{len(variants)+1} 问</span><em>{esc(variant.get('tier_tag','判断题'))}</em></div>
  <div class="diagram">{_variant_visual(master, variant)}</div>
  <div class="prompt-card">
    {student_answer_html}
    <h2>{esc(short_prompt)}</h2>
    <button type="button" class="stem-toggle" data-toggle-stem="1">展开完整题干</button>
    <p class="full-stem">{esc(variant.get('stem',''))}</p>
  </div>
  <div class="answer-zone">
    <div class="choice-label">点一个判断</div>
    <div class="options">{''.join(buttons)}</div>
    <details class="option-drawer"><summary>看完整选项与依据</summary><ol>{''.join(details)}</ol></details>
  </div>
  <div class="feedback" id="fb-{esc(qid)}"></div>
</section>"""
        )
    score_qid = f"q{len(variants)+1}"
    sample = "、".join(terms[:6]) if terms else "先判危大、再判超规模、最后写结论"
    score_pieces = (
        [
            ("病害对象", "如:卷材防水层起鼓部位"),
            ("病因处理", "如:割开放气、排气干燥、清除旧胶结料"),
            ("闭合检验", "如:附加层、搭接封严、蓄水或淋水检验"),
        ]
        if process_mode
        else [
            ("对象/阈值", "如:基坑开挖深度5.5m"),
            ("判断结果", "危大且超过一定规模"),
            ("处理结论", "专项施工方案应组织专家论证"),
        ]
    )
    score_svg_title = "起鼓割补采分句" if process_mode else "答题纸三件套"
    score_svg_line = "病害对象 + 治病因 + 闭合检验" if process_mode else "对象/阈值 + 判断结果 + 处理结论"
    score_labels = "\n".join(
        f'<label><span>{esc(label)}</span><input data-field="field{idx}" placeholder="{esc(ph)}"></label>'
        for idx, (label, ph) in enumerate(score_pieces, 1)
    )
    sections.append(
        f"""<section class="q" data-practice-id="{esc(score_qid)}" data-qid="{esc(score_qid)}">
  <div class="qtop"><span>第 {len(variants)+1}/{len(variants)+1} 问</span><em>采分句输出</em></div>
  <div class="diagram"><svg viewBox="0 0 390 220" role="img" aria-label="采分句答题纸">
    <rect x="28" y="30" width="334" height="154" rx="18" fill="#fff" stroke="#d8e2ec" stroke-width="4"/>
    <text x="58" y="72" fill="#176b7a" font-size="17" font-weight="900">{esc(score_svg_title)}</text>
    <text x="58" y="112" fill="#17202a" font-size="16" font-weight="900">{esc(score_svg_line)}</text>
    <path d="M58 138h274" stroke="#f97316" stroke-width="7" stroke-linecap="round"/>
  </svg></div>
  <h2>把这类题写成一句能拿分的话。</h2>
  <div class="score-write">
    {score_labels}
    <button type="button" class="check-score" data-check-score="1">检查采分句</button>
  </div>
  <div class="feedback" id="fb-{esc(score_qid)}"></div>
</section>"""
    )
    data = {
        "practice": practice,
        "score_question_id": score_qid,
        "score_terms": terms,
        "sample_score_sentence": sample,
        "warm_feedback": (master.get("mastery_discrimination", {}).get("warm_feedback") or {}),
    }
    css = """
*{box-sizing:border-box}html,body{margin:0;max-width:100%;overflow-x:hidden}body{background:#eaf1f6;color:#17202a;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}.practice{max-width:430px;margin:0 auto;min-height:100dvh;padding:8px 10px 12px}header{display:grid;grid-template-columns:auto minmax(0,1fr);gap:10px;align-items:center;margin-bottom:8px}header a{border:1px solid #cad8e5;border-radius:999px;padding:0 12px;background:#fff;color:#176b7a;text-decoration:none;font-weight:900;font-size:12px;white-space:nowrap;min-height:44px;display:flex;align-items:center}header span{color:#176b7a;font-size:11px;font-weight:900}h1{font-size:17px;margin:2px 0 0;line-height:1.18;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.progress{height:5px;border-radius:999px;background:#d6e2ec;margin-bottom:9px;overflow:hidden}.progress div{height:100%;width:0;background:#f97316}.q{display:none}.q.active{display:flex;min-height:calc(100dvh - 152px);flex-direction:column;gap:10px}.qtop{display:flex;justify-content:space-between;gap:10px;color:#176b7a;font-size:12px;font-weight:900}.qtop em{font-style:normal;color:#607287;text-align:right;max-width:58%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.diagram{height:clamp(250px,36dvh,330px);background:#fffdf7;border:1px solid #eadfcb;border-radius:22px;display:grid;place-items:center;overflow:hidden;box-shadow:0 16px 36px rgba(31,41,55,.1)}.diagram svg{width:100%;height:100%}.gate rect,.step rect{fill:#f8fafc;stroke:#cbd9e6;stroke-width:3}.gate.hot rect,.step.hot rect{fill:#fff7ed;stroke:#f97316;stroke-width:5}.gate.soft rect,.step.soft rect{fill:#f8fafc;stroke:#cbd9e6;stroke-width:3}.prompt-card,.answer-zone{min-width:0;overflow-wrap:anywhere;word-break:break-word;background:rgba(255,255,255,.96);border:1px solid #d2dee9;border-radius:18px;padding:11px 12px;box-shadow:0 10px 24px rgba(31,41,55,.08)}.student-answer{border-left:4px solid #f97316;background:#fff7ed;border-radius:12px;padding:8px 10px;margin-bottom:8px}.student-answer span,.choice-label,.score-write span{display:block;font-size:12px;font-weight:900;color:#176b7a}.student-answer p{margin:3px 0 0;font-size:15px;line-height:1.45;font-weight:900;color:#24364b}.q h2{font-size:17px;line-height:1.32;margin:0}.stem-toggle{margin-top:8px;min-height:44px;border:0;background:transparent;color:#176b7a;font-weight:900;padding:0}.full-stem{display:none;margin:8px 0 0;color:#55677a;font-size:13px;line-height:1.5;font-weight:800}.q.show-stem .full-stem{display:block}.options{display:grid;gap:8px;margin-top:7px}.option{text-align:left;min-height:52px;border:1px solid #cfdae6;background:#fff;border-radius:15px;padding:8px 10px;color:#24364b;font-size:15px;font-weight:900;line-height:1.24;display:grid;grid-template-columns:28px minmax(0,1fr);align-items:center;gap:6px}.option b{display:grid;place-items:center;width:28px;height:28px;border-radius:999px;background:#eef4f8;color:#176b7a}.option.correct{border-color:#73c596;background:#ecf9f2}.option.correct b{background:#16a34a;color:#fff}.option.wrong{border-color:#fb923c;background:#fff3e9}.option.wrong b{background:#f97316;color:#fff}.option:disabled{opacity:1}.option-drawer{margin-top:8px;border-top:1px solid #e4edf5;padding-top:8px}.option-drawer summary{min-height:44px;color:#607287;font-size:13px;font-weight:900;cursor:pointer;display:flex;align-items:center}.option-drawer ol{margin:6px 0 0;padding-left:20px;color:#34465b;font-size:13px;line-height:1.55;font-weight:800}.score-write{display:grid;gap:10px}.score-write label{display:grid;gap:5px}.score-write input{min-height:48px;border:1px solid #cfdae6;border-radius:13px;padding:0 12px;font-size:15px;font-weight:800;color:#17202a;background:#fff}.score-write input.ok{border-color:#73c596;background:#ecf9f2}.score-write input.no{border-color:#fb923c;background:#fff3e9}.check-score{min-height:48px;border:1px solid #176b7a;border-radius:14px;background:#176b7a;color:#fff;font-weight:900;font-size:15px}.feedback{display:none;margin-top:0;border-radius:15px;padding:12px;font-size:14px;font-weight:850;line-height:1.55}.feedback.show.correct{display:block;background:#ecf9f2;border:1px solid #73c596;color:#0f6b4f}.feedback.show.wrong{display:block;background:#fff3e9;border:1px solid #fb923c;color:#9a3412}.feedback .basis{display:block;margin-top:7px;color:#56677c;font-size:12px;font-weight:800}.done{display:none;background:#fff;border:1px solid #d2dee9;border-radius:18px;padding:18px;box-shadow:0 14px 32px rgba(31,41,55,.08)}.done.show{display:block}.done h2{font-size:24px;margin:0 0 10px;text-align:center;color:#176b7a}.done p{font-size:15px;line-height:1.65;font-weight:800;color:#34465b}.atoms{display:grid;gap:7px;margin:12px 0}.atoms span{border-left:3px solid #176b7a;background:#f7fafc;border-radius:10px;padding:8px 10px;font-size:13px;font-weight:900;color:#34465b}.done a{display:flex;align-items:center;justify-content:center;background:#176b7a;color:#fff;border-radius:14px;min-height:46px;text-decoration:none;font-weight:900}nav{width:min(430px,calc(100% - 20px));display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:10px auto calc(10px + env(safe-area-inset-bottom));padding:10px;background:rgba(255,255,255,.96);border:1px solid #d2dee9;border-radius:18px;box-shadow:0 10px 28px rgba(31,41,55,.1)}nav button{min-height:48px;border-radius:14px;border:1px solid #cfdae6;background:#fff;color:#24364b;font-weight:900}nav button:last-child{background:#176b7a;color:#fff;border-color:#176b7a}nav button:disabled{background:#eef4f8!important;color:#7b8da1!important;border-color:#cfdae6!important}nav button.blocked{border-color:#fb923c;background:#fff7ed;color:#9a3412}@media(max-height:720px){.diagram{height:clamp(230px,34dvh,300px)}.student-answer p{font-size:14px}.prompt-card,.answer-zone{padding:9px 10px}.option{min-height:48px}}@media(orientation:landscape){.practice{max-width:none;padding:8px 10px 12px}.q.active{display:grid;grid-template-columns:minmax(0,1fr) minmax(360px,.76fr);grid-template-rows:auto 1fr auto;align-items:start}.qtop{grid-column:1/-1}.diagram{height:min(calc(100dvh - 154px),520px)}.prompt-card{grid-column:2}.answer-zone{grid-column:2}.feedback{grid-column:1/-1}nav{width:min(720px,calc(100% - 20px));grid-template-columns:180px 1fr}}
"""
    practice_link = master_path.name.replace(".master.json", ".journey.html")
    return f"""<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(master.get('exam_point','深母题'))} · 独立闯关</title><style>{css}</style></head>
<body><main class="practice" data-practice-shell="challenge-theater">
<header><a href="{esc(practice_link)}">返回讲解</a><div><span>鲁班深母题 · 独立闯关</span><h1>{esc(master.get('exam_point',''))}</h1></div></header>
<div class="progress"><div id="progressFill"></div></div>
{''.join(sections)}
<section class="done" id="done"><h2>看穿结果</h2><p id="scoreText"></p><div class="atoms" id="atoms"></div><a href="{esc(practice_link)}">回看白板讲解</a></section>
</main><nav><button type="button" id="prevQ">上一题</button><button type="button" id="nextQ">下一题</button></nav>
<script type="application/json" id="practiceData">{js_json(data)}</script>
<script>
const DATA=JSON.parse(document.getElementById('practiceData').textContent);
const qs=[...document.querySelectorAll('.q')], selected={{}}, progress=document.getElementById('progressFill');
const prevBtn=document.getElementById('prevQ'), nextBtn=document.getElementById('nextQ');
let current=0, score=0;
const qById=Object.fromEntries(DATA.practice.map(q=>[q.id,q]));
const clean=s=>String(s||'').replace(/\\s+/g,'').replace(/[，。；、,.;]/g,'').toLowerCase();
function el(tag, cls, text){{const node=document.createElement(tag);if(cls)node.className=cls;if(text!=null)node.textContent=String(text);return node;}}
function showFeedback(box, ok, mainText, basisText){{box.className='feedback show '+(ok?'correct':'wrong');box.replaceChildren(document.createTextNode((ok?'对。':'再看判据。')+' '+mainText), el('span','basis',basisText));}}
function done(i){{const qid=qs[i].dataset.qid;return !!selected[qid];}}
function updateNav(){{prevBtn.disabled=current===0;const ready=done(current);nextBtn.disabled=!ready;nextBtn.textContent=ready?(current===qs.length-1?'查看结果':'下一题'):'先作答';}}
function show(i){{current=Math.max(0,Math.min(qs.length-1,i));qs.forEach((q,idx)=>q.classList.toggle('active',idx===current));progress.style.width=((current+1)/qs.length*100)+'%';updateNav();}}
function needAnswer(){{const btn=document.getElementById('nextQ'),old=btn.textContent;btn.textContent='先独立作答';btn.classList.add('blocked');setTimeout(()=>{{btn.textContent=old;btn.classList.remove('blocked');}},900);}}
document.querySelectorAll('.option').forEach(btn=>btn.addEventListener('click',()=>{{
  const qEl=btn.closest('.q'), qid=qEl.dataset.qid, q=qById[qid]; if(selected[qid])return;
  const ok=btn.dataset.opt===q.answer; selected[qid]=btn.dataset.opt; if(ok)score++;
  qEl.querySelectorAll('.option').forEach(o=>{{o.disabled=true;if(o.dataset.opt===q.answer)o.classList.add('correct');else if(o===btn)o.classList.add('wrong');}});
	  const opt=(q.options||[]).find(o=>o.id===btn.dataset.opt)||{{feedback:''}};
	  const fb=document.getElementById('fb-'+qid);
	  showFeedback(fb, ok, ok?(q.correct_feedback||''):(opt.feedback||''), '判据:'+(q.basis||'')+(q.tier?' · '+q.tier:''));
  updateNav();
	}}));
document.querySelectorAll('[data-toggle-stem]').forEach(btn=>btn.addEventListener('click',()=>{{
  const q=btn.closest('.q'); q.classList.toggle('show-stem');
  btn.textContent=q.classList.contains('show-stem')?'收起完整题干':'展开完整题干';
}}));
document.querySelector('[data-check-score]').addEventListener('click',()=>{{
  const qEl=qs[qs.length-1], qid=qEl.dataset.qid, values=[...qEl.querySelectorAll('input')].map(i=>i.value).join('');
  const terms=DATA.score_terms||[]; const hit=terms.filter(t=>clean(values).includes(clean(t))).length;
  selected[qid]=true; if(hit>=3)score++;
  qEl.querySelectorAll('input').forEach(i=>i.classList.toggle('ok',i.value.trim().length>0));
	  const fb=document.getElementById('fb-'+qid);
	  fb.className='feedback show '+(hit>=3?'correct':'wrong');
	  fb.replaceChildren(document.createTextNode(hit>=3?'对。':'还不够像采分句。'), el('span','basis','可写:'+DATA.sample_score_sentence));
  updateNav();
	}});
prevBtn.addEventListener('click',()=>show(current-1));
nextBtn.addEventListener('click',()=>{{if(!done(current)){{needAnswer();return;}} if(current<qs.length-1)show(current+1);else showDone();}});
function showDone(){{qs.forEach(q=>q.classList.remove('active'));document.getElementById('done').classList.add('show');document.querySelector('nav').style.display='none';progress.style.width='100%';const ratio=score+'/'+qs.length;document.getElementById('scoreText').textContent=ratio+'。'+((DATA.warm_feedback||{{}}).all_correct||'把判断链写成采分句,才算真正会拿分。');document.getElementById('atoms').replaceChildren(...(DATA.score_terms||[]).slice(0,6).map(t=>{{const s=document.createElement('span');s.textContent=t;return s;}}));}}
show(0);
</script></body></html>"""


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: render_archetype_practice.py <master.json>", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    out = src.with_name(src.name.replace(".master.json", ".practice.html"))
    out.write_text(render(src), encoding="utf-8")
    print(f"✅ {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
