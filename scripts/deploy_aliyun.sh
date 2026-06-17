#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

REMOTE_HOST="${REMOTE_HOST:-Aliyun-ECS-2}"
REMOTE_DIR="${REMOTE_DIR:-/root/deeptutor}"
PUBLIC_HOST="${PUBLIC_HOST:-8.135.42.145}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://test2.yousenjiaoyu.com}"
BACKUP_KEEP="${BACKUP_KEEP:-2}"
FORCE_FULL_REBUILD="${FORCE_FULL_REBUILD:-0}"

read_remote_deployed_sha() {
    ssh "${REMOTE_HOST}" "cd '${REMOTE_DIR}' && [ -f .env ] && awk -F= '/^DEEPTUTOR_GIT_SHA=/{print \$2; exit}' .env" 2>/dev/null || true
}

is_sync_only_path() {
    case "$1" in
        docs/*) return 0 ;;
        scripts/deploy_aliyun.sh) return 0 ;;
        scripts/sync_to_aliyun.sh) return 0 ;;
        scripts/verify_aliyun_public_endpoints.sh) return 0 ;;
        scripts/verify_aliyun_observability.sh) return 0 ;;
        yousenwebview/packageDeeptutor/*) return 0 ;;
        yousenwebview/tests/*) return 0 ;;
        yousenwebview/app.js) return 0 ;;
        yousenwebview/app.json) return 0 ;;
        yousenwebview/app.wxss) return 0 ;;
        yousenwebview/project.config.json) return 0 ;;
        yousenwebview/sitemap.json) return 0 ;;
        *) return 1 ;;
    esac
}

guard_sync_only_full_rebuild() {
    if [ "${FORCE_FULL_REBUILD}" = "1" ]; then
        return 0
    fi

    local remote_sha
    remote_sha="$(read_remote_deployed_sha)"
    if [ -z "${remote_sha}" ]; then
        return 0
    fi
    if ! git -C "${REPO_ROOT}" cat-file -e "${remote_sha}^{commit}" >/dev/null 2>&1; then
        return 0
    fi
    if [ "${remote_sha}" = "$(git -C "${REPO_ROOT}" rev-parse HEAD)" ]; then
        return 0
    fi

    local changed_files
    changed_files="$(git -C "${REPO_ROOT}" diff --name-only "${remote_sha}..HEAD")"
    if [ -z "${changed_files}" ]; then
        return 0
    fi

    local path
    while IFS= read -r path; do
        if [ -z "${path}" ]; then
            continue
        fi
        if ! is_sync_only_path "${path}"; then
            return 0
        fi
    done <<< "${changed_files}"

    cat >&2 <<EOF
拒绝完整阿里云重建：远端 ${remote_sha} 到本地 HEAD 的变更只包含文档/微信小程序源码/小程序测试。

这类日常同步不需要 docker compose up -d --build，也不应该重新下载 apt/Rust/pip/npm 基础依赖。
请改用：
  ALLOW_MAIN_BRANCH_DEPLOY=1 bash scripts/sync_to_aliyun.sh once

如果确实要强制完整重建，请显式设置：
  FORCE_FULL_REBUILD=1

变更文件：
${changed_files}
EOF
    exit 2
}

guard_sync_only_full_rebuild

echo "执行阿里云完整部署: sync + docker compose up -d --build"

"${SCRIPT_DIR}/sync_to_aliyun.sh" once
"${SCRIPT_DIR}/validate_aliyun_release_env.sh"

echo "执行远端运行态备份，作为本次发布的回滚基线..."
ssh "${REMOTE_HOST}" "cd '${REMOTE_DIR}' && python3 scripts/backup_data.py --project-root '${REMOTE_DIR}' --keep '${BACKUP_KEEP}'"

ssh "${REMOTE_HOST}" "cd '${REMOTE_DIR}' && PUBLIC_HOST='${PUBLIC_HOST}' PUBLIC_BASE_URL='${PUBLIC_BASE_URL}' bash scripts/server_bootstrap_aliyun.sh"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL}" bash "${SCRIPT_DIR}/verify_aliyun_public_endpoints.sh"
bash "${SCRIPT_DIR}/verify_aliyun_observability.sh"
