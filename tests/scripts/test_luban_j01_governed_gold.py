from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.build_luban_j01_governed_gold_slice import (
    DEFAULT_CONFIG,
    build_package,
    load_official_answer,
    parse_student_samples,
    split_numbered,
    verify_points_verbatim,
)
from scripts.estimate_luban_j01_gold_power import build_report, mcnemar_power
from scripts.score_luban_j01_governed_gold import cohen_kappa, fleiss_kappa, score

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _minimal_config(tmp_path: Path) -> Path:
    """A 1-selection config (Q2024-02 s2) so end-to-end tests need only one qid in the md."""
    full = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    sel = next(s for s in full["selections"] if s["qid"] == "Q2024-02")
    cfg = {**full, "selections": [sel]}
    path = tmp_path / "mini_config.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return path

# A tiny self-contained 拟真答卷 md matching the real format (2 personas × 1 J01 sub-question).
_FAKE_MD = """### Q2024-02｜网络计划、基坑专项方案与冬期施工

#### 样本元数据

- 样本ID：`Q2024-02__S01`
- 学生ID：`S01`
- ability_label：`high`

#### 题目

【问题】
1. 网络计划题。
2. 答出项目部基坑专项施工方案中不妥之处的正确做法。

#### 回答

作答：
1. B→E→I。
2. (1) 排桩混凝土灌注桩身混凝土强度不应低于C25。(2) 应先施工灌注桩，后施工截水帷幕。

#### 本题水平判断
- 学生归类：高水平

---

### Q2024-02｜网络计划、基坑专项方案与冬期施工

#### 样本元数据

- 样本ID：`Q2024-02__S02`
- 学生ID：`S02`
- ability_label：`low`

#### 题目

【问题】
2. 答出项目部基坑专项施工方案中不妥之处的正确做法。

#### 回答

作答：
1. 不会。

#### 本题水平判断
- 学生归类：低水平
"""


# ---------------------------------------------------------------------------
# parsing / extraction
# ---------------------------------------------------------------------------
def test_split_numbered_handles_paren_and_dot():
    # markers are only split at line starts (mid-line digits like "(2)"/"C25" must NOT split)
    out = split_numbered("1. aaa\n2、bbb\n3．ccc")
    assert out["1"] == "aaa"
    assert out["2"] == "bbb"
    assert out["3"] == "ccc"
    # inline enumeration inside an answer is preserved, not shredded
    inline = split_numbered("2. (1) 强度不低于C25。(2) 先灌注桩")
    assert inline["2"] == "(1) 强度不低于C25。(2) 先灌注桩"


def test_parse_student_samples_extracts_sub_answers():
    samples = parse_student_samples(_FAKE_MD)
    assert len(samples) == 2
    s01 = next(s for s in samples if s["student_id"] == "S01")
    assert "排桩混凝土灌注桩身混凝土强度不应低于C25" in s01["sub_answers"]["2"]
    # low-ability persona did not answer sub 2 -> missing key (=> miss downstream)
    s02 = next(s for s in samples if s["student_id"] == "S02")
    assert "2" not in s02["sub_answers"]


def test_verify_points_verbatim_gate_rejects_fabrication():
    official = "(1) 排桩混凝土灌注桩身混凝土强度不应低于C25。(2) 应先施工灌注桩。"
    # verbatim slice passes (whitespace-normalized)
    verify_points_verbatim(official, [{"point_id": "P1", "point_text": "排桩混凝土灌注桩身混凝土强度不应低于C25"}])
    # a fabricated / paraphrased point fails closed
    with pytest.raises(ValueError):
        verify_points_verbatim(official, [{"point_id": "PX", "point_text": "混凝土强度应大于C30"}])


def test_load_official_answer_real_snapshot_blob_and_exercise():
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    snap = PROJECT_ROOT / config["exam_snapshot_dir"]
    # blob-style (Q2024-02 s2)
    blob = load_official_answer(snap, 2024, {"chunk_id": "EXAM_1A433000_P0012_02", "exercise_index": 0, "blob_section": "2"})
    assert "泛浆高度不应小于500mm" in blob.replace(" ", "")
    # per-exercise style (Q2025-05 s4 -> exercise 3)
    ex = load_official_answer(snap, 2025, {"chunk_id": "EXAM_1A436000_P0017_01", "exercise_index": 3})
    assert "危险性较大的分部分项工程未编制、未审核专项施工方案" in ex


def test_config_points_are_all_verbatim_against_snapshot():
    """The committed pinned config must pass the anti-fabrication gate against the real snapshot."""
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    snap = PROJECT_ROOT / config["exam_snapshot_dir"]
    for sel in config["selections"]:
        official = load_official_answer(snap, int(sel["year"]), sel["official_source"])
        verify_points_verbatim(official, sel["scoring_points"])  # raises if any drift


