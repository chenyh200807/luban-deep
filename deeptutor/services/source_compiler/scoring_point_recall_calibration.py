from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from deeptutor.services.source_compiler.scoring_point_asset_compiler import normalize_for_match
from deeptutor.services.source_compiler.schema import content_hash, stable_hash


STOP_TOKENS = {
    "规定",
    "要求",
    "内容",
    "措施",
    "标准",
    "包括",
    "正确做法",
    "不妥之处",
    "必须写出",
    "规范术语原文",
    "近义不算",
    "估计",
    "注",
    "应",
    "不应",
    "不得",
    "不妥",
    "正确",
    "做法",
    "情况",
    "答案",
    "应计入",
    "不计入",
}

GENERIC_TERMS = {
    "施工",
    "设计",
    "监理",
    "建设",
    "单位",
    "工程",
    "项目",
    "质量",
    "安全",
    "材料",
    "管理",
    "控制",
    "检测",
    "记录",
    "费用",
    "计划",
    "合同",
    "时间",
    "工期",
    "问题",
    "环境",
    "勘察",
    "防护",
    "限制",
    "浇筑",
    "方案",
    "文件",
    "资料",
    "人员",
    "设备",
    "方法",
    "错误",
    "测量",
    "检验",
    "资金",
    "分层",
}


@dataclass(frozen=True)
class NodeAlignment:
    question_node: str
    status: str
    asset_nodes: list[str]


def _clean_term(value: str) -> str:
    text = re.sub(r"\s+", "", value or "")
    text = text.strip(" ,，.。;；:：、【】[]《》<>“”\"'‘’")
    text = text.replace("开、竣工", "开竣工")
    text = text.replace("日期__AND__工期", "日期及工期")
    if text.count("(") > text.count(")") and text.endswith("(图"):
        text += ")"
    return text


def _is_distinctive(value: str) -> bool:
    normalized = normalize_for_match(value)
    if len(normalized) < 2:
        return False
    if value in STOP_TOKENS or normalized in {normalize_for_match(item) for item in STOP_TOKENS}:
        return False
    if len(normalized) <= 3 and normalized in {normalize_for_match(item) for item in GENERIC_TERMS}:
        return False
    if normalized.isdigit():
        return False
    return True


def _split_list_like(text: str) -> list[str]:
    candidates: list[str] = []
    for part in re.split(r"[;；。]\s*", text or ""):
        part = part.replace("开、竣工", "开竣工")
        part = part.replace("日期及工期", "日期__AND__工期")
        part = re.sub(r"^[（(]?\d+[）).、]\s*", "", part)
        part = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*", "", part)
        pieces = re.split(r"[、,/，]|(?:和)|(?:及)|(?:与)", part)
        candidates.extend(_clean_term(piece) for piece in pieces)
    return [item for item in candidates if item]


def _quoted_terms(text: str) -> list[str]:
    terms: list[str] = []
    for pattern in (r"'([^']{2,80})'", r"‘([^’]{2,80})’", r"“([^”]{2,80})”", r"\"([^\"]{2,80})\""):
        terms.extend(_clean_term(match) for match in re.findall(pattern, text or ""))
    return terms


def _explicit_list_terms(text: str) -> list[str]:
    terms: list[str] = []
    for pattern in (
        r"包括[:：]?([^。；;]+)",
        r"还有[:：]?([^。；;]+)",
        r"还包括[:：]?([^。；;]+)",
        r"应得分项为\d*项[:：]?([^。；;]+)",
        r"共\d+项规范术语[（(][^）)]*[）)]?[:：]?([^。；;]+)",
    ):
        for match in re.findall(pattern, text or ""):
            terms.extend(_split_list_like(match))
    return terms


def _required_terms_from_existing_gold(point: dict[str, Any]) -> list[str]:
    values = point.get("required_terms_v1_5")
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        term = _clean_term(str(value))
        if term and _is_distinctive(term):
            result.append(term)
    return result


