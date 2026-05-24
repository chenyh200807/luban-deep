# DeepTutor Hermes Edu Skills Booster Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Use `root-cause-debugging` when any route, skill-loading, answer-reveal, learner-state, or authority drift appears. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** P0 implemented locally / Static inventory and runtime builder wired
**Created:** 2026-05-24
**Owner surface:** `deeptutor/tutorbot/skills`, question lifecycle skills, learner-state read models, construction grading, RAG, Hermes sandbox, developer QA skills
**Goal:** Turn `zhongweiv/hermes-edu-skills` from an external education Skill Pack into a DeepTutor booster: a reference library, inventory system, validation model, sandbox channel, and exportable education-skill ecosystem without giving it production authority.

**Architecture:** Treat Hermes Edu Skills as an upstream inspiration and experiment source, not as runtime truth. The only production path is: external skill intake -> DeepTutor translation map -> DeepTutor skill registry -> existing `SkillsLoader` / `question_lifecycle_skill_context` -> `deep_question`, TutorBot, `question_followup`, `construction_grading`, `LearnerStateService`, and RAG. No new chat entrypoint, learner memory, routing authority, or external editable skill directory is introduced.

**Tech Stack:** Markdown `SKILL.md`, `catalog.json`, Python inventory/validation scripts, pytest, Langfuse trace fields, existing DeepTutor skill loader, Hermes Agent sandbox, `/wechat-harness`, WeChat DevTools for release validation.

---

## 1. Source Facts

Current researched source:

- Repository: `zhongweiv/hermes-edu-skills`
- Local snapshot inspected: `v0.18.6`, commit `3646be2`, package version `0.18.6`
- License: MIT
- Public Skill count: 188
- Categories:
  - `learning-assistant`: 21
  - `exam-prep`: 30
  - `reading-writing`: 11
  - `textbook-sync`: 40
  - `daily-practice`: 26
  - `preschool`: 22
  - `family-education`: 7
  - `teacher-tools`: 31
- Engineering assets:
  - `catalog.json`
  - `.well-known/skills/index.json`
  - `scripts/agent-pack.mjs`
  - `scripts/validate.mjs`
  - `doctor`, `verify`, `repair`, `update`, `uninstall`, `match`, `ask`, `export`
  - export targets for Hermes, OpenClaw, Codex, Claude Code, Cursor, generic agent
- Security posture: public Skill Pack should not include model keys, private databases, user data, production private prompts, internal cost or account identifiers.

This plan uses those facts as intake evidence only. If the upstream version changes, rerun Phase 0 before implementation.

## 2. Karpathy Gate Worksheet

### 2.1 Assumptions

1. Hermes Edu Skills is important because it shows how to productize education behavior as installable, discoverable, validated skills.
2. Its current Chinese education coverage is broad, but its router and content are not construction-exam-specific enough to govern DeepTutor production behavior.
3. DeepTutor already has stronger domain authorities: `questions_bank`, active question object, `deep_question`, `construction_grading`, `rag`, `LearnerStateService`, `training_intent`, and learning-report read models.
4. The valuable move is translation and governance, not copy/paste.
5. The first production target remains construction-exam question lifecycle. K12, preschool, family education, and broad teacher tools are future optional expansions.

### 2.2 Simplest Path

Do the minimum that creates compounding leverage:

1. Build a read-only upstream inventory.
2. Score every upstream skill against DeepTutor scenarios.
3. Create a DeepTutor-native skill registry and validator.
4. Translate only high-value construction-related patterns into DeepTutor runtime skills.
5. Use Hermes + Weixin as a sandbox for low-risk learning workflows.
6. Export DeepTutor skills outward only after production invariants are covered.

Do not install all 188 skills into DeepTutor production.

### 2.3 Change Boundary

Allowed:

- `docs/plan/*`
- `deeptutor/tutorbot/skills/*/SKILL.md`
- `deeptutor/tutorbot/skills/*/references/*.md`
- `scripts/hermes_edu_booster_inventory.py`
- `scripts/validate_tutorbot_skills.py`
- `tests/scripts/test_hermes_edu_booster_inventory.py`
- `tests/scripts/test_validate_tutorbot_skills.py`
- `tests/services/test_question_lifecycle_skills.py`
- `tests/runtime/test_orchestrator_autoroute.py`
- existing question lifecycle plan files and `docs/plan/INDEX.md`

Forbidden in this plan:

- New public chat endpoint
- New WebSocket route
- New learner memory table
- New RAG mode
- External editable production skill directory
- Runtime use of Hermes Edu Skills router as DeepTutor router
- Frontend computation of weakness, mastery, diagnosis, recommendation, or reveal policy

### 2.4 Verification Target

Acceptance requires:

