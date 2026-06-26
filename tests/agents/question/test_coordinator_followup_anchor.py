from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from deeptutor.agents.question.coordinator import AgentCoordinator


@pytest.mark.asyncio
async def test_coordinator_generate_from_followup_context_builds_templates_without_idea_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        AgentCoordinator,
        "_create_idea_agent",
        lambda self: (_ for _ in ()).throw(
            AssertionError("followup anchor generation should not construct IdeaAgent")
        ),
    )
    monkeypatch.setattr(
        AgentCoordinator,
        "_create_batch_dir",
        lambda self, prefix: (tmp_path / prefix).mkdir(parents=True, exist_ok=True) or (tmp_path / prefix),
    )

    async def _fake_generation_loop(
        self,
        templates,
        user_topic: str,
        preference: str,
        history_context: str = "",
        require_explanation: bool = True,
        lightweight_generation: bool = False,
    ):
        captured["templates"] = templates
        captured["user_topic"] = user_topic
        captured["preference"] = preference
        captured["history_context"] = history_context
        captured["require_explanation"] = require_explanation
        captured["lightweight_generation"] = lightweight_generation
        return []

    monkeypatch.setattr(AgentCoordinator, "_generation_loop", _fake_generation_loop)

    coordinator = AgentCoordinator(language="zh", enable_idea_rag=True)
    result = await coordinator.generate_from_followup_context(
        user_topic="继续出2道很简单的选择题，只考刚才这几个概念。",
        preference="",
        num_questions=2,
        difficulty="easy",
        question_type="choice",
        followup_question_context={
            "question_id": "set_1",
            "question": "上一轮练习",
            "question_type": "choice",
            "items": [
                {
                    "question_id": "q_prev_1",
                    "question": "流水节拍反映什么？",
                    "question_type": "choice",
                    "correct_answer": "A",
                    "explanation": "节拍反映本专业队在一个施工段上的持续时间。",
                    "concentration": "流水节拍",
                    "difficulty": "easy",
                    "knowledge_context": "上一轮重点 1",
                },
                {
                    "question_id": "q_prev_2",
                    "question": "流水步距反映什么？",
                    "question_type": "choice",
                    "correct_answer": "B",
                    "explanation": "步距反映相邻专业队投入间隔。",
                    "concentration": "流水步距",
                    "difficulty": "easy",
                    "knowledge_context": "上一轮重点 2",
                },
            ],
        },
        history_context="最近一直在讲流水节拍和流水步距。",
    )

    templates = captured["templates"]
    assert isinstance(templates, list)
    assert len(templates) == 2
    assert [template.source for template in templates] == ["followup_anchor", "followup_anchor"]
    assert [template.concentration for template in templates] == ["流水节拍", "流水步距"]
    assert all(template.question_type == "choice" for template in templates)
    assert all(template.difficulty == "easy" for template in templates)
    assert captured["require_explanation"] is True
    assert captured["lightweight_generation"] is False
    assert result["trace"]["anchor_generation"] is True
    assert result["trace"]["anchor_item_count"] == 2


@pytest.mark.asyncio
async def test_coordinator_lightweight_topic_generation_skips_idea_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        AgentCoordinator,
        "_create_idea_agent",
        lambda self: (_ for _ in ()).throw(
            AssertionError("lightweight topic generation should not construct IdeaAgent")
        ),
    )
    monkeypatch.setattr(
        AgentCoordinator,
        "_create_batch_dir",
        lambda self, prefix: (tmp_path / prefix).mkdir(parents=True, exist_ok=True) or (tmp_path / prefix),
    )

    async def _fake_lightweight_batch_generate(
        self,
        *,
        templates,
        user_topic: str,
        preference: str,
        history_context: str,
        counters,
    ):
        # lightweight=True path never reaches _generation_loop; it uses this method.
        captured["templates"] = templates
        captured["user_topic"] = user_topic
        return []

    monkeypatch.setattr(AgentCoordinator, "_lightweight_batch_generate", _fake_lightweight_batch_generate)

    coordinator = AgentCoordinator(language="zh", enable_idea_rag=True)
    result = await coordinator.generate_from_topic(
        user_topic="我现在学到网络计划了，先给我出3道很短的小题，只出题不要答案。",
        preference="只出题",
        num_questions=3,
        difficulty="easy",
        question_type="choice",
        history_context="",
        lightweight_generation=True,
        require_explanation=False,
    )

    templates = captured["templates"]
    assert isinstance(templates, list)
    assert len(templates) == 3
    assert all(template.source == "lightweight_topic" for template in templates)
    assert all(template.question_type == "choice" for template in templates)
    assert all(template.difficulty == "easy" for template in templates)
    assert all(
        template.metadata["knowledge_context"] == "当前学习锚点：网络计划"
        for template in templates
    )
    assert all(template.concentration == "网络计划" for template in templates)
    assert result["trace"]["lightweight_generation"] is True


