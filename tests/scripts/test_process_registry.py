"""TDD for scripts/check_process_registry.py — the long-running-process policy gate.

The guard turns the RESOURCE_GOVERNANCE_FIX_PLAN root-cause business fact —
"每个长驻进程/定时任务，必须能被机器确认它登记在唯一 canonical 清单里：谁拥有、
生命周期是什么、出事谁来停" — into a real CI gate. It scans changed code and
.github/workflows and fails on TWO conditions:

  (a) a NEW GHA cron schedule (a workflow with ``- cron:`` not registered in
      process_registry.yaml scheduled_tasks[]);
  (b) a NEW always-on daemon task — a ``create_task(...)`` whose result is stored
      in a PERSISTENT holder (``self._*task* = create_task`` or
      ``*.worker_tasks[...] = ... create_task``) — at a site the registry does not
      list under daemons[].

This is the止血 (stop-the-bleed) rule against the 201.6 GB Next-process class:
an AI-agent-owned long-running task that no one registered cannot slip in.
Fire-and-forget per-request ``create_task`` (result discarded) is NOT a daemon and
is deliberately out of scope — that is the zero-false-positive boundary.

These tests pin the two fail rules + the pass/grandfather paths + the scope
carve-outs. They run on synthetic snippets (no live import of the scanned
modules), so they are deterministic and touch no parallel WIP source.
"""

from __future__ import annotations

from scripts.check_process_registry import (
    collect_cron_usages,
    collect_daemon_usages,
    evaluate_process_registry,
    evaluate_process_usages,
    load_process_registry,
)


# ── Registry loads and exposes the single canonical list ─────────────────────
def test_registry_loads_daemons_and_scheduled_tasks() -> None:
    registry = load_process_registry()
    # grandfathered存量 daemon sites are indexed (so they are not flagged as new)
    assert "deeptutor/tutorbot/heartbeat/service.py" in registry["daemon_sites"]
    assert "deeptutor/tutorbot/cron/service.py" in registry["daemon_sites"]
    assert "deeptutor/events/event_bus.py" in registry["daemon_sites"]
    # the GHA cron workflows are registered as scheduled_tasks
    assert ".github/workflows/wallet-consistency-cron.yml" in registry["cron_workflows"]
    assert ".github/workflows/hermes-upstream.yml" in registry["cron_workflows"]


# ── FAIL RULE (a): unregistered GHA cron schedule (止血 — new cron) ───────────
def test_fail_new_unregistered_cron_workflow() -> None:
    # min repro: a brand-new workflow file declares a cron schedule.
    code = "on:\n  schedule:\n    - cron: '0 5 * * *'\n"
    crons = collect_cron_usages([(".github/workflows/new-nightly.yml", code)])
    ok, message = evaluate_process_usages(crons, [], load_process_registry())
    assert ok is False
    assert "unregistered cron schedule" in message
    assert ".github/workflows/new-nightly.yml" in message


def test_pass_grandfathered_cron_workflow() -> None:
    # regression: an existing存量 cron workflow is grandfathered, not flagged.
    code = "on:\n  schedule:\n    - cron: '0 4 * * *'\n"
    crons = collect_cron_usages(
        [(".github/workflows/wallet-consistency-cron.yml", code)]
    )
    ok, message = evaluate_process_usages(crons, [], load_process_registry())
    assert ok is True
    assert "passed" in message


# ── FAIL RULE (b): unregistered always-on daemon task ────────────────────────
def test_fail_new_persistent_self_task_daemon() -> None:
    # min repro: a brand-new file starts a persistent loop task held on self.
    code = (
        "import asyncio\n"
        "class Pump:\n"
        "    async def start(self):\n"
        "        self._task = asyncio.create_task(self._run_loop())\n"
    )
    daemons = collect_daemon_usages([("deeptutor/services/pump.py", code)])
    ok, message = evaluate_process_usages([], daemons, load_process_registry())
    assert ok is False
    assert "unregistered long-running daemon" in message
    assert "deeptutor/services/pump.py" in message


def test_fail_new_worker_tasks_dict_daemon() -> None:
    # min repro: a persistent worker stored in a *.worker_tasks dict.
    code = (
        "task = asyncio.create_task(self._run_worker(key, name))\n"
        "runtime.worker_tasks[name] = task\n"
    )
    daemons = collect_daemon_usages([("deeptutor/services/new_team.py", code)])
    ok, message = evaluate_process_usages([], daemons, load_process_registry())
    assert ok is False
    assert "unregistered long-running daemon" in message


def test_pass_grandfathered_daemon_site() -> None:
    # regression: an existing存量 daemon site is grandfathered, not flagged.
    code = "        self._task = asyncio.create_task(self._run_loop())\n"
    daemons = collect_daemon_usages(
        [("deeptutor/tutorbot/heartbeat/service.py", code)]
    )
    ok, message = evaluate_process_usages([], daemons, load_process_registry())
    assert ok is True
    assert "passed" in message


# ── SCOPE CARVE-OUT: fire-and-forget create_task is NOT a daemon ─────────────
def test_fire_and_forget_create_task_not_a_daemon() -> None:
    # the zero-false-positive boundary: a per-request create_task whose result is
    # discarded (not stored in a persistent holder) is NOT a long-running daemon.
    code = "asyncio.create_task(self._dispatch(msg))\n"  # result discarded
    daemons = collect_daemon_usages([("deeptutor/services/x.py", code)])
    ok, _ = evaluate_process_usages([], daemons, load_process_registry())
    assert ok is True


def test_local_variable_create_task_not_a_daemon() -> None:
    # a create_task assigned to a plain local (not self._*task / worker_tasks)
    # is awaited/gathered in-scope, not a persistent daemon.
    code = "tasks = [asyncio.create_task(_typing_loop()) for _ in range(3)]\n"
    daemons = collect_daemon_usages([("deeptutor/services/x.py", code)])
    ok, _ = evaluate_process_usages([], daemons, load_process_registry())
    assert ok is True


def test_comment_lines_not_flagged() -> None:
    # a commented-out daemon / cron must not trip the guard.
    code = "# self._task = asyncio.create_task(self._run_loop())\n# - cron: '0 1 * * *'\n"
    daemons = collect_daemon_usages([("deeptutor/services/x.py", code)])
    crons = collect_cron_usages([(".github/workflows/x.yml", code)])
    ok, _ = evaluate_process_usages(crons, daemons, load_process_registry())
    assert ok is True


# ── changed-files entry point: scope + grandfather end-to-end ────────────────
def test_tests_dir_out_of_scope_via_changed_files_entry() -> None:
    # the changed-files entry point ignores tests/ and non-governed paths.
    ok, message = evaluate_process_registry(
        ["tests/services/test_new_pump.py", "docs/plan/whatever.md"]
    )
    assert ok is True
    assert "no in-scope" in message


def test_full_repo_scan_is_zero_false_positive() -> None:
    # the load-bearing invariant: scanning EVERY governed file in the live repo
    # exits clean. Every existing daemon site + cron workflow is grandfathered.
    import subprocess

    from scripts.check_process_registry import REPO_ROOT

    tracked = subprocess.run(
        ["git", "ls-files", "deeptutor/**/*.py", "scripts/**/*.py", ".github/workflows/*.yml"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    ok, message = evaluate_process_registry(tracked)
    assert ok is True, message
