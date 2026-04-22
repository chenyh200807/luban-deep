#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

CANONICAL_REMOTE_HOST="Aliyun-ECS-2"
CANONICAL_REMOTE_DIR="/root/deeptutor"
REMOTE_HOST="${REMOTE_HOST:-${CANONICAL_REMOTE_HOST}}"
REMOTE_DIR="${REMOTE_DIR:-${CANONICAL_REMOTE_DIR}}"
RELEASE_KEEP="${RELEASE_KEEP:-5}"
ALLOW_DIRTY_DEPLOY="${ALLOW_DIRTY_DEPLOY:-0}"
ALLOW_MAIN_BRANCH_DEPLOY="${ALLOW_MAIN_BRANCH_DEPLOY:-0}"
ALLOW_NON_CANONICAL_DEPLOY="${ALLOW_NON_CANONICAL_DEPLOY:-0}"

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

require_git_release_hygiene() {
    if [ "${ALLOW_DIRTY_DEPLOY}" = "1" ]; then
        return 0
    fi

    if ! git -C "${REPO_ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "发布脚本必须从 Git 工作区执行。" >&2
        exit 1
    fi

    local branch
    branch="$(git -C "${REPO_ROOT}" branch --show-current)"
    if [ -z "${branch}" ]; then
        echo "无法识别当前分支；禁止在 detached HEAD 直接发布。" >&2
        exit 1
    fi

    if [ "${ALLOW_MAIN_BRANCH_DEPLOY}" != "1" ] && [ "${branch}" = "main" ]; then
        echo "禁止直接从 main 发布。请先切到干净候选分支，或显式设置 ALLOW_MAIN_BRANCH_DEPLOY=1。" >&2
        exit 1
    fi

    local status
    status="$(git -C "${REPO_ROOT}" status --short --untracked-files=all)"
    if [ -n "${status}" ]; then
        echo "工作区不干净，禁止发布。请先提交/清理改动，或显式设置 ALLOW_DIRTY_DEPLOY=1。" >&2
        echo "${status}" >&2
        exit 1
    fi
}

require_canonical_target() {
    if [ "${ALLOW_NON_CANONICAL_DEPLOY}" = "1" ]; then
        return 0
    fi

    if [ "${REMOTE_HOST}" != "${CANONICAL_REMOTE_HOST}" ]; then
        echo "REMOTE_HOST 必须固定为 ${CANONICAL_REMOTE_HOST}；当前为 ${REMOTE_HOST}。" >&2
        echo "若确需临时发往其他主机，请显式设置 ALLOW_NON_CANONICAL_DEPLOY=1。" >&2
        exit 1
    fi

    if [ "${REMOTE_DIR}" != "${CANONICAL_REMOTE_DIR}" ]; then
        echo "REMOTE_DIR 必须固定为 ${CANONICAL_REMOTE_DIR}；当前为 ${REMOTE_DIR}。" >&2
        echo "若确需临时发往其他目录，请显式设置 ALLOW_NON_CANONICAL_DEPLOY=1。" >&2
        exit 1
    fi
}

resolve_remote_host() {
    echo "${REMOTE_HOST}"
}

build_release_id() {
    local timestamp branch commit
    timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    branch="$(git -C "${REPO_ROOT}" branch --show-current | tr '/ ' '__')"
    commit="$(git -C "${REPO_ROOT}" rev-parse --short=12 HEAD)"
    echo "${timestamp}_${branch}_${commit}"
}

snapshot_remote_release() {
    local resolved_host release_id branch commit
    resolved_host="$(resolve_remote_host)"
    release_id="$(build_release_id)"
    branch="$(git -C "${REPO_ROOT}" branch --show-current)"
    commit="$(git -C "${REPO_ROOT}" rev-parse HEAD)"

    ssh "${resolved_host}" \
        "PYTHONIOENCODING='utf-8' REMOTE_DIR='${REMOTE_DIR}' RELEASE_ID='${release_id}' RELEASE_BRANCH='${branch}' RELEASE_COMMIT='${commit}' RELEASE_KEEP='${RELEASE_KEEP}' python3 - <<'PY'
import json
import os
import subprocess
import time
from pathlib import Path

remote_dir = Path(os.environ['REMOTE_DIR'])
if not remote_dir.exists():
    print(f'远端目录不存在，跳过代码快照: {remote_dir}')
    raise SystemExit(0)
if not (remote_dir / 'docker-compose.yml').exists():
    print(f'远端目录缺少 docker-compose.yml，跳过代码快照: {remote_dir}')
    raise SystemExit(0)

release_dir = remote_dir / 'data' / 'releases' / 'code'
release_dir.mkdir(parents=True, exist_ok=True)
release_id = os.environ['RELEASE_ID']
snapshot_path = release_dir / f'{release_id}.tar.gz'
manifest_path = release_dir / f'{release_id}.json'

tar_cmd = ['tar', '-czf', str(snapshot_path)]
for pattern in (
    '.git',
    '.github',
    '.venv',
    'node_modules',
    '__pycache__',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
    '.next',
    '.DS_Store',
    '.env',
    'data',
    'tmp',
    '*.log',
):
    tar_cmd.append(f'--exclude={pattern}')
tar_cmd.extend(['-C', str(remote_dir), '.'])
subprocess.run(tar_cmd, check=True)

manifest = {
    'release_id': release_id,
    'branch': os.environ['RELEASE_BRANCH'],
    'commit': os.environ['RELEASE_COMMIT'],
    'created_at': int(time.time()),
    'snapshot_path': str(snapshot_path),
    'remote_dir': str(remote_dir),
}
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

keep = max(1, int(os.environ.get('RELEASE_KEEP', '5') or '5'))
snapshots = sorted(release_dir.glob('*.tar.gz'), key=lambda item: item.stat().st_mtime, reverse=True)
for stale in snapshots[keep:]:
    if stale.exists():
        stale.unlink()
    stale_manifest = stale.with_suffix('').with_suffix('.json')
    if stale_manifest.exists():
        stale_manifest.unlink()

print(f'远端代码快照已生成: {snapshot_path}')
print(f'远端代码清单已生成: {manifest_path}')
PY"
}

preflight() {
    require_git_release_hygiene
    require_canonical_target
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
    snapshot_remote_release
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
preflight

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
