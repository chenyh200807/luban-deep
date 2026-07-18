"""Whole-corpus guards for the compiled practice surface.

Two single-authority invariants that must hold for EVERY compiled pack, not just
the pack that happened to get eyeballed:

1. Projection-receipt single source — the receipt baked into each hosted practice
   HTML must appear verbatim inside the pack's compiled authority artifact. This
   locks the 2026-07 receipt SEV fix (PR #489) against silent drift for the whole
   corpus, so a partially-recompiled or hand-edited pack can never ship a hosted
   HTML whose receipt no longer matches the artifact the runtime resolves against.

2. Reachability follows the eligibility authority — the lesson viewmodel may only
   expose a practice/retest entry for a pack whose ``supply_ready`` is True. The
   runtime retest path fail-closes on ``supply_ready`` (unsigned items -> HTTP 409
   ``content_updated_retake``); if the viewmodel advertised a practice surface for a
   not-yet-released pack, users would be routed into a guaranteed 409. This test
   pins ``practice_surface.available`` / ``variant_retest.available`` to the single
   ``supply_ready`` authority so the backend entry can never drift ahead of release.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from deeptutor.services.luban_lesson.practice_html import (
    compiled_practice_eligibility_summary,
    load_compiled_practice,
)
from deeptutor.services.luban_lesson.read_model import build_lesson_viewmodel

ROOT = Path(__file__).resolve().parents[3]
COMPILED_DIR = ROOT / "deeptutor" / "services" / "luban_lesson" / "compiled"
PUBLIC = ROOT / "web" / "public" / "luban-preview"


def _compiled_pack_ids() -> list[str]:
    return sorted(
        artifact.name.split(".", 1)[0].upper()
        for artifact in COMPILED_DIR.glob("*.practice.authority.json")
    )


COMPILED_PACK_IDS = _compiled_pack_ids()


def test_compiled_corpus_is_non_empty() -> None:
    # Guard against a globbing/path regression silently turning the whole suite
    # into a no-op (0 parametrized cases would "pass" vacuously).
    assert COMPILED_PACK_IDS, "no compiled practice authorities discovered"


@pytest.mark.parametrize("pack_id", COMPILED_PACK_IDS)
def test_hosted_practice_receipt_matches_artifact(pack_id: str) -> None:
    authority = load_compiled_practice(pack_id)
    assert authority is not None, f"{pack_id}: compiled authority failed to load"
    surfaces = authority.get("surfaces") or []
    assert surfaces, f"{pack_id}: authority has no surfaces"
    for surface in surfaces:
        surface_id = str(surface.get("surface_id") or "")
        receipt = str(surface.get("projection_receipt") or "")
        assert receipt, f"{pack_id}/{surface_id}: artifact surface has empty receipt"
        hosted = PUBLIC / pack_id.lower() / surface_id
        assert hosted.is_file(), f"{pack_id}/{surface_id}: hosted practice HTML missing"
        html = hosted.read_text(encoding="utf-8")
        assert receipt in html, (
            f"{pack_id}/{surface_id}: hosted HTML embedded projection_receipt "
            "does not match the compiled authority surface receipt "
            "(receipt single-source drift)"
        )


@pytest.mark.parametrize("pack_id", COMPILED_PACK_IDS)
def test_practice_reachability_follows_supply_ready(pack_id: str) -> None:
    authority = load_compiled_practice(pack_id)
    assert authority is not None, f"{pack_id}: compiled authority failed to load"
    supply_ready = bool(
        compiled_practice_eligibility_summary(authority)["supply_ready"]
    )
    viewmodel = build_lesson_viewmodel(pack_id)
    practice_available = viewmodel.get("practice_surface", {}).get("available")
    variant_available = viewmodel.get("variant_retest", {}).get("available")
    assert practice_available is supply_ready, (
        f"{pack_id}: practice_surface.available={practice_available} but "
        f"supply_ready={supply_ready} — reachability drifted from eligibility "
        "authority (would route users into a 409 content_updated_retake)"
    )
    assert variant_available is supply_ready, (
        f"{pack_id}: variant_retest.available={variant_available} but "
        f"supply_ready={supply_ready} — retest entry drifted from eligibility"
    )