def extract_gold_terms(point: dict[str, Any]) -> list[str]:
    if str(point.get("point_type") or "") == "calculation":
        raw_terms = point.get("calculation_expected_terms_v1_5")
        if isinstance(raw_terms, list) and raw_terms:
            return _dedupe([_clean_term(str(term)) for term in raw_terms if _is_distinctive(_clean_term(str(term)))])

    compiled_terms = _required_terms_from_existing_gold(point)
    if compiled_terms:
        return _dedupe(compiled_terms)

    text = " ".join(str(point.get(key) or "") for key in ("label", "official_basis"))
    candidates: list[str] = []
    candidates.extend(_quoted_terms(text))
    candidates.extend(_explicit_list_terms(text))
    if not candidates:
        candidates.extend(_split_list_like(text))
    return _dedupe([term for term in candidates if _is_distinctive(term)])


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = normalize_for_match(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def build_parent_child_index(chunks: list[dict[str, Any]]) -> dict[str, list[str]]:
    children: dict[str, set[str]] = defaultdict(set)
    for chunk in chunks:
        taxonomy = chunk.get("taxonomy") if isinstance(chunk.get("taxonomy"), dict) else {}
        node = str(taxonomy.get("node_code") or "").strip()
        parent = str(taxonomy.get("parent_code") or "").strip()
        if node and parent:
            children[parent].add(node)

    def descendants(parent: str) -> set[str]:
        direct = set(children.get(parent) or set())
        expanded = set(direct)
        for child in direct:
            expanded.update(descendants(child))
        return expanded

    return {parent: sorted(descendants(parent)) for parent in children}


def align_question_node(question_node: str | None, *, asset_nodes: set[str], parent_child: dict[str, list[str]]) -> NodeAlignment:
    node = str(question_node or "").strip()
    if not node or node.upper() == "NA":
        return NodeAlignment(question_node=node or "NA", status="coverage_gap_na", asset_nodes=[])
    if node in asset_nodes:
        return NodeAlignment(question_node=node, status="exact", asset_nodes=[node])
    expanded = [child for child in parent_child.get(node, []) if child in asset_nodes]
    if expanded:
        return NodeAlignment(question_node=node, status="expanded_parent", asset_nodes=expanded)
    if node in parent_child:
        return NodeAlignment(question_node=node, status="coverage_gap_parent_without_assets", asset_nodes=[])
    return NodeAlignment(question_node=node, status="coverage_gap_missing_node", asset_nodes=[])


def _parents_for_node(node: str, parent_child: dict[str, list[str]]) -> list[str]:
    return sorted(parent for parent, children in parent_child.items() if node in children)


def _closest_parent(node: str, parent_child: dict[str, list[str]]) -> str | None:
    parents = _parents_for_node(node, parent_child)
    if parents:
        return min(parents, key=lambda parent: len(parent_child.get(parent, [])))
    if len(node) >= 3:
        inferred = f"{node[:-3]}000"
        if inferred in parent_child:
            return inferred
    return None


def expanded_node_scope(question_node: str | None, *, asset_nodes: set[str], parent_child: dict[str, list[str]]) -> NodeAlignment:
    node = str(question_node or "").strip()
    if not node or node.upper() == "NA":
        return NodeAlignment(question_node=node or "NA", status="coverage_gap_na", asset_nodes=[])

    if node in parent_child:
        expanded = [child for child in parent_child.get(node, []) if child in asset_nodes]
        if expanded:
            return NodeAlignment(question_node=node, status="expanded_parent", asset_nodes=expanded)
        return NodeAlignment(question_node=node, status="coverage_gap_parent_without_assets", asset_nodes=[])

    parent = _closest_parent(node, parent_child)
    if parent:
        expanded = [child for child in parent_child.get(parent, []) if child in asset_nodes]
        if expanded:
            status = "expanded_sibling_scope" if node in asset_nodes else "expanded_inferred_parent_scope"
            return NodeAlignment(question_node=node, status=status, asset_nodes=expanded)

    if node in asset_nodes:
        return NodeAlignment(question_node=node, status="exact", asset_nodes=[node])
    return NodeAlignment(question_node=node, status="coverage_gap_missing_node", asset_nodes=[])


def build_kb_term_index(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index: list[dict[str, Any]] = []
    for chunk in chunks:
        content = str(chunk.get("content_markdown") or "")
        if not content:
            continue
        taxonomy = chunk.get("taxonomy") if isinstance(chunk.get("taxonomy"), dict) else {}
        source_meta = chunk.get("source_meta") if isinstance(chunk.get("source_meta"), dict) else {}
        index.append(
            {
                "chunk_id": chunk.get("chunk_id") or chunk.get("id") or "",
                "node_code": taxonomy.get("node_code") or "",
                "page_num": source_meta.get("page_num") or chunk.get("page_num"),
                "content": content,
                "normalized_content": normalize_for_match(content),
            }
        )
    return index


def _kb_matches(term: str, kb_index: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    normalized = normalize_for_match(term)
    if not normalized:
        return []
    matches: list[dict[str, Any]] = []
    for chunk in kb_index:
        if normalized not in str(chunk.get("normalized_content") or ""):
            continue
        content = str(chunk.get("content") or "")
        plain_index = content.find(term)
        if plain_index < 0:
            plain_index = 0
        start = max(0, plain_index - 40)
        end = min(len(content), plain_index + len(term) + 40)
        matches.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "node_code": chunk.get("node_code"),
                "page_num": chunk.get("page_num"),
                "quote": content[start:end],
            }
        )
        if len(matches) >= limit:
            break
    return matches


def _chunk_id(chunk: dict[str, Any]) -> str:
    return str(chunk.get("chunk_id") or chunk.get("id") or "")


def _chunk_node_code(chunk: dict[str, Any]) -> str:
    taxonomy = chunk.get("taxonomy") if isinstance(chunk.get("taxonomy"), dict) else {}
    return str(taxonomy.get("node_code") or chunk.get("node_code") or "")


def _chunk_page_num(chunk: dict[str, Any]) -> Any:
    source_meta = chunk.get("source_meta") if isinstance(chunk.get("source_meta"), dict) else {}
    return source_meta.get("page_num") or chunk.get("page_num")


def _textbook_clause_for_term(term: str, content: str, candidate_quote: str | None = None) -> str | None:
    normalized_term = normalize_for_match(term)
    source = candidate_quote if candidate_quote and candidate_quote in content and normalized_term in normalize_for_match(candidate_quote) else content
    if not normalized_term or normalized_term not in normalize_for_match(source):
        return None

    exact_index = source.find(term)
    if exact_index < 0:
        normalized_source = ""
        normalized_to_original: list[int] = []
        for index, char in enumerate(source):
            normalized_char = normalize_for_match(char)
            if not normalized_char:
                continue
            normalized_source += normalized_char
            normalized_to_original.extend([index] * len(normalized_char))
        normalized_index = normalized_source.find(normalized_term)
        if normalized_index < 0 or normalized_index >= len(normalized_to_original):
            return source.strip()
        exact_index = normalized_to_original[normalized_index]
        original_end_index = normalized_to_original[min(len(normalized_to_original) - 1, normalized_index + len(normalized_term) - 1)] + 1
    else:
        original_end_index = exact_index + len(term)

    left = exact_index
    while left > 0 and source[left - 1] not in "\n。；;":
        left -= 1
    right = original_end_index
    while right < len(source) and source[right] not in "\n。；;":
        right += 1
    clause = source[left:right].strip(" \n\t。；;")
    return clause or source.strip()


def _is_loose_single_anchor(term: str) -> bool:
    normalized = normalize_for_match(term)
    return len(normalized) <= 3 and normalized in {normalize_for_match(item) for item in GENERIC_TERMS | STOP_TOKENS}


def build_backfill_assets(candidates: list[dict[str, Any]], chunks: list[dict[str, Any]], *, run_id: str = "scoring-point-backfill-20260602") -> list[dict[str, Any]]:
    chunks_by_id = {_chunk_id(chunk): chunk for chunk in chunks if _chunk_id(chunk)}
    assets: list[dict[str, Any]] = []
    for candidate in candidates:
        chunk = chunks_by_id.get(str(candidate.get("candidate_chunk_id") or ""))
        if not chunk:
            continue
        content = str(chunk.get("content_markdown") or "")
        term = str(candidate.get("gold_term") or "")
        required_term = _textbook_clause_for_term(term, content, str(candidate.get("candidate_quote") or ""))
        if not required_term:
            continue
        if normalize_for_match(required_term) not in normalize_for_match(content):
            continue
        if _is_loose_single_anchor(required_term):
            continue

        backfill_source = f"golden_driven_{candidate.get('case_id')}_{candidate.get('gold_point_id')}"
        point_seed = "|".join([run_id, _chunk_id(chunk), str(candidate.get("case_id") or ""), str(candidate.get("gold_point_id") or ""), normalize_for_match(required_term)])
        assets.append(
            {
                "schema_version": "luban_scoring_point_assets_backfill.v0.1",
                "version_id": run_id,
                "node_code": _chunk_node_code(chunk),
                "chunk_id": _chunk_id(chunk),
                "page_num": _chunk_page_num(chunk),
                "point_id": stable_hash(point_seed, prefix="bf_", length=20),
                "point_type": "text_term",
                "anchor_source": "textbook_backfill",
                "required_terms": [required_term],
                "label": required_term,
                "max_score": None,
                "score_status": "pending_calibration_not_official",
                "candidate_source": "recall_calibration_v2_asset_absent_but_in_kb",
                "backfill_source": backfill_source,
                "backfill_case_id": candidate.get("case_id"),
                "backfill_gold_point_id": candidate.get("gold_point_id"),
                "backfill_gold_term": candidate.get("gold_term"),
                "provenance": {
                    "chunk_id": _chunk_id(chunk),
                    "page_num": _chunk_page_num(chunk),
                    "content_hash": content_hash(content),
                    "quote": required_term,
                    "anchor_verified": True,
                    "verify_on_write": "required_term_exact_in_content_markdown",
                    "no_loose_anchor": True,
                },
                "list_rule": {
                    "mode": "term_exact_match",
                    "term_count": 1,
                    "requires_distinctive_terms": True,
                },
            }
        )
    return assets


def merge_backfill_assets(assets_by_node: dict[str, list[dict[str, Any]]], backfill_assets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    merged = {node: list(assets) for node, assets in assets_by_node.items()}
    for asset in backfill_assets:
        node = str(asset.get("node_code") or "")
        if not node:
            continue
        merged.setdefault(node, []).append(asset)
    return merged


def _infer_non_textbook_source(term: str, point_type: str | None = None) -> str:
    normalized = normalize_for_match(term)
    if point_type in {"calculation", "figure_label", "non_textbook"}:
        return point_type
    if re.search(r"\d|kg|m2|m3|万元|元|%", term, re.IGNORECASE):
        return "calculation_or_formula"
    if any(marker in normalized for marker in ("虚工作", "虚箭线", "关键线路", "总时差", "自由时差")):
        return "cross_subject_project_management"
    if any(marker in normalized for marker in ("字母", "图中", "编号", "标号")):
        return "figure_label"
    return "official_answer_or_paraphrase"


def classify_miss_row(row: dict[str, Any], kb_index: list[dict[str, Any]]) -> dict[str, Any]:
    if row.get("all_kb_hit"):
        return {
            **row,
            "class": "node_remappable",
            "evidence": row.get("all_kb_matches") or [],
        }

    kb_matches = _kb_matches(str(row.get("gold_term") or ""), kb_index)
    if kb_matches:
        return {
            **row,
            "class": "asset_absent_but_in_kb",
            "evidence": kb_matches,
        }

    return {
        **row,
        "class": "gold_non_textbook",
        "suspected_source": _infer_non_textbook_source(str(row.get("gold_term") or ""), row.get("gold_point_type")),
        "evidence": [],
    }


def _asset_text(asset: dict[str, Any]) -> str:
    parts: list[str] = []
    for term in asset.get("required_terms") or []:
        parts.append(str(term))
    provenance = asset.get("provenance") if isinstance(asset.get("provenance"), dict) else {}
    if provenance.get("quote"):
        parts.append(str(provenance["quote"]))
    calculation = asset.get("calculation") if isinstance(asset.get("calculation"), dict) else {}
    for value in calculation.get("expected_values") or []:
        parts.append(str(value))
    return " ".join(parts)


def _match_assets(term: str, assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_term = normalize_for_match(term)
    matches: list[dict[str, Any]] = []
    for asset in assets:
        if normalized_term and normalized_term in normalize_for_match(_asset_text(asset)):
            matches.append(
                {
                    "point_id": asset.get("point_id"),
                    "node_code": asset.get("node_code"),
                    "chunk_id": asset.get("chunk_id"),
                    "point_type": asset.get("point_type"),
                    "anchor_source": asset.get("anchor_source"),
                    "matched_text": _asset_text(asset)[:160],
                }
            )
    return matches


def measure_case_recall(
    case: dict[str, Any],
    *,
    assets_by_node: dict[str, list[dict[str, Any]]],
    parent_child: dict[str, list[str]],
    use_expanded_scope: bool = False,
) -> dict[str, Any]:
    alignment = (
        expanded_node_scope(case.get("question_node"), asset_nodes=set(assets_by_node), parent_child=parent_child)
        if use_expanded_scope
        else align_question_node(case.get("question_node"), asset_nodes=set(assets_by_node), parent_child=parent_child)
    )
    rows: list[dict[str, Any]] = []
    if alignment.asset_nodes:
        candidate_assets = [asset for node in alignment.asset_nodes for asset in assets_by_node.get(node, [])]
    else:
        candidate_assets = []
    all_assets = [asset for assets in assets_by_node.values() for asset in assets]

    for point in case.get("gold_scoring_points") or []:
        terms = extract_gold_terms(point)
        for term in terms:
            matches = _match_assets(term, candidate_assets) if alignment.asset_nodes else []
            all_kb_matches = _match_assets(term, all_assets)
            rows.append(
                {
                    "case_id": case.get("case_id"),
                    "question_node": case.get("question_node"),
                    "node_alignment_status": alignment.status,
                    "aligned_asset_nodes": alignment.asset_nodes,
                    "gold_point_id": point.get("point_id"),
                    "gold_point_type": point.get("point_type"),
                    "gold_term": term,
                    "normalized_gold_term": normalize_for_match(term),
                    "hit": bool(matches),
                    "matches": matches,
                    "all_kb_hit": bool(all_kb_matches),
                    "all_kb_matches": all_kb_matches[:10],
                }
            )
    denominator_rows = [row for row in rows if row["node_alignment_status"] not in {"coverage_gap_na"}]
    hit = sum(1 for row in denominator_rows if row["hit"])
    total = len(denominator_rows)
    return {
        "case_id": case.get("case_id"),
        "question_node": case.get("question_node"),
        "alignment": alignment.__dict__,
        "rows": rows,
        "summary": {
            "term_total": total,
            "term_hit": hit,
            "term_miss": total - hit,
            "term_recall": hit / total if total else None,
            "excluded_na_terms": len(rows) - total,
        },
    }


def summarize_case_results(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(item["summary"]["term_total"] for item in case_results)
    hit = sum(item["summary"]["term_hit"] for item in case_results)
    excluded = sum(item["summary"]["excluded_na_terms"] for item in case_results)
    alignment_counts: dict[str, int] = defaultdict(int)
    type_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"term_total": 0, "term_hit": 0, "all_kb_hit": 0})
    point_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"point_total": 0, "point_all_terms_hit": 0, "point_any_term_hit": 0})
    all_kb_hit = 0
    for item in case_results:
        alignment_counts[item["alignment"]["status"]] += 1
        for row in item["rows"]:
            if row["node_alignment_status"] == "coverage_gap_na":
                continue
            all_kb_hit += 1 if row.get("all_kb_hit") else 0
            point_type = str(row.get("gold_point_type") or "unknown")
            type_counts[point_type]["term_total"] += 1
            type_counts[point_type]["term_hit"] += 1 if row.get("hit") else 0
            type_counts[point_type]["all_kb_hit"] += 1 if row.get("all_kb_hit") else 0
        point_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in item["rows"]:
            if row["node_alignment_status"] == "coverage_gap_na":
                continue
            point_groups[(str(row.get("gold_point_type") or "unknown"), str(row.get("gold_point_id") or ""))].append(row)
        for (point_type, _point_id), point_rows in point_groups.items():
            if not point_rows:
                continue
            point_counts[point_type]["point_total"] += 1
            point_counts[point_type]["point_all_terms_hit"] += 1 if all(row.get("hit") for row in point_rows) else 0
            point_counts[point_type]["point_any_term_hit"] += 1 if any(row.get("hit") for row in point_rows) else 0
    by_point_type = {}
    for point_type, values in sorted(type_counts.items()):
        total_for_type = values["term_total"]
        by_point_type[point_type] = {
            **values,
            "term_recall": values["term_hit"] / total_for_type if total_for_type else None,
            "all_kb_candidate_recall": values["all_kb_hit"] / total_for_type if total_for_type else None,
        }
        if point_type in point_counts:
            point_total = point_counts[point_type]["point_total"]
            by_point_type[point_type].update(
                {
                    **point_counts[point_type],
                    "point_all_terms_recall": point_counts[point_type]["point_all_terms_hit"] / point_total if point_total else None,
                    "point_any_term_recall": point_counts[point_type]["point_any_term_hit"] / point_total if point_total else None,
                }
            )
    return {
        "case_count": len(case_results),
        "term_total": total,
        "term_hit": hit,
        "term_miss": total - hit,
        "term_recall": hit / total if total else None,
        "all_kb_candidate_hit": all_kb_hit,
        "all_kb_candidate_recall": all_kb_hit / total if total else None,
        "excluded_na_terms": excluded,
        "alignment_counts": dict(sorted(alignment_counts.items())),
        "by_point_type": by_point_type,
    }
