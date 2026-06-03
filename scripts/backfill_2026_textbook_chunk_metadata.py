#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deeptutor.services.taxonomy.textbook_directory import textbook_topic_meta


BOOK_FILENAMES = (
    "FINAL_CLEANED_BOOK2026-9-166v3_fixed.json",
    "FINAL_CLEANED_BOOK2026-167-221v3_fixed.json",
    "FINAL_CLEANED_BOOK2026-222-382_fixed.json",
)

GENERIC_TITLES = {"", "document", "source", "textbook", "教材", "2026教材"}


@dataclass(frozen=True)
class TextbookMetadataPatch:
    chunk_id: str
    title: str
    node_code: str
    taxonomy_path: str
    page_num: int | None
    source_doc: str
    metadata: dict[str, Any]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int_or_none(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_files(args: argparse.Namespace) -> list[Path]:
    if args.source_file:
        return [Path(value) for value in args.source_file]
    root_value = args.source_root or os.getenv("LUBAN_2026_SOURCE_ROOT") or ""
    if not root_value:
        raise RuntimeError("--source-root or --source-file is required")
    source_root = Path(root_value)
    return [source_root / "2026教材" / "第二次加强" / name for name in BOOK_FILENAMES]


def _path_names(taxonomy_path: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*(?:>|/|／)\s*", taxonomy_path) if part.strip()]


def _first_heading(markdown: str) -> str:
    match = re.search(r"^#{3,6}\s+(.+)$", markdown or "", flags=re.MULTILINE)
    return _text(match.group(1)) if match else ""


def _strip_section_number(value: str) -> str:
    text = _text(value)
    text = re.sub(r"^\d+(?:\.\d+)*\s*", "", text)
    return _text(text)


def _section_label(block: dict[str, Any], taxonomy_path: str, title: str) -> str:
    source_meta = block.get("source_meta") if isinstance(block.get("source_meta"), dict) else {}
    anchor = _text(source_meta.get("original_anchor"))
    heading = _first_heading(_text(block.get("content_markdown")))
    for candidate in (anchor, heading):
        if re.match(r"^\d+(?:\.\d+)+\s+", candidate):
            return _strip_section_number(candidate)
    for candidate in (title, _text((block.get("taxonomy") or {}).get("topic")), *reversed(_path_names(taxonomy_path))):
        if candidate:
            return candidate
    return ""


def _title(block: dict[str, Any], taxonomy_path: str) -> str:
    taxonomy = block.get("taxonomy") if isinstance(block.get("taxonomy"), dict) else {}
    source_meta = block.get("source_meta") if isinstance(block.get("source_meta"), dict) else {}
    return (
        _first_heading(_text(block.get("content_markdown")))
        or _text(taxonomy.get("topic"))
        or _text(source_meta.get("original_anchor"))
        or _text(taxonomy.get("node_name"))
        or (_path_names(taxonomy_path)[-1] if _path_names(taxonomy_path) else "")
        or _text(block.get("chunk_id"))
    )


def _source_doc(source_meta: dict[str, Any], source_path: Path) -> str:
    return (
        _text(source_meta.get("source_name"))
        or _text(source_meta.get("file_path")).removesuffix(".pdf")
        or source_path.stem
    )


def build_patch(block: dict[str, Any], *, source_path: Path) -> TextbookMetadataPatch | None:
    chunk_id = _text(block.get("chunk_id"))
    if not chunk_id:
        return None
    taxonomy = block.get("taxonomy") if isinstance(block.get("taxonomy"), dict) else {}
    source_meta = block.get("source_meta") if isinstance(block.get("source_meta"), dict) else {}
    node_code = _text(taxonomy.get("node_code"))
    taxonomy_path = _text(taxonomy.get("taxonomy_path"))
    title = _title(block, taxonomy_path)
    page_num = _int_or_none(source_meta.get("page_num"))
    path_names = _path_names(taxonomy_path)
    section = _section_label(block, taxonomy_path, title)
    textbook_meta = textbook_topic_meta(raw_value=node_code, label=section or title, path_names=path_names)
    chapter = _text(textbook_meta.get("textbook_chapter_name"))
    if not section:
        section = _text(textbook_meta.get("textbook_section_name"))
    source_doc = _source_doc(source_meta, source_path)
    source_span = {
        "chapter": chapter,
        "section": section,
        "page": page_num,
        "anchor": _text(source_meta.get("original_anchor")),
        "knowledge_point": _text(taxonomy.get("topic")) or title,
        "node_code": node_code,
        "taxonomy_path": taxonomy_path,
        "source_chunk_id": chunk_id,
        "source_doc": source_doc,
    }
    source_span = {key: value for key, value in source_span.items() if value not in ("", None)}
    metadata = {
        "title": title,
        "source_id": chunk_id,
        "stable_id": f"kb_chunks:{chunk_id}",
        "source_table": "kb_chunks",
        "source_type": "textbook",
        "source_doc": source_doc,
        "node_code": node_code,
        "taxonomy_path": taxonomy_path,
        "source_span": source_span,
    }
    return TextbookMetadataPatch(
        chunk_id=chunk_id,
        title=title,
        node_code=node_code,
        taxonomy_path=taxonomy_path,
        page_num=page_num,
        source_doc=source_doc,
        metadata={key: value for key, value in metadata.items() if value not in ("", None, {})},
    )


def load_patches(source_files: list[Path]) -> dict[str, TextbookMetadataPatch]:
    patches: dict[str, TextbookMetadataPatch] = {}
    for source_path in source_files:
        if not source_path.exists():
            raise RuntimeError(f"source file not found: {source_path}")
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        blocks = payload.get("content_blocks") if isinstance(payload, dict) else None
        if not isinstance(blocks, list):
            raise RuntimeError(f"source file has no content_blocks: {source_path}")
        for block in blocks:
            if not isinstance(block, dict):
                continue
            patch = build_patch(block, source_path=source_path)
            if patch is None:
                continue
            if patch.chunk_id in patches:
                raise RuntimeError(f"duplicate chunk_id in source files: {patch.chunk_id}")
            patches[patch.chunk_id] = patch
    return patches


def _db_url(explicit: str = "") -> str:
    return explicit or os.getenv("DB_URL") or os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL") or ""


def _metadata_update(existing: dict[str, Any], patch: TextbookMetadataPatch, *, force: bool) -> tuple[dict[str, Any], list[str]]:
    update: dict[str, Any] = {}
    conflicts: list[str] = []
    for key, value in patch.metadata.items():
        current = existing.get(key)
        if current in (None, "", {}, []):
            update[key] = value
            continue
        if current == value:
            continue
        if force:
            update[key] = value
        else:
            conflicts.append(f"metadata.{key}")
    return update, conflicts


def _row_plan(row: dict[str, Any], patch: TextbookMetadataPatch, *, force_metadata: bool) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    metadata_update, conflicts = _metadata_update(metadata, patch, force=force_metadata)
    top_update: dict[str, Any] = {}
    for key, value in (
        ("node_code", patch.node_code),
        ("taxonomy_path", patch.taxonomy_path),
        ("page_num", patch.page_num),
    ):
        current = row.get(key)
        if current in (None, "") and value not in (None, ""):
            top_update[key] = value
        elif value not in (None, "") and current not in (None, "") and str(current) != str(value):
            conflicts.append(key)
    if row.get("source_doc") in (None, "") and patch.source_doc:
        top_update["source_doc"] = patch.source_doc
    current_title = _text(row.get("card_title"))
    if current_title.lower() in GENERIC_TITLES and patch.title:
        top_update["card_title"] = patch.title
    return {
        "chunk_id": patch.chunk_id,
        "top_update": top_update,
        "metadata_update": metadata_update,
        "conflicts": sorted(set(conflicts)),
    }


def _connect(db_url: str):
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - environment guard.
        raise RuntimeError("psycopg is required for Supabase metadata backfill") from exc
    return psycopg.connect(db_url, connect_timeout=10)


def _fetch_rows(conn: Any, chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
    import psycopg.rows

    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            """
            SELECT chunk_id, card_title, node_code, taxonomy_path, page_num, source_doc, metadata
            FROM public.kb_chunks
            WHERE source_type = 'textbook' AND chunk_id = ANY(%s)
            """,
            (chunk_ids,),
        )
        return {str(row["chunk_id"]): dict(row) for row in cur.fetchall()}


def _apply_updates(conn: Any, plans: list[dict[str, Any]]) -> int:
    from psycopg.types.json import Jsonb

    applied = 0
    with conn.cursor() as cur:
        for plan in plans:
            if plan["conflicts"] or (not plan["top_update"] and not plan["metadata_update"]):
                continue
            set_parts = ["metadata = metadata || %s::jsonb", "updated_at = now()"]
            params: list[Any] = [Jsonb(plan["metadata_update"])]
            for column, value in plan["top_update"].items():
                set_parts.append(f"{column} = %s")
                params.append(value)
            params.append(plan["chunk_id"])
            cur.execute(
                f"""
                UPDATE public.kb_chunks
                SET {", ".join(set_parts)}
                WHERE source_type = 'textbook' AND chunk_id = %s
                """,
                params,
            )
            applied += cur.rowcount
    conn.commit()
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill 2026 textbook chunk citation metadata into Supabase kb_chunks.")
    parser.add_argument("--source-root", default="", help="2026 source root containing 2026教材/第二次加强")
    parser.add_argument("--source-file", action="append", default=[], help="Specific cleaned textbook JSON file; repeatable")
    parser.add_argument("--db-url", default="", help="Optional database URL; defaults to DB_URL/DATABASE_URL/SUPABASE_DB_URL")
    parser.add_argument("--apply", action="store_true", help="Apply safe exact chunk_id updates. Omit for dry-run.")
    parser.add_argument("--force-metadata", action="store_true", help="Overwrite conflicting metadata keys. Top-level conflicts still block.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    try:
        patches = load_patches(_source_files(args))
        db_url = _db_url(args.db_url)
        if not db_url:
            raise RuntimeError("DB_URL, DATABASE_URL, or SUPABASE_DB_URL is required")
        with _connect(db_url) as conn:
            rows = _fetch_rows(conn, sorted(patches))
            plans = [_row_plan(rows[chunk_id], patch, force_metadata=args.force_metadata) for chunk_id, patch in patches.items() if chunk_id in rows]
            report = {
                "source_chunks": len(patches),
                "matched_textbook_rows": len(rows),
                "unmatched_source_chunks": len(patches) - len(rows),
                "candidate_updates": sum(1 for plan in plans if not plan["conflicts"] and (plan["top_update"] or plan["metadata_update"])),
                "conflict_rows": sum(1 for plan in plans if plan["conflicts"]),
                "noop_rows": sum(1 for plan in plans if not plan["conflicts"] and not plan["top_update"] and not plan["metadata_update"]),
                "apply": bool(args.apply),
                "sample_updates": [plan for plan in plans if not plan["conflicts"] and (plan["top_update"] or plan["metadata_update"])][:5],
                "sample_conflicts": [plan for plan in plans if plan["conflicts"]][:5],
                "sample_unmatched": [chunk_id for chunk_id in sorted(patches) if chunk_id not in rows][:20],
            }
            if args.apply:
                report["applied_rows"] = _apply_updates(conn, plans)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(
                    " ".join(
                        [
                            f"source_chunks={report['source_chunks']}",
                            f"matched_textbook_rows={report['matched_textbook_rows']}",
                            f"unmatched_source_chunks={report['unmatched_source_chunks']}",
                            f"candidate_updates={report['candidate_updates']}",
                            f"conflict_rows={report['conflict_rows']}",
                            f"noop_rows={report['noop_rows']}",
                            f"apply={report['apply']}",
                            f"applied_rows={report.get('applied_rows', 0)}",
                        ]
                    )
                )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should fail closed with a clear message.
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
