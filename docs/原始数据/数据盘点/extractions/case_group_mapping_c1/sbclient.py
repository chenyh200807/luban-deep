"""Shared Supabase REST (service_role) client for C2 backfill. No third-party deps."""
import json, os, ssl, time, urllib.request, urllib.error, urllib.parse

ENV_PATH = "/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.env"

def load_env():
    kv = {}
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv

_E = load_env()
SUPABASE_URL = _E["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = _E["SUPABASE_KEY"]
MGMT_TOKEN = _E.get("SUPABASE_ACCESS_TOKEN", "")
PROJECT_REF = SUPABASE_URL.split("//")[1].split(".")[0]

def _req(url, method="GET", body=None, headers=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", "User-Agent": "deeptutor-c2-backfill/1.0"}
    h.update(headers or {})
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                raw = resp.read().decode()
                return resp.status, (json.loads(raw) if raw.strip() else None), dict(resp.headers)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code} {method} {url}\n{e.read().decode()[:2000]}")
        except urllib.error.URLError:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))

def rest(path, method="GET", body=None, params=None, prefer=None, timeout=120):
    """PostgREST call with service_role key."""
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, safe="().,*:")
    h = {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"}
    if prefer:
        h["Prefer"] = prefer
    return _req(url, method, body, h, timeout)

def mgmt_sql(sql, timeout=300):
    """Supabase Management API query endpoint (REST) - used ONLY for DDL / read-only asserts."""
    url = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"
    h = {"Authorization": f"Bearer {MGMT_TOKEN}"}
    return _req(url, "POST", {"query": sql}, h, timeout)

def select_all(table, select, filt=None, page=1000, order="id.asc"):
    out, offset = [], 0
    while True:
        p = {"select": select, "order": order, "limit": page, "offset": offset}
        if filt:
            p.update(filt)
        _, rows, _ = rest(table, params=p)
        out.extend(rows)
        if len(rows) < page:
            break
        offset += page
    return out
