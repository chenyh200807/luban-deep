"""WP4（2026-07-12）收权后：bare-action 出题承接 = deep_question._resolve_generation_topic
（唯一 topic decider）以 fall-through 兜底。coordinator 侧的第二套推导
``_resolve_practice_topic_with_context`` 已删除，本文件从"测已删方法"翻转为"测唯一
resolver 的承接/冷启动契约"（旧契约 pin → 新契约镜像）。

契约（新）：
- bare-action 承接（"继续出一道"）+ 对话里有既定建筑主题 ⇒ 继承该主题 fall-through 出题
  （返回非空 composed topic，非罐头拒答）；
- 本轮自带考点 ⇒ 直接用本轮考点（不需继承）；
- 真冷启动（纯动作词 + 无任何对话文本）⇒ 返回 ""（capability 层澄清一次，非罐头）。
Hermetic。
"""
from __future__ import annotations

from deeptutor.capabilities import deep_question as deep_question_module


def _resolve(raw_topic: str, conversation_context_text: str) -> str:
    return deep_question_module._resolve_generation_topic(
        raw_topic=raw_topic,
        active_object=None,
        suspended_object_stack=None,
        followup_question_context=None,
        conversation_context_text=conversation_context_text,
    )


# ---- bare-action continuation inherits the established construction topic ----------------
def test_continuation_inherits_topic_from_context():
    ctx = "用户正在练习流水施工，已经出了一道流水施工的单选题。"
    out = _resolve("继续出一道", ctx)
    # WP4：fall-through 承接（非罐头拒答），composed topic 必须锚定既定主题。
    assert out != "", f"continuation must fall through, not can: {out!r}"
    assert "流水施工" in out, f"continuation did not inherit the topic: {out!r}"


# ---- this turn's own topic wins when present (no need to inherit) ------------------------
def test_own_topic_used_when_present():
    out = _resolve("出一道流水施工的单选题考考我", "")
    assert "流水施工" in out, f"own topic lost: {out!r}"


# ---- true cold start (pure action word + no conversation text) yields no topic ----------
def test_cold_start_yields_no_topic():
    # WP4：唯一返回 "" 的情形 = 纯动作词 + 完全无对话文本（capability 层澄清一次）。
    # 旧契约里"动作词 + 非建筑闲聊上下文"也返回 ""（域状态过滤）；WP4 下改为
    # fall-through（对话尾部当锚点，generator 科目锁兜底），故此处只 pin 真冷启动。
    assert _resolve("继续出一道", "") == ""
    assert _resolve("出三道题", "") == ""
