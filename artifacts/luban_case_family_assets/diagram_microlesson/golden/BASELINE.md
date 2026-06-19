# M0 Reality Lock and Baseline Freeze

Date: 2026-06-19

Status: baseline frozen for planning only. No artifact in this folder is promoted to production truth, release truth, or a finished golden asset during M0.

## Baseline Command Output

Command:

```bash
python - <<'PY'
from pathlib import Path
root=Path('artifacts/luban_case_family_assets/diagram_microlesson')
for p in sorted(root.glob('*.lesson.json')):
    print(p.name)
PY
```

Observed `*.lesson.json` inventory:

```text
A01_crane_lifting_safety.lesson.json
F16_qigu.lesson.json
J01_danger_work_expert_argumentation.lesson.json
J01_mvp.lesson.json
J01_mvp_render.lesson.json
N01_network_keypath.lesson.json
N01_network_video_first.lesson.json
S01_scaffold_template_acceptance.lesson.json
```

Interpretation: this is a mixed prototype/candidate directory. The file inventory is not a release manifest, not a production manifest, and not proof that every listed lesson participates in the first MVP slice.

## Target MVP Candidates

These are the first-phase MVP targets for the current plan. They remain prototype/candidate assets until a later gate explicitly promotes them.

| Target | Current prefix / file | Classification | Reality locked in M0 |
| --- | --- | --- | --- |
| J01 | `J01_danger_work_expert_argumentation.lesson.json` | target_mvp_candidate | Uses `schema_version: luban_teaching_animation.v0`. Current companion files include timing and `J01_danger_work_expert_argumentation.schema_draft.rendered.html`; no standard `J01_danger_work_expert_argumentation.rendered.html` was observed in the allowed artifact set. |
| N01 | `N01_network_video_first.lesson.json` | target_mvp_candidate | Uses `schema_version: luban_teaching_animation.v0`. Current companion files include timing, poster PNG, practice HTML, rendered HTML, and existing `N01_network_video_first.remotion.mp4`. Runtime gate fails on the current rendered HTML; see gate section. |
| S02 | `A01_crane_lifting_safety.lesson.json` | target_mvp_candidate / historical_prototype_prefix | S02 currently exists under the historical prefix `A01_crane_lifting_safety`. Current companion files include timing, practice HTML, and rendered HTML. M0 records this prefix mapping only; it does not rename files or create a new IR. |

## Regression Samples

These remain regression samples only. They are useful for guarding compatibility and renderer behavior, not for defining the first MVP production baseline.

| Sample | Current prefix / file | Classification | Reality locked in M0 |
| --- | --- | --- | --- |
| S01 | `S01_scaffold_template_acceptance.lesson.json` | regression_sample | Uses `schema_version: luban_teaching_animation.v0`. Current companion files include timing, poster PNG, practice HTML, rendered HTML, and existing `S01_scaffold_template_acceptance.remotion.mp4`. |
| F16 | `F16_qigu.lesson.json` | regression_sample | Uses `schema_version: luban_teaching_animation.v0`. Current companion files include timing, rendered HTML, and multiple rendered PNG snapshots. |
| C01 | no `C01*.lesson.json` observed | regression_sample | C01 is represented by `C01_construction_joint_contrast.schema_draft.rendered.html` and PNG snapshots such as deck and mobile states. It is a visual/schema-draft regression sample, not a lesson JSON baseline. |

## Parked Or Discarded For First Phase

These items are explicitly not part of the first MVP target set for M0. M0 does not delete them; it only prevents accidental promotion.

| Artifact | Classification | M0 decision |
| --- | --- | --- |
| `J01_mvp.lesson.json` | parked_prototype | Parked as an older J01 prototype. Do not treat as the J01 target MVP authority. |
| `J01_mvp_render.lesson.json` | parked_prototype | Parked as a render-specific J01 prototype. Do not treat as the J01 target MVP authority. |
| `N01_network_keypath.lesson.json` | parked_prototype | Parked as an earlier N01 keypath prototype. Do not treat as the N01 target MVP authority. |
| Other schema draft or benchmark assets in this directory | parked_or_out_of_scope | Outside the M0 target MVP set unless a later task explicitly pulls them into scope. |

## Gate Results

Command:

```bash
python artifacts/luban_case_family_assets/diagram_microlesson/validate_schema_drafts.py
```

Result: PASS.

Observed summary:

```text
schema spine 校验 (schema_version=luban_diagram_microlesson.v1)
汇总: 9/9 OK
```

Command:

```bash
node artifacts/luban_case_family_assets/diagram_microlesson/validate_learning_stage_runtime.mjs artifacts/luban_case_family_assets/diagram_microlesson/N01_network_video_first.rendered.html
```

Result: FAIL.

Observed summary:

```text
learning-stage runtime gate: FAIL (16 fail, 0 warn)
```

Failure shape:

| Check family | Current failure |
| --- | --- |
| `orientation_adaptive` | Current N01 rendered shell does not declare orientation-adaptive behavior. |
| `stage_visible` | Stage is missing or not visible across checked states. |
| `decision_first` | Initial decision options are not visible before playback in `portrait_initial_decision`. |
| `controls_visible` | Controls are not visible in checked playback states. |
| `theater_stage_origin` | Theater stage does not start at viewport origin in `portrait_theater_controls`. |

This failure is part of the M0 baseline. It must not be papered over by treating the current N01 rendered HTML as production-ready.

## M0 Boundaries

- No MP4 generated during M0.
- Existing MP4 files observed for N01 and S01 predate this M0 task and are inventory facts only.
- No IR was created, renamed, or forked during M0.
- No renderer was rewritten during M0.
- No artifact was promoted to production truth, release truth, or a finished golden asset.
- All files remain prototype/candidate/regression assets until a later task provides explicit promotion criteria and passing gates.
