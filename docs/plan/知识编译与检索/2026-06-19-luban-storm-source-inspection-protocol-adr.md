# ADR: STORM 只能作为 Source Inspection Protocol

> Status: Proposed
> Date: 2026-06-19
> Scope: DeepTutor / 鲁班知识编译、OKF-like source layer、评分工件审查、研究综合与 ADR 决策

## Decision

鲁班吸收 Stanford STORM 方法的多视角研究结构，但只把它落成离线
`Source Inspection Protocol`。STORM 的输出是 candidate/review-only 的
问题、claim cards、矛盾地图、peer review ledger 和 work orders。

STORM 不新增 runtime、RAG provider、评分器、LearnerState/GBrain 写入层、
TutorBot persona committee、answer key、official score authority 或
published registry。

## One Business Fact

系统真正要维护的一等业务事实是：

> 对一个知识编译对象、评分工件、source bundle、产品假设或外部方法吸收对象，
> 生成多视角问题、source-grounded claims、矛盾地图、风险清单和待验证 work orders，
> 用来提高审查覆盖率，而不是直接生成生产真相。

## One Authority

STORM 没有新的业务 authority。它只能服务现有 authority：

| Fact | Existing authority | STORM role |
| --- | --- | --- |
| Grounding / retrieval | `RAGService` and registered sources | Find source gaps and source bias; no direct retrieval entry |
| Scoring rules / official score | signed grading artifact / `CaseGradingSkillKernel` / governed grading policy | Find rubric ambiguity and boundary cases; no score writing |
| OKF-like pilot artifacts | canonical extraction plus explicit review projection boundary | Inspect provenance and ambiguity; no source-truth promotion |
| Learner truth | learner evidence ledger and LearnerState synthesis | Suggest hypotheses for review; no learner fact write |
| TutorBot execution | `/api/v1/ws` and TutorBot runtime contracts | Review explanation risks; no runtime persona committee |
| Plan / ADR authority | `docs/plan/INDEX.md` and domain plan files | Produce review findings and work orders |

## Canonical Path

Allowed path:

```text
STORM method
-> multi-perspective questions
-> source-grounded claim cards
-> contradiction map
-> peer-review ledger
-> review work orders
-> existing compiler feedback / review queue
-> existing compiler and release gate
-> signed runtime_supply only if separately authorized
-> existing runtime consumer
```

Forbidden path:

```text
STORM persona consensus
-> direct RAG source / prompt patch / rubric / score / learner truth
```

## Allowed

- Use multi-perspective questioning to inspect a source bundle, plan, ADR,
  rubric extraction, compiled candidate, eval design, or external method.
- Produce `inspection_findings.md`, `claim_cards.jsonl`,
  `contradiction_map.json`, `review_work_orders.jsonl`, and
  `peer_review_ledger.md`.
- Create compiler feedback or human review work orders when each issue carries
  source refs, confidence, affected authority, and allowed next step.
- Use STORM during OKF-like pilot review, RichLeaf/RAG source audit, grading
  evaluation design, and product hypothesis review.
- Run STORM through the repo-local workflow skill
  `agent-skills/deeptutor-storm-source-inspection/SKILL.md`.

## Forbidden

- No `storm_tool`, `storm_search`, `storm_agent`, `storm_rag`,
  `storm_score`, `storm_memory`, `storm_context_pack`, or second chat route.
- No product runtime fanout to five personas inside TutorBot, grader, RAG,
  LearnerState, or GBrain.
- No STORM output writes to `runtime_supply`, questions bank, published
  registry, official score, answer key, canonical learner truth, mastery state,
  or diagnosis truth.
- No majority or consensus field may be treated as source evidence.
- No STORM synthesis may be indexed as a primary citation source for the same
  claim it synthesized.
- No promotion from inspection layer to runtime supply without a separate
  signed release gate, owner, rollback path, and eval evidence.

## Required Artifact Shape

Each finding must preserve uncertainty:

```text
id:
authority_status: candidate_review
runtime_allowed: false
official_score_allowed: false
learner_truth_write_allowed: false
canonical_write_allowed: false
type:
severity:
claim:
perspective:
source_ref:
source_span:
confidence:
contradiction:
unresolved_question:
affected_authority:
recommended_owner:
allowed_next_step:
forbidden_next_step:
```

Claims without source spans are allowed only as `verification_needed`.

## Evaluation Gates

For knowledge compilation:

- `authority_gate`: output remains candidate/review-only.
- `source_gate`: every factual claim has an approved source or becomes HOLD.
- `roundtrip_gate`: source projection to compiled candidate preserves
  provenance and non-runtime flags.
- `dry_consumer_gate`: a consumer can read the compiled candidate shape without
  treating it as runtime supply.

For scoring:

- `rubric_gate`: acceptable expressions, counterexamples, and boundary samples
  are explicit.
- `irr_gate`: inter-rater agreement is measured before production scoring
  claims.
- `anti_over_credit_gate`: high-severity false positives are zero-tolerance.
- `appeal_gate`: point-level dispute and repair feedback path exists before
  claiming trusted grading.

For product:

- `learning_gate`: verify score-sentence production, D1/D7 retest, or
  confident-wrong reduction.
- `retention_economics_gate`: pre-register D1/D7, sample size, cost per
  attempt, review minutes, and appeal upheld rate.

## 30-Day Shadow Validation

The only approved near-term expansion is shadow/concierge validation:

- One case family and one OKF-like source bundle.
- At least 20 gray users or equivalent supervised participants.
- At least 100 valid attempts and 30 retest/repractice entries.
- At least 40 grading samples, including boundary samples and real or
  near-real student answers.
- D1 return target: 50%; hard fail below 35%.
- D7 return target: 25%; hard fail below 15%.
- Student trust statement "I know why points were lost and how to improve":
  target 70%.
- Point-level recall target: 85%; precision target: 80%.
- High-severity over-credit: 0.

Passing this validation still does not authorize runtime scoring or published
registry promotion. It only authorizes a follow-up plan.

## Stop Conditions

Stop immediately if:

- a STORM artifact is about to be consumed directly by runtime, RAG, grader,
  TutorBot, LearnerState, GBrain, or a published registry;
- an output loses source spans, provenance, confidence, or unresolved-question
  fields;
- prompt consensus is being treated as source evidence;
- a proposed fix adds a wrapper/router/fallback instead of restoring the
  existing authority path;
- success is defined as "better report" without deterministic replay, baseline,
  human adjudication, or product metric.

## Consequences

This decision intentionally limits STORM to review and synthesis. It may feel
slower than wiring multi-agent research into runtime, but it prevents a second
knowledge truth, second scoring truth, second learner truth, and second RAG
entry from forming.

The next implementation step is not a runtime integration. It is to use
`deeptutor-storm-source-inspection` on the existing OKF-like rubric pilot and
produce review-only work orders.
