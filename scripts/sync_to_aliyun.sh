#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_DIR="${REMOTE_DIR:-/root/deeptutor}"
REMOTE_HOST_CANDIDATES=("Aliyun-ECS-2" "Aliyun-ECS")

EXCLUDES=(
    ".git"
    ".github"
    ".venv"
    "node_modules"
    "__pycache__"
    ".pytest_cache"
    ".mypy_cache"
    ".ruff_cache"
    ".next"
    ".DS_Store"
    ".env"
    "data"
    "tmp"
    "*.log"
)

resolve_remote_host() {
    if [ -n "${REMOTE_HOST}" ]; then
        echo "${REMOTE_HOST}"
        return 0
    fi

    local host
    for host in "${REMOTE_HOST_CANDIDATES[@]}"; do
        if ssh -o BatchMode=yes -o ConnectTimeout=5 "${host}" "echo ok" >/dev/null 2>&1; then
            echo "${host}"
            return 0
        fi
    done

    echo "没有可用的阿里云 SSH Host: ${REMOTE_HOST_CANDIDATES[*]}" >&2
    exit 1
}

sync_once() {
    local resolved_host
    local exclude_args=()
    local item
    resolved_host="$(resolve_remote_host)"

    for item in "${EXCLUDES[@]}"; do
        exclude_args+=(--exclude="${item}")
    done

    echo "同步到 ${resolved_host}:${REMOTE_DIR}"
    ssh "${resolved_host}" "mkdir -p '${REMOTE_DIR}'"
    rsync -avz --delete --stats --no-owner --no-group \
        "${exclude_args[@]}" \
        "${REPO_ROOT}/" "${resolved_host}:${REMOTE_DIR}/"
}

check_fswatch() {
    if command -v fswatch >/dev/null 2>&1; then
        return 0
    fi
    echo "未安装 fswatch，无法启用实时同步。先执行一次同步。" >&2
    exit 1
}

watch_sync() {
    check_fswatch
    sync_once

    fswatch -o "${REPO_ROOT}" \
        --exclude=".*\\.git.*" \
        --exclude=".*\\.venv.*" \
        --exclude=".*node_modules.*" \
        --exclude=".*__pycache__.*" \
        --exclude=".*\\.next.*" \
        --exclude=".*\\/data\\/.*" \
        | while read -r _; do
            sync_once
        done
}

MODE="${1:-once}"
case "${MODE}" in
    once)
        sync_once
        ;;
    watch)
        watch_sync
        ;;
    *)
        echo "用法: $0 [once|watch]" >&2
        exit 1
        ;;
esac
