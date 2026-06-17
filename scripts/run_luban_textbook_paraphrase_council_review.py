#!/usr/bin/env python3
"""Living LLM Artifact Compiler — apply a GOVERNED council review to the paraphrase backlog and sign.

This is the second half of the verified_paraphrase channel (the first half,
run_luban_textbook_paraphrase_review.py, OPENS the channel). It applies a governed council's verdicts
to the review packets and runs the deterministic signer.

Authority seam (mirrors F1): faithfulness is a SEMANTIC judgment and is NOT decided here. It comes from
a governed council (Opus 4.8 + Codex GPT5.5, both independent, user-authorized) as a verdicts file:
``[{point_id, opus_verdict, codex_verdict, models_agree, council_verdict}]``. The council_verdict is
``faithful`` ONLY when both models independently agree faithful. This runner is DETERMINISTIC: it joins
each governed verdict onto its packet and hands it to ``sign_verified_paraphrase_release_candidate``,
which signs ONLY ``faithful`` packets (from a governed reviewer) whose claim numbers are grounded in the
source. The signer never decides faithfulness; this runner never signs by itself.

A signed record lands in the SEPARATE weaker namespace ``textbook_paraphrase_review`` (teaching context,
official_answer_capable=False, ZERO verbatim authority). NO publish / production / canonical / remote.

Usage:
  python scripts/run_luban_textbook_paraphrase_council_review.py \
      --verdicts artifacts/.../council_verdicts.json
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
OUT = _REPO / "artifacts" / "luban_grading_artifacts" / "textbook_paraphrase_council_20260606"
SUPPLY_DIR = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_textbook_paraphrase_review"

# Reuse the channel-opening runner's read-only loaders (same backlog + 教材 source-of-truth).
import importlib.util as _ilu  # noqa: E402

from deeptutor.services.construction_grading import full_knowledge_compiler as FKC  # noqa: E402
from deeptutor.services.construction_grading import textbook_paraphrase_review as PR  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_pr_channel", str(_REPO / "scripts" / "run_luban_textbook_paraphrase_review.py"))
_chan = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_chan)

_REVIEWER_ID = "opus-4.8+codex-gpt5.5"  # the user-authorized build-phase governed council


def _apply_verdicts(packets: list[dict[str, Any]], verdicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join each governed council_verdict onto its packet (governed reviewer role)."""
    by_pid = {str(v.get("point_id")): v for v in verdicts}
    out: list[dict[str, Any]] = []
    for p in packets:
        v = by_pid.get(p["point_id"])
        if not v:
            out.append(p)  # no verdict -> stays unfilled -> signer routes back
            continue
        out.append({**p, "review_verdict": str(v.get("council_verdict") or ""),
                    "reviewer_role": "governed_council", "reviewer_id": _REVIEWER_ID,
                    "council_detail": {k: v.get(k) for k in
                                       ("opus_verdict", "codex_verdict", "models_agree")}})
    return out


def run(verdicts_path: str) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    backlog = _chan._load_backlog()
    cards_by_point, source_by_chunk = _chan._load_cards_and_sources()
    packets = PR.build_review_queue(backlog, cards_by_point, source_by_chunk)["packets"]
    verdicts = json.loads(Path(verdicts_path).read_text("utf-8"))
    reviewed = _apply_verdicts(packets, verdicts)
    signed = PR.sign_verified_paraphrase_release_candidate(reviewed)
    m = signed["manifest"]

    persisted = False
    if m["signed_count"] > 0:
        SUPPLY_DIR.mkdir(parents=True, exist_ok=True)
        (SUPPLY_DIR / "textbook_paraphrase_release_candidate.json").write_text(
            json.dumps(signed, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "utf-8")
        (SUPPLY_DIR / "canonical_pointer.json").write_text(json.dumps(
            {"namespace": PR.PARAPHRASE_NAMESPACE, "status": "release_candidate", "published": False,
             "expected_content_hash": m["content_hash"]}, ensure_ascii=False, indent=2), "utf-8")
        persisted = True

    council_faithful = sum(1 for v in verdicts if str(v.get("council_verdict")) == "faithful")
    unanimous = sum(1 for v in verdicts if v.get("models_agree"))
    gates = {
        "verdicts_cover_all_packets": all(
            p["point_id"] in {str(v.get("point_id")) for v in verdicts} for p in packets),
        "signed_only_governed_faithful": m["ungoverned_verdict_signed"] == 0,
        "zero_verbatim_authority": m["verbatim_authority_records"] == 0,
        "separate_namespace": m["namespace"] == PR.PARAPHRASE_NAMESPACE != FKC.TEXTBOOK_KNOWLEDGE_NAMESPACE,
        "bundle_verifies_if_signed": (m["signed_count"] == 0) or FKC.verify_lane_bundle(signed, PR.PARAPHRASE_NAMESPACE),
    }
    report = {
        "verdict": "GO" if all(gates.values()) else "NO-GO",
        "packets_reviewed": len(packets),
        "models_unanimous": f"{unanimous}/{len(verdicts)}",
        "council_faithful": council_faithful,
        "signed_count": m["signed_count"],
        "routed_back_count": m["work_order_count"],
        "supply_persisted": persisted,
        "signed_namespace": PR.PARAPHRASE_NAMESPACE,
        "reviewer": _REVIEWER_ID,
        "hard_gates": gates,
        "routed_back": signed["work_order"],
        "note": "council faithfulness is a governed input; signing is deterministic. signed=0 means the "
                "governed council rejected every card — channel discipline holding, NOT a failure.",
    }
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    (OUT / "signed_bundle.json").write_text(json.dumps(signed, ensure_ascii=False, indent=2), "utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdicts", required=True, help="governed council verdicts JSON")
    args = ap.parse_args()
    rep = run(args.verdicts)
    print(json.dumps({"verdict": rep["verdict"], "reviewed": rep["packets_reviewed"],
                      "unanimous": rep["models_unanimous"], "council_faithful": rep["council_faithful"],
                      "signed": rep["signed_count"]}, ensure_ascii=False))
    return 0 if rep["verdict"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
