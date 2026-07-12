#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash) — 拦截 git add 全量暂存。

用途:
  AGENTS.md §3.6 分支纪律:并行 agent 场景下 `git add -A` / `git add --all` /
  `git add .` 会把别的 agent 的未提交工作扫进自己的 commit(仓库已发生两次事故)。
  本 hook 只拦这三种字面形态;`git add ./specific/file`、`git add .claude/xxx`
  等具体路径不拦。

Fail-open 原则(必须遵守):
  - stdin 不是合法 JSON / 缺字段 / 任何未预期异常 → exit 0 放行。
  - 只有确定匹配到危险字面形态才 exit 2 阻断。
  - 本 hook 是止血带不是语义闭包;语义级绕过(如把命令写进脚本再执行)由
    AGENTS.md 散文权威兜底。

匹配逻辑:
  用 shlex 把命令切成 token(带引号的字符串保持为单 token,避免
  `echo '... git add -A ...'` 这类自匹配假阳性),按 shell 连接符
  (; && || | & 换行)切段;段内出现 `git ... add ...` 且 add 之后的参数
  token 中有:`--all`、单独的 `.`、或含 A 的短选项簇(-A / -Av 等) → 拦截。
"""
import json
import re
import shlex
import sys

SEPARATORS = {";", "&&", "||", "|", "&", "\n"}
SHORT_OPT_WITH_A = re.compile(r"^-[a-zA-Z]*A[a-zA-Z]*$")


def segments(tokens):
    """按 shell 连接符 token 切段。"""
    seg = []
    for tok in tokens:
        if tok in SEPARATORS:
            if seg:
                yield seg
            seg = []
        else:
            seg.append(tok)
    if seg:
        yield seg


# git 的这些全局选项自带一个独立参数值,识别子命令时要成对跳过
GIT_GLOBAL_OPTS_WITH_VALUE = {"-C", "-c", "--exec-path", "--work-tree",
                              "--git-dir", "--namespace"}


def segment_is_dangerous(seg):
    """段内是否为 git add 全量暂存。只认 git 后第一个真子命令,避免
    `git commit -m add .` 这类参数碰巧叫 add 的误伤。"""
    for i, tok in enumerate(seg):
        if tok != "git":
            continue
        # 跳过 git 全局选项,定位子命令
        k = i + 1
        subcommand = None
        while k < len(seg):
            t = seg[k]
            if t in GIT_GLOBAL_OPTS_WITH_VALUE:
                k += 2
                continue
            if t.startswith("-"):
                k += 1
                continue
            subcommand = t
            break
        if subcommand != "add":
            continue  # 段内可能还有下一个 'git'(防御性),继续外层扫描
        for a in seg[k + 1:]:
            if a == "--all" or a == ".":
                return True
            if SHORT_OPT_WITH_A.match(a):
                return True
    return False


def main():
    try:
        data = json.load(sys.stdin)
        command = data.get("tool_input", {}).get("command", "")
        if not isinstance(command, str) or "git" not in command:
            sys.exit(0)
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            sys.exit(0)  # 引号不闭合等解析失败 → fail-open
        for seg in segments(tokens):
            if segment_is_dangerous(seg):
                sys.stderr.write(
                    "AGENTS.md §分支纪律:并行 agent 场景 git add -A/. 会互扫工作"
                    "(两次事故),请用 git add <具体文件> 或 "
                    "git commit --only -- <文件>\n"
                )
                sys.exit(2)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # 任何未预期异常 → fail-open 放行


if __name__ == "__main__":
    main()
