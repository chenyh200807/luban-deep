"""取数器②：Langfuse Public API（basic auth，只读）。

langfuse_adapter.py 只有写入能力，对账走 /api/public/metrics/daily。
派生指标（success_turn_rate / cost_per_effective_learning）在 Langfuse 侧
只给分量，engine 对其按 missing/分量记录，不假装等值可比。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from scripts.bi_reconciliation.mapping import METRIC_MAPPINGS
from scripts.bi_reconciliation.types import SOURCE_LANGFUSE, SourceReading


def fetch_daily_metrics(
    host: str, public_key: str, secret_key: str, window_days: int
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    params = {
        "fromTimestamp": (now - timedelta(days=window_days)).isoformat(),
        "toTimestamp": now.isoformat(),
        "limit": "100",
    }
    # trust_env=False: 不读系统代理，内网/SSH 隧道地址经代理会 503（同 LANGFUSE_HTTPX_TRUST_ENV 的教训）
    with httpx.Client(auth=(public_key, secret_key), timeout=30, trust_env=False) as client:
        resp = client.get(f"{host.rstrip('/')}/api/public/metrics/daily", params=params)
        resp.raise_for_status()
        return resp.json()


def readings_from_daily_metrics(daily: dict[str, Any], window_days: int) -> list[SourceReading]:
    rows = list(daily.get("data") or [])
    by_kind: dict[str, float | None]
    if rows:
        by_kind = {
            "daily_cost": sum(float(r.get("totalCost") or 0) for r in rows),
            "daily_traces": float(sum(int(r.get("countTraces") or 0) for r in rows)),
            "daily_observations": float(sum(int(r.get("countObservations") or 0) for r in rows)),
        }
    else:
        by_kind = {"daily_cost": None, "daily_traces": None, "daily_observations": None}
    readings: list[SourceReading] = []
    for m in METRIC_MAPPINGS:
        if not m.langfuse_kind:
            continue
        value = by_kind.get(m.langfuse_kind)
        meta: dict[str, Any] = {"kind": m.langfuse_kind, "days": len(rows)}
        if value is None:
            meta["reason"] = "no_daily_rows"
        readings.append(SourceReading(m.metric_id, SOURCE_LANGFUSE, value, window_days, meta))
    return readings
