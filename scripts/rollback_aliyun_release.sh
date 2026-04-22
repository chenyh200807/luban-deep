#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

REMOTE_HOST="${REMOTE_HOST:-Aliyun-ECS-2}"
REMOTE_DIR="${REMOTE_DIR:-/root/deeptutor}"
PUBLIC_HOST="${PUBLIC_HOST:-8.135.42.145}"
RELEASE_ID="${1:-latest}"

cd "${REPO_ROOT}"

echo "执行阿里云代码回滚: ${RELEASE_ID}"

ssh "${REMOTE_HOST}" \
    "PYTHONIOENCODING='utf-8' REMOTE_DIR='${REMOTE_DIR}' RELEASE_ID='${RELEASE_ID}' python3 - <<'PY'
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

remote_dir = Path(os.environ['REMOTE_DIR'])
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

tmp_dir = Path(tempfile.mkdtemp(prefix='deeptutor_release_restore_'))
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
bash "${SCRIPT_DIR}/verify_aliyun_public_endpoints.sh"
