#!/usr/bin/env python3
"""
Luban compiled-source quote fidelity auditor / gate.

For every scoring point (采分点) quote in each pack's _*_compiled_source.json,
locate the source chunk in the 2026 textbook FINAL_CLEANED_BOOK*.json (by
chunk_id, python lookup — NOT grep) and classify the quote as:

  VERBATIM   - whitespace-normalized quote is a substring of the source chunk's
               content_markdown (逐字命中)
  PARAPHRASED- source chunk located, but quote is not a verbatim substring
               (教学化改写 / 时序化 / 压缩句 病)
  ORPHAN     - chunk id not found in any book (定位不到源)

Usage:
  python scripts/audit_luban_compiled_source_quote_fidelity.py            # full audit
  python scripts/audit_luban_compiled_source_quote_fidelity.py --gate     # exit 1 if any PARAPHRASED
  python scripts/audit_luban_compiled_source_quote_fidelity.py --pack B02  # single pack
  python scripts/audit_luban_compiled_source_quote_fidelity.py --json out.json
"""
import json
import sys
import os
import re
import glob
import argparse

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(REPO, "docs", "原始数据", "考点原料")

# Book JSONs may be absent in an isolated worktree; fall back to the main workspace (read-only).
BOOK_DIR_CANDIDATES = [
    os.path.join(REPO, "docs", "原始数据", "2026_副本", "2026教材", "第二次加强"),
    "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/docs/原始数据/2026_副本/2026教材/第二次加强",
]
FALLBACK_DIR_CANDIDATES = [
    os.path.join(REPO, "docs", "原始数据", "2026_副本", "2026教材", "第一次清洗"),
    "/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/docs/原始数据/2026_副本/2026教材/第一次清洗",
]

_WS = re.compile(r"\s+")

# The actionable disease family (F05实锤 = "挂quote装verbatim + 时序化改写/重排/编造计数").
# A raw substring PARAPHRASED verdict is NOT the disease: most kc: mismatches are faithful
# compressed statements (symbolic notation) and most ca: mismatches are question stems
# (see 2026-07-20 calibration). The high-signal candidates are kc: quotes that render a
# textbook enumeration as an arrow-sequence or a fabricated count — a human must then judge
# whether the source is a genuine 工序/流程 (faithful) or a non-sequential enumeration (disease).
_ARROW = re.compile(r"[→➔➜⟶]|-&gt;|->")
_COUNT = re.compile(r"(共\s*[一二三四五六七八九十0-9]+\s*(项|类|条|个|种|步|方面)|[一二三四五六七八九十]+项(?![目])|分为[：:])")


def norm(s):
    """Remove ALL whitespace (incl. full-width space) for robust substring test."""
    if not s:
        return ""
    s = s.replace("　", "").replace(" ", "")
    return _WS.sub("", s)


def load_book_index():
    """Return dict: chunk_id -> content_markdown, indexing chunk_id/original_chunk_id/id."""
    index = {}
    dirs = [d for d in BOOK_DIR_CANDIDATES if os.path.isdir(d)][:1]
    fb = [d for d in FALLBACK_DIR_CANDIDATES if os.path.isdir(d)][:1]
    if not dirs:
        raise SystemExit("FATAL: no 第二次加强 book dir found in worktree or main workspace")
    for book_dir, tag in [(dirs[0], "v3_fixed"), (fb[0] if fb else None, "cleaned")]:
        if not book_dir:
            continue
        for fp in sorted(glob.glob(os.path.join(book_dir, "FINAL_CLEANED_BOOK*.json"))):
            with open(fp) as f:
                d = json.load(f)
            blocks = d.get("content_blocks", []) if isinstance(d, dict) else d
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                cm = b.get("content_markdown", "") or ""
                for key in ("chunk_id", "original_chunk_id", "id"):
                    cid = b.get(key)
                    if cid and cid not in index:
                        index[cid] = {"content": cm, "file": os.path.basename(fp), "tag": tag}
    return index


