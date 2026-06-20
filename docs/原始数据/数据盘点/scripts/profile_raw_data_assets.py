#!/usr/bin/env python3
"""Profile docs/原始数据 assets for a reproducible data inventory note."""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "数据盘点" / "extractions"
PROFILE_PATH = OUT_DIR / "2026-06-18-raw-data-current-profile.json"
CHART_FILE_TYPES = OUT_DIR / "2026-06-18-raw-data-file-types.png"
CHART_ASSET_BUCKETS = OUT_DIR / "2026-06-18-raw-data-asset-buckets.png"

EXCLUDED_DIRS = {".git", "__pycache__", "node_modules"}
EXCLUDED_TOP_DIRS_FOR_RAW_ASSETS = {"数据盘点"}
EXCLUDED_FILES = {".DS_Store"}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def iter_files(*, include_inventory_docs: bool) -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        parts = set(path.relative_to(ROOT).parts)
        if parts & EXCLUDED_DIRS:
            continue
        if path.name in EXCLUDED_FILES:
            continue
        if not include_inventory_docs and path.relative_to(ROOT).parts[0] in EXCLUDED_TOP_DIRS_FOR_RAW_ASSETS:
            continue
        files.append(path)
    return sorted(files)


def extension(path: Path) -> str:
    suffix = path.suffix.lower().strip()
    return suffix if suffix else "[no_ext]"


def top_dir(path: Path) -> str:
    return path.relative_to(ROOT).parts[0]


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def exercise_items(data: dict) -> list[dict]:
    rows: list[dict] = []
    for chunk in data.get("chunks") or []:
        for exercise in chunk.get("exercises") or []:
            if isinstance(exercise, dict):
                rows.append(exercise)
    return rows


