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
            if [[ -n "${SSH_STUB_REMOTE_DIR_OVERRIDE:-}" ]]; then
              command="$(STUB_COMMAND="${command}" python3 - <<'PY'
import os

command = os.environ["STUB_COMMAND"]
override = os.environ["SSH_STUB_REMOTE_DIR_OVERRIDE"]
command = command.replace("REMOTE_DIR='/root/deeptutor'", f"REMOTE_DIR='{override}'")
command = command.replace("cd '/root/deeptutor'", f"cd '{override}'")
print(command)
PY
)"
            fi
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


def test_sync_dirty_override_does_not_bypass_main_branch_guard(tmp_path: Path) -> None:
    repo_root = _setup_sync_repo(tmp_path, branch="main")
    (repo_root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    env, call_log = _build_stub_env(tmp_path)
    env["ALLOW_DIRTY_DEPLOY"] = "1"

    result = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "禁止直接从 main 发布" in combined
    assert not call_log.exists()


def test_sync_dirty_override_does_not_bypass_canonical_target_guard(tmp_path: Path) -> None:
    repo_root = _setup_sync_repo(tmp_path, branch="release/candidate")
    (repo_root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    env, call_log = _build_stub_env(tmp_path)
    env["ALLOW_DIRTY_DEPLOY"] = "1"
    env["REMOTE_HOST"] = "Aliyun-ECS"

    result = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "REMOTE_HOST 必须固定为 Aliyun-ECS-2" in combined
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


def test_sync_noncanonical_override_is_not_supported(tmp_path: Path) -> None:
    repo_root = _setup_sync_repo(tmp_path, branch="release/candidate")
    env, call_log = _build_stub_env(tmp_path)
    env["ALLOW_NON_CANONICAL_DEPLOY"] = "1"
    env["REMOTE_DIR"] = "/root/luban"

    result = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "REMOTE_DIR 必须固定为 /root/deeptutor" in combined
    assert "禁止通过非 canonical 目录绕开 /root/deeptutor 写入边界" in combined
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
    assert "rsync:-avzc --delete --stats --no-owner --no-group --chmod=ugo+rX" in log
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
        "SERVICE_ENV=production\nAPP_ENV=production\nDEEPTUTOR_GIT_SHA=old\nFF_WORKER_CAPACITY_ISOLATION_V1=true\n",  # pragma: allowlist secret
        encoding="utf-8",
    )
    env, call_log = _build_stub_env(tmp_path, execute_release_injection=True)
    env["SSH_STUB_REMOTE_DIR_OVERRIDE"] = str(remote_dir)

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
    assert "DEEPTUTOR_GIT_DIRTY=false\n" in env_content
    assert "DEEPTUTOR_DEPLOY_MANIFEST_HASH=" in env_content


def test_sync_regenerates_stale_auto_prompt_version_from_release_sha(tmp_path: Path) -> None:
    """2026-08-01 生产实证：远端 DEEPTUTOR_PROMPT_VERSION=git-4505e0c10c90（04-24）与
    DEEPTUTOR_GIT_SHA（07-31）相差三个月——旧逻辑「远端已有值就保留」让脚本自己生成的
    lineage 戳永久粘住，观测面撒谎。`git-<sha>` 是机器戳，必须跟着发布 SHA 走。"""
    repo_root = _setup_sync_repo(tmp_path, branch="release/candidate")
    git_sha = _run(["git", "rev-parse", "HEAD"], cwd=repo_root).stdout.strip()
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / ".env").write_text(
        "SERVICE_ENV=production\nAPP_ENV=production\n"
        "DEEPTUTOR_PROMPT_VERSION=git-4505e0c10c90\n",  # pragma: allowlist secret
        encoding="utf-8",
    )
    env, _call_log = _build_stub_env(tmp_path, execute_release_injection=True)
    env["SSH_STUB_REMOTE_DIR_OVERRIDE"] = str(remote_dir)

    result = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)

    assert result.returncode == 0, result.stderr
    env_content = (remote_dir / ".env").read_text(encoding="utf-8")
    assert f"DEEPTUTOR_PROMPT_VERSION=git-{git_sha[:12]}\n" in env_content
    assert "git-4505e0c10c90" not in env_content


