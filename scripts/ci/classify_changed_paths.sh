#!/usr/bin/env bash
# Classify a changeset as code-relevant or docs-only.
#
# Reads a newline-separated changed-file list on stdin; prints exactly "true"
# or "false" on stdout: "true" when the changeset contains any code-relevant
# path (heavy CI jobs/steps should run), "false" when it is docs-only.
#
# Why this exists: the Tests workflow's required checks (Contract Guard, Test
# Summary) used to be `paths:`-filtered, so a docs-only PR never triggered them
# and strict branch protection BLOCKED the PR forever. The fix runs the
# required jobs on every PR and uses this classifier to skip the heavy work for
# docs-only changes while the required jobs still report success.
#
# Rule: docs-only (-> false) means every changed file is under docs/ EXCEPT
# docs/zh/guide/unified-turn-contract.md, which is an existing code-trigger
# path (turn-contract guide) and must still run the heavy contract checks.
# Anything outside docs/ (including root files) is code-relevant (-> true),
# which is strictly safer than the old behaviour of not triggering at all.
set -euo pipefail

code="false"
while IFS= read -r f || [ -n "$f" ]; do
  [ -z "$f" ] && continue
  case "$f" in
    docs/zh/guide/unified-turn-contract.md)
      code="true"
      break
      ;;
    docs/*)
      # docs change: not code-relevant on its own.
      ;;
    *)
      code="true"
      break
      ;;
  esac
done

printf '%s\n' "$code"
