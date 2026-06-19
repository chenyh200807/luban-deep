#!/usr/bin/env python3
"""双人对话(NotebookLM 式)播客视图渲染器。

输入: <card>.dialogue.json + 同名 .dialogue.timing.json(由 build_dialogue_narration.mjs 产出)。
输出: <card>.dialogue.view.html —— 手机优先的播客式聊天视图:
  顶部标题 + 主持人 chip,中间对话气泡(学员左/老师右),底部常驻播放条。
  播放时按 timing 高亮当前气泡 + 自动滚动;点气泡跳读;点进度条 seek。

student-safe: 只渲染 speaker 名 + 对话文本;anchor 是内部 grounding,绝不进学生端。
旁白事实已由 build 阶段防漂移闸 anchor 回 J01 卡真实字段。
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path


def esc(s: object) -> str:
    return html.escape(str(s if s is not None else ""))


def js_json(obj: object) -> str:
    # 安全内联进 <script>:转义 </ 和 unicode 行分隔符
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
.wrap{max-width:560px;margin:0 auto;min-height:100vh;display:flex;flex-direction:column;
  padding:18px 16px 124px}
.head{padding:6px 2px 14px}
.kicker{font-size:12px;letter-spacing:.12em;color:#7fc7ff;font-weight:700;margin:0 0 6px}
h1{font-size:21px;line-height:1.35;margin:0 0 8px;font-weight:800}
.subtitle{font-size:13px;color:#9fb0c2;margin:0 0 14px}
.casters{display:flex;gap:10px;margin:0 0 4px}
.caster{display:flex;align-items:center;gap:8px;background:#18202d;border-radius:999px;
  padding:6px 12px 6px 6px;font-size:12.5px;color:#cfe0f0}
.dot{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:800;color:#0f1722}
.dot.a{background:#7fc7ff}.dot.b{background:#ffd27f}
.thread{display:flex;flex-direction:column;gap:14px;margin-top:18px}
.row{display:flex;gap:9px;max-width:90%}
.row.a{align-self:flex-start}
.row.b{align-self:flex-end;flex-direction:row-reverse}
.av{width:30px;height:30px;border-radius:50%;flex:0 0 30px;display:grid;place-items:center;
  font-size:12px;font-weight:800;color:#0f1722;margin-top:2px}
.av.a{background:#7fc7ff}.av.b{background:#ffd27f}
.bubble{background:#1b2536;border-radius:16px;padding:11px 14px;font-size:15px;line-height:1.6;
  color:#e7eef6;cursor:pointer;transition:background .2s,box-shadow .2s,transform .15s;border:1.5px solid transparent}
.row.b .bubble{background:#243247}
.who{font-size:11.5px;color:#8aa0b6;margin:0 0 3px;font-weight:700}
.bubble.on{border-color:#7fc7ff;background:#22344b;box-shadow:0 6px 20px rgba(127,199,255,.18)}
.row.b .bubble.on{border-color:#ffd27f;box-shadow:0 6px 20px rgba(255,210,127,.16)}
.tag{display:inline-block;margin-left:6px;font-size:10px;color:#7fc7ff;opacity:.0;transition:opacity .2s}
.bubble.on .tag{opacity:.7}
.player{position:fixed;left:0;right:0;bottom:0;background:rgba(15,23,34,.96);
  backdrop-filter:blur(10px);border-top:1px solid #233148;padding:12px 16px 18px}
.player .inner{max-width:560px;margin:0 auto;display:flex;align-items:center;gap:13px}
.play{width:52px;height:52px;border-radius:50%;border:none;flex:0 0 52px;cursor:pointer;
  background:#7fc7ff;color:#0f1722;font-size:22px;display:grid;place-items:center;
  box-shadow:0 6px 18px rgba(127,199,255,.35)}
.play:active{transform:scale(.94)}
.pcol{flex:1;min-width:0}
.plabel{font-size:12px;color:#9fb0c2;margin:0 0 6px;display:flex;justify-content:space-between}
.bar{height:6px;border-radius:99px;background:#26344a;cursor:pointer;position:relative;overflow:hidden}
.fill{position:absolute;left:0;top:0;bottom:0;width:0;background:linear-gradient(90deg,#7fc7ff,#a6dbff);border-radius:99px}
.boundary{margin-top:22px;font-size:11.5px;line-height:1.6;color:#7e8da0;
  background:#141d29;border:1px solid #1f2a3a;border-radius:12px;padding:11px 13px}
.boundary b{color:#9fb0c2}
"""


