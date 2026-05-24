from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SOURCE_NAME = "zhongweiv/hermes-edu-skills"
DEFAULT_SOURCE = Path(os.getenv("HERMES_EDU_SOURCE", "~/.cache/deeptutor/hermes-edu-skills")).expanduser()

CONSTRUCTION_TARGETS: dict[str, tuple[str, list[str], str]] = {
    "agent-question-explanation": (
        "adapt_to_construction",
        ["construction-question-review"],
        "Question explanation workflow is useful, but answer reveal remains product-code authority.",
    ),
    "agent-socratic-tutor": (
        "adapt_to_construction",
        ["construction-question-review", "construction-learning-support"],
        "Socratic prompting can improve review turns; it cannot override grading or reveal policy.",
    ),
    "agent-mistake-review": (
        "adapt_to_construction",
        ["construction-learning-evidence-story", "construction-study-assistant"],
        "Mistake-review workflow is valuable; mistake book and learner evidence remain DeepTutor authorities.",
    ),
    "agent-learning-report": (
        "adapt_to_construction",
        ["construction-learning-evidence-story"],
        "Useful report narration shape; learning report read model remains the only truth source.",
    ),
    "agent-study-plan": (
        "adapt_to_construction",
        ["construction-study-assistant"],
        "Useful plan output shape; training intent remains the recommendation authority.",
    ),
    "adult-vocational-certificate": (
        "adapt_to_construction",
        ["construction-study-assistant", "construction-question-supply"],
        "Closest upstream exam-prep analogue for adult construction certification.",
    ),
}

FUTURE_CATEGORIES = {"preschool"}
SANDBOX_CATEGORIES = {"family-education"}
INTERNAL_OPS_CATEGORIES = {"teacher-tools"}

CONSTRUCTION_RELEVANCE_PATTERN = re.compile(
    r"adult|vocational|construction|建筑|施工|建造|一级|二级|建工",
    re.IGNORECASE,
)


def _skill_name(skill: dict[str, Any]) -> str:
    return str(skill.get("name") or skill.get("slug") or "").strip()


def _search_text(skill: dict[str, Any]) -> str:
    values: list[str] = []
    for key in (
        "name",
        "slug",
        "title",
        "description",
        "category",
        "path",
    ):
        value = skill.get(key)
        if isinstance(value, str):
            values.append(value)
    for key in ("tags", "subjects", "abilities", "scenarios"):
        value = skill.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
    return " ".join(values).lower()


def classify_skill(skill: dict[str, Any]) -> dict[str, Any]:
    name = _skill_name(skill)
    category = str(skill.get("category") or "unknown")
    text = _search_text(skill)

    if name in CONSTRUCTION_TARGETS:
        bucket, targets, notes = CONSTRUCTION_TARGETS[name]
        return {
            "deep_tutor_bucket": bucket,
            "deep_tutor_targets": targets,
            "authority_risk": "medium",
            "rewrite_required": "heavy",
            "recommended_phase": "P0",
            "notes": notes,
        }

    if category in INTERNAL_OPS_CATEGORIES:
        return {
            "deep_tutor_bucket": "developer_ops",
            "deep_tutor_targets": ["teacher_internal_tools"],
            "authority_risk": "medium",
            "rewrite_required": "heavy",
            "recommended_phase": "P2",
            "notes": "Teacher-tool workflow may boost BI or教研 surfaces, but must not become student runtime authority.",
        }

    if category in SANDBOX_CATEGORIES:
        return {
            "deep_tutor_bucket": "sandbox_experiment",
            "deep_tutor_targets": ["hermes_weixin_sandbox"],
            "authority_risk": "medium",
            "rewrite_required": "heavy",
            "recommended_phase": "sandbox",
            "notes": "Family education patterns can be tested in Hermes/Weixin, not production learner state.",
        }

    if category in FUTURE_CATEGORIES:
        return {
            "deep_tutor_bucket": "future_product",
            "deep_tutor_targets": [],
            "authority_risk": "low",
            "rewrite_required": "reject_for_now",
            "recommended_phase": "future",
            "notes": "Outside current construction-exam scope.",
        }

    if category == "daily-practice":
        if CONSTRUCTION_RELEVANCE_PATTERN.search(text):
            return {
                "deep_tutor_bucket": "adapt_to_construction",
                "deep_tutor_targets": ["construction-question-supply"],
                "authority_risk": "medium",
                "rewrite_required": "heavy",
                "recommended_phase": "P1",
                "notes": "Construction-relevant short-practice cadence is useful; question generation remains deep_question authority.",
            }
        return {
            "deep_tutor_bucket": "template_only",
            "deep_tutor_targets": [],
            "authority_risk": "low",
            "rewrite_required": "heavy",
            "recommended_phase": "P2",
            "notes": "Generic short-practice cadence can inspire UX only; this skill is not a confirmed construction translation target.",
        }

    if category == "exam-prep":
        return {
            "deep_tutor_bucket": "template_only",
            "deep_tutor_targets": ["construction-study-assistant"],
            "authority_risk": "medium",
            "rewrite_required": "heavy",
            "recommended_phase": "P1",
            "notes": "Exam-prep structure may be reused, but construction exam content must be rewritten.",
        }

    if category == "reading-writing" or "writing" in text or "表达" in text:
        return {
            "deep_tutor_bucket": "template_only",
            "deep_tutor_targets": ["construction-case-grading"],
            "authority_risk": "low",
            "rewrite_required": "light",
            "recommended_phase": "P2",
            "notes": "Expression-improvement pattern can help case-answer rewrite, not scoring.",
        }

    if category == "textbook-sync":
        return {
            "deep_tutor_bucket": "future_product",
            "deep_tutor_targets": ["construction_kb_sync"],
            "authority_risk": "high",
            "rewrite_required": "heavy",
            "recommended_phase": "P2",
            "notes": "Textbook-sync shape is interesting, but construction KB and RAG provenance stay authoritative.",
        }

    if category == "learning-assistant":
        return {
            "deep_tutor_bucket": "template_only",
            "deep_tutor_targets": ["construction-question-review"],
            "authority_risk": "medium",
            "rewrite_required": "heavy",
            "recommended_phase": "P1",
            "notes": "General learning workflow may be useful after construction-specific translation.",
        }

    return {
        "deep_tutor_bucket": "reject_due_authority_risk",
        "deep_tutor_targets": [],
        "authority_risk": "high",
        "rewrite_required": "reject",
        "recommended_phase": "none",
        "notes": "No clear DeepTutor mapping.",
    }


