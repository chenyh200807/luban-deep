from __future__ import annotations

from pathlib import Path

from deeptutor.services.path_service import PathService
from scripts import run_learning_report_read_model_e2e as e2e


def test_e2e_script_bootstraps_repo_root_before_deeptutor_imports() -> None:
    source = Path("scripts/run_learning_report_read_model_e2e.py").read_text(encoding="utf-8")

    assert "sys.path.insert(0, str(PROJECT_ROOT))" in source


def test_e2e_grading_writer_uses_requested_user_data_dir_after_stale_path_service(
    monkeypatch,
    tmp_path,
) -> None:
    stale_root = tmp_path / "stale-user-data"
    target_root = tmp_path / "target-user-data"
    monkeypatch.setenv("DEEPTUTOR_USER_DATA_DIR", str(stale_root))
    PathService.reset_instance()
    PathService.get_instance()

    e2e._prepare_local_user_data_dir(str(target_root))
    written = e2e._write_grading_attempt(
        user_id="student_demo",
        run_id="pytest",
        attempt_index=1,
        user_answer="只写了加强现场管理。",
        score_awarded=0,
    )

    assert written == 1
    assert (target_root / "learner_state" / "student_demo" / "MEMORY_EVENTS.jsonl").exists()
    assert not (stale_root / "learner_state" / "student_demo" / "MEMORY_EVENTS.jsonl").exists()


def test_e2e_local_api_context_starts_and_stops_server_when_unreachable(monkeypatch, tmp_path) -> None:
    calls = {"wait": 0, "terminate": 0}

    class _FakeProcess:
        pid = 12345
        returncode = None

        def poll(self):
            return None

        def terminate(self):
            calls["terminate"] += 1

        def wait(self, timeout=None):
            calls["wait"] += 1
            return 0

        def kill(self):
            raise AssertionError("server should terminate cleanly")

    def _fake_wait_for_api(base_url, *, timeout_s, poll_interval_s):
        calls["wait_for_api"] = (base_url, timeout_s, poll_interval_s)
        return True

    monkeypatch.setattr(e2e.subprocess, "Popen", lambda *_args, **_kwargs: _FakeProcess())
    monkeypatch.setattr(e2e, "_wait_for_api", _fake_wait_for_api)

    with e2e._local_api_server(
        base_url="http://127.0.0.1:8123",
        enabled=True,
        user_data_dir=str(tmp_path),
        startup_timeout_s=3.0,
        log_path=tmp_path / "api.log",
    ) as started:
        assert started is True

    assert calls["wait_for_api"] == ("http://127.0.0.1:8123", 3.0, 0.5)
    assert calls["terminate"] == 1
    assert calls["wait"] == 1
