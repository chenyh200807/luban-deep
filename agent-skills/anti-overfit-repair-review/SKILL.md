---
name: anti-overfit-repair-review
description: Use this after DeepTutor repairs that add regex, fallback, classifiers, wrappers, route guards, prompt shortcuts, special cases, or tests based on a narrow QA phrase. Use it when the user asks whether a fix was over-repaired, too rule-based, less flexible, or should be reverted.
---

# Anti-Overfit Repair Review

Use this skill to decide whether a repair restored authority or merely patched
a symptom.

## Review Frame

For each changed behavior, answer:

```text
reported symptom:
intended business fact:
actual authority after fix:
new regex / fallback / classifier / wrapper:
stable format or semantic intent:
counterexamples tested:
complexity net change:
keep / refactor / revert:
```

## What Counts as Acceptable Regex

Regex or deterministic markers are acceptable when they identify a stable,
low-ambiguity boundary:

- numbered item identity, not answer authorization
- option letters and complete option-table surfaces
- explicit negation of answer reveal
- clear free-text case grading anchors such as `案例：...我的答案...批改`

They are suspicious when they decide broad semantic intent:

- whether a learner is asking a deep conceptual question
- whether a current active question should be detached
- whether an expression should be shortened based on one sample phrase
- whether RAG/LLM should override existing question authority

## Review Process

1. Read the diff, not only the passing test.
2. Group changes by authority fact, not by file.
3. For each group, identify whether the change:
   - restores a canonical path
   - removes a competing reader
   - narrows a wrapper
   - or adds a new decision point
4. Look for hard-coded QA expressions, exact wording, fixed values, and domain-specific shortcuts.
5. Add or check counterexamples with similar words but opposite intent.
6. Decide local repair versus whole-commit revert.

## Keep / Refactor / Revert

- **Keep** when the fix makes the authority path more direct and tests include counterexamples.
- **Refactor** when the direction is right but the code hard-codes a sample phrase or value.
- **Revert the whole commit** only when the commit creates a new authority, new route, new truth source, or changes unrelated surfaces in a way that cannot be cleanly separated.

If a commit is large and partly good, prefer:

```text
keep good authority changes
record the bad slice
repair the bad slice directly
add negative tests
avoid broad revert
```

## Required Counterexamples

Choose at least one:

- suppress answer reveal: `先不要公布答案`
- missing active object: `我说了在题卡里，你就发答案`
- existing active object with the same phrase
- out-of-range item index: `公布第3题答案` when only 2 items exist
- source/reference request without answer reveal
- option challenge vs answer submission
- expression brevity request vs grading correctness

## Output

Use:

```text
Overfit verdict:
Kept:
Refactored:
Reverted:
Regex boundaries:
Counterexamples:
Residual risk:
```
