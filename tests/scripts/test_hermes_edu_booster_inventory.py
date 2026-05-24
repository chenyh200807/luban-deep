from __future__ import annotations

import json
from pathlib import Path

from scripts.hermes_edu_booster_inventory import build_inventory, load_catalog, main


def _catalog(skills: list[dict]) -> dict:
    return {
        "name": "hermes-edu-skills",
        "version": "0.18.6",
        "license": "MIT",
        "skills": skills,
    }


def test_maps_high_signal_learning_skills_to_construction_targets() -> None:
    inventory = build_inventory(
        _catalog(
            [
                {
                    "name": "agent-question-explanation",
                    "category": "learning-assistant",
                    "path": "skills/learning-assistant/agent-question-explanation/SKILL.md",
                    "description": "AI 讲题",
                },
                {
                    "name": "agent-mistake-review",
                    "category": "learning-assistant",
                    "path": "skills/learning-assistant/agent-mistake-review/SKILL.md",
                    "description": "错题复盘",
                },
            ]
        ),
        generated_at="2026-05-24T00:00:00Z",
    )

    by_name = {item["name"]: item for item in inventory["skills"]}

    assert by_name["agent-question-explanation"]["deep_tutor_bucket"] == "adapt_to_construction"
    assert by_name["agent-question-explanation"]["deep_tutor_targets"] == ["construction-question-review"]
    assert by_name["agent-mistake-review"]["deep_tutor_targets"] == [
        "construction-learning-evidence-story",
        "construction-study-assistant",
    ]


def test_classifies_teacher_and_preschool_as_non_student_runtime() -> None:
    inventory = build_inventory(
        _catalog(
            [
                {
                    "name": "teacher-math-lesson-planning",
                    "category": "teacher-tools",
                    "path": "skills/teacher-tools/teacher-math-lesson-planning/SKILL.md",
                },
                {
                    "name": "preschool-number-sense-foundation",
                    "category": "preschool",
                    "path": "skills/preschool/preschool-number-sense-foundation/SKILL.md",
                },
            ]
        ),
        generated_at="2026-05-24T00:00:00Z",
    )

    by_name = {item["name"]: item for item in inventory["skills"]}

    assert by_name["teacher-math-lesson-planning"]["deep_tutor_bucket"] == "developer_ops"
    assert by_name["teacher-math-lesson-planning"]["recommended_phase"] == "P2"
    assert by_name["preschool-number-sense-foundation"]["deep_tutor_bucket"] == "future_product"
    assert by_name["preschool-number-sense-foundation"]["recommended_phase"] == "future"


def test_daily_practice_requires_construction_relevance_for_adaptation() -> None:
    inventory = build_inventory(
        _catalog(
            [
                {
                    "name": "junior-biology-quick-practice",
                    "category": "daily-practice",
                    "path": "skills/daily-practice/junior-biology-quick-practice/SKILL.md",
                    "description": "初中生物刷题",
                },
                {
                    "name": "construction-quick-practice",
                    "category": "daily-practice",
                    "path": "skills/daily-practice/construction-quick-practice/SKILL.md",
                    "description": "建筑施工专项练习",
                },
            ]
        ),
        generated_at="2026-05-24T00:00:00Z",
    )

    by_name = {item["name"]: item for item in inventory["skills"]}

    assert by_name["junior-biology-quick-practice"]["deep_tutor_bucket"] == "template_only"
    assert by_name["junior-biology-quick-practice"]["recommended_phase"] == "P2"
    assert by_name["construction-quick-practice"]["deep_tutor_bucket"] == "adapt_to_construction"
    assert by_name["construction-quick-practice"]["deep_tutor_targets"] == ["construction-question-supply"]
    assert inventory["license_obligations"]["license"] == "MIT"


def test_cli_writes_inventory_from_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "hermes-edu-skills"
    checkout.mkdir()
    (checkout / "catalog.json").write_text(
        json.dumps(
            _catalog(
                [
                    {
                        "name": "adult-vocational-certificate",
                        "category": "exam-prep",
                        "path": "skills/exam-prep/adult-vocational-certificate/SKILL.md",
                    }
                ]
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "inventory.json"

    assert main(["--source", str(checkout), "--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["skill_count"] == 1
    assert written["skills"][0]["deep_tutor_targets"] == [
        "construction-study-assistant",
        "construction-question-supply",
    ]


def test_load_catalog_rejects_invalid_shape(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"skills": {}}), encoding="utf-8")

    try:
        load_catalog(catalog)
    except ValueError as exc:
        assert "Invalid Hermes Edu catalog" in str(exc)
    else:
        raise AssertionError("expected invalid catalog to raise")
