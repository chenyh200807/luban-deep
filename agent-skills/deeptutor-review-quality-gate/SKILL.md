---
name: deeptutor-review-quality-gate
description: "Reviews DeepTutor changes across correctness, authority, simplicity, security, performance, and verification. Use before merging, after agent-generated code, for self-review, or when asked to review a diff."
---

# DeepTutor Review Quality Gate

Use this skill as the default code-review stance for DeepTutor.

## Review Axes

1. Correctness: does the change satisfy the stated behavior and edge cases?
2. Authority: does one business fact still have one writer, store, reader, and
   terminal assembly path?
3. Simplicity: did the change add concepts, state, wrappers, or abstractions
   that are not earned?
4. Security: are auth, input, secrets, external data, and production boundaries
   still safe?
5. Performance: did the change add unbounded work, N+1 calls, worker storms, or
   frontend regressions?
6. Verification: would the tests and evidence catch the actual regression?

## Workflow

1. Read tests or evidence before implementation details.
2. Group findings by behavior and authority, not by file order.
3. Lead with actionable findings and file/line references.
4. Do not block on personal preference when the change improves local health.
5. If the diff touches schema, typed objects, env, DB, provider, process,
   route, or governance scanner wiring, also apply
   `deeptutor-schema-authority-gate` or `deeptutor-resource-registry-gate`.
6. Call out missing tests, unexercised surfaces, and dirty-worktree risk.

## Red Flags

- The diff mixes feature work with unrelated cleanup.
- Tests assert implementation details but not behavior.
- Release or WeChat claims are broader than the exercised surface.
- A fix adds a new reader, fallback, or mirror state.
- A review of schema/resource/env/provider/route changes skips the matching
  registry guard.

## Verification

- [ ] Findings are severity ordered.
- [ ] At least tests/evidence, authority, and scope were reviewed.
- [ ] Relevant schema/resource registry gates were applied or ruled out.
- [ ] No unverified PASS claim is accepted.
