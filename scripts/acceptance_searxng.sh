#!/usr/bin/env bash
set -euo pipefail

BASE="${SEARXNG_LOCAL_URL:-http://127.0.0.1:8080}"
INTERNAL="${SEARXNG_INTERNAL_URL:-http://searxng:8080}"
QUERY="${1:-DeepTutor HKUDS GitHub}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

pass() {
  echo "PASS: $*"
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

need curl
need docker

PYTHON_BIN=""
if command -v jq >/dev/null 2>&1; then
  JSON_READER="jq"
elif command -v python3 >/dev/null 2>&1; then
  JSON_READER="python"
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  JSON_READER="python"
  PYTHON_BIN="python"
else
  fail "missing command: jq or python3/python"
fi

assert_json_results() {
  local file="$1"
  if [[ "$JSON_READER" == "jq" ]]; then
    jq -e '.results and (.results | length >= 1)' "$file" >/dev/null \
      || fail "SearXNG JSON API returned no results"
    jq -e '.results[0].title and .results[0].url' "$file" >/dev/null \
      || fail "First result missing title or url"
    jq '.results[0] | {title, url, engine, content}' "$file"
    return
  fi

  "$PYTHON_BIN" - "$file" <<'PY' || fail "SearXNG JSON API validation failed"
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)

results = data.get("results", [])
if not isinstance(results, list) or not results:
    raise SystemExit("SearXNG JSON API returned no results")

first = results[0]
if not first.get("title") or not first.get("url"):
    raise SystemExit("First result missing title or url")

print(json.dumps({
    "title": first.get("title"),
    "url": first.get("url"),
    "engine": first.get("engine"),
    "content": first.get("content"),
}, ensure_ascii=True, indent=2))
PY
}

echo "== 1. Check SearXNG root =="
status="$(curl -sS -o /tmp/searxng_root.html -w "%{http_code}" "$BASE/")"
[[ "$status" == "200" || "$status" == "302" ]] || fail "SearXNG root HTTP status=$status"
pass "SearXNG root reachable: $status"

echo "== 2. Check SearXNG JSON API =="
status="$(curl -sS -o /tmp/searxng_json.json -w "%{http_code}" \
  --get "$BASE/search" \
  --data-urlencode "q=$QUERY" \
  --data "format=json")"
if [[ "$status" != "200" ]]; then
  echo "Response:"
  cat /tmp/searxng_json.json
  echo
  fail "SearXNG JSON API HTTP status=$status. If status=403, enable search.formats json in settings.yml."
fi
echo "First result:"
assert_json_results /tmp/searxng_json.json
pass "SearXNG JSON API works"

echo "== 3. Check DeepTutor container can reach SearXNG =="
if docker compose ps --services --status running | grep -q '^deeptutor$'; then
  docker compose exec -T -e PYTHONIOENCODING=utf-8 deeptutor python - <<PY
import requests
url = "${INTERNAL}/search"
params = {"q": "${QUERY}", "format": "json"}
r = requests.get(url, params=params, timeout=20)
print("status:", r.status_code)
if r.status_code != 200:
    print(r.text[:1000])
    raise SystemExit(1)
data = r.json()
results = data.get("results", [])
print("results:", len(results))
if not results:
    raise SystemExit("no results from internal SearXNG")
first = results[0]
print("title:", first.get("title"))
print("url:", first.get("url"))
if not first.get("title") or not first.get("url"):
    raise SystemExit("first result missing title/url")
PY
  pass "DeepTutor container can reach SearXNG"
else
  echo "SKIP: deeptutor service is not running"
fi

echo "== 4. Check DeepTutor runtime config =="
if docker compose ps --services --status running | grep -q '^deeptutor$'; then
  docker compose exec -T -e PYTHONIOENCODING=utf-8 deeptutor python - <<'PY'
from deeptutor.services.search import get_current_config

cfg = get_current_config()
keys = [
    "enabled",
    "provider",
    "requested_provider",
    "provider_status",
    "missing_credentials",
    "fallback_reason",
    "base_url",
    "max_results",
    "proxy",
]
for key in keys:
    print(f"{key}: {cfg.get(key)}")
available = (
    cfg.get("enabled") is True
    and cfg.get("provider") == "searxng"
    and cfg.get("provider_status") == "ok"
    and cfg.get("base_url") == "http://searxng:8080"
    and not cfg.get("missing_credentials")
)
print("available:", available)
if cfg.get("enabled") is not True:
    raise SystemExit("web_search is not enabled")
if cfg.get("provider") != "searxng":
    raise SystemExit("provider is not searxng")
if cfg.get("provider_status") != "ok":
    raise SystemExit("provider_status is not ok")
if cfg.get("base_url") != "http://searxng:8080":
    raise SystemExit("base_url is not http://searxng:8080")
if not available:
    raise SystemExit("web_search runtime unavailable")
PY
  pass "DeepTutor runtime config works"
else
  echo "SKIP: deeptutor service is not running"
fi

echo "== 5. Check DeepTutor web_search provider =="
if docker compose ps --services --status running | grep -q '^deeptutor$'; then
  docker compose exec -T -e PYTHONIOENCODING=utf-8 deeptutor python - <<PY
from deeptutor.services.search import web_search

res = web_search(
    "${QUERY}",
    provider="searxng",
    base_url="${INTERNAL}",
    max_results=3,
)
print("provider:", res.get("provider"))
print("citations:", len(res.get("citations", [])))
print("search_results:", len(res.get("search_results", [])))
if res.get("provider") != "searxng":
    raise SystemExit("provider is not searxng")
if not res.get("citations") and not res.get("search_results"):
    raise SystemExit("no citations or search_results")
for item in res.get("search_results", [])[:3]:
    print("-", item.get("title"), item.get("url"))
PY
  pass "DeepTutor web_search provider works"
else
  echo "SKIP: deeptutor service is not running"
fi

echo "== ACCEPTANCE PASSED =="
