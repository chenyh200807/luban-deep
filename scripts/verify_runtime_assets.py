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
    compose_ghcr_path = repo_root / "docker-compose.ghcr.yml"
    dockerfile_path = repo_root / "Dockerfile"
    scrape_path = repo_root / "deployment" / "observability" / "prometheus.scrape.example.yml"
    alerts_path = repo_root / "deployment" / "observability" / "prometheus.alerts.example.yml"
    alerts_test_path = repo_root / "deployment" / "observability" / "prometheus.alerts.test.yml"
    alertmanager_path = repo_root / "deployment" / "observability" / "alertmanager.yml"
    backup_doc = repo_root / "docs" / "zh" / "guide" / "runtime-backup-restore.md"
    observability_doc = repo_root / "docs" / "zh" / "guide" / "runtime-observability.md"

    # The image serves backend and frontend from one container. Health must represent
    # both processes, otherwise a healthy backend can mask a crashed frontend.
    for compose_target in (compose_path, compose_ghcr_path):
        if not compose_target.exists():
            errors.append(f"missing compose file: {compose_target}")
            continue
        try:
            compose = _load_yaml(compose_target)
            deeptutor = (compose.get("services") or {}).get("deeptutor") or {}
            healthcheck = deeptutor.get("healthcheck") or {}
            test_command = healthcheck.get("test") or []
            flat_command = (
                " ".join(test_command) if isinstance(test_command, list) else str(test_command)
            )
            if "/readyz" not in flat_command:
                errors.append(f"{compose_target.name} healthcheck must probe /readyz")
            if "FRONTEND_PORT" not in flat_command:
                errors.append(f"{compose_target.name} healthcheck must probe the frontend")
        except Exception as exc:
            errors.append(f"failed to parse {compose_target.name}: {exc}")

    if not dockerfile_path.exists():
        errors.append(f"missing Dockerfile: {dockerfile_path}")
    else:
        try:
            dockerfile_text = _load_text(dockerfile_path)
            healthcheck_marker = "HEALTHCHECK "
            healthcheck_start = dockerfile_text.find(healthcheck_marker)
            healthcheck_block = (
                dockerfile_text[healthcheck_start:].split("\n\n", 1)[0]
                if healthcheck_start >= 0
                else ""
            )
            if not healthcheck_block:
                errors.append("Dockerfile HEALTHCHECK CMD curl line not found")
            elif "/readyz" not in healthcheck_block:
                errors.append("Dockerfile HEALTHCHECK must probe /readyz")
            if "FRONTEND_PORT" not in healthcheck_block:
                errors.append("Dockerfile HEALTHCHECK must probe the frontend")
            runtime_readability_block = next(
                (
                    line
                    for line in dockerfile_text.splitlines()
                    if line.startswith("RUN chmod -R a+rX ")
                ),
                "",
            )
            if "/app/web/public" not in runtime_readability_block:
                errors.append("Dockerfile must make web/public readable by the runtime user")
        except Exception as exc:
            errors.append(f"failed to parse Dockerfile: {exc}")

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
                authorization = job.get("authorization") or {}
                if str(authorization.get("type") or "").lower() != "bearer":
                    errors.append("deeptutor scrape job must use bearer authorization")
                credentials = str(authorization.get("credentials") or "")
                if "${DEEPTUTOR_METRICS_TOKEN}" not in credentials:
                    errors.append("deeptutor scrape job must reference ${DEEPTUTOR_METRICS_TOKEN}")
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
                # Self-monitoring + watch-the-watcher: register so they cannot silently vanish.
                "DeepTutorMetricsScrapeDown": 'up{job="deeptutor"}',
                "AlertmanagerDown": 'up{job="alertmanager"}',
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

    # The promtool behavioral test file must exist (CI runs `promtool test rules` on it).
    if not alerts_test_path.exists():
        errors.append(f"missing prometheus alerts test (promtool): {alerts_test_path}")

    # Alertmanager config was previously validated nowhere. Structurally validate it so a
    # malformed route/receiver is caught in CI (delivery placeholders are intentional and are
    # surfaced as a runtime WARN by verify_aliyun_observability_stack.sh, not failed here).
    if not alertmanager_path.exists():
        errors.append(f"missing alertmanager config: {alertmanager_path}")
    else:
        try:
            am = _load_yaml(alertmanager_path) or {}
            route = am.get("route") or {}
            receivers = am.get("receivers") or []
            receiver_names = {str(r.get("name")) for r in receivers if isinstance(r, dict)}
            default_receiver = route.get("receiver")
            if not default_receiver:
                errors.append("alertmanager.yml route must define a default receiver")
            elif str(default_receiver) not in receiver_names:
                errors.append(
                    f"alertmanager.yml route.receiver {default_receiver!r} not in receivers {sorted(receiver_names)}"
                )
            for sub in route.get("routes") or []:
                sub_recv = sub.get("receiver") if isinstance(sub, dict) else None
                if sub_recv and str(sub_recv) not in receiver_names:
                    errors.append(f"alertmanager.yml sub-route receiver {sub_recv!r} not in receivers")
        except Exception as exc:
            errors.append(f"failed to parse alertmanager config: {exc}")

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
                "DEEPTUTOR_METRICS_TOKEN",
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
