"""env-registry policy gate — "registered-or-you-can't-read-it" for env/flag/secret.

This is the machine enforcement of the RESOURCE_GOVERNANCE_FIX_PLAN root-cause
business fact: *every shared resource must be machine-confirmable as registered in
the single canonical list before any agent uses it.* The documentary rule becomes
a deterministic CI gate here, wired into the SAME contract-guard runner (NOT a new
governance system). It mirrors scripts/check_db_registry.py and
scripts/check_schema_registry.py one-for-one.

The registry lives in ``contracts/env_registry.yaml`` (single canonical list).
This script reads it and scans changed code for env / feature-flag reads, failing
on TWO conditions:

  (a) UNREGISTERED ENV REFERENCE — an ``os.getenv("X")`` / ``os.environ["X"]`` /
      ``env_store.get("X")`` / ``env_flag("X")`` read in production code whose env
      NAME the registry does not list (anywhere: feature_flags ∪ credentials ∪
      aliases ∪ grandfathered_envs). This is the止血 (stop-the-bleed) rule: a NEW
      bare env cannot slip in. (The 284 existing references are grandfathered.)

  (b) UNREGISTERED BARE FEATURE FLAG — a name read through ``env_flag(...)`` — the
      machine signal "this is a boolean gray-release gate" — that the registry
      does not list under ``feature_flags``. A misspelled flag makes
      ``runtime_env.env_flag`` silently return its ``default`` → 假灰度 (a rollout
      that looks live but isn't). This is the sharp edge protecting KB v5 /
      LUBAN_V1 gray-release correctness,同构 with the learner-memory "假绿".

Scope (deliberately not bureaucratic): only UPPER_SNAKE string-literal env names
read in ``deeptutor/`` or ``scripts/`` production code are governed. A dynamic key
(``os.getenv(var)``) or a lowercase value is not a governed literal. Tests /
fixtures are out of scope.

Deterministic and pure: no LLM, no network, no DB. It reads files and applies
regexes, mirroring scripts/check_db_registry.py.

────────────────────────────────────────────────────────────────────────────────────────
PENDING HUNK — wiring into scripts/check_contract_guard.py
────────────────────────────────────────────────────────────────────────────────────────
scripts/check_contract_guard.py currently has UNCOMMITTED parallel WIP, so this
guard is NOT wired into its main() here (no dirty-file dependency / no carrying of
parallel work). Until that file is clean, the gate runs as its own CI step (see
.github/workflows/tests.yml), EXACTLY like the schema/db registry guards do.
Apply the hunk below when check_contract_guard.py is clean (or fold it into the
next contract-guard commit). It is intentionally additive and order-independent:

  # add near the other guard imports at top of scripts/check_contract_guard.py:
  from scripts.check_env_registry import evaluate_env_registry  # noqa: E402

  # inside main(), after the ws guard prints, before the final return:
  env_ok, env_message = evaluate_env_registry(changed_files)
  env_stream = sys.stdout if env_ok else sys.stderr
  print(env_message, file=env_stream)

  # and extend the final boolean:
  return 0 if (ok and code_ok and node_ok and lifecycle_ok
               and upstream_ok and ws_ok and env_ok) else 1

``evaluate_env_registry(changed_files)`` is the changed-files entry point provided
below for exactly this wiring (reads each changed file, runs collect+evaluate).
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
REGISTRY_PATH = REPO_ROOT / "contracts" / "env_registry.yaml"

# An env NAME is an UPPER_SNAKE identifier (≥2 chars, starts with a letter). We
# only govern ALL-CAPS string literals — a dynamic key or a lowercase value is
# not a governed env literal.
_ENV_NAME = r"([A-Z][A-Z0-9_]+)"

# Env-reference read entry points. Each captures the env name in group 1.
#   os.getenv("X") / os.environ.get("X") / os.environ["X"]
#   os.environ.setdefault("X", …) / os.environ.pop("X", …)   (I4)
#   env_store.get("X") / get_env_store().get("X")
#   env_flag("X")  (also matched separately as a flag below)
# I4 also adds a BARE ``getenv("X")`` form (``from os import getenv``), guarded by a
# ``(?<![\w.])`` lookbehind so it does NOT double-match the ``os.getenv`` form above
# (the ``os.`` prefix has a ``.`` immediately before ``getenv``, which the lookbehind
# excludes). The bare form is its own alternation branch BEFORE ``os.``-prefixed
# branches so the longest dotted prefix is still preferred where present.
# I4(b) — Codex adversarial round: ``from os import environ`` then bare
# ``environ['X']`` / ``environ.get('X')`` / ``environ.setdefault/pop`` escaped the
# ``os.``-prefixed branches. Same ``(?<![\w.])`` lookbehind keeps the bare
# ``environ`` branch from double-matching the ``os.environ`` form. The dotted
# sub-forms come BEFORE bare ``environ`` so the longest accessor wins.
_ENV_REF_RE = re.compile(
    r"(?:os\.getenv|os\.environ\.setdefault|os\.environ\.pop|os\.environ\.get|os\.environ|"
    r"(?:get_env_store\(\)|env_store)\.get|env_flag|env_str|env_int|env_bool|env_float|"
    r"(?<![\w.])getenv|"
    r"(?<![\w.])environ\.setdefault|(?<![\w.])environ\.pop|(?<![\w.])environ\.get|"
    r"(?<![\w.])environ)"
    rf"\s*[\(\[]\s*[\"']{_ENV_NAME}[\"']"
)

# Feature-flag read — the machine signal "this name is a boolean gray-release
# gate". Only ``env_flag()`` (runtime_env's boolean reader) counts.
_ENV_FLAG_RE = re.compile(rf"\benv_flag\s*\(\s*[\"']{_ENV_NAME}[\"']")

# Restrict to production source. Tests, fixtures, and the registry are out of
# scope. Scripts/ are in scope (maintenance scripts read env too).
_IN_SCOPE_PATH_RE = re.compile(r"^(?:deeptutor/|scripts/)")
_OUT_OF_SCOPE_PATH_RE = re.compile(r"(?:^|/)tests?/|(?:^|/)conftest\.py$|_test\.py$|/fixtures?/")


@dataclass(frozen=True)
class EnvRefUsage:
    """One env-name reference found in a scanned file."""

    path: str
    lineno: int
    env_name: str


@dataclass(frozen=True)
class FlagUsage:
    """One env_flag(NAME) read found in a scanned file."""

    path: str
    lineno: int
    flag_name: str


def load_env_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Load + index ``contracts/env_registry.yaml`` into lookup structures.

    ``registered_envs`` is the UNION of every registered name (feature_flags ∪
    credentials ∪ aliases ∪ grandfathered_envs) — rule (a) keys off it.
    ``registered_flags`` is just the feature_flags name set — rule (b) keys off it.
    """
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    registered_flags: set[str] = set()
    for entry in payload.get("feature_flags") or []:
        if isinstance(entry, dict) and entry.get("name"):
            registered_flags.add(str(entry["name"]))

    registered_envs: set[str] = set(registered_flags)
    for entry in payload.get("credentials") or []:
        if isinstance(entry, dict) and entry.get("name"):
            registered_envs.add(str(entry["name"]))
    for entry in payload.get("aliases") or []:
        if isinstance(entry, dict) and entry.get("alias"):
            registered_envs.add(str(entry["alias"]))
        if isinstance(entry, dict) and entry.get("canonical"):
            registered_envs.add(str(entry["canonical"]))
    for name in payload.get("grandfathered_envs") or []:
        registered_envs.add(str(name))

    if not registered_envs:
        raise ValueError("contracts/env_registry.yaml registered no env names")

    return {
        "registered_envs": registered_envs,
        "registered_flags": registered_flags,
    }


