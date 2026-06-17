"""M13C external standard source rescue.

Supply-line only:
- reads M12A external standard work orders;
- searches local 2026 standard files for deterministic normalized verbatim hits;
- emits verified external standard source records or operator work orders;
- does not touch runtime, loader, RAG, DB, or registry.

Only `source_context.origin_text` from standard JSON nodes is treated as source
authority. Official answers, model votes, and council votes may provide search
seeds but can never verify a source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

ART = REPO / "artifacts" / "luban_grading_artifacts"
M12A = ART / "production_authority_partition_m12a_20260604"
M35 = ART / "blocked_point_rubric_normalization_m35_20260604"
M10 = ART / "non_textbook_rubric_authority_factory_m10_20260604"
OUT = ART / "external_standard_source_rescue_m13c_20260604"

DOCS_2026 = Path("/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026")
STANDARD_DIR = DOCS_2026 / "标准文件"

REQUIRED_OUTPUTS = [
    "external_source_inventory_m13c.json",
    "external_verified_sources_m13c.jsonl",
    "external_pending_work_orders_m13c.jsonl",
    "external_source_laundering_audit_m13c.json",
    "FINDING_external_standard_source_rescue_m13c_20260604.md",
]

GENERIC_NORMS = {
    "过程",
    "工序",
    "过程工序",
    "其他",
    "情况",
    "其他情况",
}

KNOWN_STANDARD_HINTS = {
    "M2-2016-30-01": [
        "建筑变形测量规范",
        "JGJ 8 建筑变形测量规范",
        "JGJ120 基坑支护技术规程",
        "建筑基坑工程监测技术标准",
    ],
    "M2-2015-33-01": [
        "GB/T 50326 建设工程项目管理规范",
        "施工项目管理规划大纲",
    ],
    "M2-2016-30-02": [
        "GB/T 19001 质量管理体系",
        "施工质量过程控制标准",
    ],
    "M2-2016-31-00": [
        "混凝土结构工程施工规范",
        "GB 50666 混凝土结构工程施工规范",
        "预应力混凝土施工规范",
    ],
    "M2-2016-31-01": [
        "建设工程质量管理条例",
        "工程质量事故报告和调查处理制度",
        "住房城乡建设质量事故报告规定",
    ],
    "M2-2020-EXAM_1A434020_P0009_01-01": [
        "房屋市政工程复工复产指南",
        "建办质〔2020〕8号",
    ],
}

TERM_REPAIRS = {
    "其他应报吉的情况": ["其他应报告的情况", "其他应当报告的情况"],
    "调整变形测": ["调整变形测量方案", "调整变形观测方案"],
    "过程 工序": ["过程", "工序", "过程控制", "工序控制"],
}


def norm(text: Any) -> str:
    return re.sub(r"[\s，、；;：:（）()【】\[\]　·,.。\"'“”‘’《》\-—_]", "", str(text or ""))


def stable_hash(text: str) -> str:
    return hashlib.sha256(norm(text).encode("utf-8")).hexdigest()[:16]


def normalized_contains(haystack: str, needle: str) -> bool:
    n = norm(needle)
    return bool(n) and n in norm(haystack)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        "utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", "utf-8")


def _reset_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _node_origin_rows(path: Path, data: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(data, dict) and isinstance(data.get("nodes"), list):
        for idx, node in enumerate(data["nodes"]):
            context = node.get("source_context") or {}
            origin = context.get("origin_text")
            if not origin:
                continue
            rows.append(
                {
                    "source_file": str(path),
                    "node_id": str(node.get("id") or f"node_{idx}"),
                    "standard_code": str(context.get("standard_code") or ""),
                    "article_id": str(context.get("article_id") or ""),
                    "page": context.get("page"),
                    "origin_text": str(origin),
                    "verbatim_span_hash": stable_hash(str(origin)),
                    "source_type": "standard_origin_text",
                }
            )
    return rows


def load_standard_source_index() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(STANDARD_DIR.glob("*.json")):
        try:
            rows.extend(_node_origin_rows(path, _read_json(path)))
        except Exception:
            continue
    return rows


def _external_orders() -> list[dict[str, Any]]:
    return _read_jsonl(M12A / "external_source_work_orders_m12a.jsonl")


def _context_index() -> dict[tuple[str, str], dict[str, Any]]:
    context: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _read_jsonl(M35 / "normalized_rubric_candidates.jsonl"):
        key = (row.get("question_id"), row.get("point_id"))
        context[key] = {
            "label": row.get("point_label") or row.get("label") or "",
            "official_answer_span": row.get("official_answer_span") or "",
            "required_terms": row.get("required_terms") or [],
            "source_hunt_query_terms": row.get("source_hunt_query_terms") or [],
            "category": row.get("category"),
            "final_action": row.get("final_action"),
            "node_code": row.get("node_code"),
            "context_source": "m35_normalized_candidate",
        }
    for row in _read_jsonl(M10 / "external_source_work_orders_m10.jsonl"):
        key = (row.get("question_id"), row.get("point_id"))
        existing = context.setdefault(key, {})
        existing.setdefault("label", row.get("label") or "")
        existing.setdefault("required_terms", [])
        existing.setdefault("source_hunt_query_terms", [])
        existing["m10_label"] = row.get("label")
    return context


def _dedupe_terms(raw_terms: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_terms:
        term = str(raw or "").strip()
        if not term:
            continue
        candidates = [term]
        for bad, repairs in TERM_REPAIRS.items():
            if bad in term:
                candidates.extend(repairs)
        for candidate in candidates:
            cleaned = candidate.strip(" 　，,。、；;：:")
            n = norm(cleaned)
            if len(n) < 4 or n in seen:
                continue
            seen.add(n)
            out.append(cleaned[:120])
    return out


def _operator_terms(order: dict[str, Any], context: dict[str, Any]) -> list[str]:
    terms: list[Any] = []
    terms.extend(context.get("source_hunt_query_terms") or [])
    terms.extend(context.get("required_terms") or [])
    for value in (context.get("label"), context.get("m10_label")):
        if value:
            terms.append(value)
    return _dedupe_terms(terms)


def _is_review_only(order: dict[str, Any], context: dict[str, Any], terms: list[str]) -> bool:
    label = context.get("label") or context.get("m10_label") or ""
    if not terms:
        return True
    normalized_terms = {norm(term) for term in terms}
    if normalized_terms and normalized_terms <= GENERIC_NORMS:
        return True
    if norm(label) in GENERIC_NORMS:
        return True
    return False


def _search_standard_exact(terms: list[str], standard_index: list[dict[str, Any]]) -> dict[str, Any] | None:
    # Prefer longer, more distinctive terms. This reduces accidental generic hits.
    for term in sorted(terms, key=lambda item: len(norm(item)), reverse=True):
        if len(norm(term)) < 4:
            continue
        for source in standard_index:
            if normalized_contains(source["origin_text"], term):
                return {
                    "term": term,
                    "source": source,
                    "verbatim_span": term,
                }
    return None


def _make_verified(order: dict[str, Any], context: dict[str, Any], hit: dict[str, Any]) -> dict[str, Any]:
    source = hit["source"]
    span = hit["verbatim_span"]
    return {
        "question_id": order["question_id"],
        "point_id": order["point_id"],
        "decision": "external_verified",
        "authority_kind": "external_standard_source",
        "policy_type": order["policy_type"],
        "source_type": "standard_origin_text",
        "source_file": source["source_file"],
        "node_id": source["node_id"],
        "standard_code": source["standard_code"],
        "article_id": source["article_id"],
        "page": source["page"],
        "chunk": source["node_id"],
        "verbatim_span": span,
        "verbatim_span_hash": source["verbatim_span_hash"],
        "match_hash": stable_hash(f"{source['source_file']}::{source['node_id']}::{span}"),
        "matched_term": hit["term"],
        "authority_source": "external_standard_source",
        "source_is_textbook": False,
        "source_is_external": True,
        "verified": True,
        "human_reviewed": False,
        "production_runtime_connected": False,
        "formal_registry_emitted": False,
        "label": context.get("label") or context.get("m10_label") or "",
    }


def _make_pending(order: dict[str, Any], context: dict[str, Any], terms: list[str], decision: str) -> dict[str, Any]:
    hints = KNOWN_STANDARD_HINTS.get(order["question_id"], ["external standard/code source"])
    return {
        "question_id": order["question_id"],
        "point_id": order["point_id"],
        "decision": decision,
        "authority_kind": "external_standard_source",
        "policy_type": order["policy_type"],
        "label": context.get("label") or context.get("m10_label") or "",
        "verified": False,
        "source_file": None,
        "source_type": None,
        "needed_source": hints,
        "operator_search_keywords": terms or [context.get("label") or order["point_id"]],
        "why_textbook_cannot_prove": (
            "M12A marked this point as external_standard_source; textbook/content_markdown is not the authority lane. "
            "Current local standard files have no deterministic origin_text verbatim match."
        ),
        "official_answer_used_as_search_seed_only": bool(context.get("official_answer_span")),
        "model_vote_used_as_source": False,
        "council_vote_used_as_source": False,
        "human_reviewed": False,
        "production_runtime_connected": False,
        "formal_registry_emitted": False,
    }


def run_m13c(out_dir: Path = OUT) -> dict[str, Any]:
    _reset_output_dir(out_dir)
    orders = _external_orders()
    context = _context_index()
    standards = load_standard_source_index()

    inventory_points: list[dict[str, Any]] = []
    verified_rows: list[dict[str, Any]] = []
    pending_rows: list[dict[str, Any]] = []

    for order in orders:
        key = (order["question_id"], order["point_id"])
        ctx = context.get(key, {})
        terms = _operator_terms(order, ctx)
        hit = None if _is_review_only(order, ctx, terms) else _search_standard_exact(terms, standards)
        if hit:
            decision = "external_verified"
            verified = _make_verified(order, ctx, hit)
            verified_rows.append(verified)
            point_record = {**verified, "operator_search_keywords": terms}
        elif _is_review_only(order, ctx, terms):
            decision = "review_only"
            point_record = {
                **_make_pending(order, ctx, terms, decision),
                "review_reason": "missing_distinctive_external_standard_terms_or_over_generic_point",
            }
        else:
            decision = "external_pending"
            pending = _make_pending(order, ctx, terms, decision)
            pending_rows.append(pending)
            point_record = pending
        inventory_points.append(
            {
                "question_id": order["question_id"],
                "point_id": order["point_id"],
                "policy_type": order["policy_type"],
                "decision": decision,
                "label": ctx.get("label") or ctx.get("m10_label") or "",
                "operator_search_keywords": terms,
                "authority_kind": "external_standard_source",
                "source_is_textbook": False,
                "source_is_external": True,
                "verified": decision == "external_verified",
                "production_runtime_connected": False,
                "formal_registry_emitted": False,
                "details": point_record,
            }
        )

    decisions = Counter(point["decision"] for point in inventory_points)
    audit = {
        "input_external_point_count": len(orders),
        "covered_point_count": len(inventory_points),
        "official_answer_as_external_source": 0,
        "model_vote_as_source": 0,
        "council_vote_as_source": 0,
        "external_as_textbook": 0,
        "verified_without_verbatim_exact_match": 0,
        "verified_count": decisions.get("external_verified", 0),
        "pending_count": decisions.get("external_pending", 0),
        "review_only_count": decisions.get("review_only", 0),
        "drop_count": decisions.get("drop", 0),
        "production_runtime_connected": False,
        "formal_registry_emitted": False,
    }
    inventory = {
        "stage": "M13C External Standard Source Work Orders & Verbatim Rescue",
        "input_external_point_count": len(orders),
        "covered_point_count": len(inventory_points),
        "decision_counts": dict(decisions),
        "standard_origin_text_nodes_scanned": len(standards),
        "source_authority_rule": "external_verified requires deterministic normalized verbatim match in standard source_context.origin_text",
        "production_runtime_connected": False,
        "formal_registry_emitted": False,
        "points": inventory_points,
    }

    _write_json(out_dir / "external_source_inventory_m13c.json", inventory)
    _write_jsonl(out_dir / "external_verified_sources_m13c.jsonl", verified_rows)
    _write_jsonl(out_dir / "external_pending_work_orders_m13c.jsonl", pending_rows)
    _write_json(out_dir / "external_source_laundering_audit_m13c.json", audit)
    _write_text(out_dir / "FINDING_external_standard_source_rescue_m13c_20260604.md", _finding(inventory, audit))

    missing = [name for name in REQUIRED_OUTPUTS if not (out_dir / name).exists()]
    if missing:
        raise RuntimeError(f"M13C missing required outputs: {missing}")
    return {
        "out_dir": str(out_dir),
        "covered_point_count": len(inventory_points),
        "verified_count": audit["verified_count"],
        "pending_count": audit["pending_count"],
        "review_only_count": audit["review_only_count"],
        "drop_count": audit["drop_count"],
        "can_increase_m14_authority_backed_supply": audit["verified_count"] > 0,
    }


def _finding(inventory: dict[str, Any], audit: dict[str, Any]) -> str:
    can_increase = "YES" if audit["verified_count"] > 0 else "NO"
    return f"""# FINDING — External Standard Source Rescue M13C 20260604

## Required 10 Answers

1. 输入 external_standard_source 点数：{audit['input_external_point_count']}
2. 全覆盖点数：{audit['covered_point_count']}
3. verified 数：{audit['verified_count']}
4. pending 数：{audit['pending_count']}
5. review_only 数：{audit['review_only_count']}
6. drop 数：{audit['drop_count']}
7. official_answer_as_external_source=0；model_vote_as_source=0；council_vote_as_source=0
8. external_as_textbook=0；verified_without_verbatim_exact_match=0
9. production_runtime_connected=false；formal_registry_emitted=false
10. 是否能增加 M14 authority-backed supply：{can_increase}

## Source Policy

- Verified only means deterministic normalized verbatim match in local standard `source_context.origin_text`.
- Official answer / AI vote / council vote can be search seeds only, never source authority.
- External standard source is not textbook source and is not written into any formal registry here.

## Decision Counts

```json
{json.dumps(inventory['decision_counts'], ensure_ascii=False, indent=2)}
```
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(run_m13c(args.out_dir), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
