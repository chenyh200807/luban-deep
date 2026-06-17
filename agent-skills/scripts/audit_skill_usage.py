#!/usr/bin/env python3
"""Audit recent Codex skill reads without exposing raw session contents."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SESSIONS_ROOT = Path.home() / ".codex" / "sessions"
SKILL_PATH_RE = re.compile(
    r"(?P<path>(?:/[^\"'\s]+|\.?/agent-skills/[^\"'\s]+|agent-skills/[^\"'\s]+)/SKILL\.md)"
)
NON_READ_TOOL_NAMES = {
    "spawn_agent",
    "send_input",
    "wait_agent",
    "close_agent",
    "update_plan",
}


@dataclass(frozen=True)
class SkillRead:
    timestamp: str
    session_file: str
    tool_name: str
    skill_name: str
    skill_path: str
    scope: str


def parse_dt(value: str, tz: ZoneInfo) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def iter_candidate_files(root: Path, start: datetime, until: datetime) -> list[Path]:
    dates = set()
    cursor = start
    while cursor.date() <= until.date():
        dates.add(cursor.date())
        dates.add(cursor.astimezone(timezone.utc).date())
        cursor += timedelta(days=1)
    dates.add(until.date())
    dates.add(until.astimezone(timezone.utc).date())

    files: list[Path] = []
    for day in sorted(dates):
        day_dir = root / f"{day.year:04d}" / f"{day.month:02d}" / f"{day.day:02d}"
        if day_dir.exists():
            files.extend(sorted(day_dir.glob("*.jsonl")))
    return files


def find_timestamp(payload: dict[str, Any], tz: ZoneInfo) -> datetime | None:
    for key in ("timestamp", "created_at", "time"):
        value = payload.get(key)
        if isinstance(value, str):
            try:
                return parse_dt(value, tz)
            except ValueError:
                continue
    return None


def iter_dicts(value: Any) -> Any:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for item in value:
            yield from iter_dicts(item)


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def extract_skill_paths(call: dict[str, Any]) -> list[str]:
    text = stable_json(call)
    seen: set[str] = set()
    paths: list[str] = []
    for match in SKILL_PATH_RE.finditer(text):
        path = match.group("path")
        if any(marker in path for marker in ("*", "{", "}")):
            continue
        if path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def skill_name(path: str) -> str:
    return Path(path).parent.name


def skill_scope(path: str) -> str:
    if path.startswith("agent-skills/") or path.startswith("./agent-skills/"):
        return "repo-local"
    if "/agent-skills/" in path:
        return "repo-local"
    if "/.codex/skills/" in path:
        return "codex-local"
    if "/.claude/skills/" in path:
        return "claude-local"
    if "/plugins/cache/" in path:
        return "plugin"
    if "/.agents/skills/" in path:
        return "agents-local"
    return "other"


def iter_skill_reads(
    sessions_root: Path,
    start: datetime,
    until: datetime,
    tz: ZoneInfo,
) -> list[SkillRead]:
    reads: list[SkillRead] = []
    for file_path in iter_candidate_files(sessions_root, start, until):
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if "SKILL.md" not in line or "function_call" not in line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    timestamp = find_timestamp(payload, tz)
                    if timestamp is None or timestamp < start or timestamp > until:
                        continue

                    for candidate in iter_dicts(payload):
                        if candidate.get("type") != "function_call":
                            continue
                        tool_name = str(candidate.get("name") or candidate.get("tool_name") or "unknown")
                        if tool_name in NON_READ_TOOL_NAMES:
                            continue
                        paths = extract_skill_paths(candidate)
                        if not paths:
                            continue
                        for path in paths:
                            reads.append(
                                SkillRead(
                                    timestamp=timestamp.isoformat(),
                                    session_file=file_path.name,
                                    tool_name=tool_name,
                                    skill_name=skill_name(path),
                                    skill_path=path,
                                    scope=skill_scope(path),
                                )
                            )
        except OSError as exc:
            print(f"warning: could not read {file_path}: {exc}", file=sys.stderr)
    return reads


def render_table(rows: list[tuple[str, int]], heading: str) -> str:
    if not rows:
        return f"{heading}\n  none"
    width = max(len(name) for name, _count in rows)
    lines = [heading]
    for name, count in rows:
        lines.append(f"  {name.ljust(width)}  {count}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize recent SKILL.md reads from Codex session JSONL. "
            "This proves skill invocation only, not full compliance."
        )
    )
    parser.add_argument("--sessions-root", type=Path, default=DEFAULT_SESSIONS_ROOT)
    parser.add_argument("--hours", type=float, default=1.0)
    parser.add_argument("--since", help="ISO timestamp; overrides --hours start")
    parser.add_argument("--until", help="ISO timestamp; defaults to now")
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument(
        "--exclude-after",
        help="ISO timestamp for removing audit/self-observation reads from the report",
    )
    parser.add_argument(
        "--exclude-skill",
        action="append",
        default=[],
        help="Skill name to exclude; may be repeated",
    )
    parser.add_argument("--repo-only", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    tz = ZoneInfo(args.timezone)
    until = parse_dt(args.until, tz) if args.until else datetime.now(tz)
    start = parse_dt(args.since, tz) if args.since else until - timedelta(hours=args.hours)
    exclude_after = parse_dt(args.exclude_after, tz) if args.exclude_after else None
    excluded_skills = set(args.exclude_skill)

    reads = iter_skill_reads(args.sessions_root, start, until, tz)
    if exclude_after is not None:
        reads = [read for read in reads if parse_dt(read.timestamp, tz) <= exclude_after]
    if excluded_skills:
        reads = [read for read in reads if read.skill_name not in excluded_skills]
    if args.repo_only:
        reads = [read for read in reads if read.scope == "repo-local"]

    by_skill = Counter(read.skill_name for read in reads)
    by_scope = Counter(read.scope for read in reads)
    payload = {
        "window": {
            "start": start.isoformat(),
            "until": until.isoformat(),
            "timezone": args.timezone,
        },
        "total_skill_reads": len(reads),
        "unique_skills": len(by_skill),
        "counts_by_scope": dict(sorted(by_scope.items())),
        "counts_by_skill": dict(sorted(by_skill.items())),
        "events": [asdict(read) for read in reads],
        "limits": [
            "Counts prove SKILL.md read/invocation only.",
            "They do not prove every instruction in a skill was followed.",
            "Raw function-call inputs and session contents are intentionally not printed.",
        ],
    }

    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(
        "Skill usage audit\n"
        f"Window: {payload['window']['start']} -> {payload['window']['until']} "
        f"({args.timezone})\n"
        f"Total SKILL.md reads: {payload['total_skill_reads']}\n"
        f"Unique skills: {payload['unique_skills']}\n"
    )
    print(render_table(sorted(by_scope.items()), "Counts by scope:"))
    print()
    print(render_table(by_skill.most_common(), "Counts by skill:"))
    print()
    print("Limits:")
    for limit in payload["limits"]:
        print(f"  - {limit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
