# DeepTutor Web Search Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use root-cause-debugging before changing runtime/provider behavior. Use this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-hosted, zero search API fee, explicitly enabled, observable Web Search stack for DeepTutor.

**Architecture:** Deploy SearXNG as an internal Docker service, configure DeepTutor search provider through config runtime, explicitly enable `tools.web_search.enabled`, then verify host API, container network, DeepTutor provider, and real UI/turn behavior.

**Tech Stack:** Docker Compose, SearXNG, Valkey, DeepTutor GHCR image, `deeptutor.services.search`, `deeptutor.services.config`, shell acceptance script.

---

## 0. External References

Use official documentation for external services:

1. SearXNG Search API: `https://docs.searxng.org/dev/search_api.html`
2. SearXNG outgoing settings: `https://docs.searxng.org/admin/settings/settings_outgoing.html`
3. SearXNG limiter: `https://docs.searxng.org/admin/searx.limiter.html`
4. Docker Engine on Ubuntu: `https://docs.docker.com/engine/install/ubuntu/`

DeepTutor runtime semantics are governed by local repo contracts, especially `contracts/config-runtime.md`.

## 1. Scope

This plan implements the PRD in [2026-05-03-deeptutor-web-search-stack-prd.md](2026-05-03-deeptutor-web-search-stack-prd.md).

It covers:

1. Production-like Compose deployment under `/opt/deeptutor-stack`.
2. SearXNG JSON API enablement.
3. DeepTutor runtime enablement.
4. Acceptance script.
5. Backup and upgrade runbook.
6. Failure diagnosis.

Aliyun execution note from 2026-05-03:

1. The live target was CentOS 7 with an existing `/root/deeptutor` stack, not a fresh Ubuntu host under `/opt/deeptutor-stack`.
2. In that case, do not start a second DeepTutor stack on the same ports. Merge SearXNG and Valkey into the existing `/root/deeptutor/docker-compose.yml`, preserving current LLM/embedding/env settings.
3. The target host reached Bing and GitHub, but DuckDuckGo, Wikipedia, Brave and Startpage timed out; Baidu triggered CAPTCHA. The stable zero-API baseline for this ECS was therefore SearXNG with `bing` enabled and the failing engines disabled.
4. CentOS 7 may not have `jq`; acceptance must support Python JSON validation fallback.
5. Treat the repo file `scripts/acceptance_searxng.sh` as the canonical executable acceptance script.

It does not cover:

1. Public SearXNG portal.
2. Paid search API fallback.
3. New chat WebSocket route.
4. Modifying SearXNG source code.
5. Full Kubernetes deployment.

## 2. Pre-flight Decision Record

Before executing, fill this section for the target environment.

```markdown
- Target server:
- OS version:
- Deployment path: /opt/deeptutor-stack, or existing production path such as /root/deeptutor
- DeepTutor image tag:
- SearXNG image tag:
- Public frontend URL:
- Public backend URL:
- LLM provider:
- Embedding provider:
- Is SearXNG outbound proxy required: yes/no/unknown
- Does DeepTutor use local Ollama/vLLM: yes/no
```

Decision defaults:

1. Use `ghcr.io/hkuds/deeptutor:latest` only for MVP smoke. Pin a version for production.
2. Bind SearXNG to `127.0.0.1:8080` on host.
3. Use `http://searxng:8080` inside Docker network.
4. Keep SearXNG private.
5. Treat `tools.web_search.enabled=false` as expected default until explicitly changed.

## 3. Authority Gate

Do not proceed unless this design gate is understood:

1. `one business fact`: DeepTutor's advertised Web Search capability must be a real runtime capability with source-backed output.
2. `one authority`: `tools.web_search.enabled` plus `resolve_search_runtime_config()` decide availability and provider.
3. `competing authorities`: `.env`, UI search profile, `model_catalog.json`, SearXNG container status, and frontend toggles can look authoritative but are only inputs or surfaces.
4. `canonical path`: `main.yaml -> config runtime -> tool registry -> web_search -> SearXNG JSON -> citations/search_results -> response`.
5. `delete or demote`: no silent DuckDuckGo fallback, no route-level auto enablement, no UI-only truth, no separate mobile search route.

