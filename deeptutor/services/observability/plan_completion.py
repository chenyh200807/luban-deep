from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from deeptutor.services.observability.change_impact import collect_git_changed_files
from deeptutor.services.observability.release_lineage import get_release_lineage_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[3]

_PASS = "PASS"
_FAIL = "FAIL"
_WARN = "WARN"
_DONE = "DONE"
_PARTIAL = "PARTIAL"
_NOT_DONE = "NOT_DONE"
_UNVERIFIABLE = "UNVERIFIABLE"
_OUT_OF_SCOPE = "OUT_OF_SCOPE"

_CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[(?P<mark>[ xX])\]\s+(?P<text>.+?)\s*$")
_NUMBERED_RE = re.compile(r"^\s*\d+\.\s+(?P<text>.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(?P<text>.+?)\s*$")
_CODE_TOKEN_RE = re.compile(r"`([^`]+)`")
_PATH_EXTENSIONS = (
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sql",
    ".sh",
    ".wxml",
    ".wxss",
    ".css",
    ".html",
)
_LINE_QUALIFIED_PATH_RE = re.compile(
    r"^(?P<path>.+(?:"
    + "|".join(re.escape(extension) for extension in _PATH_EXTENSIONS)
    + r")):\d+$"
)
_COMMAND_PREFIXES = {
    "pytest",
    "python",
    "python3",
    "python3.11",
    "bash",
    "sh",
    "docker",
    "curl",
    "npm",
    "pnpm",
    "uv",
    "deeptutor",
}
_REPO_PATH_PREFIXES = (
    ".github/",
    "artifacts/",
    "contracts/",
    "deeptutor/",
    "deeptutor_cli/",
    "deployment/",
    "docs/",
    "scripts/",
    "supabase/",
    "tests/",
    "web/",
    "wx_miniprogram/",
    "yousenwebview/",
)
_PATH_TOKEN_RE = re.compile(r"(?<![\w./-])([A-Za-z0-9_.@+-]+(?:/[A-Za-z0-9_.@+()=-]+)+)(?![\w./-])")
_BULLET_FILE_KEYWORDS = (
    "create:",
    "modify:",
    "test:",
    "run:",
    "file:",
    "files:",
    "新增",
    "修改",
    "测试",
    "验证",
)
_SCOPE_MODES = {"changed", "full"}


