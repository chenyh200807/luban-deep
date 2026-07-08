#!/usr/bin/env python3
"""Build a self-contained static HTML demo of the case light-practice chain.

DEV / DEMO ONLY. Runs the REAL chain deterministically:
  F16 采分点(dev fixture) → 生成器(stub complete_fn,干扰项为 dev-stub 待真 LLM 换)
  → RTG1-8 门真裁决 → 确定性判分(两份作答 A/B 复现 live 验证的"漏 a5 分层剥开判低分")

The ONLY stubbed link is the distractor SOURCE (a canned complete_fn standing in for
DeepSeek until deploy/creds allow a real-LLM run). Everything else — the scoring
points, the gates, the scoring — is the production code path. Regenerate this demo
after the real-LLM swap to replace the stub.

Usage: python scripts/build_case_light_practice_demo.py [out.html]
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root on path for direct run

from deeptutor.services.construction_grading.case_light_practice_contract import (
    score_conjunction_group,
)
from deeptutor.services.construction_grading.case_light_practice_generator import (
    generate_point_select_item,
    load_dev_fixture,
)
from deeptutor.services.construction_grading.case_light_practice_rtg import GateStatus

# Realistic dev-stub distractors (stand-in for DeepSeek output; each is a
# 采分点-recognizable wrong variant with a case error_code).
_STUB_DISTRACTORS = [
    {"text": "喷灯烘烤后直接重贴,不必分层剥开", "error_code": "E06"},
    {"text": "用水泥砂浆抹平鼓泡即可,无需割开", "error_code": "E01"},
    {"text": "整片屋面铲除重做防水层", "error_code": "E05"},
]


def _run_chain() -> dict:
    qid, points = load_dev_fixture("F16_qigu_gebu")
    stub = lambda _p: json.dumps({"distractors": _STUB_DISTRACTORS})
    gen = generate_point_select_item(points, complete_fn=stub, target_point_id="a5", dev_fixture=True)

    gates = [{"gate": r.gate, "status": r.status.value, "detail": r.detail} for r in gen.report.results]

    # Two answers reproducing the live-validated distinction:
    #  A misses a5 (分层剥开); B hits it. Deterministic coverage scoring.
    all_ids = {p.point_id for p in points}
    answer_a = all_ids - {"a5"}          # 漏关键区分点
    answer_b = set(all_ids)              # 全命中(含 a5)
    total = sum(p.max_score for p in points)
    score_a = score_conjunction_group(points, answer_a)
    score_b = score_conjunction_group(points, answer_b)

    return {
        "qid": qid,
        "sub_no": points[0].sub_no,
        "points": [
            {"id": p.point_id, "statement": p.statement, "score": p.max_score, "key": p.point_id == "a5"}
            for p in points
        ],
        "item": gen.item,
        "gen_status": gen.status.value,
        "gen_attempts": gen.attempts,
        "gates": gates,
        "grading": {
            "total": round(total, 2),
            "answer_a": {"label": "作答 A(漏『分层剥开』)", "hit": sorted(answer_a), "score": round(score_a, 2)},
            "answer_b": {"label": "作答 B(写了『分层剥开』)", "hit": sorted(answer_b), "score": round(score_b, 2)},
        },
    }


_STATUS_COLOR = {
    "pass": "#2e7d32", "block": "#c62828", "soft_fail": "#ef6c00",
    "needs_human": "#6a1b9a", "not_exercised": "#616161",
}


def _render(d: dict) -> str:
    def esc(x):
        return html.escape(str(x))

    points_rows = "".join(
        f"<tr class='{'key' if p['key'] else ''}'><td>{esc(p['id'])}</td>"
        f"<td>{esc(p['statement'])}</td><td class='num'>{p['score']}</td></tr>"
        for p in d["points"]
    )
    correct = d["item"]["correct_options"][0]
    opts = f"<li class='correct'>✓ {esc(correct['text'])} <span class='src'>[采分点 {esc(correct['source_scoring_point_id'])} 原文]</span></li>"
    opts += "".join(
        f"<li class='distractor'>✗ {esc(x['text'])} <span class='code'>[{esc(x['error_code'])}]</span></li>"
        for x in d["item"]["distractors"]
    )
    gate_rows = "".join(
        f"<tr><td>{esc(g['gate'])}</td>"
        f"<td><span class='badge' style='background:{_STATUS_COLOR.get(g['status'],'#616161')}'>{esc(g['status'])}</span></td>"
        f"<td class='detail'>{esc(g['detail'])}</td></tr>"
        for g in d["gates"]
    )
    gr = d["grading"]
    a, b = gr["answer_a"], gr["answer_b"]
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>案例题轻练 · F16 起鼓割补 · 链路 demo</title>
<style>
 body{{font-family:-apple-system,'PingFang SC',sans-serif;max-width:860px;margin:0 auto;padding:20px;color:#1a1a1a;background:#faf8f4;line-height:1.6}}
 h1{{font-size:20px}} h2{{font-size:16px;margin-top:28px;border-left:4px solid #8d6e63;padding-left:10px}}
 .note{{background:#fff3e0;border:1px solid #ffcc80;padding:10px 14px;border-radius:8px;font-size:13px;color:#5d4037}}
 table{{border-collapse:collapse;width:100%;font-size:14px;margin-top:8px}} td,th{{border:1px solid #e0d8cc;padding:6px 10px;text-align:left}}
 .num{{text-align:right}} tr.key td{{background:#fff8e1;font-weight:600}}
 ul.opts{{list-style:none;padding:0}} ul.opts li{{padding:8px 12px;margin:6px 0;border-radius:8px;font-size:14px}}
 li.correct{{background:#e8f5e9;border:1px solid #a5d6a7}} li.distractor{{background:#fbe9e7;border:1px solid #ffab91}}
 .src{{color:#2e7d32;font-size:12px}} .code{{color:#c62828;font-size:12px}}
 .badge{{color:#fff;padding:2px 8px;border-radius:10px;font-size:12px}} .detail{{font-size:12px;color:#555}}
 .cmp{{display:flex;gap:14px;flex-wrap:wrap}} .card{{flex:1;min-width:260px;background:#fff;border:1px solid #e0d8cc;border-radius:10px;padding:14px}}
 .big{{font-size:26px;font-weight:700}} .a .big{{color:#ef6c00}} .b .big{{color:#2e7d32}}
</style></head><body>
<h1>案例题轻练 · 链路 demo</h1>
<p class="note"><b>DEV 演示</b> · qid <code>{esc(d['qid'])}</code> · 小问「{esc(d['sub_no'])}」· <code>official_score_allowed=false</code><br>
真链路:F16 真采分点 → 生成器 → <b>真 RTG1-8 门</b> → <b>真确定性判分</b>。唯一 stub 环节 = 干扰项来源(占位待真 DeepSeek,需部署/凭据)。生成状态:<b>{esc(d['gen_status'])}</b>(尝试 {d['gen_attempts']} 次)。</p>

<h2>① 采分点(原子化 · 已 live 验证)</h2>
<table><tr><th>id</th><th>采分点</th><th>分</th></tr>{points_rows}</table>

<h2>② 生成的点选题(correct=采分点原文,LLM 只造干扰项)</h2>
<p><b>{esc(d['item']['stem'])}</b></p>
<ul class="opts">{opts}</ul>

<h2>③ RTG1-8 门裁决(真跑,未给输入的门显式 not_exercised)</h2>
<table><tr><th>门</th><th>状态</th><th>说明</th></tr>{gate_rows}</table>

<h2>④ 确定性判分:漏关键点判出差异(复现 live 验证)</h2>
<p class="note">同一道题,作答 A 漏了关键区分点 <b>a5 分层剥开</b>、作答 B 写了——确定性判分必须判出不同分。这正是"污染 rubric 判同分虚高"被治好的证据。</p>
<div class="cmp">
 <div class="card a"><div>{esc(a['label'])}</div><div class="big">{a['score']} / {gr['total']}</div><div class="detail">命中 {len(a['hit'])}/{len(d['points'])} 点(缺 a5)</div></div>
 <div class="card b"><div>{esc(b['label'])}</div><div class="big">{b['score']} / {gr['total']}</div><div class="detail">命中 {len(b['hit'])}/{len(d['points'])} 点(含 a5)</div></div>
</div>
</body></html>"""


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("case_light_practice_demo.html")
    data = _run_chain()
    out.write_text(_render(data), encoding="utf-8")
    print(f"demo written: {out}  (gen_status={data['gen_status']}, A={data['grading']['answer_a']['score']} B={data['grading']['answer_b']['score']}/{data['grading']['total']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
