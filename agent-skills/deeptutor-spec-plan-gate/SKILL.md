---
name: deeptutor-spec-plan-gate
description: "Creates DeepTutor-local specs and implementation plans. Use when starting a new feature, roadmap slice, PRD, architecture decision, capability-status check, or any ambiguous multi-step task that should be grounded in docs/plan/INDEX.md instead of generic SPEC.md or tasks files."
---

# DeepTutor Spec Plan Gate

Use this skill to define work before coding without creating a second planning
system.

## Authority

- `AGENTS.md` defines process gates.
- `docs/plan/INDEX.md` maps canonical plan lanes.
- Existing PRD, implementation plan, checklist, or runbook files are the local
  source of truth for their lane.
- External specs are reference material only.

## Workflow

1. Read `docs/plan/INDEX.md` before writing or judging plan state.
2. Classify the task as `new lane`, `existing lane update`, `status audit`, or
   `implementation slice`.
3. Write the start frame:

```text
objective:
existing plan lane:
assumptions:
simplest path:
change boundary:
success criteria:
verification target:
not doing:
```

4. If a new plan file is needed, put it under `docs/plan/` in the matching
   lane. Do not create root `SPEC.md`, `tasks/plan.md`, or `tasks/todo.md`
   unless the user explicitly asks.
5. If the task is an audit, separate verified facts, partial evidence, and
   blind spots. Do not upgrade status to done without evidence.
6. Update `docs/plan/INDEX.md` whenever a plan file is added, renamed, or moved.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "A quick SPEC.md is easier." | DeepTutor plan authority lives in `docs/plan/`; stray specs become orphan truth. |
| "The implementation proves the plan is done." | Code presence is not release, WeChat, observability, or learner-truth closure. |
| "This is just a small plan note." | Small plan notes still need a canonical lane or they disappear from future agent context. |

## Verification

- [ ] `docs/plan/INDEX.md` was read for plan work.
- [ ] Added or changed plan files are linked from the index.
- [ ] Status claims separate done, partial, pending, and unverified.
- [ ] The plan names the verification surface and stop condition.
