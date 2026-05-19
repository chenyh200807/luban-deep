#!/usr/bin/env python3
"""本地环境 contract 检查 (fail-fast gate)。

在启动 uvicorn / pytest 前跑一次。任意检查失败 → exit 1。

合法形态 (single authority):
    local = dev Supabase project
          + local Langfuse stack (or explicitly disabled)
          + KB schema-aligned with prod
          + prod-aligned model config

调用：
    python scripts/check_local_env.py
    python scripts/check_local_env.py --json    # CI / fixture 用
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROD_SUPABASE_HOSTS = frozenset(
    {
        "zgupgizexqpwtajvghno.supabase.co",
    }
)
EXPECTED_LLM_MODEL = "deepseek-v4-flash"
EXPECTED_LLM_HOST_PREFIXES = ("https://api.deepseek.com",)


def _load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def check_supabase_isolation(env: dict[str, str]) -> tuple[bool, str]:
    url = env.get("SUPABASE_URL", "")
    host = urlparse(url).hostname or ""
    if not host:
        return False, "SUPABASE_URL 为空或非法 URL"
    if host in PROD_SUPABASE_HOSTS:
        return False, (
            f"SUPABASE_URL host={host} 命中 prod 集合。"
            " 本地必须用 dev project (例如 SUPABASE_URL_V5)。"
            " 修：用 V5 的 host/key 覆盖裸 SUPABASE_URL/SUPABASE_KEY。"
        )
    return True, f"Supabase host={host} (非 prod)"


def check_langfuse_reachable(env: dict[str, str]) -> tuple[bool, str]:
    enabled = env.get("LANGFUSE_ENABLED", "true").lower() == "true"
    if not enabled:
        return True, "Langfuse 显式 disabled (LANGFUSE_ENABLED=false)"
    parsed = urlparse(env.get("LANGFUSE_HOST", ""))
    host = parsed.hostname or "localhost"
    port = parsed.port or 3001
    try:
        with socket.create_connection((host, port), timeout=2):
            return True, f"Langfuse {host}:{port} 可达"
    except OSError as exc:
        return False, (
            f"Langfuse {host}:{port} 不可达 ({exc.__class__.__name__})。"
            " 修：起本地栈"
            " `docker compose -f deployment/local/docker-compose.dev.yml up -d langfuse`"
            " 或在 .env 设 LANGFUSE_ENABLED=false。"
        )


def check_kb_index(env: dict[str, str]) -> tuple[bool, str]:
    kb_root = PROJECT_ROOT / "data" / "knowledge_bases"
    if not kb_root.exists():
        return True, "data/knowledge_bases/ 不存在 (无本地 KB，OK)"
    cfg = kb_root / "kb_config.json"
    if not cfg.exists():
        return True, "kb_config.json 不存在 (无活跃 KB)"
    try:
        active = json.loads(cfg.read_text(encoding="utf-8")).get("knowledge_bases") or {}
    except json.JSONDecodeError as exc:
        return False, f"kb_config.json 无法解析: {exc}"
    if not active:
        orphans = [
            d.name
            for d in kb_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
        if orphans:
            return False, (
                f"kb_config.json 为空，但磁盘有孤儿 KB 目录: {orphans}。"
                " 修：删孤儿 (`rm -rf data/knowledge_bases/<name>`)"
                " 或在 kb_config.json 重新登记。"
            )
        return True, "无活跃 KB 且无孤儿"
    return True, f"活跃 KB={list(active)} (浅检查 OK；深检查走 validate_embedding_batch)"


def check_model_alignment(env: dict[str, str]) -> tuple[bool, str]:
    model = env.get("LLM_PRIMARY_MODEL", "")
    base = env.get("DEEPSEEK_BASE_URL", "")
    if model != EXPECTED_LLM_MODEL:
        return False, (
            f"LLM_PRIMARY_MODEL={model!r} != prod 期望 {EXPECTED_LLM_MODEL!r}。"
            " 修：改 .env 的 LLM_PRIMARY_MODEL 和 MODEL_NAME。"
        )
    if not any(base.startswith(p) for p in EXPECTED_LLM_HOST_PREFIXES):
        return False, (
            f"DEEPSEEK_BASE_URL={base!r} 不在白名单 {EXPECTED_LLM_HOST_PREFIXES}。"
            " 本地不要走 DashScope 等 provider drift。"
        )
    host = urlparse(base).hostname or base
    return True, f"模型 {model} @ {host} (与 prod 一致)"


CHECKS = (
    ("Supabase 隔离", check_supabase_isolation),
    ("Langfuse 可达 / disabled", check_langfuse_reachable),
    ("KB 索引完整性", check_kb_index),
    ("模型配置对齐", check_model_alignment),
)


def run(emit_json: bool = False) -> int:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        msg = ".env 不存在，先 `cp .env.example .env` 并补齐 keys"
        if emit_json:
            print(json.dumps({"ok": False, "reason": msg}))
        else:
            print(f"❌ {msg}", file=sys.stderr)
        return 1

    env = _load_env(env_path)
    results: list[dict[str, object]] = []
    failed: list[str] = []
    for name, fn in CHECKS:
        ok, msg = fn(env)
        results.append({"name": name, "ok": ok, "message": msg})
        if not ok:
            failed.append(name)

    if emit_json:
        print(json.dumps({"ok": not failed, "checks": results}, ensure_ascii=False))
    else:
        for item in results:
            prefix = "✅" if item["ok"] else "❌"
            print(f"{prefix} {item['name']}: {item['message']}")
        if failed:
            print(
                f"\n❌ {len(failed)}/{len(CHECKS)} checks failed: "
                + ", ".join(failed),
                file=sys.stderr,
            )
        else:
            print(f"\n✅ all {len(CHECKS)} checks passed")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="输出 JSON (CI / fixture)")
    args = parser.parse_args(argv)
    return run(emit_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