def text_present(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_case_placeholder(text: object) -> bool:
    if not isinstance(text, str):
        return True
    stripped = text.strip()
    if not stripped:
        return True
    placeholders = [
        "本题为案例题",
        "无选项",
        "无需分析",
    ]
    return any(token in stripped for token in placeholders) and len(stripped) < 80


def summarize_exam_files() -> dict:
    exam_files = sorted((ROOT / "2026_副本" / "题库").glob("*年一级建造师《建筑实务》考试真题及答案解析/FINAL_CLEANED_EXAM_V*.json"))
    summary = {
        "files": len(exam_files),
        "years": [],
        "chunks": 0,
        "exercises": 0,
        "exercise_types": Counter(),
        "case_study": {
            "total": 0,
            "correct_answer_non_placeholder": 0,
            "analysis_nonempty": 0,
            "score_nonnull": 0,
        },
        "choice": {
            "total": 0,
            "correct_answer_nonempty": 0,
            "analysis_nonempty": 0,
        },
        "taxonomy_missing": 0,
        "by_year": [],
    }
    for path in exam_files:
        data = load_json(path)
        year_match = re.search(r"V(\d{4})", path.name)
        year = int(year_match.group(1)) if year_match else None
        exercises = exercise_items(data)
        type_counter = Counter(ex.get("type") or "unknown" for ex in exercises)
        year_row = {
            "year": year,
            "path": rel(path),
            "chunks": len(data.get("chunks") or []),
            "exercises": len(exercises),
            "exercise_types": dict(type_counter),
            "stats": data.get("stats") or {},
        }
        summary["years"].append(year)
        summary["chunks"] += year_row["chunks"]
        summary["exercises"] += len(exercises)
        summary["exercise_types"].update(type_counter)
        summary["by_year"].append(year_row)
        for chunk in data.get("chunks") or []:
            taxonomy = chunk.get("taxonomy") or {}
            if not taxonomy.get("node_code"):
                summary["taxonomy_missing"] += 1
        for ex in exercises:
            qd = ex.get("question_data") or {}
            ex_type = ex.get("type") or "unknown"
            if ex_type == "case_study":
                summary["case_study"]["total"] += 1
                if not is_case_placeholder(qd.get("correct_answer")):
                    summary["case_study"]["correct_answer_non_placeholder"] += 1
                if text_present(qd.get("analysis")):
                    summary["case_study"]["analysis_nonempty"] += 1
                if qd.get("score") is not None:
                    summary["case_study"]["score_nonnull"] += 1
            elif ex_type in {"single_choice", "multiple_choice"}:
                summary["choice"]["total"] += 1
                if text_present(qd.get("correct_answer")):
                    summary["choice"]["correct_answer_nonempty"] += 1
                if text_present(qd.get("analysis")):
                    summary["choice"]["analysis_nonempty"] += 1
    summary["years"] = sorted(y for y in summary["years"] if y)
    summary["exercise_types"] = dict(summary["exercise_types"])
    return summary


def summarize_practice_files() -> dict:
    practice_paths = {
        "ZL500": ROOT / "2026_副本" / "题库" / "864考证宝典ZL" / "FINAL_CLEANED_ZL500.json",
        "QIANTIZAN": ROOT / "2026_副本" / "题库" / "章节千题斩SMR" / "FINAL_CLEANED_QIANTIZAN.json",
    }
    result = {}
    for name, path in practice_paths.items():
        data = load_json(path)
        exercises = exercise_items(data)
        qd_rows = [ex.get("question_data") or {} for ex in exercises]
        result[name] = {
            "path": rel(path),
            "chunks": len(data.get("chunks") or []),
            "exercises": len(exercises),
            "exercise_types": dict(Counter(ex.get("type") or "unknown" for ex in exercises)),
            "correct_answer_nonempty": sum(1 for qd in qd_rows if text_present(qd.get("correct_answer"))),
            "analysis_nonempty": sum(1 for qd in qd_rows if text_present(qd.get("analysis"))),
            "stats": data.get("stats") or {},
        }
    return result


def summarize_textbook() -> dict:
    base = ROOT / "2026_副本" / "2026教材"
    rows = []
    fixed_paths = {
        *sorted((base / "第二次加强").glob("*v3_fixed.json")),
        *sorted((base / "第二次加强").glob("FINAL_CLEANED_BOOK2026-*fixed.json")),
    }
    for path in sorted(fixed_paths):
        data = load_json(path)
        rows.append({
            "path": rel(path),
            "content_blocks": len(data.get("content_blocks") or []),
            "meta": data.get("meta") or {},
        })
    first_cleaned = []
    for path in sorted((base / "第一次清洗").glob("FINAL_CLEANED_BOOK2026-*.json")):
        data = load_json(path)
        first_cleaned.append({
            "path": rel(path),
            "top_type": type(data).__name__,
            "items": len(data) if isinstance(data, list) else len(data.get("content_blocks") or data.get("chunks") or []),
        })
    return {
        "v3_fixed_files": len(rows),
        "v3_fixed_content_blocks": sum(row["content_blocks"] for row in rows),
        "v3_fixed": rows,
        "first_cleaned_files": len(first_cleaned),
        "first_cleaned": first_cleaned,
    }


def summarize_taxonomy() -> dict:
    path = ROOT / "2026_副本" / "taxonomy" / "FINAL_CLEANED_TAXONOMY2026.json"
    data = load_json(path)
    return {
        "path": rel(path),
        "stats": data.get("stats") or {},
        "top_keys": list(data.keys()),
    }


def summarize_standards() -> dict:
    rows = []
    for path in sorted((ROOT / "2026_副本" / "标准文件").glob("*.json")):
        data = load_json(path)
        rows.append({
            "path": rel(path),
            "title": path.stem,
            "keys": list(data.keys()) if isinstance(data, dict) else [],
            "nodes": len(data.get("nodes") or []) if isinstance(data, dict) else None,
            "content_blocks": len(data.get("content_blocks") or []) if isinstance(data, dict) else None,
            "unmatched_nodes": len(data.get("unmatched_nodes") or []) if isinstance(data, dict) else None,
        })
    return {
        "files": len(rows),
        "total_nodes": sum(row["nodes"] or 0 for row in rows),
        "total_content_blocks": sum(row["content_blocks"] or 0 for row in rows),
        "rows": rows,
    }


def summarize_lectures() -> dict:
    lecture_root = ROOT / "2026_副本" / "讲义"
    packages = []
    for package in sorted(p for p in lecture_root.iterdir() if p.is_dir()):
        page_json = sorted(package.glob("page_*.json"))
        aggregate_json = [p for p in package.glob("*.json") if not p.name.startswith("page_")]
        packages.append({
            "name": package.name,
            "path": rel(package),
            "page_json": len(page_json),
            "aggregate_json": len(aggregate_json),
            "sample_pages": [p.name for p in page_json[:3]],
        })
    return {
        "packages": len(packages),
        "page_json": sum(row["page_json"] for row in packages),
        "aggregate_json": sum(row["aggregate_json"] for row in packages),
        "rows": packages,
    }


def summarize_cards() -> dict:
    cards_root = ROOT / "PDF" / "建筑实务11.20_副本" / "graphify-out-full-2026-textbook" / "cards-from-json-all"
    cards = sorted(cards_root.glob("*.md")) if cards_root.exists() else []
    manifest_paths = sorted(cards_root.parent.glob("*manifest*")) if cards_root.exists() else []
    return {
        "path": rel(cards_root) if cards_root.exists() else None,
        "md_cards": len(cards),
        "manifest_candidates": [rel(p) for p in manifest_paths],
    }


def summarize_json_inventory(files: list[Path]) -> dict:
    json_files = [p for p in files if extension(p) == ".json"]
    valid = 0
    invalid = []
    top_keys = Counter()
    top_signatures = Counter()
    by_top = Counter()
    for path in json_files:
        by_top[top_dir(path)] += 1
        try:
            data = load_json(path)
            valid += 1
        except Exception as exc:  # noqa: BLE001 - profiling should keep going.
            invalid.append({"path": rel(path), "error": str(exc)[:200]})
            continue
        if isinstance(data, dict):
            keys = sorted(str(k) for k in data.keys())
            top_keys.update(keys)
            top_signatures.update([" | ".join(keys[:12])])
        else:
            top_signatures.update([type(data).__name__])
    return {
        "json_files": len(json_files),
        "valid_json": valid,
        "invalid_json": invalid,
        "by_top_dir": dict(by_top.most_common()),
        "top_keys": dict(top_keys.most_common(30)),
        "top_signatures": dict(top_signatures.most_common(20)),
    }


def summarize_file_inventory(files: list[Path]) -> dict:
    ext_counter = Counter()
    ext_size = Counter()
    top_counter = Counter()
    top_size = Counter()
    largest = []
    for path in files:
        stat = path.stat()
        ext = extension(path)
        ext_counter[ext] += 1
        ext_size[ext] += stat.st_size
        td = top_dir(path)
        top_counter[td] += 1
        top_size[td] += stat.st_size
        largest.append((stat.st_size, rel(path)))
    largest.sort(reverse=True)
    return {
        "total_files": len(files),
        "total_bytes": sum(size for size, _ in largest),
        "by_extension": [
            {"extension": ext, "files": count, "bytes": ext_size[ext]}
            for ext, count in ext_counter.most_common()
        ],
        "by_top_dir": [
            {"top_dir": name, "files": count, "bytes": top_size[name]}
            for name, count in top_counter.most_common()
        ],
        "largest_files": [{"bytes": size, "path": path} for size, path in largest[:25]],
    }


def summarize_pdf_and_images(files: list[Path]) -> dict:
    pdfs = [p for p in files if extension(p) == ".pdf"]
    images = [p for p in files if extension(p) in {".png", ".jpg", ".jpeg", ".webp"}]
    render_dirs = {
        "docx_render_check": ROOT / "2026_副本" / "题库" / "docx_render_check",
        "docx_render_check_v2": ROOT / "2026_副本" / "题库" / "docx_render_check_v2",
    }
    return {
        "pdf_files": len(pdfs),
        "pdf_by_top_subdir": dict(Counter(p.relative_to(ROOT).parts[:3][1] if p.relative_to(ROOT).parts[0] == "PDF" and len(p.relative_to(ROOT).parts) > 2 else top_dir(p) for p in pdfs).most_common()),
        "image_files": len(images),
        "image_by_extension": dict(Counter(extension(p) for p in images).most_common()),
        "render_check_png": {
            name: len(list(path.glob("*.png"))) if path.exists() else 0
            for name, path in render_dirs.items()
        },
    }


def summarize_duplicate_and_version_signals(files: list[Path]) -> dict:
    basename_counter = Counter(p.name for p in files)
    duplicate_basenames = [
        {"basename": name, "count": count}
        for name, count in basename_counter.most_common(30)
        if count > 1
    ]
    version_signals = defaultdict(list)
    for path in files:
        name = path.name
        if re.search(r"(v\d+|fixed|FINAL_CLEANED|backup|副本|第一次清洗|第二次加强)", rel(path), re.IGNORECASE):
            root_name = re.sub(r"v\d+|_?fixed|FINAL_CLEANED_|副本|backup|第一次清洗|第二次加强", "", name, flags=re.IGNORECASE)
            version_signals[root_name].append(rel(path))
    version_clusters = [
        {"cluster_hint": key, "count": len(paths), "sample_paths": paths[:8]}
        for key, paths in version_signals.items()
        if len(paths) > 1
    ]
    version_clusters.sort(key=lambda row: row["count"], reverse=True)
    return {
        "duplicate_basenames_top": duplicate_basenames,
        "version_cluster_hints_top": version_clusters[:25],
    }


def build_asset_buckets(profile: dict) -> list[dict]:
    exam = profile["assets"]["exam"]
    practice = profile["assets"]["practice"]
    textbook = profile["assets"]["textbook"]
    taxonomy = profile["assets"]["taxonomy"]["stats"]
    standards = profile["assets"]["standards"]
    lectures = profile["assets"]["lectures"]
    media = profile["assets"]["pdf_and_images"]
    cards = profile["assets"]["cards"]
    return [
        {"asset": "历年真题练习", "count": exam["exercises"], "unit": "exercise"},
        {"asset": "章节练习", "count": sum(row["exercises"] for row in practice.values()), "unit": "exercise"},
        {"asset": "教材内容块", "count": textbook["v3_fixed_content_blocks"], "unit": "block"},
        {"asset": "知识卡片", "count": cards["md_cards"], "unit": "card"},
        {"asset": "taxonomy叶节点", "count": taxonomy.get("leaf_count") or 0, "unit": "node"},
        {"asset": "规范条目节点", "count": standards["total_nodes"], "unit": "node"},
        {"asset": "讲义页JSON", "count": lectures["page_json"], "unit": "page_json"},
        {"asset": "PDF资料", "count": media["pdf_files"], "unit": "file"},
        {"asset": "渲染/图片", "count": media["image_files"], "unit": "file"},
    ]


def render_charts(profile: dict) -> None:
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ModuleNotFoundError as exc:
        profile["chart_generation"] = {
            "status": "skipped",
            "reason": f"missing Python chart dependency: {exc.name}",
        }
        return
    import textwrap

    tokens = {
        "surface": "#FCFCFD",
        "panel": "#FFFFFF",
        "ink": "#1F2430",
        "muted": "#6F768A",
        "grid": "#E6E8F0",
        "axis": "#D7DBE7",
    }
    blue = {"base": "#A3BEFA", "dark": "#2E4780", "light": "#CEDFFE", "xlight": "#EAF1FE"}
    orange = {"base": "#F0986E", "dark": "#804126", "light": "#FFBDA1", "xlight": "#FFEDDE"}

    sns.set_theme(
        style="whitegrid",
        rc={
            "figure.facecolor": tokens["surface"],
            "axes.facecolor": tokens["panel"],
            "axes.edgecolor": tokens["axis"],
            "axes.labelcolor": tokens["ink"],
            "grid.color": tokens["grid"],
            "grid.linewidth": 0.8,
            "font.family": "sans-serif",
            "font.sans-serif": ["Aptos", "Inter", "Segoe UI", "DejaVu Sans", "Arial", "sans-serif"],
        },
    )

    def header(fig, ax, title: str, subtitle: str) -> None:
        ax.set_title("")
        left = ax.get_position().x0
        fig.text(left, 0.985, textwrap.fill(title, 76, break_long_words=False), ha="left", va="top", fontsize=13, fontweight="semibold", color=tokens["ink"])
        fig.text(left, 0.925, textwrap.fill(subtitle, 110, break_long_words=False), ha="left", va="top", fontsize=9, color=tokens["muted"])
        fig.subplots_adjust(top=0.78)
        sns.despine(ax=ax)

    ext_rows = profile["raw_asset_file_inventory"]["by_extension"][:10]
    ext_rows = sorted(ext_rows, key=lambda row: row["files"])
    fig, ax = plt.subplots(figsize=(9.6, 6.2))
    labels = [row["extension"] for row in ext_rows]
    values = [row["files"] for row in ext_rows]
    bars = ax.barh(labels, values, color=blue["base"], edgecolor=blue["dark"], linewidth=1.0)
    for bar, value in zip(bars, values):
        ax.text(value + max(values) * 0.01, bar.get_y() + bar.get_height() / 2, f"{value:,}", va="center", fontsize=8, color=tokens["ink"])
    ax.set_xlabel("文件数")
    ax.set_ylabel("扩展名")
    header(fig, ax, "当前原始数据文件类型分布", "范围排除 .git、.DS_Store 与本次数据盘点文档目录；按文件数展示前十类。")
    fig.savefig(CHART_FILE_TYPES, dpi=180, bbox_inches="tight")
    plt.close(fig)

    bucket_rows = build_asset_buckets(profile)
    bucket_rows = sorted(bucket_rows, key=lambda row: row["count"])
    fig, ax = plt.subplots(figsize=(10.5, 6.8))
    labels = [row["asset"] for row in bucket_rows]
    values = [row["count"] for row in bucket_rows]
    bars = ax.barh(labels, values, color=orange["base"], edgecolor=orange["dark"], linewidth=1.0)
    for bar, value, unit in zip(bars, values, [row["unit"] for row in bucket_rows]):
        ax.text(value + max(values) * 0.01, bar.get_y() + bar.get_height() / 2, f"{value:,} {unit}", va="center", fontsize=8, color=tokens["ink"])
    ax.set_xlabel("数量")
    ax.set_ylabel("资产桶")
    header(fig, ax, "可用资产桶规模对比", "不同桶的计量单位不同，用于看供给结构和治理优先级，不用于直接相加。")
    fig.savefig(CHART_ASSET_BUCKETS, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_files = iter_files(include_inventory_docs=False)
    all_files = iter_files(include_inventory_docs=True)
    profile = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "scope": {
            "raw_asset_files_exclude": sorted(EXCLUDED_DIRS | EXCLUDED_TOP_DIRS_FOR_RAW_ASSETS | EXCLUDED_FILES),
            "note": "Primary metrics exclude generated inventory docs under 数据盘点; all_files includes them for reconciliation.",
        },
        "raw_asset_file_inventory": summarize_file_inventory(raw_files),
        "all_file_inventory": summarize_file_inventory(all_files),
        "json_inventory": summarize_json_inventory(raw_files),
        "assets": {
            "exam": summarize_exam_files(),
            "practice": summarize_practice_files(),
            "textbook": summarize_textbook(),
            "taxonomy": summarize_taxonomy(),
            "standards": summarize_standards(),
            "lectures": summarize_lectures(),
            "cards": summarize_cards(),
            "pdf_and_images": summarize_pdf_and_images(raw_files),
            "duplicate_and_version_signals": summarize_duplicate_and_version_signals(raw_files),
        },
    }
    profile["assets"]["asset_buckets"] = build_asset_buckets(profile)
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    render_charts(profile)
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "profile": rel(PROFILE_PATH),
        "charts": [rel(path) for path in [CHART_FILE_TYPES, CHART_ASSET_BUCKETS] if path.exists()],
        "chart_generation": profile.get("chart_generation", {"status": "created"}),
        "raw_asset_files": profile["raw_asset_file_inventory"]["total_files"],
        "raw_asset_bytes": profile["raw_asset_file_inventory"]["total_bytes"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
