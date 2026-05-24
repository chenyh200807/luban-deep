from __future__ import annotations

from pathlib import Path

import yaml

import scripts.validate_tutorbot_skills as validator
from scripts.validate_tutorbot_skills import main, validate_catalog


def _write_skill(root: Path, name: str, body: str = "") -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test skill\n---\n\n# {name}\n\n{body}\n",
        encoding="utf-8",
    )


def _write_catalog(path: Path, skills: list[dict]) -> None:
    path.write_text(
        yaml.safe_dump({"version": 1, "skills": skills}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _entry(name: str, **extra) -> dict:
    entry = {
        "name": name,
        "path": f"{name}/SKILL.md",
        "subject": "construction_exam",
        "scene": "question_review",
        "runtime_scope": "production",
        "authority_scope": "presentation_policy",
        "token_budget_estimate": 800,
        "required_authorities": ["rag"],
        "forbidden_authorities": ["scoring"],
        "references": [],
        "trace_fields": ["skill_stack"],
    }
    entry.update(extra)
    return entry


def test_basic_validation_accepts_existing_file_with_warnings(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    _write_skill(skills_root, "construction-question-review")
    catalog = tmp_path / "catalog.yaml"
    _write_catalog(catalog, [_entry("construction-question-review")])

    report = validate_catalog(catalog, skills_root=skills_root)

    assert report["ok"] is True
    assert report["error_count"] == 0
    assert report["warning_count"] >= 1
    assert {item["rule"] for item in report["findings"]} >= {"missing_authority"}


def test_strict_validation_requires_authority_and_anti_patterns(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    _write_skill(skills_root, "construction-question-review")
    catalog = tmp_path / "catalog.yaml"
    _write_catalog(catalog, [_entry("construction-question-review")])

    report = validate_catalog(catalog, skills_root=skills_root, strict=True)

    assert report["ok"] is False
    assert report["error_count"] >= 3
    assert {item["rule"] for item in report["findings"]} >= {
        "missing_authority",
        "missing_forbidden_authority",
        "missing_anti_patterns",
        "anti_patterns_count",
    }


def test_strict_validation_accepts_required_sections(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    _write_skill(
        skills_root,
        "construction-question-review",
        "\n".join(
            [
                "## Authority",
                "Read active question and RAG evidence only.",
                "## Forbidden Authority",
                "Never score or write learner state.",
                "## Anti-Patterns",
                "- Do not reveal hidden answers.",
                "- Do not compute mastery.",
                "- Do not route the turn.",
            ]
        ),
    )
    catalog = tmp_path / "catalog.yaml"
    _write_catalog(catalog, [_entry("construction-question-review")])

    report = validate_catalog(catalog, skills_root=skills_root, strict=True)

    assert report["ok"] is True
    assert report["error_count"] == 0


def test_validation_fails_for_missing_references(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    _write_skill(skills_root, "construction-question-review")
    catalog = tmp_path / "catalog.yaml"
    _write_catalog(catalog, [_entry("construction-question-review", references=["missing/reference.md"])])

    report = validate_catalog(catalog, skills_root=skills_root)

    assert report["ok"] is False
    assert report["findings"][0]["rule"] == "missing_reference"


def test_expression_layer_skill_cannot_embed_authority_leaks(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    _write_skill(
        skills_root,
        "construction-study-assistant",
        "Use SELECT * FROM learner_memory_events to compute mastery >= 70 and recommend 10 题.",
    )
    catalog = tmp_path / "catalog.yaml"
    _write_catalog(
        catalog,
        [
            _entry(
                "construction-study-assistant",
                authority_scope="presentation_policy",
            )
        ],
    )

    report = validate_catalog(catalog, skills_root=skills_root)

    assert report["ok"] is False
    assert {item["rule"] for item in report["findings"]} >= {"expression_authority_leak"}


def test_safety_support_policy_requires_escalation_section(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    _write_skill(
        skills_root,
        "construction-learning-support",
        "\n".join(
            [
                "## Authority",
                "Support only.",
                "## Forbidden Authority",
                "Never diagnose.",
                "## Anti-Patterns",
                "- Do not grade.",
                "- Do not plan.",
                "- Do not write state.",
            ]
        ),
    )
    catalog = tmp_path / "catalog.yaml"
    _write_catalog(
        catalog,
        [_entry("construction-learning-support", authority_scope="safety_support_policy")],
    )

    report = validate_catalog(catalog, skills_root=skills_root, strict=True)

    assert report["ok"] is False
    assert {item["rule"] for item in report["findings"]} >= {"missing_safety_escalation"}


def test_partial_text_derivation_requires_attribution_section(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    skill_dir = skills_root / "construction-question-review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: construction-question-review",
                "description: test skill",
                "upstream_inspiration:",
                "  source: zhongweiv/hermes-edu-skills@v0.18.6",
                "  skill: agent-question-explanation",
                "  license: MIT",
                "  derivation: partial-text",
                "---",
                "",
                "## Authority",
                "Read only.",
                "## Forbidden Authority",
                "Do not score.",
                "## Anti-Patterns",
                "- Do not reveal answers.",
                "- Do not grade.",
                "- Do not route.",
            ]
        ),
        encoding="utf-8",
    )
    catalog = tmp_path / "catalog.yaml"
    _write_catalog(catalog, [_entry("construction-question-review")])

    report = validate_catalog(catalog, skills_root=skills_root, strict=True)

    assert report["ok"] is False
    assert {item["rule"] for item in report["findings"]} >= {"missing_attribution"}


def test_runtime_catalog_import_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_repo = tmp_path / "repo"
    runtime_dir = fake_repo / "deeptutor" / "services"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "bad_loader.py").write_text('CATALOG = "catalog.yaml"\n', encoding="utf-8")
    skills_root = fake_repo / "deeptutor" / "tutorbot" / "skills"
    skills_root.mkdir(parents=True)
    _write_skill(
        skills_root,
        "construction-question-review",
        "\n".join(
            [
                "## Authority",
                "Read only.",
                "## Forbidden Authority",
                "Do not score.",
                "## Anti-Patterns",
                "- Do not reveal answers.",
                "- Do not grade.",
                "- Do not route.",
            ]
        ),
    )
    catalog = skills_root / "catalog.yaml"
    _write_catalog(catalog, [_entry("construction-question-review")])
    monkeypatch.setattr(validator, "REPO_ROOT", fake_repo)

    report = validate_catalog(catalog, skills_root=skills_root, strict=True)

    assert report["ok"] is False
    assert {item["rule"] for item in report["findings"]} >= {"catalog_runtime_import"}


def test_cli_returns_nonzero_on_missing_file(tmp_path: Path) -> None:
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    catalog = tmp_path / "catalog.yaml"
    _write_catalog(catalog, [_entry("missing-skill")])

    assert main(["--catalog", str(catalog), "--skills-root", str(skills_root)]) == 1
