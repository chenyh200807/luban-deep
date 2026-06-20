#!/usr/bin/env python3
"""Build AI-only Topic OKF candidate artifacts from existing source ledgers."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_ROOT = Path(__file__).resolve().parents[1]
EXTRACTIONS_ROOT = INVENTORY_ROOT / "extractions"
DEFAULT_JSON_SOURCES = EXTRACTIONS_ROOT / "json_source_ledger_v0" / "sources.jsonl"
DEFAULT_OKF_POINTS = EXTRACTIONS_ROOT / "okf_candidate_scope_v0" / "scoring_points.jsonl"
DEFAULT_OUTPUT_ROOT = EXTRACTIONS_ROOT / "topic_okf_v0"
SENTINEL_NAME = ".topic_okf_generated.json"
OUTPUT_ROOT_SUFFIX = ("extractions", "topic_okf_v0")
GENERATOR = "build_topic_okf.py"
RUNTIME_GUARD = {
    "release_stage": "topic_okf_candidate",
    "runtime_consumable": False,
    "installed_runtime_supply": False,
    "canonical_write_allowed": False,
    "learner_truth_write_allowed": False,
    "gbrain_write_allowed": False,
    "production_registry_write_allowed": False,
    "official_score_allowed": False,
}

TOPIC_DEFINITIONS = [
    {
        "topic_id": "roof-waterproofing",
        "title": "屋面防水",
        "question_intent": "屋面防水做法、构造层次、试验验收、常见质量问题与真题证据。",
        "source_required_any": ["屋面", "女儿墙", "檐沟", "天沟", "泛水", "找坡", "找平", "隔汽"],
        "aliases": [
            "屋面防水",
            "屋面工程",
            "防水层",
            "卷材防水",
            "涂膜防水",
            "找坡层",
            "找平层",
            "隔汽层",
            "保温层",
            "泛水",
            "女儿墙",
            "檐沟",
            "天沟",
            "蓄水试验",
            "淋水试验",
            "防水等级",
        ],
    },
    {
        "topic_id": "flow-construction",
        "title": "流水施工",
        "question_intent": "流水施工参数、流水节拍、流水步距、施工段与工期计算。",
        "aliases": [
            "流水施工",
            "流水节拍",
            "流水步距",
            "施工段",
            "流水段",
            "等节奏",
            "异节奏",
            "成倍节拍",
            "流水工期",
        ],
    },
    {
        "topic_id": "network-planning",
        "title": "网络计划",
        "question_intent": "网络计划时间参数、关键线路、时差、工期调整与索赔联动。",
        "aliases": [
            "网络计划",
            "双代号",
            "时标网络",
            "关键线路",
            "关键工作",
            "总时差",
            "自由时差",
            "最早开始",
            "最迟完成",
            "工期优化",
        ],
    },
    {
        "topic_id": "claims",
        "title": "索赔",
        "question_intent": "工期索赔、费用索赔、变更签证、不可抗力与责任归属。",
        "aliases": [
            "索赔",
            "工期索赔",
            "费用索赔",
            "签证",
            "工程变更",
            "设计变更",
            "不可抗力",
            "赶工费",
            "窝工",
            "延误",
        ],
    },
    {
        "topic_id": "quality-acceptance",
        "title": "质量验收",
        "question_intent": "检验批、分项分部单位工程、主控项目、一般项目、隐蔽验收与竣工验收。",
        "aliases": [
            "质量验收",
            "检验批",
            "分项工程",
            "分部工程",
            "单位工程",
            "主控项目",
            "一般项目",
            "隐蔽工程验收",
            "竣工验收",
            "验收记录",
        ],
    },
]


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def display_path(path: Path) -> str:
    try:
        return rel(path)
    except ValueError:
        return str(path)


def resolve_soft(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def has_suffix(path: Path, suffix: tuple[str, ...]) -> bool:
    return tuple(path.parts[-len(suffix) :]) == suffix


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row is not an object: {display_path(path)}:{line_no}")
            rows.append(row)
    if not rows:
        raise ValueError(f"required JSONL input is empty: {display_path(path)}")
    return rows


def validate_output_root(path: Path) -> None:
    resolved = resolve_soft(path)
    dangerous_roots = {
        Path("/").resolve(),
        Path.home().resolve(),
        REPO_ROOT.resolve(),
        INVENTORY_ROOT.resolve(),
        EXTRACTIONS_ROOT.resolve(),
    }
    if resolved in dangerous_roots or not has_suffix(resolved, OUTPUT_ROOT_SUFFIX):
        raise ValueError(f"unsafe output root: {display_path(path)}")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"unsafe output root is not a directory: {display_path(path)}")


def load_sentinel(path: Path) -> dict[str, Any]:
    sentinel_path = path / SENTINEL_NAME
    if not sentinel_path.exists():
        raise ValueError(f"missing generated sentinel: {display_path(path)}")
    sentinel = load_json(sentinel_path)
    if (
        sentinel.get("generated_by") != GENERATOR
        or sentinel.get("kind") != "topic_okf"
        or sentinel.get("runtime_consumable") is not False
    ):
        raise ValueError(f"invalid generated sentinel: {display_path(sentinel_path)}")
    return sentinel


def assert_generated_tree(path: Path) -> None:
    if not path.exists() or not any(path.iterdir()):
        return
    load_sentinel(path)
    allowed = {
        SENTINEL_NAME,
        "manifest.json",
        "topics.jsonl",
        "source_hits.jsonl",
        "summary.md",
    }
    for child in path.iterdir():
        if child.name not in allowed or child.is_dir():
            raise ValueError(f"unsafe generated output tree: {display_path(child)}")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def write_sentinel(path: Path, generated_at: str) -> None:
    payload = {
        "kind": "topic_okf",
        "generated_by": GENERATOR,
        "generated_at": generated_at,
        "runtime_consumable": False,
    }
    (path / SENTINEL_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def require_non_runtime_guard(payload: dict[str, Any], label: str) -> None:
    guard = payload.get("runtime_guard")
    if not isinstance(guard, dict):
        raise ValueError(f"{label} must include runtime_guard")
    for key in [
        "runtime_consumable",
        "installed_runtime_supply",
        "canonical_write_allowed",
        "learner_truth_write_allowed",
        "gbrain_write_allowed",
        "production_registry_write_allowed",
        "official_score_allowed",
    ]:
        if guard.get(key) is not False:
            raise ValueError(f"{label} must keep {key}=false")


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def make_snippet(text: str, aliases: list[str], limit: int = 220) -> str:
    clean = normalize_text(text)
    positions = [clean.find(alias) for alias in aliases if alias in clean]
    start = min([pos for pos in positions if pos >= 0], default=0)
    start = max(0, start - 50)
    snippet = clean[start : start + limit]
    return snippet.rstrip() + ("..." if start + limit < len(clean) else "")


def json_path_join(parent: str, part: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part):
        return f"{parent}.{part}"
    return f"{parent}[{json.dumps(part, ensure_ascii=False)}]"


def iter_text_nodes(value: Any, path: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        text = normalize_text(value)
        if len(text) >= 2:
            yield path, text
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_text_nodes(item, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from iter_text_nodes(item, json_path_join(path, str(key)))


def matched_aliases(text: str, aliases: list[str]) -> list[str]:
    return [alias for alias in aliases if alias in text]


def source_context_allowed(text: str, topic: dict[str, Any]) -> bool:
    required = topic.get("source_required_any") or []
    if not required:
        return True
    return any(token in text for token in required)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_source_hits(
    topics: list[dict[str, Any]],
    json_sources: list[dict[str, Any]],
    *,
    max_hits_per_topic: int = 80,
) -> tuple[list[dict[str, Any]], dict[str, Counter], dict[str, set[str]]]:
    source_hits: list[dict[str, Any]] = []
    hit_counts: dict[str, Counter] = {topic["topic_id"]: Counter() for topic in topics}
    source_paths_by_topic: dict[str, set[str]] = {topic["topic_id"]: set() for topic in topics}
    kept_by_topic: Counter = Counter()

    for source in json_sources:
        require_non_runtime_guard(source, f"json source {source.get('source_id')}")
        source_path = source.get("source_path")
        if not source_path:
            continue
        absolute_path = REPO_ROOT / str(source_path)
        if not absolute_path.exists():
            continue
        try:
            payload = load_json(absolute_path)
        except (json.JSONDecodeError, OSError):
            continue
        for json_path, text in iter_text_nodes(payload):
            for topic in topics:
                aliases = matched_aliases(text, topic["aliases"])
                if not aliases or not source_context_allowed(text, topic):
                    continue
                topic_id = topic["topic_id"]
                hit_counts[topic_id][str(source.get("bucket", "unknown"))] += 1
                source_paths_by_topic[topic_id].add(str(source_path))
                if kept_by_topic[topic_id] >= max_hits_per_topic:
                    continue
                source_hits.append(
                    {
                        "schema": "luban_topic_okf_source_hit.v0",
                        "topic_id": topic_id,
                        "source_id": source.get("source_id"),
                        "source_path": source_path,
                        "bucket": source.get("bucket"),
                        "json_path": json_path,
                        "matched_aliases": aliases,
                        "snippet": make_snippet(text, aliases),
                        "authority_status": "raw_evidence_hit",
                        "runtime_guard": RUNTIME_GUARD,
                    }
                )
                kept_by_topic[topic_id] += 1
    return source_hits, hit_counts, source_paths_by_topic


def build_rubric_evidence(
    topics: list[dict[str, Any]],
    scoring_points: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for topic in topics:
        result[topic["topic_id"]] = {
            "candidate_scoring_point_count": 0,
            "case_count": 0,
            "year_count": 0,
            "cases": [],
            "years": [],
            "representative_points": [],
        }
    cases_by_topic: dict[str, set[str]] = defaultdict(set)
    years_by_topic: dict[str, set[str]] = defaultdict(set)
    for point in scoring_points:
        require_non_runtime_guard(point, f"scoring point {point.get('point_id')}")
        text = str(point.get("text") or "")
        for topic in topics:
            aliases = matched_aliases(text, topic["aliases"])
            if not aliases:
                continue
            topic_id = topic["topic_id"]
            result[topic_id]["candidate_scoring_point_count"] += 1
            cases_by_topic[topic_id].add(str(point.get("case_id")))
            years_by_topic[topic_id].add(str(point.get("year")))
            if len(result[topic_id]["representative_points"]) < 12:
                result[topic_id]["representative_points"].append(
                    {
                        "point_id": point.get("point_id"),
                        "case_id": point.get("case_id"),
                        "year": point.get("year"),
                        "matched_aliases": aliases,
                        "text": point.get("text"),
                        "source_path": point.get("source_path"),
                        "source_json_path": point.get("source_json_path"),
                    }
                )
    for topic_id, cases in cases_by_topic.items():
        result[topic_id]["cases"] = sorted(cases)
        result[topic_id]["case_count"] = len(cases)
    for topic_id, years in years_by_topic.items():
        result[topic_id]["years"] = sorted(years)
        result[topic_id]["year_count"] = len(years)
    return result


def build_topics(
    json_sources_path: Path = DEFAULT_JSON_SOURCES,
    okf_points_path: Path = DEFAULT_OKF_POINTS,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_output_root(output_root)
    assert_generated_tree(output_root)
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    json_sources = load_jsonl(json_sources_path)
    scoring_points = load_jsonl(okf_points_path)
    topics = [dict(topic) for topic in TOPIC_DEFINITIONS]
    source_hits, hit_counts, source_paths_by_topic = build_source_hits(topics, json_sources)
    rubric_evidence = build_rubric_evidence(topics, scoring_points)

    topic_records: list[dict[str, Any]] = []
    for topic in topics:
        topic_id = topic["topic_id"]
        source_paths = sorted(source_paths_by_topic[topic_id])
        bucket_counts = dict(sorted(hit_counts[topic_id].items()))
        topic_records.append(
            {
                "schema": "luban_topic_okf_topic_card.v0",
                "topic_id": topic_id,
                "title": topic["title"],
                "aliases": topic["aliases"],
                "question_intent": topic["question_intent"],
                "authority_status": "topic_okf_candidate",
                "runtime_guard": RUNTIME_GUARD,
                "evidence_summary": {
                    "source_hit_count": sum(bucket_counts.values()),
                    "source_count": len(source_paths),
                    "bucket_hit_counts": bucket_counts,
                    "candidate_rubric": rubric_evidence[topic_id],
                },
                "source_paths": source_paths,
                "guardrails": [
                    "topic card is AI navigation and synthesis support only",
                    "source hits are keyword-based candidate evidence",
                    "candidate rubric hits are not official score frequency",
                    "read linked source paths before making high-stakes claims",
                ],
            }
        )

    manifest = {
        "schema": "luban_topic_okf_manifest.v0",
        "generated_at": generated_at,
        "status": "topic_okf_candidate_ready",
        "authority_status": "ai_topic_navigation_only",
        "runtime_guard": RUNTIME_GUARD,
        "source_paths": {
            "json_sources": display_path(json_sources_path),
            "okf_scoring_points": display_path(okf_points_path),
        },
        "artifact_refs": {
            "topics": "topics.jsonl",
            "source_hits": "source_hits.jsonl",
        },
        "counts": {
            "topics": len(topic_records),
            "source_hits_kept": len(source_hits),
            "source_hit_total": sum(
                topic["evidence_summary"]["source_hit_count"] for topic in topic_records
            ),
        },
        "guardrails": [
            "AI-only Topic OKF",
            "not production runtime supply",
            "not official scoring authority",
            "not a full source mirror",
        ],
    }

    reset_dir(output_root)
    write_sentinel(output_root, generated_at)
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_jsonl(output_root / "topics.jsonl", topic_records)
    write_jsonl(output_root / "source_hits.jsonl", source_hits)
    write_summary(output_root / "summary.md", manifest, topic_records)
    return {
        "output_root": display_path(output_root),
        "manifest": manifest,
    }


def write_summary(path: Path, manifest: dict[str, Any], topics: list[dict[str, Any]]) -> None:
    lines = [
        "# Topic OKF v0",
        "",
        f"- Status: `{manifest['status']}`",
        f"- Authority status: `{manifest['authority_status']}`",
        f"- Topics: `{manifest['counts']['topics']}`",
        f"- Source hits kept: `{manifest['counts']['source_hits_kept']}`",
        f"- Source hit total: `{manifest['counts']['source_hit_total']}`",
        f"- Runtime consumable: `{manifest['runtime_guard']['runtime_consumable']}`",
        f"- Official score allowed: `{manifest['runtime_guard']['official_score_allowed']}`",
        "",
        "## Topics",
        "",
    ]
    for topic in topics:
        candidate = topic["evidence_summary"]["candidate_rubric"]
        lines.append(
            f"- `{topic['topic_id']}` {topic['title']}: "
            f"sources={topic['evidence_summary']['source_count']}, "
            f"raw_hits={topic['evidence_summary']['source_hit_count']}, "
            f"candidate_scoring_points={candidate['candidate_scoring_point_count']}, "
            f"candidate_cases={candidate['case_count']}"
        )
    lines.extend(
        [
            "",
            "This is an AI topic-navigation layer. It is not signed runtime supply and does not make official frequency or scoring claims.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-sources", type=Path, default=DEFAULT_JSON_SOURCES)
    parser.add_argument("--okf-points", type=Path, default=DEFAULT_OKF_POINTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--generated-at", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_topics(
        json_sources_path=args.json_sources,
        okf_points_path=args.okf_points,
        output_root=args.output_root,
        generated_at=args.generated_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
