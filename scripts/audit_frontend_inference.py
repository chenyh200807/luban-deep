from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATHS = (
    ROOT / "wx_miniprogram" / "utils" / "learning-report-view-model.js",
    ROOT / "yousenwebview" / "packageDeeptutor" / "utils" / "learning-report-view-model.js",
    ROOT / "wx_miniprogram" / "utils" / "learning-home-view-model.js",
    ROOT / "yousenwebview" / "packageDeeptutor" / "utils" / "learning-home-view-model.js",
    ROOT / "wx_miniprogram" / "pages" / "report" / "report.js",
    ROOT / "yousenwebview" / "packageDeeptutor" / "pages" / "report" / "report.js",
    ROOT / "wx_miniprogram" / "pages" / "report" / "report.wxml",
    ROOT / "yousenwebview" / "packageDeeptutor" / "pages" / "report" / "report.wxml",
)

_FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "frontend_threshold_mastery",
        re.compile(r"(score|mastery|rate|confidence)\s*(>=|<=|>|<)\s*\d+", re.I),
    ),
    (
        "frontend_mastery_sort",
        re.compile(r"\.sort\s*\([\s\S]{0,240}(mastery|score|rate|priority|weak)", re.I),
    ),
    (
        "frontend_weak_rank_sort",
        re.compile(r"\.sort\s*\([\s\S]{0,240}\b[ab]\.value\b", re.I),
    ),
    (
        "frontend_training_plan_text",
        re.compile(
            r"\b(priorityTask|studyMethod|coachNote|timeBudget)\b\s*[:=]\s*['\"][^'\"]*(练|复盘|训练|优先|薄弱|错因|学习|作战)",
            re.I,
        ),
    ),
    (
        "frontend_training_fallback",
        re.compile(r"training\.push\s*\([\s\S]{0,320}(薄弱点|下一步训练|变式训练)", re.I),
    ),
    (
        "frontend_prompt_fabrication",
        re.compile(r"(recommendedPrompts|focusQuery|promptIntent).*(练|复盘|讲清楚)", re.S),
    ),
)


def audit_frontend_inference_paths(paths: Iterable[Path]) -> dict[str, object]:
    violations: list[dict[str, object]] = []
    for path in paths:
        source_path = Path(path)
        if not source_path.exists():
            continue
        text = source_path.read_text(encoding="utf-8")
        for name, pattern in _FORBIDDEN_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append({
                    "path": str(source_path),
                    "line": line,
                    "rule": name,
                    "snippet": _snippet(text, match.start(), match.end()),
                })
    return {"ok": not violations, "violations": violations}


def _snippet(text: str, start: int, end: int) -> str:
    raw = text[max(0, start - 40) : min(len(text), end + 40)]
    return " ".join(raw.split())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify mini-program learning surfaces do not derive mastery, weak points, training priority, or prompt text in frontend code."
    )
    parser.add_argument("paths", nargs="*", help="Optional JS files to audit.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable report.")
    args = parser.parse_args(argv)

    paths = [Path(item) for item in args.paths] if args.paths else list(DEFAULT_PATHS)
    report = audit_frontend_inference_paths(paths)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["ok"]:
        print("frontend-inference-audit: passed")
    else:
        print("frontend-inference-audit: failed")
        for item in report["violations"]:
            print(f"{item['path']}:{item['line']} {item['rule']} {item['snippet']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
