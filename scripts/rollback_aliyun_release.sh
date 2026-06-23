#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

REMOTE_HOST="${REMOTE_HOST:-Aliyun-ECS-2}"
REMOTE_DIR="${REMOTE_DIR:-/root/deeptutor}"
PUBLIC_HOST="${PUBLIC_HOST:-8.135.42.145}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://test2.yousenjiaoyu.com}"
RELEASE_ID="${1:-latest}"

cd "${REPO_ROOT}"

echo "执行阿里云代码回滚: ${RELEASE_ID}"

ssh "${REMOTE_HOST}" \
    "PYTHONIOENCODING='utf-8' REMOTE_DIR='${REMOTE_DIR}' RELEASE_ID='${RELEASE_ID}' python3 - <<'PY'
from pathlib import Path
import os
import shutil
import subprocess

remote_dir = Path(os.environ['REMOTE_DIR']).resolve()
remote_root = remote_dir
if remote_root != Path('/root/deeptutor'):
    raise SystemExit(f'REMOTE_DIR 必须解析到 /root/deeptutor: {remote_root}')
release_dir = remote_dir / 'data' / 'releases' / 'code'
if not release_dir.exists():
    raise SystemExit(f'缺少代码快照目录: {release_dir}')

requested = os.environ['RELEASE_ID'].strip() or 'latest'
if requested == 'latest':
    candidates = sorted(release_dir.glob('*.tar.gz'), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        raise SystemExit(f'没有可用代码快照: {release_dir}')
    snapshot = candidates[0]
else:
    snapshot = release_dir / f'{requested}.tar.gz'
    if not snapshot.exists():
        raise SystemExit(f'指定代码快照不存在: {snapshot}')

snapshot = snapshot.resolve()
if release_dir not in snapshot.parents:
    raise SystemExit(f'代码快照必须位于 {release_dir} 内: {snapshot}')

staging_root = (remote_dir / 'data' / 'releases' / 'restore_tmp').resolve()
tmp_dir = (staging_root / ('restore_{}'.format(os.getpid()))).resolve()
if remote_dir not in tmp_dir.parents:
    raise SystemExit(f'回滚 staging 目录必须位于 {remote_dir} 内: {tmp_dir}')
if staging_root not in tmp_dir.parents:
    raise SystemExit(f'回滚 staging 目录必须位于 {staging_root} 内: {tmp_dir}')
if tmp_dir.exists():
    shutil.rmtree(tmp_dir, ignore_errors=True)
tmp_dir.mkdir(parents=True, exist_ok=False)
try:
    subprocess.run(['tar', '-xzf', str(snapshot), '-C', str(tmp_dir)], check=True)
    restore_cmd = [
        'rsync',
        '-a',
        '--delete',
        '--exclude=.env',
        '--exclude=data',
        '--exclude=tmp',
        '--exclude=*.log',
        f'{tmp_dir}/',
        f'{remote_dir}/',
    ]
    subprocess.run(restore_cmd, check=True)
    print(f'远端代码已回滚到: {snapshot}')
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)
PY"

ssh "${REMOTE_HOST}" "cd '${REMOTE_DIR}' && PUBLIC_HOST='${PUBLIC_HOST}' bash scripts/server_bootstrap_aliyun.sh"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL}" bash "${SCRIPT_DIR}/verify_aliyun_public_endpoints.sh"
bash "${SCRIPT_DIR}/verify_aliyun_observability.sh"
