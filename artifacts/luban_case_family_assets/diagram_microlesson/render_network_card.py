#!/usr/bin/env python3
"""网络计划关键线路图解卡 · 确定性窄渲染器（template_type=network_plan_keypath）。

输入: 一份 N01_network_keypath.json (luban_diagram_microlesson.v1)。
输出: 一张静态 HTML 卡, 自动把 activities/dependencies 画成 SVG 网络图, 高亮关键线路。

单一权威边界:
- 关键线路 / 时差是"由 activity/duration/dependencies 确定"的事实, 不是画得像就行。
- build 期有一个独立确定性 CPM 校验器 compute_cpm(): 既校验 JSON 的 expected(候选答案)自洽,
  又派生 ES/EF/LS/LF 供展示。它是校验器, 不是前端判断器。
- 前端 renderer(浏览器里的 JS)不做任何计算/判断, 只读已渲染好的图与 JSON 文案做 reveal / 跳转 / 复测反馈。
- 不接 RAG / 前端 LLM / TTS / 音频 / 外链; 不写 learner state; 不冒充官方评分。
"""
from __future__ import annotations

import html
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "luban_diagram_microlesson.v1"
TEMPLATE_TYPE = "network_plan_keypath"
START, END = "START", "END"


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def trusted_json_for_script(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


# ---------------------------------------------------------------------------
# 独立确定性 CPM 校验器 / 派生器 (build 期; 不是前端)
# ---------------------------------------------------------------------------
def build_graph(card: dict[str, Any]) -> tuple[dict[str, int], dict[str, list[str]], dict[str, list[str]]]:
    qd = card["question_data"]
    dur: dict[str, int] = {START: 0, END: 0}
    for a in qd["activities"]:
        dur[a["id"]] = int(a["duration"])
    succ: dict[str, list[str]] = {n: [] for n in dur}
    preds: dict[str, list[str]] = {n: [] for n in dur}
    for dep in qd["dependencies"]:
        f, t = dep["from"], dep["to"]
        if f not in dur or t not in dur:
            raise ValueError(f"dependency references unknown node: {dep}")
        succ[f].append(t)
        preds[t].append(f)
    return dur, succ, preds


def topo_order(dur: dict[str, int], succ: dict[str, list[str]], preds: dict[str, list[str]]) -> list[str]:
    indeg = {n: len(preds[n]) for n in dur}
    q = deque([n for n in dur if indeg[n] == 0])
    order: list[str] = []
    while q:
        n = q.popleft()
        order.append(n)
        for s in succ[n]:
            indeg[s] -= 1
            if indeg[s] == 0:
                q.append(s)
    if len(order) != len(dur):
        raise ValueError("network has a cycle; activity-on-node plan must be a DAG")
    return order


def compute_cpm(card: dict[str, Any]) -> dict[str, Any]:
    dur, succ, preds = build_graph(card)
    order = topo_order(dur, succ, preds)
    es, ef, ls, lf = {}, {}, {}, {}
    rank: dict[str, int] = {}
    for n in order:
        es[n] = max((ef[p] for p in preds[n]), default=0)
        ef[n] = es[n] + dur[n]
        rank[n] = (max((rank[p] for p in preds[n]), default=-1) + 1)
    project_duration = max(ef.values())
    for n in reversed(order):
        lf[n] = min((ls[s] for s in succ[n]), default=project_duration)
        ls[n] = lf[n] - dur[n]
    tf = {n: ls[n] - es[n] for n in dur}
    ff = {n: (min((es[s] for s in succ[n]), default=ef[n]) - ef[n]) for n in dur}
    critical = {n for n in dur if tf[n] == 0}
    return {
        "dur": dur, "succ": succ, "preds": preds, "order": order, "rank": rank,
        "es": es, "ef": ef, "ls": ls, "lf": lf, "tf": tf, "ff": ff,
        "project_duration": project_duration, "critical": critical,
    }


def validate(card: dict[str, Any]) -> dict[str, Any]:
    if card.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {card.get('schema_version')!r}")
    if card.get("template_type") != TEMPLATE_TYPE:
        raise ValueError(f"this renderer only handles template_type={TEMPLATE_TYPE!r}")

    qd = card.get("question_data") or {}
    acts = qd.get("activities") or []
    if not (5 <= len(acts) <= 7):
        raise ValueError(f"activities count must be 5-7 (got {len(acts)})")
    expected = qd.get("expected") or {}

    cpm = compute_cpm(card)

    # 独立校验: JSON 候选答案必须和确定性计算一致
    exp_cp = expected.get("critical_path") or []
    if set(exp_cp) != cpm["critical"]:
        raise ValueError(f"expected.critical_path {sorted(set(exp_cp))} != computed {sorted(cpm['critical'])}")
    if int(expected.get("project_duration")) != cpm["project_duration"]:
        raise ValueError(f"expected.project_duration {expected.get('project_duration')} != computed {cpm['project_duration']}")
    for a in acts:
        aid = a["id"]
        ef = (expected.get("float") or {}).get(aid) or {}
        if int(ef.get("total_float")) != cpm["tf"][aid]:
            raise ValueError(f"{aid} total_float expected {ef.get('total_float')} != computed {cpm['tf'][aid]}")
        if int(ef.get("free_float")) != cpm["ff"][aid]:
            raise ValueError(f"{aid} free_float expected {ef.get('free_float')} != computed {cpm['ff'][aid]}")

    # 至少一条并行路径 + 至少一个非关键工作(float>0)
    if max(cpm["rank"].values()) < 2:
        raise ValueError("graph too shallow to show a critical path")
    if not any(cpm["tf"][a["id"]] > 0 for a in acts):
        raise ValueError("need at least one non-critical activity (total_float>0) to demonstrate float")

    step_ids = {s.get("id") for s in card.get("explanation_steps") or []}
    if len(step_ids) < 2:
        raise ValueError("need >=2 explanation_steps")
    for s in card.get("explanation_steps") or []:
        if not str(s.get("script") or "").strip():
            raise ValueError(f"explanation_step script empty: {s.get('id')!r}")
        if not (s.get("evidence_refs") or []):
            raise ValueError(f"explanation_step needs evidence_refs: {s.get('id')!r}")
    for r in card.get("error_reveals") or []:
        if r.get("jump_step_id") not in step_ids:
            raise ValueError(f"error_reveal jump_step_id not found: {r.get('jump_step_id')!r}")
        if not str(r.get("script") or "").strip() or not str(r.get("correction_hint") or "").strip():
            raise ValueError(f"error_reveal needs script+correction_hint: {r.get('id')!r}")
    p = card.get("practice") or {}
    opt_ids = {o.get("id") for o in p.get("options") or []}
    if p.get("answer") not in opt_ids:
        raise ValueError("practice.answer must match an option id")
    if p.get("review_step_id") not in step_ids:
        raise ValueError("practice.review_step_id must match an explanation_step id")
    return cpm


# ---------------------------------------------------------------------------
# 确定性布局: 按 rank 分列(x), 同列按出现顺序排(y)
# ---------------------------------------------------------------------------
COL, ROW, NODE_W, NODE_H, PAD = 165, 100, 78, 56, 44


def layout(card: dict[str, Any], cpm: dict[str, Any]) -> dict[str, Any]:
    rank = cpm["rank"]
    nodes_order = [START] + [a["id"] for a in card["question_data"]["activities"]] + [END]
    by_rank: dict[int, list[str]] = {}
    for n in nodes_order:
        by_rank.setdefault(rank[n], []).append(n)
    max_rank = max(by_rank)
    max_rows = max(len(v) for v in by_rank.values())
    pos: dict[str, tuple[float, float]] = {}
    for r, ns in by_rank.items():
        offset = (max_rows - len(ns)) / 2.0
        for i, n in enumerate(ns):
            cx = PAD + r * COL + NODE_W / 2
            cy = PAD + (offset + i) * ROW + NODE_H / 2
            pos[n] = (cx, cy)
    width = PAD * 2 + max_rank * COL + NODE_W
    height = PAD * 2 + (max_rows - 1) * ROW + NODE_H
    return {"pos": pos, "width": width, "height": height}


def node_title(node: str, card: dict[str, Any]) -> str:
    if node == START:
        return "开始"
    if node == END:
        return "结束"
    for a in card["question_data"]["activities"]:
        if a["id"] == node:
            return f'{esc(a["label"])}'
    return esc(node)


def network_svg(card: dict[str, Any], cpm: dict[str, Any], lay: dict[str, Any]) -> str:
    pos = lay["pos"]
    crit = cpm["critical"]
    dur = cpm["dur"]
    parts: list[str] = []
    parts.append(
        f'<svg class="net-svg" id="netSvg" viewBox="0 0 {lay["width"]:.0f} {lay["height"]:.0f}" '
        'role="img" aria-label="网络计划箭线图，自动高亮总时差为0的关键线路" '
        'preserveAspectRatio="xMidYMid meet">'
    )
    parts.append(
        '<defs>'
        '<marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto">'
        '<path d="M0 0 L9 4.5 L0 9 z" fill="#64748b"></path></marker>'
        '<marker id="arrowC" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto">'
        '<path d="M0 0 L9 4.5 L0 9 z" fill="#c2410c"></path></marker>'
        '</defs>'
    )
    # edges
    for dep in card["question_data"]["dependencies"]:
        f, t = dep["from"], dep["to"]
        x1, y1 = pos[f]; x2, y2 = pos[t]
        sx = x1 + NODE_W / 2; ex = x2 - NODE_W / 2
        is_crit = f in crit and t in crit
        cls = "edge critical" if is_crit else "edge"
        marker = "url(#arrowC)" if is_crit else "url(#arrow)"
        parts.append(
            f'<line class="{cls}" data-from="{esc(f)}" data-to="{esc(t)}" '
            f'x1="{sx:.0f}" y1="{y1:.0f}" x2="{ex:.0f}" y2="{y2:.0f}" marker-end="{marker}"></line>'
        )
    # nodes
    for node, (cx, cy) in pos.items():
        x = cx - NODE_W / 2; y = cy - NODE_H / 2
        is_crit = node in crit
        ncls = "node critical" if is_crit else "node"
        es, ef, ls, lf, tf, ff = (cpm[k][node] for k in ("es", "ef", "ls", "lf", "tf", "ff"))
        parts.append(f'<g class="{ncls}" data-node-id="{esc(node)}">')
        parts.append(f'<rect x="{x:.0f}" y="{y:.0f}" rx="12" width="{NODE_W}" height="{NODE_H}"></rect>')
        parts.append(f'<text class="n-label" x="{cx:.0f}" y="{cy-3:.0f}">{node_title(node, card)}</text>')
        if node not in (START, END):
            parts.append(f'<text class="n-dur" x="{cx:.0f}" y="{cy+14:.0f}">{dur[node]} 天</text>')
        # 派生时间标签(默认隐藏, 由 step focus 显示)
        parts.append(f'<text class="t-early" x="{x+4:.0f}" y="{y-6:.0f}">早 {es}-{ef}</text>')
        parts.append(f'<text class="t-late" x="{x+NODE_W-4:.0f}" y="{y-6:.0f}">迟 {ls}-{lf}</text>')
        if node not in (START, END) and tf > 0:
            parts.append(
                f'<text class="float" data-node-id="{esc(node)}" data-total-float="{tf}" data-free-float="{ff}" '
                f'x="{cx:.0f}" y="{y+NODE_H+15:.0f}">总{tf}/自由{ff}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


_CSS = r"""
*{box-sizing:border-box}
html,body{max-width:100%;overflow-x:hidden;margin:0}
body{background:#f3f6f8;color:#17202a;line-height:1.55;
 font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}
.page{max-width:980px;margin:0 auto;padding:18px 14px 36px}
.eyebrow{color:#1d4ed8;font-size:12px;font-weight:800;margin-bottom:6px}
h1{margin:0 0 6px;font-size:22px;line-height:1.25}
.goal{margin:0 0 8px;color:#4a5a6e;font-size:14px}
.stem{margin:0 0 14px;color:#33425a;font-size:14px;background:#fff;border:1px solid #dfe6ee;border-radius:12px;padding:11px 13px}
.diagram{background:#fff;border:1px solid #dfe6ee;border-radius:16px;padding:10px;overflow:hidden}
.net-svg{width:100%;max-width:100%;height:auto;display:block}
.edge{stroke:#94a3b8;stroke-width:2}
.edge.critical{stroke:#cbd5e1;stroke-width:2}
.net-svg.focus-deps .edge{stroke:#475569;stroke-width:2.5}
.net-svg.focus-critical .edge.critical{stroke:#c2410c;stroke-width:4}
.node rect{fill:#f8fafc;stroke:#94a3b8;stroke-width:2}
.node.critical rect{fill:#f8fafc;stroke:#cbd5e1}
.net-svg.focus-critical .node.critical rect{fill:#fff1e8;stroke:#c2410c;stroke-width:3}
.n-label{text-anchor:middle;font-size:17px;font-weight:800;fill:#1f2d44}
.n-dur{text-anchor:middle;font-size:11px;fill:#64748b}
.t-early,.t-late{font-size:10px;fill:#1d4ed8;display:none}
.t-late{text-anchor:end;fill:#0f766e}
.net-svg.focus-early .t-early{display:block}
.net-svg.focus-late .t-late{display:block}
.float{text-anchor:middle;font-size:10px;fill:#b45309;display:none}
.net-svg.focus-critical .float{display:block}
.legend{display:flex;gap:12px;flex-wrap:wrap;margin-top:8px;color:#5b6b7d;font-size:12px}
.legend i{display:inline-block;width:18px;height:0;border-top:3px solid #c2410c;vertical-align:middle;margin-right:5px}
.narr{margin-top:12px;border:1px solid #c8dbfb;background:#f1f6ff;border-radius:14px;padding:12px}
.narr .title{font-weight:800;font-size:14px;color:#1d4ed8;margin-bottom:6px}
.narr .script{font-size:14px;color:#1f2d44;min-height:42px}
.jump-note{margin-top:10px;border-radius:12px;padding:10px 12px;background:#fff4e6;border:1px solid #f3cf9b;color:#8a4d05;font-size:13px}
.jump-note[hidden]{display:none}
.steps{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.step-tab{flex:1 1 40%;min-height:46px;border:1px solid #dfe6ee;background:#fff;border-radius:12px;padding:8px 10px;
 text-align:left;cursor:pointer;color:#475569}
.step-tab[aria-selected="true"]{background:#eff6ff;border-color:#93b7f6;color:#153e91}
.step-tab small{display:block;font-size:11px;opacity:.7}
.step-tab strong{display:block;font-size:13px}
.controls{display:flex;gap:10px;margin-top:10px}
.controls button{flex:1;min-height:46px;border-radius:12px;border:1px solid #dfe6ee;background:#fff;font-weight:700;cursor:pointer}
.controls .primary{background:#2563eb;color:#fff;border-color:#2563eb}
.bar{margin-top:16px;background:#fff;border:1px solid #dfe6ee;border-radius:14px;padding:14px}
.bar h2{font-size:16px;margin:0 0 4px}
.bar .hint{margin:0 0 10px;color:#64748b;font-size:13px}
.err-grid{display:grid;gap:10px}
.err-card{text-align:left;border:1px solid #dfe6ee;border-radius:12px;background:#fff;padding:11px;cursor:pointer}
.err-card:hover{border-color:#f1aaa0;background:#fff8f6}
.err-card b{display:block;font-size:13px;margin-bottom:4px}
.err-card span{color:#64748b;font-size:12px}
.opt-grid{display:grid;gap:10px}
.opt{min-height:48px;text-align:left;border:1px solid #dfe6ee;border-radius:12px;background:#fff;padding:10px 12px;cursor:pointer}
.opt[aria-pressed="true"].correct{border-color:#8bd0ad;background:#e8f7f0}
.opt[aria-pressed="true"].wrong{border-color:#f1aaa0;background:#fde8e3}
.feedback{margin-top:12px;border-radius:12px;padding:11px 12px;border:1px solid #dfe6ee;background:#f8fafc;font-size:13px;display:none}
.feedback.show{display:block}
.feedback.correct{background:#e8f7f0;border-color:#9bd6b6;color:#0f6b4f}
.feedback.wrong{background:#fde8e3;border-color:#f1aaa0;color:#9a3412}
.auth{margin-top:16px;border:1px solid #dfe6ee;border-radius:12px;background:#fff;padding:12px;color:#64748b;font-size:12px}
@media (max-width:520px){
 .page{padding:14px 10px 28px}
 h1{font-size:19px}
 .step-tab{flex:1 1 100%}
}
"""


def render(card: dict[str, Any]) -> str:
    cpm = validate(card)
    lay = layout(card, cpm)
    title = esc(card.get("title"))
    qd = card["question_data"]
    auth = card.get("authority") or {}
    student_boundary = esc(auth.get("student_boundary"))

    client = trusted_json_for_script({
        "explanation_steps": [
            {"id": s["id"], "title": s.get("title"), "focus": s.get("focus") or [], "script": s.get("script")}
            for s in card.get("explanation_steps") or []
        ],
        "error_reveals": [
            {"id": r["id"], "title": r.get("title"), "jump_step_id": r["jump_step_id"],
             "script": r.get("script"), "correction_hint": r.get("correction_hint")}
            for r in card.get("error_reveals") or []
        ],
        "practice": {
            "answer": (card.get("practice") or {}).get("answer"),
            "review_step_id": (card.get("practice") or {}).get("review_step_id"),
            "correct_script": (card.get("practice") or {}).get("correct_script"),
            "incorrect_script": (card.get("practice") or {}).get("incorrect_script"),
        },
    })

    step_tabs = "".join(
        f'<button class="step-tab" type="button" role="tab" data-step="{esc(s["id"])}">'
        f'<small>第 {i+1} 步</small><strong>{esc(s.get("title"))}</strong></button>'
        for i, s in enumerate(card.get("explanation_steps") or [])
    )
    err_cards = "".join(
        f'<button class="err-card" type="button" data-error-id="{esc(r["id"])}" data-jump="{esc(r["jump_step_id"])}">'
        f'<b>{esc(r.get("title"))}</b><span>{esc(r.get("correction_hint"))}</span></button>'
        for r in card.get("error_reveals") or []
    )
    opts = "".join(
        f'<button class="opt" type="button" data-opt="{esc(o["id"])}" aria-pressed="false">'
        f'<b>{esc(o["id"])}.</b> {esc(o.get("text"))}</button>'
        for o in (card.get("practice") or {}).get("options") or []
    )

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
created_by: deterministic render_network_card.py (template_type={TEMPLATE_TYPE})
schema_version: {SCHEMA_VERSION}
authority_status: {esc(auth.get("status"))}
boundary: front-end does NOT compute critical path/float; build-time compute_cpm() validated JSON candidate
 against deterministic CPM; no OpenMAIC, no LLM, no RAG, no TTS, no audio, no external refs.
-->
<main class="page">
  <div class="eyebrow">网络计划 · 看图找关键线路</div>
  <h1>{title}</h1>
  <p class="goal">{esc(card.get("student_goal"))}</p>
  <p class="stem">{esc(qd.get("stem"))}</p>

  <div class="diagram">
    {network_svg(card, cpm, lay)}
    <div class="legend"><span><i></i>关键线路（总时差为 0）</span><span>方框 = 工作，箭线 = 先后关系</span></div>
  </div>

  <div class="narr">
    <div class="title" id="narrTitle"></div>
    <div class="script" id="narrScript"></div>
    <div class="jump-note" id="jumpNote" hidden></div>
  </div>
  <div class="steps" id="steps" role="tablist" aria-label="讲解步骤"></div>
  <div class="controls">
    <button id="prevBtn" type="button">上一步</button>
    <button class="primary" id="nextBtn" type="button">下一步</button>
  </div>

  <div class="bar">
    <h2>常见判断错误</h2>
    <p class="hint">点一个你容易犯的错，我带你跳到该看的那一步。</p>
    <div class="err-grid">{err_cards}</div>
  </div>

  <div class="bar">
    <h2>复测一题</h2>
    <p class="hint">{esc((card.get("practice") or {}).get("question"))}</p>
    <div class="opt-grid">{opts}</div>
    <div class="feedback" id="feedback" role="status"></div>
  </div>

  <div class="auth">
    <b>说明</b>：{student_boundary}
    <div style="margin-top:6px;font-weight:700;color:#9a3412">教学演示 · 关键线路按“总时差为 0”判定 · 不是官方评分</div>
  </div>
</main>
<script type="application/json" id="cardData">{client}</script>
<script>
const data = JSON.parse(document.getElementById("cardData").textContent);
const steps = data.explanation_steps;
const reveals = data.error_reveals;
const practice = data.practice;
const svg = document.getElementById("netSvg");
const stepsWrap = document.getElementById("steps");
const narrTitle = document.getElementById("narrTitle");
const narrScript = document.getElementById("narrScript");
const jumpNote = document.getElementById("jumpNote");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const FOCUS = {{dependencies:"focus-deps", early_time:"focus-early", late_time:"focus-late", critical_path:"focus-critical"}};
let cur = 0;

steps.forEach((s,i)=>{{
  const b = document.createElement("button");
  b.className = "step-tab"; b.type = "button"; b.setAttribute("role","tab"); b.dataset.step = s.id;
  b.innerHTML = `<small>第 ${{i+1}} 步</small><strong>${{s.title}}</strong>`;
  b.addEventListener("click",()=>showStep(i));
  stepsWrap.appendChild(b);
}});

function applyFocus(focusList){{
  svg.classList.remove("focus-deps","focus-early","focus-late","focus-critical");
  (focusList||[]).forEach(f=>{{ if(FOCUS[f]) svg.classList.add(FOCUS[f]); }});
}}
function showStep(i, note){{
  cur = Math.max(0, Math.min(steps.length-1, i));
  const s = steps[cur];
  narrTitle.textContent = `第 ${{cur+1}} 步 · ${{s.title}}`;
  narrScript.textContent = s.script;
  applyFocus(s.focus);
  if(note){{ jumpNote.innerHTML = note; jumpNote.hidden = false; }} else {{ jumpNote.hidden = true; jumpNote.textContent = ""; }}
  [...stepsWrap.children].forEach((b,j)=>b.setAttribute("aria-selected", j===cur ? "true":"false"));
  prevBtn.disabled = cur===0;
  nextBtn.textContent = cur===steps.length-1 ? "回到第一步" : "下一步";
  document.documentElement.dataset.activeStep = s.id;
}}
prevBtn.addEventListener("click",()=>showStep(cur-1));
nextBtn.addEventListener("click",()=> cur===steps.length-1 ? showStep(0) : showStep(cur+1));

document.querySelectorAll(".err-card").forEach(btn=>{{
  btn.addEventListener("click",()=>{{
    const errId = btn.dataset.errorId;
    const rv = reveals.find(r=>r.id===errId) || {{}};
    const idx = steps.findIndex(s=>s.id===rv.jump_step_id);
    const note = `你担心的是「<b>${{rv.title||""}}</b>」——${{rv.correction_hint||""}}`;
    showStep(idx>=0?idx:0, note);
    narrScript.textContent = rv.script || narrScript.textContent;
    document.documentElement.dataset.activeError = errId;
    document.querySelector(".diagram").scrollIntoView({{behavior:"smooth", block:"start"}});
  }});
}});

document.querySelectorAll(".opt").forEach(btn=>{{
  btn.addEventListener("click",()=>{{
    document.querySelectorAll(".opt").forEach(o=>{{o.setAttribute("aria-pressed","false");o.classList.remove("correct","wrong");}});
    btn.setAttribute("aria-pressed","true");
    const correct = btn.dataset.opt === practice.answer;
    btn.classList.add(correct ? "correct":"wrong");
    const fb = document.getElementById("feedback");
    fb.classList.remove("correct","wrong");
    fb.classList.add("show", correct ? "correct":"wrong");
    if(correct){{
      fb.textContent = "✅ " + (practice.correct_script||"");
      document.documentElement.dataset.practiceResult = "correct";
    }} else {{
      fb.textContent = "❌ " + (practice.incorrect_script||"");
      const idx = steps.findIndex(s=>s.id===practice.review_step_id);
      if(idx>=0) showStep(idx, "复测发现你判断有偏差——跳回这一步对照。");
      document.documentElement.dataset.practiceResult = "incorrect";
      document.querySelector(".diagram").scrollIntoView({{behavior:"smooth", block:"start"}});
    }}
  }});
}});

showStep(0);
</script>
</body>
</html>"""


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    card_path = Path(argv[1])
    out_path = Path(argv[2]) if len(argv) > 2 else card_path.with_suffix(".rendered.html")
    card = json.loads(card_path.read_text(encoding="utf-8"))
    out_path.write_text(render(card), encoding="utf-8")
    cpm = compute_cpm(card)
    acts = card["question_data"]["activities"]
    deps = card["question_data"]["dependencies"]
    print(f"rendered: {card_path} -> {out_path}")
    print(
        f"  activities={len(acts)} nodes={len(acts)+2} edges={len(deps)} "
        f"critical_path={'-'.join(card['question_data']['expected']['critical_path'])} "
        f"duration={cpm['project_duration']} "
        f"non_critical={[a['id'] for a in acts if cpm['tf'][a['id']]>0]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
