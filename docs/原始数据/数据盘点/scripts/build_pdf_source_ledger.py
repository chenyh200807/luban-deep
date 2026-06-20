#!/usr/bin/env python3
"""Build a per-PDF source ledger with derivative compilation status."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF_ROOT = REPO_ROOT / "docs" / "原始数据" / "PDF"
DEFAULT_OUTPUT_ROOT = INVENTORY_ROOT / "extractions" / "pdf_source_ledger_v1"
SENTINEL_NAME = ".pdf_source_ledger_generated.json"
OUTPUT_ROOT_SUFFIX = ("extractions", "pdf_source_ledger_v1")

EXAM_JSON_ROOT = REPO_ROOT / "docs" / "原始数据" / "2026_副本" / "题库"
TEXTBOOK_JSON_ROOT = REPO_ROOT / "docs" / "原始数据" / "2026_副本" / "2026教材" / "第二次加强"
STANDARD_JSON_ROOT = REPO_ROOT / "docs" / "原始数据" / "2026_副本" / "标准文件"
LECTURE_JSON_ROOT = REPO_ROOT / "docs" / "原始数据" / "2026_副本" / "讲义"
PRACTICE_JSON_ROOT = REPO_ROOT / "docs" / "原始数据" / "2026_副本" / "题库"

RUNTIME_GUARD = {
    "release_stage": "raw_pdf_source_ledger",
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pdf_id_for(pdf_root: Path, path: Path) -> str:
    rel_to_root = path.relative_to(pdf_root).as_posix()
    return f"pdf_src_{hashlib.sha256(rel_to_root.encode('utf-8')).hexdigest()[:16]}"


def validate_output_root(path: Path, pdf_root: Path) -> None:
    resolved = resolve_soft(path)
    resolved_pdf_root = resolve_soft(pdf_root)
    controlled_roots = {
        (INVENTORY_ROOT / "extractions").resolve(),
        Path(tempfile.gettempdir()).resolve(),
    }
    dangerous_roots = {
        Path("/").resolve(),
        Path.home().resolve(),
        REPO_ROOT.resolve(),
        INVENTORY_ROOT.resolve(),
        (INVENTORY_ROOT / "extractions").resolve(),
        resolved_pdf_root,
    }
    if resolved in dangerous_roots or not has_suffix(resolved, OUTPUT_ROOT_SUFFIX):
        raise ValueError(f"unsafe output root: {display_path(path)}")
    if not any(is_relative_to(resolved, root) for root in controlled_roots):
        raise ValueError(f"unsafe output root outside controlled roots: {display_path(path)}")
    if is_relative_to(resolved_pdf_root, resolved) or is_relative_to(resolved, resolved_pdf_root):
        raise ValueError("output root must not overlap PDF root")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"unsafe output root is not a directory: {display_path(path)}")


def load_sentinel(path: Path) -> dict[str, Any]:
    sentinel_path = path / SENTINEL_NAME
    if not sentinel_path.exists():
        raise ValueError(f"missing generated sentinel: {display_path(path)}")
    try:
        sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}") from exc
    if (
        sentinel.get("generated_by") != "build_pdf_source_ledger.py"
        or sentinel.get("kind") != "pdf_source_ledger"
        or sentinel.get("runtime_consumable") is not False
    ):
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}")
    return sentinel


def assert_generated_tree(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    load_sentinel(path)
    allowed = {"manifest.json", "pdf_sources.jsonl", "summary.md", SENTINEL_NAME}
    for child in path.iterdir():
        if child.name not in allowed or child.is_dir():
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_sentinel(path: Path, generated_at: str) -> None:
    sentinel = {
        "kind": "pdf_source_ledger",
        "generated_by": "build_pdf_source_ledger.py",
        "generated_at": generated_at,
        "runtime_consumable": False,
    }
    (path / SENTINEL_NAME).write_text(
        json.dumps(sentinel, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def iter_pdfs(pdf_root: Path) -> list[Path]:
    return sorted(path for path in pdf_root.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf")


def normalized_code(text: str) -> str | None:
    compact = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    match = re.search(r"(?:GB|GBT|JGJ|JGJT)\d{3,}(?:\d{4})?", compact)
    return match.group(0) if match else None


def extract_years(text: str) -> list[int]:
    years = {int(year) for year in re.findall(r"20\d{2}", text)}
    for start, end in re.findall(r"(20\d{2})\s*[-—－]\s*(20\d{2})", text):
        start_i, end_i = int(start), int(end)
        if start_i <= end_i and 2010 <= start_i <= 2030 and 2010 <= end_i <= 2030:
            years.update(range(start_i, end_i + 1))
    for start, end in re.findall(r"(?<!\d)(1[5-9]|2[0-5])\s*[-—－]\s*(1[5-9]|2[0-5])(?!\d)", text):
        start_i, end_i = 2000 + int(start), 2000 + int(end)
        if start_i <= end_i:
            years.update(range(start_i, end_i + 1))
    return sorted(year for year in years if 2015 <= year <= 2026)


def classify_pdf(pdf_root: Path, path: Path) -> str:
    rel_text = path.relative_to(pdf_root).as_posix()
    name = path.name
    top = path.relative_to(pdf_root).parts[0]
    if top == "行业标准文件":
        return "standard_pdf"
    if top == "真题" or "历年真题" in rel_text or "真题" in name:
        return "exam_pdf"
    if "公式" in name:
        return "formula_pdf"
    if top == "讲义" or "讲义" in name or "精讲班" in name:
        return "lecture_pdf"
    if any(token in rel_text for token in ["必刷", "千题", "500题", "金点题", "掌中宝"]):
        return "practice_pdf"
    if top == "教材":
        return "textbook_pdf"
    supplement_tokens = [
        "导图",
        "考点",
        "口袋书",
        "背诵",
        "百题",
        "专题",
        "一本通",
        "教材变动",
        "教材对比",
        "图文教材",
        "必背",
        "问",
        "手册",
        "白皮书",
        "备考",
        "指南",
        "四色笔记",
        "默写",
    ]
    if any(token in name for token in supplement_tokens):
        return "supplement_pdf"
    if "电子版教材" in rel_text or "教材" in name:
        return "textbook_pdf"
    return "supplement_pdf"


def exam_json_by_year() -> dict[int, Path]:
    result: dict[int, Path] = {}
    for path in EXAM_JSON_ROOT.glob("*年一级建造师《建筑实务》考试真题及答案解析/FINAL_CLEANED_EXAM_V*.json"):
        match = re.search(r"V(\d{4})", path.name)
        if match:
            result[int(match.group(1))] = path
    return result


def standard_json_by_code() -> dict[str, Path]:
    result = {}
    for path in STANDARD_JSON_ROOT.glob("*.json"):
        code = normalized_code(path.name)
        if code:
            result[code] = path
    return result


def textbook_json_refs() -> list[Path]:
    return sorted(TEXTBOOK_JSON_ROOT.glob("FINAL_CLEANED_BOOK2026-*fixed.json"))


def textbook_json_by_page_range() -> dict[str, Path]:
    result = {}
    for path in textbook_json_refs():
        match = re.search(r"BOOK2026-(\d+-\d+)", path.name)
        if match:
            result[match.group(1)] = path
    return result


def textbook_json_refs_for_pdf(path: Path) -> list[dict[str, Any]]:
    if "2026" not in path.name:
        return []
    by_range = textbook_json_by_page_range()
    refs: list[dict[str, Any]] = []
    ranges = re.findall(r"(?<!\d)(\d{1,3})\s*[-—－]\s*(\d{1,3})(?!\d)", path.name)
    for start, end in ranges:
        key = f"{int(start)}-{int(end)}"
        ref = by_range.get(key)
        if ref:
            refs.append({"kind": "textbook_cleaned_json", "path": display_path(ref), "match": key})
    if refs:
        return refs
    if path.stem == "2026一建《建筑》电子版教材":
        return [
            {"kind": "textbook_cleaned_json", "path": display_path(ref), "match": "full_2026_textbook_candidate"}
            for ref in textbook_json_refs()
        ]
    return []


def practice_json_refs(rel_text: str) -> list[Path]:
    refs = []
    if any(token in rel_text for token in ["864", "ZL500", "必刷500题"]):
        refs.append(PRACTICE_JSON_ROOT / "864考证宝典ZL" / "FINAL_CLEANED_ZL500.json")
    if any(token in rel_text for token in ["章节千题", "QIANTIZAN", "千题"]):
        refs.append(PRACTICE_JSON_ROOT / "章节千题斩SMR" / "FINAL_CLEANED_QIANTIZAN.json")
    return [path for path in refs if path.exists()]


def lecture_json_refs(path: Path) -> list[Path]:
    name = path.name.replace("_副本", "")
    dates = re.findall(r"20\d{2}\.\d{1,2}\.\d{1,2}", name)
    refs = []
    for package in sorted(p for p in LECTURE_JSON_ROOT.iterdir() if p.is_dir()):
        package_name = package.name
        if any(date in package_name for date in dates):
            refs.append(package)
    return refs


def derivative_refs(pdf_root: Path, path: Path, category: str) -> list[dict[str, Any]]:
    rel_text = path.relative_to(pdf_root).as_posix()
    refs: list[dict[str, Any]] = []
    if category == "standard_pdf":
        code = normalized_code(path.name)
        matched = standard_json_by_code().get(code or "")
        if matched:
            refs.append({"kind": "standard_cleaned_json", "path": display_path(matched), "match": code})
    elif category == "exam_pdf":
        year_map = exam_json_by_year()
        for year in extract_years(path.name):
            if year in year_map:
                refs.append({"kind": "exam_cleaned_json", "path": display_path(year_map[year]), "match": str(year)})
    elif category == "textbook_pdf":
        refs.extend(textbook_json_refs_for_pdf(path))
    elif category == "lecture_pdf":
        for ref in lecture_json_refs(path):
            refs.append({"kind": "lecture_page_json_dir", "path": display_path(ref), "match": "date"})
    elif category == "practice_pdf":
        for ref in practice_json_refs(rel_text):
            refs.append({"kind": "practice_cleaned_json", "path": display_path(ref), "match": ref.name})
    return refs


def compilation_status(category: str, refs: list[dict[str, Any]]) -> str:
    if refs:
        return "candidate_structured_derivative_refs_available"
    if category == "standard_pdf":
        return "raw_indexed_needs_standard_json_backfill"
    if category == "exam_pdf":
        return "raw_indexed_needs_exam_mapping_or_backfill"
    if category == "textbook_pdf":
        return "raw_indexed_needs_textbook_chunking_or_mapping"
    if category == "lecture_pdf":
        return "raw_indexed_needs_lecture_chunking_or_mapping"
    if category == "practice_pdf":
        return "raw_indexed_needs_practice_mapping_or_backfill"
    if category == "formula_pdf":
        return "raw_indexed_needs_formula_mapping_or_backfill"
    return "raw_indexed_review_later"


def priority_for(category: str, status: str, path: Path) -> str:
    name = path.name
    if status == "candidate_structured_derivative_refs_available":
        return "P2_verify_provenance"
    if "Removed_" in name:
        return "P3_archive_or_dedupe"
    if category in {"standard_pdf", "exam_pdf", "textbook_pdf", "lecture_pdf"}:
        return "P1_compile_or_map"
    if category in {"practice_pdf", "formula_pdf"}:
        return "P2_compile_if_needed"
    return "P3_review_if_product_needs"


def recommended_next_action(status: str) -> str:
    if status == "candidate_structured_derivative_refs_available":
        return "add_or_verify_pdf_to_json_provenance_map"
    if "standard_json" in status:
        return "extract_or_map_standard_pdf_to_cleaned_json"
    if "exam" in status:
        return "map_pdf_to_exam_json_or_create_exam_chunks"
    if "textbook" in status:
        return "map_pdf_pages_to_textbook_blocks_or_chunk_missing_pdf"
    if "lecture" in status:
        return "map_pdf_to_lecture_page_json_or_chunk_missing_pdf"
    if "practice" in status:
        return "map_pdf_to_practice_json_or_extract_questions"
    if "formula" in status:
        return "map_pdf_to_formula_registry_or_extract_formulas"
    return "keep_indexed_until_product_need"


def build_records(pdf_root: Path) -> list[dict[str, Any]]:
    records = []
    for path in iter_pdfs(pdf_root):
        category = classify_pdf(pdf_root, path)
        refs = derivative_refs(pdf_root, path, category)
        status = compilation_status(category, refs)
        stat = path.stat()
        record = {
            "schema": "luban_pdf_source_record.v1",
            "pdf_id": pdf_id_for(pdf_root, path),
            "source_path": display_path(path),
            "source_relpath_under_pdf_root": path.relative_to(pdf_root).as_posix(),
            "category": category,
            "authority_status": "raw_pdf_evidence",
            "compilation_status": status,
            "candidate_structured_derivative_refs": refs,
            "priority": priority_for(category, status, path),
            "recommended_next_action": recommended_next_action(status),
            "file": {
                "bytes": stat.st_size,
                "sha256": sha256_file(path),
            },
            "runtime_guard": RUNTIME_GUARD,
        }
        records.append(record)
    return records


def render_summary(manifest: dict[str, Any], records: list[dict[str, Any]]) -> str:
    lines = [
        "# PDF Source Ledger v1",
        "",
        f"- Generated at: `{manifest['generated_at']}`",
        "- Authority: raw PDF evidence ledger only; not runtime supply, not official score authority.",
        f"- PDF files: **{manifest['counts']['pdf_sources']:,}**",
        f"- Candidate structured derivative refs: **{manifest['counts']['candidate_structured_derivative_refs_available']:,}**",
        f"- Still needing compilation or mapping: **{manifest['counts']['needs_compilation_or_mapping']:,}**",
        "",
        "## Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, count in manifest["counts"]["by_compilation_status"].items():
        lines.append(f"| `{status}` | {count:,} |")
    lines.extend([
        "",
        "## Category Counts",
        "",
        "| Category | Count |",
        "|---|---:|",
    ])
    for category, count in manifest["counts"]["by_category"].items():
        lines.append(f"| `{category}` | {count:,} |")
    lines.extend([
        "",
        "## P1 Missing Derivative Sample",
        "",
    ])
    p1 = [record for record in records if record["priority"] == "P1_compile_or_map"][:20]
    if not p1:
        lines.append("- None.")
    else:
        for record in p1:
            lines.append(f"- `{record['source_path']}` — {record['compilation_status']}")
    lines.extend([
        "",
        "## Guardrails",
        "",
        "- This ledger preserves PDF source facts and derivative status only.",
        "- Candidate structured derivative refs are unverified hints, not signed PDF -> JSON provenance.",
        "- Existing JSON derivatives still need a PDF -> JSON provenance map before release signing.",
        "- Missing derivative does not mean the PDF is useless; it means it has not been normalized into the current structured source layer.",
        "- No record in this ledger may be consumed as runtime context or official scoring authority without a later signed release artifact.",
        "",
    ])
    return "\n".join(lines)


def build_pdf_source_ledger(
    pdf_root: Path = DEFAULT_PDF_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if not pdf_root.exists() or not pdf_root.is_dir():
        raise ValueError(f"PDF root does not exist: {display_path(pdf_root)}")
    validate_output_root(output_root, pdf_root)
    assert_generated_tree(output_root)

    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    records = build_records(pdf_root)
    if not records:
        raise ValueError(f"no PDF sources found under: {display_path(pdf_root)}")

    by_category = Counter(record["category"] for record in records)
    by_status = Counter(record["compilation_status"] for record in records)
    by_priority = Counter(record["priority"] for record in records)
    candidate_refs = by_status.get("candidate_structured_derivative_refs_available", 0)
    manifest = {
        "schema": "luban_pdf_source_ledger_manifest.v1",
        "generated_at": generated_at,
        "pdf_root": display_path(pdf_root),
        "authority_status": "raw_pdf_evidence_ledger",
        "runtime_guard": RUNTIME_GUARD,
        "artifact_refs": {
            "pdf_sources": "pdf_sources.jsonl",
            "summary": "summary.md",
        },
        "counts": {
            "pdf_sources": len(records),
            "total_bytes": sum(record["file"]["bytes"] for record in records),
            "candidate_structured_derivative_refs_available": candidate_refs,
            "needs_compilation_or_mapping": len(records) - candidate_refs,
            "by_category": dict(by_category.most_common()),
            "by_compilation_status": dict(by_status.most_common()),
            "by_priority": dict(by_priority.most_common()),
        },
        "guardrails": [
            "raw PDF evidence only",
            "candidate structured derivative refs != signed release artifact",
            "no runtime supply install",
            "no official scoring claim",
            "PDF -> JSON provenance must be verified before release signing",
        ],
    }

    reset_dir(output_root)
    write_sentinel(output_root, generated_at)
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_root / "pdf_sources.jsonl").open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    (output_root / "summary.md").write_text(render_summary(manifest, records), encoding="utf-8")
    return {"manifest": manifest, "records": records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-root", type=Path, default=DEFAULT_PDF_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at")
    args = parser.parse_args()

    result = build_pdf_source_ledger(
        pdf_root=args.pdf_root,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    manifest = result["manifest"]
    print(
        json.dumps(
            {
                "manifest": display_path(args.output_root / "manifest.json"),
                "pdf_sources": display_path(args.output_root / "pdf_sources.jsonl"),
                "summary": display_path(args.output_root / "summary.md"),
                "counts": manifest["counts"],
                "runtime_consumable": manifest["runtime_guard"]["runtime_consumable"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
