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
    review_signature_envelope_sha256,
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


# s05-fact-below-50kw-measures 无有效锚（kc/quote 双空、真题锚不支撑断言），
# 其唯一变体 S05-F-mgmt-067 被剔除，不进本批候选（bank 仍原样保留 75 条）。
_S05_EXCLUDED_VARIANT_IDS = {"S05-F-mgmt-067"}


def test_covers_every_bank_variant_except_unanchored(s05_payload) -> None:
    bank = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    bank_ids = [v["variant_id"] for v in bank["variants"]]
    assert len(bank_ids) == 75  # bank 只读、原样保留
    item_ids = [row["variant_id"] for row in s05_payload["items"]]
    expected = [vid for vid in bank_ids if vid not in _S05_EXCLUDED_VARIANT_IDS]
    assert item_ids == expected
    assert s05_payload["candidate_count"] == len(expected) == 74


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
        # 签名信封（二轮 B1）：pending 候选即带信封摘要，bake 后可直接核验
        assert decision["review"][
            "signature_envelope_sha256"
        ] == review_signature_envelope_sha256(decision)


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


def test_e_color_item_source_anchor_drops_mismatched_kc(s05_payload) -> None:
    """对抗审查二轮 E5 余项：行级 source_anchor 也必须剥掉错锚 KC 头，
    只保留已裁决的 2019 真题证据（fact 摘要修了、行级证据也要修）。"""
    color_rows = [
        row for row in s05_payload["items"] if row["rule_group"] == "E-color"
    ]
    assert len(color_rows) == 3
    for row in color_rows:
        source_anchor = row["decision_candidate"]["source_anchor"]
        assert "1A431011_014_0015:1" not in source_anchor, row["variant_id"]
        assert source_anchor == "{2019,第14题}", row["variant_id"]
        # bank 原文 anchor 如实保留（content identity 覆盖它，不得改写）
        assert "kc:1A431011_014_0015:1" in row["anchor"]


def test_n01_fact_summary_matches_actual_assignment(n01_payload) -> None:
    """对抗审查二轮新病 1：facts[] 元数据必须与实际挂载一致——
    zero-float fact 摘要不得再含「延误≤总时差不影响」子句（已拆去新 fact），
    rule_group 必须如实反映 A-line + C-delay 两组来源。"""
    facts = {fact["fact_id"]: fact for fact in n01_payload["facts"]}
    zero_float = facts["n01-fact-critical-work-zero-float"]
    delay_float = facts["n01-fact-delay-vs-total-float"]
    # 新旧 fact 摘要不得语义包含（新 fact 不是旧 fact 摘要的子集）
    assert delay_float["correct_statement"] not in zero_float["correct_statement"]
    assert "总时差最小" in zero_float["correct_statement"]  # 判据面并入
    assert "延误 ≤" not in zero_float["correct_statement"]
    # rule_group 如实反映实际挂载的两组
    assert zero_float["rule_group"] == "A-line/C-delay"
    assert zero_float["variant_count"] == 4
    assert delay_float["rule_group"] == "C-delay"


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


# 判分句禁词族（2026-07-16 终轮对抗审查裁决）：loss_reason/temptation 永久
# 剥除的判分承诺句。注：枚举禁词是止血带、非充分门（同义改写可绕过枚举）——
# 真正的防线是「loss_reason 只含来源事实 + correct_statement + 题面差异」的
# 富化纪律 + 人工逐条复核；本测试只堵已知病句回流。
_FORBIDDEN_GRADING_PHRASES = (
    "把对判错同样丢分",
    "判断方向错了同样丢分",
    "丢分",
    "扣分",
    "采分点",
    "缺一件丢一分",
    "阅卷按",
)


