"""变体 decision 机器候选生成器域测试：机器绝不代签 + 确定性 + 覆盖完整。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "prefill_variant_decision_candidates",
    REPO / "scripts" / "prefill_variant_decision_candidates.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from deeptutor.services.luban_lesson.variant_eligibility import (  # noqa: E402
    VARIANT_PROBE_ROLES,
    variant_content_sha256,
)

BANK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_S05_variant_bank.v0.json"
COMMITTED = (
    REPO
    / "docs"
    / "原始数据"
    / "考点原料"
    / "成品"
    / "_practice_review_packets"
    / "s05.variant.decision.candidates.json"
)

_FORBIDDEN_TONE = ("看穿", "识破", "揭穿", "露馅")


@pytest.fixture(scope="module")
def s05_payload() -> dict[str, object]:
    return _mod.build_candidates("S05", BANK_PATH.parent)


def test_covers_every_bank_variant_exactly_once(s05_payload) -> None:
    bank = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    bank_ids = [v["variant_id"] for v in bank["variants"]]
    item_ids = [row["variant_id"] for row in s05_payload["items"]]
    assert item_ids == bank_ids
    assert s05_payload["candidate_count"] == len(bank_ids) == 75


def test_machine_never_signs(s05_payload) -> None:
    assert s05_payload["machine_candidates_only"] is True
    for row in s05_payload["items"]:
        review = row["decision_candidate"]["review"]
        assert review["status"] == "pending"
        assert review["verdict"] == "pending"
        assert review["signatures"] == []
        assert not any(review["checks"].values())


def test_content_sha_matches_governance_identity(s05_payload) -> None:
    bank = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    variants = {v["variant_id"]: v for v in bank["variants"]}
    for row in s05_payload["items"]:
        decision = row["decision_candidate"]
        assert decision["content_sha256"] == variant_content_sha256(
            variants[row["variant_id"]],
            temptation=decision["temptation"],
            loss_reason=decision["loss_reason"],
        )
        assert decision["review"]["reviewed_content_sha256"] == decision["content_sha256"]


def test_probe_roles_cover_both_pools_per_multi_variant_fact(s05_payload) -> None:
    roles_by_fact: dict[str, set[str]] = {}
    for row in s05_payload["items"]:
        decision = row["decision_candidate"]
        assert decision["probe_role"] in VARIANT_PROBE_ROLES
        roles_by_fact.setdefault(decision["fact_id"], set()).add(
            decision["probe_role"]
        )
    counts: dict[str, int] = {}
    for row in s05_payload["items"]:
        fact = row["decision_candidate"]["fact_id"]
        counts[fact] = counts.get(fact, 0) + 1
    for fact, n in counts.items():
        if n >= 2:
            assert roles_by_fact[fact] == set(VARIANT_PROBE_ROLES), fact


def test_fact_namespace_and_skeleton_are_pack_scoped(s05_payload) -> None:
    for row in s05_payload["items"]:
        decision = row["decision_candidate"]
        assert decision["fact_id"].startswith("s05-fact-")
        assert decision["skeleton_id"].startswith("s05-vskel-")
        assert decision["skeleton_id"].endswith(("-ok", "-bad"))
    fact_ids = {f["fact_id"] for f in s05_payload["facts"]}
    assert {r["decision_candidate"]["fact_id"] for r in s05_payload["items"]} <= fact_ids


def test_drafts_are_specific_and_warm(s05_payload) -> None:
    for row in s05_payload["items"]:
        decision = row["decision_candidate"]
        assert len(decision["temptation"]) >= 10, row["variant_id"]
        assert len(decision["loss_reason"]) >= 15, row["variant_id"]
        for word in _FORBIDDEN_TONE:
            assert word not in decision["temptation"]
            assert word not in decision["loss_reason"]


def test_committed_candidates_file_is_reproducible(tmp_path: Path) -> None:
    assert COMMITTED.is_file(), "S05 富化候选文件必须随切片提交"
    assert _mod.main(["S05", "--out-dir", str(tmp_path)]) == 0
    regenerated = (tmp_path / "s05.variant.decision.candidates.json").read_text(
        encoding="utf-8"
    )
    assert regenerated == COMMITTED.read_text(encoding="utf-8")


def test_pack_without_table_is_refused(tmp_path: Path) -> None:
    # A01 有变体银行但尚未在 _PACK_TABLES 建 fact/初稿映射表——必须拒绝，
    # 绝不产无表低质量模板（S05 与 N01 均已建表，故换 A01 验拒绝路径）。
    with pytest.raises(SystemExit):
        _mod.build_candidates("A01", BANK_PATH.parent)
