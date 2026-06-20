#!/usr/bin/env python3
"""Build a tiny OKF-like rubric pilot from the canonical case rubric extraction."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_PATH = INVENTORY_ROOT / "extractions" / "case_rubric_canonical.json"
DEFAULT_SOURCE_ROOT = INVENTORY_ROOT / "okf_pilot" / "rubric_v0"
DEFAULT_COMPILED_ROOT = INVENTORY_ROOT / "extractions" / "okf_rubric_pilot_v0"
DEFAULT_RUBRIC_JSONL_PATH = INVENTORY_ROOT / "extractions" / "2021_jianzhu_case_rubric.jsonl"
DEFAULT_CONTEXT_PATH = (
    REPO_ROOT
    / "docs"
    / "原始数据"
    / "2026_副本"
    / "题库"
    / "2021年一级建造师《建筑实务》考试真题及答案解析"
    / "FINAL_CLEANED_EXAM_V2021.json"
)
DEFAULT_YEAR = "2021"
DEFAULT_CASE_NO = "1"
SENTINEL_NAME = ".okf_pilot_generated.json"
QUESTION_CONTEXT_CONFIG = {
    ("2021", "1"): {
        "chunk_id": "EXAM_1A431000_P0016_02",
        "rubric_jsonl_line_range": "2-16",
    }
}
SOURCE_ROOT_SUFFIX = ("okf_pilot", "rubric_v0")
COMPILED_ROOT_SUFFIX = ("extractions", "okf_rubric_pilot_v0")
SOURCE_ROOT_TOP_LEVEL = {"cases", "rubrics", "scoring_points", "index.md", SENTINEL_NAME}
COMPILED_ROOT_TOP_LEVEL = {
    "manifest.json",
    "question_context_pack.json",
    "scoring_point_index.json",
    SENTINEL_NAME,
}
SOURCE_ROOT_KIND = "generated_review_projection"
COMPILED_ROOT_KIND = "compiled_inspection_artifacts"
RUNTIME_GUARD = {
    "release_stage": "source_pilot",
    "runtime_consumable": False,
    "installed_runtime_supply": False,
    "canonical_write_allowed": False,
    "learner_truth_write_allowed": False,
    "gbrain_write_allowed": False,
    "production_registry_write_allowed": False,
    "official_score_allowed": False,
}


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def display_path(path: Path) -> str:
    try:
        return rel(path)
    except ValueError:
        return str(path)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_soft(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def has_suffix(path: Path, suffix: tuple[str, ...]) -> bool:
    return tuple(path.parts[-len(suffix) :]) == suffix


def load_sentinel(path: Path, *, expected_kind: str) -> dict[str, Any]:
    sentinel_path = path / SENTINEL_NAME
    if not sentinel_path.exists():
        raise ValueError(f"missing generated sentinel: {display_path(path)}")
    try:
        sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}") from exc
    if (
        sentinel.get("generated_by") != "build_okf_rubric_pilot.py"
        or sentinel.get("kind") != expected_kind
        or sentinel.get("runtime_consumable") is not False
    ):
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}")
    return sentinel


def assert_source_generated_tree(path: Path) -> None:
    for child in path.iterdir():
        if child.name not in SOURCE_ROOT_TOP_LEVEL:
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")
        if child.name in {"cases", "rubrics", "scoring_points"}:
            if not child.is_dir():
                raise ValueError(f"unsafe generated output tree: {display_path(child)}")
            for nested in child.iterdir():
                if nested.is_dir():
                    raise ValueError(f"unsafe generated output tree: {display_path(nested)}")
                if child.name == "cases" and not nested.name.startswith("case_"):
                    raise ValueError(f"unsafe generated output tree: {display_path(nested)}")
                if child.name == "rubrics" and not nested.name.startswith("rubric_"):
                    raise ValueError(f"unsafe generated output tree: {display_path(nested)}")
                if child.name == "scoring_points" and not nested.name.startswith("sp_"):
                    raise ValueError(f"unsafe generated output tree: {display_path(nested)}")
                if nested.suffix != ".md":
                    raise ValueError(f"unsafe generated output tree: {display_path(nested)}")


def assert_compiled_generated_tree(path: Path) -> None:
    for child in path.iterdir():
        if child.name not in COMPILED_ROOT_TOP_LEVEL:
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")
        if child.is_dir():
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")


def assert_generated_tree(path: Path, *, expected_kind: str) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    load_sentinel(path, expected_kind=expected_kind)
    if expected_kind == SOURCE_ROOT_KIND:
        assert_source_generated_tree(path)
    elif expected_kind == COMPILED_ROOT_KIND:
        assert_compiled_generated_tree(path)
    else:
        raise ValueError(f"invalid generated sentinel kind: {expected_kind}")


def validate_output_root_shape(path: Path, *, suffix: tuple[str, ...]) -> None:
    resolved = resolve_soft(path)
    dangerous_roots = {
        Path("/").resolve(),
        Path.home().resolve(),
        REPO_ROOT.resolve(),
        INVENTORY_ROOT.resolve(),
        (INVENTORY_ROOT / "okf_pilot").resolve(),
        (INVENTORY_ROOT / "extractions").resolve(),
    }
    if resolved in dangerous_roots or not has_suffix(resolved, suffix):
        raise ValueError(f"unsafe output root: {display_path(path)}")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"unsafe output root is not a directory: {display_path(path)}")


def validate_paths(
    source_path: Path,
    source_root: Path,
    compiled_root: Path,
    *,
    context_path: Path,
    rubric_jsonl_path: Path,
) -> None:
    validate_output_root_shape(source_root, suffix=SOURCE_ROOT_SUFFIX)
    validate_output_root_shape(compiled_root, suffix=COMPILED_ROOT_SUFFIX)

    resolved_source = resolve_soft(source_path)
    resolved_source_root = resolve_soft(source_root)
    resolved_compiled_root = resolve_soft(compiled_root)

    if (
        resolved_source_root == resolved_compiled_root
        or is_relative_to(resolved_source_root, resolved_compiled_root)
        or is_relative_to(resolved_compiled_root, resolved_source_root)
    ):
        raise ValueError("output roots must not overlap")
    if is_relative_to(resolved_source, resolved_source_root) or is_relative_to(
        resolved_source, resolved_compiled_root
    ):
        raise ValueError("source_path must not be inside generated output")
    for input_path in [context_path, rubric_jsonl_path]:
        resolved_input = resolve_soft(input_path)
        if is_relative_to(resolved_input, resolved_source_root) or is_relative_to(
            resolved_input, resolved_compiled_root
        ):
            raise ValueError("input sources must not be inside generated output")
    assert_generated_tree(resolved_source_root, expected_kind=SOURCE_ROOT_KIND)
    assert_generated_tree(resolved_compiled_root, expected_kind=COMPILED_ROOT_KIND)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_sentinel(path: Path, *, kind: str, generated_at: str) -> None:
    sentinel = {
        "kind": kind,
        "generated_by": "build_okf_rubric_pilot.py",
        "generated_at": generated_at,
        "runtime_consumable": False,
    }
    (path / SENTINEL_NAME).write_text(json.dumps(sentinel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def yaml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(str(value), ensure_ascii=False)


def frontmatter(fields: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {yaml_value(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def write_markdown(path: Path, fields: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter(fields) + body.rstrip() + "\n", encoding="utf-8")


def load_case(source_path: Path, year: str, case_no: str) -> tuple[dict[str, Any], dict[str, Any]]:
    data = load_json(source_path)
    meta = data.get("_meta") or {}
    if meta.get("NOT_official") is not True:
        raise ValueError("case_rubric_canonical.json must preserve NOT_official=true")
    if meta.get("authority") != "training_org_analysis_yousen":
        raise ValueError("unexpected rubric authority; refusing to generate pilot")
    try:
        case = data["rubric"][year][case_no]
    except KeyError as exc:
        raise ValueError(f"missing rubric slice year={year} case={case_no}") from exc
    if not isinstance(case, dict) or not case:
        raise ValueError(f"empty rubric slice year={year} case={case_no}")
    return meta, case


def load_question_context(context_path: Path, year: str, case_no: str) -> dict[str, Any]:
    config = QUESTION_CONTEXT_CONFIG.get((year, case_no))
    if not config:
        raise ValueError("okf rubric pilot v0 only has question context configured for year=2021 case=1")
    data = load_json(context_path)
    chunks = data.get("chunks") or []
    for index, chunk in enumerate(chunks):
        if chunk.get("chunk_id") == config["chunk_id"]:
            source_meta = chunk.get("source_meta") or {}
            visual_description = ""
            sub_questions: list[dict[str, Any]] = []
            for seq, exercise in enumerate(chunk.get("exercises") or [], start=1):
                question_data = exercise.get("question_data") or {}
                visual_data = exercise.get("visual_data") or {}
                if visual_data.get("description"):
                    visual_description = str(visual_data["description"])
                sub_questions.append({
                    "sub_q_no": str(seq),
                    "stem": str(question_data.get("stem") or ""),
                    "score": float(question_data["score"]) if question_data.get("score") is not None else None,
                    "predicted_node": exercise.get("predicted_node"),
                })
            content_markdown = str(chunk.get("content_markdown") or "")
            return {
                "question_source": {
                    "source_chunk_id": chunk["chunk_id"],
                    "page": source_meta.get("page_num"),
                    "json_path": f"$.chunks[{index}]",
                    "source_path": display_path(context_path),
                    "taxonomy": chunk.get("taxonomy") or {},
                },
                "question_context": {
                    "question_stem": content_markdown,
                    "sub_questions": sub_questions,
                    "visual_context": {
                        "present": "图1" in content_markdown,
                        "prompt_ref": "图1：倒置式屋面构造示意图（部分）",
                        "answer_interpretation_available": bool(visual_description),
                        "student_facing_leakage_risk": bool(visual_description),
                        "answer_interpretation": visual_description,
                    },
                },
                "question_hashes": {
                    "question_context_file_sha256": sha256_file(context_path),
                    "question_chunk_sha256": sha256_text(content_markdown),
                },
            }
    raise ValueError(f"missing configured question context chunk_id={config['chunk_id']}")


def load_rubric_provenance(rubric_jsonl_path: Path, year: str, case_no: str) -> tuple[dict[str, Any], dict[tuple[str, int], dict[str, Any]]]:
    config = QUESTION_CONTEXT_CONFIG.get((year, case_no))
    if not config:
        raise ValueError("okf rubric pilot v0 only has rubric provenance configured for year=2021 case=1")
    lines = rubric_jsonl_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError(f"empty rubric jsonl source: {display_path(rubric_jsonl_path)}")
    meta_wrapper = json.loads(lines[0])
    meta = meta_wrapper.get("_meta") or {}
    point_sources: dict[tuple[str, int], dict[str, Any]] = {}
    case_pages: set[int] = set()
    for line_no, line in enumerate(lines[1:], start=2):
        record = json.loads(line)
        if str(record.get("case_no")) != case_no:
            continue
        sub_q = str(record["sub_q_no"])
        seq = int(record["point_seq"])
        page = int(record["page"])
        case_pages.add(page)
        point_sources[(sub_q, seq)] = {
            "rubric_page": page,
            "source_jsonl_line": line_no,
            "source_jsonl_path": display_path(rubric_jsonl_path),
            "source_hash_sha256": sha256_text(line),
            "ocr_suspect": record.get("_ocr_suspect"),
        }
    if not point_sources:
        raise ValueError(f"missing rubric provenance year={year} case={case_no}")
    pages = sorted(case_pages)
    rubric_source = {
        "page": pages[0] if len(pages) == 1 else None,
        "pages": pages,
        "jsonl_line_range": config["rubric_jsonl_line_range"],
        "canonical_json_path": f'$.rubric["{year}"]["{case_no}"]',
        "source_ref": rubric_jsonl_path.name,
        "source_path": display_path(rubric_jsonl_path),
        "pdf_source_path": meta.get("source_path"),
        "source_authority": meta.get("source_authority"),
        "not_official": bool(meta.get("NOT_official")),
        "method": meta.get("method"),
        "caveat": meta.get("caveat"),
        "rubric_jsonl_sha256": sha256_file(rubric_jsonl_path),
    }
    return rubric_source, point_sources


def split_acceptable_items(text: str, *, point_type: str, point_score: float) -> list[str]:
    if point_type != "列举" or point_score <= 1:
        return []
    candidate = text.split(":", 1)[1] if ":" in text else text
    candidate = candidate.replace("；", ";").replace("、", ";").replace("，", ";").replace(",", ";")
    items = [item.strip() for item in candidate.split(";") if item.strip()]
    return items if len(items) > 1 else []


def make_scoring_point_id(year: str, case_no: str, sub_q: str, seq: int) -> str:
    return f"sp_{year}_{case_no}_q{int(sub_q):02d}_{int(seq):02d}"


def make_rubric_id(year: str, case_no: str, sub_q: str) -> str:
    return f"rubric_{year}_{case_no}_q{int(sub_q):02d}"


def make_case_id(year: str, case_no: str) -> str:
    return f"case_{year}_{case_no}"


def build_case_doc(
    source_root: Path,
    *,
    source_path: Path,
    case_id: str,
    year: str,
    case_no: str,
    meta: dict[str, Any],
    case_context: dict[str, Any],
    rubric_source: dict[str, Any],
    source_hash_sha256: str,
    rubric_refs: list[dict[str, str]],
    generated_at: str,
) -> dict[str, Any]:
    path = source_root / "cases" / f"{case_id}.md"
    body_lines = [
        "# Case scope",
        "",
        f"- Year: {year}",
        f"- Case number: {case_no}",
        f"- Authority: `{meta['authority']}`",
        "- Not official: `true`",
        "- Official score allowed: `false`",
        "- Projection role: `generated_review_projection`",
        "",
        "# Question context",
        "",
        f"- Question source chunk: `{case_context['question_source']['source_chunk_id']}`",
        f"- Question source page: `{case_context['question_source']['page']}`",
        f"- Rubric source page: `{rubric_source['page']}`",
        "",
        "# Rubrics",
        "",
    ]
    for ref in rubric_refs:
        body_lines.append(f"- [{ref['title']}](../rubrics/{ref['doc_name']})")
    body_lines.extend([
        "",
        "# Citations",
        "",
        f"[1] {meta.get('source', 'case_rubric_canonical extraction')}",
    ])
    fields = {
        "type": "CaseQuestion",
        "title": f"{year} 建筑实务案例 {case_no}",
        "description": "OKF-like pilot case shell for one canonical rubric slice.",
        "timestamp": generated_at,
        "canonical_id": case_id,
        "authority": meta["authority"],
        "not_official": True,
        "official_score_allowed": False,
        "projection_role": "generated_review_projection",
        "source_ref": source_path.name,
        "source_path": display_path(source_path),
        "tags": ["luban", "rubric", "okf-pilot"],
    }
    write_markdown(path, fields, "\n".join(body_lines))
    return {
        "id": case_id,
        "path": display_path(path),
        "rubrics": [ref["id"] for ref in rubric_refs],
        "authority": meta["authority"],
        "not_official": True,
        "official_score_allowed": False,
        "source_ref": source_path.name,
        "source_path": display_path(source_path),
        "question_source": case_context["question_source"],
        "rubric_source": rubric_source,
        "question_stem": case_context["question_context"]["question_stem"],
        "sub_questions": case_context["question_context"]["sub_questions"],
        "visual_context": case_context["question_context"]["visual_context"],
        "hashes": {
            "canonical_source_sha256": source_hash_sha256,
            **case_context["question_hashes"],
        },
    }


def build_rubric_and_points(
    source_root: Path,
    *,
    source_path: Path,
    year: str,
    case_no: str,
    sub_q: str,
    sub_q_data: dict[str, Any],
    meta: dict[str, Any],
    point_sources: dict[tuple[str, int], dict[str, Any]],
    generated_at: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rubric_id = make_rubric_id(year, case_no, sub_q)
    rubric_doc_name = f"{rubric_id}.md"
    rubric_path = source_root / "rubrics" / rubric_doc_name
    points: list[dict[str, Any]] = []
    point_lines: list[str] = []
    for point in sub_q_data.get("points") or []:
        seq = int(point["seq"])
        point_id = make_scoring_point_id(year, case_no, sub_q, seq)
        point_doc_name = f"{point_id}.md"
        point_path = source_root / "scoring_points" / point_doc_name
        point_score = float(point["score"])
        point_type = str(point.get("type") or "unknown")
        text = str(point["text"])
        point_source = point_sources.get((sub_q, seq), {})
        acceptable_items = split_acceptable_items(text, point_type=point_type, point_score=point_score)
        point_fields = {
            "type": "ScoringPoint",
            "title": f"{year} 案例{case_no} 小问{sub_q} 采分点{seq}",
            "description": text,
            "timestamp": generated_at,
            "canonical_id": point_id,
            "authority": meta["authority"],
            "not_official": True,
            "official_score_allowed": False,
            "projection_role": "generated_review_projection",
            "source_ref": source_path.name,
            "source_path": display_path(source_path),
            "case_id": make_case_id(year, case_no),
            "rubric_id": rubric_id,
            "point_score": point_score,
            "point_type": point_type,
            "judge_rule": sub_q_data.get("judge_rule"),
            "rubric_page": point_source.get("rubric_page"),
            "tags": ["luban", "scoring-point", "okf-pilot"],
        }
        metadata_lines = [
            "# Scoring point",
            "",
            text,
            "",
            "# Scoring metadata",
            "",
            f"- Point score: `{point_score}`",
            f"- Point type: `{point_type}`",
            f"- Judge rule: `{sub_q_data.get('judge_rule')}`",
            f"- Rubric source page: `{point_source.get('rubric_page')}`",
        ]
        if acceptable_items:
            metadata_lines.extend([
                "- Acceptable items:",
                *[f"  - `{item}`" for item in acceptable_items],
                "- Partial credit rule: `unknown_from_source`",
                f"- Max per group: `{point_score}`",
            ])
        metadata_lines.extend([
            "- Official score allowed: `false`",
            "- Projection role: `generated_review_projection`",
            "",
            "# Parent rubric",
            "",
            f"[{rubric_id}](../rubrics/{rubric_doc_name})",
            "",
            "# Citations",
            "",
            f"[1] {meta.get('source', 'case_rubric_canonical extraction')}",
        ])
        point_body = "\n".join(metadata_lines)
        write_markdown(point_path, point_fields, point_body)
        point_record = {
            "point_id": point_id,
            "case_id": make_case_id(year, case_no),
            "rubric_id": rubric_id,
            "sub_question": sub_q,
            "seq": seq,
            "text": text,
            "point_score": point_score,
            "point_type": point_type,
            "authority": meta["authority"],
            "not_official": True,
            "official_score_allowed": False,
            "source_ref": source_path.name,
            "source_path": display_path(source_path),
            "doc_path": display_path(point_path),
            "judge_rule": sub_q_data.get("judge_rule"),
            "sub_q_total_score": float(sub_q_data["sub_q_total_score"]),
            "rubric_page": point_source.get("rubric_page"),
            "source_jsonl_line": point_source.get("source_jsonl_line"),
            "source_jsonl_path": point_source.get("source_jsonl_path"),
            "source_json_path": f'$.rubric["{year}"]["{case_no}"]["{sub_q}"].points[{seq - 1}]',
            "source_hash_sha256": point_source.get("source_hash_sha256") or sha256_text(text),
        }
        if point_source.get("ocr_suspect"):
            point_record["ocr_suspect"] = point_source["ocr_suspect"]
        if acceptable_items:
            point_record["acceptable_items"] = acceptable_items
            point_record["partial_credit_rule"] = "unknown_from_source"
            point_record["max_per_group"] = point_score
        points.append(point_record)
        point_lines.append(f"- [{point_id}](../scoring_points/{point_doc_name}) — {text} ({point_score} 分)")

    rubric_fields = {
        "type": "Rubric",
        "title": f"{year} 案例{case_no} 小问{sub_q} rubric",
        "description": f"Candidate rubric for {year} case {case_no} sub-question {sub_q}.",
        "timestamp": generated_at,
        "canonical_id": rubric_id,
        "authority": meta["authority"],
        "not_official": True,
        "official_score_allowed": False,
        "projection_role": "generated_review_projection",
        "source_ref": source_path.name,
        "source_path": display_path(source_path),
        "case_id": make_case_id(year, case_no),
        "sub_q_total_score": float(sub_q_data["sub_q_total_score"]),
        "judge_rule": sub_q_data.get("judge_rule"),
        "scoring_point_refs": [point["point_id"] for point in points],
        "tags": ["luban", "rubric", "okf-pilot"],
    }
    rubric_body = "\n".join([
        "# Rubric scope",
        "",
        f"- Sub-question total score: `{float(sub_q_data['sub_q_total_score'])}`",
        f"- Judge rule: `{sub_q_data.get('judge_rule')}`",
        "- Official score allowed: `false`",
        "- Projection role: `generated_review_projection`",
        "",
        "# Scoring points",
        "",
        *point_lines,
        "",
        "# Parent case",
        "",
        f"[{make_case_id(year, case_no)}](../cases/{make_case_id(year, case_no)}.md)",
        "",
        "# Citations",
        "",
        f"[1] {meta.get('source', 'case_rubric_canonical extraction')}",
    ])
    write_markdown(rubric_path, rubric_fields, rubric_body)
    rubric_record = {
        "rubric_id": rubric_id,
        "case_id": make_case_id(year, case_no),
        "sub_question": sub_q,
        "sub_q_total_score": float(sub_q_data["sub_q_total_score"]),
        "judge_rule": sub_q_data.get("judge_rule"),
        "authority": meta["authority"],
        "not_official": True,
        "official_score_allowed": False,
        "source_ref": source_path.name,
        "source_path": display_path(source_path),
        "doc_path": display_path(rubric_path),
        "scoring_point_refs": [point["point_id"] for point in points],
    }
    return rubric_record, points


def validate_records(meta: dict[str, Any], case_doc: dict[str, Any], rubrics: list[dict[str, Any]], points: list[dict[str, Any]]) -> None:
    if meta.get("authority") != "training_org_analysis_yousen":
        raise ValueError("pilot only accepts training_org_analysis_yousen authority")
    for record in [case_doc, *rubrics, *points]:
        if record.get("official_score_allowed") is not False:
            raise ValueError(f"{record} incorrectly allows official scoring")
        if record.get("authority") != meta["authority"]:
            raise ValueError(f"{record} lost authority")
        if record.get("not_official") is not True:
            raise ValueError(f"{record} lost not_official guard")
        if not record.get("source_ref"):
            raise ValueError(f"{record} missing source_ref")
    for point in points:
        if point.get("point_score") is None:
            raise ValueError(f"{point['point_id']} missing point_score")
        if not point.get("text"):
            raise ValueError(f"{point['point_id']} missing text")


def write_index(source_root: Path, *, generated_at: str, case_doc: dict[str, Any], rubrics: list[dict[str, Any]], points: list[dict[str, Any]]) -> None:
    index_path = source_root / "index.md"
    fields = {
        "type": "BundleIndex",
        "title": "Luban OKF-like Rubric Pilot v0",
        "description": "One-case OKF-like generated review projection for rubric traceability experiments.",
        "timestamp": generated_at,
        "canonical_id": "luban_okf_rubric_pilot_v0",
        "authority": "training_org_analysis_yousen",
        "not_official": True,
        "official_score_allowed": False,
        "tags": ["luban", "rubric", "okf-pilot"],
    }
    body = "\n".join([
        "# Scope",
        "",
        "This bundle is a generated review projection from the canonical extraction. It is not official scoring authority and is not wired to runtime.",
        "",
        "# Case",
        "",
        f"- [{case_doc['id']}](cases/{Path(case_doc['path']).name})",
        "",
        "# Counts",
        "",
        f"- Rubrics: {len(rubrics)}",
        f"- Scoring points: {len(points)}",
        "",
        "# Guardrails",
        "",
        "- Markdown files in this bundle are generated review projections, not canonical source truth.",
        "- `official_score_allowed` is always `false`.",
        "- Runtime must consume only separately signed/versioned supply.",
        "- This pilot must not write LearnerState, GBrain, or production registry.",
    ])
    write_markdown(index_path, fields, body)


def write_compiled(
    compiled_root: Path,
    *,
    source_path: Path,
    generated_at: str,
    meta: dict[str, Any],
    case_doc: dict[str, Any],
    rubrics: list[dict[str, Any]],
    points: list[dict[str, Any]],
    year: str,
    case_no: str,
) -> dict[str, Any]:
    compiled_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "luban_okf_like_rubric_pilot_manifest.v0",
        "generated_at": generated_at,
        "source_path": display_path(source_path),
        "source_sha256": sha256_file(source_path),
        "year": year,
        "case_no": case_no,
        "authority": meta["authority"],
        "not_official": bool(meta.get("NOT_official")),
        "official_score_allowed": False,
        "runtime_guard": RUNTIME_GUARD,
        "artifact_refs": {
            "question_context_pack": "question_context_pack.json",
            "scoring_point_index": "scoring_point_index.json",
        },
        "counts": {
            "cases": 1,
            "rubrics": len(rubrics),
            "scoring_points": len(points),
        },
        "guardrails": [
            "source-layer pilot only",
            "no runtime default",
            "no official scoring claim",
            "no learner truth write",
        ],
    }
    question_context_pack = {
        "schema": "luban_question_context_pack.okf_pilot.v0",
        "generated_at": generated_at,
        "runtime_guard": RUNTIME_GUARD,
        "case": case_doc,
        "rubrics": rubrics,
        "scoring_points": points,
        "authority_guardrail": {
            "source_authority": meta["authority"],
            "not_official": bool(meta.get("NOT_official")),
            "official_score_allowed": False,
            "judge_rule": meta.get("judge_rule"),
        },
    }
    scoring_point_index = {
        "schema": "luban_scoring_point_index.okf_pilot.v0",
        "generated_at": generated_at,
        "authority": meta["authority"],
        "not_official": bool(meta.get("NOT_official")),
        "official_score_allowed": False,
        "runtime_guard": RUNTIME_GUARD,
        "points_by_id": {point["point_id"]: point for point in points},
    }
    outputs = {
        "manifest": manifest,
        "question_context_pack": question_context_pack,
        "scoring_point_index": scoring_point_index,
    }
    for name, data in outputs.items():
        (compiled_root / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return manifest


def build_pilot(
    source_path: Path = DEFAULT_SOURCE_PATH,
    source_root: Path = DEFAULT_SOURCE_ROOT,
    compiled_root: Path = DEFAULT_COMPILED_ROOT,
    context_path: Path = DEFAULT_CONTEXT_PATH,
    rubric_jsonl_path: Path = DEFAULT_RUBRIC_JSONL_PATH,
    year: str = DEFAULT_YEAR,
    case_no: str = DEFAULT_CASE_NO,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_paths(
        source_path,
        source_root,
        compiled_root,
        context_path=context_path,
        rubric_jsonl_path=rubric_jsonl_path,
    )
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    meta, case = load_case(source_path, year, case_no)
    case_context = load_question_context(context_path, year, case_no)
    rubric_source, point_sources = load_rubric_provenance(rubric_jsonl_path, year, case_no)
    source_hash_sha256 = sha256_file(source_path)
    reset_dir(source_root)
    reset_dir(compiled_root)
    write_sentinel(source_root, kind=SOURCE_ROOT_KIND, generated_at=generated_at)
    write_sentinel(compiled_root, kind=COMPILED_ROOT_KIND, generated_at=generated_at)

    rubrics: list[dict[str, Any]] = []
    points: list[dict[str, Any]] = []
    rubric_refs: list[dict[str, str]] = []
    for sub_q, sub_q_data in sorted(case.items(), key=lambda item: int(item[0])):
        rubric, sub_points = build_rubric_and_points(
            source_root,
            source_path=source_path,
            year=year,
            case_no=case_no,
            sub_q=sub_q,
            sub_q_data=sub_q_data,
            meta=meta,
            point_sources=point_sources,
            generated_at=generated_at,
        )
        rubrics.append(rubric)
        points.extend(sub_points)
        rubric_refs.append({
            "id": rubric["rubric_id"],
            "title": f"{year} case {case_no} q{sub_q}",
            "doc_name": Path(rubric["doc_path"]).name,
        })

    case_doc = build_case_doc(
        source_root,
        source_path=source_path,
        case_id=make_case_id(year, case_no),
        year=year,
        case_no=case_no,
        meta=meta,
        case_context=case_context,
        rubric_source=rubric_source,
        source_hash_sha256=source_hash_sha256,
        rubric_refs=rubric_refs,
        generated_at=generated_at,
    )
    validate_records(meta, case_doc, rubrics, points)
    write_index(source_root, generated_at=generated_at, case_doc=case_doc, rubrics=rubrics, points=points)
    manifest = write_compiled(
        compiled_root,
        source_path=source_path,
        generated_at=generated_at,
        meta=meta,
        case_doc=case_doc,
        rubrics=rubrics,
        points=points,
        year=year,
        case_no=case_no,
    )
    return {
        "source_root": display_path(source_root),
        "compiled_root": display_path(compiled_root),
        "manifest": manifest,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_PATH)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--compiled-root", type=Path, default=DEFAULT_COMPILED_ROOT)
    parser.add_argument("--context-source", type=Path, default=DEFAULT_CONTEXT_PATH)
    parser.add_argument("--rubric-jsonl-source", type=Path, default=DEFAULT_RUBRIC_JSONL_PATH)
    parser.add_argument("--year", default=DEFAULT_YEAR)
    parser.add_argument("--case", dest="case_no", default=DEFAULT_CASE_NO)
    parser.add_argument(
        "--generated-at",
        default=None,
        help="ISO timestamp to write into generated docs/artifacts; defaults to current UTC time.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_pilot(
        source_path=args.source,
        source_root=args.source_root,
        compiled_root=args.compiled_root,
        context_path=args.context_source,
        rubric_jsonl_path=args.rubric_jsonl_source,
        year=str(args.year),
        case_no=str(args.case_no),
        generated_at=args.generated_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
