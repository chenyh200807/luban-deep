#!/usr/bin/env python3
"""Bake variant decisions into the bank（决策卡确认 → 签发转写，owner-delegated）.

设计：docs/plan/鲁班移动端提分闭环/2026-07-16-variant-eligibility-design.md §4。
签发流程先例 = MCQ 侧 transcribe（spec → decision 块 → publish 合并）；本工具是
变体侧的同款转写步：把 ``prefill_variant_decision_candidates.py`` 产出、经决策卡
人签 + 异源对抗收敛后的候选文件，按 owner-delegated 签发 spec 原位写进对应
``_<PACK>_variant_bank.v0.json`` 的条目 ``decision`` 块。

authority 纪律（机器绝不自铸真值）：

- **签名内容全部来自 spec**（reviewer_id / signed_at / note 由主控注入；
  运行本工具 = 执行一次已被人批准的转写，工具自身不产生任何签发决定）；
- **identity 三链逐条重算比中**：候选 ``content_sha256`` 必须等于 bank 当前
  变体内容 + 候选富化文案的重算值、``source_sha256`` 必须等于 bank
  ``source_pack_sha256``、``decision_identity_sha256`` 必须等于治理字段重算值——
  任一条目失配 **整包 abort、bank 不落盘**（候选生成后 bank/pack 漂移 =
  先重跑 prefill 再议）；
- **写后必过 runtime 同一资格谓词**：核心条目必须被
  ``eligible_variant_items`` 认账（extension 条目 identity 链核验但永不服务）；
- **幂等**：同 spec 重跑逐字节稳定；bank 其余字段零触碰
  （decision 签发状态与 bank ``status=signed`` 语义正交，不翻 bank 状态）。

Usage::

    python scripts/bake_variant_decisions.py S05 \\
        --spec docs/plan/鲁班移动端提分闭环/specs/s05.variant.bake.spec.json

spec 形状（``luban_variant_decision_bake_spec.v1``，MCQ transcribe 同款
owner-delegated 形态）::

    {
      "schema": "luban_variant_decision_bake_spec.v1",
      "pack_id": "S05",                       // 可选；给出则必须与 CLI pack 一致
      "reviewer_id": "owner-delegated:claude-main-control:2026-07-17",
      "signed_at": "2026-07-17T12:00:00+08:00",
      "note": "决策卡确认 + 异源对抗收敛，owner 授权转写。"
    }
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from deeptutor.services.luban_lesson.variant_eligibility import (  # noqa: E402
    _REVIEW_CHECKS,
    VARIANT_DECISION_SCHEMA,
    VARIANT_PROBE_ROLES,
    decision_identity_sha256,
    eligible_variant_items,
    review_signature_envelope_sha256,
    variant_content_sha256,
    variant_governance_item,
)

CANDIDATES_SCHEMA = "luban_variant_decision_candidates.v1"
SPEC_SCHEMA = "luban_variant_decision_bake_spec.v1"
DEFAULT_BASE_DIR = REPO_ROOT / "docs" / "原始数据" / "考点原料" / "成品"

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SIGNED_AT_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
_SIGNATURE_ROLES = ("teaching", "scoring")

# bake 逐字转写的候选治理/富化字段（identity 校验通过后原样入 bank）。
_DECISION_CARRY_FIELDS = (
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


class BakeError(Exception):
    """校验不过：整包 abort，bank 文件不动。"""


def _load_json(path: Path, what: str) -> Any:
    if not path.is_file():
        raise BakeError(f"{what} 不存在: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BakeError(f"{what} 解析失败: {path} ({exc})") from exc


def _validate_spec(spec: Any, *, pack_ids: list[str]) -> dict[str, Any]:
    if not isinstance(spec, dict) or spec.get("schema") != SPEC_SCHEMA:
        raise BakeError(f"spec schema 必须是 {SPEC_SCHEMA}")
    reviewer_id = str(spec.get("reviewer_id") or "").strip()
    if not reviewer_id:
        raise BakeError("spec.reviewer_id 不能为空（签发必须留痕）")
    signed_at = str(spec.get("signed_at") or "").strip()
    if not _SIGNED_AT_RE.match(signed_at):
        raise BakeError(f"spec.signed_at 非 ISO 时间: {signed_at!r}")
    note = spec.get("note")
    if note is not None and not isinstance(note, str):
        raise BakeError("spec.note 必须是字符串")
    declared = spec.get("pack_id")
    if declared is not None:
        declared_ids = [declared] if isinstance(declared, str) else list(declared)
        normalized = {str(p or "").strip().upper() for p in declared_ids}
        if normalized != {p.upper() for p in pack_ids}:
            raise BakeError(
                f"spec 声明的 pack {sorted(normalized)} 与 CLI pack "
                f"{sorted(p.upper() for p in pack_ids)} 不一致"
            )
    return {"reviewer_id": reviewer_id, "signed_at": signed_at, "note": note}


def _signed_review(decision: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """从 spec 派生双角色签发 review；信封摘要最后计算（覆盖全部审批痕迹）。"""
    review: dict[str, Any] = {
        "status": "signed",
        "verdict": "approved",
        "reviewed_content_sha256": str(decision["content_sha256"]),
        "reviewed_decision_sha256": str(decision["decision_identity_sha256"]),
        "signatures": [
            {
                "role": role,
                "reviewer_id": spec["reviewer_id"],
                "signed_at": spec["signed_at"],
            }
            for role in _SIGNATURE_ROLES
        ],
        "checks": {name: True for name in _REVIEW_CHECKS},
    }
    if spec.get("note"):
        review["note"] = spec["note"]
    review["signature_envelope_sha256"] = review_signature_envelope_sha256(
        dict(decision, review=review)
    )
    return review


def _candidate_errors(
    item: Any,
    *,
    bank_by_id: dict[str, dict[str, Any]],
    bank_sha: str,
) -> tuple[str | None, list[str]]:
    """单条候选的 identity 校验；返回 (variant_id, 失配原因列表)。"""
    if not isinstance(item, dict):
        return None, ["候选条目形状非法（应为对象）"]
    variant_id = str(item.get("variant_id") or "").strip()
    if not variant_id:
        return None, ["候选条目缺 variant_id"]
    errors: list[str] = []
    variant = bank_by_id.get(variant_id)
    if variant is None:
        return variant_id, [f"{variant_id}: bank 中无此变体"]
    decision = item.get("decision_candidate")
    if not isinstance(decision, dict):
        return variant_id, [f"{variant_id}: 缺 decision_candidate 块"]
    if decision.get("schema") != VARIANT_DECISION_SCHEMA:
        errors.append(f"{variant_id}: decision schema 非 {VARIANT_DECISION_SCHEMA}")
    for field in ("fact_id", "skeleton_id", "temptation", "loss_reason",
                  "source_anchor"):
        if not str(decision.get(field) or "").strip():
            errors.append(f"{variant_id}: decision.{field} 为空，不可签发")
    if decision.get("probe_role") not in VARIANT_PROBE_ROLES:
        errors.append(
            f"{variant_id}: probe_role {decision.get('probe_role')!r} 非法"
            "（anchor 首验归 compiled MCQ）"
        )
    expected_content = variant_content_sha256(
        variant,
        temptation=str(decision.get("temptation") or ""),
        loss_reason=str(decision.get("loss_reason") or ""),
    )
    if decision.get("content_sha256") != expected_content:
        errors.append(
            f"{variant_id}: content_sha256 与 bank 当前变体内容/富化文案失配"
        )
    if decision.get("source_sha256") != bank_sha:
        errors.append(f"{variant_id}: source_sha256 与 bank.source_pack_sha256 失配")
    if decision.get("decision_identity_sha256") != decision_identity_sha256(decision):
        errors.append(
            f"{variant_id}: decision_identity_sha256 与治理字段失配（签后被改）"
        )
    return variant_id, errors


def bake_pack(
    pack_id: str,
    spec: dict[str, Any],
    *,
    base_dir: Path,
    packets_dir: Path,
) -> tuple[Path, bool, int]:
    """单 pack 转写；返回 (bank_path, 是否有字节变化, 转写条数)。"""
    pack_id = str(pack_id or "").strip().upper()
    candidates_path = (
        packets_dir / f"{pack_id.lower()}.variant.decision.candidates.json"
    )
    candidates = _load_json(candidates_path, f"{pack_id} 候选文件")
    if not isinstance(candidates, dict) or candidates.get("schema") != CANDIDATES_SCHEMA:
        raise BakeError(f"{pack_id}: 候选文件 schema 非 {CANDIDATES_SCHEMA}")
    if candidates.get("machine_candidates_only") is not True:
        raise BakeError(
            f"{pack_id}: 候选文件缺 machine_candidates_only=true 旗标，拒绝转写"
        )
    if str(candidates.get("pack_id") or "").upper() != pack_id:
        raise BakeError(f"{pack_id}: 候选文件 pack_id 不一致")
    items = candidates.get("items")
    if not isinstance(items, list) or not items:
        raise BakeError(f"{pack_id}: 候选文件无条目，无可转写")

    bank_path = base_dir / f"_{pack_id}_variant_bank.v0.json"
    bank_text = bank_path.read_text(encoding="utf-8") if bank_path.is_file() else None
    bank = _load_json(bank_path, f"{pack_id} 变体 bank")
    if not isinstance(bank, dict) or str(bank.get("pack_id") or "") != pack_id:
        raise BakeError(f"{pack_id}: bank pack_id 不一致")
    bank_sha = str(bank.get("source_pack_sha256") or "")
    if not _SHA256_RE.fullmatch(bank_sha):
        raise BakeError(f"{pack_id}: bank.source_pack_sha256 非法")
    if str(candidates.get("generated_from_bank_sha256") or "") != bank_sha:
        raise BakeError(
            f"{pack_id}: 候选文件 generated_from_bank_sha256 与 bank 失配"
            "（pack/bank 已修订，先重跑 prefill_variant_decision_candidates.py）"
        )
    bank_by_id: dict[str, dict[str, Any]] = {}
    for variant in bank.get("variants") or []:
        if isinstance(variant, dict) and str(variant.get("variant_id") or ""):
            bank_by_id[str(variant["variant_id"])] = variant

    # 逐条 identity 校验——收齐全部失配后整包 abort（不写盘）。
    errors: list[str] = []
    seen: set[str] = set()
    verified: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in items:
        variant_id, item_errors = _candidate_errors(
            item, bank_by_id=bank_by_id, bank_sha=bank_sha
        )
        if variant_id is not None and variant_id in seen:
            item_errors.append(f"{variant_id}: 候选条目重复")
        if variant_id is not None:
            seen.add(variant_id)
        if item_errors:
            errors.extend(item_errors)
            continue
        verified.append((bank_by_id[str(variant_id)], item["decision_candidate"]))
    if errors:
        raise BakeError(
            f"{pack_id}: {len(errors)} 条 identity 失配，整包 abort：\n  "
            + "\n  ".join(errors)
        )

    # 转写：候选治理/富化字段逐字入 bank，review 从 spec 派生签发。
    for variant, candidate in verified:
        decision: dict[str, Any] = {"schema": VARIANT_DECISION_SCHEMA}
        for field in _DECISION_CARRY_FIELDS:
            decision[field] = str(candidate[field])
        decision["review"] = _signed_review(decision, spec)
        variant["decision"] = decision

    # 写前核验：runtime 同一资格谓词必须认账（防「签了但不 eligible」半开态）。
    probe_bank = dict(bank, status="signed")
    eligible_ids = {
        item["variant_id"]
        for item in eligible_variant_items(probe_bank, blocked=set())
    }
    for variant, _ in verified:
        variant_id = str(variant["variant_id"])
        if variant.get("extension"):
            item = variant_governance_item(
                variant, blocked=set(), source_pack_sha256=bank_sha
            )
            if item is None:
                raise BakeError(
                    f"{pack_id}: extension 条目 {variant_id} 转写后 identity 链断裂"
                )
        elif variant_id not in eligible_ids:
            raise BakeError(
                f"{pack_id}: 条目 {variant_id} 转写后未过 runtime 资格谓词"
            )

    new_text = json.dumps(bank, ensure_ascii=False, indent=1) + "\n"
    changed = new_text != bank_text
    if changed:
        bank_path.write_text(new_text, encoding="utf-8")
    return bank_path, changed, len(verified)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("packs", nargs="+", help="pack ids，如 S05 N01")
    parser.add_argument(
        "--spec", type=Path, required=True,
        help="签发 spec（luban_variant_decision_bake_spec.v1，主控注入）",
    )
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR)
    parser.add_argument(
        "--packets-dir", type=Path, default=None,
        help="候选文件目录（默认 <base-dir>/_practice_review_packets）",
    )
    args = parser.parse_args(argv)
    packets_dir = args.packets_dir or (args.base_dir / "_practice_review_packets")
    try:
        spec = _validate_spec(
            _load_json(args.spec, "签发 spec"), pack_ids=list(args.packs)
        )
        for pack in args.packs:
            bank_path, changed, baked = bake_pack(
                pack, spec, base_dir=args.base_dir, packets_dir=packets_dir
            )
            state = "WRITTEN" if changed else "UNCHANGED (idempotent rerun)"
            print(f"bake: {pack.strip().upper()} -> {bank_path} "
                  f"(decisions={baked}) {state}")
    except BakeError as exc:
        print(f"bake-variant-decisions: FAIL — {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
