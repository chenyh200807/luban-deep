"""案例题采分点教材 provenance 链补充脚本.

从 v_textbook_knowledge_full 中检索与每个采分点 required_terms 匹配的教材节点，
附加 textbook_source_refs，对完全覆盖的节点升级 answer_key_authority 为 textbook_verbatim，
最后重签 bundle。

运行:
    python scripts/enrich_rubric_textbook_provenance.py
    python scripts/enrich_rubric_textbook_provenance.py --dry-run   # 不写入，只打印统计
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RUBRIC_PATH = ROOT / "deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored/case_rubric_scored.json"
TEXTBOOK_PATH = ROOT / "deeptutor/services/construction_grading/runtime_supply/v_textbook_knowledge_full/textbook_knowledge_release_candidate.json"
POINTER_PATH = ROOT / "deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored/canonical_pointer.json"


def _sha256_hex(obj: Any) -> str:
    """Must match full_knowledge_compiler._sha256_hex exactly (separators + default=str)."""
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _extract_chinese_phrases(text: str, min_len: int = 4) -> list[str]:
    """Extract meaningful Chinese character sequences of at least min_len chars.
    Splits on punctuation and spaces, keeps fragments that are meaningful.
    """
    import re
    # Replace common separators with spaces
    text = re.sub(r"[：:；;，,。.、\s（()）【】「」\[\]《》]+", " ", text)
    fragments = []
    for chunk in text.split():
        chunk = chunk.strip()
        # Keep Chinese + alphanumeric fragments >= min_len
        if len(chunk) >= min_len:
            fragments.append(chunk)
        # Also consider substrings for longer fragments
        if len(chunk) > 8:
            for start in range(len(chunk) - min_len + 1):
                sub = chunk[start:start + min_len + 2]
                if len(sub) >= min_len:
                    fragments.append(sub)
    return list(dict.fromkeys(fragments))  # Deduplicate preserving order


def _build_text_index(textbook_records: list[dict]) -> dict[str, list[int]]:
    """Build inverted index: phrase -> [record_index_list].
    Indexes:
    1. required_terms (as-is)
    2. Chinese phrases from textbook_quote (min 4 chars)
    """
    index: dict[str, list[int]] = defaultdict(list)
    for idx, node in enumerate(textbook_records):
        for term in (node.get("required_terms") or []):
            t = str(term).strip()
            if t:
                index[t].append(idx)
        # Index key phrases from textbook_quote
        quote = str(node.get("textbook_quote") or "")
        if quote:
            for phrase in _extract_chinese_phrases(quote, min_len=4):
                index[phrase].append(idx)
    # Deduplicate
    return {k: list(dict.fromkeys(v)) for k, v in index.items()}


def _find_matches(rubric_text: str, rubric_terms: list[str],
                  textbook_records: list[dict],
                  text_index: dict[str, list[int]]) -> tuple[list[dict], bool]:
    """Find matching textbook nodes for a rubric point.

    Matching strategy (priority order):
    1. required_terms overlap with textbook required_terms
    2. rubric text phrases found in textbook_quote content
    3. rubric text fragments in textbook_quote

    Returns (matches_list, is_strong_match).
    strong = textbook_authority node where rubric content is substantially covered.
    """
    candidate_idx: set[int] = set()

    # Strategy 1: required_terms lookup
    for term in (rubric_terms or []):
        t = str(term).strip()
        if t and len(t) >= 2:  # Skip single chars
            for idx in text_index.get(t, []):
                candidate_idx.add(idx)

    # Strategy 2: rubric text key phrases
    for phrase in _extract_chinese_phrases(rubric_text, min_len=4):
        for idx in text_index.get(phrase, []):
            candidate_idx.add(idx)

    if not candidate_idx:
        return [], False

    matches: list[dict] = []
    strong = False
    rubric_lower = rubric_text.lower()

    for idx in candidate_idx:
        node = textbook_records[idx]
        node_terms = {t.strip() for t in (node.get("required_terms") or []) if str(t).strip()}
        quote = str(node.get("textbook_quote") or "")
        quote_lower = quote.lower()
        prov = node.get("provenance_class", "")

        # Compute overlap scores
        rubric_term_set = {t.strip() for t in (rubric_terms or []) if str(t).strip() and len(str(t).strip()) >= 2}
        term_overlap = rubric_term_set & node_terms

        # Count how many rubric phrases appear in the quote
        rubric_phrases = _extract_chinese_phrases(rubric_text, min_len=4)
        phrases_in_quote = [p for p in rubric_phrases if p in quote]

        if not term_overlap and not phrases_in_quote:
            continue

        # Strong: textbook_authority + substantial content overlap
        # phrase must be >=6 PURE Chinese chars (filter symbols/numbers)
        import re as _re
        long_phrase_matches = [
            p for p in phrases_in_quote
            if len(p) >= 6 and _re.match(r'^[一-鿿㐀-䶿]+$', p)
        ]
        has_phrase_match = len(long_phrase_matches) >= 1
        has_full_term_coverage = (
            bool(rubric_term_set) and
            len(rubric_term_set) >= 2 and
            all(t in node_terms or t in quote for t in rubric_term_set)
        )
        is_node_strong = (
            prov == "textbook_authority" and
            (has_phrase_match or has_full_term_coverage)
        )

        matches.append({
            "chunk_id": node.get("chunk_id"),
            "node_code": node.get("node_code"),
            "provenance_class": prov,
            "match_terms": sorted(term_overlap),
            "phrase_matches": phrases_in_quote[:3],
            "strong": is_node_strong,
            "quote_snippet": quote[:150],
        })
        if is_node_strong:
            strong = True

    # Deduplicate by chunk_id
    seen: set = set()
    deduped: list[dict] = []
    for m in matches:
        key = m.get("chunk_id") or m.get("node_code") or str(m)
        if key not in seen:
            seen.add(key)
            deduped.append(m)

    # Sort: strong textbook_authority first
    deduped.sort(key=lambda x: (
        -(1 if x["provenance_class"] == "textbook_authority" else 0),
        -(1 if x["strong"] else 0),
        -len(x["phrase_matches"]),
        -len(x["match_terms"]),
    ))

    return deduped[:5], strong  # Cap at 5 refs per point


def enrich(dry_run: bool = False) -> None:
    # Load bundles
    with open(RUBRIC_PATH) as f:
        rubric_bundle = json.load(f)
    with open(TEXTBOOK_PATH) as f:
        textbook_bundle = json.load(f)

    # C-3: entry guard — refuse to enrich a published or non-candidate bundle.
    # Enriching a published bundle would silently re-open it under a new hash,
    # bypassing the reverse-gate check in compiled_registry_resolver.
    old_manifest_check = rubric_bundle.get("manifest") or {}
    if old_manifest_check.get("status") not in ("release_candidate", "released"):
        print(
            f"ERROR: unexpected bundle status={old_manifest_check.get('status')!r}. "
            "Expected 'release_candidate' or 'released'. Aborting.",
            file=sys.stderr,
        )
        sys.exit(1)
    if old_manifest_check.get("published") is True:
        print(
            "ERROR: bundle is published=True. Cannot safely enrich a live-published bundle. "
            "Unpublish it first (set published=False in the manifest and pointer).",
            file=sys.stderr,
        )
        sys.exit(1)

    rubric_records: list[dict] = rubric_bundle["records"]
    textbook_records: list[dict] = textbook_bundle["records"]

    print(f"Rubric records: {len(rubric_records)}")
    print(f"Textbook records: {len(textbook_records)}")

    text_index = _build_text_index(textbook_records)
    print(f"Text index size: {len(text_index)} phrases/terms")

    enriched: list[dict] = []
    stats = {
        "total": 0,
        "has_text": 0,
        "matched": 0,
        "strong_upgraded": 0,
        "no_match": 0,
    }

    for rec in rubric_records:
        stats["total"] += 1
        rubric_terms = rec.get("required_terms") or []
        rubric_text = rec.get("text") or ""

        if rubric_text:
            stats["has_text"] += 1

        matches, is_strong = _find_matches(rubric_text, rubric_terms, textbook_records, text_index)

        new_rec = dict(rec)
        if matches:
            stats["matched"] += 1
            new_rec["textbook_source_refs"] = matches
            # calc policy derives numbers from textbook rules — upgrade would overclaim verbatim
            can_upgrade = rec.get("policy") not in ("calc",)
            if is_strong and can_upgrade and rec.get("answer_key_authority") == "exam_reference_answer":
                new_rec["answer_key_authority"] = "textbook_verbatim"
                stats["strong_upgraded"] += 1
        else:
            stats["no_match"] += 1

        enriched.append(new_rec)

    # Recompute manifest
    old_manifest = rubric_bundle["manifest"]
    content_hash = _sha256_hex(enriched)
    namespace = old_manifest["namespace"]
    status = old_manifest["status"]

    auth_dist: dict[str, int] = defaultdict(int)
    for r in enriched:
        auth_dist[r["answer_key_authority"]] += 1

    new_manifest = {
        **old_manifest,
        "content_hash": content_hash,
        "signature": _sha256_hex([content_hash, namespace, status]),
        "scoring_point_count": len(enriched),
        "question_count": len({r["qid"] for r in enriched}),
        "authority_distribution": dict(auth_dist),
        "provenance_enriched": True,
        "provenance_enrich_date": datetime.date.today().isoformat(),
        # C-1: explicitly reset published=False after enrichment re-signs the bundle.
        # The compiled_registry_resolver reverse-gate rejects published=True bundles,
        # so any new hash must not carry the old published flag forward.
        "published": False,
    }

    new_bundle = {
        "manifest": new_manifest,
        "records": enriched,
        "rejected": rubric_bundle.get("rejected", []),
    }

    print(f"\nProvenance enrichment stats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"\nAuthority distribution after enrichment:")
    for k, v in sorted(auth_dist.items()):
        print(f"  {k}: {v}")

    pct_strong = stats["strong_upgraded"] / stats["total"] * 100 if stats["total"] else 0
    pct_matched = stats["matched"] / stats["total"] * 100 if stats["total"] else 0
    print(f"\nCoverage: {pct_matched:.1f}% matched, {pct_strong:.1f}% upgraded to textbook_verbatim")

    if dry_run:
        print("\n[dry-run] Not writing files.")
        return

    with open(RUBRIC_PATH, "w", encoding="utf-8") as f:
        json.dump(new_bundle, f, ensure_ascii=False, indent=2)
    print(f"\nWrote enriched bundle: {RUBRIC_PATH}")

    # Update canonical_pointer.json
    if POINTER_PATH.exists():
        with open(POINTER_PATH) as f:
            pointer = json.load(f)
        pointer["content_hash"] = content_hash
        # C-2: sync expected_content_hash to the newly-signed bundle hash so that
        # compiled_registry_resolver integrity check passes after enrichment.
        pointer["expected_content_hash"] = content_hash
        pointer["provenance_enriched"] = True
        # C-2: keep pointer published=False to match the bundle manifest.
        pointer["published"] = False
        with open(POINTER_PATH, "w", encoding="utf-8") as f:
            json.dump(pointer, f, ensure_ascii=False, indent=2)
        print(f"Updated pointer: {POINTER_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich case rubric with textbook provenance")
    parser.add_argument("--dry-run", action="store_true", help="Print stats only, do not write")
    args = parser.parse_args()
    enrich(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
