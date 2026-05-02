from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib import error, parse, request
import json

from deeptutor.services.assessment.blueprint import AssessmentBlueprint, AssessmentSection, get_assessment_blueprint
from deeptutor.services.assessment.profile_probes import ProfileProbe, get_profile_probes


class AssessmentBlueprintUnavailable(RuntimeError):
    """Raised when a formal assessment cannot be created without breaking the blueprint."""


@dataclass(frozen=True)
class QuestionCandidate:
    source_question_id: str
    question_stem: str
    question_type: str
    chapter: str
    options: tuple[tuple[str, str], ...]
    answer: str
    difficulty: str = "medium"
    source_type: str = "DEV_FALLBACK"
    source_chunk_id: str = ""
    node_code: str = ""
    source_meta: dict[str, Any] | None = None


class AssessmentQuestionProvider(Protocol):
    def get_candidates(
        self,
        section: AssessmentSection,
        *,
        limit: int,
        exclude_source_ids: set[str],
    ) -> list[QuestionCandidate]:
        ...


class StaticAssessmentQuestionProvider:
    def __init__(self, candidates: list[QuestionCandidate]) -> None:
        self._candidates = list(candidates)

    def get_candidates(
        self,
        section: AssessmentSection,
        *,
        limit: int,
        exclude_source_ids: set[str],
    ) -> list[QuestionCandidate]:
        selected: list[QuestionCandidate] = []
        question_types = set(section.question_types) | set(section.fallback_question_types)
        for candidate in self._candidates:
            if candidate.source_question_id in exclude_source_ids:
                continue
            if candidate.question_type not in question_types and candidate.source_type != "DEV_FALLBACK":
                continue
            selected.append(candidate)
            if len(selected) >= limit:
                break
        return selected


