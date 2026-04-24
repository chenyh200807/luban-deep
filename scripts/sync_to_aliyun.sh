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
    ".env*"
    ".secrets*"
    "playwright-report"
    "playwright-report*"
    "test-results"
    "coverage"
    "data"
    "tmp"
    "*.log"
)

require_git_release_hygiene() {
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
        if [ "${ALLOW_DIRTY_DEPLOY}" = "1" ]; then
            echo "警告：ALLOW_DIRTY_DEPLOY=1 只跳过 dirty tree 检查；仍要求 Git 分支和远端目标通过发布护栏。" >&2
            echo "${status}" >&2
            return 0
        fi
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

build_deploy_manifest_hash() {
    python3 - "${REPO_ROOT}" <<'PY'
from pathlib import Path
import fnmatch
import hashlib
import os
import sys

root = Path(sys.argv[1]).resolve()
excluded_names = {
    ".git",
    ".github",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".next",
    ".DS_Store",
    "playwright-report",
    "test-results",
    "coverage",
    "data",
    "tmp",
}
excluded_patterns = (
    ".env*",
    ".secrets*",
    "playwright-report*",
    "*.log",
)


def skip_file(path: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in excluded_names for part in rel.parts):
        return True
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in excluded_patterns)


digest = hashlib.sha256()
for dirpath, dirnames, filenames in os.walk(root):
    current = Path(dirpath)
    dirnames[:] = sorted([
        dirname
        for dirname in dirnames
        if dirname not in excluded_names
        and not any(fnmatch.fnmatch(dirname, pattern) for pattern in excluded_patterns)
    ])
    for filename in sorted(filenames):
        path = current / filename
        if skip_file(path):
            continue
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.readlink(path).encode("utf-8"))
        else:
            digest.update(b"file\0")
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        digest.update(b"\0")

print(digest.hexdigest()[:16])
PY
}

resolve_service_version() {
    python3 - "${REPO_ROOT}/pyproject.toml" <<'PY'
from pathlib import Path
import re
import sys

pyproject = Path(sys.argv[1])
if not pyproject.exists():
    print("1.0.0")
    raise SystemExit(0)
content = pyproject.read_text(encoding="utf-8")
match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', content)
print(match.group(1) if match else "1.0.0")
PY
}

inject_remote_release_lineage() {
    local resolved_host git_sha service_version git_dirty deploy_manifest_hash
    resolved_host="$(resolve_remote_host)"
    git_sha="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
    service_version="$(resolve_service_version)"
    deploy_manifest_hash="$(build_deploy_manifest_hash)"
    if [ -n "$(git -C "${REPO_ROOT}" status --short --untracked-files=all)" ]; then
        git_dirty="true"
    else
        git_dirty="false"
    fi

    ssh "${resolved_host}" \
        "PYTHONIOENCODING='utf-8' REMOTE_DIR='${REMOTE_DIR}' RELEASE_GIT_SHA='${git_sha}' RELEASE_SERVICE_VERSION='${service_version}' RELEASE_GIT_DIRTY='${git_dirty}' RELEASE_DEPLOY_MANIFEST_HASH='${deploy_manifest_hash}' python3 - <<'PY'
from pathlib import Path
import hashlib
import json
import os
import re

remote_dir = Path(os.environ['REMOTE_DIR'])
env_path = remote_dir / '.env'
if not env_path.exists():
    raise SystemExit(f'远端缺少 .env，无法注入 release lineage: {env_path}')

lines = env_path.read_text(encoding='utf-8').splitlines()
values = {}
key_pattern = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)=')
for raw_line in lines:
    match = key_pattern.match(raw_line.strip())
    if match:
        key, value = raw_line.split('=', 1)
        values[key.strip()] = value.strip()

deployment_environment = (
    values.get('DEEPTUTOR_ENV')
    or values.get('APP_ENV')
    or values.get('ENVIRONMENT')
    or values.get('ENV')
    or values.get('SERVICE_ENV')
    or 'production'
).strip()
git_sha = os.environ['RELEASE_GIT_SHA'].strip()
service_version = os.environ['RELEASE_SERVICE_VERSION'].strip() or '1.0.0'
git_dirty = os.environ.get('RELEASE_GIT_DIRTY', 'false').strip().lower()
deploy_manifest_hash = os.environ.get('RELEASE_DEPLOY_MANIFEST_HASH', '').strip()
release_id = f'{service_version}+{git_sha}+{deployment_environment}'
prompt_version = (
    values.get('DEEPTUTOR_PROMPT_VERSION')
    or values.get('PROMPT_VERSION')
    or values.get('NEXT_PUBLIC_PROMPT_VERSION')
    or ''
).strip()
if not prompt_version or prompt_version.lower() in {'unknown', 'unset', 'none'}:
    prompt_version = f'git-{git_sha[:12]}'

