#!/usr/bin/env python3
"""Submission / relation gate authority guard — fail-on-new drift gate.

Context (contracts/turn.md §硬约束 24, Context-Continuity 不变量): a turn's relation
to prior conversation context — "is this a submission / which question is it about /
is it an answer at all" — must be decided ONCE by the canonical authority
(`semantic_router.build_turn_semantic_decision` for relation, `question_followup`'s
symmetric submission guard for answer extraction). The recurring "切链路丢上下文/失忆/
鸡同鸭讲" class came from ~15+ independent `_looks_like_*` regex/heuristic gates that
EACH re-decide this on the raw user message; any one mis-firing routes a context-
dependent turn into a dead path.

This scanner is the **止血 (drift-prevention) layer**, NOT the semantic closure. The
true closure is the runtime migration that collapses those gates so every layer reads
the single canonical decision (see
docs/plan/题目生命周期与助教运行时/2026-06-20-cross-capability-context-continuity-architecture.md
§剩余迁移). What this gate guarantees: a NEW independent submission/relation gate cannot
land silently — it fails CI unless the author either (a) routes through the canonical
authority instead, or (b) explicitly adds the new gate to the baseline with reviewer
sign-off (referencing the approving PR). All existing gates are grandfathered.

A `_looks_like_*` function counts as a submission/relation gate when its name carries a
submission/answer/relation-decision keyword (see ``_GATE_KEYWORDS``). Detection is
AST-level (def name), so renaming/import aliasing cannot smuggle one past the gate.

Usage:
    python scripts/check_submission_relation_gate_authority.py --all   # CI: scan repo
    python scripts/check_submission_relation_gate_authority.py --write-baseline  # regen
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "scripts/ci/baselines/submission_relation_gates_baseline.txt"

# Submission / relation-decision intent keywords. A `def _looks_like_<name>` whose name
# contains any of these is a gate that re-decides "is this a submission / which question".
_GATE_KEYWORDS = (
    "submission",
    "answer",
    "mcq",
    "grading",
    "option",
    "switch",
    "followup",
    "generation",
    "practice",
    "concession",
    "reveal",
    "free_text",
    "question",
    "anchor",
    "case_grading",
    "explanation_request",
)

# Files allowed to host the canonical decision helpers without baseline-tracking is NOT
# done here on purpose: even the single-source files' gates are grandfathered via the
# baseline, so adding a brand-new gate anywhere (incl. those files) still requires review.
_SCAN_DIRS = ("deeptutor",)


def _is_gate_name(name: str) -> bool:
    if not name.startswith("_looks_like_"):
        return False
    lowered = name.lower()
    return any(kw in lowered for kw in _GATE_KEYWORDS)


def _iter_py_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--", *(f"{d}/**/*.py" for d in _SCAN_DIRS)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    files = [REPO_ROOT / line for line in out.stdout.splitlines() if line.strip()]
    if files:
        return files
    # fallback: rglob
    result: list[Path] = []
    for d in _SCAN_DIRS:
        result.extend((REPO_ROOT / d).rglob("*.py"))
    return result


def collect_gate_keys() -> list[str]:
    keys: list[str] = []
    for path in _iter_py_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_gate_name(node.name):
                keys.append(f"{rel}::{node.name}")
    return sorted(set(keys))


def _read_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {
        line.strip()
        for line in BASELINE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="scan whole repo (CI mode)")
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="regenerate the baseline from the current tree (requires reviewer sign-off)",
    )
    args = parser.parse_args(argv)

    keys = collect_gate_keys()

    if args.write_baseline:
        header = (
            "# Submission / relation gate authority baseline (fail-on-new).\n"
            "# Each line: <relpath>::<funcname> of an existing _looks_like_* gate that\n"
            "# independently decides submission/relation intent. Grandfathered debt; the\n"
            "# guard fails on any NEW gate not listed here. Never hand-edit to silence a\n"
            "# new gate — route through the canonical authority (turn_semantic_decision /\n"
            "# question_followup single guard) or regenerate with reviewer sign-off + the\n"
            "# approving PR. See contracts/turn.md §硬约束 24.\n"
        )
        BASELINE.write_text(header + "\n".join(keys) + "\n", encoding="utf-8")
        print(f"[write-baseline] wrote {len(keys)} keys to {BASELINE.relative_to(REPO_ROOT)}")
        return 0

    baseline = _read_baseline()
    if not baseline:
        print(
            "[FAIL] baseline not found/empty: "
            f"{BASELINE.relative_to(REPO_ROOT)} — regenerate with --write-baseline",
            file=sys.stderr,
        )
        return 1

    new_gates = [k for k in keys if k not in baseline]
    removed = sorted(baseline - set(keys))

    if new_gates:
        print(
            "[FAIL] new independent submission/relation gate(s) detected — these re-decide\n"
            "  'is this a submission / which question' outside the canonical authority and\n"
            "  reintroduce the cross-capability context-loss class (contracts/turn.md §24):",
            file=sys.stderr,
        )
        for k in new_gates:
            print(f"    + {k}", file=sys.stderr)
        print(
            "  → Route the decision through the canonical authority\n"
            "    (semantic_router.build_turn_semantic_decision / question_followup's single\n"
            "    submission guard) instead of a new _looks_like_* gate. If genuinely needed,\n"
            "    regenerate the baseline (--write-baseline) with reviewer sign-off + PR ref.",
            file=sys.stderr,
        )
        return 1

    note = f" ({len(removed)} baselined gate(s) removed — consider trimming baseline)" if removed else ""
    print(f"[OK] no new submission/relation gates; {len(keys)} gates grandfathered{note}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
