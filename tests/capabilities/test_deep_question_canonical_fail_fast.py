"""Control-plane 治本 Action 2 — deep_question 退役 canonical-missing fabrication 兜底.

取证(Langfuse 537 个 deep_question turn / 4.3 天)证明 canonical decision 总在场
(control_plane_shadow_hits 全 0)。该套 fabrication 兜底是 deep_question 自带的第二
权威(turn.md §硬约束 24:canonical 唯一签发是 orchestrator semantic_router)。

本套测试钉死退役后的不变量:
  * canonical 在场 → deep_question 正常只读它,不 fabricate 第二份。
  * canonical 缺失 → 生成/复习 结果装配处 LOUD fail-fast(raise),不静默伪造第二权威。
  * paste(c)/legacy-followup(d)/S5/S6 安全带不破。
"""

from __future__ import annotations

from typing import Any

import pytest

from deeptutor.capabilities.deep_question import DeepQuestionCapability


def _canonical_decision() -> dict[str, Any]:
    return {
        "relation_to_active_object": "continue_same_learning_flow",
        "next_action": "route_to_generation",
        "allowed_patch": "set_active_object",
        "confidence": 1.0,
        "reason": "orchestrator canonical",
    }


def test_require_canonical_returns_decision_when_present() -> None:
    """canonical 在场 → helper 只读返回它(normalize 后),绝不 fabricate 第二份。"""
    require = DeepQuestionCapability._require_canonical_turn_semantic_decision
    decision = _canonical_decision()
    out = require(decision, site="practice_generation_result", metadata={})
    # 决策权威字段原样保留(normalize 仅规整 allowed_patch 形态/补 target_object_ref,
    # 不改写 relation/next_action/reason)。
    assert out["relation_to_active_object"] == decision["relation_to_active_object"]
    assert out["next_action"] == decision["next_action"]
    assert out["reason"] == decision["reason"]
    # allowed_patch 被 normalize 成 list,但语义保留。
    patch = out["allowed_patch"]
    assert "set_active_object" in (patch if isinstance(patch, list) else [patch])


@pytest.mark.parametrize("missing", [None, {}, {"next_action": ""}])
def test_require_canonical_fail_fast_when_missing(missing: Any) -> None:
    """canonical 缺失 → LOUD fail-fast(raise),不静默 fabricate 第二权威。

    取证(0/537)+ orchestrator preselect 注入(动作2 Step2)保证这条 raise 是
    never-firing 安全网;真触发说明上游有未注入 canonical 的入口泄漏,必须报警而
    不是悄悄伪造一份替代 authority。
    """
    require = DeepQuestionCapability._require_canonical_turn_semantic_decision
    with pytest.raises(RuntimeError) as exc:
        require(missing, site="practice_generation_result", metadata={})
    # 报警信息带 site,便于定位泄漏入口(loud,非静默)。
    assert "practice_generation_result" in str(exc.value)
    assert "canonical" in str(exc.value).lower()


def test_require_canonical_records_shadow_hit_on_fail_fast() -> None:
    """fail-fast 同时落 control_plane_shadow_hits(canonical_present=False),让
    既有 7 天观测窗口仍能归因到 site,即使 raise 后 turn 走 error 边界。"""
    require = DeepQuestionCapability._require_canonical_turn_semantic_decision
    metadata: dict[str, Any] = {}
    with pytest.raises(RuntimeError):
        require({}, site="practice_generation_result", metadata=metadata)
    hits = metadata.get("trace_metadata", {}).get("control_plane_shadow_hits", [])
    fail_hits = [h for h in hits if h.get("site") == "practice_generation_result"]
    assert len(fail_hits) == 1, hits
    hit = fail_hits[0]
    assert hit["fact"] == "turn_semantic_decision"
    assert hit["canonical_present"] is False
    # writer_role 区别于 compat_projection / unconditional_fabricate:这是 fail-fast,
    # 不再伪造,只报警。
    assert hit["writer_role"] == "canonical_required_fail_fast"
