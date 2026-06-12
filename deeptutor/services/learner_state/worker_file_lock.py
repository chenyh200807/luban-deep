"""跨 worker 的文件级非阻塞排他锁（fcntl.flock）。

多 uvicorn worker 各自挂载同一套 learner-state 后台循环（flusher /
heartbeat / dream cycle）；"同一时刻只要一个执行者"的约束用本模块表达。
锁非重入；持有进程退出（含被杀）时由内核自动释放，不会留死锁。
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
from typing import Iterator


def try_acquire_exclusive_lock(path: Path) -> int | None:
    """非阻塞获取排他锁，返回持锁 fd；他人持有时返回 None。

    与 release_exclusive_lock 配对使用；适合"在线程里拿锁、回事件循环干活、
    再回线程释放"的 async 场景（fcntl/open/mkdir 都是阻塞 syscall，
    不应落在事件循环线程上）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def release_exclusive_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


@contextmanager
def try_exclusive_file_lock(path: Path) -> Iterator[bool]:
    """非阻塞获取排他锁。yield True=已持有（退出 with 时释放）；False=他人持有。

    语义注意：flock 按 open-file-description 记账——同进程再次 open+flock
    同样被拒（非重入），与他进程持有不可区分；持锁进程退出（含被杀）由内核
    自动释放。目标平台为 Linux 容器 / macOS 开发机。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


__all__ = ["release_exclusive_lock", "try_acquire_exclusive_lock", "try_exclusive_file_lock"]