## 4. Files and Responsibilities

Deployment files on target server:

| File | Responsibility |
| --- | --- |
| `/opt/deeptutor-stack/docker-compose.yml` | Defines DeepTutor, SearXNG, Valkey and network |
| `/opt/deeptutor-stack/.env` | DeepTutor and SearXNG runtime env |
| `/opt/deeptutor-stack/searxng/core-config/settings.yml` | SearXNG JSON API and runtime settings |
| `/opt/deeptutor-stack/data/user/settings/main.yaml` | DeepTutor runtime tool switch |
| `/opt/deeptutor-stack/scripts/acceptance_searxng.sh` | End-to-end acceptance |
| `/opt/deeptutor-stack/scripts/backup_deeptutor_stack.sh` | Backup |

Repo files already governing behavior:

| File | Responsibility |
| --- | --- |
| `contracts/config-runtime.md` | Search runtime fail-closed contract |
| `deeptutor/services/search/__init__.py` | `web_search`, `get_current_config`, runtime availability |
| `deeptutor/services/search/providers/searxng.py` | SearXNG provider |
| `deeptutor/services/config/provider_runtime.py` | Provider/base_url/key resolution |
| `deeptutor/services/setup/init.py` | Default `web_search.enabled=false` |

## 5. Phase 0: Server Preparation

### Task 0.1: Install Docker

- [ ] **Step 1: Install prerequisites**

```bash
sudo apt update
sudo apt install -y ca-certificates curl jq openssl
```

- [ ] **Step 2: Add Docker apt repository**

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
```

- [ ] **Step 3: Install Docker Engine and Compose plugin**

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run hello-world
```

- [ ] **Step 4: Optional non-root Docker access**

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker version
docker compose version
```

Expected:

1. `docker version` prints client/server versions.
2. `docker compose version` prints compose plugin version.

## 6. Phase 1: Create Deployment Directory

### Task 1.1: Create `/opt/deeptutor-stack`

- [ ] **Step 1: Create directory**

```bash
sudo mkdir -p /opt/deeptutor-stack
sudo chown -R "$USER:$USER" /opt/deeptutor-stack
cd /opt/deeptutor-stack
mkdir -p searxng/core-config
mkdir -p data/user/settings data/memory data/knowledge_bases
mkdir -p scripts
```

- [ ] **Step 2: Verify layout**

```bash
find /opt/deeptutor-stack -maxdepth 3 -type d | sort
```

Expected directories:

```text
/opt/deeptutor-stack
/opt/deeptutor-stack/data
/opt/deeptutor-stack/data/knowledge_bases
/opt/deeptutor-stack/data/memory
/opt/deeptutor-stack/data/user
/opt/deeptutor-stack/data/user/settings
/opt/deeptutor-stack/scripts
/opt/deeptutor-stack/searxng
/opt/deeptutor-stack/searxng/core-config
```

## 7. Phase 2: Configure SearXNG

### Task 2.1: Generate secret

- [ ] **Step 1: Generate SearXNG secret**

```bash
openssl rand -hex 32
```

Copy the output into `.env` as `SEARXNG_SECRET`.

### Task 2.2: Create `.env`

- [ ] **Step 1: Create file**

```bash
cd /opt/deeptutor-stack
nano .env
```

- [ ] **Step 2: Write baseline environment**

```env
# =========================
# SearXNG
# =========================
SEARXNG_SECRET=replace-with-openssl-rand-hex-32

# =========================
# DeepTutor ports
# =========================
BACKEND_PORT=8001
FRONTEND_PORT=3782

# =========================
# DeepTutor Web Search
# =========================
SEARCH_PROVIDER=searxng
SEARCH_API_KEY=
SEARCH_BASE_URL=http://searxng:8080
SEARXNG_BASE_URL=http://searxng:8080
SEARCH_PROXY=

