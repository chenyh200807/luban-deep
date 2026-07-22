#!/usr/bin/env bash
#
# Re-runnable health check for the DeepTutor observability SIDECAR stack
# (Prometheus + Alertmanager from deployment/observability/docker-compose.observability.yml).
#
# This is the replayable artifact that replaces one-time manual curl verification (gap 3).
# It is SEPARATE from scripts/verify_aliyun_observability.sh on purpose: that one is an
# app-release gate (deeptutor's own /metrics); this one targets the opt-in sidecar and must
# NOT be wired into app release (or the app deploy would go red whenever the sidecar is down).
#
# All checks are read-only, over SSH to the host, against 127.0.0.1 (sidecar ports are
# loopback-only). Hard failures exit 1; soft conditions print WARN and do not fail.
# The Python script is fed to the remote python3 via stdin (single-quoted heredoc), so it
# may use any quoting freely.
#
#   bash scripts/verify_aliyun_observability_stack.sh

set -Eeuo pipefail

REMOTE_HOST="${REMOTE_HOST:-Aliyun-ECS-2}"
REMOTE_DIR="${REMOTE_DIR:-/root/deeptutor}"
PROM_PORT="${PROM_PORT:-9090}"
ALERTMANAGER_PORT="${ALERTMANAGER_PORT:-9093}"
STALENESS_SECONDS="${STALENESS_SECONDS:-60}"

ssh "${REMOTE_HOST}" \
    "PYTHONIOENCODING='utf-8' REMOTE_DIR='${REMOTE_DIR}' PROM_PORT='${PROM_PORT}' ALERTMANAGER_PORT='${ALERTMANAGER_PORT}' STALENESS_SECONDS='${STALENESS_SECONDS}' python3 -" <<'PY'
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

remote_dir = Path(os.environ["REMOTE_DIR"])
prom = f"http://127.0.0.1:{os.environ.get('PROM_PORT', '9090').strip()}"
am = f"http://127.0.0.1:{os.environ.get('ALERTMANAGER_PORT', '9093').strip()}"
staleness = float(os.environ.get("STALENESS_SECONDS", "60") or "60")

# NOTE: no variable annotations — the production host runs python 3.6.8, where PEP 585
# `list[str]` is not subscriptable at runtime and `from __future__ import annotations`
# is unavailable. Keep this script 3.6-compatible (matches verify_aliyun_observability.sh).
errors = []
warnings = []
oks = []

EXPECTED_RULES = {
    "DeepTutorNotReady", "DeepTutorServerErrors", "DeepTutorProviderThresholdExceeded",
    "DeepTutorCircuitBreakerOpen", "DeepTutorBillingCaptureError",
    "DeepTutorBillingEnforcementDisabled", "DeepTutorBillingContextIncomplete",
    "DeepTutorChargeableTurnNotCaptured", "DeepTutorBillingCounterReset",
    "DeepTutorNonChargeableCaptured", "DeepTutorSuspiciousWalletCredit",
    "DeepTutorWalletCounterReset",
    "DeepTutorMetricsScrapeDown", "AlertmanagerDown",
}


def _get(url, timeout=8):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8")


def _get_json(url, timeout=8):
    _status, body = _get(url, timeout)
    return json.loads(body)


def _query_value(expr):
    q = urllib.parse.quote(expr)
    data = _get_json(f"{prom}/api/v1/query?query={q}")
    result = data.get("data", {}).get("result", [])
    return result[0]["value"][1] if result else None


def check(label, fn):
    try:
        fn()
    except Exception as exc:  # report every check, never abort early
        errors.append(f"{label}: {exc}")


def _prom_health():
    assert _get(f"{prom}/-/healthy")[0] == 200, "/-/healthy not 200"
    assert _get(f"{prom}/-/ready")[0] == 200, "/-/ready not 200"
    oks.append("Prometheus healthy + ready")
check("Prometheus health", _prom_health)


def _deeptutor_up():
    # End-to-end: proves network + that the mounted metrics_token byte-matches the app .env
    # token (on drift the scrape 403s and up==0 here).
    value = _query_value('up{job="deeptutor"}')
    assert value is not None, 'no up{job="deeptutor"} series (target never scraped?)'
    assert value == "1", f"up{{job=deeptutor}}={value} (scrape failing — token byte-match / network)"
    oks.append("deeptutor scrape target up==1 (scrape + token auth OK)")
check("deeptutor target up", _deeptutor_up)


