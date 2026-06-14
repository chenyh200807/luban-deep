"""Regression: home_personalization 必须能解析 ResolvedLearningTopic（F821 修复）。

origin/main 的一次 merge 在 ``home_personalization.py`` 用 ``ResolvedLearningTopic``
作类型注解却漏了 import，因 ``from __future__ import annotations`` 运行时不崩，但
CI 的 ruff F821 NameError gate（``ruff check --select F821,F811``）会 FAIL，卡住所有
PR 的 Contract Guard。本测试钉住该 import 存在，防复发。
"""

from __future__ import annotations


def test_home_personalization_imports_resolved_learning_topic() -> None:
    import deeptutor.services.learner_state.home_personalization as home
    from deeptutor.services.taxonomy.learning_topic_resolver import (
        ResolvedLearningTopic,
    )

    assert home.ResolvedLearningTopic is ResolvedLearningTopic
