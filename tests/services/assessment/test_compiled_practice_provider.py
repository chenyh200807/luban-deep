"""编译轻练读侧聚合 provider（表单 v2 §6.2-v2）。

覆盖:聚合源过滤 eligible∧signed 单选、元数据透传、pack 级 fail-closed、
题源路由、读侧零写入(provenance 如实指认非 questions_bank)。
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from deeptutor.services.assessment import compiled_practice_provider as cpp
from deeptutor.services.assessment.blueprint import (
    COMPILED_PRACTICE_QUESTION_SOURCE,
    COMPILED_PRACTICE_SOURCE_TYPE,
    AssessmentSection,
)
from deeptutor.services.assessment.blueprint_service import (
    QuestionCandidate,
    _build_scored_question,
)
from deeptutor.services.luban_lesson import practice_html


def _signed_review(content_sha256: str) -> dict[str, Any]:
    return {
        "status": "signed",
        "verdict": "approved",
        "reviewed_content_sha256": content_sha256,
        "signatures": [
            {"role": "teaching", "reviewer_id": "t1", "signed_at": "2026-08-01T00:00:00Z"},
            {"role": "scoring", "reviewer_id": "s1", "signed_at": "2026-08-01T00:00:00Z"},
        ],
        "checks": {
            "source_verified": True,
            "answer_verified": True,
            "diagnosis_verified": True,
            "longest_option_checked": True,
            "template_leakage_checked": True,
        },
    }


def _item(
    variant_id: str,
    *,
    fact_id: str = "c01-fact-a",
    answer_type: str = "single_choice",
    signed: bool = True,
    revoked: bool = False,
    correct_index: int = 0,
    n_correct: int = 1,
) -> dict[str, Any]:
    content_sha = "c" * 64
    options = []
    for i in range(4):
        options.append(
            {
                "text": f"选项{i} of {variant_id}",
                "is_correct": bool(
                    i == correct_index or (n_correct > 1 and i < n_correct)
                ),
            }
        )
    item: dict[str, Any] = {
        "answer_type": answer_type,
        "rule_group": "施工缝·位置",
        "stem": f"题干 {variant_id}",
        "options": options,
        "variant_id": variant_id,
        "surface_id": "practice.html",
        "anchor": "compiled_html:artifacts/x/practice.dc.html#Q1",
        "source_anchor": "kc:1A413030_103_0196:0",
        "source_sha256": "a" * 64,
        "fact_id": fact_id,
        "skeleton_id": "c01-skel-构件留置位置枚举",
        "probe_role": "anchor",
        "revoked": revoked,
        "revocation_refs": [],
        "content_sha256": content_sha,
    }
    item["review"] = (
        _signed_review(content_sha)
        if signed
        else {"status": "pending", "verdict": "pending", "signatures": [], "checks": {}}
    )
    return item


def _compiled_section(packs: tuple[str, ...] = ("C01",), count: int = 2) -> AssessmentSection:
    return AssessmentSection(
        id="pr2_single_main_structure",
        label="真题变式客观 · 主体结构",
        count=count,
        scored=True,
        question_types=("single_choice",),
        question_source=COMPILED_PRACTICE_QUESTION_SOURCE,
        compiled_packs=packs,
        ability_dimension="core_knowledge",
    )


class _StubPracticeHtml:
    """load_compiled_practice / _eligible / PracticeHtmlInvalid 的最小替身。

    _eligible 直接复用生产同一谓词——测试不建平行资格判定。
    """

    PracticeHtmlInvalid = practice_html.PracticeHtmlInvalid
    _eligible = staticmethod(practice_html._eligible)

    def __init__(self, authorities: dict[str, Any]) -> None:
        self._authorities = authorities

    def load_compiled_practice(self, pack_id: str):
        value = self._authorities.get(pack_id)
        if isinstance(value, Exception):
            raise value
        return value


def _provider(authorities: dict[str, Any]) -> cpp.CompiledPracticeAssessmentQuestionProvider:
    provider = cpp.CompiledPracticeAssessmentQuestionProvider()
    provider._practice_html = _StubPracticeHtml(authorities)  # type: ignore[assignment]
    return provider


def test_only_eligible_signed_single_choice_items_are_aggregated() -> None:
    provider = _provider(
        {
            "C01": {
                "items": [
                    _item("C01-ok-1", fact_id="f1"),
                    _item("C01-pending", fact_id="f2", signed=False),
                    _item("C01-revoked", fact_id="f3", revoked=True),
                    _item("C01-multi", fact_id="f4", answer_type="multi_choice"),
                ]
            }
        }
    )
    candidates = provider.get_candidates(
        _compiled_section(), limit=10, exclude_source_ids=set(), selection_seed="s"
    )
    assert [c.source_question_id for c in candidates] == ["C01-ok-1"]
    assert candidates[0].question_type == "single_choice"
    assert candidates[0].answer == "A"


def test_metadata_passthrough_pack_leaf_scoring_point_and_anchor() -> None:
    provider = _provider({"C01": {"items": [_item("C01-ok-1", fact_id="f1")]}})
    candidate = provider.get_candidates(
        _compiled_section(), limit=1, exclude_source_ids=set(), selection_seed="s"
    )[0]
    meta = candidate.source_meta or {}
    assert meta["aggregation"] == "compiled_practice_readside"
    assert meta["pack_id"] == "C01"
    assert meta["fact_id"] == "f1"
    assert meta["skeleton_id"] == "c01-skel-构件留置位置枚举"
    assert meta["rule_group"] == "施工缝·位置"
    assert meta["source_anchor"] == "kc:1A413030_103_0196:0"
    assert meta["difficulty_anchor"] == "kc:1A413030_103_0196:0"
    assert meta["semantic_signature"] == "compiled:C01:f1"
    assert candidate.node_code == "1A413030"
    assert candidate.source_type == COMPILED_PRACTICE_SOURCE_TYPE


def test_pack_gate_failure_is_fail_closed_per_pack_not_half_open() -> None:
    provider = _provider(
        {
            "C01": practice_html.PracticeHtmlInvalid("practice_authority_digest_mismatch"),
            "C04": {"items": [_item("C04-ok-1", fact_id="f9")]},
        }
    )
    candidates = provider.get_candidates(
        _compiled_section(packs=("C01", "C04")),
        limit=10,
        exclude_source_ids=set(),
        selection_seed="s",
    )
    assert [c.source_question_id for c in candidates] == ["C04-ok-1"]


def test_malformed_single_choice_contract_is_rejected() -> None:
    provider = _provider(
        {
            "C01": {
                "items": [
                    _item("C01-two-correct", fact_id="f1", n_correct=2),
                    _item("C01-ok", fact_id="f2"),
                ]
            }
        }
    )
    candidates = provider.get_candidates(
        _compiled_section(), limit=10, exclude_source_ids=set(), selection_seed="s"
    )
    assert [c.source_question_id for c in candidates] == ["C01-ok"]


def test_exclude_source_ids_and_limit_are_respected() -> None:
    provider = _provider(
        {
            "C01": {
                "items": [
                    _item("C01-a", fact_id="f1"),
                    _item("C01-b", fact_id="f2"),
                    _item("C01-c", fact_id="f3"),
                ]
            }
        }
    )
    candidates = provider.get_candidates(
        _compiled_section(count=2),
        limit=2,
        exclude_source_ids={"C01-a"},
        selection_seed="s",
    )
    ids = {c.source_question_id for c in candidates}
    assert len(candidates) == 2 and "C01-a" not in ids


def test_provenance_names_compiled_authority_not_questions_bank() -> None:
    provider = _provider({"C01": {"items": [_item("C01-ok-1", fact_id="f1")]}})
    candidate = provider.get_candidates(
        _compiled_section(), limit=1, exclude_source_ids=set(), selection_seed="s"
    )[0]
    client, stored = _build_scored_question("q_01", _compiled_section(), candidate)
    assert client["provenance"]["source_table"] == "luban_compiled_practice_authority"
    assert stored["answer"] == "A"
    # 答案面不进客户端投影
    assert "answer" not in client


def test_source_routing_dispatches_by_section_declaration() -> None:
    class _DefaultProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_candidates(self, section, **_kwargs):
            self.calls.append(section.id)
            return []

        def question_bank_size(self) -> int:
            return 4635

    default = _DefaultProvider()
    routed = cpp.SourceRoutedAssessmentQuestionProvider(
        default_provider=default,
        compiled_provider=_provider({"C01": {"items": [_item("C01-ok-1")]}}),
    )
    bank_section = AssessmentSection(
        id="pr2_objective_multi",
        label="练习册多选",
        count=1,
        scored=True,
        question_types=("multi_choice",),
    )
    compiled = routed.get_candidates(
        _compiled_section(), limit=1, exclude_source_ids=set(), selection_seed="s"
    )
    assert [c.source_question_id for c in compiled] == ["C01-ok-1"]
    assert routed.get_candidates(
        bank_section, limit=1, exclude_source_ids=set(), selection_seed="s"
    ) == []
    assert default.calls == ["pr2_objective_multi"]
    # 其余能力（规模/持久化）委托默认供给面，不建第二 authority。
    assert routed.question_bank_size() == 4635


def test_readside_only_provider_has_no_write_surface() -> None:
    # 单一权威铁律的机械检查：模块源码不得出现任何 questions_bank 写路径。
    source = inspect.getsource(cpp)
    for forbidden in ("_rest_upsert", "POST", "PATCH", "DELETE", "insert", "upsert"):
        assert forbidden not in source
    # 也不得读 questions_bank.difficulty（难度权威=变体 anchor）。
    assert 'get("difficulty")' not in source


def test_candidate_projection_never_leaks_option_answer_face() -> None:
    provider = _provider({"C01": {"items": [_item("C01-ok-1", fact_id="f1")]}})
    candidate = provider.get_candidates(
        _compiled_section(), limit=1, exclude_source_ids=set(), selection_seed="s"
    )[0]
    assert isinstance(candidate, QuestionCandidate)
    for _letter, text in candidate.options:
        assert "is_correct" not in text
    flat = repr(candidate.options)
    for forbidden in ("temptation", "loss_reason", "fix"):
        assert forbidden not in flat


@pytest.mark.parametrize("missing", ["stem", "variant_id"])
def test_items_missing_required_fields_are_skipped(missing: str) -> None:
    broken = _item("C01-broken", fact_id="f1")
    broken[missing if missing != "variant_id" else "variant_id"] = ""
    if missing == "stem":
        broken["stem"] = ""
    provider = _provider({"C01": {"items": [broken, _item("C01-ok", fact_id="f2")]}})
    candidates = provider.get_candidates(
        _compiled_section(), limit=10, exclude_source_ids=set(), selection_seed="s"
    )
    assert [c.source_question_id for c in candidates] == ["C01-ok"]
