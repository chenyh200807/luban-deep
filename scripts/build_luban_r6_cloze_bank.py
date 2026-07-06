#!/usr/bin/env python3
"""R6 精确挖空 bank 编译器（确定性派生自签发 pack §5.1，禁 LLM 现编——双轮 v3.2 §8）。

派生层裁决（2026-07-05，与考点卡 builder 同构）：
- **§5.1「R5 采分点」表 = 唯一派生层**。每行 = `| C?-? | 采分点 statement | 锚 point_id |
  required_terms |`；required_terms 已 slash 分隔、机器可读（教研 authored 采分关键词）。
- 挖空 = **纯确定性字符串操作**：把 required_terms 里**字面命中** statement 的关键词整段
  （首命中→末命中的跨度）替成 blank，前后残句进 `text_before/text_after`，`blank_hint`
  = 被挖的 required_terms 本身（关键词即提示颗粒）。**零 LLM 决定挖哪个 span**
  （若 LLM 定 span = 隐蔽生成口，v3 §8 红队采信）。
- 忠实门口径：required_terms 是教研 authored 采分词（compiled_source 的 required_terms /
  quote 是同义**近似**，非逐字一致——实测 A01 多数采分词与 compiled_source 有破折号/
  措辞差），故本 bank grounding 到 **signed-pack §5 级**：锚 kc: resolve 到
  compiled_source（真源头绑定）+ 被挖词字面命中 statement（挖空可复现）+ 禁词。

**fail-closed 铁律**（每条都无豁免，宁缺毋滥）：
1. 锚 point_id 必须 resolve 到 `_{pack}_compiled_source.json`（真题-only / m35 锚
   在此掉，丢 `anchor_unresolved`）；
2. required_terms 至少一词**字面命中** statement 才能挖（对不上丢 `term_not_in_sentence`，
   **不 LLM 补**——无出处不成卡的惯例平移）；
3. 禁审视揭短词（看穿/识破/揭穿/露馅）落在 blank_hint/残句 → 丢；
4. 恒写 status="candidate"——签发（candidate→signed）唯一入口 =
   docs/原始数据/考点原料/promote_variant_bank.py --kind cloze（人闸）。

R7 边界裁决层（§5.3 全 🔴 待教研）不投影。gate 必须 100% 才写文件；
--check 模式零写入：重派生 + 重跑 gate + 与磁盘 bank 逐条比对。

用法::

    python3 scripts/build_luban_r6_cloze_bank.py A01          # 生成/更新 bank
    python3 scripts/build_luban_r6_cloze_bank.py A01 --check  # 零写入核验
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

SCHEMA_NAME = "luban-cloze-bank"  # dash 命名空间=脚本编译产物, 非 runtime schema(同变体池惯例)
BANK_TEMPLATE = "_{pack_id}_r6_cloze_bank.v0.json"
RECALL_PROMPT = "想一想：每个采分点的关键词，你能默写全吗？"  # 模板常量, 非 LLM 生成

_PACK_ID_RE = re.compile(r"^[A-Z]\d{2}$")
_KC_ANCHOR_RE = re.compile(r"kc:[0-9A-Za-z_]+:\d+")
_TERM_SPLIT_RE = re.compile(r"[/／,，、]")
_PAREN_NOTE_RE = re.compile(r"[（(][^（）()]*[）)]")
_MD_DECOR_RE = re.compile(r"[*`]")
FORBIDDEN_WORDS = ("看穿", "识破", "揭穿", "露馅")


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


def _section5(pack_md: str) -> str:
    """抽 `## 5` 段正文到下一个 `## `。兼容 `## 5` / `## 5.` / `## 5 ·` / `## §5`。"""
    pat = re.compile(r"^##\s+§?5([.\s·]|$)")
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
            continue
        rows.append(cells)
    return rows


def _r5_column_map(header: list[str]) -> dict[str, int] | None:
    """R5 采分点表按表头语义定位列。必须有 采分点列 + required_terms 列
    （挖空源头），否则返回 None（非 R5 采分点表）。锚由整行扫描兜底。"""
    cols: dict[str, int] = {}
    for idx, cell in enumerate(header):
        low = cell
        if "采分点" in low and "stmt" not in cols:
            cols["stmt"] = idx
        elif "required_terms" in low and "req" not in cols:
            cols["req"] = idx
    if {"stmt", "req"} <= set(cols):
        return cols
    return None


def _split_terms(raw: str) -> list[str]:
    """required_terms 单元格 → 关键词列表（剥括注/markdown 装饰/空白）。"""
    out: list[str] = []
    for part in _TERM_SPLIT_RE.split(raw):
        part = _PAREN_NOTE_RE.sub("", part)
        part = _MD_DECOR_RE.sub("", part).strip()
        if part:
            out.append(part)
    return out


def _carve(statement: str, terms: list[str]) -> dict[str, Any] | None:
    """把 statement 里 required_terms 首命中→末命中的跨度挖空。无命中返回 None。"""
    hits = [(statement.find(t), statement.find(t) + len(t), t) for t in terms if t in statement]
    if not hits:
        return None
    first = min(h[0] for h in hits)
    last = max(h[1] for h in hits)
    found = [h[2] for h in sorted(hits, key=lambda h: h[0])]
    return {
        "text_before": statement[:first],
        "blank_hint": " / ".join(found),
        "text_after": statement[last:],
    }


def derive_cloze(
    pack_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    """确定性派生：返回 (skeleton_sentences, dropped_rows, source_pack_sha256)。纯函数式重建。"""
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
    sec5 = _section5(pack_bytes.decode("utf-8"))
    rows = _table_rows(sec5)
    cols = next((c for r in rows if (c := _r5_column_map(r)) is not None), None)
    if cols is None:
        raise BankBuildError(
            f"{pack_id} §5 无 required_terms 列的 R5 采分点表（精确挖空源缺失，"
            f"须教研补 required_terms 列，禁 LLM 造）"
        )
    max_col = max(cols.values())

    sentences: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = []
    seen: set[str] = set()
    seq = 0
    for cells in rows:
        if len(cells) <= max_col:
            continue
        if _r5_column_map(cells) is not None:
            continue  # 表头行
        raw_id = re.sub(r"\s+", "", _MD_DECOR_RE.sub("", cells[0])).strip()
        seq += 1
        cid = raw_id or str(seq)
        cloze_id = f"{pack_id}:{cid}"
        if cid in seen:
            dropped.append({"cloze_id": cloze_id, "reason": "duplicate_cloze_id"})
            continue
        seen.add(cid)
        statement = _MD_DECOR_RE.sub("", cells[cols["stmt"]]).strip()
        terms = _split_terms(cells[cols["req"]])
        resolved = next(
            (k for k in _KC_ANCHOR_RE.findall(" ".join(cells)) if k in points), None
        )
        if resolved is None:
            dropped.append({"cloze_id": cloze_id, "reason": "anchor_unresolved"})
            continue
        if not terms:
            dropped.append({"cloze_id": cloze_id, "reason": "no_required_terms"})
            continue
        carved = _carve(statement, terms)
        if carved is None:
            dropped.append({"cloze_id": cloze_id, "reason": "term_not_in_sentence"})
            continue
        sentences.append(
            {
                "cloze_id": cloze_id,
                "point_id": resolved,
                "text_before": carved["text_before"],
                "blank_hint": carved["blank_hint"],
                "text_after": carved["text_after"],
            }
        )
    return sentences, dropped, pack_sha


def run_gate(pack_id: str, sentences: list[dict[str, Any]]) -> dict[str, Any]:
    """锚 resolve + 被挖词字面回填 statement + 禁审视词。100% 才算产出（防 gate 自证）。"""
    points = _point_ids(pack_id)
    anchor_unresolved: list[str] = []
    term_not_in_sentence: list[str] = []
    forbidden_words: list[str] = []
    passed = 0
    for s in sentences:
        ok = True
        if str(s.get("point_id") or "") not in points:
            anchor_unresolved.append(s["cloze_id"])
            ok = False
        # 挖空可复现性：残句 + blank_hint 拼回必须含每个被挖词（无凭空 blank）
        blank_terms = [t.strip() for t in str(s.get("blank_hint") or "").split("/") if t.strip()]
        rejoined = f'{s.get("text_before", "")}{s.get("blank_hint", "")}{s.get("text_after", "")}'
        if not blank_terms or any(t not in rejoined for t in blank_terms):
            term_not_in_sentence.append(s["cloze_id"])
            ok = False
        surface = f'{s.get("text_before", "")}｜{s.get("blank_hint", "")}｜{s.get("text_after", "")}'
        if any(w in surface for w in FORBIDDEN_WORDS):
            forbidden_words.append(s["cloze_id"])
            ok = False
        if ok:
            passed += 1
    total = len(sentences)
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "anchor_unresolved": anchor_unresolved,
        "term_not_in_sentence": term_not_in_sentence,
        "forbidden_words": forbidden_words,
    }


def build_payload(pack_id: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    sentences, dropped, pack_sha = derive_cloze(pack_id)
    if not sentences:
        raise BankBuildError(
            f"{pack_id} 派生 0 挖空句（fail-closed，无锚/关键词对不上不成句）"
        )
    gate = run_gate(pack_id, sentences)
    return {
        "schema_version": SCHEMA_NAME,
        "pack_id": pack_id,
        "status": "candidate",  # 签发唯一入口 = promote_variant_bank.py --kind cloze
        "source_pack_sha256": pack_sha,
        "generation_ms": round((time.perf_counter() - t0) * 1000, 2),
        "gate": gate,
        "recall_prompt": RECALL_PROMPT,
        "cloze_count": len(sentences),
        "dropped_rows": dropped,
        "skeleton_sentences": sentences,
    }


def _stable_view(payload: dict[str, Any]) -> dict[str, Any]:
    """确定性比对视图：剔除非确定字段（generation_ms）与签发面（status/signoff）。"""
    return {
        k: v
        for k, v in payload.items()
        if k not in ("generation_ms", "signoff", "status")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="R6 精确挖空 bank 编译器（确定性派生 + gate）")
    parser.add_argument("pack_id", help="pack id，如 A01")
    parser.add_argument(
        "--check", action="store_true",
        help="零写入：重派生 + 重跑 gate + 与磁盘 bank 逐条比对",
    )
    args = parser.parse_args()
    pack_id = args.pack_id.strip().upper()
    if not _PACK_ID_RE.match(pack_id):
        print(f"build-cloze-bank: 非法 pack_id {args.pack_id!r}", file=sys.stderr)
        return 1
    try:
        payload = build_payload(pack_id)
    except BankBuildError as exc:
        print(f"build-cloze-bank: FAIL — {exc}", file=sys.stderr)
        return 1
    gate = payload["gate"]
    clean = not (
        gate["anchor_unresolved"] or gate["term_not_in_sentence"] or gate["forbidden_words"]
    )
    print(
        f"cloze={gate['total']} gate_pass={gate['passed']} rate={gate['pass_rate']:.2%} "
        f"dropped={len(payload['dropped_rows'])} -> {'PASS' if clean else 'FAIL'}"
    )
    if not clean or gate["passed"] != gate["total"]:
        print(json.dumps(
            {k: gate[k] for k in ("anchor_unresolved", "term_not_in_sentence", "forbidden_words")},
            ensure_ascii=False), file=sys.stderr)
        return 1

    out_path = PACK_DIR / BANK_TEMPLATE.format(pack_id=pack_id)
    if args.check:
        if out_path.exists():
            existing = _load_json(out_path, "挖空 bank")
            if _stable_view(existing) != _stable_view(payload):
                print(
                    "build-cloze-bank: FAIL — 磁盘 bank 与确定性重建不一致"
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