def test_sync_keeps_human_authored_prompt_version(tmp_path: Path) -> None:
    """反向边界：非 `git-` 的值是人写的独立 prompt 装载权威，脚本不得覆盖。"""
    repo_root = _setup_sync_repo(tmp_path, branch="release/candidate")
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / ".env").write_text(
        "SERVICE_ENV=production\nAPP_ENV=production\n"
        "DEEPTUTOR_PROMPT_VERSION=construction-tutor-v9\n",  # pragma: allowlist secret
        encoding="utf-8",
    )
    env, _call_log = _build_stub_env(tmp_path, execute_release_injection=True)
    env["SSH_STUB_REMOTE_DIR_OVERRIDE"] = str(remote_dir)

    result = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)

    assert result.returncode == 0, result.stderr
    env_content = (remote_dir / ".env").read_text(encoding="utf-8")
    assert "DEEPTUTOR_PROMPT_VERSION=construction-tutor-v9\n" in env_content  # pragma: allowlist secret


def test_sync_marks_dirty_release_lineage_when_dirty_override_is_used(tmp_path: Path) -> None:
    repo_root = _setup_sync_repo(tmp_path, branch="release/candidate")
    (repo_root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / ".env").write_text(
        "SERVICE_ENV=production\nAPP_ENV=production\nDEEPTUTOR_GIT_SHA=old\n",  # pragma: allowlist secret
        encoding="utf-8",
    )
    env, call_log = _build_stub_env(tmp_path, execute_release_injection=True)
    env["ALLOW_DIRTY_DEPLOY"] = "1"
    env["SSH_STUB_REMOTE_DIR_OVERRIDE"] = str(remote_dir)

    result = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)

    assert result.returncode == 0, result.stderr
    env_content = (remote_dir / ".env").read_text(encoding="utf-8")
    assert "DEEPTUTOR_GIT_DIRTY=true\n" in env_content
    assert "DEEPTUTOR_DEPLOY_MANIFEST_HASH=" in env_content
    assert "untracked.txt" in result.stderr


def test_sync_deploy_manifest_hash_excludes_env_and_report_artifacts(tmp_path: Path) -> None:
    repo_root = _setup_sync_repo(tmp_path, branch="release/candidate")
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / ".env").write_text(
        "SERVICE_ENV=production\nAPP_ENV=production\nDEEPTUTOR_GIT_SHA=old\n",  # pragma: allowlist secret
        encoding="utf-8",
    )
    env, call_log = _build_stub_env(tmp_path, execute_release_injection=True)
    env["ALLOW_DIRTY_DEPLOY"] = "1"
    env["SSH_STUB_REMOTE_DIR_OVERRIDE"] = str(remote_dir)

    first = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)
    assert first.returncode == 0, first.stderr
    first_env = (remote_dir / ".env").read_text(encoding="utf-8")
    first_hash = next(
        line.split("=", 1)[1]
        for line in first_env.splitlines()
        if line.startswith("DEEPTUTOR_DEPLOY_MANIFEST_HASH=")
    )

    (repo_root / "web").mkdir()
    (repo_root / "web" / ".env.local").write_text("SECRET=value\n", encoding="utf-8")
    (repo_root / ".secrets.baseline").write_text("{}\n", encoding="utf-8")
    report_dir = repo_root / "web" / "playwright-report"
    report_dir.mkdir()
    (report_dir / "index.html").write_text("<html>report</html>\n", encoding="utf-8")
    test_results_dir = repo_root / "test-results"
    test_results_dir.mkdir()
    (test_results_dir / "trace.zip").write_text("trace\n", encoding="utf-8")
    (repo_root / ".gstack").mkdir()
    (repo_root / ".gstack" / "state.json").write_text("{}\n", encoding="utf-8")
    (repo_root / ".local-runs").mkdir()
    (repo_root / ".local-runs" / "probe.log").write_text("probe\n", encoding="utf-8")
    (repo_root / "dist").mkdir()
    (repo_root / "dist" / "artifact.whl").write_text("artifact\n", encoding="utf-8")

    second = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)
    assert second.returncode == 0, second.stderr
    second_env = (remote_dir / ".env").read_text(encoding="utf-8")
    second_hash = next(
        line.split("=", 1)[1]
        for line in second_env.splitlines()
        if line.startswith("DEEPTUTOR_DEPLOY_MANIFEST_HASH=")
    )
    assert second_hash == first_hash
    log = call_log.read_text(encoding="utf-8")
    assert "RELEASE_EXCLUDES_JSON=" in log
    assert ".env*" in log
    assert ".secrets*" in log
    assert "playwright-report*" in log
    assert "test-results" in log
    assert "coverage" in log
    assert ".gstack" in log
    assert ".local-runs" in log
    assert "dist" in log

    (repo_root / "included_runtime_file.txt").write_text("runtime\n", encoding="utf-8")
    third = _run(["bash", "scripts/sync_to_aliyun.sh", "once"], cwd=repo_root, env=env)
    assert third.returncode == 0, third.stderr
    third_env = (remote_dir / ".env").read_text(encoding="utf-8")
    third_hash = next(
        line.split("=", 1)[1]
        for line in third_env.splitlines()
        if line.startswith("DEEPTUTOR_DEPLOY_MANIFEST_HASH=")
    )
    assert third_hash != first_hash


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


