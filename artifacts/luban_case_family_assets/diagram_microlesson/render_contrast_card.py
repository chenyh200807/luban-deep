#!/usr/bin/env python3
"""图解微课 ⑤对比/正误原型确定性渲染器（luban_diagram_microlesson.v1）。

输入:一份 template_type=contrast_pair_reveal(_draft) 的考点 schema JSON。
输出:小程序 WebView 可承载的静态 HTML 卡:内联 SVG、内联 CSS、少量内联 JS。

边界(与 SCHEMA.md / style-guide / 红线一致):
- 渲染器只渲染 schema 内事实,不生成知识、不判分、不补采分点。
- 左右正误对照(OSHA do/don't 范式):绿=对 / 红=错,语义色永不互换。
- 图形是确定性 SVG 图元示意,不是规范级节点详图(不文生图)。
- student-safe fail-closed:错因只出 loss_display 汉语名,绝不渲 error_code(E03/E06)/
  scoring_point id / source_ref / kind / candidate / 母题包 等内部词。
- 交互只做 reveal(揭示正确做法)、错因跳转、复测反馈,不访问网络、不依赖外链、不接 TTS。
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "luban_diagram_microlesson.v1"
CONTRAST_TEMPLATES = {"contrast_pair_reveal", "contrast_pair_reveal_draft"}
CANDIDATE_STATUSES = {"candidate", "candidate_teaching_prototype", "prototype", "draft"}

_TIER_LABEL = {
    "exact_required": "须写到关键词",
    "high_risk_review": "高风险表达",
    "list_rule": "列举规则",
    "calculation": "计算规则",
}

# 语义色收敛到 style-guide.md 单一源(绿=对/红=错/琥珀=差一口气/蓝=中性进度)。
_CSS = r"""
:root{
  --bg:#eef1f5;
  --surface:#ffffff;
  --paper:#fffdf8;
  --ink:#1d2530;
  --sub:#6b7686;
  --line:#e7ebf0;
  --correct:#1aa06d; --correct-bg:#e8f7f0; --correct-line:#bfe6d4;
  --wrong:#d9534f;   --wrong-bg:#fdecea;   --wrong-line:#f3c4c0;
  --partial:#e08a1e; --partial-bg:#fdf2e3; --partial-line:#f1d6a6;
  --progress:#2f6df0;--progress-bg:#eaf1ff;
  --shadow:0 16px 38px rgba(29,37,48,.12);
}
*{box-sizing:border-box}
html,body{max-width:100%;overflow-x:hidden}
body{
  margin:0;background:linear-gradient(180deg,#eef4f8 0%,#f7f8f4 52%,#f2f5f7 100%);
  color:var(--ink);line-height:1.55;
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif;
}
button{font:inherit}
.page{max-width:1040px;margin:0 auto;padding:24px 16px 48px}
.topline{display:flex;gap:10px;align-items:center;color:var(--sub);font-size:13px;margin-bottom:10px}
.mark{width:34px;height:34px;border-radius:11px;background:var(--progress);display:grid;place-items:center;box-shadow:0 8px 18px rgba(47,109,240,.25)}
.mark svg{width:19px;height:19px;stroke:#fff}
h1{margin:0;font-size:clamp(22px,3.4vw,34px);line-height:1.2}
.subtitle{max-width:760px;margin:10px 0 14px;color:#52617a;font-size:15px}
.quicknav{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px}
.qn{display:inline-flex;align-items:center;min-height:40px;padding:8px 14px;border-radius:999px;background:#fff;border:1px solid var(--line);color:#33425a;font-size:13px;font-weight:700;text-decoration:none;box-shadow:0 6px 14px rgba(29,37,48,.06)}
.qn:hover{border-color:#a9c6f7;color:var(--progress)}
.teacher-tag{display:inline-block;font-size:11px;font-weight:800;color:var(--progress);background:#dce8ff;border-radius:999px;padding:3px 10px;margin-bottom:10px;letter-spacing:.02em}
.whycard{background:var(--progress-bg);border:1px solid #c3d8fb;border-radius:18px;padding:15px 17px;margin:0 0 18px;box-shadow:var(--shadow)}
.whycard h2{margin:0 0 7px;font-size:16px;color:#1d4ed8}
.whycard p{margin:0;color:#33425a;font-size:14px}
.whycard b{color:var(--ink)}
.narrator{background:#0f1f3a;border-radius:18px;padding:16px 18px;margin:0 0 18px;color:#eaf1ff;box-shadow:var(--shadow)}
.narrator .npar{display:flex;align-items:center;gap:14px}
.narr-play{flex:0 0 auto;min-height:48px;padding:12px 18px;border-radius:13px;border:0;background:var(--progress);color:#fff;font-size:15px;font-weight:800;cursor:pointer;display:inline-flex;align-items:center;gap:8px;white-space:nowrap}
.narr-play.playing{background:#fff;color:var(--progress)}
.narr-meta{font-size:13px;color:#a9c2ef;line-height:1.5}
.narr-sub{margin-top:12px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);border-radius:12px;padding:12px 14px;font-size:15px;line-height:1.6;min-height:48px}
.narr-track{margin-top:10px;height:8px;border-radius:999px;background:rgba(255,255,255,.16);overflow:hidden}
.narr-track i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--progress),var(--correct));border-radius:inherit;transition:width .25s linear}
.narr-focus{outline:4px solid var(--progress);outline-offset:5px;border-radius:20px}
.rows{display:grid;gap:18px}
.crow{background:rgba(255,255,255,.9);border:1px solid rgba(203,213,225,.9);border-radius:20px;box-shadow:var(--shadow);overflow:hidden}
.crow-head{display:flex;gap:12px;align-items:center;padding:14px 16px;border-bottom:1px solid var(--line);background:rgba(255,255,255,.7)}
.crow-no{flex:0 0 auto;width:30px;height:30px;border-radius:9px;background:var(--progress);color:#fff;font-weight:800;display:grid;place-items:center;font-size:14px}
.crow-head h3{margin:0;font-size:16px}
.crow-icon{margin:12px 16px 4px;padding:12px 12px 8px;background:linear-gradient(180deg,#f7fafc,#fffdf8);border:1px solid var(--line);border-radius:14px}
.crow-icon svg{width:100%;max-width:460px;height:auto;display:block;margin:0 auto}
.icon-cap{margin:8px auto 0;max-width:460px;color:var(--sub);font-size:12px;line-height:1.5;text-align:center}
.pair{display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:stretch;padding:14px 16px 16px}
.card{border-radius:15px;padding:13px 14px;border:1px solid var(--line)}
.card .tag{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:800;margin-bottom:7px}
.card .badge{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;color:#fff;font-size:13px;font-weight:900}
.card p{margin:0;font-size:14px;line-height:1.6}
.wrong-card{background:var(--wrong-bg);border-color:var(--wrong-line)}
.wrong-card .tag{color:var(--wrong)} .wrong-card .badge{background:var(--wrong)}
.loss-chip{display:inline-block;margin-top:9px;padding:3px 10px;border-radius:999px;background:#fff;border:1px solid var(--partial-line);color:var(--partial);font-size:12px;font-weight:700}
.arrow{display:grid;place-items:center;color:var(--sub);font-size:20px;font-weight:800}
.right-card{background:var(--correct-bg);border-color:var(--correct-line);position:relative}
.right-card .tag{color:var(--correct)} .right-card .badge{background:var(--correct)}
.scoring-expr{margin-top:11px;border-radius:12px;background:#f3fbf7;border:1px solid var(--correct-line);border-left:4px solid var(--correct);padding:10px 12px}
.scoring-expr small{display:block;color:var(--correct);font-weight:800;font-size:11.5px;margin-bottom:4px;letter-spacing:.02em}
.scoring-expr span{font-size:14px;color:#15402f;font-weight:600;line-height:1.6}
.veil{position:absolute;inset:0;border-radius:15px;background:rgba(232,247,240,.92);backdrop-filter:blur(2px);display:grid;place-items:center;cursor:pointer;border:1px dashed var(--correct-line)}
.veil b{color:var(--correct);font-weight:800;font-size:14px}
.right-card.revealed .veil{display:none}
.section{margin-top:20px}
.section h2{font-size:18px;margin:0 0 4px}
.section .hint{margin:0 0 12px;color:var(--sub);font-size:13px}
.bar{background:rgba(255,255,255,.9);border:1px solid rgba(203,213,225,.9);border-radius:18px;padding:16px 18px;box-shadow:var(--shadow)}
.score-grid,.error-grid{display:grid;gap:10px}
.score-card{background:#fff;border:1px solid var(--line);border-radius:13px;padding:12px;border-left:4px solid var(--correct)}
.score-card b{display:block;font-size:13px;margin-bottom:5px}
.score-card span{color:var(--sub);font-size:12.5px}
.error-card{cursor:pointer;text-align:left;background:#fff;border:1px solid var(--line);border-radius:13px;padding:12px;border-left:4px solid var(--partial)}
.error-card:hover{border-color:#a9c6f7;background:#f8fbff}
.error-card b{display:block;font-size:13px;margin-bottom:5px}
.error-card .loss{display:inline-block;margin-left:6px;padding:1px 8px;border-radius:7px;background:var(--partial-bg);color:var(--partial);font-size:11px;font-weight:700}
.error-card span.why{display:block;color:var(--sub);font-size:12.5px}
.crow.flash{animation:flash 1.1s ease}
@keyframes flash{0%{box-shadow:0 0 0 0 rgba(47,109,240,.5)}100%{box-shadow:var(--shadow)}}
.practice{margin-top:20px;border-radius:20px;padding:18px;background:#fff;border:1px solid rgba(203,213,225,.9);box-shadow:var(--shadow)}
.practice .teacher-tag{margin-bottom:6px}
.practice h2{font-size:18px;margin:0 0 8px}
.practice p.stem{font-size:14.5px;color:#36465a;margin:0 0 13px}
.option-grid{display:grid;gap:10px}
.option{min-height:54px;text-align:left;border-radius:13px;border:1px solid var(--line);background:#fff;padding:11px 13px;cursor:pointer;color:#263241;font-size:14px}
.option:hover{border-color:#a9c6f7}
.option[aria-pressed="true"].correct{border-color:var(--correct-line);background:var(--correct-bg)}
.option[aria-pressed="true"].wrong{border-color:var(--wrong-line);background:var(--wrong-bg)}
.option b{margin-right:6px}
.feedback{margin-top:12px;border-radius:12px;padding:11px 12px;background:#f8fafc;border:1px solid var(--line);color:#405066;font-size:13.5px;line-height:1.55;display:none}
.feedback.show{display:block}
.feedback.correct{background:var(--correct-bg);border-color:var(--correct-line);color:#0f6b4f;font-weight:600}
.feedback.wrong{background:var(--wrong-bg);border-color:var(--wrong-line);color:#9a3412}
.next-action{margin-top:12px;color:var(--sub);font-size:13px}
.wrap-card{margin-top:20px;border-radius:18px;padding:16px 18px;background:var(--correct-bg);border:1px solid var(--correct-line)}
.wrap-card b{color:#0f6b4f}
.memhook{margin-top:11px;border-radius:12px;background:#fff;border:1px dashed var(--correct-line);padding:11px 13px;font-size:14px;color:#15402f}
.memhook strong{color:var(--correct)}
.auth{margin-top:20px;border:1px solid var(--line);border-radius:15px;background:#fff;padding:13px;color:var(--sub);font-size:12px}
.auth .nonofficial{margin-top:8px;font-weight:700;color:#9a3412}
.sf{fill:none}
.label{fill:#33425a;font-weight:700}
.label-sub{fill:#6b7686;font-weight:600}
.label-correct{fill:#0f6b4f} .label-wrong{fill:#b5392f}
@media (max-width:560px){
  .page{padding:16px 11px 32px}
  h1{font-size:20px;line-height:1.26}
  .subtitle{font-size:13px}
  .qn{flex:1 1 28%;justify-content:center;min-height:44px;padding:8px 6px;font-size:12px}
  .pair{grid-template-columns:1fr;gap:10px}
  .arrow{transform:rotate(90deg)}
  .crow-icon svg,.icon-cap{max-width:100%}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

_JS = r"""
const cardData = JSON.parse(document.getElementById("cardData").textContent);

// 揭示正确做法: 默认右卡蒙层, 点开 → 露采分表达(动效通向"先看坏在哪→再给对")
document.querySelectorAll(".veil").forEach((v)=>{
  v.addEventListener("click",()=>{ v.closest(".right-card").classList.add("revealed"); maybePromptPractice(); });
});
let revealedAll=false;
function maybePromptPractice(){
  const cards=[...document.querySelectorAll(".right-card")];
  if(!revealedAll && cards.length && cards.every(c=>c.classList.contains("revealed"))){
    revealedAll=true;
    const fb=document.getElementById("revealDone");
    if(fb) fb.style.display="block";
  }
}

// 错因卡: 点一个常见错 → 滚到对应对照行并闪一下(jump_item_id 指向 contrast_items[].id, 非内部编号)
document.querySelectorAll(".error-card").forEach((btn)=>{
  btn.addEventListener("click",()=>{
    const target=btn.dataset.jump;
    const row=document.querySelector('.crow[data-item="'+target+'"]');
    if(!row) return;
    const rc=row.querySelector(".right-card");
    if(rc) rc.classList.add("revealed");
    row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash");
    row.scrollIntoView({behavior:"smooth",block:"center"});
    maybePromptPractice();
  });
});

// 复测题: 答对/答错都讲清原因; 答错滚回 review_item_id 对照行
document.querySelectorAll(".option").forEach((btn)=>{
  btn.addEventListener("click",()=>{
    document.querySelectorAll(".option").forEach(o=>{o.setAttribute("aria-pressed","false");o.classList.remove("correct","wrong");});
    btn.setAttribute("aria-pressed","true");
    const correct=btn.dataset.correct==="true";
    btn.classList.add(correct?"correct":"wrong");
    const fb=document.getElementById("practiceFeedback");
    fb.classList.remove("correct","wrong");
    fb.classList.add("show",correct?"correct":"wrong");
    fb.textContent=(correct?"✅ ":"❌ ")+(btn.dataset.feedback||"");
    if(!correct){
      const reviewId=(cardData.practice&&cardData.practice.review_item_id)||"";
      const row=document.querySelector('.crow[data-item="'+reviewId+'"]');
      if(row){
        const rc=row.querySelector(".right-card"); if(rc) rc.classList.add("revealed");
        row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash");
        row.scrollIntoView({behavior:"smooth",block:"center"});
      }
    }
  });
});
"""


# 旁白同步: 读预存音频 + timing, 播到某段就高亮/reveal 对应卡内锚点。无 TTS, 不重新合成。
_NARR_JS = r"""
(function(){
  const tEl = document.getElementById("narrTiming");
  const audio = document.getElementById("narrAudio");
  const btn = document.getElementById("narrPlay");
  if(!tEl || !audio || !btn) return;
  const timing = JSON.parse(tEl.textContent);
  const sub = document.getElementById("narrSub");
  const bar = document.getElementById("narrBar");
  function elForAnchor(a){
    if(a === "why") return document.querySelector('[data-anchor="why"]');
    if(a === "scoring") return document.querySelector('[data-anchor="scoring"]');
    if(a === "wrap") return document.querySelector('[data-anchor="wrap"]');
    if(a && a.indexOf("item:") === 0) return document.querySelector('.crow[data-item="'+a.slice(5)+'"]');
    return null;
  }
  let cur = null;
  function focus(seg){
    document.querySelectorAll(".narr-focus").forEach(e=>e.classList.remove("narr-focus"));
    const el = elForAnchor(seg.anchor);
    if(!el) return;
    el.classList.add("narr-focus");
    const rc = el.querySelector(".right-card"); if(rc) rc.classList.add("revealed");
    el.scrollIntoView({behavior:"smooth", block:"center"});
  }
  audio.addEventListener("timeupdate",()=>{
    const t = audio.currentTime;
    let seg = timing.segments[0];
    for(const s of timing.segments){ if(t >= s.startSec) seg = s; }
    if(seg && seg.id !== cur){ cur = seg.id; if(sub) sub.textContent = seg.text; focus(seg); }
    if(bar) bar.style.width = (timing.totalSec ? Math.min(100,(t/timing.totalSec)*100) : 0) + "%";
  });
  function setBtn(){
    const playing = !audio.paused;
    btn.classList.toggle("playing", playing);
    btn.setAttribute("aria-pressed", playing ? "true" : "false");
    btn.textContent = playing ? "⏸ 暂停讲解" : (audio.currentTime > 0 ? "▶ 继续讲解" : ("▶ 听老师讲(" + Math.round(timing.totalSec) + " 秒)"));
  }
  btn.addEventListener("click",()=>{ if(audio.paused) audio.play(); else audio.pause(); });
  audio.addEventListener("play", setBtn);
  audio.addEventListener("pause", setBtn);
  audio.addEventListener("ended",()=>{
    document.querySelectorAll(".narr-focus").forEach(e=>e.classList.remove("narr-focus"));
    cur = null; setBtn();
    if(sub) sub.textContent = "讲完啦——自己点开对照、做下面的复测题试试。";
  });
})();
"""


def narration_player(timing: dict[str, Any]) -> str:
    total = int(round(timing.get("totalSec") or 0))
    return (
        '<div class="narrator">'
        '<div class="npar">'
        f'<button class="narr-play" id="narrPlay" type="button" aria-pressed="false">▶ 听老师讲({total} 秒)</button>'
        '<div class="narr-meta">老师拿着这张卡给你讲<br>讲到哪里,卡上就高亮哪里</div>'
        '</div>'
        '<div class="narr-sub" id="narrSub">点上面,老师带你把这道题讲一遍;你随时能暂停,也能自己点开下面的对照和复测。</div>'
        '<div class="narr-track" aria-hidden="true"><i id="narrBar"></i></div>'
        '</div>'
    )


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def trusted_json_for_script(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def authority_status(schema: dict[str, Any]) -> str:
    return str((schema.get("authority") or {}).get("status") or "unspecified")


def official_score_claimed(schema: dict[str, Any]) -> bool:
    def walk(x: Any) -> bool:
        if isinstance(x, dict):
            if x.get("official_score_allowed") is True:
                return True
            return any(walk(v) for v in x.values())
        if isinstance(x, list):
            return any(walk(v) for v in x)
        return False

    return walk(schema)


def validate(schema: dict[str, Any]) -> None:
    if schema.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {schema.get('schema_version')!r}")
    tt = schema.get("template_type")
    if tt not in CONTRAST_TEMPLATES:
        raise ValueError(f"contrast renderer requires template_type in {CONTRAST_TEMPLATES}, got {tt!r}")

    items = schema.get("contrast_items") or []
    if not items:
        raise ValueError("contrast card requires non-empty contrast_items")
    ids = [it.get("id") for it in items]
    if len(set(ids)) != len(ids):
        raise ValueError("contrast_items id must be unique")
    for it in items:
        if not (it.get("wrong") or {}).get("text"):
            raise ValueError(f"contrast_items[{it.get('id')!r}].wrong.text required")
        right = it.get("right") or {}
        if not (right.get("text") or right.get("scoring_expression")):
            raise ValueError(f"contrast_items[{it.get('id')!r}].right needs text/scoring_expression")

    # body 互斥: 不得同时带 steps/diagnosis
    if schema.get("steps") or schema.get("diagnosis"):
        raise ValueError("contrast card must not also carry steps/diagnosis body")

    # candidate 不冒充签发
    if authority_status(schema) not in CANDIDATE_STATUSES:
        raise ValueError(f"contrast draft must be candidate/draft authority, got {authority_status(schema)!r}")
    if official_score_claimed(schema):
        raise ValueError("candidate/draft must not set official_score_allowed=true")

    for err in schema.get("common_errors") or []:
        tgt = err.get("jump_item_id")
        if tgt is not None and tgt not in set(ids):
            raise ValueError(f"common_errors jump_item_id not in contrast_items: {tgt!r}")

    practice = schema.get("practice") or {}
    if practice:
        options = practice.get("options") or []
        if len(options) < 2 or sum(1 for o in options if o.get("is_correct")) != 1:
            raise ValueError("practice must have options and exactly one correct option")
        rev = practice.get("review_item_id")
        if rev is not None and rev not in set(ids):
            raise ValueError(f"practice.review_item_id not in contrast_items: {rev!r}")

    # student-safe: 必须显式声明白名单(否则渲染器无法判定脱敏边界)
    if not (schema.get("rendering_contract") or {}).get("student_safe_fields"):
        raise ValueError("contrast card requires rendering_contract.student_safe_fields (student-safe gate)")


def _beam_icon() -> str:
    """简支梁施工缝位置示意(确定性图元, 非规范详图): 跨中绿=宜留, 支座红=不宜。"""
    return r"""
<svg viewBox="0 0 400 172" role="img" aria-label="简支梁施工缝位置示意:跨中受剪力较小宜留,支座附近受剪力较大不宜">
  <text x="200" y="26" text-anchor="middle" class="label label-correct" font-size="19">✓ 宜留区 · 跨中 1/3</text>
  <text x="200" y="48" text-anchor="middle" class="label label-sub" font-size="13.5">受剪力较小、便于施工</text>
  <text x="74" y="78" text-anchor="middle" class="label label-wrong" font-size="15.5">✗ 支座附近</text>
  <text x="326" y="78" text-anchor="middle" class="label label-wrong" font-size="15.5">✗ 支座附近</text>
  <line x1="22" y1="146" x2="378" y2="146" stroke="#cdd6e2" stroke-width="2"></line>
  <rect x="30" y="98" width="340" height="38" rx="6" fill="#e2e8f0" stroke="#9aa6b6" stroke-width="2"></rect>
  <rect x="32" y="100" width="74" height="34" rx="5" fill="#fdecea" fill-opacity="0.92"></rect>
  <rect x="294" y="100" width="74" height="34" rx="5" fill="#fdecea" fill-opacity="0.92"></rect>
  <rect x="135" y="92" width="130" height="50" rx="7" fill="#e8f7f0" fill-opacity="0.85" stroke="#1aa06d" stroke-width="3" stroke-dasharray="8 5"></rect>
  <path d="M42 136 l-15 22 h30 z" fill="#9aa6b6"></path>
  <path d="M358 136 l-15 22 h30 z" fill="#9aa6b6"></path>
  <path d="M64 88 l9 13 M73 88 l-9 13" stroke="#b5392f" stroke-width="3" stroke-linecap="round"></path>
  <path d="M327 88 l9 13 M336 88 l-9 13" stroke="#b5392f" stroke-width="3" stroke-linecap="round"></path>
</svg>
"""


def _treatment_icon() -> str:
    """接缝处理工序示意(确定性图元): 清浮浆→凿毛→湿润→铺同配合比砂浆。"""
    steps = [("清浮浆", "#9aa6b6"), ("凿毛", "#e08a1e"), ("湿润", "#2f6df0"), ("铺浆", "#1aa06d")]
    parts = [
        '<svg viewBox="0 0 400 108" role="img" aria-label="接缝处理工序:清浮浆 凿毛 湿润 铺同配合比砂浆">',
        '<defs><marker id="ar" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">'
        '<path d="M0 0 L9 4.5 L0 9 z" fill="#9aa6b6"></path></marker></defs>',
    ]
    cx = 56
    step_gap = 96
    for i, (label, color) in enumerate(steps):
        parts.append(f'<circle cx="{cx}" cy="44" r="25" fill="{color}"></circle>')
        parts.append(f'<text x="{cx}" y="51" text-anchor="middle" fill="#fff" font-size="17" font-weight="800">{i + 1}</text>')
        parts.append(f'<text x="{cx}" y="96" text-anchor="middle" class="label" font-size="15">{label}</text>')
        if i < len(steps) - 1:
            parts.append(f'<path d="M{cx + 32} 44 h{step_gap - 64}" stroke="#cdd6e2" stroke-width="2.5" marker-end="url(#ar)"></path>')
        cx += step_gap
    parts.append("</svg>")
    return "".join(parts)


# axis id → 确定性图元;无匹配则降级为纯文字(图标是 nice-to-have, 不阻塞任意 contrast 卡渲染)
_AXIS_ICONS = {
    "joint_position": _beam_icon,
    "joint_treatment": _treatment_icon,
}
_AXIS_ICON_CAP = {
    "joint_position": "教学示意(非规范详图):梁的施工缝宜留在受剪力较小的跨中 1/3,避开支座附近。",
    "joint_treatment": "教学示意:继续浇筑前的接缝处理工序顺序。",
}


def contrast_rows(schema: dict[str, Any]) -> str:
    rows = []
    for i, it in enumerate(schema.get("contrast_items") or []):
        item_id = it.get("id")
        wrong = it.get("wrong") or {}
        right = it.get("right") or {}
        loss = esc(wrong.get("loss_display"))
        scoring = esc(right.get("scoring_expression"))
        icon_fn = _AXIS_ICONS.get(item_id)
        icon_block = ""
        if icon_fn:
            cap = esc(_AXIS_ICON_CAP.get(item_id, ""))
            icon_block = (
                f'<div class="crow-icon">{icon_fn()}'
                f'<p class="icon-cap">{cap}</p></div>'
            )
        loss_chip = f'<span class="loss-chip">易失分:{loss}</span>' if loss else ""
        scoring_block = (
            f'<div class="scoring-expr"><small>这样写才得分</small><span>{scoring}</span></div>'
            if scoring
            else ""
        )
        rows.append(
            f'<article class="crow" data-item="{esc(item_id)}">'
            f'<div class="crow-head"><span class="crow-no">{i + 1}</span>'
            f'<h3>{esc(it.get("axis"))}</h3></div>'
            f'{icon_block}'
            '<div class="pair">'
            '<div class="card wrong-card">'
            '<span class="tag"><span class="badge">✗</span>常见错误做法</span>'
            f'<p>{esc(wrong.get("text"))}</p>{loss_chip}</div>'
            '<div class="arrow" aria-hidden="true">→</div>'
            '<div class="card right-card">'
            '<span class="tag"><span class="badge">✓</span>正确做法</span>'
            f'<p>{esc(right.get("text"))}</p>{scoring_block}'
            '<div class="veil" role="button" tabindex="0"><b>点开看正确做法 ›</b></div>'
            '</div>'
            '</div>'
            '</article>'
        )
    return "".join(rows)


def score_cards(schema: dict[str, Any]) -> str:
    """student-safe: 只出 tier 中文 + keywords;绝不出 id / source_ref / kind。"""
    cards = []
    for p in schema.get("scoring_points") or []:
        tier = esc(_TIER_LABEL.get(p.get("tier"), p.get("tier")))
        kws = " / ".join(esc(k) for k in p.get("keywords") or [])
        cards.append(
            f'<div class="score-card"><b>{tier}</b>'
            f'<span>写到这些词更稳:{kws}</span></div>'
        )
    return "".join(cards)


def error_cards(schema: dict[str, Any]) -> str:
    """student-safe: 错因只出 loss_display 汉语名;绝不渲 error_code(E03/E06)。"""
    cards = []
    for e in schema.get("common_errors") or []:
        loss = esc(e.get("loss_display"))
        loss_chip = f'<span class="loss">{loss}</span>' if loss else ""
        cards.append(
            '<button class="error-card" type="button" '
            f'data-jump="{esc(e.get("jump_item_id"))}">'
            f'<b>{esc(e.get("text"))}{loss_chip}</b>'
            f'<span class="why">{esc(e.get("why"))}</span></button>'
        )
    return "".join(cards)


def practice_options(schema: dict[str, Any]) -> str:
    practice = schema.get("practice") or {}
    # 新卡标准:单一正确 id practice.answer(泄漏面更小);无 answer 时回退 options[].is_correct
    # (F16/C01 兼容)。对齐并行 commit 289881c83 的 drift 收敛方向。
    answer = practice.get("answer")
    options = []
    for o in practice.get("options") or []:
        is_correct = (o.get("id") == answer) if answer is not None else bool(o.get("is_correct"))
        correct = "true" if is_correct else "false"
        options.append(
            f'<button class="option" type="button" data-correct="{correct}" '
            f'data-feedback="{esc(o.get("feedback"))}" aria-pressed="false">'
            f'<b>{esc(o.get("id"))}.</b>{esc(o.get("text"))}</button>'
        )
    return "".join(options)


def client_payload(schema: dict[str, Any]) -> str:
    """传给 JS 的最小载荷: 只含交互需要的非敏感字段(review_item_id 是 contrast_items[].id)。"""
    practice = schema.get("practice") or {}
    return trusted_json_for_script(
        {"practice": {"review_item_id": practice.get("review_item_id")}}
    )


def render(schema: dict[str, Any], timing: dict[str, Any] | None = None) -> str:
    validate(schema)
    title = esc(schema.get("title"))
    student_goal = esc(schema.get("student_goal"))
    why_html = schema.get("why_lose_points_html") or ""
    warm = schema.get("warm_correction_html") or esc(schema.get("warm_correction"))
    memory_hook = esc(schema.get("memory_hook"))
    scenario = schema.get("scenario") or {}
    authority = schema.get("authority") or {}
    practice = schema.get("practice") or {}

    # 学生端只看 student_boundary;内部口径(source_boundary)只进 HTML 注释(净化 "--")
    student_boundary = esc(
        authority.get("student_boundary") or "这是教研讲解,不是官方阅卷;具体以教材、规范和考试大纲为准。"
    )
    source_boundary_comment = str(authority.get("source_boundary") or "").replace("--", "—")
    judging_comment = str(authority.get("judging_authority_label") or "").replace("--", "—")
    data = client_payload(schema)

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
    <span class="teacher-tag">先看懂对照,再练一题</span>
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
<style>{_CSS}</style>
</head>
<body>
<!--
created_by: deterministic render_contrast_card.py (luban diagram micro-lesson · contrast prototype)
schema_version: {SCHEMA_VERSION}
template_type: {esc(schema.get("template_type"))}
judging_authority: {judging_comment}
source_boundary: {source_boundary_comment}
notes: 左右正误对照(OSHA do/don't);绿对红错;确定性 SVG 示意非规范详图;非官方阅卷;采分点为候选。
-->
<main class="page">
  <div class="topline">
    <div class="mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 18h16"></path><path d="M7 18V8l5-3 5 3v10"></path><path d="M9 18v-6h6v6"></path>
      </svg>
    </div>
    <span>鲁班图解微课 · 看对照 + 看穿丢分点 + 练一题</span>
  </div>
  <h1>{title}</h1>
  <p class="subtitle">{student_goal}</p>
  <nav class="quicknav" aria-label="快速跳转">
    <a class="qn" href="#rows">① 看对照</a>
    <a class="qn" href="#errors">② 错因自查</a>
    <a class="qn" href="#practice">③ 复测一题</a>
  </nav>
  {narr_player}
  <div class="whycard" data-anchor="why">
    <h2>为什么这个点容易丢分</h2>
    <p>{why_html}</p>
  </div>

  <section class="rows" id="rows" aria-label="对错做法对照">
    {contrast_rows(schema)}
  </section>
  <div class="feedback correct" id="revealDone" style="display:none">✅ 两组都看完了——现在去下面练一题,把它变成你自己的。</div>

  <section class="section" aria-label="候选采分点">
    <div class="bar" data-anchor="scoring">
      <h2>候选采分点 · 写到才稳</h2>
      <p class="hint">教研估分的关键得分表达,非官方阅卷。</p>
      <div class="score-grid">{score_cards(schema)}</div>
    </div>
  </section>

  <section class="section" id="errors" aria-label="错因自查">
    <div class="bar">
      <h2>常见失分写法 · 点一个看怎么补</h2>
      <p class="hint">点你常犯的错,我带你跳到对照里漏掉的那一组。</p>
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
    <div class="nonofficial">非官方阅卷 · 图为教学示意 · 采分点为教研候选 · 具体以教材 / 规范为准</div>
  </div>
</main>
<script type="application/json" id="cardData">{data}</script>
<script>{_JS}</script>
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
    # 预存旁白(do-once): 若存在同名 .narration.timing.json 则接上有声旁白
    timing_path = schema_path.with_name(f"{schema_path.stem}.narration.timing.json")
    timing = json.loads(timing_path.read_text(encoding="utf-8")) if timing_path.exists() else None
    html_out = render(schema, timing)
    out_path.write_text(html_out, encoding="utf-8")
    print(f"rendered: {schema_path} -> {out_path}")
    print(
        f"  contrast_items={len(schema.get('contrast_items') or [])} "
        f"scoring_points={len(schema.get('scoring_points') or [])} "
        f"errors={len(schema.get('common_errors') or [])} "
        f"practice={'yes' if schema.get('practice') else 'no'} "
        f"narration={'yes(' + str(len(timing.get('segments') or [])) + '段/' + str(round(timing.get('totalSec') or 0)) + 's)' if timing else 'no'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
