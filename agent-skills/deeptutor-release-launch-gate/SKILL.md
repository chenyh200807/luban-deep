---
name: deeptutor-release-launch-gate
description: "Controls DeepTutor release, merge-to-main, push, Aliyun deploy, rollback, and post-launch verification. Use when preparing production or test2 release closure, syncing to Aliyun, validating deployment truth, or planning rollback."
---

# DeepTutor Release Launch Gate

Use this skill when a task moves from local correctness to release truth.

## Authority

- Local tests and contract guard prove candidate correctness.
- Git push proves remote source availability.
- Host/container SHA and dirty flags prove deployed code identity.
- Public `/`, `/healthz`, `/readyz`, release payload, observability payload, and
  Langfuse connectivity prove service readiness.
- Aliyun host writes are limited to `/root/deeptutor`.

## Aliyun Write Boundary

- Iron rule: on the Aliyun host, only files inside `/root/deeptutor` may be
  modified. Any `ssh Aliyun-ECS-2`, remote script, `rsync`, `scp`,
  `docker cp`, hotfix, backup, rollback, or deploy verification that writes a
  remote host file must first prove the target path is inside
  `/root/deeptutor`.
- `/root/luban`, `/etc`, `/usr`, `/var`, `/opt`, `/home`, nginx system config,
  system services, global cron, and host Docker config are read-only
  observation surfaces: no create, edit, delete, move, or overwrite.
- Outside `/root/deeptutor`, only read-only commands are allowed: `ls`,
  `cat`, `sed -n`, `grep`/`rg`, `docker ps`, `docker logs`. No redirection,
  `tee`, `rm`, `mv`, `cp`, `chmod`, `chown`, package installs, or anything
  that mutates host state.
- If a fix appears to require writing outside `/root/deeptutor`, stop
  executing. Explain to the user the reason, target path, risk, and
  alternatives; do not touch it without new explicit authorization.
- Release scripts and runbooks must treat `/root/deeptutor` as the sole write
  root; do not route around the boundary via temp directories.

## Workflow

1. Lock repo, branch, dirty state, local HEAD, and remote target.
2. Ensure the release candidate is clean or isolated in a clean worktree.
3. Run focused tests and `scripts/check_contract_guard.py` for changed protected
   files.
4. Push the exact intended commit.
5. Choose deploy path:
   - pure backend narrow fix: prefer `scripts/redeploy_aliyun_fast.sh`;
   - dependencies, Dockerfile, standalone web, frontend build, or
     `requirements/server.txt`: use `scripts/deploy_aliyun.sh`.
6. Verify host/container/public/observability truth. Do not stop at script exit
   code or `docker compose ps`.
7. Record rollback point and remaining unverified surfaces.

## Red Flags

- Dirty `main` is used directly as release truth.
- Deploy report omits SHA, dirty flag, public endpoints, or observability
  payload.
- A remote write targets anything outside `/root/deeptutor`.
- Web/WeChat closure is inferred from backend deploy.

## Verification

- [ ] Candidate commit and remote branch are named.
- [ ] Local tests and contract guard status are reported.
- [ ] Deploy path matches changed files.
- [ ] Public endpoint and observability evidence are checked.
- [ ] Rollback point is known.