def test_validate_release_env_requires_security_observability_and_rag_ff(tmp_path: Path) -> None:
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

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "DEEPTUTOR_ATTEMPT_REF_SECRET" in combined
    assert "DEEPTUTOR_METRICS_TOKEN" in combined
    assert "SUPABASE_RAG_COMPILED_TRUTH_ENABLED" in combined
    assert "SUPABASE_RAG_PROVENANCE_BOOST_ENABLED" in combined


def test_validate_release_env_blocks_rag_compiled_truth_enabled(tmp_path: Path) -> None:
    repo_root = _setup_script_repo(tmp_path, "validate_aliyun_release_env.sh")
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / ".env").write_text(
        textwrap.dedent(
            """\
            SERVICE_ENV=production
            APP_ENV=production
            DEEPTUTOR_AUTH_SECRET=secret
            DEEPTUTOR_ATTEMPT_REF_SECRET=attempt-secret
            DEEPTUTOR_METRICS_TOKEN=metrics-secret
            DEEPTUTOR_ADMIN_USER_IDS=user_1
            DEEPTUTOR_RELEASE_ID=1.0.0+abc+production
            DEEPTUTOR_GIT_SHA=abc
            DEEPTUTOR_PROMPT_VERSION=git-abc
            DEEPTUTOR_FF_SNAPSHOT_HASH=ffaa00112233
            SUPABASE_RAG_COMPILED_TRUTH_ENABLED=true
            SUPABASE_RAG_PROVENANCE_BOOST_ENABLED=false
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
    assert "SUPABASE_RAG_COMPILED_TRUTH_ENABLED 必须显式为 false" in combined


def test_validate_release_env_rejects_weak_attempt_ref_secret(tmp_path: Path) -> None:
    repo_root = _setup_script_repo(tmp_path, "validate_aliyun_release_env.sh")
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / ".env").write_text(
        textwrap.dedent(
            """\
            SERVICE_ENV=production
            APP_ENV=production
            DEEPTUTOR_AUTH_SECRET=secret
            DEEPTUTOR_ATTEMPT_REF_SECRET=dev-attempt-ref-secret
            DEEPTUTOR_METRICS_TOKEN=metrics-secret
            DEEPTUTOR_ADMIN_USER_IDS=user_1
            DEEPTUTOR_RELEASE_ID=1.0.0+abc+production
            DEEPTUTOR_GIT_SHA=abc
            DEEPTUTOR_PROMPT_VERSION=git-abc
            DEEPTUTOR_FF_SNAPSHOT_HASH=ffaa00112233
            SUPABASE_RAG_COMPILED_TRUTH_ENABLED=false
            SUPABASE_RAG_PROVENANCE_BOOST_ENABLED=false
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
    assert "DEEPTUTOR_ATTEMPT_REF_SECRET" in combined


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
            DEEPTUTOR_ATTEMPT_REF_SECRET=attempt-secret-with-at-least-32-chars
            DEEPTUTOR_METRICS_TOKEN=metrics-secret
            DEEPTUTOR_ADMIN_USER_IDS=user_1
            DEEPTUTOR_RELEASE_ID=1.0.0+abc+production
            DEEPTUTOR_GIT_SHA=abc
            DEEPTUTOR_PROMPT_VERSION=git-abc
            DEEPTUTOR_FF_SNAPSHOT_HASH=ffaa00112233
            SUPABASE_RAG_COMPILED_TRUTH_ENABLED=false
            SUPABASE_RAG_PROVENANCE_BOOST_ENABLED=false
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


def test_validate_release_env_treats_aliyun_env_as_production(tmp_path: Path) -> None:
    # M6: production detection must mirror deeptutor/services/runtime_env.py. 'aliyun' is
    # a production env name there, so a DEEPTUTOR_ENV=aliyun release with a missing
    # required key must FAIL the checks — not silently skip them (the old fail-open
    # `== 'production'` test treated 'aliyun' as non-production and skipped everything).
    repo_root = _setup_script_repo(tmp_path, "validate_aliyun_release_env.sh")
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / ".env").write_text(
        textwrap.dedent(
            """\
            DEEPTUTOR_ENV=aliyun
            DEEPTUTOR_AUTH_SECRET=secret
            """
        ),
        encoding="utf-8",
    )
    env, _ = _build_stub_env(tmp_path, execute_remote_python=True)
    env["REMOTE_HOST"] = "fake-host"
    env["REMOTE_DIR"] = str(remote_dir)

    result = _run(["bash", "scripts/validate_aliyun_release_env.sh"], cwd=repo_root, env=env)

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0, "aliyun env must be treated as production and run the checks"
    assert "跳过生产发布必填校验" not in combined, "aliyun must NOT skip production checks"


def test_validate_release_env_explicit_non_production_still_skips(tmp_path: Path) -> None:
    # The mirror keeps the legitimate skip: an explicit non-production env (development)
    # still skips the production-only checks, so dev/test envs are not over-constrained.
    repo_root = _setup_script_repo(tmp_path, "validate_aliyun_release_env.sh")
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / ".env").write_text("DEEPTUTOR_ENV=development\n", encoding="utf-8")
    env, _ = _build_stub_env(tmp_path, execute_remote_python=True)
    env["REMOTE_HOST"] = "fake-host"
    env["REMOTE_DIR"] = str(remote_dir)

    result = _run(["bash", "scripts/validate_aliyun_release_env.sh"], cwd=repo_root, env=env)

    assert result.returncode == 0, result.stderr
    assert "跳过生产发布必填校验" in result.stdout


