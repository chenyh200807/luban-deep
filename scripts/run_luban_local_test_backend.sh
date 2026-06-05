#!/usr/bin/env bash
# M24 LOCAL TEST MODE backend launcher (manual /api/v1/ws + mini-program testing).
# NOT for production / remote / aliyun. Bundles a self-contained local profile:
#   - billing/wallet: internal QA bypass for quota/capture/bootstrap (no remote wallet dependency)
#   - v1 LLM adjudication: DEV force-on for ANY logged-in user (bypasses request-flag + cohort;
#     non-production only; deterministic validator floor + append-only still apply; legacy never mutated)
#   - auth users: local writable JSON store (no /app read-only path)
#   - DeepSeek-V4-flash primary / Qwen3.7 fallback come from the project .env
# Revert: just stop this process and run the normal backend. No git commit.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${LUBAN_TEST_BACKEND_PORT:-8001}"
mkdir -p data/user/external_auth

load_env_key() {
  local key="$1"
  if [ ! -f .env ]; then
    return 0
  fi
  python - "$key" <<'PY'
import sys
from pathlib import Path

key = sys.argv[1]
for raw in Path(".env").read_text("utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    if name.strip() != key:
        continue
    value = value.strip().strip('"').strip("'")
    if value:
        print(value)
    break
PY
}

for key in \
  SUPABASE_URL \
  SUPABASE_KEY \
  SUPABASE_SERVICE_ROLE_KEY \
  SUPABASE_RAG_ENABLED \
  SUPABASE_RAG_DEFAULT_KB_NAME \
  SUPABASE_RAG_SOURCES \
  SUPABASE_RAG_INCLUDE_QUESTIONS \
  RAG_PROVIDER; do
  if [ -z "${!key:-}" ]; then
    value="$(load_env_key "$key")"
    if [ -n "$value" ]; then
      export "$key=$value"
    fi
  fi
done

# free the port if a previous test backend is running
if lsof -ti ":${PORT}" >/dev/null 2>&1; then
  kill "$(lsof -ti ":${PORT}")" 2>/dev/null || true
  sleep 2
fi

export DEEPTUTOR_RUNTIME_ENV="${DEEPTUTOR_RUNTIME_ENV:-local}"
# --- wallet: local zero-balance fallback without clearing Supabase RAG env ---
export DEEPTUTOR_ALLOW_LOCAL_WALLET_FALLBACK="true"
export DEEPTUTOR_INTERNAL_QA_BILLING_BYPASS="true"
if [ -z "${RAG_PROVIDER:-}" ] && [ "${SUPABASE_RAG_ENABLED:-}" = "true" ] && [ -n "${SUPABASE_URL:-}" ] && [ -n "${SUPABASE_KEY:-}" ]; then
  export RAG_PROVIDER="supabase"
fi
# --- local auth user store (writable; avoids /app read-only) ---
export DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE="$PWD/data/user/external_auth/users.json"
export DEEPTUTOR_EXTERNAL_AUTH_SESSIONS_FILE="$PWD/data/user/external_auth/sessions.json"
python scripts/seed_luban_internal_qa_accounts.py
# --- v1 LLM adjudication: force on for any logged-in user (LOCAL TEST ONLY) ---
export LUBAN_V1_LLM_ADJUDICATOR_DEV_FORCE_ON="true"
export LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED="true"
export LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_COHORT="qa_,test_,operator_,auth_"
export LUBAN_V1_LLM_ADJUDICATOR_COHORT="qa_,test_,operator_,auth_"
# kill switch OFF (absent) -> v1 enabled

echo "[local-test-mode] backend on 0.0.0.0:${PORT} | v1 DEV_FORCE_ON=1 | billing-bypass=internal-qa | env=${DEEPTUTOR_RUNTIME_ENV}"
exec python -u -m uvicorn deeptutor.api.main:app --host 0.0.0.0 --port "${PORT}"
