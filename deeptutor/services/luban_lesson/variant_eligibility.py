"""签发变体银行的 practice 资格投影——同一杆枪的第二种弹药。

设计：docs/plan/鲁班移动端提分闭环/2026-07-16-variant-eligibility-design.md。

- **同一资格门语义**：逐条资格由 ``practice_html._eligible``（含
  ``_review_is_signed`` 双签结构 + 五 checks）同一谓词裁决，不新建平行 authority；
  本模块只做「bank 原位 decision 块 → 治理形状 item」的投影与校验。
- **同一签发闸**：bank 读取复用 ``read_model._load_signed_bank``（signed + sha
  双 fail-closed）与 ``read_model._variant_blocklist``（撤发唯一 authority）；
  ``revoked`` 在投影时从 blocklist 派生，绝不落盘第二份撤发状态。
- **内容 identity**：``content_sha256`` 覆盖变体内容载荷 **加 temptation /
  loss_reason 富化文案**——签后改文案即 ``reviewed_content_sha256`` 失配，
  fail-closed（与 compiled MCQ 的 options 内含富化被 content_sha256 覆盖同构）。
- **决策 identity**：``decision_identity_sha256``（不可递归，覆盖
  ``content_sha256 + fact_id + skeleton_id + probe_role + source_anchor +
  source_sha256``）把治理字段一并绑进人签——review 以
  ``reviewed_decision_sha256`` 绑定该摘要，且 ``source_sha256`` 必须等于
  bank 的 ``source_pack_sha256``；签后改任一治理字段即 identity 断裂，
  fail-closed（对抗审查 B1）。
- **fail-closed**：decision 块缺失/形状错/sha 失配/probe_role 非法/blocklist
  不可读/bank 未签发——一律不 eligible，绝不半开。

本模块零写入：不写 bank、不写学习证据、不接 endpoint（消费接线是后续切片）。
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from deeptutor.services.luban_lesson.practice_html import (
    _canonical_sha256,
    _eligible,
)
from deeptutor.services.luban_lesson.read_model import (
    _MANIFEST_PATH,
    _load_manifest,
    _load_signed_bank,
    _variant_blocklist,
)

VARIANT_DECISION_SCHEMA = "luban_variant_decision.v1"
VARIANT_REVIEW_PACKET_SCHEMA = "luban_variant_review_packet.v1"

# 变体只占确认/延时探针两种 role；anchor（D+1 首验）永远归 compiled MCQ。
VARIANT_PROBE_ROLES = ("immediate_confirm", "d1_probe")

_REVIEW_CHECKS = (
    "source_verified",
    "answer_verified",
    "diagnosis_verified",
    "longest_option_checked",
    "template_leakage_checked",
)

# checks 名字与 compiled MCQ 完全同一（同一谓词）；变体语境的语义映射随审核包下发。
_CHECK_INSTRUCTIONS = {
    "source_verified": "anchor 指向的教材原文/真题确实支撑 correct_statement",
    "answer_verified": "expected_ok 判定方向与教材口径一致（对抗面板口径）",
    "diagnosis_verified": "temptation/loss_reason 文案经教研核验（暖语气，禁审视词）",
    "longest_option_checked": "长度/风格 tell 检查（audit_variant_style_tells 口径）",
    "template_leakage_checked": "句式/答案模式不泄露判定方向",
}

_SHA256_RE = re.compile(r"[0-9a-f]{64}")

_VARIANT_CONTENT_FIELDS = (
    "variant_id",
    "rule_group",
    "surface",
    "params",
    "expected_ok",
    "correct_statement",
    "anchor",
    "extension",
)

_DECISION_STR_FIELDS = (
    "fact_id",
    "skeleton_id",
    "probe_role",
    "temptation",
    "loss_reason",
    "source_anchor",
    "source_sha256",
    "content_sha256",
    "decision_identity_sha256",
)

# 决策 identity 覆盖的治理字段（不含 identity 自身与 review——不可递归）。
_DECISION_IDENTITY_FIELDS = (
    "content_sha256",
    "fact_id",
    "skeleton_id",
    "probe_role",
    "source_anchor",
    "source_sha256",
)


def variant_content_sha256(
    variant: dict[str, Any], *, temptation: str, loss_reason: str
) -> str:
    """变体内容 identity：核心字段 + 富化文案；签名必须覆盖学员可见的一切。"""
    payload = {key: variant.get(key) for key in _VARIANT_CONTENT_FIELDS}
    payload["temptation"] = temptation
    payload["loss_reason"] = loss_reason
    return _canonical_sha256(payload)


def decision_identity_sha256(decision: dict[str, Any]) -> str:
    """决策治理 identity：content_sha256 + fact/skeleton/probe_role/source 锚。

    review 以 ``reviewed_decision_sha256`` 绑定此摘要——签后改任一治理字段
    （把已审事实重挂到另一个 fact/role/source）即摘要失配，fail-closed。
    """
    payload = {key: str(decision.get(key) or "") for key in _DECISION_IDENTITY_FIELDS}
    return _canonical_sha256(payload)


def _pending_review(content_sha256: str, identity_sha256: str) -> dict[str, Any]:
    return {
        "status": "pending",
        "verdict": "pending",
        "reviewed_content_sha256": content_sha256,
        "reviewed_decision_sha256": identity_sha256,
        "signatures": [],
        "checks": {name: False for name in _REVIEW_CHECKS},
    }


def _decision_shape_ok(decision: Any) -> bool:
    if not isinstance(decision, dict):
        return False
    if decision.get("schema") != VARIANT_DECISION_SCHEMA:
        return False
    if not all(isinstance(decision.get(k), str) for k in _DECISION_STR_FIELDS):
        return False
    return isinstance(decision.get("review"), dict)


def _decision_identity_error(
    variant: dict[str, Any],
    decision: dict[str, Any],
    *,
    source_pack_sha256: str,
) -> str | None:
    """完整 identity 校验；返回失配原因（``None`` = identity 完好）。

    校验链（对抗审查 B1）：内容摘要 → source 必须等于 bank 的
    ``source_pack_sha256`` → 决策治理摘要 → review 绑定决策摘要。
    """
    expected_content = variant_content_sha256(
        variant,
        temptation=str(decision.get("temptation") or ""),
        loss_reason=str(decision.get("loss_reason") or ""),
    )
    if decision.get("content_sha256") != expected_content:
        return "content_sha256 与当前变体内容/富化文案失配"
    if decision.get("source_sha256") != source_pack_sha256:
        return "source_sha256 与 bank.source_pack_sha256 失配"
    if decision.get("decision_identity_sha256") != decision_identity_sha256(decision):
        return "decision_identity_sha256 与治理字段失配（签后治理字段被改）"
    review = decision.get("review")
    if not isinstance(review, dict) or review.get(
        "reviewed_decision_sha256"
    ) != decision.get("decision_identity_sha256"):
        return "review 未绑定当前 decision_identity_sha256"
    return None


def variant_governance_item(
    variant: dict[str, Any], *, blocked: set[str], source_pack_sha256: str
) -> dict[str, Any] | None:
    """bank 原位 decision 块 → practice 资格门的治理形状 item。

    fail-closed：decision 缺失/形状错/content 或决策 identity 与当前变体
    失配/source_sha256 不等于 bank 的 source_pack_sha256 →
    ``None``（与未签同形）。``revoked`` 从 blocklist **派生**（单一撤发 authority）。
    """
    decision = variant.get("decision")
    if not _decision_shape_ok(decision):
        return None
    assert isinstance(decision, dict)  # narrowed by _decision_shape_ok
    if (
        _decision_identity_error(
            variant, decision, source_pack_sha256=source_pack_sha256
        )
        is not None
    ):
        return None  # 签后内容/文案/治理字段被改，identity 断裂
    if decision["probe_role"] not in VARIANT_PROBE_ROLES:
        return None  # anchor 首验归 compiled MCQ，变体不得占位
    variant_id = str(variant.get("variant_id") or "").strip()
    if not variant_id:
        return None
    item: dict[str, Any] = {
        "variant_id": variant_id,
        "rule_group": str(variant.get("rule_group") or ""),
        "surface": str(variant.get("surface") or ""),
        "expected_ok": bool(variant.get("expected_ok")),
        "correct_statement": str(variant.get("correct_statement") or ""),
        "anchor": str(variant.get("anchor") or ""),
        "extension": bool(variant.get("extension")),
        "temptation": str(decision["temptation"]),
        "loss_reason": str(decision["loss_reason"]),
        "fact_id": str(decision["fact_id"]),
        "skeleton_id": str(decision["skeleton_id"]),
        "probe_role": str(decision["probe_role"]),
        "source_anchor": str(decision["source_anchor"]),
        "source_sha256": str(decision["source_sha256"]),
        "content_sha256": str(decision["content_sha256"]),
        "decision_identity_sha256": str(decision["decision_identity_sha256"]),
        "review": decision["review"],
        "revoked": variant_id in blocked,
        "revocation_refs": [],
    }
    return item


def _bank_signed(bank: dict[str, Any]) -> bool:
    return (
        isinstance(bank, dict)
        and str(bank.get("status") or "") == "signed"
        and bool(_SHA256_RE.fullmatch(str(bank.get("source_pack_sha256") or "")))
    )


def eligible_variant_items(
    bank: dict[str, Any], *, blocked: set[str] | None
) -> list[dict[str, Any]]:
    """当前可服务的变体 item（治理形状）；``blocked=None`` = 撤发 authority
    不可读，整体 fail-closed 返回空。extension 变体永不服务（既有裁决）。"""
    if blocked is None or not _bank_signed(bank):
        return []
    source_pack_sha256 = str(bank.get("source_pack_sha256") or "")
    items: list[dict[str, Any]] = []
    for variant in bank.get("variants") or []:
        if not isinstance(variant, dict) or variant.get("extension"):
            continue
        item = variant_governance_item(
            variant, blocked=blocked, source_pack_sha256=source_pack_sha256
        )
        if item is not None and _eligible(item):
            items.append(item)
    return items


def variant_eligibility_summary(
    bank: dict[str, Any], *, blocked: set[str] | None
) -> dict[str, Any]:
    """按 fact 的就绪度 summary：fact ready = 双 role 非空 + ≥2 个骨架。"""
    items = eligible_variant_items(bank, blocked=blocked)
    facts: dict[str, dict[str, Any]] = {}
    for item in items:
        entry = facts.setdefault(
            str(item["fact_id"]),
            {role: 0 for role in VARIANT_PROBE_ROLES} | {"skeleton_ids": set()},
        )
        entry[str(item["probe_role"])] += 1
        entry["skeleton_ids"].add(str(item["skeleton_id"]))
    for entry in facts.values():
        entry["skeletons"] = len(entry.pop("skeleton_ids"))
        entry["ready"] = bool(
            all(entry[role] >= 1 for role in VARIANT_PROBE_ROLES)
            and entry["skeletons"] >= 2
        )
    ready_fact_ids = sorted(
        fact_id for fact_id, entry in facts.items() if entry["ready"]
    )
    return {
        "eligible_count": len(items),
        "fact_count": len(facts),
        "facts": facts,
        "ready_fact_ids": ready_fact_ids,
        "supply_ready": bool(ready_fact_ids),
    }


def build_variant_review_packet(
    bank: dict[str, Any], *, blocked: set[str] | None
) -> dict[str, Any]:
    """人审工作包（决策卡输入）：逐条 pending，机器绝不代签；已 bake 的
    decision 透出前先过完整 identity 校验（对抗审查 B3）——identity 失配的
    条目只能标 ``stale/invalid`` 并给原因，绝不保留 signed 外观，防止人审
    真值与 runtime 真值分叉。extension 变体如实入包并标记（不服务）。"""
    rows: list[dict[str, Any]] = []
    eligible_ids = {
        item["variant_id"] for item in eligible_variant_items(bank, blocked=blocked)
    }
    source_pack_sha256 = str(bank.get("source_pack_sha256") or "")
    for variant in bank.get("variants") or []:
        if not isinstance(variant, dict):
            continue
        decision = variant.get("decision")
        if not _decision_shape_ok(decision):
            content_sha = variant_content_sha256(
                variant, temptation="", loss_reason=""
            )
            decision = {
                "schema": VARIANT_DECISION_SCHEMA,
                "fact_id": "",
                "skeleton_id": "",
                "probe_role": "",
                "temptation": "",
                "loss_reason": "",
                "source_anchor": str(variant.get("anchor") or ""),
                "source_sha256": source_pack_sha256,
                "content_sha256": content_sha,
            }
            decision["decision_identity_sha256"] = decision_identity_sha256(decision)
            decision["review"] = _pending_review(
                content_sha, decision["decision_identity_sha256"]
            )
        else:
            assert isinstance(decision, dict)  # narrowed by _decision_shape_ok
            identity_error = _decision_identity_error(
                variant, decision, source_pack_sha256=source_pack_sha256
            )
            if identity_error is not None:
                # 题面/文案/治理字段签后漂移：人审面绝不显示旧 signed 外观。
                review = dict(decision.get("review") or {})
                review["status"] = "stale"
                review["verdict"] = "invalid"
                review["stale_reason"] = identity_error
                decision = dict(decision, review=review)
        rows.append(
            {
                "variant_id": variant.get("variant_id"),
                "rule_group": variant.get("rule_group"),
                "surface": variant.get("surface"),
                "expected_ok": variant.get("expected_ok"),
                "correct_statement": variant.get("correct_statement"),
                "anchor": variant.get("anchor"),
                "extension": bool(variant.get("extension")),
                "decision": decision,
            }
        )
    return {
        "schema": VARIANT_REVIEW_PACKET_SCHEMA,
        "pack_id": bank.get("pack_id"),
        "bank_schema_version": bank.get("schema_version"),
        "bank_status": bank.get("status"),
        "source_pack_sha256": bank.get("source_pack_sha256"),
        "candidate_count": len(rows),
        "eligible_count": len(eligible_ids),
        "human_gate": {
            "required_roles": ["teaching", "scoring"],
            "machine_must_not_sign": True,
        },
        "instructions": {
            "fact_namespace": "与 compiled MCQ 同一命名空间 {pack小写}-fact-{语义slug}；"
            "同 fact 的 MCQ 与变体必须写同一字符串（先签者为命名先例）",
            "probe_roles": list(VARIANT_PROBE_ROLES),
            "checks": dict(_CHECK_INSTRUCTIONS),
        },
        "items": rows,
    }


def resolve_variant_supply(
    pack_id: str, *, manifest_path: Path | None = None
) -> dict[str, Any] | None:
    """经同一签发闸（``_load_signed_bank`` signed+sha 双 fail-closed +
    ``_variant_blocklist``）解析一个 pack 的变体资格供给；任一闸不过 → None。

    canonical 发布门（对抗审查 B2）：pack 必须在 manifest 的
    ``projection_green`` 内——被撤回/未发布的 pack 即使 bank 仍 signed 且
    sha 匹配，也不得越过绿灯供给变体。"""
    normalized = str(pack_id or "").strip().upper()
    if not normalized:
        return None
    path = manifest_path or _MANIFEST_PATH
    manifest = _load_manifest(path)
    green = {
        str(green_id or "").strip().upper()
        for green_id in manifest.get("projection_green") or []
    }
    if normalized not in green:
        return None  # 非绿灯 pack 不供给（与 pack 缺失同形，不泄漏存在性）
    expected_sha = ""
    for pack in manifest.get("packs") or []:
        if str(pack.get("pack_id") or "").strip().upper() == normalized:
            expected_sha = str(pack.get("content_sha256") or "")
            break
    if not expected_sha:
        return None
    manifest_dir = path.parent
    bank = _load_signed_bank(normalized, manifest_dir, expected_sha)
    blocked = _variant_blocklist(manifest_dir)
    if bank is None or blocked is None:
        return None
    return {
        "pack_id": normalized,
        "source_pack_sha256": str(bank.get("source_pack_sha256") or ""),
        "items": eligible_variant_items(bank, blocked=blocked),
        "summary": variant_eligibility_summary(bank, blocked=blocked),
    }


__all__ = [
    "VARIANT_DECISION_SCHEMA",
    "VARIANT_PROBE_ROLES",
    "VARIANT_REVIEW_PACKET_SCHEMA",
    "build_variant_review_packet",
    "decision_identity_sha256",
    "eligible_variant_items",
    "resolve_variant_supply",
    "variant_content_sha256",
    "variant_eligibility_summary",
    "variant_governance_item",
]
