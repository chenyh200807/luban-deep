from __future__ import annotations

import re
from copy import deepcopy

import pytest

from deeptutor.services.first_run import manifest as manifest_module
from deeptutor.services.first_run.manifest import (
    FirstRunAnswerSetInvalid,
    FirstRunManifestUnsigned,
    FirstRunManifestVersionConflict,
    load_first_run_manifest,
    score_first_run_answers,
)

QUESTION_IDS = [
    "first_run.v1:qigu_gebu",
    "first_run.v1:zhiliang_jihua",
    "first_run.v1:tianchongqiang_fangbie",
    "first_run.v1:zhuangpeishi_laji",
]


@pytest.fixture(autouse=True)
def registered_human_reviewers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        manifest_module,
        "load_first_run_reviewer_registry",
        lambda: {"teacher-one", "teacher-two"},
    )


def test_miniprogram_script_version_mirrors_canonical_manifest() -> None:
    source = (
        manifest_module.MANIFEST_PATH.parents[3]
        / "yousenwebview/packageDeeptutor/pages/first-run/script-data.js"
    ).read_text(encoding="utf-8")
    match = re.search(r'var SCRIPT_VERSION = "([^"]+)";', source)

    assert match is not None
    assert match.group(1) == load_first_run_manifest()["script_version"]


def _answers(*, first: str = "A") -> list[dict[str, object]]:
    selected = [first, "A", "A", "A"]
    return [
        {
            "question_id": question_id,
            "selected_key": selected[index],
            "duration_ms": 10_000 + index,
        }
        for index, question_id in enumerate(QUESTION_IDS)
    ]


def _signed_manifest() -> dict[str, object]:
    payload = deepcopy(load_first_run_manifest())
    payload["release_status"] = "signed"
    for question in payload["questions"]:  # type: ignore[index]
        question["review_status"] = "signed"
        question_id = str(question["question_id"])
        content_sha256 = str(question["content_sha256"])
        question["review_refs"] = [
            _human_review("teacher-one", question_id, content_sha256),
            _human_review("teacher-two", question_id, content_sha256),
        ]
    return payload


def _human_review(reviewer_id: str, question_id: str, content_sha256: str) -> dict[str, object]:
    return {
        "reviewer_id": reviewer_id,
        "reviewer_kind": "human",
        "reviewer_role": "teaching_reviewer",
        "verdict": "approve",
        "delegated": False,
        "reviewed_on": "2026-07-11",
        "question_id": question_id,
        "content_sha256": content_sha256,
    }


def test_manifest_exposes_four_stable_question_ids_and_hashes() -> None:
    manifest = load_first_run_manifest()

    assert manifest["schema_id"] == "first_run_script.v1"
    assert str(manifest["script_version"]).startswith("first_run_script.v1@")
    assert [item["question_id"] for item in manifest["questions"]] == QUESTION_IDS
    assert all(len(item["content_sha256"]) == 64 for item in manifest["questions"])
    assert all(item["right"] == "A" for item in manifest["questions"])


def test_unsigned_release_status_blocks_server_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 签发闸行为测试(disk-agnostic):磁盘 manifest 已由 owner 签发
    # (645e0e70),旧测试钉死"未签发磁盘态"属陈旧断言——闸门语义
    # (release_status 未 signed 必 fail-closed)在受控副本上验证。
    blocked = _signed_manifest()
    blocked["release_status"] = "blocked_pending_human_verdict"
    monkeypatch.setattr(manifest_module, "load_first_run_manifest", lambda: blocked)

    with pytest.raises(FirstRunManifestUnsigned, match="manifest_release_status"):
        score_first_run_answers(
            script_version=str(blocked["script_version"]),
            answers=_answers(),
        )


def test_unsigned_question_blocks_server_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unsigned = _signed_manifest()
    question = unsigned["questions"][0]  # type: ignore[index]
    question["review_status"] = "pending_dual_teacher_verdict"
    monkeypatch.setattr(manifest_module, "load_first_run_manifest", lambda: unsigned)

    with pytest.raises(FirstRunManifestUnsigned, match="first_run.v1:qigu_gebu"):
        score_first_run_answers(
            script_version=str(unsigned["script_version"]),
            answers=_answers(),
        )


