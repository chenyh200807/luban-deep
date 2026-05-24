from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = REPO_ROOT / "deeptutor" / "tutorbot" / "skills" / "catalog.yaml"
DEFAULT_SKILLS_ROOT = REPO_ROOT / "deeptutor" / "tutorbot" / "skills"
DEFAULT_INVENTORY = REPO_ROOT / "docs" / "plan" / "artifacts" / "hermes-edu-skills-inventory.json"
EXPORT_ELIGIBLE_VALUES = {"public", "internal", "none"}

REQUIRED_SKILL_FIELDS = {
    "name",
    "path",
    "subject",
    "scene",
    "runtime_scope",
    "authority_scope",
    "token_budget_estimate",
    "export_eligible",
    "required_authorities",
    "forbidden_authorities",
    "references",
    "trace_fields",
}

SECTION_ALIASES = {
    "authority": ("## Authority", "## 单一 Authority", "## 单一 authority", "## 单一权威", "## Single Authority"),
    "forbidden_authority": (
        "## Forbidden Authority",
        "## 禁止 Authority",
        "## 禁止事项",
        "## 不应承担的职责",
    ),
    "anti_patterns": ("## Anti-Patterns", "## 反模式", "## 禁止反模式"),
}

SECRET_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"api[_-]?key",
        r"access[_-]?token",
        r"refresh[_-]?token",
        r"database[_-]?url",
        r"private[_-]?key",
        r"client[_-]?secret",
        r"password",
        r"credential",
        r"production[_-]?secret",
        r"internal[_-]?account",
    )
]

EXPRESSION_ONLY_AUTHORITY_SCOPES = {
    "narration_policy",
    "presentation_policy",
    "safety_support_policy",
    "topic_map",
}

EXPRESSION_LAYER_FORBIDDEN_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"learner_memory_events",
        r"learner_summaries",
        r"learner_mistake_book_items",
        r"\bselect\b.+\bfrom\b",
        r"\bupdate\b.+\bset\b",
        r"mastery\s*[><=]",
        r"score\s*[><=]\s*\d",
        r"threshold",
        r"prescription",
        r"recommend.*\d+.*题",
        r"grade\s*=",
    )
]

RUNTIME_CATALOG_IMPORT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"catalog\.yaml",
    )
]


@dataclass(frozen=True)
class Finding:
    severity: str
    skill: str
    rule: str
    message: str


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid skill catalog: {path}")
    return data


