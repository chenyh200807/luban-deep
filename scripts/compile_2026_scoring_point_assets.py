#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from deeptutor.services.source_compiler.jsonl import write_jsonl
from deeptutor.services.source_compiler.metadata import utc_now_iso
from deeptutor.services.source_compiler.platform import RunDirectoryLock, detect_dataless
from deeptutor.services.source_compiler.scoring_point_asset_compiler import (
    SCHEMA_VERSION,
    compile_scoring_point_assets,
)


BOOK_GLOB = "FINAL_CLEANED_BOOK2026-*_fixed.json"


def _source_root() -> Path:
    value = os.environ.get("LUBAN_2026_SOURCE_ROOT")
    if value:
        return Path(value)
    return Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")


def _book_dir(source_root: Path) -> Path:
    return source_root / "2026教材" / "第二次加强"


def _run_dir(run_id: str) -> Path:
    return Path("artifacts") / "knowledge_compiler" / "2026" / run_id


def _load_blocks(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        blocks = payload.get("content_blocks") or []
    elif isinstance(payload, list):
        blocks = payload
    else:
        blocks = []
    return [block for block in blocks if isinstance(block, dict)]


def _node_code(block: dict[str, Any]) -> str:
    taxonomy = block.get("taxonomy") if isinstance(block.get("taxonomy"), dict) else {}
    return str(taxonomy.get("node_code") or "UNKNOWN").strip() or "UNKNOWN"


def _content_type(block: dict[str, Any]) -> str:
    return str(block.get("content_type") or "unknown")


def _pdf_page_hint(block: dict[str, Any]) -> int | None:
    source_meta = block.get("source_meta") if isinstance(block.get("source_meta"), dict) else {}
    source_name = str(source_meta.get("source_name") or source_meta.get("file_path") or "")
    relative_page = source_meta.get("page_num")
    try:
        page_num = int(relative_page)
    except (TypeError, ValueError):
        return None
    match = re.search(r"BOOK2026-(\d+)-(\d+)|教材_(\d+)-(\d+)", source_name)
    if not match:
        return page_num
    start_page = int(match.group(1) or match.group(3))
    return start_page + page_num - 1


def _pdf_page_hint_from_row(row: dict[str, Any]) -> int | None:
    source_path = str(row.get("source_path") or "")
    page_num = row.get("page_num")
    try:
        page = int(page_num)
    except (TypeError, ValueError):
        return None
    match = re.search(r"BOOK2026-(\d+)-(\d+)|教材_(\d+)-(\d+)", source_path)
    if not match:
        return page
    return int(match.group(1) or match.group(3)) + page - 1


def _combine_reports(reports: list[dict[str, Any]], *, run_id: str, compiled_at: str) -> dict[str, Any]:
    point_types: Counter[str] = Counter()
    anchors: Counter[str] = Counter()
    discarded: Counter[str] = Counter()
    content_types: Counter[str] = Counter()
    node_asset_counts: Counter[str] = Counter()
    totals = {
        "chunk_count": 0,
        "asset_count": 0,
        "seed_total": 0,
        "seed_hit": 0,
        "seed_miss": 0,
        "invalid_textbook_anchor_count": 0,
        "loose_anchor_violation_count": 0,
    }
    failed_batches: list[str] = []
    for report in reports:
        for key in totals:
            totals[key] += int(report.get(key) or 0)
        point_types.update(report.get("point_type_counts") or {})
        anchors.update(report.get("anchor_source_counts") or {})
        discarded.update(report.get("discarded_candidates") or {})
        content_types.update(report.get("content_type_counts") or {})
        node_asset_counts.update(report.get("node_asset_counts") or {})
        if report.get("quality_gate") != "pass":
            failed_batches.append(str(report.get("batch_id") or report.get("source_path") or "unknown"))
    text_assets = totals["asset_count"] - anchors.get("calculation", 0)
    textbook_assets = anchors.get("textbook", 0)
    return {
        "schema_version": SCHEMA_VERSION,
        "version_id": run_id,
        "compiled_at": compiled_at,
        **totals,
        "node_count": len(node_asset_counts),
        "point_type_counts": dict(sorted(point_types.items())),
        "anchor_source_counts": dict(sorted(anchors.items())),
        "content_type_counts": dict(sorted(content_types.items())),
        "discarded_candidates": dict(sorted(discarded.items())),
        "seed_hit_rate": totals["seed_hit"] / totals["seed_total"] if totals["seed_total"] else None,
        "textbook_anchor_rate_for_text_assets": textbook_assets / text_assets if text_assets else None,
        "quality_gate": "pass" if not failed_batches and totals["invalid_textbook_anchor_count"] == 0 and totals["loose_anchor_violation_count"] == 0 else "fail",
        "failed_batches": failed_batches,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit-chunks", type=int)
    parser.add_argument("--min-textbook-anchor-rate", type=float, default=0.85)
    parser.add_argument("--pdf-path", default="/Users/yehongchen/Documents/CYH_2/Markzuo/建筑实务11.20/2026一建《建筑》电子版教材.pdf")
    args = parser.parse_args()

    try:
        source_root = _source_root()
        book_dir = _book_dir(source_root)
        paths = sorted(book_dir.glob(BOOK_GLOB))
        if not paths:
            raise FileNotFoundError(f"no book JSON files matched {book_dir / BOOK_GLOB}")
        run_dir = _run_dir(args.run_id)
        lock = RunDirectoryLock(run_dir, force=args.force)
        lock.prepare()
        compiled_at = utc_now_iso()
        all_rows: list[dict[str, Any]] = []
        batch_reports: list[dict[str, Any]] = []
        pdf_spotcheck_queue: list[dict[str, Any]] = []
        try:
            for path in paths:
                if detect_dataless(path, platform_name=sys.platform):
                    continue
                blocks = _load_blocks(path)
                if args.limit_chunks is not None:
                    remaining = max(args.limit_chunks - sum(report["chunk_count"] for report in batch_reports), 0)
                    if remaining <= 0:
                        break
                    blocks = blocks[:remaining]
                by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for block in blocks:
                    by_node[_node_code(block)].append(block)
                for node_code, node_blocks in sorted(by_node.items()):
                    rows, report = compile_scoring_point_assets(
                        node_blocks,
                        run_id=args.run_id,
                        source_path=str(path.relative_to(source_root)),
                        compiled_at=compiled_at,
                    )
                    content_type_counts = Counter(_content_type(block) for block in node_blocks)
                    report.update(
                        {
                            "batch_id": f"{path.name}:{node_code}",
                            "source_file": str(path.relative_to(source_root)),
                            "node_code": node_code,
                            "content_type_counts": dict(sorted(content_type_counts.items())),
                            "node_asset_counts": {node_code: len(rows)},
                        }
                    )
                    if report["quality_gate"] != "pass":
                        raise RuntimeError(f"quality gate failed for {report['batch_id']}: {report}")
                    all_rows.extend(rows)
                    batch_reports.append(report)
                    sample_size = max(1, round(len(rows) * 0.05)) if rows else 0
                    for row in rows[:sample_size]:
                        pdf_spotcheck_queue.append(
                            {
                                "point_id": row["point_id"],
                                "node_code": row["node_code"],
                                "chunk_id": row["chunk_id"],
                                "page_hint": _pdf_page_hint_from_row(row),
                                "quote": row["provenance"].get("quote"),
                                "anchor_source": row["anchor_source"],
                                "status": "pending_visual_review",
                            }
                        )

            overall = _combine_reports(batch_reports, run_id=args.run_id, compiled_at=compiled_at)
            rate = overall.get("textbook_anchor_rate_for_text_assets")
            if rate is not None and rate < args.min_textbook_anchor_rate:
                overall["quality_gate"] = "fail"
                overall["failed_batches"].append("overall_textbook_anchor_rate_below_threshold")
            write_jsonl(run_dir / "scoring_point_assets.jsonl", all_rows)
            write_jsonl(run_dir / "batch_reports.jsonl", batch_reports)
            (run_dir / "quality_report.json").write_text(json.dumps(overall, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            (run_dir / "pdf_spotcheck_queue.json").write_text(
                json.dumps(
                    {
                        "pdf_path": args.pdf_path,
                        "note": "Render page_hint with pdftoppm and visually verify quote against PDF; do not use PDF text layer as authority.",
                        "samples": pdf_spotcheck_queue,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            node_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in all_rows:
                node_index[row["node_code"]].append(row)
            (run_dir / "scoring_point_assets_by_node.json").write_text(json.dumps(node_index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            print(
                " ".join(
                    [
                        f"assets={overall['asset_count']}",
                        f"nodes={overall['node_count']}",
                        f"textbook_anchor_rate={overall['textbook_anchor_rate_for_text_assets']:.4f}" if overall["textbook_anchor_rate_for_text_assets"] is not None else "textbook_anchor_rate=NA",
                        f"seed_hit_rate={overall['seed_hit_rate']:.4f}" if overall["seed_hit_rate"] is not None else "seed_hit_rate=NA",
                        f"gate={overall['quality_gate']}",
                        f"run_dir={run_dir}",
                    ]
                )
            )
            return 0 if overall["quality_gate"] == "pass" else 2
        finally:
            lock.release()
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
