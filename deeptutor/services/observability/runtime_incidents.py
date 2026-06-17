from __future__ import annotations

import re
from typing import Any

_TIMESTAMP_PATTERN = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_SUPABASE_PRIMARY_PLAN_PATTERN = re.compile(
    r"\[SupabasePipeline\].*Supabase retrieval failed: .*primary plan exploded",
    re.IGNORECASE,
)
_SUPABASE_GROUP_WARNING_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*"
    r"\[SupabasePipeline\].*Supabase group '(?P<group>[^']+)' failed for query '(?P<query>[^']+)': (?P<reason>.+)$"
)


def _line_timestamp(line: str) -> str:
    match = _TIMESTAMP_PATTERN.match(str(line or ""))
    return str(match.group("timestamp") if match else "").strip()


def classify_runtime_incidents_from_backend_logs(backend_logs: dict[str, Any] | None) -> list[dict[str, Any]]:
    payload = backend_logs if isinstance(backend_logs, dict) else {}
    error_samples = [str(item) for item in payload.get("error_samples") or [] if str(item).strip()]
    warning_samples = [str(item) for item in payload.get("warning_samples") or [] if str(item).strip()]
    incidents: list[dict[str, Any]] = []

    warning_by_timestamp: dict[str, list[dict[str, str]]] = {}
    for line in warning_samples:
        match = _SUPABASE_GROUP_WARNING_PATTERN.match(line)
        if not match:
            continue
        timestamp = str(match.group("timestamp") or "").strip()
        warning_by_timestamp.setdefault(timestamp, []).append(
            {
                "group_name": str(match.group("group") or "").strip(),
                "query": str(match.group("query") or "").strip(),
                "reason": str(match.group("reason") or "").strip(),
                "sample": line,
            }
        )

    primary_plan_errors = [line for line in error_samples if _SUPABASE_PRIMARY_PLAN_PATTERN.search(line)]
    if primary_plan_errors:
        timestamps = [_line_timestamp(line) for line in primary_plan_errors if _line_timestamp(line)]
        related_warnings: list[dict[str, str]] = []
        for timestamp in timestamps:
            related_warnings.extend(warning_by_timestamp.get(timestamp, []))
        query_samples = sorted(
            {
                str(item.get("query") or "").strip()
                for item in related_warnings
                if str(item.get("query") or "").strip()
            }
        )
        related_groups = sorted(
            {
                str(item.get("group_name") or "").strip()
                for item in related_warnings
                if str(item.get("group_name") or "").strip()
            }
        )
        warning_reasons = sorted(
            {
                str(item.get("reason") or "").strip()
                for item in related_warnings
                if str(item.get("reason") or "").strip()
            }
        )
        incidents.append(
            {
                "incident_type": "supabase_primary_plan_exploded",
                "component": "rag.supabase_pipeline",
                "severity": "high",
                "release_blocking": True,
                "failure_taxonomy_hint": "FAIL_GROUNDEDNESS",
                "summary": "SupabasePipeline primary plan 在 retrieval 主链路爆炸，当前 release 的 grounding 结果不可信。",
                "repeat_count": len(primary_plan_errors),
                "first_seen": timestamps[0] if timestamps else "",
                "last_seen": timestamps[-1] if timestamps else "",
                "query_samples": query_samples,
                "related_source_groups": related_groups,
                "warning_reasons": warning_reasons,
                "evidence_samples": primary_plan_errors[:3],
                "warning_samples": [item.get("sample", "") for item in related_warnings[:3]],
                "signature": "SupabasePipeline:primary_plan_exploded",
                "benchmark_projection": {
                    "case_id": "runtime.supabase.primary_plan_exploded",
                    "recommended_tier": "incident_replay",
                    "contract_domain": "grounding_contract",
                },
            }
        )

    return incidents
