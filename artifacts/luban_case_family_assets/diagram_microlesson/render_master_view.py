#!/usr/bin/env python3
"""深母题【前台学习闭环】视图渲染器(样板)。

输入:M_*.master.json(luban_deep_archetype_master.sample.v0)。
输出:小程序 WebView 可承载的静态 HTML:母题头(不变量/出题人意图)→ 讲懂入口(链讲懂卡)
      → 变题闯关(同考点换工程/数值,逐题判档,即时对错)→ 看穿鉴别(真懂分档 vs 背结论,暖反馈)。

边界:只渲染教研预编译的母题样板;不判分(判分走 grading artifact/LLM 开放世界)、不写掌握结论
      (mastery 是鉴别候选,终判归 LearnerStateService)。复用 render_contrast_card 脊柱。
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
.mhead{background:#0f1f3a;border-radius:20px;padding:18px 20px;margin:0 0 16px;color:#eaf1ff;box-shadow:var(--shadow)}
.mhead .tag{display:inline-block;font-size:12px;font-weight:800;color:#cfe0ff;background:rgba(255,255,255,.12);border-radius:999px;padding:3px 11px;margin-bottom:9px}
.mhead h1{margin:0 0 12px;font-size:23px;line-height:1.25}
.mhead .row{margin-top:9px;font-size:13.5px;line-height:1.6;color:#cdddf6}
.mhead .row b{color:#fff}
.step{background:rgba(255,255,255,.92);border:1px solid rgba(203,213,225,.9);border-radius:18px;box-shadow:var(--shadow);padding:16px 18px;margin:0 0 16px}
.step .stepno{display:inline-flex;align-items:center;gap:8px;font-size:13px;font-weight:800;color:var(--progress);margin-bottom:9px}
.step .stepno i{width:24px;height:24px;border-radius:50%;background:var(--progress);color:#fff;display:grid;place-items:center;font-size:13px;font-style:normal}
.teach-link{display:inline-flex;align-items:center;min-height:46px;padding:11px 16px;border-radius:13px;background:var(--progress);color:#fff;font-weight:800;text-decoration:none;font-size:14px}
.teach-note{margin:10px 0 0;color:var(--sub);font-size:13px}
.quiz{display:none} .quiz.active{display:block}
.q-prog{display:flex;gap:6px;margin-bottom:12px}
.q-prog i{flex:1;height:6px;border-radius:999px;background:#e2e8f0}
.q-prog i.done{background:var(--correct)} .q-prog i.cur{background:var(--progress)} .q-prog i.wrong{background:var(--wrong)}
.q-stem{font-size:15px;font-weight:600;color:var(--ink);line-height:1.6;margin:0 0 13px}
.q-opts{display:grid;gap:10px}
.q-opt{min-height:52px;text-align:left;border-radius:13px;border:1px solid var(--line);background:#fff;padding:11px 13px;cursor:pointer;color:#263241;font-size:14px;line-height:1.5}
.q-opt:hover{border-color:#a9c6f7}
.q-opt[data-state="correct"]{border-color:var(--correct-line);background:var(--correct-bg);color:#0f6b4f;font-weight:600}
.q-opt[data-state="wrong"]{border-color:var(--wrong-line);background:var(--wrong-bg);color:#9a3412}
.q-fb{margin-top:12px;border-radius:12px;padding:11px 13px;font-size:13.5px;line-height:1.6;display:none}
.q-fb.show{display:block}
.q-fb.correct{background:var(--correct-bg);border:1px solid var(--correct-line);color:#0f6b4f}
.q-fb.wrong{background:var(--wrong-bg);border:1px solid var(--wrong-line);color:#9a3412}
.q-fb .tier{display:block;margin-top:5px;font-size:12px;color:var(--sub)}
.q-next{margin-top:13px;min-height:46px;width:100%;border-radius:13px;border:0;background:var(--ink);color:#fff;font-weight:800;font-size:15px;cursor:pointer;display:none}
.q-next.show{display:block}
.verdict{display:none}
.verdict.active{display:block}
.verdict-card{border-radius:18px;padding:18px 20px;box-shadow:var(--shadow)}
.verdict-card.real{background:var(--correct-bg);border:1px solid var(--correct-line)}
.verdict-card.partial{background:var(--partial-bg);border:1px solid var(--partial-line)}
.verdict-card.rote{background:#eef2f7;border:1px solid var(--line)}
.verdict-card h2{margin:0 0 10px;font-size:19px}
.verdict-card.real h2{color:#0f6b4f} .verdict-card.partial h2{color:#8a5212} .verdict-card.rote h2{color:#33425a}
.verdict-card p{margin:0;font-size:15px;line-height:1.65;color:var(--ink)}
.verdict-score{margin:12px 0;font-size:14px;color:var(--sub)}
.verdict-score b{color:var(--ink);font-size:16px}
.retry{margin-top:14px;min-height:44px;padding:10px 18px;border-radius:12px;border:1px solid var(--line);background:#fff;color:#334155;font-weight:700;cursor:pointer}
.auth{margin-top:18px;border:1px solid var(--line);border-radius:15px;background:#fff;padding:13px;color:var(--sub);font-size:12px}
.auth .nonofficial{margin-top:8px;font-weight:700;color:#9a3412}
"""