def test_validate_release_env_production_names_stay_in_sync_with_runtime_authority() -> None:
    # Single authority: the validator replicates runtime_env's NON-production allowlist
    # (it runs in an SSH heredoc and cannot import the package). If runtime_env ever
    # narrows that set (turning a name into production), this fails so the script is
    # updated too — preventing a production env from silently skipping its checks.
    from deeptutor.services.runtime_env import _NON_PRODUCTION_ENV_NAMES

    script = (SOURCE_SCRIPTS / "validate_aliyun_release_env.sh").read_text(encoding="utf-8")
    for name in _NON_PRODUCTION_ENV_NAMES:
        assert f"'{name}'" in script, (
            f"validate_aliyun_release_env.sh must list non-production name {name!r} "
            "to stay in sync with deeptutor/services/runtime_env.py"
        )


def test_runtime_backup_cron_writes_only_inside_canonical_root() -> None:
    # M8: the cron example must keep all writes inside /root/deeptutor (AGENTS.md §3.7),
    # never /opt/deeptutor or /var/log which violate the single writable-root boundary.
    cron = (REPO_ROOT / "deployment" / "backup" / "runtime-backup.cron.example").read_text(
        encoding="utf-8"
    )
    # Check the actual cron command lines only — a comment may legitimately mention the
    # forbidden paths to explain the boundary.
    command_lines = [
        line for line in cron.splitlines() if line.strip() and not line.strip().startswith("#")
    ]
    assert command_lines, "cron example has no active command lines"
    for line in command_lines:
        assert "/opt/deeptutor" not in line, f"cron must not use /opt/deeptutor: {line}"
        assert "/var/log" not in line, f"cron must not write to /var/log: {line}"
        assert "cd /root/deeptutor" in line, f"cron must run inside /root/deeptutor: {line}"
        assert ">> /root/deeptutor/" in line, f"cron log must stay under /root/deeptutor: {line}"


