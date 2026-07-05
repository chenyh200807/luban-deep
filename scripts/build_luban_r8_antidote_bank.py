#!/usr/bin/env python3
"""R8 解药 bank 编译器（确定性派生自签发 pack §6，禁 LLM 现编——双轮 v3.2 §8）。

派生层裁决（2026-07-05，与考点卡 builder 同构）：
- **§6「R8 误区 → error_code → 解药」= 唯一派生层**。每个 `**R8-N ｜ …**` 块
  自带 `error_code：`（可多码 `E10＋M08`）、`现象`、`错误心智模型`、`解药`、`🟢/🟡/🔴 锚`
  ——正好是错因银行「解药位」的消费形态 `{error_code} → {mental_model, textbook_ref}`。
- 解药正文 = 教研 authored **🔵 讲懂用语**，不是逐字教材 quote。所以本 bank 的忠实
  门比考点卡**弱一档**：做不了「quote 逐字命中」硬门，grounding 只到 **signed-pack
  级**（error_code ∈ registry + kc: 锚 resolve 到 compiled_source + 三色门 + 禁词）。
  对外不得声称「答案绝对正确」——这是诚实的能力边界（v3 §6 护城河口径）。

**fail-closed 铁律**（每条都无豁免，宁缺毋滥）：
1. 三色门：块含 `🔴待验证` 子句、或无 🟢 教材锚（纯 🟡/🔴）→ 丢（`antidote_amber_red`），
   R7 全 🔴 边界层本就不在 §6，不进 bank；
2. error_code 必须全部 ∈ `deeptutor/contracts/error_codes.py` 的 ERROR_CODE_REGISTRY
   （无一自造，否则丢 `code_unregistered`）；
3. 🟢 教材锚的 kc: point_id 必须 resolve 到 `_{pack}_compiled_source.json`
   （真题-only 锚 / m35 锚 / 未命中锚在此掉，丢 `anchor_unresolved`）；
4. 禁审视揭短词（看穿/识破/揭穿/露馅）落在 authored 文（解药/现象/错误心智模型）→ 丢；
5. 同 r8_id 去重；
6. 恒写 status="candidate"——签发（candidate→signed）唯一入口 =
   docs/原始数据/考点原料/promote_variant_bank.py --kind antidote（人闸）。

gate（结构 + 码 ∈ registry + 锚 resolve + 禁词）必须 100% 才写文件；
--check 模式零写入：重派生 + 重跑 gate，且若磁盘已有 bank 逐条比对
（builder 升版 / pack 改动都会在此现形）。

用法::

    python3 scripts/build_luban_r8_antidote_bank.py A01          # 生成/更新 bank
    python3 scripts/build_luban_r8_antidote_bank.py A01 --check  # 零写入核验
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

from deeptutor.contracts.error_codes import ERROR_CODE_REGISTRY

REPO = Path(__file__).resolve().parents[1]
RAW_DIR = REPO / "docs" / "原始数据" / "考点原料"
PACK_DIR = RAW_DIR / "成品"

SCHEMA_NAME = "luban-antidote-bank"  # dash 命名空间=脚本编译产物, 非 runtime schema(同变体池惯例)
BANK_TEMPLATE = "_{pack_id}_r8_antidote_bank.v0.json"

_PACK_ID_RE = re.compile(r"^[A-Z]\d{2}$")
_KC_ANCHOR_RE = re.compile(r"kc:[0-9A-Za-z_]+:\d+")
_ERROR_CODE_RE = re.compile(r"[EM]\d{2}")
_R8_BLOCK_RE = re.compile(r"(?=^\*\*R8-\d+\s*[｜|])", re.MULTILINE)
_R8_ID_RE = re.compile(r"^\*\*R8-(\d+)")
_RED_UNVERIFIED = "🔴待验证"
# error_code 单元格若被标记「待核验/待注册表确认」= 码未过 registry 门, fail-closed 丢
# （N02 类明示「错因码一律改挂待核验」——禁把括注里的 Lens 原码当已验证码采信）
_CODE_UNVERIFIED_MARKS = ("🔴", "待核验", "待注册", "待确认", "待验证")
# 文案铁律: 禁审视揭短词——只查 authored 文(解药/现象/错误心智模型), 无逐字教材可查
FORBIDDEN_WORDS = ("看穿", "识破", "揭穿", "露馅")
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


def _point_ids(pack_id: str) -> set[str]:
    """compiled_source 的 point_id 集合（锚 resolve 白名单，quote 为空的点不算锚）。"""
    cs = _load_json(RAW_DIR / f"_{pack_id}_compiled_source.json", "compiled_source")
    ids: set[str] = set()
    for unit in cs.get("units") or []:
        for sp in unit.get("scoring_points") or []:
            pid = str(sp.get("point_id") or "")
            quote = str(sp.get("quote") or "").strip()
            if pid and quote:
                ids.add(pid)
    return ids


def _section(pack_md: str, num: int) -> str:
    """抽 `## {num}` 段正文到下一个 `## `。兼容 `## 6` / `## 6.` / `## 6 ·` / `## §6`。"""
    pat = re.compile(rf"^##\s+§?{num}([.\s·]|$)")
    out: list[str] = []
    in_sec = False
    for line in pack_md.splitlines():
        if line.startswith("## "):
            in_sec = bool(pat.match(line))
            continue
        if in_sec:
            out.append(line)
    return "\n".join(out)


def _table_rows(section_md: str) -> list[list[str]]:
    """段内所有 markdown 表行（含表头，剔除分隔行）。"""
    rows: list[list[str]] = []
    for line in section_md.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and set("".join(cells)) <= set("-—: "):
            continue  # 分隔行
        rows.append(cells)
    return rows


def _antidote_column_map(header: list[str]) -> dict[str, int] | None:
    """§6 R8 表按表头语义定位列（跨 pack 列名/列数不一，同 concept_cards._column_map 思路）。
    必须定位到 error_code 列 + 解药列（锚列可选——缺列时锚由整行扫描兜底）；
    否则返回 None（此表非 R8 误区表）。"""
    cols: dict[str, int] = {}
    for idx, cell in enumerate(header):
        low = cell
        if ("error_code" in low or "错因码" in low or "错因" in low or "error code" in low) and "code" not in cols:
            cols["code"] = idx
        elif "解药" in low and "antidote" not in cols:
            cols["antidote"] = idx
        elif "锚" in low and "anchor" not in cols:
            cols["anchor"] = idx
        elif ("误区" in low or "现象" in low) and "phenom" not in cols:
            cols["phenom"] = idx
        elif "心智" in low and "wrong" not in cols:
            cols["wrong"] = idx
    if {"code", "antidote"} <= set(cols):
        return cols
    return None


def _field(block: str, label: str) -> str:
    """取 `- {label}：<值>` 行的值（markdown 装饰剥掉）。"""
    for line in block.splitlines():
        s = line.strip().lstrip("-").strip()
        if s.startswith(label + "：") or s.startswith(label + ":"):
            val = re.split(r"[：:]", s, maxsplit=1)[1]
            return _MD_DECOR_RE.sub("", val).strip()
    return ""


def _green_textbook_anchors(block: str) -> list[str]:
    """🟢锚（教材）行里的 kc: 锚（按出现序）。"""
    for line in block.splitlines():
        if "🟢锚" in line and "教材" in line:
            return _KC_ANCHOR_RE.findall(line)
    return []


def _raw_from_blocks(pack_id: str, sec6: str) -> list[dict[str, Any]]:
    """A01 体例：`**R8-N ｜**` 块 + `- 解药：` / `- error_code：` / `🟢锚（教材）` 逐字段。"""
    raws: list[dict[str, Any]] = []
    for block in _R8_BLOCK_RE.split(sec6):
        m = _R8_ID_RE.match(block)
        if not m:
            continue
        ec_line = next((l for l in block.splitlines() if "error_code" in l), "")
        raws.append(
            {
                "raw_id": f"R8-{m.group(1)}",
                "codes": _ERROR_CODE_RE.findall(ec_line),
                "code_unverified": False,  # 块体例的码不带待核验标记
                "mental_model": _field(block, "解药"),
                "phenomenon": _field(block, "现象"),
                "wrong_model": _field(block, "错误心智模型"),
                "green_kcs": _green_textbook_anchors(block),
                "has_red_unverified": _RED_UNVERIFIED in block,
            }
        )
    return raws


def _raw_from_table(pack_id: str, sec6: str) -> list[dict[str, Any]]:
    """Codex-镜头体例：§6 R8 误区表（error_code / 对症解药 / 锚 语义列，列名列数不一）。"""
    rows = _table_rows(sec6)
    header = next((r for r in rows if _antidote_column_map(r) is not None), None)
    if header is None:
        return []
    cols = _antidote_column_map(header)
    # 码列表头本身带待核验/🔴 标记（K01/N02 类明示「错因码待注册表核准」）
    # → 整表的码都不可信，逐行 fail-closed 丢。
    table_codes_unverified = any(
        mark in header[cols["code"]] for mark in _CODE_UNVERIFIED_MARKS
    )
    max_col = max(cols.values())
    raws: list[dict[str, Any]] = []
    seq = 0
    for row in rows:
        if len(row) <= max_col:
            continue
        if _antidote_column_map(row) is not None:
            continue  # 表头行
        code_cell = row[cols["code"]]
        antidote_cell = _MD_DECOR_RE.sub("", row[cols["antidote"]]).strip()
        code_unverified = table_codes_unverified or any(
            mark in code_cell for mark in _CODE_UNVERIFIED_MARKS
        )
        codes = _ERROR_CODE_RE.findall(code_cell)
        anchor_cell = row[cols["anchor"]] if "anchor" in cols else ""
        green_kcs = _KC_ANCHOR_RE.findall(anchor_cell) or _KC_ANCHOR_RE.findall(" ".join(row))
        raw_id_cell = re.sub(r"\s+", "", _MD_DECOR_RE.sub("", row[0])).strip()
        seq += 1
        raws.append(
            {
                "raw_id": f"R8-{raw_id_cell or seq}",
                "codes": codes,
                "code_unverified": code_unverified,
                "mental_model": antidote_cell,
                "phenomenon": _MD_DECOR_RE.sub("", row[cols["phenom"]]).strip()
                if "phenom" in cols else "",
                "wrong_model": _MD_DECOR_RE.sub("", row[cols["wrong"]]).strip()
                if "wrong" in cols else "",
                "green_kcs": green_kcs,
                # 解药正文自带 🔴（待规范回填/待验证）= 该条解药未定稿, fail-closed 丢
                "has_red_unverified": "🔴" in antidote_cell,
            }
        )
    return raws


def derive_antidotes(
    pack_id: str,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[dict[str, str]], str]:
    """确定性派生：返回 (antidotes_by_code, kept_rows, dropped_rows, source_pack_sha256)。

    ``antidotes_by_code``：error_code → 解药条目列表（一码可挂多条 R8）。
    ``kept_rows``：去重后的 R8 条目（gate 与计数以此为准）。纯函数式重建。
    §6 有 `**R8-N ｜` 块走块体例；否则走 R8 误区表体例（两者共用同一 fail-closed 过滤）。
    """
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
    points = _point_ids(pack_id)
    sec6 = _section(pack_bytes.decode("utf-8"), 6)
    raws = _raw_from_blocks(pack_id, sec6) or _raw_from_table(pack_id, sec6)

    antidotes: dict[str, list[dict[str, Any]]] = {}
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in raws:
        r8_id = f"{pack_id}:{raw['raw_id']}"
        if raw["raw_id"] in seen:
            dropped.append({"r8_id": r8_id, "reason": "duplicate_r8_id"})
            continue
        seen.add(raw["raw_id"])
        resolved = next((k for k in raw["green_kcs"] if k in points), None)

        # 三色门：含 🔴待验证 子句 → fail-closed 丢
        if raw["has_red_unverified"]:
            dropped.append({"r8_id": r8_id, "reason": "antidote_amber_red"})
            continue
        # 码待核验（N02 类明示待注册表确认）→ 码不可信, fail-closed 丢
        if raw["code_unverified"]:
            dropped.append({"r8_id": r8_id, "reason": "code_unverified"})
            continue
        if not raw["codes"]:
            dropped.append({"r8_id": r8_id, "reason": "no_error_code"})
            continue
        if resolved is None:
            dropped.append({"r8_id": r8_id, "reason": "anchor_unresolved"})
            continue
        if not raw["mental_model"]:
            dropped.append({"r8_id": r8_id, "reason": "no_antidote_text"})
            continue

        entry_obj = {
            "r8_id": r8_id,
            "mental_model": raw["mental_model"],
            "textbook_ref": resolved,
            "phenomenon": raw["phenomenon"],
            "wrong_model": raw["wrong_model"],
        }
        kept.append({"error_codes": raw["codes"], **entry_obj})
        for code in raw["codes"]:
            antidotes.setdefault(code, []).append(dict(entry_obj))
    return antidotes, kept, dropped, pack_sha


def run_gate(pack_id: str, kept: list[dict[str, Any]]) -> dict[str, Any]:
    """码 ∈ registry + 锚 resolve + 禁审视词。100% 才算产出（对已保留行再核一遍防自证）。"""
    points = _point_ids(pack_id)
    code_unregistered: list[str] = []
    anchor_unresolved: list[str] = []
    forbidden_words: list[str] = []
    passed = 0
    for row in kept:
        ok = True
        for code in row.get("error_codes") or []:
            if code not in ERROR_CODE_REGISTRY:
                code_unregistered.append(f'{row["r8_id"]}:{code}')
                ok = False
        if str(row.get("textbook_ref") or "") not in points:
            anchor_unresolved.append(row["r8_id"])
            ok = False
        authored = "｜".join(
            str(row.get(k) or "") for k in ("mental_model", "phenomenon", "wrong_model")
        )
        if any(w in authored for w in FORBIDDEN_WORDS):
            forbidden_words.append(row["r8_id"])
            ok = False
        if not row.get("mental_model") or not (row.get("error_codes") or []):
            if row["r8_id"] not in code_unregistered:
                code_unregistered.append(row["r8_id"])
            ok = False
        if ok:
            passed += 1
    total = len(kept)
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "code_unregistered": code_unregistered,
        "anchor_unresolved": anchor_unresolved,
        "forbidden_words": forbidden_words,
    }


def build_payload(pack_id: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    antidotes, kept, dropped, pack_sha = derive_antidotes(pack_id)
    if not kept:
        raise BankBuildError(
            f"{pack_id} 派生 0 解药（fail-closed，无 🟢 教材锚/无注册码不成解药）"
        )
    gate = run_gate(pack_id, kept)
    return {
        "schema_version": SCHEMA_NAME,
        "pack_id": pack_id,
        "status": "candidate",  # 签发唯一入口 = promote_variant_bank.py --kind antidote
        "source_pack_sha256": pack_sha,
        "generation_ms": round((time.perf_counter() - t0) * 1000, 2),
        "gate": gate,
        "antidote_count": len(kept),
        "dropped_rows": dropped,
        "antidotes": antidotes,
    }


def _stable_view(payload: dict[str, Any]) -> dict[str, Any]:
    """确定性比对视图：剔除非确定字段（generation_ms）与签发面（status/signoff）。"""
    return {
        k: v
        for k, v in payload.items()
        if k not in ("generation_ms", "signoff", "status")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="R8 解药 bank 编译器（确定性派生 + gate）")
    parser.add_argument("pack_id", help="pack id，如 A01")
    parser.add_argument(
        "--check", action="store_true",
        help="零写入：重派生 + 重跑 gate + 与磁盘 bank 逐条比对",
    )
    args = parser.parse_args()
    pack_id = args.pack_id.strip().upper()
    if not _PACK_ID_RE.match(pack_id):
        print(f"build-antidote-bank: 非法 pack_id {args.pack_id!r}", file=sys.stderr)
        return 1
    try:
        payload = build_payload(pack_id)
    except BankBuildError as exc:
        print(f"build-antidote-bank: FAIL — {exc}", file=sys.stderr)
        return 1
    gate = payload["gate"]
    clean = not (
        gate["code_unregistered"] or gate["anchor_unresolved"] or gate["forbidden_words"]
    )
    print(
        f"antidotes={gate['total']} gate_pass={gate['passed']} rate={gate['pass_rate']:.2%} "
        f"dropped={len(payload['dropped_rows'])} -> {'PASS' if clean else 'FAIL'}"
    )
    if not clean or gate["passed"] != gate["total"]:
        print(json.dumps(
            {k: gate[k] for k in ("code_unregistered", "anchor_unresolved", "forbidden_words")},
            ensure_ascii=False), file=sys.stderr)
        return 1

    out_path = PACK_DIR / BANK_TEMPLATE.format(pack_id=pack_id)
    if args.check:
        if out_path.exists():
            existing = _load_json(out_path, "解药 bank")
            if _stable_view(existing) != _stable_view(payload):
                print(
                    "build-antidote-bank: FAIL — 磁盘 bank 与确定性重建不一致"
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