def _deeptutor_no_error():
    data = _get_json(f"{prom}/api/v1/targets")
    dt = [t for t in data.get("data", {}).get("activeTargets", [])
          if t.get("labels", {}).get("job") == "deeptutor"]
    assert dt, "deeptutor not in activeTargets"
    assert dt[0].get("lastError", "") == "", f"deeptutor lastError={dt[0].get('lastError')!r}"
    oks.append("deeptutor target lastError empty")
check("deeptutor target error-free", _deeptutor_no_error)


def _prom_self():
    assert _query_value('up{job="prometheus"}') == "1", "prometheus self-scrape not up"
    oks.append("prometheus self-monitor up")
check("prometheus self-monitor", _prom_self)


def _rules():
    data = _get_json(f"{prom}/api/v1/rules")
    rules = [r for g in data.get("data", {}).get("groups", [])
             for r in g.get("rules", []) if r.get("type") == "alerting"]
    names = {r.get("name") for r in rules}
    missing = EXPECTED_RULES - names
    assert not missing, f"missing alert rules: {sorted(missing)}"
    unhealthy = [r.get("name") for r in rules if r.get("health") not in (None, "ok")]
    assert not unhealthy, f"unhealthy rules: {unhealthy}"
    oks.append(f"{len(EXPECTED_RULES)} alert rules loaded and healthy")
check("alert rules", _rules)


def _am_health():
    assert _get(f"{am}/-/ready")[0] == 200, "AM /-/ready not 200"
    oks.append("Alertmanager ready")
check("Alertmanager ready", _am_health)


def _am_up():
    assert _query_value('up{job="alertmanager"}') == "1", "alertmanager scrape job not up"
    oks.append("alertmanager scrape job up")
check("alertmanager scrape", _am_up)


def _am_connected():
    data = _get_json(f"{prom}/api/v1/alertmanagers")
    active = data.get("data", {}).get("activeAlertmanagers", [])
    dropped = data.get("data", {}).get("droppedAlertmanagers", [])
    assert active, "no active Alertmanager connected to Prometheus"
    assert not dropped, f"dropped Alertmanagers: {dropped}"
    oks.append("Prometheus->Alertmanager delivery path connected")
check("AM delivery path", _am_connected)


def _worker_metrics():
    # The only production-side signal that the Step 2 dump loop is live (and thus that the
    # multiworker merge is actually happening). Uses embedded ts (same source as merge
    # staleness), not mtime.
    wm_dir = remote_dir / "data" / "runtime" / "observability" / "worker_metrics"
    if not wm_dir.is_dir():
        raise AssertionError(f"{wm_dir} missing (Step 2 not deployed yet, or dump loop never ran)")
    now = time.time()
    fresh = []
    for p in wm_dir.glob("worker-*.json"):
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict) and (now - float(payload.get("ts", 0.0))) < staleness:
            fresh.append(payload.get("pid"))
    assert fresh, f"no fresh worker_metrics files (<{int(staleness)}s) — dump loop not running"
    oks.append(f"{len(fresh)} fresh worker_metrics file(s) (dump loop live)")
    env_path = remote_dir / ".env"
    workers = 1
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("UVICORN_WORKERS=") and "=" in s:
                try:
                    workers = int(s.split("=", 1)[1].strip() or "1")
                except ValueError:
                    workers = 1
    if len(fresh) != workers:
        warnings.append(f"fresh worker_metrics files={len(fresh)} but UVICORN_WORKERS={workers} "
                        f"(a worker dump loop may have died — silent undercount)")
check("worker_metrics freshness", _worker_metrics)


def _delivery_configured():
    # Honest gate: never let green read as "we get paged" while delivery is placeholder.
    am_cfg = remote_dir / "deployment" / "observability" / "alertmanager.yml"
    if am_cfg.exists() and "example.com" in am_cfg.read_text(encoding="utf-8"):
        warnings.append("ALERT DELIVERY NOT CONFIGURED: alertmanager.yml still has example.com "
                        "placeholders — rules compute and show in the UI, but NO notifications are "
                        "delivered. Do not report 'alerting live'.")
    else:
        oks.append("alertmanager delivery config has no example.com placeholders")
check("delivery configured", _delivery_configured)


print("=== observability stack health ===")
for o in oks:
    print(f"  OK   {o}")
for w in warnings:
    print(f"  WARN {w}")
for e in errors:
    print(f"  FAIL {e}")
print(f"=== {len(oks)} ok / {len(warnings)} warn / {len(errors)} fail ===")
raise SystemExit(1 if errors else 0)
PY
