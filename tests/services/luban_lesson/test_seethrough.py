"""F16 看穿投影域测试:签发闸 fail-closed + 真签发 bank 活体断言(证签发非硬编)。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.luban_lesson import LessonNotAvailable, build_seethrough
from deeptutor.services.luban_lesson.seethrough import build_seethrough_library


def _write_manifest(tmp_path: Path, packs, green) -> Path:
    p = tmp_path / "_pack_manifest.json"
    p.write_text(json.dumps({"projection_green": green, "packs": packs}, ensure_ascii=False), encoding="utf-8")
    return p


_F16 = {"pack_id": "F16", "title": "防水卷材分层与施工工序", "content_sha256": "abc123"}


def _bank(tmp_path: Path, status="signed", sha="abc123"):
    (tmp_path / "_F16_seethrough_bank.v0.json").write_text(
        json.dumps({
            "schema_version": "luban-f16-seethrough-bank.v0",
            "pack_id": "F16", "status": status, "source_pack_sha256": sha,
            "items": [{"variant_id": "F16-D1-seethrough", "day": 1, "stem": "s",
                       "options": [{"option_id": "A", "text": "a"}], "correct_option_id": "A"}],
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def test_non_green_pack_fail_closed(tmp_path):
    mp = _write_manifest(tmp_path, [_F16], [])  # 非绿灯
    with pytest.raises(LessonNotAvailable):
        build_seethrough("F16", manifest_path=mp)


def test_candidate_bank_rejected_same_as_missing(tmp_path):
    mp = _write_manifest(tmp_path, [_F16], ["F16"])
    _bank(tmp_path, status="candidate")  # 未签发
    with pytest.raises(LessonNotAvailable):
        build_seethrough("F16", manifest_path=mp)


def test_sha_drift_rejected_same_as_missing(tmp_path):
    mp = _write_manifest(tmp_path, [_F16], ["F16"])
    _bank(tmp_path, status="signed", sha="stale-old-sha")  # pack 修订后旧签发失效
    with pytest.raises(LessonNotAvailable):
        build_seethrough("F16", manifest_path=mp)


def test_signed_bank_projects(tmp_path):
    mp = _write_manifest(tmp_path, [_F16], ["F16"])
    _bank(tmp_path, status="signed", sha="abc123")
    vm = build_seethrough("F16", manifest_path=mp)
    assert vm["pack_id"] == "F16" and vm["day_count"] == 1
    assert vm["days"][0]["variant_id"] == "F16-D1-seethrough"


# ── 真签发 F16 看穿 bank 活体断言(证:内容确签发非硬编 + 红线守法) ──

_REGISTERED = None
_FORBIDDEN = ("看穿", "识破", "揭穿", "露馅")


def _registered_codes():
    from deeptutor.contracts.error_codes import ERROR_CODE_REGISTRY
    return set(ERROR_CODE_REGISTRY.keys())


def test_real_signed_f16_seethrough_projects_5_days():
    """对 main 上真签发的 F16 看穿 bank:5 天齐、结构完整、红线可证伪。"""
    lib = build_seethrough_library()
    if not any(p["pack_id"] == "F16" for p in lib["packs"]):
        pytest.skip("F16 看穿 bank 未签发(本环境)")
    vm = build_seethrough("F16")
    assert vm["day_count"] == 5, "F16 应有 5 天看穿内容"
    days = {d["day"]: d for d in vm["days"]}
    assert set(days) == {1, 2, 3, 4, 5}

    registered = _registered_codes()
    for d in vm["days"]:
        # 学员端文案无审视硬词(红线)
        learner_text = " ".join([
            str(d.get("today_cut") or ""), str(d.get("stem") or ""), str(d.get("warm_correction") or ""),
            *[str(o.get("text") or "") for o in d.get("options") or []],
        ])
        for w in _FORBIDDEN:
            assert w not in learner_text, f"D{d['day']} 学员端出现审视硬词: {w}"
        # 错因码 ∈ ERROR_CODE_REGISTRY(红线:不新建)
        for dis in d.get("distractors") or []:
            assert dis.get("error_code") in registered, f"D{d['day']} 未登记错因: {dis.get('error_code')}"

    # MCQ 天(1/2/3/5)恰 4 选项 + 正确项 ∈ 选项
    for day_no in (1, 2, 3, 5):
        d = days[day_no]
        opt_ids = [o["option_id"] for o in d["options"]]
        assert len(d["options"]) == 4 and d["correct_option_id"] in opt_ids

    # Day2 迎水面 = 诚实延伸:evidence chunk 带 is_extension + true_source_pack
    d2_chunks = days[2]["evidence"]["syllabus_chunks"]
    assert any(c.get("is_extension") and c.get("true_source_pack") for c in d2_chunks), \
        "Day2 迎水面应为诚实延伸(is_extension + true_source_pack)"

    # Day4 半写:诚实标注 + 已签发 P10/P11 采分点
    d4 = days[4]
    assert d4.get("answer_mode") == "semi_write"
    assert "非官方" in (d4.get("honesty_label") or ""), "Day4 须诚实标注非官方阅卷"
    assert {sp["point_id"] for sp in d4.get("scoring_points") or []} == {"P10", "P11"}
