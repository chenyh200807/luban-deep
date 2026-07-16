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
    decision_identity_sha256,
    variant_content_sha256,
)

BANK_PATH = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_S05_variant_bank.v0.json"
PACKETS_DIR = (
    REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_practice_review_packets"
)
COMMITTED = PACKETS_DIR / "s05.variant.decision.candidates.json"
COMMITTED_N01 = PACKETS_DIR / "n01.variant.decision.candidates.json"

_FORBIDDEN_TONE = ("看穿", "识破", "揭穿", "露馅")

# 2026-07-16 对抗审查（S05 48/75 REFUTED + N01 6/43 REFUTED）裁决的禁句族：
# 无来源机理句、判分承诺句、题面外事实、无条件扩写——模板层面永久剥除。
_FORBIDDEN_CLAIMS = (
    "失去上级保护",  # B 组：教材只规定顺序，不给机理
    "案例题这里通常单独设采分点",  # C 组：无评分统计来源
    "一机一闸一漏一箱",  # D 组：口号无指定来源
    "无法准确分断",  # D 组：故障分断机理无来源
    "松动打火",  # D-054：机理无来源
    "误判带电导体",  # E-color：后果无来源
    "安全员不具备电工作业资格",  # F-065：把题面缺证写成个人确定事实
    "已经编了安全用电措施",  # F-066：题面不存在的新增事实
    "用电部位与负荷发生变化",  # F-068：未提供的原因当教材事实
    "降低保护动作",  # X 组：机理无来源
    "阅卷按",  # N01：判分承诺
    "缺一件丢一分",  # N01 B-expr：虚构评分分配
    "被机动时间",  # N01 C-delay：机理 gloss 无来源
    "最小为 0",  # N01 A-005：无条件扩写（教材只说总时差最小）
)


@pytest.fixture(scope="module")
def s05_payload() -> dict[str, object]:
    return _mod.build_candidates("S05", BANK_PATH.parent)


@pytest.fixture(scope="module")
def n01_payload() -> dict[str, object]:
    return _mod.build_candidates("N01", BANK_PATH.parent)


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
        # 决策治理 identity（B1）：候选即带摘要与 review 绑定，bake 后可直接核验
        assert decision["decision_identity_sha256"] == decision_identity_sha256(
            decision
        )
        assert (
            decision["review"]["reviewed_decision_sha256"]
            == decision["decision_identity_sha256"]
        )


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


def test_drafts_carry_no_unsourced_claims_or_grading_promises(
    s05_payload, n01_payload
) -> None:
    """对抗审查禁句族（无来源机理/判分承诺/题面外事实）不得回流模板。"""
    for payload in (s05_payload, n01_payload):
        for row in payload["items"]:
            decision = row["decision_candidate"]
            for phrase in _FORBIDDEN_CLAIMS:
                assert phrase not in decision["temptation"], (
                    row["variant_id"],
                    phrase,
                )
                assert phrase not in decision["loss_reason"], (
                    row["variant_id"],
                    phrase,
                )


def test_fact_quote_join_is_topic_consistent(s05_payload, n01_payload) -> None:
    """E5 类错锚防线：fact 佐证 quote 必须与 correct_statement 主题一致，
    join 不中/不一致必须如实留空——绝不把无关教材点当证据。"""
    for payload in (s05_payload, n01_payload):
        for fact in payload["facts"]:
            quote = fact["textbook_quote"]
            if quote:
                assert _mod._quote_supports(fact["correct_statement"], quote), (
                    fact["fact_id"]
                )
    # 色标 fact 的 kc join 指向三级配电（错锚）→ 必须已被剥离
    color = next(
        fact
        for fact in s05_payload["facts"]
        if fact["fact_id"] == "s05-fact-n-pe-color-code"
    )
    assert color["kc_anchor"] == ""
    assert color["textbook_quote"] == ""


def test_n01_refuted_fact_assignments_are_remapped(n01_payload) -> None:
    """N01 对抗审查 6 条 REFUTED 的改挂裁决：判据面归 zero-float，
    非关键工作「延误 vs 总时差」独立 fact，不静默复用已签发 fact。"""
    fact_of = {
        row["variant_id"]: row["decision_candidate"]["fact_id"]
        for row in n01_payload["items"]
    }
    assert fact_of["N01-A-line-005"] == "n01-fact-critical-work-zero-float"
    assert fact_of["N01-A-line-006"] == "n01-fact-critical-work-zero-float"
    for index in (10, 11, 12, 13):
        assert (
            fact_of[f"N01-C-delay-{index:03d}"] == "n01-fact-delay-vs-total-float"
        )
    for index in (14, 15):
        assert (
            fact_of[f"N01-C-delay-{index:03d}"]
            == "n01-fact-critical-work-zero-float"
        )
    # 并列线路 fact 不再包含判据面变体
    parallel = [
        vid
        for vid, fact in fact_of.items()
        if fact == "n01-fact-parallel-critical-paths"
    ]
    assert set(parallel) == {f"N01-A-line-{i:03d}" for i in range(5)}
    # 新 fact 有佐证行且双池齐备（等待人签命名先例）
    extra = next(
        fact
        for fact in n01_payload["facts"]
        if fact["fact_id"] == "n01-fact-delay-vs-total-float"
    )
    assert extra["variant_count"] == 4


def test_committed_candidates_file_is_reproducible(tmp_path: Path) -> None:
    assert COMMITTED.is_file(), "S05 富化候选文件必须随切片提交"
    assert COMMITTED_N01.is_file(), "N01 富化候选文件必须随切片提交"
    assert _mod.main(["S05", "N01", "--out-dir", str(tmp_path)]) == 0
    for committed, name in (
        (COMMITTED, "s05.variant.decision.candidates.json"),
        (COMMITTED_N01, "n01.variant.decision.candidates.json"),
    ):
        regenerated = (tmp_path / name).read_text(encoding="utf-8")
        assert regenerated == committed.read_text(encoding="utf-8")


def test_pack_without_table_is_refused(tmp_path: Path) -> None:
    # A01 有变体银行但尚未在 _PACK_TABLES 建 fact/初稿映射表——必须拒绝，
    # 绝不产无表低质量模板（S05 与 N01 均已建表，故换 A01 验拒绝路径）。
    with pytest.raises(SystemExit):
        _mod.build_candidates("A01", BANK_PATH.parent)