def audit(packs=None):
    index = load_book_index()
    results = []  # per scoring point
    files = sorted(glob.glob(os.path.join(SRC_DIR, "_*_compiled_source.json")))
    for fp in files:
        pack = os.path.basename(fp).replace("_compiled_source.json", "").lstrip("_")
        if packs and pack not in packs:
            continue
        with open(fp) as f:
            d = json.load(f)
        for u in d.get("units", []):
            for sp in u.get("scoring_points", []):
                chunk = sp.get("chunk")
                quote = sp.get("quote", "")
                pid = sp.get("point_id", "")
                qn = norm(quote)
                entry = index.get(chunk)
                if entry is None:
                    state = "ORPHAN"
                    detail = f"chunk '{chunk}' not in any book"
                elif not qn:
                    state = "ORPHAN"
                    detail = "empty quote"
                elif qn in norm(entry["content"]):
                    state = "VERBATIM"
                    detail = entry["file"]
                else:
                    state = "PARAPHRASED"
                    detail = entry["file"]
                family = None
                if state == "PARAPHRASED" and pid.startswith("kc:"):
                    if _ARROW.search(quote):
                        family = "ARROW"
                    elif _COUNT.search(quote):
                        family = "COUNT"
                results.append({
                    "pack": pack, "point_id": pid, "chunk": chunk,
                    "state": state, "detail": detail,
                    "quote": quote,
                    "has_repair_note": "repair_note" in sp,
                    "disease_family": family,
                })
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true", help="exit 1 if any PARAPHRASED")
    ap.add_argument("--pack", action="append", help="limit to pack code(s)")
    ap.add_argument("--json", dest="json_out", help="write full per-point results")
    ap.add_argument("--show", choices=["PARAPHRASED", "ORPHAN", "all"], default="PARAPHRASED")
    ap.add_argument("--disease-family", action="store_true",
                    help="list only the actionable kc: arrow/count disease-family candidates")
    args = ap.parse_args()

    results = audit(set(args.pack) if args.pack else None)

    # per-pack table
    packs = {}
    for r in results:
        p = packs.setdefault(r["pack"], {"VERBATIM": 0, "PARAPHRASED": 0, "ORPHAN": 0})
        p[r["state"]] += 1

    print("=== PER-PACK QUOTE FIDELITY ===")
    print(f"{'PACK':<6}{'VERBATIM':>9}{'PARAPHR':>9}{'ORPHAN':>8}{'TOTAL':>7}")
    tv = tp = to = 0
    for pk in sorted(packs):
        c = packs[pk]
        t = c["VERBATIM"] + c["PARAPHRASED"] + c["ORPHAN"]
        tv += c["VERBATIM"]; tp += c["PARAPHRASED"]; to += c["ORPHAN"]
        flag = "  <== PARA" if c["PARAPHRASED"] else ("  (orphan)" if c["ORPHAN"] else "")
        print(f"{pk:<6}{c['VERBATIM']:>9}{c['PARAPHRASED']:>9}{c['ORPHAN']:>8}{t:>7}{flag}")
    print(f"{'ALL':<6}{tv:>9}{tp:>9}{to:>8}{tv+tp+to:>7}")

    if args.disease_family:
        fam = [r for r in results if r["disease_family"]]
        print(f"\n=== DISEASE-FAMILY candidates (kc: arrow/count, need human textbook judgment): {len(fam)} ===")
        for r in fam:
            print(f"[{r['disease_family']:<5}] {r['pack']} {r['point_id']} rn={r['has_repair_note']}  {r['quote'][:90]}")

    if args.show in ("PARAPHRASED", "all"):
        print("\n=== PARAPHRASED points ===")
        for r in results:
            if r["state"] == "PARAPHRASED":
                print(f"[{r['pack']}] {r['point_id']} chunk={r['chunk']} rn={r['has_repair_note']}")
    if args.show in ("ORPHAN", "all"):
        print("\n=== ORPHAN points ===")
        for r in results:
            if r["state"] == "ORPHAN":
                print(f"[{r['pack']}] {r['point_id']} chunk={r['chunk']}: {r['detail']}")

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\nwrote {args.json_out}")

    if args.gate and tp > 0:
        print(f"\nGATE FAIL: {tp} PARAPHRASED quote(s)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
