#!/usr/bin/env python3
"""Student-answer grading shadow eval for rich/typed compiled knowledge.

This runner uses the student-answer markdown dataset as learner/sample evidence. It grades
student answers against source exam gold answers and compares grading-context arms. It does not
write learner memory, official scores, runtime defaults, or DB state.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import random
import re
from statistics import mean
import sys
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
DEFAULT_STUDENT_MD = SOURCE_ROOT / "题库/近三年案例题_按学生答卷排版.md"
DEFAULT_OUTPUT = REPO / "artifacts/luban_grading_artifacts/student_answer_grading_eval_20260613/student_answer_grading_eval.json"
DEFAULT_RICH_PACK = REPO / "artifacts/luban_grading_artifacts/rich_leaf_v32_scoring_point_compile_20260613/runtime_token_pack_v32_scoring_points.json"

# KnowQL ③: the per-point grading-output shape contract is owned by the canonical typed object
# (the artifact that defines the shape enforces it), not by this eval harness. Imported under the
# original name so the local validate_grading_output + the eval tests keep calling it unchanged.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from deeptutor.services.construction_grading.unified_grading_object import (  # noqa: E402
    enforce_grading_output_schema as enforce_output_schema,
)

SCHEMA = "luban_student_answer_grading_shadow_eval.v1"

ARM_REFERENCE_ONLY = "reference_only_grader"
ARM_KBV5_CLEAN = "kbv5_clean_grader"
ARM_RUNTIME_SLIM = "runtime_slim_grader"
ARM_TYPED_RUBRIC = "typed_rubric_grader"
ARM_COMPACT_SCORING_ARTIFACT = "compact_scoring_artifact_grader"
ARM_TYPED_CASE_GRADING_ARTIFACT = "typed_case_grading_artifact_grader"
ARM_KBV5_PLUS_RUNTIME_SLIM = "kbv5_plus_runtime_slim_grader"
ARM_KBV5_PLUS_TYPED_RUBRIC = "kbv5_plus_typed_rubric_grader"
ARM_KBV5_PLUS_COMPACT_SCORING_ARTIFACT = "kbv5_plus_compact_scoring_artifact_grader"
PLANNED_ARMS = [
    ARM_REFERENCE_ONLY,
    ARM_KBV5_CLEAN,
    ARM_RUNTIME_SLIM,
    ARM_TYPED_RUBRIC,
    ARM_COMPACT_SCORING_ARTIFACT,
    ARM_TYPED_CASE_GRADING_ARTIFACT,
    ARM_KBV5_PLUS_RUNTIME_SLIM,
    ARM_KBV5_PLUS_TYPED_RUBRIC,
    ARM_KBV5_PLUS_COMPACT_SCORING_ARTIFACT,
]
ALL_ARMS = tuple(PLANNED_ARMS)


def _load_case_eval_module():
    spec = importlib.util.spec_from_file_location(
        "run_luban_rich_leaf_case_question_eval",
        REPO / "scripts/run_luban_rich_leaf_case_question_eval.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load case-question eval helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


case_eval = _load_case_eval_module()

case_eval.PROVIDER_DEFAULTS.setdefault(
    "openai",
    {
        "env_key": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.5",
    },
)


def _clip(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_student_answer_md(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    starts = list(re.finditer(r"^### (Q(?P<year>\d{4})-\d{2})｜(?P<title>.+)$", text, flags=re.M))
    samples: list[dict[str, Any]] = []
    for index, match in enumerate(starts):
        block = text[match.start() : starts[index + 1].start() if index + 1 < len(starts) else len(text)]
        meta: dict[str, str] = {}
        for key in ("样本ID", "学生ID", "ability_label", "answer_quality_label", "中文标签", "预估得分区间"):
            found = re.search(rf"- {key}：`?([^`\n]+)`?", block)
            meta[key] = found.group(1).strip() if found else ""
        sample_id = meta.get("样本ID") or ""
        if not sample_id:
            continue
        question_match = re.search(r"#### 题目\s*\n(?P<question>.*?)(?=\n#### 回答\s*\n)", block, flags=re.S)
        answer_match = re.search(
            r"#### 回答\s*\n(?P<answer>.*?)(?=\n### .*参考答案|\n#### 本题水平判断|\n---\n|$)",
            block,
            flags=re.S,
        )
        if not question_match or not answer_match:
            continue
        score_low = score_high = None
        range_match = re.search(r"(\d+)\s*%\s*-\s*(\d+)\s*%", meta.get("预估得分区间") or "")
        if range_match:
            score_low, score_high = int(range_match.group(1)), int(range_match.group(2))
        source_chunks = list(dict.fromkeys(re.findall(r"EXAM_[A-Za-z0-9_]+", block)))
        samples.append(
            {
                "question_id": match.group(1),
                "title": match.group("title").strip(),
                "year": int(match.group("year")),
                "sample_id": sample_id,
                "student_id": meta.get("学生ID") or "",
                "ability_label": meta.get("ability_label") or "",
                "answer_quality_label": meta.get("answer_quality_label") or "",
                "score_range": [score_low, score_high] if score_low is not None and score_high is not None else None,
                "source_chunks": source_chunks,
                "question": question_match.group("question").strip(),
                "student_answer": re.sub(r"^作答：\s*", "", answer_match.group("answer").strip()),
            }
        )
    return samples


def _exam_path(year: int) -> Path:
    return SOURCE_ROOT / f"题库/{year}年一级建造师《建筑实务》考试真题及答案解析/FINAL_CLEANED_EXAM_V{year}.json"


def _load_exam(year: int) -> dict[str, Any]:
    return json.loads(_exam_path(year).read_text(encoding="utf-8"))


def build_gold_reference(sample: dict[str, Any]) -> dict[str, Any]:
    exam = _load_exam(int(sample["year"]))
    source_set = set(sample.get("source_chunks") or [])
    gold_points: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for chunk in exam.get("chunks") or []:
        if source_set and str(chunk.get("chunk_id") or "") not in source_set:
            continue
        for exercise in chunk.get("exercises") or []:
            if not isinstance(exercise, dict) or exercise.get("type") != "case_study":
                continue
            data = exercise.get("question_data") if isinstance(exercise.get("question_data"), dict) else {}
            parts = case_eval.split_case_stem(str(data.get("stem") or ""))
            if parts is None:
                continue
            _background, sub_no, sub_text = parts
            gold = str(data.get("correct_answer") or "").strip()
            if not gold:
                continue
            key = (str(sub_no), gold[:80])
            if key in seen:
                continue
            seen.add(key)
            gold_points.append(
                {
                    "sub_no": str(sub_no),
                    "question": sub_text,
                    "gold_answer": gold,
                    "score": float(data.get("score") or 0.0),
                    "analysis": str(data.get("analysis") or ""),
                }
            )
    return {
        "source_chunks": sorted(source_set),
        "gold_points": sorted(gold_points, key=lambda item: str(item.get("sub_no") or "")),
    }


def _reference_text(reference: dict[str, Any]) -> str:
    lines: list[str] = []
    for point in reference.get("gold_points") or []:
        lines.append(f"问题{point.get('sub_no')}: {point.get('gold_answer')}")
    return "\n".join(lines)


def _split_numbered_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(re.finditer(r"(?:^|\n)\s*(?P<no>\d+)[.、．]\s*", str(text or "")))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = str(text or "")[start:end].strip()
        if body:
            sections[match.group("no")] = body
    return sections


def _split_atomic_expected_points(answer: str) -> list[str]:
    text = re.sub(r"\s+", "", str(answer or "").strip(" 。；;"))
    if not text:
        return []
    after_colon = re.split(r"[:：]", text, maxsplit=1)
    candidate = after_colon[1] if len(after_colon) == 2 else text
    parts = [
        part.strip(" 。；;，,、")
        for part in re.split(r"[；;。]|[、，,](?=[^，,、；;。]{2,18}(?:工程|检|验|法|度|片|筋|厚度|强度|性能|色差|掉角|脱皮|检测|试验|确认|归档))", candidate)
        if part.strip(" 。；;，,、")
    ]
    if len(parts) <= 1:
        parts = [part.strip(" 。；;") for part in re.split(r"[；;。]+", text) if part.strip(" 。；;")]
    return parts or [text]


def _infer_scoring_intent(question: str, answer: str) -> str:
    joined = f"{question}\n{answer}"
    if any(word in joined for word in ("计算", "公式", "费用", "工期", "造价")):
        return "formula"
    if any(word in joined for word in ("不妥", "改正", "纠正")):
        return "flaw_correction"
    if any(word in joined for word in ("流程", "步骤", "工艺")):
        return "procedure"
    if any(word in joined for word in ("条件", "情形", "适用", "要求")):
        return "condition_check"
    return "list_items"


def build_textbook_provenance_index(pack: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    """Index a v3.2 rich-leaf pack by scoring-point term -> textbook source refs.

    Reuses the compiled pack's ``scoring_points`` provenance (chunk_id / quote /
    source_authority) so an atomic point can be bound to a textbook source_ref
    by required-term overlap. This never fabricates new truth — it only surfaces
    provenance the compile axis already verified.
    """
    index: dict[str, list[dict[str, Any]]] = {}
    seen: dict[str, set[str]] = {}
    units = (pack or {}).get("runtime_token_pack_units") or []
    for unit in units:
        compiled = unit.get("compiled_context") if isinstance(unit.get("compiled_context"), dict) else {}
        for scoring_point in compiled.get("scoring_points") or []:
            if not isinstance(scoring_point, dict):
                continue
            provenance = scoring_point.get("provenance") if isinstance(scoring_point.get("provenance"), dict) else {}
            source_ref = str(provenance.get("chunk_id") or provenance.get("source_ref") or "").strip()
            if not source_ref:
                continue
            entry = {
                "source_ref": source_ref,
                "source_authority": str(provenance.get("source_authority") or "textbook"),
                "quote": _clip(provenance.get("quote"), limit=160),
                "leaf_id": str(unit.get("leaf_id") or ""),
            }
            terms = list(scoring_point.get("required_terms") or [])
            for term in terms:
                key = _normalize_term(term)
                if not key:
                    continue
                bucket = seen.setdefault(key, set())
                if source_ref in bucket:
                    continue
                bucket.add(source_ref)
                index.setdefault(key, []).append(entry)
    return index


def _load_provenance_index(pack_path: Path | None) -> dict[str, list[dict[str, Any]]] | None:
    """Load a v3.2 scoring-point pack and index it for textbook provenance.

    Returns ``None`` (no provenance binding, all points marked unsourced) when
    the pack is absent or unreadable — the eval degrades, it never fabricates.
    """
    if not pack_path:
        return None
    path = Path(pack_path)
    if not path.exists():
        return None
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(pack, dict):
        return None
    return build_textbook_provenance_index(pack)


def _normalize_term(term: Any) -> str:
    return re.sub(r"\s+", "", str(term or "")).strip(" 。；;，,、:：")


def lookup_textbook_source_refs(text: Any, index: dict[str, list[dict[str, Any]]] | None) -> list[dict[str, Any]]:
    """Resolve textbook source refs for ``text`` via exact or substring term match."""
    if not index:
        return []
    key = _normalize_term(text)
    if not key:
        return []
    if key in index:
        return list(index[key])
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for term, entries in index.items():
        if len(term) >= 2 and (term in key or key in term):
            for entry in entries:
                ref = str(entry.get("source_ref") or "")
                if ref and ref not in seen:
                    seen.add(ref)
                    matches.append(entry)
    return matches


def _attach_point_provenance(
    scoring_point: dict[str, Any],
    *,
    gold_ref: str,
    provenance_index: dict[str, list[dict[str, Any]]] | None,
) -> dict[str, Any]:
    """Bind every atomic point to a gold ref and, when available, a textbook ref.

    Points with no textbook hit are marked ``sourced=False`` /
    ``source_authority="unsourced"`` — never silently dropped or fabricated.
    """
    candidates: list[Any] = [scoring_point.get("canonical_answer")]
    candidates.extend(scoring_point.get("required_terms") or [])
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        for entry in lookup_textbook_source_refs(candidate, provenance_index):
            ref = str(entry.get("source_ref") or "")
            if ref and ref not in seen:
                seen.add(ref)
                hits.append(entry)
    if hits:
        primary = hits[0]
        provenance = {
            "gold_ref": gold_ref,
            "source_ref": primary.get("source_ref"),
            "source_authority": primary.get("source_authority") or "textbook",
            "sourced": True,
            "textbook_quote": primary.get("quote") or "",
            "all_source_refs": [entry.get("source_ref") for entry in hits[:4]],
        }
    else:
        provenance = {
            "gold_ref": gold_ref,
            "source_ref": None,
            "source_authority": "unsourced",
            "sourced": False,
            "textbook_quote": "",
            "all_source_refs": [],
        }
    return {**scoring_point, "provenance": provenance}


def build_typed_case_grading_artifact(
    sample: dict[str, Any],
    reference: dict[str, Any],
    *,
    provenance_index: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Build a minimal Nexus-like point-level scoring contract for shadow eval."""
    subquestions: list[dict[str, Any]] = []
    source_chunks = reference.get("source_chunks") or []
    for point in reference.get("gold_points") or []:
        question_sections = _split_numbered_sections(str(point.get("question") or ""))
        answer_sections = _split_numbered_sections(str(point.get("gold_answer") or ""))
        if not answer_sections:
            sub_no = str(point.get("sub_no") or "")
            answer_sections = {sub_no: str(point.get("gold_answer") or "")}
            question_sections = {sub_no: str(point.get("question") or "")}
        total_score = float(point.get("score") or 0.0)
        section_score = total_score / max(len(answer_sections), 1)
        for sub_no in sorted(answer_sections, key=lambda value: int(value) if value.isdigit() else value):
            answer_text = answer_sections[sub_no]
            expected_points = _split_atomic_expected_points(answer_text)
            weight = section_score / max(len(expected_points), 1)
            scoring_points = []
            for index, expected in enumerate(expected_points, start=1):
                point_id = f"{sample.get('question_id')}-{sub_no}-P{index}"
                canonical = _clip(expected, limit=140)
                gold_ref = f"gold:{sample.get('question_id')}:{sub_no}"
                raw_point = {
                    "point_id": point_id,
                    "sub_no": sub_no,
                    "weight": round(weight, 4),
                    "canonical_answer": canonical,
                    "acceptable_variants": [canonical],
                    "required_terms": [term for term in re.split(r"[、，,；;和及与]", canonical) if 1 < len(term) <= 16][:4],
                    "miss_tags": ["漏列采分点"],
                    "source_refs": source_chunks,
                }
                scoring_points.append(
                    _attach_point_provenance(raw_point, gold_ref=gold_ref, provenance_index=provenance_index)
                )
            subquestions.append(
                {
                    "sub_no": sub_no,
                    "intent": _infer_scoring_intent(question_sections.get(sub_no, ""), answer_text),
                    "max_score": round(section_score, 4),
                    "question": _clip(question_sections.get(sub_no, ""), limit=220),
                    "scoring_points": scoring_points,
                    "partial_credit_rules": ["hit=覆盖该point_id核心语义; partial=只覆盖部分关键条件; miss=未答/答非所问/关键术语缺失"],
                    "common_traps": ["概括性整改表述不能替代明确采分点"],
                    "next_action_templates": ["围绕漏判point_id回看规范条文并做同类小问列项训练"],
                }
            )
    return {
        "artifact_schema": "case_grading_artifact.v1",
        "case_id": sample.get("question_id"),
        "sample_id": sample.get("sample_id"),
        "source": "official_reference_answer_restructured_as_point_contract",
        "source_chunks": source_chunks,
        "subquestions": subquestions,
        "score_aggregation": "sum(point.awarded_points) / sum(point.weight) * 100",
        "output_contract": {
            "must_emit_one_result_per_point_id": True,
            "score_must_equal_point_sum": True,
            "deduction_required_if_any_miss": True,
            "weakness_required_if_any_miss": True,
            "basis_ref_must_use_point_id": True,
        },
    }


