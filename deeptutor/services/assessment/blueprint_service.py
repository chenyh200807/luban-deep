from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import threading
from typing import Any, Protocol
from urllib import error, parse, request
import json
import re
import uuid

from deeptutor.services.assessment.blueprint import (
    MIN_FORM_ROTATION_COUNT,
    TARGET_FORM_ROTATION_COUNT,
    AssessmentBlueprint,
    AssessmentSection,
    get_assessment_blueprint,
)
from deeptutor.services.assessment.profile_probes import ProfileProbe, get_profile_probes
from deeptutor.services.questions_bank_liveness import (
    LIVE_ROW_FILTER_COLUMN,
    LIVE_ROW_FILTER_OPERATOR,
    apply_live_row_filter,
    soft_delete_filter_enabled,
)
from deeptutor.services.taxonomy.construction_taxonomy import display_taxonomy_label
from deeptutor.services.taxonomy.learning_topic_resolver import (
    normalize_learning_topic_text,
    resolve_learning_topic_from_payload,
)

_CHAPTER_CODE_RE = re.compile(r"^1A\d{3,6}(?:-\d{2})?(?:-[a-z])?$", re.IGNORECASE)
_ASSESSMENT_FORM_COUNT = TARGET_FORM_ROTATION_COUNT
_FORM_CACHE_LOCK = threading.RLock()
_FORM_CACHE: dict[str, "_AssessmentFormBank"] = {}
_MULTI_PROMPT_STEM_RE = re.compile(r"(?:^|\n)\s*(?:【?\s*问题\s*】?\s*)?\d+\s*[\.．、:：]")


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


@dataclass(frozen=True)
class _AssessmentFormUnit:
    section_id: str
    scored: bool
    item: QuestionCandidate | ProfileProbe


@dataclass(frozen=True)
class _AssessmentForm:
    form_id: str
    form_index: int
    units: tuple[_AssessmentFormUnit, ...]
    fallback_used: bool


@dataclass(frozen=True)
class _AssessmentFormBank:
    forms: tuple[_AssessmentForm, ...]
    question_bank_size: int
    form_source: str = ""


class AssessmentQuestionProvider(Protocol):
    def get_candidates(
        self,
        section: AssessmentSection,
        *,
        limit: int,
        exclude_source_ids: set[str],
        selection_seed: str = "",
        avoid_chapters: set[str] | None = None,
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
        selection_seed: str = "",
        avoid_chapters: set[str] | None = None,
    ) -> list[QuestionCandidate]:
        question_types = set(section.question_types) | set(section.fallback_question_types)
        candidates: list[QuestionCandidate] = []
        for candidate in self._candidates:
            if candidate.source_question_id in exclude_source_ids:
                continue
            if candidate.question_type not in question_types and candidate.source_type != "DEV_FALLBACK":
                continue
            candidates.append(candidate)
        return _select_diagnostic_candidates(
            candidates,
            section=section,
            limit=limit,
            selection_seed=selection_seed,
            avoid_chapters=avoid_chapters or set(),
        )

    def question_bank_size(self) -> int:
        return len(self._candidates)


