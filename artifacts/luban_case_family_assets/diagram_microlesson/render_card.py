#!/usr/bin/env python3
"""图解微课卡确定性渲染器（luban_diagram_microlesson.v1）· 翻页 deck 版。

输入:一份考点 schema JSON。
输出:一张小程序 WebView 可承载的静态 HTML 卡:内联 SVG、内联 CSS、少量内联 JS。

体验:一屏一个重点的翻页式(deck)——8 步每步一屏(聚焦图 + 这一步 + 怎么写得分),
末尾错因 / 复测 / 收束各一屏;底部「上一步/下一步」常驻,单屏基本不需要滚动。

边界:
- 渲染器只渲染 schema 内事实,不生成知识、不判分、不补采分点。
- 图形是确定性 SVG 示意,不是规范级节点详图。
- 交互只做翻页、错因跳转和复测反馈,不访问网络、不依赖外链、不接 TTS/音频。
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "luban_diagram_microlesson.v1"

_TIER_LABEL = {
    "exact_required": "须写到关键词",
    "high_risk_review": "高风险表达",
    "list_rule": "列举规则",
    "calculation": "计算规则",
}

_CSS = r"""
:root{
  --ink:#17202a;--muted:#637083;--line:#e3e9f0;--blue:#2563eb;--green:#0f6b4f;--bg:#eef3f7;--card:#fff;
}
*{box-sizing:border-box}
html,body{margin:0;max-width:100%;overflow-x:hidden}
body{background:var(--bg);color:var(--ink);line-height:1.6;padding-bottom:86px;
 font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}
