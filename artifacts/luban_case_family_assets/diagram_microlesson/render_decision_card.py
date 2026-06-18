#!/usr/bin/env python3
"""图解微课 ④判断/分支原型确定性渲染器(luban_diagram_microlesson.v1)。

输入:template_type=decision_branch_reveal(_draft) 的考点 schema JSON。
输出:小程序 WebView 可承载的静态 HTML 卡:逐条点亮判断流 + 结论 + 依据/采分 + 预存旁白同步。

边界(与 type-decision.md / 红线一致):
- 只渲染【教研预编译】的例题判断示范,不 runtime 判断、不判分(判分走 LLM 开放世界·硬约束40)。
- 判断流确定性渲染;判据/阈值由 schema 带教材溯源(candidate,不冒充签发)。
- student-safe fail-closed:只渲染 rendering_contract.student_safe_fields;verdict 字面/source_ref/
  scoring_point id/next_* 等内部词绝不上屏。
- 复用 ../render_contrast_card.py 脊柱(esc/旁白播放器/采分卡/复测/CSS),只新写 decision body。
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

_MODE_HINT = {
    "criteria_chain": "沿判据一条条走,看走到哪个结论",
    "classify": "看落在哪一档",
    "all_conditions": "几个要件全部满足才成立",
    "select_one": "按条件选中其中一个",
    "role_path": "按环节看谁负责、走到哪一步",
}

_DECISION_CSS = r"""
.scenario-given{background:#fff;border:1px solid var(--line);border-left:4px solid var(--progress);border-radius:14px;padding:14px 16px;margin:0 0 14px}
.scenario-given .sg-tag{display:inline-block;font-size:12px;font-weight:800;color:var(--progress);background:var(--progress-bg);border-radius:999px;padding:3px 10px;margin-bottom:8px}
.scenario-given p{margin:0;font-size:15px;line-height:1.6;color:var(--ink)}
.mode-hint{margin:0 0 14px;color:var(--sub);font-size:13px;text-align:center}
.judge-flow{display:grid;gap:0}
.jp{background:rgba(255,255,255,.92);border:1px solid rgba(203,213,225,.9);border-radius:16px;box-shadow:var(--shadow);padding:14px 16px}
.jp.met{border-left:5px solid var(--correct)}
.jp.unmet{border-left:5px solid #9aa6b6;opacity:.78}
.jp-head{display:flex;gap:12px;align-items:center;margin-bottom:9px}
.jp-no{flex:0 0 auto;width:30px;height:30px;border-radius:9px;background:var(--progress);color:#fff;font-weight:800;display:grid;place-items:center;font-size:14px}
.jp-head h3{margin:0;font-size:16px}
.jp-criterion{background:#f7fafc;border:1px solid var(--line);border-radius:10px;padding:9px 11px;font-size:13.5px;color:#33425a}
.jp-criterion b{color:var(--ink)}
.jp-verdict{margin-top:9px;display:flex;gap:8px;align-items:flex-start;font-size:14px;font-weight:600;line-height:1.55}
.jp-verdict .vmark{flex:0 0 auto;width:22px;height:22px;border-radius:50%;display:grid;place-items:center;color:#fff;font-size:13px;font-weight:900}
.jp.met .jp-verdict{color:#15402f} .jp.met .vmark{background:var(--correct)}
.jp.unmet .jp-verdict{color:#5b6573} .jp.unmet .vmark{background:#9aa6b6}
.jp-basis{margin-top:9px;font-size:12.5px;color:var(--sub)}
.jp-basis::before{content:"依据 · ";font-weight:700;color:#7a8699}
.flow-arrow{display:flex;align-items:center;justify-content:center;gap:8px;color:var(--correct);font-size:13px;font-weight:700;padding:8px 0}
.flow-arrow .ln{font-size:18px}
.outcome-card{position:relative;margin-top:6px;border-radius:18px;padding:16px 18px;box-shadow:var(--shadow)}
.outcome-card.target{background:var(--correct-bg);border:1px solid var(--correct-line);border-left:6px solid var(--correct)}
.outcome-label{font-size:18px;font-weight:800;color:#0f6b4f;display:flex;gap:9px;align-items:center}
.outcome-label .ok{width:26px;height:26px;border-radius:50%;background:var(--correct);color:#fff;display:grid;place-items:center;font-weight:900}
.outcome-score{margin-top:10px;border-radius:11px;background:#fff;border:1px solid var(--correct-line);border-left:4px solid var(--correct);padding:10px 12px}
.outcome-score small{display:block;color:var(--correct);font-weight:800;font-size:11.5px;margin-bottom:4px}
.outcome-score span{font-size:14px;color:#15402f;font-weight:600;line-height:1.6}
.outcome-veil{position:absolute;inset:0;border-radius:18px;background:rgba(232,247,240,.94);backdrop-filter:blur(2px);display:grid;place-items:center;cursor:pointer;border:1px dashed var(--correct-line);text-align:center;padding:12px}
.outcome-veil b{color:var(--correct);font-weight:800;font-size:15px}
.outcome-card.revealed .outcome-veil{display:none}
.alt-outcomes{margin-top:12px;background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px 14px}
.alt-outcomes h4{margin:0 0 8px;font-size:13px;color:var(--sub);font-weight:800}
.alt-outcomes li{font-size:13px;color:#52617a;line-height:1.7;list-style:none;padding-left:16px;position:relative}
.alt-outcomes li::before{content:"·";position:absolute;left:4px;color:var(--partial);font-weight:900}
.jp.narr-focus,.outcome-card.narr-focus{outline:4px solid var(--progress);outline-offset:4px}
@media (max-width:560px){
  .outcome-label{font-size:16px}
}
"""

_DECISION_JS = r"""
const cardData = JSON.parse(document.getElementById("cardData").textContent);
// 结论卡: 先自己判 → 点开看结论(reveal)
document.querySelectorAll(".outcome-veil").forEach((v)=>{
  v.addEventListener("click",()=>v.closest(".outcome-card").classList.add("revealed"));
});
// 错因卡 → 滚到对应判断点并闪
document.querySelectorAll(".error-card").forEach((btn)=>{
  btn.addEventListener("click",()=>{
    const el=document.querySelector('[data-point="'+btn.dataset.jump+'"]');
    if(!el) return;
    el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
    el.scrollIntoView({behavior:"smooth",block:"center"});
  });
});
// 复测题: 答错滚回 review_point_id
document.querySelectorAll(".option").forEach((btn)=>{
  btn.addEventListener("click",()=>{
    document.querySelectorAll(".option").forEach(o=>{o.setAttribute("aria-pressed","false");o.classList.remove("correct","wrong");});
    btn.setAttribute("aria-pressed","true");
    const correct=btn.dataset.correct==="true";
    btn.classList.add(correct?"correct":"wrong");
    const fb=document.getElementById("practiceFeedback");
    fb.classList.remove("correct","wrong"); fb.classList.add("show",correct?"correct":"wrong");
    fb.textContent=(correct?"✅ ":"❌ ")+(btn.dataset.feedback||"");
    if(!correct){
      const el=document.querySelector('[data-point="'+((cardData.practice&&cardData.practice.review_point_id)||"")+'"]');
      if(el){ el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); el.scrollIntoView({behavior:"smooth",block:"center"}); }
    }
  });
});
"""

# 旁白同步(泛化版): anchor 直接匹配 data-anchor;归一,任何原型可共用。
_NARR_JS = r"""
(function(){
  const tEl=document.getElementById("narrTiming"), audio=document.getElementById("narrAudio"), btn=document.getElementById("narrPlay");
  if(!tEl||!audio||!btn) return;
  const timing=JSON.parse(tEl.textContent), sub=document.getElementById("narrSub"), bar=document.getElementById("narrBar");
  const elFor=(a)=>document.querySelector('[data-anchor="'+(a||"").replace(/"/g,'')+'"]');
  let cur=null;
  function focus(seg){
    document.querySelectorAll(".narr-focus").forEach(e=>e.classList.remove("narr-focus"));
    const el=elFor(seg.anchor); if(!el) return;
    el.classList.add("narr-focus");
    if(el.classList.contains("outcome-card")) el.classList.add("revealed");
    el.scrollIntoView({behavior:"smooth",block:"center"});
  }
  audio.addEventListener("timeupdate",()=>{
    const t=audio.currentTime; let seg=timing.segments[0];
    for(const s of timing.segments){ if(t>=s.startSec) seg=s; }
    if(seg&&seg.id!==cur){ cur=seg.id; if(sub) sub.textContent=seg.text; focus(seg); }
    if(bar) bar.style.width=(timing.totalSec?Math.min(100,(t/timing.totalSec)*100):0)+"%";
  });
  function setBtn(){ const p=!audio.paused; btn.classList.toggle("playing",p); btn.setAttribute("aria-pressed",p?"true":"false");
    btn.textContent=p?"⏸ 暂停讲解":(audio.currentTime>0?"▶ 继续讲解":("▶ 听老师讲("+Math.round(timing.totalSec)+" 秒)")); }
  btn.addEventListener("click",()=>{ if(audio.paused) audio.play(); else audio.pause(); });
  audio.addEventListener("play",setBtn); audio.addEventListener("pause",setBtn);
  audio.addEventListener("ended",()=>{ document.querySelectorAll(".narr-focus").forEach(e=>e.classList.remove("narr-focus")); cur=null; setBtn(); if(sub) sub.textContent="讲完啦——自己判一遍,做下面的复测题。"; });
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
    # 走向闭合: next_* 指向已知判断点或 outcome
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
    # 沿 verdict 路径求【实际】到达 outcome, 对比 reached_outcome(防声明与走向不一致)
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
    # candidate 不冒充签发
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


def decision_body(schema: dict[str, Any]) -> str:
    d = schema.get("decision") or {}
    points = d.get("judgment_points") or []
    outcomes = {o.get("id"): o for o in (d.get("outcomes") or [])}
    reached_id = d.get("reached_outcome")
    reached = outcomes.get(reached_id, {})
    mode_hint = esc(_MODE_HINT.get(d.get("mode"), ""))

    parts = [
        '<div class="scenario-given" data-anchor="scenario">'
        '<span class="sg-tag">题目情形</span>'
        f'<p>{esc(d.get("scenario_given"))}</p></div>'
    ]
    if mode_hint:
        parts.append(f'<p class="mode-hint">怎么判:{mode_hint}</p>')

    parts.append('<div class="judge-flow">')
    for i, p in enumerate(points):
        verdict = p.get("verdict")
        vmark = "✓" if verdict == "met" else ("✗" if verdict == "unmet" else "?")
        parts.append(
            f'<article class="jp {esc(verdict)}" data-point="{esc(p.get("id"))}" data-anchor="point:{esc(p.get("id"))}">'
            f'<div class="jp-head"><span class="jp-no">{i + 1}</span><h3>{esc(p.get("question"))}</h3></div>'
            f'<div class="jp-criterion"><b>判据:</b>{esc(p.get("criterion"))}</div>'
            f'<div class="jp-verdict"><span class="vmark">{vmark}</span><span>{esc(p.get("verdict_reason"))}</span></div>'
            f'<div class="jp-basis">{esc(p.get("basis"))}</div>'
            '</article>'
        )
        # 走向标注: 命中分支(met 走 next_on_met)
        if i < len(points) - 1:
            label = "满足,继续判" if verdict == "met" else "不满足"
            parts.append(f'<div class="flow-arrow"><span class="ln">↓</span>{esc(label)}</div>')
    parts.append('</div>')
    parts.append('<div class="flow-arrow"><span class="ln">↓</span>得出结论</div>')

    # 结论卡(reveal)
    parts.append(
        '<div class="outcome-card target" data-anchor="outcome">'
        '<div class="outcome-veil" role="button" tabindex="0"><b>先自己判一下 → 点开看结论 ›</b></div>'
        f'<div class="outcome-label"><span class="ok">✓</span>{esc(reached.get("label"))}</div>'
        '<div class="outcome-score"><small>答题这么写才得分</small>'
        f'<span>{esc(d.get("scenario_conclusion") or reached.get("label"))}</span></div>'
        '</div>'
    )

    # 其它分档(让学生看到完整判断空间)
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
            f'<b>{esc(e.get("text"))}{chip}</b>'
            f'<span class="why">{esc(e.get("why"))}</span></button>'
        )
    return "".join(cards)


def client_payload(schema: dict[str, Any]) -> str:
    practice = schema.get("practice") or {}
    return trusted_json_for_script({"practice": {"review_point_id": practice.get("review_point_id")}})


def render(schema: dict[str, Any], timing: dict[str, Any] | None = None) -> str:
    validate(schema)
    title = esc(schema.get("title"))
    student_goal = esc(schema.get("student_goal"))
    why_html = schema.get("why_lose_points_html") or ""
    warm = schema.get("warm_correction_html") or esc(schema.get("warm_correction"))
    memory_hook = esc(schema.get("memory_hook"))
    authority = schema.get("authority") or {}
    practice = schema.get("practice") or {}
    student_boundary = esc(authority.get("student_boundary") or "这是教研讲解,不是官方阅卷;判据以现行规范、教材为准。")
    source_boundary_comment = str(authority.get("source_boundary") or "").replace("--", "—")
    judging_comment = str(authority.get("judging_authority_label") or "").replace("--", "—")
    data = client_payload(schema)
    css = base._CSS + _DECISION_CSS

    narr_player = ""
    narr_tags = ""
    if timing:
        audio_src = esc(timing.get("audio") or "")
        timing_json = trusted_json_for_script(timing)
        narr_player = narration_player(timing)
        narr_tags = (
            f'<audio id="narrAudio" src="{audio_src}" preload="auto"></audio>'
            f'<script type="application/json" id="narrTiming">{timing_json}</script>'
            f"<script>{_NARR_JS}</script>"
        )

    practice_block = ""
    if practice:
        practice_block = f"""
  <section class="practice" id="practice" aria-label="复测题">
    <span class="teacher-tag">先自己判,再练一题</span>
    <h2>{esc(practice.get("title"))}</h2>
    <p class="stem">{esc(practice.get("stem"))}</p>
    <div class="option-grid">{practice_options(schema)}</div>
    <div class="feedback" id="practiceFeedback" role="status"></div>
    <p class="next-action">{esc(practice.get("next_action"))}</p>
  </section>"""

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
created_by: deterministic render_decision_card.py (luban diagram micro-lesson · decision prototype)
schema_version: {SCHEMA_VERSION}
template_type: {esc(schema.get("template_type"))}
judging_authority: {judging_comment}
source_boundary: {source_boundary_comment}
notes: 逐条点亮判断流;只渲染教研预编译例题示范,不判分(判分走 LLM 开放世界);判据 candidate,非官方阅卷。
-->
<main class="page">
  <div class="topline">
    <div class="mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 18h16"></path><path d="M7 18V8l5-3 5 3v10"></path><path d="M9 18v-6h6v6"></path>
      </svg>
    </div>
    <span>鲁班图解微课 · 看判断流 + 听老师讲 + 练一题</span>
  </div>
  <h1>{title}</h1>
  <p class="subtitle">{student_goal}</p>
  <nav class="quicknav" aria-label="快速跳转">
    <a class="qn" href="#rows">① 看判断</a>
    <a class="qn" href="#errors">② 错因自查</a>
    <a class="qn" href="#practice">③ 复测一题</a>
  </nav>
  {narr_player}
  <div class="whycard" data-anchor="why">
    <h2>为什么这个点容易丢分</h2>
    <p>{why_html}</p>
  </div>

  <section class="rows" id="rows" aria-label="判断流">
    {decision_body(schema)}
  </section>

  <section class="section" aria-label="候选采分点">
    <div class="bar" data-anchor="scoring">
      <h2>候选采分点 · 写到才稳</h2>
      <p class="hint">教研整理的关键判据与得分表达,非官方阅卷。</p>
      <div class="score-grid">{score_cards(schema)}</div>
    </div>
  </section>

  <section class="section" id="errors" aria-label="错因自查">
    <div class="bar">
      <h2>常见失分写法 · 点一个看怎么补</h2>
      <p class="hint">点你常犯的错,我带你跳到漏掉的那一步判断。</p>
      <div class="error-grid">{error_cards(schema)}</div>
    </div>
  </section>
{practice_block}

  <div class="wrap-card" data-anchor="wrap">
    <b>暖纠正</b>
    <p style="margin:7px 0 0">{warm}</p>
    <div class="memhook">记忆钩子 · <strong>{memory_hook}</strong></div>
  </div>

  <div class="auth">
    <b>考试依据</b>:{student_boundary}
    <div class="nonofficial">非官方阅卷 · 判断流为教学示意 · 判据为教研候选 · 具体以现行规范 / 教材为准</div>
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
    print(f"rendered: {schema_path} -> {out_path}")
    print(
        f"  mode={d.get('mode')} judgment_points={len(d.get('judgment_points') or [])} "
        f"outcomes={len(d.get('outcomes') or [])} scoring_points={len(schema.get('scoring_points') or [])} "
        f"narration={'yes(' + str(round(timing.get('totalSec') or 0)) + 's)' if timing else 'no'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
