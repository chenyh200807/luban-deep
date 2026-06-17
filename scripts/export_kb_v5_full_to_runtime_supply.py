"""从 KB v5 Supabase 导出全量 chunks 为本地 runtime supply bundle.

只读操作：从 kb_v5.chunks 表读取所有 data_version=2026 的记录，
写入本地 v_kb_v5_chunks_full bundle (不访问远端 embedding，不触发 search_chunks_v2)。

运行:
    python scripts/export_kb_v5_full_to_runtime_supply.py
    python scripts/export_kb_v5_full_to_runtime_supply.py --dry-run  # 只统计，不写文件
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BUNDLE_DIR = ROOT / "deeptutor/services/construction_grading/runtime_supply/v_kb_v5_chunks_full"
DATA_VERSION = 2026

# Columns to export (no embedding vector — vectors are large and not needed for local supply)
EXPORT_COLS = [
    "chunk_id", "doc_id", "doc_type", "authority",
    "content", "loc", "data_version"
]


class _SafeEncoder(json.JSONEncoder):
    def default(self, o):
        import decimal
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super().default(o)


def _sha256_hex(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, cls=_SafeEncoder).encode("utf-8")
    ).hexdigest()


def _safe_dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, cls=_SafeEncoder)


def export(dry_run: bool = False) -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    db_url = os.environ.get("KBV5_DB_URL")
    if not db_url:
        print("ERROR: KBV5_DB_URL not set", file=sys.stderr)
        sys.exit(1)

    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("ERROR: psycopg2 not installed", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to KB v5 (read-only)...")
    conn = psycopg2.connect(db_url)
    conn.set_session(readonly=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Count first
    cur.execute(
        "SELECT doc_type, COUNT(*) as cnt FROM kb_v5.chunks "
        "WHERE data_version = %s GROUP BY doc_type ORDER BY cnt DESC",
        (DATA_VERSION,)
    )
    type_counts = {row["doc_type"]: row["cnt"] for row in cur.fetchall()}
    total = sum(type_counts.values())
    print(f"Total chunks: {total}")
    for dt, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {dt}: {cnt}")

    if dry_run:
        conn.close()
        print("\n[dry-run] Not fetching or writing.")
        return

    # Fetch all records in batches
    cols_sql = ", ".join(EXPORT_COLS)
    cur.execute(
        f"SELECT {cols_sql} FROM kb_v5.chunks "
        "WHERE data_version = %s "
        "ORDER BY doc_type, doc_id, chunk_id",
        (DATA_VERSION,)
    )
    records = []
    batch = cur.fetchmany(500)
    while batch:
        for row in batch:
            record = dict(row)
            # Convert non-serializable types
            for k, v in record.items():
                if hasattr(v, '__dict__') or type(v).__name__ == 'Json':
                    record[k] = str(v)
            records.append(record)
        batch = cur.fetchmany(500)
        if len(records) % 1000 == 0:
            print(f"  fetched {len(records)}...")

    conn.close()
    print(f"Fetched {len(records)} chunks total")

    # Build bundle
    content_hash = _sha256_hex(records)
    namespace = "kb_v5_chunks_full"
    status = "release_candidate"

    manifest = {
        "schema_version": "luban_kb_v5_export.v1",
        "namespace": namespace,
        "lane": "kb_v5_chunks_full",
        "status": status,
        "published": False,
        "chunk_count": len(records),
        "by_doc_type": type_counts,
        "data_version": DATA_VERSION,
        "export_date": "2026-06-08",
        "content_hash": content_hash,
        "signature": _sha256_hex([content_hash, namespace, status]),
        "rollback_pointer": "no_prior_kb_v5_full_export",
        "note": "full snapshot of kb_v5.chunks (no embedding vectors), for offline RAG supply",
    }

    bundle = {"manifest": manifest, "records": records}

    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BUNDLE_DIR / "kb_v5_chunks_full.json"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_safe_dump(bundle))
    print(f"Wrote bundle: {out_path}")

    pointer = {
        "namespace": namespace,
        "status": status,
        "published": False,
        "chunk_count": len(records),
        "content_hash": content_hash,
        "bundle_file": "kb_v5_chunks_full.json",
    }
    ptr_path = BUNDLE_DIR / "canonical_pointer.json"
    with open(ptr_path, "w", encoding="utf-8") as f:
        json.dump(pointer, f, ensure_ascii=False, indent=2)
    print(f"Wrote pointer: {ptr_path}")
    print(f"\nDone. chunk_count={len(records)}, by_type={type_counts}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    export(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