def render(dialogue_path: Path) -> str:
    dlg = json.loads(dialogue_path.read_text(encoding="utf-8"))
    timing_path = dialogue_path.with_suffix(".timing.json")
    timing = json.loads(timing_path.read_text(encoding="utf-8")) if timing_path.exists() else None

    speakers = dlg["speakers"]
    a_name = speakers["A"]["name"]
    b_name = speakers["B"]["name"]

    casters = (
        f'<div class="caster"><span class="dot a">{esc(a_name[0])}</span>'
        f'{esc(a_name)}·{esc(speakers["A"]["role"])}</div>'
        f'<div class="caster"><span class="dot b">{esc(b_name[0])}</span>'
        f'{esc(b_name)}·{esc(speakers["B"]["role"])}</div>'
    )

    rows = []
    for i, t in enumerate(dlg["turns"]):
        spk = t["speaker"].lower()
        name = speakers[t["speaker"]]["name"]
        rows.append(
            f'<div class="row {spk}" data-i="{i}">'
            f'<div class="av {spk}">{esc(name[0])}</div>'
            f'<div class="bubble" data-i="{i}">'
            f'<div class="who">{esc(name)}</div>{esc(t["text"])}</div>'
            f"</div>"
        )
    thread = "\n".join(rows)

    audio_src = timing["audio"] if timing else ""
    payload = {
        "totalSec": timing["totalSec"] if timing else 0,
        "segments": [{"idx": s["idx"], "startSec": s["startSec"], "durSec": s["durSec"]} for s in timing["segments"]]
        if timing
        else [],
    }
    no_audio_note = "" if timing else '<p class="plabel" style="justify-content:center">(音频未生成 · 先看对话文字)</p>'

    return f"""<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(dlg["title"])}</title><style>{_CSS}</style></head><body>
<div class="wrap">
  <div class="head">
    <p class="kicker">图解微课 · 双人聊</p>
    <h1>{esc(dlg["title"])}</h1>
    <p class="subtitle">{esc(dlg.get("subtitle", ""))}</p>
    <div class="casters">{casters}</div>
  </div>
  <div class="thread" id="thread">{thread}</div>
  <div class="boundary"><b>说明:</b>{esc(dlg.get("boundary", ""))}<br>{esc(dlg.get("authority_label", ""))}</div>
</div>
<div class="player">
  <div class="inner">
    <button class="play" id="play" aria-label="播放">▶</button>
    <div class="pcol">
      {no_audio_note}
      <p class="plabel"><span id="cur">0:00</span><span id="tot">0:00</span></p>
      <div class="bar" id="bar"><div class="fill" id="fill"></div></div>
    </div>
  </div>
</div>
<audio id="au" preload="metadata"{' src="' + esc(audio_src) + '"' if audio_src else ''}></audio>
<script>
const DATA={js_json(payload)};
const au=document.getElementById('au'),play=document.getElementById('play');
const fill=document.getElementById('fill'),bar=document.getElementById('bar');
const cur=document.getElementById('cur'),tot=document.getElementById('tot');
const bubbles=[...document.querySelectorAll('.bubble')];
const fmt=s=>{{s=Math.max(0,s|0);return (s/60|0)+':'+String(s%60).padStart(2,'0');}};
tot.textContent=fmt(DATA.totalSec);
let active=-1;
function segAt(t){{let r=-1;for(const s of DATA.segments){{if(t>=s.startSec-0.05)r=s.idx;else break;}}return r;}}
function highlight(i){{if(i===active)return;active=i;
  bubbles.forEach((b,k)=>b.classList.toggle('on',k===i));
  const el=document.querySelector('.row[data-i="'+i+'"]');
  if(el)el.scrollIntoView({{behavior:'smooth',block:'center'}});}}
au.addEventListener('timeupdate',()=>{{
  fill.style.width=(au.currentTime/(DATA.totalSec||au.duration||1)*100)+'%';
  cur.textContent=fmt(au.currentTime);
  highlight(segAt(au.currentTime));
}});
au.addEventListener('ended',()=>{{play.textContent='▶';}});
play.addEventListener('click',()=>{{
  if(au.paused){{au.play().then(()=>play.textContent='⏸').catch(()=>{{
    cur.textContent='点屏幕任意处再点播放';}});}}
  else{{au.pause();play.textContent='▶';}}
}});
bar.addEventListener('click',e=>{{const r=bar.getBoundingClientRect();
  au.currentTime=(e.clientX-r.left)/r.width*(DATA.totalSec||au.duration||0);}});
bubbles.forEach((b,i)=>b.addEventListener('click',()=>{{
  const s=DATA.segments.find(x=>x.idx===i);if(!s)return;
  au.currentTime=s.startSec;highlight(i);
  au.play().then(()=>play.textContent='⏸').catch(()=>{{}});
}}));
</script>
</body></html>"""


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: render_dialogue.py <card.dialogue.json>", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    out = src.with_suffix(".view.html")
    out.write_text(render(src), encoding="utf-8")
    print(f"✅ {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
