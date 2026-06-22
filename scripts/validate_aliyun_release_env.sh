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
remote_root = remote_dir.resolve()
if remote_root != Path('/root/deeptutor'):
    raise SystemExit(f'REMOTE_DIR 必须解析到 /root/deeptutor: {remote_root}')
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

# Production detection mirrors deeptutor/services/runtime_env.py (the single authority):
# same key precedence, same fail-closed _NON_PRODUCTION_ENV_NAMES allowlist. This runs in
# an SSH heredoc on the host and cannot import the package, so the set is replicated here
# and kept in sync by tests/scripts/test_aliyun_deploy_scripts.py. FAIL-CLOSED: unset /
# misspelled / 'aliyun' / 'prod' / unknown all resolve to production, so a real production
# release can never silently skip the required checks below (the old == production
# test treated DEEPTUTOR_ENV=aliyun — a production deploy — as non-production and skipped).
runtime_env_keys = (
    'DEEPTUTOR_ENV', 'DEEPTUTOR_RUNTIME_ENV', 'APP_ENV', 'ENV', 'ENVIRONMENT', 'SERVICE_ENV',
)
non_production_env_names = {'local', 'dev', 'development', 'test', 'testing', 'ci', 'eval'}
resolved_env = ''
for env_key in runtime_env_keys:
    candidate = str(values.get(env_key) or '').strip().lower()
    if candidate:
        resolved_env = candidate
        break
is_production = resolved_env not in non_production_env_names
if not is_production:
    print(f'远端环境为 {resolved_env!r}（非生产），跳过生产发布必填校验。')
    raise SystemExit(0)

missing = [
    key
    for key in (
        'DEEPTUTOR_AUTH_SECRET',
        'DEEPTUTOR_ATTEMPT_REF_SECRET',
        'DEEPTUTOR_ADMIN_USER_IDS',
        'DEEPTUTOR_METRICS_TOKEN',
        'SUPABASE_RAG_COMPILED_TRUTH_ENABLED',
        'SUPABASE_RAG_PROVENANCE_BOOST_ENABLED',
    )
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

for key in ('SUPABASE_RAG_COMPILED_TRUTH_ENABLED', 'SUPABASE_RAG_PROVENANCE_BOOST_ENABLED'):
    current = str(values.get(key) or '').strip().lower()
    if current not in {'false', '0', 'no', 'off'}:
        raise SystemExit(f'{key} 必须显式为 false，当前值: {values.get(key)}')

attempt_ref_secret = str(values.get('DEEPTUTOR_ATTEMPT_REF_SECRET') or '').strip()
if len(attempt_ref_secret) < 32:
    raise SystemExit('DEEPTUTOR_ATTEMPT_REF_SECRET 太短，production 至少需要 32 字符随机值')
if attempt_ref_secret in {'dev-attempt-ref-secret', 'dev-secret', 'secret', 'change-me', 'changeme'}:
    raise SystemExit('DEEPTUTOR_ATTEMPT_REF_SECRET 不能使用开发默认值或示例值')

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

# Legacy WS routers (question/mimic, solve) are fully ANONYMOUS LLM surfaces guarded
# only by this single flag — one env typo would expose them to the public internet.
legacy_routers = str(values.get('DEEPTUTOR_ENABLE_LEGACY_ROUTERS') or '').strip().lower()
if legacy_routers in {'1', 'true', 'yes', 'on'}:
    raise SystemExit('DEEPTUTOR_ENABLE_LEGACY_ROUTERS 不允许在 production 开启（匿名 LLM WebSocket 面）')

for key in ('SUPABASE_RAG_COMPILED_TRUTH_ENABLED', 'SUPABASE_RAG_PROVENANCE_BOOST_ENABLED'):
    current = str(values.get(key) or '').strip().lower()
    if current in {'1', 'true', 'yes', 'on'}:
        raise SystemExit(f'{key} 不允许在 production 发布校验中开启；启用前必须先更新 RAG contract 与 staging baseline')

# Multi-worker pairing: heartbeat single-instance lock / WS connection cap / shared
# rate limits all need the redis backend once workers > 1 (else they degrade per-process).
workers_raw = str(values.get('UVICORN_WORKERS') or '1').strip()
try:
    workers = int(workers_raw or '1')
except ValueError:
    workers = 1
backend = str(values.get('DEEPTUTOR_RATE_LIMIT_BACKEND') or 'sqlite').strip().lower()
redis_url = str(values.get('DEEPTUTOR_RATE_LIMIT_REDIS_URL') or values.get('REDIS_URL') or '').strip()
if workers > 1 and (backend != 'redis' or not redis_url):
    raise SystemExit(
        f'UVICORN_WORKERS={workers} 需要 DEEPTUTOR_RATE_LIMIT_BACKEND=redis 且配置 '
        'DEEPTUTOR_RATE_LIMIT_REDIS_URL，否则心跳锁/WS连接帽/限流退化为每进程各一份'
    )

print('远端发布环境校验通过。')
print('SERVICE_ENV=' + str(values.get('SERVICE_ENV') or values.get('DEEPTUTOR_ENV') or ''))
print('APP_ENV=' + str(values.get('APP_ENV') or ''))
print('DEEPTUTOR_RELEASE_ID=' + str(values.get('DEEPTUTOR_RELEASE_ID') or ''))
print('DEEPTUTOR_GIT_SHA=' + str(values.get('DEEPTUTOR_GIT_SHA') or ''))
print('DEEPTUTOR_PROMPT_VERSION=' + str(values.get('DEEPTUTOR_PROMPT_VERSION') or ''))
print('DEEPTUTOR_FF_SNAPSHOT_HASH=' + str(values.get('DEEPTUTOR_FF_SNAPSHOT_HASH') or ''))
print('DEEPTUTOR_ADMIN_USER_IDS=' + str(values.get('DEEPTUTOR_ADMIN_USER_IDS') or ''))
PY"