1. Upstream inventory generated from a pinned source.
2. Every imported idea has an explicit DeepTutor authority mapping.
3. DeepTutor skill registry validates all runtime skills.
4. No new loader bypasses `SkillsLoader`.
5. No skill markdown owns scoring, learner-state computation, or routing decisions.
6. Question lifecycle scenes appear in Langfuse with skill stack metadata.
7. `/wechat-harness` and WeChat DevTools prove student-visible behavior.
8. Hermes sandbox results are clearly marked experimental and do not write production learner state.

## 3. Single Authority Hard Gate

### 3.1 One Business Fact

External education skills should increase DeepTutor's teaching capability, but every production learning turn must still be governed by one DeepTutor scene, one canonical question object, and one domain authority chain.

### 3.2 One Authority

| Business fact | Canonical authority | Hermes Edu role |
| --- | --- | --- |
| Question generation and answer hiding | `deep_question` + question lifecycle scene | Template/reference only |
| Current question identity | active question object / turn runtime | No authority |
| MCQ/case grading | `construction_grading` and its kernels | Template/reference only |
| RAG grounding | `RAGService` | No new grounded mode |
| Learner evidence | `LearnerStateService` / `learning_evidence` | No write authority |
| Learning report | `LearningReportReadModel` | Narration pattern only |
| Study plan / next task | `training_intent` / existing read path | Expression pattern only |
| Skill discovery | DeepTutor skill registry + existing `SkillsLoader` | Upstream input only |

### 3.3 Competing Authorities to Block

- Hermes Edu `match` score deciding production scene.
- External `SKILL.md` copied directly into prompt without DeepTutor translation.
- Skill markdown calculating mastery, score, weak points, or next-task priority.
- A second local skill loader reading paths directly.
- Hermes sandbox memory treated as DeepTutor learner state.
- Teacher-tool workflows writing student-facing recommendations without evidence.

### 3.4 Canonical Path

```text
Hermes Edu Skills upstream snapshot
  -> read-only inventory
  -> DeepTutor translation map
  -> DeepTutor skill registry
  -> validator and authority guard
  -> existing SkillsLoader
  -> question_lifecycle_skill_context
  -> deep_question / TutorBot / question_followup / construction_grading
  -> learner evidence / RAG / Langfuse / release gates
```

### 3.5 Delete or Demote

Anything copied from Hermes Edu must be demoted to one of:

- `reference_pattern`
- `candidate_skill`
- `sandbox_skill`
- `developer_skill`
- `rejected_due_authority_risk`

Only DeepTutor-authored skills with validator coverage may become runtime production skills.

## 4. What We Should Learn

### 4.1 Product Pattern

Hermes Edu Skills organizes education needs by repeatable task, not by one-off prompt:

- explain a question
- review a mistake
- generate daily practice
- prepare for an exam
- create a study plan
- help a teacher plan a lesson
- help a parent support learning

DeepTutor should use this task framing, but translate it into construction-exam-specific scenes and authorities.

### 4.2 Skill Format Pattern

Reusable sections worth adopting:

- `Problem`
- `Best For`
- `Not For`
- `Inputs`
- `Recommended Workflow`
- `Output Format`
- `Quality Checks`
- `Standalone Fallback`
- `Invocation Signals`
- `Public Skill Contract`
- `Required Dimensions`
- `Default Policy When Missing`

DeepTutor additions required:

- `Authority`
- `Forbidden Authority`
- `Trace Fields`
- `Evidence Requirements`
- `Answer Reveal Policy`
- `Writeback Eligibility`
- `Anti-Patterns`
- `Manual Gate`

### 4.3 Engineering Pattern

High-value engineering ideas:

- generated catalog and discovery index
- validator in CI
- health/doctor command
- category and single-skill export
- scoped activation prompt
- external-tool export
- deterministic `match` for debugging, not production routing

DeepTutor should adopt the engineering shape, not the upstream runtime authority.

## 5. Booster Scenario Matrix

### 5.1 Student-Facing Construction Exam

| Scenario | Upstream inspiration | DeepTutor target | Production authority |
| --- | --- | --- | --- |
| Analyze a true question before answering | `agent-question-explanation`, `agent-socratic-tutor` | `construction-question-review` | active question + RAG + reveal policy |
| Generate practice | `daily-practice`, `exam-prep` | `construction-question-supply` | `deep_question` |
| Grade MCQ | mistake/exam review patterns | existing `construction-mcq-grading` | `construction_grading` |
| Grade case answer | exam review patterns | existing `construction-case-grading` | `CaseGradingSkillKernel` |
| Mistake review | `agent-mistake-review` | `construction-learning-evidence-story` or `construction-mistake-review` | `learning_evidence` / mistake book |
| Study next step | `agent-study-plan`, `adult-vocational-certificate` | `construction-study-assistant` | `training_intent` |
| Emotional support | `family-emotion-support`, learning support patterns | `construction-learning-support` | TutorBot safety path + no learner-state writes |

