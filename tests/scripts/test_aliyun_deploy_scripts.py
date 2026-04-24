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


def _build_stub_env(
    tmp_path: Path, *, execute_release_injection: bool = False, execute_remote_python: bool = False
) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    call_log = tmp_path / "calls.log"

    if execute_release_injection or execute_remote_python:
        ssh_stub = """\
            #!/usr/bin/env bash
            printf 'ssh:%s\n' "$*" >> "${CALLS_LOG}"
            remote_host="$1"
            shift
            command="$*"
            if [[ "${command}" == *"RELEASE_GIT_SHA="* || "${EXECUTE_REMOTE_PYTHON:-0}" == "1" ]]; then
              eval "${command}"
              exit $?
            fi
            exit 0
            """
    else:
        ssh_stub = """\
            #!/usr/bin/env bash
            printf 'ssh:%s\n' "$*" >> "${CALLS_LOG}"
            exit 0
            """
    _write_stub(bin_dir / "ssh", textwrap.dedent(ssh_stub))
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
    if execute_remote_python:
        env["EXECUTE_REMOTE_PYTHON"] = "1"
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
        scripts_dir / "verify_aliyun_observability.sh",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            printf 'verify-observability:%s\n' "$*" >> "${CALLS_LOG}"
            exit 0
            """
        ),
    )
    _write_stub(
        scripts_dir / "validate_aliyun_release_env.sh",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            printf 'validate-release-env:%s\n' "$*" >> "${CALLS_LOG}"
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


def _setup_script_repo(tmp_path: Path, script_name: str) -> Path:
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_SCRIPTS / script_name, scripts_dir / script_name)
    _make_executable(scripts_dir / script_name)
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
    git_sha = _run(["git", "rev-parse", "HEAD"], cwd=repo_root).stdout.strip()

    result = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)

    assert result.returncode == 0, result.stderr
    assert "同步到 Aliyun-ECS-2:/root/deeptutor" in result.stdout
    log = call_log.read_text(encoding="utf-8")
    assert "ssh:Aliyun-ECS-2 mkdir -p '/root/deeptutor'" in log
    assert "rsync:-avz --delete --stats --no-owner --no-group" in log
    assert "Aliyun-ECS-2:/root/deeptutor/" in log
    assert f"RELEASE_GIT_SHA='{git_sha}'" in log
    assert "DEEPTUTOR_RELEASE_ID=" in log
    assert "DEEPTUTOR_GIT_SHA=" in log


def test_sync_injects_release_lineage_into_remote_env(tmp_path: Path) -> None:
    repo_root = _setup_sync_repo(tmp_path, branch="release/candidate")
    (repo_root / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [project]
            name = "deeptutor"
            version = "2.3.4"
            """
        ),
        encoding="utf-8",
    )
    _run(["git", "add", "pyproject.toml"], cwd=repo_root)
    _run(["git", "commit", "-m", "add pyproject"], cwd=repo_root)
    git_sha = _run(["git", "rev-parse", "HEAD"], cwd=repo_root).stdout.strip()
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / ".env").write_text(
        "SERVICE_ENV=production\nAPP_ENV=production\nDEEPTUTOR_GIT_SHA=old\nFF_WORKER_CAPACITY_ISOLATION_V1=true\n",
        encoding="utf-8",
    )
    env, _ = _build_stub_env(tmp_path, execute_release_injection=True)
    env["ALLOW_NON_CANONICAL_DEPLOY"] = "1"
    env["REMOTE_HOST"] = "fake-host"
    env["REMOTE_DIR"] = str(remote_dir)

    result = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)

    assert result.returncode == 0, result.stderr
    env_content = (remote_dir / ".env").read_text(encoding="utf-8")
    assert f"DEEPTUTOR_SERVICE_VERSION=2.3.4\n" in env_content
    assert f"DEEPTUTOR_GIT_SHA={git_sha}\n" in env_content
    assert "DEEPTUTOR_ENV=production\n" in env_content
    assert f"DEEPTUTOR_RELEASE_ID=2.3.4+{git_sha}+production\n" in env_content
    assert f"DEEPTUTOR_PROMPT_VERSION=git-{git_sha[:12]}\n" in env_content
    assert "DEEPTUTOR_FF_SNAPSHOT_HASH=" in env_content
    assert "DEEPTUTOR_FF_SNAPSHOT_HASH=none\n" not in env_content


