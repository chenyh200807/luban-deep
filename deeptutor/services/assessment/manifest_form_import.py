"""内容线 v2 表单 manifest 的钉选导入(表单 v2 续命件,指挥官 2026-08-06)。

问题:seed 的"自动组卷持久化"选的题 ≠ 内容线精选的题——尤其案例段自动取
真题原案例,违反 owner「真题只做锚、不直接出」拍板。本模块把内容线手编的
`luban_s2_diagnostic_form.v2` manifest(E 线 form_v1_manifest 模式,含逐题
content_sha256/来源/选项/键)构建成运行时表单库,逐题按题源引用解析:

- ``compiled_practice_authority``:按 pack+variant_id 从签发 authority 取
  (``load_compiled_practice`` 全链闸 + ``_eligible`` 同一谓词),manifest 的
  ``content_sha256`` 必须等于 authority 条目的 ``content_sha256``;
- ``questions_bank``:按 qb id 经供给面 resolver 取行,双校验——DB
  ``content_hash`` 列 == manifest ``db_content_hash``,且行面重算
  (NFKC + 去空白,镜像内容线 ``build_form_v2_manifest.sha`` 配方)==
  manifest ``content_sha256``;
- 案例变式(``real_exam_case_variant`` / ``compiled_practice_item_variant``):
  新内容不在任何库,manifest 自带完整题面——校验
  ``sha(material + task_id) == content_sha256`` 后直接构建 candidate,
  provenance=``manifest:<manifest 文件 sha256>``;
  compiled 底稿变式额外把 ``base_content_sha256`` 钉到签发 authority 底稿条目。

**任一 sha 失配即整表 fail(签名纪律),绝不静默换题。**
无 ``--manifest`` 的 seed 走现行自动组卷,行为不变。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable
import unicodedata

from deeptutor.services.assessment.blueprint import (
    COMPILED_PRACTICE_QUESTION_SOURCE,
    MANIFEST_SOURCE_TYPE,
    MIN_FORM_ROTATION_COUNT,
    AssessmentBlueprint,
    AssessmentSection,
)
from deeptutor.services.assessment.blueprint_service import (
    QuestionCandidate,
    _AssessmentForm,
    _AssessmentFormBank,
    _AssessmentFormUnit,
    _validate_form_bank_rotation,
)
from deeptutor.services.assessment.compiled_practice_provider import (
    _candidate_from_compiled_item,
)
from deeptutor.services.assessment.profile_probes import get_profile_probes
from deeptutor.services.luban_lesson import practice_html as _practice_html

MANIFEST_SCHEMA = "luban_s2_diagnostic_form.v2"

_ANSWER_TYPE_MAP = {
    "single_choice": "single_choice",
    "multiple_choice": "multi_choice",
    "multi_choice": "multi_choice",
}

# manifest family → v2 blueprint 单选 section(五族车道)。
_FAMILY_SINGLE_SECTION = {
    "主体结构": "pr2_single_main_structure",
    "安全": "pr2_single_safety",
    "进度": "pr2_single_schedule",
    "质量验收": "pr2_single_quality",
    "防水": "pr2_single_waterproof",
}


class ManifestFormImportError(RuntimeError):
    """manifest 钉选导入失败:引用解析不到 / sha 失配 / 结构不满足 blueprint。"""


def _normalized_sha256(text: str) -> str:
    """镜像内容线 build_form_v2_manifest.sha:NFKC + 去全部空白后取 sha256。"""

    return hashlib.sha256(
        unicodedata.normalize("NFKC", re.sub(r"\s+", "", str(text or ""))).encode("utf-8")
    ).hexdigest()


def _norm_bank_options(row: dict[str, Any]) -> list[dict[str, Any]]:
    """镜像内容线 norm_options:qb 行 options → [{key,value}](sha 重算用)。"""

    out: list[dict[str, Any]] = []
    for index, option in enumerate(row.get("options") or []):
        if isinstance(option, dict):
            out.append({"key": option.get("key"), "value": option.get("value")})
        else:
            match = re.match(r"^\s*([A-F])[\.、\s]\s*(.*)$", str(option))
            out.append(
                {
                    "key": match.group(1) if match else chr(65 + index),
                    "value": match.group(2) if match else str(option),
                }
            )
    return out


def load_form_manifest(path: str | Path) -> tuple[dict[str, Any], str]:
    """读 manifest 文件,返回 (manifest, 文件字节 sha256)。"""

    raw = Path(path).read_bytes()
    try:
        manifest = json.loads(raw)
    except ValueError as exc:
        raise ManifestFormImportError(f"manifest_unreadable:{path}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ManifestFormImportError(
            f"manifest_schema_mismatch: expected {MANIFEST_SCHEMA}, got {manifest.get('schema')!r}"
        )
    return manifest, hashlib.sha256(raw).hexdigest()


def _material_text(manifest: dict[str, Any], material_id: str) -> str:
    material = (manifest.get("materials") or {}).get(material_id)
    if isinstance(material, dict):
        material = material.get("text")
    text = str(material or "").strip()
    if not text:
        raise ManifestFormImportError(f"manifest_material_missing:{material_id}")
    return text


def _question_type(task: dict[str, Any]) -> str:
    mapped = _ANSWER_TYPE_MAP.get(str(task.get("answer_type") or "").strip())
    if not mapped:
        raise ManifestFormImportError(
            f"manifest_answer_type_unsupported:{task.get('task_id')}:{task.get('answer_type')!r}"
        )
    return mapped


def _default_compiled_loader(pack_id: str) -> dict[str, Any]:
    try:
        authority = _practice_html.load_compiled_practice(str(pack_id or "").strip().upper())
    except _practice_html.PracticeHtmlInvalid as exc:
        raise ManifestFormImportError(f"compiled_authority_gate_failed:{pack_id}:{exc}") from exc
    if authority is None:
        raise ManifestFormImportError(f"compiled_authority_missing:{pack_id}")
    return authority


def _compiled_item(
    loader: Callable[[str], dict[str, Any]], pack_id: str, variant_id: str
) -> dict[str, Any]:
    authority = loader(pack_id)
    item = next(
        (
            row
            for row in authority.get("items") or []
            if isinstance(row, dict) and str(row.get("variant_id") or "") == variant_id
        ),
        None,
    )
    if item is None:
        raise ManifestFormImportError(f"compiled_item_missing:{pack_id}:{variant_id}")
    return item


def _resolve_compiled_task(
    task: dict[str, Any],
    section: AssessmentSection,
    *,
    compiled_loader: Callable[[str], dict[str, Any]],
) -> QuestionCandidate:
    task_id = str(task.get("task_id") or "")
    source = dict(task.get("source") or {})
    pack_id = str(task.get("pack_id") or "").strip().upper()
    variant_id = str(source.get("variant_id") or "")
    item = _compiled_item(compiled_loader, pack_id, variant_id)
    if not _practice_html._eligible(item):
        raise ManifestFormImportError(f"compiled_item_not_eligible:{task_id}:{variant_id}")
    expected_sha = str(task.get("content_sha256") or "")
    if not expected_sha or str(item.get("content_sha256") or "") != expected_sha:
        raise ManifestFormImportError(
            f"compiled_content_sha256_mismatch:{task_id}:{variant_id}"
        )
    candidate = _candidate_from_compiled_item(pack_id, item, section)
    if candidate is None:
        raise ManifestFormImportError(f"compiled_item_not_projectable:{task_id}:{variant_id}")
    return candidate


def _resolve_bank_task(
    task: dict[str, Any],
    section: AssessmentSection,
    *,
    bank_row_resolver: Callable[[int], dict[str, Any] | None],
) -> QuestionCandidate:
    from deeptutor.services.assessment.blueprint_service import (
        SupabaseAssessmentQuestionProvider,
    )

    task_id = str(task.get("task_id") or "")
    source = dict(task.get("source") or {})
    qb_id = source.get("qb_id")
    if not str(qb_id or "").strip():
        raise ManifestFormImportError(f"bank_task_missing_qb_id:{task_id}")
    row = bank_row_resolver(int(qb_id))
    if not isinstance(row, dict) or not row:
        raise ManifestFormImportError(f"bank_row_missing:{task_id}:qb_id={qb_id}")
    expected_db_hash = str(source.get("db_content_hash") or "")
    if expected_db_hash and str(row.get("content_hash") or "") != expected_db_hash:
        raise ManifestFormImportError(f"bank_db_content_hash_mismatch:{task_id}:qb_id={qb_id}")
    expected_sha = str(task.get("content_sha256") or "")
    recomputed = _normalized_sha256(
        str(row.get("question_stem") or "")
        + json.dumps(_norm_bank_options(row), ensure_ascii=False)
    )
    if not expected_sha or recomputed != expected_sha:
        raise ManifestFormImportError(f"bank_content_sha256_mismatch:{task_id}:qb_id={qb_id}")
    # 真库 options 有纯字符串形态("A. 文本"),先过与内容线同一规整再投影
    # (行内容 identity 已由上面两道 sha 钉死,规整不改变语义)。
    projected_row = dict(
        row,
        options=[
            {"key": option.get("key"), "text": option.get("value")}
            for option in _norm_bank_options(row)
        ],
    )
    candidate = SupabaseAssessmentQuestionProvider._candidate_from_row(projected_row, section)
    if candidate is None:
        raise ManifestFormImportError(f"bank_row_not_projectable:{task_id}:qb_id={qb_id}")
    manifest_answer = str(task.get("answer_key") or "").strip().upper()
    if manifest_answer and set(manifest_answer) != set(candidate.answer):
        raise ManifestFormImportError(f"bank_answer_key_mismatch:{task_id}:qb_id={qb_id}")
    return candidate


def _resolve_manifest_case_task(
    task: dict[str, Any],
    section: AssessmentSection,
    *,
    manifest: dict[str, Any],
    manifest_sha256: str,
    compiled_loader: Callable[[str], dict[str, Any]],
) -> QuestionCandidate:
    task_id = str(task.get("task_id") or "")
    source = dict(task.get("source") or {})
    material_id = str(task.get("material") or "")
    material_text = _material_text(manifest, material_id)
    expected_sha = str(task.get("content_sha256") or "")
    if not expected_sha or _normalized_sha256(material_text + task_id) != expected_sha:
        raise ManifestFormImportError(f"case_content_sha256_mismatch:{task_id}")
    if source.get("kind") == "compiled_practice_item_variant":
        # 底稿变式:把已审底稿钉到签发 authority(governed transformation 锚)。
        base_variant_id = str(source.get("base_variant_id") or "")
        base_item = _compiled_item(
            compiled_loader, str(task.get("pack_id") or ""), base_variant_id
        )
        if str(base_item.get("content_sha256") or "") != str(
            source.get("base_content_sha256") or ""
        ):
            raise ManifestFormImportError(
                f"case_base_content_sha256_mismatch:{task_id}:{base_variant_id}"
            )
    options: list[tuple[str, str]] = []
    # 报告面诊断:manifest 逐选项 cause(失分原因)/source(教材出处)是已审内容,
    # 只读投影进答案面(不进 client)。
    option_diagnosis: dict[str, dict[str, str]] = {}
    for option in task.get("options") or []:
        key = str((option or {}).get("key") or "").strip().upper()
        value = str((option or {}).get("value") or "").strip()
        if not key or not value:
            raise ManifestFormImportError(f"case_option_invalid:{task_id}")
        options.append((key, value))
        diagnosis = {
            "why_missed": str((option or {}).get("cause") or "").strip(),
            "source": str((option or {}).get("source") or "").strip(),
        }
        if any(diagnosis.values()):
            option_diagnosis[key] = diagnosis
    answer = str(task.get("answer_key") or "").strip().upper()
    option_keys = {key for key, _value in options}
    if len(options) < 2 or not answer or not set(answer) <= option_keys:
        raise ManifestFormImportError(f"case_answer_key_invalid:{task_id}")
    family = str(task.get("family") or "")
    return QuestionCandidate(
        source_question_id=f"{manifest.get('form_id')}:{task_id}",
        question_stem=f"{material_text}\n\n{str(task.get('stem') or '').strip()}",
        question_type=_question_type(task),
        chapter=f"案例·{family}" if family else section.label,
        options=tuple(options),
        answer=answer,
        difficulty="hard",
        source_type=MANIFEST_SOURCE_TYPE,
        source_chunk_id="",
        node_code="",
        source_meta={
            "aggregation": "manifest_pinned",
            "provenance": f"manifest:{manifest_sha256}",
            "manifest_form_id": str(manifest.get("form_id") or ""),
            "manifest_task_id": task_id,
            "material_id": material_id,
            "family": family,
            "source_kind": str(source.get("kind") or ""),
            "exam_anchor": str(source.get("exam_anchor") or ""),
            "exam_year": str(source.get("year") or ""),
            "base_variant_id": str(source.get("base_variant_id") or ""),
            "content_sha256": expected_sha,
            "difficulty_anchor": str(task.get("difficulty") or ""),
            "semantic_signature": f"manifest:{manifest.get('form_id')}:{task_id}",
        },
        answer_diagnosis={
            "scoring_point": str(task.get("dimension") or family),
            "options": option_diagnosis,
        },
    )


def _case_section_for_family(
    family: str, case_sections: list[AssessmentSection], assigned: dict[str, str]
) -> AssessmentSection:
    """family 关键词命中 section topics 者优先;命不中取第一个未占用 section。"""

    for section in case_sections:
        if assigned.get(section.id) not in (None, family):
            continue
        if any(family and family in topic for topic in section.topics):
            return section
    for section in case_sections:
        if assigned.get(section.id) in (None, family):
            return section
    raise ManifestFormImportError(f"case_section_unassignable:{family}")


def build_manifest_form(
    manifest: dict[str, Any],
    *,
    blueprint: AssessmentBlueprint,
    manifest_sha256: str,
    bank_row_resolver: Callable[[int], dict[str, Any] | None],
    compiled_loader: Callable[[str], dict[str, Any]] | None = None,
    form_index: int = 1,
) -> _AssessmentForm:
    """一份 manifest → 一张钉选表单(逐题解析 + sha 校验 + section 配额校验)。"""

    if str(manifest.get("blueprint") or "") != blueprint.version:
        raise ManifestFormImportError(
            f"manifest_blueprint_mismatch:{manifest.get('blueprint')!r}≠{blueprint.version}"
        )
    loader = compiled_loader or _default_compiled_loader
    sections_by_id = {section.id: section for section in blueprint.sections}
    case_sections = [
        section
        for section in blueprint.sections
        if section.scored
        and section.question_source != COMPILED_PRACTICE_QUESTION_SOURCE
        and section.id.startswith("pr2_case_")
    ]
    by_section: dict[str, list[QuestionCandidate]] = {}
    case_family_assignment: dict[str, str] = {}
    for task in manifest.get("tasks") or []:
        if not isinstance(task, dict) or not task.get("scored"):
            continue
        task_id = str(task.get("task_id") or "")
        source_kind = str((task.get("source") or {}).get("kind") or "")
        if source_kind == "compiled_practice_authority":
            family = str(task.get("family") or "")
            section_id = _FAMILY_SINGLE_SECTION.get(family, "")
            section = sections_by_id.get(section_id)
            if section is None:
                raise ManifestFormImportError(f"single_family_unmapped:{task_id}:{family}")
            candidate = _resolve_compiled_task(task, section, compiled_loader=loader)
        elif source_kind == "questions_bank":
            section = sections_by_id.get("pr2_objective_multi")
            if section is None:
                raise ManifestFormImportError("multi_section_missing_in_blueprint")
            candidate = _resolve_bank_task(task, section, bank_row_resolver=bank_row_resolver)
        elif source_kind in ("real_exam_case_variant", "compiled_practice_item_variant"):
            family = str(task.get("family") or "")
            section = _case_section_for_family(family, case_sections, case_family_assignment)
            case_family_assignment[section.id] = family
            candidate = _resolve_manifest_case_task(
                task,
                section,
                manifest=manifest,
                manifest_sha256=manifest_sha256,
                compiled_loader=loader,
            )
        else:
            raise ManifestFormImportError(f"task_source_kind_unsupported:{task_id}:{source_kind!r}")
        by_section.setdefault(section.id, []).append(candidate)

    units: list[_AssessmentFormUnit] = []
    seen_ids: set[str] = set()
    probe_pool = list(get_profile_probes())
    for section in blueprint.sections:
        if section.scored:
            candidates = by_section.get(section.id, [])
            if len(candidates) != section.count:
                raise ManifestFormImportError(
                    f"section_count_mismatch:{section.id}: manifest {len(candidates)} ≠ blueprint {section.count}"
                )
            for candidate in candidates:
                if candidate.source_question_id in seen_ids:
                    raise ManifestFormImportError(
                        f"duplicate_source_question:{candidate.source_question_id}"
                    )
                seen_ids.add(candidate.source_question_id)
                units.append(
                    _AssessmentFormUnit(section_id=section.id, scored=True, item=candidate)
                )
        else:
            # probe 内容权威 = 注册表(profile_probes),manifest probe 行仅为对照。
            section_probes = [
                probe for probe in probe_pool if probe.section_id == section.id
            ][: section.count]
            if len(section_probes) < section.count:
                raise ManifestFormImportError(f"probe_supply_short:{section.id}")
            for probe in section_probes:
                units.append(
                    _AssessmentFormUnit(section_id=section.id, scored=False, item=probe)
                )
    if len(units) != blueprint.requested_count:
        raise ManifestFormImportError(
            f"form_size_mismatch:{len(units)}≠{blueprint.requested_count}"
        )
    return _AssessmentForm(
        form_id=str(manifest.get("form_id") or f"{blueprint.version}_manifest_{form_index}"),
        form_index=form_index,
        units=tuple(units),
        fallback_used=False,
    )


def build_manifest_form_bank(
    manifest_paths: list[str | Path],
    *,
    blueprint: AssessmentBlueprint,
    bank_row_resolver: Callable[[int], dict[str, Any] | None],
    compiled_loader: Callable[[str], dict[str, Any]] | None = None,
    question_bank_size: int = 0,
    replicate_to_min: bool = False,
) -> _AssessmentFormBank:
    """N 份 manifest → 表单库。

    不足轮换下限(``MIN_FORM_ROTATION_COUNT``)时默认 fail;
    ``replicate_to_min=True`` 时以显式复制补足(form_id 带 ``__r<n>`` 后缀,
    过渡措施:所有学员拿同一张钉选表单,诚实登记于 form_source)。
    """

    if not manifest_paths:
        raise ManifestFormImportError("no_manifest_paths")
    forms: list[_AssessmentForm] = []
    for index, path in enumerate(manifest_paths, start=1):
        manifest, manifest_sha = load_form_manifest(path)
        forms.append(
            build_manifest_form(
                manifest,
                blueprint=blueprint,
                manifest_sha256=manifest_sha,
                bank_row_resolver=bank_row_resolver,
                compiled_loader=compiled_loader,
                form_index=index,
            )
        )
    if len(forms) < MIN_FORM_ROTATION_COUNT:
        if not replicate_to_min:
            raise ManifestFormImportError(
                f"form_rotation_short:{len(forms)}<{MIN_FORM_ROTATION_COUNT} "
                "(补足 manifest 或显式 replicate_to_min)"
            )
        base = list(forms)
        while len(forms) < MIN_FORM_ROTATION_COUNT:
            source = base[(len(forms) - len(base)) % len(base)]
            replica_index = len(forms) + 1
            forms.append(
                _AssessmentForm(
                    form_id=f"{source.form_id}__r{replica_index}",
                    form_index=replica_index,
                    units=source.units,
                    fallback_used=source.fallback_used,
                )
            )
    delivered = max(len(form.units) for form in forms)
    form_bank = _AssessmentFormBank(
        forms=tuple(forms),
        question_bank_size=max(int(question_bank_size or 0), delivered),
        form_source="manifest_pinned",
    )
    _validate_form_bank_rotation(form_bank, blueprint)
    return form_bank


def supabase_bank_row_resolver(
    provider: Any,
) -> Callable[[int], dict[str, Any] | None]:
    """从组卷供给面 provider 派生 qb 行 resolver(复用 _query 软删谓词入口)。"""

    def resolve(qb_id: int) -> dict[str, Any] | None:
        config = getattr(provider, "_supabase_config", None)
        query = getattr(provider, "_query", None)
        if not callable(config) or not callable(query):
            raise ManifestFormImportError(
                "bank_row_resolver_unavailable: manifest qb 钉选需要 Supabase 供给面"
            )
        base_url, api_key = config()
        rows = query(base_url, api_key, {"select": "*", "id": f"eq.{int(qb_id)}", "limit": "1"})
        return rows[0] if rows else None

    return resolve


__all__ = [
    "MANIFEST_SCHEMA",
    "ManifestFormImportError",
    "build_manifest_form",
    "build_manifest_form_bank",
    "load_form_manifest",
    "supabase_bank_row_resolver",
]
