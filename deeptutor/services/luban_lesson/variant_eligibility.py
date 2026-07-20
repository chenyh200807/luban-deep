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
- **签名信封**：``review.signature_envelope_sha256`` 覆盖 decision identity
  + review 全量（signatures 的 reviewer_id/signed_at/顺序/条数/附加键、
  note、checks、status/verdict、reviewed_*）——「替换签署人/改签署时间/
  加伪签名/改批注」任一签后篡改即信封摘要失配，fail-closed
  （对抗审查二轮 B1：approval authority 与 payload authority 同绑）。
- **fail-closed**：decision 块缺失/形状错/sha 失配/probe_role 非法/blocklist
  不可读/bank 未签发——一律不 eligible，绝不半开。

本模块零写入：不写 bank、不写学习证据、不接 endpoint（消费接线是后续切片）。
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
from typing import Any

# 经模块属性调用 compiled 侧函数（而非 from-import 绑定符号），使测试夹具
# （conftest.pendingize_pack）patch ``practice_html`` 命名空间即可同时覆盖本模块。
from deeptutor.services.luban_lesson import practice_html as _practice_html
from deeptutor.services.luban_lesson.practice_html import (
    _canonical_sha256,
    _eligible,
)
from deeptutor.services.luban_lesson.read_model import (
    _MANIFEST_PATH,
    _load_green_signed_bank,
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


def review_signature_envelope_sha256(decision: dict[str, Any]) -> str:
    """签名信封 identity：decision identity + review 全量（除信封字段自身）。

    覆盖 signatures 的每一条（reviewer_id / signed_at / 顺序 / 条数 / 附加
    键）、note、checks、status/verdict、reviewed_* ——签后增删改任何审批
    痕迹即信封摘要失配，fail-closed。不可递归：信封字段自身不入摘要。
    """
    review = decision.get("review")
    review = review if isinstance(review, dict) else {}
    payload = {
        "decision_identity_sha256": str(
            decision.get("decision_identity_sha256") or ""
        ),
        "review": {
            key: value
            for key, value in review.items()
            if key != "signature_envelope_sha256"
        },
    }
    return _canonical_sha256(payload)


def _pending_review(
    decision: dict[str, Any], extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """从 decision（不含 review）派生 pending review，含双绑定 + 签名信封。

    ``extra``（如 stale 标记）先并入再算信封——附加痕迹同样被信封覆盖。
    """
    review: dict[str, Any] = {
        "status": "pending",
        "verdict": "pending",
        "reviewed_content_sha256": str(decision.get("content_sha256") or ""),
        "reviewed_decision_sha256": str(
            decision.get("decision_identity_sha256") or ""
        ),
        "signatures": [],
        "checks": {name: False for name in _REVIEW_CHECKS},
    }
    if extra:
        review.update(extra)
    review["signature_envelope_sha256"] = review_signature_envelope_sha256(
        dict(decision, review=review)
    )
    return review


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
    ``source_pack_sha256`` → 决策治理摘要 → review 绑定决策摘要 →
    签名信封摘要（审批痕迹本身不可签后篡改）。
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
    if review.get(
        "signature_envelope_sha256"
    ) != review_signature_envelope_sha256(decision):
        return "signature envelope 摘要失配（签名/批注/checks 等审批痕迹签后被改）"
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


def _packet_signed_appearance_failure(
    variant: dict[str, Any],
    decision: dict[str, Any],
    *,
    blocked: set[str] | None,
    source_pack_sha256: str,
) -> tuple[str, str] | None:
    """已 bake decision 的人审外观裁决（对抗审查二轮 B3）。

    review 自称 signed/approved 但 runtime 资格链会拒绝 →
    返回 ``(改标状态, 原因)``；``None`` = 外观如实，可原样透出。
    复用与 runtime **同一套**判定（identity 链 + probe_role + blocklist +
    ``_eligible`` 完整签发谓词），不做第二套近似。
    """
    review = decision.get("review")
    review = review if isinstance(review, dict) else {}
    claims_signed = (
        review.get("status") == "signed" or review.get("verdict") == "approved"
    )
    if not claims_signed:
        return None  # pending/stale 等非 signed 外观本身即如实
    error = _decision_identity_error(
        variant, decision, source_pack_sha256=source_pack_sha256
    )
    if error is not None:
        return ("stale", error)
    if decision.get("probe_role") not in VARIANT_PROBE_ROLES:
        return ("stale", "probe_role 非变体合法 role（anchor 首验归 compiled MCQ）")
    if blocked is None:
        return ("stale", "撤发 authority（variant blocklist）不可读，无法证明未撤发")
    variant_id = str(variant.get("variant_id") or "").strip()
    if variant_id in blocked:
        return ("revoked", "已撤发（variant blocklist）")
    item = variant_governance_item(
        variant, blocked=blocked, source_pack_sha256=source_pack_sha256
    )
    if item is None or not _eligible(item):
        return (
            "stale",
            "review 未满足完整签发谓词（签名角色/checks/reviewed hash 之一失配）",
        )
    return None


def build_variant_review_packet(
    bank: dict[str, Any], *, blocked: set[str] | None
) -> dict[str, Any]:
    """人审工作包（决策卡输入）：逐条 pending，机器绝不代签；已 bake 的
    decision 透出前复用**完整 runtime 资格判定**（对抗审查 B3 二轮）——
    任何 runtime 不 eligible 却自称 signed/approved 的条目，一律改标
    ``stale/invalid``（撤发场景标 ``revoked``）并给原因，绝不保留 signed
    外观，防止人审真值与 runtime 真值分叉。extension 变体如实入包并标记
    （不服务；其 decision 真值按同一 identity/谓词链核验）。"""
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
            decision["review"] = _pending_review(decision)
        else:
            assert isinstance(decision, dict)  # narrowed by _decision_shape_ok
            failure = _packet_signed_appearance_failure(
                variant,
                decision,
                blocked=blocked,
                source_pack_sha256=source_pack_sha256,
            )
            if failure is not None:
                status, reason = failure
                # runtime 不 eligible：人审面绝不显示旧 signed/approved 外观。
                review = dict(decision.get("review") or {})
                review["status"] = status
                review["verdict"] = "invalid" if status == "stale" else "revoked"
                review["stale_reason"] = reason
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


def _stale_pending_decision(
    variant: dict[str, Any],
    old_decision: dict[str, Any],
    *,
    source_pack_sha256: str,
    reasons: list[str],
) -> dict[str, Any]:
    """内容/source 漂移后的 decision 重置：治理提案与富化文案降级为候选，
    identity 对新内容重算自洽，review 置回 pending 并带 stale 标记——
    绝不静默保留旧签名（旧 identity 摘要留痕供追溯）。"""
    temptation = str(old_decision.get("temptation") or "")
    loss_reason = str(old_decision.get("loss_reason") or "")
    decision: dict[str, Any] = {
        "schema": VARIANT_DECISION_SCHEMA,
        "fact_id": str(old_decision.get("fact_id") or ""),
        "skeleton_id": str(old_decision.get("skeleton_id") or ""),
        "probe_role": str(old_decision.get("probe_role") or ""),
        "temptation": temptation,
        "loss_reason": loss_reason,
        "source_anchor": str(old_decision.get("source_anchor") or ""),
        "source_sha256": source_pack_sha256,
        "content_sha256": variant_content_sha256(
            variant, temptation=temptation, loss_reason=loss_reason
        ),
    }
    decision["decision_identity_sha256"] = decision_identity_sha256(decision)
    decision["review"] = _pending_review(
        decision,
        extra={
            "stale": True,
            "stale_reason": "；".join(reasons),
            "stale_from_decision_identity_sha256": str(
                old_decision.get("decision_identity_sha256") or ""
            ),
        },
    )
    return decision


def carry_variant_bank_decisions(
    previous_bank_path: Path | str, payload: dict[str, Any]
) -> dict[str, int]:
    """bank builder 重建时的 decision 保留合并（镜像 practice publisher
    ``_load_practice_review_records`` 的 build-time 人审保留模式）。

    在 ``payload``（重建产物，含 ``source_pack_sha256`` 与 ``variants``）上
    原位补回旧 bank 的 per-item decision 块：

    - **保留**：``variant_id`` 比中且旧 decision 的 ``content_sha256`` 与
      重建变体内容 + 旧富化文案重算一致、``source_sha256`` 仍等于新
      ``source_pack_sha256`` → 逐字节深拷贝保留（签名零折损）；
    - **置 stale**：内容或 pack 正文漂移 → 置回 pending + stale 标记
      （治理提案/富化文案降级为候选，identity 重算，绝不静默保留旧签名）；
    - **丢弃**：旧 decision 形状不可信 → 整块不携带。

    纯合并零写入：落盘仍由调用方（builder）完成。旧 bank 缺失/不可解析 =
    首次构建，如实返回零统计。
    """
    stats = {"preserved": 0, "stale": 0, "dropped": 0}
    try:
        previous = json.loads(
            Path(previous_bank_path).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return stats
    if not isinstance(previous, dict):
        return stats
    old_by_id: dict[str, dict[str, Any]] = {}
    for old in previous.get("variants") or []:
        if isinstance(old, dict) and "decision" in old:
            variant_id = str(old.get("variant_id") or "").strip()
            if variant_id:
                old_by_id[variant_id] = old
    source_pack_sha256 = str(payload.get("source_pack_sha256") or "")
    for variant in payload.get("variants") or []:
        if not isinstance(variant, dict):
            continue
        old = old_by_id.get(str(variant.get("variant_id") or "").strip())
        if old is None:
            continue
        old_decision = old.get("decision")
        if not _decision_shape_ok(old_decision):
            stats["dropped"] += 1
            continue
        assert isinstance(old_decision, dict)  # narrowed by _decision_shape_ok
        reasons: list[str] = []
        expected_content = variant_content_sha256(
            variant,
            temptation=str(old_decision.get("temptation") or ""),
            loss_reason=str(old_decision.get("loss_reason") or ""),
        )
        if old_decision.get("content_sha256") != expected_content:
            reasons.append("变体内容/富化文案与已审 content_sha256 漂移")
        if old_decision.get("source_sha256") != source_pack_sha256:
            reasons.append("pack 正文修订（source_pack_sha256 变更）")
        if reasons:
            variant["decision"] = _stale_pending_decision(
                variant,
                old_decision,
                source_pack_sha256=source_pack_sha256,
                reasons=reasons,
            )
            stats["stale"] += 1
        else:
            variant["decision"] = copy.deepcopy(old_decision)
            stats["preserved"] += 1
    return stats


def _resolve_compiled_probe_supply(pack_id: str) -> dict[str, Any] | None:
    """compiled v3 per-Pack artifact 的 confirm/d1 供给分支。

    资格谓词完全复用 ``practice_html``（``load_compiled_practice`` 的
    digest/registration/公开投影 sha 全链校验 + ``_eligible`` + fact 三件套
    ``compiled_practice_eligibility_summary``），零平行判定。供给 facts 收窄到
    ``complete_fact_ids``（anchor/immediate_confirm/d1_probe 三 role 齐且骨架
    互异）——三件套不齐的 fact 不发探针，防撤发后半开。

    fail-closed：工件缺失/校验失败/``supply_ready`` 假/complete fact 空 → None
    （与 legacy bank 缺失同形，不泄漏存在性）。
    """
    try:
        practice = _practice_html.load_compiled_practice(pack_id)
    except _practice_html.PracticeHtmlInvalid:
        return None
    if practice is None:
        return None
    summary = _practice_html.compiled_practice_eligibility_summary(practice)
    complete = set(summary.get("complete_fact_ids") or [])
    if not summary.get("supply_ready") or not complete:
        return None
    items = [
        dict(item)
        for item in practice.get("items") or []
        if _eligible(item)
        and str(item.get("probe_role") or "") in VARIANT_PROBE_ROLES
        and str(item.get("fact_id") or "") in complete
    ]
    if not items:
        return None
    return {
        "pack_id": pack_id,
        "source_pack_sha256": str(practice.get("source_pack_sha256") or ""),
        "items": items,
        "summary": summary,
    }


def resolve_variant_supply(
    pack_id: str, *, manifest_path: Path | None = None
) -> dict[str, Any] | None:
    """一个 pack 的变体探针资格供给唯一 gateway。

    - compiled 注册 pack（``is_compiled_practice_pack``，仅默认 manifest 生效，
      镜像 ``read_model.build_retest_items`` 复测先例）：v3 per-Pack artifact 是
      唯一资格 authority，**禁回退 signed bank**——工件任一闸不过 → None，
      绝不半开。
    - 仅无 compiled authority 的 legacy pack 走原 signed bank 路径：canonical
      绿灯签发闸 ``_load_green_signed_bank``（projection_green + manifest sha +
      signed 三重 fail-closed，对抗审查二轮 B2 唯一 gateway）+
      ``_variant_blocklist``；任一闸不过 → None（与缺失同形，不泄漏存在性）。"""
    normalized = str(pack_id or "").strip().upper()
    if not normalized:
        return None
    if manifest_path is None and _practice_html.is_compiled_practice_pack(normalized):
        return _resolve_compiled_probe_supply(normalized)
    path = manifest_path or _MANIFEST_PATH
    bank = _load_green_signed_bank(normalized, manifest_path=path)
    blocked = _variant_blocklist(path.parent)
    if bank is None or blocked is None:
        return None
    return {
        "pack_id": normalized,
        "source_pack_sha256": str(bank.get("source_pack_sha256") or ""),
        "items": eligible_variant_items(bank, blocked=blocked),
        "summary": variant_eligibility_summary(bank, blocked=blocked),
    }


# ---------------------------------------------------------------- 消费投影（切片一）
# 三个纯函数（零写入）：把 resolve_variant_supply 的绿灯供给投影成消费题面 +
# 供给 identity + 精确解析。变体供给唯一权威仍是 resolve_variant_supply（内含
# _load_green_signed_bank 绿灯签发闸）——这三个函数不读 bank 文件、不建第二真值。

# 消费题面只透出学员可见 + 判分所需字段（判断题：expected_ok 是判分锚，
# temptation/loss_reason 是错后诊断文案）；治理 identity/review 不进消费面。
_PROBE_ITEM_FIELDS = (
    "variant_id",
    "rule_group",
    "surface",
    "correct_statement",
    "anchor",
    "fact_id",
    "skeleton_id",
    "probe_role",
    "temptation",
    "loss_reason",
)


def _project_probe_item(item: dict[str, Any]) -> dict[str, Any]:
    if str(item.get("answer_type") or "") == "single_choice":
        # compiled MCQ 探针复用 ``_project_practice_rows`` 同一消费映射（单选
        # 绝不下发 is_correct/temptation/loss_reason 答案面；错后诊断经
        # writeback answer_feedback 回传），只额外携带 probe_role 供消费路由。
        row = _practice_html._project_practice_rows([item])[0]
        row["probe_role"] = str(item.get("probe_role") or "")
        return row
    row = {key: str(item.get(key) or "") for key in _PROBE_ITEM_FIELDS}
    row["expected_ok"] = bool(item.get("expected_ok"))
    return row


def _probe_seed(user_id: str, day_index: int, key: str) -> int:
    """确定性选序散列（复用 read_model build_retest_items 的高熵 seed 模式）——
    同 (user, day, key) 多端幂等，绝不派生任何题面字段。"""
    digest = hashlib.sha256(
        f"{user_id}:{int(day_index)}:{key}".encode("utf-8")
    ).hexdigest()
    return int(digest[:12], 16)


def variant_probe_supply_identity(
    pack_id: str, *, manifest_path: Path | None = None
) -> dict[str, str]:
    """变体探针供给的签发 identity（消费路由的持久真值输入）。

    经 ``resolve_variant_supply`` 的绿灯签发闸取当前 eligible 供给；identity 覆盖
    {pack_id, source_pack_sha256, items}——治理字段/撤发/重签任一漂移即 digest 变，
    selection token 随之失配（阻断过期变体池提交）。供给缺失/空 → ``{"",""}``
    （与 ``retest_supply_identity`` 空态同形），消费点据此 fail-closed 退现行为。
    """
    supply = resolve_variant_supply(pack_id, manifest_path=manifest_path)
    items = list(supply.get("items") or []) if supply else []
    if not supply or not items:
        return {"kind": "", "digest": ""}
    digest = _canonical_sha256(
        {
            "pack_id": str(supply.get("pack_id") or ""),
            "source_pack_sha256": str(supply.get("source_pack_sha256") or ""),
            "items": items,
        }
    )
    return {"kind": "signed_variant", "digest": digest}


def variant_probe_fact_ids(
    pack_id: str, *, probe_role: str, manifest_path: Path | None = None
) -> frozenset[str]:
    """Return facts with currently eligible supply for one registered role."""
    if probe_role not in VARIANT_PROBE_ROLES:
        return frozenset()
    supply = resolve_variant_supply(pack_id, manifest_path=manifest_path)
    if not supply:
        return frozenset()
    return frozenset(
        str(item.get("fact_id") or "").strip()
        for item in list(supply.get("items") or [])
        if str(item.get("probe_role") or "").strip() == probe_role
        and str(item.get("fact_id") or "").strip()
    )


def build_variant_probe_items(
    pack_id: str,
    *,
    user_id: str,
    day_index: int,
    probe_role: str,
    fact_ids: list[str] | None = None,
    limit: int = 5,
    per_fact: int = 2,
    manifest_path: Path | None = None,
) -> list[dict[str, Any]]:
    """从绿灯变体供给投影一组消费题面（compiled pack = MCQ；legacy bank = 判断题）。

    - 供给唯一权威 = ``resolve_variant_supply``（绿灯签发闸）；缺失/空 → ``[]``。
    - 只取指定 ``probe_role``（immediate_confirm / d1_probe）；``fact_ids`` 给定时
      再取 fact 交集（错题当场确认场用 completion 派生的错题 facts）。
    - 确定性选序：fact 序与 fact 内选序均由 ``sha256(user:day:key)`` 派生（多端
      幂等）；每 fact 至多 ``per_fact`` 题，总量 ≤ ``limit``。零生成、零新供给。

    fail-closed：``probe_role`` 非法（如 anchor）→ 空（anchor 首验归 compiled MCQ）。
    """
    if probe_role not in VARIANT_PROBE_ROLES:
        return []
    supply = resolve_variant_supply(pack_id, manifest_path=manifest_path)
    if not supply:
        return []
    wanted_facts = (
        {str(fact or "").strip() for fact in fact_ids if str(fact or "").strip()}
        if fact_ids is not None
        else None
    )
    per_fact = max(1, int(per_fact))
    limit = max(1, min(int(limit), 10))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in supply.get("items") or []:
        if str(item.get("probe_role") or "") != probe_role:
            continue
        fact = str(item.get("fact_id") or "").strip()
        if wanted_facts is not None and fact not in wanted_facts:
            continue
        grouped.setdefault(fact, []).append(item)
    ordered_facts = sorted(
        grouped, key=lambda fact: _probe_seed(user_id, day_index, fact)
    )
    picked: list[dict[str, Any]] = []
    for fact in ordered_facts:
        members = sorted(
            grouped[fact],
            key=lambda item: _probe_seed(
                user_id, day_index, f"{fact}:{item.get('variant_id')}"
            ),
        )
        picked.extend(members[:per_fact])
    return [_project_probe_item(item) for item in picked[:limit]]


def resolve_variant_probe_items(
    pack_id: str, variant_ids: list[str], *, manifest_path: Path | None = None
) -> list[dict[str, Any]] | None:
    """completion 精确解析：按 ``variant_ids`` 取当前仍 eligible 的变体消费行。

    completion 绝不重跑选题算法——只按 id 精确解析。任一 id 缺失/不再 eligible
    （撤发、签后漂移、供给闸不过）→ ``None``（fail-closed，writeback 拒收）。

    compiled MCQ 探针返回 authority 原行拷贝（writeback 判分需要
    options.is_correct，镜像 ``resolve_compiled_practice_items`` canonical 口径）；
    judgment 变体保持消费投影（expected_ok 即判分锚）。
    """
    wanted = [str(item or "").strip() for item in variant_ids]
    if not wanted or len(wanted) > 10 or len(set(wanted)) != len(wanted):
        return None
    supply = resolve_variant_supply(pack_id, manifest_path=manifest_path)
    if not supply:
        return None
    by_id = {
        str(item.get("variant_id") or "").strip(): item
        for item in supply.get("items") or []
    }
    selected = [by_id.get(variant_id) for variant_id in wanted]
    if any(item is None for item in selected):
        return None
    return [
        dict(item)
        if str(item.get("answer_type") or "") == "single_choice"
        else _project_probe_item(item)
        for item in selected
        if item is not None
    ]


__all__ = [
    "VARIANT_DECISION_SCHEMA",
    "VARIANT_PROBE_ROLES",
    "VARIANT_REVIEW_PACKET_SCHEMA",
    "build_variant_probe_items",
    "build_variant_review_packet",
    "carry_variant_bank_decisions",
    "decision_identity_sha256",
    "eligible_variant_items",
    "resolve_variant_probe_items",
    "variant_probe_fact_ids",
    "resolve_variant_supply",
    "review_signature_envelope_sha256",
    "variant_content_sha256",
    "variant_eligibility_summary",
    "variant_governance_item",
    "variant_probe_supply_identity",
]
