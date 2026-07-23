from __future__ import annotations

import asyncio
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from deeptutor.services.observability import reset_product_behavior_store

bi = pytest.importorskip("deeptutor.api.routers.bi")


def _seed(store, *, event_id, user_id, object_type, object_id, event_name="learning_action_started",
          module="learning", action="open_detail", result="", visit_id="v1"):
    now_ms = int(time.time() * 1000)
    store.record_event(
        {
            "event_id": event_id,
            "event_name": event_name,
            "event_version": 1,
            "occurred_at_ms": now_ms,
            "received_at_ms": now_ms + 10,
            "user_id": user_id,
            "visit_id": visit_id,
            "surface": "wechat_yousenwebview",
            "module": module,
            "action": action,
            "properties_json": {"object_type": object_type, "object_id": object_id, "result": result},
        }
    )


def _seed_playback(
    store,
    *,
    event_id: str,
    sequence: int,
    section_index: int,
    action: str,
    active_ms: int,
    progress_pct: int,
    section_progress_pct: int,
) -> None:
    now_ms = int(time.time() * 1000)
    session_id = "bi-playback-session"
    object_id = "F16:lesson:2"
    section_id = f"section-{section_index}"
    section_start_ms = (section_index - 1) * 10_000
    section_end_ms = section_start_ms + 10_000
    store.record_event(
        {
            "event_id": event_id,
            "event_name": "microlesson_playback",
            "event_version": 1,
            "occurred_at_ms": now_ms + sequence,
            "received_at_ms": now_ms + sequence,
            "user_id": "u-real",
            "visit_id": session_id,
            "session_id": session_id,
            "surface": "wechat_yousenwebview",
            "module": "learning",
            "section": section_id,
            "action": action,
            "properties_json": {
                "visit_id": session_id,
                "module": "learning",
                "section": section_id,
                "action": action,
                "object_type": "microlesson",
                "object_id": object_id,
                "duration_ms": active_ms,
                "playback_session_id": session_id,
                "sequence": sequence,
                "progress_pct": progress_pct,
                "section_index": section_index,
                "section_label": f"第{section_index}节",
                "section_group": "讲解",
                "section_start_ms": section_start_ms,
                "section_end_ms": section_end_ms,
                "from_position_ms": section_start_ms,
                "to_position_ms": section_start_ms + active_ms,
                "section_progress_pct": section_progress_pct,
                "reason": "auto",
            },
        }
    )


def test_learning_preference_endpoint_shapes_and_excludes_demo(tmp_path: Path) -> None:
    store = reset_product_behavior_store(tmp_path / "behavior.db")
    # 真实用户：微课 + 练习答题
    _seed(store, event_id="m1", user_id="u-real", object_type="microlesson", object_id="F16:tp1:1")
    _seed(store, event_id="m2", user_id="u-real", object_type="microlesson", object_id="F16:tp1:1", visit_id="v2")
    _seed(store, event_id="p1", user_id="u-real", object_type="variant", object_id="var-1",
          event_name="retest_item_answered", module="practice", action="complete", result="correct")
    _seed(store, event_id="p2", user_id="u-real", object_type="variant", object_id="var-2",
          event_name="retest_item_answered", module="practice", action="complete", result="incorrect")
    # 模块触达只认真实 module_viewed，不把答题/退出等任意事件冒充页面触达。
    _seed(store, event_id="lv1", user_id="u-real", object_type="station", object_id="F16",
          event_name="module_viewed", module="learning", action="view")
    _seed(store, event_id="pv1", user_id="u-real", object_type="practice_home", object_id="practice",
          event_name="module_viewed", module="practice", action="view")
    # demo/eval cohort：应被默认口径排除
    _seed(store, event_id="d1", user_id="eval_demo", object_type="microlesson", object_id="F16:tp1:1")

    prod = asyncio.run(bi.bi_learning_preference(days=7, include_demo=False, limit=12, _auth=None))
    assert prod["completion_source"] == "page_dwell"
    assert prod["time_source"] == "page_dwell"
    assert prod["demo_included"] is False
    # 全模块偏好("产品功能偏好")：真实用户的 learning/practice 模块应出现
    demo_all = asyncio.run(bi.bi_learning_preference(days=7, include_demo=True, limit=12, _auth=None))
    module_keys = {r["key"] for r in demo_all["module_preference"]}
    assert {"learning", "practice"} <= module_keys
    assert "login" not in module_keys  # 鉴权噪音排除
    assert "by_topic" in demo_all["practice"]
    # 内容 Top 只含真实用户（demo 排除后 member_count=1）
    content = prod["content_top"]
    assert content and content[0]["key"] == "F16:tp1:1"
    assert content[0]["member_count"] == 1
    assert content[0]["display_label"].startswith("未识别微课")
    # 练习量 + 正确率
    assert prod["practice"]["answered_count"] == 2
    assert prod["practice"]["correct_count"] == 1
    assert prod["practice"]["accuracy"] == 0.5

    demo_view = asyncio.run(bi.bi_learning_preference(days=7, include_demo=True, limit=12, _auth=None))
    assert demo_view["demo_included"] is True
    # 含 demo 后微课观看人数升到 2
    assert demo_view["content_top"][0]["member_count"] == 2


