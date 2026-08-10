"""external_auth 存储锁的跨进程互斥回归钉。

背景(2026-07-26):生产实测 `UVICORN_WORKERS=2`,而 `_STORE_LOCK` 原本是裸
`threading.Lock()` —— 只在单进程内互斥。users.json / sessions.json 的
read-modify-write 在两个 worker 间结构上无保护,交错时静默丢账号绑定:

    P1 load {A}          P2 load {A}
    P1 write {A,B}       P2 write {A,C}   ← B 丢失,无任何错误

本文件钉住三件事:
  1. 跨进程并发 RMW 不丢更新(真起子进程,不是 mock)
  2. 同进程多线程并发 RMW 不丢更新
  3. 8 个持锁函数互不在锁内嵌套调用(非重入 flock 的前提;新增嵌套会立即死锁)
"""

from __future__ import annotations

import ast
import json
import multiprocessing as mp
import pathlib
import threading

import pytest

from deeptutor.services.member_console import external_auth


def _rmw_once(lock_env: str, data_path: str, key: str) -> None:
    """一次 read-modify-write,全程持锁。子进程入口必须是模块级函数。

    刻意复用生产的 `_write_json_mapping`(tempfile + replace 原子写),因为要复现的是
    **丢更新**而不是**文件损坏**:原子写保证了任何时刻读到的都是完整 JSON,所以
    修复前的失败模式与生产一致 —— 数据静默变少,没有任何异常。
    """
    import os

    os.environ["DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE"] = lock_env
    from deeptutor.services.member_console import external_auth as ea

    p = pathlib.Path(data_path)
    with ea._STORE_LOCK:
        payload = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        payload[key] = True
        ea._write_json_mapping(p, payload)


def _worker(lock_env: str, data_path: str, prefix: str, count: int) -> None:
    for i in range(count):
        _rmw_once(lock_env, data_path, f"{prefix}-{i}")


def _resolve_lock_path(lock_env: str, results) -> None:
    """Return one spawned worker's independently resolved lock path."""
    import os

    os.environ["DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE"] = lock_env
    from deeptutor.services.member_console import external_auth as ea

    results.put(str(ea._store_lock_path()))


@pytest.fixture()
def store(tmp_path, monkeypatch):
    users = tmp_path / "users.json"
    users.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(users))
    return users


def test_lock_path_does_not_depend_on_file_existence(tmp_path, monkeypatch):
    """锁要在 users.json 首次创建之前就能拿到 —— 路径解析不许依赖 exists()。"""
    missing = tmp_path / "not-created-yet" / "users.json"
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", str(missing))

    assert external_auth.get_external_auth_users_file() is None  # 文件确实不存在
    lock_path = external_auth._store_lock_path()  # 但锁路径仍必须确定
    assert lock_path.name == ".external_auth.lock"
    assert lock_path.parent == missing.parent

    with external_auth._STORE_LOCK:  # 且能真正获取(会自动建父目录)
        assert lock_path.exists()


def test_implicit_legacy_store_and_lock_share_one_effective_path(
    tmp_path, monkeypatch
):
    """受支持的 implicit legacy writer 不得被不可写 primary 锁路径阻断。"""
    primary = tmp_path / "primary" / "users.json"
    legacy = tmp_path / "legacy" / "users.json"
    legacy.parent.mkdir()
    legacy.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", raising=False)
    monkeypatch.setattr(external_auth, "_PRIMARY_USERS_FILE", primary)
    monkeypatch.setattr(external_auth, "_LEGACY_USERS_FILE", legacy)
    monkeypatch.setattr(
        external_auth, "_allow_legacy_external_auth_default", lambda: True
    )

    assert external_auth._resolve_users_file_for_write() == legacy
    assert external_auth._store_lock_path() == legacy.with_name(
        ".external_auth.lock"
    )
    with external_auth._STORE_LOCK:
        assert external_auth._store_lock_path().exists()


def test_lock_releases_after_exception(store):
    """异常路径必须释放 thread lock 与 flock，后续 mutation 才不会永久挂死。"""
    with pytest.raises(RuntimeError, match="boom"):
        with external_auth._STORE_LOCK:
            raise RuntimeError("boom")
    with external_auth._STORE_LOCK:
        assert external_auth._store_lock_path().exists()