def test_validate_release_env_requires_ff_snapshot_hash(tmp_path: Path) -> None:
    repo_root = _setup_script_repo(tmp_path, "validate_aliyun_release_env.sh")
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / ".env").write_text(
        textwrap.dedent(
            """\
            SERVICE_ENV=production
            APP_ENV=production
            DEEPTUTOR_AUTH_SECRET=secret
            DEEPTUTOR_ADMIN_USER_IDS=user_1
            DEEPTUTOR_RELEASE_ID=1.0.0+abc+production
            DEEPTUTOR_GIT_SHA=abc
            DEEPTUTOR_PROMPT_VERSION=git-abc
            """
        ),
        encoding="utf-8",
    )
    env, _ = _build_stub_env(tmp_path, execute_remote_python=True)
    env["REMOTE_HOST"] = "fake-host"
    env["REMOTE_DIR"] = str(remote_dir)

    result = _run(["bash", "scripts/validate_aliyun_release_env.sh"], cwd=repo_root, env=env)

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "DEEPTUTOR_FF_SNAPSHOT_HASH" in combined


def test_validate_release_env_accepts_complete_lineage(tmp_path: Path) -> None:
    repo_root = _setup_script_repo(tmp_path, "validate_aliyun_release_env.sh")
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / ".env").write_text(
        textwrap.dedent(
            """\
            SERVICE_ENV=production
            APP_ENV=production
            DEEPTUTOR_AUTH_SECRET=secret
            DEEPTUTOR_ADMIN_USER_IDS=user_1
            DEEPTUTOR_RELEASE_ID=1.0.0+abc+production
            DEEPTUTOR_GIT_SHA=abc
            DEEPTUTOR_PROMPT_VERSION=git-abc
            DEEPTUTOR_FF_SNAPSHOT_HASH=ffaa00112233
            """
        ),
        encoding="utf-8",
    )
    env, _ = _build_stub_env(tmp_path, execute_remote_python=True)
    env["REMOTE_HOST"] = "fake-host"
    env["REMOTE_DIR"] = str(remote_dir)

    result = _run(["bash", "scripts/validate_aliyun_release_env.sh"], cwd=repo_root, env=env)

    assert result.returncode == 0, result.stderr
    assert "远端发布环境校验通过" in result.stdout
    assert "DEEPTUTOR_FF_SNAPSHOT_HASH=ffaa00112233" in result.stdout


def test_deploy_runs_remote_backup_before_bootstrap(tmp_path: Path) -> None:
    repo_root = _setup_wrapper_repo(tmp_path, "deploy_aliyun.sh")
    env, call_log = _build_stub_env(tmp_path)

    result = _run(["bash", "scripts/deploy_aliyun.sh"], cwd=repo_root, env=env)

    assert result.returncode == 0, result.stderr
    log_lines = call_log.read_text(encoding="utf-8").splitlines()
    assert log_lines[0] == "sync:once"
    assert log_lines[1] == "validate-release-env:"
    assert "python3 scripts/backup_data.py --project-root '/root/deeptutor' --keep '2'" in log_lines[2]
    assert "bash scripts/server_bootstrap_aliyun.sh" in log_lines[3]
    assert log_lines[4] == "verify-public:"
    assert log_lines[5] == "verify-observability:"


def test_fast_redeploy_runs_remote_backup_before_reload(tmp_path: Path) -> None:
    repo_root = _setup_wrapper_repo(tmp_path, "redeploy_aliyun_fast.sh")
    env, call_log = _build_stub_env(tmp_path)

    result = _run(["bash", "scripts/redeploy_aliyun_fast.sh"], cwd=repo_root, env=env)

    assert result.returncode == 0, result.stderr
    log_lines = call_log.read_text(encoding="utf-8").splitlines()
    assert log_lines[0] == "sync:once"
    assert log_lines[1] == "validate-release-env:"
    assert "python3 scripts/backup_data.py --project-root '/root/deeptutor' --keep '2'" in log_lines[2]
    assert "bash scripts/server_fast_reload_aliyun.sh" in log_lines[3]
    assert log_lines[4] == "verify-public:"
    assert log_lines[5] == "verify-observability:"
