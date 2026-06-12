# M35 Artifact Ownership and Data Lifecycle Contract

Date: 2026-06-09

Scope: M35 scoring artifact ownership, lifecycle, runtime-consumability, and data growth boundaries.

## Authority

M35 scoring artifacts are global, versioned scoring assets. They are not per-learner memory, not RAG chunks, not published registry truth, and not official score authority.

Runtime wrappers may read a governed artifact and append shadow metadata. They must not decide artifact ownership, promote lifecycle status, write learner truth, or grant official scoring authority.

## Lifecycle

The required lifecycle is:

```text
candidate -> reviewed -> shadow_candidate -> release_candidate -> controlled_default -> superseded
```

`blocked` is a terminal quarantine state for unsafe or unsupported artifacts.

`controlled_default` is a lifecycle status only. It does not grant official score authority, published registry authority, or canonical learner-truth write authority.

## Runtime-Consumability Gate

No artifact may be runtime-consumable without owner_role, review_authority,
supersede_policy, rollback_policy, artifact_version, source_refs, and quality_gates.
Teachers maintain disputed and high-impact decisions; compiler workers maintain
candidates; deterministic gates maintain release eligibility.

Minimum gates:

- `artifact_version` exists and is immutable.
- `owner_role` names the accountable artifact owner.
- `review_authority` names the reviewer class, such as `teacher_validated` or `po_directional_single_reviewer`.
- `supersede_policy` names how a later artifact version replaces this one.
- `rollback_policy` names how runtime visibility is disabled.
- `source_refs` are present and source-bearing points are verifiable.
- `quality_gates.score_sum_ok=true`.
- `quality_gates.source_validity >= 0.95` before runtime-consumable status.

## Role Split

| Role | Responsibility | Not Allowed |
| --- | --- | --- |
| compiler worker | generate candidates and source-linked diffs | promote release truth |
| teacher / PO reviewer | review disputed, high-impact, and source-conflict decisions | edit runtime defaults directly |
| deterministic gate | evaluate lifecycle, source validity, score sum, rollback, supersede path | invent scoring semantics |
| runtime wrapper | read runtime-consumable artifact and append shadow metadata | write canonical learner truth or official score |

## Data Lifecycle

Artifacts are global/versioned. Attempts reference `artifact_version` and `point_id`; attempts must not copy the full artifact per learner.

Hot runtime traces may keep compact point-level references and evidence spans. Full artifacts and large review payloads belong in versioned artifact storage or cold review artifacts, not per-turn learner memory.

Global scoring artifacts are stored once per artifact_version and never copied per learner.
Student attempts store references to artifact_version and point_id, not full rubric copies.
Hot store keeps compact point evidence and current projections.
Prompt, raw LLM trace, and verbose review logs require TTL or cold object storage.
Read models aggregate learner_point_stats, learner_weaknesses, and review_plan_projection.
50k readiness is blocked until synthetic capacity covers 100k, 1M, and 3M attempts/month.

## 50k Capacity Gate

The capacity estimator is an estimate-only gate, not a load test. It must report three monthly attempt scenarios:

- `standard_100k`
- `heavy_1m`
- `peak_3m`

The expected growth driver is attempt evidence and trace storage, not global artifacts. Any design that copies full scoring artifacts per user fails this contract.

## Stop Conditions

Stop runtime consumption if any of these appear:

- missing owner or review authority
- missing rollback or supersede policy
- source validity below gate
- score sum not verified
- artifact copied into learner memory as canonical truth
- candidate used as release truth
- controlled default treated as official score authorization
- runtime wrapper mutates lifecycle status
