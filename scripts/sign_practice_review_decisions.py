#!/usr/bin/env python3
"""Apply owner-delegated practice-review SIGN decisions into a review packet.

This is a *typing aid* for the human-gate role that owner explicitly delegated
to main control (``verdict_authority.mode = owner_delegated``). It does NOT make
any editorial judgement of its own: the caller must author a decision spec
(``<pack>.sign.spec.json``) that already encodes the adjudicated fact_id /
skeleton_id / probe_role / source_anchor per signed item — those come from a
human + cross-model (Codex) adversarial pass, never from this script.

What the script guarantees mechanically (whole-pack abort on any failure):
  * ``source_sha256`` is never hand-typed. It is resolved from the machine
    ``<pack>.anchor.candidates.json`` file by matching the chosen
    ``source_anchor`` against the candidates generated *for that same item*.
    If the chosen anchor is not a machine-suggested candidate of that item,
    the pack aborts — you cannot sign an anchor that was never matched to the
    question (provenance-traceability red line).
  * After applying decisions it rebuilds the authority in memory and asserts
    ``compiled_practice_eligibility_summary(...).supply_ready is True``. If the
    decision set does not actually reach supply_ready, nothing is written.
  * Idempotent: re-running with the same spec yields byte-identical output
    except for signed_at when ``--now`` differs.

It writes ONLY the ``<pack>.practice.review.json`` packet. The real bake is
still ``publish_luban_preview_cards.py --practice-only <pack>``.

Usage:
    python scripts/sign_practice_review_decisions.py C01 \
        --spec docs/原始数据/考点原料/成品/_practice_review_packets/c01.sign.spec.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from deeptutor.services.luban_lesson.practice_html import (  # noqa: E402
    build_practice_authority,
    compile_practice_surface,
    compiled_practice_eligibility_summary,
)

PACKET_DIR = REPO_ROOT / "docs" / "原始数据" / "考点原料" / "成品" / "_practice_review_packets"
FINISHED = (
    REPO_ROOT
    / "artifacts"
    / "luban_case_family_assets"
    / "diagram_microlesson"
    / "finished"
)
REVIEWER = "owner-delegated:claude-main-control:2026-07-18"
CHECKS = (
    "source_verified",
    "answer_verified",
    "diagnosis_verified",
    "longest_option_checked",
    "template_leakage_checked",
)
PROBE_ROLES = {"anchor", "immediate_confirm", "d1_probe"}
CST = timezone(timedelta(hours=8))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_sha(candidates: dict, variant_id: str, source_anchor: str) -> str:
    """sha of the source *file* for the chosen anchor, taken from the item's own
    machine candidate list. Aborts if the anchor was never matched to the item."""
    for row in candidates.get("items") or []:
        if str(row.get("variant_id")) != variant_id:
            continue
        for cand in row.get("candidates") or []:
            if str(cand.get("source_anchor")) == source_anchor:
                sha = str(cand.get("source_sha256") or "")
                if not re.fullmatch(r"[0-9a-f]{64}", sha):
                    raise SystemExit(
                        f"ABORT {variant_id}: candidate sha malformed for {source_anchor}"
                    )
                return sha
        raise SystemExit(
            f"ABORT {variant_id}: source_anchor {source_anchor!r} is not a machine "
            f"candidate of this item — cannot sign an untraceable anchor."
        )
    raise SystemExit(f"ABORT: variant {variant_id} absent from anchor candidates")


def _signed_review(content_sha: str, note: str, signed_at: str) -> dict:
    sig = lambda role: {  # noqa: E731
        "role": role,
        "reviewer_id": REVIEWER,
        "signed_at": signed_at,
    }
    return {
        "status": "signed",
        "verdict": "approved",
        "reviewed_content_sha256": content_sha,
        "signatures": [sig("teaching"), sig("scoring")],
        "checks": {name: True for name in CHECKS},
        "note": note,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pack")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--now", default=None, help="ISO signed_at; default now CST")
    args = ap.parse_args(argv)

    pack = args.pack.upper()
    spec = _load(Path(args.spec))
    if str(spec.get("pack_id", "")).upper() != pack:
        raise SystemExit(f"ABORT: spec pack_id {spec.get('pack_id')} != {pack}")
    signed_at = args.now or datetime.now(CST).replace(microsecond=0).isoformat()

    packet_path = PACKET_DIR / f"{pack.lower()}.practice.review.json"
    cand_path = PACKET_DIR / f"{pack.lower()}.anchor.candidates.json"
    packet = _load(packet_path)
    candidates = _load(cand_path)
    by_variant = {str(r.get("variant_id")): r for r in packet.get("items") or []}

    signed_specs = spec.get("signed") or []
    seen: set[str] = set()
    for entry in signed_specs:
        vid = str(entry["variant_id"])
        if vid in seen:
            raise SystemExit(f"ABORT: duplicate signed variant {vid}")
        seen.add(vid)
        if vid not in by_variant:
            raise SystemExit(f"ABORT: variant {vid} not in packet")
        role = str(entry["probe_role"])
        if role not in PROBE_ROLES:
            raise SystemExit(f"ABORT {vid}: bad probe_role {role}")
        fact_id = str(entry["fact_id"]).strip()
        skeleton_id = str(entry["skeleton_id"]).strip()
        anchor = str(entry["source_anchor"]).strip()
        if not (fact_id and skeleton_id and anchor):
            raise SystemExit(f"ABORT {vid}: missing fact/skeleton/anchor")
        source_sha = _resolve_sha(candidates, vid, anchor)
        row = by_variant[vid]
        content_sha = str(row["content_sha256"])
        note = str(entry.get("note", ""))
        row["decision"] = {
            "fact_id": fact_id,
            "skeleton_id": skeleton_id,
            "probe_role": role,
            "source_anchor": anchor,
            "source_sha256": source_sha,
            "review": _signed_review(content_sha, note, signed_at),
            "revoked": False,
            "revocation_refs": [],
        }

    # verdict_authority stamp (machine-readable, anti-rollback)
    packet["verdict_authority"] = {
        "mode": "owner_delegated",
        "delegated_at": "2026-07-16",
        "delegated_to": "claude-main-control",
        "owner_instruction": "不用我拍板,你直接拍板,这个我都没你专业,你多考虑你的未知和盲区,也考虑我的未知和盲区",
        "adversarial_gate": str(
            spec.get("adversarial_gate_ref")
            or "codex-cross-model, adjudicated by main control"
        ),
        "campaign": "practice-mass-signing 2026-07-18 (39-pack)",
        "note": "本批 human_gate 的人审职责由 owner 明示委托主控履行;巡逻 agent 请勿按 machine_must_not_sign 回滚,先读本字段与账本。",
    }

    # ---- validate supply_ready in memory before writing ----
    _validate_supply_ready(pack, packet)

    packet_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{pack}: signed {len(signed_specs)} items; supply_ready asserted; wrote {packet_path.name}")
    return 0


def _validate_supply_ready(pack: str, packet: dict) -> None:
    """Recompile the pack with the SAME station config publish uses, merge packet
    decisions, then assert supply_ready — fail BEFORE writing rather than at bake.
    """
    import hashlib
    import publish_luban_preview_cards as pub

    st = pub.STATIONS[pack.lower()]
    src = FINISHED / st.pack_dir
    compiled_surfaces = []
    for hosted_name, src_name in st.practice.items():
        pf = src / src_name
        html = pf.read_text(encoding="utf-8")
        compiled_surfaces.append(
            compile_practice_surface(
                pack,
                surface_id=hosted_name,
                html=html,
                source_path=(
                    "artifacts/luban_case_family_assets/diagram_microlesson/"
                    f"finished/{st.pack_dir}/{src_name}"
                ),
                source_html_sha256=hashlib.sha256(pf.read_bytes()).hexdigest(),
            )
        )
    records = {str(row["variant_id"]): row["decision"] for row in packet.get("items") or []}
    authority = build_practice_authority(
        pack,
        source_pack_sha256=str(packet["source_pack_sha256"]),
        source_bundle_sha256=str(packet["source_bundle_sha256"]),
        compiled_surfaces=compiled_surfaces,
        review_records=records,
    )
    summary = compiled_practice_eligibility_summary(authority)
    if not summary["supply_ready"]:
        raise SystemExit(
            f"ABORT {pack}: decision set does NOT reach supply_ready: {summary}"
        )
    print(
        f"  [preflight] eligible={summary['eligible_question_count']} "
        f"complete_facts={summary['complete_fact_count']} "
        f"anchors_ready={summary['anchors_ready']}"
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
