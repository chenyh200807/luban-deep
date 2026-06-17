from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.invite_test_applications import (
    InviteTestApplicationStore,
    InviteTestApplicationValidationError,
    build_invite_test_application_record,
    normalize_invite_test_application,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")


@pytest.fixture(autouse=True)
def _clear_invite_test_storage_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_KEY",
        "INVITE_TEST_DATABASE_URL",
        "SUPABASE_DB_URL",
        "DB_URL",
        "INVITE_TEST_APPLICATIONS_PATH",
    ):
        monkeypatch.delenv(key, raising=False)


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
                "rawPayload": {
                    "province": "浙江",
                    "ageRange": "25-34",
                    "education": "本科",
                    "occupation": "施工员",
                    "preparationYears": "1 年",
                    "knowledgeFoundation": "基础薄弱",
                    "dailyStudyTime": "1 小时",
                },
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
                "rawPayload": {
                    "province": "江苏",
                    "ageRange": "35-44",
                    "education": "大专",
                    "occupation": "项目经理",
                    "preparationYears": "2 年",
                    "knowledgeFoundation": "有基础",
                    "dailyStudyTime": "30 分钟",
                },
            },
            {
                "id": "app-archived",
                "createdAt": "2026-05-15T10:00:00.000Z",
                "sourcePage": "invite-test",
                "name": "归档学员",
                "phone": "13700137000",
                "email": "archived@example.com",
                "examType": "一建建筑实务",
                "examStage": "刚开始备考",
                "painPoint": "知识点记不住",
                "weeklyTime": "30-60 分钟",
                "acceptInterview": True,
                "consent": True,
                "status": "archived",
                "rawPayload": {
                    "province": "北京",
                    "ageRange": "45+",
                    "education": "硕士",
                    "occupation": "工程总监",
                    "preparationYears": "3 年以上",
                    "knowledgeFoundation": "基础扎实",
                    "dailyStudyTime": "2 小时",
                },
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
    assert {"age_range": "25-34", "count": 1} in stats["age_range_breakdown"]
    assert {"province": "浙江", "count": 1} in stats["province_breakdown"]
    assert {"education": "本科", "count": 1} in stats["education_breakdown"]
    assert {"occupation": "施工员", "count": 1} in stats["occupation_breakdown"]
    assert {"preparation_years": "1 年", "count": 1} in stats["preparation_years_breakdown"]
    assert {"knowledge_foundation": "基础薄弱", "count": 1} in stats["knowledge_foundation_breakdown"]
    assert {"daily_study_time": "1 小时", "count": 1} in stats["daily_study_time_breakdown"]
    assert {"age_range": "45+", "count": 1} not in stats["age_range_breakdown"]


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


def test_build_invite_test_application_record_validates_public_payload() -> None:
    record = build_invite_test_application_record(
        {
            "name": "张同学",
            "phone": " 13800138000 ",
            "email": "QA@EXAMPLE.COM",
            "wechatId": "wx_luban",
            "examType": "二建建筑实务",
            "examStage": "正在冲刺刷题",
            "painPoint": "错题原因不清楚",
            "weeklyTime": "10-30 分钟",
            "province": "江苏",
            "ageRange": "26-35 岁",
            "education": "本科",
            "occupation": "施工员",
            "preparationYears": "第 2 次备考",
            "knowledgeFoundation": "基础薄弱",
            "dailyStudyTime": "30-60 分钟",
            "studyDifficulties": "工作忙，案例题不会组织语言。",
            "consent": True,
            "acceptInterview": True,
            "sourcePage": "invite-test",
        }
    )

    assert record["phone"] == "13800138000"
    assert record["email"] == "qa@example.com"
    assert record["wechat_id"] == "wx_luban"
    assert record["exam_type"] == "二建建筑实务"
    assert record["accept_interview"] is True
    assert record["status"] == "submitted"
    assert record["raw_payload"]["examType"] == "二建建筑实务"
    assert record["raw_payload"]["province"] == "江苏"
    assert record["raw_payload"]["ageRange"] == "26-35 岁"
    assert record["raw_payload"]["knowledgeFoundation"] == "基础薄弱"
    assert record["raw_payload"]["dailyStudyTime"] == "30-60 分钟"
    assert "province" not in record


def test_build_invite_test_application_record_rejects_missing_wechat_id() -> None:
    with pytest.raises(InviteTestApplicationValidationError, match="缺少必填字段：wechatId"):
        build_invite_test_application_record(
            {
                "name": "张同学",
                "phone": "13800138000",
                "email": "qa@example.com",
                "examType": "二建建筑实务",
                "examStage": "正在冲刺刷题",
                "painPoint": "错题原因不清楚",
                "weeklyTime": "10-30 分钟",
                "consent": True,
            }
        )


def test_build_invite_test_application_record_rejects_bad_phone() -> None:
    with pytest.raises(InviteTestApplicationValidationError, match="手机号格式不正确"):
        build_invite_test_application_record(
            {
                "name": "张同学",
                "phone": "123",
                "email": "qa@example.com",
                "wechatId": "wx_luban",
                "examType": "二建建筑实务",
                "examStage": "正在冲刺刷题",
                "painPoint": "错题原因不清楚",
                "weeklyTime": "10-30 分钟",
                "consent": True,
            }
        )


@pytest.mark.asyncio
async def test_invite_test_store_submits_to_jsonl_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    jsonl_path = tmp_path / "submitted.jsonl"
    store = InviteTestApplicationStore(jsonl_path=str(jsonl_path))

    result = await store.submit_application(
        {
            "name": "张同学",
            "phone": "13800138000",
            "email": "qa@example.com",
            "wechatId": "wx_luban",
            "examType": "二建建筑实务",
            "examStage": "正在冲刺刷题",
            "painPoint": "错题原因不清楚",
            "weeklyTime": "10-30 分钟",
            "consent": True,
            "sourcePage": "invite-test",
        }
    )

    assert result["ok"] is True
    assert result["storage_status"] == "jsonl_fallback"
    rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["phone"] == "13800138000"
    assert rows[0]["source_page"] == "invite-test"


@pytest.mark.asyncio
async def test_invite_test_store_prefers_supabase_write_when_supabase_and_db_are_both_configured() -> None:
    store = InviteTestApplicationStore(
        base_url="https://example.supabase.co",
        service_key="service-key",
        database_url="postgresql://user:pass@example.com:5432/app",
    )
    calls: list[str] = []

    async def _fake_save_supabase(record):
        calls.append(f"supabase:{record['phone']}")

    async def _fake_save_database(record):
        calls.append(f"database:{record['phone']}")

    store._save_supabase_record = _fake_save_supabase  # type: ignore[method-assign]
    store._save_database_record = _fake_save_database  # type: ignore[method-assign]

    result = await store.submit_application(
        {
            "name": "张同学",
            "phone": "13800138000",
            "email": "qa@example.com",
            "wechatId": "wx_luban",
            "examType": "二建建筑实务",
            "examStage": "正在冲刺刷题",
            "painPoint": "错题原因不清楚",
            "weeklyTime": "10-30 分钟",
            "consent": True,
        }
    )

    assert result["storage_status"] == "supabase"
    assert calls == ["supabase:13800138000"]


@pytest.mark.asyncio
async def test_invite_test_store_falls_back_to_database_when_supabase_write_fails() -> None:
    store = InviteTestApplicationStore(
        base_url="https://example.supabase.co",
        service_key="service-key",
        database_url="postgresql://user:pass@example.com:5432/app",
    )
    calls: list[str] = []

    async def _failing_save_supabase(record):
        calls.append(f"supabase:{record['phone']}")
        raise RuntimeError("supabase unavailable")

    async def _fake_save_database(record):
        calls.append(f"database:{record['phone']}")

    store._save_supabase_record = _failing_save_supabase  # type: ignore[method-assign]
    store._save_database_record = _fake_save_database  # type: ignore[method-assign]

    result = await store.submit_application(
        {
            "name": "张同学",
            "phone": "13800138000",
            "email": "qa@example.com",
            "wechatId": "wx_luban",
            "examType": "二建建筑实务",
            "examStage": "正在冲刺刷题",
            "painPoint": "错题原因不清楚",
            "weeklyTime": "10-30 分钟",
            "consent": True,
        }
    )

    assert result["storage_status"] == "supabase_error_database_fallback"
    assert calls == ["supabase:13800138000", "database:13800138000"]


@pytest.mark.asyncio
async def test_invite_test_store_falls_back_to_jsonl_when_remote_writes_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    jsonl_path = tmp_path / "submitted-fallback.jsonl"
    store = InviteTestApplicationStore(
        base_url="https://example.supabase.co",
        service_key="service-key",
        database_url="postgresql://user:pass@example.com:5432/app",
        jsonl_path=str(jsonl_path),
    )
    calls: list[str] = []

    async def _failing_save_supabase(record):
        calls.append(f"supabase:{record['phone']}")
        raise RuntimeError("supabase unavailable")

    async def _failing_save_database(record):
        calls.append(f"database:{record['phone']}")
        raise RuntimeError("database unavailable")

    store._save_supabase_record = _failing_save_supabase  # type: ignore[method-assign]
    store._save_database_record = _failing_save_database  # type: ignore[method-assign]

    result = await store.submit_application(
        {
            "name": "张同学",
            "phone": "13800138000",
            "email": "qa@example.com",
            "wechatId": "wx_luban",
            "examType": "二建建筑实务",
            "examStage": "正在冲刺刷题",
            "painPoint": "错题原因不清楚",
            "weeklyTime": "10-30 分钟",
            "consent": True,
            "sourcePage": "invite-test",
        }
    )

    assert result["storage_status"] == "supabase_database_error_jsonl_fallback"
    assert calls == ["supabase:13800138000", "database:13800138000"]
    rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["phone"] == "13800138000"


def test_normalize_invite_test_application_reads_profile_fields_from_raw_payload() -> None:
    row = {
        "id": "app-profile-1",
        "name": "画像学员",
        "phone": "13800138000",
        "email": "profile@example.com",
        "exam_type": "二建建筑实务",
        "exam_stage": "正在冲刺刷题",
        "pain_point": "案例题不会写",
        "weekly_time": "10-30 分钟",
        "raw_payload": {
            "province": "广东",
            "ageRange": "36-45 岁",
            "education": "大专",
            "occupation": "项目经理",
            "preparationYears": "第 3 次备考",
            "knowledgeFoundation": "一般",
            "dailyStudyTime": "1-2 小时",
            "studyDifficulties": "错题复盘坚持不下来。",
        },
    }

    normalized = normalize_invite_test_application(row, reveal_contact=True)

    assert normalized["province"] == "广东"
    assert normalized["age_range"] == "36-45 岁"
    assert normalized["education"] == "大专"
    assert normalized["occupation"] == "项目经理"
    assert normalized["preparation_years"] == "第 3 次备考"
    assert normalized["knowledge_foundation"] == "一般"
    assert normalized["daily_study_time"] == "1-2 小时"
    assert normalized["study_difficulties"] == "错题复盘坚持不下来。"


@pytest.mark.asyncio
async def test_invite_test_store_updates_local_jsonl_application(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPTUTOR_ENV", "local")
    jsonl_path = tmp_path / "invite-test-applications.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            {
                "id": "app-edit-1",
                "createdAt": "2026-05-17T11:29:29.524Z",
                "sourcePage": "invite-test",
                "name": "张同学",
                "phone": "13800138000",
                "email": "qa@example.com",
                "wechatId": "wx_old",
                "examType": "二建建筑实务",
                "examStage": "正在冲刺刷题",
                "painPoint": "错题原因不清楚",
                "weeklyTime": "10-30 分钟",
                "currentMethod": "自己刷题",
                "latestWrongQuestion": "案例题漏点",
                "acceptInterview": False,
                "consent": True,
                "status": "submitted",
                "operatorNote": "",
                "rawPayload": {"province": "广东", "studyDifficulties": "旧困难"},
            }
        ],
    )
    store = InviteTestApplicationStore(jsonl_path=str(jsonl_path))

    result = await store.update_application(
        "app-edit-1",
        {
            "status": "contacted",
            "operator_note": "已电话联系，愿意进入首批体验",
            "name": "张三同学",
            "phone": "13800138001",
            "wechat_id": "wx_new",
            "accept_interview": True,
            "study_difficulties": "案例题不会组织语言",
        },
    )

    assert result["storage_status"] == "jsonl_fallback"
    assert result["before"]["status"] == "submitted"
    assert result["after"]["status"] == "contacted"
    assert result["after"]["operator_note"] == "已电话联系，愿意进入首批体验"
    assert result["after"]["name"] == "张三同学"
    assert result["after"]["phone"] == "13800138001"
    assert result["after"]["wechat_id"] == "wx_new"
    assert result["after"]["accept_interview"] is True
    assert result["after"]["study_difficulties"] == "案例题不会组织语言"

    stored = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert stored[0]["status"] == "contacted"
    assert stored[0]["operator_note"] == "已电话联系，愿意进入首批体验"
    assert stored[0]["raw_payload"]["studyDifficulties"] == "案例题不会组织语言"


