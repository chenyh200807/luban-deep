#!/usr/bin/env python3
"""N01 video-first renderer: HTML lesson + independent practice page.

The lesson page is a phone-first HTML preview of a Remotion-style timeline:
pre-generated mp3 narration + timing JSON drive SVG animation states.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from render_network_card import SCHEMA_VERSION, compute_cpm, esc, trusted_json_for_script


def validate_video_card(card: dict[str, Any]) -> dict[str, Any]:
    if card.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {card.get('schema_version')!r}")
    if card.get("template_type") != "network_plan_keypath":
        raise ValueError("video-first renderer only supports network_plan_keypath")
    beats = card.get("video_beats") or []
    if not 5 <= len(beats) <= 8:
        raise ValueError("whiteboard video needs 5-8 beats")
    for key in ["wrong_idea", "visual_correction", "exam_phrase", "warm_correction", "authority"]:
        if not str((card.get("teaching_spine") or {}).get(key) or "").strip():
            raise ValueError(f"teaching_spine.{key} is required")
    cpm = compute_cpm(card)
    expected = card["question_data"]["expected"]
    if set(expected["critical_path"]) != cpm["critical"]:
        raise ValueError("expected.critical_path mismatch")
    if int(expected["project_duration"]) != cpm["project_duration"]:
        raise ValueError("expected.project_duration mismatch")
    for activity in card["question_data"]["activities"]:
        aid = activity["id"]
        got = expected["float"][aid]
        if int(got["total_float"]) != cpm["tf"][aid] or int(got["free_float"]) != cpm["ff"][aid]:
            raise ValueError(f"float mismatch for {aid}")
    return cpm


BOARD_POS = {
    "START": (34, 134),
    "A": (112, 82),
    "B": (112, 184),
    "C": (202, 82),
    "D": (202, 184),
    "E": (292, 134),
    "END": (362, 134),
}
NODE_W, NODE_H = 46, 34


def node_label(node: str) -> str:
    return "开始" if node == "START" else "结束" if node == "END" else node


def critical_edges(card: dict[str, Any]) -> set[tuple[str, str]]:
    path = card["question_data"]["expected"]["critical_path"]
    return set(zip(path, path[1:]))


def edge_path(f: str, t: str) -> str:
    x1, y1 = BOARD_POS[f]
    x2, y2 = BOARD_POS[t]
    start = x1 + NODE_W / 2
    end = x2 - NODE_W / 2
    mid = (start + end) / 2
    bend = 0
    if f == "A" and t == "D":
        bend = 18
    elif f == "B" and t == "D":
        bend = -8
    elif f == "C" and t == "E":
        bend = 13
    elif f == "D" and t == "E":
        bend = -13
    return f"M {start:.1f} {y1:.1f} C {mid:.1f} {y1 + bend:.1f}, {mid:.1f} {y2 - bend:.1f}, {end:.1f} {y2:.1f}"


def board_svg(card: dict[str, Any], cpm: dict[str, Any]) -> str:
    crit = critical_edges(card)
    dur = cpm["dur"]
    parts: list[str] = [
        '<svg class="board-svg" viewBox="0 0 390 300" role="img" aria-label="网络计划白板动画图" preserveAspectRatio="xMidYMid meet">',
        '<defs>',
        '<marker id="smallArrow" markerWidth="7" markerHeight="7" refX="6.2" refY="3.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0 L7 3.5 L0 7 z" fill="#4b5d73"></path></marker>',
        '<marker id="hotArrow" markerWidth="8" markerHeight="8" refX="7.2" refY="4" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0 L8 4 L0 8 z" fill="#c2410c"></path></marker>',
        "</defs>",
        '<text class="wrong-equation" x="52" y="28">C 最长 = 关键线路？</text>',
        '<path class="wrong-cross" d="M50 12 L244 34 M242 12 L52 34"></path>',
    ]
    for i, dep in enumerate(card["question_data"]["dependencies"]):
        f, t = dep["from"], dep["to"]
        cls = "edge critical" if (f, t) in crit else "edge"
        parts.append(
            f'<path class="{cls}" data-from="{esc(f)}" data-to="{esc(t)}" style="--d:{i * 70}ms" '
            f'pathLength="1" d="{edge_path(f, t)}" marker-end="url(#smallArrow)"></path>'
        )
    for node, (cx, cy) in BOARD_POS.items():
        x, y = cx - NODE_W / 2, cy - NODE_H / 2
        cls = "node critical" if node in cpm["critical"] else "node"
        if node == "C":
            cls += " trap-node"
        parts.append(f'<g class="{cls}" data-node-id="{esc(node)}">')
        parts.append(f'<rect x="{x:.0f}" y="{y:.0f}" rx="8" width="{NODE_W}" height="{NODE_H}"></rect>')
        parts.append(f'<text class="node-label" x="{cx:.0f}" y="{cy - 2:.0f}">{esc(node_label(node))}</text>')
        if node not in ("START", "END"):
            parts.append(f'<text class="node-dur" x="{cx:.0f}" y="{cy + 12:.0f}">{dur[node]}天</text>')
            parts.append(f'<text class="early-label" x="{cx:.0f}" y="{y - 9:.0f}">早{cpm["es"][node]}-{cpm["ef"][node]}</text>')
            parts.append(f'<text class="late-label" x="{cx:.0f}" y="{y + NODE_H + 16:.0f}">迟{cpm["ls"][node]}-{cpm["lf"][node]}</text>')
            tf, ff = cpm["tf"][node], cpm["ff"][node]
            tone = "zero" if tf == 0 else "slack"
            parts.append(f'<text class="float-label {tone}" x="{cx:.0f}" y="{y + NODE_H + 16:.0f}">总{tf}/自{ff}</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def practice_board_svg(card: dict[str, Any], cpm: dict[str, Any], q: dict[str, Any]) -> str:
    qid = q.get("id")
    crit = critical_edges(card)
    focus_edges: set[tuple[str, str]] = set()
    focus_nodes: set[str] = set()
    duration_override: dict[str, int] = {}
    note = "原图：先读逻辑，再算路径和时差。"
    if qid == "path":
        focus_nodes = set(card["question_data"]["expected"]["critical_path"])
        focus_edges = crit
        note = "看整条 0 时差连续线路，不看单个工作。"
    elif qid == "concept_trap":
        focus_nodes = {"C"}
        note = "提醒：C 是一个工作，不是一条线路。"
    elif qid == "transfer_recompute":
        duration_override = {"D": 5}
        focus_nodes = {"A", "D", "E"}
        focus_edges = {("A", "D"), ("D", "E")}
        note = "变化：D 从 2 天改为 5 天，必须重新算。"
    elif qid == "float_compare":
        focus_nodes = {"B", "D"}
        focus_edges = {("B", "D")}
        note = "看 B：自由时差看紧后 D，总时差看总工期。"
    elif qid == "score_sentence":
        note = "主观题别只写路径，要写线路、工期、理由。"
    parts: list[str] = [
        '<div class="mini-board">',
        '<svg class="mini-svg" viewBox="0 0 390 238" role="img" aria-label="练习用网络计划图" preserveAspectRatio="xMidYMid meet">',
        '<defs>',
        '<marker id="practiceArrow" markerWidth="7" markerHeight="7" refX="6.2" refY="3.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0 L7 3.5 L0 7 z" fill="#4b5d73"></path></marker>',
        "</defs>",
    ]
    for dep in card["question_data"]["dependencies"]:
        f, t = dep["from"], dep["to"]
        classes = ["m-edge"]
        if (f, t) in focus_edges:
            classes.append("focus")
        elif (f, t) in crit and qid == "score_sentence":
            classes.append("soft")
        parts.append(
            f'<path class="{" ".join(classes)}" d="{edge_path(f, t)}" marker-end="url(#practiceArrow)"></path>'
        )
    for node, (cx, cy) in BOARD_POS.items():
        x, y = cx - NODE_W / 2, cy - NODE_H / 2
        cls = "m-node focus" if node in focus_nodes else "m-node"
        parts.append(f'<g class="{cls}">')
        parts.append(f'<rect x="{x:.0f}" y="{y:.0f}" rx="8" width="{NODE_W}" height="{NODE_H}"></rect>')
        parts.append(f'<text class="m-label" x="{cx:.0f}" y="{cy - 2:.0f}">{esc(node_label(node))}</text>')
        if node not in ("START", "END"):
            dur = duration_override.get(node, cpm["dur"][node])
            changed = " changed" if node in duration_override else ""
            parts.append(f'<text class="m-dur{changed}" x="{cx:.0f}" y="{cy + 12:.0f}">{dur}天</text>')
        parts.append("</g>")
    if qid == "transfer_recompute":
        parts.append('<text class="m-note hot" x="195" y="218">A-D-E = 3+5+3 = 11天；A-C-E = 10天</text>')
    elif qid == "float_compare":
        parts.append('<text class="m-note" x="195" y="218">B 最早完第2天，D 最早第3天开始</text>')
    else:
        parts.append(f'<text class="m-note" x="195" y="218">{esc(note)}</text>')
    parts.append("</svg></div>")
    return "".join(parts)


def read_timing(card_path: Path) -> dict[str, Any] | None:
    timing = card_path.with_name(card_path.stem + ".lesson.timing.json")
    if not timing.exists():
        return None
    return json.loads(timing.read_text(encoding="utf-8"))


def lesson_html(card: dict[str, Any], cpm: dict[str, Any], card_path: Path, practice_name: str) -> str:
    spine = card.get("teaching_spine") or {}
    deep = card.get("deep_archetype") or {}
    timing = read_timing(card_path)
    audio_name = timing.get("audio") if timing else None
    remotion_name = card_path.stem + ".remotion.mp4"
    remotion_path = card_path.with_name(remotion_name)
    poster_name = card_path.stem + ".poster.png"
    poster_path = card_path.with_name(poster_name)

    def asset_url(name: str | None) -> str:
        if not name:
            return ""
        path = card_path.with_name(name)
        if not path.exists():
            return name
        return f"{name}?v={int(path.stat().st_mtime)}"

    remotion_url = asset_url(remotion_name)
    poster_url = asset_url(poster_name) if poster_path.exists() else ""
    audio_url = asset_url(audio_name)
    poster_attr = f' poster="{esc(poster_url)}"' if poster_url else ""
    use_remotion = remotion_path.exists()
    if use_remotion:
        poster_img = (
            f'<img class="poster-img" id="posterImg" src="{esc(poster_url)}" alt="课程首帧">'
            if poster_url
            else ""
        )
        media_stage = (
            f'<div class="remotion-stage">'
            f'<video id="lessonAudio" preload="metadata" playsinline{poster_attr} src="{esc(remotion_url)}"></video>'
            f"{poster_img}"
            f'<button type="button" class="center-play" id="centerPlay">播放视频</button>'
            f"</div>"
        )
        audio_tag = ""
    else:
        media_stage = (
            f'<div class="whiteboard">'
            f'{board_svg(card, cpm)}'
            f'<div class="score-card">'
            f'<b>采分句</b>'
            f'<span>{esc(spine.get("exam_phrase"))}</span>'
            f'</div>'
            f'</div>'
        )
        audio_tag = f'<audio id="lessonAudio" preload="metadata" src="{esc(audio_url)}"></audio>' if audio_url else ""
    score_slots = [
        ("路径", "待推导", "开始-A-C-E-结束"),
        ("工期", "待推导", "10 天"),
        ("依据", "待推导", "A、C、E 总时差均为 0"),
    ]
    score_slots_html = "".join(
        f'<div data-score-slot="{esc(label)}" data-final="{esc(final)}"><b>{esc(label)}</b><span>{esc(initial)}</span></div>'
        for label, initial, final in score_slots
    )
    client = trusted_json_for_script(
        {
            "video_beats": card.get("video_beats") or [],
            "timing": timing,
            "practice": practice_name,
        }
    )
    beat_labels = ["先学", "错觉", "读图", "顺推", "逆推", "时差", "线路", "采分"]
    dots = "".join(
        f'<button type="button" class="beat-dot" data-beat="{i}" title="{esc(beat.get("title"))}" aria-label="跳到第 {i + 1} 节：{esc(beat.get("title"))}">{esc(beat_labels[i] if i < len(beat_labels) else f"重点{i + 1}")}</button>'
        for i, beat in enumerate(card.get("video_beats") or [])
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>{esc(card.get("title"))}</title>
<style>{_LESSON_CSS}</style>
</head>
<body>
<main class="phone">
  <section class="lesson" id="lesson" data-stage="trap">
    <div class="journey-rail" aria-label="学习进度">
      <span class="on">① 讲懂</span>
      <a id="practiceGate" class="locked" href="{esc(practice_name)}" aria-disabled="true">② 看完后闯关</a>
      <span>③ 看穿</span>
    </div>
    <div class="topbar">
      <div class="topline">
        <div class="kicker">鲁班深母题 · 有声白板</div>
        <div class="top-actions">
          <button type="button" class="full-btn" id="fullBtn">全屏</button>
          <div class="time" id="timeLabel">00:00</div>
        </div>
      </div>
      <h1>关键线路不是最长那一项</h1>
    </div>
    {media_stage}
    <div class="subtitle">
      <h2 id="beatTitle">1. 先抓错觉</h2>
      <p id="beatSubtitle">点播放，听老师讲。</p>
    </div>
    <div class="score-slots" id="scoreSlots">{score_slots_html}</div>
    <div class="qa-panel" id="qaPanel">
      <div class="qa-title">讲完追问</div>
      <div id="qaList"></div>
    </div>
    <div class="control-deck" id="controlDeck">
      <div class="audio-row">
        {audio_tag}
        <button type="button" class="play" id="playBtn">播放</button>
        <button type="button" id="pauseBtn">暂停</button>
        <button type="button" id="muteBtn" aria-pressed="false">静音</button>
        <button type="button" class="exit-full" id="exitFullBtn">退出</button>
      </div>
      <label class="scrubber" aria-label="拖动调整播放进度">
        <input type="range" id="scrubRange" min="0" max="1000" value="0" step="1">
        <span id="scrubFill"></span>
      </label>
      <div class="timeline" aria-label="章节跳转">{dots}</div>
    </div>
    <div class="nav">
      <button type="button" id="prevBeat">上一幕</button>
      <button type="button" id="nextBeat">下一幕</button>
      <a id="practiceCta" class="locked" href="{esc(practice_name)}" aria-disabled="true">看完后闯关</a>
    </div>
  </section>
  <section class="below">
    <div><b>纠正的错觉</b><span>{esc(spine.get("wrong_idea"))}</span></div>
    <div><b>记忆钩子</b><span>{esc(deep.get("memory_hook"))}</span></div>
  </section>
</main>
<script type="application/json" id="lessonData">{client}</script>
<script>{_LESSON_JS}</script>
</body>
</html>"""


