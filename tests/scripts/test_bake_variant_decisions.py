"""变体决策 bake 转写工具域测试——幂等、identity fail-closed、整包 abort 不落盘。

设计：docs/plan/鲁班移动端提分闭环/2026-07-16-variant-eligibility-design.md §4。
bake = 决策卡确认后的「候选 + 签发 spec → bank 原位 decision 块」转写；
机器绝不自铸真值：签名内容全部来自 owner-delegated spec，identity 三链
（content / decision / envelope）逐条重算比中，任一失配整包 abort、bank 不动。
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys

from deeptutor.services.luban_lesson.variant_eligibility import (
    VARIANT_DECISION_SCHEMA,
    decision_identity_sha256,
    eligible_variant_items,
    review_signature_envelope_sha256,
    variant_content_sha256,
)

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "bake_variant_decisions.py"
_il_spec = importlib.util.spec_from_file_location("bake_variant_decisions", SCRIPT)
_mod = importlib.util.module_from_spec(_il_spec)
sys.modules["bake_variant_decisions"] = _mod
_il_spec.loader.exec_module(_mod)

_PACK_SHA = "b" * 64
_REVIEWER = "owner-delegated:claude-main-control:2026-07-17"
_SIGNED_AT = "2026-07-17T12:00:00+08:00"


def _variant(
    variant_id: str,
    *,
    surface: str,
    expected_ok: bool = True,
    extension: bool = False,
) -> dict[str, object]:
    return {
        "variant_id": variant_id,
        "rule_group": "B-send",
        "surface": surface,
        "params": {"order": ["总配电箱", "分配电箱", "开关箱"], "op": "send"},
        "expected_ok": expected_ok,
        "correct_statement": "送电顺序应为总配电箱→分配电箱→开关箱",
        "anchor": "kc:1A431011_015_0016:1",
        "extension": extension,
    }


def _candidate_decision(
    variant: dict[str, object],
    *,
    fact_id: str = "t01-fact-send-power-order",
    skeleton_id: str = "t01-vskel-b-send-ok",
    probe_role: str = "immediate_confirm",
) -> dict[str, object]:
    temptation = "送电与停电顺序容易记串。"
    loss_reason = "送电顺序应为总配电箱→分配电箱→开关箱。"
    decision: dict[str, object] = {
        "schema": VARIANT_DECISION_SCHEMA,
        "fact_id": fact_id,
        "skeleton_id": skeleton_id,
        "probe_role": probe_role,
        "temptation": temptation,
        "loss_reason": loss_reason,
        "source_anchor": "kc:1A431011_015_0016:1",
        "source_sha256": _PACK_SHA,
        "content_sha256": variant_content_sha256(
            variant, temptation=temptation, loss_reason=loss_reason
        ),
    }
    decision["decision_identity_sha256"] = decision_identity_sha256(decision)
    decision["review"] = {
        "status": "pending",
        "verdict": "pending",
        "reviewed_content_sha256": decision["content_sha256"],
        "reviewed_decision_sha256": decision["decision_identity_sha256"],
        "signatures": [],
        "checks": {
            "source_verified": False,
            "answer_verified": False,
            "diagnosis_verified": False,
            "longest_option_checked": False,
            "template_leakage_checked": False,
        },
    }
    decision["review"]["signature_envelope_sha256"] = (
        review_signature_envelope_sha256(decision)
    )
    return decision


def _write_fixture(tmp_path: Path) -> dict[str, Path]:
    """T01 三变体（confirm/d1_probe 双 role + 1 extension）全套 fixture。"""
    v_confirm = _variant("T01-B-send-000", surface="工地A送电顺序：总→分→开")
    v_probe = _variant("T01-B-send-001", surface="工地B送电顺序：总→分→开")
    v_ext = _variant(
        "T01-X-dist-002", surface="开关箱距配电箱 32m", extension=True
    )
    bank = {
        "schema_version": "luban-t01-variant-bank",
        "pack_id": "T01",
        "status": "signed",
        "source_pack_sha256": _PACK_SHA,
        "generation_ms": 0.1,
        "gate": {
            "total": 3,
            "passed": 3,
            "pass_rate": 1.0,
            "verdict_mismatches": [],
            "contested_leaks": [],
            "duplicate_surfaces": [],
        },
        "variants": [v_confirm, v_probe, v_ext],
        "signoff": {"who": "教研", "when": "2026-07-05T00:00:00+08:00", "basis": "x"},
    }
    items = [
        {
            "variant_id": v_confirm["variant_id"],
            "extension": False,
            "decision_candidate": _candidate_decision(
                v_confirm, probe_role="immediate_confirm"
            ),
        },
        {
            "variant_id": v_probe["variant_id"],
            "extension": False,
            "decision_candidate": _candidate_decision(
                v_probe, skeleton_id="t01-vskel-b-send-ok-b", probe_role="d1_probe"
            ),
        },
        {
            "variant_id": v_ext["variant_id"],
            "extension": True,
            "decision_candidate": _candidate_decision(
                v_ext, skeleton_id="t01-vskel-x-dist-ok", probe_role="d1_probe"
            ),
        },
    ]
    candidates = {
        "schema": "luban_variant_decision_candidates.v1",
        "machine_candidates_only": True,
        "pack_id": "T01",
        "bank_status": "signed",
        "generated_from_bank_sha256": _PACK_SHA,
        "candidate_count": len(items),
        "facts": [],
        "items": items,
    }
    spec = {
        "schema": "luban_variant_decision_bake_spec.v1",
        "pack_id": "T01",
        "reviewer_id": _REVIEWER,
        "signed_at": _SIGNED_AT,
        "note": "决策卡确认 + 异源对抗收敛，owner 授权转写。",
    }
    base_dir = tmp_path / "成品"
    packets_dir = base_dir / "_practice_review_packets"
    packets_dir.mkdir(parents=True)
    bank_path = base_dir / "_T01_variant_bank.v0.json"
    bank_path.write_text(
        json.dumps(bank, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    candidates_path = packets_dir / "t01.variant.decision.candidates.json"
    candidates_path.write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    spec_path = tmp_path / "t01.bake.spec.json"
    spec_path.write_text(
        json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return {
        "base_dir": base_dir,
        "packets_dir": packets_dir,
        "bank": bank_path,
        "candidates": candidates_path,
        "spec": spec_path,
    }


def _run(paths: dict[str, Path], *packs: str) -> int:
    return _mod.main(
        [
            *(packs or ("T01",)),
            "--spec",
            str(paths["spec"]),
            "--base-dir",
            str(paths["base_dir"]),
            "--packets-dir",
            str(paths["packets_dir"]),
        ]
    )


def test_bake_signs_decisions_idempotently_and_touches_nothing_else(tmp_path):
    """签发转写：decision 块签妥入 bank、幂等重跑逐字节稳定、其余字段零触碰。"""
    paths = _write_fixture(tmp_path)
    before = json.loads(paths["bank"].read_text(encoding="utf-8"))
    assert _run(paths) == 0
    first = paths["bank"].read_text(encoding="utf-8")
    bank = json.loads(first)

    # 其余字段零触碰（除 variants[*].decision 外逐键相等）
    stripped = copy.deepcopy(bank)
    for variant in stripped["variants"]:
        variant.pop("decision")
    assert stripped == before

    # 每条 decision：signed/approved + 双角色签名 + checks 全真 + 三链自洽
    for variant in bank["variants"]:
        decision = variant["decision"]
        review = decision["review"]
        assert decision["schema"] == VARIANT_DECISION_SCHEMA
        assert review["status"] == "signed"
        assert review["verdict"] == "approved"
        assert [s["role"] for s in review["signatures"]] == ["teaching", "scoring"]
        assert all(s["reviewer_id"] == _REVIEWER for s in review["signatures"])
        assert all(s["signed_at"] == _SIGNED_AT for s in review["signatures"])
        assert all(review["checks"].values())
        assert review["reviewed_content_sha256"] == decision["content_sha256"]
        assert (
            review["reviewed_decision_sha256"]
            == decision["decision_identity_sha256"]
            == decision_identity_sha256(decision)
        )
        assert review["signature_envelope_sha256"] == (
            review_signature_envelope_sha256(decision)
        )

    # runtime 资格链认账：核心双 role 进 eligible，extension 永不服务
    eligible = {
        item["variant_id"]
        for item in eligible_variant_items(bank, blocked=set())
    }
    assert eligible == {"T01-B-send-000", "T01-B-send-001"}

    # 幂等：同 spec 重跑逐字节稳定
    assert _run(paths) == 0
    assert paths["bank"].read_text(encoding="utf-8") == first


def test_bake_aborts_whole_pack_on_unknown_variant_id(tmp_path):
    paths = _write_fixture(tmp_path)
    candidates = json.loads(paths["candidates"].read_text(encoding="utf-8"))
    candidates["items"][1]["variant_id"] = "T01-GHOST-999"
    paths["candidates"].write_text(
        json.dumps(candidates, ensure_ascii=False), encoding="utf-8"
    )
    before = paths["bank"].read_text(encoding="utf-8")
    assert _run(paths) == 1
    assert paths["bank"].read_text(encoding="utf-8") == before  # 整包不落盘


def test_bake_aborts_whole_pack_on_content_identity_mismatch(tmp_path):
    """bank 变体内容在候选生成后被改——content_sha256 失配即整包 abort。"""
    paths = _write_fixture(tmp_path)
    bank = json.loads(paths["bank"].read_text(encoding="utf-8"))
    bank["variants"][0]["surface"] = "被篡改的题面"
    paths["bank"].write_text(
        json.dumps(bank, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    before = paths["bank"].read_text(encoding="utf-8")
    assert _run(paths) == 1
    assert paths["bank"].read_text(encoding="utf-8") == before


def test_bake_aborts_on_decision_identity_tamper(tmp_path):
    """候选治理字段签后改挂（fact 改名）——decision identity 失配即 abort。"""
    paths = _write_fixture(tmp_path)
    candidates = json.loads(paths["candidates"].read_text(encoding="utf-8"))
    candidates["items"][0]["decision_candidate"]["fact_id"] = "t01-fact-hijacked"
    paths["candidates"].write_text(
        json.dumps(candidates, ensure_ascii=False), encoding="utf-8"
    )
    before = paths["bank"].read_text(encoding="utf-8")
    assert _run(paths) == 1
    assert paths["bank"].read_text(encoding="utf-8") == before


def test_bake_aborts_on_bank_sha_drift(tmp_path):
    """pack 正文修订后 bank sha 变——候选文件过期即 abort（先重跑 prefill）。"""
    paths = _write_fixture(tmp_path)
    candidates = json.loads(paths["candidates"].read_text(encoding="utf-8"))
    candidates["generated_from_bank_sha256"] = "c" * 64
    paths["candidates"].write_text(
        json.dumps(candidates, ensure_ascii=False), encoding="utf-8"
    )
    assert _run(paths) == 1


def test_bake_aborts_on_illegal_probe_role(tmp_path):
    """anchor 首验归 compiled MCQ——变体候选占 anchor role 即 abort。"""
    paths = _write_fixture(tmp_path)
    candidates = json.loads(paths["candidates"].read_text(encoding="utf-8"))
    dc = candidates["items"][0]["decision_candidate"]
    dc["probe_role"] = "anchor"
    dc["decision_identity_sha256"] = decision_identity_sha256(dc)
    paths["candidates"].write_text(
        json.dumps(candidates, ensure_ascii=False), encoding="utf-8"
    )
    assert _run(paths) == 1


def test_bake_rejects_spec_without_reviewer_or_bad_schema(tmp_path):
    paths = _write_fixture(tmp_path)
    spec = json.loads(paths["spec"].read_text(encoding="utf-8"))
    spec["reviewer_id"] = ""
    paths["spec"].write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    assert _run(paths) == 1
    spec["reviewer_id"] = _REVIEWER
    spec["schema"] = "wrong.schema.v9"
    paths["spec"].write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    assert _run(paths) == 1


def test_bake_rejects_non_machine_candidates_file(tmp_path):
    """候选文件缺 machine_candidates_only 旗标——来路不明的输入拒绝转写。"""
    paths = _write_fixture(tmp_path)
    candidates = json.loads(paths["candidates"].read_text(encoding="utf-8"))
    candidates["machine_candidates_only"] = False
    paths["candidates"].write_text(
        json.dumps(candidates, ensure_ascii=False), encoding="utf-8"
    )
    assert _run(paths) == 1


def test_bake_rejects_spec_pack_mismatch(tmp_path):
    """spec 里声明的 pack 与 CLI pack 不一致——拒绝（spec 由主控逐包签发）。"""
    paths = _write_fixture(tmp_path)
    spec = json.loads(paths["spec"].read_text(encoding="utf-8"))
    spec["pack_id"] = "Z99"
    paths["spec"].write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    assert _run(paths) == 1