button{font:inherit}
.deck{max-width:520px;margin:0 auto;min-height:100vh;position:relative}
.deck-top{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:12px 16px;color:var(--muted);font-size:12px}
.deck-top .brandmini{font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.deck-count{flex:0 0 auto;font-weight:800;color:var(--blue)}
.slide{display:none;padding:0 14px}
.slide.active{display:block;animation:fade .25s ease}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.stage{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:8px;box-shadow:0 10px 30px rgba(31,41,55,.08)}
.roof-wrap{position:relative;background:#fffdf8;border:1px solid #eadfcf;border-radius:14px;overflow:hidden}
.svg-frame{width:100%;display:block;aspect-ratio:470/350}
.legend{display:flex;flex-wrap:wrap;gap:6px;padding:8px 8px 4px}
.legend span{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:#566573}
.sw{width:13px;height:8px;border-radius:3px;display:inline-block}
.layer-label{font-size:15px;fill:#334155;font-weight:700}
.thin-label{display:none}
.step-layer{opacity:.12;transition:opacity .25s ease}
.step-layer.active{opacity:1;filter:drop-shadow(0 6px 12px rgba(37,99,235,.18))}
.step-layer.done{opacity:.34}
.step-point{margin-top:12px}
.ptop{display:flex;justify-content:space-between;align-items:center;gap:10px}
.eyebrow{color:var(--blue);font-size:12px;font-weight:800}
.say-btn{flex:0 0 auto;min-height:36px;border:1px solid var(--blue);background:#eaf1ff;color:#153e91;border-radius:999px;padding:6px 12px;font-size:12px;font-weight:800;cursor:pointer;white-space:nowrap}
.say-btn.playing{background:var(--blue);color:#fff}
.step-point h2{margin:6px 0 8px;font-size:21px;line-height:1.3}
.step-say{margin:0 0 12px;color:#3f4d5e;font-size:14.5px;line-height:1.7}
.point-box{background:#e9f7f0;border:1px solid #b7e3cf;border-radius:14px;padding:13px 14px}
.point-box b{display:block;color:var(--green);font-size:13px;margin-bottom:5px}
.point-box p{margin:0;color:#1f3b30;font-size:15px;line-height:1.65}
.more-toggle{margin-top:12px;border:0;background:transparent;color:var(--blue);font-size:13px;font-weight:700;cursor:pointer;padding:6px 0;min-height:40px}
.more{margin-top:4px;border:1px solid var(--line);border-radius:12px;padding:11px 13px;background:#fbfdff}
.more-line{margin:0 0 8px;font-size:13px;color:#405066;line-height:1.6}
.more-line:last-child{margin-bottom:0}
.more-line.muted{color:var(--muted);font-size:12px}
.jump-note{margin-top:12px;border-radius:12px;padding:11px 13px;background:#fff4e6;border:1px solid #f3cf9b;color:#8a4d05;font-size:13px;line-height:1.55}
.jump-note b{color:#7a3d00}
.aux-h{font-size:20px;margin:10px 0 4px}
.aux-sub{color:var(--muted);font-size:13.5px;margin:0 0 14px;line-height:1.6}
.error-grid,.option-grid{display:flex;flex-direction:column;gap:10px}
.error-card{text-align:left;border:1px solid var(--line);border-radius:14px;background:var(--card);padding:13px;cursor:pointer;width:100%}
.error-card b{display:block;font-size:14px;margin-bottom:5px}
.error-card span{color:var(--muted);font-size:12.5px;line-height:1.55}
.error-card .code{display:none}
.option{min-height:54px;text-align:left;border:1px solid var(--line);border-radius:14px;background:var(--card);padding:12px 14px;cursor:pointer;color:#263241;font-size:14.5px}
.option[aria-pressed="true"].correct{border-color:#8bd0ad;background:#e8f7f0}
.option[aria-pressed="true"].wrong{border-color:#f1aaa0;background:#fde8e3}
.feedback{margin-top:14px;border-radius:13px;padding:12px 14px;border:1px solid var(--line);background:#f8fafc;font-size:14px;line-height:1.65;display:none}
.feedback.show{display:block}
.feedback.correct{background:#e8f7f0;border-color:#9bd6b6;color:#0f6b4f}
.feedback.wrong{background:#fde8e3;border-color:#f1aaa0;color:#9a3412}
.hook{font-size:18px;font-weight:800;color:#153e91;background:#eaf1ff;border:1px solid #c3d8fb;border-radius:14px;padding:16px;text-align:center;line-height:1.55}
.warm-box{margin-top:12px;border:1px solid var(--line);border-radius:14px;background:var(--card);padding:14px;font-size:14px;color:#3f4d5e;line-height:1.75}
.auth{margin-top:14px;border:1px solid var(--line);border-radius:12px;background:var(--card);padding:12px;color:var(--muted);font-size:12px;line-height:1.6}
.auth-sub{margin-top:6px;font-weight:700;color:#9a3412}
.stepnav{position:fixed;left:0;right:0;bottom:0;z-index:60;display:flex;align-items:center;gap:12px;max-width:520px;margin:0 auto;
 padding:10px 14px calc(10px + env(safe-area-inset-bottom));background:rgba(255,255,255,.97);
 border-top:1px solid var(--line);box-shadow:0 -6px 22px rgba(31,41,55,.12);backdrop-filter:saturate(1.3) blur(8px)}
.stepnav-mid{flex:1;min-width:0;display:flex;flex-direction:column;gap:5px;align-items:center}
.stepnav-mid span{font-size:12px;color:var(--muted);font-weight:800}
.mini-progress{display:block;width:100%;height:7px;border-radius:999px;background:#e6edf5;overflow:hidden}
.mini-progress b{display:block;height:100%;width:9%;background:linear-gradient(90deg,#2563eb,#16a37f);border-radius:inherit;transition:width .25s ease}
.control{flex:0 0 auto;min-width:88px;min-height:48px;border-radius:14px;border:1px solid var(--line);background:#fff;color:#334155;font-weight:700;cursor:pointer;padding:0 14px}
.control.primary{background:var(--blue);color:#fff;border-color:var(--blue)}
.control:disabled{opacity:.4}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def trusted_json_for_script(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def validate(schema: dict[str, Any]) -> None:
    if schema.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {schema.get('schema_version')!r}")

    steps = schema.get("steps") or []
    if len(steps) != 8:
        raise ValueError(f"F16 formal card requires 8 steps, got {len(steps)}")
    step_ids = {s.get("id") for s in steps}
    if len(step_ids) != len(steps):
        raise ValueError("step id must be unique")

    for err in schema.get("common_errors") or []:
        target = err.get("jump_step_id")
        if target not in step_ids:
            raise ValueError(f"common_errors jump_step_id not found: {target!r}")

    practice = schema.get("practice") or {}
    if practice:
        options = practice.get("options") or []
        if len(options) < 2 or sum(1 for o in options if o.get("is_correct")) != 1:
            raise ValueError("practice must have options and exactly one correct option")

    narration = schema.get("narration") or {}
    for n in narration.get("steps") or []:
        if n.get("step_id") not in step_ids:
            raise ValueError(f"narration step_id not found: {n.get('step_id')!r}")
        if not str(n.get("script") or "").strip():
            raise ValueError(f"narration script empty for: {n.get('step_id')!r}")
        secs = n.get("seconds")
        if not isinstance(secs, (int, float)) or not (8 <= secs <= 12):
            raise ValueError(f"narration seconds must be 8-12, got {secs!r} for {n.get('step_id')!r}")

    opening = narration.get("opening")
    if opening:
        if not str(opening.get("script") or "").strip():
            raise ValueError("narration.opening.script empty")
        osecs = opening.get("seconds")
        if not isinstance(osecs, (int, float)) or not (6 <= osecs <= 8):
            raise ValueError(f"narration.opening.seconds must be 6-8, got {osecs!r}")

    error_ids = {e.get("id") for e in schema.get("common_errors") or []}
    for r in narration.get("error_reveals") or []:
        if r.get("error_id") not in error_ids:
            raise ValueError(f"error_reveal error_id not in common_errors: {r.get('error_id')!r}")
        if r.get("jump_step_id") not in step_ids:
            raise ValueError(f"error_reveal jump_step_id not found: {r.get('jump_step_id')!r}")
        if not str(r.get("script") or "").strip() or not str(r.get("correction_hint") or "").strip():
            raise ValueError(f"error_reveal needs script+correction_hint: {r.get('error_id')!r}")
        rsecs = r.get("seconds")
        if not isinstance(rsecs, (int, float)) or not (5 <= rsecs <= 8):
            raise ValueError(f"error_reveal seconds must be 5-8, got {rsecs!r} for {r.get('error_id')!r}")

    pf = narration.get("practice_feedback")
    if pf and (not str(pf.get("correct_script") or "").strip() or not str(pf.get("incorrect_script") or "").strip()):
        raise ValueError("narration.practice_feedback needs correct_script+incorrect_script")


def roof_svg() -> str:
    return r"""
<svg class="svg-frame" id="roofSvg" viewBox="210 150 470 350" role="img" aria-labelledby="svgTitle svgDesc">
  <title id="svgTitle">屋面卷材防水起鼓割补工序剖面图</title>
  <desc id="svgDesc">图示基层、找平层、基层处理剂、防水卷材、起鼓、割开排气、附加层、修补卷材和检验闭环。</desc>
  <defs>
    <linearGradient id="sky" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0%" stop-color="#eef7ff"></stop>
      <stop offset="100%" stop-color="#fffdf8"></stop>
    </linearGradient>
    <pattern id="concrete" width="24" height="24" patternUnits="userSpaceOnUse">
      <rect width="24" height="24" fill="#aeb7bf"></rect>
      <path d="M3 18l5-3M12 8l7-4M16 21l5-5M2 6l4 2" stroke="#8a949e" stroke-width="1.2" opacity=".55"></path>
    </pattern>
    <marker id="arrowBlue" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">
      <path d="M0 0 L10 5 L0 10 z" fill="#2563eb"></path>
    </marker>
    <marker id="arrowGreen" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">
      <path d="M0 0 L10 5 L0 10 z" fill="#16815f"></path>
    </marker>
  </defs>
  <rect x="0" y="0" width="900" height="560" fill="url(#sky)"></rect>
  <path d="M50 384 C180 350 265 390 380 360 C520 324 640 368 850 330" fill="none" stroke="#d8e0e8" stroke-width="2" opacity=".7"></path>
  <g id="base">
    <path d="M110 380 L780 310 L780 455 L110 455 Z" fill="url(#concrete)" stroke="#7f8994" stroke-width="2"></path>
    <path d="M110 350 L780 280 L780 312 L110 382 Z" fill="#c8cdd2" stroke="#98a2ad" stroke-width="2"></path>
    <path d="M110 332 L780 262 L780 281 L110 351 Z" fill="#f3b340" stroke="#d79520" stroke-width="2"></path>
    <path d="M110 308 L780 238 L780 263 L110 333 Z" fill="#3a4b61" stroke="#263647" stroke-width="2"></path>
    <text x="675" y="430" class="layer-label">结构基层</text>
    <text x="672" y="356" class="layer-label">找平层</text>
    <text x="664" y="300" class="layer-label">基层处理剂</text>
    <text x="630" y="246" class="layer-label">防水卷材层</text>
  </g>
  <g class="step-layer" data-layer="identify_bulge">
    <path d="M362 295 C378 248 445 237 478 274 C506 306 480 338 427 344 C382 349 345 331 362 295 Z" fill="#fde68a" stroke="#d97706" stroke-width="4"></path>
    <path d="M387 304 C407 283 440 283 457 302" fill="none" stroke="#b45309" stroke-width="3" stroke-linecap="round"></path>
    <text x="330" y="223" class="layer-label" fill="#92400e">起鼓部位</text>
    <path d="M390 232 C398 246 400 258 399 276" stroke="#92400e" stroke-width="2" fill="none" marker-end="url(#arrowGreen)"></path>
  </g>
  <g class="step-layer" data-layer="cut_bulge">
    <path d="M390 270 L470 345" stroke="#c24130" stroke-width="7" stroke-linecap="round"></path>
    <path d="M468 270 L388 346" stroke="#c24130" stroke-width="7" stroke-linecap="round"></path>
    <text x="212" y="284" class="layer-label" fill="#991b1b">十字或丁字割开</text>
  </g>
  <g class="step-layer" data-layer="vent_dry">
    <path d="M398 292 C370 242 382 200 412 178" stroke="#2563eb" stroke-width="4" fill="none" marker-end="url(#arrowBlue)"></path>
    <path d="M438 290 C443 236 480 207 522 197" stroke="#2563eb" stroke-width="4" fill="none" marker-end="url(#arrowBlue)"></path>
    <text x="500" y="175" class="layer-label" fill="#1d4ed8">排气、干燥</text>
    <text x="500" y="196" class="thin-label">没有干燥就直接贴，是常见弱表达</text>
  </g>
  <g class="step-layer" data-layer="clean_prime">
    <path d="M318 320 L540 296 L540 321 L318 346 Z" fill="#fbbf24" stroke="#d97706" stroke-width="3" opacity=".92"></path>
    <text x="222" y="386" class="layer-label" fill="#92400e">清理基层后补刷处理剂</text>
  </g>
  <g class="step-layer" data-layer="fill_repair">
    <path d="M360 304 L492 290 L492 322 L360 336 Z" fill="#e2e8f0" stroke="#64748b" stroke-width="3"></path>
    <text x="200" y="238" class="layer-label" fill="#475569">嵌填、修补基层缺陷</text>
  </g>
  <g class="step-layer" data-layer="reinforcement_layer">
    <path d="M265 284 L622 247 L622 292 L265 330 Z" fill="#9be7cf" stroke="#16815f" stroke-width="4"></path>
    <text x="240" y="207" class="layer-label" fill="#0f6b4f">增铺附加层，范围盖过病害边缘</text>
  </g>
  <g class="step-layer" data-layer="new_membrane_seal">
    <path d="M220 262 L690 213 L690 254 L220 304 Z" fill="#1f7665" stroke="#0f5d4c" stroke-width="4"></path>
    <path d="M610 221 L692 212 L692 254 L610 263 Z" fill="#34a185" stroke="#0f5d4c" stroke-width="3"></path>
    <path d="M646 214 L650 256" stroke="#fff" stroke-width="3" stroke-dasharray="5 5"></path>
    <text x="238" y="250" class="layer-label" fill="#ffffff">新卷材覆盖、搭接封严</text>
  </g>
  <g class="step-layer" data-layer="water_test">
    <path d="M194 210 C286 235 384 221 486 199 C574 180 666 176 745 192" fill="none" stroke="#38bdf8" stroke-width="7" stroke-linecap="round"></path>
    <path d="M224 193 l14 25 M304 189 l14 25 M382 177 l14 25 M462 166 l14 25 M542 158 l14 25 M622 158 l14 25 M702 172 l14 25" stroke="#38bdf8" stroke-width="3" stroke-linecap="round"></path>
    <text x="574" y="160" class="layer-label" fill="#0369a1">蓄水或淋水检验</text>
    <text x="574" y="181" class="thin-label">最终不是“做完”，而是确认不渗漏</text>
  </g>
</svg>
"""


def client_step(step: dict[str, Any]) -> dict[str, Any]:
    """学生端 step 数据: 只保留讲解需要的字段, 剥离 source_refs / score_point_id 等内部权威。"""
    b = step.get("exam_binding") or {}
    return {
        "id": step.get("id"),
        "tab": step.get("tab"),
        "action": step.get("action"),
        "brief": step.get("brief"),
        "why": step.get("why"),
        "scoring_expression": step.get("scoring_expression"),
        "common_loss": step.get("common_loss"),
        "exam_binding": {"kind": b.get("kind"), "label": b.get("label"), "max_score": b.get("max_score")},
    }


def client_narration(schema: dict[str, Any]) -> dict[str, Any]:
    """学生端 narration 载荷: 只保留播放需要的字段, 剥离 kind/voice/boundary 等内部说明。"""
    n = schema.get("narration") or {}
    out: dict[str, Any] = {}
    opening = n.get("opening")
    if opening:
        out["opening"] = {"seconds": opening.get("seconds"), "script": opening.get("script")}
    out["steps"] = [
        {"step_id": s.get("step_id"), "seconds": s.get("seconds"), "script": s.get("script")}
        for s in n.get("steps") or []
    ]
    out["error_reveals"] = [
        {
            "error_id": r.get("error_id"),
            "jump_step_id": r.get("jump_step_id"),
            "seconds": r.get("seconds"),
            "script": r.get("script"),
            "correction_hint": r.get("correction_hint"),
        }
        for r in n.get("error_reveals") or []
    ]
    pf = n.get("practice_feedback") or {}
    if pf:
        out["practice_feedback"] = {
            "correct_script": pf.get("correct_script"),
            "incorrect_script": pf.get("incorrect_script"),
        }
    return out


def score_cards(schema: dict[str, Any]) -> str:
    cards = []
    for p in schema.get("scoring_points") or []:
        tier = esc(_TIER_LABEL.get(p.get("tier"), p.get("tier")))
        kws = " / ".join(esc(k) for k in p.get("keywords") or [])
        cards.append(
            f'<div class="error-card"><b>{tier} · 约 {esc(p.get("max_score"))} 分</b>'
            f'<span>写到这些词更稳：{kws}</span></div>'
        )
    return "".join(cards)


def error_cards(schema: dict[str, Any]) -> str:
    cards = []
    for e in schema.get("common_errors") or []:
        cards.append(
            '<button class="error-card" type="button" '
            f'data-jump="{esc(e.get("jump_step_id"))}" '
            f'data-error-id="{esc(e.get("id"))}" '
            f'data-error="{esc(e.get("text"))}">'
            f'<b>{esc(e.get("text"))}<span class="code">{esc(e.get("error_code"))}</span></b>'
            f'<span>{esc(e.get("why"))}</span></button>'
        )
    return "".join(cards)


def practice_options(schema: dict[str, Any]) -> str:
    practice = schema.get("practice") or {}
    options = []
    for o in practice.get("options") or []:
        correct = "true" if o.get("is_correct") else "false"
        options.append(
            f'<button class="option" type="button" data-correct="{correct}" '
            f'data-feedback="{esc(o.get("feedback"))}" aria-pressed="false">'
            f'<b>{esc(o.get("id"))}.</b> {esc(o.get("text"))}</button>'
        )
    return "".join(options)


# 全部交互逻辑(普通 JS, 单括号); 数据来自页面内的 #cardData JSON, 无 Python 插值。
_JS = r"""
const cardData = JSON.parse(document.getElementById("cardData").textContent);
const steps = cardData.steps;
const N = steps.length;
const ERRORS = N, PRACTICE = N + 1, SUMMARY = N + 2, TOTAL = N + 3;
const narr = cardData.narration || {};
const narrSteps = narr.steps || [];
const reveals = narr.error_reveals || [];
const pf = narr.practice_feedback || {};

const roofSvg = document.getElementById("roofSvg");
const stepEls = [...document.querySelectorAll("[data-layer]")];
const slides = {
  step: document.getElementById("slideStep"),
  errors: document.getElementById("slideErrors"),
  practice: document.getElementById("slidePractice"),
  summary: document.getElementById("slideSummary"),
};
const $ = (id) => document.getElementById(id);
const stepCount = $("stepCount"), stepTitle = $("stepTitle"), stepSay = $("stepSay");
const answerText = $("answerText"), whyText = $("whyText"), mistakeText = $("mistakeText"), sourceText = $("sourceText");
const jumpNote = $("jumpNote"), moreToggle = $("moreToggle"), moreBox = $("moreBox");
const deckCount = $("deckCount"), stepCountMini = $("stepCountMini"), progressBar = $("progressBar");
const prevBtn = $("prevBtn"), nextBtn = $("nextBtn"), narrPlay = $("narrPlay"), feedback = $("practiceFeedback");

let screen = 0, playing = false, playTimer = null;
const root = document.documentElement;

function scriptForStep(id){ const n = narrSteps.find(s => s.step_id === id); return n ? n.script : ""; }
function sourceLine(step){
  const b = step.exam_binding || {};
  if(b.kind === "signed_candidate")
    return `候选采分点${b.label ? " · " + b.label : ""}${b.max_score ? " · 约 " + b.max_score + " 分" : ""}（教研估分，非官方阅卷）`;
  return `教学理解步骤${b.label ? " · " + b.label : ""}（帮助你把工序讲完整，不单独计分）`;
}
function setMode(mode, errId){
  root.dataset.narrMode = mode;
  if(mode === "error" && errId) root.dataset.activeError = errId;
  else delete root.dataset.activeError;
}
function showSlide(type){ for(const k in slides) slides[k].classList.toggle("active", k === type); }

function renderStep(i, note){
  const step = steps[i];
  stepCount.textContent = "步骤 " + (i + 1) + " / " + N;
  stepTitle.textContent = step.action;
  stepSay.textContent = scriptForStep(step.id) || step.brief;
  answerText.textContent = step.scoring_expression;
  whyText.textContent = step.why;
  mistakeText.textContent = step.common_loss;
  sourceText.textContent = sourceLine(step);
  moreBox.hidden = true;
  moreToggle.textContent = "为什么 / 你常漏 ▸";
  if(note){ jumpNote.innerHTML = note; jumpNote.hidden = false; }
  else { jumpNote.hidden = true; jumpNote.textContent = ""; }
  root.dataset.activeLayer = step.id;
  root.dataset.narrIndex = String(i);
  stepEls.forEach((el) => {
    const idx = steps.findIndex(s => s.id === el.dataset.layer);
    el.classList.remove("active", "done");
    if(idx === i) el.classList.add("active");
    else if(idx > -1 && idx < i) el.classList.add("done");
  });
}

function goScreen(n, note){
  screen = Math.max(0, Math.min(TOTAL - 1, n));
  const isStep = screen < N;
  showSlide(isStep ? "step" : screen === ERRORS ? "errors" : screen === PRACTICE ? "practice" : "summary");
  if(isStep) renderStep(screen, note);
  prevBtn.disabled = screen === 0;
  nextBtn.textContent = screen === TOTAL - 1 ? "重新开始" : "下一步";
  const label = (screen + 1) + " / " + TOTAL;
  stepCountMini.textContent = label;
  deckCount.textContent = label;
  progressBar.style.width = (((screen + 1) / TOTAL) * 100) + "%";
  root.dataset.screen = String(screen);
  window.scrollTo(0, 0);
}

function playBtnUI(){
  if(!narrPlay) return;
  narrPlay.classList.toggle("playing", playing);
  narrPlay.setAttribute("aria-pressed", playing ? "true" : "false");
  narrPlay.textContent = playing ? "⏸ 暂停" : "▶ 听老师讲";
  root.dataset.narrPlaying = playing ? "true" : "false";
}
function scheduleNext(){
  const secs = ((narrSteps[screen] || {}).seconds || 9) * 1000;
  playTimer = setTimeout(() => {
    if(screen < N - 1){ goScreen(screen + 1); setMode("step"); scheduleNext(); }
    else stopPlay();
  }, secs);
}
function startPlay(){
  if(screen >= N) goScreen(0);
  playing = true; setMode("step"); playBtnUI(); scheduleNext();
}
function stopPlay(){ playing = false; clearTimeout(playTimer); playTimer = null; playBtnUI(); }
function togglePlay(){ playing ? stopPlay() : startPlay(); }
if(narrPlay) narrPlay.addEventListener("click", togglePlay);

function manualGo(n){ stopPlay(); goScreen(n); if(n < N) setMode("manual_step"); }
prevBtn.addEventListener("click", () => manualGo(screen - 1));
nextBtn.addEventListener("click", () => manualGo(screen === TOTAL - 1 ? 0 : screen + 1));
document.addEventListener("keydown", (e) => {
  if(e.key === "ArrowRight") manualGo(screen + 1);
  if(e.key === "ArrowLeft") manualGo(screen - 1);
});
moreToggle.addEventListener("click", () => {
  const willOpen = moreBox.hidden;
  moreBox.hidden = !willOpen;
  moreToggle.textContent = willOpen ? "收起 ▾" : "为什么 / 你常漏 ▸";
});

document.querySelectorAll(".error-card[data-jump]").forEach((b) => {
  b.addEventListener("click", () => {
    stopPlay();
    const i = steps.findIndex(s => s.id === b.dataset.jump);
    if(i < 0) return;
    const rv = reveals.find(r => r.error_id === b.dataset.errorId) || {};
    const note = "你刚点的是「<b>" + (b.dataset.error || "这类写法") + "</b>」——真正漏的是「<b>" + steps[i].action + "</b>」。" + (rv.correction_hint || "");
    goScreen(i, note);
    if(rv.script) stepSay.textContent = rv.script;
    setMode("error", b.dataset.errorId);
  });
});

document.querySelectorAll(".option").forEach((b) => {
  b.addEventListener("click", () => {
    stopPlay();
    document.querySelectorAll(".option").forEach(o => { o.setAttribute("aria-pressed", "false"); o.classList.remove("correct", "wrong"); });
    b.setAttribute("aria-pressed", "true");
    const correct = b.dataset.correct === "true";
    b.classList.add(correct ? "correct" : "wrong");
    feedback.classList.remove("correct", "wrong");
    feedback.classList.add("show", correct ? "correct" : "wrong");
    if(correct){
      feedback.textContent = "✅ " + (pf.correct_script || b.dataset.feedback || "");
      setMode("practice_correct");
      root.dataset.practiceResult = "correct";
    } else {
      const msg = pf.incorrect_script || b.dataset.feedback || "";
      feedback.textContent = "❌ " + msg;
      setMode("practice_incorrect");
      root.dataset.practiceResult = "incorrect";
      const rid = (cardData.practice && cardData.practice.review_step_id) || "reinforcement_layer";
      const i = steps.findIndex(s => s.id === rid);
      if(i >= 0) goScreen(i, "复测发现你漏了关键闭环——跳到「<b>" + steps[i].action + "</b>」对照一下。");
    }
  });
});

roofSvg.setAttribute("viewBox", "210 150 470 350");
setMode("idle");
goScreen(0);
const fromHash = Number((location.hash.match(/step=(\d+)/) || [])[1] || 0);
const fromQuery = Number(new URLSearchParams(location.search).get("step") || 0);
const sk = fromQuery || fromHash;
if(sk >= 1 && sk <= N) goScreen(sk - 1);
"""


def render(schema: dict[str, Any]) -> str:
    validate(schema)
    title = esc(schema.get("title"))
    practice = schema.get("practice") or {}
    data = trusted_json_for_script({
        "steps": [client_step(s) for s in (schema.get("steps") or [])],
        # 学生端只需 review_step_id 做答错回跳; 判分对错由按钮 data-correct 承载,
        # 不把 options[].is_correct / feedback 透进 #cardData (避免复测答案在 JSON 里明文双写)。
        # 注: data-correct 仍在 DOM, 是静态卡前端判分的固有项, 无服务端时无法真隐藏 (见 SCHEMA.md 复测题边界)。
        "practice": {"review_step_id": practice.get("review_step_id")},
        "narration": client_narration(schema),
    })
    authority = schema.get("authority") or {}
    judging = esc(authority.get("judging_authority_label"))
    student_boundary = esc(authority.get("student_boundary") or "图为教学示意，具体数值以教材和规范为准。")
    # HTML 注释内不能出现 "--"; 用原文(非实体转义)写 provenance, 仅做最小净化
    source_boundary_comment = str(authority.get("source_boundary") or "").replace("--", "—")
    judging_comment = str(authority.get("judging_authority_label") or "").replace("--", "—")
    warm = schema.get("warm_correction_html") or esc(schema.get("warm_correction"))
    memory_hook = esc(schema.get("memory_hook"))

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title} · 图解微课</title>
<style>{_CSS}</style>
</head>
<body>
<!--
created_by: deterministic render_card.py (luban diagram micro-lesson renderer · deck)
schema_version: {SCHEMA_VERSION}
purpose: paged one-point-per-screen diagram micro-lesson card (mobile WebView v0 baseline)
judging_authority: {judging_comment}
source_boundary: {source_boundary_comment}
notes: no OpenMAIC code copied; ../F16 html is v0 visual baseline only; not official grading.
-->
<main class="deck">
  <header class="deck-top">
    <span class="brandmini">鲁班图解微课 · {title}</span>
    <span class="deck-count" id="deckCount">1 / 11</span>
  </header>

  <section class="slide step active" id="slideStep" aria-label="工序讲解">
    <div class="stage">
      <div class="roof-wrap">
        {roof_svg()}
        <div class="legend" aria-label="图例">
          <span><i class="sw" style="background:#3a4b61"></i>原防水层</span>
          <span><i class="sw" style="background:#f4b740"></i>基层处理剂</span>
          <span><i class="sw" style="background:#9be7cf"></i>附加层</span>
          <span><i class="sw" style="background:#1b7f68"></i>新卷材</span>
        </div>
      </div>
    </div>
    <div class="step-point">
      <div class="ptop">
        <span class="eyebrow" id="stepCount">步骤 1 / 8</span>
        <button class="say-btn" id="narrPlay" type="button" aria-pressed="false">▶ 听老师讲</button>
      </div>
      <h2 id="stepTitle"></h2>
      <p class="step-say" id="stepSay"></p>
      <div class="point-box"><b>✍ 这样写才得分</b><p id="answerText"></p></div>
      <button class="more-toggle" id="moreToggle" type="button">为什么 / 你常漏 ▸</button>
      <div class="more" id="moreBox" hidden>
        <p class="more-line"><b>为什么：</b><span id="whyText"></span></p>
        <p class="more-line"><b>你常漏：</b><span id="mistakeText"></span></p>
        <p class="more-line muted" id="sourceText"></p>
      </div>
      <div class="jump-note" id="jumpNote" hidden></div>
    </div>
  </section>

  <section class="slide" id="slideErrors" aria-label="错因自查">
    <h2 class="aux-h">你常踩的坑</h2>
    <p class="aux-sub">点一个，我带你跳回那一步讲清楚。</p>
    <div class="error-grid">{error_cards(schema)}</div>
  </section>

  <section class="slide" id="slidePractice" aria-label="复测题">
    <h2 class="aux-h">复测一题</h2>
    <p class="aux-sub">{esc(practice.get("stem"))}</p>
    <div class="option-grid">{practice_options(schema)}</div>
    <div class="feedback" id="practiceFeedback" role="status"></div>
  </section>

  <section class="slide" id="slideSummary" aria-label="收束">
    <h2 class="aux-h">记住这套顺序</h2>
    <div class="hook">{memory_hook}</div>
    <div class="warm-box">{warm}</div>
    <div class="auth"><b>考试依据</b>：{student_boundary}
      <div class="auth-sub">非官方阅卷 · 图为教学示意 · 数值以教材 / 规范为准</div>
    </div>
  </section>

  <div class="stepnav" id="stepNav">
    <button class="control" id="prevBtn" type="button">上一步</button>
    <div class="stepnav-mid"><span id="stepCountMini">1 / 11</span><i class="mini-progress"><b id="progressBar"></b></i></div>
    <button class="control primary" id="nextBtn" type="button">下一步</button>
  </div>
</main>
<script type="application/json" id="cardData">{data}</script>
<script>{_JS}</script>
</body>
</html>"""


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    schema_path = Path(argv[1])
    out_path = Path(argv[2]) if len(argv) > 2 else schema_path.with_suffix(".rendered.html")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    html_out = render(schema)
    out_path.write_text(html_out, encoding="utf-8")
    print(f"rendered: {schema_path} -> {out_path}")
    print(
        f"  steps={len(schema.get('steps') or [])} "
        f"scoring_points={len(schema.get('scoring_points') or [])} "
        f"errors={len(schema.get('common_errors') or [])} "
        f"practice={'yes' if schema.get('practice') else 'no'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
