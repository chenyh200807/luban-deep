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

# WebSocket single-control-plane allowlist gate (contracts/turn.md:22). The
# evaluator reflects the live app and degrades to a pass-with-note when server
# deps are absent (the lightweight contract-guard job); the dedicated workflow
# step installs server deps so the reflection runs for real.
from scripts.ci.check_websocket_route_allowlist import (  # noqa: E402
    evaluate_websocket_route_allowlist,
)

# Schema-registry register-before-use, wired into the ONE runner (P0#1 of the schema-
# governance closure). The standalone `--closure` CI step catches orphan IDs full-tree;
# this changed-files entry adds per-PR drift-field + authority-completeness enforcement so
# a grading schema can't drift its fields / lose authority_source in a touched file.
from scripts.check_schema_registry import evaluate_schema_registry  # noqa: E402

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

# Question lifecycle authority guard. The orchestrator is the only runtime
# route authority. A few downstream files may mirror the canonical scene into
# trace / observer payloads, but executors must not call the legacy attach or
# derive helpers to decide a scene on their own.
_QUESTION_LIFECYCLE_APPROVED_SCENE_WRITERS: frozenset[str] = frozenset(
    {
        "deeptutor/runtime/orchestrator.py",
        "deeptutor/services/question_lifecycle_skills.py",
        "deeptutor/capabilities/deep_question.py",
        "deeptutor/services/session/turn_runtime.py",
    }
)
_QUESTION_LIFECYCLE_SERVICE_PATH = "deeptutor/services/question_lifecycle_skills.py"
_QUESTION_LIFECYCLE_SCENE_WRITE_RE = re.compile(
    r"(?:metadata|context\.metadata|trace_meta|summary)\[['\"]question_lifecycle_scene['\"]\]\s*="
)
_QUESTION_LIFECYCLE_FORBIDDEN_CALLS: tuple[str, ...] = (
    "attach_question_lifecycle_scene_to_context",
    "derive_question_lifecycle_scene",
)

# Upstream absorption guard. HKUDS/DeepTutor v1.4.3 introduces useful
# implementation patterns, but these upstream product concepts are not allowed
# to become production authorities in this fork without an explicit contract
# redesign:
# - Partners must not replace or sit beside TutorBot as the business identity.
# - /api/v1/partners must not become a chat/control-plane route; chat remains
#   under /api/v1/ws.
# - upstream's standalone deeptutor.learning runtime must not become a second
#   Learning Brain / learner-memory authority.
_UPSTREAM_FORBIDDEN_PATHS: tuple[tuple[str, str], ...] = (
    (
        "deeptutor/partners",
        "deeptutor/partners is forbidden in production code: TutorBot remains the business identity.",
    ),
    (
        "deeptutor/partners.py",
        "deeptutor/partners.py is forbidden in production code: TutorBot remains the business identity.",
    ),
    (
        "deeptutor/services/partners",
        "deeptutor/services/partners is forbidden in production code: keep partner-like channels as TutorBot adapters.",
    ),
    (
        "deeptutor/services/partners.py",
        "deeptutor/services/partners.py is forbidden in production code: keep partner-like channels as TutorBot adapters.",
    ),
    (
        "deeptutor/api/routers/partners",
        "deeptutor/api/routers/partners is forbidden: do not add /api/v1/partners beside /api/v1/ws.",
    ),
    (
        "deeptutor/api/routers/partners.py",
        "deeptutor/api/routers/partners.py is forbidden: do not add /api/v1/partners beside /api/v1/ws.",
    ),
    (
        "deeptutor/learning",
        "deeptutor/learning is forbidden as a standalone runtime: use Learning Brain / learner_state authority.",
    ),
    (
        "deeptutor/learning.py",
        "deeptutor/learning.py is forbidden as a standalone runtime: use Learning Brain / learner_state authority.",
    ),
)
_UPSTREAM_FORBIDDEN_ROUTE_RE = re.compile(r"['\"]\/api\/v1\/partners(?:\/|\b)")


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


def _iter_question_lifecycle_python_files(repo_root: Path) -> list[Path]:
    source_root = repo_root / "deeptutor"
    if not source_root.exists():
        return []
    return sorted(path for path in source_root.rglob("*.py") if path.is_file())


