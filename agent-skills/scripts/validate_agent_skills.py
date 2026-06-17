#!/usr/bin/env python3
"""Validate DeepTutor repo-local agent skills and routing indexes."""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "agent-skills"
README = SKILL_ROOT / "README.md"
AGENTS = ROOT / "AGENTS.md"
CATALOG = SKILL_ROOT / "catalog.yaml"


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
FIELD_RE = re.compile(r"^(name|description):\s*(.*)$", re.MULTILINE)
LINK_RE = re.compile(r"\]\((\./agent-skills/[^)]+)\)")
CATALOG_FIELD_RE = re.compile(r"^\s{4}([a-z_]+):\s*(.+?)\s*$")
BACKTICK_RE = re.compile(r"`([^`]+)`")


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("missing YAML frontmatter")
    fields = {}
    for key, value in FIELD_RE.findall(match.group(1)):
        fields[key] = value.strip().strip('"').strip("'")
    return fields


def parse_catalog(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    if "source_root: agent-skills" not in text:
        raise ValueError("catalog must declare source_root: agent-skills")
    if "authority_boundary: catalog-is-validation-index-not-runtime-loader" not in text:
        raise ValueError("catalog must declare that it is not a runtime loader")
    if "description_authority: SKILL.md-frontmatter" not in text:
        raise ValueError("catalog must keep SKILL.md frontmatter as description authority")

    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- name: "):
            if current is not None:
                entries.append(current)
            current = {"name": stripped.removeprefix("- name: ").strip()}
            continue
        if current is None:
            continue
        match = CATALOG_FIELD_RE.match(line)
        if match:
            current[match.group(1)] = match.group(2).strip()
    if current is not None:
        entries.append(current)
    return entries


def validate_catalog(skill_files: list[Path]) -> list[str]:
    errors: list[str] = []
    if not CATALOG.exists():
        return ["agent-skills/catalog.yaml: missing catalog"]

    try:
        entries = parse_catalog(CATALOG)
    except ValueError as exc:
        return [f"agent-skills/catalog.yaml: {exc}"]

    by_name = {entry.get("name", ""): entry for entry in entries}
    duplicate_names = [
        name
        for name, count in Counter(entry.get("name", "") for entry in entries).items()
        if name and count > 1
    ]
    for name in sorted(duplicate_names):
        errors.append(f"agent-skills/catalog.yaml: duplicate skill {name!r}")

    skill_names = {path.parent.name for path in skill_files}
    catalog_names = set(by_name)

    missing = skill_names - catalog_names
    extra = catalog_names - skill_names
    for name in sorted(missing):
        errors.append(f"agent-skills/catalog.yaml: missing skill {name!r}")
    for name in sorted(extra):
        errors.append(f"agent-skills/catalog.yaml: extra skill {name!r}")

    required_fields = {"name", "path", "lane", "expected_use"}
    allowed_expected_use = {"near-always", "conditional"}
    for entry in entries:
        name = entry.get("name", "<missing>")
        missing_fields = required_fields - set(entry)
        if missing_fields:
            errors.append(
                f"agent-skills/catalog.yaml: {name}: missing fields "
                f"{', '.join(sorted(missing_fields))}"
            )
            continue

        rel_path = entry["path"]
        expected_path = f"agent-skills/{name}/SKILL.md"
        if rel_path != expected_path:
            errors.append(
                f"agent-skills/catalog.yaml: {name}: path {rel_path!r} "
                f"does not match {expected_path!r}"
            )
        if not (ROOT / rel_path).exists():
            errors.append(f"agent-skills/catalog.yaml: {name}: path does not exist")
        if entry["expected_use"] not in allowed_expected_use:
            errors.append(
                f"agent-skills/catalog.yaml: {name}: invalid expected_use "
                f"{entry['expected_use']!r}"
            )

    return errors


def markdown_section(text: str, heading: str) -> str:
    start_marker = f"## {heading}"
    start = text.find(start_marker)
    if start == -1:
        return ""
    next_heading = text.find("\n## ", start + len(start_marker))
    if next_heading == -1:
        return text[start:]
    return text[start:next_heading]


def validate_readme_lifecycle(skill_files: list[Path], readme_text: str) -> list[str]:
    errors: list[str] = []
    section = markdown_section(readme_text, "Lifecycle Map")
    if not section:
        return ["agent-skills/README.md: missing Lifecycle Map section"]

    names_in_section = set(BACKTICK_RE.findall(section))
    exempt = {"deeptutor-engineering-lifecycle-gate"}
    for skill in skill_files:
        name = skill.parent.name
        if name in exempt:
            continue
        if name not in names_in_section:
            errors.append(
                "agent-skills/README.md: Lifecycle Map missing "
                f"`{name}`"
            )
    return errors


def validate_skill(path: Path, readme_text: str, agents_text: str) -> list[str]:
    errors: list[str] = []
    rel = path.relative_to(ROOT)
    try:
        fields = parse_frontmatter(path)
    except ValueError as exc:
        return [f"{rel}: {exc}"]

    name = fields.get("name")
    description = fields.get("description")
    expected = path.parent.name
    if name != expected:
        errors.append(f"{rel}: name {name!r} does not match directory {expected!r}")
    if not description:
        errors.append(f"{rel}: missing description")
    else:
        if len(description) > 1024:
            errors.append(f"{rel}: description too long ({len(description)} chars)")
        if "Use " not in description and "Use when" not in description:
            errors.append(f"{rel}: description lacks a clear Use trigger")

    token = f"`{expected}`"
    if token not in readme_text:
        errors.append(f"{rel}: missing README index entry {token}")

    link = f"./agent-skills/{expected}/SKILL.md"
    if link not in agents_text:
        errors.append(f"{rel}: missing AGENTS link {link}")

    return errors


def validate_links(text: str, owner: Path) -> list[str]:
    errors: list[str] = []
    base = owner.parent
    for target in LINK_RE.findall(text):
        path = (base / target).resolve()
        if not path.exists():
            errors.append(f"{owner.relative_to(ROOT)}: missing link target {target}")
    return errors


def main() -> int:
    if not README.exists() or not AGENTS.exists():
        print("missing README.md or AGENTS.md", file=sys.stderr)
        return 1

    readme_text = README.read_text(encoding="utf-8")
    agents_text = AGENTS.read_text(encoding="utf-8")
    errors: list[str] = []

    skill_files = sorted(SKILL_ROOT.glob("*/SKILL.md"))
    if not skill_files:
        errors.append("no agent skills found")

    for skill in skill_files:
        errors.extend(validate_skill(skill, readme_text, agents_text))

    errors.extend(validate_catalog(skill_files))
    errors.extend(validate_readme_lifecycle(skill_files, readme_text))
    errors.extend(validate_links(readme_text, README))
    errors.extend(validate_links(agents_text, AGENTS))

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(f"validated {len(skill_files)} DeepTutor agent skills and catalog")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
