#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REMOTE_HOST="${REMOTE_HOST:-Aliyun-ECS-2}"
REMOTE_DIR="${REMOTE_DIR:-/root/deeptutor}"
PUBLIC_HOST="${PUBLIC_HOST:-8.135.42.145}"

echo "执行阿里云快速发布: sync + docker cp + restart"
echo "适合 Python 后端 / Prompt / YAML 改动；若改了 Dockerfile、requirements、前端构建产物，请改用 deploy_aliyun.sh"

"${SCRIPT_DIR}/sync_to_aliyun.sh" once
ssh "${REMOTE_HOST}" "cd '${REMOTE_DIR}' && PUBLIC_HOST='${PUBLIC_HOST}' bash scripts/server_fast_reload_aliyun.sh"
