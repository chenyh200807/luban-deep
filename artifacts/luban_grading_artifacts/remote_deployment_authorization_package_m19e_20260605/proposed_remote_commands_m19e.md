# Proposed Remote Commands (documentation only; not executed)

All commands below are pending explicit user authorization for M19F. They are not run by M19E.

## 1. Preflight read-only commands

```bash
git status --short --branch
git rev-parse HEAD
ssh Aliyun-ECS-2 "cd /root/deeptutor && grep -E '^DEEPTUTOR_(GIT_SHA|RELEASE_ID|GIT_DIRTY)=' .env"
ssh Aliyun-ECS-2 "cd /root/deeptutor && grep -E '^LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_' .env || true"
ssh Aliyun-ECS-2 "docker inspect deeptutor --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(DEEPTUTOR_|LUBAN_V1_LLM_ADJUDICATOR_)'"
```

## 2. Authorized deploy commands

Use the existing runbook/scripts only. Do not replace them with ad hoc `ssh docker compose`.

```bash
# Apply the authorized env diff to Aliyun-ECS-2:/root/deeptutor/.env only.
# Then run one existing runbook path from the local repo:
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/redeploy_aliyun_fast.sh

# If dependencies, Dockerfile, or full build surface changed, use:
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/deploy_aliyun.sh
```

## 3. Rollback commands

See `rollback_commands_m19e.md`. Rollback must cover env kill, flag off, registry unavailable, and code rollback.

## Acceptance commands after authorized M19F

```bash
ssh Aliyun-ECS-2 "cd /root/deeptutor && grep -E '^DEEPTUTOR_(GIT_SHA|RELEASE_ID|GIT_DIRTY)=' .env"
ssh Aliyun-ECS-2 "docker inspect deeptutor --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^DEEPTUTOR_(GIT_SHA|RELEASE_ID|GIT_DIRTY)='"
PUBLIC_BASE_URL=https://test2.yousenjiaoyu.com bash scripts/verify_aliyun_public_endpoints.sh
bash scripts/verify_aliyun_observability.sh
```
