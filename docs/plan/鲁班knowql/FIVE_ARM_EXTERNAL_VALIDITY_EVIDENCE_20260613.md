# Five-Arm External-Validity Evidence Pack - 2026-06-13

结论：**B failed / regression**。

这里的失败边界很窄：不是说 production 判分链路回归，也不是说 atomic contract 没价值；而是这次 15 个 student-answer fixture、5 arms、3 live trials 没有支持“`arm_B_atomic_contract` 稳定优于 A0/A1/RAG+ref/RAG_only”的假设。B 的 anti-over-credit 很稳，但 calibration MAE 和 latency 没有赢过 RAG+ref。

## Scope

- review-only harness only.
- No production runtime change.
- No DB writes.
- No canonical truth writes.
- Official answer key remains the scoring authority; AI labels do not override it.
- RAG arms are comparison baselines only, not grading authority.

## Inputs

- Blueprint: `docs/plan/鲁班knowql/KNOWQL_BUILDOUT_BLUEPRINT.md`
- Harness: `scripts/run_luban_per_question_grading_ab.py`
- External fixture: `deeptutor/services/construction_grading/fixtures/per_question_grading_external_validity_fixtures.json`
- Contract compiler: `deeptutor/services/construction_grading/per_question_grading_object.py`
- Judge diagnostics: `deeptutor/services/construction_grading/per_question_grading_judge.py`
- Student-answer corpus: `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库/近三年案例题_按学生答卷排版.docx`

Note: the corpus itself says it is “10名学生模拟作答”; this pack treats it as a student-answer external-validity corpus, not human-expert gold.

## Run

```bash
python3 scripts/run_luban_per_question_grading_ab.py \
  --live \
  --progress \
  --call-timeout 180 \
  --max-tokens 4096 \
  --fixtures deeptutor/services/construction_grading/fixtures/per_question_grading_external_validity_fixtures.json \
  --out-dir artifacts/luban_grading_artifacts/five_arm_external_validity_20260613 \
  --trials 3
```

Artifacts:

- `artifacts/luban_grading_artifacts/five_arm_external_validity_20260613/per_question_grading_ab_live_llm.json`
- `artifacts/luban_grading_artifacts/five_arm_external_validity_20260613/per_question_grading_ab_dry_run_label_oracle.json`

## Fixture Coverage

- 15 answer-level fixtures: 3 compiled questions x 5 answers.
- Answer types: complete, over_credit_trap, partial, distractor.
- Each fixture partitions all point_ids into `covered_point_ids`, `missing_point_ids`, `partial_point_ids`, `contradiction_point_ids`.
- Exact official slice leakage is guarded by focused test.
- Historical label `Q2024-03__S05_skip_subq5` maps to the compiled contract `Q2024-1A432000-P0015-01`, which corresponds to docx source `Q2024-04__S05` (工程量清单/违法分包/结算造价). It is kept as a continuity label for the skip-subquestion-5 counterexample.

## Live Results

N = 15 fixtures x 5 arms x 3 trials = 225 live judge calls. `parse_error_rate = 0.0` for every arm after setting `--max-tokens 4096` and `--call-timeout 180`.

| arm | calibration MAE mean±std | over-credit rate mean±std | false-hit | parse_error | mean tokens | mean latency ms | mean TTFT ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| A0 freestyle | 0.0407±0.0148 | 0.0000±0.0000 | n/a | 0.0000 | 1118.93 | 4408.10 | 4114.10 |
| A1 self-decompose | 0.0597±0.0116 | 0.0278±0.0481 | n/a | 0.0000 | 2438.56 | 13764.75 | 11056.41 |
| B atomic contract | 0.0546±0.0058 | 0.0000±0.0000 | 0.0000 | 0.0000 | 2572.53 | 11004.28 | 8664.59 |
| RAG only | 0.1501±0.0653 | 0.0833±0.0834 | n/a | 0.0000 | 3029.33 | 8287.82 | 7865.71 |
| RAG + ref | **0.0306±0.0120** | 0.0000±0.0000 | n/a | 0.0000 | 2945.36 | **4675.36** | **4326.29** |

## Required Answers

### Q2024 skip 小问5 counterexample

Pass for B: all three trials scored exactly `0.75` against true coverage `0.75`.

| trial | B score | true coverage | B MAE | B false-hit |
|---:|---:|---:|---:|---:|
| 0 | 0.75 | 0.75 | 0.00 | 0.00 |
| 1 | 0.75 | 0.75 | 0.00 | 0.00 |
| 2 | 0.75 | 0.75 | 0.00 | 0.00 |

RAG+ref did not give 100 in this external pack, but it did not match the true coverage as tightly:

| trial | RAG+ref score | true coverage | MAE |
|---:|---:|---:|---:|
| 0 | 0.80 | 0.75 | 0.05 |
| 1 | 0.74 | 0.75 | 0.01 |
| 2 | 0.80 | 0.75 | 0.05 |

### Is RAG+ref still worse than B?

No. In this pack, RAG+ref is better on calibration MAE and faster:

- RAG+ref MAE: `0.0306±0.0120`
- B MAE: `0.0546±0.0058`
- RAG+ref mean latency: `4675.36 ms`
- B mean latency: `11004.28 ms`

B still beats RAG+ref on the typed diagnostic that RAG+ref does not expose: per-point false-hit is measurable for B and was `0.0`. But that is not enough to claim B stable superiority across the requested five-arm metrics.

## Interpretation

The evidence now points to a narrower role for B:

- Good: anti-over-credit trap handling.
- Good: per-point false-hit visibility.
- Good: deterministic coverage on the must-pass Q2024 skip-subquestion-5 counterexample.
- Bad: not best calibration MAE on this external pack.
- Bad: slower than A0 and RAG+ref.
- Bad: token-heavy on 24-point contracts.

Therefore B should not be promoted as a production default or as a replacement for the current RAG+ref/reference lane from this evidence. The better next experiment is not another prompt-only bump; it is to test a hybrid adjudication shape: keep RAG+ref as the fast initial scorer, then invoke B only for over-credit-risk cases, high-stakes missed-subquestion checks, or per-point feedback generation.

## Verification

Focused test added:

```bash
python3 -m pytest tests/scripts/test_luban_per_question_grading_ab_external_validity.py -q
```

Dry-run replay:

```bash
python3 scripts/run_luban_per_question_grading_ab.py \
  --fixtures deeptutor/services/construction_grading/fixtures/per_question_grading_external_validity_fixtures.json \
  --out-dir artifacts/luban_grading_artifacts/five_arm_external_validity_20260613 \
  --trials 3
```

Final acceptance verification is tracked separately in the run closeout.
