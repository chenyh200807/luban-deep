"""Claude Code 确定性强制层 hook 回归测试。

被测对象(随 repo 分发,任何人改坏都会在 CI 里现形):
  .claude/hooks/block_git_add_all.py   — PreToolUse(Bash) 拦 git add 全量暂存
  .claude/hooks/aliyun_write_boundary.py — PreToolUse(Bash) 拦阿里云边界外写
  .claude/hooks/validate_skill_md.py   — PostToolUse(Edit|Write) SKILL.md 校验

测法:subprocess 把 Claude Code hook 协议的 JSON 喂给脚本 stdin,断言退出码。
约定:exit 0 = 放行,exit 2 = 阻断(stderr 带说明);任何解析失败必须 fail-open。

validate_skill_md 的"真跑校验器"分支不直接跑仓库级 validate_agent_skills.py
(重 IO、慢),而是在 tmp cwd 里放一个假校验器,分别断言退出 0 / 非零两条真实分支。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"

GIT_ADD_HOOK = HOOKS_DIR / "block_git_add_all.py"
ALIYUN_HOOK = HOOKS_DIR / "aliyun_write_boundary.py"
SKILL_HOOK = HOOKS_DIR / "validate_skill_md.py"

ALLOW = 0
BLOCK = 2


def run_hook(hook_path, stdin_text, timeout=30):
    """把原始 stdin 文本喂给 hook 脚本,返回 CompletedProcess。"""
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(REPO_ROOT),
    )


def bash_payload(command):
    """PreToolUse(Bash) 的 hook 输入 JSON。"""
    return json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}}
    )


def edit_payload(file_path, cwd):
    """PostToolUse(Edit|Write) 的 hook 输入 JSON。"""
    return json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {"file_path": file_path},
            "cwd": cwd,
        }
    )


def test_hook_scripts_exist():
    """三个 hook 必须随 repo 存在(分发前提)。"""
    for p in (GIT_ADD_HOOK, ALIYUN_HOOK, SKILL_HOOK):
        assert p.is_file(), f"hook 缺失: {p}"


# ---------------------------------------------------------------------------
# block_git_add_all.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "command",
    [
        "git add -A",
        "git add --all",
        "cd subdir && git add . && git commit -m 'msg'",
        "git add -Av",
        "git add -A && git commit -m wip",
    ],
    ids=["dash-A", "long-all", "chained-dot", "short-cluster-Av", "chained-A"],
)
def test_git_add_blocks_bulk_staging(command):
    proc = run_hook(GIT_ADD_HOOK, bash_payload(command))
    assert proc.returncode == BLOCK, f"应拦截: {command!r}\nstderr={proc.stderr}"
    assert "git add" in proc.stderr  # 阻断必须带人类可读理由


@pytest.mark.parametrize(
    "command",
    [
        "git add .claude/settings.json",
        "git add ./docs/a.md",
        "git commit --only -- x",
        "echo 'git add -A' >> notes.md",
        "git status && git diff --stat",
    ],
    ids=["specific-file", "dot-slash-path", "commit-only", "quoted-mention", "readonly-git"],
)
def test_git_add_allows_safe_commands(command):
    proc = run_hook(GIT_ADD_HOOK, bash_payload(command))
    assert proc.returncode == ALLOW, f"不应拦截: {command!r}\nstderr={proc.stderr}"


def test_git_add_fail_open_on_invalid_json():
    proc = run_hook(GIT_ADD_HOOK, "this is not json{{{")
    assert proc.returncode == ALLOW


def test_git_add_fail_open_on_missing_command_field():
    proc = run_hook(GIT_ADD_HOOK, json.dumps({"tool_input": {}}))
    assert proc.returncode == ALLOW


# ---------------------------------------------------------------------------
# aliyun_write_boundary.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "command",
    [
        "ssh Aliyun-ECS-2 'rm /root/luban/x'",
        "ssh Aliyun-ECS-2 'echo hi > /etc/cron.d/x'",
        "scp a.py Aliyun-ECS-2:/opt/x.py",
        "ssh Aliyun-ECS-2 'rm /root/deeptutor-evil/x'",
        "ssh root@Aliyun-ECS-2 'mv /root/deeptutor/a.py /opt/a.py'",
    ],
    ids=["ssh-rm-outside", "ssh-redirect-cron", "scp-upload-outside",
         "prefix-spoof-deeptutor-evil", "mv-dest-outside"],
)
def test_aliyun_blocks_out_of_boundary_writes(command):
    proc = run_hook(ALIYUN_HOOK, bash_payload(command))
    assert proc.returncode == BLOCK, f"应拦截: {command!r}\nstderr={proc.stderr}"
    assert "/root/deeptutor" in proc.stderr  # 阻断必须指明唯一可写边界


@pytest.mark.parametrize(
    "command",
    [
        "ssh Aliyun-ECS-2 'docker logs deeptutor-backend --tail 50'",
        "ssh Aliyun-ECS-2 'cat /etc/nginx/nginx.conf'",
        "rm -rf /tmp/x",
        "ssh Aliyun-ECS-2 'rm /root/deeptutor/tmp/old.log'",
        "scp Aliyun-ECS-2:/root/luban/report.json ./report.json",
        "ssh Aliyun-ECS-2 'ls /var/log 2>/dev/null'",
    ],
    ids=["remote-readonly-docker", "remote-readonly-cat", "local-rm-no-aliyun",
         "write-inside-boundary", "scp-download-direction", "dev-null-allowlist"],
)
def test_aliyun_allows_safe_commands(command):
    proc = run_hook(ALIYUN_HOOK, bash_payload(command))
    assert proc.returncode == ALLOW, f"不应拦截: {command!r}\nstderr={proc.stderr}"


def test_aliyun_fail_open_on_invalid_json():
    proc = run_hook(ALIYUN_HOOK, "not json at all")
    assert proc.returncode == ALLOW


def test_aliyun_allows_quoted_mention_without_real_ssh():
    """引号内提及 ssh Aliyun 不构成独立 ssh token → 不得自匹配(项目 memory 教训)。"""
    proc = run_hook(
        ALIYUN_HOOK,
        bash_payload("echo 'ssh Aliyun-ECS-2 rm /etc/x' >> notes.md"),
    )
    assert proc.returncode == ALLOW, proc.stderr


# ---------------------------------------------------------------------------
# validate_skill_md.py
# ---------------------------------------------------------------------------

def test_skill_md_ignores_non_skill_paths():
    proc = run_hook(SKILL_HOOK, edit_payload("docs/a.md", str(REPO_ROOT)))
    assert proc.returncode == ALLOW


def test_skill_md_fail_open_on_invalid_json():
    proc = run_hook(SKILL_HOOK, "{{{broken")
    assert proc.returncode == ALLOW


def test_skill_md_fail_open_on_missing_cwd():
    """cwd 指向不存在目录 → 定位不到项目根 → fail-open。"""
    proc = run_hook(
        SKILL_HOOK,
        edit_payload("agent-skills/foo/SKILL.md", "/nonexistent/dir/xyz"),
    )
    assert proc.returncode == ALLOW


def test_skill_md_fail_open_when_validator_missing(tmp_path):
    """cwd 合法但没有 validate_agent_skills.py → fail-open。"""
    proc = run_hook(
        SKILL_HOOK,
        edit_payload("agent-skills/foo/SKILL.md", str(tmp_path)),
    )
    assert proc.returncode == ALLOW


def _make_fake_validator(tmp_path, exit_code):
    scripts_dir = tmp_path / "agent-skills" / "scripts"
    scripts_dir.mkdir(parents=True)
    validator = scripts_dir / "validate_agent_skills.py"
    validator.write_text(
        "import sys\n"
        f"print('fake validator ran')\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return validator


def test_skill_md_passes_when_validator_green(tmp_path):
    """校验器退出 0 → hook 放行(真实分支,tmp cwd 避免仓库级重 IO)。"""
    _make_fake_validator(tmp_path, exit_code=0)
    proc = run_hook(
        SKILL_HOOK,
        edit_payload(str(tmp_path / "agent-skills" / "foo" / "SKILL.md"),
                     str(tmp_path)),
    )
    assert proc.returncode == ALLOW, proc.stderr


def test_skill_md_blocks_when_validator_fails(tmp_path):
    """校验器退出非零 → hook exit 2 且 stderr 回传校验输出。"""
    _make_fake_validator(tmp_path, exit_code=3)
    proc = run_hook(
        SKILL_HOOK,
        edit_payload(str(tmp_path / "agent-skills" / "foo" / "SKILL.md"),
                     str(tmp_path)),
    )
    assert proc.returncode == BLOCK
    assert "SKILL.md 校验失败" in proc.stderr
    assert "fake validator ran" in proc.stderr
