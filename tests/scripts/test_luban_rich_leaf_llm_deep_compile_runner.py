from __future__ import annotations

import json
from pathlib import Path


def _packets() -> dict:
    return {
        "schema": "luban_rich_leaf_llm_deep_compile_packets.v1",
        "verdict": "READY_FOR_LLM_DEEP_COMPILE_SHADOW",
        "summary": {"work_order_count": 1, "packet_count": 1, "production_write_count": 0},
        "packets": [
            {
                "packet_id": "llm_deep_compile_shard_000",
                "llm_role": "rich_leaf_deep_compiler",
                "work_orders": [
                    {
                        "work_order_id": "source_corpus_gap:教材/a.md",
                        "relative_path": "教材/a.md",
                        "source_lane": "source_truth",
                        "sha256": "a" * 64,
                        "candidate_only": True,
                        "review_only": True,
                        "runtime_install_allowed": False,
                        "release_truth_claimed": False,
                    }
                ],
                "output_contract": {"schema": "rich_leaf_deep_compile_candidate.v1"},
                "forbidden_actions": ["claim_release_truth", "write_runtime_default", "write_production_db"],
            }
        ],
        "classification": {
            "candidate_only": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        },
        "safety": {"production_write_count": 0, "release_truth_claimed": False},
    }


def _provider(_: str, messages: list[dict[str, str]]) -> dict:
    assert "教材原文" in messages[-1]["content"]
    assert "MAX_ITEMS_PER_FIELD=2" in messages[-1]["content"]
    assert "Return exactly one top-level JSON object" in messages[-1]["content"]
    return {
        "model": "fake-model",
        "content": json.dumps(
            {
                "concepts": ["施工缝"],
                "definitions": [{"term": "施工缝", "definition": "混凝土分段施工形成的接缝"}],
                "rules": [{"rule": "施工缝位置应符合设计和规范要求"}],
                "procedures": [],
                "numeric_constraints": [],
                "common_mistakes": [{"mistake": "把后浇带混同为施工缝"}],
                "exam_patterns": [{"pattern": "问施工缝留设与处理"}],
                "source_refs": [{"span": "教材原文：施工缝位置应符合设计要求。"}],
                "negative_evidence": [],
                "teaching_cards": [{"front": "施工缝要求", "back": "按设计和规范处理"}],
                "grading_relevance": [{"use": "判断是否踩中施工缝处理要求"}],
                "learner_memory_event_templates": [{"event_type": "case_grading_completed"}],
            },
            ensure_ascii=False,
        ),
        "prompt_tokens": 100,
        "completion_tokens": 80,
        "latency_ms": 12.3,
    }


def test_llm_deep_compile_runner_materializes_candidate_only_output(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_llm_deep_compile_runner import run_llm_deep_compile_runner

    source_root = tmp_path / "docs2026"
    (source_root / "教材").mkdir(parents=True)
    (source_root / "教材" / "a.md").write_text("教材原文：施工缝位置应符合设计要求。", encoding="utf-8")

    report = run_llm_deep_compile_runner(
        llm_deep_compile_packets=_packets(),
        source_root=source_root,
        provider_call=_provider,
        max_work_orders=1,
        max_source_chars=200,
    )

    assert report["schema"] == "luban_rich_leaf_llm_deep_compile_runner.v1"
    assert report["verdict"] == "PASS_LLM_DEEP_COMPILE_SHADOW_CANDIDATES"
    assert report["summary"]["provider_call_count"] == 1
    assert report["summary"]["candidate_count"] == 1
    assert report["summary"]["production_write_count"] == 0
    candidate = report["candidates"][0]
    assert candidate["candidate_status"] == "llm_shadow_candidate"
    assert candidate["relative_path"] == "教材/a.md"
    assert candidate["compiled_fields"]["concepts"] == ["施工缝"]
    assert candidate["runtime_install_allowed"] is False
    assert candidate["release_truth_claimed"] is False
    assert report["classification"]["candidate_only"] is True
    assert report["classification"]["runtime_install_allowed"] is False
    assert report["safety"]["production_write_count"] == 0


def test_llm_deep_compile_runner_cli_dry_run_writes_no_provider_report(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_llm_deep_compile_runner import main

    packets = tmp_path / "packets.json"
    source_root = tmp_path / "docs2026"
    output = tmp_path / "runner.json"
    source_root.mkdir()
    packets.write_text(json.dumps(_packets(), ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "--packets",
            str(packets),
            "--source-root",
            str(source_root),
            "--output",
            str(output),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text("utf-8"))
    assert payload["verdict"] == "DRY_RUN_READY_FOR_PROVIDER"
    assert payload["summary"]["provider_call_count"] == 0
    assert payload["summary"]["production_write_count"] == 0


def test_llm_deep_compile_runner_can_start_after_existing_work_orders(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_llm_deep_compile_runner import run_llm_deep_compile_runner

    packets = _packets()
    packets["packets"][0]["work_orders"].append(
        {
            "work_order_id": "source_corpus_gap:教材/b.md",
            "relative_path": "教材/b.md",
            "source_lane": "source_truth",
            "sha256": "b" * 64,
            "candidate_only": True,
            "review_only": True,
            "runtime_install_allowed": False,
            "release_truth_claimed": False,
        }
    )
    source_root = tmp_path / "docs2026"
    (source_root / "教材").mkdir(parents=True)
    (source_root / "教材" / "a.md").write_text("教材原文 A", encoding="utf-8")
    (source_root / "教材" / "b.md").write_text("教材原文 B", encoding="utf-8")

    report = run_llm_deep_compile_runner(
        llm_deep_compile_packets=packets,
        source_root=source_root,
        provider_call=_provider,
        start_index=1,
        max_work_orders=1,
        max_source_chars=200,
    )

    assert report["summary"]["planned_work_order_count"] == 1
    assert report["candidates"][0]["relative_path"] == "教材/b.md"


def test_llm_deep_compile_runner_records_raw_excerpt_on_non_json(tmp_path: Path) -> None:
    from scripts.run_luban_rich_leaf_llm_deep_compile_runner import run_llm_deep_compile_runner

    source_root = tmp_path / "docs2026"
    (source_root / "教材").mkdir(parents=True)
    (source_root / "教材" / "a.md").write_text("教材原文", encoding="utf-8")

    def bad_provider(_: str, __: list[dict[str, str]]) -> dict:
        return {
            "model": "bad-model",
            "content": "我无法完成这个任务，因为需要更多上下文。",
            "prompt_tokens": 10,
            "completion_tokens": 12,
            "latency_ms": 1.0,
        }

    report = run_llm_deep_compile_runner(
        llm_deep_compile_packets=_packets(),
        source_root=source_root,
        provider_call=bad_provider,
        max_work_orders=1,
        max_source_chars=200,
    )

    assert report["verdict"] == "NO_GO_LLM_DEEP_COMPILE_FAILED"
    assert report["errors"][0]["error"] == "provider_returned_non_json"
    assert "我无法完成" in report["errors"][0]["raw_content_excerpt"]
