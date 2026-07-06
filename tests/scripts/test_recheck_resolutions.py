"""recheck_resolutions.py 反自证核验器测试.

核心契约: exit 0 = 全部 resolution 机器可核部分重放命中; 任何造假 verified
(子串核不命中 / 无可解析证据 / registry 语义不符) 必须 exit 1 并打印精确失败项。
双闸/manifest 子进程在单测中 mock 为绿 (它们各有自己的集成路径), 本测试
只锁 replay 逻辑与 exit code 契约。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "recheck_resolutions",
    REPO / "docs" / "原始数据" / "考点原料" / "recheck_resolutions.py",
)
rr = importlib.util.module_from_spec(_spec)
sys.modules["recheck_resolutions"] = rr
_spec.loader.exec_module(rr)

QUOTE = "侧模拆除时的混凝土强度应能保证其表面及棱角不受损伤，且不小于1N/mm²"


def _write_fixture(pack_dir: Path, jury_rows: list[dict]) -> None:
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "T01_测试考点.md").write_text("# 测试 pack\n🟢 kc:TEST_001_0001:0\n", encoding="utf-8")
    (pack_dir / "_T01_compiled_source.json").write_text(
        json.dumps(
            {"units": [{"scoring_points": [
                {"point_id": "kc:TEST_001_0001:0", "quote": QUOTE},
            ]}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (pack_dir / "_T01_jury.json").write_text(
        json.dumps(jury_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _legit_row() -> dict:
    return {
        "issue": "kc:TEST_001_0001 的 quote 未含 1N/mm²",
        "confidence": "高可信",
        "resolution": {
            "status": "not_applicable",
            "fixed_in": "无需改正文——jury 断言被确定性核验证伪",
            "verified": "2026-07-04 确定性核验：kc:TEST_001_0001:0 quote 直读含「1N/mm²」，jury 断言系幻觉",
        },
    }


@pytest.fixture()
def patched(monkeypatch, tmp_path):
    pack_dir = tmp_path / "成品"
    monkeypatch.setattr(rr, "PACK_DIR", pack_dir)
    # 双闸 + manifest 子进程 mock 为绿: 本测试只锁 replay 逻辑与 exit 契约
    monkeypatch.setattr(rr, "_run", lambda cmd: (0, "mocked-green"))
    return pack_dir


def test_legit_not_applicable_replays_and_exits_0(patched, capsys):
    _write_fixture(patched, [_legit_row()])
    assert rr.main(["T01"]) == 0
    assert "✅ PASS" in capsys.readouterr().out


def test_forged_verified_token_miss_exits_1(patched, capsys):
    forged = _legit_row()
    forged["resolution"]["verified"] = (
        "2026-07-04 确定性核验：kc:TEST_001_0001:0 quote 直读含「5N/mm²」，jury 断言系幻觉"
    )
    _write_fixture(patched, [_legit_row(), forged])
    assert rr.main(["T01"]) == 1
    out = capsys.readouterr().out
    assert "5N/mm²" in out and "未命中" in out  # 精确失败项被打印


def test_not_applicable_without_machine_evidence_is_fail_closed(patched):
    row = _legit_row()
    row["resolution"]["verified"] = "面板一致认为 jury 断言不成立"  # 无 point_id 无 token = 自证
    _write_fixture(patched, [row])
    assert rr.main(["T01"]) == 1


def test_nonexistent_point_id_in_verified_exits_1(patched, capsys):
    row = _legit_row()
    row["resolution"]["verified"] = "确定性核验：kc:GHOST_999_0001:0 quote 直读含「1N/mm²」"
    _write_fixture(patched, [row])
    assert rr.main(["T01"]) == 1
    assert "不存在于源料" in capsys.readouterr().out


def test_registry_semantic_forgery_exits_1(patched, capsys):
    row = _legit_row()
    row["resolution"]["status"] = "fixed"
    row["resolution"]["verified"] = (
        "2026-07-04 确定性核验：kc:TEST_001_0001:0 quote 直读含「1N/mm²」；registry 直读 E06=数字混淆"
    )
    _write_fixture(patched, [row])
    assert rr.main(["T01"]) == 1
    assert "E06" in capsys.readouterr().out


def test_illegal_status_exits_1(patched):
    row = _legit_row()
    row["resolution"]["status"] = "wip"
    _write_fixture(patched, [row])
    assert rr.main(["T01"]) == 1


def test_corrupt_jury_sidecar_is_fail_closed(patched):
    _write_fixture(patched, [_legit_row()])
    (patched / "_T01_jury.json").write_bytes(b'[{"a"\x00: 1}]')
    assert rr.main(["T01"]) == 1