# =========================
# LLM example: DeepSeek
# Replace with your real provider before production.
# =========================
LLM_BINDING=deepseek
LLM_MODEL=deepseek-v4-flash
LLM_API_KEY=
LLM_HOST=https://api.deepseek.com/v1
LLM_API_VERSION=

# =========================
# Embedding example: DashScope
# =========================
EMBEDDING_BINDING=dashscope
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_API_KEY=
EMBEDDING_HOST=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_DIMENSION=1024
EMBEDDING_API_VERSION=
EMBEDDING_SEND_DIMENSIONS=false

# =========================
# Cloud / Security
# =========================
NEXT_PUBLIC_API_BASE_EXTERNAL=
NEXT_PUBLIC_API_BASE=
DISABLE_SSL_VERIFY=false
```

If using Ollama on the Docker host, replace LLM and embedding with:

```env
LLM_BINDING=ollama
LLM_MODEL=qwen3:14b
LLM_API_KEY=sk-no-key-required
LLM_HOST=http://host.docker.internal:11434/v1
LLM_API_VERSION=

EMBEDDING_BINDING=ollama
EMBEDDING_MODEL=qwen3-embedding:0.6b
EMBEDDING_API_KEY=sk-no-key-required
EMBEDDING_HOST=http://host.docker.internal:11434/api/embed
EMBEDDING_DIMENSION=1024
EMBEDDING_API_VERSION=
EMBEDDING_SEND_DIMENSIONS=false
```

### Task 2.3: Create SearXNG `settings.yml`

- [ ] **Step 1: Create file**

```bash
cd /opt/deeptutor-stack
nano searxng/core-config/settings.yml
```

- [ ] **Step 2: Write settings**

```yaml
use_default_settings: true

general:
  instance_name: "deeptutor-search"
  debug: false
  enable_metrics: true

search:
  safe_search: 0
  autocomplete: ""
  default_lang: "auto"
  formats:
    - html
    - json

server:
  port: 8080
  bind_address: "0.0.0.0"
  secret_key: "change-this-secret-is-overridden-by-env"
  limiter: false
  public_instance: false
  image_proxy: false
  method: "GET"

valkey:
  url: valkey://valkey:6379/0

outgoing:
  request_timeout: 6.0
  max_request_timeout: 15.0
  pool_connections: 100
  pool_maxsize: 20
  enable_http2: true
```

Important:

1. `json` under `search.formats` is mandatory.
2. `bind_address: "0.0.0.0"` is container-internal. Public exposure is controlled by Compose binding to `127.0.0.1`.
3. If target server has unstable outbound access, add `outgoing.proxies` later after measuring failures.

## 8. Phase 3: Configure Docker Compose

### Task 3.1: Create `docker-compose.yml`

- [ ] **Step 1: Create file**

```bash
cd /opt/deeptutor-stack
nano docker-compose.yml
```

- [ ] **Step 2: Write Compose**

```yaml
name: deeptutor-stack

networks:
  backend:
    driver: bridge