### 5.2 Teacher / Operator / BI

| Scenario | Use |
| --- | --- |
| Teacher lesson planning | Internal教研 tool, not student runtime |
| Unit review lesson | BI / teacher-tools future module |
| Class weakness summary | Member/backoffice read model only |
| Parent report style | Can inspire learner report narration, but not authority |
| Homework generation | Future exercise package generation after validator |

### 5.3 Developer and QA

| Scenario | Use |
| --- | --- |
| Skill validator | Must implement |
| Skill doctor | Must implement after registry |
| Export to Codex / Claude / Cursor | Developer workflow booster |
| Release gate checklist | Add skill registry status to launch readiness |
| Authority regression skill | Upgrade current TutorBot-only lesson into question lifecycle review skill |

### 5.4 Hermes Sandbox

Use Hermes + Weixin for experiments only:

- daily 10-minute construction practice
- one mistake review per day
- 7-day exam sprint
- parent/teacher-facing explanation style tests
- low-risk motivation and routine coaching

Sandbox outputs must be labeled experimental and must not write production learner state.

### 5.5 Future Optional Expansion

Do not implement now, but keep a path:

- preschool / K12 expansion if product scope changes
- construction visual question review
- teacher studio
- public `luban-construction-skills` package
- commercial skill pack for partner institutions

## 6. Target Architecture

### 6.1 ExternalSkillInventory

Purpose: classify the upstream 188 skills into DeepTutor-relevant buckets.

Proposed output:

```json
{
  "source": "zhongweiv/hermes-edu-skills",
  "version": "0.18.6",
  "generated_at": "2026-05-24T00:00:00Z",
  "skills": [
    {
      "name": "agent-mistake-review",
      "category": "learning-assistant",
      "upstream_path": "skills/learning-assistant/agent-mistake-review/SKILL.md",
      "deep_tutor_bucket": "adapt_to_construction",
      "deep_tutor_targets": ["construction-learning-evidence-story", "construction-study-assistant"],
      "authority_risk": "medium",
      "notes": "Useful workflow; cannot own mistake-book or learner-state writes."
    }
  ]
}
```

Buckets:

- `adapt_to_construction`
- `template_only`
- `developer_ops`
- `sandbox_experiment`
- `future_product`
- `reject_due_authority_risk`

### 6.2 DeepTutor Skill Registry

Purpose: make runtime skills first-class, inspectable, and verifiable.

Proposed file:

```text
deeptutor/tutorbot/skills/catalog.yaml
```

Minimum fields:

```yaml
version: 1
skills:
  - name: construction-question-review
    path: construction-question-review/SKILL.md
    subject: construction_exam
    scene: question_review
    runtime_scope: production
    authority_scope: presentation_policy
    export_eligible: internal
    required_authorities:
      - active_question
      - rag
      - answer_reveal_policy
    forbidden_authorities:
      - scoring
      - learner_state_write
      - route_decision
    trace_fields:
      - question_lifecycle_scene
      - skill_stack
      - loader_source
```

This registry is not a new router. It is a validation and discovery surface over existing skills.

### 6.3 Validator

Proposed script:

```text
scripts/validate_tutorbot_skills.py
```

Checks:

- every catalog skill file exists
- every catalog skill explicitly declares `export_eligible: public | internal | none`
- every referenced `references/*.md` exists
- frontmatter name matches directory
- `Authority` and `Forbidden Authority` sections exist
- `Anti-Patterns` section has at least three concrete entries for production skills
- narration skills do not include SQL, thresholds, table names, mastery formulas, or direct recommendations not backed by read models
- grading skills do not claim to replace `construction_grading`
- question-review skills respect answer/explanation reveal policy
- no PII or secrets
- no `Path(...skills...)` loader bypass outside approved files

### 6.4 Skill Doctor

Command:

```bash
python scripts/validate_tutorbot_skills.py --doctor
```

It reports:

- registry version
- total skills
- production skills
- sandbox skills
- missing references
- authority-risk findings
- inventory-to-catalog translation gaps for upstream `adapt_to_construction` skills
- loader-source drift
- skills not visible through `SkillsLoader`
- Langfuse skill-stack coverage if trace access is configured

Current P2 implementation covers the inventory-to-catalog gap report. It reads `docs/plan/artifacts/hermes-edu-skills-inventory.json`, filters `deep_tutor_bucket == adapt_to_construction`, and checks that every `deep_tutor_targets` entry exists in `catalog.yaml`. This is a doctor report only; it must not be used by runtime code.

### 6.5 Export Pack

Once production skills are stable, export a curated pack:

```text
dist/luban-construction-skills/
```

Targets:

- Hermes Agent
- Codex skills
- Claude Code skills
- Cursor rules
- generic agent

Export must strip private references, internal paths, production prompts, keys, user data, and tenant-specific examples.

