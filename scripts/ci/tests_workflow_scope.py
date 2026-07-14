#!/usr/bin/env python3
"""Helpers for the GitHub Actions Tests workflow fast path."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from typing import Iterable

WORKFLOW_FILES = {
    ".github/workflows/tests.yml",
    ".github/pull_request_template.md",
}

SECRET_SCAN_EXCLUDED_PREFIXES = (
    ".playwright-cli/",
    ".playwright-mcp/",
    ".superpowers/",
    "artifacts/",
    "deeptutor/services/benchmark/fixtures/",
    "deeptutor/services/construction_grading/runtime_supply/",
    "deeptutor/services/luban_lesson/compiled/",
    "deeptutor/services/taxonomy/compiled/",
    "dist/",
    "output/",
    "tests/fixtures/",
    "tmp/",
    "web/public/luban-preview/",
)

SECRET_SCAN_EXCLUDED_SUFFIXES = (
    ".bmp",
    ".db",
    ".docx",
    ".gif",
    ".gz",
    ".jpeg",
    ".jpg",
    ".lock",
    ".mov",
    ".mp3",
    ".mp4",
    ".parquet",
    ".pdf",
    ".pkl",
    ".png",
    ".psd",
    ".sqlite",
    ".webm",
    ".webp",
    ".xlsx",
    ".zip",
)

SECRET_SCAN_EXCLUDED_EXACT = {
    ".secrets.baseline",
    "package-lock.json",
}


def git_lines(*args: str) -> list[str]:
    return subprocess.check_output(["git", *args], text=True).splitlines()


def changed_files(event_name: str, base_sha: str, head_sha: str) -> list[str]:
    if event_name == "pull_request":
        return git_lines("diff", "--name-only", base_sha, head_sha)
    if base_sha and set(base_sha) != {"0"}:
        return git_lines("diff", "--name-only", base_sha, head_sha)
    return git_lines("diff-tree", "--no-commit-id", "--name-only", "-r", head_sha)


def changed_tracked_files(base_sha: str, head_sha: str) -> list[str]:
    changed = git_lines("diff", "--name-only", "--diff-filter=ACMR", base_sha, head_sha)
    return secret_scan_files([path for path in changed if Path(path).is_file()])


def should_secret_scan(path: str) -> bool:
    normalized = path.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        return False
    if normalized in SECRET_SCAN_EXCLUDED_EXACT:
        return False
    if normalized.startswith(SECRET_SCAN_EXCLUDED_PREFIXES):
        return False
    lowered = normalized.lower()
    return not lowered.endswith(SECRET_SCAN_EXCLUDED_SUFFIXES)


def secret_scan_files(paths: Iterable[str]) -> list[str]:
    return [path for path in paths if should_secret_scan(path)]


def _has(changed: Iterable[str], *, prefixes: tuple[str, ...] = (), exact: tuple[str, ...] = ()) -> bool:
    exact_set = set(exact) | WORKFLOW_FILES
    return any(path in exact_set or any(path.startswith(prefix) for prefix in prefixes) for path in changed)


def classify(changed: Iterable[str]) -> dict[str, bool]:
    changed = list(changed)
    return {
        "governance": _has(
            changed,
            prefixes=(
                "deeptutor/",
                "deeptutor_cli/",
                "tests/",
                "scripts/ci/",
                "scripts/check_",
                "requirements/",
                "agent-skills/",
                "contracts/",
                "domains/",
                "eval/",
                "deployment/",
                "supabase/migrations/",
            ),
            exact=(
                "requirements.txt",
                "pyproject.toml",
                "CONTRACT.md",
                "AGENTS.md",
                ".secrets.baseline",
                ".bandit-baseline.json",
                "docker-compose.yml",
                "docs/zh/guide/unified-turn-contract.md",
            ),
        ),
        "backend": _has(
            changed,
            prefixes=(
                "deeptutor/",
                "deeptutor_cli/",
                "tests/",
                "scripts/check_",
                "requirements/",
                "agent-skills/",
                "contracts/",
            ),
            exact=(
                "requirements.txt",
                "pyproject.toml",
                "CONTRACT.md",
                "AGENTS.md",
            ),
        ),
        "frontend": _has(changed, prefixes=("web/",)),
        "wx": _has(changed, prefixes=("wx_miniprogram/",)),
        "yousen": _has(changed, prefixes=("yousenwebview/",)),
    }


def write_github_outputs(scope: dict[str, bool], output_path: str) -> None:
    with open(output_path, "a", encoding="utf-8") as out:
        for name, value in scope.items():
            out.write(f"{name}={str(value).lower()}\n")


def run_secret_scan(paths: list[str], baseline: str) -> int:
    if not paths:
        print("No tracked files to scan.")
        return 0
    print(f"Scanning {len(paths)} tracked file(s).")
    sample = paths if len(paths) <= 25 else paths[:25]
    for path in sample:
        print(f"  {path}")
    if len(sample) != len(paths):
        print(f"  ... {len(paths) - len(sample)} more")
    result = subprocess.run(["detect-secrets-hook", "--baseline", baseline, *paths])
    if result.returncode:
        print("::error::detect-secrets found a secret not in .secrets.baseline.")
        print("If real: remove it and ROTATE the credential. If false positive: add a narrow pragma or audited baseline entry.")
    return result.returncode


def cmd_classify(args: argparse.Namespace) -> int:
    changed = changed_files(args.event_name, args.base_sha, args.head_sha)
    scope = classify(changed)
    if args.github_output:
        write_github_outputs(scope, args.github_output)
    print("Changed files:")
    for path in changed:
        print(f"  {path}")
    print("Scope:", " ".join(f"{name}={value}" for name, value in scope.items()))
    return 0


def cmd_scan_changed(args: argparse.Namespace) -> int:
    return run_secret_scan(changed_tracked_files(args.base_sha, args.head_sha), args.baseline)


def cmd_scan_full(args: argparse.Namespace) -> int:
    return run_secret_scan(secret_scan_files(git_lines("ls-files")), args.baseline)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    classify_parser = subparsers.add_parser("classify")
    classify_parser.add_argument("--event-name", required=True)
    classify_parser.add_argument("--base-sha", required=True)
    classify_parser.add_argument("--head-sha", required=True)
    classify_parser.add_argument("--github-output")
    classify_parser.set_defaults(func=cmd_classify)

    scan_changed_parser = subparsers.add_parser("scan-secrets-changed")
    scan_changed_parser.add_argument("--base-sha", required=True)
    scan_changed_parser.add_argument("--head-sha", required=True)
    scan_changed_parser.add_argument("--baseline", default=".secrets.baseline")
    scan_changed_parser.set_defaults(func=cmd_scan_changed)

    scan_full_parser = subparsers.add_parser("scan-secrets-full")
    scan_full_parser.add_argument("--baseline", default=".secrets.baseline")
    scan_full_parser.set_defaults(func=cmd_scan_full)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
