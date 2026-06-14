---
name: deeptutor-incremental-implementation
description: "Guides DeepTutor multi-file implementation in small verified slices. Use when changing more than one file, building a feature, refactoring behavior, or when a task is large enough that one broad patch would hide risk."
---

# DeepTutor Incremental Implementation

Use this skill to keep implementation narrow, reviewable, and always
verifiable.

## Start Frame

```text
slice goal:
files allowed:
files explicitly not touched:
authority service:
wrapper boundary:
test to run:
rollback point:
```

## Workflow

1. Lock context with `pwd -P`, git toplevel, and `git status --short --branch`.
2. Pick one vertical or risk-first slice. Avoid broad framework setup.
3. For each touched wrapper, state the fat authority it delegates to.
4. Implement the smallest complete slice.
5. Run the focused test or validation for that slice before expanding scope.
6. Re-check diff for unrelated formatting, import churn, or opportunistic
   cleanup.
7. Leave unrelated dirty files untouched and unstaged.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "I'll wire all layers first, then test." | DeepTutor failures often hide in one boundary; test the first slice early. |
| "This refactor is nearby." | Nearby is not in scope unless it is required for the slice. |
| "A generic abstraction will help later." | Add abstractions only after current duplication or complexity earns them. |

## Verification

- [ ] One logical slice is complete.
- [ ] Focused tests or validations ran.
- [ ] Diff is limited to declared files and behavior.
- [ ] Wrapper/fat authority split is preserved.
