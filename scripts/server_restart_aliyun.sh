#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PUBLIC_HOST="${PUBLIC_HOST:-8.135.42.145}"
LANGFUSE_OVERRIDE_FILE="deployment/aliyun/docker-compose.langfuse.yml"
SHARED_LANGFUSE_NETWORK="${SHARED_LANGFUSE_NETWORK:-luban_jgzk-network}"
export APT_MIRROR="${APT_MIRROR:-https://mirrors.aliyun.com/debian}"
export SECURITY_MIRROR="${SECURITY_MIRROR:-https://mirrors.aliyun.com/debian-security}"
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"
export RUSTUP_DIST_SERVER="${RUSTUP_DIST_SERVER:-https://rsproxy.cn}"
export RUSTUP_UPDATE_ROOT="${RUSTUP_UPDATE_ROOT:-https://rsproxy.cn/rustup}"

cd "${REPO_ROOT}"

read_env_default() {
    local key="$1"
    local fallback="$2"
    if [ ! -f .env ]; then
        echo "${fallback}"
        return 0
    fi
    local value
    value="$(awk -F= -v key="${key}" '$1 == key {sub(/^[^=]*=/, "", $0); print $0; exit}' .env | tr -d '\r')"
    if [ -z "${value}" ]; then
        echo "${fallback}"
    else
        echo "${value}"
    fi
}

compose_args=(-f docker-compose.yml)
if [ -f "${LANGFUSE_OVERRIDE_FILE}" ] && docker network inspect "${SHARED_LANGFUSE_NETWORK}" >/dev/null 2>&1; then
    compose_args+=(-f "${LANGFUSE_OVERRIDE_FILE}")
fi

docker compose --progress plain "${compose_args[@]}" build deeptutor
docker compose "${compose_args[@]}" up -d --no-deps --force-recreate deeptutor
docker compose "${compose_args[@]}" ps deeptutor

backend_port="$(read_env_default BACKEND_PORT 8001)"
frontend_port="$(read_env_default FRONTEND_PORT 3782)"

for _ in $(seq 1 30); do
    health="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' deeptutor 2>/dev/null || true)"
    if [ "${health}" = "healthy" ] || [ "${health}" = "running" ]; then
        break
    fi
    sleep 2
done

curl -fsS "http://127.0.0.1:${backend_port}/" >/dev/null
curl -fsS "http://127.0.0.1:${frontend_port}/" >/dev/null

cat <<EOF
DeepTutor 已重启完成。
前端: http://${PUBLIC_HOST}:${frontend_port}
后端: http://${PUBLIC_HOST}:${backend_port}
EOF
