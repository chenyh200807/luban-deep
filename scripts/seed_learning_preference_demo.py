"""学习模块偏好看板 demo 数据 seeder（学习模块偏好计划 §6-P4）。

用途：生产 product_behavior_events 当前为空（客户端埋点未随小程序发版），BI"学习模块偏好"
看板短期内无真实数据。本脚本用 **eval cohort 前缀账号**（qa_eval_/eval_）灌一批合成学习行为，
让 owner 现在就能在 BI 打开 /bi?tab=learning-pref&include_demo=1 看到驾驶舱成品形态。

红线（专家 D）：
- 所有 demo 事件 user_id 带 `eval_demo_` 前缀 → 看板默认口径(include_demo=false)按前缀排除，
  绝不污染生产真值；只有显式 include_demo=true 才显示。
- 事件 event_id 确定性 → 重复运行幂等（record_event 主键去重），不会累积翻倍。
- **禁止对生产 DB 运行**；只对本地/测试环境的 product_behavior.db。阿里云测试环境写入受
  AGENTS Aliyun Write Boundary 约束，须 owner 授权后在 /root/deeptutor 内执行。

运行：
    python -m scripts.seed_learning_preference_demo               # 写默认 store db
    python -m scripts.seed_learning_preference_demo --db-path /path/to/product_behavior.db
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from deeptutor.services.observability.product_behavior_store import SQLiteProductBehaviorStore

_DEMO_PREFIX = "eval_demo_"  # 命中 BI 默认排除前缀 eval_，天然隔离
_DAY_MS = 86_400_000

# (teaching_point_id, 中文标签仅注释, 触达人数, 人均复看次数) —— 造出"触达×深度错位"的题眼形态：
# 高触达低复看=泡沫；低触达高复看=被埋没金矿。
_MICROLESSONS = [
    ("F16:cashflow:1", "现金流量表微课", 8, 1),   # 高触达低深度（首页推荐位泡沫）
    ("N01:merge:1", "合并报表微课", 3, 4),          # 低触达高复看（被埋没金矿）
    ("J01:longterm:1", "长投微课", 5, 2),
    ("A01:tax:1", "税会差异微课", 6, 1),
    ("G01:revenue:1", "收入确认微课", 2, 3),
]
_CONCEPT_CARDS = [
    ("card-cashflow-01", 6, 2),
    ("card-merge-03", 2, 5),   # 反复翻（真被需要）
    ("card-tax-02", 4, 1),
]
# (pack, 答题数, 正确数) —— 练习量 + 正确率，含一个正确率地板 pack
_PRACTICE = [
    ("N01", 40, 30),
    ("F16", 32, 20),
    ("J01", 24, 12),  # 55% 地板
]


def _mk(store: SQLiteProductBehaviorStore, now_ms: int, seq: list[int], **props) -> None:
    """按 properties 造一条事件（record_event 从 properties_json 读维度字段）。"""
    seq[0] += 1
    event_id = f"demo-lp-{seq[0]:05d}"
    day_back = seq[0] % 7
    store.record_event(
        {
            "event_id": event_id,
            "event_name": props.pop("event_name"),
            "event_version": 1,
            "occurred_at_ms": now_ms - day_back * _DAY_MS,
            "received_at_ms": now_ms - day_back * _DAY_MS + 10,
            "user_id": props.pop("user_id"),
            "visit_id": props.pop("visit_id"),
            "session_id": "",
            "turn_id": "",
            "surface": "wechat_yousenwebview",
            "module": props.pop("module"),
            "section": props.pop("section", ""),
            "action": props.pop("action"),
            "properties_json": props,
        }
    )


def seed(db_path: Path) -> dict[str, int]:
    store = SQLiteProductBehaviorStore(db_path)
    now_ms = int(time.time() * 1000)
    seq = [0]

    # 微课内容偏好 + 站停留时长
    for tp_id, _label, reach, repeat in _MICROLESSONS:
        for u in range(reach):
            user = f"{_DEMO_PREFIX}u{u:02d}"
            for r in range(repeat):
                visit = f"{user}-v{r}"
                _mk(store, now_ms, seq, event_name="learning_action_started", module="learning",
                    action="open_detail", object_type="microlesson", object_id=tp_id, user_id=user, visit_id=visit)
                # 进站曝光（station-enter，object_type=station，对齐 producer onLoad）
                _mk(store, now_ms, seq, event_name="module_viewed", module="learning",
                    action="view", object_type="station", object_id=tp_id.split(":")[0], user_id=user, visit_id=visit)
                # 停留时长（观看时长信号，代替完播率）：exit 打微课对象，忠实于修正后的
                # station producer(onHide/onUnload 传 objectType=microlesson)，否则 demo 有停留
                # 而生产恒 0 = 假绿。
                _mk(store, now_ms, seq, event_name="module_exited", module="learning", action="return",
                    object_type="microlesson", object_id=tp_id, user_id=user, visit_id=visit,
                    visible_ms=45_000 + r * 12_000)

    # 考点卡复看
    for card_id, reach, repeat in _CONCEPT_CARDS:
        for u in range(reach):
            user = f"{_DEMO_PREFIX}u{u:02d}"
            for r in range(repeat):
                _mk(store, now_ms, seq, event_name="learning_action_started", module="learning",
                    action="open_detail", object_type="concept_card", object_id=card_id,
                    user_id=user, visit_id=f"{user}-cv{r}")

    # 功能偏好（驾驶舱功能卡点击）——真实的功能启动动作，不含 view/return 生命周期动作
    for action in ("start_training", "start_retest", "start_review", "open_detail"):
        for u in range(4):
            user = f"{_DEMO_PREFIX}u{u:02d}"
            _mk(store, now_ms, seq, event_name="learning_action_started", module="learning",
                action=action, object_type="feature", object_id=f"feature-{action}",
                user_id=user, visit_id=f"{user}-fv")

    # 练习量 + 正确率
    for pack, answered, correct in _PRACTICE:
        for i in range(answered):
            user = f"{_DEMO_PREFIX}u{i % 6:02d}"
            _mk(store, now_ms, seq, event_name="retest_item_answered", module="practice", action="complete",
                object_type="variant", object_id=f"{pack}-var-{i}", result="correct" if i < correct else "incorrect",
                practice_mode="review", user_id=user, visit_id=f"{user}-pv{pack}")

    return {"events_written": seq[0]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed learning-preference BI demo data (eval cohort only)")
    parser.add_argument("--db-path", default="", help="product_behavior.db path; default=session store sibling")
    args = parser.parse_args()

    if args.db_path:
        db_path = Path(args.db_path)
    else:
        from deeptutor.services.session.sqlite_store import get_sqlite_session_store

        db_path = Path(get_sqlite_session_store().db_path).with_name("product_behavior.db")

    print(f"[seed] target db: {db_path}")
    result = seed(db_path)
    print(f"[seed] done: {result['events_written']} demo events (user_id prefix '{_DEMO_PREFIX}').")
    print("[seed] 看板默认口径已按 eval 前缀排除；需在 BI 加 include_demo=1 才显示这批合成数据。")


if __name__ == "__main__":
    main()
