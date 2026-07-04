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

用法::

    python3 docs/原始数据/考点原料/promote_variant_bank.py F16 \
        --basis "gate 100% + 随 pack 签发使用过（微信真机复测链路核验）" \
        --who 教研张三
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
_BANK_TEMPLATE = "_{pack_id}_variant_bank.v0.json"
_GATE_VIOLATION_KEYS = ("verdict_mismatches", "contested_leaks", "duplicate_surfaces")


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


def _run_builder_gate_check(pack_id: str, repo: Path) -> None:
    """gate 数字重跑：调对应 builder 的 --check（确定性重建 + 重跑门，零写入）。"""
    script = repo / "scripts" / f"build_luban_{pack_id.lower()}_variant_bank.py"
    if not script.exists():
        raise PromotionError(f"找不到 bank builder（无法重跑 gate）: {script}")
    proc = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        raise PromotionError(
            f"gate 重跑 FAIL（builder --check 退出 {proc.returncode}）:\n"
            f"{proc.stdout.strip()}\n{proc.stderr.strip()}"
        )


def _check_stored_gate(bank: dict[str, Any]) -> None:
    gate = bank.get("gate")
    if not isinstance(gate, dict):
        raise PromotionError("bank 缺 gate 字段，无法核验一致性门数字")
    total, passed = gate.get("total"), gate.get("passed")
    if not isinstance(total, int) or total <= 0 or passed != total:
        raise PromotionError(f"bank 登记的 gate 数字不干净: passed={passed}/total={total}")
    for key in _GATE_VIOLATION_KEYS:
        if gate.get(key):
            raise PromotionError(f"bank 登记的 gate 有未清违规 {key}: {gate[key]}")


def promote(
    pack_id: str,
    basis: str,
    who: str,
    *,
    pack_dir: Path = PACK_DIR,
    repo: Path = REPO,
    gate_check: Callable[[str, Path], None] = _run_builder_gate_check,
) -> Path:
    """校验全过则把 bank status 翻 signed 并写签发记录；任一不过抛 PromotionError。"""
    pack_id = str(pack_id or "").strip().upper()
    if not _PACK_ID_RE.match(pack_id):
        raise PromotionError(f"非法 pack_id（应形如 F16）: {pack_id!r}")
    basis = str(basis or "").strip()
    if not basis:
        raise PromotionError("签发依据 --basis 不能为空（签发必须留痕）")
    who = str(who or "").strip()
    if not who:
        raise PromotionError("签发人 --who 不能为空")

    bank_path = pack_dir / _BANK_TEMPLATE.format(pack_id=pack_id)
    bank = _load_json(bank_path, "变体 bank")
    if not isinstance(bank, dict):
        raise PromotionError(f"变体 bank 形状非法（应为对象）: {bank_path}")
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
        raise PromotionError(
            f"bank source_pack_sha256 与当前 pack 正文不一致（pack 已修订），"
            f"先重跑 scripts/build_luban_{pack_id.lower()}_variant_bank.py 重建 bank"
            f"（bank={bank.get('source_pack_sha256')} actual={actual_sha}）"
        )

    _check_stored_gate(bank)
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
    parser = argparse.ArgumentParser(description="变体池签发（candidate → signed，人闸）")
    parser.add_argument("pack_id", help="pack id，如 F16")
    parser.add_argument("--basis", required=True, help="签发依据（留痕，必填）")
    parser.add_argument("--who", default=getpass.getuser(), help="签发人（默认当前系统用户）")
    args = parser.parse_args()
    try:
        path = promote(args.pack_id, args.basis, args.who)
    except PromotionError as exc:
        print(f"promote-variant-bank: FAIL — {exc}", file=sys.stderr)
        return 1
    print(f"promote-variant-bank: SIGNED — {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
