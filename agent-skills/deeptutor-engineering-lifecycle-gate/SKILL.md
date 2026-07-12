---
name: deeptutor-engineering-lifecycle-gate
description: "Use this as the DeepTutor dispatcher for non-trivial engineering work: new features, bug fixes, multi-file changes, contract/API changes, docs or plan updates, reviews, release preparation, or requests to adopt external agent skill packs such as addyosmani/agent-skills. It translates generic agent engineering workflows into DeepTutor authority, verification, and guardrail requirements."
---

# DeepTutor Engineering Lifecycle Gate

Use this skill to turn general agent engineering discipline into DeepTutor-local
execution. It absorbs the useful mechanics of external skill packs without
letting them become a second authority.

## Non-Negotiable Authority Order

1. User instruction for the current task.
2. `AGENTS.md` hard gates and project rules.
3. `CONTRACT.md` and `contracts/index.yaml` for chat, TutorBot, trace,
   session, stream, replay, resume, or public boundary changes.
4. `docs/plan/INDEX.md` for PRD, roadmap, implementation-plan, or capability
   status work.
5. Local `agent-skills/*/SKILL.md` workflows.
6. External skill packs as reference material only.

If an external skill suggests a route, command, artifact, branch, commit, or
deployment behavior that conflicts with DeepTutor authority, translate or
discard it.

## Start Frame

Write this frame before implementing, repairing, reviewing, or adopting an
external workflow:

```text
task type:
assumptions:
simplest path:
change boundary:
authority chain:
selected local skill(s):
external material used:
verification target:
stop condition:
```

If the frame cannot identify the authority chain or verification target, keep
investigating before editing files.

During execution, keep two self-checks running:

- If an implementation grows from ~50 lines toward ~200 lines, stop and ask
  whether one-off logic is being turned into a framework.
- If the diff contains lines that cannot be traced directly to the user's
  request, delete them or split them out by default; do not smuggle
  "drive-by improvements" into this task.

## Dispatch Matrix

Use the narrowest matching local workflow:

- Ambiguous product or roadmap work: read `docs/plan/INDEX.md`, then write or
  update the canonical plan file through `deeptutor-spec-plan-gate`. Do not
  create stray `SPEC.md` or `tasks/` artifacts unless the user asks.
- Framework, library, API, or external documentation dependency: use
  `deeptutor-source-grounded-change`.
- Multi-file implementation: use `deeptutor-incremental-implementation`.
- Behavior changes, bug fixes, or skill/doc validations: use
  `deeptutor-test-verification-gate`.
- GitHub Actions, `Tests`, `Smoke Tests`, `Security Scan`, `Deploy Gate`,
  contract-guard CI, route smoke, secret baseline, or CI/local runtime mismatch
  failures: use `deeptutor-ci-runtime-fix-gate`; tie every conclusion to one
  workflow run and one SHA.
- API, control-plane, stream, trace, or contract boundary changes: use
  `deeptutor-api-contract-design`; read `CONTRACT.md` and
  `contracts/index.yaml`; keep wrappers thin and put policy in the existing
  authority service.
- Stable schema, schema registry, typed object, event payload, ViewModel,
  request config, or cross-surface payload changes: use
  `deeptutor-schema-authority-gate` before editing producers or consumers.
- DB connection/table write, env var, feature flag, credential, provider,
  long-running process, cron, route existence, model authority, harness
  authority, or governance scanner changes: use
  `deeptutor-resource-registry-gate`.
- Web, BI, browser, screenshot, Playwright, or `next dev` work: use
  `deeptutor-web-bi-frontend-gate`; run the memory preflight commands from that
  skill before any frontend command; do not let Codex, Computer Use, or another AI
  agent host a long-lived Next dev server.
- TutorBot, WeChat, follow-up, refusal, active object, route, terminal truth, or
  state continuity bugs: use `deeptutor-authority-debugging`.
- Real WeChat front-end risk: use `wechat-tutorbot-real-entry-qa`. Keep
  `devtools_project_root=yousenwebview` and
  `target_subpackage=packageDeeptutor` separate.
- Regex, fallback, classifier, wrapper, prompt shortcut, or special-case repair:
  use `anti-overfit-repair-review` before calling the fix complete.
- Compiled knowledge, general knowledge context, source pollution, or compiled
  default rollout: use `compiled-knowledge-shadow-eval`.
- Luban RichLeaf, candidate artifacts, review queues, runtime supply, or
  Grading-to-Brain claims: use `luban-rich-leaf-compiler`.
