#!/usr/bin/env python3
"""Build the J01 governed-gold annotation package (Stage 0 of the grading revenue-gate plan).

This harness produces a *blind, human-fillable* annotation package so 教研 can label
~150 per-scoring-point hit/miss judgments on 拟真 student answers. It does NOT label,
does NOT grade, does NOT touch runtime/DB, and creates no second authority:

  - 采分点 (scoring points) are verbatim slices of the OFFICIAL exam answer
    (FINAL_CLEANED_EXAM_V{year}.json snapshot). Every point_text is verified to be a
    verbatim substring of the official answer (whitespace-normalized) or the build
    fails closed — this prevents drift/fabrication.
  - gold truth = the human hit/miss labels filled later; the package is blind
    (no model prediction, no prior label shown) to prevent anchoring.

Output (default artifacts/luban_governed_gold/j01_v1/):
  annotation_package.jsonl   one row per (student answer × scoring point)
  annotator_A.csv            blank label template (annotator 1)
  annotator_B.csv            blank label template (annotator 2)
  manifest.json              governance metadata (hashes, selection, expected rows)
  protocol.md                教研标注说明 (hit 定义 / 踩字 / 边界 / 盲标防锚定)
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "scripts/luban_j01_gold_selection.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts/luban_governed_gold/j01_v1"

HIT_VALUES = ("hit", "partial", "miss")
LABEL_FIELDS = ["human_hit", "human_score", "human_note", "human_point_boundary_flag"]


# ---------------------------------------------------------------------------
# hashing / io helpers
# ---------------------------------------------------------------------------
def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _no_ws(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


# ---------------------------------------------------------------------------
# student answer parsing (拟真答卷 markdown -> per-sub-question answers)
# ---------------------------------------------------------------------------
def split_numbered(text: str) -> dict[str, str]:
    """Split a numbered answer/question blob into {sub_no: body}."""
    matches = list(re.finditer(r"(?:^|\n)\s*(\d+)[.、．)]\s*", str(text or "")))
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[m.group(1)] = text[start:end].strip()
    return out


def parse_student_samples(md_text: str) -> list[dict[str, Any]]:
    """Parse 近三年案例题_按学生答卷排版.md into per-persona samples."""
    starts = list(re.finditer(r"^### (Q(?P<year>\d{4})-\d{2})｜.+$", md_text, flags=re.M))
    samples: list[dict[str, Any]] = []
    for i, m in enumerate(starts):
        block = md_text[m.start() : starts[i + 1].start() if i + 1 < len(starts) else len(md_text)]
        sid = re.search(r"- 学生ID：`?([^`\n]+)`?", block)
        ability = re.search(r"- ability_label：`?([^`\n]+)`?", block)
        ans = re.search(
            r"#### 回答\s*\n(?P<a>.*?)(?=\n### .*参考答案|\n#### 本题水平判断|\n---\n|$)",
            block,
            flags=re.S,
        )
        if not (sid and ans):
            continue
        answer_text = re.sub(r"^作答：\s*", "", ans.group("a").strip())
        samples.append(
            {
                "qid": m.group(1),
                "year": int(m.group("year")),
                "student_id": sid.group(1).strip(),
                "ability_label": (ability.group(1).strip() if ability else ""),
                "sub_answers": split_numbered(answer_text),
            }
        )
    return samples


# ---------------------------------------------------------------------------
# official answer extraction (authority = exam snapshot)
# ---------------------------------------------------------------------------
def load_official_answer(snapshot_dir: Path, year: int, source: dict[str, Any]) -> str:
    """Pull one sub-question's official answer from the exam snapshot.

    Two storage styles handled deterministically:
      - blob:  exercises[exercise_index].correct_answer is a whole-case numbered blob;
               take the section keyed by blob_section ("1"/"2"/...).
      - per-exercise: exercises[exercise_index].correct_answer IS the sub answer.
    """
    exam = json.loads((snapshot_dir / f"FINAL_CLEANED_EXAM_V{year}.json").read_text(encoding="utf-8"))
    exercises: list[str] = []
    for chunk in exam.get("chunks", []):
        if chunk.get("chunk_id") != source["chunk_id"]:
            continue
        for ex in chunk.get("exercises", []):
            if ex.get("type") == "case_study":
                exercises.append(str(ex.get("question_data", {}).get("correct_answer") or ""))
    idx = int(source.get("exercise_index", 0))
    if idx >= len(exercises):
        raise ValueError(f"exercise_index {idx} out of range for chunk {source['chunk_id']} (have {len(exercises)})")
    answer = exercises[idx]
    section = source.get("blob_section")
    if section is not None:
        blob = split_numbered(answer)
        if str(section) not in blob:
            raise ValueError(f"blob_section {section} not found in chunk {source['chunk_id']} ex{idx}")
        return blob[str(section)]
    return answer


def verify_points_verbatim(official_answer: str, scoring_points: list[dict[str, Any]]) -> None:
    """Fail closed unless every point_text is a verbatim substring (whitespace-normalized)."""
    hay = _no_ws(official_answer)
    for point in scoring_points:
        needle = _no_ws(point["point_text"])
        if needle not in hay:
            raise ValueError(
                f"point {point['point_id']} is NOT a verbatim slice of the official answer "
                f"(anti-fabrication gate). point_text={point['point_text']!r}"
            )


# ---------------------------------------------------------------------------
# row build
# ---------------------------------------------------------------------------
def _row_id(slice_version: str, qid: str, sub_no: str, student_id: str, point_id: str) -> str:
    return sha256_text(f"{slice_version}|{qid}|{sub_no}|{student_id}|{point_id}")[:16]


def build_rows(config: dict[str, Any], samples: list[dict[str, Any]], snapshot_dir: Path) -> list[dict[str, Any]]:
    slice_version = config["slice_version"]
    by_qid: dict[str, list[dict[str, Any]]] = {}
    for s in samples:
        by_qid.setdefault(s["qid"], []).append(s)

    rows: list[dict[str, Any]] = []
    for sel in config["selections"]:
        qid, sub_no = sel["qid"], str(sel["sub_no"])
        official = load_official_answer(snapshot_dir, int(sel["year"]), sel["official_source"])
        verify_points_verbatim(official, sel["scoring_points"])
        source = sel["official_source"]
        source_ref = source["chunk_id"] + (
            f"#blob:{source['blob_section']}" if source.get("blob_section") is not None
            else f"#ex:{source.get('exercise_index', 0)}"
        )
        personas = sorted(by_qid.get(qid, []), key=lambda x: x["student_id"])
        if not personas:
            raise ValueError(f"no student samples found for {qid} — student md missing/unparsed?")
        for persona in personas:
            segment = persona["sub_answers"].get(sub_no, "")
            for point in sel["scoring_points"]:
                rows.append(
                    {
                        "row_id": _row_id(slice_version, qid, sub_no, persona["student_id"], point["point_id"]),
                        "qid": qid,
                        "year": int(sel["year"]),
                        "sub_no": sub_no,
                        "student_id": persona["student_id"],
                        "ability_label": persona.get("ability_label", ""),
                        "sub_question": sel["sub_question"],
                        "point_id": point["point_id"],
                        "point_text": point["point_text"],
                        "required_terms": list(point.get("required_terms") or []),
                        "j01_relevance": point.get("j01_relevance", sel.get("j01_relevance", "")),
                        "dimension": point.get("dimension", ""),
                        "r5_anchor": point.get("r5_anchor", ""),
                        "source_ref": source_ref,
                        "student_answer_segment": segment,
                        # blind fields (empty; filled by 教研). NO ai prediction / prior label present.
                        "human_hit": "",
                        "human_score": "",
                        "human_note": "",
                        "human_point_boundary_flag": "",
                    }
                )
    return rows


# ---------------------------------------------------------------------------
# manifest / package writers
# ---------------------------------------------------------------------------
def _content_hash(config: dict[str, Any]) -> str:
    """Hash the FROZEN point definitions (slice_version + verbatim point set)."""
    frozen = {
        "slice_version": config["slice_version"],
        "selections": [
            {
                "qid": s["qid"],
                "sub_no": str(s["sub_no"]),
                "official_source": s["official_source"],
                "scoring_points": [
                    {"point_id": p["point_id"], "point_text": p["point_text"], "j01_relevance": p.get("j01_relevance")}
                    for p in s["scoring_points"]
                ],
            }
            for s in config["selections"]
        ],
    }
    return sha256_text(json.dumps(frozen, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def build_manifest(
    config: dict[str, Any], rows: list[dict[str, Any]], *, student_md: Path, snapshot_dir: Path, config_path: Path
) -> dict[str, Any]:
    years = sorted({int(s["year"]) for s in config["selections"]})
    tier_counts: dict[str, int] = {}
    for r in rows:
        tier_counts[r["j01_relevance"]] = tier_counts.get(r["j01_relevance"], 0) + 1
    personas_per_qid: dict[str, int] = {}
    for r in rows:
        personas_per_qid.setdefault(r["qid"], set()).add(r["student_id"])  # type: ignore[arg-type]
    personas_per_qid = {k: len(v) for k, v in personas_per_qid.items()}  # type: ignore[assignment]

    return {
        "slice_version": config["slice_version"],
        "topic": config["topic"],
        "status": "awaiting_human_labels",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "content_hash": _content_hash(config),
        "source_hashes": {
            "config": sha256_file(config_path),
            "student_md": sha256_file(student_md),
            "j01_evidence_pack": sha256_file(PROJECT_ROOT / config["j01_evidence_pack"]),
            "exam_snapshots": {str(y): sha256_file(snapshot_dir / f"FINAL_CLEANED_EXAM_V{y}.json") for y in years},
        },
        "expected_rows": len(rows),
        "distinct_scoring_points": sum(len(s["scoring_points"]) for s in config["selections"]),
        "distinct_sub_questions": len(config["selections"]),
        "relevance_tier_row_counts": tier_counts,
        "personas_per_qid": personas_per_qid,
        "selections": [
            {
                "qid": s["qid"],
                "sub_no": str(s["sub_no"]),
                "j01_relevance": s.get("j01_relevance"),
                "n_points": len(s["scoring_points"]),
                "official_source": s["official_source"],
                "verbatim_verified": True,
            }
            for s in config["selections"]
        ],
        "annotator_files_expected": ["annotator_A.csv", "annotator_B.csv"],
        "min_reviewers_for_irr": 2,
        "honest_scope_note": config.get("honest_scope_note", ""),
        "red_lines": [
            "gold 真值 = 人工 hit/miss；AI 面板只能作预标草稿，绝不单独当金标 (fleiss_kappa=-0.05 是反例)。",
            "盲标：包内不含任何模型预测/先验标签，防锚定。",
            "采分点逐字来自官方答案，build 已 verbatim-verified；单一权威不被打破。",
            "单标注人 = directional，不得称 gold；≥2 标注人 + IRR 才可 promote。",
            "冻结在先：content_hash 冻结采分点定义，标注开始后不得改点集(改则新 slice_version)。",
        ],
    }


CSV_COLUMNS = [
    "row_id", "qid", "sub_no", "student_id", "ability_label", "point_id", "point_text",
    "required_terms", "dimension", "j01_relevance", "sub_question", "student_answer_segment",
    "human_hit", "human_score", "human_note", "human_point_boundary_flag",
]


def _csv_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row.get(k, "") for k in CSV_COLUMNS}
    out["required_terms"] = "；".join(row.get("required_terms") or [])
    return out


def write_bundle(
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    jsonl_path = output_dir / "annotation_package.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    paths["annotation_package"] = jsonl_path

    for name in ("annotator_A.csv", "annotator_B.csv"):
        csv_path = output_dir / name
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow(_csv_row(row))
        paths[name] = csv_path

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["manifest"] = manifest_path

    protocol_path = output_dir / "protocol.md"
    protocol_path.write_text(render_protocol(config, manifest), encoding="utf-8")
    paths["protocol"] = protocol_path
    return paths


def render_protocol(config: dict[str, Any], manifest: dict[str, Any]) -> str:
    tiers = manifest["relevance_tier_row_counts"]
    return f"""# J01 governed gold 标注说明（教研必读）