class SupabaseAssessmentQuestionProvider:
    def __init__(self, *, env_file: str | Path = ".env") -> None:
        self._env_file = Path(env_file)

    def get_candidates(
        self,
        section: AssessmentSection,
        *,
        limit: int,
        exclude_source_ids: set[str],
        selection_seed: str = "",
        avoid_chapters: set[str] | None = None,
    ) -> list[QuestionCandidate]:
        base_url, api_key = self._supabase_config()
        question_types = list(dict.fromkeys(section.question_types + section.fallback_question_types))
        if "calculation" in question_types or "case_study" in question_types:
            question_types.extend(["single_choice", "multi_choice"])
        question_types_tuple = tuple(dict.fromkeys(question_types))
        pool_limit = max(limit * 80, 160)
        candidates = self._get_candidates_for_types(
            base_url,
            api_key,
            section,
            question_types=question_types_tuple,
            limit=pool_limit,
            exclude_source_ids=exclude_source_ids,
            selection_seed=f"{selection_seed}:{section.id}:{','.join(question_types_tuple)}",
            offset=_selection_offset(selection_seed, section.id),
        )
        selected = self._select_from_candidate_pool(
            candidates,
            section=section,
            limit=limit,
            selection_seed=selection_seed,
            avoid_chapters=avoid_chapters or set(),
        )
        if len(selected) >= limit:
            return selected
        for offset in (1000, 2000, 3000, 4000):
            fallback_candidates = self._get_candidates_for_types(
                base_url,
                api_key,
                section,
                question_types=question_types_tuple,
                limit=pool_limit,
                exclude_source_ids=exclude_source_ids,
                selection_seed=f"{selection_seed}:{section.id}:offset:{offset}",
                offset=offset,
            )
            candidates.extend(fallback_candidates)
            selected = self._select_from_candidate_pool(
                candidates,
                section=section,
                limit=limit,
                selection_seed=selection_seed,
                avoid_chapters=avoid_chapters or set(),
            )
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def _select_from_candidate_pool(
        candidates: list[QuestionCandidate],
        *,
        section: AssessmentSection,
        limit: int,
        selection_seed: str,
        avoid_chapters: set[str],
    ) -> list[QuestionCandidate]:
        unique_candidates = list({item.source_question_id: item for item in candidates}.values())
        return _select_diagnostic_candidates(
            unique_candidates,
            section=section,
            limit=limit,
            selection_seed=selection_seed,
            avoid_chapters=avoid_chapters,
        )

    def _get_candidates_for_types(
        self,
        base_url: str,
        api_key: str,
        section: AssessmentSection,
        *,
        question_types: tuple[str, ...],
        limit: int,
        exclude_source_ids: set[str],
        selection_seed: str,
        offset: int = 0,
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
            "limit": str(max(limit, 1)),
            "order": "id.asc",
        }
        if offset > 0:
            filters["offset"] = str(offset)
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
            candidate = self._candidate_from_row(row, section)
            if candidate is None:
                continue
            candidates.append(candidate)
        return _stable_shuffle_candidates(candidates, selection_seed)

    def _query(self, base_url: str, api_key: str, filters: dict[str, str]) -> list[dict[str, Any]]:
        # 软删收权（task#31 2026-08-02）：组卷候选查询唯一入口，注入
        # retired_at=is.null——软删行不得进正式测评卷。谓词权威在
        # deeptutor/services/questions_bank_liveness.py，不在本文件手写。
        return self._rest_get(
            base_url, api_key, "questions_bank", apply_live_row_filter(dict(filters))
        )

    def _rest_get(
        self,
        base_url: str,
        api_key: str,
        table: str,
        filters: dict[str, str],
    ) -> list[dict[str, Any]]:
        encoded = parse.urlencode(filters)
        req = request.Request(
            f"{base_url}/rest/v1/{table}?{encoded}",
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
            raise AssessmentBlueprintUnavailable(f"Supabase {table} query failed: HTTP {exc.code} {body}") from exc
        return list(json.loads(payload or "[]"))

    def _rest_upsert(
        self,
        base_url: str,
        api_key: str,
        table: str,
        rows: list[dict[str, Any]],
        *,
        on_conflict: str,
    ) -> None:
        encoded = parse.urlencode({"on_conflict": on_conflict})
        req = request.Request(
            f"{base_url}/rest/v1/{table}?{encoded}",
            data=json.dumps(rows, ensure_ascii=False).encode("utf-8"),
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=30):
                return
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AssessmentBlueprintUnavailable(f"Supabase {table} upsert failed: HTTP {exc.code} {body}") from exc

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
    def _candidate_from_row(row: dict[str, Any], section: AssessmentSection) -> QuestionCandidate | None:
        source_id = str(row.get("id") or "").strip()
        stem = str(row.get("question_stem") or row.get("stem") or "").strip()
        options = _normalize_options(row.get("options"))
        answer = _normalize_answer_for_options(row.get("correct_answer"), options)
        if not source_id or not stem or not options or not answer:
            return None
        question_type = str(row.get("question_type") or "single_choice").strip() or "single_choice"
        candidate = QuestionCandidate(
            source_question_id=source_id,
            question_stem=stem,
            question_type=question_type,
            chapter=_chapter_from_row(row, section),
            options=tuple(options),
            answer=answer,
            difficulty=_normalize_diagnostic_difficulty(row.get("difficulty"), question_type),
            source_type=str(row.get("source_type") or "").strip(),
            source_chunk_id=str(row.get("source_chunk_id") or "").strip(),
            node_code=str(row.get("node_code") or "").strip(),
            source_meta=dict(row.get("source_meta") or {}) if isinstance(row.get("source_meta"), dict) else {},
        )
        if not _is_supported_click_assessment_candidate(candidate):
            return None
        return candidate

    def question_bank_size(self) -> int:
        base_url, api_key = self._supabase_config()
        # 软删收权（task#31）：题库规模只算在服行（口径裁决见设计稿 §2.5）。
        # 与 _query 同一旗标（默认 OFF = 现行为），OFF 期间列可能尚未上线。
        live_filter = (
            f"&{LIVE_ROW_FILTER_COLUMN}={LIVE_ROW_FILTER_OPERATOR}"
            if soft_delete_filter_enabled()
            else ""
        )
        req = request.Request(
            f"{base_url}/rest/v1/questions_bank?select=id&limit=1{live_filter}",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Prefer": "count=exact",
            },
            method="GET",
        )
        try:
            with request.urlopen(req, timeout=15) as response:
                content_range = response.headers.get("Content-Range", "")
        except Exception:
            return 0
        if "/" not in content_range:
            return 0
        try:
            return int(content_range.rsplit("/", 1)[1])
        except ValueError:
            return 0

    def form_cache_key(self, blueprint_version: str) -> str:
        base_url, _api_key = self._supabase_config()
        return f"supabase_questions_bank:{base_url}:{blueprint_version}:assessment_forms_v3"

    def load_persisted_form_bank(self, blueprint: AssessmentBlueprint) -> _AssessmentFormBank:
        base_url, api_key = self._supabase_config()
        rows = self._rest_get(
            base_url,
            api_key,
            "assessment_forms",
            {
                "select": "form_id,form_index,items_json,question_bank_size,fallback_used",
                "blueprint_version": f"eq.{blueprint.version}",
                "status": "eq.active",
                "order": "form_index.asc",
                "limit": str(_ASSESSMENT_FORM_COUNT),
            },
        )
        forms = tuple(_form_from_persisted_row(row, blueprint) for row in rows)
        if len(forms) < MIN_FORM_ROTATION_COUNT:
            raise AssessmentBlueprintUnavailable(
                f"Persisted assessment forms missing: expected at least {MIN_FORM_ROTATION_COUNT}, found {len(forms)}"
            )
        question_bank_size = max(int(row.get("question_bank_size") or 0) for row in rows)
        form_bank = _AssessmentFormBank(
            forms=forms,
            question_bank_size=question_bank_size,
            form_source="supabase_persisted",
        )
        _validate_form_bank_rotation(form_bank, blueprint)
        return form_bank

    def active_form_count(self, blueprint_version: str) -> int:
        base_url, api_key = self._supabase_config()
        rows = self._rest_get(
            base_url,
            api_key,
            "assessment_forms",
            {
                "select": "form_id",
                "blueprint_version": f"eq.{blueprint_version}",
                "status": "eq.active",
                "limit": str(_ASSESSMENT_FORM_COUNT),
            },
        )
        return len(rows)

    def active_form_summaries(self, blueprint_versions: list[str] | tuple[str, ...]) -> dict[str, dict[str, Any]]:
        versions = [str(item or "").strip() for item in blueprint_versions if str(item or "").strip()]
        if not versions:
            return {}
        base_url, api_key = self._supabase_config()
        rows = self._rest_get(
            base_url,
            api_key,
            "assessment_forms",
            {
                "select": "blueprint_version,form_id,form_index,fallback_used,question_bank_size",
                "blueprint_version": f"in.({','.join(versions)})",
                "status": "eq.active",
                "order": "blueprint_version.asc,form_index.asc",
                "limit": str(_ASSESSMENT_FORM_COUNT * len(versions)),
            },
        )
        summaries: dict[str, dict[str, Any]] = {
            version: {
                "active_form_count": 0,
                "fallback_used": False,
                "question_bank_size": 0,
            }
            for version in versions
        }
        seen_form_ids: dict[str, set[str]] = {version: set() for version in versions}
        for row in rows:
            version = str(row.get("blueprint_version") or "").strip()
            if version not in summaries:
                continue
            form_id = str(row.get("form_id") or row.get("form_index") or "").strip()
            if form_id and form_id in seen_form_ids[version]:
                continue
            if form_id:
                seen_form_ids[version].add(form_id)
            summaries[version]["active_form_count"] = int(summaries[version]["active_form_count"]) + 1
            summaries[version]["fallback_used"] = bool(
                summaries[version]["fallback_used"] or row.get("fallback_used")
            )
            try:
                question_bank_size = int(row.get("question_bank_size") or 0)
            except (TypeError, ValueError):
                question_bank_size = 0
            summaries[version]["question_bank_size"] = max(
                int(summaries[version]["question_bank_size"]),
                question_bank_size,
            )
        return summaries

    def save_form_bank(self, blueprint: AssessmentBlueprint, form_bank: _AssessmentFormBank) -> None:
        base_url, api_key = self._supabase_config()
        rows = [
            _form_to_persisted_row(blueprint.version, form, question_bank_size=form_bank.question_bank_size)
            for form in form_bank.forms
        ]
        self._rest_upsert(base_url, api_key, "assessment_forms", rows, on_conflict="form_id")


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
        self._local_form_bank: _AssessmentFormBank | None = None

    @property
    def blueprint(self) -> AssessmentBlueprint:
        return self._blueprint

    def prewarm_forms(self) -> dict[str, Any]:
        form_bank = self._get_or_build_form_bank()
        return {
            "blueprint_version": self._blueprint.version,
            "form_count": len(form_bank.forms),
            "form_ids": [form.form_id for form in form_bank.forms],
            "form_source": form_bank.form_source or "unknown",
            "question_bank_size": form_bank.question_bank_size,
            "fallback_used": any(form.fallback_used for form in form_bank.forms),
        }

    def generate_and_persist_forms(self) -> dict[str, Any]:
        form_bank = self._build_form_bank()
        saver = getattr(self._provider, "save_form_bank", None)
        if not callable(saver):
            raise AssessmentBlueprintUnavailable("Assessment provider cannot persist form bank")
        saver(self._blueprint, form_bank)
        form_bank = _with_form_source(form_bank, "generated_and_persisted")
        cache_key = self._form_cache_key()
        if cache_key:
            with _FORM_CACHE_LOCK:
                _FORM_CACHE[cache_key] = form_bank
        self._local_form_bank = form_bank
        return {
            "blueprint_version": self._blueprint.version,
            "form_count": len(form_bank.forms),
            "form_ids": [form.form_id for form in form_bank.forms],
            "form_source": form_bank.form_source or "unknown",
            "question_bank_size": form_bank.question_bank_size,
            "fallback_used": any(form.fallback_used for form in form_bank.forms),
            "persisted": True,
        }

    def create_session(
        self,
        *,
        user_id: str,
        count: int = 20,
        assessment_type: str = "diagnostic",
        subject_id: str = "construction_exam",
        topic_ids: tuple[str, ...] | list[str] | None = None,
    ) -> dict[str, Any]:
        requested_count = max(1, int(count or self._blueprint.requested_count))
        if requested_count != self._blueprint.requested_count:
            requested_count = self._blueprint.requested_count

        form_bank = self._get_or_build_form_bank()
        form = _choose_assessment_form(form_bank.forms)
        client_questions: list[dict[str, Any]] = []
        session_questions: list[dict[str, Any]] = []
        sections: list[dict[str, Any]] = []
        for section in self._blueprint.sections:
            section_question_ids: list[str] = []
            section_units = [unit for unit in form.units if unit.section_id == section.id]
            if len(section_units) != section.count:
                raise AssessmentBlueprintUnavailable(
                    f"Assessment form {form.form_id} section {section.id} expected {section.count} units, "
                    f"found {len(section_units)}"
                )
            for unit in section_units:
                if unit.scored:
                    candidate = unit.item
                    if not isinstance(candidate, QuestionCandidate):
                        raise AssessmentBlueprintUnavailable(f"Assessment form {form.form_id} has invalid scored unit")
                    question_id = _make_question_id(candidate.source_question_id, len(client_questions) + 1)
                    section_question_ids.append(question_id)
                    client, stored = _build_scored_question(question_id, section, candidate)
                    client_questions.append(client)
                    session_questions.append(stored)
                else:
                    probe = unit.item
                    if not isinstance(probe, ProfileProbe):
                        raise AssessmentBlueprintUnavailable(f"Assessment form {form.form_id} has invalid profile unit")
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
        question_bank_size = max(form_bank.question_bank_size, delivered_count)
        return {
            "quiz_id": quiz_id,
            "user_id": user_id,
            "assessment_type": str(assessment_type or "diagnostic").strip() or "diagnostic",
            "subject_id": str(subject_id or "construction_exam").strip() or "construction_exam",
            "topic_ids": [str(item).strip() for item in list(topic_ids or []) if str(item).strip()],
            "questions": client_questions,
            "session_questions": session_questions,
            "blueprint_version": self._blueprint.version,
            "sections": sections,
            "requested_count": requested_count,
            "delivered_count": delivered_count,
            "scored_count": self._blueprint.scored_count,
            "profile_count": self._blueprint.profile_count,
            "available_count": question_bank_size,
            "question_bank_size": question_bank_size,
            "unique_source_question_count": len({item["source_question_id"] for item in session_questions}),
            "shortfall_count": 0,
            "fallback_used": form.fallback_used,
            "form_source": form_bank.form_source or "unknown",
            "form_id": form.form_id,
            "form_index": form.form_index,
            "form_count": len(form_bank.forms),
        }

    def _get_or_build_form_bank(self) -> _AssessmentFormBank:
        if self._local_form_bank is not None:
            return self._local_form_bank
        cache_key = self._form_cache_key()
        if cache_key:
            with _FORM_CACHE_LOCK:
                cached = _FORM_CACHE.get(cache_key)
                if cached is not None:
                    self._local_form_bank = cached
                    return cached
        persisted_loader = getattr(self._provider, "load_persisted_form_bank", None)
        if callable(persisted_loader):
            try:
                form_bank = persisted_loader(self._blueprint)
            except AssessmentBlueprintUnavailable:
                form_bank = None
            if form_bank is not None:
                fallback_source = (
                    "supabase_persisted"
                    if isinstance(self._provider, SupabaseAssessmentQuestionProvider)
                    else "persisted"
                )
                form_bank = _with_form_source(form_bank, form_bank.form_source or fallback_source)
                if cache_key:
                    with _FORM_CACHE_LOCK:
                        _FORM_CACHE[cache_key] = form_bank
                self._local_form_bank = form_bank
                return form_bank
        form_bank = self._build_form_bank()
        if cache_key:
            with _FORM_CACHE_LOCK:
                _FORM_CACHE.setdefault(cache_key, form_bank)
                form_bank = _FORM_CACHE[cache_key]
        self._local_form_bank = form_bank
        return form_bank

    def _form_cache_key(self) -> str:
        getter = getattr(self._provider, "form_cache_key", None)
        if not callable(getter):
            return ""
        try:
            return str(getter(self._blueprint.version) or "")
        except Exception:
            return ""

    def _build_form_bank(self) -> _AssessmentFormBank:
        forms: list[_AssessmentForm] = []
        bank_fallback_used = False
        bank_exclude_source_ids: set[str] = set()
        bank_exclude_semantic_signatures: set[str] = set()
        requires_rotation = _requires_form_bank_scored_rotation(self._blueprint)
        for form_index in range(1, _ASSESSMENT_FORM_COUNT + 1):
            try:
                units, fallback_used, used_source_ids, used_semantic_signatures = self._build_form_units(
                    form_index,
                    bank_exclude_source_ids=bank_exclude_source_ids if requires_rotation else set(),
                    bank_exclude_semantic_signatures=bank_exclude_semantic_signatures if requires_rotation else set(),
                )
            except AssessmentBlueprintUnavailable:
                if requires_rotation and len(forms) >= MIN_FORM_ROTATION_COUNT:
                    break
                raise
            if requires_rotation:
                bank_exclude_source_ids.update(used_source_ids)
                bank_exclude_semantic_signatures.update(used_semantic_signatures)
            bank_fallback_used = bank_fallback_used or fallback_used
            if len(units) != self._blueprint.requested_count:
                raise AssessmentBlueprintUnavailable(
                    f"Assessment form {form_index} delivered {len(units)}, expected {self._blueprint.requested_count}"
                )
            forms.append(
                _AssessmentForm(
                    form_id=f"{self._blueprint.version}_form_{form_index}",
                    form_index=form_index,
                    units=tuple(units),
                    fallback_used=fallback_used,
                )
            )
        question_bank_size = _provider_question_bank_size(self._provider)
        if any(form.fallback_used for form in forms) and self._fallback_provider:
            question_bank_size = max(question_bank_size, _provider_question_bank_size(self._fallback_provider))
        form_source = _built_form_source(self._provider)
        if bank_fallback_used and self._fallback_provider is not None:
            form_source = _built_form_source(self._fallback_provider)
        form_bank = _AssessmentFormBank(
            forms=tuple(forms),
            question_bank_size=question_bank_size,
            form_source=form_source,
        )
        _validate_form_bank_rotation(form_bank, self._blueprint)
        return form_bank

    def _build_form_units(
        self,
        form_index: int,
        *,
        bank_exclude_source_ids: set[str] | None = None,
        bank_exclude_semantic_signatures: set[str] | None = None,
    ) -> tuple[list[_AssessmentFormUnit], bool, set[str], set[str]]:
        units: list[_AssessmentFormUnit] = []
        exclude_source_ids: set[str] = set(bank_exclude_source_ids or set())
        exclude_semantic_signatures: set[str] = set(bank_exclude_semantic_signatures or set())
        avoid_scored_chapters: set[str] = set()
        profile_probe_iter = iter(get_profile_probes())
        fallback_used = False
        used_source_ids: set[str] = set()
        used_semantic_signatures: set[str] = set()
        selection_seed = f"{self._blueprint.version}:assessment_form:{form_index}"

        for section in self._blueprint.sections:
            if section.scored:
                try:
                    candidates = self._provider.get_candidates(
                        section,
                        limit=max(section.count * max(section.minimum_multiplier, 1), section.count),
                        exclude_source_ids=exclude_source_ids,
                        selection_seed=selection_seed,
                        avoid_chapters=avoid_scored_chapters,
                    )
                except AssessmentBlueprintUnavailable:
                    if not self._allow_dev_fallback:
                        raise
                    candidates = []
                candidates = _supported_click_assessment_candidates(candidates)
                if len(candidates) < section.count and self._allow_dev_fallback and self._fallback_provider:
                    fallback_candidates = self._fallback_provider.get_candidates(
                        section,
                        limit=max((section.count - len(candidates)) * max(section.minimum_multiplier, 1), section.count - len(candidates)),
                        exclude_source_ids=exclude_source_ids | {item.source_question_id for item in candidates},
                        selection_seed=selection_seed,
                        avoid_chapters=avoid_scored_chapters,
                    )
                    fallback_candidates = _supported_click_assessment_candidates(fallback_candidates)
                    candidates.extend(fallback_candidates)
                    fallback_used = True
                section_candidates: list[QuestionCandidate] = []
                for candidate in candidates:
                    semantic_signature = _candidate_semantic_signature(candidate)
                    if semantic_signature and semantic_signature in exclude_semantic_signatures:
                        continue
                    section_candidates.append(candidate)
                    if len(section_candidates) >= section.count:
                        break
                if len(section_candidates) < section.count:
                    raise AssessmentBlueprintUnavailable(
                        f"Assessment blueprint {self._blueprint.version} section {section.id} "
                        f"requires {section.count} scored questions, found {len(section_candidates)}"
                    )
                for candidate in section_candidates:
                    exclude_source_ids.add(candidate.source_question_id)
                    used_source_ids.add(candidate.source_question_id)
                    semantic_signature = _candidate_semantic_signature(candidate)
                    if semantic_signature:
                        exclude_semantic_signatures.add(semantic_signature)
                        used_semantic_signatures.add(semantic_signature)
                    avoid_scored_chapters.add(_chapter_key(candidate.chapter))
                    units.append(_AssessmentFormUnit(section_id=section.id, scored=True, item=candidate))
            else:
                for _ in range(section.count):
                    try:
                        probe = next(profile_probe_iter)
                    except StopIteration as exc:
                        raise AssessmentBlueprintUnavailable("Not enough built-in profile probes") from exc
                    units.append(_AssessmentFormUnit(section_id=section.id, scored=False, item=probe))
        return units, fallback_used, used_source_ids, used_semantic_signatures


