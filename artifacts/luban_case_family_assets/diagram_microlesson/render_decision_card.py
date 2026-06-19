#!/usr/bin/env python3
"""图解微课 ④判断/分支原型确定性渲染器(luban_diagram_microlesson.v1)· 翻页 deck 版。

输入:template_type=decision_branch_reveal(_draft) 的考点 schema JSON。
输出:一屏一个重点的翻页 deck——why+题干 / 每个判断点各一屏 / 结论 / 采分 / 错因 / 复测 / 收束;
底部「上一页/下一页」常驻,不下拉。旁白播到哪屏自动翻到哪屏。

边界(与 type-decision.md / 红线一致):
- 只渲染【教研预编译】的例题判断示范,不 runtime 判断、不判分(判分走 LLM 开放世界·硬约束40)。
- student-safe fail-closed:verdict 字面/source_ref/scoring_point id/next_* 等内部词绝不上屏。
- 复用 ../render_contrast_card.py 脊柱(esc/旁白播放器/采分卡/复测/deck CSS)。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import render_contrast_card as base

SCHEMA_VERSION = "luban_diagram_microlesson.v1"
DECISION_TEMPLATES = {"decision_branch_reveal", "decision_branch_reveal_draft"}
CANDIDATE_STATUSES = base.CANDIDATE_STATUSES

esc = base.esc
trusted_json_for_script = base.trusted_json_for_script
narration_player = base.narration_player
score_cards = base.score_cards
practice_options = base.practice_options

_DECISION_CSS = r"""
.scenario-given{background:#fff;border:1px solid var(--line);border-left:4px solid var(--progress);border-radius:14px;padding:14px 16px;margin:12px 0 0}
.scenario-given .sg-tag{display:inline-block;font-size:12px;font-weight:800;color:var(--progress);background:var(--progress-bg);border-radius:999px;padding:3px 10px;margin-bottom:8px}
.scenario-given p{margin:0;font-size:15px;line-height:1.65;color:var(--ink)}
.jp{background:#fff;border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow);padding:16px 17px}
.jp.met{border-left:5px solid var(--correct)} .jp.unmet{border-left:5px solid #9aa6b6}
.jp-criterion{background:#f7fafc;border:1px solid var(--line);border-radius:11px;padding:11px 13px;font-size:14.5px;color:#33425a;margin-top:4px}
.jp-criterion b{color:var(--ink)}
.jp-verdict{margin-top:12px;display:flex;gap:9px;align-items:flex-start;font-size:15px;font-weight:600;line-height:1.6}
.jp-verdict .vmark{flex:0 0 auto;width:24px;height:24px;border-radius:50%;display:grid;place-items:center;color:#fff;font-size:14px;font-weight:900}
.jp.met .jp-verdict{color:#15402f} .jp.met .vmark{background:var(--correct)}
.jp.unmet .jp-verdict{color:#5b6573} .jp.unmet .vmark{background:#9aa6b6}
.jp-basis{margin-top:11px;font-size:13px;color:var(--sub)}
.jp-basis::before{content:"依据 · ";font-weight:700;color:#7a8699}
.jp-next{margin-top:12px;text-align:center;color:var(--correct);font-size:13px;font-weight:700}
.outcome-card{position:relative;border-radius:18px;padding:18px;box-shadow:var(--shadow)}
.outcome-card.target{background:var(--correct-bg);border:1px solid var(--correct-line);border-left:6px solid var(--correct)}
.outcome-label{font-size:19px;font-weight:800;color:#0f6b4f;display:flex;gap:10px;align-items:center}
.outcome-label .ok{width:28px;height:28px;border-radius:50%;background:var(--correct);color:#fff;display:grid;place-items:center;font-weight:900}
.outcome-score{margin-top:12px;border-radius:12px;background:#fff;border:1px solid var(--correct-line);border-left:4px solid var(--correct);padding:11px 13px}
.outcome-score small{display:block;color:var(--correct);font-weight:800;font-size:11.5px;margin-bottom:4px}
.outcome-score span{font-size:14.5px;color:#15402f;font-weight:600;line-height:1.6}
.outcome-veil{position:absolute;inset:0;border-radius:18px;background:rgba(232,247,240,.95);backdrop-filter:blur(2px);display:grid;place-items:center;cursor:pointer;border:1px dashed var(--correct-line);text-align:center;padding:14px}
.outcome-veil b{color:var(--correct);font-weight:800;font-size:16px}
.outcome-card.revealed .outcome-veil{display:none}
.alt-outcomes{margin-top:14px;background:#fff;border:1px solid var(--line);border-radius:14px;padding:13px 15px}
.alt-outcomes h4{margin:0 0 8px;font-size:13px;color:var(--sub);font-weight:800}
.alt-outcomes li{font-size:13.5px;color:#52617a;line-height:1.8;list-style:none;padding-left:16px;position:relative}
.alt-outcomes li::before{content:"·";position:absolute;left:4px;color:var(--partial);font-weight:900}
"""

# deck 翻页 + 屏内交互(结论 reveal / 错因翻页 / 复测)。
_DECISION_JS = r"""
const cardData = JSON.parse(document.getElementById("cardData").textContent);
const slides = [...document.querySelectorAll(".slide")];
const TOTAL = slides.length;
let screen = 0;
const $ = (id)=>document.getElementById(id);
const prevBtn=$("prevBtn"), nextBtn=$("nextBtn"), deckCount=$("deckCount"), stepCount=$("stepCount"), progressBar=$("progressBar");
function goScreen(n){
  screen=Math.max(0,Math.min(TOTAL-1,n));
  slides.forEach((s,i)=>s.classList.toggle("active",i===screen));
  const label=(screen+1)+" / "+TOTAL;
  if(deckCount) deckCount.textContent=label;
  if(stepCount) stepCount.textContent=label;
  if(progressBar) progressBar.style.width=(((screen+1)/TOTAL)*100)+"%";
  if(prevBtn) prevBtn.disabled=screen===0;
  if(nextBtn) nextBtn.textContent=screen===TOTAL-1?"重新开始":"下一页 →";
  window.scrollTo(0,0);
}
function slideIndexByAnchor(a){
  const el=document.querySelector('.slide[data-anchor="'+(a||"").replace(/"/g,'')+'"]');
  return el?slides.indexOf(el):-1;
}
if(prevBtn) prevBtn.addEventListener("click",()=>goScreen(screen-1));
if(nextBtn) nextBtn.addEventListener("click",()=>goScreen(screen===TOTAL-1?0:screen+1));
document.addEventListener("keydown",(e)=>{ if(e.key==="ArrowRight")goScreen(screen+1); if(e.key==="ArrowLeft")goScreen(screen-1); });
document.querySelectorAll(".outcome-veil").forEach((v)=>v.addEventListener("click",()=>v.closest(".outcome-card").classList.add("revealed")));
// 错因卡 → 翻到对应判断点屏
document.querySelectorAll(".error-card").forEach((btn)=>{
  btn.addEventListener("click",()=>{ const idx=slideIndexByAnchor("point:"+btn.dataset.jump); if(idx>=0) goScreen(idx); });
});
// 复测题: 答错翻回 review_point_id 判断屏
document.querySelectorAll(".option").forEach((btn)=>{
  btn.addEventListener("click",()=>{
    document.querySelectorAll(".option").forEach(o=>{o.setAttribute("aria-pressed","false");o.classList.remove("correct","wrong");});
    btn.setAttribute("aria-pressed","true");
    const correct=btn.dataset.correct==="true";
    btn.classList.add(correct?"correct":"wrong");
    const fb=$("practiceFeedback");
    fb.classList.remove("correct","wrong"); fb.classList.add("show",correct?"correct":"wrong");
    fb.textContent=(correct?"✅ ":"❌ ")+(btn.dataset.feedback||"");
  });
});
goScreen(0);
"""

# 旁白同步: 播到某段就翻到对应屏 + reveal 结论。
_NARR_JS = r"""
(function(){
  const tEl=document.getElementById("narrTiming"), audio=document.getElementById("narrAudio"), btn=document.getElementById("narrPlay");
  if(!tEl||!audio||!btn) return;
  const timing=JSON.parse(tEl.textContent), sub=document.getElementById("narrSub"), bar=document.getElementById("narrBar");
  const slides=[...document.querySelectorAll(".slide")];
  function go(a){
    const el=document.querySelector('.slide[data-anchor="'+(a||"").replace(/"/g,'')+'"]');
    if(!el) return;
    const oc=el.querySelector(".outcome-card"); if(oc) oc.classList.add("revealed");
    if(typeof goScreen==="function") goScreen(slides.indexOf(el));
  }
  let cur=null;
  audio.addEventListener("timeupdate",()=>{
    const t=audio.currentTime; let seg=timing.segments[0];
    for(const s of timing.segments){ if(t>=s.startSec) seg=s; }
    if(seg&&seg.id!==cur){ cur=seg.id; if(sub) sub.textContent=seg.text; go(seg.anchor); }
    if(bar) bar.style.width=(timing.totalSec?Math.min(100,(t/timing.totalSec)*100):0)+"%";
  });
  function setBtn(){ const p=!audio.paused; btn.classList.toggle("playing",p); btn.setAttribute("aria-pressed",p?"true":"false");
    btn.textContent=p?"⏸ 暂停讲解":(audio.currentTime>0?"▶ 继续讲解":("▶ 听老师讲("+Math.round(timing.totalSec)+" 秒)")); }
  btn.addEventListener("click",()=>{ if(audio.paused){ var pr=audio.play(); if(pr&&pr.catch) pr.catch(function(){ if(sub) sub.textContent="(音频没能播放——微信 web-view 常限制 HTML5 音频;真机请用 Safari 打开,或改走小程序原生音频)"; }); } else audio.pause(); });
  audio.addEventListener("play",setBtn); audio.addEventListener("pause",setBtn);
  audio.addEventListener("ended",()=>{ cur=null; setBtn(); if(sub) sub.textContent="讲完啦——自己翻页判一遍,做复测题。"; });
})();
"""


def validate(schema: dict[str, Any]) -> None:
    if schema.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {schema.get('schema_version')!r}")
    if schema.get("template_type") not in DECISION_TEMPLATES:
        raise ValueError(f"decision renderer requires template_type in {DECISION_TEMPLATES}")
    d = schema.get("decision") or {}
    points = d.get("judgment_points") or []
    if not points:
        raise ValueError("decision requires non-empty judgment_points")
    if schema.get("steps") or schema.get("contrast_items") or schema.get("diagnosis"):
        raise ValueError("decision card must not also carry steps/contrast_items/diagnosis body")
    pids = {p.get("id") for p in points}
    oids = {o.get("id") for o in (d.get("outcomes") or [])}
    for p in points:
        for nxt in (p.get("next_on_met"), p.get("next_on_unmet")):
            if nxt is None:
                continue
            if str(nxt).startswith("outcome:"):
                if str(nxt).split(":", 1)[1] not in oids:
                    raise ValueError(f"{p.get('id')} 走向指向未知 outcome: {nxt!r}")
            elif nxt not in pids:
                raise ValueError(f"{p.get('id')} 走向指向未知判断点: {nxt!r}")
        if p.get("verdict") not in ("met", "unmet", "na"):
            raise ValueError(f"{p.get('id')}.verdict 非法: {p.get('verdict')!r}")
    if d.get("reached_outcome") not in oids:
        raise ValueError(f"reached_outcome 不在 outcomes: {d.get('reached_outcome')!r}")
    pts_by_id = {p.get("id"): p for p in points}
    cur = points[0].get("id")
    seen: set[Any] = set()
    reached_actual = None
    for _ in range(len(points) + 1):
        if cur in seen or cur not in pts_by_id:
            break
        seen.add(cur)
        pp = pts_by_id[cur]
        nxt = pp.get("next_on_met") if pp.get("verdict") == "met" else pp.get("next_on_unmet")
        if str(nxt).startswith("outcome:"):
            reached_actual = str(nxt).split(":", 1)[1]
            break
        cur = nxt
    if reached_actual != d.get("reached_outcome"):
        raise ValueError(f"reached_outcome 声明 {d.get('reached_outcome')!r} 但沿 verdict 实走到 {reached_actual!r}")
    practice = schema.get("practice") or {}
    if practice.get("answer") is not None and practice["answer"] not in {o.get("id") for o in practice.get("options") or []}:
        raise ValueError(f"practice.answer {practice['answer']!r} 不在 options")
    if base.authority_status(schema) not in CANDIDATE_STATUSES:
        raise ValueError(f"decision draft must be candidate/draft authority, got {base.authority_status(schema)!r}")
    if base.official_score_claimed(schema):
        raise ValueError("candidate/draft must not set official_score_allowed=true")
    for sp in schema.get("scoring_points") or []:
        if not sp.get("kind"):
            raise ValueError(f"scoring_points[{sp.get('id')!r}] 缺 kind (candidate 不冒充签发)")
    for e in schema.get("common_errors") or []:
        if e.get("jump_point_id") is not None and e.get("jump_point_id") not in pids:
            raise ValueError(f"common_errors.jump_point_id 不在 judgment_points: {e.get('jump_point_id')!r}")
    if not (schema.get("rendering_contract") or {}).get("student_safe_fields"):
        raise ValueError("decision card requires rendering_contract.student_safe_fields (student-safe gate)")


def jp_slide_body(p: dict[str, Any], i: int, total: int) -> str:
    verdict = p.get("verdict")
    vmark = "✓" if verdict == "met" else ("✗" if verdict == "unmet" else "?")
    nxt_hint = ""
    if i < total - 1:
        nxt_hint = '<div class="jp-next">↓ 满足,继续判下一道 →</div>' if verdict == "met" else '<div class="jp-next">↓ 不满足 →</div>'
    return (
        f'<article class="jp {esc(verdict)}" data-point="{esc(p.get("id"))}">'
        f'<div class="jp-criterion"><b>判据:</b>{esc(p.get("criterion"))}</div>'
        f'<div class="jp-verdict"><span class="vmark">{vmark}</span><span>{esc(p.get("verdict_reason"))}</span></div>'
        f'<div class="jp-basis">{esc(p.get("basis"))}</div></article>'
        f'{nxt_hint}'
    )


def outcome_slide_body(d: dict[str, Any]) -> str:
    outcomes = {o.get("id"): o for o in (d.get("outcomes") or [])}
    reached_id = d.get("reached_outcome")
    reached = outcomes.get(reached_id, {})
    parts = [
        '<div class="outcome-card target">'
        '<div class="outcome-veil" role="button" tabindex="0"><b>先自己判一下 → 点开看结论 ›</b></div>'
        f'<div class="outcome-label"><span class="ok">✓</span>{esc(reached.get("label"))}</div>'
        '<div class="outcome-score"><small>答题这么写才得分</small>'
        f'<span>{esc(reached.get("label"))}</span></div></div>'
    ]
    alts = [o for oid, o in outcomes.items() if oid != reached_id]
    if alts:
        items = "".join(f'<li>{esc(o.get("label"))}</li>' for o in alts)
        parts.append(f'<div class="alt-outcomes"><h4>其它情况会落到这些档(对照记)</h4><ul style="margin:0;padding:0">{items}</ul></div>')
    return "".join(parts)


def error_cards(schema: dict[str, Any]) -> str:
    cards = []
    for e in schema.get("common_errors") or []:
        loss = esc(e.get("loss_display"))
        chip = f'<span class="loss">{loss}</span>' if loss else ""
        cards.append(
            '<button class="error-card" type="button" '
            f'data-jump="{esc(e.get("jump_point_id"))}">'
            f'<b>{esc(e.get("text"))}{chip}</b><span class="why">{esc(e.get("why"))}</span></button>'
        )
    return "".join(cards)


def client_payload(schema: dict[str, Any]) -> str:
    practice = schema.get("practice") or {}
    return trusted_json_for_script({"practice": {"review_point_id": practice.get("review_point_id")}})


def render(schema: dict[str, Any], timing: dict[str, Any] | None = None) -> str:
    validate(schema)
    title = esc(schema.get("title"))
    why_html = schema.get("why_lose_points_html") or esc(schema.get("student_goal"))
    warm = schema.get("warm_correction_html") or esc(schema.get("warm_correction"))
    memory_hook = esc(schema.get("memory_hook"))
    authority = schema.get("authority") or {}
    practice = schema.get("practice") or {}
    d = schema.get("decision") or {}
    points = d.get("judgment_points") or []
    student_boundary = esc(authority.get("student_boundary") or "这是教研讲解,不是官方阅卷;判据以现行规范、教材为准。")
    source_boundary_comment = str(authority.get("source_boundary") or "").replace("--", "—")
    judging_comment = str(authority.get("judging_authority_label") or "").replace("--", "—")
    data = client_payload(schema)
    css = base._CSS + _DECISION_CSS

    narr_player, narr_tags = "", ""
    if timing:
        audio_src = esc(timing.get("audio") or "")
        timing_json = trusted_json_for_script(timing)
        narr_player = narration_player(timing)
        narr_tags = (
            f'<audio id="narrAudio" src="{audio_src}" preload="auto"></audio>'
            f'<script type="application/json" id="narrTiming">{timing_json}</script>'
            f"<script>{_NARR_JS}</script>"
        )

    slides: list[str] = []
    # 屏 1:为什么丢分 + 题干情形
    slides.append(
        '<section class="slide active" data-anchor="why">'
        '<div class="slide-kicker">看穿丢分点</div>'
        '<h2 class="slide-title">为什么这个点容易丢分</h2>'
        f'<div class="whycard"><p>{why_html}</p></div>'
        '<div class="scenario-given"><span class="sg-tag">这道题的情形</span>'
        f'<p>{esc(d.get("scenario_given"))}</p></div></section>'
    )
    # 屏 2..n:每个判断点一屏
    for i, p in enumerate(points):
        slides.append(
            f'<section class="slide" data-anchor="point:{esc(p.get("id"))}">'
            f'<div class="slide-kicker">判断 {i + 1} / {len(points)}</div>'
            f'<h2 class="slide-title">{esc(p.get("question"))}</h2>'
            f'{jp_slide_body(p, i, len(points))}</section>'
        )
    # 屏:结论 + 分档
    slides.append(
        '<section class="slide" data-anchor="outcome">'
        '<div class="slide-kicker">得出结论</div>'
        '<h2 class="slide-title">所以这道题怎么判</h2>'
        f'{outcome_slide_body(d)}</section>'
    )
    # 屏:采分
    slides.append(
        '<section class="slide" data-anchor="scoring">'
        '<div class="slide-kicker">候选采分点</div>'
        '<h2 class="slide-title">写到这些判据才稳</h2>'
        '<p class="hint">教研整理的关键判据与得分表达,非官方阅卷。</p>'
        f'<div class="bar"><div class="score-grid">{score_cards(schema)}</div></div></section>'
    )
    # 屏:错因
    if schema.get("common_errors"):
        slides.append(
            '<section class="slide">'
            '<div class="slide-kicker">错因自查</div>'
            '<h2 class="slide-title">常见失分写法 · 点一个翻去看</h2>'
            '<p class="hint">点你常犯的错,我翻到漏掉的那一步判断。</p>'
            f'<div class="error-grid">{error_cards(schema)}</div></section>'
        )
    # 屏:复测
    if practice:
        slides.append(
            '<section class="slide">'
            '<div class="slide-kicker">复测一题</div>'
            f'<h2 class="slide-title">{esc(practice.get("title") or "复测题")}</h2>'
            f'<p class="stem">{esc(practice.get("stem"))}</p>'
            f'<div class="option-grid">{practice_options(schema)}</div>'
            '<div class="feedback" id="practiceFeedback" role="status"></div>'
            f'<p class="next-action">{esc(practice.get("next_action"))}</p></section>'
        )
    # 屏:收束
    slides.append(
        '<section class="slide" data-anchor="wrap">'
        '<div class="slide-kicker">记住判据</div>'
        '<h2 class="slide-title">收束</h2>'
        f'<div class="wrap-card"><b>暖纠正</b><p>{warm}</p>'
        f'<div class="memhook">记忆钩子 · <strong>{memory_hook}</strong></div></div>'
        f'<div class="auth"><b>考试依据</b>:{student_boundary}'
        '<div class="nonofficial">非官方阅卷 · 判断流为教学示意 · 判据为教研候选 · 具体以现行规范 / 教材为准</div></div></section>'
    )

    slides_html = "".join(slides)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · 图解微课</title>
<style>{css}</style>
</head>
<body>
<!--
created_by: deterministic render_decision_card.py (luban diagram micro-lesson · decision · deck)
schema_version: {SCHEMA_VERSION}
template_type: {esc(schema.get("template_type"))}
judging_authority: {judging_comment}
source_boundary: {source_boundary_comment}
notes: 翻页 deck 一屏一判断点;只渲染教研预编译示范,不判分;判据 candidate,非官方阅卷。
-->
<main class="deck">
  <div class="deck-top"><span class="brandmini">鲁班图解微课 · {title}</span><span class="deck-count" id="deckCount">1 / 1</span></div>
  {narr_player}
  {slides_html}
  <div class="stepnav">
    <button class="nav-btn" id="prevBtn" type="button">← 上一页</button>
    <div class="nav-mid"><span id="stepCount">1 / 1</span><i class="nav-prog"><b id="progressBar"></b></i></div>
    <button class="nav-btn primary" id="nextBtn" type="button">下一页 →</button>
  </div>
</main>
<script type="application/json" id="cardData">{data}</script>
<script>{_DECISION_JS}</script>
{narr_tags}
</body>
</html>"""


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    schema_path = Path(argv[1])
    out_path = Path(argv[2]) if len(argv) > 2 else schema_path.with_suffix(".rendered.html")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    timing_path = schema_path.with_name(f"{schema_path.stem}.narration.timing.json")
    timing = json.loads(timing_path.read_text(encoding="utf-8")) if timing_path.exists() else None
    out_path.write_text(render(schema, timing), encoding="utf-8")
    d = schema.get("decision") or {}
    print(f"rendered (deck): {schema_path} -> {out_path}")
    print(
        f"  mode={d.get('mode')} judgment_points={len(d.get('judgment_points') or [])} "
        f"outcomes={len(d.get('outcomes') or [])} narration={'yes' if timing else 'no'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