Slice: `{manifest['slice_version']}`  ·  content_hash: `{manifest['content_hash'][:16]}…`
状态: **{manifest['status']}**  ·  期望标注行数: **{manifest['expected_rows']}**（{manifest['distinct_sub_questions']} 小问 × 10 拟真考生 × 采分点）

## 0. 这是什么 / 为什么要你标
这是全项目**第一份治理级人类金标**，用来取代现有「合成 fixture + AI 面板」（AI 面板 `fleiss_kappa=-0.05`，比随机还差，是反例）。
你逐条判定：**某个拟真考生的作答，是否命中某个采分点**。这批人工金标是后续「编译判分 vs open-world 现编 谁判得更准」A/B 的唯一裁判。

## 1. 你要做什么（每行一判）
每行给你：`采分点原文`(point_text，逐字来自官方答案) + `该考生这一小问的作答`(student_answer_segment)。
你填 3 列（第 4 列可选）：
- **human_hit**：`hit` / `partial` / `miss`
  - `hit`  = 考生作答**踩字命中**该采分点（写出官方/教材术语原文或等价确定表述）。
  - `partial` = 沾边但缺关键词 / 缺半句（如只写结论不写理由、数字错、主体含糊）。
  - `miss` = 未涉及 / 答非所问 / 该小问空着（student_answer_segment 为空 → 一律 miss）。