def test_disk_manifest_stays_blocked_until_two_human_teaching_reviews() -> None:
    manifest = load_first_run_manifest()

    assert manifest["release_status"] == "blocked_pending_human_verdict"
    assert all(item["review_status"] == "pending_dual_teacher_verdict" for item in manifest["questions"])
    assert all(item["review_refs"] == [] for item in manifest["questions"])
    assert manifest["questions"][-1]["question_id"] == "first_run.v1:zhuangpeishi_laji"
    with pytest.raises(FirstRunManifestUnsigned, match="first_run.v1:qigu_gebu"):
        score_first_run_answers(script_version=str(manifest["script_version"]), answers=_answers())


def test_signed_gate_requires_distinct_reviewers_bound_to_question_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signed = _signed_manifest()
    question = signed["questions"][0]  # type: ignore[index]
    question_id = str(question["question_id"])
    content_sha256 = str(question["content_sha256"])
    same_reviewer = _human_review("teacher-one", question_id, content_sha256)
    question["review_refs"] = [same_reviewer, same_reviewer]
    monkeypatch.setattr(manifest_module, "load_first_run_manifest", lambda: signed)

    with pytest.raises(FirstRunManifestUnsigned, match=question_id):
        score_first_run_answers(
            script_version=str(signed["script_version"]),
            answers=_answers(),
        )

    question["review_refs"] = [
        same_reviewer,
        _human_review("teacher-two", question_id, "0" * 64),
    ]

    with pytest.raises(FirstRunManifestUnsigned, match=question_id):
        score_first_run_answers(
            script_version=str(signed["script_version"]),
            answers=_answers(),
        )


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("legacy", "teacher_review:teacher-one:2026-07-11:first_run.v1:qigu_gebu:hash"),
        ("reviewer_kind", "agent"),
        ("delegated", True),
        ("reviewer_role", "owner_delegate"),
        ("verdict", "pending"),
    ],
)
def test_signed_gate_rejects_non_human_or_delegated_review(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    value: object,
) -> None:
    signed = _signed_manifest()
    question = signed["questions"][0]  # type: ignore[index]
    if mutation == "legacy":
        question["review_refs"][0] = value
    else:
        question["review_refs"][0][mutation] = value
    monkeypatch.setattr(manifest_module, "load_first_run_manifest", lambda: signed)

    with pytest.raises(FirstRunManifestUnsigned, match=str(question["question_id"])):
        score_first_run_answers(script_version=str(signed["script_version"]), answers=_answers())


def test_signed_gate_rejects_unregistered_or_future_reviewers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signed = _signed_manifest()
    question = signed["questions"][0]  # type: ignore[index]
    question_id = str(question["question_id"])
    content_sha256 = str(question["content_sha256"])
    question["review_refs"][0] = _human_review("invented-reviewer", question_id, content_sha256)
    question["review_refs"][1]["reviewed_on"] = "2099-01-01"
    monkeypatch.setattr(manifest_module, "load_first_run_manifest", lambda: signed)

    with pytest.raises(FirstRunManifestUnsigned, match=question_id):
        score_first_run_answers(script_version=str(signed["script_version"]), answers=_answers())


def test_server_scores_against_signed_manifest_not_client_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signed = _signed_manifest()
    monkeypatch.setattr(manifest_module, "load_first_run_manifest", lambda: signed)

    scored = score_first_run_answers(
        script_version=str(signed["script_version"]),
        answers=_answers(first="B"),
    )

    assert scored[0]["learner_answer"] == "B"
    assert scored[0]["correct_answer"] == "A"
    assert scored[0]["is_correct"] is False
    assert all("client_score" not in item for item in scored)


def test_version_and_answer_set_mismatch_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signed = _signed_manifest()
    monkeypatch.setattr(manifest_module, "load_first_run_manifest", lambda: signed)

    with pytest.raises(FirstRunManifestVersionConflict):
        score_first_run_answers(script_version="first_run_script.v1@stale", answers=_answers())

    with pytest.raises(FirstRunAnswerSetInvalid, match="answer_set_mismatch"):
        score_first_run_answers(
            script_version=str(signed["script_version"]),
            answers=_answers()[:-1],
        )


def test_duplicate_question_id_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signed = _signed_manifest()
    monkeypatch.setattr(manifest_module, "load_first_run_manifest", lambda: signed)
    answers = _answers()
    answers[-1] = dict(answers[0])

    with pytest.raises(FirstRunAnswerSetInvalid, match="duplicate_question_id"):
        score_first_run_answers(
            script_version=str(signed["script_version"]),
            answers=answers,
        )
