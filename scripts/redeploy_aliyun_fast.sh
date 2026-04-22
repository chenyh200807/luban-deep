#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REMOTE_HOST="${REMOTE_HOST:-Aliyun-ECS-2}"
REMOTE_DIR="${REMOTE_DIR:-/root/deeptutor}"
PUBLIC_HOST="${PUBLIC_HOST:-8.135.42.145}"
BACKUP_KEEP="${BACKUP_KEEP:-2}"

echo "执行阿里云快速发布: sync + docker cp + restart"
echo "适合 Python 后端 / Prompt / YAML 改动；若改了 Dockerfile、requirements、前端构建产物，请改用 deploy_aliyun.sh"

"${SCRIPT_DIR}/sync_to_aliyun.sh" once
"${SCRIPT_DIR}/validate_aliyun_release_env.sh"
echo "执行远端运行态备份，作为本次快速发布的回滚基线..."
ssh "${REMOTE_HOST}" "cd '${REMOTE_DIR}' && python3 scripts/backup_data.py --project-root '${REMOTE_DIR}' --keep '${BACKUP_KEEP}'"
ssh "${REMOTE_HOST}" "cd '${REMOTE_DIR}' && PUBLIC_HOST='${PUBLIC_HOST}' bash scripts/server_fast_reload_aliyun.sh"
bash "${SCRIPT_DIR}/verify_aliyun_public_endpoints.sh"
