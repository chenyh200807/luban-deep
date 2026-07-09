"""P-1 schema contract: LubanCaseScoringPoint field pin + claim ceiling + authority.

These are the §2.5② acceptance tests. The introspection reconciliation
(dataclass fields == registry canonical_fields) is the field-level protection
the plan §1.5C demands — it is what makes this a真"独立 typed schema", not a
name-only T2 registration.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from deeptutor.services.construction_grading.case_light_practice_contract import (
    CANONICAL_WRITE_ALLOWED,
    OFFICIAL_SCORE_ALLOWED,
    RUNTIME_INSTALL_ALLOWED,
    SCHEMA_ID,
    AcceptableVariant,
    AuthoritySourceError,
    LubanCaseScoringPoint,
    PointType,
    ScoringPointError,
    SourceRef,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REGISTRY = _REPO_ROOT / "contracts" / "schema_registry.yaml"


def _registry_canonical_fields() -> list[str]:
    payload = yaml.safe_load(_REGISTRY.read_text(encoding="utf-8"))
    for entry in payload.get("tier2_canonical_contracts") or []:
        if entry.get("name") == SCHEMA_ID:
            return list(entry.get("canonical_fields") or [])
    raise AssertionError(f"{SCHEMA_ID} not registered in tier2_canonical_contracts")


def _valid_point(**overrides) -> LubanCaseScoringPoint:
    base = dict(
        point_id="sp_1",
        sub_no="1",
        qid="2017::EXAM_X::E0::sub1",
        sub_qid="2017::EXAM_X::E0::sub1",
        statement="再用喷灯烘烤旧卷材槎口,并分层剥开",
        authority_source="official_answer",
        point_type=PointType.PROCEDURE,
        required_terms=("分层剥开",),
        acceptable_variants=(
            AcceptableVariant("逐层剥开", SourceRef("textbook_cited", "教材P123")),
        ),
        max_score=1.0,
        textbook_source_refs=(SourceRef("textbook_cited", "教材P123"),),
        answer_key_authority="exam_reference_answer",
    )
    base.update(overrides)
    return LubanCaseScoringPoint(**base)


def test_dataclass_fields_match_registry_both_ways():
    dataclass_fields = list(LubanCaseScoringPoint.__dataclass_fields__.keys())
    registry_fields = _registry_canonical_fields()
    assert dataclass_fields == registry_fields, (
        "LubanCaseScoringPoint fields drifted from registry canonical_fields "
        f"(dataclass={dataclass_fields} registry={registry_fields})"
    )


def test_point_type_enum_covers_the_six_types():
    assert {t.value for t in PointType} == {
        "程序",
        "条件",
        "记录",
        "合取子",
        "列举项",
        "计算步",
    }


def test_claim_ceiling_is_structurally_false():
    # A read-view grants NO scoring / write / install authority.
    assert OFFICIAL_SCORE_ALLOWED is False
    assert CANONICAL_WRITE_ALLOWED is False
    assert RUNTIME_INSTALL_ALLOWED is False


def test_valid_channel_one_point_constructs():
    point = _valid_point()
    assert point.authority_source == "official_answer"
    assert point.answer_key_authority == "exam_reference_answer"


def test_non_official_authority_source_is_rejected():
    # 判分权威(计分通道①)只认 official_answer — exam_reference_answer 在这里非法。
    with pytest.raises(AuthoritySourceError):
        _valid_point(authority_source="exam_reference_answer")


def test_illegitimate_answer_key_authority_is_rejected():
    with pytest.raises(AuthoritySourceError):
        _valid_point(answer_key_authority="owner_freeform")


def test_negative_max_score_is_rejected():
    # 2026-07-09 Codex 对抗核证伪:负 max_score 会让满答得分低于漏答。
    with pytest.raises(ScoringPointError):
        _valid_point(max_score=-0.5)
