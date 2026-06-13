"""process-registry policy gate — "registered-or-you-can't-run-it" for daemons.

This is the machine enforcement of the RESOURCE_GOVERNANCE_FIX_PLAN root-cause
business fact: *every shared resource must be machine-confirmable as registered in
the single canonical list before any agent uses it.* The documentary rule becomes
a deterministic CI gate here, wired into the SAME contract-guard runner (NOT a new
governance system). It mirrors scripts/check_db_registry.py and
scripts/check_env_registry.py one-for-one.

The registry lives in ``contracts/process_registry.yaml`` (single canonical
list). This script reads it and scans changed code + GHA workflows for the TWO
machine signals of a long-running process, failing on:

  (a) UNREGISTERED GHA CRON — a ``- cron:`` schedule line in a
      ``.github/workflows/*.yml`` whose workflow file the registry does not list
      under ``scheduled_tasks[]``. 止血: a NEW cron schedule cannot slip in
      unowned.

  (b) UNREGISTERED ALWAYS-ON DAEMON — a ``create_task(...)`` whose result is
      stored in a PERSISTENT holder (``self._<...>task<...> = create_task`` or
      ``<obj>.worker_tasks[...] = ... create_task``) at a source file the registry
      does not list under ``daemons[]``. The persistent holder is the machine
      signal "this task outlives the call that started it" — the 201.6 GB
      blast-radius class. A fire-and-forget ``create_task(coro)`` whose result is
      discarded is NOT a daemon (zero-false-positive boundary).

Scope (deliberately not bureaucratic): only governed signals in production
``deeptutor/`` / ``scripts/`` code (daemons) and ``.github/workflows/`` (cron) are
checked. Tests / fixtures are out of scope.

Deterministic and pure: no LLM, no network, no app import, no DB. It reads files
and applies regexes, mirroring scripts/check_db_registry.py.

────────────────────────────────────────────────────────────────────────────────────────
PENDING HUNK — wiring into scripts/check_contract_guard.py
────────────────────────────────────────────────────────────────────────────────────────
scripts/check_contract_guard.py currently has UNCOMMITTED parallel WIP, so this
guard is NOT wired into its main() here (no dirty-file dependency / no carrying of
parallel work). Until that file is clean, the gate runs as its own CI step (see
.github/workflows/tests.yml), EXACTLY like the schema/db/env/provider registry
guards do. Apply the hunk below when check_contract_guard.py is clean:

  # add near the other guard imports at top of scripts/check_contract_guard.py:
  from scripts.check_process_registry import evaluate_process_registry  # noqa: E402

  # inside main(), after the provider guard prints, before the final return:
  proc_ok, proc_message = evaluate_process_registry(changed_files)
  proc_stream = sys.stdout if proc_ok else sys.stderr
  print(proc_message, file=proc_stream)

  # and extend the final boolean:
  return 0 if (ok and code_ok and node_ok and lifecycle_ok
               and upstream_ok and ws_ok and env_ok and provider_ok
               and proc_ok) else 1

``evaluate_process_registry(changed_files)`` is the changed-files entry point
provided below for exactly this wiring.
────────────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "contracts" / "process_registry.yaml"

# Cron schedule line in a GHA workflow:  - cron: "0 4 * * *"
_CRON_RE = re.compile(r"-\s*cron\s*:")

# Persistent-daemon signal (b): a create_task whose result is stored in a
# PERSISTENT holder. Two machine-recognizable shapes:
#   self._<...>task<...> = asyncio.create_task(...)   (instance-attr task holder)
#   <obj>.worker_tasks[<key>] = ... create_task(...)  (worker-task dict holder)
# A fire-and-forget create_task (result discarded) does NOT match either.
_SELF_TASK_DAEMON_RE = re.compile(
    r"self\._[A-Za-z0-9_]*task[A-Za-z0-9_]*\s*=\s*(?:asyncio\.)?create_task\s*\("
)
_WORKER_TASKS_DAEMON_RE = re.compile(r"\.worker_tasks\[[^\]]+\]\s*=")

# Daemons are governed in production source; cron in workflows. Tests/fixtures out.
_DAEMON_SCOPE_RE = re.compile(r"^(?:deeptutor/|scripts/).*\.py$")
_WORKFLOW_SCOPE_RE = re.compile(r"^\.github/workflows/.*\.ya?ml$")
_OUT_OF_SCOPE_PATH_RE = re.compile(
    r"(?:^|/)tests?/|(?:^|/)conftest\.py$|_test\.py$|/fixtures?/"
)


@dataclass(frozen=True)
class CronUsage:
    """One GHA cron schedule line found in a scanned workflow file."""

    path: str
    lineno: int


@dataclass(frozen=True)
class DaemonUsage:
    """One persistent-daemon create_task found in a scanned source file."""

    path: str
    lineno: int


def load_process_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Load + index ``contracts/process_registry.yaml`` into lookup structures.

    ``daemon_sites`` is the set of registered daemon source files — rule (b) keys
    off it. ``cron_workflows`` is the set of registered workflow files — rule (a)
    keys off it.
    """
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    daemon_sites: set[str] = set()
    for entry in payload.get("daemons") or []:
        if isinstance(entry, dict) and entry.get("file"):
            daemon_sites.add(str(entry["file"]))

    cron_workflows: set[str] = set()
    for entry in payload.get("scheduled_tasks") or []:
        if isinstance(entry, dict) and entry.get("file"):
            cron_workflows.add(str(entry["file"]))

    if not daemon_sites and not cron_workflows:
        raise ValueError(
            "contracts/process_registry.yaml registered no daemons or scheduled_tasks"
        )

    return {"daemon_sites": daemon_sites, "cron_workflows": cron_workflows}


