#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

REMOTE_HOST="${REMOTE_HOST:-Aliyun-ECS-2}"
REMOTE_DIR="${REMOTE_DIR:-/root/deeptutor}"
PUBLIC_HOST="${PUBLIC_HOST:-8.135.42.145}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://test2.yousenjiaoyu.com}"
BACKUP_KEEP="${BACKUP_KEEP:-2}"

echo "执行阿里云完整部署: sync + docker compose up -d --build"

"${SCRIPT_DIR}/sync_to_aliyun.sh" once
"${SCRIPT_DIR}/validate_aliyun_release_env.sh"

echo "执行远端运行态备份，作为本次发布的回滚基线..."
ssh "${REMOTE_HOST}" "cd '${REMOTE_DIR}' && python3 scripts/backup_data.py --project-root '${REMOTE_DIR}' --keep '${BACKUP_KEEP}'"

ssh "${REMOTE_HOST}" "cd '${REMOTE_DIR}' && PUBLIC_HOST='${PUBLIC_HOST}' bash scripts/server_bootstrap_aliyun.sh"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL}" bash "${SCRIPT_DIR}/verify_aliyun_public_endpoints.sh"
bash "${SCRIPT_DIR}/verify_aliyun_observability.sh"
