"""Tests for QuestionGradingArtifact Registry v0 (file-based admission gate).

Deterministic: builds in-memory from the golden projection. No DB, no provider
key, no RAG authority.
"""
from __future__ import annotations

from deeptutor.services.construction_grading import question_grading_artifacts as qga
from deeptutor.services.construction_grading import question_grading_registry as reg


def _registry() -> reg.QuestionGradingRegistry:
    return reg.build_default_registry()


# --- coverage / schema ---------------------------------------------------------


def test_registry_covers_twenty_questions():
    r = _registry()
    assert len(r.question_ids()) == 20


def test_build_registry_report_shape():
    report = reg.build_registry()
    assert len(report["questions"]) == 20
    summary = report["summary"]
    assert set(summary) == {"published_count", "draft_count", "blocked_count"}
    assert (
        summary["published_count"]
        + summary["draft_count"]
        + summary["blocked_count"]
        == 20
    )
    for row in report["questions"]:
        assert row["status"] in {"published", "draft", "blocked"}
        assert "reason" in row
        assert isinstance(row["source_weak_points"], list)
        assert isinstance(row["missing_policy_points"], list)


def test_published_artifact_carries_full_schema_v0():
    art = qga.build_question_grading_artifact("Q1-NA")
    assert art["schema_version"] == "question_grading_artifact.v0"
    assert art["artifact_id"] == f"Q1-NA::{qga.VERSION_ID}"
    assert art["status"] in {"published", "draft", "blocked"}
    assert "status_reason" in art
    assert "source_profile" in art
    assert "quality_gates" in art
    assert art["provenance"]["compiler_version"] == "qga_compiler_v0"
    assert art["provenance"]["content_hash"]


def test_every_scoring_point_has_required_schema_fields():
    for cid in qga.list_case_ids():
        art = qga.build_question_grading_artifact(cid)
        for sp in art["scoring_points"]:
            for field in (
                "point_id",
                "label",
                "max_score",
                "policy_type",
                "required_terms",
                "source_refs",
                "auto_certifiable",
                "knowledge_point_refs",
            ):
                assert field in sp, f"{cid}/{sp.get('point_id')} missing {field}"


# --- fail-closed lookup --------------------------------------------------------


def test_unknown_question_returns_artifact_missing_via_class():
    r = _registry()
    result = r.lookup("DOES-NOT-EXIST")
    assert result.found is False
    assert result.status == reg.ARTIFACT_MISSING
    assert result.artifact is None
    assert result.auto_certification_allowed is False


def test_get_artifact_unknown_question_is_artifact_missing():
    out = reg.get_question_grading_artifact("DOES-NOT-EXIST")
    assert out == {"artifact_missing": True, "question_id": "DOES-NOT-EXIST"}


def test_get_artifact_known_question_returns_artifact():
    out = reg.get_question_grading_artifact("Q1-NA")
    assert out.get("artifact_missing") is None
    assert out["question_id"] == "Q1-NA"
    assert out["status"] in {"published", "draft", "blocked"}


def test_auto_certification_unknown_question_blocks():
    assert reg.auto_certification_allowed("DOES-NOT-EXIST") is False


# --- runtime gate semantics ----------------------------------------------------


def test_published_allows_auto_certification():
    r = _registry()
    published = [q for q in r.question_ids() if r.lookup(q).status == "published"]
    assert published, "expected at least one published question"
    for qid in published:
        assert reg.auto_certification_allowed(qid, registry=r) is True


def test_draft_does_not_allow_auto_certification():
    # The golden bank no longer guarantees a draft sample (its former drafts carry
    # genuine declared-total/point-sum mismatches and are correctly blocked), so the
    # draft invariant is pinned with a synthetic structurally-valid draft artifact.
    synthetic = {
        "question_id": "QD-SYNTH-DRAFT",
        "version_id": "qga_v0_synth",
        "status": "draft",
        "scoring_points": [
            {
                "point_id": "P1",
                "label": "x",
                "max_score": 2.0,
                "policy_type": "qualitative",
                "auto_certifiable": False,
                "source_status": "missing",
            }
        ],
        "quality_gates": {"auto_certifiable_point_count": 0, "blocked_reasons": []},
    }
    r = reg.QuestionGradingRegistry([synthetic])
    assert r.lookup("QD-SYNTH-DRAFT").status == "draft"
    assert reg.auto_certification_allowed("QD-SYNTH-DRAFT", registry=r) is False
    # Any drafts that DO exist in the live bank must also never auto-certify.
    live = _registry()
    for qid in [q for q in live.question_ids() if live.lookup(q).status == "draft"]:
        assert reg.auto_certification_allowed(qid, registry=live) is False


