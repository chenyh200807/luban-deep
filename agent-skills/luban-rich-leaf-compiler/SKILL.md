---
name: luban-rich-leaf-compiler
description: Use this for DeepTutor Luban Nexus-like RichLeafArtifact compiler work, full 2026 source compilation, source-evidence agents, semantic review queues, runtime-supply candidates, scoring A/B, Grading-to-Brain Loop dry-runs, or any task that could confuse candidate artifacts with release truth.
---

# Luban Rich Leaf Compiler

Use this skill to run RichLeaf/Nexus-like compilation without creating a second
truth source or accidentally promoting AI candidates into runtime authority.

## Start Gate

Write this frame before changing code, generating artifacts, or reporting GO:

```text
one business fact:
one authority:
source lanes:
candidate/review/release state:
runtime default status:
Learning Brain write status:
verification target:
not_exercised:
```

If any state is unknown, mark it `unknown` or `not_exercised`; do not infer GO.

## Authority Rules

- Taxonomy comes from canonical taxonomy only. LLMs cannot edit leaf ids or paths.
- Textbook/standard source spans are source truth; lecture is teaching evidence;
  question bank is assessment evidence; student answers are learner/sample evidence.
- RichLeafArtifact is compiled context authority, not source truth, rubric truth,
  learner truth, official score, or release truth.
- AI/council/Codex review is `shadow` unless a separate governance gate says
  otherwise.
- `candidate_only`, `review_only`, `runtime_install_allowed=false`,
  `release_truth_claimed=false`, `official_score_allowed=false`, and
  `production_write_count=0` must survive every workbench artifact.
- Runtime default, canonical learner truth, official score, remote write, and DB
  write require explicit authorization and readback gates.

## Workflow

1. Lock paths and dirty state:
   - `pwd -P`
   - `git rev-parse --show-toplevel`
   - `git status --short --branch`
   - record source root, usually `.../FastAPI20251222/docs/2026`
2. Run or inspect Phase 0 contracts:
   - schema/validator
   - source lane registry
   - field claim envelope
   - lifecycle matrix
   - CompiledContextPack contract
3. Compile candidates in this order:
   - sampler
   - skeleton compiler
   - source gap candidates
   - candidate patch generator
   - patch evidence audit
   - weak source refinement
   - source-evidence agent
   - semantic audit packets / queue / shards / suggestions
4. Convert suggestions to review decisions only as shadow review:
   - accept/reject/needs-external may be materialized with reviewer id
   - manual-review remains missing, not forced through
   - validate decisions before audit-record ingestion
5. Only after validated decisions:
   - build semantic evidence audit record
   - build reviewed candidates
   - compile rich field candidates
   - assemble artifact candidates
   - run interop audit and focused tests
6. Only after reviewed artifact candidates exist:
   - build runtime supply candidate in a new versioned directory
   - run regression, context-pack smoke, offline/nearline/live A/B as available
   - keep runtime default off until authorized
7. For Grading-to-Brain:
   - produce `learner_memory_event` candidates only
   - run sandbox/test learner readback gates before any write
   - never let RichLeaf write canonical learner truth directly

## Decision Table

| Evidence | Allowed claim |
|---|---|
| source-gap candidates only | review-ready source candidates |
| patch precheck pass | machine-prechecked strong candidates |
| suggestions only | non-binding review suggestions |
| shadow decisions validated | shadow-reviewed candidates |
| reviewed candidates > 0 | reviewed source-ref candidates |
| artifact candidates > 0 + interop pass | local candidate artifact bundle |
| runtime supply candidate + regression | runtime candidate, not default |
| live A/B + authorization + rollback | controlled-default candidate |
| governance signoff | release claim, if gate says so |

## NO-GO Signals

- Bucket/taxonomy/authority fields are hand-filled to pass a gate.
- `source_ref` is created without readable path, record id, span, and hash.
- Question-bank evidence becomes mandatory rule.
- Synthetic mistakes become learner truth.
- `manual_review_required` is auto-accepted.
- Interop summary is used without checking what its count actually means.
- A local/offline adapter result is reported as live provider A/B.
- Runtime default or DB write happens before explicit authorization.

## Verification

For code changes, run focused tests first, then the RichLeaf suite:

```bash
python3 -m pytest tests/services/construction_grading/test_rich_leaf_artifacts_phase0.py tests/scripts/test_luban_rich_leaf_*.py -q
```

For artifact runs, print summary fields from each JSON and assert the boundary:

```text
candidate counts:
decision counts:
reviewed candidate counts:
artifact candidate counts:
safety invariants:
not_exercised:
```

Do not claim completion from green tests alone. Match the claim to the strongest
artifact actually produced.

## Report Template

```text
Status:
Compiled scope:
Artifacts produced:
Reviewed candidate count:
Runtime/default status:
Learning Brain write status:
Tests:
Safety invariants:
NO-GO / WEAK-GO blockers:
Next action:
```