services:
  searxng:
    image: docker.io/searxng/searxng:latest
    container_name: deeptutor-searxng
    restart: unless-stopped
    networks:
      - backend
    ports:
      - "127.0.0.1:8080:8080"
    environment:
      - SEARXNG_SECRET=${SEARXNG_SECRET}
      - SEARXNG_PORT=8080
      - SEARXNG_BIND_ADDRESS=0.0.0.0
      - SEARXNG_BASE_URL=http://127.0.0.1:8080/
    volumes:
      - ./searxng/core-config:/etc/searxng:rw
      - searxng-cache:/var/cache/searxng
    depends_on:
      - valkey

  valkey:
    image: docker.io/valkey/valkey:9-alpine
    container_name: deeptutor-valkey
    command: valkey-server --save 30 1 --loglevel warning
    restart: unless-stopped
    networks:
      - backend
    volumes:
      - valkey-data:/data

  deeptutor:
    image: ghcr.io/hkuds/deeptutor:latest
    container_name: deeptutor
    restart: unless-stopped
    networks:
      - backend
    env_file:
      - .env
    environment:
      - SEARCH_PROVIDER=${SEARCH_PROVIDER:-}
      - SEARCH_API_KEY=${SEARCH_API_KEY:-}
      - SEARCH_BASE_URL=${SEARCH_BASE_URL:-}
      - SEARXNG_BASE_URL=${SEARXNG_BASE_URL:-}
      - SEARCH_PROXY=${SEARCH_PROXY:-}
      - BACKEND_PORT=${BACKEND_PORT:-8001}
      - FRONTEND_PORT=${FRONTEND_PORT:-3782}
      - NEXT_PUBLIC_API_BASE_EXTERNAL=${NEXT_PUBLIC_API_BASE_EXTERNAL:-}
      - NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE:-}
    ports:
      - "127.0.0.1:3782:3782"
      - "127.0.0.1:8001:8001"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - ./data/user:/app/data/user
      - ./data/memory:/app/data/memory
      - ./data/knowledge_bases:/app/data/knowledge_bases
    depends_on:
      - searxng

volumes:
  searxng-cache:
  valkey-data:
```

Production hardening:

1. Replace `latest` tags with pinned versions after MVP smoke.
2. Keep host port binding on `127.0.0.1` unless a reverse proxy is explicitly configured.
3. If browser is remote, set `NEXT_PUBLIC_API_BASE_EXTERNAL` to the public backend HTTPS URL.

## 9. Phase 4: Start and Verify SearXNG

### Task 4.1: Start SearXNG

- [ ] **Step 1: Start Valkey and SearXNG**

```bash
cd /opt/deeptutor-stack
docker compose up -d valkey searxng
docker compose ps
```

Expected:

```text
deeptutor-valkey     running
deeptutor-searxng    running
```

- [ ] **Step 2: Check logs**

```bash
docker compose logs --tail=100 searxng
```

Expected:

1. No YAML parse error.
2. No crash loop.

### Task 4.2: Host API acceptance

- [ ] **Step 1: Test root**

```bash
curl -sS -o /tmp/searxng_root.html -w "%{http_code}\n" http://127.0.0.1:8080/
```

Expected: `200` or `302`.

- [ ] **Step 2: Test JSON API**

```bash
curl -sS -o /tmp/searxng_json.json -w "%{http_code}\n" \
  --get "http://127.0.0.1:8080/search" \
  --data-urlencode "q=DeepTutor" \
  --data "format=json"
jq '.results | length' /tmp/searxng_json.json
jq '.results[0] | {title, url, engine, content}' /tmp/searxng_json.json
```

Expected:

1. HTTP `200`.
2. `.results | length` is at least `1`.
3. First result has `title` and `url`.

If HTTP is `403`, fix `search.formats` and restart:

```bash
docker compose restart searxng
```

## 10. Phase 5: Start DeepTutor and Enable Runtime

### Task 5.1: Start DeepTutor

- [ ] **Step 1: Start service**

```bash
cd /opt/deeptutor-stack
docker compose up -d deeptutor
docker compose ps
docker compose logs --tail=100 deeptutor
```

Expected:

1. `deeptutor` is running.
2. No immediate config crash.

### Task 5.2: Ensure `main.yaml` exists

- [ ] **Step 1: Check settings file**

```bash
cd /opt/deeptutor-stack
ls -la data/user/settings/main.yaml
```

If missing, let DeepTutor initialize, or create it manually:

```bash
mkdir -p data/user/settings
nano data/user/settings/main.yaml
```

Minimal acceptable file:

```yaml
system:
  language: zh
logging:
  level: WARNING
  save_to_file: true
  console_output: true
tools:
  run_code:
    allowed_roots:
      - ./data/user
  web_search:
    enabled: true
    max_results: 5