## 7. Implementation Phases

### Phase -1: Intake Safety

- [ ] Keep upstream in `HERMES_EDU_SOURCE` or a read-only vendored snapshot. Default local path: `~/.cache/deeptutor/hermes-edu-skills`.
- [ ] Record upstream version and license.
- [ ] Do not install upstream into `~/.codex/skills`, `~/.hermes/skills`, or DeepTutor runtime.
- [ ] Document that upstream router is not production route authority.

Validation:

```bash
HERMES_EDU_SOURCE=${HERMES_EDU_SOURCE:-~/.cache/deeptutor/hermes-edu-skills}
bash scripts/fetch_hermes_upstream.sh
npm --prefix "$HERMES_EDU_SOURCE" run validate
```

Expected: validates all upstream skills.

### Phase 0: Inventory and Scoring

Create:

```text
scripts/hermes_edu_booster_inventory.py
tests/scripts/test_hermes_edu_booster_inventory.py
docs/plan/artifacts/hermes-edu-skills-inventory.json
```

Score fields:

- `domain_fit`: construction / generic education / unrelated
- `runtime_fit`: production / sandbox / developer / future
- `authority_risk`: low / medium / high
- `rewrite_required`: none / light / heavy / reject
- `target_deeptutor_skill`
- `recommended_phase`

Minimum scoring rules:

- Any skill that implies grading, mastery, or learner recommendation is at least medium authority risk.
- Any skill that can be used as expression policy without writing state is lower risk.
- Any K12/preschool-only skill is future product, not P0.
- Any teacher-tool skill is internal ops unless explicitly mapped to student-facing experience.

Validation:

```bash
HERMES_EDU_SOURCE=${HERMES_EDU_SOURCE:-~/.cache/deeptutor/hermes-edu-skills}
python scripts/hermes_edu_booster_inventory.py --source "$HERMES_EDU_SOURCE" --output docs/plan/artifacts/hermes-edu-skills-inventory.json
pytest tests/scripts/test_hermes_edu_booster_inventory.py -q
```

Expected:

- 188 skills classified.
- No skill has empty `deep_tutor_bucket`.
- At least `agent-mistake-review`, `agent-question-explanation`, `agent-socratic-tutor`, `adult-vocational-certificate`, and `agent-learning-report` have explicit construction mappings or explicit rejection reasons.
- `adapt_to_construction` is not a generic todo bucket. It only contains explicitly mapped skills or daily-practice skills whose metadata is construction/adult-vocational relevant.
- Generic K12 daily-practice skills remain `template_only` or lower.

### Phase 0.5: P1 Operational Guardrails

Create:

```text
scripts/fetch_hermes_upstream.sh
scripts/check_hermes_upstream.py
scripts/scan_hermes_sandbox_transcripts.py
.github/workflows/hermes-upstream.yml
tests/scripts/test_fetch_hermes_upstream_script.py
tests/scripts/test_check_hermes_upstream.py
tests/scripts/test_scan_hermes_sandbox_transcripts.py
```

Rules:

- `fetch_hermes_upstream.sh` is the only blessed bootstrap path for local/CI upstream snapshots. It uses `HERMES_EDU_SOURCE` when present and otherwise writes to `~/.cache/deeptutor/hermes-edu-skills`.
- `check_hermes_upstream.py` compares the pinned DeepTutor inventory version with upstream `package.json` first, then `catalog.json`. Local use warns on drift; scheduled CI uses `--fail-on-drift` so the team sees upstream changes.
- `scan_hermes_sandbox_transcripts.py` scans only sandbox files/summaries for common raw PII patterns before commit/CI. It is not a runtime redaction engine and must not be used as learner-state authority.
- Weekly GitHub Action fetches the pinned upstream snapshot, checks drift, and scans committed Hermes sandbox summaries.

Validation:

```bash
pytest tests/scripts/test_check_hermes_upstream.py tests/scripts/test_scan_hermes_sandbox_transcripts.py tests/scripts/test_fetch_hermes_upstream_script.py -q
python scripts/check_hermes_upstream.py --source "$HERMES_EDU_SOURCE"
python scripts/scan_hermes_sandbox_transcripts.py
```

Expected:

- Version match prints `INFO`.
- Version mismatch prints `WARN`; with `--fail-on-drift` it exits non-zero.
- Missing `docs/sandbox` is OK; raw phone/email/openid/name-labeled transcript files fail.

### Phase 1: DeepTutor Skill Registry and Validator

Create:

```text
deeptutor/tutorbot/skills/catalog.yaml
scripts/validate_tutorbot_skills.py
tests/scripts/test_validate_tutorbot_skills.py
```

Initial catalog must include:

- `construction-exam-tutor`
- `construction-mcq-grading`
- `construction-case-grading`
- `deep-question`
- `lecture-waterproof-energy-decoration`

