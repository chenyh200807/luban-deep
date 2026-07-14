from __future__ import annotations

import re
from pathlib import Path

import yaml

import scripts.verify_runtime_assets as runtime_assets
from scripts.verify_runtime_assets import validate_runtime_assets


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OBSERVABILITY_DIR = PROJECT_ROOT / "deployment" / "observability"
OBSERVABILITY_COMPOSE = OBSERVABILITY_DIR / "docker-compose.observability.yml"
SYNC_SCRIPT = PROJECT_ROOT / "scripts" / "sync_to_aliyun.sh"


def test_runtime_assets_remain_self_consistent() -> None:
    errors = validate_runtime_assets(PROJECT_ROOT)
    assert errors == []


def test_runtime_assets_reject_unreadable_public_assets(monkeypatch) -> None:
    original_load_text = runtime_assets._load_text

    def load_text_without_public_permission(path: Path) -> str:
        text = original_load_text(path)
        if path.name == "Dockerfile":
            return "\n".join(
                line.replace(" /app/web/public", "")
                if line.startswith("RUN chmod -R a+rX ")
                else line
                for line in text.splitlines()
            )
        return text

    monkeypatch.setattr(runtime_assets, "_load_text", load_text_without_public_permission)
    errors = runtime_assets.validate_runtime_assets(PROJECT_ROOT)
    assert "Dockerfile must make web/public readable by the runtime user" in errors


def test_runtime_assets_reject_backend_only_docker_healthcheck(monkeypatch) -> None:
    original_load_text = runtime_assets._load_text

    def load_text_without_frontend_health(path: Path) -> str:
        text = original_load_text(path)
        if path.name == "Dockerfile":
            start = text.index("HEALTHCHECK ")
            end = text.index("\n\n", start)
            healthcheck = text[start:end].replace("FRONTEND_PORT", "OMITTED_PORT")
            return text[:start] + healthcheck + text[end:]
        return text

    monkeypatch.setattr(runtime_assets, "_load_text", load_text_without_frontend_health)
    errors = runtime_assets.validate_runtime_assets(PROJECT_ROOT)
    assert "Dockerfile HEALTHCHECK must probe the frontend" in errors


def _observability_secret_mount_sources() -> list[str]:
    """Host source paths of every secret bind-mount in the observability compose
    (mounts whose container target sits under /etc/<svc>/secrets/)."""
    compose = yaml.safe_load(OBSERVABILITY_COMPOSE.read_text(encoding="utf-8"))
    sources: list[str] = []
    for service in (compose.get("services") or {}).values():
        for mount in service.get("volumes") or []:
            if not isinstance(mount, str):
                continue
            source, _, target = mount.partition(":")
            if "/secrets/" in target:
                sources.append(source)
    return sources


def test_observability_secrets_live_in_sync_excluded_data_dir() -> None:
    """Regression guard for the secret-wiped-by-sync footgun.

    `sync_to_aliyun.sh` runs `rsync --delete`; any host file not present in the clean
    checkout under a synced path is deleted on every full release. The observability
    secret files (prometheus metrics_token / alertmanager smtp_password) must therefore
    live under `data/` — the one tree `sync_to_aliyun.sh` excludes — and NOT under the
    synced `deployment/observability/secrets/` tree, or a routine deploy silently wipes
    the scrape token and breaks metrics auth on the next container recreate.
    """
    sources = _observability_secret_mount_sources()
    assert sources, "expected at least one secret bind-mount in the observability compose"

    data_root = (PROJECT_ROOT / "data").resolve()
    for source in sources:
        resolved = (OBSERVABILITY_DIR / source).resolve()
        assert data_root in resolved.parents, (
            f"observability secret mount {source!r} resolves to {resolved}, which is NOT "
            f"under the sync-excluded data/ tree — a full sync_to_aliyun.sh would delete it"
        )
        assert "deployment/observability/secrets" not in source, (
            f"secret mount {source!r} sits in the synced+deletable config tree"
        )


def test_sync_script_excludes_data_dir() -> None:
    """The durability guarantee above only holds if `sync_to_aliyun.sh` actually excludes
    `data/` from its rsync. Lock that other half of the invariant too: if someone drops
    `data` from EXCLUDES, the secret-in-data placement stops protecting anything."""
    text = SYNC_SCRIPT.read_text(encoding="utf-8")
    excludes_block = re.search(r"EXCLUDES=\((.*?)\)", text, re.S)
    assert excludes_block, "could not locate EXCLUDES array in sync_to_aliyun.sh"
    assert re.search(r'^\s*"data"\s*$', excludes_block.group(1), re.M), (
        "sync_to_aliyun.sh EXCLUDES must contain a bare \"data\" entry so the durable "
        "data/ tree (incl. observability secrets) is never rsync --delete'd"
    )