def test_learning_preference_projects_explicit_playback_without_reinterpreting_page_dwell(
    tmp_path: Path,
) -> None:
    store = reset_product_behavior_store(tmp_path / "behavior.db")
    _seed_playback(
        store,
        event_id="playback-section-1",
        sequence=1,
        section_index=1,
        action="checkpoint",
        active_ms=10_000,
        progress_pct=45,
        section_progress_pct=100,
    )
    _seed_playback(
        store,
        event_id="playback-section-2",
        sequence=2,
        section_index=2,
        action="checkpoint",
        active_ms=10_000,
        progress_pct=100,
        section_progress_pct=100,
    )
    _seed_playback(
        store,
        event_id="playback-complete",
        sequence=3,
        section_index=2,
        action="complete",
        active_ms=0,
        progress_pct=100,
        section_progress_pct=100,
    )

    result = asyncio.run(
        bi.bi_learning_preference(
            days=7, include_demo=True, limit=12, _auth=None
        )
    )

    assert (
        result["completion_source"]
        == "mixed_explicit_playback_and_page_dwell"
    )
    assert result["time_source"] == "mixed"
    playback = result["playback"]
    assert playback["available"] is True
    assert playback["time_source"] == "player_active_time"
    assert playback["mastery_eligible"] is False
    assert playback["use_boundary"] == "product_interest_only"
    assert playback["event_count"] == 3
    assert playback["playback_session_count"] == 1
    assert playback["content"] == [
        {
            "object_id": "F16:lesson:2",
            "play_count": 0,
            "completed_sessions": 1,
            "total_active_ms": 20_000,
            "progress_25_sessions": 1,
            "progress_50_sessions": 1,
            "progress_75_sessions": 1,
            "progress_90_sessions": 1,
            "max_reached_section_index": 2,
            "max_contiguous_watched_section_index": 2,
            "last_event_at_ms": playback["content"][0][
                "last_event_at_ms"
            ],
            "member_count": 1,
            "playback_session_count": 1,
            "completion_rate": 1.0,
            "avg_active_ms": 20_000,
        }
    ]
    assert [
        (
            row["section_index"],
            row["reached_session_count"],
            row["watched_sessions"],
            row["watched_rate"],
        )
        for row in playback["sections"]
    ] == [(1, 1, 1, 1.0), (2, 1, 1, 1.0)]


def test_learning_preference_excludes_exact_uuid_machine_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = reset_product_behavior_store(tmp_path / "behavior.db")
    machine_uuid = "0f6d0f92-46bf-4e36-a16a-e23d4ef813c4"
    _seed(store, event_id="real", user_id="u-real", object_type="microlesson", object_id="real-card")
    _seed(store, event_id="machine", user_id=machine_uuid, object_type="microlesson", object_id="machine-card")
    monkeypatch.setattr(
        bi,
        "get_bi_service",
        lambda: SimpleNamespace(get_non_business_identity_ids=lambda: frozenset({machine_uuid})),
    )

    result = asyncio.run(
        bi.bi_learning_preference(days=7, include_demo=False, limit=12, _auth=None)
    )

    assert {row["key"] for row in result["content_top"]} == {"real-card"}


