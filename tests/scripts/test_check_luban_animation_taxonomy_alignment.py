from __future__ import annotations

import json
from pathlib import Path

from scripts.check_luban_animation_taxonomy_alignment import (
    DEFAULT_REGISTRY_PATH,
    DEFAULT_TAXONOMY_PATH,
    evaluate_alignment,
)


def _taxonomy(tmp_path: Path, codes: list[str] | None = None) -> Path:
    payload = {"nodes": [{"code": code, "name": code} for code in (codes or ["1A431030-E01", "1A436000-B029"])]}
    path = tmp_path / "taxonomy.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _registry(tmp_path: Path, *, code: str = "1A431030-E01", status: str = "direct") -> Path:
    text = f"""# test registry

| Slot | Pack ID | Student title | Canonical taxonomy refs | Status | Note |
|---:|---|---|---|---|---|
| 1 | J01 | 危大工程专家论证 | `{code}` | `{status}` | test |
"""
    path = tmp_path / "registry.md"
    path.write_text(text, encoding="utf-8")
    return path


def _manifest(
    tmp_path: Path,
    *,
    pack_id: str = "J01_danger_work_expert_argumentation",
    primary: str = "1A431030-E01",
    status: str = "direct",
    title: str = "危大工程专家论证",
    authority_status: str = "candidate",
) -> Path:
    payload = {
        "pack_id": pack_id,
        "primary_taxonomy_ref": primary,
        "supporting_taxonomy_refs": [],
        "taxonomy_alignment_status": status,
        "student_title": title,
        "authority": {"status": authority_status, "official_score_allowed": False},
    }
    path = tmp_path / f"{pack_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_current_registry_resolves_all_taxonomy_codes() -> None:
    result = evaluate_alignment(
        registry_path=DEFAULT_REGISTRY_PATH,
        taxonomy_path=DEFAULT_TAXONOMY_PATH,
    )
    assert result.ok
    assert result.registry_rows >= 60
    assert result.manifest_count == 0


def test_registry_unknown_taxonomy_code_fails(tmp_path: Path) -> None:
    result = evaluate_alignment(
        registry_path=_registry(tmp_path, code="1A499999-BAD"),
        taxonomy_path=_taxonomy(tmp_path),
        min_registry_rows=1,
    )
    assert not result.ok
    assert any("unknown taxonomy ref 1A499999-BAD" in error for error in result.errors)


def test_manifest_pack_must_be_registered(tmp_path: Path) -> None:
    result = evaluate_alignment(
        registry_path=_registry(tmp_path),
        taxonomy_path=_taxonomy(tmp_path),
        manifest_paths=[_manifest(tmp_path, pack_id="N99_new_pack")],
        min_registry_rows=1,
    )
    assert not result.ok
    assert any("not registered in taxonomy alignment registry" in error for error in result.errors)


def test_manifest_taxonomy_ref_must_match_registry(tmp_path: Path) -> None:
    result = evaluate_alignment(
        registry_path=_registry(tmp_path),
        taxonomy_path=_taxonomy(tmp_path, codes=["1A431030-E01", "1A436000-B029"]),
        manifest_paths=[_manifest(tmp_path, primary="1A436000-B029")],
        min_registry_rows=1,
    )
    assert not result.ok
    assert any("is not registered for pack J01" in error for error in result.errors)


def test_production_like_manifest_cannot_use_coarse_review(tmp_path: Path) -> None:
    result = evaluate_alignment(
        registry_path=_registry(tmp_path, status="coarse_review"),
        taxonomy_path=_taxonomy(tmp_path),
        manifest_paths=[_manifest(tmp_path, status="coarse_review", authority_status="production")],
        min_registry_rows=1,
    )
    assert not result.ok
    assert any("production-like pack cannot use coarse_review" in error for error in result.errors)


def test_student_facing_manifest_text_cannot_leak_raw_code(tmp_path: Path) -> None:
    result = evaluate_alignment(
        registry_path=_registry(tmp_path),
        taxonomy_path=_taxonomy(tmp_path),
        manifest_paths=[_manifest(tmp_path, title="危大工程 1A431030-E01")],
        min_registry_rows=1,
    )
    assert not result.ok
    assert any("student-facing field" in error and "raw taxonomy code" in error for error in result.errors)
