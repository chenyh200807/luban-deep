#!/usr/bin/env python3
"""Compile 2026 lecture JSON into Luban answer-method runtime-supply candidates.

This is a compiler candidate, not a production publisher. It reads cleaned lecture
aggregate JSON, produces source inventory, pilot lecture answer-method shards, a
manifest that pins shard hashes, audit notes, and regression probes. It does not
write DB/remote state and it does not grant official-score authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_LECTURE_ROOT = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/讲义"
)
DEFAULT_PDF_ROOT = Path(
    "/Users/yehongchen/Documents/CYH_2/Markzuo/PDF清洗工厂/learning_marterial/@input"
)
DEFAULT_EXTRA_PDF_ROOTS = [
    Path("/Users/yehongchen/Documents/CYH_2/Markzuo/建筑实务11.20/2025年精讲课讲义合集/已清洗")
]
DEFAULT_OUT_DIR = REPO / "artifacts" / "luban_grading_artifacts" / (
    "lecture_answer_skill_pack_v1_" + date.today().strftime("%Y%m%d")
)

SCHEMA_VERSION = "luban_lecture_answer_skill_pack.v1"
SHARD_SCHEMA_VERSION = "luban_lecture_answer_method_shard.v1"
NAMESPACE = "lecture_answer_skill_pack"
PRODUCER = "scripts/run_luban_lecture_answer_skill_pack_compile.py"

DEFAULT_PILOT_TITLES = ["主体结构", "流水施工&网络计划"]
TITLE_SLUGS = {
    "流水施工&网络计划": "schedule-network",
    "招投标及合同管理": "tender-contract",
    "费用控制（成本＋造价）": "cost-control",
    "第三章": "chapter-3",
    "专业技术": "professional-technology",
    "防水&节能&装修工程": "waterproof-energy-decoration",
    "专业管理": "professional-management",
    "主体结构": "main-structure",
}
AD_TERMS = ("小佑题库", "佑森在线", "官方企微", "扫码关注", "免费听课", "在线刷题", "售后反馈")
COVER_META_TERMS = ("专用讲义", "版权所有", "全国一级注册建造师", "佑森教育", "珠峰班")


def _sha256_obj(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _title_from_dir(name: str) -> str:
    match = re.search(r"《([^》]+)》", name)
    return match.group(1) if match else name


def _slug(title: str) -> str:
    if title in TITLE_SLUGS:
        return TITLE_SLUGS[title]
    text = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()
    return text or hashlib.sha1(title.encode("utf-8")).hexdigest()[:12]


def _first_heading(markdown: str) -> str:
    for line in (markdown or "").splitlines():
        match = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line)
        if match:
            return match.group(1)
    return ""


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _aggregate_json_path(lecture_dir: Path) -> Path | None:
    candidates = sorted(p for p in lecture_dir.glob("*.json") if not p.name.startswith("page_"))
    return candidates[0] if candidates else None


def _pdf_for_title(pdf_roots: list[Path], title: str) -> Path | None:
    for pdf_root in pdf_roots:
        if not pdf_root.exists():
            continue
        matches = sorted(pdf_root.glob(f"*{title}*.pdf"))
        if matches:
            return matches[0]
    return None


def _is_non_exam_record(record: dict[str, Any]) -> tuple[bool, str]:
    text = "\n".join(
        str(record.get(key) or "")
        for key in ("chunk_id", "content_markdown", "rag_content")
    )
    source = record.get("source_meta") or {}
    text += "\n" + str(source.get("original_anchor") or "")
    if sum(term in text for term in AD_TERMS) >= 2:
        return True, "advertising/resource QR codes; invalid for exam answers"
    page_num = (record.get("source_meta") or {}).get("page_num")
    heading = _first_heading(record.get("content_markdown") or "")
    if isinstance(page_num, int) and page_num <= 2 and sum(term in text for term in COVER_META_TERMS) >= 2:
        if not any(term in heading for term in ("分值", "考点", "施工", "合同", "费用", "防水", "模板", "钢筋")):
            return True, "cover/meta course page; invalid for exam answers"
    return False, ""


def _page_numbers(records: list[dict[str, Any]]) -> list[int]:
    pages: list[int] = []
    for record in records:
        page = (record.get("source_meta") or {}).get("page_num")
        if isinstance(page, int):
            pages.append(page)
    return sorted(set(pages))


def inspect_sources(lecture_root: Path, pdf_root: Path, extra_pdf_roots: list[Path] | None = None) -> dict[str, Any]:
    pdf_roots = [pdf_root] + list(extra_pdf_roots or [])
    lectures: list[dict[str, Any]] = []
    for lecture_dir in sorted(p for p in lecture_root.iterdir() if p.is_dir()):
        title = _title_from_dir(lecture_dir.name)
        aggregate = _aggregate_json_path(lecture_dir)
        page_json = sorted(lecture_dir.glob("page_*_*.json"))
        pdf = _pdf_for_title(pdf_roots, title)
        if aggregate is None:
            lectures.append(
                {
                    "title": title,
                    "slug": _slug(title),
                    "source_dir": str(lecture_dir),
                    "aggregate_json": None,
                    "aggregate_status": "missing_aggregate_json",
                    "page_json_count": len(page_json),
                    "pdf_path": str(pdf) if pdf else None,
                    "pdf_status": "found" if pdf else "missing_pdf",
                    "coverage_status": "blocked_no_aggregate",
                }
            )
            continue
        records = [x for x in _load_json(aggregate) if isinstance(x, dict)]
        pages = _page_numbers(records)
        page_min = min(pages) if pages else None
        page_max = max(pages) if pages else None
        expected = range(page_min, page_max + 1) if page_min is not None and page_max is not None else []
        missing = [p for p in expected if p not in pages]
        duplicate_chunk_ids = {
            chunk_id: count
            for chunk_id, count in Counter(r.get("chunk_id") for r in records if r.get("chunk_id")).items()
            if count > 1
        }
        non_exam = []
        for record in records:
            excluded, reason = _is_non_exam_record(record)
            if excluded:
                non_exam.append(
                    {
                        "base_chunk_id": record.get("chunk_id"),
                        "json_page_num": (record.get("source_meta") or {}).get("page_num"),
                        "reason": reason,
                    }
                )
        exam_counts = {"trap_alert": 0, "grading_keywords": 0, "red_lines": 0, "mnemonics": 0}
        content_types: Counter[str] = Counter()
        for record in records:
            content_types[str(record.get("content_type") or "unknown")] += 1
            matrix = record.get("exam_matrix") or {}
            for key in exam_counts:
                value = matrix.get(key)
                if value and (not isinstance(value, list) or len(value) > 0):
                    exam_counts[key] += 1
        coverage_status = "complete_json"
        if missing or not pdf:
            coverage_status = "needs_visual_audit"
        lectures.append(
            {
                "title": title,
                "slug": _slug(title),
                "source_dir": str(lecture_dir),
                "aggregate_json": str(aggregate),
                "aggregate_sha256": _file_sha256(aggregate),
                "aggregate_status": "found",
                "raw_chunk_count": len(records),
                "page_json_count": len(page_json),
                "json_page_count": len(pages),
                "page_min": page_min,
                "page_max": page_max,
                "missing_internal_pages": missing,
                "non_exam_exclusions": non_exam,
                "duplicate_chunk_ids": duplicate_chunk_ids,
                "exam_matrix_counts": exam_counts,
                "content_type_counts": dict(content_types),
                "pdf_path": str(pdf) if pdf else None,
                "pdf_status": "found" if pdf else "missing_pdf",
                "coverage_status": coverage_status,
            }
        )
    inventory_body = {
        "schema_version": "luban_lecture_source_inventory.v1",
        "generated_at": date.today().isoformat(),
        "lecture_root": str(lecture_root),
        "pdf_roots": [str(p) for p in pdf_roots],
        "lecture_count": len(lectures),
        "lectures": lectures,
    }
    inventory_hash = _sha256_obj(inventory_body)
    return {**inventory_body, "inventory_hash": inventory_hash}


def _unique_source_id(record: dict[str, Any], seen: Counter[str]) -> str:
    chunk_id = str(record.get("chunk_id") or "chunk")
    seen[chunk_id] += 1
    if seen[chunk_id] == 1:
        return chunk_id
    heading = _first_heading(record.get("content_markdown") or "")
    suffix = re.sub(r"[\s/\\:*?\"<>|]+", "-", heading).strip("-")[:32] or str(seen[chunk_id])
    return f"{chunk_id}__{seen[chunk_id]}-{suffix}"


def _as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    return [str(value)]


def _intents(record: dict[str, Any], matrix: dict[str, Any]) -> list[str]:
    content_type = str(record.get("content_type") or "unknown")
    intents = {
        "definition": ["define", "explain"],
        "rule_numeric": ["numeric_rule", "case_judgement"],
        "process_flow": ["process_answer"],
        "comparison_matrix": ["compare"],
        "table_data": ["table_lookup"],
        "example_case": ["case_application"],
        "mnemonic": ["memorize"],
        "causal_principle": ["why_explain"],
        "exam_point": ["exam_point"],
    }.get(content_type, ["exam_point"])
    out = list(intents)
    if matrix.get("trap_alert"):
        out.append("trap_detection")
    if matrix.get("red_lines"):
        out.append("error_correction")
    if matrix.get("grading_keywords"):
        out.append("grading_keywords")
    return sorted(set(out))


def _question_patterns(record: dict[str, Any], matrix: dict[str, Any]) -> list[str]:
    taxonomy = record.get("taxonomy") or {}
    meta = record.get("meta_info") or {}
    patterns: list[str] = []
    for value in (
        _first_heading(record.get("content_markdown") or ""),
        meta.get("core_entity"),
        taxonomy.get("topic"),
        taxonomy.get("node_name"),
    ):
        if value:
            patterns.append(str(value))
    patterns.extend(_as_list(matrix.get("grading_keywords"))[:6])
    out: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        clean = str(pattern).strip()
        if clean and len(clean) <= 60 and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _probe_label(unit: dict[str, Any]) -> str:
    for pattern in unit.get("question_patterns") or []:
        if len(pattern) >= 4 and not re.fullmatch(r"[A-Za-z0-9'=+\-*/().]+", pattern):
            return pattern
    topic = str(unit.get("topic") or "").strip()
    if topic:
        return topic
    patterns = unit.get("question_patterns") or []
    return patterns[0] if patterns else unit["unit_id"]


def _numeric_snippets(markdown: str) -> list[str]:
    snippets: list[str] = []
    for raw in re.split(r"[。\n；;]", markdown or ""):
        line = raw.strip()
        if re.search(r"\d|%|≥|≤|不小于|不大于|以上|以下|超过|不少于", line):
            snippets.append(line[:160])
        if len(snippets) >= 6:
            break
    return snippets


def _answer_style(content_type: str) -> str:
    if content_type == "rule_numeric":
        return "先写适用条件，再写阈值/数值，最后提醒易错边界。"
    if content_type == "process_flow":
        return "按施工或管理顺序分点作答，不跳步。"
    if content_type == "mnemonic":
        return "先给口诀，再展开每个字对应的得分点。"
    if content_type == "comparison_matrix":
        return "按比较维度成组作答，避免只背单侧结论。"
    if content_type == "example_case":
        return "先判断案例做法是否正确，再给原因和正确做法。"
    return "先给直接结论，再列采分关键词和讲义出处。"


def build_answer_units(lecture: dict[str, Any], records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    answer_units: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    seen: Counter[str] = Counter()
    for index, record in enumerate(records, start=1):
        source_chunk_id = _unique_source_id(record, seen)
        excluded, reason = _is_non_exam_record(record)
        source_meta = record.get("source_meta") or {}
        if excluded:
            exclusions.append(
                {
                    "source_chunk_id": source_chunk_id,
                    "base_chunk_id": record.get("chunk_id"),
                    "json_page_num": source_meta.get("page_num"),
                    "reason": reason,
                    "action": "exclude_from_answer_units_and_routing",
                }
            )
            continue
        matrix = record.get("exam_matrix") or {}
        taxonomy = record.get("taxonomy") or {}
        markdown = record.get("content_markdown") or ""
        unit_id = f"lecture.{lecture['slug']}.{index:04d}"
        answer_units.append(
            {
                "unit_id": unit_id,
                "lecture": lecture["title"],
                "lecture_slug": lecture["slug"],
                "topic": taxonomy.get("topic") or taxonomy.get("node_name") or _first_heading(markdown),
                "taxonomy": {
                    "node_code": taxonomy.get("node_code"),
                    "node_name": taxonomy.get("node_name"),
                    "topic": taxonomy.get("topic"),
                },
                "content_type": record.get("content_type") or "unknown",
                "intent": _intents(record, matrix),
                "question_patterns": _question_patterns(record, matrix),
                "answer_method": {
                    "answer_style": _answer_style(str(record.get("content_type") or "unknown")),
                    "must_mentions": _as_list(matrix.get("grading_keywords")),
                    "red_lines": _as_list(matrix.get("red_lines")),
                    "trap_alerts": _as_list(matrix.get("trap_alert")),
                    "mnemonics": _as_list(matrix.get("mnemonics")),
                    "formula_or_thresholds": _numeric_snippets(markdown),
                },
                "source_ref": {
                    "source_chunk_id": source_chunk_id,
                    "base_chunk_id": record.get("chunk_id"),
                    "json_page_num": source_meta.get("page_num"),
                    "aggregate_json": lecture.get("aggregate_json"),
                    "pdf_path": lecture.get("pdf_path"),
                },
                "source_excerpt": markdown.strip()[:900],
                "authority": "lecture_json_primary",
                "tier": "teaching_answer_method_not_answer_key",
                "official_score_allowed": False,
                "confidence": "json_exam_matrix_enriched",
                "learning_mapping": {
                    "weakness_tags": sorted(
                        set(
                            [
                                f"lecture:{lecture['slug']}",
                                f"topic:{taxonomy.get('topic') or taxonomy.get('node_name') or 'unknown'}",
                            ]
                        )
                    )
                },
            }
        )
    return answer_units, exclusions


def _with_hash_and_signature(manifest: dict[str, Any]) -> dict[str, Any]:
    body = {k: v for k, v in manifest.items() if k not in {"content_hash", "signature"}}
    content_hash = _sha256_obj(body)
    return {**body, "content_hash": content_hash, "signature": _sha256_obj([content_hash, body["namespace"], body["status"]])}


def build_shard(lecture: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    answer_units, exclusions = build_answer_units(lecture, records)
    manifest = _with_hash_and_signature(
        {
            "schema_version": SHARD_SCHEMA_VERSION,
            "namespace": f"lecture_answer_method.{lecture['slug']}",
            "status": "release_candidate",
            "published": False,
            "tier": "teaching_answer_method_not_answer_key",
            "official_score_allowed": False,
            "lecture": lecture["title"],
            "lecture_slug": lecture["slug"],
            "answer_unit_count": len(answer_units),
            "non_exam_exclusion_count": len(exclusions),
            "coverage_status": lecture.get("coverage_status"),
            "missing_internal_pages": lecture.get("missing_internal_pages", []),
            "source_aggregate_sha256": lecture.get("aggregate_sha256"),
        }
    )
    return {"manifest": manifest, "answer_units": answer_units, "non_exam_exclusions": exclusions}


def _schema_doc() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "purpose": "Runtime-supply release_candidate for Luban lecture answer-method teaching context.",
        "authority": {
            "allowed": "teaching context, answer method, citation guidance, trap/red-line/mnemonic recall",
            "forbidden": "official score, published registry, canonical learner truth, mutable DB truth",
        },
        "required_manifest_fields": [
            "schema_version",
            "namespace",
            "status",
            "published",
            "version",
            "source_inventory_hash",
            "shards",
            "content_hash",
            "signature",
        ],
        "answer_unit_required_fields": [
            "unit_id",
            "lecture",
            "topic",
            "intent",
            "question_patterns",
            "answer_method",
            "source_ref",
            "authority",
            "tier",
            "official_score_allowed",
        ],
    }


def _write_inventory_markdown(path: Path, inventory: dict[str, Any]) -> None:
    lines = [
        "# Lecture Source Inventory",
        "",
        "| 讲义 | chunks | JSON页 | 页码范围 | 缺页 | PDF | 广告/资源chunk | coverage |",
        "|---|---:|---:|---|---|---|---:|---|",
    ]
    for lecture in inventory["lectures"]:
        lines.append(
            "| {title} | {chunks} | {pages} | {page_min}-{page_max} | {missing} | {pdf} | {ads} | {coverage} |".format(
                title=lecture["title"],
                chunks=lecture.get("raw_chunk_count", 0),
                pages=lecture.get("json_page_count", 0),
                page_min=lecture.get("page_min"),
                page_max=lecture.get("page_max"),
                missing=lecture.get("missing_internal_pages", []),
                pdf=lecture.get("pdf_status"),
                ads=len(lecture.get("non_exam_exclusions") or []),
                coverage=lecture.get("coverage_status"),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_regression_probes(path: Path, shards: list[dict[str, Any]]) -> None:
    probes: list[dict[str, Any]] = []
    for shard in shards:
        for unit in shard["answer_units"][:10]:
            method = unit["answer_method"]
            probe_type = "trap_red_line" if method["red_lines"] or method["trap_alerts"] else "citation"
            probes.append(
                {
                    "probe_id": f"probe.{unit['unit_id']}",
                    "lecture": unit["lecture"],
                    "question": f"{_probe_label(unit)}怎么按考试答？",
                    "expected": {
                        "must_cite_chunk": unit["source_ref"]["source_chunk_id"],
                        "must_cite_page": unit["source_ref"]["json_page_num"],
                        "must_include_red_line_or_trap_when_present": probe_type == "trap_red_line",
                        "no_outside_knowledge": True,
                    },
                }
            )
    path.write_text("\n".join(json.dumps(p, ensure_ascii=False, sort_keys=True) for p in probes) + "\n", encoding="utf-8")


def _write_finding(path: Path, inventory: dict[str, Any], manifest: dict[str, Any], result: dict[str, Any]) -> None:
    lines = [
        "# FINDING: Lecture Answer Skill Pack V1",
        "",
        f"- verdict: {result['verdict']}",
        f"- manifest: `runtime_supply/manifest.json`",
        f"- source_inventory_hash: `{inventory['inventory_hash']}`",
        f"- shard_count: {manifest['shard_count']}",
        f"- answer_unit_count: {manifest['answer_unit_count']}",
        "",
        "## Boundary",
        "",
        "- This is `release_candidate` teaching context, not official score authority.",
        "- Runtime must consume manifest-pointed shards only; no directory scanning.",
        "- Non-exam advertising/resource pages are excluded from answer units.",
        "- Missing JSON pages require visual/PDF audit before claiming complete lecture coverage.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_records(lecture: dict[str, Any]) -> list[dict[str, Any]]:
    aggregate = lecture.get("aggregate_json")
    if not aggregate:
        return []
    return [x for x in _load_json(Path(aggregate)) if isinstance(x, dict)]


def compile_pack(
    *,
    lecture_root: Path,
    pdf_root: Path,
    extra_pdf_roots: list[Path] | None = None,
    out_dir: Path,
    pilot_titles: list[str],
    all_lectures: bool = False,
    version: str | None = None,
) -> dict[str, Any]:
    version = version or date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir = out_dir / "runtime_supply"
    shard_dir = runtime_dir / "shards"
    audit_dir = out_dir / "audit"
    eval_dir = out_dir / "eval"
    schema_dir = out_dir / "schema"
    for directory in (runtime_dir, shard_dir, audit_dir, eval_dir, schema_dir):
        directory.mkdir(parents=True, exist_ok=True)

    inventory = inspect_sources(lecture_root, pdf_root, extra_pdf_roots=extra_pdf_roots)
    if all_lectures:
        selected = [lecture for lecture in inventory["lectures"] if lecture.get("aggregate_json")]
        scope = "all_lecture_release_candidate"
    else:
        selected = [lecture for lecture in inventory["lectures"] if lecture["title"] in set(pilot_titles)]
        scope = "release_candidate_pilot"
    shards: list[dict[str, Any]] = []
    shard_descriptors: list[dict[str, Any]] = []
    for lecture in selected:
        shard = build_shard(lecture, _load_records(lecture))
        shard_path = shard_dir / f"{lecture['slug']}.json"
        shard_path.write_text(json.dumps(shard, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        shards.append(shard)
        shard_descriptors.append(
            {
                "lane": "lecture_answer_methods",
                "topic": lecture["slug"],
                "path": str(shard_path.relative_to(runtime_dir)),
                "namespace": shard["manifest"]["namespace"],
                "content_hash": shard["manifest"]["content_hash"],
                "record_count": shard["manifest"]["answer_unit_count"],
                "tier": shard["manifest"]["tier"],
            }
        )

    manifest_body = {
        "schema_version": SCHEMA_VERSION,
        "namespace": NAMESPACE,
        "status": "release_candidate",
        "published": False,
        "version": version,
        "producer": PRODUCER,
        "scope": scope,
        "rollback_pointer": "none; first lecture-answer-method release_candidate",
        "source_inventory_hash": inventory["inventory_hash"],
        "source_lecture_count": inventory["lecture_count"],
        "pilot_lectures": [] if all_lectures else [lecture["title"] for lecture in selected],
        "selected_lectures": [lecture["title"] for lecture in selected],
        "all_lectures_selected": all_lectures,
        "shards": sorted(shard_descriptors, key=lambda x: (x["lane"], x["topic"])),
        "shard_count": len(shard_descriptors),
        "answer_unit_count": sum(int(s["record_count"] or 0) for s in shard_descriptors),
        "official_score_allowed": False,
        "tier": "teaching_answer_method_not_answer_key",
    }
    manifest = _with_hash_and_signature(manifest_body)

    (out_dir / "source_inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (runtime_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (schema_dir / "luban_answer_skill_pack.schema.json").write_text(
        json.dumps(_schema_doc(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_inventory_markdown(audit_dir / "source_inventory.md", inventory)
    _write_regression_probes(eval_dir / "pilot_regression_questions.jsonl", shards)

    blockers: list[str] = []
    for lecture in inventory["lectures"]:
        if lecture.get("coverage_status") != "complete_json":
            blockers.append(f"{lecture['title']}: {lecture.get('coverage_status')}")
    result = {
        "verdict": "WEAK-GO" if blockers else "GO",
        "scope": scope,
        "out_dir": str(out_dir),
        "manifest_path": str(runtime_dir / "manifest.json"),
        "source_inventory_hash": inventory["inventory_hash"],
        "pilot_lectures": [] if all_lectures else [lecture["title"] for lecture in selected],
        "selected_lectures": [lecture["title"] for lecture in selected],
        "all_lectures_selected": all_lectures,
        "answer_unit_count": manifest["answer_unit_count"],
        "blockers": blockers,
    }
    (out_dir / "go_no_go.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    _write_finding(out_dir / "FINDING_lecture_answer_skill_pack_v1.md", inventory, manifest, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lecture-root", type=Path, default=DEFAULT_LECTURE_ROOT)
    parser.add_argument("--pdf-root", type=Path, default=DEFAULT_PDF_ROOT)
    parser.add_argument("--extra-pdf-root", type=Path, action="append", default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--pilot-title", action="append", dest="pilot_titles", default=None)
    parser.add_argument("--all-lectures", action="store_true")
    parser.add_argument("--version", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = compile_pack(
        lecture_root=args.lecture_root,
        pdf_root=args.pdf_root,
        extra_pdf_roots=args.extra_pdf_root if args.extra_pdf_root is not None else DEFAULT_EXTRA_PDF_ROOTS,
        out_dir=args.out_dir,
        pilot_titles=args.pilot_titles or DEFAULT_PILOT_TITLES,
        all_lectures=args.all_lectures,
        version=args.version,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