explicit_ff_snapshot_hash = (
    values.get('DEEPTUTOR_FF_SNAPSHOT_HASH')
    or values.get('FF_SNAPSHOT_HASH')
    or ''
).strip()

def should_capture_flag(key: str) -> bool:
    if key in {'DEEPTUTOR_FF_SNAPSHOT_HASH', 'FF_SNAPSHOT_HASH'}:
        return False
    if key.startswith('FF_'):
        return True
    if not key.startswith('DEEPTUTOR_'):
        return False
    return key.endswith('_ENABLED') or key.endswith('_MODE') or '_SHADOW_' in key or key.endswith('_STRICT')

def normalize_flag_value(value: str) -> str:
    lowered = str(value or '').strip().lower()
    if lowered in {'1', 'true', 'yes', 'on'}:
        return 'true'
    if lowered in {'0', 'false', 'no', 'off'}:
        return 'false'
    return str(value or '').strip()

if explicit_ff_snapshot_hash and explicit_ff_snapshot_hash.lower() not in {'unknown', 'unset', 'none'}:
    ff_snapshot_hash = explicit_ff_snapshot_hash
else:
    flag_snapshot = {
        key: normalize_flag_value(value)
        for key, value in sorted(values.items(), key=lambda item: item[0])
        if should_capture_flag(key)
    }
    if flag_snapshot:
        ff_snapshot_hash = hashlib.sha256(
            json.dumps(flag_snapshot, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('utf-8')
        ).hexdigest()[:12]
    else:
        ff_snapshot_hash = f'git-{git_sha[:12]}'

managed = {
    'DEEPTUTOR_SERVICE_VERSION': service_version,
    'DEEPTUTOR_GIT_SHA': git_sha,
    'DEEPTUTOR_ENV': deployment_environment,
    'DEEPTUTOR_RELEASE_ID': release_id,
    'DEEPTUTOR_PROMPT_VERSION': prompt_version,
    'DEEPTUTOR_FF_SNAPSHOT_HASH': ff_snapshot_hash,
    'DEEPTUTOR_GIT_DIRTY': 'true' if git_dirty == 'true' else 'false',
    'DEEPTUTOR_DEPLOY_MANIFEST_HASH': deploy_manifest_hash,
}

updated = []
seen = set()
for raw_line in lines:
    stripped = raw_line.strip()
    match = key_pattern.match(stripped)
    if not match:
        updated.append(raw_line)
        continue
    key = match.group(1)
    if key in managed:
        updated.append(f'{key}={managed[key]}')
        seen.add(key)
    else:
        updated.append(raw_line)

missing = [key for key in managed if key not in seen]
if missing:
    if updated and updated[-1].strip():
        updated.append('')
    updated.append('# Release lineage, managed by scripts/sync_to_aliyun.sh')
    for key in missing:
        updated.append(f'{key}={managed[key]}')

env_path.write_text('\n'.join(updated).rstrip() + '\n', encoding='utf-8')
print('远端 release lineage 已注入。')
print('DEEPTUTOR_RELEASE_ID=' + release_id)
print('DEEPTUTOR_GIT_SHA=' + git_sha)
print('DEEPTUTOR_PROMPT_VERSION=' + prompt_version)
print('DEEPTUTOR_FF_SNAPSHOT_HASH=' + ff_snapshot_hash)
print('DEEPTUTOR_GIT_DIRTY=' + managed['DEEPTUTOR_GIT_DIRTY'])
print('DEEPTUTOR_DEPLOY_MANIFEST_HASH=' + deploy_manifest_hash)
PY"
}

snapshot_remote_release() {
    local resolved_host release_id branch commit excludes_json
    resolved_host="$(resolve_remote_host)"
    release_id="$(build_release_id)"
    branch="$(git -C "${REPO_ROOT}" branch --show-current)"
    commit="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
    excludes_json="$(python3 - "${EXCLUDES[@]}" <<'PY'
import json
import sys

print(json.dumps(sys.argv[1:], ensure_ascii=True))
PY
)"

    ssh "${resolved_host}" \
        "PYTHONIOENCODING='utf-8' REMOTE_DIR='${REMOTE_DIR}' RELEASE_ID='${release_id}' RELEASE_BRANCH='${branch}' RELEASE_COMMIT='${commit}' RELEASE_KEEP='${RELEASE_KEEP}' RELEASE_EXCLUDES_JSON='${excludes_json}' python3 - <<'PY'
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
exclude_patterns = json.loads(os.environ.get('RELEASE_EXCLUDES_JSON') or '[]')

tar_cmd = ['tar', '-czf', str(snapshot_path)]
for pattern in exclude_patterns:
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
    inject_remote_release_lineage
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
