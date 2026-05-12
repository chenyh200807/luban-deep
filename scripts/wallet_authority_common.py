from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


def discover_repo_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return current.parent


def _parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


@dataclass(frozen=True)
class WalletAuthorityEnv:
    supabase_url: str = ""
    api_key: str = ""
    service_role_key: str = ""
    db_url: str = ""
    source_map: dict[str, str] = field(default_factory=dict)

    @property
    def rest_enabled(self) -> bool:
        return bool(self.supabase_url and self.api_key)

    @property
    def service_role_enabled(self) -> bool:
        return bool(self.supabase_url and self.service_role_key)

    @property
    def postgres_enabled(self) -> bool:
        return bool(self.db_url)

    def to_summary(self) -> dict[str, Any]:
        return {
            "supabase_url_present": bool(self.supabase_url),
            "api_key_present": bool(self.api_key),
            "service_role_key_present": bool(self.service_role_key),
            "db_url_present": bool(self.db_url),
            "rest_enabled": self.rest_enabled,
            "service_role_enabled": self.service_role_enabled,
            "postgres_enabled": self.postgres_enabled,
            "source_map": dict(self.source_map),
        }


def resolve_wallet_env(
    *,
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> WalletAuthorityEnv:
    root = (repo_root or discover_repo_root()).resolve()
    env_values: dict[str, str] = {}
    source_map: dict[str, str] = {}
    for dotenv_name in (".env", ".env.local"):
        dotenv_path = root / dotenv_name
        for key, value in _parse_dotenv(dotenv_path).items():
            env_values[key] = value
            source_map[key] = str(dotenv_path)
    for key, value in dict(environ or os.environ).items():
        if value:
            env_values[key] = value
            source_map[key] = "process_env"
    service_role_key = str(env_values.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    fallback_api_key = str(env_values.get("SUPABASE_KEY") or "").strip()
    return WalletAuthorityEnv(
        supabase_url=str(env_values.get("SUPABASE_URL") or "").strip(),
        api_key=service_role_key or fallback_api_key,
        service_role_key=service_role_key,
        db_url=str(env_values.get("SUPABASE_DB_URL") or env_values.get("DATABASE_URL") or "").strip(),
        source_map=source_map,
    )


def rest_headers(api_key: str, *, prefer_count: bool = False) -> dict[str, str]:
    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if prefer_count:
        headers["Prefer"] = "count=exact"
    return headers


def command_available(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> None:
    ensure_output_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_sql_comment_file(path: Path, title: str, lines: Sequence[str]) -> None:
    ensure_output_dir(path.parent)
    rendered = [f"-- {title}"]
    rendered.extend(f"-- {line}" if line else "--" for line in lines)
    path.write_text("\n".join(rendered) + "\n", encoding="utf-8")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
