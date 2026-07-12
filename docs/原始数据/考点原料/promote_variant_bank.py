#!/usr/bin/env python3
"""变体池签发工具（candidate → signed，人闸）。

背景：变体 bank 由 ``scripts/build_luban_{pack_id}_variant_bank.py`` 编译期生成，
恒写 ``status: "candidate"``（脚本绝不代签）。runtime 消费端
``deeptutor/services/luban_lesson/read_model.py`` 只认 ``status=="signed"`` 且
``source_pack_sha256`` 锚定当前 pack 正文的 bank——本工具是唯一的签发翻牌动作。

**人闸语义**：owner/教研运行本工具本身 = 签发决定。工具只做确定性校验后翻牌
并留痕（who/when/basis），绝不自动批量跑、绝不代替人的裁决。

校验（任一不过 exit 1，bank 不动）：
1. bank 存在、可解析、当前 status == "candidate"（已 signed 拒绝重签——
   pack 修订后须先重跑 builder 回到 candidate 再签）；
2. sha 三方一致：sha256(pack 正文) == manifest ``content_sha256`` == bank
   ``source_pack_sha256``（manifest 落后 → 先重跑 build_luban_pack_manifest.py；
   bank 落后 → 先重跑对应 bank builder）；
3. bank 内登记的 gate 数字干净（passed==total>0 且三违规清单全空）；
4. gate 数字重跑：``scripts/build_luban_{pid}_variant_bank.py --check`` 退出 0
   （确定性重建变体 + 重跑一致性门，不写文件）。

本工具同时是**考点卡池 / R8 解药池 / R6 挖空池**的签发人闸（``--kind
concept_cards|antidote|cloze``，复用优先——不另造第二个 promote authority）：
bank 分别由 ``scripts/build_luban_concept_card_bank.py`` /
``scripts/build_luban_r8_antidote_bank.py`` / ``scripts/build_luban_r6_cloze_bank.py``
编译期生成，同样恒写 candidate，runtime 消费端（``concept_cards.py`` /
``antidotes.py`` / ``cloze.py``）同样 signed+sha 双 fail-closed。各类 bank 的差异
只有文件模板 / builder 命令 / gate 违规键名（``_BANK_KINDS`` 一张表收敛），
校验语义逐条同构。

用法::

    python3 docs/原始数据/考点原料/promote_variant_bank.py F16 \
        --basis "gate 100% + 随 pack 签发使用过（微信真机复测链路核验）" \
        --who 教研张三
    python3 docs/原始数据/考点原料/promote_variant_bank.py S05 --kind concept_cards \
        --basis "gate 100% + owner 逐卡过目" --who 教研张三
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import getpass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable

TOOL_DIR = Path(__file__).resolve().parent
PACK_DIR = TOOL_DIR / "成品"
REPO = TOOL_DIR.parents[2]

_PACK_ID_RE = re.compile(r"^[A-Z]\d{2}$")

# 两类 bank 的形态差异收敛在这一张表里（校验流程完全同构，禁分叉第二工具）：
# - template: 成品目录里的 bank 文件名模板
# - builder:  gate 重跑命令模板（相对 repo 根；{pid}/{pid_lower} 由 pack_id 派生）
# - violation_keys: bank.gate 里必须全空的违规清单键
_BANK_KINDS: dict[str, dict[str, Any]] = {
    "variant": {
        "template": "_{pack_id}_variant_bank.v0.json",
        "builder": ("scripts/build_luban_{pid_lower}_variant_bank.py", "--check"),
        "violation_keys": ("verdict_mismatches", "contested_leaks", "duplicate_surfaces"),
        "label": "变体 bank",
    },
    "concept_cards": {
        "template": "_{pack_id}_concept_card_bank.v0.json",
        "builder": ("scripts/build_luban_concept_card_bank.py", "{pid}", "--check"),
        "violation_keys": ("quote_mismatches", "duplicate_cards", "forbidden_words"),
        "label": "考点卡 bank",
    },
    "antidote": {
        "template": "_{pack_id}_r8_antidote_bank.v0.json",
        "builder": ("scripts/build_luban_r8_antidote_bank.py", "{pid}", "--check"),
        "violation_keys": ("code_unregistered", "anchor_unresolved", "forbidden_words"),
        "label": "R8 解药 bank",
    },
    "cloze": {
        "template": "_{pack_id}_r6_cloze_bank.v0.json",
        "builder": ("scripts/build_luban_r6_cloze_bank.py", "{pid}", "--check"),
        "violation_keys": ("term_not_in_sentence", "anchor_unresolved", "forbidden_words"),
        "label": "R6 挖空 bank",
    },
    "seethrough": {
        "template": "_{pack_id}_seethrough_bank.v0.json",
        "builder": ("scripts/build_luban_seethrough_bank.py", "{pid}", "--check"),
        "violation_keys": ("code_unregistered", "anchor_unresolved", "extension_unannotated", "forbidden_words"),
        "label": "看穿 bank",
    },
}


# ── 标准考点卡车道(2026-07-12 owner授权放量): 无 pack manifest 的编译资产梯队 ──
# 同构语义不减: ①builder 复现一致 ②source_v32_sha256 锚定编译资产
# ③禁词/复核违规扫描 ④签发翻牌唯一在本工具。
_STD_BANK = "_STD_concept_card_bank.v0.json"
_STD_BUILDER = ("scripts/build_luban_standard_concept_cards.py",)


def promote_std(basis: str, who: str) -> Path:
    path = PACK_DIR / _STD_BANK
    bank = _load_json(path, "标准考点卡 bank")
    if str(bank.get("tier") or "") != "standard":
        raise PromotionError("非标准梯队 bank, 走常规 kind")
    if str(bank.get("status") or "") == "signed":
        raise PromotionError("已是 signed, 不重复翻牌")
    # ① v32 编译资产 sha 锚(本机有资产才可签——签发只在编译机做)
    v32 = REPO / "artifacts" / "luban_grading_artifacts" / (
        "rich_leaf_v32_scoring_point_compile_20260613"
    ) / "runtime_token_pack_v32_scoring_points.json"
    if not v32.exists():
        raise PromotionError("v32 编译资产缺席, 无法复核锚, 拒签")
    if _sha256(v32) != str(bank.get("source_v32_sha256") or ""):
        raise PromotionError("bank 的 source_v32_sha256 与 v32 资产不一致, 先重编")
    # ② builder 复现一致(--check 只算不写, 比对确定性视图)
    top_n = int(bank.get("card_count") or 0)
    proc = subprocess.run(
        [sys.executable, str(REPO / _STD_BUILDER[0]), "--top", str(top_n), "--check"],
        capture_output=True, text=True, timeout=600, cwd=str(REPO),
    )
    if proc.returncode != 0:
        raise PromotionError(f"builder --check 失败: {proc.stderr[-300:]}")
    import importlib.util as _ilu

    spec = _ilu.spec_from_file_location("_stdb", REPO / _STD_BUILDER[0])
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rebuilt = mod.build_payload(top_n)
    def _view(p: dict) -> dict:
        return {k: v for k, v in p.items() if k not in ("generation_ms", "status", "signoff")}
    if _view(rebuilt) != _view(bank):
        raise PromotionError("重编产物与 bank 不一致(非确定性或源漂移), 拒签")
    # ③ 违规扫描: 禁词 + 教材复核必须零跳过(全量 verified)
    if int(bank.get("quote_recheck_skipped") or 0) != 0:
        raise PromotionError("存在未过教材逐字复核的卡, 拒签")
    forbidden = ("看穿", "识破", "揭穿", "露馅")
    for card in bank.get("cards") or []:
        text = f"{card.get('front','')}|{card.get('quote','')}"
        if any(w in text for w in forbidden):
            raise PromotionError(f"禁词违规: {card.get('card_id')}")
    # ④ 翻牌 + 留痕
    bank["status"] = "signed"
    bank["signoff"] = {
        "who": who,
        "basis": basis,
        "at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "tool": "promote_variant_bank.py(std lane)",
    }
    path.write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


class PromotionError(Exception):
    """校验不过：签发中止，bank 文件不动。"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path, what: str) -> Any:
    if not path.exists():
        raise PromotionError(f"{what} 不存在: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PromotionError(f"{what} 解析失败: {path} ({exc})")


def _run_builder_gate_check(pack_id: str, repo: Path, kind: str = "variant") -> None:
    """gate 数字重跑：调对应 builder 的 --check（确定性重建 + 重跑门，零写入）。"""
    parts = [
        p.format(pid=pack_id, pid_lower=pack_id.lower())
        for p in _BANK_KINDS[kind]["builder"]
    ]
    script = repo / parts[0]
    if not script.exists():
        raise PromotionError(f"找不到 bank builder（无法重跑 gate）: {script}")
    proc = subprocess.run(
        [sys.executable, str(script), *parts[1:]],
        capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        raise PromotionError(
            f"gate 重跑 FAIL（builder --check 退出 {proc.returncode}）:\n"
            f"{proc.stdout.strip()}\n{proc.stderr.strip()}"
        )


def _check_stored_gate(bank: dict[str, Any], kind: str = "variant") -> None:
    gate = bank.get("gate")
    if not isinstance(gate, dict):
        raise PromotionError("bank 缺 gate 字段，无法核验一致性门数字")
    total, passed = gate.get("total"), gate.get("passed")
    if not isinstance(total, int) or total <= 0 or passed != total:
        raise PromotionError(f"bank 登记的 gate 数字不干净: passed={passed}/total={total}")
    for key in _BANK_KINDS[kind]["violation_keys"]:
        if gate.get(key):
            raise PromotionError(f"bank 登记的 gate 有未清违规 {key}: {gate[key]}")


def promote(
    pack_id: str,
    basis: str,
    who: str,
    *,
    pack_dir: Path = PACK_DIR,
    repo: Path = REPO,
    gate_check: Callable[[str, Path], None] | None = None,
    kind: str = "variant",
) -> Path:
    """校验全过则把 bank status 翻 signed 并写签发记录；任一不过抛 PromotionError。"""
    if kind not in _BANK_KINDS:
        raise PromotionError(f"未知 bank kind: {kind!r}（可选 {sorted(_BANK_KINDS)}）")
    label = _BANK_KINDS[kind]["label"]
    if gate_check is None:
        def gate_check(pid: str, r: Path) -> None:  # noqa: ANN001 — 同签名默认闸
            _run_builder_gate_check(pid, r, kind)
    pack_id = str(pack_id or "").strip().upper()
    if not _PACK_ID_RE.match(pack_id):
        raise PromotionError(f"非法 pack_id（应形如 F16）: {pack_id!r}")
    basis = str(basis or "").strip()
    if not basis:
        raise PromotionError("签发依据 --basis 不能为空（签发必须留痕）")
    who = str(who or "").strip()
    if not who:
        raise PromotionError("签发人 --who 不能为空")

    bank_path = pack_dir / _BANK_KINDS[kind]["template"].format(pack_id=pack_id)
    bank = _load_json(bank_path, label)
    if not isinstance(bank, dict):
        raise PromotionError(f"{label} 形状非法（应为对象）: {bank_path}")
    status = str(bank.get("status") or "")
    if status == "signed":
        raise PromotionError(
            f"{pack_id} bank 已是 signed，拒绝重签；pack 修订后请先重跑 builder 回到 candidate"
        )
    if status != "candidate":
        raise PromotionError(f"{pack_id} bank status 非 candidate（{status!r}），不可签发")

    # sha 三方一致：pack 正文 == manifest == bank
    manifest = _load_json(pack_dir / "_pack_manifest.json", "pack manifest")
    entry = next(
        (p for p in manifest.get("packs") or [] if p.get("pack_id") == pack_id), None
    )
    if entry is None:
        raise PromotionError(f"manifest 中无 pack {pack_id}")
    pack_file = pack_dir / str(entry.get("file") or "")
    if not entry.get("file") or not pack_file.exists():
        raise PromotionError(f"pack 正文文件缺失: {pack_file}")
    actual_sha = _sha256(pack_file)
    if actual_sha != str(entry.get("content_sha256") or ""):
        raise PromotionError(
            f"manifest content_sha256 落后于 pack 正文，先重跑 "
            f"scripts/build_luban_pack_manifest.py（manifest={entry.get('content_sha256')} "
            f"actual={actual_sha}）"
        )
    if str(bank.get("source_pack_sha256") or "") != actual_sha:
        rebuild = _BANK_KINDS[kind]["builder"][0].format(
            pid=pack_id, pid_lower=pack_id.lower()
        )
        raise PromotionError(
            f"bank source_pack_sha256 与当前 pack 正文不一致（pack 已修订），"
            f"先重跑 {rebuild} 重建 bank"
            f"（bank={bank.get('source_pack_sha256')} actual={actual_sha}）"
        )

    _check_stored_gate(bank, kind)
    gate_check(pack_id, repo)  # gate 数字重跑（builder --check）

    bank["status"] = "signed"
    bank["signoff"] = {
        "who": who,
        # §9-D2 同款服务端 UTC+8 口径
        "when": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "basis": basis,
    }
    bank_path.write_text(
        json.dumps(bank, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return bank_path


def main() -> int:
    parser = argparse.ArgumentParser(description="供给池签发（candidate → signed，人闸）")
    parser.add_argument("pack_id", help="pack id，如 F16")
    parser.add_argument("--basis", required=True, help="签发依据（留痕，必填）")
    parser.add_argument("--who", default=getpass.getuser(), help="签发人（默认当前系统用户）")
    parser.add_argument(
        "--kind", default="variant", choices=sorted(_BANK_KINDS) + ["std_concept_cards"],
        help="bank 类型：variant=变体池（默认）/ concept_cards=考点卡池 / "
             "antidote=R8 解药池 / cloze=R6 挖空池 / std_concept_cards=标准考点卡(packless)",
    )
    args = parser.parse_args()
    try:
        if args.kind == "std_concept_cards":
            path = promote_std(args.basis, args.who)
        else:
            path = promote(args.pack_id, args.basis, args.who, kind=args.kind)
    except PromotionError as exc:
        print(f"promote-variant-bank: FAIL — {exc}", file=sys.stderr)
        return 1
    print(f"promote-variant-bank: SIGNED — {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
