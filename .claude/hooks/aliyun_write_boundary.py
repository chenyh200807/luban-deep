#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash) — 阿里云写边界拦截。

用途:
  AGENTS.md §3.7 Aliyun SSH Write Boundary:阿里云主机上唯一可写路径是
  /root/deeptutor。本 hook 拦截两类字面形态:
  1. `ssh <含 aliyun 的主机> '<远端命令>'`,且远端命令含明显写动作
     (rm/mv/cp/tee/chmod/chown/mkdir/touch/truncate/dd/sed -i/重定向 > >>),
     且能解析出以 / 开头的写目标路径、该路径不在 /root/deeptutor 内。
  2. `scp`/`rsync` 的**最后一个参数**(即目标)形如 `<含aliyun主机>:/绝对路径`
     且路径不在 /root/deeptutor 内(目标为远端才是写;远端为源=下载=只读,不拦)。

Fail-open 原则(必须遵守):
  - stdin 不是合法 JSON / shlex 解析失败 / 任何未预期异常 → exit 0 放行。
  - 解析不出以 / 开头的写目标路径 → 放行(宁漏勿误拦)。
  - 主机 token 必须独立含 aliyun(大小写不敏感);引号包裹的整段字符串
    (如 echo 'ssh Aliyun ...')不会让外层命令误中,因为外层没有独立的
    ssh token —— 避免 guard 自匹配假阳性(项目 memory 教训)。

本 hook 是止血带不是语义闭包:base64、脚本间接执行、远端二跳等语义级绕过
由 AGENTS.md 散文权威兜底。
"""
import json
import re
import shlex
import sys

BOUNDARY = "/root/deeptutor"
SEPARATORS = {";", "&&", "||", "|", "&", "\n"}
# 写动作命令 → 写目标路径的判定方式
WRITE_CMDS_ALL_PATHS = {"rm", "chmod", "chown", "mkdir", "touch", "truncate", "tee"}
WRITE_CMDS_LAST_PATH = {"mv", "cp"}  # 只有目的地(最后一个绝对路径)算写目标
REDIRECT_RE = re.compile(r">>?\s*(/[^\s;|&<>]+)")
DD_OF_RE = re.compile(r"\bof=(/[^\s;|&]+)")
# 重定向到这些设备文件是常见只读习惯用法(2>/dev/null 等),不算写出界
REDIRECT_DEVICE_ALLOWLIST = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty"}
# ssh 中自带参数值的选项(识别主机 token 时成对跳过)
SSH_OPTS_WITH_VALUE = {"-p", "-i", "-l", "-o", "-F", "-J", "-L", "-R", "-D",
                       "-W", "-b", "-c", "-e", "-m", "-E", "-Q", "-S", "-B"}


def inside_boundary(path):
    p = path.rstrip("/")
    return p == BOUNDARY or p.startswith(BOUNDARY + "/")


def segments(tokens):
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


def remote_command_of_ssh(seg):
    """seg 形如 ssh [opts] host [cmd...]。返回 (host, 远端命令字符串) 或 None。"""
    if "ssh" not in seg:
        return None
    i = seg.index("ssh")
    k = i + 1
    host = None
    while k < len(seg):
        t = seg[k]
        if t in SSH_OPTS_WITH_VALUE:
            k += 2
            continue
        if t.startswith("-"):
            k += 1
            continue
        host = t
        break
    if host is None:
        return None
    remote = " ".join(seg[k + 1:])
    return host, remote


def remote_has_out_of_boundary_write(remote):
    """远端命令字符串是否包含'写动作 + 边界外绝对路径'。解析不出路径 → False。"""
    # 1) 重定向 > / >>
    for m in REDIRECT_RE.finditer(remote):
        path = m.group(1)
        if path in REDIRECT_DEVICE_ALLOWLIST:
            continue
        if not inside_boundary(path):
            return True
    # 2) dd of=
    for m in DD_OF_RE.finditer(remote):
        if not inside_boundary(m.group(1)):
            return True
    # 3) 命令级写动作
    try:
        rtokens = shlex.split(remote, posix=True)
    except ValueError:
        return False  # fail-open
    for seg in segments(rtokens):
        if not seg:
            continue
        # sudo/env/nohup 前缀与 VAR=val 环境赋值剥掉,取第一个像命令的 token
        idx = 0
        while idx < len(seg) and (
                seg[idx] in {"sudo", "env", "nohup"}
                or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[idx])):
            idx += 1
        if idx >= len(seg):
            continue
        cmd = seg[idx].split("/")[-1]  # /usr/bin/rm → rm
        args = seg[idx + 1:]
        abs_paths = [a for a in args if a.startswith("/")]
        if cmd in WRITE_CMDS_ALL_PATHS:
            if any(not inside_boundary(p) for p in abs_paths):
                return True
        elif cmd in WRITE_CMDS_LAST_PATH:
            if abs_paths and not inside_boundary(abs_paths[-1]):
                return True
        elif cmd == "sed":
            if any(a == "-i" or a.startswith("-i") for a in args if a.startswith("-")):
                if any(not inside_boundary(p) for p in abs_paths):
                    return True
        elif cmd == "dd":
            for a in args:
                if a.startswith("of=/") and not inside_boundary(a[3:]):
                    return True
    return False


def check_scp_rsync(seg):
    """scp/rsync 最后一个参数为 aliyun 主机:边界外绝对路径 → True。"""
    if not seg:
        return False
    cmd = seg[0].split("/")[-1]
    if cmd not in {"scp", "rsync"}:
        return False
    args = [a for a in seg[1:] if not a.startswith("-")]
    if not args:
        return False
    dest = args[-1]
    m = re.match(r"^([^:@\s]+@)?([^:\s]*aliyun[^:\s]*):(/.*)$", dest, re.IGNORECASE)
    if m and not inside_boundary(m.group(3)):
        return True
    return False


def main():
    try:
        data = json.load(sys.stdin)
        command = data.get("tool_input", {}).get("command", "")
        if not isinstance(command, str) or "aliyun" not in command.lower():
            sys.exit(0)
        try:
            tokens = shlex.split(command, posix=True)
        except ValueError:
            sys.exit(0)  # fail-open
        for seg in segments(tokens):
            # ssh 分支
            info = remote_command_of_ssh(seg)
            if info is not None:
                host, remote = info
                if "aliyun" in host.lower() and remote:
                    if remote_has_out_of_boundary_write(remote):
                        sys.stderr.write(
                            "违反 AGENTS.md §3.7 阿里云写边界:检测到对 "
                            "/root/deeptutor 之外路径的远端写操作。阿里云主机上"
                            "唯一可写边界是 /root/deeptutor;请改写目标路径,"
                            "或确认为只读命令。\n"
                        )
                        sys.exit(2)
            # scp/rsync 分支
            if check_scp_rsync(seg):
                sys.stderr.write(
                    "违反 AGENTS.md §3.7 阿里云写边界:scp/rsync 目标为阿里云 "
                    "/root/deeptutor 之外的路径。唯一可写边界是 /root/deeptutor。\n"
                )
                sys.exit(2)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # 任何未预期异常 → fail-open 放行


if __name__ == "__main__":
    main()
