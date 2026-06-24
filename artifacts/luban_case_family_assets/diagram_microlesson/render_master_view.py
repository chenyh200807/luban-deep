#!/usr/bin/env python3
"""深母题【前台学习闭环】视图渲染器(样板)· 翻页 deck 版。

输入:M_*.master.json(luban_deep_archetype_master.sample.v0)。
输出:一屏一个重点的翻页 deck——母题头(不变量/出题人意图)/ 讲懂入口 / 每道变题各一屏闯关 / 看穿鉴别。
底部「上一页/下一页」常驻,不下拉。

边界:只渲染教研预编译的母题样板;不判分(判分走 grading artifact/LLM 开放世界)、不写掌握结论
      (mastery 是鉴别候选,终判归 LearnerStateService)。复用 render_contrast_card 脊柱(deck CSS)。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import render_contrast_card as base

esc = base.esc
trusted_json_for_script = base.trusted_json_for_script

_MASTER_CSS = r"""
.mhead{background:#0f1f3a;border-radius:20px;padding:18px 20px;color:#eaf1ff;box-shadow:var(--shadow)}
.mhead .tag{display:inline-block;font-size:12px;font-weight:800;color:#cfe0ff;background:rgba(255,255,255,.12);border-radius:999px;padding:3px 11px;margin-bottom:10px}
.mhead h1{margin:0 0 14px;font-size:22px;line-height:1.3}
.mhead .row{margin-top:11px;font-size:14px;line-height:1.7;color:#cdddf6}
.mhead .row b{color:#fff}
.teach-link{display:inline-flex;align-items:center;min-height:50px;padding:14px 18px;border-radius:14px;background:var(--progress);color:#fff;font-weight:800;text-decoration:none;font-size:16px;box-shadow:var(--shadow)}
.teach-note{margin:14px 0 0;color:var(--sub);font-size:14px;line-height:1.6}
.q-opts{display:grid;gap:10px}
.q-opt{min-height:56px;text-align:left;border-radius:13px;border:1px solid var(--line);background:#fff;padding:12px 14px;cursor:pointer;color:#263241;font-size:15px;line-height:1.5}
.q-opt[data-state="correct"]{border-color:var(--correct-line);background:var(--correct-bg);color:#0f6b4f;font-weight:600}
.q-opt[data-state="wrong"]{border-color:var(--wrong-line);background:var(--wrong-bg);color:#9a3412}
.q-fb{margin-top:13px;border-radius:12px;padding:12px 14px;font-size:14px;line-height:1.6;display:none}
.q-fb.show{display:block}
.q-fb.correct{background:var(--correct-bg);border:1px solid var(--correct-line);color:#0f6b4f}
.q-fb.wrong{background:var(--wrong-bg);border:1px solid var(--wrong-line);color:#9a3412}
.q-fb .tier{display:block;margin-top:6px;font-size:12.5px;color:var(--sub)}
.verdict-card{border-radius:18px;padding:18px 20px;box-shadow:var(--shadow)}
.verdict-card.real{background:var(--correct-bg);border:1px solid var(--correct-line)}
.verdict-card.partial{background:var(--partial-bg);border:1px solid var(--partial-line)}
.verdict-card.rote{background:#eef2f7;border:1px solid var(--line)}
.verdict-card h2{margin:0 0 10px;font-size:20px}
.verdict-card.real h2{color:#0f6b4f} .verdict-card.partial h2{color:#8a5212} .verdict-card.rote h2{color:#33425a}
.verdict-card p{margin:0;font-size:15px;line-height:1.7;color:var(--ink)}
.verdict-score{margin:12px 0;font-size:14px;color:var(--sub)}
.verdict-score b{color:var(--ink);font-size:16px}
.retry{margin-top:16px;min-height:46px;padding:11px 18px;border-radius:12px;border:1px solid var(--line);background:#fff;color:#334155;font-weight:700;cursor:pointer}
"""

_MASTER_JS = r"""
const M = JSON.parse(document.getElementById("masterData").textContent);
const V = M.variants;
const slides = [...document.querySelectorAll(".slide")];
const TOTAL = slides.length;
let screen = 0; const results = [];
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
  if(slides[screen].dataset.verdict!==undefined) showVerdict();
  window.scrollTo(0,0);
}
// 每道变题屏: 选答 → 记 results + 屏内反馈
slides.forEach((s)=>{
  const qi=s.dataset.qi; if(qi===undefined) return;
  const i=parseInt(qi,10); const v=V[i];
  const opts=[...s.querySelectorAll(".q-opt")]; const fb=s.querySelector(".q-fb");
  opts.forEach((b)=>b.addEventListener("click",()=>{
    if(results[i]!==undefined) return;
    opts.forEach(x=>x.style.pointerEvents="none");
    const correct=b.dataset.id===v.answer;
    b.dataset.state=correct?"correct":"wrong";
    if(!correct) opts.forEach(x=>{ if(x.dataset.id===v.answer) x.dataset.state="correct"; });
    fb.className="q-fb show "+(correct?"correct":"wrong");
    fb.innerHTML=(correct?"✅ ":"❌ ")+(v.feedback||"")+'<span class="tier">判据:'+(v.basis||"")+' · 档位:'+(v.tier_tag||"")+'</span>';
    results[i]=correct;
  }));
});
function showVerdict(){
  const right=results.filter(Boolean).length;
  const keyIdx=V.map((v,i)=>/边界|非危大|中间档|下限/.test(v.tier_tag||"")?i:-1).filter(i=>i>=0);
  const keyAllRight=keyIdx.every(i=>results[i]);
  const answered=results.filter(x=>x!==undefined).length;
  const wf=M.mastery_discrimination.warm_feedback;
  let kind,title,msg;
  if(answered<V.length){ kind="partial"; title="还没答完"; msg="把 "+V.length+" 道变题都判一遍,才看得准你是真懂还是背过。"; }
  else if(right===V.length){ kind="real"; title="真懂 · 看穿了"; msg=wf.all_correct; }
  else if(results[0] && !keyAllRight){ kind="rote"; title="像在背结论"; msg=wf.rote_leaning; }
  else { kind="partial"; title="就差一步"; msg=wf.partial; }
  const card=document.querySelector(".verdict-card");
  card.className="verdict-card "+kind;
  card.querySelector("h2").textContent=title;
  card.querySelector(".verdict-msg").textContent=msg;
  card.querySelector(".verdict-score").innerHTML="答对 <b>"+right+"/"+V.length+"</b> · 关键鉴别题(边界档+非危大档)"+(answered<V.length?"未答完":(keyAllRight?"全过":"有失手"));
}
const retry=$("retry");
if(retry) retry.addEventListener("click",()=>{
  results.length=0;
  slides.forEach(s=>{ if(s.dataset.qi===undefined) return; s.querySelectorAll(".q-opt").forEach(x=>{x.dataset.state="";x.style.pointerEvents="";}); const fb=s.querySelector(".q-fb"); if(fb){fb.className="q-fb";fb.textContent="";} });
  goScreen(slides.findIndex(s=>s.dataset.qi==="0"));
});
if(prevBtn) prevBtn.addEventListener("click",()=>goScreen(screen-1));
if(nextBtn) nextBtn.addEventListener("click",()=>goScreen(screen===TOTAL-1?0:screen+1));
document.addEventListener("keydown",(e)=>{ if(e.key==="ArrowRight")goScreen(screen+1); if(e.key==="ArrowLeft")goScreen(screen-1); });
goScreen(0);
"""


def render(master: dict[str, Any]) -> str:
    exam_point = esc(master.get("exam_point"))
    invariant = esc(master.get("R2_invariant"))
    intent = esc(master.get("examiner_intent"))
    teach_ref = esc(master.get("teaching_card_ref"))
    boundary = esc((master.get("authority") or {}).get("student_boundary"))
    variants = master.get("variants") or []
    client = {
        "variants": [
            {
                "id": v.get("id"), "answer": v.get("answer"),
                "feedback": v.get("feedback"), "basis": v.get("basis"), "tier_tag": v.get("tier_tag"),
            }
            for v in variants
        ],
        "mastery_discrimination": {"warm_feedback": (master.get("mastery_discrimination") or {}).get("warm_feedback") or {}},
    }
    data = trusted_json_for_script(client)
    css = base._CSS + _MASTER_CSS
    teach_html = f'<a class="teach-link" href="{teach_ref}.schema_draft.rendered.html">▶ 先听老师讲这道判断逻辑</a>'

    slides: list[str] = []
    # 屏 0:母题头 + 讲懂入口
    slides.append(
        '<section class="slide active">'
        '<div class="mhead"><span class="tag">鲁班深母题 · 围绕一个考点的完整闭环</span>'
        f'<h1>{exam_point}</h1>'
        f'<div class="row"><b>出题人真正考:</b>{intent}</div>'
        f'<div class="row"><b>不变量(换皮不变):</b>{invariant}</div></div>'
        '<div style="margin-top:16px">'
        '<div class="slide-kicker">第一步 · 看懂</div>'
        f'{teach_html}'
        '<p class="teach-note">先把两道判据看懂(危大→编方案、超规模→还要论证),再来闯关。点底部「下一页」开始。</p>'
        '</div></section>'
    )
    # 屏 1..n:每道变题各一屏(闯关)
    for i, v in enumerate(variants):
        opts = "".join(
            f'<button class="q-opt" type="button" data-id="{esc(o.get("id"))}">{esc(o.get("id"))}. {esc(o.get("text"))}</button>'
            for o in v.get("options") or []
        )
        slides.append(
            f'<section class="slide" data-qi="{i}">'
            f'<div class="slide-kicker">闯关 {i + 1} / {len(variants)} · 同考点换工程/数值</div>'
            f'<h2 class="slide-title">{esc(v.get("stem"))}</h2>'
            f'<div class="q-opts">{opts}</div>'
            '<div class="q-fb"></div></section>'
        )
    # 屏 n+1:看穿鉴别
    slides.append(
        '<section class="slide" data-verdict>'
        '<div class="slide-kicker">看穿:真懂还是背过</div>'
        '<div class="verdict-card"><h2></h2><div class="verdict-score"></div>'
        '<p class="verdict-msg"></p>'
        '<button class="retry" id="retry" type="button">换一组数值再练一遍</button></div>'
        f'<div class="auth"><b>考试依据</b>:{boundary}'
        '<div class="nonofficial">非官方阅卷 · 判据为教研候选 · 闯关不写掌握结论(鉴别候选)· 具体以现行规范 / 教材为准</div></div></section>'
    )

    slides_html = "".join(slides)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{exam_point} · 深母题</title>
<style>{css}</style>
</head>
<body>
<!--
created_by: render_master_view.py (luban deep-archetype master · deck) — 讲懂→变题闯关→看穿鉴别;不判分、不写掌握结论(候选)。
-->
<main class="deck">
  <div class="deck-top"><span class="brandmini">鲁班深母题 · {exam_point}</span><span class="deck-count" id="deckCount">1 / 1</span></div>
  {slides_html}
  <div class="stepnav">
    <button class="nav-btn" id="prevBtn" type="button">← 上一页</button>
    <div class="nav-mid"><span id="stepCount">1 / 1</span><i class="nav-prog"><b id="progressBar"></b></i></div>
    <button class="nav-btn primary" id="nextBtn" type="button">下一页 →</button>
  </div>
</main>
<script type="application/json" id="masterData">{data}</script>
<script>{_MASTER_JS}</script>
</body>
</html>"""


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    p = Path(argv[1])
    out = Path(argv[2]) if len(argv) > 2 else p.with_suffix(".view.html")
    master = json.loads(p.read_text(encoding="utf-8"))
    out.write_text(render(master), encoding="utf-8")
    print(f"rendered master view (deck): {p} -> {out}")
    print(f"  variants={len(master.get('variants') or [])} exam_point={master.get('exam_point')!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