def test_all_processes_resolve_the_same_lock_path(tmp_path, monkeypatch):
    """互斥的唯一要求:所有 worker 算出同一个路径。"""
    users = str(tmp_path / "u.json")
    monkeypatch.setenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", users)
    expected = str(external_auth._store_lock_path())
    ctx = mp.get_context("spawn")
    results = ctx.Queue()
    procs = [
        ctx.Process(target=_resolve_lock_path, args=(users, results))
        for _ in range(3)
    ]
    for proc in procs:
        proc.start()
    resolved = [results.get(timeout=30) for _ in procs]
    for proc in procs:
        proc.join(timeout=30)

    assert all(proc.exitcode == 0 for proc in procs), "子进程异常退出"
    assert resolved == [expected] * len(procs)

    # 未配置时所有进程仍会落到同一个 primary lock directory。
    primary = tmp_path / "primary" / "users.json"
    monkeypatch.delenv("DEEPTUTOR_EXTERNAL_AUTH_USERS_FILE", raising=False)
    monkeypatch.setattr(external_auth, "_PRIMARY_USERS_FILE", primary)
    monkeypatch.setattr(
        external_auth, "_allow_legacy_external_auth_default", lambda: False
    )
    fallback = external_auth._store_lock_path()
    assert fallback.parent == primary.parent


def test_threads_do_not_lose_updates(store):
    """同进程多线程:threading.Lock 那一层。"""
    n_threads, per_thread = 8, 25
    lock_env = str(store)
    threads = [
        threading.Thread(target=_worker, args=(lock_env, str(store), f"t{i}", per_thread))
        for i in range(n_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    payload = json.loads(store.read_text(encoding="utf-8"))
    assert len(payload) == n_threads * per_thread, "多线程 RMW 丢更新"


@pytest.mark.skipif(external_auth.fcntl is None, reason="平台无 fcntl,跨进程互斥不适用")
def test_processes_do_not_lose_updates(store):
    """跨进程:flock 那一层 —— 这条是本次修复的实质。

    修复前(裸 threading.Lock)此测试必然失败:子进程各有各的 Lock 对象。
    """
    n_procs, per_proc = 4, 40
    lock_env = str(store)
    ctx = mp.get_context("spawn")  # 不继承父进程的锁状态,模拟真实 worker
    procs = [
        ctx.Process(target=_worker, args=(lock_env, str(store), f"p{i}", per_proc))
        for i in range(n_procs)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=120)

    assert all(p.exitcode == 0 for p in procs), "子进程异常退出"
    payload = json.loads(store.read_text(encoding="utf-8"))
    assert len(payload) == n_procs * per_proc, (
        f"跨进程 RMW 丢更新:期望 {n_procs * per_proc},实得 {len(payload)}"
    )


def test_no_nested_lock_acquisition():
    """非重入 flock 的前提:持锁函数不得在 with 块内调用另一个持锁函数。

    新增嵌套会在运行时死锁。这条钉子让它在 CI 里就暴露,而不是在生产挂死。
    """
    src = pathlib.Path(external_auth.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    holders = {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and "with _STORE_LOCK" in "\n".join(
            src.splitlines()[n.lineno - 1 : (n.end_lineno or n.lineno)]
        )
    }
    assert holders, "未找到任何持锁函数,判据失效"

    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in holders:
            continue
        ranges = [
            (w.lineno, w.end_lineno)
            for w in ast.walk(node)
            if isinstance(w, ast.With)
            and any(getattr(i.context_expr, "id", None) == "_STORE_LOCK" for i in w.items)
        ]
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            callee = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
            if callee in holders and callee != node.name:
                if any(lo <= call.lineno <= (hi or lo) for lo, hi in ranges):
                    violations.append(f"{node.name}():{call.lineno} → {callee}()")

    assert not violations, (
        "持锁函数在锁内嵌套调用另一个持锁函数,非重入 flock 会死锁:\n  "
        + "\n  ".join(violations)
    )
