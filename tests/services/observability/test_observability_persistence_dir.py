"""P0-b 持久化收口回归。

根因(dormant authority / provisioned-but-unbound durable root):observability 生产事实
落点(turn 观测事件 / 控制面 run / 失败轮事故)的 default 目录硬编码在每个模块的
``PROJECT_ROOT / "tmp" / ...``,绕过了 ``PathService`` 这个已存在的路径权威。``/app/tmp``
未挂载,每次部署 ``docker build / --force-recreate`` 即蒸发——control-plane shadow 7天窗、
readiness/ARR history 物理上永远累积不满。

治本:让这些 default 从单一权威 ``PathService.get_observability_dir()`` 派生,该方法挂在
已挂载的 ``data/runtime`` 下。env / 显式参数 override 优先级保持不变,仅 default 收口。
"""

from __future__ import annotations

import deeptutor.services.path_service as ps_mod
from deeptutor.services.path_service import get_path_service


def _patch_runtime(monkeypatch, tmp_path):
    """把 runtime 根指到 tmp，断言 default 经 get_observability_dir 派生而非 /app/tmp。"""
    fake_runtime = tmp_path / "data" / "runtime"
    monkeypatch.setattr(ps_mod.PathService, "get_runtime_dir", lambda self: fake_runtime)
    return fake_runtime


def test_observability_dir_is_under_runtime_not_tmp():
    obs = get_path_service().get_observability_dir()
    # 单一权威：observability 根 = runtime 根 / observability
    assert obs == get_path_service().get_runtime_dir() / "observability"
    # 生产事实落点必须在持久 data/runtime 下，绝不能是每次部署蒸发的 /app/tmp。
    # 用相对结构断言(父目录=runtime),不假设仓库绝对路径不含 "tmp"——
    # 否则 worktree 落在 /private/tmp/... 下会假阳性。
    assert obs.parts[-3:] == ("data", "runtime", "observability")
    assert obs.parent.name == "runtime"


def test_turn_event_log_default_routes_through_observability_dir(monkeypatch, tmp_path):
    fake_runtime = _patch_runtime(monkeypatch, tmp_path)
    monkeypatch.delenv("DEEPTUTOR_OBSERVER_EVENT_DIR", raising=False)
    from deeptutor.services.observability.turn_event_log import TurnEventLog

    log = TurnEventLog()
    assert log.events_dir == (fake_runtime / "observability" / "observer" / "events").resolve()


def test_control_plane_store_default_routes_through_observability_dir(monkeypatch, tmp_path):
    fake_runtime = _patch_runtime(monkeypatch, tmp_path)
    monkeypatch.delenv("DEEPTUTOR_OBSERVABILITY_STORE_DIR", raising=False)
    from deeptutor.services.observability.control_plane_store import ObservabilityControlPlaneStore

    store = ObservabilityControlPlaneStore()
    assert store.base_dir == (fake_runtime / "observability" / "control_plane").resolve()


def test_failed_turn_incident_default_routes_through_observability_dir(monkeypatch, tmp_path):
    fake_runtime = _patch_runtime(monkeypatch, tmp_path)
    from deeptutor.services.observability.failed_turn_promotion import write_failed_turn_incident_report

    out = write_failed_turn_incident_report({"incident_id": "x", "candidates": []})
    expected = (fake_runtime / "observability" / "failed_turn_incidents").resolve()
    assert str(expected) in out["json_path"]


def test_explicit_arg_and_env_override_still_win(monkeypatch, tmp_path):
    """default 收口不得破坏既有的显式参数 / env override 优先级。"""
    _patch_runtime(monkeypatch, tmp_path)
    from deeptutor.services.observability.turn_event_log import TurnEventLog

    explicit = tmp_path / "explicit_events"
    assert TurnEventLog(events_dir=explicit).events_dir == explicit.resolve()

    env_dir = tmp_path / "env_events"
    monkeypatch.setenv("DEEPTUTOR_OBSERVER_EVENT_DIR", str(env_dir))
    assert TurnEventLog().events_dir == env_dir.resolve()
