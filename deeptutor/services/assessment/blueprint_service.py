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

from deeptutor.services.assessment.blueprint import AssessmentBlueprint, AssessmentSection, get_assessment_blueprint
from deeptutor.services.assessment.profile_probes import ProfileProbe, get_profile_probes

_CHAPTER_CODE_RE = re.compile(r"^1A\d{6}$")
_CHAPTER_CODE_LABELS = {
    "1A411": "建筑设计与构造",
    "1A412": "结构设计与建筑材料",
    "1A413": "装配式建筑",
    "1A414": "建筑工程材料",
    "1A415": "建筑工程施工技术",
    "1A421": "项目组织管理",
    "1A422": "施工进度管理",
    "1A423": "施工质量管理",
    "1A424": "施工安全管理",
    "1A425": "合同与招投标管理",
    "1A426": "施工成本管理",
    "1A427": "资源与现场管理",
    "1A431": "建筑工程法规",
    "1A432": "建筑工程技术标准",
}
_ASSESSMENT_FORM_COUNT = 5
_FORM_CACHE_LOCK = threading.RLock()
_FORM_CACHE: dict[str, "_AssessmentFormBank"] = {}


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
        if len(candidates) < limit:
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
                if len({item.source_question_id for item in candidates}) >= limit:
                    break
        unique_candidates = list({item.source_question_id: item for item in candidates}.values())
        return _select_diagnostic_candidates(
            unique_candidates,
            section=section,
            limit=limit,
            selection_seed=selection_seed,
            avoid_chapters=avoid_chapters or set(),
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
    def _candidate_from_row(row: dict[str, Any], section: AssessmentSection) -> QuestionCandidate | None:
        source_id = str(row.get("id") or "").strip()
        stem = str(row.get("question_stem") or row.get("stem") or "").strip()
        options = _normalize_options(row.get("options"))
        answer = _normalize_answer(row.get("correct_answer"))
        if not source_id or not stem or not options or not answer:
            return None
        question_type = str(row.get("question_type") or "single_choice").strip() or "single_choice"
        return QuestionCandidate(
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

    def question_bank_size(self) -> int:
        base_url, api_key = self._supabase_config()
        req = request.Request(
            f"{base_url}/rest/v1/questions_bank?select=id&limit=1",
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
        return f"supabase_questions_bank:{base_url}:{blueprint_version}:assessment_forms_v2"


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
            "question_bank_size": form_bank.question_bank_size,
            "fallback_used": any(form.fallback_used for form in form_bank.forms),
        }

    def create_session(self, *, user_id: str, count: int = 20) -> dict[str, Any]:
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
        for form_index in range(1, _ASSESSMENT_FORM_COUNT + 1):
            units, fallback_used = self._build_form_units(form_index)
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
        return _AssessmentFormBank(forms=tuple(forms), question_bank_size=question_bank_size)

    def _build_form_units(self, form_index: int) -> tuple[list[_AssessmentFormUnit], bool]:
        units: list[_AssessmentFormUnit] = []
        exclude_source_ids: set[str] = set()
        avoid_scored_chapters: set[str] = set()
        profile_probe_iter = iter(get_profile_probes())
        fallback_used = False
        selection_seed = f"{self._blueprint.version}:assessment_form:{form_index}"

        for section in self._blueprint.sections:
            if section.scored:
                try:
                    candidates = self._provider.get_candidates(
                        section,
                        limit=section.count,
                        exclude_source_ids=exclude_source_ids,
                        selection_seed=selection_seed,
                        avoid_chapters=avoid_scored_chapters,
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
                        selection_seed=selection_seed,
                        avoid_chapters=avoid_scored_chapters,
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
                    avoid_scored_chapters.add(_chapter_key(candidate.chapter))
                    units.append(_AssessmentFormUnit(section_id=section.id, scored=True, item=candidate))
            else:
                for _ in range(section.count):
                    try:
                        probe = next(profile_probe_iter)
                    except StopIteration as exc:
                        raise AssessmentBlueprintUnavailable("Not enough built-in profile probes") from exc
                    units.append(_AssessmentFormUnit(section_id=section.id, scored=False, item=probe))
        return units, fallback_used


def _make_question_id(source_id: str, index: int) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in str(source_id or "q"))[:40].strip("_") or "q"
    return f"{normalized}__{index:02d}_{uuid.uuid4().hex[:6]}"


def _choose_assessment_form(forms: tuple[_AssessmentForm, ...]) -> _AssessmentForm:
    if not forms:
        raise AssessmentBlueprintUnavailable("Assessment form bank is empty")
    index = int(uuid.uuid4().hex[:8], 16) % len(forms)
    return forms[index]


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
    ordered = _prioritize_section_topics(
        _stable_shuffle_candidates(candidates, selection_seed),
        section=section,
    )
    selected: list[QuestionCandidate] = []
    used_ids: set[str] = set()
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
        selected.append(candidate)
        used_ids.add(candidate.source_question_id)
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
        return _CHAPTER_CODE_LABELS.get(upper[:5]) or section.label or "综合能力"
    return raw


def _chapter_from_row(row: dict[str, Any], section: AssessmentSection) -> str:
    source_meta = row.get("source_meta")
    if isinstance(source_meta, dict):
        for key in ("chapter_name", "chapter_label", "topic_name", "node_name"):
            value = str(source_meta.get(key) or "").strip()
            if value and not _is_chapter_code(value):
                return value
    tags = row.get("tags")
    if isinstance(tags, dict):
        for key in ("node_name", "chapter_name", "chapter_label", "topic_name", "chapter", "topic", "module"):
            if tags.get(key):
                return _humanize_chapter_label(str(tags[key]), section=section)
    if isinstance(tags, list) and tags:
        for tag in tags:
            label = _humanize_chapter_label(str(tag), section=section)
            if label:
                return label
    node_code = str(row.get("node_code") or "").strip()
    return _humanize_chapter_label(node_code, section=section)
