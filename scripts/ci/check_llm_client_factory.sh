#!/usr/bin/env bash
# SR4 PR-4 — LLM client factory single authority.
#
# Forbid direct construction of AsyncOpenAI / AsyncAnthropic / AsyncAzureOpenAI
# anywhere outside the canonical factory at
# deeptutor/services/llm/openai_http_client.py.
#
# The factory injects sane default timeouts (60s for OpenAI, 180s for Anthropic),
# DISABLE_SSL_VERIFY handling, and a single shared httpx.AsyncClient lifecycle.
# Direct SDK construction silently uses 600s timeout — a single hung LLM call
# blocks a worker for 10 minutes.

set -euo pipefail

ALLOWED_FILE="deeptutor/services/llm/openai_http_client.py"
fail=0

bad=$(grep -RnE 'AsyncOpenAI\(|AsyncAnthropic\(|AsyncAzureOpenAI\(' deeptutor/ --include='*.py' 2>/dev/null \
    | grep -v "$ALLOWED_FILE" \
    | grep -vE ':[[:space:]]*#|"""' || true)

if [ -n "$bad" ]; then
    echo "[FAIL] direct SDK construction found outside $ALLOWED_FILE:" >&2
    echo "$bad" >&2
    echo >&2
    echo "  → use make_openai_client / make_anthropic_client / make_azure_openai_client" >&2
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo "[OK] check_llm_client_factory: all LLM SDK construction goes through factory"
fi
exit "$fail"
