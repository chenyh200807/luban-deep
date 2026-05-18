from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.invite_test_applications import (
    InviteTestApplicationStore,
    normalize_invite_test_application,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")


def test_normalize_invite_test_application_masks_contact_by_default() -> None:
    row = {
        "id": "app-1",
        "createdAt": "2026-05-17T11:29:29.524Z",
        "name": "测试学员",
        "phone": "13800138000",
        "email": "qa@example.com",
        "wechatId": "wx_luban",
        "examType": "二建建筑实务",
        "examStage": "正在冲刺刷题",
        "painPoint": "错题原因不清楚",
        "weeklyTime": "10-30 分钟",
        "consent": True,
    }

    masked = normalize_invite_test_application(row)
    revealed = normalize_invite_test_application(row, reveal_contact=True)

    assert masked["phone"] == "138****8000"
    assert masked["email"] == "q*@example.com"
    assert masked["wechat_id"] == "w***n"
    assert masked["contact_revealed"] is False
    assert revealed["phone"] == "13800138000"
    assert revealed["email"] == "qa@example.com"
    assert revealed["wechat_id"] == "wx_luban"
    assert revealed["contact_revealed"] is True


@pytest.mark.asyncio
async def test_invite_test_store_reads_local_jsonl_and_builds_stats(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "invite-test-applications.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            {
                "id": "app-1",
                "createdAt": "2026-05-17T11:29:29.524Z",
                "sourcePage": "invite-test",
                "name": "张同学",
                "phone": "13800138000",
                "email": "a@example.com",
                "examType": "二建建筑实务",
                "examStage": "正在冲刺刷题",
                "painPoint": "错题原因不清楚",
                "weeklyTime": "10-30 分钟",
                "latestWrongQuestion": "案例题漏采分点",
                "acceptInterview": True,
                "consent": True,
                "status": "submitted",
            },
            {
                "id": "app-2",
                "createdAt": "2026-05-16T10:00:00.000Z",
                "sourcePage": "intro",
                "name": "李同学",
                "phone": "13900139000",
                "email": "b@example.com",
                "examType": "一建建筑实务",
                "examStage": "刚开始备考",
                "painPoint": "案例题不会写",
                "weeklyTime": "30-60 分钟",
                "acceptInterview": False,
                "consent": True,
                "status": "submitted",
            },
        ],
    )
    store = InviteTestApplicationStore(jsonl_path=str(jsonl_path))

    listing = await store.list_applications(days=30, q="张同学", reveal_contact=True)
    stats = await store.get_stats(days=30)

    assert listing["storage_status"] == "jsonl_fallback"
    assert listing["total"] == 1
    assert listing["items"][0]["phone"] == "13800138000"
    assert stats["summary"]["total_applications"] == 2
    assert stats["summary"]["unique_contacts"] == 2
    assert stats["summary"]["accept_interview_count"] == 1
    assert stats["summary"]["with_wrong_question_count"] == 1
    assert {"exam_type": "二建建筑实务", "count": 1} in stats["exam_type_breakdown"]


@pytest.mark.asyncio
async def test_invite_test_store_falls_back_to_database_when_supabase_rest_fails() -> None:
    class _Store(InviteTestApplicationStore):
        async def _load_supabase_rows(self, *, days: int):
            raise RuntimeError("postgrest unavailable")

        async def _load_database_rows(self, *, days: int):
            assert days == 30
            return [
                {
                    "id": "db-app-1",
                    "created_at": "2026-05-17T11:29:29.524Z",
                    "name": "数据库学员",
                    "phone": "13800138000",
                    "email": "db@example.com",
                    "exam_type": "二建建筑实务",
                    "exam_stage": "正在冲刺刷题",
                    "pain_point": "错题原因不清楚",
                    "weekly_time": "10-30 分钟",
                    "accept_interview": True,
                    "consent": True,
                    "status": "submitted",
                }
            ]

    store = _Store(
        base_url="https://example.supabase.co",
        service_key="service-role",
        database_url="postgresql://postgres:postgres@localhost:5432/postgres",
    )

    listing = await store.list_applications(days=30, reveal_contact=True)

    assert listing["storage_status"] == "database_fallback"
    assert listing["total"] == 1
    assert listing["items"][0]["name"] == "数据库学员"
    assert listing["items"][0]["phone"] == "13800138000"
