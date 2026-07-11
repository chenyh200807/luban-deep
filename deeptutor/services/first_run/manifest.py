from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any

MANIFEST_PATH = Path(__file__).with_name("script_manifest.v1.json")
SCHEMA_ID = "first_run_script.v1"
QUESTION_KEYS = ("A", "B", "C", "D")


class FirstRunManifestError(ValueError):
    pass


class FirstRunManifestUnsigned(FirstRunManifestError):
    pass


class FirstRunManifestVersionConflict(FirstRunManifestError):
    pass


class FirstRunAnswerSetInvalid(FirstRunManifestError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validate_question(question: dict[str, Any]) -> None:
    question_id = str(question.get("question_id") or "").strip()
    if not question_id.startswith("first_run.v1:"):
        raise FirstRunManifestError(f"invalid_question_id:{question_id}")
    for key in ("source_question_id", "source_scoring_point_id", "concept_id", "concept_label"):
        if not str(question.get(key) or "").strip():
            raise FirstRunManifestError(f"missing_{key}:{question_id}")
    source_refs = [str(item or "").strip() for item in list(question.get("source_refs") or [])]
    if not source_refs or any(not item for item in source_refs):
        raise FirstRunManifestError(f"missing_source_refs:{question_id}")
    content = question.get("content") if isinstance(question.get("content"), dict) else {}
    options = content.get("options") if isinstance(content.get("options"), dict) else {}
    if tuple(options.keys()) != QUESTION_KEYS:
        raise FirstRunManifestError(f"invalid_options:{question_id}")
    right = str(content.get("right") or "").strip()
    if right not in options:
        raise FirstRunManifestError(f"invalid_right_answer:{question_id}")
    if not str(content.get("stem") or "").strip():
        raise FirstRunManifestError(f"missing_stem:{question_id}")


def load_first_run_manifest() -> dict[str, Any]:
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_id") != SCHEMA_ID:
        raise FirstRunManifestError("invalid_schema_id")
    questions = [dict(item) for item in list(raw.get("questions") or []) if isinstance(item, dict)]
    if len(questions) != 4:
        raise FirstRunManifestError("first_run_requires_exactly_four_questions")
    ids = [str(item.get("question_id") or "").strip() for item in questions]
    if len(set(ids)) != len(ids):
        raise FirstRunManifestError("duplicate_manifest_question_id")
    for question in questions:
        _validate_question(question)
        question["content_sha256"] = _sha256(question["content"])
        question["right"] = str(question["content"]["right"])
    manifest = deepcopy(raw)
    manifest["questions"] = questions
    manifest["script_version"] = f"{SCHEMA_ID}@{_sha256(raw)}"
    return manifest


def _require_signed_manifest(manifest: dict[str, Any]) -> None:
    unsigned: list[str] = []
    for question in list(manifest.get("questions") or []):
        if not isinstance(question, dict):
            continue
        question_id = str(question.get("question_id") or "").strip()
        content_sha256 = str(question.get("content_sha256") or "").strip()
        reviewer_ids = {
            reviewer_id
            for reviewer_id in (
                _reviewer_id_for_question(
                    item,
                    question_id=question_id,
                    content_sha256=content_sha256,
                )
                for item in list(question.get("review_refs") or [])
            )
            if reviewer_id
        }
        if question.get("review_status") != "signed" or len(reviewer_ids) < 2:
            unsigned.append(str(question.get("question_id") or "unknown"))
    if manifest.get("release_status") != "signed" or unsigned:
        raise FirstRunManifestUnsigned(",".join(unsigned) or "manifest_release_status")


def _reviewer_id_for_question(
    value: Any,
    *,
    question_id: str,
    content_sha256: str,
) -> str:
    parts = str(value or "").strip().split(":")
    if len(parts) < 6 or parts[0] != "teacher_review":
        return ""
    reviewer_id = parts[1].strip()
    reviewed_on = parts[2].strip()
    bound_question_id = ":".join(parts[3:-1]).strip()
    bound_content_sha256 = parts[-1].strip()
    try:
        date.fromisoformat(reviewed_on)
    except ValueError:
        return ""
    if (
        not reviewer_id
        or bound_question_id != question_id
        or bound_content_sha256 != content_sha256
    ):
        return ""
    return reviewer_id


def score_first_run_answers(
    *,
    script_version: str,
    answers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    manifest = load_first_run_manifest()
    if str(script_version or "").strip() != str(manifest["script_version"]):
        raise FirstRunManifestVersionConflict(str(script_version or ""))
    _require_signed_manifest(manifest)

    submitted: dict[str, dict[str, Any]] = {}
    for raw_answer in list(answers or []):
        item = dict(raw_answer or {})
        question_id = str(item.get("question_id") or "").strip()
        if question_id in submitted:
            raise FirstRunAnswerSetInvalid("duplicate_question_id")
        selected_key = str(item.get("selected_key") or "").strip()
        if selected_key not in QUESTION_KEYS:
            raise FirstRunAnswerSetInvalid(f"invalid_selected_key:{question_id}")
        try:
            duration_ms = int(item.get("duration_ms") or 0)
        except (TypeError, ValueError) as exc:
            raise FirstRunAnswerSetInvalid(f"invalid_duration_ms:{question_id}") from exc
        if duration_ms < 0 or duration_ms > 900_000:
            raise FirstRunAnswerSetInvalid(f"invalid_duration_ms:{question_id}")
        submitted[question_id] = {
            "selected_key": selected_key,
            "duration_ms": duration_ms,
        }

    questions = list(manifest["questions"])
    expected_ids = {str(item["question_id"]) for item in questions}
    if set(submitted) != expected_ids:
        raise FirstRunAnswerSetInvalid("answer_set_mismatch")

    scored: list[dict[str, Any]] = []
    for question in questions:
        question_id = str(question["question_id"])
        selected = submitted[question_id]
        right = str(question["content"]["right"])
        scored.append(
            {
                "question_id": question_id,
                "source_question_id": question["source_question_id"],
                "source_scoring_point_id": question["source_scoring_point_id"],
                "concept_id": question["concept_id"],
                "concept_label": question["concept_label"],
                "source_refs": list(question["source_refs"]),
                "content_sha256": question["content_sha256"],
                "learner_answer": selected["selected_key"],
                "correct_answer": right,
                "is_correct": selected["selected_key"] == right,
                "duration_ms": selected["duration_ms"],
            }
        )
    return scored


__all__ = [
    "FirstRunAnswerSetInvalid",
    "FirstRunManifestError",
    "FirstRunManifestUnsigned",
    "FirstRunManifestVersionConflict",
    "load_first_run_manifest",
    "score_first_run_answers",
]