```

If file already exists, edit only `tools.web_search`:

```yaml
tools:
  web_search:
    enabled: true
    max_results: 5
```

- [ ] **Step 2: Restart DeepTutor after settings change**

```bash
docker compose restart deeptutor
```

## 11. Phase 6: Container Network Acceptance

### Task 6.1: DeepTutor can reach SearXNG

- [ ] **Step 1: Run request from DeepTutor container**

```bash
cd /opt/deeptutor-stack
docker compose exec -T deeptutor python - <<'PY'
import requests

url = "http://searxng:8080/search"
params = {"q": "DeepTutor", "format": "json"}
r = requests.get(url, params=params, timeout=20)
print("status:", r.status_code)
print("content-type:", r.headers.get("content-type"))
if r.status_code != 200:
    print(r.text[:1000])
    raise SystemExit(1)
data = r.json()
results = data.get("results", [])
print("results:", len(results))
if not results:
    raise SystemExit("no results")
first = results[0]
print("title:", first.get("title"))
print("url:", first.get("url"))
if not first.get("title") or not first.get("url"):
    raise SystemExit("first result missing title/url")
PY
```

Expected:

```text
status: 200
results: >= 1
title: non-empty
url: non-empty
```

## 12. Phase 7: DeepTutor Runtime Acceptance

### Task 7.1: Print current config

- [ ] **Step 1: Run runtime config check**

```bash
cd /opt/deeptutor-stack
docker compose exec -T -e PYTHONIOENCODING=utf-8 deeptutor python - <<'PY'
from deeptutor.services.search import get_current_config

cfg = get_current_config()
print("current_config:")
for key in [
    "enabled",
    "provider",
    "requested_provider",
    "provider_status",
    "missing_credentials",
    "fallback_reason",
    "base_url",
    "max_results",
    "proxy",
]:
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
```

Expected:

```text
enabled: True
provider: searxng
provider_status: ok
base_url: http://searxng:8080
available: True
```

### Task 7.2: Run DeepTutor provider test

- [ ] **Step 1: Invoke `web_search`**

```bash
cd /opt/deeptutor-stack
docker compose exec -T deeptutor python - <<'PY'
from deeptutor.services.search import web_search

