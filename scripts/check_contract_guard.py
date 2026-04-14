from __future__ import annotations

import argparse
import fnmatch
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "contracts" / "index.yaml"


def load_contract_index() -> dict[str, Any]:
    payload = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8")) or {}
    domains = payload.get("domains")
    if not isinstance(domains, dict) or not domains:
        raise ValueError("contracts/index.yaml must define non-empty domains")
    return payload


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _git_diff_name_only(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def resolve_changed_files(files: list[str], *, base: str | None, head: str | None) -> list[str]:
    if files:
        return [item for item in files if item.strip()]
    if base and head:
        return _git_diff_name_only(base, head)
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def evaluate_changed_files(changed_files: list[str]) -> tuple[bool, str]:
    normalized = tuple(sorted({path.strip() for path in changed_files if path.strip()}))
    if not normalized:
        return True, "contract-guard: no changed files detected"

    index = load_contract_index()
    domains: dict[str, dict[str, Any]] = index["domains"]
    failures: list[str] = []
    passes: list[str] = []
    touched_any_domain = False

    for domain_name, raw_domain in domains.items():
        protected_patterns = list(raw_domain.get("protected_patterns") or [])
        sensitive_patterns = list(raw_domain.get("sensitive_patterns") or [])
        contract_files = set(raw_domain.get("contract_files") or [])
        test_files = set(raw_domain.get("test_files") or [])

        protected = [path for path in normalized if _matches_any(path, protected_patterns)]
        if not protected:
            continue

        touched_any_domain = True
        touched_tests = sorted(path for path in normalized if path in test_files)
        if not touched_tests:
            failures.append(
                f"[{domain_name}] protected files changed but no domain tests were updated.\n"
                f"protected: {', '.join(protected)}\n"
                f"required tests: {', '.join(sorted(test_files))}"
            )
            continue

        sensitive = [path for path in protected if _matches_any(path, sensitive_patterns)]
        touched_contract = sorted(path for path in normalized if path in contract_files)
        if sensitive and not touched_contract:
            failures.append(
                f"[{domain_name}] contract-sensitive files changed but no contract surfaces were updated.\n"
                f"sensitive: {', '.join(sensitive)}\n"
                f"required contract files: {', '.join(sorted(contract_files))}"
            )
            continue

        detail = f"[{domain_name}] passed | protected={', '.join(protected)} | tests={', '.join(touched_tests)}"
        if touched_contract:
            detail += f" | contract={', '.join(touched_contract)}"
        passes.append(detail)

    if failures:
        return False, "contract-guard: failed\n" + "\n\n".join(failures)
    if not touched_any_domain:
        return True, "contract-guard: no protected contract domains changed"
    return True, "contract-guard: passed\n" + "\n".join(passes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail CI when protected contract boundaries change without docs/tests coverage."
    )
    parser.add_argument("files", nargs="*", help="Explicit changed files. If omitted, git diff is used.")
    parser.add_argument("--base", help="Base git ref for diff.")
    parser.add_argument("--head", help="Head git ref for diff.")
    args = parser.parse_args(argv)

    try:
        changed_files = resolve_changed_files(args.files, base=args.base, head=args.head)
    except subprocess.CalledProcessError as exc:
        print(f"contract-guard: failed to determine changed files: {exc}", file=sys.stderr)
        return 2

    ok, message = evaluate_changed_files(changed_files)
    stream = sys.stdout if ok else sys.stderr
    print(message, file=stream)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
