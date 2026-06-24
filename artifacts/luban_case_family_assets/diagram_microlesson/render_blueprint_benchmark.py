#!/usr/bin/env python3
"""视觉对标 spike 渲染器(luban_diagram_microlesson.benchmark_spike.v0)。

目的:把 NotebookLM PPTX(image7 那种"蓝图密度 + 阈值告警框")的视觉信息密度,
用我们的【确定性内联 SVG】复刻出来,并做出关键差异化——
每个阈值数字屏上都带【规范出处】,原始 source_ref id 只进 HTML 注释。

边界(与红线一致):
- 不判分、不生成知识、不推断官方答案;数字全部来自输入 JSON 的候选阈值。
- candidate 诚实标注,不冒充签发(official_score_allowed 必须为 false)。
- 学生端 fail-closed:source_ref.id / content_sha256 / schema / card_id / candidate
  等内部词绝不上屏;只有规范出处文字(cite)和阈值标签可见。
- 全内联:无外链 / 无 CDN / 无 web 字体 / 无音频 / 无前端 LLM。

这是 spike,不是生产 template_type;不进 SCHEMA.md 注册表,不冒充 case_family。
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "luban_diagram_microlesson.benchmark_spike.v0"
CANDIDATE_STATUSES = {"candidate_teaching_prototype", "candidate", "draft"}


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def validate(schema: dict[str, Any]) -> None:
    if schema.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {schema.get('schema_version')!r}")
    auth = schema.get("authority") or {}
    if auth.get("status") not in CANDIDATE_STATUSES:
        raise ValueError(f"benchmark spike must be candidate authority, got {auth.get('status')!r}")
    if auth.get("official_score_allowed") is True:
        raise ValueError("candidate spike must not set official_score_allowed=true")
    panels = schema.get("panels") or []
    if not panels:
        raise ValueError("benchmark spike requires non-empty panels")
    for p in panels:
        for t in p.get("thresholds") or []:
            sr = t.get("source_ref") or {}
            if not sr.get("cite"):
                raise ValueError(f"threshold {t.get('label')!r} 缺 source_ref.cite(对标关键:数字必须带出处)")
            if sr.get("kind") not in CANDIDATE_STATUSES:
                raise ValueError(f"threshold {t.get('label')!r} source_ref.kind 须 candidate,不冒充签发")
    if not (schema.get("rendering_contract") or {}).get("student_safe_fields"):
        raise ValueError("benchmark spike requires rendering_contract.student_safe_fields")


# ---- 蓝图 SVG(确定性绘制,尺寸/标注来自阈值数据,前端不计算判断)----

def _dim_marks(thresholds: list[dict[str, Any]], y0: float, y_per_m: float) -> str:
    """在深度/高度轴上,按阈值数值画出标记线(纯展示,不判断)。"""
    out = []
    colors = {"危大": "#f5a623", "超规模": "#ff5d5d"}
    for t in thresholds:
        v = t.get("value_m")
        if not isinstance(v, (int, float)):
            continue
        y = y0 + v * y_per_m
        c = colors.get(t.get("tier"), "#7fd4ff")
        out.append(
            f'<line x1="60" y1="{y:.1f}" x2="250" y2="{y:.1f}" stroke="{c}" '
            f'stroke-width="2" stroke-dasharray="5 4"/>'
            f'<circle cx="60" cy="{y:.1f}" r="4" fill="{c}"/>'
            f'<text x="256" y="{y + 4:.1f}" fill="{c}" font-size="13" font-weight="700">'
            f'{esc(t.get("tier"))} {esc(v)}m</text>'
        )
    return "".join(out)


def pit_section(thresholds: list[dict[str, Any]]) -> str:
    """基坑开挖剖面:地面线 + 阶梯坑壁 + 深度尺寸轴。"""
    y0, y_per_m = 70.0, 26.0
    return (
        '<svg viewBox="0 0 320 260" role="img" aria-label="基坑开挖剖面示意">'
        '<defs><pattern id="hatchP" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        '<line x1="0" y1="0" x2="0" y2="8" stroke="#1c4a63" stroke-width="1.4"/></pattern></defs>'
        # 地面 + 土体
        '<rect x="60" y="70" width="200" height="170" fill="url(#hatchP)" opacity="0.6"/>'
        '<line x1="20" y1="70" x2="300" y2="70" stroke="#bfe6ff" stroke-width="2.5"/>'
        '<text x="22" y="64" fill="#bfe6ff" font-size="12">原地面 ±0.000</text>'
        # 阶梯式基坑(白线开挖轮廓)
        '<path d="M60 70 L60 200 L120 200 L120 240 L210 240 L210 200 L260 200 L260 70" '
        'fill="#0a2230" stroke="#eaf6ff" stroke-width="2.4" stroke-linejoin="round"/>'
        '<line x1="120" y1="200" x2="210" y2="200" stroke="#5ea8c8" stroke-width="1.2" stroke-dasharray="3 3"/>'
        # 深度尺寸轴
        '<line x1="60" y1="70" x2="60" y2="240" stroke="#7fd4ff" stroke-width="1.6"/>'
        '<polygon points="60,240 56,232 64,232" fill="#7fd4ff"/>'
        '<text x="36" y="160" fill="#7fd4ff" font-size="12" transform="rotate(-90 36 160)">开挖深度 H</text>'
        f'{_dim_marks(thresholds, y0, y_per_m)}'
        '</svg>'
    )


def formwork_section(thresholds: list[dict[str, Any]]) -> str:
    """模板支撑剖面:支撑立杆塔架 + 搭设高度尺寸轴。"""
    y0, y_per_m = 60.0, 18.0
    bars = "".join(
        f'<line x1="{x}" y1="60" x2="{x}" y2="234" stroke="#eaf6ff" stroke-width="2.2"/>'
        for x in (110, 150, 190, 230)
    )
    rungs = "".join(
        f'<line x1="110" y1="{y}" x2="230" y2="{y}" stroke="#9fd4ec" stroke-width="1.4"/>'
        for y in range(80, 235, 26)
    )
    diags = "".join(
        f'<line x1="110" y1="{y}" x2="150" y2="{y - 26}" stroke="#5ea8c8" stroke-width="1" stroke-dasharray="3 3"/>'
        for y in range(106, 235, 26)
    )
    return (
        '<svg viewBox="0 0 320 260" role="img" aria-label="模板支撑剖面示意">'
        # 顶部模板梁 + 底部地面
        '<rect x="96" y="48" width="148" height="12" fill="#0a2230" stroke="#eaf6ff" stroke-width="2"/>'
        '<text x="98" y="44" fill="#bfe6ff" font-size="11">混凝土模板(待浇)</text>'
        '<line x1="80" y1="234" x2="260" y2="234" stroke="#bfe6ff" stroke-width="2.5"/>'
        '<text x="82" y="250" fill="#bfe6ff" font-size="12">楼面 ±0.000</text>'
        f'{bars}{rungs}{diags}'
        # 高度尺寸轴
        '<line x1="60" y1="60" x2="60" y2="234" stroke="#7fd4ff" stroke-width="1.6"/>'
        '<polygon points="60,60 56,68 64,68" fill="#7fd4ff"/>'
        '<text x="36" y="150" fill="#7fd4ff" font-size="12" transform="rotate(-90 36 150)">搭设高度 H</text>'
        f'{_dim_marks(thresholds, y0, y_per_m)}'
        '</svg>'
    )


_DIAGRAMS = {"pit_section": pit_section, "formwork_section": formwork_section}


def threshold_rows(thresholds: list[dict[str, Any]]) -> str:
    rows = []
    for t in thresholds:
        cls = "t-danger" if t.get("tier") == "危大" else "t-scale"
        cite = esc((t.get("source_ref") or {}).get("cite"))
        rows.append(
            f'<div class="thr {cls}">'
            f'<span class="thr-tier">{esc(t.get("tier"))}</span>'
            f'<span class="thr-val">{esc(t.get("label"))}</span>'
            f'<span class="thr-cite">依据 · {cite}</span>'
            '</div>'
        )
    return "".join(rows)


def panel_html(p: dict[str, Any]) -> str:
    diagram_fn = _DIAGRAMS.get(p.get("diagram"))
    svg = diagram_fn(p.get("thresholds") or []) if diagram_fn else ""
    return (
        f'<article class="panel" data-panel="{esc(p.get("id"))}">'
        f'<h3 class="panel-name">{esc(p.get("name"))}</h3>'
        f'<div class="panel-svg">{svg}</div>'
        f'<div class="thr-list">{threshold_rows(p.get("thresholds") or [])}</div>'
        '</article>'
    )


def source_comment(schema: dict[str, Any]) -> str:
    lines = ["raw source_ref provenance (HTML-comment only; never on student screen):"]
    for p in schema.get("panels") or []:
        for t in p.get("thresholds") or []:
            sr = t.get("source_ref") or {}
            lines.append(
                f"  {p.get('id')}.{t.get('tier')} {t.get('label')} "
                f"-> id={sr.get('id')} kind={sr.get('kind')} sha={sr.get('content_sha256')}"
            )
    return "\n".join(lines).replace("--", "—")


_CSS = r"""
:root{--bg:#0c2230;--bg2:#0e2a3a;--line:#1f4d66;--ink:#eaf6ff;--sub:#9cc6dc;
--danger:#f5a623;--scale:#ff5d5d;--accent:#7fd4ff}
*{box-sizing:border-box}
html,body{margin:0}
body{background:linear-gradient(160deg,#0b1f2c,#0e2c3d 60%,#0a2230);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
-webkit-font-smoothing:antialiased}
.bp{max-width:390px;margin:0 auto;min-height:100vh;padding:18px 16px 92px;position:relative}
.bp::before{content:"";position:absolute;inset:0;pointer-events:none;opacity:.5;
background-image:linear-gradient(rgba(127,212,255,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(127,212,255,.05) 1px,transparent 1px);
background-size:26px 26px}
.bp>*{position:relative}
.brand{display:flex;justify-content:space-between;align-items:center;font-size:11px;color:var(--sub);letter-spacing:.04em}
.brand b{color:var(--accent);font-weight:800}
.slide{display:none}.slide.active{display:block}
.kicker{display:inline-block;margin-top:14px;font-size:11px;font-weight:800;letter-spacing:.08em;
color:#06283a;background:var(--accent);border-radius:999px;padding:4px 11px}
h1.title{margin:10px 0 2px;font-size:23px;line-height:1.25;font-weight:800}
.subtitle{margin:0 0 6px;font-size:13.5px;color:var(--sub)}
.panels{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-top:14px}
.panel{background:rgba(8,28,40,.55);border:1px solid var(--line);border-radius:14px;padding:10px 9px}
.panel-name{margin:0 0 6px;font-size:13.5px;font-weight:800;color:var(--ink);text-align:center}
.panel-svg svg{width:100%;height:auto;display:block}
.thr-list{margin-top:8px;display:grid;gap:7px}
.thr{border-radius:10px;padding:7px 9px;border:1px solid var(--line);background:rgba(6,22,32,.6)}
.thr-tier{display:inline-block;font-size:11px;font-weight:800;border-radius:6px;padding:1px 7px;margin-right:6px}
.t-danger{border-left:3px solid var(--danger)} .t-danger .thr-tier{background:rgba(245,166,35,.18);color:var(--danger)}
.t-scale{border-left:3px solid var(--scale)} .t-scale .thr-tier{background:rgba(255,93,93,.16);color:var(--scale)}
.thr-val{font-size:14px;font-weight:800}
.thr-cite{display:block;margin-top:4px;font-size:10.5px;line-height:1.45;color:var(--sub)}
.alert{margin-top:16px;border-radius:14px;border:1px solid rgba(245,166,35,.5);
background:linear-gradient(180deg,rgba(245,166,35,.16),rgba(245,166,35,.06));padding:13px 14px}
.alert-h{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:800;color:var(--danger);letter-spacing:.05em}
.alert-h .ico{width:20px;height:20px;border-radius:50%;background:var(--danger);color:#06283a;display:grid;place-items:center;font-weight:900;font-size:13px}
.alert p{margin:8px 0 0;font-size:13.5px;line-height:1.6;color:var(--ink)}
.diff{margin-top:16px;border-radius:14px;border:1px dashed var(--accent);background:rgba(127,212,255,.07);padding:14px}
.diff h3{margin:0 0 8px;font-size:14px;color:var(--accent);font-weight:800}
.diff .row{display:flex;gap:10px;font-size:13px;line-height:1.6;margin-top:7px}
.diff .row .b{flex:0 0 auto;width:18px;height:18px;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:900}
.diff .ours .b{background:var(--accent);color:#06283a}
.diff .theirs .b{background:#52677a;color:#cfe2ee}
.boundary{margin-top:16px;font-size:11px;line-height:1.55;color:var(--sub);border-top:1px solid var(--line);padding-top:10px}
.nav{position:fixed;left:0;right:0;bottom:0;max-width:390px;margin:0 auto;display:flex;align-items:center;gap:10px;
padding:10px 14px;background:rgba(8,24,34,.92);backdrop-filter:blur(6px);border-top:1px solid var(--line)}
.nav button{flex:0 0 auto;min-width:88px;min-height:44px;border-radius:12px;border:1px solid var(--line);
background:#10303f;color:var(--ink);font-size:14px;font-weight:700}
.nav button.primary{background:var(--accent);color:#06283a;border-color:var(--accent)}
.nav button:disabled{opacity:.4}
.nav .mid{flex:1;text-align:center}
.nav .mid i{display:block;height:4px;border-radius:3px;background:#163a4d;margin-top:5px;overflow:hidden}
.nav .mid i b{display:block;height:100%;background:var(--accent);width:50%}
.panel.hl{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent),0 0 18px rgba(127,212,255,.35)}
.panel{transition:box-shadow .25s,border-color .25s}
.narr{margin-top:12px;background:rgba(8,28,40,.7);border:1px solid var(--line);border-radius:14px;padding:10px 12px}
.narr-btn{width:100%;min-height:44px;border-radius:11px;border:1px solid var(--accent);background:rgba(127,212,255,.12);color:var(--accent);font-size:14px;font-weight:800}
.narr-btn.playing{background:var(--accent);color:#06283a}
.narr-sub{margin-top:9px;font-size:13px;line-height:1.55;color:var(--ink);min-height:20px}
.narr-prog{display:block;height:4px;border-radius:3px;background:#163a4d;margin-top:8px;overflow:hidden}
.narr-prog b{display:block;height:100%;background:var(--accent);width:0}
"""

_JS = r"""
const slides=[...document.querySelectorAll(".slide")];
const T=slides.length;let s=0;
const $=(i)=>document.getElementById(i);
const prev=$("prevBtn"),next=$("nextBtn"),cnt=$("cnt"),bar=$("bar");
function go(n){s=Math.max(0,Math.min(T-1,n));
 slides.forEach((el,i)=>el.classList.toggle("active",i===s));
 cnt.textContent=(s+1)+" / "+T;bar.style.width=(((s+1)/T)*100)+"%";
 prev.disabled=s===0;next.textContent=s===T-1?"重新看":"下一页 →";
 document.documentElement.dataset.screen=String(s);window.scrollTo(0,0);}
prev.addEventListener("click",()=>go(s-1));
next.addEventListener("click",()=>go(s===T-1?0:s+1));
document.addEventListener("keydown",(e)=>{if(e.key==="ArrowRight")go(s+1);if(e.key==="ArrowLeft")go(s-1);});
go(0);
"""

# 旁白同步:预录音频(do-once `say` 生成,非运行时 TTS),播到哪段就翻到哪屏 + 高亮对应 panel + 字幕。
_NARR_JS = r"""
(function(){
 var tEl=document.getElementById("narrTiming"),audio=document.getElementById("narrAudio"),btn=document.getElementById("narrPlay");
 if(!tEl||!audio||!btn)return;
 var timing=JSON.parse(tEl.textContent),sub=document.getElementById("narrSub"),prog=document.getElementById("narrProg");
 function gotoAnchor(a){var el=document.querySelector('.slide[data-anchor="'+(a||"").replace(/"/g,'')+'"]');if(el)go(slides.indexOf(el));}
 function hl(id){document.querySelectorAll(".panel").forEach(function(p){p.classList.toggle("hl",!!id&&p.dataset.panel===id);});}
 var cur=null;
 audio.addEventListener("timeupdate",function(){
  var t=audio.currentTime,seg=timing.segments[0];
  for(var i=0;i<timing.segments.length;i++){if(t>=timing.segments[i].startSec)seg=timing.segments[i];}
  if(seg&&seg.id!==cur){cur=seg.id;if(sub)sub.textContent=seg.text;gotoAnchor(seg.anchor);hl(seg.highlight);}
  if(prog)prog.style.width=(timing.totalSec?Math.min(100,(t/timing.totalSec)*100):0)+"%";
 });
 function setBtn(){var p=!audio.paused;btn.classList.toggle("playing",p);
  btn.textContent=p?"⏸ 暂停讲解":(audio.currentTime>0?"▶ 继续讲解":("▶ 听老师讲("+Math.round(timing.totalSec)+" 秒)"));}
 btn.addEventListener("click",function(){if(audio.paused){var pr=audio.play();if(pr&&pr.catch)pr.catch(function(){if(sub)sub.textContent="(音频被浏览器拦了——点一下页面再点播放,或用 Safari 打开)";});}else audio.pause();});
 audio.addEventListener("play",setBtn);audio.addEventListener("pause",setBtn);
 audio.addEventListener("ended",function(){cur=null;hl("");setBtn();if(sub)sub.textContent="讲完啦——自己翻页再判一遍。";});
 setBtn();
})();
"""


def narration_block(timing: dict[str, Any]) -> tuple[str, str]:
    """返回 (player_html, audio+timing+script tags)。"""
    audio_src = esc(timing.get("audio") or "")
    total = int(round(timing.get("totalSec") or 0))
    timing_json = json.dumps(timing, ensure_ascii=False).replace("</", "<\\/")
    player = (
        '<div class="narr">'
        f'<button class="narr-btn" id="narrPlay" type="button">▶ 听老师讲({total} 秒)</button>'
        '<div class="narr-sub" id="narrSub">点上面,听老师边讲边翻页。</div>'
        '<i class="narr-prog"><b id="narrProg"></b></i>'
        '</div>'
    )
    tags = (
        f'<audio id="narrAudio" src="{audio_src}" preload="auto"></audio>'
        f'<script type="application/json" id="narrTiming">{timing_json}</script>'
        f'<script>{_NARR_JS}</script>'
    )
    return player, tags


def render(schema: dict[str, Any], timing: dict[str, Any] | None = None) -> str:
    validate(schema)
    title = esc(schema.get("title"))
    subtitle = esc(schema.get("subtitle"))
    panels_html = "".join(panel_html(p) for p in schema.get("panels") or [])
    rule_chain = esc(schema.get("rule_chain"))
    boundary = esc((schema.get("authority") or {}).get("student_boundary"))
    comment = source_comment(schema)
    narr_player, narr_tags = narration_block(timing) if timing else ("", "")

    slide1 = (
        '<section class="slide active" data-anchor="blueprint">'
        '<span class="kicker">蓝图速判</span>'
        f'<h1 class="title">{title}</h1>'
        f'<p class="subtitle">{subtitle}</p>'
        f'<div class="panels">{panels_html}</div>'
        '<div class="alert"><div class="alert-h"><span class="ico">!</span>两道闸 · 阈值告警</div>'
        f'<p>{rule_chain}</p></div>'
        '</section>'
    )
    slide2 = (
        '<section class="slide" data-anchor="diff">'
        '<span class="kicker">差在哪</span>'
        '<h1 class="title">同样好看,凭什么信我们</h1>'
        '<p class="subtitle">AI 把数字烤进图里 vs 每个数字带规范出处</p>'
        '<div class="diff">'
        '<h3>NotebookLM 那张图</h3>'
        '<div class="row theirs"><span class="b">✕</span><span>数字(≥3m / ≥5m)是 AI 生成、烤进位图,<b>无出处、不可核、可能编错</b>——一建考试错一个数就背错。</span></div>'
        '<div class="row theirs"><span class="b">✕</span><span>位图放大就糊,改一个数要重新生成整张图。</span></div>'
        '</div>'
        '<div class="diff" style="border-color:var(--accent)">'
        '<h3>我们这张卡</h3>'
        '<div class="row ours"><span class="b">✓</span><span>每个阈值都标着<b>《危大规定》出处</b>,数值来自教研锚定的规范原文,可追溯、可复核。</span></div>'
        '<div class="row ours"><span class="b">✓</span><span>矢量 SVG,放大不糊;改一个数只动数据,图自动重画。</span></div>'
        '</div>'
        f'<div class="boundary">{boundary}</div>'
        '</section>'
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · 视觉对标</title>
<style>{_CSS}</style>
</head>
<body>
<!--
created_by: deterministic render_blueprint_benchmark.py (visual benchmark spike vs NotebookLM PPTX image7)
schema_version: {SCHEMA_VERSION}
status: candidate_teaching_prototype · official_score_allowed=false · 非生产 case_family · 不判分 · 不冒充签发
{comment}
-->
<main class="bp">
  <div class="brand"><span><b>鲁班图解</b> · 视觉对标样张</span><span id="cnt">1 / 2</span></div>
  {narr_player}
  {slide1}
  {slide2}
  <div class="nav">
    <button id="prevBtn" type="button">← 上一页</button>
    <div class="mid"><span>翻页看</span><i><b id="bar"></b></i></div>
    <button class="primary" id="nextBtn" type="button">下一页 →</button>
  </div>
</main>
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
    timing_path = schema_path.with_name(f"{schema_path.stem}.narration.timing.json")
    timing = json.loads(timing_path.read_text(encoding="utf-8")) if timing_path.exists() else None
    out_path.write_text(render(schema, timing), encoding="utf-8")
    print(f"rendered (benchmark spike): {schema_path} -> {out_path}")
    print(f"  panels={len(schema.get('panels') or [])} screens=2 narration={'yes' if timing else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
