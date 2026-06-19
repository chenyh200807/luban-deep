#!/usr/bin/env python3
"""Render an independent practice page from a mother-question master JSON.

This renderer is presentation-only: it reads variants/scoring terms and renders
a self-check challenge page. It does not infer answers, scoring authority, or
learner-state conclusions.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path
from typing import Any


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def js_json(obj: object) -> str:
    return (
        json.dumps(obj, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_card(master_path: Path, master: dict[str, Any]) -> dict[str, Any]:
    lesson_ref = master.get("teaching_lesson_ref")
    if not lesson_ref:
        return {}
    lesson_path = master_path.parent / str(lesson_ref)
    if not lesson_path.exists():
        return {}
    lesson = _load_json(lesson_path)
    card_ref = lesson.get("derived_from")
    if not card_ref:
        return {}
    card_path = master_path.parent / str(card_ref)
    return _load_json(card_path) if card_path.exists() else {}


def _score_terms(card: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for sp in card.get("scoring_points", []):
        for term in sp.get("keywords", []):
            text = str(term).strip()
            if text and text not in seen:
                seen.add(text)
                out.append(text)
    return out


def _first_metric_threshold(text: str) -> float:
    values = [float(x) for x in re.findall(r"[≥>=]\s*(\d+(?:\.\d+)?)\s*m", text)]
    return values[0] if values else 0.0


def _scenario_specs(master: dict[str, Any]) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    for item in master.get("R3_scenario_templates", []):
        scenario_id = str(item.get("id", ""))
        if not scenario_id:
            continue
        danger = str(item.get("danger_threshold", ""))
        over = str(item.get("over_scale_threshold", ""))
        specs[scenario_id] = {
            "label": str(item.get("engineering") or scenario_id),
            "danger": _first_metric_threshold(danger),
            "over": _first_metric_threshold(over),
        }
    return specs


def _variant_visual(master: dict[str, Any], variant: dict[str, Any]) -> str:
    stem = str(variant.get("stem", ""))
    basis = str(variant.get("basis", ""))
    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)m", stem + " " + basis)]
    value = nums[0] if nums else 0
    scenario = _scenario_specs(master).get(str(variant.get("scenario_id", "")), {})
    obj = str(scenario.get("label") or variant.get("scenario_id") or "本工程")
    g1 = float(scenario.get("danger") or 0)
    g2 = float(scenario.get("over") or 0)
    unit = "m"
    first = value >= g1
    second = value >= g2
    c1 = "hot" if first else "soft"
    c2 = "hot" if second else "soft"
    value_label = f"{value:g}"
    return f"""<svg viewBox="0 0 390 220" role="img" aria-label="{esc(obj)}判断图">
  <rect x="18" y="18" width="354" height="184" rx="18" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/>
  <text x="42" y="50" fill="#176b7a" font-size="16" font-weight="900">{esc(obj)} · {esc(value_label)}{unit}</text>
  <g class="gate {c1}">
    <rect x="42" y="72" width="136" height="68" rx="14"/>
    <text x="110" y="99" text-anchor="middle" font-size="15" font-weight="900">第一道闸</text>
    <text x="110" y="122" text-anchor="middle" font-size="14" font-weight="900">≥{g1}{unit} 危大</text>
  </g>
  <g class="gate {c2}">
    <rect x="212" y="72" width="136" height="68" rx="14"/>
    <text x="280" y="99" text-anchor="middle" font-size="15" font-weight="900">第二道闸</text>
    <text x="280" y="122" text-anchor="middle" font-size="14" font-weight="900">≥{g2}{unit} 超规模</text>
  </g>
  <path d="M178 106 H212" stroke="#8aa0b6" stroke-width="5" stroke-linecap="round"/>
  <text x="195" y="174" text-anchor="middle" fill="#24364b" font-size="15" font-weight="900">{esc(basis)}</text>
