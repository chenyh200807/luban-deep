"""PR-α — session.owner_key 回填脚本（dry-run / apply / verify）

为什么需要：SR1 把 `_authorize_session_access` 的"owner_key 缺失 + anon 放行"
旁路修掉后，**真正遗留 owner_key 为空的老 session 会全部 PermissionError**。
必须先回填，再上 SR1 的行为切换（PR-1b）。

数据语义（从 `deeptutor/services/session/sqlite_store.py` 反推）：
- sessions 表 schema：`owner_key TEXT DEFAULT ''`，session 创建时若 preferences
  里没显式 owner_key 则该列默认空字符串
- `owner_key` 格式：`"user:{user_id}"` （`build_user_owner_key()`）
- user_id 不存 sessions 列，只在 `preferences_json` JSON 内
- derivation 优先级（与 `_derive_owner_key_from_preferences` 一致）：
    1. preferences_json['owner_key'] 非空
    2. preferences_json['user_id'] 非空 → `"user:{user_id}"`
    3. 都没有 → orphan，跳过 + 记录

Idempotent：UPDATE 只动 `owner_key IS NULL OR owner_key = ''`，重复跑无副作用。

用法：

    # 1. dry-run（默认）：count + 列出 sample，不动数据
    python scripts/migrations/pr_alpha_session_owner_key_backfill.py dry-run \\
        --db /root/deeptutor/data/chat_history.db

    # 2. 真实回填（必须显式 --apply）
    python scripts/migrations/pr_alpha_session_owner_key_backfill.py apply \\
        --db /root/deeptutor/data/chat_history.db --apply

    # 3. 抽样验证（回填后跑）：随机抽 N session 校验 owner_key == "user:" + preferences.user_id
    python scripts/migrations/pr_alpha_session_owner_key_backfill.py verify \\
        --db /root/deeptutor/data/chat_history.db --sample 50

退出码：
    0 = OK；1 = 找不到 DB；2 = orphan session 比例 > 5%（需人工干预）；3 = verify 失败
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

# Match the production logic in sqlite_store.build_user_owner_key
USER_OWNER_PREFIX = "user:"


def _build_user_owner_key(user_id: str | None) -> str:
    resolved = str(user_id or "").strip()
    return f"{USER_OWNER_PREFIX}{resolved}" if resolved else ""


def _derive_owner_key_from_prefs(prefs_json: str | None) -> str:
    if not prefs_json:
        return ""
    try:
        prefs = json.loads(prefs_json)
    except (ValueError, TypeError):
        return ""
    if not isinstance(prefs, dict):
        return ""
    explicit = str(prefs.get("owner_key") or "").strip()
    if explicit:
        return explicit
    return _build_user_owner_key(prefs.get("user_id"))


def _scan(conn: sqlite3.Connection) -> dict:
    """Read-only scan; classify every session row."""
    cur = conn.execute("SELECT id, owner_key, preferences_json FROM sessions")
    total = 0
    already = 0
    backfillable = 0
    orphan = 0
    backfill_sample: list[tuple[str, str]] = []
    orphan_sample: list[str] = []
    for sid, owner_key, prefs_json in cur:
        total += 1
        if owner_key and owner_key.strip():
            already += 1
            continue
        derived = _derive_owner_key_from_prefs(prefs_json)
        if derived:
            backfillable += 1
            if len(backfill_sample) < 10:
                # don't print full id (PII safety) — just first 8 chars
                backfill_sample.append((sid[:8] + "...", derived))
        else:
            orphan += 1
            if len(orphan_sample) < 10:
                orphan_sample.append(sid[:8] + "...")
    return {
        "total": total,
        "already_set": already,
        "backfillable": backfillable,
        "orphan": orphan,
        "backfill_sample": backfill_sample,
        "orphan_sample": orphan_sample,
    }


def _print_summary(stats: dict, header: str) -> None:
    print(f"\n=== {header} ===")
    print(f"  total sessions:       {stats['total']}")
    print(f"  owner_key already set:  {stats['already_set']}")
    print(f"  backfillable:           {stats['backfillable']}")
    print(f"  orphan (no derivable):  {stats['orphan']}")
    if stats["backfill_sample"]:
        print("\n  sample backfill (id prefix, derived owner):")
        for sid, owner in stats["backfill_sample"]:
            print(f"    {sid}  →  {owner}")
    if stats["orphan_sample"]:
        print("\n  sample orphan (cannot derive):")
        for sid in stats["orphan_sample"]:
            print(f"    {sid}")


def cmd_dry_run(args: argparse.Namespace) -> int:
    db = Path(args.db)
    if not db.exists():
        print(f"ERROR: DB not found: {db}", file=sys.stderr)
        return 1
    with sqlite3.connect(db) as conn:
        stats = _scan(conn)
    _print_summary(stats, "PR-α owner_key backfill DRY-RUN")
    if stats["backfillable"] == 0:
        print("\n→ Nothing to backfill. Safe to proceed to PR-1b without this script.")
        return 0
    pct = 100.0 * stats["orphan"] / max(stats["total"], 1)
    if pct > 5.0:
        print(f"\n⚠️  Orphan ratio {pct:.1f}% > 5% — investigate before running apply.")
        return 2
    print(f"\n→ {stats['backfillable']} rows will be UPDATEd by `apply --apply`.")
    print(f"   Orphan ratio {pct:.1f}% (within 5% threshold).")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    db = Path(args.db)
    if not db.exists():
        print(f"ERROR: DB not found: {db}", file=sys.stderr)
        return 1
    if not args.apply:
        print("ERROR: refuse to write without --apply (default is dry-only).", file=sys.stderr)
        return 1
    with sqlite3.connect(db) as conn:
        pre = _scan(conn)
        if pre["backfillable"] == 0:
            print("Nothing to backfill.")
            return 0
        cur = conn.execute(
            "SELECT id, preferences_json FROM sessions "
            "WHERE owner_key IS NULL OR owner_key = ''"
        )
        rows: list[tuple[str, str]] = []
        for sid, prefs_json in cur:
            derived = _derive_owner_key_from_prefs(prefs_json)
            if derived:
                rows.append((derived, sid))
        # Single transaction for atomicity
        conn.executemany("UPDATE sessions SET owner_key = ? WHERE id = ?", rows)
        conn.commit()
        post = _scan(conn)
    _print_summary(pre, "PRE-apply")
    _print_summary(post, "POST-apply")
    print(f"\n→ Backfilled {len(rows)} sessions.")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Sample N session ids that should now have owner_key set; recompute and compare."""
    db = Path(args.db)
    if not db.exists():
        print(f"ERROR: DB not found: {db}", file=sys.stderr)
        return 1
    with sqlite3.connect(db) as conn:
        cur = conn.execute(
            "SELECT id, owner_key, preferences_json FROM sessions "
            "WHERE owner_key IS NOT NULL AND owner_key != ''"
        )
        candidates: list[tuple[str, str, str]] = cur.fetchall()
    if not candidates:
        print("No sessions with owner_key set — nothing to verify.")
        return 0
    sample_size = min(args.sample, len(candidates))
    sample = random.sample(candidates, sample_size)
    mismatches: list[tuple[str, str, str]] = []
    for sid, owner_key, prefs_json in sample:
        expected = _derive_owner_key_from_prefs(prefs_json)
        # If preferences cannot derive (orphan-but-set), accept owner_key as-is
        if not expected:
            continue
        if owner_key.strip() != expected:
            mismatches.append((sid[:8] + "...", owner_key, expected))
    print(f"\nVerified {sample_size} samples; mismatches: {len(mismatches)}")
    if mismatches:
        print("\n  mismatch details (id prefix, stored, expected):")
        for sid, stored, expected in mismatches[:10]:
            print(f"    {sid}  stored={stored}  expected={expected}")
        return 3
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PR-α session.owner_key backfill")
    parser.add_argument("--db", required=True, help="Path to chat_history.db")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dry-run", help="Read-only scan + sample (default)")
    p_apply = sub.add_parser("apply", help="Run UPDATE")
    p_apply.add_argument("--apply", action="store_true", help="Required to actually write")
    p_verify = sub.add_parser("verify", help="Sample N rows + cross-check")
    p_verify.add_argument("--sample", type=int, default=50)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd == "dry-run":
        return cmd_dry_run(args)
    if args.cmd == "apply":
        return cmd_apply(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    parser.error("unknown command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