res = web_search(
    "DeepTutor",
    provider="searxng",
    base_url="http://searxng:8080",
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
```

Expected:

1. `provider: searxng`.
2. `search_results` or `citations` is at least 1.
3. Output contains title and URL.

## 13. Phase 8: Acceptance Script

### Task 8.1: Create `scripts/acceptance_searxng.sh`

- [ ] **Step 1: Create file**

```bash
cd /opt/deeptutor-stack
nano scripts/acceptance_searxng.sh
```

- [ ] **Step 2: Write script**

```bash
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
```

- [ ] **Step 3: Make executable and run**

```bash
chmod +x scripts/acceptance_searxng.sh
./scripts/acceptance_searxng.sh
```

Expected:

```text
PASS: SearXNG root reachable
PASS: SearXNG JSON API works
PASS: DeepTutor container can reach SearXNG
PASS: DeepTutor runtime config works
PASS: DeepTutor web_search provider works
== ACCEPTANCE PASSED ==
```

## 14. Phase 9: UI and Turn Acceptance

### Task 9.1: Local Web UI smoke

- [ ] **Step 1: Open UI**

Open:

```text
http://127.0.0.1:3782
```

For remote deployment, open the configured public frontend URL.

- [ ] **Step 2: Check Settings**

Go to:

```text
Settings / Provider / Search
```

Confirm:

```text
Provider: searxng
Base URL: http://searxng:8080
API Key: empty
Max results: 3 to 5
```

- [ ] **Step 3: Ask a联网 question**

Use:

```text
请联网搜索 HKUDS/DeepTutor 的最新 release，并列出来源链接。
```

Pass criteria:

1. Answer contains sources.
2. Source URLs are visible.
3. DeepTutor logs show search behavior.
4. SearXNG logs show the request.
5. No fallback to DuckDuckGo.

### Task 9.2: Log evidence

- [ ] **Step 1: Watch logs**

```bash
cd /opt/deeptutor-stack
docker compose logs -f deeptutor
```

In another terminal:

```bash
cd /opt/deeptutor-stack
docker compose logs -f searxng
```

Pass criteria:

1. DeepTutor search errors absent.
2. SearXNG receives query.
3. Failure, if any, is explicit.

## 15. Phase 10: Security Acceptance

### Task 10.1: Verify SearXNG not public

- [ ] **Step 1: Check listening sockets**

```bash
ss -tulpen | grep ':8080' || true
```

Expected:

```text
127.0.0.1:8080
```

Not acceptable:

```text
0.0.0.0:8080
```

- [ ] **Step 2: Check Compose binding**

```bash
grep -n '127.0.0.1:8080:8080' docker-compose.yml
```

Expected: one match under `searxng.ports`.

### Task 10.2: Verify secrets not committed

If deployment directory is inside a git repo:

```bash
git status --short
```

Pass criteria:

1. `.env` is not tracked.
2. Secret files are not staged.

## 16. Phase 11: Backup

### Task 11.1: Create backup script

- [ ] **Step 1: Create script**

```bash
cd /opt/deeptutor-stack
nano scripts/backup_deeptutor_stack.sh
```

- [ ] **Step 2: Write script**

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${DEEPTUTOR_STACK_ROOT:-/opt/deeptutor-stack}"
BACKUP_DIR="${DEEPTUTOR_BACKUP_DIR:-/opt/deeptutor-backups}"
STAMP="$(date +%F-%H%M%S)"
OUT="$BACKUP_DIR/deeptutor-stack-$STAMP.tar.gz"

mkdir -p "$BACKUP_DIR"
cd "$ROOT"

tar -czf "$OUT" \
  data \
  searxng/core-config \
  .env \
  docker-compose.yml \
  scripts/acceptance_searxng.sh

echo "$OUT"
```

- [ ] **Step 3: Run backup**

```bash
chmod +x scripts/backup_deeptutor_stack.sh
scripts/backup_deeptutor_stack.sh
```

Expected:

1. Prints backup path.
2. Archive exists.

## 17. Phase 12: Upgrade

### Task 12.1: Upgrade runbook

- [ ] **Step 1: Backup**

```bash
cd /opt/deeptutor-stack
scripts/backup_deeptutor_stack.sh
```

- [ ] **Step 2: Pull images**

```bash
docker compose pull
```

- [ ] **Step 3: Restart**

```bash
docker compose up -d
```

- [ ] **Step 4: Acceptance**

```bash
./scripts/acceptance_searxng.sh
```

If acceptance fails, rollback to the previous Compose file/image tag and restore backup if configuration changed.

## 18. Failure Diagnosis Table

| Symptom | Likely cause | Verification | Fix |
| --- | --- | --- | --- |
| SearXNG JSON returns 403 | `search.formats` lacks `json` | `cat searxng/core-config/settings.yml` | Add `json`, restart SearXNG |
| Host curl works, DeepTutor container fails | Docker network/service name issue | `docker compose exec deeptutor python requests` | Ensure same network and service name `searxng` |
| `get_current_config` says disabled | `tools.web_search.enabled=false` | Print `data/user/settings/main.yaml` | Set `enabled: true`, restart |
| provider is empty | `SEARCH_PROVIDER` empty or active profile empty | `get_current_config()` | Set `.env` or UI search profile |
| provider is DuckDuckGo | UI/profile overrides env or wrong config | `requested_provider` / `provider` | Set active search profile to SearXNG |
| `missing_credentials=True` for SearXNG | Missing `base_url` | `get_current_config()` | Set `SEARCH_BASE_URL` and `SEARXNG_BASE_URL` |
| Search returns no results | Upstream engine issue/query too narrow | Try `DeepTutor`, Chinese query, GitHub query | Adjust engines, query, timeout, proxy |
| Works locally, fails on Aliyun | Outbound access blocked or unstable | Run acceptance on ECS | Configure SearXNG outbound proxy or overseas SearXNG |
| UI works but browser cannot call backend | Remote API base missing | Browser network tab | Set `NEXT_PUBLIC_API_BASE_EXTERNAL` |
| Latest info answered without sources | Tool not used or failure masked | Logs + answer | Enforce tool availability and source requirement in smoke |

## 19. Performance Probe

### Task 13.1: Run 20-query sample

```bash
cd /opt/deeptutor-stack
queries=(
  "DeepTutor"
  "HKUDS DeepTutor GitHub"
  "SearXNG search API format json"
  "Docker Compose SearXNG"
  "Qwen3 embedding Ollama"
  "vLLM OpenAI compatible server"
  "建筑实务 安全管理 最新 政策"
  "一级建造师 建筑实务 施工组织设计"
  "GitHub HKUDS DeepTutor release"
  "SearXNG outgoing proxies settings"
  "DeepTutor web search provider searxng"
  "Ollama host.docker.internal docker linux"
  "Valkey limiter SearXNG"
  "AGPL SearXNG license"
  "DeepTutor RAG web search"
  "FastAPI health check docker compose"
  "Caddy reverse proxy docker localhost"
  "Nginx reverse proxy 127.0.0.1 docker"
  "Uptime Kuma HTTP keyword monitor"
  "SearXNG JSON 403 format"
)

ok=0
fail=0
for q in "${queries[@]}"; do
  echo "QUERY: $q"
  start="$(date +%s)"
  if curl -sS --get "http://127.0.0.1:8080/search" \
    --data-urlencode "q=$q" \
    --data "format=json" \
    | jq -e '.results and (.results | length >= 1)' >/dev/null; then
    ok=$((ok + 1))
    echo "OK elapsed=$(( $(date +%s) - start ))s"
  else
    fail=$((fail + 1))
    echo "FAIL elapsed=$(( $(date +%s) - start ))s"
  fi
done
echo "ok=$ok fail=$fail"
test "$ok" -ge 18
```

Pass criteria:

1. `ok >= 18`.
2. No continuous 3 failures.
3. Slow/failing query types recorded.

## 20. Production Notes

### 20.1 Reverse proxy

Recommended:

```text
https://tutor.example.com -> 127.0.0.1:3782
https://api-tutor.example.com -> 127.0.0.1:8001
```

Then set:

```env
NEXT_PUBLIC_API_BASE_EXTERNAL=https://api-tutor.example.com
```

Do not expose:

```text
http://server:8080
```

### 20.2 Pinned versions

After MVP, replace:

```yaml
image: ghcr.io/hkuds/deeptutor:latest
image: docker.io/searxng/searxng:latest
```

with known-good tags and record them in the acceptance report.

### 20.3 SearXNG outbound proxy

Only configure after measuring actual failures. If needed, extend `settings.yml`:

```yaml
outgoing:
  proxies:
    all://:
      - http://proxy-host:proxy-port
```

Use the exact proxy syntax accepted by the deployed SearXNG version.

## 21. Final Go/No-Go Checklist

Go only if all P0 items pass:

- [ ] SearXNG root reachable
- [ ] SearXNG JSON API works
- [ ] DeepTutor container can reach SearXNG
- [ ] DeepTutor runtime enabled
- [ ] provider is `searxng`
- [ ] `provider_status=ok`
- [ ] runtime availability expression resolves `True`
- [ ] DeepTutor provider returns citations/search_results
- [ ] UI or turn returns source links
- [ ] SearXNG not publicly exposed
- [ ] Backup script works

No-go if any of these are true:

- [ ] `web_search` is disabled
- [ ] provider silently falls back
- [ ] SearXNG JSON API returns 403
- [ ] `base_url` is empty
- [ ] UI answer claims latest information without sources
- [ ] SearXNG 8080 is public
- [ ] acceptance script was not run on the target server
