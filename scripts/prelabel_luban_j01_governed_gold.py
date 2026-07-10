#!/usr/bin/env python3
"""J01 governed-gold AI PRE-LABEL (draft/candidate only — NEVER gold).

Optional工作量-reducer: emits a per-cell hit/partial/miss *draft* to seed educators,
who then confirm/override. Every output row is stamped ``label_status=draft_candidate``
and ``authority=ai_prelabel_not_gold``. This script CANNOT produce gold — gold is
the human column filled in the annotation templates, adjudicated by
score_luban_j01_governed_gold.py.

RED LINES (eval-design):
  * gold = 人. AI 面板 `fleiss_kappa=-0.05` 已证其不可单独当金标。
  * 反循环:预标用的模型 **不得** 等于阶段1 judging 用的模型/供应商,否则臂不公平
    (circular metric)。本脚本记录 prelabel_model_id 供阶段1 做臂公平审计。
  * 预标只进独立的 *_ai_prelabel.csv,绝不写进人的标注模板,避免锚定偏置(anchoring)。

Two backends:
  * ``--backend offline_stub`` (default, no network, deterministic, CI-safe) — a
    transparent keyword-overlap heuristic. It is a scaffold demonstrator, explicitly
    NOT a real judge; its model_id is ``offline_deterministic_stub`` so it can never
    be confused with a stage-1 judge.
  * ``--backend arbitration_panel`` — documents the hook to the existing metered
    pure-API panel ``scripts/run_luban_arbitration_gold_panel.py`` (run it with
    ``--tier live`` and a roster DISJOINT from the stage-1 judge, then map its
    per-point verdicts in here). Not invoked automatically (billable + double opt-in).

Offline, re-runnable. `production_write_count == 0`.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _keywords(label: str, official_basis: str) -> list[str]:
    """Extract candidate 踩字 terms from the scoring point (deterministic)."""
    text = f"{label or ''} {official_basis or ''}"
    # Chinese terms of length >=2, plus tokens like ≥3m.
    terms = re.findall(r"[一-鿿]{2,6}", text)
    terms += re.findall(r"[≥≤]?\d+\s*m", text)
    # de-dup preserving order, drop over-generic connectors
    stop = {"须写", "原文", "官方", "规范", "术语", "命中", "得分", "满分", "如果", "以及", "或者"}
    out: list[str] = []
    for t in terms:
        if t not in out and t not in stop:
            out.append(t)
    return out[:12]


def _offline_stub_verdict(scoring_point: dict[str, Any], student_answer: str) -> tuple[str, float]:
    """Transparent keyword-overlap heuristic. Returns (verdict, overlap_ratio).

    NOT a real judge — a deterministic demonstrator so the scaffold runs end-to-end.
    """
    kws = _keywords(str(scoring_point.get("label") or ""), str(scoring_point.get("official_basis") or ""))
    ans = student_answer or ""
    if not kws:
        return "miss", 0.0
    hits = sum(1 for k in kws if k in ans)
    ratio = hits / len(kws)
    if ratio >= 0.6:
        return "hit", round(ratio, 3)
    if ratio >= 0.2:
        return "partial", round(ratio, 3)
    return "miss", round(ratio, 3)


def build_prelabels(*, manifest_path: Path, packets_path: Path, backend: str) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    packets = {str(p["cell_id"]): p for p in _read_json(packets_path)}
    if backend == "offline_stub":
        model_id = "offline_deterministic_stub"
    elif backend == "arbitration_panel":
        raise SystemExit(
            "backend=arbitration_panel is a documented HOOK, not auto-run (billable + double opt-in). "
            "Run scripts/run_luban_arbitration_gold_panel.py --tier live with a roster disjoint from the "
            "stage-1 judge, then map its per-point verdicts into this format."
        )
    else:
        raise SystemExit(f"unknown backend {backend!r}")

    rows: list[dict[str, Any]] = []
    for cell in manifest.get("cells") or []:
        cid = str(cell["cell_id"])
        packet = packets.get(cid, {})
        sp = packet.get("scoring_point", {})
        verdict, confidence = _offline_stub_verdict(sp, str(packet.get("student_answer_text") or ""))
        rows.append({
            "cell_id": cid,
            "case_id": cell.get("case_id"),
            "student_id": cell.get("student_id"),
            "point_id": cell.get("point_id"),
            "ai_draft_hit": verdict,
            "ai_confidence": confidence,
            "label_status": "draft_candidate",
            "authority": "ai_prelabel_not_gold",
            "prelabel_model_id": model_id,
        })
    return {
        "slice_id": manifest.get("slice_id"),
        "schema_version": "luban_j01_governed_gold_prelabel.v1",
        "backend": backend,
        "prelabel_model_id": model_id,
        "authority": "ai_prelabel_not_gold",
        "redline": (
            "draft/candidate only — 教研必须逐条复核;预标模型不得等于阶段1 judging 模型(反循环)。"
            "gold = 人;AI 面板 fleiss_kappa=-0.05 反例。"
        ),
        "anti_circularity_note": (
            f"prelabel_model_id={model_id}. 阶段1 A/B 的 judging 模型必须与此不同,否则臂不公平。"
        ),
        "rows": rows,
        "production_write_count": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AI pre-label (draft/candidate) for J01 governed-gold slice.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--packets", required=True)
    parser.add_argument("--backend", default="offline_stub", choices=["offline_stub", "arbitration_panel"])
    parser.add_argument("--output", required=True, help="Writes a *_ai_prelabel.json (NOT the human template).")
    args = parser.parse_args()
    result = build_prelabels(
        manifest_path=Path(args.manifest), packets_path=Path(args.packets), backend=args.backend
    )
    out = Path(args.output)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # Also emit a CSV sidecar for convenience.
    csv_path = out.with_suffix(".csv")
    if result["rows"]:
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(result["rows"][0].keys()))
            writer.writeheader()
            writer.writerows(result["rows"])
    from collections import Counter
    dist = Counter(r["ai_draft_hit"] for r in result["rows"])
    print(json.dumps({
        "slice_id": result["slice_id"], "backend": result["backend"],
        "prelabel_model_id": result["prelabel_model_id"],
        "rows": len(result["rows"]), "verdict_distribution": dict(dist),
        "output": str(out), "csv": str(csv_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