def _frontmatter_name(content: str) -> str:
    match = re.search(r"^name:\s*['\"]?([^'\"\r\n]+)['\"]?\s*$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _frontmatter(content: str) -> dict[str, Any]:
    match = re.match(r"^---\s*\n([\s\S]*?)\n---\s*", content)
    if not match:
        return {}
    data = yaml.safe_load(match.group(1))
    return data if isinstance(data, dict) else {}


def _has_section(content: str, aliases: tuple[str, ...]) -> bool:
    lowered = content.lower()
    return any(alias.lower() in lowered for alias in aliases)


def _count_anti_pattern_items(content: str) -> int:
    match = re.search(r"^##\s+(?:Anti-Patterns|反模式|禁止反模式)\s*$([\s\S]*?)(?:^##\s+|\Z)", content, re.MULTILINE)
    if not match:
        return 0
    return len(re.findall(r"^\s*[-*]\s+\S+", match.group(1), re.MULTILINE))


def _is_expression_only_skill(skill: dict[str, Any]) -> bool:
    name = str(skill.get("name", ""))
    authority_scope = str(skill.get("authority_scope", ""))
    return "narration" in name or authority_scope in EXPRESSION_ONLY_AUTHORITY_SCOPES


def _has_safety_escalation(content: str) -> bool:
    has_section = re.search(r"^##\s+Safety Escalation\s*$", content, re.MULTILINE | re.IGNORECASE)
    has_risk_phrase = re.search(r"自我伤害|心理危机|极端情绪|严重焦虑", content)
    has_action_phrase = re.search(r"升级|人工|exit_skill|safety_escalation", content, re.IGNORECASE)
    return bool(has_section and has_risk_phrase and has_action_phrase)


def _catalog_runtime_import_findings(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    roots = [
        repo_root / "deeptutor" / "api",
        repo_root / "deeptutor" / "runtime",
        repo_root / "deeptutor" / "services",
        repo_root / "deeptutor" / "capabilities",
        repo_root / "deeptutor" / "tutorbot",
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "skills" in path.relative_to(repo_root).parts:
                continue
            content = path.read_text(encoding="utf-8")
            for pattern in RUNTIME_CATALOG_IMPORT_PATTERNS:
                if pattern.search(content):
                    findings.append(
                        Finding(
                            "error",
                            "<runtime>",
                            "catalog_runtime_import",
                            f"runtime code must not import catalog.yaml: {path.relative_to(repo_root)}",
                        )
                    )
                    break
    return findings


def validate_catalog(
    catalog_path: Path = DEFAULT_CATALOG,
    *,
    skills_root: Path = DEFAULT_SKILLS_ROOT,
    strict: bool = False,
) -> dict[str, Any]:
    findings: list[Finding] = []
    findings.extend(_catalog_runtime_import_findings(REPO_ROOT))
    catalog = _load_yaml(catalog_path)
    skills = catalog.get("skills")
    if not isinstance(skills, list):
        findings.append(Finding("error", "<catalog>", "shape", "catalog.skills must be a list"))
        skills = []

    names: set[str] = set()
    for index, skill in enumerate(skills):
        if not isinstance(skill, dict):
            findings.append(Finding("error", f"<skill:{index}>", "shape", "skill entry must be an object"))
            continue

        name = str(skill.get("name") or f"<skill:{index}>")
        missing = sorted(REQUIRED_SKILL_FIELDS - set(skill))
        if missing:
            findings.append(Finding("error", name, "missing_fields", f"missing fields: {', '.join(missing)}"))

        export_eligible = str(skill.get("export_eligible") or "").strip()
        if export_eligible and export_eligible not in EXPORT_ELIGIBLE_VALUES:
            findings.append(
                Finding(
                    "error",
                    name,
                    "invalid_export_eligible",
                    "export_eligible must be one of: public, internal, none",
                )
            )

        if name in names:
            findings.append(Finding("error", name, "duplicate_name", "duplicate skill name"))
        names.add(name)

        relative_path = str(skill.get("path") or "")
        skill_path = skills_root / relative_path
        if not skill_path.exists():
            findings.append(Finding("error", name, "missing_skill_file", f"missing skill file: {relative_path}"))
            continue

        content = skill_path.read_text(encoding="utf-8")
        line_count = len(content.splitlines())
        if line_count > 300:
            findings.append(Finding("error", name, "skill_line_count", f"SKILL.md has {line_count} lines; max 300"))
        elif line_count > 200:
            findings.append(Finding("warn", name, "skill_line_count", f"SKILL.md has {line_count} lines; prefer <=200"))

        frontmatter = _frontmatter(content)
        frontmatter_name = _frontmatter_name(content)
        if frontmatter_name != name:
            findings.append(
                Finding(
                    "error",
                    name,
                    "frontmatter_name",
                    f"frontmatter name {frontmatter_name!r} does not match catalog name {name!r}",
                )
            )

        for reference in skill.get("references") or []:
            reference_path = skills_root / str(reference)
            if not reference_path.exists():
                findings.append(Finding("error", name, "missing_reference", f"missing reference: {reference}"))

        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                findings.append(Finding("error", name, "secret_pattern", f"skill content matches {pattern.pattern}"))

        if _is_expression_only_skill(skill):
            for pattern in EXPRESSION_LAYER_FORBIDDEN_PATTERNS:
                if pattern.search(content):
                    findings.append(
                        Finding(
                            "error",
                            name,
                            "expression_authority_leak",
                            f"expression-layer skill matches {pattern.pattern}",
                        )
                    )

        upstream = frontmatter.get("upstream_inspiration") if isinstance(frontmatter, dict) else None
        if isinstance(upstream, dict):
            derivation = str(upstream.get("derivation") or "").strip()
            if not derivation:
                findings.append(
                    Finding(
                        "error",
                        name,
                        "missing_upstream_derivation",
                        "upstream_inspiration requires derivation: pattern-only | partial-text | verbatim",
                    )
                )
            if derivation in {"partial-text", "verbatim"} and not _has_section(content, ("## Attribution",)):
                findings.append(
                    Finding(
                        "error",
                        name,
                        "missing_attribution",
                        "partial-text or verbatim upstream derivation requires an Attribution section",
                    )
                )

        if str(skill.get("authority_scope")) == "safety_support_policy" and not _has_safety_escalation(content):
            findings.append(
                Finding(
                    "error",
                    name,
                    "missing_safety_escalation",
                    "safety_support_policy skill must define Safety Escalation with risk and escalation phrases",
                )
            )

        if strict and str(skill.get("runtime_scope")) == "production":
            for rule, aliases in SECTION_ALIASES.items():
                if not _has_section(content, aliases):
                    findings.append(Finding("error", name, f"missing_{rule}", f"missing section: {aliases[0]}"))
            if _count_anti_pattern_items(content) < 3:
                findings.append(
                    Finding("error", name, "anti_patterns_count", "production skill needs at least 3 anti-pattern items")
                )
        elif str(skill.get("runtime_scope")) == "production":
            for rule, aliases in SECTION_ALIASES.items():
                if not _has_section(content, aliases):
                    findings.append(Finding("warn", name, f"missing_{rule}", f"missing section: {aliases[0]}"))

    errors = [finding for finding in findings if finding.severity == "error"]
    warnings = [finding for finding in findings if finding.severity == "warn"]
    return {
        "ok": not errors,
        "strict": strict,
        "skill_count": len(skills),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "findings": [asdict(finding) for finding in findings],
    }


def build_doctor_report(
    *,
    catalog_path: Path = DEFAULT_CATALOG,
    inventory_path: Path = DEFAULT_INVENTORY,
) -> dict[str, Any]:
    catalog = _load_yaml(catalog_path)
    catalog_skills = catalog.get("skills")
    if not isinstance(catalog_skills, list):
        catalog_skills = []
    catalog_names = {str(skill.get("name")) for skill in catalog_skills if isinstance(skill, dict)}

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory_skills = inventory.get("skills") if isinstance(inventory, dict) else None
    if not isinstance(inventory_skills, list):
        raise ValueError(f"Invalid Hermes inventory: {inventory_path}")

    checked: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for item in inventory_skills:
        if not isinstance(item, dict) or item.get("deep_tutor_bucket") != "adapt_to_construction":
            continue
        targets = [str(target) for target in item.get("deep_tutor_targets") or [] if str(target)]
        missing_targets = [target for target in targets if target not in catalog_names]
        checked.append(
            {
                "upstream_skill": str(item.get("name") or ""),
                "targets": targets,
                "missing_targets": missing_targets,
            }
        )
        if missing_targets:
            gaps.append(
                {
                    "upstream_skill": str(item.get("name") or ""),
                    "missing_targets": missing_targets,
                }
            )

    return {
        "ok": not gaps,
        "catalog_skill_count": len(catalog_names),
        "adapt_to_construction_count": len(checked),
        "gap_count": len(gaps),
        "checked": checked,
        "gaps": gaps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate DeepTutor TutorBot skill registry.")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG), help="Path to deeptutor/tutorbot/skills/catalog.yaml.")
    parser.add_argument("--skills-root", default=str(DEFAULT_SKILLS_ROOT), help="Path to skill root directory.")
    parser.add_argument("--inventory", default=str(DEFAULT_INVENTORY), help="Path to Hermes inventory JSON.")
    parser.add_argument("--strict", action="store_true", help="Fail on missing authority/anti-pattern sections.")
    parser.add_argument("--doctor", action="store_true", help="Print inventory-to-catalog absorption gap report.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args(argv)

    report = validate_catalog(Path(args.catalog), skills_root=Path(args.skills_root), strict=args.strict)
    doctor_report = None
    if args.doctor:
        doctor_report = build_doctor_report(catalog_path=Path(args.catalog), inventory_path=Path(args.inventory))
        report["doctor"] = doctor_report

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "ok" if report["ok"] else "failed"
        print(
            f"DeepTutor TutorBot Skill Validator: {status}; "
            f"skills={report['skill_count']} errors={report['error_count']} warnings={report['warning_count']}"
        )
        for finding in report["findings"]:
            print(f"[{finding['severity']}] {finding['skill']} {finding['rule']}: {finding['message']}")
        if doctor_report is not None:
            print(
                "Doctor inventory gap report: "
                f"adapt_to_construction={doctor_report['adapt_to_construction_count']} "
                f"gaps={doctor_report['gap_count']}"
            )
            for gap in doctor_report["gaps"]:
                missing = ", ".join(gap["missing_targets"])
                print(f"[doctor] {gap['upstream_skill']}: missing catalog targets: {missing}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