def _as_project_relative(path: Path, *, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _normalize_plan_path(path: str | Path, *, project_root: Path) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = project_root / target
    return target.resolve()


def _normalize_changed_files(changed_files: list[str] | tuple[str, ...] | None) -> list[str]:
    normalized: list[str] = []
    for item in changed_files or []:
        path = str(item or "").strip().replace("\\", "/").lstrip("./")
        if path:
            normalized.append(path.rstrip("/"))
    return sorted(dict.fromkeys(normalized))


def _looks_like_command(token: str) -> bool:
    parts = token.strip().split(maxsplit=1)
    if len(parts) < 2:
        return False
    return parts[0] in _COMMAND_PREFIXES


def _looks_like_local_path(token: str) -> bool:
    value = token.strip().strip("'\"")
    if not value or value.startswith(("http://", "https://", "wss://", "ws://")):
        return False
    if " " in value or "\n" in value or value.startswith("-"):
        return False
    if value.startswith("$"):
        return False
    if "/" not in value and not value.endswith(_PATH_EXTENSIONS):
        return False
    if value.endswith("/"):
        return True
    return value.endswith(_PATH_EXTENSIONS) or "/" in value


def _looks_like_repo_path(path: str) -> bool:
    value = path.lstrip("./")
    return value.startswith(_REPO_PATH_PREFIXES) or value.endswith(_PATH_EXTENSIONS)


def _normalize_local_path(token: str, *, project_root: Path, repo_path_only: bool = False) -> str | None:
    value = token.strip().strip("'\"").rstrip(".,:;)")
    line_qualified = _LINE_QUALIFIED_PATH_RE.match(value)
    if line_qualified:
        value = line_qualified.group("path")
    if not value or value.startswith(("http://", "https://", "wss://", "ws://")):
        return None
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(project_root.resolve()).as_posix().rstrip("/")
        except ValueError:
            return None
    if not _looks_like_local_path(value):
        return None
    normalized = value.replace("\\", "/").lstrip("./").rstrip("/")
    if repo_path_only and not _looks_like_repo_path(normalized):
        return None
    return normalized


def _extract_paths_and_commands(text: str, *, project_root: Path) -> tuple[list[str], list[str]]:
    paths: list[str] = []
    commands: list[str] = []

    for token in _CODE_TOKEN_RE.findall(text):
        normalized = token.strip()
        if _looks_like_command(normalized):
            commands.append(normalized)
            continue
        path = _normalize_local_path(normalized, project_root=project_root)
        if path:
            paths.append(path)

    for match in _PATH_TOKEN_RE.findall(text):
        path = _normalize_local_path(match, project_root=project_root, repo_path_only=True)
        if path:
            paths.append(path)

    return sorted(dict.fromkeys(paths)), sorted(dict.fromkeys(commands))


def _extract_command_paths(commands: list[str], *, project_root: Path) -> list[str]:
    paths: list[str] = []
    for command in commands:
        for token in command.split():
            path = _normalize_local_path(token, project_root=project_root, repo_path_only=True)
            if path:
                paths.append(path)
    return sorted(dict.fromkeys(paths))


def _should_keep_bullet(text: str, *, paths: list[str], commands: list[str]) -> bool:
    if commands:
        return True
    lowered = text.strip().lower()
    return bool(paths) and any(keyword in lowered for keyword in _BULLET_FILE_KEYWORDS)


def extract_plan_items(
    plan_path: str | Path,
    *,
    project_root: Path | None = None,
) -> list[dict[str, Any]]:
    root = (project_root or PROJECT_ROOT).resolve()
    target = _normalize_plan_path(plan_path, project_root=root)
    lines = target.read_text(encoding="utf-8").splitlines()
    plan_rel = _as_project_relative(target, project_root=root)
    items: list[dict[str, Any]] = []

    for line_no, raw_line in enumerate(lines, start=1):
        kind: str | None = None
        text: str | None = None
        declared_complete = False

        checkbox = _CHECKBOX_RE.match(raw_line)
        if checkbox:
            kind = "checkbox"
            text = checkbox.group("text").strip()
            declared_complete = checkbox.group("mark").lower() == "x"
        else:
            numbered = _NUMBERED_RE.match(raw_line)
            if numbered:
                kind = "numbered"
                text = numbered.group("text").strip()
            else:
                bullet = _BULLET_RE.match(raw_line)
                if bullet:
                    candidate_text = bullet.group("text").strip()
                    candidate_paths, candidate_commands = _extract_paths_and_commands(candidate_text, project_root=root)
                    if _should_keep_bullet(candidate_text, paths=candidate_paths, commands=candidate_commands):
                        kind = "bullet"
                        text = candidate_text

        if not kind or text is None:
            continue

        paths, commands = _extract_paths_and_commands(text, project_root=root)
        command_paths = _extract_command_paths(commands, project_root=root)
        items.append(
            {
                "id": f"{plan_rel}:{line_no}",
                "plan_path": plan_rel,
                "line": line_no,
                "kind": kind,
                "declared_complete": declared_complete,
                "text": text,
                "paths": paths,
                "commands": commands,
                "command_paths": command_paths,
                "category": _classify_item(text=text, paths=paths, commands=commands),
            }
        )

    return items


def _classify_item(*, text: str, paths: list[str], commands: list[str]) -> str:
    lowered = text.lower()
    if commands or "验证" in text or "测试" in text or "run:" in lowered:
        return "VERIFY"
    if paths and all(path.startswith("tests/") or "/test_" in path for path in paths):
        return "TEST"
    if paths and all(path.startswith("docs/") or path.endswith(".md") for path in paths):
        return "DOCS"
    if paths and any(path.endswith((".yaml", ".yml", ".toml", ".json")) or "compose" in path for path in paths):
        return "CONFIG"
    if paths:
        return "CODE"
    return "EXTERNAL"


def _path_has_changed(path: str, *, changed_files: set[str]) -> bool:
    normalized = path.rstrip("/")
    return any(
        changed == normalized or changed.startswith(f"{normalized}/")
        for changed in changed_files
    )


def _path_has_evidence(path: str, *, evidence_files: set[str]) -> bool:
    normalized = path.rstrip("/")
    return any(
        evidence == normalized or evidence.startswith(f"{normalized}/")
        for evidence in evidence_files
    )


def _scope_item(
    item: dict[str, Any],
    *,
    scope_mode: str,
    changed_files: set[str],
    evidence_files: set[str],
) -> dict[str, Any]:
    if scope_mode == "full":
        return {**item, "scope": "in_scope", "scope_reason": "full_plan"}

    candidates = [*(item.get("paths") or []), *(item.get("command_paths") or [])]
    if any(_path_has_changed(path, changed_files=changed_files) for path in candidates):
        return {**item, "scope": "in_scope", "scope_reason": "changed_file_match"}
    if any(_path_has_evidence(path, evidence_files=evidence_files) for path in candidates):
        return {**item, "scope": "in_scope", "scope_reason": "evidence_file_match"}
    return {
        **item,
        "scope": "out_of_scope",
        "scope_reason": "no_changed_or_evidence_match",
        "status": _OUT_OF_SCOPE,
        "evidence": ["not_in_current_release_scope"],
    }


def _evaluate_item(
    item: dict[str, Any],
    *,
    changed_files: set[str],
    evidence_files: list[str],
    project_root: Path,
    scope_mode: str,
) -> dict[str, Any]:
    paths = list(item.get("paths") or [])
    commands = list(item.get("commands") or [])
    evidence: list[str] = []

    if paths:
        changed_paths = [path for path in paths if _path_has_changed(path, changed_files=changed_files)]
        missing_paths = [
            path
            for path in paths
            if not (project_root / path).exists() and not _path_has_changed(path, changed_files=changed_files)
        ]
        declared_existing_paths = [
            path
            for path in paths
            if item.get("declared_complete")
            and path not in changed_paths
            and path not in missing_paths
        ]
        current_state_existing_paths = [
            path
            for path in paths
            if scope_mode == "full"
            and path not in changed_paths
            and path not in missing_paths
            and path not in declared_existing_paths
        ]
        unchanged_paths = [
            path
            for path in paths
            if path not in changed_paths
            and path not in missing_paths
            and path not in declared_existing_paths
            and path not in current_state_existing_paths
        ]
        evidence.extend(f"changed:{path}" for path in changed_paths)
        evidence.extend(f"declared_complete_existing:{path}" for path in declared_existing_paths)
        evidence.extend(f"current_state_existing:{path}" for path in current_state_existing_paths)
        evidence.extend(f"missing:{path}" for path in missing_paths)
        evidence.extend(f"unchanged:{path}" for path in unchanged_paths)
        done_paths = {*changed_paths, *declared_existing_paths, *current_state_existing_paths}
        if len(done_paths) == len(paths):
            status = _DONE
        elif done_paths:
            status = _PARTIAL
        else:
            status = _NOT_DONE
        return {**item, "status": status, "evidence": evidence}

    if commands:
        if item.get("declared_complete"):
            return {**item, "status": _DONE, "evidence": ["declared_complete"]}
        if evidence_files:
            evidence.extend(f"evidence:{path}" for path in evidence_files)
            return {**item, "status": _PARTIAL, "evidence": evidence}
        return {**item, "status": _NOT_DONE, "evidence": ["missing_test_or_runtime_evidence"]}

    if evidence_files:
        evidence.extend(f"evidence:{path}" for path in evidence_files)
        return {**item, "status": _PARTIAL, "evidence": evidence}

    if item.get("declared_complete"):
        return {**item, "status": _DONE, "evidence": ["declared_complete"]}

    return {**item, "status": _UNVERIFIABLE, "evidence": ["no_local_path_or_evidence"]}


def build_plan_completion_audit(
    *,
    plan_paths: list[str | Path],
    changed_files: list[str] | None = None,
    evidence_files: list[str] | None = None,
    base_ref: str = "origin/main",
    scope_mode: str = "changed",
    project_root: Path | None = None,
    release: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = (project_root or PROJECT_ROOT).resolve()
    normalized_scope_mode = str(scope_mode or "").strip().lower()
    if normalized_scope_mode not in _SCOPE_MODES:
        raise ValueError(f"Unsupported plan completion scope_mode: {scope_mode!r}")
    normalized_plans = [_normalize_plan_path(path, project_root=root) for path in plan_paths]
    normalized_evidence = _normalize_changed_files(evidence_files or [])
    effective_changed_files = _normalize_changed_files(
        changed_files if changed_files is not None else collect_git_changed_files(base_ref=base_ref)
    )
    changed_set = set(effective_changed_files)

    raw_items = [
        item
        for plan_path in normalized_plans
        for item in extract_plan_items(plan_path, project_root=root)
    ]
    scoped_items = [
        _scope_item(
            item,
            scope_mode=normalized_scope_mode,
            changed_files=changed_set,
            evidence_files=set(normalized_evidence),
        )
        for item in raw_items
    ]
    items = [
        _evaluate_item(
            item,
            changed_files=changed_set,
            evidence_files=normalized_evidence,
            project_root=root,
            scope_mode=normalized_scope_mode,
        )
        if item.get("scope") == "in_scope"
        else item
        for item in scoped_items
    ]
    in_scope_items = [item for item in items if item.get("scope") == "in_scope"]

    status_counts = {
        "done": len([item for item in items if item.get("status") == _DONE]),
        "partial": len([item for item in items if item.get("status") == _PARTIAL]),
        "not_done": len([item for item in items if item.get("status") == _NOT_DONE]),
        "unverifiable": len([item for item in items if item.get("status") == _UNVERIFIABLE]),
        "out_of_scope": len([item for item in items if item.get("status") == _OUT_OF_SCOPE]),
    }
    summary = {
        "total": len(items),
        "scoped": len(in_scope_items),
        **status_counts,
        "plan_count": len(normalized_plans),
        "changed_file_count": len(effective_changed_files),
        "evidence_file_count": len(normalized_evidence),
    }
    blockers = ["plan_item_not_done"] if status_counts["not_done"] else []
    warnings = ["no_scoped_plan_items"] if not in_scope_items else []
    status = (
        _FAIL
        if blockers
        else _WARN
        if warnings or status_counts["partial"] or status_counts["unverifiable"]
        else _PASS
    )

    return {
        "run_id": f"plan-completion-{int(time.time())}",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "release": release or get_release_lineage_snapshot(),
        "scope_mode": normalized_scope_mode,
        "status": status,
        "summary": summary,
        "plan_files": [_as_project_relative(path, project_root=root) for path in normalized_plans],
        "changed_files": effective_changed_files,
        "evidence_files": normalized_evidence,
        "items": items,
        "blockers": blockers,
        "warnings": warnings,
    }


def render_plan_completion_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Plan Completion Audit",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- status: `{payload.get('status')}`",
        f"- scope_mode: `{payload.get('scope_mode')}`",
        f"- plans: `{summary.get('plan_count', 0)}`",
        f"- total_items: `{summary.get('total', 0)}`",
        f"- scoped_items: `{summary.get('scoped', 0)}`",
        f"- done: `{summary.get('done', 0)}`",
        f"- partial: `{summary.get('partial', 0)}`",
        f"- not_done: `{summary.get('not_done', 0)}`",
        f"- unverifiable: `{summary.get('unverifiable', 0)}`",
        f"- out_of_scope: `{summary.get('out_of_scope', 0)}`",
        "",
        "## Items",
        "",
    ]
    for item in payload.get("items") or []:
        lines.append(
            f"- `{item.get('status')}` `{item.get('category')}` "
            f"{item.get('plan_path')}:{item.get('line')} | {item.get('text')}"
        )
        evidence = item.get("evidence") or []
        if evidence:
            lines.append(f"  evidence: {', '.join(evidence)}")

    blockers = payload.get("blockers") or []
    lines.extend(["", "## Blockers", ""])
    if blockers:
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    else:
        lines.append("- 无")
    warnings = payload.get("warnings") or []
    lines.extend(["", "## Warnings", ""])
    if warnings:
        lines.extend(f"- `{warning}`" for warning in warnings)
    else:
        lines.append("- 无")
    return "\n".join(lines)
