#!/usr/bin/env python3
"""spike D1 度量（乙案 owner-approved 2026-07-02 的唯一执行口径）。

判据登记：docs/plan/鲁班移动端提分闭环/2026-07-02-luban-spike-d1-baseline-preregistration.md
- D1 定义：sessions.owner_key 为用户，turns.created_at（unixepoch, UTC+8 取日）为活动日；
  首个活动日 D0，D0+1 有任意 turn 即留存；首访=当天的用户不入 cohort。
- QA/内部账号剔除：**唯一权威 = MemberConsoleService.list_internal_test_user_ids()**
  （复用 _looks_like_test_member，不再用 turns>50 启发式——启发式仅作对照披露）。
- 乙案判据：D1 ≥ 15% 且 cohort ≥ 30 才读数；窗口 ≥ 7 天。

用法（生产容器内）::

    python3 scripts/report_luban_spike_d1.py [--db /app/data/user/chat_history.db] [--json]
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import sqlite3

COHORT_MIN = 30
D1_THRESHOLD = 0.15


def load_activity(db_path: str) -> dict[str, set[str]]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        select s.owner_key, date(datetime(t.created_at, 'unixepoch', '+8 hours')) d
        from turns t join sessions s on s.id = t.session_id
        where s.owner_key is not null and s.owner_key != ''
        """
    ).fetchall()
    days: dict[str, set[str]] = collections.defaultdict(set)
    for owner_key, day in rows:
        if day:
            days[str(owner_key)].add(day)
    return days


def owner_key_uuid(owner_key: str) -> str:
    return owner_key.split(":", 1)[1] if owner_key.startswith("user:") else owner_key


def compute_d1(
    days: dict[str, set[str]],
    excluded_ids: set[str],
    *,
    today: datetime.date,
) -> dict:
    cohort = retained = excluded = 0
    for owner_key, active_days in days.items():
        if owner_key_uuid(owner_key) in excluded_ids or owner_key in excluded_ids:
            excluded += 1
            continue
        first = min(active_days)
        next_day = (datetime.date.fromisoformat(first) + datetime.timedelta(days=1)).isoformat()
        if next_day >= today.isoformat():
            continue  # D1 窗口未过
        cohort += 1
        retained += 1 if next_day in active_days else 0
    d1 = (retained / cohort) if cohort else None
    return {
        "cohort": cohort,
        "retained": retained,
        "excluded_internal_accounts": excluded,
        "d1": round(d1, 4) if d1 is not None else None,
        "cohort_gate_met": cohort >= COHORT_MIN,
        "criterion": f"乙案: D1>={D1_THRESHOLD:.0%} 且 cohort>={COHORT_MIN}",
        "verdict": (
            "未达读数条件（cohort 门槛）"
            if cohort < COHORT_MIN
            else ("PASS" if d1 is not None and d1 >= D1_THRESHOLD else "FAIL")
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="/app/data/user/chat_history.db")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from deeptutor.services.member_console.service import get_member_console_service

    excluded = get_member_console_service().list_internal_test_user_ids()
    days = load_activity(args.db)
    report = compute_d1(days, excluded, today=datetime.date.today())
    report["allowlist_size"] = len(excluded)
    report["total_owner_keys"] = len(days)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for key, value in report.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
