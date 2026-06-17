#!/usr/bin/env python3
"""Find review-only source candidates for RichLeaf missing source lanes.

This is a source-evidence workbench. It may use local source records, runtime
source refs, or retrieval chunks as candidate retrieval input, but the output is
not authority and never installs evidence into canonical/runtime artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SKELETON_BATCH = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_skeleton_candidates_20260611/rich_leaf_skeleton_candidates.json"
)
DEFAULT_SAMPLE_MANIFEST = (
    REPO / "artifacts/luban_grading_artifacts/rich_leaf_phase1_sampler_20260611/sample_manifest.json"
)
DEFAULT_UNIFIED_BUNDLE = (
    REPO
    / "deeptutor/services/construction_grading/runtime_supply/v_canonical_unified_knowledge/canonical_unified_knowledge.json"
)
DEFAULT_SOURCE_ROOT = Path(
    os.getenv(
        "LUBAN_RICH_LEAF_SOURCE_ROOT",
        "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库",
    )
)
DEFAULT_OUTPUT_DIR = REPO / "artifacts/luban_grading_artifacts/rich_leaf_source_gap_candidates_20260611"
VALID_SOURCE_LANES = {"textbook", "standard", "lecture", "question"}
TEXT_KEYS = (
    "content_markdown",
    "markdown",
    "text",
    "text_preview",
    "span",
    "clause_text",
    "body",
    "answer",
    "analysis",
    "title",
    "heading",
)
STOP_TERMS = {
    "建筑工程技术",
    "建筑工程",
    "建筑",
    "施工",
    "工程",
    "技术",
    "要求",
    "管理",
    "应用",
    "分类",
    "内容",
}
OPTION_MARKER_TERMS = {"a", "b", "c", "d", "a.", "b.", "c.", "d.", "A.", "B.", "C.", "D."}
PRACTICE_PATH_MARKERS = ("必刷", "千题", "题斩", "考证宝典", "mcq", "practice")
PRACTICE_CONTENT_TYPES = {"exercise", "question", "quiz", "mcq", "practice", "exam_trend"}
PRACTICE_ROW_KEYS = {
    "exercises",
    "question_data",
    "correct_answer",
    "options",
    "analysis",
    "answer_analysis",
}
PRACTICE_TEXT_MARKERS = (
    "必刷",
    "千题",
    "题斩",
    "考证宝典",
    "mcq",
    "practice",
    "exercise",
    "question_data",
    "correct_answer",
)


@dataclass(frozen=True)
class SourceRecord:
    source_lane: str
    source_path: str
    record_id: str
    text: str
    provenance: dict[str, Any]
    span: str | None = None
    span_hash: str | None = None
    retrieval_stage: str = "source_record"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()


def _split_terms(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[>\s/、，,（）()：:；;|]+", text) if part.strip()]


def _normalize_search_term(term: str) -> str:
    return str(term or "").strip().strip("*#[]【】「」'\"“”‘’。.!！?？")


def _is_searchable_term(term: str) -> bool:
    normalized = _normalize_search_term(term)
    if len(normalized) < 2 or normalized in STOP_TERMS or normalized in OPTION_MARKER_TERMS:
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z0-9]", normalized))


def _explicit_lane_from_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.lower()
    if text in ("textbook", "教材", "教材原文"):
        return "textbook"
    if text in ("standard", "规范", "标准"):
        return "standard"
    if text in ("lecture", "讲义", "课件"):
        return "lecture"
    if (
        text in ("question", "题库", "真题", "答案", "解析")
        or "question" in text
        or "exam" in text
        or "answer" in text
        or "题库" in value
        or "真题" in value
        or "答案" in value
        or "解析" in value
    ):
        return "question"
    if "教材" in value:
        return "textbook"
    if "规范" in value or "标准" in value:
        return "standard"
    if "讲义" in value or "课件" in value:
        return "lecture"
    return None


def _source_lane_from_path(path: Path) -> str | None:
    joined = "/".join(path.parts)
    joined_lower = joined.lower()
    if any(marker in joined for marker in PRACTICE_PATH_MARKERS) or any(
        marker in joined_lower for marker in PRACTICE_PATH_MARKERS
    ):
        return "question"
    has_question_marker = any(
        marker in joined for marker in ("真题", "答案解析", "学生答卷", "按学生答卷", "试题", "案例题")
    ) or any(
        marker in joined_lower for marker in ("question", "exam", "answer", "final_cleaned_exam")
    )
    explicit_support_markers = (
        ("textbook", ("2026教材", "教材原文", "课本原文")),
        ("standard", ("标准文件", "规范原文", "标准原文", "规范条文")),
        ("lecture", ("讲义", "课件", "授课")),
    )
    for lane, markers in explicit_support_markers:
        if any(marker in joined for marker in markers):
            return lane
    if has_question_marker:
        return "question"
    generic_support_markers = (
        ("textbook", ("教材", "课本")),
        ("standard", ("规范", "标准")),
        ("lecture", ("讲义", "课件", "授课")),
    )
    for lane, markers in generic_support_markers:
        if any(marker in joined for marker in markers):
            return lane
    return None


def _row_is_practice_source(row: dict[str, Any]) -> bool:
    content_type = str(row.get("content_type") or "").strip().lower()
    if content_type in PRACTICE_CONTENT_TYPES:
        return True
    if PRACTICE_ROW_KEYS & set(row):
        return True
    row_text = json.dumps(
        {
            "source_path": row.get("source_path"),
            "record_id": row.get("record_id") or row.get("chunk_id"),
            "provenance": row.get("provenance"),
            "source_meta": row.get("source_meta"),
            "meta_info": row.get("meta_info"),
            "document_meta": row.get("document_meta"),
            "taxonomy": row.get("taxonomy"),
            "snippet": row.get("snippet"),
            "source": row.get("source"),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).lower()
    if any(marker in row_text for marker in PRACTICE_TEXT_MARKERS):
        return True
    meta = row.get("meta")
    if isinstance(meta, dict):
        meta_content_type = str(meta.get("content_type") or "").strip().lower()
        if meta_content_type in PRACTICE_CONTENT_TYPES:
            return True
    return False


def _source_lane(path: Path, row: dict[str, Any] | None = None) -> str:
    path_lane = _source_lane_from_path(path)
    if path_lane:
        return path_lane
    if row and _row_is_practice_source(row):
        return "question"
    if row:
        for key in ("source_lane", "lane", "source_type", "source_dataset_id", "authority_tier"):
            lane = _explicit_lane_from_value(row.get(key))
            if lane:
                return lane
        for key in ("source_meta", "meta_info", "taxonomy", "document_meta", "provenance"):
            value = row.get(key)
            if isinstance(value, dict):
                for nested in value.values():
                    lane = _explicit_lane_from_value(nested)
                    if lane:
                        return lane
    return "unknown"


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _record_text(row: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key in TEXT_KEYS:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            chunks.append(value)
    for key in ("source_meta", "meta_info", "taxonomy", "document_meta", "provenance"):
        meta = row.get(key)
        if not isinstance(meta, dict):
            continue
        for meta_key in ("core_entity", "taxonomy_path", "node_name", "topic", "source", "lecture"):
            value = meta.get(meta_key)
            if isinstance(value, str) and value.strip():
                chunks.append(value)
    return "\n".join(part.strip() for part in chunks if part.strip())


def _record_id(row: dict[str, Any], fallback: str) -> str:
    for key in ("record_id", "unit_id", "chunk_id", "node_id", "id", "clause_id", "source_ref_id"):
        value = row.get(key)
        if value:
            return str(value)
    return fallback


def _provenance(row: dict[str, Any]) -> dict[str, Any]:
    provenance: dict[str, Any] = {}
    for key in ("source_path", "source_meta", "meta_info", "taxonomy", "document_meta", "provenance"):
        value = row.get(key)
        if isinstance(value, (dict, str, int, float, bool)):
            provenance[key] = value
    return provenance


def _span_for_record(text: str, row: dict[str, Any] | None = None, max_len: int = 900) -> str:
    if row:
        for key in ("span", "text_preview", "content_markdown", "markdown", "text"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:max_len]
    return text.strip()[:max_len]


def _source_path_for_row(path: str, row: dict[str, Any]) -> str:
    for key in ("source_path", "path", "source_file"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    provenance = row.get("provenance")
    if isinstance(provenance, dict):
        for key in ("source_path", "path", "source", "lecture"):
            value = provenance.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return path


def _record_from_dict(row: dict[str, Any], fallback_path: str, fallback_id: str) -> SourceRecord | None:
    text = _record_text(row)
    if len(_clean_text(text)) < 8:
        return None
    path = _source_path_for_row(fallback_path, row)
    path_lane = _source_lane_from_path(Path(path))
    if path_lane:
        lane = path_lane
    elif _row_is_practice_source(row):
        lane = "question"
    else:
        lane = str(row.get("source_lane") or row.get("lane") or _source_lane(Path(path), row))
    if lane not in VALID_SOURCE_LANES:
        lane = _source_lane(Path(path), row)
    span = _span_for_record(text, row)
    return SourceRecord(
        source_lane=lane,
        source_path=path,
        record_id=_record_id(row, fallback_id),
        text=text,
        provenance=_provenance(row),
        span=span,
        span_hash=str(row.get("span_hash") or row.get("content_hash") or _sha256(span)),
        retrieval_stage=str(row.get("retrieval_stage") or "source_record"),
    )


def _chunk_markdown(text: str, *, source_path: str, source_lane: str, chunk_size: int = 1600) -> list[SourceRecord]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) > chunk_size:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}".strip()
    if current:
        chunks.append(current)
    if not chunks and text.strip():
        chunks.append(text.strip()[:chunk_size])
    return [
        SourceRecord(
            source_lane=source_lane,
            source_path=source_path,
            record_id=f"{source_path}#chunk-{idx}",
            text=chunk,
            provenance={"source_path": source_path},
            span=chunk[:900],
            span_hash=_sha256(chunk[:900]),
            retrieval_stage="local_corpus_chunk",
        )
        for idx, chunk in enumerate(chunks)
        if len(_clean_text(chunk)) >= 8
    ]


def load_source_records_from_root(source_root: Path) -> list[SourceRecord]:
    if not source_root.exists():
        return []
    paths = [source_root] if source_root.is_file() else sorted(source_root.rglob("*"))
    records: list[SourceRecord] = []
    for path in paths:
        if not path.is_file() or path.name.startswith("."):
            continue
        try:
            rel_path = str(path.relative_to(source_root if source_root.is_dir() else source_root.parent))
        except ValueError:
            rel_path = str(path)
        if path.suffix.lower() == ".json":
            try:
                payload = _read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            file_lane = _source_lane(path)
            if isinstance(payload, dict):
                meta = payload.get("meta")
                if isinstance(meta, dict) and file_lane not in VALID_SOURCE_LANES:
                    file_lane = _source_lane(path, meta)
            seen: set[str] = set()
            for idx, row in enumerate(_walk_dicts(payload)):
                row_lane = _source_lane(path, row)
                if row_lane not in VALID_SOURCE_LANES and file_lane in VALID_SOURCE_LANES:
                    row_lane = file_lane
                if row_lane not in VALID_SOURCE_LANES:
                    continue
                record = _record_from_dict(row, rel_path, f"{rel_path}#{idx}")
                if not record:
                    continue
                record = SourceRecord(
                    source_lane=row_lane,
                    source_path=record.source_path or rel_path,
                    record_id=record.record_id,
                    text=record.text,
                    provenance=record.provenance,
                    span=record.span,
                    span_hash=record.span_hash,
                    retrieval_stage="local_corpus_record",
                )
                key = f"{record.source_lane}:{record.source_path}:{record.record_id}:{record.span_hash}"
                if key in seen:
                    continue
                seen.add(key)
                records.append(record)
        elif path.suffix.lower() in {".md", ".txt"}:
            lane = _source_lane(path)
            if lane not in VALID_SOURCE_LANES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            records.extend(_chunk_markdown(text, source_path=rel_path, source_lane=lane))
    return records


def load_source_records_from_source_bundle(source_bundle: dict[str, Any]) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    for idx, row in enumerate(source_bundle.get("source_records") or source_bundle.get("records") or []):
        if isinstance(row, dict):
            record = _record_from_dict(row, str(row.get("source_path") or f"source_bundle#{idx}"), f"source_bundle#{idx}")
            if record and record.source_lane in VALID_SOURCE_LANES:
                records.append(record)
    records.extend(load_source_records_from_unified_bundle(source_bundle))
    return records


def load_source_records_from_unified_bundle(unified_bundle: dict[str, Any]) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    nodes = unified_bundle.get("nodes") or {}
    if not isinstance(nodes, dict):
        return records
    for leaf_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        sources = node.get("sources") or {}
        if not isinstance(sources, dict):
            continue
        for lane, source_rows in sources.items():
            if lane not in VALID_SOURCE_LANES or not isinstance(source_rows, list):
                continue
            for idx, row in enumerate(source_rows):
                if not isinstance(row, dict):
                    continue
                text = _record_text(row)
                if len(_clean_text(text)) < 8:
                    continue
                span = _span_for_record(text, row)
                provenance = _provenance(row)
                provenance["runtime_leaf_id"] = leaf_id
                provenance["runtime_source_index"] = idx
                path = _source_path_for_row(f"canonical_unified_knowledge:nodes.{leaf_id}.sources.{lane}[{idx}]", row)
                records.append(
                    SourceRecord(
                        source_lane=lane,
                        source_path=path,
                        record_id=_record_id(row, f"{leaf_id}:{lane}:{idx}"),
                        text=text,
                        provenance=provenance,
                        span=span,
                        span_hash=str(row.get("span_hash") or row.get("content_hash") or _sha256(span)),
                        retrieval_stage="runtime_source_ref",
                    )
                )
    return records


def _records_deduped(records: Iterable[SourceRecord]) -> list[SourceRecord]:
    out: list[SourceRecord] = []
    seen: set[str] = set()
    for record in records:
        if record.source_lane not in VALID_SOURCE_LANES:
            continue
        span = record.span or _span_for_record(record.text)
        key = f"{record.source_lane}:{record.source_path}:{record.record_id}:{record.span_hash or _sha256(span)}"
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _sample_keywords(sample_manifest: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in sample_manifest.get("selected_leaves") or []:
        if isinstance(row, dict) and row.get("leaf_id"):
            out[str(row["leaf_id"])] = [str(term) for term in row.get("keywords") or [] if term]
    return out


def _teaching_card_terms(artifact: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for card in artifact.get("teaching_cards") or []:
        if not isinstance(card, dict):
            continue
        text = str(card.get("card") or "")
        if "keywords:" in text:
            terms.extend(part.strip() for part in text.split("keywords:", 1)[1].split(",") if part.strip())
    return terms


def _question_context(artifact: dict[str, Any]) -> tuple[list[str], list[str]]:
    record_ids: list[str] = []
    spans: list[str] = []
    for source_ref in artifact.get("source_refs") or []:
        if not isinstance(source_ref, dict) or source_ref.get("source_lane") != "question":
            continue
        record_id = source_ref.get("record_id")
        if record_id:
            record_ids.append(str(record_id))
        span = source_ref.get("span")
        if isinstance(span, str) and span.strip():
            spans.append(span.strip())
    return record_ids, spans


def _terms_for_artifact(artifact: dict[str, Any], sample_terms: dict[str, list[str]]) -> list[str]:
    raw_terms: list[str] = []
    leaf_id = str(artifact.get("leaf_id") or "")
    raw_terms.extend(sample_terms.get(leaf_id) or [])
    raw_terms.extend(_teaching_card_terms(artifact))
    raw_terms.extend(_split_terms(str(artifact.get("name_path") or "")))
    for source_ref in artifact.get("source_refs") or []:
        if isinstance(source_ref, dict) and source_ref.get("source_lane") == "question":
            raw_terms.extend(_split_terms(str(source_ref.get("span") or ""))[:12])
    if leaf_id:
        raw_terms.append(leaf_id.split("-")[0])

    out: list[str] = []
    seen: set[str] = set()
    for term in raw_terms:
        normalized = _normalize_search_term(term)
        if not _is_searchable_term(normalized):
            continue
        if normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out[:24]


def _snippet(text: str, matched_terms: list[str], max_len: int = 360) -> str:
    first_hit = min((text.find(term) for term in matched_terms if term in text), default=-1)
    start = max(0, first_hit - 80) if first_hit >= 0 else 0
    return _clean_text(text[start : start + max_len])


def _score_record(record: SourceRecord, terms: list[str]) -> tuple[float, list[str]]:
    matched = [term for term in terms if term in record.text]
    if not matched:
        return 0.0, []
    long_bonus = sum(min(len(term), 8) for term in matched) / 24
    stage_bonus = {"runtime_source_ref": 0.25, "local_corpus_record": 0.2, "local_corpus_chunk": 0.1}.get(
        record.retrieval_stage, 0.0
    )
    return round(len(matched) + long_bonus + stage_bonus, 4), matched


def _candidate(
    *,
    artifact: dict[str, Any],
    missing_lane: str,
    record: SourceRecord,
    score: float,
    matched_terms: list[str],
) -> dict[str, Any]:
    span = record.span or _span_for_record(record.text)
    return {
        "leaf_id": str(artifact.get("leaf_id")),
        "missing_lane": missing_lane,
        "source_lane": record.source_lane,
        "source_path": record.source_path,
        "record_id": record.record_id,
        "provenance": record.provenance,
        "span": span,
        "snippet": _snippet(record.text, matched_terms),
        "hash": record.span_hash or _sha256(span),
        "matched_terms": matched_terms,
        "score": score,
        "retrieval_stage": record.retrieval_stage,
        "candidate_only": True,
        "install_allowed": False,
    }


def build_source_gap_candidates(
    *,
    skeleton_batch: dict[str, Any],
    sample_manifest: dict[str, Any] | None = None,
    source_records: list[SourceRecord],
    top_k_per_lane: int = 5,
    strong_candidate_threshold: float = 2.0,
) -> dict[str, Any]:
    sample_manifest = sample_manifest or {}
    records = _records_deduped(source_records)
    sample_terms = _sample_keywords(sample_manifest)
    rows: list[dict[str, Any]] = []
    question_context_total = 0

    for artifact in skeleton_batch.get("rich_leaf_artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        missing_lanes = [str(lane) for lane in artifact.get("missing_source_lanes") or [] if lane in VALID_SOURCE_LANES]
        if not missing_lanes:
            continue
        terms = _terms_for_artifact(artifact, sample_terms)
        question_record_ids, question_spans = _question_context(artifact)
        if question_record_ids or question_spans:
            question_context_total += 1
        for missing_lane in missing_lanes:
            scored: list[tuple[float, SourceRecord, list[str]]] = []
            for record in records:
                if record.source_lane != missing_lane:
                    continue
                score, matched = _score_record(record, terms)
                if score > 0:
                    scored.append((score, record, matched))
            scored.sort(
                key=lambda item: (
                    -item[0],
                    item[1].retrieval_stage != "runtime_source_ref",
                    item[1].retrieval_stage != "local_corpus_record",
                    item[1].source_path,
                    item[1].record_id,
                )
            )
            candidates = [
                _candidate(
                    artifact=artifact,
                    missing_lane=missing_lane,
                    record=record,
                    score=score,
                    matched_terms=matched,
                )
                for score, record, matched in scored[:top_k_per_lane]
            ]
            top_score = float(candidates[0]["score"]) if candidates else 0.0
            status = (
                "strong_candidate_sources_found"
                if top_score >= strong_candidate_threshold
                else "weak_candidate_sources_found"
                if candidates
                else "no_candidate_sources_found"
            )
            rows.append(
                {
                    "leaf_id": str(artifact.get("leaf_id")),
                    "artifact_id": artifact.get("artifact_id"),
                    "name_path": artifact.get("name_path"),
                    "missing_lane": missing_lane,
                    "status": status,
                    "terms": terms,
                    "top_score": top_score,
                    "candidate_count": len(candidates),
                    "strong_candidate_threshold": strong_candidate_threshold,
                    "query_context": {
                        "question_source_record_ids": question_record_ids,
                        "question_source_spans": question_spans[:3],
                        "question_source_only_not_support": True,
                    },
                    "candidates": candidates,
                }
            )

    status_counts = {
        "strong_candidate_sources_found": sum(1 for row in rows if row["status"] == "strong_candidate_sources_found"),
        "weak_candidate_sources_found": sum(1 for row in rows if row["status"] == "weak_candidate_sources_found"),
        "no_candidate_sources_found": sum(1 for row in rows if row["status"] == "no_candidate_sources_found"),
    }
    return {
        "schema": "luban_rich_leaf_source_gap_candidates.v1",
        "source_skeleton_schema": skeleton_batch.get("schema"),
        "source_sample_schema": sample_manifest.get("schema"),
        "classification": {
            "review_only": True,
            "candidate_only": True,
            "rag_or_chunk_retrieval_is_not_authority": True,
            "question_source_is_query_context_only": True,
        },
        "summary": {
            "artifact_count": len(skeleton_batch.get("rich_leaf_artifacts") or []),
            "gap_lane_count": len(rows),
            "source_record_count": len(records),
            "candidate_total": sum(int(row["candidate_count"]) for row in rows),
            "question_sources_used_as_query_context": question_context_total,
            **status_counts,
        },
        "source_gap_candidates": rows,
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skeleton-batch", type=Path, default=DEFAULT_SKELETON_BATCH)
    parser.add_argument("--sample-manifest", type=Path, default=DEFAULT_SAMPLE_MANIFEST)
    parser.add_argument("--source-bundle", type=Path)
    parser.add_argument("--unified-bundle", type=Path, default=DEFAULT_UNIFIED_BUNDLE)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-k-per-lane", type=int, default=5)
    parser.add_argument("--strong-candidate-threshold", type=float, default=2.0)
    args = parser.parse_args(argv)

    source_records: list[SourceRecord] = []
    if args.source_bundle and args.source_bundle.exists():
        source_records.extend(load_source_records_from_source_bundle(_read_json(args.source_bundle)))
    if args.unified_bundle and args.unified_bundle.exists():
        source_records.extend(load_source_records_from_unified_bundle(_read_json(args.unified_bundle)))
    if args.source_root and args.source_root.exists():
        source_records.extend(load_source_records_from_root(args.source_root))

    report = build_source_gap_candidates(
        skeleton_batch=_read_json(args.skeleton_batch),
        sample_manifest=_read_json(args.sample_manifest) if args.sample_manifest.exists() else {},
        source_records=source_records,
        top_k_per_lane=args.top_k_per_lane,
        strong_candidate_threshold=args.strong_candidate_threshold,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "source_gap_candidates.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "summary": report["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
