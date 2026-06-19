#!/usr/bin/env python3
"""教学动画(先讲后问)渲染器 —— SVG 可停可交互。

输入: <card>.lesson.json + 同名 .lesson.timing.json(由 build_lesson_narration.mjs 产出)。
输出: <card>.lesson.view.html
  · 上半:基坑剖面 SVG 舞台,按旁白时间轴推进 state(挖深→3m线亮→5m线亮→结论),
    考点采分词在结论时贴边高亮。
  · 播放条:▶/⏸ + 重播 + 进度(标出"讲解↔答疑"分界) + 5 个分镜点(点步跳读)。
  · 讲完后:模拟学生答疑(聊天气泡,学生左/老师右),随音频高亮。
  · 页脚常驻 boundary。

student-safe: 只渲染旁白文本 + 采分词(keywords);不渲染 scoring_point id / source_ref / verdict 等内部词。
旁白事实已由 build 阶段防漂移闸 anchor 回卡真实字段。
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

# ---- 基坑剖面几何(viewBox 0 0 360 360,1m = 46px,地面 y=56)----
GROUND_Y = 56
SCALE = 46
Y3 = GROUND_Y + 3 * SCALE   # 194
Y5 = GROUND_Y + 5 * SCALE   # 286
Y55 = GROUND_Y + 5.5 * SCALE  # 309
PIT_X, PIT_W = 108, 144
PIT_H = Y55 - GROUND_Y
RULER_X = 64

STATE_ORDER = ["intro", "dig", "gate3", "gate5", "conclude"]
STATE_LABEL = {"intro": "引入", "dig": "挖深", "gate3": "3米", "gate5": "5米", "conclude": "结论"}


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""))


def js_json(obj: object) -> str:
    return (
        json.dumps(obj, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


_CSS = """
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;
  background:#0f1722;color:#eef3f8;-webkit-text-size-adjust:100%}
