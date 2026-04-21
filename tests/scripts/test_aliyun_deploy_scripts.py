from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import textwrap


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_SCRIPTS = REPO_ROOT / "scripts"


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_stub(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    _make_executable(path)


def _build_stub_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    call_log = tmp_path / "calls.log"

    _write_stub(
        bin_dir / "ssh",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            printf 'ssh:%s\n' "$*" >> "${CALLS_LOG}"
            exit 0
            """
        ),
    )
    _write_stub(
        bin_dir / "rsync",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            printf 'rsync:%s\n' "$*" >> "${CALLS_LOG}"
            exit 0
            """
        ),
    )

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["CALLS_LOG"] = str(call_log)
    return env, call_log


def _init_git_repo(repo_root: Path, *, branch: str) -> None:
    _run(["git", "init"], cwd=repo_root)
    _run(["git", "config", "user.email", "codex@example.com"], cwd=repo_root)
    _run(["git", "config", "user.name", "Codex"], cwd=repo_root)
    (repo_root / "README.md").write_text("release candidate\n", encoding="utf-8")
    _run(["git", "add", "."], cwd=repo_root)
    _run(["git", "commit", "-m", "init"], cwd=repo_root)
    _run(["git", "branch", "-M", branch], cwd=repo_root)


def _setup_sync_repo(tmp_path: Path, *, branch: str) -> Path:
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_SCRIPTS / "sync_to_aliyun.sh", scripts_dir / "sync_to_aliyun.sh")
    _make_executable(scripts_dir / "sync_to_aliyun.sh")
    _init_git_repo(repo_root, branch=branch)
    return repo_root


def _setup_wrapper_repo(tmp_path: Path, wrapper_name: str) -> Path:
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_SCRIPTS / wrapper_name, scripts_dir / wrapper_name)
    _make_executable(scripts_dir / wrapper_name)
    _write_stub(
        scripts_dir / "verify_aliyun_public_endpoints.sh",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            printf 'verify-public:%s\n' "$*" >> "${CALLS_LOG}"
            exit 0
            """
        ),
    )
    _write_stub(
        scripts_dir / "sync_to_aliyun.sh",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            printf 'sync:%s\n' "$*" >> "${CALLS_LOG}"
            exit 0
            """
        ),
    )
    return repo_root


def test_sync_blocks_main_branch_release(tmp_path: Path) -> None:
    repo_root = _setup_sync_repo(tmp_path, branch="main")
    env, call_log = _build_stub_env(tmp_path)

    result = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "禁止直接从 main 发布" in combined
    assert not call_log.exists()


def test_sync_blocks_dirty_tree_release(tmp_path: Path) -> None:
    repo_root = _setup_sync_repo(tmp_path, branch="release/candidate")
    (repo_root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    env, call_log = _build_stub_env(tmp_path)

    result = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "工作区不干净，禁止发布" in combined
    assert "untracked.txt" in combined
    assert not call_log.exists()


def test_sync_requires_canonical_remote_target(tmp_path: Path) -> None:
    repo_root = _setup_sync_repo(tmp_path, branch="release/candidate")
    env, call_log = _build_stub_env(tmp_path)
    env["REMOTE_HOST"] = "Aliyun-ECS"

    result = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "REMOTE_HOST 必须固定为 Aliyun-ECS-2" in combined
    assert not call_log.exists()


def test_sync_runs_against_canonical_target_when_release_candidate_is_clean(tmp_path: Path) -> None:
    repo_root = _setup_sync_repo(tmp_path, branch="release/candidate")
    env, call_log = _build_stub_env(tmp_path)

    result = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)

    assert result.returncode == 0, result.stderr
    assert "同步到 Aliyun-ECS-2:/root/deeptutor" in result.stdout
    log = call_log.read_text(encoding="utf-8")
    assert "ssh:Aliyun-ECS-2 mkdir -p '/root/deeptutor'" in log
    assert "rsync:-avz --delete --stats --no-owner --no-group" in log
    assert "Aliyun-ECS-2:/root/deeptutor/" in log


def test_deploy_runs_remote_backup_before_bootstrap(tmp_path: Path) -> None:
    repo_root = _setup_wrapper_repo(tmp_path, "deploy_aliyun.sh")
    env, call_log = _build_stub_env(tmp_path)

    result = _run(["bash", "scripts/deploy_aliyun.sh"], cwd=repo_root, env=env)

    assert result.returncode == 0, result.stderr
    log_lines = call_log.read_text(encoding="utf-8").splitlines()
    assert log_lines[0] == "sync:once"
    assert "python3 scripts/backup_data.py --project-root '/root/deeptutor' --keep '2'" in log_lines[1]
    assert "bash scripts/server_bootstrap_aliyun.sh" in log_lines[2]
    assert log_lines[3] == "verify-public:"


def test_fast_redeploy_runs_remote_backup_before_reload(tmp_path: Path) -> None:
    repo_root = _setup_wrapper_repo(tmp_path, "redeploy_aliyun_fast.sh")
    env, call_log = _build_stub_env(tmp_path)

    result = _run(["bash", "scripts/redeploy_aliyun_fast.sh"], cwd=repo_root, env=env)

    assert result.returncode == 0, result.stderr
    log_lines = call_log.read_text(encoding="utf-8").splitlines()
    assert log_lines[0] == "sync:once"
    assert "python3 scripts/backup_data.py --project-root '/root/deeptutor' --keep '2'" in log_lines[1]
    assert "bash scripts/server_fast_reload_aliyun.sh" in log_lines[2]
    assert log_lines[3] == "verify-public:"
