from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_SCAN_ROOT = Path("docs/sandbox")
SCANNED_SUFFIXES = {".md", ".txt", ".json", ".jsonl", ".csv"}

PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "id_card": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "openid": re.compile(r"\b(?:open[_-]?id|union[_-]?id)\s*[:=：]\s*[A-Za-z0-9_-]{8,}", re.IGNORECASE),
    "chinese_name_label": re.compile(r"(?:学员姓名|真实姓名|姓名)\s*[:=：]\s*[\u4e00-\u9fff]{2,4}"),
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    snippet: str


def _iter_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if not path.exists():
            continue
        if path.is_file():
            if path.suffix.lower() in SCANNED_SUFFIXES:
                yield path
            continue
        for candidate in sorted(path.rglob("*")):
            if candidate.is_file() and candidate.suffix.lower() in SCANNED_SUFFIXES:
                yield candidate


def _mask_snippet(text: str) -> str:
    masked = text.strip()
    for pattern in PII_PATTERNS.values():
        masked = pattern.sub("[REDACTED]", masked)
    return masked[:160]


def scan_paths(paths: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_files(paths):
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            for kind, pattern in PII_PATTERNS.items():
                if pattern.search(line):
                    findings.append(
                        Finding(
                            path=str(path),
                            line=line_number,
                            kind=kind,
                            snippet=_mask_snippet(line),
                        )
                    )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan Hermes sandbox transcripts for raw PII before commit.")
    parser.add_argument(
        "--path",
        action="append",
        default=None,
        help="File or directory to scan. May be repeated. Defaults to docs/sandbox.",
    )
    args = parser.parse_args(argv)

    paths = [Path(item) for item in args.path] if args.path else [DEFAULT_SCAN_ROOT]
    findings = scan_paths(paths)
    for finding in findings:
        print(f"PII finding: {finding.path}:{finding.line} [{finding.kind}] {finding.snippet}")
    if findings:
        print(f"ERROR hermes sandbox PII scan failed: findings={len(findings)}")
        return 1
    print("Hermes sandbox PII scan: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