def load_catalog(source: Path) -> dict[str, Any]:
    catalog_path = source / "catalog.json" if source.is_dir() else source
    with catalog_path.open("r", encoding="utf-8") as handle:
        catalog = json.load(handle)
    if not isinstance(catalog, dict) or not isinstance(catalog.get("skills"), list):
        raise ValueError(f"Invalid Hermes Edu catalog: {catalog_path}")
    return catalog


def build_inventory(catalog: dict[str, Any], *, generated_at: str | None = None) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    skills: list[dict[str, Any]] = []

    for skill in catalog["skills"]:
        classification = classify_skill(skill)
        skills.append(
            {
                "name": _skill_name(skill),
                "category": skill.get("category") or "unknown",
                "upstream_path": skill.get("path") or "",
                "description": skill.get("description") or "",
                **classification,
            }
        )

    bucket_counts = Counter(item["deep_tutor_bucket"] for item in skills)
    category_counts = Counter(item["category"] for item in skills)
    risk_counts = Counter(item["authority_risk"] for item in skills)

    return {
        "source": SOURCE_NAME,
        "version": catalog.get("version"),
        "license": catalog.get("license"),
        "license_obligations": {
            "license": catalog.get("license") or "unknown",
            "policy": "Pattern-only inspiration may be recorded in frontmatter. Partial-text or verbatim derivations must preserve MIT attribution in the target skill.",
            "required_notice_when_copying_text": "Preserve upstream copyright and permission notice for MIT-licensed text.",
        },
        "generated_at": generated_at,
        "skill_count": len(skills),
        "summary": {
            "by_bucket": dict(sorted(bucket_counts.items())),
            "by_category": dict(sorted(category_counts.items())),
            "by_authority_risk": dict(sorted(risk_counts.items())),
        },
        "skills": skills,
    }


def write_inventory(inventory: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a DeepTutor absorption inventory for hermes-edu-skills.")
    parser.add_argument(
        "--source",
        default=str(DEFAULT_SOURCE),
        help="Path to hermes-edu-skills checkout or catalog.json. Defaults to HERMES_EDU_SOURCE or ~/.cache/deeptutor/hermes-edu-skills.",
    )
    parser.add_argument("--output", help="Optional output JSON path.")
    args = parser.parse_args(argv)

    inventory = build_inventory(load_catalog(Path(args.source)))
    if args.output:
        write_inventory(inventory, Path(args.output))
    else:
        print(json.dumps(inventory, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