Then add new candidate production skills only after Phase 2.

Validation:

```bash
python scripts/validate_tutorbot_skills.py
pytest tests/scripts/test_validate_tutorbot_skills.py -q
```

Expected:

- Current skills pass basic registry checks.
- Missing authority sections are reported as actionable findings before strict mode is enabled.

### Phase 2: Construction Runtime Skill Pack

Create or restore:

```text
deeptutor/tutorbot/skills/construction-question-supply/SKILL.md
deeptutor/tutorbot/skills/construction-question-review/SKILL.md
deeptutor/tutorbot/skills/construction-learning-evidence-story/SKILL.md
deeptutor/tutorbot/skills/construction-study-assistant/SKILL.md
deeptutor/tutorbot/skills/construction-learning-support/SKILL.md
```

Each skill must include:

- `Authority`
- `Forbidden Authority`
- `Inputs`
- `Workflow`
- `Output Contract`
- `Quality Checks`
- `Anti-Patterns`
- `Trace Fields`
- `Fallback`

Important constraints:

- `construction-question-supply` cannot reveal answers or explanations during generation.
- `construction-question-review` cannot override answer/explanation reveal policy.
- `construction-learning-evidence-story` cannot compute learning state.
- `construction-study-assistant` cannot invent next-task priority outside `training_intent`.
- `construction-learning-support` cannot write learning evidence unless a real learning event happens.

Validation:

```bash
python scripts/validate_tutorbot_skills.py --strict
pytest tests/services/test_question_lifecycle_skills.py -q
```

Expected:

- All production skills visible through `SkillsLoader`.
- No skill violates forbidden authority checks.

### 6.6 Token Budget Discipline

The skill pack must stay usable in real TutorBot turns, not just pass static validation.

- Each catalog entry must declare `token_budget_estimate`.
- Single-turn skill stack budget should stay at or below 8K tokens.
- `SKILL.md` over 200 lines is a validator warning; over 300 lines is a validator error.
- If a skill grows past the budget, split stable reference material into `references/` and keep `SKILL.md` as the decision contract.
- Runtime must still load only the selected skill stack; catalog discovery must not cause all skills to be concatenated.
- `token_budget_estimate` covers `SKILL.md` only; references are lazy-loaded by selected scene and not pre-summed.

### Phase 3: Runtime Wiring Through Existing Question Lifecycle Plan

This phase depends on:

- `2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md`

Do not duplicate that plan. This booster plan supplies source patterns and registry/validation.

Coupling note: this booster assumes the sibling question-lifecycle plan provides `question_lifecycle_skill_context.scene`, `skill_names`, and `loader_sources`. If that plan changes the scene schema, alias map, or kill-switch behavior, rerun this phase's runtime gates and trace metadata checks before release.

Required invariants:

- `ChatOrchestrator` remains the single scene decider.
- `SkillsLoader` remains the single skill loader.
- `question_lifecycle_skill_context` owns scene -> skill stack composition.
- `deep_question`, TutorBot, `question_followup`, and `construction_grading` consume, but do not re-decide, skill scene.

Validation:

```bash
pytest tests/runtime/test_orchestrator_autoroute.py -q
pytest tests/services/test_question_lifecycle_skills.py -q
```

Manual gates:

- `/wechat-harness` practice generation hides answer.
- Submitted MCQ grades and then explains.
- Submitted case answer uses case grading path.
- "分析一道真题" before answer does not leak final answer unless explicit product rule allows it.
- Learning report follow-up cites concrete history, not generic advice.

### Phase 4: Hermes + Weixin Sandbox Booster

Create:

```text
docs/plan/2026-05-24-hermes-weixin-learning-sandbox-checklist.md
```

Sandbox workflows:

- daily mistake review
- daily 10-minute practice
- 7-day exam sprint
- motivation / study routine support
- teacher-facing mini lesson plan

Rules:

- Sandbox cannot write DeepTutor production learner state.
- Sandbox cannot claim production grading.
- Sandbox transcripts used for product research must be redacted.
- Any useful workflow must be re-authored as DeepTutor-native skill before production.

Validation:

- Hermes DM test: user can trigger skill-guided response.
- Manual transcript review: no private data copied into repo.
- Product review: only summarized workflow lessons enter backlog.

### Phase 5: Internal Teacher and Operator Booster

Use upstream `teacher-tools` as inspiration for internal-only tools:

- lesson planning from weak points
- unit review from class mistake clusters
- parent report draft from read model
- teaching material outline from RAG evidence

Production boundary:

- This is BI / teacher workspace, not student chat.
- It reads existing projections only.
- It never writes learner-state truth.

Candidate future files:

```text
docs/plan/2026-05-25-luban-teacher-tools-skill-booster-plan.md
```

### Phase 6: Exportable Luban Skill Pack

