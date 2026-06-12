"""LearningBrainDreamCycle 契约（gbrain 式夜间巩固）。

- 不是第二权威：合成只经 service.synthesize_learning_truth（单一入口），
  写入门控（G4 cohort）在 service / canonical_truth_policy 内生效；
  dream cycle 只决定"何时跑、跑哪些用户、汇报结果"。
- 默认关（env flag fail-closed）；生产环境候选用户受 G4 cohort 限定；
  单用户失败隔离，不拖垮整轮。
"""

from __future__ import annotations

from typing import Any

import pytest

import deeptutor.services.learner_state.dream_cycle as dream_cycle_module
from deeptutor.services.learner_state.dream_cycle import (
    DREAM_CYCLE_ENABLED_FLAG,
    LearningBrainDreamCycle,
)


class _FakeService:
    def __init__(self, user_ids: list[str], *, fail_users: set[str] | None = None) -> None:
        self._user_ids = list(user_ids)
        self._fail_users = set(fail_users or set())
        self.synthesize_calls: list[dict[str, Any]] = []

    def list_local_memory_event_user_ids(self) -> list[str]:
        return list(self._user_ids)

    def synthesize_learning_truth(self, user_id: str, *, dry_run: bool = True, event_limit: int | None = None):
        self.synthesize_calls.append({"user_id": user_id, "dry_run": dry_run, "event_limit": event_limit})
        if user_id in self._fail_users:
            raise RuntimeError("synthesis boom")
        return {
            "projection": {"weak_points": []},
            "summary_md": "## ok",
            "outbox_item": None,
            "canonical_truth_promotion": {"allowed": True, "reason": "non_production"},
        }


def test_disabled_flag_means_no_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DREAM_CYCLE_ENABLED_FLAG, raising=False)
    service = _FakeService(["stu_1"])
    cycle = LearningBrainDreamCycle(service)

    report = cycle.run_once(now=1000.0)

    assert report["ran"] is False
    assert report["reason"] == "disabled"
    assert service.synthesize_calls == []


def test_run_once_consolidates_full_history_for_each_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DREAM_CYCLE_ENABLED_FLAG, "true")
    service = _FakeService(["stu_1", "stu_2"])
    cycle = LearningBrainDreamCycle(service)

    report = cycle.run_once(now=1000.0)

    assert report["ran"] is True
    assert report["user_count"] == 2
    assert [c["user_id"] for c in service.synthesize_calls] == ["stu_1", "stu_2"]
    # 全量历史：dry_run=False 且不加 event_limit 窗口
    assert all(c["dry_run"] is False for c in service.synthesize_calls)
    assert all(c["event_limit"] is None for c in service.synthesize_calls)
    assert [item["user_id"] for item in report["consolidated"]] == ["stu_1", "stu_2"]


def test_interval_gate_and_force(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DREAM_CYCLE_ENABLED_FLAG, "true")
    service = _FakeService(["stu_1"])
    cycle = LearningBrainDreamCycle(service)

    first = cycle.run_once(now=1000.0)
    assert first["ran"] is True

    second = cycle.run_once(now=1000.0 + 60.0)
    assert second["ran"] is False
    assert second["reason"] == "not_due"
    assert len(service.synthesize_calls) == 1

    forced = cycle.run_once(now=1000.0 + 60.0, force=True)
    assert forced["ran"] is True
    assert len(service.synthesize_calls) == 2

    due_later = cycle.run_once(now=1000.0 + cycle.interval_seconds() + 61.0)
    assert due_later["ran"] is True


def test_production_limits_users_to_canonical_cohort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DREAM_CYCLE_ENABLED_FLAG, "true")
    monkeypatch.setattr(dream_cycle_module, "is_production_environment", lambda: True)
    monkeypatch.setattr(
        dream_cycle_module,
        "canonical_truth_production_write_cohort_allowed",
        lambda user_id: str(user_id).startswith("qa_"),
    )
    service = _FakeService(["qa_alpha", "stu_beta"])
    cycle = LearningBrainDreamCycle(service)

    report = cycle.run_once(now=1000.0)

    assert [c["user_id"] for c in service.synthesize_calls] == ["qa_alpha"]
    assert report["skipped"] == [
        {"user_id": "stu_beta", "reason": "production_cohort_required"}
    ]


def test_single_user_failure_is_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DREAM_CYCLE_ENABLED_FLAG, "true")
    service = _FakeService(["stu_1", "stu_2", "stu_3"], fail_users={"stu_2"})
    cycle = LearningBrainDreamCycle(service)

    report = cycle.run_once(now=1000.0)

    assert report["ran"] is True
    assert [item["user_id"] for item in report["consolidated"]] == ["stu_1", "stu_3"]
    assert len(report["errors"]) == 1
    assert report["errors"][0]["user_id"] == "stu_2"


def test_empty_user_list_is_a_clean_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DREAM_CYCLE_ENABLED_FLAG, "true")
    service = _FakeService([])
    cycle = LearningBrainDreamCycle(service)

    report = cycle.run_once(now=1000.0)

    assert report["ran"] is True
    assert report["user_count"] == 0
    assert report["consolidated"] == []
    assert report["errors"] == []


# ---------------------------------------------------------------- 文件级 watermark 锁（多 worker 单执行）

import fcntl
import os
from pathlib import Path

from deeptutor.services.learner_state.worker_file_lock import try_exclusive_file_lock


def test_watermark_persists_across_instances_and_restarts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """同一 state_dir 的两个实例（≈两个 worker / 一次重启）共享 watermark：
    第一个跑完后，第二个在 interval 内不再重跑。"""
    monkeypatch.setenv(DREAM_CYCLE_ENABLED_FLAG, "true")
    service = _FakeService(["stu_1"])

    first = LearningBrainDreamCycle(service, state_dir=tmp_path)
    assert first.run_once(now=1000.0)["ran"] is True
    assert (tmp_path / ".dream_cycle_last_run").exists()

    second = LearningBrainDreamCycle(service, state_dir=tmp_path)
    report = second.run_once(now=1000.0 + 60.0)
    assert report["ran"] is False
    assert report["reason"] == "not_due"
    assert len(service.synthesize_calls) == 1

    third = LearningBrainDreamCycle(service, state_dir=tmp_path)
    assert third.run_once(now=1000.0 + third.interval_seconds() + 1.0)["ran"] is True


def test_lock_held_by_peer_means_skip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(DREAM_CYCLE_ENABLED_FLAG, "true")
    service = _FakeService(["stu_1"])
    cycle = LearningBrainDreamCycle(service, state_dir=tmp_path)

    lock_path = tmp_path / ".dream_cycle.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        report = cycle.run_once(now=1000.0, force=True)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    assert report["ran"] is False
    assert report["reason"] == "lock_held"
    assert service.synthesize_calls == []

    report = cycle.run_once(now=1000.0, force=True)
    assert report["ran"] is True


def test_try_exclusive_file_lock_contract(tmp_path: Path) -> None:
    lock_path = tmp_path / "x.lock"
    with try_exclusive_file_lock(lock_path) as got:
        assert got is True
        with try_exclusive_file_lock(lock_path) as got_again:
            # 同进程二次 open+flock 同样被拒（非重入），等价于他进程持有
            assert got_again is False
    with try_exclusive_file_lock(lock_path) as got_after_release:
        assert got_after_release is True
