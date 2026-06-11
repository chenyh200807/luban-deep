"""judge_point_enrichment — 为 artifact_first_llm_judge 编译结构化判定字段。

约束：
- 编译产物只服务 judge 理解与 deterministic validator；alias 不直接成为官方可得分项。
- 每个派生字段必须带 provenance（source/confidence/hash）。
- LLM 编译器可注入（hermetic 测试不打外网），失败时 fail-closed 返回空增强。
"""
from __future__ import annotations

from typing import Any

from deeptutor.services.construction_grading.judge_point_enrichment import (
    compile_judge_aliases,
    derive_calculation_spec,
    derive_list_spec,
    enrich_scoring_point,
)


def test_derive_list_spec_from_list_rule_text():
    point = {
        "point_id": "P1",
        "policy_type": "list_rule",
        "required_terms": ["施工总进度计划表(图)", "开竣工日期及工期一览表", "资源需要量及供应平衡表"],
        "list_rule": "应得分项为3项:施工总进度计划表(图)、开竣工日期及工期一览表、资源需要量及供应平衡表。命中3项满分5分。",
    }
    spec = derive_list_spec(point)
    assert spec["denominator"] == 3
    assert spec["provenance"]["source"] == "list_rule_text"
    assert spec["provenance"]["field_hash"]


def test_derive_list_spec_falls_back_to_required_terms():
    point = {
        "point_id": "P1",
        "policy_type": "list",
        "required_terms": ["排水沟", "集水井"],
        "list_rule": "",
    }
    spec = derive_list_spec(point)
    assert spec["denominator"] == 2
    assert spec["provenance"]["source"] == "required_terms"


def test_derive_list_spec_returns_none_for_non_list_policy():
    assert derive_list_spec({"point_id": "P1", "policy_type": "qualitative"}) is None


def test_derive_calculation_spec_passthrough_has_priority():
    point = {
        "point_id": "P1",
        "policy_type": "calculation",
        "calculation_spec": {"expected_value": "31.5"},
        "criterion": "总工期为30天",
    }
    spec = derive_calculation_spec(point)
    assert spec["expected_value"] == "31.5"
    assert spec["provenance"]["source"] == "artifact_calculation_spec"


def test_derive_calculation_spec_parses_expected_value_from_criterion():
    point = {
        "point_id": "P1",
        "policy_type": "calculation",
        "criterion": "总工期=31.5天（关键线路计算）",
    }
    spec = derive_calculation_spec(point)
    assert spec["expected_value"] == "31.5"
    assert spec["provenance"]["source"] == "criterion_number_parse"
    assert spec["provenance"]["confidence"] < 1.0


def test_enrich_scoring_point_is_immutable_and_carries_provenance():
    point = {
        "point_id": "P1",
        "policy_type": "list_rule",
        "required_terms": ["排水沟", "集水井"],
        "list_rule": "应得分项为2项:排水沟、集水井。",
        "max_score": 4.0,
    }
    enriched = enrich_scoring_point(point)
    assert "list_spec" not in point          # 不可变：原 point 不被修改
    assert enriched["list_spec"]["denominator"] == 2
    assert enriched["point_id"] == "P1"


def test_compile_judge_aliases_marks_non_official_and_keeps_provenance():
    def fake_llm(points: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            "P1": {
                "aliases": ["专家评审", "组织专家评审论证"],
                "negative_evidence": ["仅编制专项方案未论证"],
            }
        }

    points = [{"point_id": "P1", "criterion": "组织专家论证", "policy_type": "qualitative"}]
    out = compile_judge_aliases(points, llm_compile_fn=fake_llm)
    entry = out["P1"]
    assert entry["aliases"] == ["专家评审", "组织专家评审论证"]
    assert entry["negative_evidence"] == ["仅编制专项方案未论证"]
    assert entry["official_scoring_authority"] is False     # alias 不是官方可得分项
    assert entry["provenance"]["source"] == "llm_alias_compiler"
    assert entry["provenance"]["field_hash"]


def test_compile_judge_aliases_fails_closed_on_llm_error():
    def broken_llm(points: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        raise RuntimeError("provider down")

    out = compile_judge_aliases(
        [{"point_id": "P1", "criterion": "组织专家论证"}], llm_compile_fn=broken_llm
    )
    assert out == {}
