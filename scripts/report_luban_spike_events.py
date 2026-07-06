#!/usr/bin/env python3
"""spike D15 埋点取数（QA allowlist 口径与 D1 度量共用同一权威）。

- 事件源：product_behavior_events（register-before-use catalog 词表）。
- QA/内部账号剔除：MemberConsoleService.list_internal_test_user_ids()
  ——与 scripts/report_luban_spike_d1.py 同一权威，绝不各自维护名单。
- 输出：按 event_name 分 全量/剔除 QA 后 双计数，供点火包与读数期直接贴数。

用法（生产容器内）::

    python3 scripts/report_luban_spike_events.py \
        [--db /app/data/user/product_behavior.db] [--days 30] [--json]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="/app/data/user/product_behavior.db")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from deeptutor.services.member_console.service import get_member_console_service

    excluded = get_member_console_service().list_internal_test_user_ids()
    since_ms = int((time.time() - args.days * 86400) * 1000)

    conn = sqlite3.connect(args.db)
    rows = conn.execute(
        """
        select event_name, user_id, count(*)
        from product_behavior_events
        where occurred_at_ms >= ?
        group by event_name, user_id
        """,
        (since_ms,),
    ).fetchall()

    def norm(user_id: str) -> str:
        return user_id.split(":", 1)[1] if user_id.startswith("user:") else user_id

    report: dict[str, dict[str, int]] = {}
    for event_name, user_id, count in rows:
        bucket = report.setdefault(event_name, {"total": 0, "real": 0, "qa_excluded": 0})
        bucket["total"] += count
        if norm(str(user_id)) in excluded or str(user_id) in excluded:
            bucket["qa_excluded"] += count
        else:
            bucket["real"] += count

    payload = {
        "window_days": args.days,
        "allowlist_size": len(excluded),
        "events": report,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"window_days={args.days} allowlist_size={len(excluded)}")
        for name in sorted(report):
            b = report[name]
            print(f"{name}: total={b['total']} real={b['real']} qa_excluded={b['qa_excluded']}")


if __name__ == "__main__":
    main()
