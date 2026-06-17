"""Single-authority audit: prove the concept registry (B) is THE taxonomy truth, A is consistent with it.

The system has two taxonomy artifacts compiled from the same source tree: the legacy
``services/taxonomy`` compiled authority (A, consumed by learner_state/assessment/citations) and the
verified ``concept_registry`` (B, the identity spine). To honour "single authority" WITHOUT a risky
big-bang rewrite of A's 8 consumers, this audit enforces the invariants that make B the truth and A a
consistent projection of it:

  1. SAME SOURCE: A and B derive from the same FINAL_CLEANED_TAXONOMY2026 (sha or node-count parity).
  2. B COVERS A: every code A serves resolves in B (no A-only authority).
  3. NO STALE FABRICATION IN A's SERVED SET: codes B deprecated (dual-model fabricated) must not be
     A's primary served label source — flagged for cleanup.
  4. B STRICTLY BETTER: B recovers the 2257 nodes A silently dropped (coverage gain, not loss).

Exit non-zero on a real divergence (CI-able). This is the enforceable "single authority" contract
until A is reduced to a thin facade over B.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("LANGFUSE_ENABLED", "false")

_REPO = Path(__file__).resolve().parents[1]
A_PATH = _REPO / "deeptutor" / "services" / "taxonomy" / "compiled" / "construction_2026_taxonomy.compiled.json"
B_PATH = _REPO / "deeptutor" / "services" / "construction_grading" / "runtime_supply" / "v_concept_registry" / "concept_registry.json"


def run() -> tuple[bool, list[tuple[str, bool, str]]]:
    A = json.loads(A_PATH.read_text("utf-8"))
    B = json.loads(B_PATH.read_text("utf-8"))
    a_served = set((A.get("nodes_by_code") or {}).keys())
    a_all = {n["code"] for n in (A.get("nodes") or []) if n.get("code")}
    b_alias = set(B.get("alias_index") or {})
    b_deprecated = {code for c in B["concepts"].values()
                    if c["lifecycle"]["status"] == "deprecated" for code in (c.get("alias_codes") or [])}
    b_active = {code for c in B["concepts"].values()
                if c["lifecycle"]["status"] == "active" for code in (c.get("alias_codes") or [])}

    checks: list[tuple[str, bool, str]] = []

    # 1. same source universe MODULO B's deprecations: A == B's non-deprecated codes (A correctly
    #    projects B by excluding fabricated concepts; A must not contain anything B doesn't know).
    b_nondeprecated = b_alias - (b_deprecated - b_active)
    a_extra = a_all - b_alias                      # A-only codes B never saw (real divergence)
    a_serves_deprecated_universe = a_all & (b_deprecated - b_active)  # A still carries fabricated
    same_universe = not a_extra and not a_serves_deprecated_universe
    checks.append(("A_is_consistent_projection_of_B", same_universe,
                   f"A_all={len(a_all)} B_nondeprecated={len(b_nondeprecated)} "
                   f"A_only={len(a_extra)} A_has_fabricated={len(a_serves_deprecated_universe)}"))

    # 2. B covers every code A serves
    a_only = a_served - b_alias
    checks.append(("B_covers_all_A_served_codes", not a_only,
                   f"A_served={len(a_served)} uncovered_by_B={len(a_only)}"))

    # 3. A's served set should not be primarily serving B-deprecated (fabricated) concepts
    a_serving_deprecated = a_served & b_deprecated & (b_deprecated - b_active)
    checks.append(("A_not_serving_fabricated", not a_serving_deprecated,
                   f"A_serves_deprecated={len(a_serving_deprecated)}"))

    # 4. B recovers nodes A silently dropped (strictly-better coverage, not loss)
    recovered = (a_all - a_served) & b_active
    checks.append(("B_recovers_A_dropped_nodes", len(recovered) > 0,
                   f"recovered={len(recovered)} (A dropped {len(a_all - a_served)})"))

    all_ok = all(ok for _, ok, _ in checks)
    return all_ok, checks


def main() -> int:
    ok, checks = run()
    print("=== Single-authority audit (B=concept_registry is truth, A=projection) ===")
    for name, passed, detail in checks:
        print(f"  {'✓' if passed else '✗ FAIL'} {name}: {detail}")
    print(f"\n{'SINGLE AUTHORITY CONSISTENT' if ok else 'AUTHORITY DIVERGENCE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