class SupabaseAssessmentQuestionProvider:
    def __init__(self, *, env_file: str | Path = ".env") -> None:
        self._env_file = Path(env_file)

    def get_candidates(
        self,
        section: AssessmentSection,
        *,
        limit: int,
        exclude_source_ids: set[str],
    ) -> list[QuestionCandidate]:
        base_url, api_key = self._supabase_config()
        question_types = tuple(dict.fromkeys(section.question_types + section.fallback_question_types))
        query_type_groups = [(question_type,) for question_type in question_types]
        if len(query_type_groups) > 1:
            query_type_groups.append(question_types)
        if "calculation" in question_types or "case_study" in question_types:
            query_type_groups.append(("single_choice", "multi_choice"))
        candidates: list[QuestionCandidate] = []
        live_excludes = set(exclude_source_ids)
        for type_group in query_type_groups:
            candidates.extend(
                self._get_candidates_for_types(
                    base_url,
                    api_key,
                    section,
                    question_types=type_group,
                    limit=limit - len(candidates),
                    exclude_source_ids=live_excludes,
                )
            )
            live_excludes.update(item.source_question_id for item in candidates)
            if len(candidates) >= limit:
                break
        return candidates[:limit]

    def _get_candidates_for_types(
        self,
        base_url: str,
        api_key: str,
        section: AssessmentSection,
        *,
        question_types: tuple[str, ...],
        limit: int,
        exclude_source_ids: set[str],
    ) -> list[QuestionCandidate]:
        if limit <= 0:
            return []
        filters: dict[str, str] = {
            "select": ",".join(
                (
                    "id",
                    "question_stem",
                    "stem",
                    "question_type",
                    "source_type",
                    "source_chunk_id",
                    "node_code",
                    "source_meta",
                    "options",
                    "correct_answer",
                    "difficulty",
                    "tags",
                )
            ),
            "limit": str(max(limit * 3, limit)),
            "order": "id.asc",
        }
        if question_types:
            filters["question_type"] = f"in.({','.join(question_types)})"
        if section.source_types:
            filters["source_type"] = f"in.({','.join(section.source_types)})"
        numeric_excludes = [str(item) for item in sorted(exclude_source_ids) if str(item).isdigit()]
        if numeric_excludes:
            escaped = ",".join(numeric_excludes)
            if escaped:
                filters["id"] = f"not.in.({escaped})"

        rows = self._query(base_url, api_key, filters)
        candidates: list[QuestionCandidate] = []
        for row in rows:
            candidate = self._candidate_from_row(row)
            if candidate is None:
                continue
            candidates.append(candidate)
            if len(candidates) >= limit:
                break
        return candidates

    def _query(self, base_url: str, api_key: str, filters: dict[str, str]) -> list[dict[str, Any]]:
        encoded = parse.urlencode(filters)
        req = request.Request(
            f"{base_url}/rest/v1/questions_bank?{encoded}",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
            },
            method="GET",
        )
        try:
            with request.urlopen(req, timeout=15) as response:
                payload = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AssessmentBlueprintUnavailable(f"Supabase questions_bank query failed: HTTP {exc.code} {body}") from exc
        return list(json.loads(payload or "[]"))

    def _supabase_config(self) -> tuple[str, str]:
        env_file = self._read_env_file(self._env_file)
        url = (
            os.getenv("SUPABASE_URL")
            or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
            or env_file.get("SUPABASE_URL")
            or env_file.get("NEXT_PUBLIC_SUPABASE_URL")
            or ""
        ).rstrip("/")
        key = (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_KEY")
            or os.getenv("SUPABASE_ANON_KEY")
            or env_file.get("SUPABASE_SERVICE_ROLE_KEY")
            or env_file.get("SUPABASE_KEY")
            or env_file.get("SUPABASE_ANON_KEY")
            or ""
        )
        if not url or not key:
            raise AssessmentBlueprintUnavailable("Supabase config missing for formal assessment")
        return url, key

    @staticmethod
    def _read_env_file(path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        values: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'").strip('"')
        return values

    @staticmethod
    def _candidate_from_row(row: dict[str, Any]) -> QuestionCandidate | None:
        source_id = str(row.get("id") or "").strip()
        stem = str(row.get("question_stem") or row.get("stem") or "").strip()
        options = _normalize_options(row.get("options"))
        answer = _normalize_answer(row.get("correct_answer"))
        if not source_id or not stem or not options or not answer:
            return None
        return QuestionCandidate(
            source_question_id=source_id,
            question_stem=stem,
            question_type=str(row.get("question_type") or "single_choice").strip() or "single_choice",
            chapter=_chapter_from_row(row),
            options=tuple(options),
            answer=answer,
            difficulty=str(row.get("difficulty") or "medium").strip() or "medium",
            source_type=str(row.get("source_type") or "").strip(),
            source_chunk_id=str(row.get("source_chunk_id") or "").strip(),
            node_code=str(row.get("node_code") or "").strip(),
            source_meta=dict(row.get("source_meta") or {}) if isinstance(row.get("source_meta"), dict) else {},
        )


class AssessmentBlueprintService:
    def __init__(
        self,
        *,
        blueprint: AssessmentBlueprint | None = None,
        provider: AssessmentQuestionProvider,
        fallback_provider: AssessmentQuestionProvider | None = None,
        allow_dev_fallback: bool = False,
    ) -> None:
        self._blueprint = blueprint or get_assessment_blueprint("diagnostic_v1")
        self._provider = provider
        self._fallback_provider = fallback_provider
        self._allow_dev_fallback = allow_dev_fallback

    @property
    def blueprint(self) -> AssessmentBlueprint:
        return self._blueprint

    def create_session(self, *, user_id: str, count: int = 20) -> dict[str, Any]:
        requested_count = max(1, int(count or self._blueprint.requested_count))
        if requested_count != self._blueprint.requested_count:
            requested_count = self._blueprint.requested_count

        client_questions: list[dict[str, Any]] = []
        session_questions: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []
        exclude_source_ids: set[str] = set()
        profile_probe_iter = iter(get_profile_probes())
        fallback_used = False

        for section in self._blueprint.sections:
            section_question_ids: list[str] = []
            if section.scored:
                try:
                    candidates = self._provider.get_candidates(
                        section,
                        limit=section.count,
                        exclude_source_ids=exclude_source_ids,
                    )
                except AssessmentBlueprintUnavailable:
                    if not self._allow_dev_fallback:
                        raise
                    candidates = []
                if len(candidates) < section.count and self._allow_dev_fallback and self._fallback_provider:
                    fallback_candidates = self._fallback_provider.get_candidates(
                        section,
                        limit=section.count - len(candidates),
                        exclude_source_ids=exclude_source_ids | {item.source_question_id for item in candidates},
                    )
                    candidates.extend(fallback_candidates)
                    fallback_used = True
                if len(candidates) < section.count:
                    raise AssessmentBlueprintUnavailable(
                        f"Assessment blueprint {self._blueprint.version} section {section.id} "
                        f"requires {section.count} scored questions, found {len(candidates)}"
                    )
                for candidate in candidates[: section.count]:
                    exclude_source_ids.add(candidate.source_question_id)
                    question_id = _make_question_id(candidate.source_question_id, len(client_questions) + 1)
                    section_question_ids.append(question_id)
                    client, stored = _build_scored_question(question_id, section, candidate)
                    client_questions.append(client)
                    session_questions.append(stored)
            else:
                for _ in range(section.count):
                    try:
                        probe = next(profile_probe_iter)
                    except StopIteration as exc:
                        raise AssessmentBlueprintUnavailable("Not enough built-in profile probes") from exc
                    question_id = _make_question_id(probe.id, len(client_questions) + 1)
                    section_question_ids.append(question_id)
                    client, stored = _build_profile_probe_question(question_id, section, probe)
                    client_questions.append(client)
                    session_questions.append(stored)

            sections.append(
                {
                    "section_id": section.id,
                    "label": section.label,
                    "count": section.count,
                    "scored": section.scored,
                    "question_ids": section_question_ids,
                }
            )

        delivered_count = len(client_questions)
        if delivered_count != self._blueprint.requested_count:
            raise AssessmentBlueprintUnavailable(
                f"Assessment blueprint {self._blueprint.version} delivered {delivered_count}, "
                f"expected {self._blueprint.requested_count}"
            )
        quiz_id = f"quiz_{uuid.uuid4().hex[:10]}"
        return {
            "quiz_id": quiz_id,
            "user_id": user_id,
            "questions": client_questions,
            "session_questions": session_questions,
            "blueprint_version": self._blueprint.version,
            "sections": sections,
            "requested_count": requested_count,
            "delivered_count": delivered_count,
            "scored_count": self._blueprint.scored_count,
            "profile_count": self._blueprint.profile_count,
            "available_count": delivered_count,
            "question_bank_size": delivered_count,
            "unique_source_question_count": len({item["source_question_id"] for item in session_questions}),
            "shortfall_count": 0,
            "fallback_used": fallback_used,
        }


def _make_question_id(source_id: str, index: int) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in str(source_id or "q"))[:40].strip("_") or "q"
    return f"{normalized}__{index:02d}_{uuid.uuid4().hex[:6]}"