</svg>"""


def _wrong_basis(option_text: str) -> str:
    if "非危大" in option_text:
        return "错因：第一道危大阈值没过清"
    if "无需专家论证" in option_text or "无需论证" in option_text:
        return "错因：漏看第二道超规模阈值"
    if "需专家论证" in option_text or "需要专家论证" in option_text:
        return "错因：把危大和超规模混成一档"
    return "错因：没有同时核对两道闸"


def _option_text(variant: dict[str, Any], option: dict[str, Any]) -> str:
    text = str(option.get("text", ""))
    if option.get("id") == variant.get("answer"):
        basis = str(variant.get("basis", "")).replace("、", "；")
        return f"{text}；判断依据：{basis}"
    return f"{text}；{_wrong_basis(text)}"


def _option_feedback(variant: dict[str, Any], option: dict[str, Any]) -> str:
    if option.get("id") == variant.get("answer"):
        return str(variant.get("feedback", ""))
    return _wrong_basis(str(option.get("text", "")))


def render(master_path: Path) -> str:
    master = _load_json(master_path)
    card = _load_card(master_path, master)
    terms = _score_terms(card)
    variants = master.get("variants", [])
    practice = []
    sections: list[str] = []
    for i, variant in enumerate(variants, 1):
        qid = f"q{i}"
        opts = []
        buttons = []
        for option in variant.get("options", []):
            oid = str(option.get("id", ""))
            text = _option_text(variant, option)
            opts.append({"id": oid, "text": text, "feedback": _option_feedback(variant, option)})
            buttons.append(
                f'<button type="button" class="option" data-opt="{esc(oid)}"><b>{esc(oid)}.</b> {esc(text)}</button>'
            )
        practice.append(
            {
                "id": qid,
                "answer": variant.get("answer"),
                "correct_feedback": variant.get("feedback", ""),
                "basis": variant.get("basis", ""),
                "tier": variant.get("tier_tag", ""),
                "options": opts,
            }
        )
        sections.append(
            f"""<section class="q" data-practice-id="{esc(qid)}" data-qid="{esc(qid)}">
  <div class="qtop"><span>第 {i}/{len(variants)+1} 问</span><em>{esc(variant.get('tier_tag','判断题'))}</em></div>
  <div class="diagram">{_variant_visual(master, variant)}</div>
  <h2>{esc(variant.get('stem',''))}</h2>
  <div class="options">{''.join(buttons)}</div>
  <div class="feedback" id="fb-{esc(qid)}"></div>
</section>"""
        )
    score_qid = f"q{len(variants)+1}"
    sample = "、".join(terms[:6]) if terms else "先判危大、再判超规模、最后写结论"
    sections.append(
        f"""<section class="q" data-practice-id="{esc(score_qid)}" data-qid="{esc(score_qid)}">
  <div class="qtop"><span>第 {len(variants)+1}/{len(variants)+1} 问</span><em>采分句输出</em></div>
  <div class="diagram"><svg viewBox="0 0 390 220" role="img" aria-label="采分句答题纸">
    <rect x="28" y="30" width="334" height="154" rx="18" fill="#fff" stroke="#d8e2ec" stroke-width="4"/>
    <text x="58" y="72" fill="#176b7a" font-size="17" font-weight="900">答题纸三件套</text>
    <text x="58" y="112" fill="#17202a" font-size="16" font-weight="900">对象/阈值 + 判断结果 + 处理结论</text>
    <path d="M58 138h274" stroke="#f97316" stroke-width="7" stroke-linecap="round"/>
  </svg></div>
  <h2>把这类题写成一句能拿分的话。</h2>
  <div class="score-write">
    <label><span>对象/阈值</span><input data-field="fact" placeholder="如:基坑开挖深度5.5m"></label>
    <label><span>判断结果</span><input data-field="judgment" placeholder="危大且超过一定规模"></label>
    <label><span>处理结论</span><input data-field="conclusion" placeholder="专项施工方案应组织专家论证"></label>
    <button type="button" class="check-score" data-check-score="1">检查采分句</button>
  </div>
  <div class="feedback" id="fb-{esc(score_qid)}"></div>
</section>"""
    )
    data = {
        "practice": practice,
        "score_question_id": score_qid,
        "score_terms": terms,
        "sample_score_sentence": sample,
        "warm_feedback": (master.get("mastery_discrimination", {}).get("warm_feedback") or {}),
    }
    css = """
