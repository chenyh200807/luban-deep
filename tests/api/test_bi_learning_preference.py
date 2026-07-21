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