def _build_scored_question(
    question_id: str,
    section: AssessmentSection,
    candidate: QuestionCandidate,
) -> tuple[dict[str, Any], dict[str, Any]]:
    provenance = {
        "source_table": "questions_bank" if candidate.source_type != "DEV_FALLBACK" else "dev_fallback",
        "question_id": candidate.source_question_id,
        "source_question_id": candidate.source_question_id,
        "source_type": candidate.source_type,
        "source_chunk_id": candidate.source_chunk_id,
        "node_code": candidate.node_code,
        "source_meta": dict(candidate.source_meta or {}),
    }
    client = {
        "question_id": question_id,
        "source_question_id": candidate.source_question_id,
        "question_stem": candidate.question_stem,
        "question_type": candidate.question_type,
        "difficulty": candidate.difficulty,
        "chapter": candidate.chapter or section.label,
        "section_id": section.id,
        "section_label": section.label,
        "scored": True,
        "provenance": provenance,
        "options": [{"key": key, "text": text} for key, text in candidate.options],
    }
    stored = {
        **client,
        "answer": candidate.answer,
    }
    return client, stored


def _build_profile_probe_question(
    question_id: str,
    section: AssessmentSection,
    probe: ProfileProbe,
) -> tuple[dict[str, Any], dict[str, Any]]:
    provenance = {
        "source_table": "profile_probe_bank",
        "question_id": probe.id,
        "source_question_id": probe.id,
        "source_type": "PROFILE_PROBE",
        "source_chunk_id": "",
        "node_code": probe.topic,
        "source_meta": {"topic": probe.topic},
    }
    options = [{"key": key, "text": text, "value": value} for key, text, value in probe.options]
    client = {
        "question_id": question_id,
        "source_question_id": probe.id,
        "question_stem": probe.question_stem,
        "question_type": "profile_probe",
        "difficulty": "profile",
        "chapter": section.label,
        "section_id": section.id,
        "section_label": section.label,
        "scored": False,
        "profile_topic": probe.topic,
        "provenance": provenance,
        "options": options,
    }
    stored = {
        **client,
        "answer": "",
        "option_values": {key: value for key, _text, value in probe.options},
    }
    return client, stored


def _normalize_options(value: Any) -> list[tuple[str, str]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if isinstance(value, dict):
        return [(str(key).strip(), str(text).strip()) for key, text in sorted(value.items()) if str(key).strip()]
    if isinstance(value, list):
        items: list[tuple[str, str]] = []
        for item in value:
            if isinstance(item, dict):
                key = str(item.get("key") or item.get("label") or "").strip()
                text = str(item.get("text") or item.get("value") or item.get("content") or "").strip()
                if key:
                    items.append((key, text))
        return items
    return []


def _normalize_answer(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(item).strip().upper() for item in value)
    if isinstance(value, dict):
        for key in ("answer", "key", "correct"):
            if value.get(key):
                return _normalize_answer(value.get(key))
    return str(value or "").strip().upper()


def _chapter_from_row(row: dict[str, Any]) -> str:
    tags = row.get("tags")
    if isinstance(tags, dict):
        for key in ("chapter", "topic", "module"):
            if tags.get(key):
                return str(tags[key]).strip()
    if isinstance(tags, list) and tags:
        return str(tags[0]).strip()
    node_code = str(row.get("node_code") or "").strip()
    return node_code or "综合能力"