*{box-sizing:border-box}html,body{margin:0;max-width:100%;overflow-x:hidden}body{background:#eaf1f6;color:#17202a;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}.practice{max-width:430px;margin:0 auto;min-height:100vh;padding:12px 10px 96px}header{display:flex;gap:12px;align-items:flex-start;margin-bottom:12px}header a{border:1px solid #cad8e5;border-radius:999px;padding:9px 11px;background:#fff;color:#176b7a;text-decoration:none;font-weight:900;font-size:12px;white-space:nowrap;min-height:44px;display:flex;align-items:center}header span{color:#176b7a;font-size:12px;font-weight:900}h1{font-size:22px;margin:3px 0 0;line-height:1.2}.progress{height:6px;border-radius:999px;background:#d6e2ec;margin-bottom:12px;overflow:hidden}.progress div{height:100%;width:0;background:#f97316}.q{display:none;background:#fff;border:1px solid #d2dee9;border-radius:18px;padding:13px;box-shadow:0 14px 32px rgba(31,41,55,.08)}.q.active{display:block}.qtop{display:flex;justify-content:space-between;gap:10px;color:#176b7a;font-size:12px;font-weight:900}.qtop em{font-style:normal;color:#607287;text-align:right}.diagram{height:220px;background:#fffdf7;border:1px solid #eadfcb;border-radius:14px;margin:10px 0;display:grid;place-items:center;overflow:hidden}.diagram svg{width:100%;height:100%}.gate rect{fill:#f8fafc;stroke:#cbd9e6;stroke-width:3}.gate.hot rect{fill:#fff7ed;stroke:#f97316;stroke-width:5}.gate.soft rect{fill:#f8fafc;stroke:#cbd9e6;stroke-width:3}.q h2{font-size:18px;line-height:1.34;margin:10px 0 12px}.options{display:grid;gap:9px}.option{text-align:left;min-height:58px;border:1px solid #cfdae6;background:#fff;border-radius:14px;padding:11px 12px;color:#24364b;font-size:15px;font-weight:800;line-height:1.42}.option.correct{border-color:#73c596;background:#ecf9f2}.option.wrong{border-color:#fb923c;background:#fff3e9}.option:disabled{opacity:1}.score-write{display:grid;gap:10px}.score-write label{display:grid;gap:5px}.score-write span{font-size:12px;font-weight:900;color:#176b7a}.score-write input{min-height:48px;border:1px solid #cfdae6;border-radius:13px;padding:0 12px;font-size:15px;font-weight:800;color:#17202a;background:#fff}.score-write input.ok{border-color:#73c596;background:#ecf9f2}.score-write input.no{border-color:#fb923c;background:#fff3e9}.check-score{min-height:48px;border:1px solid #176b7a;border-radius:14px;background:#176b7a;color:#fff;font-weight:900;font-size:15px}.feedback{display:none;margin-top:12px;border-radius:13px;padding:11px;font-size:14px;font-weight:800;line-height:1.55}.feedback.show.correct{display:block;background:#ecf9f2;border:1px solid #73c596;color:#0f6b4f}.feedback.show.wrong{display:block;background:#fff3e9;border:1px solid #fb923c;color:#9a3412}.feedback .basis{display:block;margin-top:7px;color:#56677c;font-size:12px;font-weight:800}.done{display:none;background:#fff;border:1px solid #d2dee9;border-radius:18px;padding:18px;box-shadow:0 14px 32px rgba(31,41,55,.08)}.done.show{display:block}.done h2{font-size:24px;margin:0 0 10px;text-align:center;color:#176b7a}.done p{font-size:15px;line-height:1.65;font-weight:800;color:#34465b}.atoms{display:grid;gap:7px;margin:12px 0}.atoms span{border-left:3px solid #176b7a;background:#f7fafc;border-radius:10px;padding:8px 10px;font-size:13px;font-weight:900;color:#34465b}.done a{display:flex;align-items:center;justify-content:center;background:#176b7a;color:#fff;border-radius:14px;min-height:46px;text-decoration:none;font-weight:900}nav{position:fixed;left:50%;bottom:0;transform:translateX(-50%);width:min(430px,100%);display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:10px 12px calc(10px + env(safe-area-inset-bottom));background:rgba(255,255,255,.96);border-top:1px solid #d2dee9;box-shadow:0 -10px 28px rgba(31,41,55,.12)}nav button{min-height:48px;border-radius:14px;border:1px solid #cfdae6;background:#fff;color:#24364b;font-weight:900}nav button:last-child{background:#176b7a;color:#fff;border-color:#176b7a}nav button.blocked{border-color:#fb923c;background:#fff7ed;color:#9a3412}
"""
    practice_link = master_path.name.replace(".master.json", ".journey.html")
    return f"""<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(master.get('exam_point','深母题'))} · 独立闯关</title><style>{css}</style></head>