.wrap{max-width:560px;margin:0 auto;min-height:100vh;display:flex;flex-direction:column;padding:16px 14px 132px}
.kicker{font-size:12px;letter-spacing:.12em;color:#ffd27f;font-weight:700;margin:0 0 6px}
h1{font-size:20px;line-height:1.35;margin:0 0 6px;font-weight:800}
.subtitle{font-size:13px;color:#9fb0c2;margin:0 0 12px}
.stagebox{background:#13202e;border:1px solid #223247;border-radius:18px;padding:12px 10px 6px;margin-bottom:12px}
svg{width:100%;height:auto;display:block}
.ground{stroke:#8b7a59;stroke-width:2.5}
.earth{fill:#cdb892}.sky{fill:#1a2940}
.pit-fill{fill:#e9f1fb;transform:scaleY(0);transform-origin:center top;transition:transform 1s cubic-bezier(.3,.7,.3,1)}
.reached-dig .pit-fill{transform:scaleY(1)}
.pit-out{fill:none;stroke:#9bb0c8;stroke-width:2;opacity:0;transition:opacity .5s}
.reached-dig .pit-out{opacity:1}
.ruler{stroke:#6c7d92;stroke-width:1.5}
.tick{stroke:#6c7d92;stroke-width:1.5}
.ticklbl{fill:#9fb0c2;font-size:11px}
.lbl55{fill:#7fc7ff;font-weight:700}
.mark{opacity:0;transition:opacity .5s}
.reached-dig .mark{opacity:1}
.markdot{fill:#2f6df0}.marktxt{fill:#cfe0f0;font-size:11px;font-weight:700}
.gline{stroke-dasharray:6 5;stroke-width:2;opacity:0;transition:opacity .6s}
.glbl{font-size:12px;font-weight:700;opacity:0;transition:opacity .6s}
.line3m{stroke:#1aa06d}.lbl3m{fill:#3fd39a}
.line5m{stroke:#e08a1e}.lbl5m{fill:#ffc06b}
.reached-gate3 .line3m,.reached-gate3 .lbl3m{opacity:1}
.reached-gate5 .line5m,.reached-gate5 .lbl5m{opacity:1}
.chk{font-size:11px;font-weight:800;opacity:0;transition:opacity .5s}
.chk-danger{fill:#3fd39a}.chk-scale{fill:#ffc06b}
.reached-gate3 .chk-danger{opacity:1}.reached-gate5 .chk-scale{opacity:1}
.banner{margin:10px 4px 2px;background:#16321f;border:1px solid #1f7a4d;border-radius:12px;
  padding:11px 13px;color:#bff0d4;font-size:14px;font-weight:700;line-height:1.5;
  opacity:0;transform:translateY(6px);transition:opacity .5s,transform .5s}
.reached-conclude .banner{opacity:1;transform:none}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin:9px 4px 4px;opacity:0;transition:opacity .5s}
.reached-conclude .chips{opacity:1}
.chips .lbl{width:100%;font-size:11.5px;color:#9fb0c2;margin-bottom:2px}
.chip{background:#1d2b3d;border:1px solid #4a3a1e;border-radius:999px;padding:5px 11px;font-size:12.5px;color:#ffd27f;font-weight:700}
.caption{min-height:58px;background:#18222f;border-radius:12px;padding:10px 13px;margin-bottom:6px;
  font-size:14.5px;line-height:1.55;color:#e7eef6;display:flex;gap:9px;align-items:flex-start}
.caption .who{flex:0 0 auto;font-size:11px;color:#ffd27f;font-weight:800;margin-top:2px}
.caption.hide{display:none}
.qa{margin-top:6px;display:none;flex-direction:column;gap:12px}
.qa.show{display:flex}
.qa .qlbl{font-size:12px;letter-spacing:.1em;color:#7fc7ff;font-weight:700;margin:4px 2px 0}
.row{display:flex;gap:9px;max-width:92%}
.row.s{align-self:flex-start}.row.t{align-self:flex-end;flex-direction:row-reverse}
.av{width:28px;height:28px;border-radius:50%;flex:0 0 28px;display:grid;place-items:center;font-size:11px;font-weight:800;color:#0f1722;margin-top:2px}
.av.s{background:#7fc7ff}.av.t{background:#ffd27f}
.bubble{background:#1b2536;border-radius:15px;padding:10px 13px;font-size:14px;line-height:1.55;border:1.5px solid transparent;transition:border-color .2s,background .2s}
.row.t .bubble{background:#243247}
.bubble.on{border-color:#7fc7ff;background:#22344b}
.row.t .bubble.on{border-color:#ffd27f}
.player{position:fixed;left:0;right:0;bottom:0;background:rgba(15,23,34,.96);backdrop-filter:blur(10px);
  border-top:1px solid #233148;padding:10px 14px 16px}
.player .inner{max-width:560px;margin:0 auto}
.prow{display:flex;align-items:center;gap:12px}
.play{width:48px;height:48px;border-radius:50%;border:none;flex:0 0 48px;cursor:pointer;background:#ffd27f;color:#0f1722;font-size:20px;display:grid;place-items:center}
.play:active{transform:scale(.94)}
.replay{width:38px;height:38px;border-radius:50%;border:1px solid #3a4a60;background:#1a2533;color:#cfe0f0;font-size:16px;cursor:pointer;flex:0 0 38px}
.pcol{flex:1;min-width:0}
.ptime{font-size:11.5px;color:#9fb0c2;display:flex;justify-content:space-between;margin-bottom:5px}
.bar{height:7px;border-radius:99px;background:#26344a;cursor:pointer;position:relative;overflow:hidden}
.fill{position:absolute;left:0;top:0;bottom:0;width:0;background:linear-gradient(90deg,#ffd27f,#ffe6b8);border-radius:99px}
.divider{position:absolute;top:-2px;bottom:-2px;width:2px;background:#7fc7ff;opacity:.7}
.dots{display:flex;gap:6px;margin-top:9px}
.dot{flex:1;text-align:center;font-size:11px;color:#8aa0b6;background:#1a2533;border:1px solid #2b3b50;border-radius:8px;padding:5px 2px;cursor:pointer}
.dot.on{color:#0f1722;background:#ffd27f;border-color:#ffd27f;font-weight:700}
.boundary{margin-top:20px;font-size:11.5px;line-height:1.6;color:#7e8da0;background:#141d29;border:1px solid #1f2a3a;border-radius:12px;padding:11px 13px}
.boundary b{color:#9fb0c2}
"""


def _svg() -> str:
    return f"""<svg viewBox="0 0 360 360" role="img" aria-label="基坑剖面教学动画">
  <g data-visual-node-id="stage.intro"></g>
  <rect class="sky" x="0" y="0" width="360" height="{GROUND_Y}"/>
  <rect class="earth" x="0" y="{GROUND_Y}" width="360" height="{360 - GROUND_Y}"/>
  <line class="ground" x1="0" y1="{GROUND_Y}" x2="360" y2="{GROUND_Y}"/>
  <!-- 基坑 -->
  <g data-visual-node-id="stage.dig">
    <rect class="pit-fill" x="{PIT_X}" y="{GROUND_Y}" width="{PIT_W}" height="{PIT_H}"/>
    <path class="pit-out" d="M{PIT_X} {GROUND_Y} L{PIT_X} {Y55} L{PIT_X+PIT_W} {Y55} L{PIT_X+PIT_W} {GROUND_Y}"/>
  </g>
  <!-- 深度标尺 -->
  <line class="ruler" x1="{RULER_X}" y1="{GROUND_Y}" x2="{RULER_X}" y2="{Y55}"/>
  <line class="tick" x1="{RULER_X-5}" y1="{GROUND_Y}" x2="{RULER_X+5}" y2="{GROUND_Y}"/>
  <text class="ticklbl" x="{RULER_X-9}" y="{GROUND_Y+4}" text-anchor="end">0</text>
  <line class="tick" x1="{RULER_X-5}" y1="{Y3}" x2="{RULER_X+5}" y2="{Y3}"/>
  <text class="ticklbl" x="{RULER_X-9}" y="{Y3+4}" text-anchor="end">3m</text>
  <line class="tick" x1="{RULER_X-5}" y1="{Y5}" x2="{RULER_X+5}" y2="{Y5}"/>
  <text class="ticklbl" x="{RULER_X-9}" y="{Y5+4}" text-anchor="end">5m</text>
  <text class="ticklbl lbl55" x="{RULER_X-9}" y="{Y55+4}" text-anchor="end">5.5m</text>
  <!-- 阈值线 3m -->
  <g data-visual-node-id="criterion.danger">
    <line class="gline line3m" data-visual-node-id="threshold.3m" x1="{RULER_X}" y1="{Y3}" x2="320" y2="{Y3}"/>
    <text class="glbl lbl3m" x="256" y="{Y3-6}">≥3m 危大</text>
    <text class="glbl lbl3m" data-visual-node-id="action.special_plan" x="256" y="{Y3+13}" style="font-size:10.5px">编专项方案</text>
    <text class="chk chk-danger" x="{PIT_X+PIT_W//2}" y="{Y3-7}" text-anchor="middle">✓ 过第一道闸</text>
  </g>
  <!-- 阈值线 5m -->
  <g data-visual-node-id="criterion.overscale">
    <line class="gline line5m" data-visual-node-id="threshold.5m" x1="{RULER_X}" y1="{Y5}" x2="320" y2="{Y5}"/>
    <text class="glbl lbl5m" x="256" y="{Y5-6}">≥5m 超规模</text>
    <text class="glbl lbl5m" data-visual-node-id="action.expert_argumentation" x="256" y="{Y5+13}" style="font-size:10.5px">还要专家论证</text>
    <text class="chk chk-scale" x="{PIT_X+PIT_W//2}" y="{Y5-7}" text-anchor="middle">✓ 过第二道闸</text>
  </g>
  <!-- 本题点 5.5m -->
  <g class="mark" data-visual-node-id="pit.depth_5_5">
    <circle class="markdot" cx="{PIT_X+PIT_W//2}" cy="{Y55}" r="7"/>
    <text class="marktxt" x="{PIT_X+PIT_W//2}" y="{Y55+22}" text-anchor="middle">本题 5.5m</text>
  </g>
</svg>"""


def stage_spec(lesson: dict):
    """舞台外置:lesson 自带 stage(svg + states + 专用 css + 结论 banner)就用它,
    否则回退 J01 基坑(零回归)。返回 (svg, state_order, state_label, extra_css, banner)。
    这一步让讲懂幕引擎从'J01 专用'变'原型通用'——工序类/构造类各带自己的舞台。"""
    st = lesson.get("stage")
    if st and st.get("svg"):
        states = st.get("states", [])
        order = [s["id"] for s in states]
        label = {s["id"]: s.get("label", s["id"]) for s in states}
        return st["svg"], order, label, st.get("css", ""), st.get("banner", "")
    return _svg(), STATE_ORDER, STATE_LABEL, "", "两道闸全过 → 这个专项施工方案应当组织专家论证。"


def render(lesson_path: Path) -> str:
    lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
    timing_path = lesson_path.with_suffix(".timing.json")
    timing = json.loads(timing_path.read_text(encoding="utf-8")) if timing_path.exists() else None

    # 采分词 chips:从源卡 scoring_points keywords 取(student-safe:只取词,不取 id/source_ref)
    card_path = lesson_path.parent / lesson.get("derived_from", "")
    chips: list[str] = []
    if card_path.exists():
        card = json.loads(card_path.read_text(encoding="utf-8"))
        seen: set[str] = set()
        for sp in card.get("scoring_points", []):
            for kw in sp.get("keywords", []):
                if kw not in seen:
                    seen.add(kw)
                    chips.append(kw)
    chips_html = "".join(f'<span class="chip">{esc(k)}</span>' for k in chips)

    sp = lesson["speakers"]
    # 答疑气泡
    qa_rows = []
    for i, pair in enumerate(lesson.get("qa", [])):
        q, a = pair["q"], pair["a"]
        qn, an = sp[q["speaker"]]["name"], sp[a["speaker"]]["name"]
        qs, as_ = q["speaker"].lower(), a["speaker"].lower()
        qa_rows.append(
            f'<div class="row {qs}" data-qi="{i}" data-role="q"><div class="av {qs}">{esc(qn[0])}</div>'
            f'<div class="bubble">{esc(q["text"])}</div></div>'
            f'<div class="row {as_}" data-qi="{i}" data-role="a"><div class="av {as_}">{esc(an[0])}</div>'
            f'<div class="bubble">{esc(a["text"])}</div></div>'
        )
    qa_html = "\n".join(qa_rows)

    seg_payload = []
    for s in (timing["segments"] if timing else []):
        seg_payload.append({
            "idx": s["idx"], "kind": s["kind"], "state": s["state"],
            "qaIndex": s.get("qaIndex"), "speaker": s["speaker"],
            "text": s["text"], "startSec": s["startSec"], "durSec": s["durSec"],
        })
    teach_dots = [
        {"state": s["state"], "label": STATE_LABEL.get(s["state"], s["state"]), "startSec": s["startSec"]}
        for s in (timing["segments"] if timing else []) if s["kind"] == "teach"
    ]
    payload = {
        "totalSec": timing["totalSec"] if timing else 0,
        "teachEndSec": timing.get("teachEndSec", 0) if timing else 0,
        "segments": seg_payload,
        "teachDots": teach_dots,
        "teacherName": sp["T"]["name"],
    }
    audio_src = timing["audio"] if timing else ""
    dots_html = "".join(
        f'<div class="dot" data-state="{esc(d["state"])}" data-t="{d["startSec"]}">{esc(d["label"])}</div>'
        for d in teach_dots
    )
    no_audio = "" if timing else '<p class="ptime" style="justify-content:center">(音频未生成 · 先看动画/讲稿)</p>'

    return f"""<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(lesson["title"])}</title><style>{_CSS}</style></head><body>
<div class="wrap">
  <p class="kicker">图解微课 · 老师带你看懂</p>
  <h1>{esc(lesson["title"])}</h1>
  <p class="subtitle">{esc(lesson.get("subtitle", ""))}</p>
  <div class="stagebox">
    <div class="stage" id="stage">
      {_svg()}
      <div class="banner">两道闸全过 → 这个专项施工方案应当组织专家论证。</div>
      <div class="chips"><span class="lbl">写到这几组采分词就稳:</span>{chips_html}</div>
    </div>
  </div>
  <div class="caption" id="caption"><span class="who">{esc(sp['T']['name'])}</span><span id="captxt">点下面 ▶,老师开讲。</span></div>
  <div class="qa" id="qa"><div class="qlbl">讲完了 · 同学还有疑问 👇</div>{qa_html}</div>
  <div class="boundary"><b>说明:</b>{esc(lesson.get("boundary",""))}<br>{esc(lesson.get("authority_label",""))}</div>
</div>
<div class="player">
  <div class="inner">
    {no_audio}
    <div class="prow">
      <button class="play" id="play" aria-label="播放">▶</button>
      <button class="replay" id="replay" aria-label="重播">↺</button>
      <div class="pcol">
        <div class="ptime"><span id="cur">0:00</span><span id="tot">0:00</span></div>
        <div class="bar" id="bar"><div class="fill" id="fill"></div><div class="divider" id="divider"></div></div>
      </div>
    </div>
    <div class="dots" id="dots">{dots_html}</div>
  </div>
</div>
<audio id="au" preload="metadata"{' src="' + esc(audio_src) + '"' if audio_src else ''}></audio>
<script>
const DATA={js_json(payload)};
const ORDER={js_json(STATE_ORDER)};
const au=document.getElementById('au'),play=document.getElementById('play'),replay=document.getElementById('replay');
const fill=document.getElementById('fill'),bar=document.getElementById('bar'),divider=document.getElementById('divider');
const cur=document.getElementById('cur'),tot=document.getElementById('tot');
const stage=document.getElementById('stage'),caption=document.getElementById('caption'),captxt=document.getElementById('captxt');
const qa=document.getElementById('qa'),dots=[...document.querySelectorAll('.dot')];
const fmt=s=>{{s=Math.max(0,s|0);return (s/60|0)+':'+String(s%60).padStart(2,'0');}};
tot.textContent=fmt(DATA.totalSec);
if(DATA.totalSec)divider.style.left=(DATA.teachEndSec/DATA.totalSec*100)+'%';

let curState=null;
function setStage(state){{
  if(state===curState)return;curState=state;
  const i=ORDER.indexOf(state);
  stage.className='stage '+ORDER.slice(0,i+1).map(s=>'reached-'+s).join(' ');
  dots.forEach(d=>d.classList.toggle('on',d.dataset.state===state));
}}
let qaShown=false;
function revealQA(){{if(!qaShown){{qaShown=true;qa.classList.add('show');}}}}
function setQAActive(qi,role){{
  document.querySelectorAll('.qa .bubble').forEach(b=>b.classList.remove('on'));
  if(qi==null)return;
  const row=document.querySelector('.row[data-qi="'+qi+'"][data-role="'+role+'"]');
  if(row){{row.querySelector('.bubble').classList.add('on');row.scrollIntoView({{behavior:'smooth',block:'center'}});}}
}}
function segAt(t){{let r=null;for(const s of DATA.segments){{if(t>=s.startSec-0.05)r=s;else break;}}return r;}}
au.addEventListener('timeupdate',()=>{{
  const t=au.currentTime;
  fill.style.width=(t/(DATA.totalSec||au.duration||1)*100)+'%';
  cur.textContent=fmt(t);
  const s=segAt(t);if(!s)return;
  setStage(s.state);
  if(s.kind==='teach'){{caption.classList.remove('hide');captxt.textContent=s.text;setQAActive(null);}}
  else{{caption.classList.add('hide');revealQA();setQAActive(s.qaIndex,s.kind);}}
  if(t>=DATA.teachEndSec-0.2)revealQA();
}});
au.addEventListener('ended',()=>{{play.textContent='▶';}});
play.addEventListener('click',()=>{{
  if(au.paused){{au.play().then(()=>play.textContent='⏸').catch(()=>{{captxt.textContent='点一下屏幕再点 ▶ 试试';}});}}
  else{{au.pause();play.textContent='▶';}}
}});
replay.addEventListener('click',()=>{{au.currentTime=0;qaShown=false;qa.classList.remove('show');au.play().then(()=>play.textContent='⏸').catch(()=>{{}});}});
bar.addEventListener('click',e=>{{const r=bar.getBoundingClientRect();au.currentTime=(e.clientX-r.left)/r.width*(DATA.totalSec||au.duration||0);}});
dots.forEach(d=>d.addEventListener('click',()=>{{au.currentTime=parseFloat(d.dataset.t)||0;au.play().then(()=>play.textContent='⏸').catch(()=>{{}});}}));
setStage('intro');
</script>
</body></html>"""


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: render_teaching_animation.py <card.lesson.json>", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    out = src.with_suffix(".view.html")
    out.write_text(render(src), encoding="utf-8")
    print(f"✅ {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
