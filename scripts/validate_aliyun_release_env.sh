#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

REMOTE_HOST="${REMOTE_HOST:-Aliyun-ECS-2}"
REMOTE_DIR="${REMOTE_DIR:-/root/deeptutor}"

cd "${REPO_ROOT}"

ssh "${REMOTE_HOST}" \
    "PYTHONIOENCODING='utf-8' REMOTE_DIR='${REMOTE_DIR}' python3 - <<'PY'
from pathlib import Path
import os
import sys

remote_dir = Path(os.environ['REMOTE_DIR'])
env_path = remote_dir / '.env'
if not env_path.exists():
    raise SystemExit(f'远端缺少 .env: {env_path}')

values = {}
for raw_line in env_path.read_text(encoding='utf-8').splitlines():
    line = raw_line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    values[key.strip()] = value.strip()

service_env = str(values.get('SERVICE_ENV') or values.get('DEEPTUTOR_ENV') or '').strip().lower()
app_env = str(values.get('APP_ENV') or '').strip().lower()
is_production = service_env == 'production' or app_env == 'production'
if not is_production:
    print('远端环境不是 production，跳过生产发布必填校验。')
    raise SystemExit(0)

missing = [
    key
    for key in ('DEEPTUTOR_AUTH_SECRET', 'DEEPTUTOR_ADMIN_USER_IDS')
    if not str(values.get(key) or '').strip()
]
missing.extend(
    key
    for key in (
        'DEEPTUTOR_RELEASE_ID',
        'DEEPTUTOR_GIT_SHA',
        'DEEPTUTOR_PROMPT_VERSION',
        'DEEPTUTOR_FF_SNAPSHOT_HASH',
    )
    if not str(values.get(key) or '').strip()
)
if missing:
    raise SystemExit(
        'production 环境缺少必填项: ' + ', '.join(missing)
    )

for key in (
    'DEEPTUTOR_RELEASE_ID',
    'DEEPTUTOR_GIT_SHA',
    'DEEPTUTOR_PROMPT_VERSION',
    'DEEPTUTOR_FF_SNAPSHOT_HASH',
):
    current = str(values.get(key) or '').strip().lower()
    if not current or current in {'unknown', 'unset', 'none'} or (key in {'DEEPTUTOR_RELEASE_ID', 'DEEPTUTOR_GIT_SHA'} and 'unknown' in current):
        raise SystemExit(f'{key} 不是完整发布追溯值: {values.get(key)}')

for key in ('DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE', 'DEEPTUTOR_EXTERNAL_AUTH_SESSIONS_FILE'):
    current = str(values.get(key) or '').strip()
    if current and '/root/luban' in current:
        raise SystemExit(f'{key} 不允许指向 /root/luban: {current}')

print('远端发布环境校验通过。')
print('SERVICE_ENV=' + str(values.get('SERVICE_ENV') or values.get('DEEPTUTOR_ENV') or ''))
print('APP_ENV=' + str(values.get('APP_ENV') or ''))
print('DEEPTUTOR_RELEASE_ID=' + str(values.get('DEEPTUTOR_RELEASE_ID') or ''))
print('DEEPTUTOR_GIT_SHA=' + str(values.get('DEEPTUTOR_GIT_SHA') or ''))
print('DEEPTUTOR_PROMPT_VERSION=' + str(values.get('DEEPTUTOR_PROMPT_VERSION') or ''))
print('DEEPTUTOR_FF_SNAPSHOT_HASH=' + str(values.get('DEEPTUTOR_FF_SNAPSHOT_HASH') or ''))
print('DEEPTUTOR_ADMIN_USER_IDS=' + str(values.get('DEEPTUTOR_ADMIN_USER_IDS') or ''))
PY"