- **human_score**：可选，该采分点你给的分（缺满分口径可留空，本 slice 主指标是 hit）。
- **human_note**：分歧/边界时写一句原因（便于仲裁）。
- **human_point_boundary_flag**：可选。若你认为这个采分点应该拆/并，写 `split`/`merge`+一句话——**人对点集也有最终权**。

## 2. 踩字口径（命中的边界）
- **命中 = 写出官方术语原文或确定等价**；近义泛化、口号、大白话**不算 hit**（最多 partial）。
  例：官方「季节性施工保证措施」——考生写「冬雨季怎么保证」= partial（缺术语），写「季节性施工保证措施」= hit。
- **数字/主体错 = 不得该分**：如泛浆高度官方「≥500mm」，考生写「≥300mm」= miss（数字错）；主体官方「建设方委托」，考生写「施工单位委托」= miss。
- `required_terms` 只是**提示**（🔵 作答策略，非判分律令），最终由你按踩字口径判。

## 3. 盲标铁律（防锚定 / 防自证）
- 本包**不含任何 AI 判定 / 模型预测 / 先验标签**——你只看采分点原文 + 考生作答，独立判断。
- **≥2 名教研各自独立填一份**（`annotator_A.csv` / `annotator_B.csv`，可再加 `annotator_C.csv`…）。**互相不看对方的标注**。
- 标注期间**不得改采分点集**（content_hash 已冻结）；发现点集有问题写 `human_point_boundary_flag`，由主控起新 slice_version，不就地改。

