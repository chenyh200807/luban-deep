# Rollback Commands (documentation only; not executed)

All remote writes, if authorized later, must stay inside `Aliyun-ECS-2:/root/deeptutor`.

## 1. env kill switch

```bash
# In /root/deeptutor/.env:
LUBAN_V1_LLM_ADJUDICATOR_ENABLED=false

# Then use the existing runbook restart path:
bash scripts/restart_aliyun.sh
```

## 2. flag off / limited default off

```bash
# In /root/deeptutor/.env:
LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=false

# Keep request-flag explicit path only; qa_/operator_ no longer get default-on behavior.
bash scripts/restart_aliyun.sh
```

## 3. registry unavailable fail-closed drill

```bash
# Temporarily point the release registry config to an unavailable candidate inside /root/deeptutor
# and verify the adjudicator fail-closes while legacy construction_grading_result remains intact.
# Do not write outside /root/deeptutor.
```

## 4. code rollback

```bash
bash scripts/rollback_aliyun_release.sh
```

Rollback acceptance:

- legacy result remains intact.
- non-cohort users remain blocked from limited default.
- production_write_count remains 0.
- canonical_truth_written remains false.
- public endpoint health remains passing after rollback.
