#!/usr/bin/env bash

set -Eeuo pipefail

REMOTE_HOST="${REMOTE_HOST:-Aliyun-ECS-2}"
REMOTE_DIR="${REMOTE_DIR:-/root/deeptutor}"
BACKEND_PORT="${BACKEND_PORT:-8001}"

ssh "${REMOTE_HOST}" \
    "PYTHONIOENCODING='utf-8' REMOTE_DIR='${REMOTE_DIR}' BACKEND_PORT='${BACKEND_PORT}' python3 - <<'PY'
from pathlib import Path
import json
import os
import subprocess
import sys
import textwrap
import urllib.request

remote_dir = Path(os.environ['REMOTE_DIR'])
backend_port = str(os.environ.get('BACKEND_PORT') or '8001').strip()
env_path = remote_dir / '.env'
if not env_path.exists():
    raise SystemExit(f'远端缺少 .env: {env_path}')

env_values = {}
for raw_line in env_path.read_text(encoding='utf-8').splitlines():
    line = raw_line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    env_values[key.strip()] = value.strip()

token = env_values.get('DEEPTUTOR_METRICS_TOKEN', '')

if not token:
    raise SystemExit('远端缺少 DEEPTUTOR_METRICS_TOKEN，无法执行 observability 内网验收。')

headers = {'X-Metrics-Token': token}
metrics_url = f'http://127.0.0.1:{backend_port}/metrics'
prometheus_url = f'http://127.0.0.1:{backend_port}/metrics/prometheus'

metrics_request = urllib.request.Request(metrics_url, headers=headers)
with urllib.request.urlopen(metrics_request, timeout=8) as response:
    payload = json.loads(response.read().decode('utf-8'))

prometheus_request = urllib.request.Request(prometheus_url, headers=headers)
with urllib.request.urlopen(prometheus_request, timeout=8) as response:
    prometheus_body = response.read().decode('utf-8')

release_snapshot = payload.get('release') or {}
readiness = payload.get('readiness') or {}
http_snapshot = payload.get('http') or {}
turn_snapshot = payload.get('turn_runtime') or {}

if readiness.get('ready') is not True:
    raise SystemExit(f'metrics readiness 未就绪: {readiness}')

if 'deeptutor_ready 1' not in prometheus_body:
    raise SystemExit('metrics/prometheus 未导出 deeptutor_ready 1')

langfuse_status = 'skipped'
langfuse_enabled = env_values.get('LANGFUSE_ENABLED', '').lower() in {'1', 'true', 'yes', 'on'}
langfuse_url = env_values.get('LANGFUSE_BASE_URL', '')
if langfuse_enabled:
    if not langfuse_url:
        raise SystemExit('LANGFUSE_ENABLED=true 但缺少 LANGFUSE_BASE_URL。')
    probe = textwrap.dedent(
        f'''
        import socket
        from urllib.parse import urlparse

        url = {langfuse_url!r}
        parsed = urlparse(url if '://' in url else 'http://' + url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if not host:
            raise SystemExit(f'invalid LANGFUSE_BASE_URL: {{url}}')
        socket.getaddrinfo(host, port)
        with socket.create_connection((host, port), timeout=5):
            pass
        print(f'{{host}}:{{port}} reachable')
        '''
    )
    result = subprocess.run(
        ['docker', 'exec', 'deeptutor', 'python3', '-c', probe],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=12,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout or '').strip()
        raise SystemExit(f'Langfuse 容器内连通性失败: {details}')
    langfuse_status = result.stdout.strip() or 'ok'

print('Observability 内网验收通过。')
print('metrics=' + metrics_url)
print('metrics_prometheus=' + prometheus_url)
print('release_id=' + str(release_snapshot.get('release_id') or ''))
print('ready=' + str(readiness.get('ready')))
print('http_requests_total=' + str(http_snapshot.get('requests_total')))
print('turns_completed_total=' + str(turn_snapshot.get('turns_completed_total')))
print('langfuse_connectivity=' + langfuse_status)
PY"
