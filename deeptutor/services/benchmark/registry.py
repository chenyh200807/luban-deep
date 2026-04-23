"""Benchmark registry loading helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import BenchmarkRegistry


def load_benchmark_registry(path: str | Path) -> BenchmarkRegistry:
    """Load a benchmark registry from JSON."""

    registry_path = Path(path)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("benchmark registry JSON must be an object")
    return BenchmarkRegistry.from_dict(payload)


def dump_benchmark_registry(registry: BenchmarkRegistry) -> dict[str, Any]:
    """Serialize a registry back to plain JSON-compatible data."""

    return {
        "version": registry.version,
        "dataset_id": registry.dataset_id,
        "dataset_version": registry.dataset_version,
        "cases": {
            case_id: {
                "dataset_id": case.dataset_id,
                "dataset_version": case.dataset_version,
                "case_id": case.case_id,
                "contract_domain": case.contract_domain,
                "case_tier": case.case_tier,
                "execution_kind": case.execution_kind,
                "surface": case.surface,
                "expected_contract": case.expected_contract,
                "failure_taxonomy_scope": list(case.failure_taxonomy_scope),
                "source_fixture": case.source_fixture,
                "origin_type": case.origin_type,
                "origin_ref": case.origin_ref,
                "promotion_status": case.promotion_status,
                "promoted_from_case_id": case.promoted_from_case_id,
            }
            for case_id, case in registry.cases.items()
        },
        "suites": {
            suite_name: {"case_ids": list(suite.case_ids)}
            for suite_name, suite in registry.suites.items()
        },
    }
