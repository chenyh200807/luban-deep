from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "lecture_pack",
    REPO / "scripts" / "run_luban_lecture_answer_skill_pack_compile.py",
)
lecture_pack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lecture_pack)


def _write_lecture(root: Path, dirname: str, records: list[dict]) -> Path:
    d = root / dirname
    d.mkdir(parents=True)
    (d / f"{dirname}.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    for page in range(1, 5):
        (d / f"page_{page}_{page}.json").write_text("{}", encoding="utf-8")
    return d


def _record(
    chunk_id: str,
    page: int,
    title: str,
    markdown: str,
    *,
    content_type: str = "rule_numeric",
    trap: str = "不要把阈值和适用条件分开背。",
) -> dict:
    return {
        "chunk_id": chunk_id,
        "content_markdown": f"### {title}\n\n{markdown}",
        "content_type": content_type,
        "granularity": "chunk",
        "exam_matrix": {
            "trap_alert": trap,
            "grading_keywords": [title, "适用条件"],
            "red_lines": ["未引用适用条件不得分"],
            "mnemonics": "先判后答",
        },
        "taxonomy": {
            "node_code": "1A400000",
            "node_name": title,
            "topic": "测试专题",
        },
        "source_meta": {
            "page_num": page,
            "original_anchor": title,
        },
        "meta_info": {
            "core_entity": title,
        },
    }


def test_compile_pilot_pack_excludes_ads_and_pins_manifest(tmp_path: Path) -> None:
    lecture_root = tmp_path / "lectures"
    pdf_root = tmp_path / "pdfs"
    pdf_root.mkdir()

    subject_dir = "2025.test佑森教育《主体结构》专用讲义_v8"
    _write_lecture(
        lecture_root,
        subject_dir,
        [
            _record(
                "LEC_COVER_P0001_000",
                1,
                "全国一级注册建造师执业资格考试",
                "2025佑森教育珠峰班直播课程 专用讲义 版权所有，侵权必究",
                content_type="definition",
            ),
            _record("LEC_TEST_P0001_001", 1, "模板起拱", "跨度不小于4m时起拱。"),
            _record("LEC_TEST_P0001_001", 2, "后浇带模板", "后浇带模板及支架应独立设置。"),
            _record(
                "LEC_AD_P0004_001",
                4,
                "课程资源",
                "小佑题库 佑森在线 官方企微 微信扫码关注 免费听课 在线刷题 售后反馈",
                content_type="definition",
            ),
        ],
    )
    (pdf_root / "2025.test佑森教育《主体结构》专用讲义.pdf").write_text("fake", encoding="utf-8")

    out = tmp_path / "out"
    result = lecture_pack.compile_pack(
        lecture_root=lecture_root,
        pdf_root=pdf_root,
        out_dir=out,
        pilot_titles=["主体结构"],
        version="test-version",
    )

    manifest = json.loads((out / "runtime_supply" / "manifest.json").read_text(encoding="utf-8"))
    inventory = json.loads((out / "source_inventory.json").read_text(encoding="utf-8"))
    shard_path = out / "runtime_supply" / manifest["shards"][0]["path"]
    shard = json.loads(shard_path.read_text(encoding="utf-8"))

    assert result["verdict"] == "WEAK-GO"
    assert manifest["schema_version"] == "luban_lecture_answer_skill_pack.v1"
    assert manifest["status"] == "release_candidate"
    assert manifest["published"] is False
    assert manifest["source_inventory_hash"] == inventory["inventory_hash"]
    assert manifest["shards"][0]["content_hash"] == shard["manifest"]["content_hash"]
    assert manifest["shards"][0]["record_count"] == 2

    units = shard["answer_units"]
    assert [u["source_ref"]["base_chunk_id"] for u in units] == [
        "LEC_TEST_P0001_001",
        "LEC_TEST_P0001_001",
    ]
    assert units[0]["unit_id"] != units[1]["unit_id"]
    assert all(u["authority"] == "lecture_json_primary" for u in units)
    assert all(u["official_score_allowed"] is False for u in units)
    assert "小佑题库" not in json.dumps(units, ensure_ascii=False)
    excluded_ids = {e["base_chunk_id"] for e in shard["non_exam_exclusions"]}
    assert excluded_ids == {"LEC_COVER_P0001_000", "LEC_AD_P0004_001"}
    reasons = {e["base_chunk_id"]: e["reason"] for e in shard["non_exam_exclusions"]}
    assert "cover/meta" in reasons["LEC_COVER_P0001_000"]
    assert "advertising" in reasons["LEC_AD_P0004_001"]


def test_inventory_records_missing_pages_and_pdf_blocker(tmp_path: Path) -> None:
    lecture_root = tmp_path / "lectures"
    pdf_root = tmp_path / "pdfs"
    pdf_root.mkdir()

    _write_lecture(
        lecture_root,
        "2025.test佑森教育《流水施工&网络计划》专用讲义_v8",
        [
            _record("LEC_FLOW_P0001_001", 1, "流水节拍", "流水节拍是时间参数。"),
            _record("LEC_FLOW_P0003_001", 3, "关键线路", "关键线路总时差为0。"),
        ],
    )

    out = tmp_path / "out"
    lecture_pack.compile_pack(
        lecture_root=lecture_root,
        pdf_root=pdf_root,
        out_dir=out,
        pilot_titles=["流水施工&网络计划"],
        version="test-version",
    )

    inventory = json.loads((out / "source_inventory.json").read_text(encoding="utf-8"))
    lecture = inventory["lectures"][0]
    assert lecture["missing_internal_pages"] == [2]
    assert lecture["pdf_status"] == "missing_pdf"
    assert lecture["coverage_status"] == "needs_visual_audit"

    audit = (out / "audit" / "source_inventory.md").read_text(encoding="utf-8")
    assert "流水施工&网络计划" in audit
    assert "missing_pdf" in audit


def test_compile_all_lectures_uses_every_available_aggregate(tmp_path: Path) -> None:
    lecture_root = tmp_path / "lectures"
    pdf_root = tmp_path / "pdfs"
    pdf_root.mkdir()

    _write_lecture(
        lecture_root,
        "2025.test佑森教育《主体结构》专用讲义_v8",
        [_record("LEC_MAIN_P0001_001", 1, "模板起拱", "跨度不小于4m时起拱。")],
    )
    _write_lecture(
        lecture_root,
        "2025.test佑森教育《流水施工&网络计划》专用讲义_v8",
        [_record("LEC_FLOW_P0001_001", 1, "关键线路", "关键线路总时差为0。")],
    )
    (pdf_root / "2025.test佑森教育《主体结构》专用讲义.pdf").write_text("fake", encoding="utf-8")
    (pdf_root / "2025.test佑森教育《流水施工&网络计划》专用讲义.pdf").write_text("fake", encoding="utf-8")

    out = tmp_path / "out"
    result = lecture_pack.compile_pack(
        lecture_root=lecture_root,
        pdf_root=pdf_root,
        out_dir=out,
        pilot_titles=[],
        all_lectures=True,
        version="test-version",
    )

    manifest = json.loads((out / "runtime_supply" / "manifest.json").read_text(encoding="utf-8"))
    assert result["scope"] == "all_lecture_release_candidate"
    assert manifest["scope"] == "all_lecture_release_candidate"
    assert manifest["all_lectures_selected"] is True
    assert sorted(manifest["selected_lectures"]) == ["主体结构", "流水施工&网络计划"]
    assert manifest["shard_count"] == 2