_MASTER_JS = r"""
const M = JSON.parse(document.getElementById("masterData").textContent);
const V = M.variants;
let cur = 0; const results = [];
const quiz = document.getElementById("quiz");
const stemEl = document.getElementById("qStem");
const optsEl = document.getElementById("qOpts");
const fbEl = document.getElementById("qFb");
const nextEl = document.getElementById("qNext");
const progEl = document.getElementById("qProg");

function renderProg(){
  progEl.innerHTML = V.map((_,i)=>{
    let c = i<results.length ? (results[i]?"done":"wrong") : (i===cur?"cur":"");
    return '<i class="'+c+'"></i>';
  }).join("");
}
function renderQ(){
  const v = V[cur];
  stemEl.textContent = `第 ${cur+1}/${V.length} 题 · ${v.stem}`;
  fbEl.className = "q-fb"; fbEl.textContent = ""; nextEl.className = "q-next";
  optsEl.innerHTML = "";
  v.options.forEach(o=>{
    const b = document.createElement("button");
    b.className = "q-opt"; b.type = "button"; b.textContent = o.id + ". " + o.text;
    b.addEventListener("click",()=>answer(o, b, v));
    optsEl.appendChild(b);
  });
  renderProg();
}
function answer(o, btn, v){
  if(results.length > cur) return; // 已答
  [...optsEl.children].forEach(x=>x.style.pointerEvents="none");
  const correct = !!o.is_correct;
  btn.dataset.state = correct ? "correct" : "wrong";
  if(!correct){
    [...optsEl.children].forEach((x,i)=>{ if(v.options[i].is_correct) x.dataset.state="correct"; });
  }
  fbEl.className = "q-fb show " + (correct?"correct":"wrong");
  fbEl.innerHTML = (correct?"✅ ":"❌ ") + (v.feedback||"") + '<span class="tier">判据:'+(v.basis||"")+' · 档位:'+(v.tier_tag||"")+'</span>';
  results[cur] = correct;
  renderProg();
  nextEl.className = "q-next show";
  nextEl.textContent = (cur < V.length-1) ? "下一题 →" : "看穿:我到底懂没懂 →";
}
nextEl.addEventListener("click",()=>{
  if(cur < V.length-1){ cur++; renderQ(); }
  else showVerdict();
});
function showVerdict(){
  quiz.classList.remove("active");
  const right = results.filter(Boolean).length;
  // 鉴别:V2(边界)+V4(非危大)是关键鉴别题
  const keyIdx = V.map((v,i)=>/边界|非危大|中间档|下限/.test(v.tier_tag||"")?i:-1).filter(i=>i>=0);
  const keyAllRight = keyIdx.every(i=>results[i]);
  const wf = M.mastery_discrimination.warm_feedback;
  let kind, title, msg;
  if(right===V.length){ kind="real"; title="真懂 · 看穿了"; msg=wf.all_correct; }
  else if(results[0] && !keyAllRight){ kind="rote"; title="像在背结论"; msg=wf.rote_leaning; }
  else { kind="partial"; title="就差一步"; msg=wf.partial; }
  const v = document.getElementById("verdict");
  v.querySelector(".verdict-card").className = "verdict-card "+kind;
  v.querySelector("h2").textContent = title;
  v.querySelector(".verdict-msg").textContent = msg;
  v.querySelector(".verdict-score").innerHTML = "答对 <b>"+right+"/"+V.length+"</b> · 关键鉴别题(边界档+非危大档)"+(keyAllRight?"全过":"有失手");
  v.classList.add("active");
  v.scrollIntoView({behavior:"smooth",block:"start"});
}
document.getElementById("retry").addEventListener("click",()=>{
  cur=0; results.length=0;
  document.getElementById("verdict").classList.remove("active");
  quiz.classList.add("active"); renderQ();
  quiz.scrollIntoView({behavior:"smooth",block:"start"});
});
window.__demo=function(mode){results.length=0;if(mode==='rote'){results[0]=true;for(let i=1;i<V.length;i++)results[i]=false;}else{V.forEach((_,i)=>results[i]=true);}cur=V.length-1;showVerdict();};
renderQ();
"""


