#!/usr/bin/env python3
"""图解微课卡确定性渲染器（luban_diagram_microlesson.v1）。

输入:一份考点 schema JSON。
输出:一张小程序 WebView 可承载的静态 HTML 卡:内联 SVG、内联 CSS、少量内联 JS。

边界:
- 渲染器只渲染 schema 内事实,不生成知识、不判分、不补采分点。
- 图形是确定性 SVG 示意,不是规范级节点详图。
- 交互只做 step reveal、错因跳转和复测反馈,不访问网络、不依赖外链。
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
  --bg:#f3f6f8;
  --paper:#fffdf8;
  --surface:#ffffff;
  --ink:#17202a;
  --muted:#637083;
  --line:#dfe6ee;
  --blue:#2563eb;
  --blue-2:#dbeafe;
  --green:#16815f;
  --green-2:#dff4ea;
  --amber:#b96b12;
  --amber-2:#fff0d7;
  --red:#c24130;
  --red-2:#fde8e3;
  --membrane:#3a4b61;
  --primer:#f4b740;
  --patch:#1b7f68;
  --shadow:0 18px 40px rgba(31,41,55,.12);
}
*{box-sizing:border-box}
html,body{max-width:100%;overflow-x:hidden}
body{
  margin:0;
  background:linear-gradient(180deg,#eef4f8 0%,#f7f8f4 48%,#f2f5f7 100%);
  color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif;
  line-height:1.5;
}
button{font:inherit}
.page{max-width:1180px;margin:0 auto;padding:24px 16px 40px}
.topline{display:flex;gap:10px;align-items:center;color:var(--muted);font-size:13px;margin-bottom:10px}
.mark{width:34px;height:34px;border-radius:11px;background:var(--blue);display:grid;place-items:center;box-shadow:0 8px 18px rgba(37,99,235,.25)}
.mark svg{width:19px;height:19px;stroke:#fff}
h1{margin:0;font-size:clamp(26px,4vw,42px);letter-spacing:0;line-height:1.18}
.subtitle{max-width:820px;margin:12px 0 14px;color:#526173;font-size:16px}
.quicknav{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 20px}
.qn{display:inline-flex;align-items:center;min-height:40px;padding:8px 14px;border-radius:999px;background:#fff;border:1px solid var(--line);color:#33425a;font-size:13px;font-weight:700;text-decoration:none;box-shadow:0 6px 14px rgba(31,41,55,.06)}
.qn:hover{border-color:#93b7f6;color:#153e91}
.teacher-tag{display:inline-block;font-size:11px;font-weight:800;color:#1d4ed8;background:#dce8ff;border-radius:999px;padding:3px 10px;margin-bottom:8px;letter-spacing:.02em}
.jump-note{margin:0 0 12px;border-radius:14px;padding:11px 13px;background:#fff4e6;border:1px solid #f3cf9b;color:#8a4d05;font-size:13px;line-height:1.55}
.jump-note b{color:#7a3d00}
.bar .hint{margin:-4px 0 12px;color:var(--muted);font-size:13px}
.layout{display:grid;grid-template-columns:minmax(0,1.08fr) minmax(330px,.62fr);gap:18px;align-items:start;min-width:0}
.lesson,.side,.bar{background:rgba(255,255,255,.88);border:1px solid rgba(203,213,225,.9);box-shadow:var(--shadow);min-width:0}
.lesson{border-radius:22px;overflow:hidden}
.lesson-head{padding:18px 20px 14px;display:flex;gap:14px;justify-content:space-between;align-items:flex-start;border-bottom:1px solid var(--line);background:rgba(255,255,255,.82)}
.lesson-head h2{margin:0 0 6px;font-size:18px}
.lesson-head p{margin:0;color:var(--muted);font-size:13px}
.goal-chip{flex:0 0 auto;border-radius:999px;background:var(--amber-2);color:#87530f;border:1px solid #f5d39d;padding:8px 12px;font-size:12px;font-weight:700}
.visual{padding:18px;background:radial-gradient(circle at 12% 0%,rgba(37,99,235,.10),transparent 28%),linear-gradient(180deg,#fffdf8,#f9fbfd)}
.roof-wrap{position:relative;background:var(--paper);border:1px solid #eadfcf;border-radius:18px;overflow:hidden;min-height:430px}
.svg-frame{width:100%;max-width:100%;aspect-ratio:16/10;min-height:360px;display:block;overflow:hidden}
.callout{position:absolute;left:18px;top:18px;width:min(300px,44%);background:rgba(255,255,255,.94);border:1px solid var(--line);border-radius:14px;padding:12px 13px;box-shadow:0 12px 28px rgba(15,23,42,.10)}
.callout b{display:block;font-size:14px;margin-bottom:4px}
.callout span{display:block;color:var(--muted);font-size:12px}
.legend{position:absolute;right:16px;bottom:14px;display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;max-width:380px}
.legend span{display:inline-flex;align-items:center;gap:6px;padding:6px 8px;border-radius:10px;background:rgba(255,255,255,.9);border:1px solid var(--line);color:#465364;font-size:12px}
.sw{width:14px;height:8px;border-radius:4px;display:inline-block}
.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:14px 18px 18px;border-top:1px solid var(--line);background:#fff}
.step-tab{min-height:54px;border:1px solid var(--line);background:#f8fafc;color:#475569;border-radius:13px;padding:8px 9px;text-align:left;cursor:pointer;transition:background .18s ease,border-color .18s ease,transform .18s ease}
.step-tab:hover{transform:translateY(-1px);border-color:#b9c6d6}
.step-tab[aria-selected="true"]{background:#eff6ff;color:#153e91;border-color:#93b7f6;box-shadow:0 8px 20px rgba(37,99,235,.12)}
.step-tab small{display:block;color:inherit;opacity:.72;font-size:11px;margin-bottom:2px}
.step-tab strong{display:block;font-size:13px;line-height:1.25}
.side{border-radius:22px;padding:18px;position:sticky;top:16px}
.eyebrow{color:var(--blue);font-size:12px;font-weight:800;letter-spacing:0;margin-bottom:8px}
.side h2{margin:0 0 10px;font-size:22px;line-height:1.25}
.side .brief{margin:0 0 14px;color:var(--muted);font-size:14px}
.info-card{border-radius:16px;padding:13px;margin-top:10px;border:1px solid var(--line);background:#fbfdff}
.info-card h3{margin:0 0 7px;font-size:14px}
.info-card p{margin:0;color:#405066;font-size:13px}
.info-card.why{background:#eef4ff;border-color:#c3d8fb}
.info-card.why h3{color:#1d4ed8}
.info-card.answer{background:var(--green-2);border-color:#b7e3cf}
.info-card.answer h3{color:#0f6b4f}
.info-card.mistake{background:var(--red-2);border-color:#f4b8ae}
.info-card.mistake h3{color:#9a3412}
.info-card.source{background:#f8fafc}
.controls{margin-top:14px;display:grid;grid-template-columns:1fr 1.3fr;gap:10px}
.control{min-height:48px;border-radius:14px;border:1px solid var(--line);cursor:pointer;background:#fff;color:#334155;font-weight:700}
.control.primary{background:var(--blue);color:#fff;border-color:var(--blue)}
.progress{margin-top:14px;height:8px;border-radius:999px;background:#e6edf5;overflow:hidden}
.progress i{display:block;height:100%;width:12.5%;background:linear-gradient(90deg,#2563eb,#16a37f);border-radius:inherit;transition:width .22s ease}
.narration{margin:14px 18px 0;border:1px solid #c8dbfb;border-radius:16px;background:#f1f6ff;padding:13px 14px}
.narr-top{display:flex;align-items:center;gap:12px}
.narr-play{flex:0 0 auto;min-height:44px;padding:10px 16px;border-radius:12px;border:1px solid var(--blue);background:var(--blue);color:#fff;font-weight:800;cursor:pointer;display:inline-flex;align-items:center;gap:8px;white-space:nowrap}
.narr-play.playing{background:#fff;color:var(--blue)}
.narr-meta{color:var(--muted);font-size:12px;line-height:1.45}
.narr-meta b{color:#1d4ed8;font-weight:800}
.narr-sub{margin-top:11px;border-radius:12px;background:#fff;border:1px solid #cddcfb;padding:11px 13px;color:#1f2d44;font-size:14px;line-height:1.65;min-height:46px}
.narr-track{margin-top:10px;height:7px;border-radius:999px;background:#dce6f6;overflow:hidden}
.narr-track i{display:block;height:100%;width:0;background:linear-gradient(90deg,#2563eb,#16a37f);border-radius:inherit;transition:width .35s ease}
.panel-row{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:18px}
.bar{border-radius:20px;padding:16px 18px}
.bar h2{font-size:17px;margin:0 0 10px}
.score-grid,.error-grid{display:grid;gap:10px}
.score-card,.error-card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px}
.score-card b,.error-card b{display:block;font-size:13px;margin-bottom:5px}
.score-card span,.error-card span{color:var(--muted);font-size:12px}
.error-card{cursor:pointer;text-align:left}
.error-card:hover{border-color:#93b7f6;background:#f8fbff}
.code{display:inline-block;margin-left:6px;padding:1px 7px;border-radius:7px;background:#fee2d8;color:#9a3412;font-family:ui-monospace,Menlo,monospace;font-size:11px}
.practice{margin-top:18px;border-radius:20px;padding:18px;background:#fff;border:1px solid rgba(203,213,225,.9);box-shadow:var(--shadow)}
.practice h2{font-size:18px;margin:0 0 8px}
.practice p{font-size:14px;color:#3f4d5e;margin:0 0 12px}
.option-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.option{min-height:58px;text-align:left;border-radius:14px;border:1px solid var(--line);background:#fff;padding:10px 12px;cursor:pointer;color:#263241}
.option[aria-pressed="true"].correct{border-color:#8bd0ad;background:#e8f7f0}
.option[aria-pressed="true"].wrong{border-color:#f1aaa0;background:#fde8e3}
.feedback{margin-top:12px;border-radius:13px;padding:11px 12px;background:#f8fafc;border:1px solid var(--line);color:#405066;font-size:13px;line-height:1.55;display:none}
.feedback.show{display:block}
.feedback.correct{background:#e8f7f0;border-color:#9bd6b6;color:#0f6b4f;font-weight:600}
.feedback.wrong{background:#fde8e3;border-color:#f1aaa0;color:#9a3412}
.auth{margin-top:18px;border:1px solid var(--line);border-radius:16px;background:#fff;padding:13px;color:var(--muted);font-size:12px}
.layer-label{font-size:14px;fill:#334155;font-weight:700}
.thin-label{font-size:12px;fill:#64748b}
.step-layer{opacity:.10;transition:opacity .22s ease,filter .22s ease}
.step-layer.active{opacity:1;filter:drop-shadow(0 8px 14px rgba(37,99,235,.14))}
.step-layer.done{opacity:.36}
@media (max-width:900px){
  .layout,.panel-row{grid-template-columns:1fr}
  .side{position:static}
  .steps{grid-template-columns:repeat(2,1fr)}
  .option-grid{grid-template-columns:1fr}
}
@media (max-width:520px){
  .page,.layout,.lesson,.side,.bar,.roof-wrap{width:100%;max-width:100%}
  .page{padding:16px 10px 28px}
  .topline{align-items:flex-start;flex-wrap:wrap}
  .topline span,h1,.subtitle,.lesson-head h2,.lesson-head p,.goal-chip{white-space:normal;overflow-wrap:anywhere;word-break:break-word}
  h1{font-size:21px;line-height:1.26}
  .subtitle{font-size:13.5px;line-height:1.6;margin-bottom:12px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  .quicknav{margin-bottom:14px;gap:6px}
  .qn{flex:1 1 28%;justify-content:center;min-height:44px;padding:8px 4px;font-size:12px}
  .lesson-head{display:block;padding:14px 14px 12px}
  .lesson-head h2{font-size:16px}
  .goal-chip{display:inline-block;margin-top:10px}
  .visual{padding:8px}
  .narration{margin:12px 8px 0;padding:11px}
  .narr-top{flex-wrap:wrap;gap:8px}
  .narr-sub{font-size:13.5px}
  .roof-wrap{min-height:auto}
  .svg-frame{height:auto;min-height:0;width:100%;aspect-ratio:470/350}
  .callout{display:none}
  .legend{position:relative;right:auto;bottom:auto;justify-content:flex-start;padding:8px 10px 10px;max-width:100%;gap:6px}
  .legend span{font-size:11px;padding:5px 7px}
  .thin-label{display:none}
  .layer-label{font-size:15px}
  .steps{grid-template-columns:1fr 1fr;gap:8px;padding:12px}
  .step-tab{min-height:48px}
  .side{padding:14px}
  .side h2{font-size:19px}
  .panel-row{margin-top:14px}
  .option{min-height:52px}
}
@media (prefers-reduced-motion:reduce){
  *{transition:none!important;scroll-behavior:auto!important}
}
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
<svg class="svg-frame" id="roofSvg" viewBox="0 0 900 560" role="img" aria-labelledby="svgTitle svgDesc">
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
            f'<div class="score-card"><b>{tier} · 约 {esc(p.get("max_score"))} 分</b>'
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


def narration_module(schema: dict[str, Any]) -> str:
    narration = schema.get("narration") or {}
    steps = narration.get("steps") or []
    if not steps:
        return ""
    total = narration.get("total_seconds_hint") or sum(int(n.get("seconds") or 0) for n in steps)
    n = len(steps)
    return (
        '<div class="narration" id="narration">'
        '<div class="narr-top">'
        f'<button class="narr-play" id="narrPlay" type="button" aria-pressed="false">▶ 听老师讲 {esc(total)} 秒</button>'
        f'<div class="narr-meta">字幕式旁白 · 自动从第 1 步讲到第 {n} 步<br><b id="narrStatus">未开始</b></div>'
        '</div>'
        f'<div class="narr-sub" id="narrSub">点「听老师讲」，老师带你把这道题从第 1 步讲到第 {n} 步。</div>'
        '<div class="narr-track" aria-hidden="true"><i id="narrBar"></i></div>'
        '</div>'
    )


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


def render(schema: dict[str, Any]) -> str:
    validate(schema)
    title = esc(schema.get("title"))
    data = trusted_json_for_script({
        "steps": [client_step(s) for s in (schema.get("steps") or [])],
        "practice": schema.get("practice") or {},
        "narration": client_narration(schema),
    })
    authority = schema.get("authority") or {}
    source_boundary = esc(authority.get("source_boundary"))
    judging = esc(authority.get("judging_authority_label"))
    artifact = esc(authority.get("judging_artifact_id"))
    # 学生端只展示面向学生的边界说明; raw source_ref / artifact id 只进 HTML 注释
    student_boundary = esc(authority.get("student_boundary") or "图为教学示意，具体数值以教材和规范为准。")
    # HTML 注释内不能出现 "--"; 用原文(非实体转义)写 provenance, 仅做最小净化
    source_boundary_comment = str(authority.get("source_boundary") or "").replace("--", "—")
    judging_comment = str(authority.get("judging_authority_label") or "").replace("--", "—")
    warm = schema.get("warm_correction_html") or esc(schema.get("warm_correction"))
    memory_hook = esc(schema.get("memory_hook"))
    scenario = schema.get("scenario") or {}

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · 图解微课</title>
<style>{_CSS}</style>
</head>
<body>
<!--
created_by: deterministic render_card.py (luban diagram micro-lesson renderer)
schema_version: {SCHEMA_VERSION}
purpose: first formal Luban diagram micro-lesson card (mobile WebView v0 baseline)
judging_authority: {judging_comment}
source_boundary: {source_boundary_comment}
notes: no OpenMAIC code copied; ../F16 html is v0 visual baseline only; not official grading.
-->
<main class="page">
  <div class="topline">
    <div class="mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 18h16"></path><path d="M7 18V8l5-3 5 3v10"></path><path d="M9 18v-6h6v6"></path>
      </svg>
    </div>
    <span>鲁班图解微课 · 看图 + 听老师讲 + 练一题</span>
  </div>
  <h1>{title}: 起鼓割补工序</h1>
  <p class="subtitle">{esc(schema.get("learning_goal"))}</p>
  <nav class="quicknav" aria-label="快速跳转">
    <a class="qn" href="#lesson">① 看工序</a>
    <a class="qn" href="#errors">② 错因自查</a>
    <a class="qn" href="#practice">③ 复测一题</a>
  </nav>

  <section class="layout" aria-label="{title} 图解微课">
    <article class="lesson" id="lesson">
      <div class="lesson-head">
        <div>
          <h2>剖面里看工序，不背散点</h2>
          <p>{esc(scenario.get("caption"))}</p>
        </div>
        <div class="goal-chip">目标: 错因跳转 / 采分表达 / 复测题</div>
      </div>

      <div class="visual">
        <div class="roof-wrap">
          <div class="callout" id="callout">
            <b>先看坏在哪里</b>
            <span>卷材下有气体或水汽，受热膨胀后顶起防水层。</span>
          </div>
          {roof_svg()}
          <div class="legend" aria-label="图例">
            <span><i class="sw" style="background:#3a4b61"></i>原防水层</span>
            <span><i class="sw" style="background:#f4b740"></i>基层处理剂</span>
            <span><i class="sw" style="background:#9be7cf"></i>附加层</span>
            <span><i class="sw" style="background:#1b7f68"></i>新卷材</span>
          </div>
        </div>
      </div>
      {narration_module(schema)}
      <div class="steps" id="steps" role="tablist" aria-label="起鼓割补 8 步"></div>
    </article>

    <aside class="side" aria-live="polite">
      <div class="jump-note" id="jumpNote" hidden></div>
      <div class="eyebrow" id="stepCount">步骤 1 / 8</div>
      <span class="teacher-tag">老师拿着图给你讲</span>
      <h2 id="stepTitle"></h2>
      <p class="brief" id="stepBrief"></p>
      <div class="info-card why"><h3>为什么这么做</h3><p id="whyText"></p></div>
      <div class="info-card answer"><h3>这样写才得分</h3><p id="answerText"></p></div>
      <div class="info-card mistake"><h3>你常漏什么</h3><p id="mistakeText"></p></div>
      <div class="info-card source"><h3>这一步算不算分</h3><p id="sourceText"></p></div>
      <div class="controls">
        <button class="control" id="prevBtn" type="button">上一步</button>
        <button class="control primary" id="nextBtn" type="button">下一步</button>
      </div>
      <div class="progress" aria-hidden="true"><i id="progressBar"></i></div>
    </aside>
  </section>

  <section class="panel-row" aria-label="采分点和错因跳转">
    <div class="bar">
      <h2>候选采分点 · 写到才稳</h2>
      <p class="hint">教研估分的关键得分表达，非官方阅卷。</p>
      <div class="score-grid">{score_cards(schema)}</div>
    </div>
    <div class="bar" id="errors">
      <h2>错因节点跳转</h2>
      <p class="hint">点一个你常犯的错，我直接带你跳到漏掉的那一步。</p>
      <div class="error-grid">{error_cards(schema)}</div>
    </div>
  </section>

  <section class="practice" id="practice" aria-label="复测题">
    <h2>{esc((schema.get("practice") or {}).get("title"))}</h2>
    <p>{esc((schema.get("practice") or {}).get("stem"))}</p>
    <div class="option-grid">{practice_options(schema)}</div>
    <div class="feedback" id="practiceFeedback" role="status"></div>
  </section>

  <section class="bar" style="margin-top:18px">
    <h2>讲解收束</h2>
    <div class="score-card"><b>暖纠正</b><span>{warm}</span></div>
    <div class="score-card" style="margin-top:10px"><b>记忆钩子</b><span>{memory_hook}</span></div>
  </section>

  <div class="auth">
    <b>考试依据</b>：{student_boundary}
    <div style="margin-top:8px;font-weight:700;color:#9a3412">非官方阅卷 · 图为教学示意 · 具体数值以教材 / 规范为准</div>
  </div>
</main>
<script type="application/json" id="cardData">{data}</script>
<script>
const cardData = JSON.parse(document.getElementById("cardData").textContent);
let current = 0;
const stepEls = [...document.querySelectorAll("[data-layer]")];
const roofSvg = document.getElementById("roofSvg");
const stepsWrap = document.getElementById("steps");
const callout = document.getElementById("callout");
const stepCount = document.getElementById("stepCount");
const stepTitle = document.getElementById("stepTitle");
const stepBrief = document.getElementById("stepBrief");
const whyText = document.getElementById("whyText");
const jumpNote = document.getElementById("jumpNote");
const answerText = document.getElementById("answerText");
const mistakeText = document.getElementById("mistakeText");
const sourceText = document.getElementById("sourceText");
const progressBar = document.getElementById("progressBar");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");

// ---- 字幕式旁白(无 TTS / 无音频): 文本全部来自 schema 的 narration ----
const narration = cardData.narration || {{}};
const narrSteps = narration.steps || [];
const narrErrorReveals = narration.error_reveals || [];
const narrPF = narration.practice_feedback || {{}};
const narrPlayBtn = document.getElementById("narrPlay");
const narrSub = document.getElementById("narrSub");
const narrBar = document.getElementById("narrBar");
const narrStatus = document.getElementById("narrStatus");
const firstStepId = (cardData.steps[0] || {{}}).id;

// 播放时间线 = opening(可选) + 各 step; opening 保持 step1 高亮
const narrSeq = [];
if(narration.opening && narration.opening.script){{
  narrSeq.push({{mode:"opening", step_id:firstStepId, seconds:Number(narration.opening.seconds)||7, script:narration.opening.script, label:"开场"}});
}}
narrSteps.forEach((s,k)=>narrSeq.push({{mode:"step", step_id:s.step_id, seconds:Number(s.seconds)||9, script:s.script, label:`第 ${{k+1}} 步`}}));
const narrTotalMs = narrSeq.reduce((a,s)=>a + s.seconds*1000, 0);
let narrIndex = 0, narrTimer = null, narrPlaying = false, narrStarted = false, segStart = 0, segRemaining = 0;

function setNarrMode(mode, errorId){{
  document.documentElement.dataset.narrMode = mode;
  if(mode === "error" && errorId) document.documentElement.dataset.activeError = errorId;
  else delete document.documentElement.dataset.activeError;
}}
function narrUpdateState(){{
  document.documentElement.dataset.narrPlaying = narrPlaying ? "true" : "false";
  document.documentElement.dataset.narrIndex = String(narrIndex);
}}
function narrButton(){{
  if(!narrPlayBtn) return;
  narrPlayBtn.classList.toggle("playing", narrPlaying);
  narrPlayBtn.setAttribute("aria-pressed", narrPlaying ? "true" : "false");
  narrPlayBtn.textContent = narrPlaying ? "⏸ 暂停讲解" : (narrStarted ? "▶ 继续讲解" : `▶ 听老师讲 ${{Math.round(narrTotalMs/1000)}} 秒`);
}}
function scriptForStep(stepId){{
  const n = narrSteps.find(s=>s.step_id === stepId);
  return n ? n.script : "";
}}
function narrShow(i){{
  const seq = narrSeq[i];
  if(!seq) return;
  const si = cardData.steps.findIndex(s=>s.id === seq.step_id);
  if(si >= 0) render(si, true);
  if(narrSub) narrSub.textContent = seq.script;
  const doneMs = narrSeq.slice(0,i+1).reduce((a,s)=>a + s.seconds*1000, 0);
  if(narrBar) narrBar.style.width = `${{narrTotalMs ? (doneMs/narrTotalMs)*100 : 0}}%`;
  if(narrStatus) narrStatus.textContent = `播放中 · ${{seq.label}}`;
  setNarrMode(seq.mode === "opening" ? "opening" : "step");
  narrUpdateState();
}}
function narrPlaySeg(){{
  narrShow(narrIndex);
  segRemaining = (narrSeq[narrIndex].seconds||9) * 1000;
  segStart = performance.now();
  narrTimer = setTimeout(narrAdvance, segRemaining);
}}
function narrAdvance(){{
  if(narrIndex >= narrSeq.length - 1){{ narrFinish(); return; }}
  narrIndex += 1;
  narrPlaySeg();
}}
function narrFinish(){{
  narrPlaying = false; narrStarted = false; segRemaining = 0;
  clearTimeout(narrTimer); narrTimer = null;
  if(narrStatus) narrStatus.textContent = "讲完啦，可重听或自己复述一遍";
  narrButton(); narrUpdateState();
}}
function narrStart(){{
  if(!narrSeq.length) return;
  if(!narrStarted){{ narrIndex = 0; narrPlaying = true; narrStarted = true; narrButton(); narrPlaySeg(); return; }}
  narrPlaying = true; narrButton();
  segStart = performance.now();
  narrTimer = setTimeout(narrAdvance, Math.max(0, segRemaining));
  narrUpdateState();
}}
function narrPause(){{
  if(!narrPlaying) return;
  narrPlaying = false;
  clearTimeout(narrTimer); narrTimer = null;
  segRemaining = Math.max(0, segRemaining - (performance.now() - segStart));
  narrButton(); narrUpdateState();
}}
function narrToggle(){{ narrPlaying ? narrPause() : narrStart(); }}
if(narrPlayBtn) narrPlayBtn.addEventListener("click", narrToggle);

// 手动翻到某步: 暂停自动旁白, 显示该步普通讲解
function manualStep(index){{
  narrPause();
  render(index, true);
  const sc = scriptForStep(cardData.steps[current].id);
  if(narrSub && sc) narrSub.textContent = sc;
  if(narrStatus) narrStatus.textContent = "你手动翻到这一步";
  setNarrMode("manual_step");
  narrUpdateState();
}}

cardData.steps.forEach((step,index)=>{{
  const btn = document.createElement("button");
  btn.className = "step-tab";
  btn.type = "button";
  btn.setAttribute("role","tab");
  btn.dataset.stepId = step.id;
  btn.innerHTML = `<small>步骤 ${{index + 1}}</small><strong>${{step.tab}}</strong>`;
  btn.addEventListener("click",()=>manualStep(index));
  stepsWrap.appendChild(btn);
}});

function sourceLine(step){{
  // 学生端: 只说"候选采分点 / 教学理解步骤", 不露 source_ref / 编号
  const b = step.exam_binding || {{}};
  if(b.kind === "signed_candidate"){{
    return `候选采分点${{b.label ? ` · ${{b.label}}` : ""}}${{b.max_score ? ` · 约 ${{b.max_score}} 分` : ""}}（教研估分，非官方阅卷）`;
  }}
  return `教学理解步骤${{b.label ? ` · ${{b.label}}` : ""}}（帮助你把工序讲完整，不单独计分）`;
}}

function render(index, updateHash=false, note=null){{
  current = Math.max(0,Math.min(cardData.steps.length - 1,index));
  const step = cardData.steps[current];
  stepCount.textContent = `步骤 ${{current + 1}} / ${{cardData.steps.length}}`;
  stepTitle.textContent = step.action;
  stepBrief.textContent = step.brief;
  whyText.textContent = step.why;
  if(callout) callout.innerHTML = `<b>${{step.tab}}</b><span>${{step.why}}</span>`;
  answerText.textContent = step.scoring_expression;
  mistakeText.textContent = step.common_loss;
  sourceText.textContent = sourceLine(step);
  if(note){{ jumpNote.innerHTML = note; jumpNote.hidden = false; }}
  else {{ jumpNote.hidden = true; jumpNote.textContent = ""; }}
  progressBar.style.width = `${{((current + 1) / cardData.steps.length) * 100}}%`;
  prevBtn.disabled = current === 0;
  nextBtn.textContent = current === cardData.steps.length - 1 ? "回到第一步" : "下一步";
  document.documentElement.dataset.activeLayer = step.id;
  stepEls.forEach((el)=>{{
    const idx = cardData.steps.findIndex(s=>s.id === el.dataset.layer);
    el.classList.remove("active","done");
    if(idx === current) el.classList.add("active");
    if(idx > -1 && idx < current) el.classList.add("done");
  }});
  [...stepsWrap.children].forEach((btn,i)=>btn.setAttribute("aria-selected",i === current ? "true" : "false"));
  if(updateHash) history.replaceState(null,"",`#step=${{current + 1}}`);
}}

function applyResponsiveSvgView(){{
  if(window.matchMedia("(max-width:520px)").matches){{
    roofSvg.setAttribute("viewBox","210 150 470 350");
  }}else{{
    roofSvg.setAttribute("viewBox","0 0 900 560");
  }}
}}

// 错因卡: 暂停自动旁白 → 跳到对应工序 → 专项讲解 + 横幅 + narrMode=error
document.querySelectorAll(".error-card").forEach((btn)=>{{
  btn.addEventListener("click",()=>{{
    narrPause();
    const target = btn.dataset.jump;
    const errId = btn.dataset.errorId;
    const idx = cardData.steps.findIndex(s=>s.id === target);
    if(idx < 0) return;
    const reveal = narrErrorReveals.find(r=>r.error_id === errId) || {{}};
    const errText = btn.dataset.error || "这类写法";
    const hint = reveal.correction_hint || "";
    render(idx, true, `你刚点的是「<b>${{errText}}</b>」——真正漏的是「<b>${{cardData.steps[idx].tab}}</b>」。${{hint}}`);
    if(narrSub) narrSub.textContent = reveal.script || cardData.steps[idx].why;
    if(narrStatus) narrStatus.textContent = "错因专项讲解";
    setNarrMode("error", errId);
    narrUpdateState();
    document.getElementById("lesson").scrollIntoView({{behavior:"smooth", block:"start"}});
  }});
}});

// 复测题: 答对/答错都要讲清原因; 答错跳回 review_step_id
document.querySelectorAll(".option").forEach((btn)=>{{
  btn.addEventListener("click",()=>{{
    narrPause();
    document.querySelectorAll(".option").forEach(o=>{{o.setAttribute("aria-pressed","false");o.classList.remove("correct","wrong");}});
    btn.setAttribute("aria-pressed","true");
    const correct = btn.dataset.correct === "true";
    btn.classList.add(correct ? "correct" : "wrong");
    const feedback = document.getElementById("practiceFeedback");
    feedback.classList.remove("correct","wrong");
    feedback.classList.add("show", correct ? "correct" : "wrong");
    feedback.textContent = (correct ? "✅ " : "❌ ") + (btn.dataset.feedback || "");
    if(correct){{
      const msg = narrPF.correct_script || "你抓住了核心得分逻辑。";
      if(narrSub) narrSub.textContent = msg;
      if(narrStatus) narrStatus.textContent = "复测点评 · 答对";
      setNarrMode("practice_correct");
    }} else {{
      const msg = narrPF.incorrect_script || (btn.dataset.feedback || "");
      const reviewId = (cardData.practice && cardData.practice.review_step_id) || "reinforcement_layer";
      const idx = cardData.steps.findIndex(s=>s.id === reviewId);
      if(idx >= 0){{
        render(idx, true, `复测发现你漏了关键闭环——跳到「<b>${{cardData.steps[idx].tab}}</b>」对照一下。`);
        document.getElementById("lesson").scrollIntoView({{behavior:"smooth", block:"start"}});
      }}
      if(narrSub) narrSub.textContent = msg;
      if(narrStatus) narrStatus.textContent = "复测点评 · 答错";
      setNarrMode("practice_incorrect");
    }}
    narrUpdateState();
  }});
}});

prevBtn.addEventListener("click",()=>manualStep(current - 1));
nextBtn.addEventListener("click",()=> current === cardData.steps.length - 1 ? manualStep(0) : manualStep(current + 1));
document.addEventListener("keydown",(event)=>{{
  if(event.key === "ArrowRight") manualStep(current + 1);
  if(event.key === "ArrowLeft") manualStep(current - 1);
}});
window.addEventListener("resize",applyResponsiveSvgView);
applyResponsiveSvgView();
const fromHash = Number((location.hash.match(/step=(\\d+)/) || [])[1] || 1) - 1;
const fromQuery = Number(new URLSearchParams(location.search).get("step") || "") - 1;
render(Number.isFinite(fromQuery) && fromQuery >= 0 ? fromQuery : fromHash, false);
setNarrMode("idle");
narrButton();
narrUpdateState();
</script>
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
