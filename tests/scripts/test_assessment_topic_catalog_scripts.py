from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.smoke_assessment_flywheel as flywheel_smoke
from scripts.smoke_assessment_flywheel import _assert_real_exam_source_policy, _normalize_api_base_url


def test_seed_topic_catalog_forms_supports_dry_run_help() -> None:
    result = subprocess.run(
        [
            "python",
            "scripts/seed_assessment_topic_catalog_forms.py",
            "--help",
        ],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0
    assert "--dry-run" in result.stdout
    assert "--persist" in result.stdout
    assert "--topic-id" in result.stdout
    assert "--out-json" in result.stdout
    assert "--out-md" in result.stdout
    assert "--reviewed-json" in result.stdout
    assert "--require-target-main" in result.stdout
    assert "--idempotency-key" in result.stdout


def test_seed_topic_catalog_forms_persist_requires_reviewed_guard_and_idempotency() -> None:
    result = subprocess.run(
        [
            "python",
            "scripts/seed_assessment_topic_catalog_forms.py",
            "--persist",
        ],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "reviewed_json_required_for_persist" in combined


def test_seed_topic_catalog_forms_dry_run_writes_requested_artifacts(tmp_path: Path) -> None:
    out_json = tmp_path / "catalog.json"
    out_md = tmp_path / "catalog.md"

    result = subprocess.run(
        [
            "python",
            "scripts/seed_assessment_topic_catalog_forms.py",
            "--dry-run",
            "--topic-id",
            "waterproof",
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
            "--json",
        ],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    assert out_json.exists()
    assert out_md.exists()
    assert "waterproof" in out_json.read_text(encoding="utf-8")
    assert "| waterproof |" in out_md.read_text(encoding="utf-8")


def test_assessment_flywheel_smoke_requires_token_for_live_run() -> None:
    result = subprocess.run(
        [
            "python",
            "scripts/smoke_assessment_flywheel.py",
            "--base-url",
            "https://test2.yousenjiaoyu.com",
        ],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 2
    assert "assessment_flywheel_smoke_requires_token" in result.stderr


def test_assessment_flywheel_smoke_help_documents_live_gate() -> None:
    result = subprocess.run(
        [
            "python",
            "scripts/smoke_assessment_flywheel.py",
            "--help",
        ],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0
    assert "--base-url" in result.stdout
    assert "--token" in result.stdout
    assert "--topic-id" in result.stdout
    assert "--verify-training-loop" in result.stdout
    assert "--expect-retest-recommendation" in result.stdout


def test_assessment_flywheel_smoke_accepts_origin_or_api_base_url() -> None:
    assert _normalize_api_base_url("https://test2.yousenjiaoyu.com") == "https://test2.yousenjiaoyu.com/api/v1"
    assert _normalize_api_base_url("https://test2.yousenjiaoyu.com/api/v1") == "https://test2.yousenjiaoyu.com/api/v1"


def test_assessment_flywheel_smoke_rejects_overclaimed_official_real_exam_copy() -> None:
    with pytest.raises(RuntimeError, match="assessment_real_exam_copy_overclaims_official"):
        _assert_real_exam_source_policy(
            {
                "source_policy": {
                    "source_policy_label": "官方真题卷",
                    "user_copy": "官方真题卷",
                    "official_real_exam_label_allowed": False,
                    "real_exam_share": 1.0,
                }
            }
        )


def test_assessment_flywheel_smoke_accepts_safe_real_exam_style_copy() -> None:
    policy = _assert_real_exam_source_policy(
        {
            "source_policy": {
                "source_policy_label": "真题样式测评",
                "user_copy": "本次真题样式测评用于校准综合应用能力，不代表官方考试分数。",
                "official_real_exam_label_allowed": False,
                "real_exam_share": 0.8,
            }
        }
    )

    assert policy["source_policy_label"] == "真题样式测评"


def test_assessment_flywheel_smoke_can_verify_training_loop_start(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    questions = [
        {
            "question_id": f"q{i}",
            "question_stem": f"题目 {i}",
            "options": [{"key": "A", "text": "A"}],
        }
        for i in range(1, 13)
    ]
    calls: list[tuple[str, str, dict | None]] = []
    responses = [
        {"topics": [{"topic_id": "waterproof", "status": "stable"}]},
        {"quiz_id": "quiz_1", "questions": questions, "assessment_type": "topic_diagnostic"},
        {"score_summary": {"score_pct": 50}},
        {"quiz_id": "quiz_1"},
        {"explanation": {"score_mutation_allowed": False}},
        {
            "recommended_prompts": [
                {
                    "prompt_type": "practice_prompt",
                    "text": "用 3 道题训练防水工程",
                    "intent": {
                        "learning_signal_type": "assessment_wrong_item_practice",
                        "evidence_refs": ["attempt_1"],
                    },
                }
            ]
        },
        {
            "conversation": {"id": "conversation_1"},
            "turn": {"id": "turn_1", "capability": "deep_question", "status": "running"},
            "stream": {"url": "/api/v1/ws"},
        },
    ]

    def fake_request_json(method, url, *, headers, timeout, body=None):
        calls.append((method, url, body))
        return responses.pop(0)

    monkeypatch.setattr(flywheel_smoke, "_request_json", fake_request_json)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smoke_assessment_flywheel.py",
            "--base-url",
            "https://example.com",
            "--token",
            "learner-token",
            "--verify-training-loop",
        ],
    )

    assert flywheel_smoke.main() == 0
    output = json.loads(capsys.readouterr().out)

    assert output["training_start_ready"] is True
    assert output["training_turn_id"] == "turn_1"
    start_call = calls[-1]
    assert start_call[0] == "POST"
    assert start_call[1].endswith("/api/v1/chat/start-turn")
    assert start_call[2]["capability"] == "deep_question"
    assert start_call[2]["prompt_intent"]["question_count"] == 3


def test_assessment_flywheel_smoke_can_verify_retest_recommendation_after_training_completion(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    questions = [
        {
            "question_id": f"q{i}",
            "question_stem": f"题目 {i}",
            "options": [{"key": "A", "text": "A"}],
        }
        for i in range(1, 13)
    ]
    responses = [
        {"topics": [{"topic_id": "waterproof", "status": "stable"}]},
        {"quiz_id": "quiz_1", "questions": questions, "assessment_type": "topic_diagnostic"},
        {"score_summary": {"score_pct": 50}},
        {"quiz_id": "quiz_1"},
        {"explanation": {"score_mutation_allowed": False}},
        {
            "recommended_prompts": [
                {
                    "prompt_type": "practice_prompt",
                    "text": "用 3 道题训练防水工程",
                    "intent": {
                        "learning_signal_type": "assessment_wrong_item_practice",
                        "question_count": 3,
                        "evidence_refs": ["attempt_1"],
                    },
                }
            ]
        },
        {
            "conversation": {"id": "conversation_1"},
            "turn": {"id": "turn_1", "capability": "deep_question", "status": "running"},
            "stream": {"url": "/api/v1/ws"},
        },
        {
            "recommended_prompts": [
                {
                    "prompt_type": "assessment",
                    "text": "再测一次防水工程",
                    "intent": {"learning_signal_type": "assessment", "concept_label": "防水工程"},
                }
            ]
        },
    ]

    monkeypatch.setattr(
        flywheel_smoke,
        "_request_json",
        lambda *_args, **_kwargs: responses.pop(0),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smoke_assessment_flywheel.py",
            "--base-url",
            "https://example.com",
            "--token",
            "learner-token",
            "--verify-training-loop",
            "--expect-retest-recommendation",
        ],
    )

    assert flywheel_smoke.main() == 0
    output = json.loads(capsys.readouterr().out)

    assert output["training_start_ready"] is True
    assert output["retest_recommendation_ready"] is True