@pytest.mark.asyncio
async def test_coordinator_lightweight_topic_exclusion_skips_rag_reference_anchor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        AgentCoordinator,
        "_create_idea_agent",
        lambda self: (_ for _ in ()).throw(
            AssertionError("lightweight topic generation should not construct IdeaAgent")
        ),
    )
    monkeypatch.setattr(
        AgentCoordinator,
        "_create_batch_dir",
        lambda self, prefix: (tmp_path / prefix).mkdir(parents=True, exist_ok=True) or (tmp_path / prefix),
    )

    async def _fake_rag_search(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("current-question exclusion must not ask RAG for a reference anchor")

    async def _fake_lightweight_batch_generate(
        self,
        *,
        templates,
        user_topic: str,
        preference: str,
        history_context: str,
        counters,
    ):
        captured["templates"] = templates
        captured["user_topic"] = user_topic
        captured["counters"] = dict(counters)
        return []

    monkeypatch.setattr("deeptutor.agents.question.coordinator.rag_search", _fake_rag_search)
    monkeypatch.setattr(AgentCoordinator, "_lightweight_batch_generate", _fake_lightweight_batch_generate)

    coordinator = AgentCoordinator(language="zh", kb_name="construction-exam", enable_idea_rag=True)
    result = await coordinator.generate_from_topic(
        user_topic=(
            "再出一道不同考点的单选题，不要和刚才那题重复。\n\n"
            "请从建筑实务/建造师考试高频考点中选择一个与当前题不同的小考点出题；"
            "不要沿用当前题题干、选项或同一小考点。\n\n"
            "排除当前题（仅用于去重，不得作为新题考点）：\n"
            "当前题：施工现场负责审查批准一级动火作业的（ ）。"
        ),
        preference="只出题",
        num_questions=1,
        difficulty="easy",
        question_type="choice",
        history_context="",
        lightweight_generation=True,
        require_explanation=False,
        avoid_current_question=True,
    )

    templates = captured["templates"]
    assert isinstance(templates, list)
    assert len(templates) == 1
    assert templates[0].source == "lightweight_topic"
    assert templates[0].reference_question is None
    assert templates[0].metadata["anchor_source"] == "current_question_exclusion"
    assert "排除当前题" in templates[0].metadata["knowledge_context"]
    assert result["trace"]["lightweight_generation"] is True
    assert result["trace"]["lightweight_counters"]["retriever_calls"] == 0


@pytest.mark.asyncio
async def test_coordinator_lightweight_topic_generation_uses_single_rag_anchor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        AgentCoordinator,
        "_create_idea_agent",
        lambda self: (_ for _ in ()).throw(
            AssertionError("lightweight topic generation should not construct IdeaAgent")
        ),
    )
    monkeypatch.setattr(
        AgentCoordinator,
        "_create_batch_dir",
        lambda self, prefix: (tmp_path / prefix).mkdir(parents=True, exist_ok=True) or (tmp_path / prefix),
    )

    async def _fake_rag_search(**kwargs: Any) -> dict[str, Any]:
        captured["rag_kwargs"] = kwargs
        return {
            "query": kwargs.get("query", ""),
            "provider": "supabase",
            "kb_name": kwargs.get("kb_name"),
            "answer": "【题目】关于流水节拍，下列说法正确的是？\n【选项】{\"A\":\"反映工序持续时间\"}\n【答案】A\n【解析】流水节拍反映本专业队在一个施工段上的持续时间。",
            "exact_question": {
                "stem": "关于流水节拍，下列说法正确的是？",
                "question_type": "choice",
                "correct_answer": "A",
                "analysis": "流水节拍反映本专业队在一个施工段上的持续时间。",
                "options": {"A": "反映工序持续时间"},
                "source_group": "question_exact_text",
                "confidence": 0.93,
            },
        }

    async def _fake_lightweight_batch_generate(
        self,
        *,
        templates,
        user_topic: str,
        preference: str,
        history_context: str,
        counters,
    ):
        captured["templates"] = templates
        return []

    monkeypatch.setattr("deeptutor.agents.question.coordinator.rag_search", _fake_rag_search)
    monkeypatch.setattr(AgentCoordinator, "_lightweight_batch_generate", _fake_lightweight_batch_generate)

    coordinator = AgentCoordinator(language="zh", kb_name="construction-exam", enable_idea_rag=True)
    result = await coordinator.generate_from_topic(
        user_topic="我现在学到流水节拍了，先给我出1道很短的小题，只出题不要答案。",
        preference="只出题",
        num_questions=1,
        difficulty="easy",
        question_type="choice",
        history_context="",
        lightweight_generation=True,
        require_explanation=False,
    )

    templates = captured["templates"]
    assert isinstance(templates, list)
    assert len(templates) == 1
    assert captured["rag_kwargs"]["query"] == "我现在学到流水节拍了，先给我出1道很短的小题，只出题不要答案。"
    assert captured["rag_kwargs"]["kb_name"] == "construction-exam"
    assert captured["rag_kwargs"]["only_need_context"] is True
    assert templates[0].concentration == "流水节拍"
    assert "题库参考题目：关于流水节拍，下列说法正确的是？" in templates[0].metadata["knowledge_context"]
    assert "题库解析要点：流水节拍反映本专业队在一个施工段上的持续时间。" in templates[0].metadata["knowledge_context"]
    assert templates[0].reference_question == "关于流水节拍，下列说法正确的是？"
    assert templates[0].reference_answer == "A"
    assert templates[0].metadata["anchor_source"] == "question_exact_text"
    assert templates[0].metadata["anchor_confidence"] == 0.93
    assert result["trace"]["lightweight_generation"] is True


