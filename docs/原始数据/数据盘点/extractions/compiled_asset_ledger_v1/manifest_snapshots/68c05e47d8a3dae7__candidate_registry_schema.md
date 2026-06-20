# M6 Candidate Registry Schema

Version: `qga_v1_candidate_dry_run_m6_20260604`

This is a candidate dry-run schema, not a formal Registry v1 schema.

## Top-level registry

- `version_id`: fixed to `qga_v1_candidate_dry_run_m6_20260604`
- `package_status`: fixed to `candidate_dry_run`
- `simulation_only`: `true`
- `formal_registry_emitted`: `false`
- `questions`: map of `question_id -> candidate index row`
- `summary`: total question / point / candidate status counts

## Candidate artifact

- `schema_version`: `question_grading_artifact.v1_candidate_dry_run`
- `status`: one of `candidate_dry_run`, `draft_review`, `po_review_required`, `blocked_candidate`
- `question_authority_status`: copied from M5
- `scoring_points[].auto_certifiable`: copied only from M5 final authority decision
- `scoring_points[].runtime_auto_certification_allowed`: always `false` in M6
- `provenance.formal_registry_emitted`: always `false`
- `provenance.production_runtime_connected`: always `false`

## Publish boundary

`candidate_dry_run` is deliberately not `published`. The existing
`ArtifactRuntimeGate` only allows auto-certification for `published` artifacts, so
M6 cannot unlock runtime auto-certification.
