# DeepTutor Agent Skills

These skills capture repeatable developer-agent workflows for DeepTutor.
They are not TutorBot runtime skills and must not be loaded by the product
skill loader under `deeptutor/tutorbot/skills/`.

Use them when planning, debugging, reviewing, or QA'ing DeepTutor work:

- `deeptutor-engineering-lifecycle-gate`: DeepTutor-local translation of
  general agent engineering lifecycle skills. Use it as the dispatcher for
  non-trivial implementation, repair, review, documentation, or launch work
  before selecting narrower skills.
- `deeptutor-spec-plan-gate`: spec and implementation-plan workflow for
  roadmap, PRD, architecture, and capability-status work under `docs/plan/`.
- `deeptutor-source-grounded-change`: source-driven workflow for framework,
  library, API, or external-reference changes where stale assumptions are risky.
- `deeptutor-storm-source-inspection`: STORM/Co-STORM-like multi-perspective
  source inspection producing candidate/review-only findings with provenance,
  without runtime, scoring, RAG, or learner-truth authority drift.
- `deeptutor-incremental-implementation`: thin vertical-slice implementation
  workflow for multi-file DeepTutor changes.
- `deeptutor-test-verification-gate`: test-first and evidence-first workflow
  for behavior changes, bug fixes, and doc/skill validations.
- `deeptutor-ci-runtime-fix-gate`: CI/runtime failure workflow for GitHub
  Actions, route smoke, contract guard, detect-secrets, and same-SHA deploy
  gate failures.
- `deeptutor-api-contract-design`: contract-first API and control-plane
  boundary workflow for REST, WebSocket, trace, session, and schema changes.
- `deeptutor-schema-authority-gate`: schema and registry authority workflow for
  stable external boundaries, typed objects, event payloads, view models, and
  machine-checkable schema changes.
- `deeptutor-resource-registry-gate`: register-before-use workflow for
  foundational resources such as DB connections, env vars, feature flags,
  credentials, providers, long-running processes, routes, model authority, and
  governance scanner wiring.
- `deeptutor-web-bi-frontend-gate`: Web/BI/frontend workflow with memory
  preflight and no agent-hosted long-lived Next dev server.
- `deeptutor-authority-debugging`: root-cause workflow for authority, state,
  route, follow-up, refusal, and terminal-truth bugs.
- `tutorbot-student-army-eval-loop`: proactively pressure-tests TutorBot on
  test2 with a multi-persona student army (long conversations), then runs the
  discover→root-cause→fix→verify→sediment loop. Continuously maintained: each
  run appends new bug patterns and ironclad diagnosis/fix rules to the skill.
- `wechat-tutorbot-real-entry-qa`: QA workflow for the real WeChat TutorBot
  path, with explicit evidence-surface boundaries.
- `compiled-knowledge-shadow-eval`: QA and rollout workflow for Nexus-like
  RAG+compiled TutorBot knowledge conversations, source pollution feedback,
  and system-wide default decisions.
- `anti-overfit-repair-review`: review workflow for regex, fallback,
  classifier, and special-case repairs.
- `deeptutor-review-quality-gate`: five-axis review workflow for self-review,
  agent code review, and pre-merge assessment.
- `deeptutor-code-simplification`: behavior-preserving simplification workflow
  for recently changed code that is heavier than necessary.
- `deeptutor-security-hardening-gate`: security review workflow for auth,
  untrusted input, secrets, external integrations, and production boundaries.
- `deeptutor-observability-gate`: logging, metrics, trace, and release-gate
  evidence workflow for production-visible behavior.
- `deeptutor-docs-adr-gate`: documentation and ADR workflow that keeps
  `AGENTS.md`, `CONTRACT.md`, and `docs/plan/INDEX.md` as the authority map.
- `deeptutor-git-workflow-gate`: branch, dirty-worktree, staging, commit,
  merge, and worktree discipline for DeepTutor.
- `deeptutor-release-launch-gate`: release, merge-to-main, push, Aliyun deploy,
  rollback, and post-launch verification workflow.
- `luban-rich-leaf-compiler`: RichLeafArtifact / 2026 source compilation /
  review queue / runtime supply candidate workflow.
- `luban-okf-context`: AI-only OKF source-navigation workflow for data asset,
  topic coverage, exam/source-evidence, and candidate/runtime boundary questions.
- `luban-diagram-microlesson`: 图解微课卡 authoring / 确定性 renderer / 一屏一重点
  翻页 deck UX / 单一权威边界 / web-view 沙盒 / 零依赖 CDP 验收 workflow.