- Self-review, agent review, or pre-merge assessment: use
  `deeptutor-review-quality-gate`.
- Working code that is heavier than needed: use `deeptutor-code-simplification`.
- Auth, permissions, untrusted input, secrets, external integrations, or
  production trust boundaries: use `deeptutor-security-hardening-gate`.
- Logs, metrics, traces, release gate, or production evidence: use
  `deeptutor-observability-gate`.
- Documentation, ADRs, plan index, or authority doc sync: use
  `deeptutor-docs-adr-gate`.
- Branch, worktree, dirty files, stage, commit, or merge work: use
  `deeptutor-git-workflow-gate`.
- Release, merge, push, Aliyun, or production-like verification: use the
  repository release runbooks through `deeptutor-release-launch-gate` and keep
  all Aliyun host writes inside `/root/deeptutor`.

## Lifecycle Process

1. **Lock context.** Record `pwd -P`, git toplevel, branch, and dirty files
   before file edits. Treat unrelated dirty files as user or parallel-agent work.
2. **Specify only enough.** Reframe the request as success criteria. For
   substantial roadmap or architecture work, put the spec under `docs/plan/`
   and update `docs/plan/INDEX.md`.
3. **Plan thin slices.** Prefer one vertical or risk-first slice with direct
   verification over a broad framework. State what will not be touched.
4. **Prove behavior.** For bugs, reproduce first when practical. For behavior
   changes, add or update focused tests. For pure docs/skills, validate
   frontmatter, links, routing, and authority wording.
5. **Keep wrappers thin.** Boundary files normalize, authorize, delegate,
   preserve trace, and return. Business policy belongs to the single authority.
6. **Review for overfit.** Check whether the solution added a duplicate reader,
   fallback, mirror state, special-case phrase, or second truth source.
7. **Verify with evidence.** Report exact commands, tests, payloads, logs,
   screenshots, or reasoned doc checks. Do not write `PASS` for a surface that
   was not exercised.
8. **Close with residual risk.** Name unverified surfaces, partial evidence,
   dirty-worktree constraints, and the smallest next step.

## What To Learn From Generic Agent Skills

Adopt these mechanics:

- clear `description` triggers because skill routing depends on metadata;
- workflows as ordered actions, not prose advice;
- common rationalizations that catch agent excuses before they become behavior;
- red flags that reviewers can detect from a diff or report;
- verification checklists with evidence, not confidence;
- progressive disclosure: keep entry docs thin and long procedures in skills.

Do not adopt these mechanics blindly:

- generic `/ship`, `/build auto`, or auto-commit behavior;
- browser/devtools instructions that bypass DeepTutor memory guardrails;
- generic changelog/version/documentation churn;
- duplicate specs outside `docs/plan/`;
- any second chat route, second TutorBot identity, second learner memory, second
  RAG, or second release truth.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "The external skill is popular, so installing the whole pack is safer." | Popularity does not resolve DeepTutor authority conflicts. Translate useful workflow mechanics locally. |
| "This is just documentation, no verification needed." | Skill and docs changes still need frontmatter, routing, link, and authority-boundary checks. |
| "The generic ship workflow already has a checklist." | DeepTutor release truth requires its own git, contract, public endpoint, observability, and Aliyun evidence. |
| "A fallback is faster than tracing the authority path." | Fallbacks often become new authorities. First identify the single writer, store, reader, and terminal assembly path. |
| "The dirty files are unrelated, so we can ignore git state." | Dirty state is a safety signal. Ignore unrelated files for scope, but report them and do not stage them. |

## Red Flags

- A generic external skill becomes the first source of truth.
- A plan creates `SPEC.md`, `tasks/`, `CHANGELOG.md`, or `VERSION` without
  explicit DeepTutor need.
- A fix adds regex, classifier, fallback, route guard, or wrapper policy before
  identifying the authority break.
- A report collapses harness, near-real HTTP+WS, DevTools project-open, and real
  WeChat package evidence into one `PASS`.
- A release report says deploy succeeded based only on script exit code.
- Browser or Next dev work starts without the memory preflight.

## Verification

Before closing work governed by this skill, verify:

- [ ] The start frame names the authority chain and selected local skills.
- [ ] Any external skill material was translated into local DeepTutor rules.
- [ ] Modified files are limited to the declared change boundary.
- [ ] Required contracts, plan indexes, or local skill routing docs were updated.
- [ ] Tests or doc/skill validations ran, or an explicit blocker is reported.
- [ ] Final output separates completed evidence from pending or partial surfaces.
