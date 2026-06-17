"""Deterministic smoke for Best-Quality vs DeepSeek-Fast (cached, no live provider).

Asserts the runtime-test guarantees the FINDING claims:
  - bad_certified_count == 0 across all samples (guards never auto-certify junk);
  - at least one unsupported point is fail-closed (auto_certified=False);
  - same cached input -> identical results (determinism);
  - comparison covers >= 3 distinct policy_type samples.

These run entirely off the cached 4-model 485 file + golden fixture; they do NOT
call any provider. If the cached file is missing, the suite is skipped (never faked).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.construction_grading.best_quality_ai_draft import CACHED_4MODEL  # noqa: E402

if not CACHED_4MODEL.exists():  # pragma: no cover - environment guard
    pytest.skip("cached 4-model 485 predictions not available", allow_module_level=True)

from scripts.run_luban_best_quality_smoke import (  # noqa: E402
    SMOKE_SAMPLES,
    build_comparison,
    build_smoke_results,
    run_sample,
)


@pytest.fixture(scope="module")
def smoke():
    return build_smoke_results()


def test_smoke_has_at_least_three_policy_type_samples(smoke):
    ptypes = set()
    for entry in smoke:
        for pr in entry["best_quality"]["point_results"]:
            if pr.get("policy_type"):
                ptypes.add(pr["policy_type"])
    assert len(ptypes) >= 3, f"expected >=3 distinct policy_types, got {sorted(ptypes)}"


def test_comparison_covers_at_least_three_policy_types(smoke):
    comparison = build_comparison(smoke)
    ptypes = {pc["policy_type"] for entry in comparison for pc in entry["point_comparison"]}
    ptypes.discard(None)
    assert len(ptypes) >= 3, f"comparison must span >=3 policy types, got {sorted(ptypes)}"


def test_no_bad_certified_anywhere(smoke):
    for entry in smoke:
        assert entry["best_quality"]["bad_certified_count"] == 0, entry["case_id"]
        assert entry["deepseek_fast"]["bad_certified_count"] == 0, entry["case_id"]


def test_at_least_one_unsupported_point_is_fail_closed(smoke):
    fail_closed = []
    for entry in smoke:
        for pr in entry["best_quality"]["point_results"]:
            if pr["unsupported"]:
                # fail-closed: an unsupported positive must never be auto_certified
                assert pr["auto_certified"] is False, (entry["case_id"], pr["point_id"])
                fail_closed.append((entry["case_id"], pr["point_id"]))
    assert fail_closed, "expected at least one unsupported point fail-closed in best_quality"


def test_deterministic_repeat_run_is_identical():
    first = build_smoke_results()
    second = build_smoke_results()
    assert first == second, "best-quality smoke must be deterministic over cached input"


def test_run_sample_is_self_consistent():
    case_id, student_id, _ = SMOKE_SAMPLES[0]
    a = run_sample(case_id, student_id)
    b = run_sample(case_id, student_id)
    assert a == b
    assert a["best_quality"]["authority"] == "best_quality_4model_shadow"
    assert a["deepseek_fast"]["prediction_source"] == "cached_deepseek_v4_flash_485"