# G4: evidence_source emit-site register-before-use.
# learner_memory ``learning_evidence`` events may only carry an evidence_source from
# ``contracts/index.yaml:learning_state_inference.allowed_evidence_sources``. An
# unregistered hard-coded evidence_source literal makes ``learning_synthesis`` (which
# filters by source) SILENTLY DROP that evidence. No literal found is a passing
# condition — production reads the value from data, not constants; the guard becomes
# load-bearing the moment someone hard-codes an unrecognized source.
_EVIDENCE_SOURCE_SCAN_DIRS: tuple[str, ...] = (
    "deeptutor/services/learner_state",
    "deeptutor/services/construction_grading",
)
_EVIDENCE_SOURCE_EMIT_RE = re.compile(r'"evidence_source"\s*:\s*"([a-z_]+)"')


def _allowed_evidence_sources(repo_root: Path = REPO_ROOT) -> set[str]:
    """Read the canonical allowed set from contracts/index.yaml (repo_root scoped)."""
    index_path = repo_root / "contracts" / "index.yaml"
    payload = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    lsi = payload.get("learning_state_inference") or {}
    return {str(item) for item in (lsi.get("allowed_evidence_sources") or [])}


def collect_emitted_evidence_sources(repo_root: Path = REPO_ROOT) -> dict[str, list[str]]:
    """Map each hard-coded ``"evidence_source": "<literal>"`` value -> emit-site locations.

    The regex matches only the dict-emit form, so reader comparisons
    (``payload.get("evidence_source") == ...``) and source_feature pass-throughs
    (``"evidence_source": str(...)``) are intentionally NOT captured.
    """
    found: dict[str, list[str]] = {}
    for rel_dir in _EVIDENCE_SOURCE_SCAN_DIRS:
        base = repo_root / rel_dir
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if "test" in path.name:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(text.splitlines(), start=1):
                for match in _EVIDENCE_SOURCE_EMIT_RE.finditer(line):
                    location = f"{path.relative_to(repo_root).as_posix()}:{lineno}"
                    found.setdefault(match.group(1), []).append(location)
    return found


def evaluate_emitted_evidence_sources(repo_root: Path = REPO_ROOT) -> tuple[bool, str]:
    """Cross-check every hard-coded evidence_source literal against the
    contracts/index.yaml allowed set (G4 register-before-use).

    No literal found is a passing condition. Fails closed if the allowed set is
    unreadable/empty so a missing registry cannot silently disable the gate.
    """
    emitted = collect_emitted_evidence_sources(repo_root)
    if not emitted:
        return True, "evidence-source-guard: no hard-coded evidence_source literals found"
    allowed = _allowed_evidence_sources(repo_root)
    if not allowed:
        return False, (
            "evidence-source-guard: failed — contracts/index.yaml "
            "learning_state_inference.allowed_evidence_sources is empty or unreadable"
        )
    unknown = {value: locs for value, locs in emitted.items() if value not in allowed}
    if unknown:
        detail = "; ".join(
            f"{value} @ {', '.join(sorted(locs))}" for value, locs in sorted(unknown.items())
        )
        return False, (
            "evidence-source-guard: failed\n"
            f"unregistered evidence_source literal(s): {detail} — add to contracts/index.yaml "
            "learning_state_inference.allowed_evidence_sources or remove the emit-site literal."
        )
    return True, (
        f"evidence-source-guard: passed | evidence_sources={', '.join(sorted(emitted))}"
    )


def evaluate_question_lifecycle_authority(repo_root: Path = REPO_ROOT) -> tuple[bool, str]:
    """Fail when production code introduces a competing lifecycle authority."""

    failures: list[str] = []
    scene_write_count = 0
    for path in _iter_question_lifecycle_python_files(repo_root):
        relative = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if _QUESTION_LIFECYCLE_SCENE_WRITE_RE.search(stripped):
                scene_write_count += 1
                if relative not in _QUESTION_LIFECYCLE_APPROVED_SCENE_WRITERS:
                    failures.append(
                        f"{relative}:{lineno}: question_lifecycle_scene writer outside authority: {stripped[:140]}"
                    )
            for call_name in _QUESTION_LIFECYCLE_FORBIDDEN_CALLS:
                call_token = f"{call_name}("
                if call_token not in stripped:
                    continue
                if stripped.startswith(f"def {call_name}("):
                    continue
                if relative == _QUESTION_LIFECYCLE_SERVICE_PATH:
                    continue
                failures.append(
                    f"{relative}:{lineno}: competing lifecycle call {call_name}: {stripped[:140]}"
                )

    if failures:
        return False, "question-lifecycle-authority-guard: failed\n" + "\n".join(failures)
    return True, (
        "question-lifecycle-authority-guard: passed | "
        f"approved_scene_writes={scene_write_count}"
    )