<body><main class="practice">
<header><a href="{esc(practice_link)}">返回讲解</a><div><span>鲁班深母题 · 独立闯关</span><h1>{esc(master.get('exam_point',''))}</h1></div></header>
<div class="progress"><div id="progressFill"></div></div>
{''.join(sections)}
<section class="done" id="done"><h2>看穿结果</h2><p id="scoreText"></p><div class="atoms" id="atoms"></div><a href="{esc(practice_link)}">回看白板讲解</a></section>
</main><nav><button type="button" id="prevQ">上一题</button><button type="button" id="nextQ">下一题</button></nav>
<script type="application/json" id="practiceData">{js_json(data)}</script>
<script>
const DATA=JSON.parse(document.getElementById('practiceData').textContent);
const qs=[...document.querySelectorAll('.q')], selected={{}}, progress=document.getElementById('progressFill');
let current=0, score=0;
const qById=Object.fromEntries(DATA.practice.map(q=>[q.id,q]));
const clean=s=>String(s||'').replace(/\\s+/g,'').replace(/[，。；、,.;]/g,'').toLowerCase();
function el(tag, cls, text){{const node=document.createElement(tag);if(cls)node.className=cls;if(text!=null)node.textContent=String(text);return node;}}
function showFeedback(box, ok, mainText, basisText){{box.className='feedback show '+(ok?'correct':'wrong');box.replaceChildren(document.createTextNode((ok?'对。':'再看判据。')+' '+mainText), el('span','basis',basisText));}}
function show(i){{current=Math.max(0,Math.min(qs.length-1,i));qs.forEach((q,idx)=>q.classList.toggle('active',idx===current));progress.style.width=((current+1)/qs.length*100)+'%';document.getElementById('nextQ').textContent=current===qs.length-1?'查看结果':'下一题';}}
function done(i){{const qid=qs[i].dataset.qid;return !!selected[qid];}}
function needAnswer(){{const btn=document.getElementById('nextQ'),old=btn.textContent;btn.textContent='先独立作答';btn.classList.add('blocked');setTimeout(()=>{{btn.textContent=old;btn.classList.remove('blocked');}},900);}}
document.querySelectorAll('.option').forEach(btn=>btn.addEventListener('click',()=>{{
  const qEl=btn.closest('.q'), qid=qEl.dataset.qid, q=qById[qid]; if(selected[qid])return;
  const ok=btn.dataset.opt===q.answer; selected[qid]=btn.dataset.opt; if(ok)score++;
  qEl.querySelectorAll('.option').forEach(o=>{{o.disabled=true;if(o.dataset.opt===q.answer)o.classList.add('correct');else if(o===btn)o.classList.add('wrong');}});
	  const opt=(q.options||[]).find(o=>o.id===btn.dataset.opt)||{{feedback:''}};
	  const fb=document.getElementById('fb-'+qid);
	  showFeedback(fb, ok, ok?(q.correct_feedback||''):(opt.feedback||''), '判据:'+(q.basis||'')+(q.tier?' · '+q.tier:''));
	}}));
document.querySelector('[data-check-score]').addEventListener('click',()=>{{
  const qEl=qs[qs.length-1], qid=qEl.dataset.qid, values=[...qEl.querySelectorAll('input')].map(i=>i.value).join('');
  const terms=DATA.score_terms||[]; const hit=terms.filter(t=>clean(values).includes(clean(t))).length;
  selected[qid]=true; if(hit>=3)score++;
  qEl.querySelectorAll('input').forEach(i=>i.classList.toggle('ok',i.value.trim().length>0));
	  const fb=document.getElementById('fb-'+qid);
	  fb.className='feedback show '+(hit>=3?'correct':'wrong');
	  fb.replaceChildren(document.createTextNode(hit>=3?'对。':'还不够像采分句。'), el('span','basis','可写:'+DATA.sample_score_sentence));
	}});
document.getElementById('prevQ').addEventListener('click',()=>show(current-1));
document.getElementById('nextQ').addEventListener('click',()=>{{if(!done(current)){{needAnswer();return;}} if(current<qs.length-1)show(current+1);else showDone();}});
function showDone(){{qs.forEach(q=>q.classList.remove('active'));document.getElementById('done').classList.add('show');progress.style.width='100%';const ratio=score+'/'+qs.length;document.getElementById('scoreText').textContent=ratio+'。'+((DATA.warm_feedback||{{}}).all_correct||'把判断链写成采分句,才算真正会拿分。');document.getElementById('atoms').replaceChildren(...(DATA.score_terms||[]).slice(0,6).map(t=>{{const s=document.createElement('span');s.textContent=t;return s;}}));}}
show(0);
</script></body></html>"""


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: render_archetype_practice.py <master.json>", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    out = src.with_name(src.name.replace(".master.json", ".practice.html"))
    out.write_text(render(src), encoding="utf-8")
    print(f"✅ {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
