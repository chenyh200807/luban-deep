#!/usr/bin/env python
"""Verify runtime backup and observability assets stay internally consistent."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _contains_all(text: str, needles: list[str]) -> list[str]:
    return [needle for needle in needles if needle not in text]


def validate_runtime_assets(repo_root: Path) -> list[str]:
    errors: list[str] = []

    compose_path = repo_root / "docker-compose.yml"
    scrape_path = repo_root / "deployment" / "observability" / "prometheus.scrape.example.yml"
    alerts_path = repo_root / "deployment" / "observability" / "prometheus.alerts.example.yml"
    backup_doc = repo_root / "docs" / "zh" / "guide" / "runtime-backup-restore.md"
    observability_doc = repo_root / "docs" / "zh" / "guide" / "runtime-observability.md"

    if not compose_path.exists():
        errors.append(f"missing compose file: {compose_path}")
    else:
        try:
            compose = _load_yaml(compose_path)
            deeptutor = (compose.get("services") or {}).get("deeptutor") or {}
            healthcheck = deeptutor.get("healthcheck") or {}
            test_command = healthcheck.get("test") or []
            flat_command = " ".join(test_command) if isinstance(test_command, list) else str(test_command)
            if "/readyz" not in flat_command:
                errors.append("docker-compose.yml healthcheck must probe /readyz")
        except Exception as exc:
            errors.append(f"failed to parse docker-compose.yml: {exc}")

    if not scrape_path.exists():
        errors.append(f"missing prometheus scrape example: {scrape_path}")
    else:
        try:
            scrape = _load_yaml(scrape_path)
            scrape_configs = scrape.get("scrape_configs") or []
            deeptutor_jobs = [job for job in scrape_configs if job.get("job_name") == "deeptutor"]
            if not deeptutor_jobs:
                errors.append("prometheus scrape example must define a deeptutor job")
            else:
                job = deeptutor_jobs[0]
                if job.get("metrics_path") != "/metrics/prometheus":
                    errors.append("deeptutor scrape job must use /metrics/prometheus")
                if not job.get("static_configs"):
                    errors.append("deeptutor scrape job must define static_configs")
        except Exception as exc:
            errors.append(f"failed to parse prometheus scrape example: {exc}")

    if not alerts_path.exists():
        errors.append(f"missing prometheus alerts example: {alerts_path}")
    else:
        try:
            alerts = _load_yaml(alerts_path)
            groups = alerts.get("groups") or []
            alerts_by_name: dict[str, dict[str, Any]] = {}
            for group in groups:
                for rule in group.get("rules") or []:
                    alert_name = rule.get("alert")
                    if alert_name:
                        alerts_by_name[str(alert_name)] = rule

            required_alerts = {
                "DeepTutorNotReady": "deeptutor_ready",
                "DeepTutorServerErrors": "deeptutor_http_errors_total",
                "DeepTutorProviderThresholdExceeded": "deeptutor_provider_threshold_exceeded",
                "DeepTutorCircuitBreakerOpen": "deeptutor_circuit_breaker_open",
            }
            for alert_name, metric_name in required_alerts.items():
                rule = alerts_by_name.get(alert_name)
                if rule is None:
                    errors.append(f"missing alert rule: {alert_name}")
                    continue
                expr = str(rule.get("expr") or "")
                if metric_name not in expr:
                    errors.append(f"alert {alert_name} must reference {metric_name}")
        except Exception as exc:
            errors.append(f"failed to parse prometheus alerts example: {exc}")

    if not backup_doc.exists():
        errors.append(f"missing backup runbook: {backup_doc}")
    else:
        backup_text = _load_text(backup_doc)
        missing = _contains_all(
            backup_text,
            [
                "scripts/backup_data.py",
                "scripts/restore_data.py",
                "--keep",
                "--replace",
                "data/backups",
            ],
        )
        for needle in missing:
            errors.append(f"backup runbook must mention {needle}")

    if not observability_doc.exists():
        errors.append(f"missing observability guide: {observability_doc}")
    else:
        observability_text = _load_text(observability_doc)
        missing = _contains_all(
            observability_text,
            [
                "/healthz",
                "/readyz",
                "/metrics/prometheus",
                "prometheus.scrape.example.yml",
                "prometheus.alerts.example.yml",
                ".github/workflows/runtime-ops.yml",
            ],
        )
        for needle in missing:
            errors.append(f"observability guide must mention {needle}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate runtime backup and observability assets")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root to inspect")
    args = parser.parse_args(argv)

    errors = validate_runtime_assets(args.repo_root.resolve())
    if errors:
        print("Runtime asset validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Runtime asset validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