def render(master: dict[str, Any]) -> str:
    exam_point = esc(master.get("exam_point"))
    invariant = esc(master.get("R2_invariant"))
    intent = esc(master.get("examiner_intent"))
    teach_ref = esc(master.get("teaching_card_ref"))
    boundary = esc((master.get("authority") or {}).get("student_boundary"))
    # 只把闯关+鉴别需要的非敏感字段传前端
    client = {
        "variants": [
            {
                "id": v.get("id"), "stem": v.get("stem"),
                "options": [{"id": o.get("id"), "text": o.get("text"), "is_correct": bool(o.get("is_correct"))} for o in v.get("options") or []],
                "feedback": v.get("feedback"), "basis": v.get("basis"), "tier_tag": v.get("tier_tag"),
            }
            for v in master.get("variants") or []
        ],
        "mastery_discrimination": {"warm_feedback": (master.get("mastery_discrimination") or {}).get("warm_feedback") or {}},
    }
    data = trusted_json_for_script(client)
    css = base._CSS + _MASTER_CSS
    teach_html = f'<a class="teach-link" href="{teach_ref}.selfcontained.html">▶ 先听老师讲这道判断逻辑</a>'

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
created_by: render_master_view.py (luban deep-archetype master · front-stage learning loop, sample)
notes: 讲懂→变题闯关→看穿鉴别;不判分、不写掌握结论(候选);判据为教研候选,非官方阅卷。
-->
<main class="page">
  <div class="mhead">
    <span class="tag">鲁班深母题 · 围绕一个考点的完整闭环</span>
    <h1>{exam_point}</h1>
    <div class="row"><b>出题人真正考:</b>{intent}</div>
    <div class="row"><b>不变量(换皮不变):</b>{invariant}</div>
  </div>

  <div class="step">
    <span class="stepno"><i>1</i>看懂</span>
    {teach_html}
    <p class="teach-note">先把"危大→编方案、超规模→还要论证"两道判据看懂,再来闯关。</p>
  </div>

  <div class="step quiz active" id="quiz">
    <span class="stepno"><i>2</i>闯关变题(同考点换工程/换数值)</span>
    <div class="q-prog" id="qProg"></div>
    <p class="q-stem" id="qStem"></p>
    <div class="q-opts" id="qOpts"></div>
    <div class="q-fb" id="qFb"></div>
    <button class="q-next" id="qNext" type="button"></button>
  </div>

  <div class="verdict" id="verdict">
    <span class="stepno" style="margin-bottom:9px"><i>3</i>看穿:真懂还是背过</span>
    <div class="verdict-card">
      <h2></h2>
      <div class="verdict-score"></div>
      <p class="verdict-msg"></p>
      <button class="retry" id="retry" type="button">换一组数值再练一遍</button>
    </div>
  </div>

  <div class="auth">
    <b>考试依据</b>:{boundary}
    <div class="nonofficial">非官方阅卷 · 判据为教研候选 · 闯关不写掌握结论(鉴别候选)· 具体以现行规范 / 教材为准</div>
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
    print(f"rendered master view: {p} -> {out}")
    print(f"  variants={len(master.get('variants') or [])} exam_point={master.get('exam_point')!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