def _make_question_id(source_id: str, index: int) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in str(source_id or "q"))[:40].strip("_") or "q"
    return f"{normalized}__{index:02d}_{uuid.uuid4().hex[:6]}"


def _choose_assessment_form(forms: tuple[_AssessmentForm, ...]) -> _AssessmentForm:
    if not forms:
        raise AssessmentBlueprintUnavailable("Assessment form bank is empty")
    index = int(uuid.uuid4().hex[:8], 16) % len(forms)
    return forms[index]


def _built_form_source(provider: AssessmentQuestionProvider) -> str:
    if isinstance(provider, SupabaseAssessmentQuestionProvider):
        return "supabase_questions_bank"
    if isinstance(provider, StaticAssessmentQuestionProvider):
        return "local_static_fallback"
    return "generated"


def _with_form_source(form_bank: _AssessmentFormBank, form_source: str) -> _AssessmentFormBank:
    normalized = str(form_source or "").strip()
    if not normalized or form_bank.form_source == normalized:
        return form_bank
    return _AssessmentFormBank(
        forms=form_bank.forms,
        question_bank_size=form_bank.question_bank_size,
        form_source=normalized,
    )


def _form_to_persisted_row(
    blueprint_version: str,
    form: _AssessmentForm,
    *,
    question_bank_size: int,
) -> dict[str, Any]:
    scored_units = [unit for unit in form.units if unit.scored and isinstance(unit.item, QuestionCandidate)]
    return {
        "form_id": form.form_id,
        "blueprint_version": blueprint_version,
        "form_index": form.form_index,
        "status": "active",
        "question_bank_size": question_bank_size,
        "fallback_used": form.fallback_used,
        "items_json": [_form_unit_to_json(unit) for unit in form.units],
        "quality_json": {
            "scored_count": len(scored_units),
            "unique_chapter_count": len({_chapter_key(unit.item.chapter) for unit in scored_units}),
            "difficulties": sorted({_difficulty_key(unit.item.difficulty) for unit in scored_units}),
            "question_types": sorted({unit.item.question_type for unit in scored_units}),
        },
    }


