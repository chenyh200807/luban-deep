#!/usr/bin/env python3
"""Read-only audit of TutorBot working_memory projections (task#32 出处链化).

对每条 bot-learner overlay 的 working_memory_projection 展示：
- 内容摘要（首 60 字符）
- 出处 turn_id / source_kind / 写入时间（或 LEGACY = 出处强制上线前的存量记忆）
- 该 (user, bot) 曾被拒入的次数与最近一次原因（含 #638 安全模板拒入、缺出处拒入）

只读，不改任何文件。用法：

    python scripts/audit_working_memory.py                 # 全量表格
    python scripts/audit_working_memory.py --user <uid>    # 只看某学员
    python scripts/audit_working_memory.py --legacy-only   # 只看无出处存量
    python scripts/audit_working_memory.py --json          # 机器可读
    python scripts/audit_working_memory.py --root <dir>    # 指定 bot_overlays 目录
                                                           # （如审计生产数据拷贝）
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

_WM_REJECTED_EVENT_TYPE = "overlay_working_memory_rejected"


def _default_root() -> Path:
    from deeptutor.services.path_service import get_path_service

    return get_path_service().get_learner_state_root() / "bot_overlays"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_rejections(events_path: Path) -> list[dict[str, Any]]:
    if not events_path.exists():
        return []
    rejections: list[dict[str, Any]] = []
    try:
        with events_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except Exception:
                    continue
                if (
                    isinstance(event, dict)
                    and str(event.get("event_type") or "") == _WM_REJECTED_EVENT_TYPE
                ):
                    rejections.append(event)
    except Exception:
        return rejections
    return rejections


def collect_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        if path.name.endswith(".events.jsonl"):
            continue
        payload = _read_json(path)
        overlay = dict(payload.get("overlay") or {})
        projection = str(overlay.get("working_memory_projection") or "").strip()
        provenance = dict(overlay.get("working_memory_provenance") or {})
        rejections = _read_rejections(path.with_name(path.stem + ".events.jsonl"))
        last_rejection = rejections[-1] if rejections else {}
        legacy = bool(projection) and not provenance
        rows.append(
            {
                "user_id": str(payload.get("user_id") or path.stem.split("__", 1)[0]),
                "bot_id": str(
                    payload.get("bot_id")
                    or (path.stem.split("__", 1)[1] if "__" in path.stem else "")
                ),
                "updated_at": str(payload.get("updated_at") or ""),
                "content_preview": projection[:60],
                "content_chars": len(projection),
                "has_memory": bool(projection),
                "provenance_turn_id": str(provenance.get("turn_id") or ""),
                "provenance_source_kind": str(provenance.get("source_kind") or ""),
                "provenance_written_at": str(provenance.get("written_at") or ""),
                # admin 边界盖章的写入带 actor：能查到是**谁**改的（比 turn_id 更有审计价值）
                "provenance_actor": str(provenance.get("actor") or ""),
                "legacy_no_provenance": legacy,
                "rejected_count": len(rejections),
                "last_rejection_reason": str(last_rejection.get("reason") or ""),
                "last_rejection_at": str(last_rejection.get("created_at") or ""),
            }
        )
    rows.sort(key=lambda item: item["updated_at"], reverse=True)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None, help="bot_overlays 目录（默认取 PathService）")
    parser.add_argument("--user", default="", help="只看该 user_id（前缀匹配 normalize 后的 key 亦可）")
    parser.add_argument("--bot", default="", help="只看该 bot_id")
    parser.add_argument("--limit", type=int, default=0, help="最多输出 N 行（0=全部）")
    parser.add_argument("--legacy-only", action="store_true", help="只输出无出处的存量记忆")
    parser.add_argument("--json", action="store_true", dest="as_json", help="输出 JSON")
    args = parser.parse_args()

    root = args.root or _default_root()
    if not root.exists():
        print(f"bot_overlays 目录不存在: {root}", file=sys.stderr)
        return 1

    rows = collect_rows(root)
    if args.user:
        rows = [r for r in rows if args.user in r["user_id"]]
    if args.bot:
        rows = [r for r in rows if args.bot in r["bot_id"]]
    if args.legacy_only:
        rows = [r for r in rows if r["legacy_no_provenance"]]

    total = len(rows)
    with_memory = [r for r in rows if r["has_memory"]]
    legacy = [r for r in rows if r["legacy_no_provenance"]]
    with_provenance = [r for r in with_memory if r["provenance_turn_id"]]
    rejected_total = sum(r["rejected_count"] for r in rows)

    if args.limit > 0:
        rows = rows[: args.limit]

    if args.as_json:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "summary": {
                        "overlays": total,
                        "with_memory": len(with_memory),
                        "with_provenance": len(with_provenance),
                        "legacy_no_provenance": len(legacy),
                        "rejected_events_total": rejected_total,
                    },
                    "rows": rows,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"working_memory 审计  root={root}")
    print(
        f"overlays={total}  有记忆={len(with_memory)}  带出处={len(with_provenance)}  "
        f"LEGACY无出处={len(legacy)}  拒入事件={rejected_total}"
    )
    admin_writes = [r for r in with_memory if r["provenance_source_kind"] == "admin_override"]
    if admin_writes:
        print(f"其中 admin 手工写入={len(admin_writes)}（source_kind=admin_override，actor 可查）")
    print("-" * 118)
    header = f"{'user':<20} {'bot':<14} {'出处turn_id':<28} {'写入时间':<26} {'拒入':>4}  内容摘要"
    print(header)
    print("-" * 118)
    for row in rows:
        if row["has_memory"]:
            origin = row["provenance_turn_id"] or "LEGACY(无出处)"
        else:
            origin = "(空)"
        written = row["provenance_written_at"] or row["updated_at"]
        reject = str(row["rejected_count"]) if row["rejected_count"] else "-"
        if row["last_rejection_reason"]:
            reject = f"{row['rejected_count']}({row['last_rejection_reason'][:24]})"
        print(
            f"{row['user_id'][:20]:<20} {row['bot_id'][:14]:<14} {origin[:28]:<28} "
            f"{written[:26]:<26} {reject:>4}  {row['content_preview']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
