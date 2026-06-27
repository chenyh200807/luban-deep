#!/usr/bin/env python3
"""QTPK import-allowlist guard (QTPK physical extraction plan, S0).

The Question-Turn Policy Kernel (``deeptutor/services/question_turn_policy.py``)
is a read-only forwarder over the canonical question-turn resolvers. Its
single-authority value collapses the moment it grows a sixth class of fact, so
its import surface is locked to a god-object red line: QTPK may ONLY import the
canonical question-turn resolver modules + the standard library; it MUST NOT
import any LLM client, grading kernel, RAG / retrieval, learner-state,
reveal/answer-reveal, terminal-result / visible-output, stream / transport,
orchestrator, or turn_runtime module.

This guard AST-scans the QTPK module's ``import`` / ``from ... import``
statements (alias-proof, no docstring/comment false-positives) and:

  * ALLOWS imports whose top-level module is the standard library, or one of the
    four canonical question-turn resolver modules (semantic_router /
    question_lifecycle_skills / active_object_builder / question_followup), or a
    pure type/dataclass helper (``typing`` / ``dataclasses`` / ``__future__``).
  * FORBIDS any import whose module path matches a forbidden substring
    (llm / grading kernel / rag / learner_state / reveal / terminal /
    stream / orchestrator / turn_runtime).
  * FAIL-CLOSED: any deeptutor.* import that is neither explicitly allowed nor
    explicitly forbidden is rejected — a new internal dependency cannot slip in
    unreviewed.

Exit codes:
  0  clean (every import in the QTPK module is on the allowlist)
  2  fail-closed: a forbidden / unreviewed import is present, OR the QTPK module
     is missing / unparseable.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QTPK_MODULE = PROJECT_ROOT / "deeptutor" / "services" / "question_turn_policy.py"

# Canonical question-turn resolver modules QTPK is allowed to forward to.
# Matched on the *full* dotted module path's trailing segment so an alias-import
# of ``deeptutor.services.semantic_router`` is recognised regardless of depth.
_ALLOWED_DEEPTUTOR_MODULES: frozenset[str] = frozenset(
    {
        "deeptutor.services.semantic_router",
        "deeptutor.services.question_lifecycle_skills",
        "deeptutor.services.active_object_builder",
        "deeptutor.services.question_followup",
    }
)

# Standard-library / pure type+dataclass top-level modules that are always fine.
_ALLOWED_STDLIB_ROOTS: frozenset[str] = frozenset(
    {
        "__future__",
        "typing",
        "dataclasses",
        "collections",
        "collections.abc",
        "abc",
        "enum",
        "functools",
        "itertools",
        "copy",
        "re",
        "json",
        "math",
        "datetime",
        "decimal",
        "logging",
        "dataclass",
    }
)

# Forbidden import substrings — the god-object red line. If any of these appear
# anywhere in a deeptutor.* module path, the import is rejected outright (even if
# it would otherwise be a fail-closed "unreviewed" case — these get a clearer
# message).
_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "llm",
    "grading",
    "rag",
    "retrieval",
    "learner_state",
    "learner",
    "reveal",
    "terminal_result",
    "terminal",
    "user_visible_output",
    "visible_output",
    "stream_bus",
    "stream",
    "orchestrator",
    "turn_runtime",
)


def _imported_module_paths(tree: ast.AST) -> list[tuple[str, int]]:
    """Return ``(module_path, lineno)`` for every import in the tree.

    ``import a.b.c`` -> ``a.b.c``. For ``from a.b import c`` the resolved target
    can be either the module ``a.b`` (when ``c`` is a name) OR the submodule
    ``a.b.c`` (when ``c`` is itself a module, e.g.
    ``from deeptutor.services import active_object_builder``). We cannot tell
    statically which, so for a from-import we emit the ``module.name`` candidate
    when ``module.name`` is an explicitly allowed canonical module; otherwise we
    emit the package ``module`` (keeping the conservative fail-closed default for
    everything else).
    """
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            # Relative imports (``from . import x``) have module possibly None.
            module = node.module or ""
            # ``from <module> import a, b`` — ``a``/``b`` may be names OR
            # submodules. Emit one candidate path PER imported name so a
            # forbidden submodule sharing a line with an allowed one is still
            # caught: prefer the ``module.name`` path when it is the resolved
            # target (allowed canonical or forbidden-substring submodule),
            # otherwise fall back to the package ``module`` path.
            for alias in node.names:
                candidate = f"{module}.{alias.name}" if module else alias.name
                if candidate in _ALLOWED_DEEPTUTOR_MODULES:
                    out.append((candidate, node.lineno))
                elif module and _forbidden_reason(alias.name) is not None:
                    out.append((candidate, node.lineno))
                else:
                    out.append((module, node.lineno))
    return out


def _is_allowed(module_path: str) -> bool:
    if not module_path:
        # ``from . import x`` — relative import inside the package; treat as
        # unreviewed (fail-closed) since we cannot resolve the target module.
        return False
    if module_path in _ALLOWED_DEEPTUTOR_MODULES:
        return True
    root = module_path.split(".")[0]
    if module_path in _ALLOWED_STDLIB_ROOTS or root in _ALLOWED_STDLIB_ROOTS:
        return True
    return False


def _forbidden_reason(module_path: str) -> str | None:
    lowered = module_path.lower()
    for sub in _FORBIDDEN_SUBSTRINGS:
        if sub in lowered:
            return sub
    return None


def evaluate_qtpk_imports(source: str, rel: str) -> list[str]:
    """Return a list of violation strings for one QTPK source string.

    Empty list == clean. Raises ``SyntaxError`` for an unparseable source
    (callers fail-closed on that).
    """
    tree = ast.parse(source, filename=rel)
    violations: list[str] = []
    for module_path, lineno in _imported_module_paths(tree):
        if _is_allowed(module_path):
            continue
        forbidden = _forbidden_reason(module_path)
        if forbidden is not None:
            violations.append(
                f"{rel}:{lineno}: FORBIDDEN import '{module_path}' "
                f"(matched god-object red-line substring '{forbidden}') — QTPK must "
                f"not import LLM/grading/RAG/learner-state/reveal/terminal/stream/"
                f"orchestrator/turn_runtime."
            )
        else:
            violations.append(
                f"{rel}:{lineno}: UNREVIEWED import '{module_path}' is not on the "
                f"QTPK allowlist (canonical question-turn resolvers + stdlib only). "
                f"Add it to the allowlist with review, or remove it (fail-closed)."
            )
    return violations


def _scan() -> list[str]:
    if not QTPK_MODULE.exists():
        return [
            f"{QTPK_MODULE.relative_to(PROJECT_ROOT)}: QTPK module missing — "
            f"guard cannot verify (fail-closed)."
        ]
    rel = str(QTPK_MODULE.relative_to(PROJECT_ROOT))
    try:
        return evaluate_qtpk_imports(QTPK_MODULE.read_text(encoding="utf-8"), rel)
    except SyntaxError as exc:  # unparseable -> cannot verify -> fail-closed
        return [f"{rel}: AST parse failed ({exc}); cannot verify QTPK imports"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="gate mode: fail (exit 2) on any forbidden/unreviewed QTPK import",
    )
    parser.parse_args(argv)

    violations = _scan()
    if violations:
        print("qtpk-import-allowlist-guard: FAIL", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 2

    print(
        "qtpk-import-allowlist-guard: OK "
        "(QTPK imports only canonical question-turn resolvers + stdlib)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
