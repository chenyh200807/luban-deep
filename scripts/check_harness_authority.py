#!/usr/bin/env python3
"""Static guard against harness single-authority drift.

The "how to execute a turn" facts — which lifecycle *scene* a turn is, whether
to *ground*, and whether an *exact* answer applies — each have exactly one
canonical authority. The two execution shells (chat ``agentic_pipeline`` and
``tutorbot/agent/loop``) must *read* those authorities, never re-derive them.

This guard makes that contract enforceable so the re-judgement cannot creep
back in via a wrapper:

A. **No legacy scene re-judgement in the execution shells.** Scene authority is
   :data:`deeptutor.services.question_lifecycle_skills.SCENE_COMPOSITION` /
   ``resolve_question_lifecycle_scene_decision``; shells read
   ``context.metadata["question_lifecycle_scene" | "question_lifecycle_skill_names"]``.
   The shells must not reference the legacy
   ``detect_construction_exam_scene`` / ``get_construction_exam_skill_instruction``
   construction-scene detector.

B. **Single definition per authority.** ``SCENE_COMPOSITION`` (scene→skill map),
   ``build_grounding_decision`` (grounding), and ``should_force_exact_authority``
   (exact) must each be defined in exactly one module — their authority module.

Exit code is non-zero (red) on any violation, with the offending file:line, so
the gate fails the moment a second authority or a shell re-judgement appears.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "deeptutor"

# --- Rule A: execution shells must not re-judge scene via the legacy detector.
EXECUTION_SHELLS: tuple[str, ...] = (
    "deeptutor/agents/chat/agentic_pipeline.py",
    "deeptutor/tutorbot/agent/loop.py",
)
FORBIDDEN_SHELL_SYMBOLS: frozenset[str] = frozenset(
    {
        "detect_construction_exam_scene",
        "get_construction_exam_skill_instruction",
    }
)
# Legacy module the forbidden detectors live in (matched by trailing segment so
# `deeptutor.tutorbot.teaching_modes` and a bare `teaching_modes` both resolve).
FORBIDDEN_MODULE_SUFFIX = "teaching_modes"

# --- Rule B: each authority is defined exactly once, in its authority module.
@dataclass(frozen=True)
class SingleAuthorityDef:
    label: str
    pattern: str  # anchored at line start
    expected_file: str


SINGLE_AUTHORITY_DEFS: tuple[SingleAuthorityDef, ...] = (
    SingleAuthorityDef(
        label="scene→skill map (SCENE_COMPOSITION)",
        pattern=r"^SCENE_COMPOSITION\s*[:=]",
        expected_file="deeptutor/services/question_lifecycle_skills.py",
    ),
    SingleAuthorityDef(
        label="grounding authority (build_grounding_decision)",
        pattern=r"^def build_grounding_decision\s*\(",
        expected_file="deeptutor/services/query_intent.py",
    ),
    SingleAuthorityDef(
        label="exact authority (should_force_exact_authority)",
        pattern=r"^def should_force_exact_authority\s*\(",
        expected_file="deeptutor/services/rag/exact_authority.py",
    ),
)


def _iter_python_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def _is_forbidden_module(name: str | None) -> bool:
    return bool(name) and name.split(".")[-1] == FORBIDDEN_MODULE_SUFFIX


def _attr_root_name(node: ast.expr) -> str | None:
    """Resolve the owner name of an attribute access: `tm.x` -> 'tm',
    `a.b.teaching_modes.x` -> 'teaching_modes'."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _scan_shell_file_ast(rel: str, source: str) -> list[str]:
    """AST (not text) scan: flag actual import bindings / attribute-access calls
    of the legacy scene detectors — alias-proof, and without false-positives on
    docstrings/comments that merely mention the symbol.

    Out of scope (no static check can catch this; runtime enforcement is
    deliberately not built per the project's thin-wrapper / less-is-more rule):
    fully dynamic access such as ``getattr(mod, "detect_" + "...")``.
    """
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:  # fail-safe: unparseable shell cannot be verified
        return [f"{rel}: AST parse failed ({exc}); cannot verify scene authority"]

    violations: list[str] = []
    module_aliases: set[str] = set()  # local names bound to the teaching_modes module

    for node in ast.walk(tree):
        # (1) from ...teaching_modes import <forbidden> [as alias]  — alias-proof.
        if isinstance(node, ast.ImportFrom) and _is_forbidden_module(node.module):
            for alias in node.names:
                if alias.name in FORBIDDEN_SHELL_SYMBOLS:
                    as_part = f" as `{alias.asname}`" if alias.asname else ""
                    violations.append(
                        f"{rel}:{node.lineno}: execution shell imports legacy scene "
                        f"detector `{alias.name}`{as_part} — read "
                        f"context.metadata['question_lifecycle_scene'] instead"
                    )
        # (2) import ...teaching_modes [as alias]  — remember the bound name.
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden_module(alias.name):
                    module_aliases.add(alias.asname or alias.name.split(".")[0])

    # (3) attribute-access calls: <teaching_modes alias|name>.<forbidden>.
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_SHELL_SYMBOLS:
            root = _attr_root_name(node.value)
            if root in module_aliases or root == FORBIDDEN_MODULE_SUFFIX:
                violations.append(
                    f"{rel}:{node.lineno}: execution shell calls legacy scene "
                    f"detector `{root}.{node.attr}` — read "
                    f"context.metadata['question_lifecycle_scene'] instead"
                )
    return violations


def _scan_shell_rejudgement() -> list[str]:
    violations: list[str] = []
    for rel in EXECUTION_SHELLS:
        path = PROJECT_ROOT / rel
        if not path.exists():
            violations.append(f"{rel}: execution shell missing (guard cannot verify)")
            continue
        violations.extend(_scan_shell_file_ast(rel, path.read_text(encoding="utf-8")))
    return violations


def _scan_single_authority(files: list[Path]) -> list[str]:
    violations: list[str] = []
    for spec in SINGLE_AUTHORITY_DEFS:
        pattern = re.compile(spec.pattern, re.MULTILINE)
        hits: list[str] = []
        for path in files:
            text = path.read_text(encoding="utf-8")
            if pattern.search(text):
                hits.append(str(path.relative_to(PROJECT_ROOT)))
        if not hits:
            violations.append(f"{spec.label}: definition not found (expected {spec.expected_file})")
        elif len(hits) > 1:
            violations.append(
                f"{spec.label}: defined in multiple modules {hits} — single authority required"
            )
        elif hits[0] != spec.expected_file:
            violations.append(
                f"{spec.label}: defined in {hits[0]}, expected authority module {spec.expected_file}"
            )
    return violations


def main() -> int:
    files = _iter_python_files()
    violations = _scan_shell_rejudgement() + _scan_single_authority(files)

    if violations:
        print("harness authority guard: FAIL", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    print("harness authority guard: OK (single scene/grounding/exact authority)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
