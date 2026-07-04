"""§6-5 题→pack 映射产物守护：year:chunk_id 复合键（题库 chunk_id 跨年
不唯一）、弱锚歧义不硬塞、reverse 索引一致、确定性重跑。"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAP_JSON = REPO_ROOT / "docs/原始数据/考点原料/成品/_question_pack_map.v0.json"
EVIDENCE_DIR = REPO_ROOT / "docs/原始数据/考点原料"

_QUESTION_KEY_RE = re.compile(r"^(19|20)\d{2}:EXAM_[A-Za-z0-9_]+$")


def _load_map() -> dict:
    assert MAP_JSON.exists(), "run scripts/compile_luban_question_pack_map.py first"
    return json.loads(MAP_JSON.read_text(encoding="utf-8"))


def test_map_covers_all_exam_evidence_packs() -> None:
    compiled = _load_map()
    assert compiled["schema"] == "luban_question_pack_map.v0"
    evidence_packs = {
        path.name.split("_")[1] for path in EVIDENCE_DIR.glob("_*_exam_evidence.json")
    }
    assert set(compiled["packs"]) == evidence_packs
    assert len(evidence_packs) == 37


def test_question_keys_are_year_qualified() -> None:
    compiled = _load_map()
    for pack_id, entry in compiled["packs"].items():
        for key in entry["linked_question_ids"]:
            assert _QUESTION_KEY_RE.match(key), f"{pack_id}: bad question key {key!r}"


def test_ambiguous_weak_anchors_are_not_silently_linked() -> None:
    compiled = _load_map()
    for pack_id, entry in compiled["packs"].items():
        for item in entry["ambiguous"]:
            # 歧义候选必须 ≥2 且一个都不进 linked（如实报告，禁硬塞）。
            candidates = item["candidates"]
            assert len(candidates) >= 2, f"{pack_id}: ambiguous with <2 candidates"
            leaked = set(candidates) & set(entry["linked_question_ids"])
            assert not leaked, f"{pack_id}: ambiguous candidates leaked into linked: {leaked}"


def test_reverse_index_is_consistent_with_packs() -> None:
    compiled = _load_map()
    expected: dict[str, list[str]] = {}
    for pack_id, entry in compiled["packs"].items():
        for key in entry["linked_question_ids"]:
            expected.setdefault(key, []).append(pack_id)
    expected = {key: sorted(value) for key, value in expected.items()}
    assert compiled["reverse_index"] == expected


def _load_compiler_module():
    script = REPO_ROOT / "scripts/compile_luban_question_pack_map.py"
    spec = importlib.util.spec_from_file_location("compile_luban_question_pack_map", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_compiled_map_is_deterministic_rebuild() -> None:
    # 题库快照已收进 repo(3.3MB)——本测试在任何 checkout/CI 上都真跑,
    # 不再有"数据盘缺失即 skip"的假绿窗口。
    module = _load_compiler_module()
    assert module.DEFAULT_BANK_ROOT.exists(), "repo-local bank snapshot must exist"
    rebuilt = module.compile_map(module.DEFAULT_BANK_ROOT)
    on_disk = _load_map()
    assert rebuilt == on_disk, "question-pack map drifted — rerun the compile script"


def test_sources_hashes_are_independently_verifiable() -> None:
    # 溯源反自证:测试(核验方)直接重算快照文件 sha256 对照产物 sources 段,
    # 与编译动作(声称方)物理分离。
    import hashlib

    compiled = _load_map()
    sources = compiled.get("sources") or []
    assert len(sources) == 11, "11 个年卷源必须全部登记"
    for source in sources:
        path = REPO_ROOT / source["relpath"]
        assert path.exists(), f"source file missing: {source['relpath']}"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == source["sha256"], f"source drifted: {source['relpath']}"
        assert source["chunk_count"] > 0