def test_deploy_runs_remote_backup_before_bootstrap(tmp_path: Path) -> None:
    repo_root = _setup_wrapper_repo(tmp_path, "deploy_aliyun.sh")
    env, call_log = _build_stub_env(tmp_path)
    env["FORCE_FULL_REBUILD"] = "1"

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


def test_isolated_long_dialog_defaults_to_fail_closed_gate(tmp_path: Path) -> None:
    repo_root = _setup_script_repo(tmp_path, "server_run_long_dialog_v1_aliyun_isolated.sh")
    source_json = tmp_path / "source.json"
    source_json.write_text("{}", encoding="utf-8")
    host_output_dir = tmp_path / "ld-output"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    call_log = tmp_path / "calls.log"
    _write_stub(
        bin_dir / "docker",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            printf 'docker:%s\n' "$*" >> "${CALLS_LOG}"
            exit 0
            """
        ),
    )
    _write_stub(
        bin_dir / "logger",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            printf 'logger:%s\n' "$*" >> "${CALLS_LOG}"
            exit 0
            """
        ),
    )
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["CALLS_LOG"] = str(call_log)
    env["SOURCE_JSON_HOST"] = str(source_json)
    env["HOST_OUTPUT_DIR"] = str(host_output_dir)

    result = _run(
        ["bash", "scripts/server_run_long_dialog_v1_aliyun_isolated.sh", "--turn-mode", "focus"],
        cwd=repo_root,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    log = call_log.read_text(encoding="utf-8")
    assert "--fail-on-hard-errors" in log
    assert "--turn-mode focus" in log


def test_remote_reload_scripts_probe_health_and_readiness() -> None:
    for script_name in ("server_fast_reload_aliyun.sh", "server_restart_aliyun.sh"):
        content = (SOURCE_SCRIPTS / script_name).read_text(encoding="utf-8")
        assert "/healthz" in content
        assert "/readyz" in content
        assert 'http://127.0.0.1:${backend_port}/"' not in content


def test_fast_reload_does_not_use_container_hot_patch() -> None:
    content = (SOURCE_SCRIPTS / "server_fast_reload_aliyun.sh").read_text(encoding="utf-8")

    assert "\ndocker cp " not in content
    assert "build deeptutor" in content
    assert "force-recreate deeptutor" in content


def test_rollback_uses_remote_dir_staging_not_tmp() -> None:
    content = (SOURCE_SCRIPTS / "rollback_aliyun_release.sh").read_text(encoding="utf-8")

    assert "tempfile.mkdtemp" not in content
    assert "remote_dir / 'tmp' / 'release_restore'" in content
    assert "Path(os.environ['REMOTE_DIR']).resolve()" in content
    assert "snapshot.resolve()" in content
    assert "release_dir not in snapshot.parents" in content


def test_env_examples_pin_production_security_and_rag_flags() -> None:
    required_lines = {
        "DEEPTUTOR_ATTEMPT_REF_SECRET=",
        "DEEPTUTOR_METRICS_TOKEN=",
        "SUPABASE_RAG_COMPILED_TRUTH_ENABLED=false",
        "SUPABASE_RAG_PROVENANCE_BOOST_ENABLED=false",
    }
    for rel_path in (".env.example", ".env.example_CN", "deployment/aliyun/aliyun.env.example"):
        content = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        missing = sorted(line for line in required_lines if line not in content)
        assert not missing, f"{rel_path} missing: {missing}"