def build_compact_scoring_artifact(reference: dict[str, Any]) -> dict[str, Any]:
    """Build a production-shaped compact rubric from official reference points.

    This is intentionally deterministic: it restructures existing official
    reference answers into a short point-wise artifact and does not create new
    scoring truth.
    """
    points: list[dict[str, Any]] = []
    for point in reference.get("gold_points") or []:
        gold = str(point.get("gold_answer") or "").strip()
        snippets = [
            chunk.strip(" ：:;；、-")
            for chunk in re.split(r"[\n。；;]+", gold)
            if chunk.strip(" ：:;；、-")
        ]
        points.append(
            {
                "sub_no": str(point.get("sub_no") or ""),
                "max_score": point.get("score"),
                "question": _clip(point.get("question"), limit=180),
                "expected_points": [_clip(snippet, limit=120) for snippet in snippets[:6]],
                "grading_policy": "hit=覆盖核心判断和关键做法; partial=只覆盖部分关键内容; miss=未答/答非所问/关键判断错",
                "deduction_shape": {
                    "must_name_missing_points": True,
                    "must_quote_student_evidence": True,
                    "must_emit_misconception_tag": True,
                    "must_emit_next_action": True,
                },
            }
        )
    return {
        "artifact_schema": "compact_scoring_artifact.v1",
        "source": "official_reference_answer_restructured",
        "source_chunks": reference.get("source_chunks") or [],
        "points": points,
        "output_contract": {
            "score_pct": "number",
            "point_results": "one result per sub_no, concise",
            "deduction_reasons": "only material missing or wrong points",
            "misconception_tags": "stable short Chinese tags",
            "next_review_action": "one concrete drill/review task",
        },
    }


