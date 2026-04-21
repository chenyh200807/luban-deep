#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PUBLIC_HOST="${PUBLIC_HOST:-8.135.42.145}"
LANGFUSE_OVERRIDE_FILE="deployment/aliyun/docker-compose.langfuse.yml"
SHARED_LANGFUSE_NETWORK="${SHARED_LANGFUSE_NETWORK:-luban_jgzk-network}"

cd "${REPO_ROOT}"

export APT_MIRROR="${APT_MIRROR:-https://mirrors.aliyun.com/debian}"
export SECURITY_MIRROR="${SECURITY_MIRROR:-https://mirrors.aliyun.com/debian-security}"
export RUSTUP_DIST_SERVER="${RUSTUP_DIST_SERVER:-https://rsproxy.cn}"
export RUSTUP_UPDATE_ROOT="${RUSTUP_UPDATE_ROOT:-https://rsproxy.cn/rustup}"
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}"

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker 未安装，无法部署。" >&2
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose v2 不可用，无法部署。" >&2
    exit 1
fi

mkdir -p data/user data/knowledge_bases

if [ ! -f .env ]; then
    cp deployment/aliyun/aliyun.env.example .env
    echo "已生成 .env，请先补齐密钥后再重新运行。"
    exit 0
fi

compose_args=(-f docker-compose.yml)
if [ -f "${LANGFUSE_OVERRIDE_FILE}" ] && docker network inspect "${SHARED_LANGFUSE_NETWORK}" >/dev/null 2>&1; then
    compose_args+=(-f "${LANGFUSE_OVERRIDE_FILE}")
    echo "检测到共享 Langfuse 网络: ${SHARED_LANGFUSE_NETWORK}"
fi

docker compose "${compose_args[@]}" config >/dev/null
docker compose "${compose_args[@]}" up -d --build
docker compose "${compose_args[@]}" ps

cat <<EOF

DeepTutor 远端容器已启动，等待公网验收。
前端: http://${PUBLIC_HOST}:3782
后端: http://${PUBLIC_HOST}:8001
API 文档: http://${PUBLIC_HOST}:8001/docs

常用命令:
  docker compose logs -f
  docker compose ps
  docker compose restart
EOF
