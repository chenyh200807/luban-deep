#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${HERMES_EDU_REPO_URL:-https://github.com/zhongweiv/hermes-edu-skills.git}"
REF="${HERMES_EDU_REF:-v0.18.6}"
EXPECTED_COMMIT_PREFIX="${HERMES_EDU_COMMIT_PREFIX:-3646be2}"
TARGET="${HERMES_EDU_SOURCE:-$HOME/.cache/deeptutor/hermes-edu-skills}"

if [[ -e "$TARGET" && ! -d "$TARGET/.git" ]]; then
  echo "ERROR: HERMES_EDU_SOURCE exists but is not a git checkout: $TARGET" >&2
  exit 2
fi

if [[ ! -d "$TARGET/.git" ]]; then
  mkdir -p "$(dirname "$TARGET")"
  git clone --depth=1 --branch "$REF" "$REPO_URL" "$TARGET"
else
  git -C "$TARGET" fetch --depth=1 origin "$REF"
  git -C "$TARGET" checkout --detach FETCH_HEAD
fi

actual_commit="$(git -C "$TARGET" rev-parse HEAD)"
if [[ "$actual_commit" != "$EXPECTED_COMMIT_PREFIX"* ]]; then
  echo "ERROR: hermes-edu-skills commit mismatch: expected prefix $EXPECTED_COMMIT_PREFIX, got $actual_commit" >&2
  exit 3
fi

echo "Hermes upstream ready: $TARGET @ $actual_commit"