def grading_context(
    arm: str,
    *,
    sample: dict[str, Any],
    retrieval: dict[str, Any],
    rich: dict[str, Any] | None,
    reference: dict[str, Any],
    provenance_index: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {"mode": arm}
    if arm in {
        ARM_KBV5_CLEAN,
        ARM_KBV5_PLUS_RUNTIME_SLIM,
        ARM_KBV5_PLUS_TYPED_RUBRIC,
        ARM_KBV5_PLUS_COMPACT_SCORING_ARTIFACT,
    }:
        context["retrieved_chunks"] = [
            {
                "chunk_id": chunk.get("chunk_id"),
                "doc_type": chunk.get("doc_type"),
                "content": _clip(chunk.get("content"), limit=450),
            }
            for chunk in retrieval.get("chunks") or []
        ]
    if arm in {ARM_RUNTIME_SLIM, ARM_KBV5_PLUS_RUNTIME_SLIM}:
        context["rich_leaf_grounding"] = (rich or {}).get("grounding") or ""
        context["rich_leaf_ids"] = (rich or {}).get("leaf_ids") or []
    if arm in {ARM_TYPED_RUBRIC, ARM_KBV5_PLUS_TYPED_RUBRIC}:
        context["typed_rubric_artifact"] = (rich or {}).get("typed_artifact") or {}
        context["typed_leaf_ids"] = (rich or {}).get("leaf_ids") or []
    if arm in {ARM_COMPACT_SCORING_ARTIFACT, ARM_KBV5_PLUS_COMPACT_SCORING_ARTIFACT}:
        context["compact_scoring_artifact"] = build_compact_scoring_artifact(reference)
    if arm == ARM_TYPED_CASE_GRADING_ARTIFACT:
        context["typed_case_grading_artifact"] = build_typed_case_grading_artifact(
            sample, reference, provenance_index=provenance_index
        )
    return context


def grading_messages(*, sample: dict[str, Any], reference: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    typed_artifact = context.get("typed_case_grading_artifact") if isinstance(context.get("typed_case_grading_artifact"), dict) else None
    payload = {
        "sample_id": sample["sample_id"],
        "student_id": sample["student_id"],
        "ability_label_hint_for_audit_only": sample.get("ability_label"),
        "question": _clip(sample.get("question"), limit=2600),
        "student_answer": _clip(sample.get("student_answer"), limit=2200),
        "reference_gold_points": [] if typed_artifact else reference.get("gold_points") or [],
        "context": context,
        "required_json": {
            "score_pct": "0-100 estimated score for THIS student answer",
            "point_results": [
                {
                    "point_id": "required when typed_case_grading_artifact is present",
                    "sub_no": "question number",
                    "status": "hit | partial | miss | contradiction",
                    "awarded_points": "numeric points awarded for this point_id",
                    "max_points": "numeric max points for this point_id",
                    "deduction_reason": "specific Chinese reason",
                    "student_evidence_quote": "short quote from student answer",
                    "basis_ref": "gold point id, chunk id, rich leaf id, or typed source ref",
                }
            ],
            "deduction_reasons": "list of clear Chinese deduction reasons",
            "misconception_tags": "list of stable tags, e.g. 责任主体混淆/数字阈值错误/计算基数错误/漏列采分点",
            "learning_evidence_event": {
                "knowledge_points": "list",
                "weaknesses": "list",
                "evidence_refs": "list",
            },
            "next_review_action": {
                "action_type": "review | drill | worked_example | recite",
                "focus": "specific focus",
                "concrete_task": "actionable next task in Chinese",
            },
            "confidence": "0-1",
            "citations": "list of evidence ids actually used",
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a strict Chinese construction-exam grader. Grade the STUDENT answer, not a model answer. "
                "If context contains typed_case_grading_artifact, use it as the rubric authority: emit exactly one point_results "
                "item for every scoring_points.point_id, include point_id, awarded_points, max_points, student_evidence_quote, "
                "and basis_ref=point_id, and make score_pct equal the point sum. If any point is miss/partial/contradiction, "
                "do not give a full score and explain the deduction. Otherwise use the reference gold points as rubric authority. "
                "Context may help clarify knowledge, but must not override the rubric authority. Return JSON only. Make deduction "
                "reasons, misconception_tags, learning_evidence_event, and next_review_action specific enough to support a learner profile. "
                "If context contains compact_scoring_artifact, follow its point-wise output contract and keep each point result concise."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


def judge_messages(*, sample: dict[str, Any], reference: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[list[dict[str, str]], dict[str, str]]:
    mapping = {str(index + 1): str(row.get("arm")) for index, row in enumerate(rows)}
    payload = {
        "sample_id": sample["sample_id"],
        "score_range_hint": sample.get("score_range"),
        "answer_quality_label": sample.get("answer_quality_label"),
        "question": _clip(sample.get("question"), limit=1800),
        "student_answer": _clip(sample.get("student_answer"), limit=1600),
        "reference_gold_points": reference.get("gold_points") or [],
        "grading_outputs": {
            str(index + 1): {
                "score_pct": row.get("score_pct"),
                "point_results": row.get("point_results"),
                "deduction_reasons": row.get("deduction_reasons"),
                "misconception_tags": row.get("misconception_tags"),
                "learning_evidence_event": row.get("learning_evidence_event"),
                "next_review_action": row.get("next_review_action"),
            }
            for index, row in enumerate(rows)
        },
        "required_json": {
            "candidates": {
                key: {
                    "point_decision_quality": "1-5",
                    "deduction_reason_clarity": "1-5",
                    "misconception_tag_quality": "1-5",
                    "learning_evidence_quality": "1-5",
                    "next_action_specificity": "1-5",
                    "overclaim": "boolean",
                    "notes": "short Chinese rationale",
                }
                for key in mapping
            }
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are auditing grader outputs for a student-answer grading system. Compare each candidate "
                "against the gold points and student answer. Reward accurate point hit/miss/partial decisions, "
                "clear deduction reasons, stable misconception tags, evidence-backed learning evidence, and actionable next review steps. "
                "Return JSON only."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ], mapping


def _score_range_hit(score_pct: Any, score_range: list[int | None] | None) -> bool | None:
    if not score_range or score_range[0] is None or score_range[1] is None:
        return None
    try:
        score = float(score_pct)
    except (TypeError, ValueError):
        return None
    return float(score_range[0]) <= score <= float(score_range[1])


def _mean(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def _contract_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Report-level scoring-contract validator outcome across all completed rows."""
    completed = [row for row in rows if row.get("status") == "completed"]
    validated = [row for row in completed if row.get("validation_status")]
    passed = [row for row in validated if row.get("validation_status") == "passed"]
    invalid = [row for row in validated if row.get("validation_status") == "contract_invalid"]
    regraded = [row for row in completed if row.get("regrade_attempted")]
    unsourced_total = sum(int(row.get("unsourced_point_count") or 0) for row in completed)
    return {
        "completed_rows": len(completed),
        "validated_rows": len(validated),
        "contract_valid_count": len(passed),
        "contract_invalid_count": len(invalid),
        "validator_pass_rate": _mean([1.0 if row in passed else 0.0 for row in validated]),
        "regrade_triggered_count": len(regraded),
        "unsourced_point_total": unsourced_total,
    }


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _grading_list(payload: dict[str, Any], *keys: str) -> list[Any]:
    value = _first_present(payload, keys)
    return value if isinstance(value, list) else []


def _grading_dict(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    value = _first_present(payload, keys)
    return value if isinstance(value, dict) else {}


def normalize_grading_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize live model grading JSON variants into the eval schema."""
    score_pct = _first_present(
        payload,
        (
            "score_pct",
            "score_percentage",
            "score_percent",
            "estimated_score_pct",
            "total_score_pct",
            "score",
        ),
    )
    return {
        "score_pct": score_pct,
        "point_results": _grading_list(payload, "point_results", "points", "subquestion_results", "grading_points"),
        "deduction_reasons": _grading_list(payload, "deduction_reasons", "deductions", "deduction_reason_list"),
        "misconception_tags": _grading_list(payload, "misconception_tags", "error_tags", "weakness_tags"),
        "learning_evidence_event": _grading_dict(payload, "learning_evidence_event", "learning_evidence"),
        "next_review_action": _grading_dict(payload, "next_review_action", "next_action", "review_action"),
        "citations": _grading_list(payload, "citations", "evidence_refs", "basis_refs"),
    }


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _negative_marker_present(values: Any) -> bool:
    text = json.dumps(values, ensure_ascii=False) if not isinstance(values, str) else values
    return any(marker in text for marker in ("漏", "未", "错", "缺", "不完整", "不准确", "答非所问"))


# ``enforce_output_schema`` / ``_REQUIRED_POINT_RESULT_FIELDS`` / valid statuses are lifted to the
# canonical typed object (deeptutor.services.construction_grading.unified_grading_object,
# ``enforce_grading_output_schema`` — imported at the top under the original name). KnowQL ③:
# the artifact that defines the rubric shape now also owns the grading-output shape it enforces.


def validate_grading_output(context: dict[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    point_results = normalized.get("point_results") if isinstance(normalized.get("point_results"), list) else []
    score_pct = _as_float(normalized.get("score_pct"))
    statuses = [str(item.get("status") or "").lower() for item in point_results if isinstance(item, dict)]
    has_non_hit = any(status in {"partial", "miss", "contradiction"} for status in statuses)
    if score_pct is not None and score_pct >= 95 and (
        has_non_hit
        or _negative_marker_present(normalized.get("deduction_reasons"))
        or _negative_marker_present(normalized.get("misconception_tags"))
        or _negative_marker_present(point_results)
    ):
        errors.append("high_score_conflicts_with_miss_or_deduction")

    artifact = context.get("typed_case_grading_artifact") if isinstance(context.get("typed_case_grading_artifact"), dict) else None
    if not artifact:
        return {"status": "passed" if not errors else "failed", "errors": errors, "warnings": warnings}

    # Hardening 2: locked per-point output schema. Any missing/typed field makes
    # the row a contract_invalid that must be regraded once.
    schema_errors = enforce_output_schema(point_results)
    errors.extend(schema_errors)

    expected_points: dict[str, float] = {}
    point_sub_no: dict[str, str] = {}
    sub_no_points: dict[str, list[str]] = defaultdict(list)
    unsourced_ids: list[str] = []
    for subquestion in artifact.get("subquestions") or []:
        sub_no = str(subquestion.get("sub_no") or "")
        for point in subquestion.get("scoring_points") or []:
            point_id = str(point.get("point_id") or "")
            if not point_id:
                continue
            expected_points[point_id] = float(point.get("weight") or 0.0)
            point_sub_no[point_id] = sub_no
            sub_no_points[sub_no].append(point_id)
            provenance = point.get("provenance") if isinstance(point.get("provenance"), dict) else {}
            if provenance and provenance.get("sourced") is False:
                unsourced_ids.append(point_id)
    if unsourced_ids:
        # Hardening 1: surface compile-axis gaps, never fabricate a source.
        warnings.append("unsourced_scoring_points:" + ",".join(unsourced_ids[:8]))

    emitted_ids = [str(item.get("point_id") or item.get("basis_ref") or "") for item in point_results if isinstance(item, dict)]
    missing_ids = sorted(point_id for point_id in expected_points if point_id not in emitted_ids)
    extra_ids = sorted(point_id for point_id in emitted_ids if point_id and point_id not in expected_points)
    if missing_ids:
        errors.append("missing_point_results:" + ",".join(missing_ids[:8]))
    if extra_ids:
        warnings.append("unknown_point_results:" + ",".join(extra_ids[:8]))

    # Hardening 3c: every artifact sub_no must have at least one emitted point
    # result — graders may not collapse the 5 sub-questions (or the 4-point 节能
    # sub-question) into a single result.
    emitted_sub_nos: set[str] = set()
    for item in point_results:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("point_id") or item.get("basis_ref") or "")
        if pid in point_sub_no:
            emitted_sub_nos.add(point_sub_no[pid])
    collapsed_subs = sorted(sub for sub in sub_no_points if sub not in emitted_sub_nos)
    if collapsed_subs:
        errors.append("subquestion_without_point_results:" + ",".join(collapsed_subs[:8]))

    awarded_total = 0.0
    max_total = sum(expected_points.values())
    saw_awarded = False
    for item in point_results:
        if not isinstance(item, dict):
            continue
        point_id = str(item.get("point_id") or item.get("basis_ref") or "")
        if point_id not in expected_points:
            continue
        awarded = _as_float(item.get("awarded_points"))
        max_points = _as_float(item.get("max_points"))
        status = str(item.get("status") or "").lower()
        if awarded is None:
            errors.append(f"missing_awarded_points:{point_id}")
            continue
        saw_awarded = True
        if max_points is not None and abs(max_points - expected_points[point_id]) > 0.05:
            warnings.append(f"max_points_mismatch:{point_id}")
        # Hardening 3a (per point): awarded within [0, max].
        if awarded < -0.001 or awarded - expected_points[point_id] > 0.05:
            errors.append(f"awarded_points_out_of_range:{point_id}")
        # Hardening 3b: any miss/partial/contradiction needs a deduction reason.
        if status in {"partial", "miss", "contradiction"} and not str(item.get("deduction_reason") or "").strip():
            errors.append(f"missing_deduction_reason:{point_id}")
        awarded_total += max(0.0, min(awarded, expected_points[point_id]))

    # Hardening 3a (aggregate): Σawarded must not exceed Σmax.
    raw_awarded_total = sum(
        _as_float(item.get("awarded_points")) or 0.0
        for item in point_results
        if isinstance(item, dict) and str(item.get("point_id") or item.get("basis_ref") or "") in expected_points
    )
    if max_total > 0 and raw_awarded_total - max_total > 0.05:
        errors.append(f"awarded_sum_exceeds_max:awarded={raw_awarded_total:.2f},max={max_total:.2f}")

    recomputed_score_pct = round((awarded_total / max_total * 100.0), 2) if saw_awarded and max_total > 0 else None
    # Hardening 3d: declared score_pct must be self-consistent with Σawarded/Σmax.
    if recomputed_score_pct is not None and score_pct is not None and abs(score_pct - recomputed_score_pct) > 2.0:
        errors.append(f"score_pct_mismatch:model={score_pct:.2f},point_sum={recomputed_score_pct:.2f}")

    status = "contract_invalid" if errors else "passed"
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "should_regrade": status == "contract_invalid",
        "expected_point_count": len(expected_points),
        "emitted_point_count": len(emitted_ids),
        "unsourced_point_count": len(unsourced_ids),
        "recomputed_score_pct": recomputed_score_pct,
    }


def build_report(
    *,
    samples: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    judge_rows: list[dict[str, Any]],
    provider_configured: bool,
    grader_model: str,
    judge_model: str | None,
    rich_supply: dict[str, Any] | None,
    kbv5_status: dict[str, Any],
    planned_arms: list[str],
) -> dict[str, Any]:
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_arm[str(row.get("arm"))].append(row)
    arms: list[dict[str, Any]] = []
    for arm in planned_arms:
        arm_rows = by_arm.get(arm, [])
        completed = [row for row in arm_rows if row.get("status") == "completed"]
        judged = [row for row in completed if row.get("judge_status") == "completed"]
        quality_keys = [
            "point_decision_quality",
            "deduction_reason_clarity",
            "misconception_tag_quality",
            "learning_evidence_quality",
            "next_action_specificity",
        ]
        arms.append(
            {
                "arm": arm,
                "sample_count": len(arm_rows),
                "completed_count": len(completed),
                "score_range_hit_rate": _mean([1.0 if row.get("score_range_hit") else 0.0 for row in completed if row.get("score_range_hit") is not None]),
                "mean_score_pct": _mean([float(row.get("score_pct")) for row in completed if row.get("score_pct") is not None]),
                "judge_quality_score": _mean(
                    [
                        mean([float(row.get(key) or 0.0) for key in quality_keys])
                        for row in judged
                    ]
                ),
                **{key: _mean([float(row.get(key) or 0.0) for row in judged]) for key in quality_keys},
                "overclaim_rate": _mean([1.0 if row.get("overclaim") else 0.0 for row in judged]),
                "validation_pass_rate": _mean([1.0 if row.get("validation_status") == "passed" else 0.0 for row in completed]),
                "contract_invalid_rate": _mean([1.0 if row.get("validation_status") == "contract_invalid" else 0.0 for row in completed]),
                "regrade_rate": _mean([1.0 if row.get("regrade_attempted") else 0.0 for row in completed]),
                "mean_total_tokens": _mean([float(row.get("total_tokens") or 0.0) for row in completed]),
            }
        )
    prompt_tokens = sum(int(row.get("prompt_tokens") or 0) for row in rows + judge_rows)
    completion_tokens = sum(int(row.get("completion_tokens") or 0) for row in rows + judge_rows)
    blockers: list[str] = []
    if not provider_configured:
        blockers.append("provider_call_not_configured")
    if not samples:
        blockers.append("no_student_samples")
    return {
        "schema": SCHEMA,
        "runtime_exercised": bool(rows) and not blockers,
        "model": grader_model if rows else None,
        "models": {
            "grader_model": grader_model if rows else None,
            "judge_model": judge_model,
            "judge_mode": "provider" if judge_model else "external_or_skipped",
        },
        "sample": {
            "sample_count": len(samples),
            "sample_ids": [sample["sample_id"] for sample in samples],
            "ability_labels": sorted({sample.get("ability_label") for sample in samples}),
        },
        "kbv5_retrieval": kbv5_status,
        "rich_supply": rich_supply,
        "provider_usage": {
            "grading_call_count": len([row for row in rows if row.get("status") == "completed"]),
            "judge_call_count": len([row for row in judge_rows if row.get("status") == "completed"]),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "arms": arms,
        "rows": rows,
        "judge_rows": judge_rows,
        "contract_summary": _contract_summary(rows),
        "blockers": blockers,
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "student_answer_grading_shadow_eval": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "safety": {
            "official_score_allowed": False,
            "canonical_truth_written": False,
            "learner_memory_write_count": 0,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def run_eval(
    *,
    samples: list[dict[str, Any]],
    provider_call,
    judge_provider_call=None,
    retriever,
    rich_resolver,
    grader_model: str,
    judge_model: str | None = None,
    grading_max_tokens: int = 1200,
    judge_max_tokens: int = 1200,
    planned_arms: list[str] | None = None,
    output_path: Path | None = None,
    provenance_index: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    judge_rows: list[dict[str, Any]] = []
    active_arms = planned_arms or list(PLANNED_ARMS)
    kbv5_status = {
        "channel": "kb_v5.search_chunks_v2",
        "config": getattr(retriever, "config", None),
        "degraded": False,
        "unavailable_count": 0,
    }
    rich_supply = getattr(rich_resolver, "supply_info", None)

    def checkpoint() -> dict[str, Any]:
        report = build_report(
            samples=samples,
            rows=rows,
            judge_rows=judge_rows,
            provider_configured=provider_call is not None,
            grader_model=grader_model,
            judge_model=judge_model,
            rich_supply=rich_supply,
            kbv5_status=kbv5_status,
            planned_arms=active_arms,
        )
        if output_path:
            _write_json(output_path, report)
        return report

    if provider_call is None:
        return checkpoint()

    for sample in samples:
        reference = build_gold_reference(sample)
        if not reference.get("gold_points"):
            continue
        query = f"{sample['question']}\n学生作答：{sample['student_answer']}"
        retrieval = retriever(query) if retriever else {"status": "skipped", "chunks": [], "latency_ms": 0.0}
        if retrieval.get("status") != "completed":
            kbv5_status["degraded"] = True
            kbv5_status["unavailable_count"] += 1
        rich = rich_resolver(str(sample["question"]), str(sample["student_answer"])) if rich_resolver else None
        sample_rows: list[dict[str, Any]] = []
        for arm in active_arms:
            context = grading_context(
                arm,
                sample=sample,
                retrieval=retrieval,
                rich=rich,
                reference=reference,
                provenance_index=provenance_index,
            )
            row: dict[str, Any] = {
                "sample_id": sample["sample_id"],
                "question_id": sample["question_id"],
                "student_id": sample["student_id"],
                "ability_label": sample.get("ability_label"),
                "answer_quality_label": sample.get("answer_quality_label"),
                "score_range": sample.get("score_range"),
                "arm": arm,
                "gold_point_count": len(reference.get("gold_points") or []),
                "typed_artifact_schema": (context.get("typed_rubric_artifact") or {}).get("artifact_schema")
                if isinstance(context.get("typed_rubric_artifact"), dict)
                else (context.get("typed_case_grading_artifact") or {}).get("artifact_schema")
                if isinstance(context.get("typed_case_grading_artifact"), dict)
                else None,
                "rich_leaf_ids": context.get("rich_leaf_ids") or context.get("typed_leaf_ids") or None,
            }
            try:
                base_messages = grading_messages(sample=sample, reference=reference, context=context)
                response = provider_call(base_messages, max_tokens=grading_max_tokens)
                content = str(response.get("content") or "")
                parsed = case_eval._parse_json_object(content)
                normalized = normalize_grading_payload(parsed)
                validation = validate_grading_output(context, normalized)
                prompt_tokens = int(response.get("prompt_tokens") or 0)
                completion_tokens = int(response.get("completion_tokens") or 0)
                regrade_attempted = False
                # Contract enforcement: a contract_invalid output earns exactly one
                # regrade with the violations fed back. The retry result is kept
                # only if it is itself contract-valid.
                if validation.get("should_regrade"):
                    regrade_attempted = True
                    retry_messages = base_messages + [
                        {"role": "assistant", "content": content[:2400]},
                        {
                            "role": "user",
                            "content": (
                                "你上一次的判分输出违反了评分合约，必须修正后重新输出 JSON。违规清单："
                                + json.dumps(validation.get("errors") or [], ensure_ascii=False)
                                + "。要求：每个 point_id 都要有一条结果且锁死字段齐全（sub_no/max_points/required_points/"
                                "accepted_variants/student_evidence_quote/status/awarded_points/deduction_reason/"
                                "misconception_tag/next_review_action/learning_evidence_event）；所有小问都要有结果，"
                                "不得合并小问；Σawarded≤Σmax；任何 miss/partial 必须给出非空 deduction_reason；"
                                "score_pct 必须与 Σawarded/Σmax 自洽。只返回 JSON。"
                            ),
                        },
                    ]
                    retry = provider_call(retry_messages, max_tokens=grading_max_tokens)
                    retry_content = str(retry.get("content") or "")
                    retry_parsed = case_eval._parse_json_object(retry_content)
                    retry_normalized = normalize_grading_payload(retry_parsed)
                    retry_validation = validate_grading_output(context, retry_normalized)
                    prompt_tokens += int(retry.get("prompt_tokens") or 0)
                    completion_tokens += int(retry.get("completion_tokens") or 0)
                    if retry_validation.get("status") != "contract_invalid":
                        content, parsed, normalized, validation, response = (
                            retry_content,
                            retry_parsed,
                            retry_normalized,
                            retry_validation,
                            retry,
                        )
                score_pct = normalized.get("score_pct")
                row.update(
                    {
                        "status": "completed",
                        "raw_response": content[:2400],
                        "parsed_keys": sorted(str(key) for key in parsed.keys()),
                        "finish_reason": response.get("finish_reason"),
                        "score_pct": score_pct,
                        "score_range_hit": _score_range_hit(score_pct, sample.get("score_range")),
                        "point_results": normalized["point_results"],
                        "deduction_reasons": normalized["deduction_reasons"],
                        "misconception_tags": normalized["misconception_tags"],
                        "learning_evidence_event": normalized["learning_evidence_event"],
                        "next_review_action": normalized["next_review_action"],
                        "citations": normalized["citations"],
                        "validation": validation,
                        "validation_status": validation.get("status"),
                        "validation_errors": validation.get("errors") or [],
                        "validation_warnings": validation.get("warnings") or [],
                        "unsourced_point_count": validation.get("unsourced_point_count"),
                        "regrade_attempted": regrade_attempted,
                        "recomputed_score_pct": validation.get("recomputed_score_pct"),
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    }
                )
            except Exception as exc:  # pragma: no cover - live failure path
                row.update({"status": "failed", "error": str(exc)[:240], "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
            sample_rows.append(row)
        completed = [row for row in sample_rows if row.get("status") == "completed"]
        if completed and judge_provider_call is not None:
            try:
                messages, mapping = judge_messages(sample=sample, reference=reference, rows=completed)
                response = judge_provider_call(messages, max_tokens=judge_max_tokens)
                parsed = case_eval._parse_json_object(str(response.get("content") or ""))
                candidates = parsed.get("candidates") if isinstance(parsed.get("candidates"), dict) else {}
                judge_rows.append(
                    {
                        "sample_id": sample["sample_id"],
                        "status": "completed",
                        "mapping": mapping,
                        "prompt_tokens": int(response.get("prompt_tokens") or 0),
                        "completion_tokens": int(response.get("completion_tokens") or 0),
                        "finish_reason": response.get("finish_reason"),
                    }
                )
                for ordinal, arm in mapping.items():
                    candidate = candidates.get(ordinal) if isinstance(candidates.get(ordinal), dict) else {}
                    for row in sample_rows:
                        if row.get("arm") == arm:
                            row.update(
                                {
                                    "judge_status": "completed",
                                    "point_decision_quality": float(candidate.get("point_decision_quality") or 0),
                                    "deduction_reason_clarity": float(candidate.get("deduction_reason_clarity") or 0),
                                    "misconception_tag_quality": float(candidate.get("misconception_tag_quality") or 0),
                                    "learning_evidence_quality": float(candidate.get("learning_evidence_quality") or 0),
                                    "next_action_specificity": float(candidate.get("next_action_specificity") or 0),
                                    "overclaim": bool(candidate.get("overclaim")),
                                    "judge_notes": str(candidate.get("notes") or "")[:240],
                        }
                    )
            except Exception as exc:  # pragma: no cover - live failure path
                judge_rows.append({"sample_id": sample["sample_id"], "status": "failed", "error": str(exc)[:240]})
        elif completed:
            judge_rows.append(
                {
                    "sample_id": sample["sample_id"],
                    "status": "skipped",
                    "reason": "external_or_manual_judge",
                    "arms": [row.get("arm") for row in completed],
                }
            )
        rows.extend(sample_rows)
        checkpoint()
    return checkpoint()


def _select_samples(samples: list[dict[str, Any]], *, sample_ids: str, limit: int, seed: int) -> list[dict[str, Any]]:
    by_id = {sample["sample_id"]: sample for sample in samples}
    if sample_ids:
        return [by_id[sid.strip()] for sid in sample_ids.split(",") if sid.strip() in by_id]
    eligible = [sample for sample in samples if sample.get("source_chunks")]
    rng = random.Random(seed)
    return sorted(rng.sample(eligible, min(limit, len(eligible))), key=lambda sample: sample["sample_id"])


def parse_arm_list(value: str) -> list[str]:
    arms = [arm.strip() for arm in str(value or "").split(",") if arm.strip()]
    if not arms:
        return list(PLANNED_ARMS)
    unknown = [arm for arm in arms if arm not in ALL_ARMS]
    if unknown:
        raise ValueError(f"unknown arms: {', '.join(unknown)}")
    return arms


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--student-md", type=Path, default=DEFAULT_STUDENT_MD)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--rich-pack", type=Path, default=DEFAULT_RICH_PACK)
    parser.add_argument("--sample-ids", default="")
    parser.add_argument("--arms", default=",".join(PLANNED_ARMS))
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260613)
    parser.add_argument("--provider", choices=sorted(case_eval.PROVIDER_DEFAULTS), default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--judge-provider", choices=sorted(case_eval.PROVIDER_DEFAULTS), default=None)
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--skip-llm-judge", action="store_true")
    parser.add_argument("--timeout-s", type=float, default=60.0)
    parser.add_argument("--grading-max-tokens", type=int, default=1200)
    parser.add_argument("--judge-max-tokens", type=int, default=1200)
    parser.add_argument("--no-provider-call", action="store_true")
    args = parser.parse_args(argv)

    model = args.model or case_eval.PROVIDER_DEFAULTS[args.provider]["model"]
    planned_arms = parse_arm_list(args.arms)
    provider_call = None if args.no_provider_call else case_eval._openai_compat_provider(provider=args.provider, model=model, timeout_s=args.timeout_s)
    judge_provider = args.judge_provider or args.provider
    judge_model = None
    judge_provider_call = None
    if provider_call is not None and not args.skip_llm_judge:
        judge_model = args.judge_model or case_eval.PROVIDER_DEFAULTS[judge_provider]["model"]
        judge_provider_call = case_eval._openai_compat_provider(provider=judge_provider, model=judge_model, timeout_s=args.timeout_s)
    samples = _select_samples(parse_student_answer_md(args.student_md), sample_ids=args.sample_ids, limit=args.limit, seed=args.seed)
    provenance_index = _load_provenance_index(args.rich_pack) if provider_call is not None else None
    report = run_eval(
        samples=samples,
        provider_call=provider_call,
        judge_provider_call=judge_provider_call,
        retriever=case_eval._kbv5_retriever(3, doc_types=case_eval.DEFAULT_KBV5_DOC_TYPES) if provider_call is not None else None,
        rich_resolver=(
            case_eval._rich_resolver(pack_path=args.rich_pack, grading=True, source_root=SOURCE_ROOT)
            if provider_call is not None
            else None
        ),
        grader_model=model,
        judge_model=judge_model,
        grading_max_tokens=args.grading_max_tokens,
        judge_max_tokens=args.judge_max_tokens,
        planned_arms=planned_arms,
        output_path=args.output,
        provenance_index=provenance_index,
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "runtime_exercised": report["runtime_exercised"],
                "models": report["models"],
                "sample": report["sample"],
                "provider_usage": report["provider_usage"],
                "arms": [
                    {
                        key: arm.get(key)
                        for key in (
                            "arm",
                            "sample_count",
                            "score_range_hit_rate",
                            "judge_quality_score",
                            "point_decision_quality",
                            "deduction_reason_clarity",
                            "misconception_tag_quality",
                            "learning_evidence_quality",
                            "next_action_specificity",
                            "validation_pass_rate",
                            "mean_total_tokens",
                        )
                    }
                    for arm in report["arms"]
                ],
                "blockers": report["blockers"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["runtime_exercised"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
