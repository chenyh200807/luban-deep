from __future__ import annotations

from pathlib import Path

from scripts.audit_frontend_inference import audit_frontend_inference_paths


def test_audit_frontend_inference_rejects_threshold_derived_mastery(tmp_path: Path) -> None:
    source = tmp_path / "bad.js"
    source.write_text(
        "var level = score >= 70 ? 'strong' : score >= 40 ? 'normal' : 'weak';\n",
        encoding="utf-8",
    )

    report = audit_frontend_inference_paths([source])

    assert report["ok"] is False
    assert report["violations"][0]["path"].endswith("bad.js")


def test_audit_frontend_inference_accepts_backend_field_mapping(tmp_path: Path) -> None:
    source = tmp_path / "good.js"
    source.write_text(
        "return { level: source.level || 'observed', promptIntent: source.intent || {} };\n",
        encoding="utf-8",
    )

    report = audit_frontend_inference_paths([source])

    assert report["ok"] is True
    assert report["violations"] == []


def test_audit_frontend_inference_rejects_frontend_training_plan_text(tmp_path: Path) -> None:
    source = tmp_path / "bad-plan.js"
    source.write_text(
        "var priorityTask = '先围绕薄弱点做 3 题';\n"
        "var studyMethod = '系统建议先复盘再训练';\n"
        "var coachNote = '今天重点突破这个错因';\n",
        encoding="utf-8",
    )

    report = audit_frontend_inference_paths([source])

    assert report["ok"] is False
    assert {item["rule"] for item in report["violations"]} == {
        "frontend_training_plan_text"
    }


def test_audit_frontend_inference_rejects_frontend_weak_rank_sort(tmp_path: Path) -> None:
    source = tmp_path / "bad-rank.js"
    source.write_text(
        "var dimList = dims.slice().sort(function (a, b) { return (a.value || 0) - (b.value || 0); });\n",
        encoding="utf-8",
    )

    report = audit_frontend_inference_paths([source])

    assert report["ok"] is False
    assert report["violations"][0]["rule"] == "frontend_weak_rank_sort"


def test_audit_frontend_inference_rejects_learning_brain_fallback_training(tmp_path: Path) -> None:
    source = tmp_path / "bad-training-fallback.js"
    source.write_text(
        "training.push({ title: '围绕薄弱点做变式训练', meta: weak.error_code });\n",
        encoding="utf-8",
    )

    report = audit_frontend_inference_paths([source])

    assert report["ok"] is False
    assert report["violations"][0]["rule"] == "frontend_training_fallback"