@pytest.mark.asyncio
async def test_coordinator_lightweight_topic_generation_falls_back_when_rag_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        AgentCoordinator,
        "_create_idea_agent",
        lambda self: (_ for _ in ()).throw(
            AssertionError("lightweight topic generation should not construct IdeaAgent")
        ),
    )
    monkeypatch.setattr(
        AgentCoordinator,
        "_create_batch_dir",
        lambda self, prefix: (tmp_path / prefix).mkdir(parents=True, exist_ok=True) or (tmp_path / prefix),
    )

    async def _fake_rag_search(**kwargs: Any) -> dict[str, Any]:
        captured["rag_kwargs"] = kwargs
        return {
            "query": kwargs.get("query", ""),
            "provider": "supabase",
            "kb_name": kwargs.get("kb_name"),
            "answer": "",
            "exact_question": {},
        }

    async def _fake_lightweight_batch_generate(
        self,
        *,
        templates,
        user_topic: str,
        preference: str,
        history_context: str,
        counters,
    ):
        captured["templates"] = templates
        return []

    monkeypatch.setattr("deeptutor.agents.question.coordinator.rag_search", _fake_rag_search)
    monkeypatch.setattr(AgentCoordinator, "_lightweight_batch_generate", _fake_lightweight_batch_generate)

    coordinator = AgentCoordinator(language="zh", kb_name="construction-exam", enable_idea_rag=True)
    await coordinator.generate_from_topic(
        user_topic="我现在学到网络计划了，先给我出1道很短的小题，只出题不要答案。",
        preference="只出题",
        num_questions=1,
        difficulty="easy",
        question_type="choice",
        history_context="",
        lightweight_generation=True,
        require_explanation=False,
    )

    templates = captured["templates"]
    assert isinstance(templates, list)
    assert len(templates) == 1
    assert templates[0].metadata["knowledge_context"] == "当前学习锚点：网络计划"
    assert templates[0].concentration == "网络计划"