After production skill registry is stable, build:

```text
dist/luban-construction-skills/
scripts/export_luban_skills.py
```

Export modes:

- `hermes`
- `codex`
- `claude-code`
- `cursor`
- `generic-agent`

Package rules:

- public pack strips private references
- internal pack can include runbooks but no secrets or user data
- each exported skill includes license and source version
- exported pack includes validator report

This creates ecosystem leverage: our own DeepTutor skills can become reusable tools for developers,教研, and partner workflows.

## 8. Concrete Absorption Map

| Upstream category | Count | DeepTutor use | Priority |
| --- | ---: | --- | --- |
| `learning-assistant` | 21 | Question explanation, mistake review, study planning, learning report narration | P0/P1 |
| `exam-prep` | 30 | Construction exam planning, sprint plan, review cadence | P0/P1 |
| `daily-practice` | 26 | 10-minute drills, spaced review, short practice UX | P1 |
| `teacher-tools` | 31 | Internal教研/BI/teacher workspace booster | P2 |
| `textbook-sync` | 40 | Future教材/讲义同步; current construction KB must stay RAG authority | P2 |
| `reading-writing` | 11 | Case answer expression improvement | P2 |
| `family-education` | 7 | Motivation/routine support patterns only | Sandbox |
| `preschool` | 22 | Out of current construction scope | Future |

## 9. P0 Deliverables

P0 is complete only when these exist:

1. `docs/plan/2026-05-24-deeptutor-hermes-edu-skills-booster-plan.md`
2. `docs/plan/INDEX.md` links this plan under 鲁班智考个性化教学 / question lifecycle
3. `scripts/hermes_edu_booster_inventory.py`
4. `docs/plan/artifacts/hermes-edu-skills-inventory.json`
5. `deeptutor/tutorbot/skills/catalog.yaml`
   - validation/discovery only; runtime code must not import it
   - every production entry declares `token_budget_estimate`
6. `scripts/validate_tutorbot_skills.py`
7. strict-mode validator passing for registered production skills
8. translated construction scene skill pack:
   - `construction-question-supply`
   - `construction-question-review`
   - `construction-learning-evidence-story`
   - `construction-study-assistant`
   - `construction-learning-support`
9. `question_lifecycle_skills` builder and trace metadata propagation:
   - `question_lifecycle_scene`
   - `skill_stack`
   - `loader_source`
   - `skill_source_status`

## 10. Release Gates

### 10.1 Static Gates

```bash
HERMES_EDU_SOURCE=${HERMES_EDU_SOURCE:-~/.cache/deeptutor/hermes-edu-skills}
bash scripts/fetch_hermes_upstream.sh
python scripts/check_hermes_upstream.py --source "$HERMES_EDU_SOURCE"
python scripts/hermes_edu_booster_inventory.py --source "$HERMES_EDU_SOURCE" --output docs/plan/artifacts/hermes-edu-skills-inventory.json
python scripts/validate_tutorbot_skills.py --strict
python scripts/validate_tutorbot_skills.py --doctor
python scripts/scan_hermes_sandbox_transcripts.py
pytest tests/scripts/test_hermes_edu_booster_inventory.py tests/scripts/test_validate_tutorbot_skills.py -q
pytest tests/scripts/test_check_hermes_upstream.py tests/scripts/test_scan_hermes_sandbox_transcripts.py tests/scripts/test_fetch_hermes_upstream_script.py -q
pytest tests/scripts/test_hermes_edu_booster_inventory.py tests/scripts/test_validate_tutorbot_skills.py tests/services/test_question_lifecycle_skills.py tests/services/test_tutorbot_teaching_modes.py tests/core/test_capabilities_runtime.py -q
pytest tests/services/test_question_lifecycle_skills.py tests/services/test_tutorbot_teaching_modes.py tests/core/test_capabilities_runtime.py::test_tutorbot_progressive_skills_load_construction_scene_for_fast_and_deep -q
pytest tests/core/test_capabilities_runtime.py -q
pytest tests/runtime/test_orchestrator_autoroute.py tests/services/construction_grading -q
cd web && npm run test:wechat-harness
python scripts/run_wechat_learning_brain_devtools_e2e.py --base-url http://127.0.0.1:8001
python -m py_compile deeptutor/services/question_lifecycle_skills.py deeptutor/tutorbot/teaching_modes.py deeptutor/tutorbot/agent/skills.py deeptutor/tutorbot/agent/loop.py deeptutor/services/tutorbot/manager.py deeptutor/capabilities/tutorbot.py
rg -n "_read_skill_file|Path\(__file__\).*skills" deeptutor | rg -v "deeptutor/tutorbot/agent/skills.py|deeptutor/services/question_lifecycle_skills.py"
```

### 10.2 Runtime Gates