## 4. 交付后怎么算（你不用管，主控跑）
```bash
python scripts/score_luban_j01_governed_gold.py \\
  --manifest artifacts/luban_governed_gold/j01_v1/manifest.json \\
  --labels artifacts/luban_governed_gold/j01_v1/annotator_A.csv \\
           artifacts/luban_governed_gold/j01_v1/annotator_B.csv \\
  --output artifacts/luban_governed_gold/j01_v1/governed_gold.json
```
产出：真 IRR（Cohen/Fleiss κ）+ 分歧仲裁队列 + governed_gold 工件（带 κ / 标注人 / 时间 / 版本）。
**κ 低的采分点进仲裁，不直接入 gold；单标注人不得称 gold。**

## 5. 覆盖范围（诚实）
- 相关性分层行数：{json.dumps(tiers, ensure_ascii=False)}
  - `core` = 危大工程专项方案(基坑/深基坑方案内容 + 危大未编方案判定)——直击 J01。
  - `adjacent` = 安全管理重大事故隐患条件——J01 家族旁支。
  - `extension` = 雨期施工专项方案(非危大)——专项方案家族，J01 边缘。
- **{config.get('honest_scope_note', '')}**
"""


# ---------------------------------------------------------------------------
def build_package(*, config_path: Path, student_md: Path, output_dir: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    snapshot_dir = PROJECT_ROOT / config["exam_snapshot_dir"]
    samples = parse_student_samples(student_md.read_text(encoding="utf-8"))
    rows = build_rows(config, samples, snapshot_dir)
    manifest = build_manifest(config, rows, student_md=student_md, snapshot_dir=snapshot_dir, config_path=config_path)
    paths = write_bundle(config, rows, manifest, output_dir)
    return {"manifest": manifest, "paths": {k: str(v) for k, v in paths.items()}, "row_count": len(rows)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the J01 governed-gold annotation package.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--student-md", default=None, help="拟真答卷 md (默认取 config.student_md，相对 repo root)")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    config_path = Path(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    student_md = Path(args.student_md) if args.student_md else PROJECT_ROOT / config["student_md"]
    if not student_md.exists():
        print(
            f"[error] 拟真答卷不存在: {student_md}\n"
            "  该数据集被 gitignore(docs/原始数据/2026_副本/)，需在主 checkout 或用 --student-md 指定绝对路径。",
            file=sys.stderr,
        )
        return 2
    result = build_package(config_path=config_path, student_md=student_md, output_dir=Path(args.output_dir))
    print(json.dumps({"row_count": result["row_count"], "paths": result["paths"],
                      "content_hash": result["manifest"]["content_hash"][:16],
                      "tiers": result["manifest"]["relevance_tier_row_counts"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