@pytest.mark.asyncio
async def test_coordinator_lightweight_topic_generation_extracts_reference_anchor_from_answer_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        AgentCoordinator,
        "_create_idea_agent",
        lambda self: (_ for _ in ()).throw(
            AssertionError("lightweight topic generation should not construct IdeaAgent")
        ),
    )
    monkeypatch.setattr(
        AgentCoordinator,
        "_create_batch_dir",
        lambda self, prefix: (tmp_path / prefix).mkdir(parents=True, exist_ok=True) or (tmp_path / prefix),
    )

    async def _fake_rag_search(**kwargs: Any) -> dict[str, Any]:
        captured["rag_kwargs"] = kwargs
        return {
            "query": kwargs.get("query", ""),
            "provider": "supabase",
            "kb_name": kwargs.get("kb_name"),
            "answer": (
                "【题目】屋面防水施工基本要求正确的有（　　）。\n"
                "【选项】"
                '[{"key": "A", "value": "以排为主，以防为辅"}, '
                '{"key": "B", "value": "上下层卷材不得相互垂直铺贴"}, '
                '{"key": "C", "value": "屋面卷材防水施工时，由高向低铺贴"}, '
                '{"key": "D", "value": "天沟卷材施工时，宜顺天沟方向铺贴"}]\n'
                "【答案】BDE\n"
                "【解析】A选项错误，屋面防水以防为主，以排为辅。"
            ),
            "exact_question": {},
        }

    _orig_build_templates = AgentCoordinator._build_lightweight_topic_templates

    def _spy_build_templates(**kwargs):
        result = _orig_build_templates(**kwargs)
        captured["templates"] = result
        return result

    monkeypatch.setattr(
        AgentCoordinator,
        "_build_lightweight_topic_templates",
        staticmethod(_spy_build_templates),
    )

    monkeypatch.setattr("deeptutor.agents.question.coordinator.rag_search", _fake_rag_search)

    coordinator = AgentCoordinator(language="zh", kb_name="construction-exam", enable_idea_rag=True)
    await coordinator.generate_from_topic(
        user_topic="我现在在学防水工程，先给我出1道建筑实务单选题，不要给答案。",
        preference="只出题",
        num_questions=1,
        difficulty="easy",
        question_type="choice",
        history_context="",
        lightweight_generation=True,
        require_explanation=False,
    )

    templates = captured["templates"]
    assert isinstance(templates, list)
    assert len(templates) == 1
    assert templates[0].concentration == "防水工程"
    assert templates[0].reference_question == "屋面防水施工基本要求正确的有（　　）。"
    assert templates[0].reference_answer == "BDE"
    assert templates[0].metadata["anchor_source"] == "rag_answer_bundle"
    assert "题库参考题目：屋面防水施工基本要求正确的有（　　）。" in templates[0].metadata["knowledge_context"]
    assert "A. 以排为主，以防为辅" in templates[0].metadata["knowledge_context"]
    assert "题库解析要点：A选项错误，屋面防水以防为主，以排为辅。" in templates[0].metadata["knowledge_context"]


def test_lightweight_anchor_rejects_off_topic_rag_hit() -> None:
    # Bug#1 主因 regression: an off-topic RAG hit (SMA topic → 垂直运输/井架 question)
    # must NOT become the canonical generation anchor; fall back to the pure topic
    # anchor so the generator stays on the user's 考点.
    from deeptutor.agents.question.coordinator import AgentCoordinator

    off_topic = AgentCoordinator._build_lightweight_rag_anchor_payload(
        user_topic="再出一道SMA沥青混合料关键技术要求的选择题",
        result={
            "answer": "",
            "exact_question": {
                "stem": "下列哪一项属于垂直运输设备？",
                "options": {"A": "手推车", "B": "井架"},
                "correct_answer": "B",
                "analysis": "井架属于垂直运输。",
                "source_group": "exact_question",
            },
        },
    )
    assert "reference_question" not in off_topic  # rejected -> pure topic anchor (base)

    on_topic = AgentCoordinator._build_lightweight_rag_anchor_payload(
        user_topic="出一道法律基础的选择题",
        result={
            "answer": "",
            "exact_question": {
                "stem": "下列哪一项属于法律？",
                "options": {"A": "法律", "B": "行政法规"},
                "correct_answer": "A",
                "analysis": "全国人大制定的是法律。",
                "source_group": "exact_question",
            },
        },
    )
    assert on_topic.get("reference_question") == "下列哪一项属于法律？"  # kept


def test_construction_scope_gate_allows_intra_jianzao_subjects() -> None:
    # 科目门反转 regression(用户从生产 trace 报):市政/机电/沟槽开挖等一建他科或
    # 建筑工程白名单漏词,过去走 unknown_topic 被 coordinator 误 block;现在 coordinator
    # 用 practice_generation_topic_block_decision,只 out_of_scope 才 block,一建范畴一律
    # 放行(他科走通用 LLM 出题 + 非专项标注),真正非考试越界仍 block。
    from deeptutor.tutorbot.teaching_modes import (
        practice_generation_topic_block_decision,
        practice_generation_topic_domain_status,
    )

    for topic in (
        "给我出一道市政公用工程实务的单选题",
        "那就考点给我出一道关于沟槽开挖与支护的单选题吧",
        "给我出一道机电工程的题",
        "给我出一道公路工程的题",
    ):
        status = practice_generation_topic_domain_status(topic)
        assert (
            practice_generation_topic_block_decision(status) == "allow"
        ), f"intra-jianzao topic wrongly blocked at coordinator gate: {topic} -> {status}"

    blocked = practice_generation_topic_domain_status("法国首都是哪")
    assert practice_generation_topic_block_decision(blocked) == "block_out_of_scope"


