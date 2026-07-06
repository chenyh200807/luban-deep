#!/usr/bin/env python3
"""考点卡 bank 编译器（确定性派生，禁 LLM 现编——双轮 v3.2 §6.2 / §8）。

派生层裁决（2026-07-05，调研 S05/A01/F16/J01/N01 五包后定）：
- **§1 跨章知识点全景表 = 唯一派生层**。一行 = 一个原子知识点，自带人审短名
  （卡正面问法的确定性底料）、关键数值/做法（可背关键词颗粒=助记）、三色标注
  与 kc: point_id 锚——正好是 30 秒再认卡的形态。
- R5 采分点不做卡源：R5 是答案态语句、按采分簇组织，已归 §6.3 实务闯关的
  答案键（再认卡复用它会把两种复习单元的面撕混）；且 R5 的 🟢 标注在 A01
  等包挂在簇标题层，行级机械解析不稳。
- R2 不变量不做卡源：每包一段、cardinality=1，是闯关的判别逻辑不是再认颗粒。

**fail-closed 铁律**（每条都无豁免）：
1. 只收三色 🟢 行（🟡/🔴 直接掉，🟢+🔵 混标行按 🟢 分支收，quote 门兜底）；
2. 教材原文 = compiled_source 对应 point 的 quote **逐字**——锚解析不到
   quote 的行不成卡（真题-only 锚、`…` 省略锚、m35 锚都在此掉）；
3. 同 point_id 重复行只留首行（后续行留痕 dropped_rows，不算违规）；
4. 恒写 status="candidate"——签发（candidate→signed）唯一入口 =
   docs/原始数据/考点原料/promote_variant_bank.py --kind concept_cards（人闸）。

gate（结构 + quote 逐字命中 + 去重 + 禁审视词）必须 100% 才写文件；
--check 模式零写入：重新派生 + 重跑 gate，且若磁盘已有 bank，
逐卡比对（确定性重建一致性——builder 升版/pack 改动都会在此现形）。

用法::

    python3 scripts/build_luban_concept_card_bank.py S05          # 生成/更新 bank
    python3 scripts/build_luban_concept_card_bank.py S05 --check  # 零写入核验
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
RAW_DIR = REPO / "docs" / "原始数据" / "考点原料"
PACK_DIR = RAW_DIR / "成品"

SCHEMA_NAME = "luban-concept-card-bank"  # dash 命名空间=脚本编译产物, 非 runtime schema(同变体池惯例)
BANK_TEMPLATE = "_{pack_id}_concept_card_bank.v0.json"

_PACK_ID_RE = re.compile(r"^[A-Z]\d{2}$")
_KC_ANCHOR_RE = re.compile(r"kc:[0-9A-Za-z_]+:\d+")
# 文案铁律(评审要点摘要): 禁审视揭短词——只查模板侧字段, 教材 quote 是逐字权威不动
FORBIDDEN_WORDS = ("看穿", "识破", "揭穿", "露馅")
# 去掉知识点名尾部括注(全/半角)——A01 的括注常把答案写在正面, 会泄卡背
_TRAILING_PAREN_RE = re.compile(r"[（(][^（）()]*[）)]\s*$")
_MD_DECOR_RE = re.compile(r"[*`]")


class BankBuildError(Exception):
    """派生/gate 失败：bank 不写。"""


def _load_json(path: Path, what: str) -> Any:
    if not path.exists():
        raise BankBuildError(f"{what} 不存在: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — 统一转 BankBuildError
        raise BankBuildError(f"{what} 解析失败: {path} ({exc})")


def _point_index(pack_id: str) -> dict[str, dict[str, Any]]:
    """compiled_source 的 point_id → {quote, source_ref} 索引（quote 为空的点不进索引）。"""
    cs = _load_json(RAW_DIR / f"_{pack_id}_compiled_source.json", "compiled_source")
    index: dict[str, dict[str, Any]] = {}
    for unit in cs.get("units") or []:
        ref = unit.get("source_ref") or {}
        for sp in unit.get("scoring_points") or []:
            pid = str(sp.get("point_id") or "")
            quote = str(sp.get("quote") or "").strip()
            if not pid or not quote or pid in index:
                continue
            index[pid] = {
                "quote": quote,
                "source_ref": {
                    "chunk_id": str(ref.get("chunk_id") or ""),
                    "page_num": ref.get("page_num"),
                    "source_lane": str(ref.get("source_lane") or ""),
                },
                "leaf_name_path": str(unit.get("leaf_name_path") or ""),
            }
    return index


def _section1_table_rows(pack_md: str) -> list[list[str]]:
    """抽 §1（`## 1.` / `## 1 ·`）里的 markdown 表行（含表头，不含分隔行）。"""
    rows: list[list[str]] = []
    in_sec = False
    for line in pack_md.splitlines():
        if line.startswith("## "):
            in_sec = bool(re.match(r"^## 1[.\s·]", line))
            continue
        if not in_sec:
            continue
        striped = line.strip()
        if not striped.startswith("|"):
            continue
        cells = [c.strip() for c in striped.strip("|").split("|")]
        if cells and set("".join(cells)) <= set("-—: "):
            continue  # 分隔行
        rows.append(cells)
    return rows


def _column_map(header: list[str]) -> dict[str, int]:
    """按表头语义定位列（S05 七列版 / A01 五列版共用）。"""
    cols: dict[str, int] = {}
    for idx, cell in enumerate(header):
        if "知识点" in cell and "name" not in cols:
            cols["name"] = idx
        elif "关键" in cell and "gist" not in cols:
            cols["gist"] = idx
        elif "三色" in cell and "color" not in cols:
            cols["color"] = idx
    missing = {"name", "gist", "color"} - set(cols)
    if missing:
        raise BankBuildError(f"§1 表头缺语义列 {sorted(missing)}: {header}")
    return cols


def _clean_name(raw: str) -> str:
    name = _MD_DECOR_RE.sub("", raw).strip()
    return _TRAILING_PAREN_RE.sub("", name).strip()


def derive_cards(pack_id: str) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    """确定性派生：返回 (cards, dropped_rows, source_pack_sha256)。纯函数式重建。"""
    manifest = _load_json(PACK_DIR / "_pack_manifest.json", "pack manifest")
    entry = next(
        (p for p in manifest.get("packs") or [] if p.get("pack_id") == pack_id), None
    )
    if entry is None or not entry.get("file"):
        raise BankBuildError(f"manifest 中无 pack {pack_id}")
    pack_path = PACK_DIR / str(entry["file"])
    pack_bytes = pack_path.read_bytes()
    pack_sha = hashlib.sha256(pack_bytes).hexdigest()
    if pack_sha != str(entry.get("content_sha256") or ""):
        raise BankBuildError(
            f"manifest content_sha256 落后于 pack 正文，先重跑 scripts/build_luban_pack_manifest.py"
        )
    points = _point_index(pack_id)
    rows = _section1_table_rows(pack_bytes.decode("utf-8"))
    if len(rows) < 2:
        raise BankBuildError(f"{pack_id} §1 未找到知识点全景表")
    cols = _column_map(rows[0])

    cards: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    seen_points: set[str] = set()
    for row in rows[1:]:
        if len(row) <= max(cols.values()):
            continue
        name = _clean_name(row[cols["name"]])
        color_cell = row[cols["color"]]
        row_text = " | ".join(row)
        if not name:
            continue
        if "🟢" not in color_cell or "🟡" in color_cell or "🔴" in color_cell:
            dropped.append({"row": name, "reason": "not_green"})
            continue
        resolved = next(
            (a for a in _KC_ANCHOR_RE.findall(row_text) if a in points), None
        )
        if resolved is None:
            dropped.append({"row": name, "reason": "no_verbatim_quote"})
            continue
        if resolved in seen_points:
            dropped.append({"row": name, "reason": "duplicate_point_id"})
            continue
        seen_points.add(resolved)
        point = points[resolved]
        cards.append(
            {
                "card_id": f"{pack_id}:{resolved}",
                "front": name,
                "key_gist": _MD_DECOR_RE.sub("", row[cols["gist"]]).strip(),
                "quote": point["quote"],
                "point_id": resolved,
                "source_ref": point["source_ref"],
                "leaf_name_path": point["leaf_name_path"],
            }
        )
    return cards, dropped, pack_sha


def run_gate(pack_id: str, cards: list[dict[str, Any]]) -> dict[str, Any]:
    """结构 + quote 逐字命中 compiled_source + 去重 + 禁审视词。100% 才算产出。"""
    points = _point_index(pack_id)
    quote_mismatches: list[str] = []
    duplicate_cards: list[str] = []
    forbidden_words: list[str] = []
    passed = 0
    seen_front: set[str] = set()
    for card in cards:
        ok = True
        source = points.get(str(card.get("point_id") or ""))
        if source is None or card.get("quote") != source["quote"]:
            quote_mismatches.append(card["card_id"])
            ok = False
        if card["front"] in seen_front:
            duplicate_cards.append(card["card_id"])
            ok = False
        seen_front.add(card["front"])
        template_text = f'{card.get("front", "")}|{card.get("key_gist", "")}'
        if any(w in template_text for w in FORBIDDEN_WORDS):
            forbidden_words.append(card["card_id"])
            ok = False
        if not card.get("front") or not card.get("quote"):
            if card["card_id"] not in quote_mismatches:
                quote_mismatches.append(card["card_id"])
            ok = False
        if ok:
            passed += 1
    total = len(cards)
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "quote_mismatches": quote_mismatches,
        "duplicate_cards": duplicate_cards,
        "forbidden_words": forbidden_words,
    }


def build_payload(pack_id: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    cards, dropped, pack_sha = derive_cards(pack_id)
    if not cards:
        raise BankBuildError(f"{pack_id} 派生 0 卡（fail-closed，无 quote 不成卡）")
    gate = run_gate(pack_id, cards)
    return {
        "schema_version": SCHEMA_NAME,
        "pack_id": pack_id,
        "status": "candidate",  # 签发唯一入口 = promote_variant_bank.py --kind concept_cards
        "source_pack_sha256": pack_sha,
        "generation_ms": round((time.perf_counter() - t0) * 1000, 2),
        "gate": gate,
        "card_count": len(cards),
        "dropped_rows": dropped,
        "cards": cards,
    }


def _stable_view(payload: dict[str, Any]) -> dict[str, Any]:
    """确定性比对视图：剔除非确定字段（generation_ms）与签发面（status/signoff，
    promote 人闸独占的翻牌字段——签发后的 bank 重跑 --check 仍应一致）。"""
    return {
        k: v
        for k, v in payload.items()
        if k not in ("generation_ms", "signoff", "status")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="考点卡 bank 编译器（确定性派生 + gate）")
    parser.add_argument("pack_id", help="pack id，如 S05")
    parser.add_argument(
        "--check", action="store_true",
        help="零写入：重派生 + 重跑 gate + 与磁盘 bank 逐卡比对",
    )
    args = parser.parse_args()
    pack_id = args.pack_id.strip().upper()
    if not _PACK_ID_RE.match(pack_id):
        print(f"build-concept-card-bank: 非法 pack_id {args.pack_id!r}", file=sys.stderr)
        return 1
    try:
        payload = build_payload(pack_id)
    except BankBuildError as exc:
        print(f"build-concept-card-bank: FAIL — {exc}", file=sys.stderr)
        return 1
    gate = payload["gate"]
    clean = not (
        gate["quote_mismatches"] or gate["duplicate_cards"] or gate["forbidden_words"]
    )
    print(
        f"cards={gate['total']} gate_pass={gate['passed']} rate={gate['pass_rate']:.2%} "
        f"dropped={len(payload['dropped_rows'])} -> {'PASS' if clean else 'FAIL'}"
    )
    if not clean or gate["passed"] != gate["total"]:
        print(json.dumps(
            {k: gate[k] for k in ("quote_mismatches", "duplicate_cards", "forbidden_words")},
            ensure_ascii=False), file=sys.stderr)
        return 1

    out_path = PACK_DIR / BANK_TEMPLATE.format(pack_id=pack_id)
    if args.check:
        if out_path.exists():
            existing = _load_json(out_path, "考点卡 bank")
            if _stable_view(existing) != _stable_view(payload):
                print(
                    "build-concept-card-bank: FAIL — 磁盘 bank 与确定性重建不一致"
                    "（pack/builder 已变更），请重跑本脚本重建后再签发",
                    file=sys.stderr,
                )
                return 1
        return 0
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"written {out_path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
