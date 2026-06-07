"""Canonical resolution bridge — verified-registry wiring (deprecated concepts excluded).

Proves the bridge resolves to canonical codes and, when the verified concept registry is present,
never resolves to a registry-deprecated (dual-model fabricated) concept. Hermetic.
"""
from __future__ import annotations

import json

from deeptutor.services.construction_grading import canonical_resolution as CR


def _setup(tmp_path, monkeypatch, deprecated_code):
    idx_dir = tmp_path / "idx"
    idx_dir.mkdir()
    (idx_dir / "canonical_taxonomy_index.json").write_text(json.dumps({
        "leaves": [
            {"code": "1A413031-01", "name_path": "地基 > 强夯法", "keywords": ["强夯", "夯锤"]},
            {"code": deprecated_code, "name_path": "虚构 > 泛化", "keywords": ["泛化测试项"]},
        ]}), "utf-8")
    reg_dir = tmp_path / "reg"
    reg_dir.mkdir()
    (reg_dir / "concept_registry.json").write_text(json.dumps({"concepts": {
        "c_real": {"alias_codes": ["1A413031-01"], "lifecycle": {"status": "active"}},
        "c_fake": {"alias_codes": [deprecated_code], "lifecycle": {"status": "deprecated"}},
    }}), "utf-8")
    monkeypatch.setattr(CR, "_INDEX_DIR", idx_dir)
    monkeypatch.setattr(CR, "_REGISTRY_DIR", reg_dir)
    for fn in (CR._index, CR._registry, CR.to_canonical):
        fn.cache_clear()


def test_resolves_active_concept(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "1A413099-01")
    assert CR.to_canonical("强夯法夯锤质量") == "1A413031-01"
    assert CR.to_canonical("", "1A413031-01") == "1A413031-01"  # explicit active code
    for fn in (CR._index, CR._registry, CR.to_canonical):
        fn.cache_clear()


def test_deprecated_concept_never_resolved(tmp_path, monkeypatch):
    dep = "1A413099-01"
    _setup(tmp_path, monkeypatch, dep)
    # explicit deprecated code -> refused
    assert CR.to_canonical("", dep) == ""
    # keyword that only matches the deprecated leaf -> not resolved to it
    assert CR.to_canonical("泛化测试项内容") == ""
    for fn in (CR._index, CR._registry, CR.to_canonical):
        fn.cache_clear()