- `luban-case-answer-layer`: 案例题作答训练(采分点可写化、五维框架、AI 批改
  训练闭环),依附已 signed pack 加层,不造第二 authority.
- `luban-learning-pack-factory`: 鲁班"教研测一体"学习包批量生产总纲与质量闭环;
  造法细节调用 `luban-diagram-microlesson`,本 skill 不重复它.
- `external-tool-absorption-boundary`: adopting/upgrading a plugin, marketplace skill,
  gstack, CLI, MCP, or shared hook — audit + neutralize opinionated defaults
  (auto-commit, CLAUDE.md injection, blocking hooks, telemetry) so they never
  override single authority, branch discipline, or register-before-use.

Keep `AGENTS.md` as the hard-gate index. Put long procedures and reusable
checklists here so project entry files stay thin.

## Invocation Contract

These are repo-local workflow skills. In DeepTutor, normal invocation comes from
`AGENTS.md` routing plus direct reads of `agent-skills/<name>/SKILL.md`; they are
not product TutorBot runtime skills.

Expected trigger rate:

- near-always for non-trivial engineering work: implementation, repair, review,
  plan, docs, tests, release, Web/BI, WeChat, Aliyun, observability, security,
  or external-source adoption;
- optional for tiny self-contained answers, one-line shell checks, translations,
  or purely conversational clarification;
- never as a generic external authority that overrides `AGENTS.md`,
  `CONTRACT.md`, `contracts/index.yaml`, or `docs/plan/INDEX.md`.

Run this after adding, renaming, or editing skill routing:

```bash
python agent-skills/scripts/validate_agent_skills.py
```

`catalog.yaml` is the machine-checkable inventory for these workflow skills. It
is deliberately not a loader and not an authority for descriptions; `SKILL.md`
frontmatter remains the trigger source, while `AGENTS.md` remains the hard-gate
index.

To audit whether skills were actually invoked in recent Codex work, run:

```bash
python agent-skills/scripts/audit_skill_usage.py --hours 1
python agent-skills/scripts/audit_skill_usage.py --hours 1 --repo-only
```

The usage audit only proves that `SKILL.md` files were read through recorded
tool calls. It cannot prove that every instruction was followed; use review and
verification evidence for that stronger claim.

## Lifecycle Map

The upstream `addyosmani/agent-skills` lifecycle is absorbed as this local map:

- Define and plan: `deeptutor-spec-plan-gate`
- Ground in sources: `deeptutor-source-grounded-change`,
  `deeptutor-storm-source-inspection`
- Build: `deeptutor-incremental-implementation`,
  `deeptutor-api-contract-design`, `deeptutor-schema-authority-gate`,
  `deeptutor-resource-registry-gate`, `deeptutor-web-bi-frontend-gate`,
  `luban-okf-context`, `luban-diagram-microlesson`,
  `luban-case-answer-layer`, `luban-learning-pack-factory`
- Verify: `deeptutor-test-verification-gate`,
  `deeptutor-ci-runtime-fix-gate`,
  `tutorbot-student-army-eval-loop`,
  `wechat-tutorbot-real-entry-qa`, `compiled-knowledge-shadow-eval`,
  `luban-rich-leaf-compiler`
- Debug and repair: `deeptutor-authority-debugging`,
  `anti-overfit-repair-review`
- Review and simplify: `deeptutor-review-quality-gate`,
  `deeptutor-code-simplification`, `deeptutor-security-hardening-gate`
- Document and observe: `deeptutor-docs-adr-gate`,
  `deeptutor-observability-gate`
- Version and ship: `deeptutor-git-workflow-gate`,
  `deeptutor-release-launch-gate`
- Tooling and absorption: `external-tool-absorption-boundary`

## External Skill Absorption Boundary

External skill packs such as `addyosmani/agent-skills` are upstream workflow
material, not DeepTutor authority. Learn their process shape, then translate it
into local constraints:

- keep `AGENTS.md`, `CONTRACT.md`, `contracts/index.yaml`, and
  `contracts/schema_registry.yaml` / `docs/plan/INDEX.md` as the authority
  chain;
- do not install a generic slash-command lifecycle that can bypass DeepTutor
  release, WeChat, Aliyun, or memory guardrails;
- prefer one local dispatcher plus domain skills over copying a full external
  skill tree;
- preserve the useful mechanics: clear trigger descriptions, stepwise workflow,
  common rationalizations, red flags, and evidence-based verification.

When a future external skill looks useful, first run
`deeptutor-engineering-lifecycle-gate`, then either map it to an existing local
skill or create a DeepTutor-specific skill with an explicit authority boundary.
