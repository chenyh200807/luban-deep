#!/usr/bin/env python3
"""Build a compact AI-readable brief for all raw data assets."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_ROOT = Path(__file__).resolve().parents[1]
EXTRACTIONS_ROOT = INVENTORY_ROOT / "extractions"
DEFAULT_RAW_PROFILE = EXTRACTIONS_ROOT / "2026-06-18-raw-data-current-profile.json"
DEFAULT_JSON_LEDGER = EXTRACTIONS_ROOT / "json_source_ledger_v0" / "manifest.json"
DEFAULT_PDF_LEDGER = EXTRACTIONS_ROOT / "pdf_source_ledger_v1" / "manifest.json"
DEFAULT_COMPILED_LEDGER = EXTRACTIONS_ROOT / "compiled_asset_ledger_v1" / "manifest.json"
DEFAULT_OKF_SCOPE = EXTRACTIONS_ROOT / "okf_candidate_scope_v0" / "manifest.json"
DEFAULT_OUTPUT_ROOT = EXTRACTIONS_ROOT / "data_asset_brief_v1"
OUTPUT_ROOT_SUFFIX = ("extractions", "data_asset_brief_v1")
SENTINEL_NAME = ".data_asset_brief_generated.json"

RUNTIME_GUARD = {
    "release_stage": "asset_inventory_only",
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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"required input not found: {display_path(path)}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"required input is not a JSON object: {display_path(path)}")
    return data


def load_pdf_ledger(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if data.get("schema") != "luban_pdf_source_ledger_manifest.v1":
        raise ValueError(f"invalid PDF source ledger schema: {display_path(path)}")
    if data.get("authority_status") != "raw_pdf_evidence_ledger":
        raise ValueError(f"invalid PDF source ledger authority: {display_path(path)}")
    runtime_guard = data.get("runtime_guard") or {}
    if runtime_guard.get("runtime_consumable") is not False or runtime_guard.get("official_score_allowed") is not False:
        raise ValueError(f"invalid PDF source ledger runtime guard: {display_path(path)}")
    counts = data.get("counts") or {}
    if not isinstance(counts.get("pdf_sources"), int):
        raise ValueError(f"invalid PDF source ledger counts: {display_path(path)}")
    return data


def load_compiled_asset_ledger(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if data.get("schema") != "luban_compiled_asset_ledger_manifest.v1":
        raise ValueError(f"invalid compiled asset ledger schema: {display_path(path)}")
    if data.get("authority_status") != "compiled_asset_inventory_only":
        raise ValueError(f"invalid compiled asset ledger authority: {display_path(path)}")
    runtime_guard = data.get("runtime_guard") or {}
    if runtime_guard.get("runtime_consumable") is not False or runtime_guard.get("official_score_allowed") is not False:
        raise ValueError(f"invalid compiled asset ledger runtime guard: {display_path(path)}")
    counts = data.get("counts") or {}
    if not isinstance(counts.get("files"), int):
        raise ValueError(f"invalid compiled asset ledger counts: {display_path(path)}")
    return data


def validate_output_root(path: Path) -> None:
    resolved = resolve_soft(path)
    controlled_roots = {
        EXTRACTIONS_ROOT.resolve(),
        Path(tempfile.gettempdir()).resolve(),
    }
    dangerous_roots = {
        Path("/").resolve(),
        Path.home().resolve(),
        REPO_ROOT.resolve(),
        INVENTORY_ROOT.resolve(),
        EXTRACTIONS_ROOT.resolve(),
    }
    if resolved in dangerous_roots or not has_suffix(resolved, OUTPUT_ROOT_SUFFIX):
        raise ValueError(f"unsafe output root: {display_path(path)}")
    if not any(is_relative_to(resolved, root) for root in controlled_roots):
        raise ValueError(f"unsafe output root outside controlled roots: {display_path(path)}")
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
        sentinel.get("generated_by") != "build_data_asset_brief.py"
        or sentinel.get("kind") != "data_asset_brief"
        or sentinel.get("runtime_consumable") is not False
    ):
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}")
    return sentinel


def assert_generated_tree(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    load_sentinel(path)
    allowed = {"manifest.json", "asset_buckets.json", "ai_brief.md", SENTINEL_NAME}
    for child in path.iterdir():
        if child.name not in allowed or child.is_dir():
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_sentinel(path: Path, generated_at: str) -> None:
    sentinel = {
        "kind": "data_asset_brief",
        "generated_by": "build_data_asset_brief.py",
        "generated_at": generated_at,
        "runtime_consumable": False,
    }
    (path / SENTINEL_NAME).write_text(
        json.dumps(sentinel, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def fmt_bytes(value: int | float | None) -> str:
    if value is None:
        return "unknown"
    size = float(value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.2f} TB"


def ext_count(profile: dict[str, Any], extension: str) -> int:
    for row in profile["raw_asset_file_inventory"]["by_extension"]:
        if row["extension"] == extension:
            return int(row["files"])
    return 0


def ext_bytes(profile: dict[str, Any], extension: str) -> int:
    for row in profile["raw_asset_file_inventory"]["by_extension"]:
        if row["extension"] == extension:
            return int(row["bytes"])
    return 0


def practice_total(practice: dict[str, Any], key: str) -> int:
    total = 0
    for row in practice.values():
        total += int(row.get(key) or 0)
    return total


def guardrail(note: str) -> dict[str, Any]:
    return {"note": note, "runtime_guard": RUNTIME_GUARD}


def build_asset_buckets(
    profile: dict[str, Any],
    json_ledger: dict[str, Any],
    compiled_ledger: dict[str, Any],
    okf_scope: dict[str, Any],
) -> list[dict[str, Any]]:
    assets = profile["assets"]
    exam = assets["exam"]
    practice = assets["practice"]
    textbook = assets["textbook"]
    taxonomy_stats = assets["taxonomy"]["stats"]
    standards = assets["standards"]
    lectures = assets["lectures"]
    media = assets["pdf_and_images"]
    okf_counts = okf_scope.get("counts") or {}
    json_counts = json_ledger.get("counts") or {}
    compiled_counts = compiled_ledger.get("counts") or {}
    return [
        {
            "id": "all_raw_files",
            "label": "全原始资产文件",
            "count": profile["raw_asset_file_inventory"]["total_files"],
            "unit": "file",
            "bytes": profile["raw_asset_file_inventory"]["total_bytes"],
            "primary_entry": "docs/原始数据",
            "ai_use": "快速判断资产总体规模、文件类型、容量结构",
            "readiness": "inventory_ready",
            "authority_status": "raw_asset_inventory",
        },
        {
            "id": "cleaned_json_sources",
            "label": "清洗 JSON 源",
            "count": json_counts.get("json_sources", profile["json_inventory"]["json_files"]),
            "unit": "json_file",
            "bucket_counts": json_counts.get("buckets") or {},
            "primary_entry": "docs/原始数据/数据盘点/extractions/json_source_ledger_v0/sources.jsonl",
            "ai_use": "AI 快速定位教材、真题、讲义、标准、taxonomy 的结构化入口",
            "readiness": "machine_readable_ledger_ready",
            "authority_status": "raw_evidence_ledger",
        },
        {
            "id": "exam_cleaned_json",
            "label": "历年真题结构化 JSON",
            "count": exam["files"],
            "unit": "year_file",
            "metrics": {
                "years": exam["years"],
                "chunks": exam["chunks"],
                "exercises": exam["exercises"],
                "choice_questions": exam["choice"]["total"],
                "case_questions": exam["case_study"]["total"],
                "case_analysis_nonempty": exam["case_study"]["analysis_nonempty"],
                "case_score_nonnull": exam["case_study"]["score_nonnull"],
                "taxonomy_missing_chunks": exam["taxonomy_missing"],
            },
            "primary_entry": "docs/原始数据/2026_副本/题库/*/FINAL_CLEANED_EXAM_V*.json",
            "ai_use": "真题覆盖、考点频次、案例题候选 rubric、客观题确定性判分",
            "readiness": "structured_high_with_case_rubric_gap",
            "authority_status": "source_evidence_not_official_score",
        },
        {
            "id": "practice_question_banks",
            "label": "章节练习库",
            "count": practice_total(practice, "exercises"),
            "unit": "exercise",
            "metrics": {
                "files": len(practice),
                "correct_answer_nonempty": practice_total(practice, "correct_answer_nonempty"),
                "analysis_nonempty": practice_total(practice, "analysis_nonempty"),
            },
            "primary_entry": "docs/原始数据/2026_副本/题库/864考证宝典ZL + 章节千题斩SMR",
            "ai_use": "客观题练习、错因解释、章节覆盖监控",
            "readiness": "structured_high_for_objective_questions",
            "authority_status": "practice_source_evidence",
        },
        {
            "id": "textbook_2026",
            "label": "2026 教材结构化内容",
            "count": textbook["v3_fixed_content_blocks"],
            "unit": "content_block",
            "metrics": {
                "fixed_files": textbook["v3_fixed_files"],
                "first_cleaned_files": textbook["first_cleaned_files"],
            },
            "primary_entry": "docs/原始数据/2026_副本/2026教材/第二次加强/FINAL_CLEANED_BOOK2026-*fixed.json",
            "ai_use": "教材讲解、知识点 grounding、候选知识卡生成",
            "readiness": "structured_high",
            "authority_status": "textbook_source_evidence",
        },
        {
            "id": "taxonomy_2026",
            "label": "2026 taxonomy",
            "count": taxonomy_stats.get("total_node_count"),
            "unit": "node",
            "metrics": {
                "leaf_count": taxonomy_stats.get("leaf_count"),
                "book_derived_leaf_count": taxonomy_stats.get("book_derived_leaf_count"),
                "anchored_chunk_count": taxonomy_stats.get("anchored_chunk_count"),
            },
            "primary_entry": "docs/原始数据/2026_副本/taxonomy/FINAL_CLEANED_TAXONOMY2026.json",
            "ai_use": "章节/知识点路由、覆盖率、学习路径锚点",
            "readiness": "structured_high_with_mapping_gaps",
            "authority_status": "taxonomy_source_evidence",
        },
        {
            "id": "standards_json",
            "label": "规范/标准结构化 JSON",
            "count": standards["files"],
            "unit": "standard_file",
            "metrics": {
                "nodes": standards["total_nodes"],
                "content_blocks": standards["total_content_blocks"],
                "unmatched_nodes": sum(row.get("unmatched_nodes") or 0 for row in standards["rows"]),
            },
            "primary_entry": "docs/原始数据/2026_副本/标准文件/*.json",
            "ai_use": "规范引用、案例解释 grounding、图解/构造内容约束",
            "readiness": "structured_high_for_grounding",
            "authority_status": "standard_source_evidence_not_exam_rubric",
        },
        {
            "id": "lecture_json",
            "label": "讲义 JSON",
            "count": lectures["page_json"],
            "unit": "page_json",
            "metrics": {
                "packages": lectures["packages"],
                "aggregate_json": lectures["aggregate_json"],
            },
            "primary_entry": "docs/原始数据/2026_副本/讲义/*/page_*.json",
            "ai_use": "老师表达、讲义讲解、专题化解释素材",
            "readiness": "structured_medium",
            "authority_status": "lecture_source_evidence",
        },
        {
            "id": "pdf_library",
            "label": "PDF 原件库",
            "count": media["pdf_files"],
            "unit": "pdf_file",
            "bytes": ext_bytes(profile, ".pdf"),
            "metrics": {
                "pdf_by_top_subdir": media["pdf_by_top_subdir"],
            },
            "primary_entry": "docs/原始数据/PDF",
            "ai_use": "补源、视觉核查、OCR 回溯、原件审计",
            "readiness": "raw_evidence_needs_ocr_or_existing_json",
            "authority_status": "raw_source_not_direct_compiled_context",
        },
        {
            "id": "rendered_images",
            "label": "渲染/图片资产",
            "count": media["image_files"],
            "unit": "image_file",
            "metrics": {
                "image_by_extension": media["image_by_extension"],
                "render_check_png": media["render_check_png"],
            },
            "primary_entry": "docs/原始数据/2026_副本/**/docx_render_check*",
            "ai_use": "OCR/视觉核查、题卷排版证据、图像回溯",
            "readiness": "raw_visual_evidence",
            "authority_status": "visual_evidence_not_text_truth",
        },
        {
            "id": "compiled_assets_ledger",
            "label": "编译资产 / artifacts 总账",
            "count": compiled_counts.get("files"),
            "unit": "compiled_asset_file",
            "bytes": compiled_counts.get("total_bytes"),
            "metrics": {
                "asset_groups": compiled_counts.get("asset_groups"),
                "manifest_like_files": compiled_counts.get("manifest_like_files"),
                "manifest_refs_copied": compiled_counts.get("manifest_refs_copied"),
            },
            "primary_entry": "docs/原始数据/数据盘点/extractions/compiled_asset_ledger_v1/manifest.json",
            "ai_use": "定位 artifacts/workbench/runtime_supply 编译产物、区分 shadow candidate 与 runtime supply",
            "readiness": "inventory_ready_not_runtime_truth",
            "authority_status": "compiled_asset_inventory_only",
        },
        {
            "id": "case_rubric_candidate_scope",
            "label": "案例题 OKF-like 候选评分工件",
            "count": okf_counts.get("scoring_points"),
            "unit": "candidate_scoring_point",
            "metrics": {
                "cases": okf_counts.get("cases"),
                "rubrics": okf_counts.get("rubrics"),
                "scoring_points": okf_counts.get("scoring_points"),
            },
            "primary_entry": "docs/原始数据/数据盘点/extractions/okf_candidate_scope_v0",
            "ai_use": "案例题候选采分点检索、source-layer 对齐、后续专家复核入口",
            "readiness": okf_scope.get("status", "candidate"),
            "authority_status": "candidate_only_not_official_score",
        },
    ]


def build_pdf_compilation_status(
    profile: dict[str, Any],
    pdf_ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assets = profile["assets"]
    media = assets["pdf_and_images"]
    exam = assets["exam"]
    practice = assets["practice"]
    textbook = assets["textbook"]
    standards = assets["standards"]
    lectures = assets["lectures"]
    pdf_by_subdir = media["pdf_by_top_subdir"]
    status = {
        "status": "partially_structured_not_fully_pdf_compiled",
        "raw_pdf_files": media["pdf_files"],
        "raw_pdf_bytes": ext_bytes(profile, ".pdf"),
        "raw_pdf_by_subdir": pdf_by_subdir,
        "what_is_done": [
            {
                "asset": "教材 PDF 派生结构化内容",
                "structured_artifact": "2026 教材 fixed JSON",
                "count": textbook["v3_fixed_content_blocks"],
                "unit": "content_block",
                "status": "structured_json_available",
            },
            {
                "asset": "真题 PDF 派生结构化题库",
                "structured_artifact": "2015-2025 FINAL_CLEANED_EXAM_V*.json",
                "count": exam["exercises"],
                "unit": "exercise",
                "status": "structured_json_available",
            },
            {
                "asset": "章节题 PDF 派生结构化题库",
                "structured_artifact": "ZL500 + QIANTIZAN JSON",
                "count": practice_total(practice, "exercises"),
                "unit": "exercise",
                "status": "structured_json_available",
            },
            {
                "asset": "讲义 PDF 派生 page JSON",
                "structured_artifact": "讲义 page_*.json",
                "count": lectures["page_json"],
                "unit": "page_json",
                "status": "structured_json_available",
            },
            {
                "asset": "标准/规范 PDF 派生结构化 JSON",
                "structured_artifact": "标准文件/*.json",
                "count": standards["total_nodes"],
                "unit": "standard_node",
                "status": "structured_json_available_for_8_standard_files",
            },
        ],
        "what_is_not_done": [
            "95 个 PDF 没有逐文件生成统一 full_text/chunk manifest。",
            "PDF 与 JSON 派生物之间还没有逐文件一对一 provenance map。",
            "未对全部 PDF 做 OCR 质量评分、页码级 hash、图片/表格抽取覆盖率统计。",
            "任何 PDF 派生内容都还不能直接升级为 runtime supply 或 official scoring authority。",
        ],
        "recommended_next_artifact": "pdf_source_ledger_v1",
        "runtime_guard": RUNTIME_GUARD,
    }
    if pdf_ledger:
        status["pdf_source_ledger"] = {
            "path": "docs/原始数据/数据盘点/extractions/pdf_source_ledger_v1/manifest.json",
            "counts": pdf_ledger.get("counts") or {},
            "authority_status": pdf_ledger.get("authority_status"),
        }
    return status


def markdown_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| 资产桶 | 数量 | 单位 | 可用状态 | AI 首入口 |",
        "|---|---:|---|---|---|",
    ]
    for row in rows:
        count = row.get("count")
        if count is None:
            count_text = "unknown"
        elif isinstance(count, int):
            count_text = f"{count:,}"
        else:
            count_text = str(count)
        lines.append(
            f"| {row['label']} | {count_text} | {row['unit']} | {row['readiness']} | `{row['primary_entry']}` |"
        )
    return "\n".join(lines)


def render_ai_brief(manifest: dict[str, Any], asset_buckets: list[dict[str, Any]]) -> str:
    totals = manifest["totals"]
    top_takeaways = manifest["top_takeaways"]
    pdf_status = manifest["pdf_compilation_status"]
    lines = [
        "# AI Data Asset Brief v1",
        "",
        f"- Generated at: `{manifest['generated_at']}`",
        "- Authority: asset inventory only; not runtime supply, not official scoring, not learner truth.",
        f"- Raw asset files: **{totals['raw_asset_files']:,}** ({fmt_bytes(totals['raw_asset_bytes'])})",
        f"- Cleaned JSON sources: **{totals['cleaned_json_sources']:,}**",
        f"- PDFs: **{totals['pdf_files']:,}**",
        f"- Images/render evidence: **{totals['image_files']:,}**",
        f"- Compiled/artifact files indexed: **{totals['compiled_asset_files']:,}** ({fmt_bytes(totals['compiled_asset_bytes'])})",
        "",
        "## One-Minute Takeaways",
        "",
    ]
    lines.extend(f"- {item}" for item in top_takeaways)
    lines.extend([
        "",
        "## Asset Buckets",
        "",
        markdown_table(asset_buckets),
        "",
        "## PDF Compilation Status",
        "",
        f"- Status: `{pdf_status['status']}`",
        f"- Raw PDFs indexed: **{pdf_status['raw_pdf_files']:,}** ({fmt_bytes(pdf_status['raw_pdf_bytes'])})",
        "- Structured JSON artifacts exist for textbook, exams, practice questions, lectures, and 8 standard files, but PDF links are still candidate evidence.",
        "- Not yet done: no per-PDF full-text/chunk manifest, no one-to-one PDF→JSON provenance map, no full OCR quality ledger.",
    ])
    if "pdf_source_ledger" in pdf_status:
        counts = pdf_status["pdf_source_ledger"]["counts"]
        lines.append(
            f"- Per-PDF ledger: **{counts.get('candidate_structured_derivative_refs_available', 0):,}** candidate structured derivative refs, "
            f"**{counts.get('needs_compilation_or_mapping', 0):,}** still need compilation or mapping."
        )
    lines.extend([
        "",
        "## What AI Should Load First",
        "",
    ])
    for item in manifest["ai_entrypoints"]:
        lines.append(f"- `{item['path']}` — {item['why']}")
    lines.extend([
        "",
        "## Guardrails",
        "",
    ])
    for item in manifest["guardrails"]:
        lines.append(f"- {item['note']}")
    lines.append("")
    return "\n".join(lines)


def build_data_asset_brief(
    raw_profile_path: Path = DEFAULT_RAW_PROFILE,
    json_ledger_path: Path = DEFAULT_JSON_LEDGER,
    pdf_ledger_path: Path = DEFAULT_PDF_LEDGER,
    compiled_ledger_path: Path = DEFAULT_COMPILED_LEDGER,
    okf_scope_path: Path = DEFAULT_OKF_SCOPE,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_output_root(output_root)
    assert_generated_tree(output_root)

    profile = load_json(raw_profile_path)
    json_ledger = load_json(json_ledger_path)
    pdf_ledger = load_pdf_ledger(pdf_ledger_path)
    compiled_ledger = load_compiled_asset_ledger(compiled_ledger_path)
    okf_scope = load_json(okf_scope_path)
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    asset_buckets = build_asset_buckets(profile, json_ledger, compiled_ledger, okf_scope)
    pdf_compilation_status = build_pdf_compilation_status(profile, pdf_ledger)
    raw_inventory = profile["raw_asset_file_inventory"]
    pdf_files = ext_count(profile, ".pdf")
    image_files = int(profile["assets"]["pdf_and_images"]["image_files"])
    json_sources = int((json_ledger.get("counts") or {}).get("json_sources") or profile["json_inventory"]["json_files"])
    exam = profile["assets"]["exam"]
    practice_total_exercises = practice_total(profile["assets"]["practice"], "exercises")
    okf_counts = okf_scope.get("counts") or {}
    compiled_counts = compiled_ledger.get("counts") or {}

    manifest = {
        "schema": "luban_data_asset_brief_manifest.v1",
        "generated_at": generated_at,
        "authority_status": "asset_inventory_only",
        "runtime_guard": RUNTIME_GUARD,
        "source_paths": {
            "raw_profile": display_path(raw_profile_path),
            "json_source_ledger": display_path(json_ledger_path),
            "pdf_source_ledger": display_path(pdf_ledger_path) if pdf_ledger_path.exists() else None,
            "compiled_asset_ledger": display_path(compiled_ledger_path),
            "okf_candidate_scope": display_path(okf_scope_path),
        },
        "artifact_refs": {
            "asset_buckets": "asset_buckets.json",
            "ai_brief": "ai_brief.md",
        },
        "totals": {
            "raw_asset_files": raw_inventory["total_files"],
            "raw_asset_bytes": raw_inventory["total_bytes"],
            "cleaned_json_sources": json_sources,
            "pdf_files": pdf_files,
            "image_files": image_files,
            "exam_exercises": exam["exercises"],
            "exam_choice_questions": exam["choice"]["total"],
            "exam_case_questions": exam["case_study"]["total"],
            "practice_exercises": practice_total_exercises,
            "textbook_content_blocks": profile["assets"]["textbook"]["v3_fixed_content_blocks"],
            "taxonomy_nodes": profile["assets"]["taxonomy"]["stats"].get("total_node_count"),
            "standard_nodes": profile["assets"]["standards"]["total_nodes"],
            "lecture_page_json": profile["assets"]["lectures"]["page_json"],
            "candidate_cases": okf_counts.get("cases"),
            "candidate_rubrics": okf_counts.get("rubrics"),
            "candidate_scoring_points": okf_counts.get("scoring_points"),
            "compiled_asset_files": compiled_counts.get("files"),
            "compiled_asset_bytes": compiled_counts.get("total_bytes"),
            "compiled_asset_groups": compiled_counts.get("asset_groups"),
            "compiled_manifest_refs_copied": compiled_counts.get("manifest_refs_copied"),
        },
        "pdf_compilation_status": pdf_compilation_status,
        "ai_entrypoints": [
            {
                "path": "docs/原始数据/数据盘点/extractions/data_asset_brief_v1/ai_brief.md",
                "why": "最快读懂全资产规模、边界和下一步路由",
            },
            {
                "path": "docs/原始数据/数据盘点/extractions/data_asset_brief_v1/manifest.json",
                "why": "机器可读 totals、guardrails、entrypoints",
            },
            {
                "path": "docs/原始数据/数据盘点/extractions/json_source_ledger_v0/sources.jsonl",
                "why": "逐个清洗 JSON source 的路径、bucket、sha256 和 shape",
            },
            {
                "path": "docs/原始数据/数据盘点/extractions/pdf_source_ledger_v1/pdf_sources.jsonl",
                "why": "逐个 PDF 的 hash、分类、结构化派生状态和下一步动作",
            },
            {
                "path": "docs/原始数据/数据盘点/extractions/compiled_asset_ledger_v1/manifest.json",
                "why": "编译资产、artifacts、runtime_supply 的总入口和边界",
            },
            {
                "path": "docs/原始数据/数据盘点/extractions/compiled_asset_ledger_v1/files.jsonl",
                "why": "逐个编译资产文件的路径、hash、分组和 authority 状态",
            },
            {
                "path": "docs/原始数据/数据盘点/extractions/2026-06-18-raw-data-current-profile.json",
                "why": "全目录原始资产深度统计",
            },
            {
                "path": "docs/原始数据/数据盘点/extractions/okf_candidate_scope_v0/manifest.json",
                "why": "案例题候选 rubric / scoring point source-layer 范围",
            },
        ],
        "top_takeaways": [
            "优先目标是全数据资产总账，而不是先接 production runtime consumer。",
            f"结构化 JSON 已有 {json_sources:,} 个，足够让 AI 快速知道教材、真题、讲义、标准、taxonomy 的入口。",
            f"真题层有 {exam['exercises']:,} 道练习，其中案例题 {exam['case_study']['total']:,}、选择题 {exam['choice']['total']:,}。",
            f"章节练习有 {practice_total_exercises:,} 道，适合客观题闭环和错因解释。",
            f"PDF 有 {pdf_files:,} 个；逐 PDF ledger 已生成，仍需对未映射 PDF 做 chunking 或 provenance backfill。",
            f"编译资产 ledger 已收录 {compiled_counts.get('files', 0):,} 个 artifacts/runtime 文件，复制 {compiled_counts.get('manifest_refs_copied', 0):,} 个小型 manifest-like 快照；payload 原地保留。",
            "OKF-like 候选评分工件已覆盖 25 cases / 117 rubrics / 431 scoring points，但仍是 candidate-only。",
        ],
        "guardrails": [
            guardrail("本产物只回答资产规模、入口、可用性和边界，不签发 production truth。"),
            guardrail("PDF 原件库不等于已 OCR/已结构化/已可检索知识库。"),
            guardrail("artifacts/workbench 编译产物不等于 runtime truth；runtime_supply 也必须逐 pointer 检查 published/status。"),
            guardrail("案例题 correct_answer / 候选 scoring point 不等于 official scoring authority。"),
            guardrail("任何 runtime default、LearnerState、GBrain、official score 写入都必须走后续独立 gate。"),
        ],
    }

    reset_dir(output_root)
    write_sentinel(output_root, generated_at)
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_root / "asset_buckets.json").write_text(
        json.dumps({"schema": "luban_data_asset_buckets.v1", "asset_buckets": asset_buckets}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_root / "ai_brief.md").write_text(
        render_ai_brief(manifest, asset_buckets),
        encoding="utf-8",
    )
    return {"manifest": manifest, "asset_buckets": asset_buckets}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-profile", type=Path, default=DEFAULT_RAW_PROFILE)
    parser.add_argument("--json-ledger", type=Path, default=DEFAULT_JSON_LEDGER)
    parser.add_argument("--pdf-ledger", type=Path, default=DEFAULT_PDF_LEDGER)
    parser.add_argument("--compiled-ledger", type=Path, default=DEFAULT_COMPILED_LEDGER)
    parser.add_argument("--okf-scope", type=Path, default=DEFAULT_OKF_SCOPE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at")
    args = parser.parse_args()

    result = build_data_asset_brief(
        raw_profile_path=args.raw_profile,
        json_ledger_path=args.json_ledger,
        pdf_ledger_path=args.pdf_ledger,
        compiled_ledger_path=args.compiled_ledger,
        okf_scope_path=args.okf_scope,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    manifest = result["manifest"]
    print(
        json.dumps(
            {
                "manifest": display_path(args.output_root / "manifest.json"),
                "ai_brief": display_path(args.output_root / "ai_brief.md"),
                "asset_buckets": len(result["asset_buckets"]),
                "totals": manifest["totals"],
                "runtime_consumable": manifest["runtime_guard"]["runtime_consumable"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
