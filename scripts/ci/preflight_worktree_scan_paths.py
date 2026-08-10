#!/usr/bin/env python3
"""列出「工作区里还没提交、但需要过密钥扫描」的文件路径（每行一个）。

`scripts/preflight_pr.sh` 用它补 CI 看不见的那一半：CI 的 secret scan 只看
base..head 的**已提交** diff，本地开 PR 前真正危险的恰恰是还躺在工作区里的
改动和新文件（.env 副本、临时脚本里粘的 key）。

刻意不复制过滤规则：生成物 / 二进制 / runtime supply 的排除清单只有
``scripts/ci/tests_workflow_scope.py`` 一份权威，这里直接调它的
``secret_scan_files``。两份清单会漂，漂了就等于本地和 CI 判据不一致。

纯读操作，无副作用。没有需要扫描的文件时输出为空、退出码 0。
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tests_workflow_scope import secret_scan_files  # noqa: E402


def worktree_paths() -> list[str]:
    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    paths: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        entry = line[3:]
        if " -> " in entry:  # rename/copy：只扫新路径
            entry = entry.split(" -> ", 1)[1]
        entry = entry.strip().strip('"')
        if not entry or entry.endswith("/"):
            continue
        if Path(entry).is_file():  # 删除态的路径不存在，跳过
            paths.append(entry)
    return paths


def main() -> int:
    for path in secret_scan_files(worktree_paths()):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
