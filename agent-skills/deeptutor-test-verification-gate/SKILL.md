---
name: deeptutor-test-verification-gate
description: "Defines DeepTutor test and evidence requirements. Use when implementing behavior, fixing bugs, changing docs or skills, validating release claims, or deciding whether a result is PASS, partial, blocked, or unverified."
---

# DeepTutor Test Verification Gate

Use this skill to make completion evidence-based.

## Workflow

1. Define the claim being tested in one sentence.
2. Choose the lowest sufficient evidence surface:
   - unit or contract test for deterministic logic;
   - integration test for service boundaries;
   - HTTP+WS smoke for chat control-plane behavior;
   - WeChat DevTools or real device for real package UI closure;
   - script/frontmatter/link validation for docs and skills;
   - GitHub Actions `Tests` plus same-SHA `Deploy Gate` for CI green claims;
   - release payload and public endpoints for deployment truth.
3. For bugs, write or identify a reproducer before fixing when practical.
4. Include at least one counterexample when the fix touches regex, fallback,
   routing, classifier, or semantic interpretation.
5. Run the command and preserve the exact command in the report.
6. Classify the result as `pass`, `partial`, `blocked`, or `not_exercised`.

## PASS Discipline

Do not report PASS when:

- only a script exited but the target surface was not exercised;
- DevTools `islogin` or `open --project` ran without a page scenario;
- near-real HTTP+WS is being substituted for real WeChat package closure;
- an observability runner succeeded but payload says `ready=false`;
- a `Tests` job passed but the same-SHA `Deploy Gate` failed or has not run;
- a doc or skill change was not validated for frontmatter and links.

## Verification

- [ ] The claim and evidence surface match.
- [ ] Exact commands are recorded.
- [ ] Counterexamples exist for overfit-prone changes.
- [ ] Unexercised surfaces are named explicitly.