def collect_cron_usages(files: list[tuple[str, str]]) -> list[CronUsage]:
    """Scan ``(path, body)`` workflow pairs for cron schedule lines."""
    usages: list[CronUsage] = []
    for path, body in files:
        if not body or not _WORKFLOW_SCOPE_RE.match(path):
            continue
        for lineno, line in enumerate(body.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            if _CRON_RE.search(line):
                usages.append(CronUsage(path=path, lineno=lineno))
    return usages


def collect_daemon_usages(files: list[tuple[str, str]]) -> list[DaemonUsage]:
    """Scan ``(path, body)`` source pairs for persistent-daemon create_task sites."""
    usages: list[DaemonUsage] = []
    for path, body in files:
        if not body:
            continue
        for lineno, line in enumerate(body.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if _SELF_TASK_DAEMON_RE.search(line) or _WORKER_TASKS_DAEMON_RE.search(line):
                usages.append(DaemonUsage(path=path, lineno=lineno))
    return usages


def _check_unregistered_crons(
    usages: list[CronUsage], registry: dict[str, Any]
) -> list[str]:
    """Fail rule (a): a cron schedule in a workflow the registry does not list."""
    registered: set[str] = registry["cron_workflows"]
    failures: list[str] = []
    seen: set[str] = set()
    for usage in usages:
        if usage.path in registered:
            continue
        if usage.path in seen:
            continue
        seen.add(usage.path)
        failures.append(
            f"{usage.path}:{usage.lineno}: unregistered cron schedule. Add the "
            f"workflow to contracts/process_registry.yaml scheduled_tasks[] with "
            f"its owner + schedule + supervised_by so the single canonical "
            f"inventory machine-confirms it. An unowned cron drifts silently."
        )
    return failures


def _check_unregistered_daemons(
    usages: list[DaemonUsage], registry: dict[str, Any]
) -> list[str]:
    """Fail rule (b): a persistent daemon at a file the registry does not list.

    This is the sharp edge: an AI-agent-owned always-on task that no one
    registered is the 201.6 GB blast-radius class. The file MUST be registered
    under daemons[] (with owner + lifecycle + stop procedure).
    """
    registered: set[str] = registry["daemon_sites"]
    failures: list[str] = []
    seen: set[str] = set()
    for usage in usages:
        if usage.path in registered:
            continue
        if usage.path in seen:
            continue
        seen.add(usage.path)
        failures.append(
            f"{usage.path}:{usage.lineno}: unregistered long-running daemon "
            f"(persistent create_task held on self._*task / worker_tasks). "
            f"Register the file in contracts/process_registry.yaml daemons[] with "
            f"its owner + lifecycle + supervised_by — an unowned always-on task "
            f"can leak memory/handles like the 201.6 GB Next incident with no "
            f"registry to audit or stop it."
        )
    return failures


def evaluate_process_usages(
    crons: list[CronUsage],
    daemons: list[DaemonUsage],
    registry: dict[str, Any],
) -> tuple[bool, str]:
    """Apply the two fail rules to collected usages."""
    failures: list[str] = []
    failures.extend(_check_unregistered_crons(crons, registry))
    failures.extend(_check_unregistered_daemons(daemons, registry))

    if failures:
        unique = list(dict.fromkeys(failures))
        return False, "process-registry-guard: failed\n" + "\n".join(unique)

    if not (crons or daemons):
        return True, "process-registry-guard: no cron / daemon signal in changed files"
    return True, (
        "process-registry-guard: passed | "
        f"cron_lines={len(crons)} daemon_sites={len(daemons)} (all registered)"
    )


def _read_changed_files(changed_files: list[str]) -> list[tuple[str, str]]:
    """Read in-scope governed files into (path, body) pairs.

    In scope: production ``deeptutor/`` / ``scripts/`` .py (daemons) and
    ``.github/workflows/`` .yml (cron). Tests/fixtures excluded.
    """
    pairs: list[tuple[str, str]] = []
    for raw in changed_files:
        path = raw.strip()
        if not path:
            continue
        governed = _DAEMON_SCOPE_RE.match(path) or _WORKFLOW_SCOPE_RE.match(path)
        if not governed:
            continue
        if _OUT_OF_SCOPE_PATH_RE.search(path):
            continue
        full = REPO_ROOT / path
        if not full.exists() or not full.is_file():
            continue
        try:
            body = full.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        pairs.append((path, body))
    return pairs


def evaluate_process_registry(changed_files: list[str]) -> tuple[bool, str]:
    """Changed-files entry point — the hook contract-guard wires into (pending hunk).

    Reads each in-scope changed file, collects cron + daemon signals, evaluates
    the two fail rules. Mirrors the other ``evaluate_*`` guards' signature.
    """
    pairs = _read_changed_files(changed_files)
    if not pairs:
        return True, "process-registry-guard: no in-scope governed source changed"
    registry = load_process_registry()
    crons = collect_cron_usages(pairs)
    daemons = collect_daemon_usages(pairs)
    return evaluate_process_usages(crons, daemons, registry)


def _git_current_candidate_files() -> list[str]:
    files: set[str] = set()
    for command in (
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        files.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when code introduces an unregistered GHA cron / "
        "always-on daemon task (止血 — 防新增未登记长驻进程)."
    )
    parser.add_argument(
        "files", nargs="*", help="Explicit changed files. If omitted, git diff is used."
    )
    args = parser.parse_args(argv)

    changed = args.files or _git_current_candidate_files()
    ok, message = evaluate_process_registry(changed)
    stream = sys.stdout if ok else sys.stderr
    print(message, file=stream)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
