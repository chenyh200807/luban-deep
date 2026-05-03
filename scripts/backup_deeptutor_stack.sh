#!/usr/bin/env bash
set -euo pipefail

ROOT="${DEEPTUTOR_STACK_ROOT:-/root/deeptutor}"
BACKUP_DIR="${DEEPTUTOR_BACKUP_DIR:-/root/deeptutor-backups}"
STAMP="$(date +%F-%H%M%S)"
OUT="$BACKUP_DIR/deeptutor-stack-$STAMP.tar.gz"

mkdir -p "$BACKUP_DIR"
cd "$ROOT"

tar -czf "$OUT" \
  data/user/settings \
  data/knowledge_bases \
  deployment/searxng \
  .env \
  docker-compose.yml \
  deployment/aliyun/docker-compose.langfuse.yml \
  scripts/acceptance_searxng.sh \
  scripts/backup_deeptutor_stack.sh

echo "$OUT"
