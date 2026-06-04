# Observability Checklist for Authorized M19F

M19E does not run these checks; they are acceptance criteria for a future authorized remote deploy.

## Release lineage

- Host `.env` `DEEPTUTOR_GIT_SHA` / `DEEPTUTOR_RELEASE_ID` matches candidate release.
- Container env `DEEPTUTOR_GIT_SHA` / `DEEPTUTOR_RELEASE_ID` matches host `.env`.
- `DEEPTUTOR_GIT_DIRTY=false` in both host and container.

## Public health

- `https://test2.yousenjiaoyu.com/`
- `https://test2.yousenjiaoyu.com/healthz`
- `https://test2.yousenjiaoyu.com/readyz`

## Runtime safety

- qa_/operator_ limited default hit.
- non-cohort real student blocked.
- kill switch works.
- malformed registry fail-closed.
- provider failure fail-closed.
- legacy result remains unchanged.
- production_write_count=0.
- canonical_truth_written=false.

## Metrics

- submissions_total
- cohort_hit_count
- non_cohort_blocked_count
- deepseek_success_count
- qwen_fallback_count
- failclosed_count
- latency p50/p95/p99
- token and cost estimate p50/p95
- validator downgrade rate
- Learning Brain preview-only count
