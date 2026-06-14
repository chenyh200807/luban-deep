#!/usr/bin/env python3
"""Validate DeepTutor repo-local agent skills and routing indexes."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "agent-skills"
README = SKILL_ROOT / "README.md"
AGENTS = ROOT / "AGENTS.md"


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
FIELD_RE = re.compile(r"^(name|description):\s*(.*)$", re.MULTILINE)
LINK_RE = re.compile(r"\]\((\./agent-skills/[^)]+)\)")


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("missing YAML frontmatter")
    fields = {}
    for key, value in FIELD_RE.findall(match.group(1)):
        fields[key] = value.strip().strip('"').strip("'")
    return fields


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

    errors.extend(validate_links(readme_text, README))
    errors.extend(validate_links(agents_text, AGENTS))

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(f"validated {len(skill_files)} DeepTutor agent skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