def render_quiz_options(q: dict[str, Any]) -> str:
    return "".join(
        f'<button type="button" class="option" data-opt="{esc(o["id"])}"><b>{esc(o["id"])}.</b> {esc(o.get("text"))}</button>'
        for o in q.get("options") or []
    )


def render_score_sentence(q: dict[str, Any]) -> str:
    prompts = q.get("prompts") or []
    return (
        '<div class="score-write">'
        + "".join(
            f'<label><span>{esc(p.get("label"))}</span><input data-field="{esc(p.get("id"))}" placeholder="{esc(p.get("placeholder"))}"></label>'
            for p in prompts
        )
        + '<button type="button" class="check-score" data-check-score="1">检查采分句</button>'
        + "</div>"
    )


def render_question_controls(q: dict[str, Any]) -> str:
    if q.get("kind") == "score_sentence":
        return render_score_sentence(q)
    return f'<div class="options">{render_quiz_options(q)}</div>'


def practice_html(card: dict[str, Any], cpm: dict[str, Any], lesson_name: str) -> str:
    quiz = card.get("quiz") or []
    blocks: list[str] = []
    for i, q in enumerate(quiz):
        tag = q.get("tier_tag") or q.get("kind") or "choice"
        key = '<strong>关键鉴别</strong>' if q.get("key_discriminator") else ""
        blocks.append(
            f'<section class="q" data-index="{i}" data-qid="{esc(q["id"])}">'
            f'<div class="qtop"><span>第 {i + 1}/{len(quiz)} 问</span><em>{esc(tag)}</em></div>'
            f'{key}'
            f'{practice_board_svg(card, cpm, q)}'
            f'<h2>{esc(q.get("question"))}</h2>'
            f'{render_question_controls(q)}'
            f'<div class="feedback" id="fb-{esc(q["id"])}"></div>'
            f'</section>'
        )
    items = "".join(blocks)
    client = trusted_json_for_script(
        {
            "quiz": quiz,
            "score_atoms": (card.get("deep_archetype") or {}).get("score_atoms") or [],
            "mastery": (card.get("deep_archetype") or {}).get("mastery_discrimination") or {},
        }
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>N01 闯关 · 看穿关键线路</title>
<style>{_PRACTICE_CSS}</style>
</head>
<body>
<main class="practice">
  <header>
    <a href="{esc(lesson_name)}">返回讲解</a>
    <div>
      <span>鲁班深母题 · 闯关</span>
      <h1>N01 关键线路五步闯关</h1>
    </div>
  </header>
  <div class="progress"><div id="progressFill"></div></div>
  {items}
  <section class="done" id="done">
    <h2 id="verdictTitle">看穿结果</h2>
    <p id="scoreText"></p>
    <div class="score-atoms" id="scoreAtoms"></div>
    <div class="recap" id="recap"></div>
    <a href="{esc(lesson_name)}">回看白板讲解</a>
  </section>
  <nav>
    <button type="button" id="prevQ">上一题</button>
    <button type="button" id="nextQ">下一题</button>
  </nav>
</main>
<script type="application/json" id="practiceData">{client}</script>
<script>{_PRACTICE_JS}</script>
</body>
</html>"""


_LESSON_CSS = r"""
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;max-width:100%;overflow:hidden}body{background:#eaf1f6;color:#17202a;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}
.phone{width:min(430px,100%);height:100dvh;margin:0 auto;padding:8px;overflow:hidden}.lesson{height:calc(100dvh - 16px);background:#fff;border:1px solid #d2dee9;border-radius:18px;padding:8px;box-shadow:0 14px 32px rgba(31,41,55,.08);display:flex;flex-direction:column;overflow:hidden;gap:7px}
.journey-rail{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;flex:0 0 auto}.journey-rail span,.journey-rail a{height:30px;border:1px solid #d7e2ed;border-radius:10px;background:#f6f9fc;color:#607287;text-decoration:none;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:900;text-align:center}.journey-rail .on{background:#176b7a;color:#fff;border-color:#176b7a}.journey-rail a.ready{background:#176b7a;color:#fff;border-color:#176b7a}.journey-rail a.locked{opacity:.72}
.topbar{display:flex;flex-direction:column;gap:3px;flex:0 0 auto}.topline{display:flex;justify-content:space-between;gap:8px;align-items:center}.kicker{color:#176b7a;font-size:11px;font-weight:900}.topbar h1{margin:0;font-size:19px;line-height:1.12}.top-actions{display:flex;gap:6px;align-items:center;flex:0 0 auto}.full-btn{height:31px;border:1px solid #176b7a;border-radius:999px;background:#fff;color:#176b7a;padding:0 10px;font-size:11px;font-weight:950;white-space:nowrap}.time{font-weight:900;color:#176b7a;border:1px solid #c9dce8;border-radius:999px;padding:5px 8px;font-size:11px;white-space:nowrap}
.remotion-stage{position:relative;background:#eaf1f6;border:1px solid #d2dee9;border-radius:16px;overflow:hidden;flex:1 1 auto;min-height:250px;max-height:56dvh;display:flex;align-items:center;justify-content:center}.remotion-stage video,.poster-img{display:block;width:100%;height:100%;background:#eaf1f6;object-fit:contain;object-position:center center}.poster-img{position:absolute;inset:0;z-index:2}.lesson.started .poster-img{display:none}.center-play{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:88px;height:88px;border-radius:999px;border:4px solid rgba(255,255,255,.9);background:rgba(23,107,122,.94);color:#fff;font-weight:950;font-size:16px;box-shadow:0 18px 44px rgba(31,41,55,.24);z-index:3}.lesson.started .center-play{opacity:0;pointer-events:none}
.whiteboard{position:relative;background:#fffdf7;border:1px solid #e6dbc7;border-radius:16px;padding:6px;overflow:hidden;flex:1 1 auto;min-height:250px}.whiteboard:before{content:"";position:absolute;inset:8px;border:1px dashed rgba(71,85,105,.18);border-radius:12px;pointer-events:none}.board-svg{position:relative;z-index:1;width:100%;height:100%;display:block}
.edge{fill:none;stroke:#4b5d73;stroke-width:2.2;stroke-linecap:round;opacity:.24;stroke-dasharray:1;stroke-dashoffset:0}.edge.critical{stroke:#8fa0b3}.node rect{fill:#fffdf7;stroke:#4b5d73;stroke-width:1.7}.node-label{text-anchor:middle;font-size:10px;font-weight:900;fill:#17202a}.node-dur{text-anchor:middle;font-size:9px;font-weight:800;fill:#637386}.wrong-equation{display:none;font-size:16px;font-weight:900;fill:#c2410c}.wrong-cross{display:none;stroke:#c2410c;stroke-width:3;stroke-linecap:round;stroke-dasharray:1;stroke-dashoffset:1;pathLength:1}.early-label,.late-label,.float-label{display:none;text-anchor:middle;font-size:8.5px;font-weight:900}.early-label{fill:#1d4ed8}.late-label{fill:#0f766e}.float-label.zero{fill:#0f766e}.float-label.slack{fill:#b45309}
@keyframes draw{to{stroke-dashoffset:0}}@keyframes pop{0%{transform:scale(.92);opacity:.4}100%{transform:scale(1);opacity:1}}@keyframes fadeup{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}.lesson[data-stage="trap"] .wrong-equation,.lesson[data-stage="trap"] .wrong-cross{display:block}.lesson[data-stage="trap"] .wrong-cross{animation:draw .6s ease forwards}.lesson[data-stage="trap"] .node{opacity:.34}.lesson[data-stage="trap"] .trap-node{opacity:1;animation:pop .32s ease forwards}.lesson[data-stage="trap"] .trap-node rect{fill:#fff3e9;stroke:#c2410c;stroke-width:2.4}.lesson[data-stage="logic"] .edge,.lesson[data-stage="forward"] .edge,.lesson[data-stage="backward"] .edge,.lesson[data-stage="float"] .edge,.lesson[data-stage="critical"] .edge,.lesson[data-stage="score"] .edge{opacity:.78;stroke-dashoffset:1;animation:draw .58s cubic-bezier(.16,1,.3,1) forwards;animation-delay:var(--d)}.lesson[data-stage="forward"] .early-label,.lesson[data-stage="backward"] .early-label,.lesson[data-stage="backward"] .late-label{display:block;animation:fadeup .28s ease forwards}.lesson[data-stage="float"] .float-label,.lesson[data-stage="critical"] .float-label.zero{display:block;animation:fadeup .28s ease forwards}.lesson[data-stage="critical"] .edge.critical,.lesson[data-stage="score"] .edge.critical{stroke:#c2410c;stroke-width:3.4;opacity:1;marker-end:url(#hotArrow)}.lesson[data-stage="critical"] .node.critical rect,.lesson[data-stage="score"] .node.critical rect{fill:#fff3e9;stroke:#c2410c;stroke-width:2.4}.lesson[data-stage="score"] .node:not(.critical),.lesson[data-stage="score"] .edge:not(.critical){opacity:.18}
.score-card{display:none}.subtitle{border:1px solid #c8dcf5;background:#f2f7ff;border-radius:13px;padding:8px 10px;flex:0 0 68px;overflow:hidden}.subtitle h2{font-size:15px;color:#1d4ed8;margin:0 0 3px;line-height:1.15}.subtitle p{font-size:13px;line-height:1.36;margin:0;font-weight:850;color:#24364b;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.score-slots{display:grid;grid-template-columns:repeat(3,1fr);gap:5px;flex:0 0 auto}.score-slots div{min-height:43px;border:1px solid #d7e2ed;background:#f7fafc;border-radius:11px;padding:6px 7px}.score-slots b{display:block;font-size:11px;color:#176b7a;line-height:1}.score-slots span{display:block;margin-top:3px;font-size:12px;line-height:1.15;font-weight:900;color:#34465b;word-break:break-word}.score-slots div.revealed{border-color:#fed7aa;background:#fff7ed}.score-slots div.revealed span{color:#9a3412}
.qa-panel{display:none;border-top:1px dashed #cbd9e6;padding-top:6px;flex:0 0 auto;max-height:118px;overflow:auto}.qa-panel.show{display:block}.qa-title{font-size:11px;color:#176b7a;font-weight:900;margin:0 0 5px}.qa-bubble{display:flex;gap:6px;margin:5px 0;align-items:flex-start}.qa-bubble.teacher{flex-direction:row-reverse}.qa-avatar{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;flex:0 0 24px;font-size:11px;font-weight:900;background:#dbeafe;color:#1d4ed8}.qa-bubble.teacher .qa-avatar{background:#ffedd5;color:#c2410c}.qa-text{max-width:88%;border:1px solid #d5e1ec;background:#fff;border-radius:12px;padding:7px 8px;font-size:12px;line-height:1.35;color:#34465b;font-weight:850}.qa-bubble.active .qa-text{border-color:#176b7a;box-shadow:0 0 0 3px rgba(23,107,122,.10)}
.control-deck{display:flex;flex-direction:column;gap:7px;flex:0 0 auto}.audio-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;flex:0 0 auto}.audio-row button{border:1px solid #cbd9e6;border-radius:12px;height:38px;padding:0 8px;background:#fff;font-weight:900;color:#24364b;touch-action:manipulation}.audio-row .play{background:#176b7a;color:#fff;border-color:#176b7a}.exit-full{display:none}.scrubber{position:relative;height:36px;border-radius:999px;background:#d6e2ec;display:block;overflow:visible;flex:0 0 auto}.scrubber input{position:absolute;inset:0;z-index:2;width:100%;height:100%;margin:0;opacity:1;cursor:pointer;appearance:none;-webkit-appearance:none;background:transparent;touch-action:none}.scrubber input::-webkit-slider-runnable-track{height:36px;background:transparent}.scrubber input::-webkit-slider-thumb{-webkit-appearance:none;width:28px;height:28px;margin-top:4px;border-radius:999px;border:5px solid #f97316;background:#fff;box-shadow:0 5px 14px rgba(31,41,55,.22)}.scrubber input::-moz-range-track{height:36px;background:transparent}.scrubber input::-moz-range-thumb{width:24px;height:24px;border-radius:999px;border:5px solid #f97316;background:#fff;box-shadow:0 5px 14px rgba(31,41,55,.22)}.scrubber span{position:absolute;left:0;top:0;bottom:0;z-index:1;width:0;background:linear-gradient(90deg,#176b7a,#f97316);border-radius:999px;pointer-events:none}
.timeline{display:grid;grid-template-columns:repeat(8,1fr);gap:5px;flex:0 0 auto}.beat-dot{height:30px;border:1px solid #cbd9e6;border-radius:999px;background:#eef4f8;color:#607287;font-size:10px;font-weight:950;white-space:nowrap;touch-action:manipulation}.beat-dot.active{background:#176b7a;color:#fff;border-color:#176b7a}.beat-dot.current{background:#f97316;color:#fff;border-color:#f97316}
.nav{display:grid;grid-template-columns:1fr 1fr 1.2fr;gap:6px;flex:0 0 auto}.nav button,.nav a{height:38px;border-radius:12px;border:1px solid #cbd9e6;background:#fff;font-size:13px;font-weight:900;color:#24364b;text-decoration:none;display:flex;align-items:center;justify-content:center}.nav a{background:#eef4f8;color:#607287;border-color:#d2dee9}.nav a.locked{opacity:.72}.nav a.ready{background:#f97316;color:#fff;border-color:#f97316;box-shadow:0 10px 22px rgba(249,115,22,.22);pointer-events:auto;opacity:1}
.below{display:none}.lesson.theater,.lesson:fullscreen{position:fixed;inset:0;z-index:9999;width:100vw;height:100dvh;max-width:none;border-radius:0;border:0;padding:0;background:#eaf1f6;box-shadow:none;gap:0}.lesson.theater .journey-rail,.lesson:fullscreen .journey-rail,.lesson.theater .topbar,.lesson:fullscreen .topbar,.lesson.theater .subtitle,.lesson:fullscreen .subtitle,.lesson.theater .score-slots,.lesson:fullscreen .score-slots,.lesson.theater .qa-panel,.lesson:fullscreen .qa-panel,.lesson.theater .nav,.lesson:fullscreen .nav,.lesson.theater .center-play,.lesson:fullscreen .center-play{display:none}.lesson.theater .remotion-stage,.lesson:fullscreen .remotion-stage{position:absolute;inset:0;z-index:1;width:100%;height:100%;max-height:none;min-height:0;border:0;border-radius:0;flex:none}.lesson.theater.controls-visible .remotion-stage,.lesson:fullscreen.controls-visible .remotion-stage{bottom:calc(156px + env(safe-area-inset-bottom));height:auto}.lesson.theater .control-deck,.lesson:fullscreen .control-deck{position:absolute;left:10px;right:10px;bottom:calc(10px + env(safe-area-inset-bottom));z-index:30;padding:10px;border:1px solid rgba(203,217,230,.92);border-radius:18px;background:#fff;box-shadow:0 14px 34px rgba(31,41,55,.20);opacity:0;transform:translateY(14px);pointer-events:none;transition:opacity .18s ease,transform .18s ease}.lesson.theater.controls-visible .control-deck,.lesson:fullscreen.controls-visible .control-deck{opacity:1;transform:translateY(0);pointer-events:auto}.lesson.theater .audio-row,.lesson:fullscreen .audio-row{grid-template-columns:1.1fr 1fr 1fr .8fr}.lesson.theater .audio-row button,.lesson:fullscreen .audio-row button{height:42px}.lesson.theater .timeline .beat-dot,.lesson:fullscreen .timeline .beat-dot{height:30px}.lesson.theater .exit-full,.lesson:fullscreen .exit-full{display:block}@media (max-height:760px){.journey-rail{display:none}.topbar h1{font-size:17px}.remotion-stage{min-height:220px}.subtitle{flex-basis:58px}.subtitle h2{font-size:14px}.subtitle p{font-size:12px}.score-slots div{min-height:36px;padding:5px}.audio-row button,.nav button,.nav a{height:34px}.timeline .beat-dot{height:26px}.lesson.theater.controls-visible .remotion-stage,.lesson:fullscreen.controls-visible .remotion-stage{bottom:calc(146px + env(safe-area-inset-bottom))}}@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

_LESSON_JS = r"""
const data = JSON.parse(document.getElementById('lessonData').textContent);
const lesson = document.getElementById('lesson');
const audio = document.getElementById('lessonAudio');
const title = document.getElementById('beatTitle');
const subtitle = document.getElementById('beatSubtitle');
const playBtn = document.getElementById('playBtn');
const pauseBtn = document.getElementById('pauseBtn');
const centerPlay = document.getElementById('centerPlay');
const muteBtn = document.getElementById('muteBtn');
const fullBtn = document.getElementById('fullBtn');
const exitFullBtn = document.getElementById('exitFullBtn');
const controlDeck = document.getElementById('controlDeck');
const practiceGate = document.getElementById('practiceGate');
const practiceCta = document.getElementById('practiceCta');
const dots = [...document.querySelectorAll('.beat-dot')];
const fill = document.getElementById('scrubFill');
const scrubRange = document.getElementById('scrubRange');
const timeLabel = document.getElementById('timeLabel');
const qaPanel = document.getElementById('qaPanel');
const qaList = document.getElementById('qaList');
const scoreSlots = [...document.querySelectorAll('[data-score-slot]')];
let idx = 0;
const beats = data.video_beats || [];
const allSegs = (data.timing && data.timing.segments || []);
const segs = allSegs.filter(s => s.kind === 'teach');
const qaSegs = allSegs.filter(s => s.kind === 'q' || s.kind === 'a');
let suppressTimeupdate = false;
let unlocked = false;
let controlsTimer = null;
function pad(n){ return String(Math.floor(n)).padStart(2,'0'); }
function fmt(t){ return `${pad(t/60)}:${pad(t%60)}`; }
function html(s){ return String(s ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function renderQa(){
  if(!qaList || !qaSegs.length) return;
  qaList.innerHTML = qaSegs.map((s,i)=>{
    const teacher = s.kind === 'a';
    const avatar = teacher ? '鲁' : '问';
    return `<div class="qa-bubble ${teacher ? 'teacher' : 'student'}" data-qa="${i}"><div class="qa-avatar">${avatar}</div><div class="qa-text">${html(s.text)}</div></div>`;
  }).join('');
}
function qaFromTime(t){
  let found = null;
  for(let i=0;i<qaSegs.length;i++){
    if(t >= qaSegs[i].startSec - 0.05) found = {seg: qaSegs[i], idx: i};
    else break;
  }
  return found;
}
function updateQa(t){
  if(!qaPanel || !qaSegs.length) return false;
  const teachEnd = (data.timing && data.timing.teachEndSec) || Infinity;
  if(t < teachEnd - 0.05){
    qaPanel.classList.remove('show');
    document.querySelectorAll('.qa-bubble').forEach(b=>b.classList.remove('active'));
    return false;
  }
  const active = qaFromTime(t);
  qaPanel.classList.add('show');
  if(active){
    title.textContent = active.seg.kind === 'q' ? '讲完追问' : '老师补充';
    subtitle.textContent = active.seg.text;
  }
  document.querySelectorAll('.qa-bubble').forEach((b,i)=>b.classList.toggle('active', !!active && i === active.idx));
  return true;
}
function updateScoreSlots(t){
  const cues = [
    {at: segs[6] ? segs[6].startSec + 3.0 : Infinity, slot: '路径'},
    {at: segs[6] ? segs[6].startSec + 8.2 : Infinity, slot: '工期'},
    {at: segs[7] ? segs[7].startSec + 7.2 : Infinity, slot: '依据'},
  ];
  scoreSlots.forEach(el => {
    const label = el.dataset.scoreSlot;
    const cue = cues.find(x => x.slot === label);
    const span = el.querySelector('span');
    if(cue && t >= cue.at){
      el.classList.add('revealed');
      span.textContent = el.dataset.final || span.textContent;
    } else {
      el.classList.remove('revealed');
      span.textContent = '待推导';
    }
  });
}
function setBeat(next, seek=false){
  idx = Math.max(0, Math.min(beats.length-1, next));
  const beat = beats[idx];
  lesson.dataset.stage = beat.stage;
  title.textContent = `${idx+1}. ${beat.title}`;
  subtitle.textContent = beat.subtitle || ((segs[idx] && segs[idx].text) || '');
  dots.forEach((d,i)=>{
    d.classList.toggle('active', i<=idx);
    d.classList.toggle('current', i===idx);
  });
  if(seek && audio && segs[idx]) audio.currentTime = segs[idx].startSec;
}
function beatFromTime(t){
  if(!segs.length) return idx;
  let found = 0;
  for(let i=0;i<segs.length;i++){
    if(t >= segs[i].startSec) found = i;
  }
  return Math.min(found, beats.length-1);
}
function manualBeat(next){
  lesson.classList.add('started');
  if(audio) suppressTimeupdate = true;
  setBeat(next,true);
  if(audio) updateProgress();
  window.setTimeout(()=>{ suppressTimeupdate = false; }, 180);
}
document.getElementById('prevBeat').addEventListener('click',()=>manualBeat(idx-1));
document.getElementById('nextBeat').addEventListener('click',()=>manualBeat(idx+1));
dots.forEach(btn => btn.addEventListener('click', () => manualBeat(Number(btn.dataset.beat || 0))));
function unlockPractice(){
  unlocked = true;
  lesson.classList.add('finished');
  if(practiceGate){ practiceGate.textContent='② 开始闯关'; practiceGate.classList.add('ready'); practiceGate.classList.remove('locked'); practiceGate.removeAttribute('aria-disabled'); }
  if(practiceCta){ practiceCta.textContent='开始闯关'; practiceCta.classList.add('ready'); practiceCta.classList.remove('locked'); practiceCta.removeAttribute('aria-disabled'); }
}
function guardPractice(evt){
  if(unlocked) return;
  evt.preventDefault();
  subtitle.textContent = '先听完采分句，再进入闯关。';
}
if(practiceGate) practiceGate.addEventListener('click', guardPractice);
if(practiceCta) practiceCta.addEventListener('click', guardPractice);
function fullscreenElement(){
  return document.fullscreenElement || document.webkitFullscreenElement || null;
}
function setFullButton(){
  if(!fullBtn) return;
  fullBtn.textContent = fullscreenElement() || lesson.classList.contains('theater') ? '退出' : '全屏';
}
function hideControls(){
  clearTimeout(controlsTimer);
  controlsTimer = null;
  lesson.classList.remove('controls-visible');
}
function showControls(autoHide=true){
  if(!lesson.classList.contains('theater')) return;
  clearTimeout(controlsTimer);
  lesson.classList.add('controls-visible');
  if(autoHide && audio && !audio.paused){
    controlsTimer = window.setTimeout(hideControls, 3200);
  }
}
async function toggleFullscreen(evt){
  if(evt) evt.stopPropagation();
  const active = fullscreenElement() || lesson.classList.contains('theater');
  if(active){
    if(fullscreenElement()){
      const exit = document.exitFullscreen || document.webkitExitFullscreen;
      if(exit) {
        try { await exit.call(document); } catch {}
      }
    }
    lesson.classList.remove('theater');
    hideControls();
    setFullButton();
    return;
  }
  lesson.classList.add('theater');
  hideControls();
  const request = lesson.requestFullscreen || lesson.webkitRequestFullscreen;
  if(request){
    try { await request.call(lesson); } catch {}
  }
  setFullButton();
}
if(fullBtn){
  fullBtn.addEventListener('click', toggleFullscreen);
  document.addEventListener('fullscreenchange', setFullButton);
  document.addEventListener('webkitfullscreenchange', setFullButton);
}
if(exitFullBtn) exitFullBtn.addEventListener('click', toggleFullscreen);
lesson.addEventListener('click', (evt)=>{
  if(!lesson.classList.contains('theater')) return;
  if(evt.target.closest('.control-deck') || evt.target.closest('.full-btn')) return;
  if(lesson.classList.contains('controls-visible')) hideControls();
  else showControls(true);
});
function updateProgress(){
  if(!audio) return;
  const total = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : ((data.timing && data.timing.totalSec) || 1);
  const pct = Math.min(100, audio.currentTime / total * 100);
  fill.style.width = `${pct}%`;
  if(scrubRange) scrubRange.value = String(Math.round(audio.currentTime / total * 1000));
  timeLabel.textContent = `${fmt(audio.currentTime)} / ${fmt(total)}`;
  updateScoreSlots(audio.currentTime);
}
if(audio){
  async function togglePlay(){
    lesson.classList.add('started');
    if(audio.paused){ if(centerPlay){ centerPlay.style.opacity=''; centerPlay.style.pointerEvents=''; } await audio.play(); playBtn.textContent='播放中'; if(centerPlay) centerPlay.textContent='播放中'; }
    else { audio.pause(); playBtn.textContent='继续'; if(centerPlay) centerPlay.textContent='继续'; }
  }
  function pause(){
    audio.pause();
    playBtn.textContent = '继续';
    if(centerPlay) centerPlay.textContent = '继续';
  }
  playBtn.addEventListener('click', togglePlay);
  pauseBtn.addEventListener('click', pause);
  if(centerPlay) centerPlay.addEventListener('click', togglePlay);
  muteBtn.addEventListener('click', ()=>{
    audio.muted = !audio.muted;
    muteBtn.textContent = audio.muted ? '开声' : '静音';
    muteBtn.setAttribute('aria-pressed', String(audio.muted));
  });
  audio.addEventListener('timeupdate', ()=>{
    if(suppressTimeupdate) return;
    const next = beatFromTime(audio.currentTime);
    if(next !== idx) setBeat(next,false);
    updateQa(audio.currentTime);
    updateProgress();
  });
  audio.addEventListener('loadedmetadata', updateProgress);
  if(scrubRange){
    scrubRange.addEventListener('pointerdown', ()=>showControls(false));
    scrubRange.addEventListener('input', ()=>{
      lesson.classList.add('started');
      showControls(false);
      const total = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : ((data.timing && data.timing.totalSec) || 1);
      audio.currentTime = Number(scrubRange.value || 0) / 1000 * total;
      const next = beatFromTime(audio.currentTime);
      if(next !== idx) setBeat(next,false);
      updateQa(audio.currentTime);
      updateProgress();
    });
    scrubRange.addEventListener('change', ()=>showControls(true));
  }
  audio.addEventListener('play',()=>{
    playBtn.textContent = '播放中';
    showControls(true);
  });
  audio.addEventListener('pause',()=>{ if(!audio.ended) playBtn.textContent = '继续'; showControls(false); });
  audio.addEventListener('ended',()=>{
    playBtn.textContent='重播';
    fill.style.width='100%';
    if(centerPlay){ centerPlay.textContent='重播'; centerPlay.style.opacity='1'; centerPlay.style.pointerEvents='auto'; }
    unlockPractice();
  });
} else {
  playBtn.textContent='无音频文件';
  playBtn.disabled = true;
  pauseBtn.disabled = true;
}
renderQa();
setBeat(0,false);
updateScoreSlots(0);
"""

_PRACTICE_CSS = r"""
*{box-sizing:border-box}html,body{margin:0;max-width:100%;overflow-x:hidden}body{background:#eaf1f6;color:#17202a;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}.practice{max-width:430px;margin:0 auto;min-height:100vh;padding:12px 10px 96px}header{display:flex;gap:12px;align-items:flex-start;margin-bottom:12px}header a{border:1px solid #cad8e5;border-radius:999px;padding:9px 11px;background:#fff;color:#176b7a;text-decoration:none;font-weight:900;font-size:12px;white-space:nowrap;min-height:44px;display:flex;align-items:center}header span{color:#176b7a;font-size:12px;font-weight:900}h1{font-size:22px;margin:3px 0 0;line-height:1.2}.progress{height:6px;border-radius:999px;background:#d6e2ec;margin-bottom:12px;overflow:hidden}.progress div{height:100%;width:0;background:#f97316}.q{display:none;background:#fff;border:1px solid #d2dee9;border-radius:18px;padding:13px;box-shadow:0 14px 32px rgba(31,41,55,.08)}.q.active{display:block}.qtop{display:flex;justify-content:space-between;gap:10px;color:#176b7a;font-size:12px;font-weight:900}.qtop em{font-style:normal;color:#607287;text-align:right}.q strong{display:inline-block;margin-top:8px;border:1px solid #fed7aa;border-radius:999px;background:#fff7ed;color:#c2410c;padding:4px 9px;font-size:12px}.mini-board{margin:10px 0 8px;border:1px solid #e6dbc7;background:#fffdf7;border-radius:14px;overflow:hidden}.mini-svg{display:block;width:100%;height:auto}.m-edge{fill:none;stroke:#4b5d73;stroke-width:2.2;stroke-linecap:round;opacity:.52}.m-edge.focus{stroke:#f97316;stroke-width:3.6;opacity:1}.m-edge.soft{stroke:#c2410c;stroke-width:3;opacity:.8}.m-node rect{fill:#fffdf7;stroke:#4b5d73;stroke-width:1.8}.m-node.focus rect{fill:#fff7ed;stroke:#f97316;stroke-width:2.6}.m-label{text-anchor:middle;font-size:10px;font-weight:900;fill:#17202a}.m-dur{text-anchor:middle;font-size:9px;font-weight:900;fill:#607287}.m-dur.changed{fill:#c2410c}.m-note{text-anchor:middle;font-size:11px;font-weight:900;fill:#607287}.m-note.hot{fill:#c2410c}.q h2{font-size:18px;line-height:1.32;margin:10px 0 12px}.options{display:grid;gap:9px}.option{text-align:left;min-height:58px;border:1px solid #cfdae6;background:#fff;border-radius:14px;padding:11px 12px;color:#24364b;font-size:15.5px;font-weight:800;line-height:1.38}.option.correct{border-color:#73c596;background:#ecf9f2}.option.wrong{border-color:#fb923c;background:#fff3e9}.option:disabled{opacity:1}.score-write{display:grid;gap:10px}.score-write label{display:grid;gap:5px}.score-write span{font-size:12px;font-weight:900;color:#176b7a}.score-write input{min-height:48px;border:1px solid #cfdae6;border-radius:13px;padding:0 12px;font-size:15px;font-weight:800;color:#17202a;background:#fff}.score-write input.ok{border-color:#73c596;background:#ecf9f2}.score-write input.no{border-color:#fb923c;background:#fff3e9}.check-score{min-height:48px;border:1px solid #176b7a;border-radius:14px;background:#176b7a;color:#fff;font-weight:900;font-size:15px}.feedback{display:none;margin-top:12px;border-radius:13px;padding:11px;font-size:14px;font-weight:800;line-height:1.55}.feedback.show.correct{display:block;background:#ecf9f2;border:1px solid #73c596;color:#0f6b4f}.feedback.show.wrong{display:block;background:#fff3e9;border:1px solid #fb923c;color:#9a3412}.feedback .basis{display:block;margin-top:7px;color:#56677c;font-size:12px;font-weight:800}.done{display:none;background:#fff;border:1px solid #d2dee9;border-radius:18px;padding:18px;text-align:left;box-shadow:0 14px 32px rgba(31,41,55,.08)}.done.show{display:block}.done h2{font-size:24px;margin:0 0 10px;text-align:center}.done.good h2{color:#0f6b4f}.done.mid h2{color:#b45309}.done.low h2{color:#176b7a}.done p{font-size:15px;line-height:1.65;font-weight:800;color:#34465b}.score-atoms{display:grid;gap:7px;margin:12px 0}.score-atoms span{border-left:3px solid #176b7a;background:#f7fafc;border-radius:10px;padding:8px 10px;font-size:13px;font-weight:900;color:#34465b}.recap{display:grid;gap:8px;margin:12px 0}.recap div{border:1px solid #d7e2ed;border-radius:12px;padding:9px 10px;font-size:13px;line-height:1.45;font-weight:800;color:#34465b}.recap .ok{background:#ecf9f2;border-color:#b7e4c7}.recap .no{background:#fff3e9;border-color:#fed7aa}.recap b{display:inline-block;margin-right:6px}.recap small{display:block;color:#607287;margin-top:4px;font-size:12px}.done a{display:flex;align-items:center;justify-content:center;background:#176b7a;color:#fff;border-radius:14px;min-height:46px;padding:0 14px;text-decoration:none;font-weight:900;text-align:center}nav{position:fixed;left:50%;bottom:0;transform:translateX(-50%);width:min(430px,100%);display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:10px 12px calc(10px + env(safe-area-inset-bottom));background:rgba(255,255,255,.96);border-top:1px solid #d2dee9;box-shadow:0 -10px 28px rgba(31,41,55,.12)}nav button{min-height:48px;border-radius:14px;border:1px solid #cfdae6;background:#fff;color:#24364b;font-weight:900}nav button:last-child{background:#176b7a;color:#fff;border-color:#176b7a}nav button.blocked{border-color:#fb923c;background:#fff7ed;color:#9a3412}
"""

_PRACTICE_JS = r"""
const data = JSON.parse(document.getElementById('practiceData').textContent);
const qs = [...document.querySelectorAll('.q')];
const selected = {};
const quiz = data.quiz || [];
const qById = Object.fromEntries(quiz.map(q => [q.id, q]));
let current = 0;
function html(s){ return String(s ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function clean(s){ return String(s || '').replace(/\s+/g,'').replace(/[，。；、,.;]/g,'').toLowerCase(); }
function includesAny(value, needles){ const v = clean(value); return needles.some(n => v.includes(clean(n))); }
function scoreSentenceResult(qEl, q){
  const inputs = [...qEl.querySelectorAll('input[data-field]')];
  const values = Object.fromEntries(inputs.map(i => [i.dataset.field, i.value.trim()]));
  const pathOk = includesAny(values.path, ['开始-A-C-E-结束','开始ACE结束','A-C-E','ACE']);
  const durationOk = includesAny(values.duration, ['10天','10']);
  const reasonOk = includesAny(values.reason, ['总时差均为0','总时差为0','A、C、E的总时差均为0','ACE总时差0']);
  inputs.forEach(input => {
    const id = input.dataset.field;
    const ok = id === 'path' ? pathOk : id === 'duration' ? durationOk : reasonOk;
    input.classList.toggle('ok', ok);
    input.classList.toggle('no', !ok && input.value.trim().length > 0);
  });
  return {values, ok: pathOk && durationOk && reasonOk, pathOk, durationOk, reasonOk};
}
function qIsDone(i){
  const q = quiz[i];
  return !!(q && selected[q.id]);
}
function flashNeedAnswer(){
  const btn = document.getElementById('nextQ');
  const original = btn.textContent;
  btn.textContent = '先独立作答';
  btn.classList.add('blocked');
  window.setTimeout(()=>{ btn.textContent = original; btn.classList.remove('blocked'); }, 900);
}
function show(i){
  current = Math.max(0, Math.min(qs.length-1, i));
  qs.forEach((q,idx)=>q.classList.toggle('active',idx===current));
  document.getElementById('progressFill').style.width = `${((current+1)/qs.length)*100}%`;
  document.getElementById('nextQ').textContent = current === qs.length - 1 ? '查看结果' : '下一题';
}
document.querySelectorAll('.option').forEach(btn=>{
  btn.addEventListener('click',()=>{
    const qEl = btn.closest('.q');
    const qid = qEl.dataset.qid;
    if(selected[qid]) return;
    const q = qById[qid];
    const opt = q.options.find(o=>o.id===btn.dataset.opt);
    const correct = btn.dataset.opt === q.answer;
    selected[qid] = btn.dataset.opt;
    qEl.querySelectorAll('.option').forEach(o=>{
      o.disabled = true;
      if(o.dataset.opt === q.answer) o.classList.add('correct');
      else if(o.dataset.opt === btn.dataset.opt) o.classList.add('wrong');
    });
    const fb = document.getElementById(`fb-${qid}`);
    fb.className = `feedback show ${correct ? 'correct':'wrong'}`;
    fb.innerHTML = `${correct ? '对。' : '再看白板。'} ${html(opt.feedback)}<span class="basis">判据：${html(q.basis || '')}${q.tier_tag ? ' · ' + html(q.tier_tag) : ''}</span>`;
  });
});
document.querySelectorAll('[data-check-score]').forEach(btn=>{
  btn.addEventListener('click',()=>{
    const qEl = btn.closest('.q');
    const qid = qEl.dataset.qid;
    const q = qById[qid];
    const result = scoreSentenceResult(qEl, q);
    selected[qid] = result;
    const fb = document.getElementById(`fb-${qid}`);
    fb.className = `feedback show ${result.ok ? 'correct':'wrong'}`;
    const miss = [
      result.pathOk ? '' : '关键线路',
      result.durationOk ? '' : '总工期',
      result.reasonOk ? '' : '总时差为 0 的理由',
    ].filter(Boolean).join('、');
    fb.innerHTML = result.ok
      ? `对。这就是主观题能拿分的表达。<span class="basis">${html(q.sample_answer || '')}</span>`
      : `还差：${html(miss)}。考试不能只写 A-C-E。<span class="basis">标准句：${html(q.sample_answer || '')}</span>`;
  });
});
document.getElementById('prevQ').addEventListener('click',()=>show(current-1));
document.getElementById('nextQ').addEventListener('click',()=>{
  if(!qIsDone(current)){ flashNeedAnswer(); return; }
  if(current < qs.length-1) show(current+1);
  else showDone();
});
function showDone(){
  qs.forEach(q=>q.classList.remove('active'));
  document.querySelector('nav').style.display = 'none';
  document.getElementById('progressFill').style.width = '100%';
  const correct = quiz.map(q => q.kind === 'score_sentence' ? !!(selected[q.id] && selected[q.id].ok) : selected[q.id] === q.answer);
  const right = correct.filter(Boolean).length;
  const keyIds = (data.mastery && data.mastery.key_discriminator_ids || quiz.filter(q=>q.key_discriminator).map(q=>q.id));
  const keyIndexes = keyIds.map(id => quiz.findIndex(q=>q.id===id)).filter(i=>i>=0);
  const all = right === quiz.length;
  const keyAllWrong = keyIndexes.length > 0 && keyIndexes.every(i => !correct[i]);
  let bucket = 'partial', cls = 'mid', title = '就差一步';
  if(all){ bucket = 'all_correct'; cls = 'good'; title = '看穿了：你是真会'; }
  else if(keyAllWrong){ bucket = 'rote_leaning'; cls = 'low'; title = '先别急着背'; }
  const warm = (data.mastery && data.mastery.warm_feedback || {});
  const done = document.getElementById('done');
  done.className = `done show ${cls}`;
  document.getElementById('verdictTitle').textContent = title;
  document.getElementById('scoreText').textContent = `${warm[bucket] || ''} 本轮 ${right}/${quiz.length}。`;
  document.getElementById('scoreAtoms').innerHTML = (data.score_atoms || []).map(x => `<span>${html(x)}</span>`).join('');
  document.getElementById('recap').innerHTML = quiz.map((q,i)=>{
    const ok = correct[i];
    const chosen = q.kind === 'score_sentence'
      ? (selected[q.id] ? '已写采分句' : '未写')
      : (selected[q.id] || '未答');
    const answer = q.kind === 'score_sentence' ? (q.sample_answer || '标准采分句') : q.answer;
    const key = keyIndexes.includes(i) ? ' · 关键鉴别题' : '';
    return `<div class="${ok ? 'ok' : 'no'}"><b>${ok ? '✓' : '×'}</b>${html(q.tier_tag || q.question)}${key}<small>你的回答：${html(chosen)}；标准：${html(answer)}。${html(q.basis || '')}</small></div>`;
  }).join('');
}
show(0);
"""


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: render_network_video_first.py N01_network_video_first.json [lesson.html]")
        return 2
    card_path = Path(argv[1])
    out = Path(argv[2]) if len(argv) > 2 else card_path.with_suffix(".rendered.html")
    card = json.loads(card_path.read_text(encoding="utf-8"))
    cpm = validate_video_card(card)
    practice_name = card_path.stem + ".practice.html"
    out.write_text(lesson_html(card, cpm, card_path, practice_name), encoding="utf-8")
    practice_out = out.with_name(practice_name)
    practice_out.write_text(practice_html(card, cpm, out.name), encoding="utf-8")
    print(f"rendered lesson: {out}")
    print(f"rendered practice: {practice_out}")
    print(f"  beats={len(card.get('video_beats') or [])} duration={cpm['project_duration']} critical_path={'-'.join(card['question_data']['expected']['critical_path'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