def test_blocked_question_never_auto_certifies():
    r = _registry()
    blocked = [q for q in r.question_ids() if r.lookup(q).status == "blocked"]
    # Q15-NA: 0 auto-certifiable + high_risk_review point -> runtime blocks it.
    assert "Q15-NA" in blocked
    for qid in blocked:
        assert reg.auto_certification_allowed(qid, registry=r) is False


def test_zero_auto_without_high_risk_stays_draft():
    # 0 auto-certifiable points without a high_risk_review point -> draft, not blocked.
    # (Q20 used to pin this case while its point sum mismatched its declared total;
    # the split has since been repaired from official chunks, so a synthetic
    # artifact keeps pinning the rule independent of golden-data repairs.)
    synthetic = {
        "question_id": "QD-SYNTH-DRAFT",
        "version_id": "qga_v0_synth",
        "status": "draft",
        "scoring_points": [
            {
                "point_id": "P1",
                "label": "x",
                "max_score": 2.0,
                "policy_type": "qualitative",
                "auto_certifiable": False,
                "source_status": "missing",
            }
        ],
        "quality_gates": {"auto_certifiable_point_count": 0, "blocked_reasons": []},
    }
    r = reg.QuestionGradingRegistry([synthetic])
    assert r.lookup("QD-SYNTH-DRAFT").status == "draft"
    # And the genuine mismatch case stays blocked, never draft. (Q18's declared
    # total is officially unconfirmable — 2017 chunks conflict 15.0 vs 10.0 — so
    # its point sum 14.5 != declared 15 stays a real mismatch; Q20 was repaired
    # from official 2019 chunks and no longer serves as the mismatch exemplar.)
    assert _registry().lookup("Q18-1A434000").status == "blocked"


def test_per_point_auto_certification_respects_point_flag():
    r = _registry()
    art = reg.get_question_grading_artifact("Q1-NA", registry=r)
    assert art["status"] == "published"
    auto_pt = next(sp for sp in art["scoring_points"] if sp["auto_certifiable"])
    assert reg.auto_certification_allowed("Q1-NA", auto_pt["point_id"], registry=r) is True
    non_auto = [sp for sp in art["scoring_points"] if not sp["auto_certifiable"]]
    for sp in non_auto:
        assert (
            reg.auto_certification_allowed("Q1-NA", sp["point_id"], registry=r) is False
        )
    # unknown point in a published question -> fail closed.
    assert reg.auto_certification_allowed("Q1-NA", "NO-SUCH-POINT", registry=r) is False


def test_weak_source_point_is_never_auto_certifiable():
    for cid in qga.list_case_ids():
        art = qga.build_question_grading_artifact(cid)
        for sp in art["scoring_points"]:
            if sp["source_status"] != "ok":
                assert sp["auto_certifiable"] is False


def test_verified_flag_only_true_for_real_textbook_source():
    # No non-textbook ref is ever marked verified=True; no textbook ref without a quote.
    for cid in qga.list_case_ids():
        art = qga.build_question_grading_artifact(cid)
        for sp in art["scoring_points"]:
            for ref in sp["source_refs"]:
                if ref.get("verified") is True:
                    assert ref["source_type"] == "textbook"
                    assert ref.get("quote")
                if ref["source_type"] != "textbook":
                    assert ref.get("verified") is False


def test_no_source_fabrication_weak_points_have_no_textbook_ref():
    # A weak-source point must not carry any verified textbook ref (no fabricated anchor).
    for cid in qga.list_case_ids():
        art = qga.build_question_grading_artifact(cid)
        for sp in art["scoring_points"]:
            if sp["source_status"] != "ok":
                assert not any(
                    ref.get("verified") and ref.get("source_type") == "textbook"
                    for ref in sp["source_refs"]
                )


# --- determinism / versioning --------------------------------------------------


def test_content_hash_is_stable_across_rebuilds():
    a = qga.build_question_grading_artifact("Q10-1A422000")
    b = qga.build_question_grading_artifact("Q10-1A422000")
    assert a["provenance"]["content_hash"] == b["provenance"]["content_hash"]


def test_latest_version_wins_on_duplicate_question_id():
    old = qga.build_question_grading_artifact("Q1-NA")
    old = {**old, "version_id": "qga_v0_20260101", "status": "draft"}
    new = qga.build_question_grading_artifact("Q1-NA")  # version qga_v0_20260604
    r = reg.QuestionGradingRegistry([old, new])
    assert r.get_artifact("Q1-NA")["version_id"] == new["version_id"]
    assert r.lookup("Q1-NA").status == new["status"]


def test_publish_summary_counts_match_lookups():
    r = _registry()
    summary = r.publish_summary()
    expected = {"published": 0, "draft": 0, "blocked": 0}
    for qid in r.question_ids():
        expected[r.lookup(qid).status] += 1
    assert summary == expected
    assert summary["published"] + summary["draft"] + summary["blocked"] == 20
