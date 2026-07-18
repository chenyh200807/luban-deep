#!/usr/bin/env python3
"""Prefill source-anchor CANDIDATES for practice review packets.

Machine-suggestion helper for the owner sign-off of practice review packets
(schema ``luban_practice_review_packet.v1``). For every item in a packet it
matches the question text (stem + correct options + model_answer) against the
pack's compiled textbook source chunks (``_<PACK>_compiled_source.json``) and
real-exam evidence (``_<PACK>_exam_evidence.json``) using plain keyword /
character-bigram overlap (no LLM, no third-party deps), and writes the top-3
candidate anchors per question to a SEPARATE file::

    docs/原始数据/考点原料/成品/_practice_review_packets/{pack}.anchor.candidates.json

Hard safety guarantees (human_gate.machine_must_not_sign = true):
  * The review packet itself is opened read-only and NEVER modified.
  * ``decision.*`` fields are NEVER filled and nothing is signed.
  * The output file carries ``"machine_candidates_only": true`` so downstream
    tooling can never mistake it for a human decision.

Usage:
    python scripts/prefill_practice_review_anchors.py N01 S05 X01
    python scripts/prefill_practice_review_anchors.py --base-dir <考点原料 dir> --threshold 0.25 N01
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_DIR = REPO_ROOT / "docs" / "原始数据" / "考点原料"
PACKETS_SUBDIR = Path("成品") / "_practice_review_packets"
DEFAULT_THRESHOLD = 0.25  # min match_score for a candidate to count as "像样"
TOP_K = 3
MAX_QUOTE_LEN = 200

_CJK_RE = re.compile(r"[一-鿿]")
# numbers with an optional unit tail (25个月, 3%, 1.5m, 30mA, TT系统的"30")
_NUM_RE = re.compile(r"\d+(?:\.\d+)?(?:%|‰|[a-zA-Z²³]{1,4}|[个条道台次级层月日天年步阶段米]{1,2})?")
# latin tokens like TF, GB/T, TN-S
_ASCII_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-/]{1,10}")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cjk_bigrams(text: str) -> set[str]:
    chars = _CJK_RE.findall(text)
    return {a + b for a, b in zip(chars, chars[1:])}


def salient_terms(text: str) -> set[str]:
    """Numeric tokens + latin tokens — the high-precision keywords."""
    terms = {t for t in _NUM_RE.findall(text) if len(t) >= 2 or t.isdigit()}
    terms |= {t.upper() for t in _ASCII_RE.findall(text)}
    return terms


def match_score(query_bigrams: set[str], query_terms: set[str], cand_text: str) -> float:
    """0..1 overlap score: 0.7 * CJK-bigram containment + 0.3 * salient-term hits."""
    cand_bigrams = cjk_bigrams(cand_text)
    if query_bigrams and cand_bigrams:
        overlap = len(query_bigrams & cand_bigrams) / min(len(query_bigrams), len(cand_bigrams))
    else:
        overlap = 0.0
    if not query_terms:
        return round(overlap, 4)
    cand_upper = cand_text.upper()
    hit = sum(1 for t in query_terms if t.upper() in cand_upper)
    return round(0.7 * overlap + 0.3 * (hit / len(query_terms)), 4)


def best_quote(cand_text: str, query_bigrams: set[str], max_len: int = MAX_QUOTE_LEN) -> str:
    """Pick the <=max_len window of cand_text densest in matched bigrams."""
    text = re.sub(r"\s+", " ", cand_text).strip()
    if len(text) <= max_len:
        return text
    best_start, best_hits = 0, -1
    step = max(1, max_len // 4)
    for start in range(0, len(text) - max_len + 1, step):
        window = text[start : start + max_len]
        hits = sum(1 for bg in query_bigrams if bg in window)
        if hits > best_hits:
            best_start, best_hits = start, hits
    return text[best_start : best_start + max_len]


def load_source_units(base_dir: Path, pack: str) -> tuple[list[dict], list[str]]:
    """Return matchable evidence units [{anchor, text, source_file, source_sha256, group}] + warnings."""
    units: list[dict] = []
    warnings: list[str] = []

    compiled_path = base_dir / f"_{pack}_compiled_source.json"
    if compiled_path.exists():
        sha = sha256_file(compiled_path)
        rel = str(compiled_path.relative_to(REPO_ROOT)) if compiled_path.is_relative_to(REPO_ROOT) else str(compiled_path)
        data = json.loads(compiled_path.read_text(encoding="utf-8"))
        for unit in data.get("units", []):
            chunk = (unit.get("source_ref") or {}).get("chunk_id", "")
            note = unit.get("note", "")
            for sp in unit.get("scoring_points", []):
                point_id = sp.get("point_id") or (f"kc:{chunk}" if chunk else "")
                if not point_id:
                    continue
                text = " ".join(filter(None, [sp.get("statement", ""), sp.get("quote", ""), note]))
                if not text.strip():
                    continue
                units.append(
                    {
                        "anchor": point_id,
                        "text": text,
                        "source_file": rel,
                        "source_sha256": sha,
                        # dedupe group: one candidate per distinct 采分点 (point_id).
                        # A single textbook chunk often carries multiple orthogonal
                        # scoring points (e.g. 1A413030_107_0210 = 灰缝/斜槎/马牙槎);
                        # grouping per-chunk masked the correct point for questions
                        # whose fact was not the chunk's top-scoring one. Per-point
                        # grouping surfaces each true textbook anchor as selectable;
                        # the human gate still picks the right one and the sign
                        # helper still resolves sha only from machine candidates.
                        "group": point_id,
                    }
                )
    else:
        warnings.append(f"[{pack}] compiled_source 不存在: {compiled_path} — 降级跳过教材锚")

    evidence_path = base_dir / f"_{pack}_exam_evidence.json"
    if evidence_path.exists():
        sha = sha256_file(evidence_path)
        rel = str(evidence_path.relative_to(REPO_ROOT)) if evidence_path.is_relative_to(REPO_ROOT) else str(evidence_path)
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
        for idx, ev in enumerate(data.get("evidence", [])):
            year = str(ev.get("year", "")).strip() or "unknown"
            qno = str(ev.get("题号", "")).strip() or f"idx{idx}"
            anchor = f"exam:{year}:{qno}"
            text = " ".join(
                filter(None, [ev.get("stem", ""), ev.get("correct_answer", ""), ev.get("analysis", "")])
            )
            if not text.strip():
                continue
            units.append(
                {
                    "anchor": anchor,
                    "text": text,
                    "source_file": rel,
                    "source_sha256": sha,
                    "group": anchor,
                }
            )
    else:
        warnings.append(f"[{pack}] exam_evidence 不存在: {evidence_path} — 降级只用 compiled_source")

    return units, warnings


def build_query(item: dict) -> str:
    parts = [item.get("stem", "")]
    for opt in item.get("options", []):
        if opt.get("is_correct"):
            parts.append(opt.get("text", ""))
    parts.append(item.get("model_answer", ""))
    return " ".join(filter(None, parts))


def candidates_for_item(item: dict, units: list[dict], threshold: float) -> list[dict]:
    query = build_query(item)
    qb = cjk_bigrams(query)
    qt = salient_terms(query)
    best_per_group: dict[str, dict] = {}
    for unit in units:
        score = match_score(qb, qt, unit["text"])
        if score < threshold:
            continue
        prev = best_per_group.get(unit["group"])
        if prev is None or score > prev["match_score"]:
            best_per_group[unit["group"]] = {
                "source_anchor": unit["anchor"],
                "quote": best_quote(unit["text"], qb),
                "match_score": score,
                "source_file": unit["source_file"],
                "source_sha256": unit["source_sha256"],
            }
    ranked = sorted(best_per_group.values(), key=lambda c: -c["match_score"])
    return ranked[:TOP_K]


def process_pack(base_dir: Path, pack: str, threshold: float) -> dict:
    pack = pack.upper()
    packet_path = base_dir / PACKETS_SUBDIR / f"{pack.lower()}.practice.review.json"
    if not packet_path.exists():
        raise FileNotFoundError(f"审核包不存在: {packet_path}")

    # Read-only: keep the original bytes to prove we never touch the packet.
    packet_bytes_before = packet_path.read_bytes()
    packet = json.loads(packet_bytes_before.decode("utf-8"))

    units, warnings = load_source_units(base_dir, pack)
    if not units:
        raise FileNotFoundError(
            f"[{pack}] compiled_source 与 exam_evidence 均不可用, 无法生成候选 (不造数据)"
        )

    items_out = []
    with_candidates = 0
    for item in packet.get("items", []):
        cands = candidates_for_item(item, units, threshold)
        if cands:
            with_candidates += 1
        items_out.append({"variant_id": item.get("variant_id", ""), "candidates": cands})

    total = len(items_out)
    out = {
        "machine_candidates_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "scripts/prefill_practice_review_anchors.py",
        "note": (
            "机器预填的来源锚候选, 仅供 owner 签发时参考。本文件绝不代表人工裁决: "
            "不写审核包、不填 decision 字段、不签名 (human_gate.machine_must_not_sign=true)。"
            "匹配方法=题干+正确项+model_answer 对 compiled_source 采分点与 exam_evidence 真题的"
            "汉字二元组重合度(0.7)+数值/术语命中率(0.3), 无 LLM。"
        ),
        "pack_id": pack,
        "packet_file": str(packet_path.relative_to(REPO_ROOT)) if packet_path.is_relative_to(REPO_ROOT) else str(packet_path),
        "score_threshold": threshold,
        "warnings": warnings,
        "coverage": {
            "total_items": total,
            "items_with_candidates": with_candidates,
            "items_empty_handed": total - with_candidates,
        },
        "items": items_out,
    }

    out_path = base_dir / PACKETS_SUBDIR / f"{pack.lower()}.anchor.candidates.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Paranoia check: the review packet must be byte-identical after the run.
    if packet_path.read_bytes() != packet_bytes_before:
        raise RuntimeError(f"[{pack}] 审核包被意外修改! {packet_path}")

    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("packs", nargs="+", help="pack id 列表, 如 N01 S05 X01")
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR, help="考点原料目录 (默认 repo 内)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help=f"候选最低分 (默认 {DEFAULT_THRESHOLD})")
    args = parser.parse_args(argv)

    failed = False
    for pack in args.packs:
        try:
            out = process_pack(args.base_dir, pack, args.threshold)
        except FileNotFoundError as exc:
            print(f"SKIP {pack}: {exc}", file=sys.stderr)
            failed = True
            continue
        cov = out["coverage"]
        print(
            f"{out['pack_id']}: {cov['items_with_candidates']}/{cov['total_items']} 题有候选 "
            f"(threshold={out['score_threshold']}), 空手 {cov['items_empty_handed']} 题"
            + ("".join(f"\n  WARN {w}" for w in out["warnings"]))
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
