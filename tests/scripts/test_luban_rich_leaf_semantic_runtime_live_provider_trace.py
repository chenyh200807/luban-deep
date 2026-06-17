from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _near_live_shadow_ab() -> dict:
    return {
        "schema": "luban_rich_leaf_semantic_runtime_near_live_shadow_ab.v1",
        "verdict": "PASS",
        "summary": {
            "shadow_case_count": 2,
            "current_rag_answerable_rate": 0.5,
            "current_rag_mean_token_proxy": 1000,
            "local_adapter_answerable_rate": 1.0,
            "local_adapter_mean_token_proxy": 40,
        },
        "classification": {
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "production_default": False,
            "release_truth_claimed": False,
        },
        "sample_rows": [
            {
                "arm": "current_rag_lexical_proxy",
                "case_id": "case_1",
                "task": "rag_answer",
                "answerable": False,
                "fail_open": True,
                "token_proxy": 900,
            },
            {
                "arm": "current_rag_lexical_proxy",
                "case_id": "case_2",
                "task": "tutoring",
                "answerable": True,
                "fail_open": False,
                "token_proxy": 800,
            },
        ],
        "current_rag_rows": [
            {
                "arm": "current_rag_lexical_proxy",
                "case_id": "case_1",
                "task": "rag_answer",
                "answerable": False,
                "fail_open": True,
                "token_proxy": 900,
            },
            {
                "arm": "current_rag_lexical_proxy",
                "case_id": "case_2",
                "task": "tutoring",
                "answerable": True,
                "fail_open": False,
                "token_proxy": 800,
            },
        ],
        "local_adapter_rows": [
            {
                "arm": "rich_leaf_local_adapter",
                "case_id": "case_1",
                "task": "rag_answer",
                "family": "rules",
                "leaf_id": "L1",
                "field_id": "F1",
                "expected_source_ref_ids": ["src_1"],
                "cited_source_ref_ids": ["src_1"],
                "answer": {"text": "建筑设计一般可分为四个阶段。", "cited_source_ref_ids": ["src_1"]},
                "answerable": True,
                "term_hit": True,
                "fail_open": False,
                "token_proxy": 40,
            },
            {
                "arm": "rich_leaf_local_adapter",
                "case_id": "case_2",
                "task": "tutoring",
                "family": "teaching_cards",
                "leaf_id": "L2",
                "field_id": "F2",
                "expected_source_ref_ids": ["src_2"],
                "cited_source_ref_ids": ["src_2"],
                "answer": {"text": "女儿墙顶点可作为高度计算终点。", "cited_source_ref_ids": ["src_2"]},
                "answerable": True,
                "term_hit": True,
                "fail_open": False,
                "token_proxy": 38,
            },
        ],
        "safety": {
            "canonical_truth_written": False,
            "official_score_allowed": False,
            "installed_runtime_supply": False,
            "production_write_count": 0,
            "release_truth_claimed": False,
        },
    }


def _fake_provider(model: str, messages: list[dict], *, timeout_s: float) -> dict:
    del timeout_s
    prompt = "\n".join(str(message.get("content") or "") for message in messages)
    answerable = "RICH_LEAF_CONTEXT" in prompt or "ARTIFACT_JUDGE" in prompt
    payload = {
        "answerable": answerable,
        "evidence_cited": answerable,
        "fail_open": False,
        "answer": "ok" if answerable else "",
    }
    return {
        "model": model,
        "content": json.dumps(payload, ensure_ascii=False),
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "latency_ms": 10,
    }


def test_live_provider_trace_builds_four_arm_results() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_live_provider_trace import build_live_provider_trace

    report = build_live_provider_trace(
        near_live_shadow_ab=_near_live_shadow_ab(),
        sample_limit=2,
        provider_call=_fake_provider,
        model="deepseek-chat",
    )

    assert report["schema"] == "luban_rich_leaf_semantic_runtime_live_ab_results.v1"
    assert report["runtime_exercised"] is True
    assert report["provider_call_count"] == 8
    assert report["total_tokens"] == 960
    assert report["models"] == ["deepseek-chat"]
    by_arm = {arm["arm"]: arm for arm in report["arms"]}
    assert set(by_arm) == {
        "current_rag_runtime",
        "legacy_runtime_or_projection",
        "rich_leaf_promoted_context",
        "artifact_first_llm_judge",
    }
    assert by_arm["rich_leaf_promoted_context"]["accuracy_rate"] == 1.0
    assert by_arm["artifact_first_llm_judge"]["evidence_citation_rate"] == 1.0
    assert report["safety"]["production_write_count"] == 0
    assert report["classification"]["release_truth_claimed"] is False


def test_live_provider_trace_fails_closed_when_provider_missing() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_live_provider_trace import build_live_provider_trace

    report = build_live_provider_trace(
        near_live_shadow_ab=_near_live_shadow_ab(),
        sample_limit=1,
        provider_call=None,
        model="deepseek-chat",
    )

    assert report["schema"] == "luban_rich_leaf_semantic_runtime_live_ab_results.v1"
    assert report["runtime_exercised"] is False
    assert report["provider_call_count"] == 0
    assert "provider_call_not_configured" in report["blockers"]


def test_live_provider_trace_reuses_completed_previous_rows() -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_live_provider_trace import build_live_provider_trace

    previous_results = {
        "rows": [
            {
                "arm": "current_rag_runtime",
                "case_id": "case_2",
                "status": "completed",
                "answerable": False,
                "expected_answerable": False,
                "matches_expected": True,
                "evidence_cited": False,
                "fail_open": False,
                "prompt_tokens": 50,
                "completion_tokens": 10,
                "total_tokens": 60,
                "latency_ms": 5,
            }
        ]
    }
    calls: list[str] = []

    def provider(model: str, messages: list[dict], *, timeout_s: float) -> dict:
        del timeout_s
        prompt = "\n".join(str(message.get("content") or "") for message in messages)
        if "current_rag_runtime" in prompt:
            calls.append("current_rag_runtime")
        return _fake_provider(model, messages, timeout_s=30)

    report = build_live_provider_trace(
        near_live_shadow_ab=_near_live_shadow_ab(),
        sample_limit=1,
        provider_call=provider,
        model="deepseek-chat",
        previous_results=previous_results,
    )

    assert report["runtime_exercised"] is True
    assert report["provider_call_count"] == 4
    assert report["summary"]["reused_provider_call_count"] == 1
    assert report["summary"]["new_provider_call_count"] == 3
    assert calls == []


def test_live_provider_trace_cli_writes_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_semantic_runtime_live_provider_trace import main

    near_live = tmp_path / "near_live_shadow_ab.json"
    output = tmp_path / "live_results.json"
    _write_json(near_live, _near_live_shadow_ab())

    exit_code = main(
        [
            "--near-live-shadow-ab",
            str(near_live),
            "--output",
            str(output),
            "--sample-limit",
            "1",
            "--no-provider-call",
        ]
    )

    assert exit_code == 1
    payload = json.loads(output.read_text("utf-8"))
    assert payload["runtime_exercised"] is False
    assert payload["summary"]["sample_count"] == 1
