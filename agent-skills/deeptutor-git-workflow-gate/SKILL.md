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
4. Never reset, stash, checkout, or overwrite user/parallel-agent changes
   without explicit instruction.
5. Stage only files in the current task boundary. Avoid `git add -A` and
   `git add .` in dirty shared worktrees.
6. For commits in dirty worktrees, prefer precise `git add <file>` or
   `git commit --only -- <files>`.
7. After commit, check `git show --stat HEAD` for payload scope.

## Merge To Main Addendum

If the user asks to merge to main:

- use a clean candidate worktree when current workspace is dirty;
- report remote `origin/main` commit, deployment state, and whether the current
  local workspace is back on `main`;
- do not hide local dirty blockers.

## Verification

- [ ] Repo, branch, and dirty files were recorded.
- [ ] Staged files match the task boundary.
- [ ] No unrelated dirty file was swept into commit.
- [ ] Merge/push reports include exact commit ids when performed.
