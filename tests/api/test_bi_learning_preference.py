from __future__ import annotations

import asyncio
import time
from pathlib import Path

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


def test_learning_preference_endpoint_shapes_and_excludes_demo(tmp_path: Path) -> None:
    store = reset_product_behavior_store(tmp_path / "behavior.db")
    # 真实用户：微课 + 练习答题
    _seed(store, event_id="m1", user_id="u-real", object_type="microlesson", object_id="F16:tp1:1")
    _seed(store, event_id="m2", user_id="u-real", object_type="microlesson", object_id="F16:tp1:1", visit_id="v2")
    _seed(store, event_id="p1", user_id="u-real", object_type="variant", object_id="var-1",
          event_name="retest_item_answered", module="practice", action="complete", result="correct")
    _seed(store, event_id="p2", user_id="u-real", object_type="variant", object_id="var-2",
          event_name="retest_item_answered", module="practice", action="complete", result="incorrect")
    # demo/eval cohort：应被默认口径排除
    _seed(store, event_id="d1", user_id="eval_demo", object_type="microlesson", object_id="F16:tp1:1")

    prod = asyncio.run(bi.bi_learning_preference(days=7, include_demo=False, limit=12, _auth=None))
    assert prod["completion_source"] == "dwell"
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
    # 练习量 + 正确率
    assert prod["practice"]["answered_count"] == 2
    assert prod["practice"]["correct_count"] == 1
    assert prod["practice"]["accuracy"] == 0.5

    demo_view = asyncio.run(bi.bi_learning_preference(days=7, include_demo=True, limit=12, _auth=None))
    assert demo_view["demo_included"] is True
    # 含 demo 后微课观看人数升到 2
    assert demo_view["content_top"][0]["member_count"] == 2


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