def test_submodule_interest_excludes_non_learning_object_types(tmp_path: Path) -> None:
    """审查 SEV-2 #1 回归：submodule_interest 必须只含学习模块 object_type，
    不能把 login(password/phone_auth)/chat(first_answer) 等全产品对象聚进来。"""
    store = reset_product_behavior_store(tmp_path / "behavior.db")
    # 学习子模块对象
    _seed(store, event_id="s1", user_id="u1", object_type="station", object_id="F16", module="learning")
    _seed(store, event_id="mc1", user_id="u1", object_type="microlesson", object_id="F16:tp:1", module="learning")
    # 非学习对象（登录/聊天）——每个用户都会产生，member_count 天然更高
    _seed(store, event_id="lg1", user_id="u1", object_type="password", object_id="pw", module="login", action="complete")
    _seed(store, event_id="lg2", user_id="u2", object_type="password", object_id="pw", module="login", action="complete")
    _seed(store, event_id="ct1", user_id="u2", object_type="first_answer", object_id="turn-1", module="chat", action="render")

    result = asyncio.run(bi.bi_learning_preference(days=7, include_demo=True, limit=12, _auth=None))
    keys = {row["key"] for row in result["submodule_interest"]}
    assert "password" not in keys and "first_answer" not in keys
    assert keys <= {"station", "microlesson", "concept_card", "seethrough_day", "variant", "retest", "full_answer"}
    assert {"station", "microlesson"} <= keys


def test_content_dwell_attributes_to_microlesson_from_module_exited(tmp_path: Path) -> None:
    """审查 SEV-2 #2 回归：module_exited 打上微课对象后，微课行的 avg_dwell_ms 非 0。"""
    store = reset_product_behavior_store(tmp_path / "behavior.db")
    _seed(store, event_id="open1", user_id="u1", object_type="microlesson", object_id="F16:tp:1", module="learning")
    # 修正后的 producer：离站 module_exited 带微课对象 + visible_ms（停留时长）
    _seed(store, event_id="exit1", user_id="u1", object_type="microlesson", object_id="F16:tp:1",
          event_name="module_exited", module="learning", action="return", result="")
    store.record_event(
        {
            "event_id": "exit-dwell", "event_name": "module_exited", "event_version": 1,
            "occurred_at_ms": int(time.time() * 1000), "received_at_ms": int(time.time() * 1000),
            "user_id": "u1", "visit_id": "v1", "surface": "wechat_yousenwebview",
            "module": "learning", "action": "return",
            "properties_json": {"object_type": "microlesson", "object_id": "F16:tp:1", "visible_ms": 60000},
        }
    )
    result = asyncio.run(bi.bi_learning_preference(days=7, include_demo=True, limit=12, _auth=None))
    micro = [r for r in result["content_top"] if r["key"] == "F16:tp:1"]
    assert micro and micro[0]["avg_dwell_ms"] == 60000
    assert micro[0]["total_dwell_ms"] == 60000
    assert micro[0]["dwell_event_count"] == 1
    assert micro[0]["display_label"] == "微课｜屋面防水起鼓割补 · 完整讲解"


def test_member_engagement_endpoint_scopes_to_one_user(tmp_path: Path) -> None:
    """单会员点击详情端点：只反映该用户自己的行为，不混入其他会员。"""
    store = reset_product_behavior_store(tmp_path / "behavior.db")
    _seed(store, event_id="ua1", user_id="u-a", object_type="microlesson", object_id="F16:tp:1", module="learning")
    _seed(store, event_id="ua2", user_id="u-a", object_type="station", object_id="F16", module="learning")
    _seed(store, event_id="ua3", user_id="u-a", object_type="variant", object_id="var-1",
          event_name="retest_item_answered", module="practice", action="complete", result="correct")
    _seed(store, event_id="ub1", user_id="u-b", object_type="microlesson", object_id="F16:tp:1", module="learning")

    result = asyncio.run(bi.bi_member_engagement(user_id="u-a", days=30, _auth=None))
    assert result["user_id"] == "u-a"
    module_keys = {r["key"]: r["event_count"] for r in result["module_breakdown"]}
    assert module_keys == {"learning": 2, "practice": 1}
    content_keys = {r["key"] for r in result["content_breakdown"]}
    assert content_keys == {"F16:tp:1", "F16", "var-1"}
    # u-b 的事件不应污染 u-a 的明细
    for row in result["content_breakdown"]:
        assert row["member_count"] == 1
        assert row["display_label"]
        assert row["display_context"].startswith("微信小程序")


def test_member_engagement_returns_every_content_row_without_top_100_truncation(tmp_path: Path) -> None:
    store = reset_product_behavior_store(tmp_path / "behavior.db")
    for index in range(105):
        _seed(
            store,
            event_id=f"content-{index}",
            user_id="u-many",
            object_type="concept_card",
            object_id=f"card-{index}",
            visit_id=f"visit-{index}",
        )

    result = asyncio.run(bi.bi_member_engagement(user_id="u-many", days=30, _auth=None))

    assert len(result["content_breakdown"]) == 105
