---
name: deeptutor-code-simplification
description: "Simplifies DeepTutor code without behavior changes. Use when recently changed code works but is too complex, when review flags over-engineering, or when wrappers, fallbacks, abstractions, or branching can be reduced."
---

# DeepTutor Code Simplification

Use this skill only after behavior is understood and protected.

## Workflow

1. Name the behavior that must remain unchanged.
2. Identify tests or evidence that protect it.
3. Prefer deletion, demotion, and authority consolidation over new helpers.
4. Keep simplification scoped to recently changed or explicitly requested code.
5. Do not remove compatibility paths unless their callers and migration state
   are known.
6. Run the same focused tests before and after simplification.

## Good Simplification

- Deletes a duplicate decision point.
- Moves business policy out of a wrapper into the authority service.
- Replaces a generic abstraction with straightforward code.
- Removes a fallback that competed with canonical state.

## Bad Simplification

- Changes behavior while calling it cleanup.
- Rewrites style across unrelated files.
- Removes comments or guards without understanding why they exist.
- Optimizes line count at the cost of clarity.

## Verification

- [ ] Behavior preservation is stated.
- [ ] Existing tests still pass.
- [ ] Complexity net change is lower.
- [ ] Scope did not drift into unrelated cleanup.
