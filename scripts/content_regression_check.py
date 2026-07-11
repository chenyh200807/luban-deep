#!/usr/bin/env python3
"""内容资产回归检查器（2026-07-11 宏观独立审计工单①落地）。

背景：三轮验尸(卡/解药/变体)+判分库异源终审证明——签发时全绿 ≠ 长期干净：
pack 修订、builder 升版、blocklist 演化、新池带病加入，此前**全靠有人记得跑
脚本**。本检查器把"内容不悄悄烂掉"变成机器职责，供 nightly 质量飞轮调度
（scheduled_run 之后跑）与手动执行。

四道检查（任一 FAIL 退出码 1）：
  1. 复现闸：每个 signed bank 跑对应 builder --check（确定性重建一致 + gate 复绿）；
  2. blocklist 一致性：三份停发清单的条目仍指向真实存在的资产（防清单腐烂），
     且变体停发在 serve 侧真的不下发（活体抽查）；
  3. 风格棘轮：audit_variant_style_tells 对比基线 `_style_tells_baseline.json`——
     新池 LEAK 或存量口诀命中率恶化 >2pp 即回归（存量带病在对偶返工前豁免，
     但不许变得更坏）；
  4. sha 对齐：signed bank source_pack_sha256 == manifest content_sha256。

注意：复现闸依赖教材权威库（docs/原始数据/2026_副本，仅本机、不入 git）——
缺库时 concept builder 会 fail-loud，这是设计（防两台机器产出漂移），
本检查器将其如实报告为环境缺陷而非内容回归。

用法::

    python3 scripts/content_regression_check.py           # 全量四道
    python3 scripts/content_regression_check.py --rebaseline-style  # 重立风格基线
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "docs" / "原始数据" / "考点原料"
PACK_DIR = RAW / "成品"
BASELINE_PATH = PACK_DIR / "_style_tells_baseline.json"

_BANK_BUILDERS = {
    "variant": ("_{pid}_variant_bank.v0.json", ["scripts/build_luban_{pid_lower}_variant_bank.py", "--check"]),
    "concept_cards": ("_{pid}_concept_card_bank.v0.json", ["scripts/build_luban_concept_card_bank.py", "{pid}", "--check"]),
    "antidote": ("_{pid}_r8_antidote_bank.v0.json", ["scripts/build_luban_r8_antidote_bank.py", "{pid}", "--check"]),
    "cloze": ("_{pid}_r6_cloze_bank.v0.json", ["scripts/build_luban_r6_cloze_bank.py", "{pid}", "--check"]),
    "seethrough": ("_{pid}_seethrough_bank.v0.json", ["scripts/build_luban_seethrough_bank.py", "{pid}", "--check"]),
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _signed_banks() -> list[tuple[str, str, Path]]:
    """[(kind, pack_id, path)] 全部 signed bank。"""
    out = []
    for kind, (template, _cmd) in _BANK_BUILDERS.items():
        pattern = template.format(pid="*")
        for path in sorted(PACK_DIR.glob(pattern)):
            try:
                bank = _load(path)
            except Exception:
                out.append((kind, "?", path))
                continue
            if bank.get("status") == "signed":
                out.append((kind, str(bank.get("pack_id") or ""), path))
    return out


def check_reproducibility(failures: list[str]) -> None:
    for kind, pid, path in _signed_banks():
        template, cmd = _BANK_BUILDERS[kind]
        parts = [p.format(pid=pid, pid_lower=pid.lower()) for p in cmd]
        script = REPO / parts[0]
        if not script.exists():
            failures.append(f"[复现] {kind}:{pid} builder 不存在: {parts[0]}")
            continue
        proc = subprocess.run(
            [sys.executable, str(script), *parts[1:]],
            capture_output=True, text=True, timeout=600, cwd=str(REPO),
        )
        if proc.returncode != 0:
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-2:]
            failures.append(f"[复现] {kind}:{pid} --check 退出 {proc.returncode}: {' / '.join(tail)}")


def check_blocklists(failures: list[str]) -> None:
    # 变体停发清单 → bank 里真有这些 variant_id
    bl_path = PACK_DIR / "_variant_blocklist.json"
    if bl_path.exists():
        entries = _load(bl_path).get("variants") or []
        by_pack: dict[str, set[str]] = {}
        for e in entries:
            by_pack.setdefault(str(e.get("pack_id") or ""), set()).add(str(e.get("variant_id") or ""))
        for pack, ids in by_pack.items():
            bank_path = PACK_DIR / f"_{pack}_variant_bank.v0.json"
            if not bank_path.exists():
                failures.append(f"[blocklist] 变体清单引用不存在的 bank: {pack}")
                continue
            have = {str(v.get("variant_id") or "") for v in _load(bank_path).get("variants") or []}
            for vid in ids - have:
                failures.append(f"[blocklist] 变体清单条目已不在 bank(该修的修完了就从清单移除): {vid}")
        # serve 侧活体抽查：停发变体绝不下发
        sys.path.insert(0, str(REPO))
        from deeptutor.services.luban_lesson.read_model import build_retest_items  # noqa: E402
        all_blocked = {str(e.get("variant_id") or "") for e in entries}
        for pack in sorted(by_pack):
            for uid in ("cr_u1", "cr_u2"):
                for day in (2026190, 2026195):
                    for mode in ("forward", "review"):
                        for item in build_retest_items(pack, user_id=uid, day_index=day, limit=10, mode=mode):
                            if item["variant_id"] in all_blocked:
                                failures.append(f"[blocklist] 停发变体被下发: {item['variant_id']}")
    # 解药/考点卡清单 → 条目留痕在 dropped_rows(panel_reject)
    for fname, key, bank_tpl, drop_field in (
        ("_antidote_blocklist.json", "antidotes", "_{p}_r8_antidote_bank.v0.json", "r8_id"),
        ("_concept_card_blocklist.json", "cards", "_{p}_concept_card_bank.v0.json", None),
    ):
        path = RAW / fname
        if not path.exists():
            continue
        for e in _load(path).get(key) or []:
            eid = str(e.get("r8_id") or e.get("card_id") or "")
            pack = eid.split(":")[0]
            bank_path = PACK_DIR / bank_tpl.format(p=pack)
            if not bank_path.exists():
                continue  # 站可下线, 不算腐烂
            bank = _load(bank_path)
            blob = json.dumps(bank, ensure_ascii=False)
            if eid in blob and '"panel_reject"' not in blob:
                failures.append(f"[blocklist] {fname} 条目 {eid} 在 bank 中未被剔除")


def check_style_ratchet(failures: list[str], rebaseline: bool) -> None:
    sys.path.insert(0, str(REPO / "scripts"))
    import audit_variant_style_tells as audit  # noqa: E402
    current: dict[str, dict] = {}
    for path in sorted(PACK_DIR.glob("_*_variant_bank.v0.json")):
        bank = _load(path)
        if bank.get("status") != "signed":
            continue
        rep = audit.audit_pack(str(bank.get("pack_id")), audit._core_variants(bank))
        current[rep["pack_id"]] = {
            "leak": bool(rep["violations"]),
            "combo_rule": rep["combo_rule"],
        }
    if rebaseline or not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(
            json.dumps({"_note": "风格泄露棘轮基线(存量带病豁免但不许恶化;对偶返工后 --rebaseline-style)",
                        "packs": current}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        print(f"风格基线已{'重' if rebaseline else ''}建: {len(current)} 池")
        return
    baseline = _load(BASELINE_PATH).get("packs") or {}
    for pack, now in current.items():
        base = baseline.get(pack)
        if base is None:
            if now["leak"]:
                failures.append(f"[风格棘轮] 新池 {pack} 带泄露入库(基线外禁 LEAK)")
            continue
        if now["leak"] and not base.get("leak"):
            failures.append(f"[风格棘轮] {pack} 从干净退化为 LEAK")
        if now["combo_rule"] > float(base.get("combo_rule") or 0) + 0.02:
            failures.append(
                f"[风格棘轮] {pack} 口诀命中率恶化 {base.get('combo_rule'):.0%}→{now['combo_rule']:.0%}")


def check_sha_alignment(failures: list[str]) -> None:
    manifest = _load(PACK_DIR / "_pack_manifest.json")
    sha_by_pack = {p.get("pack_id"): str(p.get("content_sha256") or "") for p in manifest.get("packs") or []}
    for kind, pid, path in _signed_banks():
        bank = _load(path)
        expect = sha_by_pack.get(pid)
        if expect and str(bank.get("source_pack_sha256") or "") != expect:
            failures.append(f"[sha] {kind}:{pid} bank sha 与 manifest 漂移(pack 修订后未重编重签)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebaseline-style", action="store_true")
    parser.add_argument("--skip-repro", action="store_true", help="跳过复现闸(快扫)")
    args = parser.parse_args()

    failures: list[str] = []
    check_sha_alignment(failures)
    check_blocklists(failures)
    check_style_ratchet(failures, rebaseline=args.rebaseline_style)
    if not args.skip_repro:
        check_reproducibility(failures)

    banks = _signed_banks()
    print(f"内容回归: {len(banks)} 个 signed bank / 4 道检查")
    if failures:
        print(f"FAIL {len(failures)} 项:")
        for f in failures:
            print("  ", f)
        return 1
    print("PASS 全绿")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
