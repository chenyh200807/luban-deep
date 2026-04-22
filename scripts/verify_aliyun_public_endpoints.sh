#!/usr/bin/env bash

set -Eeuo pipefail

CANONICAL_PUBLIC_BASE_URL="https://test2.yousenjiaoyu.com"
PUBLIC_HOST="${PUBLIC_HOST:-8.135.42.145}"
BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_PORT="${FRONTEND_PORT:-3782}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-${CANONICAL_PUBLIC_BASE_URL}}"
PROBE_RETRIES="${PROBE_RETRIES:-20}"
PROBE_INTERVAL_SECONDS="${PROBE_INTERVAL_SECONDS:-3}"
PROBE_TIMEOUT_SECONDS="${PROBE_TIMEOUT_SECONDS:-5}"

if [[ -n "${PUBLIC_BASE_URL}" ]]; then
    public_base="${PUBLIC_BASE_URL%/}"
    frontend_url="${public_base}/"
    healthz_url="${public_base}/healthz"
    readyz_url="${public_base}/readyz"
else
    frontend_url="http://${PUBLIC_HOST}:${FRONTEND_PORT}/"
    healthz_url="http://${PUBLIC_HOST}:${BACKEND_PORT}/healthz"
    readyz_url="http://${PUBLIC_HOST}:${BACKEND_PORT}/readyz"
fi

probe_url() {
    local label="$1"
    local url="$2"
    local expected_substring="${3:-}"
    local last_error=""
    local body=""

    for attempt in $(seq 1 "${PROBE_RETRIES}"); do
        if body="$(curl -fsS --connect-timeout "${PROBE_TIMEOUT_SECONDS}" --max-time "${PROBE_TIMEOUT_SECONDS}" "${url}")"; then
            if [[ -n "${expected_substring}" ]] && [[ "${body}" != *"${expected_substring}"* ]]; then
                last_error="公网探针失败(${attempt}/${PROBE_RETRIES}): ${label} -> ${url}，响应缺少 ${expected_substring}"
                echo "${last_error}" >&2
                sleep "${PROBE_INTERVAL_SECONDS}"
                continue
            fi
            echo "公网探针通过: ${label} -> ${url}"
            return 0
        fi
        last_error="公网探针失败(${attempt}/${PROBE_RETRIES}): ${label} -> ${url}"
        echo "${last_error}" >&2
        sleep "${PROBE_INTERVAL_SECONDS}"
    done

    echo "发布未通过公网验收: ${label} -> ${url}" >&2
    return 1
}

echo "执行公网发布验收..."
echo "验收口径: ${PUBLIC_BASE_URL:-http://${PUBLIC_HOST}:${FRONTEND_PORT}}"
probe_url "frontend" "${frontend_url}"
probe_url "healthz" "${healthz_url}" '"alive":true'
probe_url "readyz" "${readyz_url}" '"ready":true'

cat <<EOF
公网发布验收完成。
前端: ${frontend_url}
后端健康: ${healthz_url}
后端就绪: ${readyz_url}
EOF
