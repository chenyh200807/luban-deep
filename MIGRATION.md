# DeepTutor migration: shared gitdir → independent clone

**Date:** 2026-05-24 23:42:44 +0800
**New primary:** `/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor-clean-main-20260524`
**Old primary:** `/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor` (DISABLED)

## Why

The old DT used a pointer `.git` file redirecting to `/Users/yehongchen/.gitdirs/deeptutor-documents.git`. That shared gitdir's `core.worktree` was repeatedly hijacked by concurrent Codex sessions creating new worktrees in `/private/tmp/deeptutor-*`. Result: from inside old DT, `git status` / `git diff` / `git add` / `git commit` were operating on a *different* worktree than the user's physical files. Commit evidence was untrustworthy.

## What changed

1. **New independent clone** at `deeptutor-clean-main-20260524` — `.git` is a directory, `core.worktree` unset, completely independent of the polluted `.gitdirs`.
2. **Old DT's `.git` pointer disabled**: renamed to `.git.disabled`. Any `git` command run from inside old DT now correctly reports "not a git repository," preventing accidental commits to the wrong worktree.

## Restoring old DT (if ever needed)

```
mv /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.git.disabled \
   /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.git
```

## Recommended workflow now

- **Use this directory** as your sole development workspace.
- **Add a shell alias** in your `~/.zshrc` or `~/.bashrc`:

```
alias dt='cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor-clean-main-20260524'
```

- **IDE**: open this folder in your editor (VSCode/Cursor/JetBrains). Close any old DT project window.
- **Codex sessions** still using the `.gitdirs`-based worktrees in `/private/tmp/deeptutor-*` continue to work; their state is independent of this clone.

## Outstanding artifacts

- **PR #41** ("feat: assessment testset P0A execution plan + integration (DT snapshot)") captures old DT's real dirty state at 2026-05-24 22:56. Review and merge or close as appropriate.
- **PR #38** (report training inside learning module) and **PR #39** (route assessment answers into learning evidence) were merged earlier during cleanup.
- **Stash patches** at `~/stash-backups/20260524-214958-stash{0,1}-*.patch` from earlier cleanup; restore with `git apply` if needed.

## How to verify this clone is healthy

```
cd /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor-clean-main-20260524
git rev-parse --show-toplevel    # must equal pwd
git config --get core.worktree   # must be empty
git worktree list                # must show only this path
```

If `core.worktree` is ever non-empty here, something has broken the independence — investigate immediately.
