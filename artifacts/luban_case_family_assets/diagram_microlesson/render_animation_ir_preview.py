#!/usr/bin/env python3
"""Render a student-safe HTML preview from luban_animation_ir.v0.

This is the OpenMAIC-style path: animation IR declares scene/focus/enter/exit;
the renderer deterministically draws one active scene at a time. It does not
infer visual state from accumulated `reached-*` classes.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def js_json(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _section_svg(scene_id: str) -> str:
    overlays: dict[str, str] = {
        "hook": """
          <g data-visible-node="wrong_phrase"><rect x="48" y="70" width="264" height="44" rx="12" fill="#fff7ed" stroke="#f97316" stroke-width="3"/><text x="180" y="98" text-anchor="middle" font-size="18" font-weight="900" fill="#9a3412">错觉:只写“修补防水层”</text></g>
          <g data-visible-node="score_goal"><rect x="76" y="138" width="208" height="54" rx="14" fill="#ecfdf5" stroke="#10b981" stroke-width="3"/><text x="180" y="161" text-anchor="middle" font-size="15" font-weight="900" fill="#047857">目标:写出修补闭环</text><text x="180" y="181" text-anchor="middle" font-size="13" font-weight="800" fill="#047857">治因 → 闭合 → 检验</text></g>
        """,
        "disease": """
          <g data-visible-node="roof_section"><rect x="32" y="176" width="296" height="52" rx="4" fill="#87919d"/><rect x="32" y="160" width="296" height="16" fill="#c5b78f"/><rect x="32" y="148" width="296" height="12" fill="#34465b"/></g>
          <g data-visible-node="bulge"><path d="M146 148 Q180 92 214 148 Z" fill="#34465b" stroke="#7fc7ff" stroke-width="3"/><text x="180" y="88" text-anchor="middle" font-size="16" font-weight="900" fill="#7fc7ff">气/水汽顶起卷材</text></g>
          <g data-visible-node="vapour_arrows"><path d="M164 144 V116 M180 144 V108 M196 144 V116" stroke="#ffd27f" stroke-width="4" stroke-linecap="round"/><path d="M158 120 l6 -8 l6 8 M174 112 l6 -8 l6 8 M190 120 l6 -8 l6 8" fill="none" stroke="#ffd27f" stroke-width="3"/></g>
        """,
        "cut": """
          <g data-visible-node="roof_section"><rect x="32" y="176" width="296" height="52" rx="4" fill="#87919d"/><rect x="32" y="160" width="296" height="16" fill="#c5b78f"/><rect x="32" y="148" width="296" height="12" fill="#34465b"/></g>
          <g data-visible-node="cut_cross"><path d="M162 162 L198 126 M162 126 L198 162" stroke="#ef4444" stroke-width="8" stroke-linecap="round"/><text x="180" y="106" text-anchor="middle" font-size="17" font-weight="900" fill="#fecaca">割开放气</text></g>
          <g data-visible-node="gas_escape"><path d="M180 128 V84" stroke="#fecaca" stroke-width="4"/><path d="M170 94 l10 -14 l10 14" fill="none" stroke="#fecaca" stroke-width="4"/></g>
          <g data-visible-node="direct_cover_trap"><text x="180" y="235" text-anchor="middle" font-size="14" font-weight="900" fill="#f97316">不先放气,直接盖层还会再鼓</text></g>
        """,
        "dry": """
          <g data-visible-node="roof_section"><rect x="32" y="176" width="296" height="52" rx="4" fill="#87919d"/><rect x="32" y="160" width="296" height="16" fill="#c5b78f"/><rect x="32" y="148" width="296" height="12" fill="#34465b"/></g>
          <g data-visible-node="dry_zone"><rect x="120" y="142" width="120" height="38" rx="8" fill="none" stroke="#7fc7ff" stroke-width="5" stroke-dasharray="9 7"/><text x="180" y="118" text-anchor="middle" font-size="17" font-weight="900" fill="#7fc7ff">排气干燥</text></g>
          <g data-visible-node="old_glue"><path d="M126 184 H234" stroke="#ffd27f" stroke-width="5" stroke-linecap="round"/><text x="180" y="210" text-anchor="middle" font-size="14" font-weight="900" fill="#ffd27f">清除旧胶结料 / 清基层</text></g>
        """,
        "add": """
          <g data-visible-node="roof_section"><rect x="32" y="176" width="296" height="52" rx="4" fill="#87919d"/><rect x="32" y="160" width="296" height="16" fill="#c5b78f"/><rect x="32" y="148" width="296" height="12" fill="#34465b"/></g>
          <g data-visible-node="reinforcement_layer"><rect x="112" y="136" width="136" height="14" rx="5" fill="#10b981"/><text x="180" y="118" text-anchor="middle" font-size="17" font-weight="900" fill="#bbf7d0">增铺附加层</text></g>
          <g data-visible-node="edge_coverage"><path d="M112 156 v18 M248 156 v18 M112 166 H248" stroke="#bbf7d0" stroke-width="4" fill="none"/><text x="180" y="198" text-anchor="middle" font-size="14" font-weight="900" fill="#bbf7d0">盖过病害边缘</text></g>
        """,
        "seal": """
          <g data-visible-node="roof_section"><rect x="32" y="176" width="296" height="52" rx="4" fill="#87919d"/><rect x="32" y="160" width="296" height="16" fill="#c5b78f"/><rect x="32" y="148" width="296" height="12" fill="#34465b"/></g>
          <g data-visible-node="new_membrane_lap"><rect x="88" y="128" width="184" height="14" rx="5" fill="#60a5fa"/><text x="180" y="108" text-anchor="middle" font-size="17" font-weight="900" fill="#bfdbfe">新卷材搭接</text></g>
          <g data-visible-node="lap_joint"><path d="M88 150 C126 174 230 174 272 150" stroke="#bfdbfe" stroke-width="4" fill="none" stroke-dasharray="10 7"/></g>
          <g data-visible-node="seal_edge"><text x="180" y="204" text-anchor="middle" font-size="14" font-weight="900" fill="#bfdbfe">边缘和搭接缝封严</text></g>
        """,
        "test": """
          <g data-visible-node="roof_section"><rect x="32" y="176" width="296" height="52" rx="4" fill="#87919d"/><rect x="32" y="160" width="296" height="16" fill="#c5b78f"/><rect x="32" y="148" width="296" height="12" fill="#34465b"/></g>
          <g data-visible-node="water_layer"><rect x="32" y="116" width="296" height="24" rx="6" fill="#7fc7ff" opacity=".72"/><text x="180" y="99" text-anchor="middle" font-size="17" font-weight="900" fill="#bfdbfe">蓄水 / 淋水检验</text></g>
          <g data-visible-node="result_tick"><circle cx="180" cy="198" r="24" fill="#052e1a" stroke="#10b981" stroke-width="4"/><text x="180" y="207" text-anchor="middle" font-size="26" font-weight="900" fill="#bbf7d0">✓</text></g>
        """,
    }
    return f"""<svg viewBox="0 0 360 270" role="img" aria-label="屋面卷材起鼓割补教学图">
      <rect x="12" y="18" width="336" height="234" rx="22" fill="#101b28" stroke="#24364b" stroke-width="2"/>
      {overlays.get(scene_id, overlays["disease"])}
    </svg>"""


def _answer_paper_svg() -> str:
    return """<svg viewBox="0 0 360 270" role="img" aria-label="答题纸采分句">
      <rect x="28" y="32" width="304" height="206" rx="18" fill="#fffdf7" stroke="#eadfcb" stroke-width="4"/>
      <text x="54" y="72" font-size="15" font-weight="900" fill="#176b7a">答题纸这样写</text>
      <g data-visible-node="answer_paper"><rect x="54" y="96" width="252" height="36" rx="10" fill="#ecfdf5" stroke="#10b981" stroke-width="2"/><text x="180" y="120" text-anchor="middle" font-size="14" font-weight="900" fill="#047857">割开放气 + 排气干燥 + 清旧胶</text></g>
      <g data-visible-node="score_sentence"><rect x="54" y="144" width="252" height="36" rx="10" fill="#eff6ff" stroke="#60a5fa" stroke-width="2"/><text x="180" y="168" text-anchor="middle" font-size="14" font-weight="900" fill="#1d4ed8">附加层 + 搭接封严 + 蓄水检验</text></g>
      <g data-visible-node="score_atoms"><text x="180" y="210" text-anchor="middle" font-size="13" font-weight="900" fill="#b45309">不是写结论,是写采分动作</text></g>
    </svg>"""


def _dialogue_svg() -> str:
    return """<svg viewBox="0 0 360 270" role="img" aria-label="常见错误答疑">
      <rect x="18" y="26" width="324" height="218" rx="22" fill="#101b28" stroke="#24364b" stroke-width="2"/>
      <g data-visible-node="mini_section"><rect x="46" y="164" width="268" height="42" rx="4" fill="#87919d"/><rect x="46" y="150" width="268" height="14" fill="#c5b78f"/><rect x="46" y="138" width="268" height="12" fill="#34465b"/></g>
      <g data-visible-node="current_question"><rect x="46" y="54" width="268" height="42" rx="12" fill="#321a1c" stroke="#ef4444" stroke-width="2"/><text x="180" y="80" text-anchor="middle" font-size="14" font-weight="900" fill="#fecaca">能不能省掉基层/附加层/检验?</text></g>
      <g data-visible-node="teacher_answer"><rect x="62" y="106" width="236" height="36" rx="12" fill="#16321f" stroke="#10b981" stroke-width="2"/><text x="180" y="129" text-anchor="middle" font-size="14" font-weight="900" fill="#bbf7d0">漏闭合,就漏分</text></g>
    </svg>"""


def _closing_svg() -> str:
    return """<svg viewBox="0 0 360 270" role="img" aria-label="收尾闯关">
      <rect x="24" y="34" width="312" height="198" rx="22" fill="#10251a" stroke="#10b981" stroke-width="3"/>
      <g data-visible-node="closing_sentence"><text x="180" y="92" text-anchor="middle" font-size="18" font-weight="900" fill="#bbf7d0">三步闭环</text><text x="180" y="132" text-anchor="middle" font-size="20" font-weight="900" fill="#ecfdf5">治病因 → 恢复闭合 → 检验</text></g>
      <g data-visible-node="challenge_cta"><rect x="90" y="166" width="180" height="44" rx="22" fill="#ffd27f"/><text x="180" y="194" text-anchor="middle" font-size="17" font-weight="900" fill="#0f1722">开始闯关</text></g>
    </svg>"""


def _scene_visual(scene: dict[str, Any]) -> str:
    sid = str(scene["id"])
    if sid == "score":
        return _answer_paper_svg()
    if sid == "qa_closure":
        return _dialogue_svg()
    if sid == "closing_challenge":
        return _closing_svg()
    return _section_svg(sid)


def _scene_actions(scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive a deterministic OpenMAIC-style action queue for preview playback."""
    nodes = list(scene.get("visible_nodes", []))
    actions: list[dict[str, Any]] = []
    for index, node_id in enumerate(nodes):
        start = round(0.04 + index * 0.14, 3)
        actions.append({"kind": "reveal", "target": node_id, "start": start, "end": round(start + 0.18, 3)})
    focus = scene.get("focus")
    if focus:
        actions.append({"kind": "highlight", "target": focus, "start": 0.22, "end": 0.92})
    camera = scene.get("camera", {})
    actions.append(
        {
            "kind": "camera",
            "verb": camera.get("verb", "spotlight"),
            "target": camera.get("target", focus or (nodes[0] if nodes else "scene")),
            "start": 0,
            "end": min(0.42, float(camera.get("duration_sec", 0.42) or 0.42)),
        }
    )
    return actions


