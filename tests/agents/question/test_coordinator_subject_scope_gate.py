"""出口科目门口径对称回归。

根因：出口门 `_generated_questions_in_construction_scope` 旧实现用正向白名单命中
（`any(== construction_topic)`）判 in-scope，导致建筑长尾考点（"水泥/沟槽开挖"——白名单
未覆盖 → unknown_topic）被误判 out-of-scope 拒答，重蹈入口门
`practice_generation_topic_block_decision` 已修正过的 `!= construction_topic` 误拒。

修法：出口门口径与入口门对称——只在生成题**确有他科证据（out_of_scope_topic）且无任何
建筑证据**时才判 out-of-scope；unknown_topic 一律放行。本测试双向锁定：建筑长尾放行 +
他科仍拒。
"""

from __future__ import annotations

import pytest

from deeptutor.agents.question.coordinator import AgentCoordinator


def _qa(concentration: str, question: str = "请作答。") -> dict:
    return {"qa_pair": {"concentration": concentration, "question": question}}


_gate = AgentCoordinator._generated_questions_in_construction_scope


# ---- 建筑长尾（白名单未覆盖 = unknown_topic）必须放行（回归本次 bug） ----
@pytest.mark.parametrize(
    "concentration",
    [
        "水泥强度等级",
        "水泥的凝结时间与安定性",
        "沟槽开挖的边坡稳定",
        "盘扣式脚手架搭设要求",
    ],
)
def test_construction_longtail_unknown_topic_is_in_scope(concentration: str) -> None:
    assert _gate([], [_qa(concentration)]) is True


# ---- 命中建筑白名单（construction_topic）当然放行 ----
@pytest.mark.parametrize("concentration", ["混凝土浇筑", "屋面防水构造", "变形缝设置"])
def test_construction_marker_is_in_scope(concentration: str) -> None:
    assert _gate([], [_qa(concentration)]) is True


# ---- 明确他科（命中 _OUT_OF_SCOPE 白名单 = out_of_scope_topic）且无建筑证据：
#      仍诚实拒答（防跑题保护不塌） ----
@pytest.mark.parametrize(
    "concentration",
    ["数学函数求导", "英语作文范文", "物理受力分析", "化学元素周期"],
)
def test_explicit_other_subject_is_out_of_scope(concentration: str) -> None:
    assert _gate([], [_qa(concentration)]) is False


# ---- 已知边界（诚实记录）：他科但 _OUT_OF_SCOPE 白名单未覆盖（如"法语"白名单只有
#      "英语"）→ unknown_topic → 新对称口径放行。这是选项 A 的明确 trade-off：出口门
#      拦截力 = _OUT_OF_SCOPE 白名单覆盖范围；入口门对同一输入同样放行（unknown），真正
#      的语义守门由主 LLM 的建筑 KB grounding 承担，不靠出口关键词门冒充语义判定。
#      补白名单是独立的打地鼠决策，不在本口径修复 scope。
def test_other_subject_outside_blocklist_falls_through_documented() -> None:
    assert _gate([], [_qa("法语动词变位")]) is True


# ---- 混合：至少一题建筑 → 放行；他科混进但有建筑证据不算跑偏 ----
def test_mixed_with_one_construction_is_in_scope() -> None:
    assert _gate([], [_qa("混凝土浇筑"), _qa("法语动词变位")]) is True


# ---- 混合：他科 + 建筑长尾(unknown)、无建筑白名单命中 → 有他科证据判拒 ----
def test_mixed_other_subject_and_unknown_without_construction_is_out_of_scope() -> None:
    assert _gate([], [_qa("水泥强度等级"), _qa("数学函数求导")]) is False


# ---- 无题面可判：不拦（避免空判误拒） ----
def test_no_candidates_is_in_scope() -> None:
    assert _gate([], []) is True
    assert _gate([], [_qa("", question="")]) is True
