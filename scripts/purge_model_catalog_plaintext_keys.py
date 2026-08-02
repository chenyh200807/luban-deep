#!/usr/bin/env python3
"""Replace plaintext API keys in an existing model_catalog.json with [REDACTED].

WHY THIS EXISTS
    `model_catalog.py` used to redact only when
    DEEPTUTOR_REDACT_MODEL_CATALOG_API_KEYS_AT_REST was set, so an unset variable
    persisted live provider keys in plaintext. Redaction is now the default, but
    that only fixes FUTURE writes — a catalog file written before the fix still
    holds the plaintext key until something rewrites it. This script closes that
    gap in one shot.

THE RULE THIS ENFORCES
    A key is only redacted if the SAME value is still reachable from the
    environment. Redacting a key that the environment cannot supply would leave
    it nowhere — the file was the last copy. When that happens the script
    refuses and tells you which profile is at risk.

SAFETY
    - Read-only by default. Prints a plan and exits; nothing is written.
    - `--apply` is required to modify the file, and it takes a timestamped
      backup (mode 0600) next to the original first.
    - Never prints a key value. Only name, first 4 characters and length.
    - Exit codes: 0 = clean or applied, 2 = refused (unrecoverable key),
      3 = usage/IO error.

USAGE
    python3 scripts/purge_model_catalog_plaintext_keys.py            # dry run
    python3 scripts/purge_model_catalog_plaintext_keys.py --apply
    python3 scripts/purge_model_catalog_plaintext_keys.py --path /app/data/user/settings/model_catalog.json
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REDACTED_SECRET = "[REDACTED]"
CATALOG_FILE_MODE = 0o600

# Which env var backs each service's active profile. Mirrors
# EnvStore.render_from_catalog / _sync_active_services_from_env.
SERVICE_ENV_KEYS = {
    "llm": "LLM_API_KEY",
    "embedding": "EMBEDDING_API_KEY",
    "search": "SEARCH_API_KEY",
}


def _mask(value: str) -> str:
    """Render a secret as prefix + length. Never returns the full value."""

    if not value:
        return "<empty>"
    return f"{value[:4]}… (len={len(value)})"


def _env_values() -> dict[str, str]:
    """Every value the environment can currently supply, via EnvStore + os.environ."""

    values: dict[str, str] = {}
    try:
        from deeptutor.services.config.env_store import get_env_store

        values.update({k: str(v) for k, v in get_env_store().load().items()})
    except Exception as exc:  # pragma: no cover - defensive, env_store is optional here
        print(f"  ! could not load EnvStore ({exc}); falling back to os.environ only")
    for key in SERVICE_ENV_KEYS.values():
        env_value = os.environ.get(key)
        if env_value and not values.get(key):
            values[key] = env_value
    return values


def _iter_profiles(catalog: dict[str, Any]):
    """Yield (service_name, profile, is_active) for every profile in the catalog."""

    services = catalog.get("services", {})
    if not isinstance(services, dict):
        return
    for service_name, service in services.items():
        if not isinstance(service, dict):
            continue
        active_id = str(service.get("active_profile_id") or "")
        profiles = service.get("profiles")
        if not isinstance(profiles, list):
            continue
        for profile in profiles:
            if isinstance(profile, dict):
                yield service_name, profile, str(profile.get("id") or "") == active_id


def plan_purge(catalog: dict[str, Any], env: dict[str, str]) -> tuple[list, list]:
    """Split plaintext keys into (recoverable, unrecoverable).

    Recoverable = the environment holds the identical value, so redacting the
    file loses nothing. Unrecoverable = the file is the last copy.
    """

    recoverable: list[tuple[str, str, str]] = []
    unrecoverable: list[tuple[str, str, str]] = []
    for service_name, profile, is_active in _iter_profiles(catalog):
        api_key = str(profile.get("api_key") or "").strip()
        if not api_key or api_key == REDACTED_SECRET:
            continue
        profile_id = str(profile.get("id") or "<no-id>")
        env_key = SERVICE_ENV_KEYS.get(service_name, "")
        env_value = env.get(env_key, "") if env_key else ""
        # Only the ACTIVE profile is re-hydrated from env on load; a non-active
        # profile is never refilled even if the value happens to match.
        if is_active and env_value and env_value == api_key:
            recoverable.append((service_name, profile_id, api_key))
        else:
            unrecoverable.append((service_name, profile_id, api_key))
    return recoverable, unrecoverable


def _redact_in_place(catalog: dict[str, Any], targets: set[tuple[str, str]]) -> int:
    count = 0
    for service_name, profile, _ in _iter_profiles(catalog):
        profile_id = str(profile.get("id") or "<no-id>")
        if (service_name, profile_id) not in targets:
            continue
        if str(profile.get("api_key") or "").strip():
            profile["api_key"] = REDACTED_SECRET
            count += 1
    return count


def _write_secure(path: Path, catalog: dict[str, Any]) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, CATALOG_FILE_MODE)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(catalog, handle, indent=2, ensure_ascii=False)
    os.chmod(path, CATALOG_FILE_MODE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--path",
        default="",
        help="Catalog file. Defaults to the path the app itself resolves.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually rewrite the file. Without it the script only reports.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Redact even keys the environment cannot supply. DESTRUCTIVE: the "
        "key must be re-entered afterwards. Refused by default.",
    )
    args = parser.parse_args(argv)

    if args.path:
        path = Path(args.path).expanduser()
    else:
        from deeptutor.services.config.model_catalog import CATALOG_PATH

        path = Path(CATALOG_PATH)

    print(f"catalog: {path}")
    if not path.exists():
        print("  nothing to do: file does not exist")
        return 0

    mode = os.stat(path).st_mode & 0o777
    print(f"  mode:   0o{mode:o}" + ("  <-- looser than 0600" if mode & 0o077 else ""))

    try:
        catalog = json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  ! cannot read/parse: {exc}")
        return 3

    env = _env_values()
    recoverable, unrecoverable = plan_purge(catalog, env)

    if not recoverable and not unrecoverable:
        print("  clean: no plaintext api_key found")
        if args.apply and mode & 0o077:
            os.chmod(path, CATALOG_FILE_MODE)
            print(f"  tightened mode to 0o{CATALOG_FILE_MODE:o}")
        return 0

    print(f"\n  plaintext keys found: {len(recoverable) + len(unrecoverable)}")
    for service_name, profile_id, key in recoverable:
        print(f"    [recoverable]   {service_name}/{profile_id}  {_mask(key)}"
              f"  <- {SERVICE_ENV_KEYS.get(service_name, '?')} matches")
    for service_name, profile_id, key in unrecoverable:
        env_key = SERVICE_ENV_KEYS.get(service_name, "?")
        env_value = env.get(env_key, "") if env_key else ""
        if not env_value:
            reason = f"{env_key} is not set; this file is the last copy"
        else:
            # Distinguish "no key" from "a DIFFERENT key" — the second usually
            # means the env moved on and the catalog is stale, which is a very
            # different decision for the operator.
            reason = (
                f"{env_key} is set to a DIFFERENT value ({_mask(env_value)}); "
                "the catalog copy exists nowhere else"
            )
        print(f"    [UNRECOVERABLE] {service_name}/{profile_id}  {_mask(key)}  <- {reason}")

    if unrecoverable and not args.force:
        print(
            "\n  REFUSING to write. Redacting the entries above would destroy the only\n"
            "  copy of those keys. Either put the value in the environment first, or\n"
            "  re-run with --force once you have the key stored somewhere else."
        )
        return 2

    if not args.apply:
        target_count = len(recoverable) + (len(unrecoverable) if args.force else 0)
        print(f"\n  DRY RUN: would redact {target_count} key(s) and set mode 0o600.")
        print("  Re-run with --apply to write.")
        return 0

    targets = {(s, p) for s, p, _ in recoverable}
    if args.force:
        targets |= {(s, p) for s, p, _ in unrecoverable}

    backup = path.with_name(
        f"{path.name}.bak.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    shutil.copy2(path, backup)
    os.chmod(backup, CATALOG_FILE_MODE)
    print(f"\n  backup: {backup} (mode 0o600)")

    changed = _redact_in_place(catalog, targets)
    _write_secure(path, catalog)
    print(f"  redacted {changed} key(s); mode now 0o{CATALOG_FILE_MODE:o}")

    remaining = json.dumps(catalog)
    if REDACTED_SECRET not in remaining and changed:  # pragma: no cover - sanity
        print("  ! post-write sanity check failed: no placeholder present")
        return 3
    print("  done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