def evaluate_upstream_authority_absorption(repo_root: Path = REPO_ROOT) -> tuple[bool, str]:
    """Fail when upstream v1.4.x concepts are copied in as new authorities.

    The scan is deliberately limited to production code under ``deeptutor/``.
    Plans and docs may discuss upstream names; runtime code must keep those
    concepts demoted to patterns, candidates, or TutorBot adapters.
    """

    failures: list[str] = []
    for relative, message in _UPSTREAM_FORBIDDEN_PATHS:
        path = repo_root / relative
        if path.exists():
            failures.append(f"{relative}: {message}")

    source_root = repo_root / "deeptutor"
    if source_root.exists():
        for path in sorted(source_root.rglob("*.py")):
            relative = path.relative_to(repo_root).as_posix()
            text = path.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if _UPSTREAM_FORBIDDEN_ROUTE_RE.search(line):
                    failures.append(
                        f"{relative}:{lineno}: /api/v1/partners must not become a production route; chat/control-plane traffic stays on /api/v1/ws."
                    )

    if failures:
        return False, "upstream-authority-absorption-guard: failed\n" + "\n".join(failures)
    return True, "upstream-authority-absorption-guard: passed"


_ROUTE_MODEL_CLASS_RE = re.compile(r"^class ([A-Za-z_][A-Za-z0-9_]*)\([^)]*BaseModel")


def evaluate_route_model_uniqueness(repo_root: Path = REPO_ROOT) -> tuple[bool, str]:
    """Fail when an API route pydantic model NAME is defined in more than one router.

    Two routers defining a same-named ``BaseModel`` (e.g. two ``CreateSessionRequest`` with
    DIFFERENT field shapes) is a silent collision: FastAPI auto-suffixes them in the OpenAPI
    components and a reader/tool cannot tell which shape a name denotes. Each route-model name
    must map to ONE definition — import one shared owner, or rename to disambiguate. This brings
    the api/router schema surface (the largest previously-ungoverned schema class) into the one
    contract-guard runner, no second system (schema-governance P3#10).
    """
    routers_root = repo_root / "deeptutor" / "api" / "routers"
    if not routers_root.exists():
        return True, "route-model-uniqueness-guard: no routers dir"
    by_name: dict[str, list[str]] = {}
    for path in sorted(routers_root.rglob("*.py")):
        relative = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            match = _ROUTE_MODEL_CLASS_RE.match(line)
            if match:
                by_name.setdefault(match.group(1), []).append(relative)
    dupes = {name: files for name, files in by_name.items() if len(files) > 1}
    if dupes:
        detail = "\n".join(
            f"  '{name}' defined in: {', '.join(files)}" for name, files in sorted(dupes.items())
        )
        return False, (
            "route-model-uniqueness-guard: failed — same-named route pydantic model defined in "
            "≥2 routers (rename to disambiguate, or import one shared definition):\n" + detail
        )
    return True, (
        f"route-model-uniqueness-guard: passed | {len(by_name)} route models, all names unique"
    )


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

    lifecycle_ok, lifecycle_message = evaluate_question_lifecycle_authority()
    lifecycle_stream = sys.stdout if lifecycle_ok else sys.stderr
    print(lifecycle_message, file=lifecycle_stream)

    upstream_ok, upstream_message = evaluate_upstream_authority_absorption()
    upstream_stream = sys.stdout if upstream_ok else sys.stderr
    print(upstream_message, file=upstream_stream)

    ws_ok, ws_message = evaluate_websocket_route_allowlist()
    ws_stream = sys.stdout if ws_ok else sys.stderr
    print(ws_message, file=ws_stream)

    # Schema-registry register-before-use on the changed files (P0#1): per-PR drift +
    # authority enforcement now lives in the one runner, not only the full-tree --closure step.
    schema_ok, schema_message = evaluate_schema_registry(changed_files)
    schema_stream = sys.stdout if schema_ok else sys.stderr
    print(schema_message, file=schema_stream)

    route_model_ok, route_model_message = evaluate_route_model_uniqueness()
    route_model_stream = sys.stdout if route_model_ok else sys.stderr
    print(route_model_message, file=route_model_stream)

    evidence_ok, evidence_message = evaluate_emitted_evidence_sources()
    evidence_stream = sys.stdout if evidence_ok else sys.stderr
    print(evidence_message, file=evidence_stream)

    return 0 if (ok and code_ok and node_ok and lifecycle_ok
                 and upstream_ok and ws_ok and schema_ok and route_model_ok
                 and evidence_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
