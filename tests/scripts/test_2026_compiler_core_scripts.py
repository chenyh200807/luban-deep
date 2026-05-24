from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_script(args: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged["PYTHONPATH"] = str(REPO_ROOT)
    merged.update(env)
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        env=merged,
        text=True,
        capture_output=True,
        timeout=30,
    )


def make_source_root(tmp_path: Path) -> Path:
    root = tmp_path / "2026"
    (root / "taxonomy").mkdir(parents=True)
    (root / "标准文件").mkdir()
    (root / "题库").mkdir()
    (root / "讲义" / "demo").mkdir(parents=True)
    (root / "2026教材").mkdir()
    (root / "taxonomy" / "FINAL_CLEANED_TAXONOMY2026.json").write_text(
        json.dumps([{"node_code": "1A", "name": "防水", "path_names": ["建筑", "防水"]}]),
        encoding="utf-8",
    )
    (root / "标准文件" / "std.json").write_text(
        json.dumps([{"source_record_id": "STD_1", "standard_code": "GB 50210-2018", "article_code": "1.0.1", "content": "标准"}]),
        encoding="utf-8",
    )
    (root / "题库" / "q.json").write_text(
        json.dumps(
            [
                {
                    "source_chunk_id": "chunk1",
                    "original_id": "orig1",
                    "question_type": "single_choice",
                    "node_code": "1A",
                    "stem": "题干",
                    "options": {"A": "a"},
                    "correct_answer": "A",
                    "option_reasoning": {"A": "ok"},
                }
            ]
        ),
        encoding="utf-8",
    )
    (root / "讲义" / "demo" / "demo.json").write_text(
        json.dumps([{"node_code": "1A", "title": "讲义", "content_markdown": "内容"}]),
        encoding="utf-8",
    )
    return root


def test_combined_compile_and_diff_tool(tmp_path: Path) -> None:
    root = make_source_root(tmp_path)
    env = {"LUBAN_2026_SOURCE_ROOT": str(root)}

    first = run_script(
        ["scripts/compile_2026_knowledge_assets.py", "--run-id", "pytest-core-a", "--force"],
        env=env,
    )
    assert first.returncode == 0, first.stderr
    assert "standard=1" in first.stdout
    assert "question=1" in first.stdout
    assert "lecture_bundle=1" in first.stdout

    second = run_script(
        ["scripts/compile_2026_knowledge_assets.py", "--run-id", "pytest-core-b", "--only-class", "standard", "--force"],
        env=env,
    )
    assert second.returncode == 0, second.stderr

    diff = run_script(
        ["scripts/diff_2026_compiler_artifacts.py", "--base", "pytest-core-a", "--head", "pytest-core-b"],
        env=env,
    )
    assert diff.returncode == 0, diff.stderr
    assert "standard_clauses" in diff.stdout