def test_no_grading_commitment_phrases(s05_payload, n01_payload) -> None:
    """判分句禁词族不得出现在任一 loss_reason/temptation。"""
    for payload in (s05_payload, n01_payload):
        for row in payload["items"]:
            decision = row["decision_candidate"]
            for phrase in _FORBIDDEN_GRADING_PHRASES:
                assert phrase not in decision["loss_reason"], (
                    row["variant_id"],
                    phrase,
                )
                assert phrase not in decision["temptation"], (
                    row["variant_id"],
                    phrase,
                )


def test_c_voltage_drops_unsourced_generalization(s05_payload) -> None:
    """C 组「环境越危险，电压档位越低」泛化无来源（教材只列各场所具体限值），
    模板层已剥除。"""
    for row in s05_payload["items"]:
        if row["rule_group"] == "C-voltage":
            assert "环境越危险" not in row["decision_candidate"]["loss_reason"]


def test_unanchored_fact_excluded_from_candidates(s05_payload) -> None:
    """无有效锚 fact 不进本批候选：facts[] 与 items[] 均无它及其变体。"""
    fact_ids = {f["fact_id"] for f in s05_payload["facts"]}
    assert "s05-fact-below-50kw-measures" not in fact_ids
    item_facts = {r["decision_candidate"]["fact_id"] for r in s05_payload["items"]}
    assert "s05-fact-below-50kw-measures" not in item_facts
    item_ids = {r["variant_id"] for r in s05_payload["items"]}
    assert "S05-F-mgmt-067" not in item_ids


def test_n01_zero_float_identity_note_present(n01_payload) -> None:
    """N01 identity 之争终裁：zero-float 命名不变，候选文件显式声明复合事实，
    005/006 名实异议逐条记 adjudicated-note（条目保留）。"""
    fact = next(
        f
        for f in n01_payload["facts"]
        if f["fact_id"] == "n01-fact-critical-work-zero-float"
    )
    assert "命名沿用 MCQ 签发先例" in fact.get("adjudicated_note", "")
    notes = {
        r["variant_id"]: r.get("adjudicated_note", "") for r in n01_payload["items"]
    }
    for vid in ("N01-A-line-005", "N01-A-line-006"):
        assert "名实" in notes[vid], vid
        # 条目保留：仍在候选、fact 仍挂 zero-float（沿用 MCQ 先例）
        assert vid in notes
    fact_of = {
        r["variant_id"]: r["decision_candidate"]["fact_id"] for r in n01_payload["items"]
    }
    assert fact_of["N01-A-line-005"] == "n01-fact-critical-work-zero-float"
    assert fact_of["N01-A-line-006"] == "n01-fact-critical-work-zero-float"


def test_n01_procedure_fact_not_overclaiming(n01_payload) -> None:
    """F-procedure fact 已按 2026-07-17 增量复核终裁整体剔出本批:bank 的
    canonical correct_statement 携带「含补虚工作」复合断言,候选层不得覆盖已签
    bank 文本(第二真相),治本归编译管道批。本批候选中该 fact 与其条目必须缺席;
    「补虚工作」证据只留在 G-logic 具体案例 fact。"""
    assert not any(
        f["fact_id"] == "n01-fact-network-procedure-order"
        for f in n01_payload["facts"]
    )
    assert not any(
        row["rule_group"] == "F-procedure" for row in n01_payload["items"]
    )
    assert len(n01_payload["items"]) == 40
    # 补虚工作证据仍在 G-logic fact（未被误删）
    glogic = next(
        f
        for f in n01_payload["facts"]
        if f["fact_id"] == "n01-fact-dummy-activity-logic"
    )
    assert "补虚工作" in glogic["correct_statement"]


def test_pack_without_table_is_refused(tmp_path: Path) -> None:
    # A01 有变体银行但尚未在 _PACK_TABLES 建 fact/初稿映射表——必须拒绝，
    # 绝不产无表低质量模板（S05 与 N01 均已建表，故换 A01 验拒绝路径）。
    with pytest.raises(SystemExit):
        _mod.build_candidates("A01", BANK_PATH.parent)