# ---------------------------------------------------------------------------
# end-to-end build
# ---------------------------------------------------------------------------
def test_build_package_end_to_end(tmp_path: Path):
    md = tmp_path / "fake_student.md"
    md.write_text(_FAKE_MD, encoding="utf-8")
    out = tmp_path / "pkg"
    result = build_package(config_path=_minimal_config(tmp_path), student_md=md, output_dir=out)

    # only Q2024-02 has personas in the fake md -> 5 points × 2 personas = 10 rows
    assert result["row_count"] == 10
    manifest = result["manifest"]
    assert manifest["status"] == "awaiting_human_labels"
    assert manifest["content_hash"]
    assert "student_md" in manifest["source_hashes"]

    rows = [json.loads(line) for line in (out / "annotation_package.jsonl").read_text(encoding="utf-8").splitlines()]
    # blind: no model prediction / prior label fields leak in
    for r in rows:
        assert r["human_hit"] == ""
        assert "ai_prediction" not in r and "prediction" not in r
    # low-ability persona S02 gets rows with EMPTY segment (=> annotator marks miss)
    s02 = [r for r in rows if r["student_id"] == "S02"]
    assert s02 and all(r["student_answer_segment"] == "" for r in s02)

    # two independent annotator templates exist and are blank
    for name in ("annotator_A.csv", "annotator_B.csv"):
        reader = list(csv.DictReader((out / name).open(encoding="utf-8")))
        assert len(reader) == 10
        assert all(row["human_hit"] == "" for row in reader)


def test_build_fails_closed_when_no_personas(tmp_path: Path):
    md = tmp_path / "empty.md"
    md.write_text("### Q2099-99｜nothing\n", encoding="utf-8")
    with pytest.raises(ValueError):
        build_package(config_path=DEFAULT_CONFIG, student_md=md, output_dir=tmp_path / "o")


# ---------------------------------------------------------------------------
# IRR / kappa
# ---------------------------------------------------------------------------
def test_cohen_kappa_perfect_and_chance():
    cats = ("hit", "partial", "miss")
    assert cohen_kappa(["hit", "miss", "hit"], ["hit", "miss", "hit"], cats) == 1.0
    # total disagreement structure -> non-positive kappa
    k = cohen_kappa(["hit", "hit", "miss", "miss"], ["miss", "miss", "hit", "hit"], cats)
    assert k <= 0.0


def test_fleiss_kappa_perfect_agreement():
    cats = ("hit", "partial", "miss")
    items = [["hit", "hit", "hit"], ["miss", "miss", "miss"], ["partial", "partial", "partial"]]
    assert fleiss_kappa(items, cats) == 1.0


def _write_labels(path: Path, rows: list[dict], hits: dict[str, str]):
    cols = ["row_id", "qid", "sub_no", "student_id", "point_id", "point_text", "j01_relevance",
            "human_hit", "human_score", "human_note", "human_point_boundary_flag"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            base = {c: r.get(c, "") for c in cols}
            base["human_hit"] = hits.get(r["row_id"], "")
            w.writerow(base)


def test_score_governed_gold_agreement_and_adjudication(tmp_path: Path):
    md = tmp_path / "fake.md"
    md.write_text(_FAKE_MD, encoding="utf-8")
    out = tmp_path / "pkg"
    build_package(config_path=_minimal_config(tmp_path), student_md=md, output_dir=out)
    rows = [json.loads(line) for line in (out / "annotation_package.jsonl").read_text(encoding="utf-8").splitlines()]

    # annotator A: all miss; annotator B: agree on all but ONE row (disagreement -> adjudication)
    a_hits = {r["row_id"]: "miss" for r in rows}
    b_hits = dict(a_hits)
    flip = rows[0]["row_id"]
    b_hits[flip] = "hit"
    _write_labels(out / "annotator_A.csv", rows, a_hits)
    _write_labels(out / "annotator_B.csv", rows, b_hits)

    result = score(manifest_path=out / "manifest.json", label_paths=[out / "annotator_A.csv", out / "annotator_B.csv"])
    assert result["validation"]["meets_min_reviewers"] is True
    assert result["governance"]["gold_row_count"] == 9  # 10 rows, 1 disagreement
    assert result["governance"]["adjudication_count"] == 1
    assert result["adjudication_queue"][0]["row_id"] == flip
    assert result["status"] == "gold_partial_needs_adjudication"
    assert result["irr"]["hit_3category"]["kappa"] is not None


def test_score_single_reviewer_is_directional_not_gold(tmp_path: Path):
    md = tmp_path / "fake.md"
    md.write_text(_FAKE_MD, encoding="utf-8")
    out = tmp_path / "pkg"
    build_package(config_path=_minimal_config(tmp_path), student_md=md, output_dir=out)
    rows = [json.loads(line) for line in (out / "annotation_package.jsonl").read_text(encoding="utf-8").splitlines()]
    _write_labels(out / "annotator_A.csv", rows, {r["row_id"]: "miss" for r in rows})
    result = score(manifest_path=out / "manifest.json", label_paths=[out / "annotator_A.csv"])
    assert result["status"] == "directional_single_reviewer"
    assert result["governance"]["gold_row_count"] == 0  # single reviewer never becomes gold


# ---------------------------------------------------------------------------
# power
# ---------------------------------------------------------------------------
def test_mcnemar_power_monotonic_in_n():
    p_small = mcnemar_power(80, 0.30, 0.70)
    p_large = mcnemar_power(400, 0.30, 0.70)
    assert 0.0 <= p_small <= p_large <= 1.0


def test_power_report_flags_underpowered_and_recommends_expansion():
    report = build_report(raw_n=150, core_n=90, clusters=4)
    assert report["n_for_80pct_power_at_disc0.30_psi0.70"] is not None
    assert "BORDERLINE" in report["verdict"]["headline"]
    assert "design effect" in report["verdict"]["clustering_risk"].lower()
