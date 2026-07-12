---
name: deeptutor-git-workflow-gate
description: "Governs DeepTutor branch, worktree, dirty-file, staging, commit, merge, and push behavior. Use before creating branches or worktrees, staging files, committing, resolving conflicts, merging to main, or handling parallel agent work."
---

# DeepTutor Git Workflow Gate

Use this skill to keep version-control actions narrow and reversible.

## Workflow

1. Confirm repo with `git rev-parse --show-toplevel`.
2. Record `git status --short --branch` before edits and before staging.
3. Do not create or switch branches unless the user asked or isolation is
   required by risk or parallel work.
4. Before creating a worktree, declare four things: worktree path, base
   branch, target branch name, and the task scope that worktree owns. After
   creation, work only inside that worktree for that task line.
5. Never reset, stash, checkout, or overwrite user/parallel-agent changes
   without explicit instruction. Never embed `git stash` in diagnostic or
   merge command chains: it sweeps away conflict resolutions and clears
   `MERGE_HEAD` mid-merge.
6. Stage only files in the current task boundary. Never use `git add -A` or
   `git add .` in dirty shared worktrees: they sweep parallel-agent WIP into
   your commit, and other parallel committers will sweep away your own
   uncommitted work the same way (this has happened twice).
7. For commits in dirty worktrees, use `git commit --only -- <files>` or
   precise `git add <file>` per file.
8. After commit, check `git show --stat HEAD`: it must contain only this
   task's files, and parallel WIP must still be dirty.

## Merge To Main Addendum

If the user asks to merge to main:

- use a clean candidate worktree when current workspace is dirty;
- report remote `origin/main` commit, deployment state, and whether the current
  local workspace is back on `main` (if not, say why);
- do not hide local dirty blockers.

Contract-guard protected files (sources registered in
`deeptutor/contracts/index.yaml`, e.g. `deep_question.py`,
`rubric_grader_v1.py`): any change must also update one of that domain's
registered `test_files` with a test covering the change, or the required
contract-guard gate fails. Before merge/push, run
`python scripts/check_contract_guard.py <changed files>` and confirm
`contract-guard: passed`.

## Verification

- [ ] Repo, branch, and dirty files were recorded.
- [ ] Staged files match the task boundary.
- [ ] No unrelated dirty file was swept into commit (`git show --stat HEAD`).
- [ ] Contract-guard passed locally when protected files changed.
- [ ] Merge/push reports include exact commit ids when performed.
