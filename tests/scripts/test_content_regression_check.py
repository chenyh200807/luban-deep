"""内容回归检查器冒烟(真仓数据, 跳过重复现闸——复现闸由 nightly 全量跑)。"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_content_regression_fast_lanes_pass():
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "content_regression_check.py"), "--skip-repro"],
        capture_output=True, text=True, timeout=300, cwd=str(REPO),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout


def test_style_baseline_exists_and_covers_signed_pools():
    import json
    baseline = json.loads(
        (REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_style_tells_baseline.json")
        .read_text(encoding="utf-8"))
    assert len(baseline.get("packs") or {}) >= 17
