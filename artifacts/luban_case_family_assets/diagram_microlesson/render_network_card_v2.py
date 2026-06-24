#!/usr/bin/env python3
"""N01 网络计划关键线路 v2 · 先猜后证的白板式窄渲染器。

目标不是替代生产判分，而是验证一个教学形态：
- 不在首屏高亮关键线路，先让学生暴露直觉错误。
- 用 deterministic CPM 派生早/迟时间和总时差，前端只做 reveal。
- 最后把图上判断压缩成考试采分句。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from render_network_card import (
    END,
    NODE_H,
    NODE_W,
    SCHEMA_VERSION,
    START,
    TEMPLATE_TYPE,
    compute_cpm,
    esc,
    layout,
    trusted_json_for_script,
    validate,
)


def node_title(node: str, card: dict[str, Any]) -> str:
    if node == START:
        return "开始"
    if node == END:
        return "结束"
    for activity in card["question_data"]["activities"]:
        if activity["id"] == node:
            return str(activity.get("label") or node)
    return node


def critical_edge_set(card: dict[str, Any]) -> set[tuple[str, str]]:
    path = card["question_data"]["expected"]["critical_path"]
    return set(zip(path, path[1:]))


def network_svg(card: dict[str, Any], cpm: dict[str, Any], lay: dict[str, Any]) -> str:
    pos = lay["pos"]
    crit_nodes = cpm["critical"]
    crit_edges = critical_edge_set(card)
    dur = cpm["dur"]
    parts: list[str] = []
    parts.append(
        f'<svg class="net-svg stage-guess" id="netSvg" viewBox="0 0 {lay["width"]:.0f} {lay["height"] + 30:.0f}" '
        'role="img" aria-label="网络计划图，关键线路会在推导到最后一步时显示" preserveAspectRatio="xMidYMid meet">'
    )
    parts.append(
        '<defs>'
        '<marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto">'
        '<path d="M0 0 L9 4.5 L0 9 z" fill="#728197"></path></marker>'
        '<marker id="arrowHot" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto">'
        '<path d="M0 0 L9 4.5 L0 9 z" fill="#c2410c"></path></marker>'
        '</defs>'
    )

    for dep in card["question_data"]["dependencies"]:
        f, t = dep["from"], dep["to"]
        x1, y1 = pos[f]
        x2, y2 = pos[t]
        sx = x1 + NODE_W / 2
        ex = x2 - NODE_W / 2
        cls = "edge critical" if (f, t) in crit_edges else "edge"
        parts.append(
            f'<line class="{cls}" data-from="{esc(f)}" data-to="{esc(t)}" '
            f'x1="{sx:.0f}" y1="{y1:.0f}" x2="{ex:.0f}" y2="{y2:.0f}" marker-end="url(#arrow)"></line>'
        )

    for node, (cx, cy) in pos.items():
        x = cx - NODE_W / 2
        y = cy - NODE_H / 2
        is_crit = node in crit_nodes
        ncls = "node critical" if is_crit else "node"
        es_v, ef_v, ls_v, lf_v, tf_v, ff_v = (cpm[k][node] for k in ("es", "ef", "ls", "lf", "tf", "ff"))
        parts.append(f'<g class="{ncls}" data-node-id="{esc(node)}">')
        parts.append(f'<rect x="{x:.0f}" y="{y:.0f}" rx="10" width="{NODE_W}" height="{NODE_H}"></rect>')
        parts.append(f'<text class="n-label" x="{cx:.0f}" y="{cy - 4:.0f}">{esc(node_title(node, card))}</text>')
        if node not in (START, END):
            parts.append(f'<text class="n-dur" x="{cx:.0f}" y="{cy + 14:.0f}">{dur[node]} 天</text>')
        parts.append(f'<text class="t-early" x="{x + 3:.0f}" y="{y - 7:.0f}">早 {es_v}-{ef_v}</text>')
        parts.append(f'<text class="t-late" x="{x + NODE_W - 3:.0f}" y="{y - 7:.0f}">迟 {ls_v}-{lf_v}</text>')
        if node not in (START, END):
            zero_cls = " zero" if tf_v == 0 else ""
            parts.append(
                f'<text class="float{zero_cls}" x="{cx:.0f}" y="{y + NODE_H + 15:.0f}">'
                f'总{tf_v}/自由{ff_v}</text>'
            )
        parts.append("</g>")

    parts.append("</svg>")
    return "".join(parts)


def render_options(options: list[dict[str, Any]], cls: str) -> str:
    return "".join(
        f'<button class="{cls}" type="button" data-opt="{esc(o["id"])}" aria-pressed="false">'
        f'<b>{esc(o["id"])}.</b> {esc(o.get("text"))}</button>'
        for o in options
    )


def render_error_cards(card: dict[str, Any]) -> str:
    return "".join(
        f'<button class="err-card" type="button" data-error-id="{esc(r["id"])}" data-jump="{esc(r["jump_step_id"])}">'
        f'<b>{esc(r.get("title"))}</b><span>{esc(r.get("correction_hint"))}</span></button>'
        for r in card.get("error_reveals") or []
    )


_CSS = r"""
*{box-sizing:border-box}
html,body{margin:0;max-width:100%;overflow-x:hidden}
body{background:#eef3f7;color:#17202a;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif;line-height:1.48}
button{font:inherit}
.page{max-width:1040px;margin:0 auto;padding:18px 14px 40px}
.topline{display:flex;gap:8px;align-items:center;color:#176b7a;font-size:12px;font-weight:900;margin-bottom:7px}
.dot{width:7px;height:7px;border-radius:50%;background:#f97316;box-shadow:0 0 0 4px rgba(249,115,22,.13)}
h1{margin:0 0 6px;font-size:24px;line-height:1.22;letter-spacing:0}
.goal{margin:0 0 12px;color:#45566d;font-size:14px}
.layout{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(320px,.88fr);gap:14px;align-items:start}
.board,.panel{background:#fff;border:1px solid #d7e1eb;border-radius:16px;box-shadow:0 12px 28px rgba(31,41,55,.06)}
.board{padding:12px}
.stem{margin:0 0 10px;color:#334155;font-size:14px}
.cold-strip{margin:0 0 10px;border:1px solid #fed7aa;background:#fff7ed;border-radius:13px;padding:10px 11px;color:#7c2d12;font-size:13px}
.cold-strip b{display:block;color:#9a3412;font-size:14px;margin-bottom:3px}
.diagram-shell{position:relative;border:1px solid #dbe5ee;border-radius:14px;background:linear-gradient(180deg,#fbfdff,#f6f9fb);padding:8px;overflow:hidden}
.net-svg{width:100%;height:auto;display:block}
.edge{stroke:#8290a3;stroke-width:2.2;opacity:.86}
.edge.critical{stroke:#b6c2cf;opacity:.74}
.net-svg.stage-deps .edge{stroke:#394b63;stroke-width:3;opacity:1}
.net-svg.stage-early .edge,.net-svg.stage-late .edge,.net-svg.stage-float .edge{opacity:.72}
.net-svg.stage-critical .edge.critical,.net-svg.stage-score .edge.critical{stroke:#c2410c;stroke-width:4.6;opacity:1;marker-end:url(#arrowHot)}
.node rect{fill:#f9fbfd;stroke:#8da0b5;stroke-width:2}
.node.critical rect{stroke:#bdc8d4}
.net-svg.stage-critical .node.critical rect,.net-svg.stage-score .node.critical rect{fill:#fff3e9;stroke:#c2410c;stroke-width:3}
.n-label{text-anchor:middle;font-size:17px;font-weight:900;fill:#1f2d44}
.n-dur{text-anchor:middle;font-size:11px;fill:#607086}
.t-early,.t-late{display:none;font-size:10px;font-weight:800}
.t-early{fill:#1d4ed8}.t-late{text-anchor:end;fill:#0f766e}
.net-svg.stage-early .t-early,.net-svg.stage-late .t-late,.net-svg.stage-score .t-early,.net-svg.stage-score .t-late{display:block}
.float{display:none;text-anchor:middle;font-size:10px;font-weight:900;fill:#b45309}
.float.zero{fill:#14765b}
.net-svg.stage-float .float,.net-svg.stage-critical .float,.net-svg.stage-score .float{display:block}
.legend{display:flex;gap:12px;flex-wrap:wrap;margin-top:8px;color:#5d6f84;font-size:12px}
.legend i{display:inline-block;width:20px;border-top:4px solid #c2410c;vertical-align:middle;margin-right:5px}
.scoreline{display:none;margin-top:10px;border:1px solid #fed7aa;background:#fff7ed;border-radius:13px;padding:11px 12px}
html[data-stage="score"] .scoreline{display:block}
.scoreline small{display:block;color:#9a3412;font-weight:900;margin-bottom:4px}
.scoreline strong{display:block;color:#7c2d12;font-size:14px}
.panel{padding:12px}
.trap{border:1px solid #fed7aa;background:#fff7ed;border-radius:14px;padding:12px;margin-bottom:12px}
.trap .wrong{font-weight:900;color:#9a3412;font-size:15px;margin-bottom:8px}
.trap p{margin:6px 0;color:#5b3b19;font-size:13px}
.trap .fix{margin-top:9px;border-top:1px dashed #fdba74;padding-top:8px;color:#7c2d12;font-weight:800}
.guess h2,.inline-guess h2,.narr h2,.bar h2{font-size:16px;margin:0 0 8px}
.inline-guess{margin-top:10px;border:1px solid #d7e1eb;background:#fff;border-radius:14px;padding:11px}
.inline-guess .guess-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.guess-grid,.opt-grid,.err-grid{display:grid;gap:8px}
.guess-opt,.opt,.err-card,.step-tab{border:1px solid #d7e1eb;background:#fff;border-radius:12px;cursor:pointer;text-align:left}
.guess-opt,.opt{min-height:46px;padding:10px 12px;color:#26364a}
.guess-opt[aria-pressed="true"].correct,.opt[aria-pressed="true"].correct{border-color:#77bf9a;background:#e9f8f0}
.guess-opt[aria-pressed="true"].wrong,.opt[aria-pressed="true"].wrong{border-color:#fb923c;background:#fff1e7}
.feedback{display:none;margin-top:10px;border-radius:12px;padding:10px 12px;font-size:13px}
.feedback.show{display:block}.feedback.correct{background:#e9f8f0;color:#0f6b4f;border:1px solid #8bd0ad}.feedback.wrong{background:#fff1e7;color:#9a3412;border:1px solid #fb923c}
.narr{margin-top:12px;border:1px solid #c8dbfb;background:#f2f7ff;border-radius:14px;padding:12px}
.narr h2{color:#1d4ed8}.narr p{margin:0;color:#24364f;font-size:14px;min-height:44px}
.action-line{margin-top:9px;color:#0f766e;font-size:13px;font-weight:900}
.jump-note{margin-top:10px;border-radius:12px;padding:9px 11px;background:#fff7ed;border:1px solid #fed7aa;color:#92400e;font-size:13px}
.jump-note[hidden]{display:none}
.steps{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:10px}
.step-tab{min-height:48px;padding:8px 10px;color:#526174}
.step-tab[aria-selected="true"]{background:#eaf2ff;border-color:#8db7f7;color:#153e91}
.step-tab small{display:block;font-size:11px;font-weight:800;opacity:.72}.step-tab strong{display:block;font-size:13px}
.controls{display:flex;gap:9px;margin-top:10px}
.controls button{flex:1;min-height:44px;border-radius:12px;border:1px solid #d7e1eb;background:#fff;font-weight:900;cursor:pointer}
.controls .primary{background:#176b7a;color:#fff;border-color:#176b7a}
.bar{margin-top:12px;border:1px solid #d7e1eb;background:#fff;border-radius:14px;padding:12px}
.bar .hint{margin:0 0 9px;color:#65758b;font-size:13px}
.err-card{padding:10px 11px}
.err-card:hover{border-color:#fb923c;background:#fff7ed}
.err-card b{display:block;font-size:13px;margin-bottom:3px}.err-card span{color:#65758b;font-size:12px}
.faded{border:1px solid #dbe5ee;background:#f9fbfd;border-radius:13px;padding:11px;margin-top:10px}
.blank{font-weight:900;color:#22324a;background:#fff;border:1px dashed #adc0d4;border-radius:10px;padding:10px;margin:8px 0;font-size:13px}
.model{display:none;border-radius:10px;background:#e9f8f0;border:1px solid #8bd0ad;color:#0f6b4f;padding:10px;font-size:13px;font-weight:800}
.model.show{display:block}
.linkbtn{border:0;background:transparent;color:#176b7a;font-weight:900;padding:4px 0;cursor:pointer}
.auth{margin-top:12px;color:#627184;font-size:12px}
@media (max-width:880px){
 .page{max-width:440px;padding-bottom:86px}
 .layout{display:block}
 .panel{margin-top:12px}
 .controls{position:sticky;bottom:0;z-index:40;margin:10px -2px 0;padding:10px 2px calc(10px + env(safe-area-inset-bottom));background:rgba(255,255,255,.96);border-top:1px solid #d7e1eb;box-shadow:0 -9px 26px rgba(31,41,55,.12);backdrop-filter:blur(9px)}
 .controls button{min-height:48px}
}
@media (max-width:460px){
 h1{font-size:21px}
 .page{padding-left:10px;padding-right:10px}
 .inline-guess .guess-grid{grid-template-columns:1fr}
 .steps{grid-template-columns:1fr}
}
@media (prefers-reduced-motion:reduce){
 *{scroll-behavior:auto!important;transition:none!important}
}
"""

_JS = r"""
const data = JSON.parse(document.getElementById("cardData").textContent);
const svg = document.getElementById("netSvg");
const narrTitle = document.getElementById("narrTitle");
const narrScript = document.getElementById("narrScript");
const actionLine = document.getElementById("actionLine");
const jumpNote = document.getElementById("jumpNote");
const stepsWrap = document.getElementById("steps");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
let cur = -1;

function stageFor(step){
  const focus = step && step.focus || [];
  if (focus.includes("score_sentence")) return "score";
  if (focus.includes("critical_path")) return "critical";
  if (focus.includes("total_float")) return "float";
  if (focus.includes("late_time")) return "late";
  if (focus.includes("early_time")) return "early";
  if (focus.includes("dependencies")) return "deps";
  return "guess";
}
function setStage(stage){
  svg.className.baseVal = `net-svg stage-${stage}`;
  document.documentElement.dataset.stage = stage;
}
function showCold(){
  cur = -1;
  setStage("guess");
  narrTitle.textContent = "先猜一次，再看为什么";
  narrScript.textContent = data.first_guess.question;
  actionLine.textContent = "目标：不是听懂答案，而是能自己写出采分句。";
  jumpNote.hidden = true;
  [...stepsWrap.children].forEach(b => b.setAttribute("aria-selected", "false"));
  prevBtn.disabled = true;
  nextBtn.textContent = "开始白板推导";
}
function showStep(i, note){
  cur = Math.max(0, Math.min(data.explanation_steps.length - 1, i));
  const step = data.explanation_steps[cur];
  setStage(stageFor(step));
  narrTitle.textContent = `第 ${cur + 1} 步 · ${step.title}`;
  narrScript.textContent = step.script;
  actionLine.textContent = step.score_action || "";
  if (note){
    jumpNote.innerHTML = note;
    jumpNote.hidden = false;
  } else {
    jumpNote.hidden = true;
    jumpNote.textContent = "";
  }
  [...stepsWrap.children].forEach((b, idx) => b.setAttribute("aria-selected", idx === cur ? "true" : "false"));
  prevBtn.disabled = false;
  nextBtn.textContent = cur === data.explanation_steps.length - 1 ? "回到先猜" : "下一步";
}
data.explanation_steps.forEach((step, idx) => {
  const btn = document.createElement("button");
  btn.className = "step-tab";
  btn.type = "button";
  btn.setAttribute("role", "tab");
  btn.innerHTML = `<small>第 ${idx + 1} 步</small><strong>${step.title}</strong>`;
  btn.addEventListener("click", () => showStep(idx));
  stepsWrap.appendChild(btn);
});
prevBtn.addEventListener("click", () => cur <= 0 ? showCold() : showStep(cur - 1));
nextBtn.addEventListener("click", () => cur < 0 ? showStep(0) : (cur === data.explanation_steps.length - 1 ? showCold() : showStep(cur + 1)));

function wireChoice(selector, feedbackId, answer, options, onWrongStepId){
  document.querySelectorAll(selector).forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(selector).forEach(o => {
        o.setAttribute("aria-pressed", "false");
        o.classList.remove("correct", "wrong");
      });
      btn.setAttribute("aria-pressed", "true");
      const correct = btn.dataset.opt === answer;
      btn.classList.add(correct ? "correct" : "wrong");
      const fb = document.getElementById(feedbackId);
      fb.className = `feedback show ${correct ? "correct" : "wrong"}`;
      const opt = options.find(o => o.id === btn.dataset.opt) || {};
      fb.textContent = (correct ? "对。 " : "先别急。 ") + (opt.feedback || (correct ? data.practice.correct_script : data.practice.incorrect_script));
      if (!correct && onWrongStepId){
        const idx = data.explanation_steps.findIndex(s => s.id === onWrongStepId);
        if (idx >= 0) showStep(idx, "这类错通常要回到“总时差”这一步校正。");
      }
    });
  });
}
wireChoice(".guess-opt", "guessFeedback", data.first_guess.answer, data.first_guess.options, null);
wireChoice(".opt", "practiceFeedback", data.practice.answer, data.practice.options, data.practice.review_step_id);

document.querySelectorAll(".err-card").forEach(btn => {
  btn.addEventListener("click", () => {
    const reveal = data.error_reveals.find(r => r.id === btn.dataset.errorId) || {};
    const idx = data.explanation_steps.findIndex(s => s.id === reveal.jump_step_id);
    showStep(idx >= 0 ? idx : 0, `你担心的是「<b>${reveal.title || ""}</b>」：${reveal.correction_hint || ""}`);
    narrScript.textContent = reveal.script || narrScript.textContent;
    document.querySelector(".board").scrollIntoView({behavior:"smooth", block:"start"});
  });
});
document.getElementById("showModelBtn").addEventListener("click", () => {
  document.getElementById("modelAnswer").classList.add("show");
});
showCold();
"""


def render(card: dict[str, Any]) -> str:
    cpm = validate(card)
    lay = layout(card, cpm)
    title = esc(card.get("title"))
    qd = card["question_data"]
    auth = card.get("authority") or {}
    first_guess = card.get("first_guess") or {}
    faded = card.get("faded_practice") or {}
    cold = card.get("cold_open") or {}
    scoring = esc(cold.get("make_it_score"))
    client = trusted_json_for_script(
        {
            "first_guess": first_guess,
            "explanation_steps": [
                {
                    "id": s["id"],
                    "title": s.get("title"),
                    "focus": s.get("focus") or [],
                    "script": s.get("script"),
                    "score_action": s.get("score_action"),
                }
                for s in card.get("explanation_steps") or []
            ],
            "error_reveals": [
                {
                    "id": r["id"],
                    "title": r.get("title"),
                    "jump_step_id": r["jump_step_id"],
                    "script": r.get("script"),
                    "correction_hint": r.get("correction_hint"),
                }
                for r in card.get("error_reveals") or []
            ],
            "practice": card.get("practice") or {},
        }
    )

    return f"""<!doctype html>
<html lang="zh-CN" data-stage="guess">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>{title} · v2</title>
<style>{_CSS}</style>
</head>
<body>
<!--
created_by: deterministic render_network_card_v2.py
schema_version: {SCHEMA_VERSION}
template_type: {TEMPLATE_TYPE}
authority_status: {esc(auth.get("status"))}
boundary: browser JS only reveals pre-rendered derivations; CPM validation runs at build time; candidate teaching prototype only.
-->
<main class="page">
  <div class="topline"><span class="dot"></span><span>N01 · 先猜后证 · 网络计划</span></div>
  <h1>{title}</h1>
  <p class="goal">{esc(card.get("student_goal"))}</p>
  <section class="layout">
    <div class="board">
      <p class="stem">{esc(qd.get("stem"))}</p>
      <div class="cold-strip"><b>错法警报：{esc(cold.get("wrong_answer"))}</b>{esc(cold.get("lost_score"))}</div>
      <div class="diagram-shell">
        {network_svg(card, cpm, lay)}
      </div>
      <div class="legend"><span><i></i>关键线路最后才亮</span><span>早/迟时间与时差按步骤出现</span></div>
      <div class="inline-guess">
        <h2>先猜一次</h2>
        <div class="guess-grid">{render_options(first_guess.get("options") or [], "guess-opt")}</div>
        <div class="feedback" id="guessFeedback" role="status"></div>
      </div>
      <div class="scoreline">
        <small>考试采分句</small>
        <strong>{scoring}</strong>
      </div>
      <div class="narr">
        <h2 id="narrTitle"></h2>
        <p id="narrScript"></p>
        <div class="action-line" id="actionLine"></div>
        <div class="jump-note" id="jumpNote" hidden></div>
      </div>
      <div class="steps" id="steps" role="tablist" aria-label="白板推导步骤"></div>
      <div class="controls">
        <button id="prevBtn" type="button">上一步</button>
        <button class="primary" id="nextBtn" type="button">开始白板推导</button>
      </div>
    </div>
    <aside class="panel">
      <div class="bar">
        <h2>常见错误定位</h2>
        <p class="hint">不是泛泛讲错，而是点错法后跳回对应步骤。</p>
        <div class="err-grid">{render_error_cards(card)}</div>
      </div>
      <div class="bar">
        <h2>半撤提示小练</h2>
        <p class="hint">{esc(faded.get("prompt"))}</p>
        <div class="blank">{esc(faded.get("blank_sentence"))}</div>
        <button class="linkbtn" type="button" id="showModelBtn">看采分句</button>
        <div class="model" id="modelAnswer">{esc(faded.get("model_answer"))}</div>
      </div>
      <div class="bar">
        <h2>复测</h2>
        <p class="hint">{esc((card.get("practice") or {}).get("question"))}</p>
        <div class="opt-grid">{render_options((card.get("practice") or {}).get("options") or [], "opt")}</div>
        <div class="feedback" id="practiceFeedback" role="status"></div>
      </div>
      <div class="auth">
        <b>边界</b>：{esc(auth.get("student_boundary"))}
      </div>
    </aside>
  </section>
</main>
<script type="application/json" id="cardData">{client}</script>
<script>{_JS}</script>
</body>
</html>"""


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: render_network_card_v2.py N01_network_keypath_v2.json [out.html]")
        return 2
    card_path = Path(argv[1])
    out_path = Path(argv[2]) if len(argv) > 2 else card_path.with_suffix(".rendered.html")
    card = json.loads(card_path.read_text(encoding="utf-8"))
    out_path.write_text(render(card), encoding="utf-8")
    cpm = compute_cpm(card)
    non_critical = [a["id"] for a in card["question_data"]["activities"] if cpm["tf"][a["id"]] > 0]
    print(f"rendered: {card_path} -> {out_path}")
    print(
        f"  duration={cpm['project_duration']} "
        f"critical_path={'-'.join(card['question_data']['expected']['critical_path'])} "
        f"non_critical={non_critical}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
