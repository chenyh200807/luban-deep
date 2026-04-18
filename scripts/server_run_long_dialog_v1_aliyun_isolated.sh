#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SOURCE_JSON_HOST="${SOURCE_JSON_HOST:-/root/luban/artifacts/long_dialog_round7_full_detail_20260328.json}"
IMAGE_NAME="${IMAGE_NAME:-deeptutor-deeptutor}"
STAMP="${STAMP:-$(date +%Y%m%d_%H%M%S)}"
RUN_NAME="${RUN_NAME:-deeptutor-ldv1-${STAMP}}"
HOST_OUTPUT_DIR="${HOST_OUTPUT_DIR:-${REPO_ROOT}/tmp/aliyun_isolated_ldv1/${STAMP}}"
CONTAINER_SOURCE_JSON="/tmp/long_dialog_round7_full_detail_20260328.json"
CONTAINER_OUTPUT_DIR="/app/tmp/aliyun_isolated_ldv1/${STAMP}"

cd "${REPO_ROOT}"

if [ ! -f "${SOURCE_JSON_HOST}" ]; then
    echo "未找到 source json: ${SOURCE_JSON_HOST}" >&2
    exit 1
fi

mkdir -p "${HOST_OUTPUT_DIR}"

if ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
    echo "镜像 ${IMAGE_NAME} 不存在，先构建 deeptutor ..."
    docker compose build deeptutor >/dev/null
fi

echo "以隔离 one-off 容器执行 Long Dialog V1：${RUN_NAME}"
echo "source json: ${SOURCE_JSON_HOST}"
echo "host output: ${HOST_OUTPUT_DIR}"

logger -t deeptutor-eval "start isolated long-dialog eval run_name=${RUN_NAME} output=${HOST_OUTPUT_DIR}"

docker run --rm \
    --name "${RUN_NAME}" \
    --env-file "${REPO_ROOT}/.env" \
    -v "${REPO_ROOT}/data/user:/app/data/user" \
    -v "${REPO_ROOT}/data/knowledge_bases:/app/data/knowledge_bases" \
    -v "${SOURCE_JSON_HOST}:${CONTAINER_SOURCE_JSON}:ro" \
    -v "${HOST_OUTPUT_DIR}:${CONTAINER_OUTPUT_DIR}" \
    -w /app \
    --entrypoint python \
    "${IMAGE_NAME}" \
    scripts/run_long_dialog_v1_retest.py \
    --source-json "${CONTAINER_SOURCE_JSON}" \
    --output-dir "${CONTAINER_OUTPUT_DIR}" \
    "$@"

logger -t deeptutor-eval "finish isolated long-dialog eval run_name=${RUN_NAME} output=${HOST_OUTPUT_DIR}"

echo "隔离评测完成。产物目录: ${HOST_OUTPUT_DIR}"
