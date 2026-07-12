#!/usr/bin/env python3
"""PostToolUse hook (matcher: Edit|Write) — SKILL.md 改动自动校验。

用途:
  当 Edit/Write 的目标文件匹配 agent-skills/**/SKILL.md 时,自动运行
  agent-skills/scripts/validate_agent_skills.py(README 索引 / AGENTS 链接 /
  catalog.yaml 登记等一致性校验),失败时以 exit 2 把校验器输出经 stderr
  反馈给模型,提醒补登记(register-before-use 纪律)。

Fail-open 原则(必须遵守):
  - stdin 不是合法 JSON / 文件路径不匹配 / 校验脚本不存在 / 校验超时(30s)/
    任何未预期异常 → exit 0 放行。
  - 只有"校验器真实跑完且返回非零"才 exit 2 —— 那是真实信号,不是 hook 故障。
  - PostToolUse 的 exit 2 只反馈信息给模型,不会撤销已完成的编辑。
"""
import json
import os
import re
import subprocess
import sys

SKILL_PATH_RE = re.compile(r"agent-skills/.*SKILL\.md$")
VALIDATOR_REL = os.path.join("agent-skills", "scripts", "validate_agent_skills.py")
TIMEOUT_SECONDS = 30


def main():
    try:
        data = json.load(sys.stdin)
        file_path = data.get("tool_input", {}).get("file_path", "")
        if not isinstance(file_path, str) or not SKILL_PATH_RE.search(file_path):
            sys.exit(0)
        cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR")
        if not cwd or not os.path.isdir(cwd):
            sys.exit(0)  # 定位不到项目根 → fail-open
        validator = os.path.join(cwd, VALIDATOR_REL)
        if not os.path.isfile(validator):
            sys.exit(0)  # 校验脚本不存在 → fail-open
        try:
            proc = subprocess.run(
                [sys.executable or "python3", validator],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
        except (subprocess.TimeoutExpired, OSError):
            sys.exit(0)  # 超时/无法执行 → fail-open
        if proc.returncode != 0:
            output = (proc.stdout or "") + (proc.stderr or "")
            sys.stderr.write(
                "SKILL.md 校验失败(agent-skills/scripts/validate_agent_skills.py"
                " 返回非零)。请按 register-before-use 纪律补齐 README 索引 / "
                "AGENTS 链接 / catalog.yaml 登记:\n"
            )
            sys.stderr.write(output[-4000:])  # 只回传尾部,避免超长
            sys.exit(2)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # 任何未预期异常 → fail-open 放行


if __name__ == "__main__":
    main()
