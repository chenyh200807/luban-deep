---
name: deeptutor-schema-authority-gate
description: "Protects DeepTutor schema and registry single authority. Use when creating, changing, renaming, deleting, registering, validating, or consuming stable schemas, typed objects, event payloads, ViewModels, capability request configs, unified turn payloads, learner-state projections, grading objects, or any cross-surface payload that should be machine-checkable."
---

# DeepTutor Schema Authority Gate

Use this skill when a change could affect the shape of data that crosses a
module, API, runtime, frontend, WeChat, observability, learner-state, or release
boundary.

## Authority Chain

1. `CONTRACT.md` defines when a boundary deserves a machine-readable schema.
2. `contracts/index.yaml` maps contract domains, protected files, and required
   tests.
3. `contracts/schema_registry.yaml` is the canonical registry for registered
   runtime and typed-object schemas.
4. Domain schema modules own validation:
   - turn schema: `deeptutor/contracts/unified_turn.py`
   - capability request config: `deeptutor/capabilities/request_contracts.py`
   - grading typed object: `deeptutor/services/construction_grading/unified_grading_object.py`
5. Guard scripts enforce the authority:
   - `python scripts/check_contract_guard.py <changed files>`
   - `python scripts/check_schema_registry.py <changed files>` when directly
     investigating schema registry failures.

Do not introduce a parallel schema file, enum, event catalog, ViewModel shape, or
payload validator if one of these authorities already owns the concept.

## Start Frame

```text
schema fact:
current authority:
registered name/version:
producer(s):
consumer(s):
compatibility impact:
registry impact:
validator/test impact:
delete or demote duplicate shapes:
```

If `current authority` is unknown, stop and inspect contracts before editing.

## Workflow

1. Classify the shape:
   - external stable contract;
   - runtime canonical schema;
   - registered typed object;
   - internal helper shape;
   - temporary candidate artifact.
2. For stable or runtime-canonical shapes, update the single authority first.
3. Register or update `contracts/schema_registry.yaml` when the shape belongs in
   the schema registry. Do not rely on prose-only docs for reusable payloads.
4. Update producers and consumers to use the canonical schema, not copied field
   lists or local enums.
5. Keep compatibility aliases at the edge. Normalize them before execution
   logic, trace, persistence, or learner truth.
6. Add or update tests listed in `contracts/index.yaml` or
   `contracts/schema_registry.yaml`.
7. Run the guard on the changed files and report the exact command.

## Red Flags

- A frontend ViewModel, WeChat payload, observability event, or BI shape invents
  fields that duplicate an existing schema concept.
- A new enum or event type is documented in prose but not registered or tested.
- A compatibility alias continues to participate in runtime decisions.
- A stable payload is validated in multiple places with diverging rules.
- A candidate artifact is promoted to runtime truth without registry,
  signature, lifecycle, or release gate.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "This is just a UI payload." | Cross-surface UI payloads can become second schema authority if producers and consumers copy fields. |
| "The schema is obvious from the code." | Stable boundaries need machine-checkable authority, not implied shapes. |
| "I'll add tests later." | Schema drift is exactly what contract and schema registry guards are meant to catch immediately. |
| "A local enum is harmless." | Local enums silently fork control-plane vocabulary unless they are projections of the canonical schema. |

## Verification

- [ ] `CONTRACT.md` and `contracts/index.yaml` were checked for stable boundary work.
- [ ] The schema authority and registered name/version are identified.
- [ ] `contracts/schema_registry.yaml` was updated or explicitly ruled out.
- [ ] Producers and consumers read the canonical shape rather than duplicate it.
- [ ] Contract/schema guard and focused tests were run or a concrete blocker is reported.
