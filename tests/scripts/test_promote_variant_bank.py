"""变体池签发工具域测试——校验负路径必须逐条拒签（fail-closed，bank 不动）。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "docs" / "原始数据" / "考点原料" / "promote_variant_bank.py"
_spec = importlib.util.spec_from_file_location("promote_variant_bank", TOOL)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["promote_variant_bank"] = _mod
_spec.loader.exec_module(_mod)

_PACK_TEXT = "# F16 屋面卷材防水\n正文内容\n"
_PACK_SHA = hashlib.sha256(_PACK_TEXT.encode("utf-8")).hexdigest()


def _gate_ok(pack_id: str, repo: Path) -> None:  # gate 重跑 stub：PASS
    return None


def _gate_fail(pack_id: str, repo: Path) -> None:  # gate 重跑 stub：FAIL
    raise _mod.PromotionError("gate 重跑 FAIL（stub）")


def _write_fixture(tmp_path: Path, *, bank_patch: dict | None = None,
                   manifest_sha: str = _PACK_SHA) -> Path:
    (tmp_path / "F16_屋面卷材防水.md").write_text(_PACK_TEXT, encoding="utf-8")
    (tmp_path / "_pack_manifest.json").write_text(json.dumps({
        "packs": [{"pack_id": "F16", "file": "F16_屋面卷材防水.md",
                   "content_sha256": manifest_sha}],
    }, ensure_ascii=False), encoding="utf-8")
    bank = {
        "schema_version": "luban_variant_bank.v0",
        "pack_id": "F16",
        "status": "candidate",
        "source_pack_sha256": _PACK_SHA,
        "gate": {"total": 47, "passed": 47, "pass_rate": 1.0,
                 "verdict_mismatches": [], "contested_leaks": [],
                 "duplicate_surfaces": []},
        "variants": [{"variant_id": "F16-A-000"}],
    }
    bank.update(bank_patch or {})
    path = tmp_path / "_F16_variant_bank.v0.json"
    path.write_text(json.dumps(bank, ensure_ascii=False), encoding="utf-8")
    return path


def _promote(tmp_path: Path, gate=_gate_ok, **kwargs):
    defaults = dict(pack_id="F16", basis="gate 100% + 随 pack 签发使用过", who="教研")
    defaults.update(kwargs)
    return _mod.promote(defaults["pack_id"], defaults["basis"], defaults["who"],
                        pack_dir=tmp_path, repo=REPO, gate_check=gate)


def test_happy_path_flips_signed_with_signoff_record(tmp_path):
    bank_path = _write_fixture(tmp_path)
    _promote(tmp_path)
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    assert bank["status"] == "signed"
    assert bank["signoff"]["who"] == "教研"
    assert bank["signoff"]["basis"] == "gate 100% + 随 pack 签发使用过"
    assert bank["signoff"]["when"]  # ISO 留痕
    assert bank["source_pack_sha256"] == _PACK_SHA  # 只翻牌不动锚


def test_missing_bank_rejected(tmp_path):
    (tmp_path / "_pack_manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(_mod.PromotionError, match="不存在"):
        _promote(tmp_path)


def test_already_signed_rejected_no_resign(tmp_path):
    bank_path = _write_fixture(tmp_path, bank_patch={"status": "signed"})
    before = bank_path.read_text(encoding="utf-8")
    with pytest.raises(_mod.PromotionError, match="已是 signed"):
        _promote(tmp_path)
    assert bank_path.read_text(encoding="utf-8") == before  # bank 不动


def test_bank_sha_drift_rejected(tmp_path):
    bank_path = _write_fixture(tmp_path, bank_patch={"source_pack_sha256": "stale"})
    with pytest.raises(_mod.PromotionError, match="pack 已修订"):
        _promote(tmp_path)
    assert json.loads(bank_path.read_text(encoding="utf-8"))["status"] == "candidate"


def test_stale_manifest_rejected(tmp_path):
    _write_fixture(tmp_path, manifest_sha="stale-manifest-sha")
    with pytest.raises(_mod.PromotionError, match="manifest content_sha256 落后"):
        _promote(tmp_path)


def test_dirty_stored_gate_rejected(tmp_path):
    _write_fixture(tmp_path, bank_patch={"gate": {
        "total": 47, "passed": 46, "verdict_mismatches": ["F16-A-001"],
        "contested_leaks": [], "duplicate_surfaces": []}})
    with pytest.raises(_mod.PromotionError, match="gate"):
        _promote(tmp_path)


def test_gate_rerun_failure_rejected(tmp_path):
    bank_path = _write_fixture(tmp_path)
    with pytest.raises(_mod.PromotionError, match="gate 重跑 FAIL"):
        _promote(tmp_path, gate=_gate_fail)
    assert json.loads(bank_path.read_text(encoding="utf-8"))["status"] == "candidate"


def test_empty_basis_or_who_rejected(tmp_path):
    _write_fixture(tmp_path)
    with pytest.raises(_mod.PromotionError, match="basis"):
        _promote(tmp_path, basis="  ")
    with pytest.raises(_mod.PromotionError, match="who"):
        _promote(tmp_path, who="")


def test_bad_pack_id_rejected(tmp_path):
    with pytest.raises(_mod.PromotionError, match="非法 pack_id"):
        _promote(tmp_path, pack_id="../etc")


def test_real_repo_gate_rerun_wiring_f16():
    """活体接线断言：真 builder --check 可被 gate 重跑路径调起且 PASS（F16）。"""
    _mod._run_builder_gate_check("F16", REPO)


# ── --kind concept_cards（考点卡池复用同一人闸，禁分叉第二 promote 工具） ──

def _write_concept_fixture(tmp_path, *, bank_patch=None):
    (tmp_path / "F16_屋面卷材防水.md").write_text(_PACK_TEXT, encoding="utf-8")
    (tmp_path / "_pack_manifest.json").write_text(json.dumps({
        "packs": [{"pack_id": "F16", "file": "F16_屋面卷材防水.md",
                   "content_sha256": _PACK_SHA}],
    }, ensure_ascii=False), encoding="utf-8")
    bank = {
        "schema_version": "luban-concept-card-bank",
        "pack_id": "F16",
        "status": "candidate",
        "source_pack_sha256": _PACK_SHA,
        "gate": {"total": 2, "passed": 2, "pass_rate": 1.0,
                 "quote_mismatches": [], "duplicate_cards": [],
                 "forbidden_words": []},
        "cards": [{"card_id": "F16:kc:x:0"}],
    }
    bank.update(bank_patch or {})
    path = tmp_path / "_F16_concept_card_bank.v0.json"
    path.write_text(json.dumps(bank, ensure_ascii=False), encoding="utf-8")
    return path


def _promote_concept(tmp_path, gate=_gate_ok, kind="concept_cards"):
    return _mod.promote("F16", "gate 100% + owner 逐卡过目", "教研",
                        pack_dir=tmp_path, repo=REPO, gate_check=gate, kind=kind)


def test_concept_kind_happy_path_flips_signed(tmp_path):
    bank_path = _write_concept_fixture(tmp_path)
    _promote_concept(tmp_path)
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    assert bank["status"] == "signed"
    assert bank["signoff"]["who"] == "教研"


def test_concept_kind_reads_own_template_not_variant(tmp_path):
    """--kind concept_cards 只认 _*_concept_card_bank.v0.json——
    同目录存在变体池也不许被它顶包。"""
    _write_fixture(tmp_path)  # 变体池在场
    with pytest.raises(_mod.PromotionError, match="不存在"):
        _promote_concept(tmp_path)  # 考点卡池缺失必须拒


def test_concept_kind_dirty_gate_rejected(tmp_path):
    _write_concept_fixture(tmp_path, bank_patch={"gate": {
        "total": 2, "passed": 2, "pass_rate": 1.0,
        "quote_mismatches": ["F16:kc:x:0"], "duplicate_cards": [],
        "forbidden_words": []}})
    with pytest.raises(_mod.PromotionError, match="quote_mismatches"):
        _promote_concept(tmp_path)


def test_unknown_kind_rejected(tmp_path):
    with pytest.raises(_mod.PromotionError, match="未知 bank kind"):
        _promote_concept(tmp_path, kind="nope")


def test_real_repo_concept_gate_rerun_wiring_s05():
    """活体接线断言：concept builder --check 可被 kind 化 gate 重跑调起且 PASS。"""
    _mod._run_builder_gate_check("S05", REPO, "concept_cards")