def collect_env_reference_usages(files: list[tuple[str, str]]) -> list[EnvRefUsage]:
    """Scan ``(path, body)`` pairs for env-name reference reads."""
    usages: list[EnvRefUsage] = []
    for path, body in files:
        if not body:
            continue
        for lineno, line in enumerate(body.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for match in _ENV_REF_RE.finditer(line):
                usages.append(
                    EnvRefUsage(path=path, lineno=lineno, env_name=match.group(1))
                )
    return usages


def collect_feature_flag_usages(files: list[tuple[str, str]]) -> list[FlagUsage]:
    """Scan ``(path, body)`` pairs for env_flag(NAME) reads."""
    usages: list[FlagUsage] = []
    for path, body in files:
        if not body:
            continue
        for lineno, line in enumerate(body.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for match in _ENV_FLAG_RE.finditer(line):
                usages.append(
                    FlagUsage(path=path, lineno=lineno, flag_name=match.group(1))
                )
    return usages


def _check_unregistered_env_references(
    usages: list[EnvRefUsage], registry: dict[str, Any]
) -> list[str]:
    """Fail rule (a): an env reference whose name the registry does not list."""
    registered: set[str] = registry["registered_envs"]
    failures: list[str] = []
    seen: set[tuple[str, int, str]] = set()
    for usage in usages:
        if usage.env_name in registered:
            continue
        key = (usage.path, usage.lineno, usage.env_name)
        if key in seen:
            continue
        seen.add(key)
        failures.append(
            f"{usage.path}:{usage.lineno}: unregistered env '{usage.env_name}'. "
            f"Add it to contracts/env_registry.yaml (grandfathered_envs, or "
            f"credentials if it is a secret) so the single canonical inventory "
            f"machine-confirms it. A bare env that no one declared drifts silently."
        )
    return failures


def _check_unregistered_feature_flags(
    usages: list[FlagUsage], registry: dict[str, Any]
) -> list[str]:
    """Fail rule (b): an env_flag() read whose name is not a registered flag.

    This is the sharp edge: a misspelled flag makes env_flag() return its default
    → 假灰度. The name MUST be registered under feature_flags (with its default +
    gray-release semantics) so the gray-release is real.
    """
    registered_flags: set[str] = registry["registered_flags"]
    failures: list[str] = []
    seen: set[tuple[str, int, str]] = set()
    for usage in usages:
        if usage.flag_name in registered_flags:
            continue
        key = (usage.path, usage.lineno, usage.flag_name)
        if key in seen:
            continue
        seen.add(key)
        failures.append(
            f"{usage.path}:{usage.lineno}: unregistered feature flag "
            f"'{usage.flag_name}' read via env_flag(). Register it in "
            f"contracts/env_registry.yaml feature_flags[] with its default + kind "
            f"— a misspelled flag silently returns env_flag's default (假灰度), so "
            f"the gray-release would look live but never take effect."
        )
    return failures


def evaluate_env_usages(
    env_refs: list[EnvRefUsage],
    flags: list[FlagUsage],
    registry: dict[str, Any],
) -> tuple[bool, str]:
    """Apply the two fail rules to collected usages."""
    failures: list[str] = []
    failures.extend(_check_unregistered_env_references(env_refs, registry))
    failures.extend(_check_unregistered_feature_flags(flags, registry))

    if failures:
        unique = list(dict.fromkeys(failures))
        return False, "env-registry-guard: failed\n" + "\n".join(unique)

    if not (env_refs or flags):
        return True, "env-registry-guard: no env / feature-flag read in changed files"
    return True, (
        "env-registry-guard: passed | "
        f"env_refs={len(env_refs)} feature_flags={len(flags)} (all registered)"
    )


def _read_changed_files(changed_files: list[str]) -> list[tuple[str, str]]:
    """Read in-scope production files into (path, body) pairs."""
    pairs: list[tuple[str, str]] = []
    for raw in changed_files:
        path = raw.strip()
        if not path or not _IN_SCOPE_PATH_RE.match(path):
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


def evaluate_env_registry(changed_files: list[str]) -> tuple[bool, str]:
    """Changed-files entry point — the hook contract-guard wires into (pending hunk).

    Reads each in-scope changed file, collects env / feature-flag reads, evaluates
    the two fail rules. Mirrors the other ``evaluate_*`` guards' signature.
    """
    pairs = _read_changed_files(changed_files)
    if not pairs:
        return True, "env-registry-guard: no in-scope production source changed"
    registry = load_env_registry()
    env_refs = collect_env_reference_usages(pairs)
    flags = collect_feature_flag_usages(pairs)
    return evaluate_env_usages(env_refs, flags, registry)


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


# M2: scan-all glob set, run INSIDE the scanner via subprocess (a list arg, never
# shell-word-split). The CI used ``$(git ls-files …)`` unquoted, so a tracked path
# containing a space would be split into two bogus arguments. ``--all`` lets CI call
# the scanner with no shell expansion (``python check_env_registry.py --all``).
_SCAN_ALL_GLOBS = ("deeptutor/**/*.py", "scripts/**/*.py")


def _git_tracked_in_scope_files() -> list[str]:
    """Return tracked in-scope files via the scanner's own ``git ls-files``.

    Uses a subprocess LIST argument (no shell), so a path with a space stays one
    argument — closing the M2 unquoted-``$(git ls-files)`` word-split hole.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z", *_SCAN_ALL_GLOBS],
        check=True,
        capture_output=True,
        text=True,
    )
    return [p for p in result.stdout.split("\0") if p]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when code references an unregistered env / reads an "
        "unregistered feature flag (防新增裸 env / 防假灰度)."
    )
    parser.add_argument(
        "files", nargs="*", help="Explicit changed files. If omitted, git diff is used."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan ALL tracked in-scope files via the scanner's own git ls-files "
        "(no shell word-splitting on spaced paths — the CI-safe full-repo mode).",
    )
    args = parser.parse_args(argv)

    if args.all:
        changed = _git_tracked_in_scope_files()
    else:
        changed = args.files or _git_current_candidate_files()
    ok, message = evaluate_env_registry(changed)
    stream = sys.stdout if ok else sys.stderr
    print(message, file=stream)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