```bash
pytest tests/services/test_question_lifecycle_skills.py -q
pytest tests/runtime/test_orchestrator_autoroute.py -q
pytest tests/services/construction_grading -q
```

### 10.3 Product Gates

- `/wechat-harness` generation: no answer leak.
- `/wechat-harness` answer submission: grade then explain.
- WeChat DevTools true entry: same behavior as Web harness.
- Langfuse: `question_lifecycle_scene`, `skill_stack`, `loader_source` present in live trace.
- Learning report: no frontend-derived weak point or mastery text.

### 10.4 Sandbox Gates

- Hermes + Weixin workflows are labeled experimental.
- No transcript with PII enters repo; `python scripts/scan_hermes_sandbox_transcripts.py` must pass before committing sandbox summaries.
- No sandbox memory is treated as DeepTutor learner state.

## 11. Risks and Mitigations

| Risk | Failure shape | Mitigation |
| --- | --- | --- |
| Full upstream install pollutes routing | K12 skill handles construction query | Do not install upstream into production; inventory only |
| External router becomes production decider | Hermes `match` overrides `ChatOrchestrator` | Router is debug-only; production scene decided once |
| Skill markdown becomes learner-state truth | Skill calculates mastery or weak points | Validator forbids table names, formulas, thresholds and prescription leakage in expression-layer skills |
| Grading becomes prompt-only | Skill invents score without kernel | Grading skills must delegate to `construction_grading` |
| Hidden answer leaks | Review skill reveals answer before attempt | Product code enforces reveal policy; skill only reinforces |
| Upstream drift goes unnoticed | v0.19 changes inventory but DeepTutor still trusts v0.18.6 mappings | Weekly `hermes-upstream` sentinel fetches pinned upstream and runs `check_hermes_upstream.py --fail-on-drift` |
| Sandbox contaminates production | Hermes Weixin transcript written to learner state | Sandbox cannot write production state |
| Sandbox raw PII committed | Weixin/Hermes transcript lands under docs without redaction | `scan_hermes_sandbox_transcripts.py` blocks common phone/email/openid/name-labeled patterns |
| Ecosystem export leaks private data | Internal prompts or paths exported | Every catalog skill declares `export_eligible`; future export script must refuse `none` and separately review `public` |
| Over-expansion into K12 | Product focus diffuses | P0 only construction-exam lifecycle |

## 12. What Not To Do

- Do not copy all 188 skills into `deeptutor/tutorbot/skills`.
- Do not add a second skill loader.
- Do not put Hermes Edu `catalog.json` directly into production runtime.
- Do not import `deeptutor/tutorbot/skills/catalog.yaml` from `deeptutor/runtime/`, `deeptutor/services/`, `deeptutor/capabilities/`, or runtime files under `deeptutor/tutorbot/`.
- Do not let frontend choose a skill.
- Do not let Skill markdown compute scores, mastery, next-task priority, or wallet/member facts.
- Do not create `/api/v1/mobile/tutorbot/ws/...` or any dedicated chat WebSocket.
- Do not treat broad `exam-prep` as equivalent to construction exam expertise.
- Do not treat `adapt_to_construction` as a backlog list. It means confirmed construction translation target.
- Do not silently merge sandbox findings into durable memory.
- Do not write raw Hermes sandbox transcripts into the repo; only redacted summaries may be committed.
- Do not export any construction skill publicly unless `export_eligible` is explicitly set in a future export contract.

## 13. First 72 Hours

### Day 1

- [x] Pin upstream version and source path.
- [x] Write inventory script.
- [x] Classify all 188 skills.
- [x] Produce initial absorption dashboard in JSON/Markdown.

### Day 2

- [x] Add DeepTutor skill registry draft.
- [x] Add validator basic checks.
- [x] Register existing construction skills.
- [x] Run validator and close strict-mode skill-section gaps.

### Day 3

- [x] Translate `agent-question-explanation` + `agent-socratic-tutor` patterns into `construction-question-review`.
- [x] Translate daily/exam-prep patterns into `construction-question-supply`.
- [x] Add authority and anti-pattern sections.
- [x] Run static validator and script tests.

### P1 Guardrail Day

- [x] Add upstream fetch script with pinned ref and commit-prefix check.
- [x] Add upstream drift sentinel and weekly GitHub Action.
- [x] Add Hermes sandbox PII scanner and script tests.

### P2 Schema Day

- [x] Add `export_eligible: public | internal | none` to `catalog.yaml`.
- [x] Add validator coverage for explicit export eligibility.
- [x] Add `--doctor` inventory-to-catalog gap report for `adapt_to_construction` upstream skills.

### P3 Hardening Day

- [x] Require `upstream_inspiration.derivation` when upstream inspiration is declared.
- [x] Extend catalog runtime-import guard to `deeptutor/api`.
- [x] Document references token policy as selected-scene lazy loading.

## 14. Decision Log