def _form_unit_to_json(unit: _AssessmentFormUnit) -> dict[str, Any]:
    if unit.scored:
        item = unit.item
        if not isinstance(item, QuestionCandidate):
            raise AssessmentBlueprintUnavailable("Invalid scored assessment form unit")
        return {
            "section_id": unit.section_id,
            "scored": True,
            "source_question_id": item.source_question_id,
            "question_stem": item.question_stem,
            "question_type": item.question_type,
            "chapter": item.chapter,
            "options": [{"key": key, "text": text} for key, text in item.options],
            "answer": item.answer,
            "difficulty": item.difficulty,
            "source_type": item.source_type,
            "source_chunk_id": item.source_chunk_id,
            "node_code": item.node_code,
            "source_meta": dict(item.source_meta or {}),
        }
    item = unit.item
    if not isinstance(item, ProfileProbe):
        raise AssessmentBlueprintUnavailable("Invalid profile assessment form unit")
    return {
        "section_id": unit.section_id,
        "scored": False,
        "probe_id": item.id,
        "topic": item.topic,
        "question_stem": item.question_stem,
        "options": [{"key": key, "text": text, "value": value} for key, text, value in item.options],
    }


def _form_from_persisted_row(row: dict[str, Any], blueprint: AssessmentBlueprint) -> _AssessmentForm:
    raw_items = row.get("items_json")
    if isinstance(raw_items, str):
        raw_items = json.loads(raw_items)
    if not isinstance(raw_items, list):
        raise AssessmentBlueprintUnavailable(f"Assessment form {row.get('form_id')} has invalid items_json")
    units = tuple(_form_unit_from_json(item) for item in raw_items)
    _validate_form_units(str(row.get("form_id") or ""), units, blueprint)
    return _AssessmentForm(
        form_id=str(row.get("form_id") or ""),
        form_index=int(row.get("form_index") or 0),
        units=units,
        fallback_used=bool(row.get("fallback_used")),
    )


