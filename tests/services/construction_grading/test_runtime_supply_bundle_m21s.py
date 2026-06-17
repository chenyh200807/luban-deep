"""M21S — guards for the tracked runtime supply bundle.

The luban limited-default runtime must load its supply from the TRACKED, signed bundle (not
gitignored review artifacts) so a clean checkout works. Tampering / missing / malformed must
fail-closed; the artifacts fallback must not be the silent default.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from deeptutor.services.construction_grading import beta_shadow_loader as bsl

BUNDLE = bsl._SUPPLY_BUNDLE

pytestmark = pytest.mark.skipif(not (BUNDLE / "runtime_supply_manifest.json").exists(),
                                reason="runtime supply bundle absent")


def test_bundle_is_the_default_runtime_supply_no_artifacts_needed():
    # default (no root, no dev env) -> bundle, even though artifacts/ may not exist
    supply = bsl.load_beta_supply()
    assert supply.supply_dir.replace("\\", "/").endswith("runtime_supply/v1_limited_default")
    c = supply.counts()
    assert c["machine_specs"] > 0 and c["list_specs"] > 0 and c["source_backed"] > 0
    reg = bsl.load_release_candidate_registry()
    assert reg["status"] == "release_candidate" and reg["points"]


def test_manifest_is_signed_and_minimal():
    man = json.loads((BUNDLE / "runtime_supply_manifest.json").read_text("utf-8"))
    assert man["status"] == "limited_default_candidate"
    assert man["content_hash"] and man["registry_hash"]
    assert man["production_default"] == "off"
    # minimal: residual reduced to auto-candidate points only; no raw votes / FINDINGs
    assert "raw_llm_votes" in man["excluded_review_artifact_categories"]
    # the source matcher authority is deterministic; models never a source
    assert "never a source" in man["runtime_authority"].lower()


def test_no_review_material_in_bundle():
    # golden_typed_policy holds only {case_id, point_id, typed_policy}; no answer/stem text rows
    for row in (BUNDLE / "golden_typed_policy.jsonl").read_text("utf-8").splitlines():
        if not row.strip():
            continue
        r = json.loads(row)
        assert set(r.keys()) == {"case_id", "point_id", "typed_policy"}
    # source_backed_points: only keys + verified terms
    for row in (BUNDLE / "source_backed_points.jsonl").read_text("utf-8").splitlines():
        if not row.strip():
            continue
        r = json.loads(row)
        assert set(r.keys()) <= {"question_id", "point_id", "source_terms"}


def test_hash_mismatch_fails_closed(tmp_path: Path):
    dst = tmp_path / "bundle"
    shutil.copytree(BUNDLE, dst)
    # tamper a supply file -> recomputed content_hash != manifest content_hash
    f = dst / "machine_checkable_case_specs_m10.jsonl"
    f.write_text(f.read_text("utf-8") + '{"question_id":"X","point_id":"P","textbook_source":false,'
                 '"auto_certifiable":false,"spec":{"kind":"numeric_judgment"}}\n', "utf-8")
    with pytest.raises(bsl.BetaSupplyUnavailable):
        bsl.load_beta_supply(root=dst)


def test_malformed_manifest_fails_closed(tmp_path: Path):
    dst = tmp_path / "bundle"
    shutil.copytree(BUNDLE, dst)
    (dst / "runtime_supply_manifest.json").write_text("{ not json", "utf-8")
    with pytest.raises(bsl.BetaSupplyUnavailable):
        bsl.load_beta_supply(root=dst)


def test_missing_supply_fails_closed(tmp_path: Path):
    with pytest.raises(bsl.BetaSupplyUnavailable):
        bsl.load_beta_supply(root=tmp_path)  # empty dir -> missing inventory


def test_legacy_untouched_and_production_default_off():
    # the bundle never claims production default / published
    reg = bsl.load_release_candidate_registry()
    assert reg.get("published") is not True
    assert reg.get("production_default") in (None, "off", False)
