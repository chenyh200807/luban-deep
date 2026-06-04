# M19E Deployment Authorization Form

M19E verdict: **GO for authorization package**.

This form does **not** authorize deployment by itself. M19F actual remote deploy is **等待用户显式授权**.
Until that authorization is given,不得执行 ssh 写入、不得修改 Aliyun `.env`、不得 deploy/restart。

## Requested scope for M19F

- Remote root: `Aliyun-ECS-2:/root/deeptutor` only.
- Env diff:
  - `LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=true`
  - `LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_COHORT=qa_,operator_`
- Cohort: `qa_` and `operator_` only.
- Use existing runbook scripts: `redeploy_aliyun_fast.sh` or `deploy_aliyun.sh`.

## Explicitly not authorized

- Broad production default: **NO-GO**.
- Canonical learner truth write: **NO-GO**.
- Production DB write: **NO-GO**.
- Published registry emission: **NO-GO**.
- M20.1 delta in current runtime: **NO-GO**.
- Remote writes outside `/root/deeptutor`: **NO-GO**.

## Approval checkbox for user

`[ ] I explicitly authorize M19F actual remote deploy for the limited qa_/operator_ default only.`
