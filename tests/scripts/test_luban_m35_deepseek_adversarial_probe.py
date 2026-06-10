import json
import os
import subprocess
from pathlib import Path

from scripts.run_luban_m35_deepseek_adversarial_probe import (
    _extract_json_object,
    _samples,
)


SCRIPT = "scripts/run_luban_m35_deepseek_adversarial_probe.py"
FIXTURE = "tests/fixtures/luban_m35_case_scoring"


def _run_probe(tmp_path: Path, *args: str, env: dict[str, str] | None = None) -> dict:
    out = tmp_path / "deepseek_probe.json"
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


def test_fixture_mode_writes_deepseek_candidate_report_without_truth_or_provider_call(tmp_path):
    payload = _run_probe(tmp_path, "--mode", "fixture", "--max-samples", "1")

    assert payload["mode"] == "fixture"
    assert payload["provider_call_count"] == 0
    assert payload["production_write_count"] == 0
    assert payload["canonical_truth_written"] is False
    assert payload["official_score_allowed"] is False
    assert payload["promote_to_release"] is False
    assert payload["runtime_usable_as_truth"] is False
    assert payload["reports"][0]["origin"] == "deepseek_v4_pro_adversarial"
    assert payload["reports"][0]["role"] == "adversarial_prosecutor"


def test_live_mode_without_key_blocks_without_secret_or_network_claim(tmp_path):
    payload = _run_probe(
        tmp_path,
        "--mode",
        "live",
        "--max-samples",
        "1",
        env={"DEEPSEEK_API_KEY": "", "DEEPSEEK_SECRET_SENTINEL": "sk-test-secret"},
    )

    assert payload["mode"] == "live"
    assert payload["status"] == "BLOCKED_MISSING_DEEPSEEK_API_KEY"
    assert payload["provider_call_count"] == 0
    assert "sk-test-secret" not in json.dumps(payload)
    assert payload["canonical_truth_written"] is False
    assert payload["official_score_allowed"] is False


def test_fixture_report_preserves_question_and_answer_ids_for_audit_trace(tmp_path):
    payload = _run_probe(tmp_path, "--mode", "fixture", "--max-samples", "2")

    report_refs = [
        (report["question_id"], report["answer_id"])
        for report in payload["reports"]
    ]

    assert len(report_refs) == 2
    assert all(question_id and answer_id for question_id, answer_id in report_refs)
    assert payload["adversarial_role"] == "prosecutor"


def test_extract_json_object_from_fenced_or_prefaced_provider_reply():
    text = """```json
{"source_challenges": [], "rubric_attacks": [], "suggested_demotions": [], "unresolved_objection_count": 0}
```"""

    assert _extract_json_object(text)["unresolved_objection_count"] == 0


def test_probe_samples_keep_live_prompt_bounded():
    sample = _samples(Path(FIXTURE), 1)[0]

    assert len(sample["question"]["stem"]) <= 1800
    assert len(sample["student_answer"]) <= 1800