@pytest.mark.asyncio
async def test_invite_test_store_hides_archived_rows_by_default(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "invite-test-applications.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            {
                "id": "app-visible",
                "createdAt": "2026-05-17T11:29:29.524Z",
                "sourcePage": "invite-test",
                "name": "可见学员",
                "phone": "13800138000",
                "email": "visible@example.com",
                "wechatId": "wx_visible",
                "examType": "二建建筑实务",
                "examStage": "正在冲刺刷题",
                "painPoint": "错题原因不清楚",
                "weeklyTime": "10-30 分钟",
                "consent": True,
                "status": "submitted",
            },
            {
                "id": "app-archived",
                "createdAt": "2026-05-17T11:30:29.524Z",
                "sourcePage": "invite-test",
                "name": "已删学员",
                "phone": "13900139000",
                "email": "archived@example.com",
                "wechatId": "wx_archived",
                "examType": "一建建筑实务",
                "examStage": "刚开始学建筑实务",
                "painPoint": "案例题不会写",
                "weeklyTime": "10-30 分钟",
                "consent": True,
                "status": "archived",
            },
        ],
    )
    store = InviteTestApplicationStore(jsonl_path=str(jsonl_path))

    default_listing = await store.list_applications(days=30, reveal_contact=True)
    archived_listing = await store.list_applications(days=30, status="archived", reveal_contact=True)
    stats = await store.get_stats(days=30)

    assert [item["id"] for item in default_listing["items"]] == ["app-visible"]
    assert [item["id"] for item in archived_listing["items"]] == ["app-archived"]
    assert stats["summary"]["total_applications"] == 1
    assert stats["summary"]["unique_contacts"] == 1
