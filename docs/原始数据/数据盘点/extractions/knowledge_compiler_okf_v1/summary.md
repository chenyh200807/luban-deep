# Knowledge Compiler OKF v1

- Generated at: `2026-07-16T14:54:49+08:00`
- Authority: compiler workbench inventory only; not runtime supply and not official scoring authority.
- Runs indexed: **14**
- Files indexed: **189**
- Total bytes: **50,729,003**

## Stage Counts

- `candidate`: 10
- `fixture`: 4

## Compiler Runs

| Run | Stage | Kind | Files | Bytes |
|---|---|---|---:|---:|
| `lecture_compile_20260608` | `candidate` | `lecture_compile` | 8 | 1,426,351 |
| `mvp-answer-rubric-20260531` | `candidate` | `answer_rubric_candidate` | 3 | 38,854 |
| `mvp-rubric-ab-20260531` | `candidate` | `rubric_ab_eval` | 4 | 10,588 |
| `mvp-rubric-ab-20q-20260531` | `candidate` | `rubric_ab_eval` | 4 | 105,152 |
| `mvp-rubric-artifact-20260531` | `candidate` | `rubric_artifact_candidate` | 5 | 116,802 |
| `mvp-rubric-artifact-20q-20260531` | `candidate` | `rubric_artifact_candidate` | 5 | 319,088 |
| `pytest-core-a` | `fixture` | `test_fixture` | 8 | 2,416 |
| `pytest-core-b` | `fixture` | `test_fixture` | 10 | 1,340 |
| `pytest-inventory` | `fixture` | `test_fixture` | 2 | 970 |
| `pytest-scoring-point-assets` | `fixture` | `test_fixture` | 5 | 8,680 |
| `scoring-point-assets-20260602` | `candidate` | `scoring_point_candidate_assets` | 84 | 41,765,074 |
| `scoring-point-recall-calibration-20260602` | `candidate` | `scoring_point_recall_calibration` | 7 | 901,610 |
| `scoring-point-recall-calibration-v2-20260602` | `candidate` | `scoring_point_recall_calibration` | 18 | 2,175,928 |
| `scoring-point-recall-calibration-v2-backfill-20260602` | `candidate` | `scoring_point_recall_calibration` | 26 | 3,856,150 |

## Guardrails

- `candidate` means useful compiler output that still needs source review or signing.
- `release` means release-shaped naming only unless a separate runtime supply pointer signs it.
- `fixture` means test/workbench data; never promote directly into production runtime supply.
- This ledger copies no payloads. Source files remain in `artifacts/knowledge_compiler/2026`.