def render(ir_path: Path) -> str:
    ir = json.loads(ir_path.read_text(encoding="utf-8"))
    base = ir_path.parent
    timing_path = base / ir["source_refs"]["timing"]
    timing = json.loads(timing_path.read_text(encoding="utf-8")) if timing_path.exists() else {}
    audio = ir["source_refs"].get("audio", "")
    practice_href = ir.get("render_contract", {}).get("practice_href", "")
    max_nodes = int(ir.get("render_contract", {}).get("max_visible_nodes", 4))

    scenes = ir["scenes"]
    student_data = {
        "title": "屋面卷材防水起鼓怎么修补",
        "subtitle": ir["main_exam_action"],
        "totalSec": timing.get("totalSec", scenes[-1]["end_sec"]),
        "audio": audio,
        "practiceHref": practice_href,
        "maxVisibleNodes": max_nodes,
        "chapters": ir["chapters"],
        "segments": [
            {
                "start": seg.get("startSec", 0),
                "end": seg.get("startSec", 0) + seg.get("durSec", 0),
                "text": seg.get("text", ""),
                "speaker": seg.get("speaker", "T"),
                "kind": seg.get("kind", ""),
            }
            for seg in timing.get("segments", [])
        ],
        "scenes": [
            {
                "id": s["id"],
                "label": s["label"],
                "start": s["start_sec"],
                "end": s["end_sec"],
                "focus": s["focus"],
                "camera": s["camera"]["verb"],
                "keycard": s["keycard"],
                "coach": s["coach"],
                "visibleNodes": s["visible_nodes"],
                "actions": _scene_actions(s),
            }
            for s in scenes
        ],
    }
    chapters_html = "".join(
        f'<button class="chapter" type="button" data-t="{c["start_sec"]}">{esc(c["label"])}</button>'
        for c in ir["chapters"]
        if c["id"] != "challenge"
    )
    scenes_html = "\n".join(
        f"""<section class="scene" data-scene-id="{esc(s["id"])}" data-focus="{esc(s["focus"])}" data-visible-count="{len(s["visible_nodes"])}">
  <div class="visual">{_scene_visual(s)}</div>
  <div class="coach-card" data-info-node="keycard"><b>{esc(s["keycard"])}</b><span>{esc(s["coach"])}</span></div>
</section>"""
        for s in scenes
    )
    css = """
*{box-sizing:border-box}html,body{margin:0;max-width:100%;overflow-x:hidden}body{background:#0d1723;color:#eef3f8;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}.lesson{max-width:460px;margin:0 auto;min-height:100vh;padding:14px 12px 132px}.top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.kicker{font-size:12px;font-weight:900;color:#ffd27f;margin:0 0 6px}.top h1{font-size:22px;line-height:1.2;margin:0}.time{border:1px solid #31445c;border-radius:999px;padding:7px 10px;color:#cfe0f0;font-size:12px;font-weight:900;white-space:nowrap}.subtitle{margin:10px 0 12px;color:#9fb0c2;font-size:13px;font-weight:800;line-height:1.5}.stage{--camera-scale:1;--camera-x:0px;--camera-y:0px;position:relative;background:#13202e;border:1px solid #24364b;border-radius:20px;min-height:430px;display:grid;align-items:center;overflow:hidden;cursor:pointer;touch-action:manipulation}.scene{display:none;padding:16px}.scene.active{display:grid;gap:12px;animation:sceneIn .2s ease-out}.visual{position:relative;min-height:270px;display:grid;place-items:center;transform:translate3d(var(--camera-x),var(--camera-y),0) scale(var(--camera-scale));transition:transform .12s linear;will-change:transform}.visual svg{width:100%;height:auto;display:block}[data-visible-node]{opacity:0;transform-box:fill-box;transform-origin:center;will-change:opacity,transform,filter}.node-focus{filter:drop-shadow(0 0 9px rgba(255,210,127,.75))}.coach-card{border-left:4px solid #ffd27f;background:#172434;border-radius:14px;padding:12px 13px;box-shadow:0 12px 30px rgba(0,0,0,.22);transition:opacity .18s,transform .18s}.coach-card b{display:block;color:#ffd27f;font-size:15px;line-height:1.35;margin-bottom:6px}.coach-card span{display:block;color:#dbe6f1;font-size:14px;line-height:1.55;font-weight:800}.caption-line{position:absolute;left:14px;right:14px;bottom:14px;z-index:4;min-height:40px;padding:10px 13px;border-radius:13px;background:rgba(9,17,27,.82);border:1px solid rgba(207,224,240,.18);box-shadow:0 14px 32px rgba(0,0,0,.28);color:#eef6ff;font-size:14px;font-weight:900;line-height:1.45;text-align:center;backdrop-filter:blur(8px)}.caption-line[data-speaker="S"]{color:#d7e9ff;border-color:rgba(96,165,250,.35)}.center-play{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);z-index:5;border:0;border-radius:999px;background:#ffd27f;color:#0f1722;font-size:17px;font-weight:900;padding:16px 24px;box-shadow:0 18px 44px rgba(0,0,0,.35)}.lesson.started .center-play{display:none}.challenge-inline{display:flex;align-items:center;justify-content:center;margin:12px 0 0;min-height:46px;border-radius:14px;border:1px dashed #3a4a60;color:#cfe0f0;text-decoration:none;font-weight:900}.player{position:fixed;left:0;right:0;bottom:0;background:rgba(13,23,35,.96);border-top:1px solid #233148;backdrop-filter:blur(10px);padding:10px 12px calc(10px + env(safe-area-inset-bottom));z-index:20;transition:opacity .18s ease,transform .18s ease}.player-inner{max-width:460px;margin:0 auto}.row{display:flex;align-items:center;gap:10px}.play,.theater,.challenge{border:1px solid #3a4a60;background:#162234;color:#cfe0f0;font-weight:900;border-radius:999px;height:44px}.play{width:54px;border:0;background:#ffd27f;color:#0f1722;font-size:20px}.theater{width:58px}.challenge{min-width:64px;text-decoration:none;display:flex;align-items:center;justify-content:center;color:#ffd27f;border-color:#5a421c;background:#211a0c}.progress{flex:1;min-width:0}.ptime{display:flex;justify-content:space-between;color:#9fb0c2;font-size:12px;font-weight:800;margin-bottom:4px}.bar{height:8px;border-radius:999px;background:#26344a;overflow:hidden}.fill{height:100%;width:0;background:#ffd27f}.scrubber{width:100%;accent-color:#ffd27f;margin-top:7px}.chapters{display:flex;gap:6px;margin-top:8px}.chapter{flex:1;border:1px solid #2b3b50;background:#172434;color:#9fb0c2;border-radius:9px;min-height:34px;font-weight:900}.chapter.on{background:#ffd27f;color:#0f1722;border-color:#ffd27f}@keyframes sceneIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}.lesson.theater{max-width:none;padding:0;background:#0d1723}.lesson.theater .top,.lesson.theater .subtitle,.lesson.theater .challenge-inline{display:none}.lesson.theater .stage{position:fixed;inset:0;border:0;border-radius:0;min-height:0;transition:inset .18s ease}.lesson.theater.controls-visible .stage{inset:0 0 124px 0}.lesson.theater .scene{height:100%;align-content:center;padding:24px}.lesson.theater .visual{min-height:0}.lesson.theater .visual svg{max-height:62vh}.lesson.theater .coach-card{margin-top:4px}.lesson.theater .caption-line{bottom:18px;left:18px;right:18px;font-size:15px}.lesson.theater.controls-visible .caption-line{bottom:16px}.lesson.theater .player{z-index:40;opacity:0;transform:translateY(105%);pointer-events:none}.lesson.theater.controls-visible .player{opacity:1;transform:none;pointer-events:auto}@media (orientation:landscape),(min-width:760px){.lesson{max-width:980px}.stage{min-height:420px}.scene.active{grid-template-columns:minmax(0,1.35fr) minmax(260px,.65fr);align-items:center}.visual{min-height:330px}.coach-card{align-self:center}.lesson.theater .scene.active{grid-template-columns:minmax(0,1.2fr) minmax(260px,.55fr)}.lesson.theater .visual svg{max-height:76vh}.lesson.theater .caption-line{left:8%;right:8%;bottom:20px}}@media(max-width:420px){.top h1{font-size:20px}.stage{min-height:430px}.scene{padding:12px}.coach-card b{font-size:14px}.coach-card span{font-size:13px}.caption-line{font-size:13px}.chapter{font-size:12px}}
"""
    return f"""<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>F16 起鼓割补 · IR 预览</title><style>{css}</style></head>
<body>
<main class="lesson orientation-adaptive" data-card-id="{esc(ir['card_id'])}" data-stage-shell="animation-ir-preview" data-animation-ir-preview="v0">
  <div class="top"><div><p class="kicker">鲁班深母题 · F16 起鼓割补</p><h1>屋面卷材防水起鼓怎么修补</h1></div><div class="time"><span id="cur">0:00</span> / <span id="tot">0:00</span></div></div>
  <p class="subtitle">{esc(ir['main_exam_action'])}</p>
  <div class="stage" id="stage" data-stage-shell="visual-stage">
    {scenes_html}
    <div class="caption-line" id="captionLine" data-caption="1" data-speaker="T"></div>
    <button class="center-play" id="centerPlay" type="button">播放讲解</button>
  </div>
  <a class="challenge-inline" href="{esc(practice_href)}" data-challenge-cta="inline">直接进入闯关 →</a>
  <div class="player controls" id="player">
    <div class="player-inner">
      <div class="row">
        <button class="play" id="play" type="button">▶</button>
        <button class="theater" id="theaterToggle" data-theater-toggle="1" type="button">全屏</button>
        <div class="progress"><div class="ptime"><span id="cur2">0:00</span><span id="tot2">0:00</span></div><div class="bar"><div class="fill" id="fill"></div></div><input class="scrubber" id="scrubber" type="range" min="0" max="{student_data['totalSec']}" value="0" step="0.05" aria-label="拖动播放进度"></div>
        <a class="challenge" href="{esc(practice_href)}" data-challenge-cta="controls">闯关</a>
      </div>
      <div class="chapters">{chapters_html}</div>
    </div>
  </div>
  <audio id="au" preload="metadata"{' src="' + esc(audio) + '"' if audio else ''}></audio>
</main>
<script type="application/json" id="irPreviewData">{js_json(student_data)}</script>
<script>
const DATA=JSON.parse(document.getElementById('irPreviewData').textContent);
const lesson=document.querySelector('.lesson'),au=document.getElementById('au'),play=document.getElementById('play'),centerPlay=document.getElementById('centerPlay'),scrubber=document.getElementById('scrubber'),fill=document.getElementById('fill');
const cur=document.getElementById('cur'),cur2=document.getElementById('cur2'),tot=document.getElementById('tot'),tot2=document.getElementById('tot2'),theaterToggle=document.getElementById('theaterToggle'),stage=document.getElementById('stage'),player=document.getElementById('player'),captionLine=document.getElementById('captionLine');
const scenes=[...document.querySelectorAll('.scene')],chapters=[...document.querySelectorAll('.chapter')];
const fmt=s=>{{s=Math.max(0,Math.floor(s||0));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');}};
let raf=0,hideTimer=0,lastScene='';
tot.textContent=tot2.textContent=fmt(DATA.totalSec);
const clamp01=x=>Math.max(0,Math.min(1,x));
const ease=x=>{{x=clamp01(x);return 1-Math.pow(1-x,3);}};
function sceneAt(t){{return DATA.scenes.find(s=>t>=s.start-0.05&&t<s.end-0.05)||DATA.scenes[DATA.scenes.length-1];}}
function segmentAt(t){{return (DATA.segments||[]).find(s=>t>=s.start-0.05&&t<s.end-0.05)||(DATA.segments||[]).at(-1)||{{text:'',speaker:'T'}};}}
function setControls(visible=true,auto=true){{clearTimeout(hideTimer);lesson.classList.toggle('controls-visible',visible);if(visible&&auto&&lesson.classList.contains('theater')&&!au.paused)hideTimer=setTimeout(()=>lesson.classList.remove('controls-visible'),2600);}}
function applyMotion(activeEl,active,t){{if(!activeEl)return;const dur=Math.max(.001,active.end-active.start),p=clamp01((t-active.start)/dur),nodes=[...activeEl.querySelectorAll('[data-visible-node]')],actions=active.actions||[];const cameraAction=actions.find(a=>a.kind==='camera')||{{verb:active.camera,start:0,end:.28}},cameraVerb=cameraAction.verb||active.camera;const cameraPush=cameraVerb==='push-in'||cameraVerb==='spotlight'||cameraVerb==='answer-paper'||cameraVerb==='trace';const cameraP=ease((p-(cameraAction.start||0))/Math.max(.05,(cameraAction.end||.28)-(cameraAction.start||0)));stage.style.setProperty('--camera-scale',String(1+(cameraPush?0.035*cameraP:0)));stage.style.setProperty('--camera-y',(cameraVerb==='pull-back'?String(-8*ease(p)):'0')+'px');nodes.forEach((node,i)=>{{const name=node.dataset.visibleNode||'';const reveal=actions.find(a=>a.kind==='reveal'&&a.target===name)||{{start:.04+i*.14,end:.22+i*.14}};const v=ease((p-reveal.start)/Math.max(.05,reveal.end-reveal.start));const highlighted=actions.some(a=>a.kind==='highlight'&&(a.target===name||name===a.target||name.includes(a.target))&&p>=a.start&&p<=a.end)||name===active.focus||name.includes(active.focus);node.style.opacity=String(v);node.style.transform=`translateY(${{(1-v)*10}}px) scale(${{0.96+v*0.04}})`;node.classList.toggle('node-focus',highlighted);}});if(active.id!==lastScene){{scenes.forEach(scene=>{{if(scene!==activeEl)scene.querySelectorAll('[data-visible-node]').forEach(node=>{{node.style.opacity='0';node.style.transform='translateY(10px) scale(.96)';node.classList.remove('node-focus');}});}});lastScene=active.id;}}}}
function paint(){{const t=Number(au.currentTime||scrubber.value||0);const active=sceneAt(t);const seg=segmentAt(t);lesson.classList.add('started');lesson.classList.toggle('paused',au.paused);lesson.classList.toggle('playing',!au.paused);let activeEl=null;scenes.forEach(el=>{{const on=el.dataset.sceneId===active.id;el.classList.toggle('active',on);if(on)activeEl=el;}});const visual=activeEl?.querySelector('.visual');if(visual&&captionLine.parentElement!==visual)visual.appendChild(captionLine);applyMotion(activeEl,active,t);chapters.forEach(el=>el.classList.toggle('on',t>=Number(el.dataset.t)&&Number(el.dataset.t)>=active.start-0.1));fill.style.width=(Math.min(t,DATA.totalSec)/DATA.totalSec*100)+'%';scrubber.value=String(Math.min(t,DATA.totalSec));cur.textContent=cur2.textContent=fmt(t);captionLine.textContent=seg.text||active.coach||'';captionLine.dataset.speaker=seg.speaker||'T';}}
function loop(){{paint();if(!au.paused)raf=requestAnimationFrame(loop);}}
function startLoop(){{cancelAnimationFrame(raf);raf=requestAnimationFrame(loop);}}
function seek(t){{au.currentTime=Math.max(0,Math.min(DATA.totalSec,Number(t)||0));scrubber.value=String(au.currentTime);paint();setControls(true);}}
function playAudio(){{lesson.classList.add('started');return au.play().then(()=>{{play.textContent='⏸';setControls(true);startLoop();}}).catch(()=>{{paint();}});}}
function toggle(){{if(au.paused)playAudio();else{{au.pause();play.textContent='▶';setControls(true,false);paint();}}}}
play.addEventListener('click',toggle);centerPlay.addEventListener('click',playAudio);au.addEventListener('timeupdate',paint);au.addEventListener('ended',()=>{{play.textContent='▶';seek(DATA.totalSec);setControls(true,false);}});
scrubber.addEventListener('input',()=>seek(scrubber.value));chapters.forEach(btn=>btn.addEventListener('click',()=>{{seek(btn.dataset.t);playAudio();}}));
stage.addEventListener('click',e=>{{if(e.target===centerPlay)return;if(lesson.classList.contains('theater'))setControls(true);}});
player.addEventListener('click',e=>e.stopPropagation());
theaterToggle.addEventListener('click',()=>{{lesson.classList.toggle('theater');theaterToggle.textContent=lesson.classList.contains('theater')?'退出':'全屏';setControls(true);paint();}});
window.__IR_PLAYER__={{seek,paint,state:()=>({{time:Number(au.currentTime||0),scene:sceneAt(Number(au.currentTime||0)).id}})}};
seek(0);setControls(false,false);
</script></body></html>"""


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: render_animation_ir_preview.py <animation_ir.v0.json>", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    out = src.with_name(src.name.replace(".animation_ir.v0.json", ".animation_ir_preview.html"))
    out.write_text(render(src), encoding="utf-8")
    print(f"✅ {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
