from __future__ import annotations

import argparse
import fnmatch
import re
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "contracts" / "index.yaml"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Phase -1.B: error-code emit-site cross-check.
# Scan these source paths for hard-coded error_code literals that look like
# E0X / M0X codes and validate them against ERROR_CODE_REGISTRY. The list is
# intentionally narrow — only the authoritative emit modules. Tests, fixtures
# and learning_brain_read_model's local label dict are excluded; if a test
# hand-rolls an unregistered code it will surface via the consumer pipeline.
_ERROR_CODE_EMIT_PATHS: tuple[str, ...] = (
    "deeptutor/services/construction_grading/mcq.py",
    "deeptutor/services/construction_grading/case_kernel.py",
    "deeptutor/services/construction_grading/learning_evidence.py",
    "deeptutor/services/learner_state/learning_synthesis.py",
)
_ERROR_CODE_LITERAL_RE = re.compile(r'"([EM]\d{2}|unknown_error)"')

# Batch A Task 3: knowledge_node_id emit-site cross-check.
# Hard-coded 1A4XXXXX literals in evidence / synthesis / training_intent
# emit modules must resolve to a seeded node in
# ``deeptutor.services.taxonomy.construction_learning_graph``. Runtime
# data is not scanned here — only static defaults / examples / fallbacks
# in production code.
_NODE_ID_SCAN_PATHS: tuple[str, ...] = (
    "deeptutor/services/construction_grading/mcq.py",
    "deeptutor/services/construction_grading/case_kernel.py",
    "deeptutor/services/construction_grading/learning_evidence.py",
    "deeptutor/services/learner_state/learning_synthesis.py",
    "deeptutor/services/learner_state/training_intent.py",
)
_NODE_ID_LITERAL_RE = re.compile(r'"(1A4\d{4,5})"')


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


def _git_current_candidate_files() -> list[str]:
    files: set[str] = set()
    for command in (
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        files.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(files)


def resolve_changed_files(files: list[str], *, base: str | None, head: str | None) -> list[str]:
    if files:
        return [item for item in files if item.strip()]
    if base and head:
        return _git_diff_name_only(base, head)
    return _git_current_candidate_files()


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


def collect_emitted_error_codes(repo_root: Path) -> list[str]:
    """Scan the authoritative emit modules for E0X / M0X / fallback literals.

    Read-only: opens each file and applies a regex. Returns the deduped list
    of codes found across all emit modules.
    """
    found: set[str] = set()
    for relative in _ERROR_CODE_EMIT_PATHS:
        path = repo_root / relative
        if not path.exists():
            continue
        for match in _ERROR_CODE_LITERAL_RE.finditer(path.read_text(encoding="utf-8")):
            found.add(match.group(1))
    return sorted(found)


def evaluate_emitted_error_codes() -> tuple[bool, str]:
    """Cross-check every emitted error code against ERROR_CODE_REGISTRY.

    Imports the registry lazily so the rest of the contract guard still runs
    when the registry module is broken or absent (e.g. early in a refactor).
    """
    codes = collect_emitted_error_codes(REPO_ROOT)
    if not codes:
        return True, "error-code-guard: no emit-site codes detected"

    try:
        from deeptutor.contracts.error_codes import check_emitted_error_codes, ContractGuardError
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"error-code-guard: registry import failed: {exc}"

    try:
        check_emitted_error_codes(codes)
    except ContractGuardError as exc:
        return False, f"error-code-guard: failed\n{exc}"
    return True, f"error-code-guard: passed | codes={', '.join(codes)}"


def collect_emitted_node_ids(repo_root: Path) -> list[str]:
    """Scan the authoritative emit modules for hard-coded 1A4XXXXX literals."""
    found: set[str] = set()
    for relative in _NODE_ID_SCAN_PATHS:
        path = repo_root / relative
        if not path.exists():
            continue
        for match in _NODE_ID_LITERAL_RE.finditer(path.read_text(encoding="utf-8")):
            found.add(match.group(1))
    return sorted(found)


def evaluate_emitted_node_ids() -> tuple[bool, str]:
    """Cross-check every hard-coded knowledge_node_id against the seed graph.

    No literal found is a passing condition — Phase -1 production code
    intentionally takes node_ids from data, not constants. The guard
    becomes load-bearing as soon as someone hard-codes a default or fallback.
    """
    node_ids = collect_emitted_node_ids(REPO_ROOT)
    if not node_ids:
        return True, "node-id-guard: no hard-coded knowledge_node_id literals found"

    try:
        from deeptutor.services.taxonomy.construction_learning_graph import (
            is_known_learning_graph_node,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"node-id-guard: graph seed import failed: {exc}"

    unknown = [node_id for node_id in node_ids if not is_known_learning_graph_node(node_id)]
    if unknown:
        return False, (
            "node-id-guard: failed\n"
            f"unregistered knowledge_node_id(s): {', '.join(unknown)} — "
            "add to deeptutor/services/taxonomy/construction_learning_graph.py "
            "(seed cluster) or remove the literal from emit-site source."
        )
    return True, f"node-id-guard: passed | node_ids={', '.join(node_ids)}"


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

    code_ok, code_message = evaluate_emitted_error_codes()
    code_stream = sys.stdout if code_ok else sys.stderr
    print(code_message, file=code_stream)

    node_ok, node_message = evaluate_emitted_node_ids()
    node_stream = sys.stdout if node_ok else sys.stderr
    print(node_message, file=node_stream)

    return 0 if (ok and code_ok and node_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
