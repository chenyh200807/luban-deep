#!/usr/bin/env python3
"""深母题学习闭环渲染器 —— 一镜到底·无缝流动(讲懂 → 闯关 → 看穿)。

输入: <master>.master.json(顶层)。据 teaching_lesson_ref 加载讲懂层(教学动画脚本 +
  其 .lesson.timing.json + mp3),据 variants 渲染闯关,据 mastery_discrimination 渲染看穿。
输出: <master>.journey.html —— 一条连续流,系统自动带着走(不整屏硬切、不跳顶):
  ① 讲懂:PPT 式教学动画(基坑 SVG + 关键词卡逐点飞入 + 旁白时间轴)+ 双人答疑。
  ② 闯关:讲完自动浮现 V1-V4,答完一题自动滑入下一题(平滑滚动,旧题留上方可回看)。
  ③ 看穿:4 题完自动滑入,读 master signal 判真懂/就差一步/背过 + 暖反馈 + 四题回看。

单一权威:看穿判定只读 master.mastery_discrimination 的 signal,不另造标准;渲染器只展示。
student-safe:闯关/看穿只渲染 stem/options/feedback/warm 文案。
看穿是自测鉴别候选(authority.official_score_allowed=false,终判归 LearnerStateService),非正式判分。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import render_teaching_animation as ta  # 复用:基坑 SVG、helpers、state 序列(单一来源)

esc, js_json = ta.esc, ta.js_json


_EXTRA_CSS = """
.wrap{padding:12px 14px 132px}
.lesson.orientation-adaptive{max-width:640px}
.topline{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin:2px 0 8px}
.titlegroup{min-width:0}
.topline h1{margin-bottom:0}
.timepill{flex:0 0 auto;border:1px solid #31445c;border-radius:999px;padding:8px 12px;color:#cfe0f0;font-weight:800;font-size:13px;background:#121d2a}
.quick-options{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:8px 0 10px}
.quick-options button{border:1px solid #2d4158;border-radius:9px;background:#142031;color:#94a8bd;
  min-height:32px;font-size:12px;font-weight:800}
.quick-options button.active{border-color:#ffd27f;color:#ffd27f;background:#211a0c}
.stagebox{position:relative}
.stage{position:relative;display:grid;place-items:center;min-height:300px;aspect-ratio:5/4;overflow:hidden}
.stage svg{width:100%;height:100%;object-fit:contain}
.stage .banner{position:absolute;left:12px;right:12px;bottom:10px;z-index:2}
.score-strip{position:absolute;left:12px;right:12px;bottom:58px;z-index:2;display:flex;flex-wrap:wrap;gap:6px;
  opacity:0;transform:translateY(6px);transition:opacity .4s,transform .4s}
.reached-conclude .score-strip{opacity:1;transform:none}
.score-strip span{background:#211a0c;border:1px solid #5a421c;color:#ffd27f;border-radius:999px;padding:4px 9px;font-size:11.5px;font-weight:800}
.caption{position:fixed;left:50%;bottom:118px;transform:translateX(-50%);width:min(560px,calc(100vw - 28px));
  z-index:32;box-shadow:0 14px 44px rgba(0,0,0,.24)}
.center-play{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);z-index:4;
  border:none;border-radius:999px;background:#ffd27f;color:#0f1722;font-size:16px;font-weight:900;
  padding:16px 22px;box-shadow:0 12px 36px rgba(0,0,0,.28);cursor:pointer}
.lesson.started .center-play{display:none}
.player{transition:transform .45s,opacity .45s}
.player.hide{transform:translateY(135%);opacity:0;pointer-events:none}
.steps{display:flex;gap:6px;margin:2px 0 12px;position:sticky;top:0;z-index:5;
  background:linear-gradient(#0f1722,#0f1722f0);padding:8px 0 6px}
.step{flex:1;text-align:center;font-size:12px;color:#6c7d92;background:#161f2b;border:1px solid #243247;border-radius:9px;padding:7px 2px;font-weight:700}
.step.on{color:#0f1722;background:#ffd27f;border-color:#ffd27f}
.step.done{color:#3fd39a;border-color:#26513c}
.keycards{display:flex;flex-direction:column;gap:6px;margin-top:10px}
.kc{opacity:0;transform:translateX(-12px);transition:opacity .4s,transform .4s;
  background:#16202d;border-left:3px solid #3a4a60;border-radius:8px;padding:8px 12px;font-size:13.5px;font-weight:700;color:#dbe6f1}
.kc.in{opacity:1;transform:none}
.kc-q{border-left-color:#7fc7ff;color:#cfe6fb}
.kc-a{border-left-color:#3fd39a;color:#cdeedd}
.kc-concl{border-left-color:#ffd27f;color:#ffe7bd;background:#231d10}
.kc-score{border-left-color:#e08a1e;color:#ffd9a6}
/* 连续流:锁定段折叠隐藏,reveal 时平滑展开 + 滑入 */
.seg{overflow:hidden;max-height:0;opacity:0;transform:translateY(16px);
  transition:max-height .6s ease,opacity .55s ease,transform .55s ease}
.seg.open{max-height:4000px;opacity:1;transform:none}
	.skip{display:block;width:100%;margin:14px 0 2px;padding:11px;border:1px dashed #3a4a60;border-radius:12px;
	  background:transparent;color:#9fb0c2;font-size:13.5px;cursor:pointer;text-align:center;text-decoration:none}
.bridge{margin-top:18px}
.section-tag{font-size:12px;letter-spacing:.1em;color:#7fc7ff;font-weight:800;margin:18px 2px 10px}
.qlabel{font-size:12px;color:#9fb0c2;font-weight:700;margin:0 0 8px}
.qlabel b{color:#7fc7ff}
.qblock{padding:2px 0 6px;border-top:1px solid #1d2735;margin-top:14px}
.qblock:first-of-type{border-top:none}
.qstem{font-size:16.5px;line-height:1.55;font-weight:700;margin:0 0 14px;color:#eef3f8}
.qopt{display:block;width:100%;text-align:left;margin:9px 0;padding:13px 15px;border-radius:13px;
  background:#1a2533;border:1.5px solid #2b3b50;color:#dbe6f1;font-size:14.5px;line-height:1.5;cursor:pointer}
.qopt:active{transform:scale(.99)}
.qopt.correct{border-color:#3fd39a;background:#16321f}
.qopt.wrong{border-color:#e0575a;background:#321a1c}
.qopt[disabled]{cursor:default;opacity:.92}
.qfb{margin:12px 0 2px;padding:12px 14px;border-radius:12px;font-size:14px;line-height:1.6;display:none}
.qfb.show{display:block}
.qfb.ok{background:#16321f;border:1px solid #1f7a4d;color:#bff0d4}
.qfb.no{background:#2a1c20;border:1px solid #7a3540;color:#f3c9cd}
	.qfb .tier{display:inline-block;margin-top:6px;font-size:11.5px;color:#9fb0c2;font-weight:700}
	.qfb .nexthint{display:block;margin-top:8px;font-size:12px;color:#7fc7ff;opacity:.85}
.vcard{border-radius:16px;padding:18px 16px;margin:6px 0 14px;text-align:center}
.vcard.good{background:#143020;border:1px solid #2a7a4f}
.vcard.mid{background:#322a12;border:1px solid #7a6326}
.vcard.low{background:#152a3a;border:1px solid #2a5a7a}
.vtitle{font-size:21px;font-weight:800;margin:0 0 8px}
.vcard.good .vtitle{color:#7fe6ab}.vcard.mid .vtitle{color:#ffd27f}.vcard.low .vtitle{color:#7fc7ff}
.vtext{font-size:14.5px;line-height:1.65;color:#e7eef6}
.vscore{font-size:13px;color:#9fb0c2;margin-top:10px}
.recap{margin:6px 0 14px}
.recap .rl{font-size:12px;color:#9fb0c2;font-weight:700;margin:0 0 8px;letter-spacing:.05em}
	.rrow{display:flex;align-items:flex-start;gap:9px;padding:9px 11px;background:#16202d;border-radius:10px;margin:7px 0;font-size:13.5px;line-height:1.5}
	.rrow .mk{flex:0 0 auto;font-weight:800}
	.rrow.ok .mk{color:#3fd39a}.rrow.no .mk{color:#e0575a}
	.rrow .key{display:inline-block;margin-left:6px;font-size:11px;color:#ffd27f;font-weight:700;border:1px solid #4a3a1e;border-radius:6px;padding:1px 6px}
	.rrow .basis-text{color:#9fb0c2;font-size:12px}
.cta{display:block;width:100%;margin:12px 0 4px;padding:14px;border:none;border-radius:14px;
  background:#ffd27f;color:#16202d;font-size:15px;font-weight:800;cursor:pointer}
.cta.ghost{background:#1a2533;color:#cfe0f0}
.mnote{font-size:11.5px;color:#7e8da0;line-height:1.6;margin-top:4px}
.scrubber{width:100%;margin:8px 0 0;accent-color:#ffd27f}
	.lesson.theater{max-width:none;padding:0;background:#0f1722}
.lesson.theater .steps,.lesson.theater .topline,.lesson.theater .quick-options,
.lesson.theater .subtitle,.lesson.theater .caption,.lesson.theater .qa,
.lesson.theater .skip,.lesson.theater .bridge,.lesson.theater .qblock,
.lesson.theater #verdictSec,.lesson.theater .boundary{display:none!important}
	.lesson.theater .stagebox{position:fixed;inset:0;z-index:80;margin:0;border-radius:0;border:0;padding:0;background:#101b28}
	.lesson.theater.controls-visible .stagebox{inset:0 0 112px 0}
	.lesson.theater .stage{width:100vw;height:calc(100vh - 112px);min-height:0;aspect-ratio:auto;border-radius:0}
	.lesson.theater .keycards{position:fixed;right:14px;top:14px;width:min(300px,42vw);z-index:85}
	.theater-toggle{width:54px;height:38px;border-radius:999px;border:1px solid #3a4a60;background:#1a2533;color:#cfe0f0;font-size:13px;font-weight:800;cursor:pointer;flex:0 0 54px}
	.lesson.theater .player.controls{position:fixed;left:0;right:0;bottom:0;z-index:90;transform:translateY(120%);opacity:0;pointer-events:none}
	.lesson.theater.controls-visible .player.controls{transform:none;opacity:1;pointer-events:auto}
@media (orientation:landscape),(min-width:760px){
  .lesson.orientation-adaptive{max-width:1040px}
  .stagebox{display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,28%);align-items:stretch;gap:12px}
  .stage{min-height:min(58vh,430px);aspect-ratio:16/10}
  .caption{min-height:48px}
  .keycards{margin-top:0;align-self:stretch;justify-content:center}
}
@media (orientation:landscape) and (max-height:520px){
  .wrap{max-width:none;padding-top:8px}
  .steps{display:none}
  .topline{margin-bottom:4px}
  .kicker,.quick-options{display:none}
  h1{font-size:18px}
  .stagebox{display:block}
  .stage{height:calc(100vh - 72px);min-height:300px;aspect-ratio:auto}
  .keycards{position:absolute;right:12px;top:12px;width:min(300px,34vw);z-index:5}
  .caption{bottom:92px;width:min(460px,calc(100vw - 28px))}
}
@media (max-width:430px){
  .wrap{padding-top:10px}
  .topline{align-items:flex-start}
  h1{font-size:19px}
  .timepill{font-size:12px;padding:7px 10px}
  .stage{min-height:300px}
  .quick-options button{font-size:11.5px}
}
"""


def _load_master(path: Path) -> tuple[dict, dict, dict | None]:
    master = json.loads(path.read_text(encoding="utf-8"))
    lesson_ref = master.get("teaching_lesson_ref")
    lesson_path = path.parent / lesson_ref if lesson_ref else None
    lesson = json.loads(lesson_path.read_text(encoding="utf-8")) if lesson_path and lesson_path.exists() else {}
    timing_path = lesson_path.with_suffix(".timing.json") if lesson_path else None
    timing = json.loads(timing_path.read_text(encoding="utf-8")) if timing_path and timing_path.exists() else None
    return master, lesson, timing


def _teach_keycards(lesson: dict, timing: dict | None) -> str:
    if not timing:
        return ""
    cards = []
    teach_beats = [b for b in lesson.get("teach", {}).get("beats", []) if isinstance(b, dict)]
    teach_i = 0
    for s in timing["segments"]:
        if s["kind"] == "teach" and s.get("keycard"):
            kc = s["keycard"]
            beat = teach_beats[teach_i] if teach_i < len(teach_beats) else {}
            beat_id = str(beat.get("id") or f"beat_{teach_i}")
            action_id = f"{beat_id}.keycard"
            cards.append(
                f'<div class="kc kc-{esc(kc.get("tone","a"))}" data-start="{s["startSec"]}" '
                f'data-beat-id="{esc(beat_id)}" data-action-id="{esc(action_id)}" '
                f'data-visual-node-id="keycard.{esc(beat_id)}">{esc(kc["text"])}</div>'
            )
            teach_i += 1
    return "\n".join(cards)


def _load_card(master_path: Path, lesson: dict) -> dict:
    card_ref = lesson.get("derived_from")
    if not card_ref:
        return {}
    card_path = master_path.parent / str(card_ref)
    if not card_path.exists():
        return {}
    return json.loads(card_path.read_text(encoding="utf-8"))


def _safe_terms_from_card(card: dict) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for sp in card.get("scoring_points", []):
        for raw in sp.get("keywords", []):
            term = str(raw).strip()
            if not term or term in seen:
                continue
            seen.add(term)
            terms.append(term)
    return terms


def _quick_terms(score_terms: list[str]) -> list[str]:
    labels: list[str] = []

    def add(label: str) -> None:
        if label and label not in labels:
            labels.append(label)

    for term in score_terms:
        if "危大" in term:
            add("危大")
        elif "规模" in term:
            add("超规模")
        elif "专项" in term:
            add("专项方案")
        elif "专家" in term:
            add("专家论证")
    for term in score_terms:
        add(term.replace("工程", "").replace("一定规模", "规模").replace("专项施工方案", "专项方案"))
        if len(labels) >= 4:
            break
    return labels[:4]


def _score_strip_html(score_terms: list[str]) -> str:
    if not score_terms:
        return ""
    chips = "".join(f'<span data-visual-node-id="score.atom.{i}">{esc(term)}</span>' for i, term in enumerate(score_terms[:8], 1))
    return f'<div class="score-strip" data-visual-node-id="score.keywords">{chips}</div>'


def _action_manifest(lesson: dict) -> dict:
    beats = []
    for beat in lesson.get("teach", {}).get("beats", []):
        if not isinstance(beat, dict):
            continue
        actions = []
        for idx, action in enumerate(beat.get("animation_action", []) or []):
            if not isinstance(action, dict):
                continue
            target = str(action.get("target", ""))
            actions.append({
                "id": f"{beat.get('id', 'beat')}.{action.get('type', 'action')}.{idx}",
                "type": action.get("type"),
                "target": target,
                "target_id": target.removeprefix("data-id:"),
            })
        beats.append({"id": beat.get("id"), "stage": beat.get("stage"), "actions": actions})
    # Student/debug manifest exposes only presentation action wiring.
    # Internal schema ids/source refs/scoring point ids stay in source JSON.
    return {"card_id": lesson.get("card_id"), "beats": beats}


def _qa_rows(lesson: dict) -> str:
    sp = lesson.get("speakers", {})
    rows = []
    for i, pair in enumerate(lesson.get("qa", [])):
        q, a = pair["q"], pair["a"]
        qn = sp.get(q["speaker"], {}).get("name", "学生")
        an = sp.get(a["speaker"], {}).get("name", "老师")
        qs, as_ = q["speaker"].lower(), a["speaker"].lower()
        rows.append(
            f'<div class="row {qs}" data-qi="{i}" data-role="q"><div class="av {qs}">{esc(qn[0])}</div>'
            f'<div class="bubble">{esc(q["text"])}</div></div>'
            f'<div class="row {as_}" data-qi="{i}" data-role="a"><div class="av {as_}">{esc(an[0])}</div>'
            f'<div class="bubble">{esc(a["text"])}</div></div>'
        )
    return "\n".join(rows)


def _quiz_blocks(variants: list[dict]) -> str:
    n = len(variants)
    out = []
    for qi, v in enumerate(variants):
        opts = "".join(
            f'<button class="qopt" data-qi="{qi}" data-oid="{esc(o["id"])}">'
            f'<b>{esc(o["id"])}.</b> {esc(o["text"])}</button>'
            for o in v["options"]
        )
        out.append(
            f'<div class="qblock seg" data-qi="{qi}" data-practice-id="{esc(v["id"])}">'
            f'<p class="qlabel">闯关 · 第 <b>{qi+1}</b>/{n} 题 · 用两道判据给新工程分档</p>'
            f'<p class="qstem">{esc(v["stem"])}</p>'
            f'<div class="qopts">{opts}</div>'
            f'<div class="qfb" data-qi="{qi}"></div>'
            f"</div>"
        )
    return "\n".join(out)


def render(master_path: Path) -> str:
    master, lesson, timing = _load_master(master_path)
    sp = lesson.get("speakers", {"T": {"name": "鲁班老师"}, "S": {"name": "小问"}})
    variants = master.get("variants", [])
    md = master.get("mastery_discrimination", {})
    warm = md.get("warm_feedback", {})
    boundary = master.get("authority", {}).get("student_boundary", "")
    exam_point = master.get("exam_point", "")
    teacher = sp.get("T", {}).get("name", "老师")
    card = _load_card(master_path, lesson)
    score_terms = _safe_terms_from_card(card)
    quick_terms = _quick_terms(score_terms)
    quick_html = "".join(
        f'<button class="{"active" if i == 0 else ""}" type="button">{esc(label)}</button>'
        for i, label in enumerate(quick_terms)
    )
    if not quick_html:
        quick_html = '<button class="active" type="button">先判断</button>'
    score_strip = _score_strip_html(score_terms)

    # 舞台外置:从 lesson.stage 取 SVG/states/css/banner(无则回退基坑)——引擎对原型通用
    stage_svg, state_order, state_label, stage_css, banner = ta.stage_spec(lesson)

    def vidx(prefix: str) -> int:
        for i, v in enumerate(variants):
            if str(v.get("id", "")).startswith(prefix):
                return i
        return -1

    # 关键鉴别题外置到 master(不再写死 V2/V4):mastery_discrimination.key_discriminator_ids
    key_ids = md.get("key_discriminator_ids") or []
    key_idx = [i for i, v in enumerate(variants) if v.get("id") in key_ids]
    if not key_idx:  # 回退:旧 J01 按 V2/V4 前缀
        key_idx = [i for i in (vidx("V2"), vidx("V4")) if i >= 0]

    seg_payload = [
        {"idx": s["idx"], "kind": s["kind"], "state": s["state"], "qaIndex": s.get("qaIndex"),
         "text": s["text"], "startSec": s["startSec"]}
        for s in (timing["segments"] if timing else [])
    ]
    # 分镜点按 state 去重(每个状态一个点,取该状态第一个 beat 的起点)——
    # 否则一个 state 配多个 beat 时点会重复(F16 验证抓到:intro/conclude 各 2 beat → 重复)
    teach_dots = []
    _seen_states: set[str] = set()
    for s in (timing["segments"] if timing else []):
        if s["kind"] == "teach" and s["state"] not in _seen_states:
            _seen_states.add(s["state"])
            teach_dots.append({"state": s["state"], "label": state_label.get(s["state"], s["state"]), "startSec": s["startSec"]})
    payload = {
        "totalSec": timing["totalSec"] if timing else 0,
        "teachEndSec": timing.get("teachEndSec", 0) if timing else 0,
        "segments": seg_payload,
        "variants": [
            {"id": v["id"], "answer": v["answer"], "feedback": v.get("feedback", ""),
             "basis": v.get("basis", ""), "tier": v.get("tier_tag", "")}
            for v in variants
        ],
        "keyIdx": key_idx,
        "warm": {"all_correct": warm.get("all_correct", ""), "partial": warm.get("partial", ""), "rote_leaning": warm.get("rote_leaning", "")},
    }
    manifest = _action_manifest(lesson)
    dots_html = "".join(
        f'<button class="dot beat-dot" data-state="{esc(d["state"])}" data-t="{d["startSec"]}">{esc(d["label"])}</button>'
        for d in teach_dots
    )
    audio_src = timing["audio"] if timing else ""
    no_audio = "" if timing else '<p class="ptime" style="justify-content:center">(音频未生成 · 先看动画/讲稿)</p>'
    practice_href = master_path.name.replace(".master.json", ".practice.html")

    return f"""<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(exam_point)} · 深母题闭环</title><style>{ta._CSS}{_EXTRA_CSS}{stage_css}</style></head>
<body>
<main class="wrap lesson orientation-adaptive" data-card-id="{esc(master.get('master_id', lesson.get('card_id', '')))}" data-stage-shell="archetype-journey">
  <div class="steps">
    <div class="step on" data-step="teach">① 讲懂</div>
    <div class="step" data-step="quiz">② 闯关</div>
    <div class="step" data-step="verdict">③ 看穿</div>
  </div>
  <div class="topline">
    <div class="titlegroup">
      <p class="kicker">深母题 · 讲懂→闯关→看穿</p>
      <h1>{esc(exam_point)}</h1>
    </div>
    <div class="timepill"><span id="topcur">0:00</span> / <span id="toptot">0:00</span></div>
  </div>
	  <div class="quick-options" aria-label="本卡判断抓手">
	    {quick_html}
	  </div>

  <!-- ① 讲懂(始终展开) -->
  <p class="subtitle">{esc(lesson.get('subtitle',''))}</p>
  <div class="stagebox">
    <div class="stage" id="stage" data-stage-shell="visual-stage">
      {stage_svg}
	      {score_strip}
      <div class="banner" data-visual-node-id="invariant.two_gates stage.conclude"><span data-visual-node-id="conclusion.need_argumentation">{esc(banner)}</span></div>
      <button class="center-play" id="centerPlay" type="button">播放讲解</button>
    </div>
    <div class="keycards" id="keycards">{_teach_keycards(lesson, timing)}</div>
  </div>
	  <div class="caption" id="caption"><span class="who">{esc(teacher)}</span><span id="captxt">点下面 ▶,老师开讲。</span></div>
	  <div class="qa" id="qa"><div class="qlbl">讲完了 · 同学还有疑问 👇</div>{_qa_rows(lesson)}</div>
	  <button class="skip" id="skipQuiz">听够了?直接进闯关 →</button>
	  <a class="skip practice-link" href="{esc(practice_href)}">开始闯关 · 独立页 →</a>

  <!-- 过渡:老师领入闯关 -->
  <div class="seg bridge" id="bridge">
    <div class="row t"><div class="av t">{esc(teacher[0])}</div>
      <div class="bubble">听明白了?来,我出 {len(variants)} 道题考考你,看你是真会分档,还是背了'要论证'三个字 👇</div></div>
  </div>

  <!-- ② 闯关(逐题自动浮现) -->
  {_quiz_blocks(variants)}

  <!-- ③ 看穿(4 题完自动浮现) -->
  <div class="seg" id="verdictSec">
    <p class="section-tag">③ 看穿</p>
    <div id="verdict"></div>
    <div class="recap" id="recap"></div>
	    <p class="mnote">这是自测看穿,不是正式判定;客观掌握结论以学情系统为准。</p>
    <button class="cta" id="retry">再闯一次</button>
    <button class="cta ghost" id="backTeach">回看讲解</button>
  </div>

	  <div class="boundary"><b>说明:</b>{esc(boundary)}</div>

<div class="player controls" id="player">
  <div class="inner">
{no_audio}
    <div class="prow">
	      <button class="play" id="play" aria-label="播放">▶</button>
	      <button class="replay" id="replay" aria-label="重播">↺</button>
	      <button class="theater-toggle" id="theaterToggle" data-theater-toggle="1" type="button" aria-label="全屏">全屏</button>
	      <div class="pcol">
        <div class="ptime"><span id="cur">0:00</span><span id="tot">0:00</span></div>
        <div class="bar" id="bar"><div class="fill" id="fill"></div><div class="divider" id="divider"></div></div>
        <input class="scrubber" id="scrubber" type="range" min="0" max="{timing["totalSec"] if timing else 0}" value="0" step="0.05" aria-label="拖动播放进度">
      </div>
    </div>
    <div class="dots" id="dots">{dots_html}</div>
  </div>
</div>
<audio id="au" preload="metadata"{' src="' + esc(audio_src) + '"' if audio_src else ''}></audio>
</main>
<script>
const DATA={js_json(payload)};
window.__LUBAN_LESSON_MANIFEST__={js_json(manifest)};
	const ORDER={js_json(state_order)};
	const $=id=>document.getElementById(id);
	const txt=(value)=>document.createTextNode(value==null?'':String(value));
	function node(tag, cls, text){{
	  const el=document.createElement(tag);
	  if(cls)el.className=cls;
	  if(text!=null)el.textContent=String(text);
	  return el;
	}}
	function reset(el,...children){{el.replaceChildren(...children);return el;}}

/* ---- 进度条(不切屏,只更新高亮)---- */
function setStep(name){{
  const order=['teach','quiz','verdict'],ci=order.indexOf(name);
  document.querySelectorAll('.step').forEach((s,i)=>{{
    s.classList.toggle('on',s.dataset.step===name);
    s.classList.toggle('done',i<ci);
  }});
}}
/* ---- 连续流:平滑展开 + 滑到视野 ---- */
function openSeg(el){{el.classList.add('open');}}
function flowTo(el){{requestAnimationFrame(()=>setTimeout(()=>el.scrollIntoView({{behavior:'smooth',block:'start'}}),90));}}

/* ---- ① 讲懂:动画 + 旁白时间轴 + 关键词卡 PPT ---- */
	const au=$('au'),play=$('play'),replay=$('replay'),theaterToggle=$('theaterToggle'),fill=$('fill'),bar=$('bar'),divider=$('divider'),scrubber=$('scrubber');
const cur=$('cur'),tot=$('tot'),topcur=$('topcur'),toptot=$('toptot'),stage=$('stage'),caption=$('caption'),captxt=$('captxt'),qa=$('qa'),player=$('player'),centerPlay=$('centerPlay');
const lesson=document.querySelector('.lesson');
const dots=[...document.querySelectorAll('.dot')],kcs=[...document.querySelectorAll('.kc')];
const fmt=s=>{{s=Math.max(0,s|0);return (s/60|0)+':'+String(s%60).padStart(2,'0');}};
tot.textContent=fmt(DATA.totalSec);toptot.textContent=fmt(DATA.totalSec);
if(DATA.totalSec)divider.style.left=(DATA.teachEndSec/DATA.totalSec*100)+'%';
let curState=null;
function setStage(st){{if(st===curState)return;curState=st;const i=ORDER.indexOf(st);
  stage.className='stage '+ORDER.slice(0,i+1).map(s=>'reached-'+s).join(' ');
  dots.forEach(d=>d.classList.toggle('on',d.dataset.state===st));}}
let qaShown=false;
function revealQA(){{if(!qaShown){{qaShown=true;qa.classList.add('show');}}}}
function setQAActive(qi,role){{document.querySelectorAll('.qa .bubble').forEach(b=>b.classList.remove('on'));
  if(qi==null)return;const r=document.querySelector('.row[data-qi="'+qi+'"][data-role="'+role+'"]');
  if(r)r.querySelector('.bubble').classList.add('on');}}
function segAt(t){{let r=null;for(const s of DATA.segments){{if(t>=s.startSec-0.05)r=s;else break;}}return r;}}
function paint(){{const t=au.currentTime;
  fill.style.width=(t/(DATA.totalSec||au.duration||1)*100)+'%';cur.textContent=fmt(t);topcur.textContent=fmt(t);scrubber.value=String(t);
  kcs.forEach(k=>k.classList.toggle('in',t>=parseFloat(k.dataset.start)-0.05));
  const s=segAt(t);if(!s)return;setStage(s.state);
  if(s.kind==='teach'){{caption.classList.remove('hide');captxt.textContent=s.text;setQAActive(null);}}
  else{{caption.classList.add('hide');revealQA();setQAActive(s.qaIndex,s.kind);}}
  if(t>=DATA.teachEndSec-0.2)revealQA();}}
window.paint=paint;
au.addEventListener('timeupdate',paint);
au.addEventListener('ended',()=>{{play.textContent='▶';startQuiz();}});
function playAudio(){{lesson.classList.add('started');return au.play().then(()=>play.textContent='⏸').catch(()=>{{captxt.textContent='点一下屏幕再点 ▶';}});}}
function togglePlay(){{if(au.paused){{playAudio();}}else{{au.pause();play.textContent='▶';}}}}
play.addEventListener('click',togglePlay);
centerPlay.addEventListener('click',()=>{{playAudio();}});
replay.addEventListener('click',()=>{{lesson.classList.add('started');au.currentTime=0;qaShown=false;qa.classList.remove('show');kcs.forEach(k=>k.classList.remove('in'));playAudio();}});
bar.addEventListener('click',e=>{{const r=bar.getBoundingClientRect();au.currentTime=(e.clientX-r.left)/r.width*(DATA.totalSec||au.duration||0);}});
	scrubber.addEventListener('input',()=>{{au.currentTime=parseFloat(scrubber.value)||0;}});
	dots.forEach(d=>d.addEventListener('click',()=>{{au.currentTime=parseFloat(d.dataset.t)||0;playAudio();}}));
	function updateTheaterButton(){{theaterToggle.textContent=lesson.classList.contains('theater')?'退出':'全屏';theaterToggle.setAttribute('aria-label',theaterToggle.textContent);}}
	function enterTheater(){{lesson.classList.add('theater','controls-visible','started');updateTheaterButton();}}
	function exitTheater(){{lesson.classList.remove('theater','controls-visible');updateTheaterButton();}}
	theaterToggle.addEventListener('click',()=>{{lesson.classList.contains('theater')?exitTheater():enterTheater();}});
	stage.addEventListener('click',(event)=>{{if(event.target===centerPlay)return;if(lesson.classList.contains('theater'))lesson.classList.toggle('controls-visible');}});
	document.addEventListener('keydown',(event)=>{{if(event.key==='Escape'&&lesson.classList.contains('theater'))exitTheater();}});
	updateTheaterButton();
	setStage('intro');

/* ---- ② 闯关:讲完自动浮现,答完自动滑入下一题 ---- */
const V=DATA.variants;const answers=new Array(V.length).fill(null);
const qblocks=[...document.querySelectorAll('.qblock')];
let quizStarted=false;
function startQuiz(){{if(quizStarted)return;quizStarted=true;
  au.pause();play.textContent='▶';player.classList.add('hide');setStep('quiz');
  openSeg($('bridge'));openSeg(qblocks[0]);flowTo($('bridge'));}}
$('skipQuiz').addEventListener('click',startQuiz);

document.querySelectorAll('.qopt').forEach(btn=>btn.addEventListener('click',()=>{{
  const i=+btn.dataset.qi;if(answers[i]!=null)return;const oid=btn.dataset.oid;answers[i]=oid;
  const correct=oid===V[i].answer,last=i===V.length-1;
  document.querySelectorAll('.qopt[data-qi="'+i+'"]').forEach(b=>{{b.disabled=true;
    if(b.dataset.oid===V[i].answer)b.classList.add('correct');
    else if(b.dataset.oid===oid)b.classList.add('wrong');}});
	  const fb=document.querySelector('.qfb[data-qi="'+i+'"]');
	  fb.className='qfb show '+(correct?'ok':'no');
	  reset(
	    fb,
	    txt((correct?'✅ ':'❌ ')+V[i].feedback),
	    document.createElement('br'),
	    node('span','tier','判据:'+V[i].basis+' · '+V[i].tier),
	    node('span','nexthint',last?'↓ 看你是真懂还是背过':'↓ 下一题来了')
	  );
  setTimeout(()=>{{
    if(last){{showVerdict();openSeg($('verdictSec'));setStep('verdict');flowTo($('verdictSec'));}}
    else{{openSeg(qblocks[i+1]);flowTo(qblocks[i+1]);}}
  }},correct?1700:2600);
}}));

/* ---- ③ 看穿:读 master signal,不另造标准 ---- */
function showVerdict(){{
  const correct=V.map((v,i)=>answers[i]===v.answer);
  const all=correct.every(Boolean);
  const keyIdx=DATA.keyIdx||[];
  const keyAllWrong=keyIdx.length>0&&keyIdx.every(i=>!correct[i]);
  let bucket,cls,title;
  if(all){{bucket='all_correct';cls='good';title='看穿了:你是真懂 ✅';}}
	  else if(keyAllWrong){{bucket='rote_leaning';cls='low';title='先别急着背 🔵';}}
	  else{{bucket='partial';cls='mid';title='就差一步 🟡';}}
	  const n=correct.filter(Boolean).length;
	  const vcard=node('div','vcard '+cls);
	  reset(
	    vcard,
	    node('div','vtitle',title),
	    node('div','vtext',DATA.warm[bucket]),
	    node('div','vscore','这轮 '+n+'/'+V.length+' 题判对'+(keyIdx.length?' · 关键鉴别题是看穿点':''))
	  );
	  reset($('verdict'),vcard);
	  const recap=$('recap');
	  reset(recap,node('div','rl','闯关回看'));
	  V.forEach((v,i)=>{{
	    const ok=correct[i];
	    const row=node('div','rrow '+(ok?'ok':'no'));
	    const body=node('span','');
	    body.append(txt(v.tier));
	    if(keyIdx.includes(i))body.append(node('span','key','关键鉴别题'));
	    body.append(document.createElement('br'),node('span','basis-text',v.basis));
	    reset(row,node('span','mk',ok?'✓':'✗'),body);
	    recap.append(row);
	  }});
	}}

/* ---- 重来 / 回看 ---- */
$('retry').addEventListener('click',()=>{{answers.fill(null);
  document.querySelectorAll('.qopt').forEach(b=>{{b.disabled=false;b.classList.remove('correct','wrong');}});
  document.querySelectorAll('.qfb').forEach(f=>f.className='qfb');
  qblocks.forEach((q,i)=>{{if(i>0)q.classList.remove('open');}});
  $('verdictSec').classList.remove('open');setStep('quiz');flowTo(qblocks[0]);}});
$('backTeach').addEventListener('click',()=>{{player.classList.remove('hide');setStep('teach');window.scrollTo({{top:0,behavior:'smooth'}});}});
</script>
</body></html>"""


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: render_archetype_journey.py <master.json>", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    out = src.with_name(src.name.replace(".master.json", "") + ".journey.html")
    out.write_text(render(src), encoding="utf-8")
    print(f"✅ {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
