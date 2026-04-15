from __future__ import annotations

from pathlib import Path

from deeptutor.services.learning_plan import LearningPlanService


class _FakePathService:
    def __init__(self, root: Path) -> None:
        self._root = root

    def get_guide_dir(self) -> Path:
        path = self._root / "workspace" / "guide"
        path.mkdir(parents=True, exist_ok=True)
        return path


def test_learning_plan_service_creates_reads_and_rebuilds_view(tmp_path: Path) -> None:
    service = LearningPlanService(path_service=_FakePathService(tmp_path))

    created = service.create_plan(
        session_id="session_demo",
        user_id="student_demo",
        source_bot_id="bot_alpha",
        notebook_id="notebook_1",
        notebook_name="地基基础承载力",
        notebook_context="Notebook context",
        pages=[
            {
                "knowledge_title": "承载力判定",
                "knowledge_summary": "判断基底承载力的核心思路。",
                "user_difficulty": "medium",
                "html": "<h1>page-0</h1>",
                "page_status": "ready",
            },
            {
                "knowledge_title": "地基验算",
                "knowledge_summary": "验算步骤与常见错误。",
            },
        ],
        status="learning",
        current_index=0,
        summary="初步总结",
    )

    assert created["session_id"] == "session_demo"
    assert created["page_count"] == 2
    assert created["ready_count"] == 1
    assert created["progress"] == 50

    updated = service.update_plan("session_demo", current_index=1, summary="更新后的总结")
    assert updated is not None
    assert updated["current_index"] == 1
    assert updated["summary"] == "更新后的总结"

    page = service.upsert_page(
        "session_demo",
        1,
        knowledge_title="地基验算",
        knowledge_summary="验算步骤与常见错误。",
        user_difficulty="hard",
        html="<h1>page-1</h1>",
        page_status="ready",
        page_error="",
    )
    assert page["page_index"] == 1
    assert page["page_status"] == "ready"

    reloaded = service.read_plan("session_demo")
    assert reloaded is not None
    assert reloaded["page_count"] == 2
    assert reloaded["ready_count"] == 2
    assert reloaded["progress"] == 100

    view = service.read_guided_session_view("session_demo")
    assert view is not None
    assert view["session_id"] == "session_demo"
    assert view["notebook_name"] == "地基基础承载力"
    assert view["knowledge_points"][0]["knowledge_title"] == "承载力判定"
    assert view["html_pages"]["0"] == "<h1>page-0</h1>"
    assert view["page_statuses"]["1"] == "ready"
    assert view["page_errors"]["1"] == ""
    assert view["current_index"] == 1
    assert view["current_knowledge"]["knowledge_title"] == "地基验算"


def test_learning_plan_service_lists_and_deletes_plans(tmp_path: Path) -> None:
    service = LearningPlanService(path_service=_FakePathService(tmp_path))

    service.create_plan(session_id="session_a", notebook_name="A")
    service.create_plan(session_id="session_b", notebook_name="B", status="completed")

    plans = service.list_plans()
    assert [item["session_id"] for item in plans] == ["session_b", "session_a"]
    assert plans[0]["status"] == "completed"

    assert service.delete_plan("session_a") is True
    assert service.read_plan("session_a") is None
    assert service.read_guided_session_view("session_a") is None

    remaining = service.list_plans()
    assert [item["session_id"] for item in remaining] == ["session_b"]

