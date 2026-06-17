"""CLI 入口：live / offline 双模式。

live 模式凭据全部来自环境变量；缺哪个源就跳过并在报告标 missing_source，
不硬失败——部分证据好过零证据。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.bi_reconciliation.bi_api_source import (
    extract_bi_readings,
    fetch_bi_payloads,
    find_unregistered_labels,
)
from scripts.bi_reconciliation.business_source import (
    behavior_readings_from_db,
    member_readings_from_supabase,
)
from scripts.bi_reconciliation.engine import reconcile_metric
from scripts.bi_reconciliation.langfuse_source import (
    fetch_daily_metrics,
    readings_from_daily_metrics,
)
from scripts.bi_reconciliation.mapping import METRIC_MAPPINGS
from scripts.bi_reconciliation.report import (
    build_metric_dictionary,
    build_report,
    render_markdown,
)
from scripts.bi_reconciliation.types import SourceReading


def _reconcile_and_write(
    readings: list[SourceReading],
    unregistered_labels: list[str],
    *,
    out_root: Path,
    window_days: int,
    generated_at: str,
) -> Path:
    by_metric: dict[str, list[SourceReading]] = {}
    for r in readings:
        by_metric.setdefault(r.metric_id, []).append(r)
    verdicts = [
        reconcile_metric(m, by_metric.get(m.metric_id, [])) for m in METRIC_MAPPINGS
    ]
    report = build_report(
        verdicts,
        window_days=window_days,
        generated_at=generated_at,
        unregistered_labels=unregistered_labels,
    )
    date_tag = generated_at[:10].replace("-", "")
    out_dir = out_root / f"bi_reconciliation_{date_tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reconciliation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out_dir / "reconciliation_report.md").write_text(render_markdown(report), encoding="utf-8")
    (out_dir / "metric_dictionary.json").write_text(
        json.dumps(build_metric_dictionary(), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return out_dir


def run_offline(
    *, fixtures_dir: Path, out_root: Path, window_days: int, generated_at: str
) -> Path:
    payloads: dict[str, Any] = {}
    for ep in ("overview", "cost", "members", "anomalies"):
        path = fixtures_dir / f"bi_{ep}.json"
        if path.exists():
            payloads[ep] = json.loads(path.read_text())
    readings = extract_bi_readings(payloads, window_days)
    daily_path = fixtures_dir / "langfuse_daily.json"
    if daily_path.exists():
        readings += readings_from_daily_metrics(json.loads(daily_path.read_text()), window_days)
    return _reconcile_and_write(
        readings,
        find_unregistered_labels(payloads),
        out_root=out_root,
        window_days=window_days,
        generated_at=generated_at,
    )


def run_live(*, bi_base_url: str, out_root: Path, window_days: int) -> Path:
    generated_at = datetime.now(timezone.utc).isoformat()
    readings: list[SourceReading] = []
    payloads: dict[str, Any] = {}

    metrics_token = os.getenv("DEEPTUTOR_METRICS_TOKEN", "").strip()
    if metrics_token:
        payloads = fetch_bi_payloads(bi_base_url, metrics_token, window_days)
        readings += extract_bi_readings(payloads, window_days)
    else:
        print("[skip] DEEPTUTOR_METRICS_TOKEN 未设置——跳过 BI API 源", file=sys.stderr)

    lf_host = (os.getenv("LANGFUSE_RECON_URL") or os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST") or "").strip()
    lf_pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    lf_sk = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    if lf_host and lf_pk and lf_sk:
        daily = fetch_daily_metrics(lf_host, lf_pk, lf_sk, window_days)
        readings += readings_from_daily_metrics(daily, window_days)
    else:
        print("[skip] LANGFUSE_* 配置不全——跳过 Langfuse 源", file=sys.stderr)

    behavior_db = os.getenv("BI_RECON_BEHAVIOR_DB", "").strip()
    if behavior_db and Path(behavior_db).exists():
        conn = sqlite3.connect(f"file:{behavior_db}?mode=ro", uri=True)
        try:
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            readings += behavior_readings_from_db(conn, window_days, now_ms)
        finally:
            conn.close()
    else:
        print("[skip] BI_RECON_BEHAVIOR_DB 未设置或不存在——跳过行为库源", file=sys.stderr)

    sb_url = os.getenv("SUPABASE_URL", "").strip()
    sb_key = os.getenv("SUPABASE_KEY", "").strip() or os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if sb_url and sb_key:
        readings += member_readings_from_supabase(sb_url, sb_key, window_days)
    else:
        print("[skip] SUPABASE_URL/KEY 未设置——跳过会员源", file=sys.stderr)

    return _reconcile_and_write(
        readings,
        find_unregistered_labels(payloads),
        out_root=out_root,
        window_days=window_days,
        generated_at=generated_at,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BI 三源对账 harness（只读）")
    parser.add_argument("--mode", choices=("live", "offline"), default="live")
    parser.add_argument("--bi-base-url", default="https://test2.yousenjiaoyu.com")
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--out", default="artifacts")
    parser.add_argument("--fixtures-dir", default="tests/scripts/bi_reconciliation/fixtures")
    args = parser.parse_args(argv)
    if args.mode == "offline":
        out_dir = run_offline(
            fixtures_dir=Path(args.fixtures_dir),
            out_root=Path(args.out),
            window_days=args.window_days,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    else:
        out_dir = run_live(
            bi_base_url=args.bi_base_url,
            out_root=Path(args.out),
            window_days=args.window_days,
        )
    print(f"报告已写入: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
