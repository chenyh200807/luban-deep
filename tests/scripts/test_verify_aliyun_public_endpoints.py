from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import textwrap


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_aliyun_public_endpoints.sh"


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)


def _write_stub(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_public_probe_checks_frontend_healthz_and_readyz(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    calls_log = tmp_path / "calls.log"
    _write_stub(
        bin_dir / "curl",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            printf 'curl:%s\n' "$*" >> "${CALLS_LOG}"
            exit 0
            """
        ),
    )

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["CALLS_LOG"] = str(calls_log)
    env["PUBLIC_HOST"] = "1.2.3.4"
    env["BACKEND_PORT"] = "8001"
    env["FRONTEND_PORT"] = "3782"
    env["PROBE_RETRIES"] = "1"
    env["PROBE_INTERVAL_SECONDS"] = "0"

    result = _run(["bash", str(SCRIPT_PATH)], cwd=REPO_ROOT, env=env)

    assert result.returncode == 0, result.stderr
    log_lines = calls_log.read_text(encoding="utf-8").splitlines()
    assert any("http://1.2.3.4:3782/" in line for line in log_lines)
    assert any("http://1.2.3.4:8001/healthz" in line for line in log_lines)
    assert any("http://1.2.3.4:8001/readyz" in line for line in log_lines)


def test_public_probe_uses_public_base_url_when_configured(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    calls_log = tmp_path / "calls.log"
    _write_stub(
        bin_dir / "curl",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            printf 'curl:%s\n' "$*" >> "${CALLS_LOG}"
            exit 0
            """
        ),
    )

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["CALLS_LOG"] = str(calls_log)
    env["PUBLIC_BASE_URL"] = "https://test2.yousenjiaoyu.com"
    env["PROBE_RETRIES"] = "1"
    env["PROBE_INTERVAL_SECONDS"] = "0"

    result = _run(["bash", str(SCRIPT_PATH)], cwd=REPO_ROOT, env=env)

    assert result.returncode == 0, result.stderr
    log_lines = calls_log.read_text(encoding="utf-8").splitlines()
    assert any("https://test2.yousenjiaoyu.com/" in line for line in log_lines)
    assert any("https://test2.yousenjiaoyu.com/healthz" in line for line in log_lines)
    assert any("https://test2.yousenjiaoyu.com/readyz" in line for line in log_lines)