def _requires_form_bank_scored_rotation(blueprint: AssessmentBlueprint) -> bool:
    return blueprint.version.startswith("topic_")


def _validate_form_bank_rotation(form_bank: _AssessmentFormBank, blueprint: AssessmentBlueprint) -> None:
    if len(form_bank.forms) < MIN_FORM_ROTATION_COUNT:
        raise AssessmentBlueprintUnavailable(
            f"Assessment blueprint {blueprint.version} requires at least {MIN_FORM_ROTATION_COUNT} forms, "
            f"found {len(form_bank.forms)}"
        )
    if not _requires_form_bank_scored_rotation(blueprint):
        return
    source_ids: list[str] = []
    semantic_signatures: list[str] = []
    for form in form_bank.forms:
        for unit in form.units:
            if not unit.scored or not isinstance(unit.item, QuestionCandidate):
                continue
            source_ids.append(unit.item.source_question_id)
            semantic_signature = _candidate_semantic_signature(unit.item)
            if semantic_signature:
                semantic_signatures.append(semantic_signature)
    if len(source_ids) != len(set(source_ids)):
        raise AssessmentBlueprintUnavailable(
            f"Assessment blueprint {blueprint.version} form bank repeats scored source_question_id"
        )
    if len(semantic_signatures) != len(set(semantic_signatures)):
        raise AssessmentBlueprintUnavailable(
            f"Assessment blueprint {blueprint.version} form bank repeats semantic_signature"
        )