def test_generated_questions_construction_scope_gate() -> None:
    # 出口科目门(owner=只建筑):生成题 ground 建筑→放行;全跑偏(汉字/外国常识)→诚实拒答。
    from deeptutor.agents.question.coordinator import AgentCoordinator

    jianzhu = [{"qa_pair": {"concentration": "基坑支护", "question": "深基坑开挖与支护下列说法正确的是"}}]
    assert AgentCoordinator._generated_questions_in_construction_scope([], jianzhu) is True

    # LLM 跑偏出的语文/汉字题(用户真实 case:市政→"你好"情境题)→ 出 scope,拒答
    hanzi = [{"qa_pair": {"concentration": "汉语日常交流", "question": "“你好”最常被用于哪种情境"}}]
    assert AgentCoordinator._generated_questions_in_construction_scope([], hanzi) is False

    live_hanzi = [{"qa_pair": {"concentration": "词语理解", "question": "“先”在“先来后到”中表示什么？"}}]
    assert AgentCoordinator._generated_questions_in_construction_scope([], live_hanzi) is False

    # 外国地理常识跑偏 → 出 scope
    paris = [{"qa_pair": {"concentration": "世界地理", "question": "法国的首都是哪座城市"}}]
    assert AgentCoordinator._generated_questions_in_construction_scope([], paris) is False

    # 至少一道建筑题即放行(混合时不误杀建筑题)
    mixed = hanzi + jianzhu
    assert AgentCoordinator._generated_questions_in_construction_scope([], mixed) is True

    # 无题面可判 → 不拦(避免空判误拒)
    assert AgentCoordinator._generated_questions_in_construction_scope([], []) is True


def test_lightweight_anchor_label_uses_explicit_exam_topic_after_action_words() -> None:
    user_topic = "先出一道建筑实务单选题，考屋面保温或屋面防水，带A-D选项。"

    assert (
        AgentCoordinator._derive_lightweight_anchor_label(user_topic=user_topic)
        == "屋面保温或屋面防水"
    )

    payload = AgentCoordinator._base_lightweight_anchor_payload(user_topic=user_topic)
    assert payload["concentration"] == "屋面保温或屋面防水"
    assert payload["knowledge_context"] == "当前学习锚点：屋面保温或屋面防水"


def test_lightweight_anchor_label_uses_topic_clause_when_answer_reveal_is_suppressed() -> None:
    user_topic = "先出一道建筑实务单选题，临时用电/安全，只出题，不要给答案或解析。"

    assert AgentCoordinator._derive_lightweight_anchor_label(user_topic=user_topic) == "临时用电/安全"

    payload = AgentCoordinator._base_lightweight_anchor_payload(user_topic=user_topic)
    assert payload["concentration"] == "临时用电/安全"
    assert payload["knowledge_context"] == "当前学习锚点：临时用电/安全"


def test_current_question_exclusion_anchor_label_ignores_exclusion_block() -> None:
    user_topic = """再出一道不同考点的单选题，不要和刚才那题重复；仍然只给题目和A/B/C/D选项。

请基于以下更大范围学习主题出题，但必须避开当前题题干、选项和同一小考点：
当前会话主题：新对话

排除当前题（仅用于去重，不得作为新题考点）：
需避开考点：一级建造师项目管理
需避开题干：施工现场负责审查批准一级动火作业的（ ）。
需避开选项面：A. 项目负责人；B. 项目生产负责人；C. 项目安全管理部门；D. 企业安全管理部门"""

    payload = AgentCoordinator._current_question_exclusion_anchor_payload(user_topic=user_topic)

    assert payload["anchor_source"] == "current_question_exclusion"
    assert payload["concentration"] == "建筑实务高频考点"
    assert "排除当前题" in payload["knowledge_context"]
    assert "需避开题干" in payload["knowledge_context"]
    assert "需避开" not in payload["concentration"]
    assert "不得作为新题考点" not in payload["concentration"]
