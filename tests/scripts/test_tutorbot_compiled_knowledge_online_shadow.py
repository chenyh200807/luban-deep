from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "shadow",
    REPO / "scripts" / "run_tutorbot_compiled_knowledge_online_shadow.py",
)
shadow = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = shadow


def test_pair_metrics_detect_compiled_hit_and_answer_improvement() -> None:
    assert _spec.loader is not None
    _spec.loader.exec_module(shadow)

    case = shadow.ShadowCase(
        case_id="c1",
        query="施工合同索赔成立条件是什么？",
        expected="hit",
        path_terms=("索赔",),
        answer_terms=("索赔", "合同"),
    )
    control = {
        "visible_response": "可以看合同条款。",
        "result_metadata": {"total_tokens": 100},
    }
    treatment = {
        "visible_response": "施工合同索赔成立要看索赔事件、合同约定和证据。",
        "result_metadata": {
            "total_tokens": 130,
            "luban_general_knowledge_context": {
                "authority": "luban_general_knowledge_context",
                "tier": "teaching_context_not_answer_key",
                "official_score_allowed": False,
                "llm_may_decide_correctness": False,
                "leaf_name_path": "智能建造新技术 > 工程变更、新增工程与索赔 > 工程索赔类型与条件",
                "confidence": {"status": "high", "source_category_count": 2},
                "sources": {"textbook": [{"text_preview": "索赔条件"}], "lecture": [{"text_preview": "合同索赔"}]},
            },
        },
    }

    row = shadow.evaluate_pair(case, control=control, treatment=treatment)

    assert row["compiled_hit"] is True
    assert row["wrong_path"] is False
    assert row["source_valid"] is True
    assert row["answer_improved"] is True
    assert row["token_delta"] == 30


def test_start_turn_body_uses_mobile_top_level_shadow_flag() -> None:
    assert _spec.loader is not None
    _spec.loader.exec_module(shadow)

    case = shadow.ShadowCase(
        case_id="c1",
        query="施工合同索赔成立条件是什么？",
        expected="hit",
    )

    control = shadow._build_start_turn_body(case=case, conversation_id="conv1", arm="rag_only")
    treatment = shadow._build_start_turn_body(case=case, conversation_id="conv2", arm="compiled")

    assert control["general_knowledge_context"] is False
    assert treatment["general_knowledge_context"] is True
    assert control["config"] == {"bot_id": "construction-exam-coach"}
    assert treatment["config"] == {"bot_id": "construction-exam-coach"}


def test_pair_metrics_treat_low_confidence_hit_as_wrong_path() -> None:
    assert _spec.loader is not None
    _spec.loader.exec_module(shadow)

    case = shadow.ShadowCase(
        case_id="c2",
        query="双代号网络计划总时差怎么算？",
        expected="open",
        path_terms=("总时差",),
        answer_terms=("总时差",),
    )

    row = shadow.evaluate_pair(
        case,
        control={"visible_response": "总时差看网络计划。", "result_metadata": {}},
        treatment={
            "visible_response": "总时差看网络计划。",
            "result_metadata": {
                "luban_general_knowledge_context": {
                    "leaf_name_path": "结构工程材料 > 水泥的性能与应用 > 水泥的分类与代号",
                    "sources": {"lecture": [{"text_preview": "网络计划总时差"}]},
                }
            },
        },
    )

    assert row["compiled_hit"] is True
    assert row["fail_open"] is False
    assert row["wrong_path"] is True
    assert row["source_valid"] is False