def _form_unit_from_json(item: dict[str, Any]) -> _AssessmentFormUnit:
    if not isinstance(item, dict):
        raise AssessmentBlueprintUnavailable("Invalid assessment form item")
    section_id = str(item.get("section_id") or "").strip()
    scored = bool(item.get("scored"))
    if scored:
        options = item.get("options") or []
        normalized_options = tuple(
            (str(option.get("key") or "").strip(), str(option.get("text") or "").strip())
            for option in options
            if isinstance(option, dict) and str(option.get("key") or "").strip()
        )
        candidate = QuestionCandidate(
            source_question_id=str(item.get("source_question_id") or "").strip(),
            question_stem=str(item.get("question_stem") or "").strip(),
            question_type=str(item.get("question_type") or "single_choice").strip() or "single_choice",
            chapter=str(item.get("chapter") or "").strip(),
            options=normalized_options,
            answer=_normalize_answer_for_options(item.get("answer"), normalized_options),
            difficulty=str(item.get("difficulty") or "medium").strip() or "medium",
            source_type=str(item.get("source_type") or "").strip(),
            source_chunk_id=str(item.get("source_chunk_id") or "").strip(),
            node_code=str(item.get("node_code") or "").strip(),
            source_meta=dict(item.get("source_meta") or {}) if isinstance(item.get("source_meta"), dict) else {},
        )
        if not _is_supported_click_assessment_candidate(candidate):
            raise AssessmentBlueprintUnavailable(
                f"Assessment form item {candidate.source_question_id} is not a supported click assessment candidate"
            )
        return _AssessmentFormUnit(
            section_id=section_id,
            scored=True,
            item=candidate,
        )
    options = item.get("options") or []
    return _AssessmentFormUnit(
        section_id=section_id,
        scored=False,
        item=ProfileProbe(
            id=str(item.get("probe_id") or "").strip(),
            section_id=section_id,
            topic=str(item.get("topic") or "").strip(),
            question_stem=str(item.get("question_stem") or "").strip(),
            options=tuple(
                (
                    str(option.get("key") or "").strip(),
                    str(option.get("text") or "").strip(),
                    str(option.get("value") or "").strip(),
                )
                for option in options
                if isinstance(option, dict) and str(option.get("key") or "").strip()
            ),
        ),
    )


