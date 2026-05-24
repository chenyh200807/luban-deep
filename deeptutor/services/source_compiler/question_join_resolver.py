from __future__ import annotations

from collections import defaultdict
from typing import Iterable


def _index(rows: Iterable[dict], key: str) -> dict[object, list[dict]]:
    indexed: dict[object, list[dict]] = defaultdict(list)
    for row in rows:
        value = row.get(key)
        if value not in (None, ""):
            indexed[value].append(row)
    return indexed


def resolve_question_capsule_joins(capsules: list[dict], bank_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    by_original = _index(bank_rows, "original_id")
    by_chunk = _index(bank_rows, "source_chunk_id")
    by_semantic = defaultdict(list)
    by_stem_hash = defaultdict(list)
    for row in bank_rows:
        if row.get("semantic_signature") and row.get("node_code"):
            by_semantic[(row.get("semantic_signature"), row.get("node_code"))].append(row)
        if row.get("stem_hash") and row.get("node_code"):
            by_stem_hash[(row.get("stem_hash"), row.get("node_code"))].append(row)

    matched: list[dict] = []
    unmatched: list[dict] = []
    for capsule in capsules:
        candidates: list[dict] = []
        reason = "no_match"
        for candidate_set, match_reason in (
            (by_original.get(capsule.get("original_id"), []), "original_id"),
            (by_chunk.get(capsule.get("source_chunk_id"), []), "source_chunk_id"),
            (by_semantic.get((capsule.get("semantic_signature"), capsule.get("node_code")), []), "semantic_signature_node"),
            (by_stem_hash.get((capsule.get("stem_hash"), capsule.get("node_code")), []), "stem_hash_node"),
        ):
            if candidate_set:
                candidates = candidate_set
                reason = match_reason
                break
        if len(candidates) == 1:
            row = dict(capsule)
            row["candidate_questions_bank_id"] = int(candidates[0]["id"])
            row["match_reason"] = reason
            matched.append(row)
        elif len(candidates) > 1:
            unmatched.append(
                {
                    "stable_question_source_id": capsule.get("stable_question_source_id"),
                    "reason": "ambiguous_match",
                    "candidate_ids": [candidate.get("id") for candidate in candidates],
                }
            )
        else:
            unmatched.append(
                {
                    "stable_question_source_id": capsule.get("stable_question_source_id"),
                    "reason": "no_match",
                }
            )
    return matched, unmatched

