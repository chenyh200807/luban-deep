import json
import os
import subprocess
import importlib.util
import http.client
from pathlib import Path


SCRIPT = "scripts/run_luban_m35_three_model_blind_ab.py"
FIXTURE = "tests/fixtures/luban_m35_case_scoring"
REPO = Path(__file__).resolve().parents[2]


def _run_ab(tmp_path: Path, *args: str, env: dict[str, str] | None = None) -> dict:
    out = tmp_path / "three_model_ab.json"
    run_env = os.environ.copy()
    if env is not None:
        run_env.update(env)
    subprocess.run(
        [
            "python",
            SCRIPT,
            "--fixture",
            FIXTURE,
            "--output",
            str(out),
            *args,
        ],
        check=True,
        env=run_env,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def test_fixture_mode_runs_three_roles_without_provider_or_truth_writes(tmp_path):
    payload = _run_ab(tmp_path, "--mode", "fixture", "--max-samples", "2")

    assert payload["mode"] == "fixture"
    assert payload["status"] == "OK"
    assert payload["roles"] == {
        "qwen": "blind_scorer",
        "deepseek": "adversarial_prosecutor",
        "gpt55": "final_adjudicator",
    }
    assert payload["provider_call_count"] == 0
    assert payload["production_write_count"] == 0
    assert payload["canonical_truth_written"] is False
    assert payload["official_score_allowed"] is False
    assert payload["promote_to_release"] is False
    assert len(payload["cases"]) == 2
    assert payload["summary"]["artifact_first_win_count"] >= 0
    assert payload["summary"]["quality_claim_allowed"] is False


def test_live_mode_missing_keys_blocks_without_secret_leak(tmp_path):
    payload = _run_ab(
        tmp_path,
        "--mode",
        "live",
        "--max-samples",
        "1",
        env={
            "DASHSCOPE_API_KEY": "",
            "DEEPSEEK_API_KEY": "",
            "OPENAI_API_KEY": "",
            "SECRET_SENTINEL": "sk-should-not-appear",
        },
    )

    rendered = json.dumps(payload, ensure_ascii=False)
    assert payload["status"] == "BLOCKED_MISSING_PROVIDER_KEYS"
    assert payload["provider_call_count"] == 0
    assert "sk-should-not-appear" not in rendered
    assert payload["missing_key_envs"] == [
        "DASHSCOPE_API_KEY",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
    ]


def test_live_mode_local_final_adjudicator_does_not_require_openai_key(tmp_path):
    payload = _run_ab(
        tmp_path,
        "--mode",
        "live",
        "--max-samples",
        "0",
        "--local-final-adjudicator",
        env={
            "DASHSCOPE_API_KEY": "qwen-present",
            "DEEPSEEK_API_KEY": "deepseek-present",
            "OPENAI_API_KEY": "",
        },
    )

    assert payload["status"] == "AWAITING_LOCAL_FINAL_ADJUDICATION"
    assert payload["missing_key_envs"] == []
    assert payload["provider_call_count"] == 0
    assert payload["roles"]["gpt55"] == "local_agent_final_adjudicator"
    assert payload["models"]["gpt55"] == "codex-gpt55-local-agent"
    assert payload["official_score_allowed"] is False


def test_fixture_cases_keep_blind_protocol_and_review_boundary(tmp_path):
    payload = _run_ab(tmp_path, "--mode", "fixture", "--max-samples", "1")
    case = payload["cases"][0]

    assert case["answer_id"]
    assert case["question_id"]
    assert case["qwen_blind_scores"]["artifact_first"]["blind_to_arm_name"] is True
    assert case["deepseek_prosecution"]["role"] == "adversarial_prosecutor"
    assert case["gpt55_adjudication"]["role"] == "final_adjudicator"
    assert case["final_adjudication"] == case["gpt55_adjudication"]
    assert case["gpt55_adjudication"]["official_score_allowed"] is False
    assert case["gpt55_adjudication"]["recommendation"] in {
        "artifact_first_wins",
        "baseline_wins",
        "tie",
        "send_to_review",
    }


def test_start_index_runs_a_stable_sample_window(tmp_path):
    payload = _run_ab(
        tmp_path,
        "--mode",
        "fixture",
        "--start-index",
        "1",
        "--max-samples",
        "1",
    )

    assert payload["sample_window"] == {"start_index": 1, "max_samples": 1}
    assert len(payload["cases"]) == 1
    assert payload["cases"][0]["answer_id"] == "M35-A002"


def test_fixture_mode_can_reverse_to_deepseek_primary_and_qwen_adversary(tmp_path):
    payload = _run_ab(
        tmp_path,
        "--mode",
        "fixture",
        "--max-samples",
        "1",
        "--scorer",
        "deepseek",
        "--adversary",
        "qwen",
        "--local-final-adjudicator",
    )
    case = payload["cases"][0]

    assert payload["roles"] == {
        "deepseek": "blind_scorer",
        "qwen": "adversarial_prosecutor",
        "gpt55": "local_agent_final_adjudicator",
    }
    assert payload["models"]["deepseek"] == "deepseek-v4-flash"
    assert payload["models"]["qwen"] == "qwen-flash"
    assert case["primary_scores"] == case["deepseek_blind_scores"]
    assert case["adversarial_review"] == case["qwen_prosecution"]
    assert case["final_adjudication"]["official_score_allowed"] is False


def test_artifact_preserves_mcq_overselect_penalty_protocol():
    spec = importlib.util.spec_from_file_location(
        "run_luban_m35_three_model_blind_ab",
        REPO / SCRIPT,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    artifact = module._artifact_for_sample(
        {
            "question_id": "MCQ-1",
            "question": {"source_refs": []},
            "generated_label": {
                "gold_point_matches": [],
                "scoring_points": [
                    {"point_id": "OPT_A", "criterion": "选择 A", "max_score": 1.0}
                ],
                "scoring_protocol": {
                    "question_type": "multiple_choice",
                    "overselect_policy": "zero_score_if_any_wrong_option_selected",
                    "correct_answer": "A",
                    "wrong_options": ["B", "C"],
                },
            },
        }
    )

    assert artifact["scoring_points"] == [
        {"point_id": "OPT_A", "criterion": "选择 A", "max_score": 1.0}
    ]
    assert artifact["scoring_protocol"]["overselect_policy"] == "zero_score_if_any_wrong_option_selected"


def test_remote_disconnected_provider_error_is_reported(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "run_luban_m35_three_model_blind_ab",
        REPO / SCRIPT,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    monkeypatch.setenv("DASHSCOPE_API_KEY", "qwen-present")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-present")
    monkeypatch.setattr(
        module,
        "_chat_json",
        lambda **_: (_ for _ in ()).throw(http.client.RemoteDisconnected("closed")),
    )

    payload = module.build_payload(
        fixture=REPO / FIXTURE,
        output=tmp_path / "out.json",
        mode="live",
        max_samples=1,
        timeout_seconds=1,
        local_final_adjudicator=True,
        scorer="deepseek",
        adversary="qwen",
    )

    assert payload["status"] == "BLOCKED_PROVIDER_ERROR"
    assert payload["error_type"] == "RemoteDisconnected"
    assert payload["provider_call_count"] == 0