def _validate_form_units(form_id: str, units: tuple[_AssessmentFormUnit, ...], blueprint: AssessmentBlueprint) -> None:
    if len(units) != blueprint.requested_count:
        raise AssessmentBlueprintUnavailable(
            f"Assessment form {form_id} delivered {len(units)}, expected {blueprint.requested_count}"
        )
    for section in blueprint.sections:
        section_units = [unit for unit in units if unit.section_id == section.id]
        if len(section_units) != section.count:
            raise AssessmentBlueprintUnavailable(
                f"Assessment form {form_id} section {section.id} expected {section.count}, found {len(section_units)}"
            )
        if any(unit.scored != section.scored for unit in section_units):
            raise AssessmentBlueprintUnavailable(f"Assessment form {form_id} section {section.id} scored mismatch")


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


def _normalize_answer_for_options(value: Any, options: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> str:
    raw = _normalize_answer(value)
    option_keys = [str(key or "").strip().upper() for key, _text in options if str(key or "").strip()]
    option_key_set = set(option_keys)
    if not raw or not option_keys:
        return ""
    if raw in option_key_set:
        return raw
    letters = [ch for ch in raw if ch in option_key_set]
    non_letters = re.sub(r"[A-Z]", "", raw)
    non_letters = re.sub(r"[\s,，、;；/|+&]+", "", non_letters)
    if letters and not non_letters:
        selected = set(letters)
        return "".join(key for key in option_keys if key in selected)
    normalized_raw = _normalize_match_text(raw)
    for key, text in options:
        if normalized_raw and normalized_raw == _normalize_match_text(text):
            return str(key or "").strip().upper()
    return ""


def _has_multiple_prompt_stem(stem: str) -> bool:
    return len(_MULTI_PROMPT_STEM_RE.findall(str(stem or ""))) >= 2


def _is_supported_click_assessment_candidate(candidate: QuestionCandidate) -> bool:
    if len(candidate.options) < 2 or not candidate.answer:
        return False
    qtype = str(candidate.question_type or "").strip().lower()
    if qtype in {"case_study", "calculation"} and _has_multiple_prompt_stem(candidate.question_stem):
        return False
    return True


def _supported_click_assessment_candidates(candidates: list[QuestionCandidate]) -> list[QuestionCandidate]:
    return [candidate for candidate in candidates if _is_supported_click_assessment_candidate(candidate)]


def _normalize_difficulty(value: Any) -> str:
    raw = str(value or "").strip()
    normalized = _normalize_match_text(raw)
    if not normalized:
        return "medium"
    if any(token in normalized for token in ("easy", "简单", "基础", "low")):
        return "easy"
    if any(token in normalized for token in ("hard", "困难", "较难", "挑战", "high")):
        return "hard"
    try:
        numeric = float(raw)
    except ValueError:
        return "medium"
    if numeric <= 0.4:
        return "easy"
    if numeric <= 0.75:
        return "medium"
    return "hard"


def _normalize_diagnostic_difficulty(value: Any, question_type: str) -> str:
    normalized = _normalize_difficulty(value)
    qtype = str(question_type or "").strip().lower()
    if qtype in {"case_study", "calculation"}:
        return "hard"
    if qtype in {"multi_choice", "structured_judgment", "diagram_interpretation"}:
        return "medium" if normalized != "hard" else "hard"
    if qtype in {"single_choice", "judgment", "recall"} and normalized == "medium":
        return "easy"
    return normalized


def _stable_shuffle_candidates(candidates: list[QuestionCandidate], selection_seed: str) -> list[QuestionCandidate]:
    if not selection_seed:
        return list(candidates)
    return sorted(
        candidates,
        key=lambda item: hashlib.sha1(f"{selection_seed}:{item.source_question_id}".encode("utf-8")).hexdigest(),
    )


def _selection_offset(selection_seed: str, section_id: str) -> int:
    if not selection_seed:
        return 1000
    digest = hashlib.sha1(f"{selection_seed}:{section_id}:offset".encode("utf-8")).hexdigest()
    return 1000 + (int(digest[:8], 16) % 3000)


def _select_diagnostic_candidates(
    candidates: list[QuestionCandidate],
    *,
    section: AssessmentSection,
    limit: int,
    selection_seed: str,
    avoid_chapters: set[str],
) -> list[QuestionCandidate]:
    filtered = list(candidates)
    if section.strict_topics:
        filtered = [candidate for candidate in filtered if _section_topic_score(candidate, section) > 0]
    ordered = _prioritize_section_topics(
        _stable_shuffle_candidates(filtered, selection_seed),
        section=section,
    )
    selected: list[QuestionCandidate] = []
    used_ids: set[str] = set()
    used_semantic_signatures: set[str] = set()
    used_chapters = {_chapter_key(item) for item in avoid_chapters if item}
    used_difficulties: set[str] = set()
    used_question_types: set[str] = set()

    while len(selected) < limit and ordered:
        best_index = min(
            range(len(ordered)),
            key=lambda index: _balance_rank(
                ordered[index],
                index,
                section,
                used_chapters,
                used_difficulties,
                used_question_types,
            ),
        )
        candidate = ordered.pop(best_index)
        if candidate.source_question_id in used_ids:
            continue
        semantic_signature = _candidate_semantic_signature(candidate)
        if semantic_signature and semantic_signature in used_semantic_signatures:
            continue
        selected.append(candidate)
        used_ids.add(candidate.source_question_id)
        if semantic_signature:
            used_semantic_signatures.add(semantic_signature)
        used_chapters.add(_chapter_key(candidate.chapter))
        used_difficulties.add(_difficulty_key(candidate.difficulty))
        used_question_types.add(candidate.question_type)
    return selected


def _prioritize_section_topics(
    candidates: list[QuestionCandidate],
    *,
    section: AssessmentSection,
) -> list[QuestionCandidate]:
    if not section.topics:
        return candidates
    scored = [(_section_topic_score(candidate, section), index, candidate) for index, candidate in enumerate(candidates)]
    if not any(score > 0 for score, _index, _candidate in scored):
        return candidates
    return [candidate for _score, _index, candidate in sorted(scored, key=lambda item: (-item[0], item[1]))]


def _section_topic_score(candidate: QuestionCandidate, section: AssessmentSection) -> int:
    haystack = _normalize_match_text(
        " ".join(
            (
                candidate.chapter,
                candidate.node_code,
                candidate.question_stem,
                json.dumps(candidate.source_meta or {}, ensure_ascii=False),
            )
        )
    )
    score = 0
    for topic in section.topics:
        needle = _normalize_match_text(topic)
        if needle and needle in haystack:
            score += 1
    return score


def _candidate_semantic_signature(candidate: QuestionCandidate) -> str:
    source_meta = dict(candidate.source_meta or {})
    for key in ("semantic_signature", "source_semantic_signature"):
        value = str(source_meta.get(key) or "").strip()
        if value:
            return value
    return ""


def _balance_rank(
    candidate: QuestionCandidate,
    index: int,
    section: AssessmentSection,
    used_chapters: set[str],
    used_difficulties: set[str],
    used_question_types: set[str],
) -> tuple[int, int, int, int, int]:
    return (
        1 if candidate.question_type not in section.question_types else 0,
        1 if _chapter_key(candidate.chapter) in used_chapters else 0,
        1 if candidate.question_type in used_question_types else 0,
        1 if _difficulty_key(candidate.difficulty) in used_difficulties else 0,
        index,
    )


def _chapter_key(value: str) -> str:
    return _normalize_match_text(value or "综合能力")


def _difficulty_key(value: str) -> str:
    return _normalize_difficulty(value)


def _normalize_match_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _provider_question_bank_size(provider: AssessmentQuestionProvider) -> int:
    counter = getattr(provider, "question_bank_size", None)
    if not callable(counter):
        return 0
    try:
        return int(counter() or 0)
    except Exception:
        return 0


def _is_chapter_code(value: str) -> bool:
    return bool(_CHAPTER_CODE_RE.match(str(value or "").strip().upper()))


def _humanize_chapter_label(value: str, *, section: AssessmentSection) -> str:
    raw = str(value or "").strip()
    if not raw:
        return section.label or "综合能力"
    upper = raw.upper()
    if _is_chapter_code(upper):
        return display_taxonomy_label(raw, fallback="") or section.label or "综合能力"
    return raw


def _chapter_from_row(row: dict[str, Any], section: AssessmentSection) -> str:
    node_code = str(row.get("node_code") or "").strip()
    resolved = _confirmed_taxonomy_chapter({"node_code": node_code})
    if resolved:
        return resolved

    legacy_candidates: list[str] = []
    source_meta = row.get("source_meta")
    if isinstance(source_meta, dict):
        for key in ("chapter_name", "chapter_label", "topic_name", "node_name"):
            value = str(source_meta.get(key) or "").strip()
            if not value:
                continue
            resolved = _confirmed_taxonomy_chapter({"knowledge_points": [value]})
            if resolved:
                return resolved
            normalized = normalize_learning_topic_text(value)
            if normalized and not _is_chapter_code(normalized):
                legacy_candidates.append(normalized)
    tags = row.get("tags")
    if isinstance(tags, dict):
        for key in ("node_name", "chapter_name", "chapter_label", "topic_name", "chapter", "topic", "module"):
            if tags.get(key):
                value = str(tags[key])
                resolved = _confirmed_taxonomy_chapter({"knowledge_points": [value], "node_code": value})
                if resolved:
                    return resolved
                label = _humanize_chapter_label(value, section=section)
                normalized = normalize_learning_topic_text(label)
                if normalized:
                    legacy_candidates.append(normalized)
    if isinstance(tags, list) and tags:
        for tag in tags:
            value = str(tag)
            resolved = _confirmed_taxonomy_chapter({"knowledge_points": [value], "node_code": value})
            if resolved:
                return resolved
            label = _humanize_chapter_label(value, section=section)
            if label:
                normalized = normalize_learning_topic_text(label)
                if normalized:
                    legacy_candidates.append(normalized)
    if legacy_candidates:
        return legacy_candidates[0]
    return _humanize_chapter_label(node_code, section=section)


def _confirmed_taxonomy_chapter(payload: dict[str, Any]) -> str:
    resolved = resolve_learning_topic_from_payload(payload, llm_topic_inferer=None)
    if not resolved or not resolved.taxonomy_code:
        return ""
    return resolved.label
