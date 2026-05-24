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