| Decision | Status |
| --- | --- |
| Use Hermes Edu as booster, not authority | Accepted |
| Do not full-install 188 skills into production | Accepted |
| First runtime target is construction question lifecycle | Accepted |
| Registry and validator come before broad skill expansion | Accepted |
| Hermes + Weixin is sandbox only | Accepted |
| Upstream drift is checked weekly, not every PR | Accepted |
| Export eligibility is explicit metadata, not inferred by export scripts | Accepted |
| Skill markdown declares upstream license and derivation explicitly | Accepted |
| Public/commercial Luban skill pack is future phase | Proposed |

## 15. Open Questions

| Question | Proposed resolution | Owner | Verification deadline | Default if unresolved |
| --- | --- | --- | --- | --- |
| YAML registry or JSON registry? | Keep YAML as source of review, optionally generate JSON later. | DeepTutor Eng | 2026-06-15 | YAML remains source; no runtime import. |
| Merge learning evidence, study assistant, and learning support? | Keep separate; add sibling-boundary sections and validator coverage. | DeepTutor Eng | 2026-06-15 | Keep separate. |
| Open-source `luban-construction-skills`? | Do not publish until private RAG, rubric, business context, and attribution checks pass. | Product + Eng | 2026-06-15 | Internal pack only. |
| Personal Hermes home or project-scoped Hermes home? | Personal home is okay for <=3 internal testers; project home required once real learner transcripts or >3 testers enter. | Ops | 2026-06-15 | Project-scoped home. |
| Teacher tools student-facing? | Keep in BI/teacher workspace until separately designed. | Product | 2026-06-15 | Not student-facing. |

## 16. Local Execution Evidence

Executed on 2026-05-24:

```bash
HERMES_EDU_SOURCE=${HERMES_EDU_SOURCE:-~/.cache/deeptutor/hermes-edu-skills}
python scripts/hermes_edu_booster_inventory.py --source "$HERMES_EDU_SOURCE" --output docs/plan/artifacts/hermes-edu-skills-inventory.json
python scripts/validate_tutorbot_skills.py --strict
python scripts/validate_tutorbot_skills.py --doctor
pytest tests/scripts/test_hermes_edu_booster_inventory.py tests/scripts/test_validate_tutorbot_skills.py -q
pytest tests/scripts/test_check_hermes_upstream.py tests/scripts/test_scan_hermes_sandbox_transcripts.py tests/scripts/test_fetch_hermes_upstream_script.py -q
```

Results:

- Hermes inventory generated from upstream snapshot: 188 skills.
- Inventory bucket distribution after P0 review: `adapt_to_construction=6`, `template_only=90`, `developer_ops=31`, `future_product=54`, `sandbox_experiment=7`.
- License obligations live at inventory top-level (`license_obligations`); per-skill license stays in SKILL.md `upstream_inspiration`.
- DeepTutor TutorBot Skill Validator: 10 skills, 0 errors, 0 warnings.
- Doctor inventory gap report: `adapt_to_construction=6`, `gaps=0`.
- Script tests: 17 passed.
- P1 guardrail script tests: 7 passed.
- Script + runtime builder + teaching mode + learner-state + TutorBot capability tests: 162 passed.
- Orchestrator autoroute + construction grading runtime gates: 105 passed.
- `/wechat-harness` data tests: 4 passed.
- `/wechat-harness` Playwright e2e: 11 passed.
- Learning-brain WeChat local e2e: passed with local WeChat login fallback, grading -> synthesis -> projection, L1/L2 evidence levels, and improved/not-improved graph chain.
- WeChat DevTools CLI project open: passed for `yousenwebview`.
- TutorBot capability runtime tests: 89 passed.
- Python compile check passed for the builder, shim, loader, manager, TutorBotCapability and AgentLoop touchpoints.
- No skill file reads remain outside `SkillsLoader` and `question_lifecycle_skills`.
- Trace metadata propagation is wired through AgentLoop -> TutorBot manager observation metadata -> TutorBotCapability result metadata for `question_lifecycle_scene`, `skill_stack`, `loader_source`, and `skill_source_status`.
- Local learning-brain e2e root cause fixed: local QA subprocesses now clear Supabase env and enable `DEEPTUTOR_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK`; `LearnerStateService.list_memory_events` honors local event authority only when that local fallback flag is enabled outside production.

Remaining production gates:

- Verify live Langfuse trace fields before production release.

## 17. Related Plans

- [2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md](2026-05-24-deeptutor-question-lifecycle-skill-authority-execution-plan.md)
- [2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md](2026-05-14-luban-skill-first-grading-thin-shell-execution-plan.md)
- [2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md](2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md)
- [2026-05-18-luban-learning-brain-gbrain-absorption-prd.md](2026-05-18-luban-learning-brain-gbrain-absorption-prd.md)
- [2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md](2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md)
