"""签发变体 practice 资格投影域测试——同一资格门谓词、fail-closed 是唯一存在理由。"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from deeptutor.services.luban_lesson.variant_eligibility import (
    VARIANT_DECISION_SCHEMA,
    VARIANT_REVIEW_PACKET_SCHEMA,
    build_variant_review_packet,
    carry_variant_bank_decisions,
    decision_identity_sha256,
    eligible_variant_items,
    resolve_variant_supply,
    review_signature_envelope_sha256,
    variant_content_sha256,
    variant_eligibility_summary,
)


def _variant(
    variant_id: str = "S05-B-send-000",
    *,
    rule_group: str = "B-send",
    expected_ok: bool = True,
    extension: bool = False,
) -> dict[str, object]:
    return {
        "variant_id": variant_id,
        "rule_group": rule_group,
        "surface": "某住宅楼工地送电操作顺序：总配电箱→分配电箱→开关箱",
        "params": {"order": ["总配电箱", "分配电箱", "开关箱"], "op": "send"},
        "expected_ok": expected_ok,
        "correct_statement": "送电顺序应为总配电箱→分配电箱→开关箱",
        "anchor": "kc:1A431011_015_0016:1",
        "extension": extension,
    }


def _signed_decision(
    variant: dict[str, object],
    *,
    fact_id: str = "s05-fact-send-power-order",
    skeleton_id: str = "s05-vskel-b-send-ok",
    probe_role: str = "immediate_confirm",
    temptation: str = "送电与停电顺序容易记反。",
    loss_reason: str = "送电顺序必须是总配电箱→分配电箱→开关箱。",
) -> dict[str, object]:
    decision: dict[str, object] = {
        "schema": VARIANT_DECISION_SCHEMA,
        "fact_id": fact_id,
        "skeleton_id": skeleton_id,
        "probe_role": probe_role,
        "temptation": temptation,
        "loss_reason": loss_reason,
        "source_anchor": "kc:1A431011_015_0016:1",
        # source_sha256 必须等于 bank.source_pack_sha256（B1 收紧后）
        "source_sha256": "a" * 64,
    }
    decision["content_sha256"] = variant_content_sha256(
        variant, temptation=temptation, loss_reason=loss_reason
    )
    decision["decision_identity_sha256"] = decision_identity_sha256(decision)
    decision["review"] = {
        "status": "signed",
        "verdict": "approved",
        "reviewed_content_sha256": decision["content_sha256"],
        "reviewed_decision_sha256": decision["decision_identity_sha256"],
        "signatures": [
            {
                "role": "teaching",
                "reviewer_id": "teacher-reviewer",
                "signed_at": "2026-07-16T00:00:00Z",
            },
            {
                "role": "scoring",
                "reviewer_id": "scoring-owner",
                "signed_at": "2026-07-16T00:00:00Z",
            },
        ],
        "checks": {
            "source_verified": True,
            "answer_verified": True,
            "diagnosis_verified": True,
            "longest_option_checked": True,
            "template_leakage_checked": True,
        },
    }
    decision["review"]["signature_envelope_sha256"] = review_signature_envelope_sha256(
        decision
    )
    return decision


def _signed_bank(variants: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "luban-s05-variant-bank",
        "pack_id": "S05",
        "status": "signed",
        "source_pack_sha256": "a" * 64,
        "variants": variants,
    }


def _bank_with_ready_fact() -> dict[str, object]:
    ok = _variant("S05-B-send-000", expected_ok=True)
    ok["decision"] = _signed_decision(
        ok, skeleton_id="s05-vskel-b-send-ok", probe_role="immediate_confirm"
    )
    bad = _variant("S05-B-send-002", expected_ok=False)
    bad["surface"] = "某住宅楼工地送电操作顺序：总配电箱→开关箱→分配电箱"
    bad["expected_ok"] = False
    bad["decision"] = _signed_decision(
        bad, skeleton_id="s05-vskel-b-send-bad", probe_role="d1_probe"
    )
    return _signed_bank([ok, bad])


# ---------------------------------------------------------------- content identity


def test_content_sha_covers_enrichment_text() -> None:
    variant = _variant()
    base = variant_content_sha256(variant, temptation="甲", loss_reason="乙")
    assert base == variant_content_sha256(variant, temptation="甲", loss_reason="乙")
    assert base != variant_content_sha256(variant, temptation="改", loss_reason="乙")
    assert base != variant_content_sha256(variant, temptation="甲", loss_reason="改")
    tampered = dict(variant, surface="改了题面")
    assert base != variant_content_sha256(tampered, temptation="甲", loss_reason="乙")


# ---------------------------------------------------------------- eligibility gate


def test_fully_signed_decision_is_eligible() -> None:
    bank = _bank_with_ready_fact()
    items = eligible_variant_items(bank, blocked=set())
    assert [item["variant_id"] for item in items] == [
        "S05-B-send-000",
        "S05-B-send-002",
    ]
    assert all(item["fact_id"] == "s05-fact-send-power-order" for item in items)
    assert {item["probe_role"] for item in items} == {"immediate_confirm", "d1_probe"}
    assert all(item["temptation"] and item["loss_reason"] for item in items)


def test_missing_decision_block_is_ineligible() -> None:
    bank = _signed_bank([_variant()])
    assert eligible_variant_items(bank, blocked=set()) == []


def test_blocklisted_variant_is_revoked_not_eligible() -> None:
    bank = _bank_with_ready_fact()
    items = eligible_variant_items(bank, blocked={"S05-B-send-000"})
    assert [item["variant_id"] for item in items] == ["S05-B-send-002"]


def test_unreadable_blocklist_fails_closed() -> None:
    bank = _bank_with_ready_fact()
    assert eligible_variant_items(bank, blocked=None) == []
    summary = variant_eligibility_summary(bank, blocked=None)
    assert summary["eligible_count"] == 0
    assert summary["supply_ready"] is False


def test_content_tampering_after_signing_is_ineligible() -> None:
    bank = _bank_with_ready_fact()
    bank["variants"][0]["surface"] = "签后被改的题面"
    items = eligible_variant_items(bank, blocked=set())
    assert [item["variant_id"] for item in items] == ["S05-B-send-002"]


def test_enrichment_tampering_after_signing_is_ineligible() -> None:
    bank = _bank_with_ready_fact()
    bank["variants"][0]["decision"]["temptation"] = "签后被改的文案"
    items = eligible_variant_items(bank, blocked=set())
    assert [item["variant_id"] for item in items] == ["S05-B-send-002"]


# --------------------------------------------------- decision identity（对抗审查 B1）


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("fact_id", "s05-fact-stop-power-order"),
        ("skeleton_id", "s05-vskel-b-send-bad"),
        # 在两个合法 role 之间切换——role 本身合法，identity 必须仍能抓住
        ("probe_role", "d1_probe"),
        ("source_anchor", "kc:1A431011_014_0015:1"),
        ("source_sha256", "c" * 64),
    ],
)
def test_governance_field_tampering_after_signing_is_ineligible(
    field: str, tampered: str
) -> None:
    bank = _bank_with_ready_fact()
    decision = bank["variants"][0]["decision"]
    assert decision[field] != tampered
    decision[field] = tampered
    items = eligible_variant_items(bank, blocked=set())
    assert [item["variant_id"] for item in items] == ["S05-B-send-002"]


def test_identity_recompute_without_review_rebind_is_ineligible() -> None:
    """篡改治理字段并重算 identity 摘要，但 review 仍绑旧摘要 → fail-closed。"""
    bank = _bank_with_ready_fact()
    decision = bank["variants"][0]["decision"]
    decision["fact_id"] = "s05-fact-hijacked"
    decision["decision_identity_sha256"] = decision_identity_sha256(decision)
    items = eligible_variant_items(bank, blocked=set())
    assert [item["variant_id"] for item in items] == ["S05-B-send-002"]


def test_source_sha_must_equal_bank_source_pack_sha() -> None:
    """整体自洽（identity/review 全重算）但 source_sha256 != bank sha → 不 eligible。"""
    variant = _variant()
    decision = _signed_decision(variant)
    decision["source_sha256"] = "c" * 64
    decision["decision_identity_sha256"] = decision_identity_sha256(decision)
    decision["review"]["reviewed_decision_sha256"] = decision[
        "decision_identity_sha256"
    ]
    variant["decision"] = decision
    assert eligible_variant_items(_signed_bank([variant]), blocked=set()) == []


def test_decision_missing_identity_sha_fails_closed() -> None:
    bank = _bank_with_ready_fact()
    del bank["variants"][0]["decision"]["decision_identity_sha256"]
    items = eligible_variant_items(bank, blocked=set())
    assert [item["variant_id"] for item in items] == ["S05-B-send-002"]


def test_review_missing_decision_binding_fails_closed() -> None:
    bank = _bank_with_ready_fact()
    del bank["variants"][0]["decision"]["review"]["reviewed_decision_sha256"]
    items = eligible_variant_items(bank, blocked=set())
    assert [item["variant_id"] for item in items] == ["S05-B-send-002"]


# ---------------------------------------- signature envelope（对抗审查二轮 B1）


def _assert_only_second_item_eligible(bank: dict[str, object]) -> None:
    items = eligible_variant_items(bank, blocked=set())
    assert [item["variant_id"] for item in items] == ["S05-B-send-002"]


def test_replacing_reviewer_after_signing_is_ineligible() -> None:
    bank = _bank_with_ready_fact()
    review = bank["variants"][0]["decision"]["review"]
    review["signatures"][0]["reviewer_id"] = "impostor-reviewer"
    _assert_only_second_item_eligible(bank)


def test_changing_signed_at_after_signing_is_ineligible() -> None:
    bank = _bank_with_ready_fact()
    review = bank["variants"][0]["decision"]["review"]
    review["signatures"][1]["signed_at"] = "2026-07-17T09:00:00Z"
    _assert_only_second_item_eligible(bank)


def test_appending_forged_signature_is_ineligible() -> None:
    bank = _bank_with_ready_fact()
    review = bank["variants"][0]["decision"]["review"]
    review["signatures"].append(
        {
            "role": "scoring",
            "reviewer_id": "forged-owner",
            "signed_at": "2026-07-17T00:00:00Z",
        }
    )
    _assert_only_second_item_eligible(bank)


def test_reordering_signatures_is_ineligible() -> None:
    bank = _bank_with_ready_fact()
    review = bank["variants"][0]["decision"]["review"]
    review["signatures"] = list(reversed(review["signatures"]))
    _assert_only_second_item_eligible(bank)


def test_adding_extra_field_to_signature_is_ineligible() -> None:
    bank = _bank_with_ready_fact()
    review = bank["variants"][0]["decision"]["review"]
    review["signatures"][0]["scope"] = "偷偷缩小签署范围"
    _assert_only_second_item_eligible(bank)


def test_adding_or_editing_review_note_is_ineligible() -> None:
    bank = _bank_with_ready_fact()
    bank["variants"][0]["decision"]["review"]["note"] = "签后偷加的批注"
    _assert_only_second_item_eligible(bank)


def test_missing_signature_envelope_fails_closed() -> None:
    bank = _bank_with_ready_fact()
    del bank["variants"][0]["decision"]["review"]["signature_envelope_sha256"]
    _assert_only_second_item_eligible(bank)


def test_envelope_recompute_cannot_bless_identity_tamper() -> None:
    """改治理字段 + 重算 envelope，但 identity/review binding 仍抓得住。"""
    bank = _bank_with_ready_fact()
    decision = bank["variants"][0]["decision"]
    decision["fact_id"] = "s05-fact-hijacked"
    decision["review"]["signature_envelope_sha256"] = (
        review_signature_envelope_sha256(decision)
    )
    _assert_only_second_item_eligible(bank)


def test_anchor_probe_role_is_reserved_for_compiled_mcq() -> None:
    variant = _variant()
    variant["decision"] = _signed_decision(variant, probe_role="anchor")
    bank = _signed_bank([variant])
    assert eligible_variant_items(bank, blocked=set()) == []


def test_missing_scoring_signature_is_ineligible() -> None:
    bank = _bank_with_ready_fact()
    review = bank["variants"][0]["decision"]["review"]
    review["signatures"] = [s for s in review["signatures"] if s["role"] == "teaching"]
    items = eligible_variant_items(bank, blocked=set())
    assert [item["variant_id"] for item in items] == ["S05-B-send-002"]


def test_extension_variants_never_serve() -> None:
    ext = _variant("S05-X-distance-069", rule_group="X-distance", extension=True)
    ext["decision"] = _signed_decision(ext, fact_id="s05-fact-switchbox-distance")
    bank = _signed_bank([ext])
    assert eligible_variant_items(bank, blocked=set()) == []


def test_unsigned_bank_yields_nothing() -> None:
    bank = _bank_with_ready_fact()
    bank["status"] = "candidate"
    assert eligible_variant_items(bank, blocked=set()) == []
    assert variant_eligibility_summary(bank, blocked=set())["supply_ready"] is False


# ---------------------------------------------------------------- fact readiness


def test_fact_with_both_roles_and_two_skeletons_is_ready() -> None:
    summary = variant_eligibility_summary(_bank_with_ready_fact(), blocked=set())
    assert summary["eligible_count"] == 2
    assert summary["ready_fact_ids"] == ["s05-fact-send-power-order"]
    assert summary["supply_ready"] is True
    fact = summary["facts"]["s05-fact-send-power-order"]
    assert fact["immediate_confirm"] == 1
    assert fact["d1_probe"] == 1
    assert fact["skeletons"] == 2
    assert fact["ready"] is True


def test_single_item_fact_is_not_ready() -> None:
    variant = _variant()
    variant["decision"] = _signed_decision(variant)
    summary = variant_eligibility_summary(_signed_bank([variant]), blocked=set())
    assert summary["eligible_count"] == 1
    assert summary["ready_fact_ids"] == []
    assert summary["supply_ready"] is False


def test_same_skeleton_pair_is_not_ready() -> None:
    bank = _bank_with_ready_fact()
    variant = bank["variants"][1]
    variant["decision"] = _signed_decision(
        variant, skeleton_id="s05-vskel-b-send-ok", probe_role="d1_probe"
    )
    summary = variant_eligibility_summary(bank, blocked=set())
    assert summary["eligible_count"] == 2
    assert summary["ready_fact_ids"] == []
    assert summary["supply_ready"] is False


# ---------------------------------------------------------------- review packet


def test_review_packet_covers_all_variants_and_never_machine_signs() -> None:
    ok = _variant("S05-B-send-000")
    ext = _variant("S05-X-distance-069", rule_group="X-distance", extension=True)
    bank = _signed_bank([ok, ext])
    packet = build_variant_review_packet(bank, blocked=set())
    assert packet["schema"] == VARIANT_REVIEW_PACKET_SCHEMA
    assert packet["pack_id"] == "S05"
    assert packet["source_pack_sha256"] == "a" * 64
    assert packet["human_gate"]["machine_must_not_sign"] is True
    assert packet["candidate_count"] == 2
    assert packet["eligible_count"] == 0
    rows = packet["items"]
    assert [row["variant_id"] for row in rows] == [
        "S05-B-send-000",
        "S05-X-distance-069",
    ]
    assert rows[0]["extension"] is False
    assert rows[1]["extension"] is True
    for row in rows:
        decision = row["decision"]
        assert decision["fact_id"] == ""
        assert decision["review"]["status"] == "pending"
        assert decision["review"]["signatures"] == []
        assert not any(decision["review"]["checks"].values())
        assert decision["content_sha256"] == variant_content_sha256(
            next(v for v in bank["variants"] if v["variant_id"] == row["variant_id"]),
            temptation="",
            loss_reason="",
        )
        assert decision["decision_identity_sha256"] == decision_identity_sha256(
            decision
        )
        assert (
            decision["review"]["reviewed_decision_sha256"]
            == decision["decision_identity_sha256"]
        )
    assert "longest_option_checked" in packet["instructions"]["checks"]


def test_review_packet_passes_through_baked_decisions() -> None:
    bank = _bank_with_ready_fact()
    packet = build_variant_review_packet(bank, blocked=set())
    assert packet["eligible_count"] == 2
    decision = packet["items"][0]["decision"]
    assert decision["fact_id"] == "s05-fact-send-power-order"
    assert decision["review"]["status"] == "signed"


def test_review_packet_marks_identity_broken_decisions_stale(  # 对抗审查 B3
) -> None:
    """题面签后被改：人审包绝不显示旧 signed 外观，必须标 stale+原因。"""
    bank = _bank_with_ready_fact()
    bank["variants"][0]["surface"] = "签后被改的题面"
    packet = build_variant_review_packet(bank, blocked=set())
    assert packet["eligible_count"] == 1  # runtime 面同步 fail-closed
    stale_review = packet["items"][0]["decision"]["review"]
    assert stale_review["status"] == "stale"
    assert stale_review["verdict"] == "invalid"
    assert stale_review["stale_reason"]
    assert packet["items"][1]["decision"]["review"]["status"] == "signed"


def test_review_packet_marks_governance_tampering_stale() -> None:
    bank = _bank_with_ready_fact()
    bank["variants"][0]["decision"]["fact_id"] = "s05-fact-hijacked"
    packet = build_variant_review_packet(bank, blocked=set())
    review = packet["items"][0]["decision"]["review"]
    assert review["status"] == "stale"
    assert review["verdict"] == "invalid"


def _rebless_envelope(decision: dict[str, object]) -> None:
    """模拟攻击者把 envelope 也重算干净（测非 envelope 维度的分叉必须仍被抓）。"""
    decision["review"]["signature_envelope_sha256"] = (
        review_signature_envelope_sha256(decision)
    )


def test_review_packet_marks_reviewed_content_mismatch_stale() -> None:
    """runtime 因 reviewed_content_sha256 失配拒绝：人审面同步失去 signed 外观。"""
    bank = _bank_with_ready_fact()
    decision = bank["variants"][0]["decision"]
    decision["review"]["reviewed_content_sha256"] = "f" * 64
    _rebless_envelope(decision)
    packet = build_variant_review_packet(bank, blocked=set())
    assert packet["eligible_count"] == 1
    review = packet["items"][0]["decision"]["review"]
    assert review["status"] == "stale"
    assert review["verdict"] == "invalid"
    assert review["stale_reason"]


def test_review_packet_marks_missing_role_signature_stale() -> None:
    bank = _bank_with_ready_fact()
    decision = bank["variants"][0]["decision"]
    decision["review"]["signatures"] = [
        s for s in decision["review"]["signatures"] if s["role"] == "teaching"
    ]
    _rebless_envelope(decision)
    packet = build_variant_review_packet(bank, blocked=set())
    review = packet["items"][0]["decision"]["review"]
    assert review["status"] == "stale"
    assert review["verdict"] == "invalid"


def test_review_packet_marks_false_check_stale() -> None:
    bank = _bank_with_ready_fact()
    decision = bank["variants"][0]["decision"]
    decision["review"]["checks"]["diagnosis_verified"] = False
    _rebless_envelope(decision)
    packet = build_variant_review_packet(bank, blocked=set())
    review = packet["items"][0]["decision"]["review"]
    assert review["status"] == "stale"
    assert review["verdict"] == "invalid"


def test_review_packet_with_unreadable_blocklist_never_shows_signed() -> None:
    """撤发 authority 不可读：runtime 全 fail-closed，人审面不得再展示 signed。"""
    bank = _bank_with_ready_fact()
    packet = build_variant_review_packet(bank, blocked=None)
    assert packet["eligible_count"] == 0
    for row in packet["items"]:
        review = row["decision"]["review"]
        assert review["status"] != "signed"
        assert review["verdict"] != "approved"


def test_review_packet_marks_blocklisted_variant_revoked_not_signed() -> None:
    bank = _bank_with_ready_fact()
    packet = build_variant_review_packet(bank, blocked={"S05-B-send-000"})
    assert packet["eligible_count"] == 1
    review = packet["items"][0]["decision"]["review"]
    assert review["status"] == "revoked"
    assert review["verdict"] == "revoked"
    assert review["stale_reason"]
    assert packet["items"][1]["decision"]["review"]["status"] == "signed"


# ---------------------------------------------------------------- resolve (同一签发闸)


def _write_supply_files(tmp_path: Path, bank: dict[str, object]) -> Path:
    manifest = tmp_path / "_pack_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "projection_green": ["S05"],
                "packs": [
                    {
                        "pack_id": "S05",
                        "content_sha256": bank["source_pack_sha256"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "_S05_variant_bank.v0.json").write_text(
        json.dumps(bank, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "_variant_blocklist.json").write_text(
        json.dumps({"variants": []}), encoding="utf-8"
    )
    return manifest


def test_resolve_variant_supply_reuses_signing_gate(tmp_path: Path) -> None:
    manifest = _write_supply_files(tmp_path, _bank_with_ready_fact())
    supply = resolve_variant_supply("S05", manifest_path=manifest)
    assert supply is not None
    assert supply["summary"]["supply_ready"] is True
    assert len(supply["items"]) == 2


def test_resolve_variant_supply_rejects_sha_drift(tmp_path: Path) -> None:
    bank = _bank_with_ready_fact()
    drifted = copy.deepcopy(bank)
    drifted["source_pack_sha256"] = "c" * 64
    manifest = _write_supply_files(tmp_path, bank)
    (tmp_path / "_S05_variant_bank.v0.json").write_text(
        json.dumps(drifted, ensure_ascii=False), encoding="utf-8"
    )
    assert resolve_variant_supply("S05", manifest_path=manifest) is None


def test_resolve_variant_supply_fails_closed_without_blocklist(tmp_path: Path) -> None:
    manifest = _write_supply_files(tmp_path, _bank_with_ready_fact())
    (tmp_path / "_variant_blocklist.json").unlink()
    assert resolve_variant_supply("S05", manifest_path=manifest) is None


def test_resolve_variant_supply_requires_projection_green(  # 对抗审查 B2
    tmp_path: Path,
) -> None:
    """pack 在 manifest.packs 且 bank signed+sha 匹配，但不在 projection_green
    （撤回/未发布）→ 供给必须为 None，不得越过 canonical 发布门。"""
    manifest = _write_supply_files(tmp_path, _bank_with_ready_fact())
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["projection_green"] = []
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert resolve_variant_supply("S05", manifest_path=manifest) is None


# ------------------------------------------------- builder 重建保留合并（bake 前置）


def _rebuilt_payload(bank: dict[str, object]) -> dict[str, object]:
    """模拟 builder 重建产物：同 source、变体不带 decision、status 回 candidate。"""
    payload = copy.deepcopy(bank)
    payload["status"] = "candidate"
    payload.pop("signoff", None)
    for variant in payload["variants"]:
        variant.pop("decision", None)
    return payload


def _write_bank(tmp_path: Path, bank: dict[str, object]) -> Path:
    path = tmp_path / "_S05_variant_bank.v0.json"
    path.write_text(
        json.dumps(bank, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return path


def test_carry_preserves_signed_decisions_by_id_and_content(tmp_path: Path) -> None:
    """variant_id + content_sha256 双比中——已签 decision 逐字节保留合并。"""
    bank = _bank_with_ready_fact()
    path = _write_bank(tmp_path, bank)
    payload = _rebuilt_payload(bank)
    stats = carry_variant_bank_decisions(path, payload)
    assert stats == {"preserved": 2, "stale": 0, "dropped": 0}
    for variant, original in zip(payload["variants"], bank["variants"]):
        assert variant["decision"] == original["decision"]
    # 保留后的条目在 signed bank 语义下仍然 eligible（保留没有折损签名）
    payload["status"] = "signed"
    assert len(eligible_variant_items(payload, blocked=set())) == 2


def test_carry_resets_content_drift_to_pending_stale(tmp_path: Path) -> None:
    """内容漂移的条目绝不静默保留旧签名——置回 pending + stale 标记。"""
    bank = _bank_with_ready_fact()
    path = _write_bank(tmp_path, bank)
    payload = _rebuilt_payload(bank)
    payload["variants"][0]["surface"] = "重建后被修订的题面"
    stats = carry_variant_bank_decisions(path, payload)
    assert stats == {"preserved": 1, "stale": 1, "dropped": 0}
    stale = payload["variants"][0]["decision"]
    review = stale["review"]
    assert review["status"] == "pending"
    assert review["verdict"] == "pending"
    assert review["signatures"] == []
    assert not any(review["checks"].values())
    assert "漂移" in review["stale_reason"]
    # identity 对新内容自洽（decision 是合法 pending 候选，不是残签名）
    assert stale["content_sha256"] == variant_content_sha256(
        payload["variants"][0],
        temptation=stale["temptation"],
        loss_reason=stale["loss_reason"],
    )
    assert stale["decision_identity_sha256"] == decision_identity_sha256(stale)
    assert review["signature_envelope_sha256"] == review_signature_envelope_sha256(
        stale
    )
    # 漂移条目在 signed bank 语义下不再 eligible
    payload["status"] = "signed"
    eligible = {i["variant_id"] for i in eligible_variant_items(payload, blocked=set())}
    assert payload["variants"][0]["variant_id"] not in eligible


def test_carry_resets_source_pack_drift_to_stale(tmp_path: Path) -> None:
    """pack 正文修订（source_pack_sha256 变更）——全部 decision 置 stale。"""
    bank = _bank_with_ready_fact()
    path = _write_bank(tmp_path, bank)
    payload = _rebuilt_payload(bank)
    payload["source_pack_sha256"] = "d" * 64
    stats = carry_variant_bank_decisions(path, payload)
    assert stats == {"preserved": 0, "stale": 2, "dropped": 0}
    for variant in payload["variants"]:
        assert variant["decision"]["source_sha256"] == "d" * 64
        assert variant["decision"]["review"]["status"] == "pending"


def test_carry_is_idempotent_across_rebuilds(tmp_path: Path) -> None:
    """stale 置回后再重建（内容不再变）——第二轮如实保留 pending，不再翻新。"""
    bank = _bank_with_ready_fact()
    path = _write_bank(tmp_path, bank)
    payload = _rebuilt_payload(bank)
    payload["variants"][0]["surface"] = "重建后被修订的题面"
    carry_variant_bank_decisions(path, payload)
    _write_bank(tmp_path, payload)
    second = _rebuilt_payload(payload)
    second["variants"][0]["surface"] = "重建后被修订的题面"
    stats = carry_variant_bank_decisions(path, second)
    assert stats == {"preserved": 2, "stale": 0, "dropped": 0}
    assert second["variants"][0]["decision"] == payload["variants"][0]["decision"]


def test_carry_noop_without_previous_bank(tmp_path: Path) -> None:
    payload = _rebuilt_payload(_bank_with_ready_fact())
    stats = carry_variant_bank_decisions(tmp_path / "missing.json", payload)
    assert stats == {"preserved": 0, "stale": 0, "dropped": 0}
    assert all("decision" not in v for v in payload["variants"])


def test_carry_drops_malformed_decision_blocks(tmp_path: Path) -> None:
    """旧 decision 形状不可信——整块丢弃（绝不携带垃圾进新 bank）。"""
    bank = _bank_with_ready_fact()
    bank["variants"][0]["decision"] = {"schema": "wrong", "review": "not-a-dict"}
    path = _write_bank(tmp_path, bank)
    payload = _rebuilt_payload(bank)
    stats = carry_variant_bank_decisions(path, payload)
    assert stats == {"preserved": 1, "stale": 0, "dropped": 1}
    assert "decision" not in payload["variants"][0]
