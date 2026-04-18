#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REMOTE_HOST="${REMOTE_HOST:-Aliyun-ECS-2}"
REMOTE_DIR="${REMOTE_DIR:-/root/deeptutor}"
SOURCE_JSON_HOST="${SOURCE_JSON_HOST:-/root/luban/artifacts/long_dialog_round7_full_detail_20260328.json}"

scp "${SCRIPT_DIR}/server_run_long_dialog_v1_aliyun_isolated.sh" "${REMOTE_HOST}:${REMOTE_DIR}/scripts/server_run_long_dialog_v1_aliyun_isolated.sh"

remote_args=()
for arg in "$@"; do
    remote_args+=("$(printf '%q' "${arg}")")
done

printf -v remote_cmd "cd %q && SOURCE_JSON_HOST=%q bash scripts/server_run_long_dialog_v1_aliyun_isolated.sh %s" \
    "${REMOTE_DIR}" \
    "${SOURCE_JSON_HOST}" \
    "${remote_args[*]-}"

ssh "${REMOTE_HOST}" "${remote_cmd}"
