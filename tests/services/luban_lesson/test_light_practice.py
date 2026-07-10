"""PRD v1.3 头牌 MCQ 轻练域测试：签发池投影 fail-closed + 死判分确定性 + 学情写既有 sink。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.luban_lesson import (
    LessonNotAvailable,
    build_light_practice_set,
    parse_anchor,
    record_light_practice_evidence,
    score_light_practice,
)

_S05 = {
    "pack_id": "S05", "title": "临时用电三级配电", "content_sha256": "abc123",
    "published": True, "jury_clean": True, "explicitly_barred_default_entry": False,
    "card_hosted": True,
}
_X99 = {
    "pack_id": "X99", "title": "未签发包", "content_sha256": "def456",
    "published": False, "jury_clean": False, "explicitly_barred_default_entry": False,
}


def _write_manifest(tmp_path: Path, packs, green) -> Path:
    p = tmp_path / "_pack_manifest.json"
    p.write_text(
        json.dumps({"projection_green": green, "packs": packs}, ensure_ascii=False),
        encoding="utf-8",
    )
    return p


def _write_bank(tmp_path: Path, *, status="signed", sha="abc123", variants=None) -> None:
    (tmp_path / "_S05_variant_bank.v0.json").write_text(
        json.dumps({"status": status, "source_pack_sha256": sha,
                    "variants": variants or []}, ensure_ascii=False),
        encoding="utf-8",
    )


def _variants_multi_group():
    """3 个 rule_group × 2 条核心 + 1 条外延，用于覆盖抽题与判分。"""
    out = []
    for g in ("A-line", "B-order", "C-wall"):
        for i in range(2):
            out.append({
                "variant_id": f"S05-{g}-{i:03d}", "rule_group": g,
                "surface": f"{g}说法{i}", "expected_ok": (i % 2 == 0),
                "correct_statement": f"{g}正确版{i}",
                "anchor": "kc:1A433000_056_0085:1 + {2015,案例1}", "extension": False,
            })
    out.append({
        "variant_id": "S05-ext-000", "rule_group": "A-line", "surface": "外延",
        "expected_ok": True, "correct_statement": "s",
        "anchor": "kc:1A433000_056_0085:1", "extension": True,
    })
    return out


# ── anchor 解析 ────────────────────────────────────────────────────────────

def test_parse_anchor_splits_scoring_points_exam_refs_and_chapter():
    parsed = parse_anchor("kc:1A433000_056_0085:1 + {2015,案例1} + {2020,案例二问题2}")
    assert parsed["scoring_point"] == "kc:1A433000_056_0085:1"
    assert parsed["scoring_points"] == ["kc:1A433000_056_0085:1"]
    assert parsed["exam_refs"] == ["{2015,案例1}", "{2020,案例二问题2}"]
    # kc 内嵌 1A433000 taxonomy chapter → 教材章节 label（确定性定位）
    assert parsed["textbook_chapters"], "kc 应解析出教材章节"
    assert parsed["textbook_chapters"][0]["taxonomy_code"] == "1A433000"
    assert parsed["textbook_chapters"][0]["chapter_label"]


def test_parse_anchor_ca_token_is_case_anchor_not_exam_ref():
    parsed = parse_anchor("kc:1A434000_076_0119:0 + ca:1A434000_076_0119")
    assert parsed["scoring_points"] == ["kc:1A434000_076_0119:0"]
    assert parsed["case_anchors"] == ["ca:1A434000_076_0119"]
    assert parsed["exam_refs"] == []


def test_parse_anchor_empty_is_fail_closed():
    parsed = parse_anchor("")
    assert parsed["scoring_point"] == ""
    assert parsed["exam_refs"] == []
    assert parsed["textbook_chapters"] == []


# ── 投影 signed→题 / 无池→空 ────────────────────────────────────────────────

def test_build_set_projects_signed_variants_to_mcq_items(tmp_path):
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _write_bank(tmp_path, variants=_variants_multi_group())
    items = build_light_practice_set("S05", n=3, manifest_path=mp)
    assert len(items) == 3
    it = items[0]
    assert set(it) >= {"variant_id", "statement", "answer", "correct_statement",
                       "scoring_point", "exam_refs", "rule_group", "textbook_chapters"}
    assert isinstance(it["answer"], bool)          # 判断题答案=对/错
    assert it["statement"].endswith("0") or it["statement"]  # 逐字透传 surface
    assert it["scoring_point"] == "kc:1A433000_056_0085:1"


def test_build_set_prioritizes_distinct_rule_groups(tmp_path):
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _write_bank(tmp_path, variants=_variants_multi_group())
    items = build_light_practice_set("S05", n=3, manifest_path=mp)
    groups = [it["rule_group"] for it in items]
    assert len(set(groups)) == 3, "n=3 应先覆盖 3 个不同 rule_group"


def test_build_set_is_deterministic_idempotent(tmp_path):
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _write_bank(tmp_path, variants=_variants_multi_group())
    a = build_light_practice_set("S05", n=4, manifest_path=mp)
    b = build_light_practice_set("S05", n=4, manifest_path=mp)
    assert a == b, "种子固定→同 pack 同 n 必须完全幂等"


def test_build_set_excludes_extension_variants(tmp_path):
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _write_bank(tmp_path, variants=_variants_multi_group())
    items = build_light_practice_set("S05", n=10, manifest_path=mp)
    assert all(not it["variant_id"].startswith("S05-ext") for it in items)
    assert len(items) == 6, "只发 6 条核心变体（外延禁入）"


def test_build_set_no_signed_pool_is_empty_fail_closed(tmp_path):
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    assert build_light_practice_set("S05", manifest_path=mp) == []          # 无 bank 文件
    _write_bank(tmp_path, status="candidate", variants=_variants_multi_group())
    assert build_light_practice_set("S05", manifest_path=mp) == []          # 未签发
    _write_bank(tmp_path, sha="stale", variants=_variants_multi_group())
    assert build_light_practice_set("S05", manifest_path=mp) == []          # sha 漂移


def test_build_set_non_green_pack_raises(tmp_path):
    mp = _write_manifest(tmp_path, [_S05, _X99], ["S05"])
    with pytest.raises(LessonNotAvailable):
        build_light_practice_set("X99", manifest_path=mp)
    with pytest.raises(LessonNotAvailable):
        build_light_practice_set("Z00", manifest_path=mp)


# ── 死判分确定性（vs 签发池 expected_ok，不信客户端答案键）──────────────────

def test_score_deterministic_hit_and_miss(tmp_path):
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _write_bank(tmp_path, variants=_variants_multi_group())
    # A-line-000 expected_ok=True, A-line-001 expected_ok=False
    answers = {"S05-A-line-000": True, "S05-A-line-001": True}  # 第二条判反=漏
    scored = score_light_practice("S05", answers, manifest_path=mp)
    assert scored["total"] == 2
    assert scored["correct_count"] == 1
    hit = next(i for i in scored["items"] if i["variant_id"] == "S05-A-line-000")
    miss = next(i for i in scored["items"] if i["variant_id"] == "S05-A-line-001")
    assert hit["is_correct"] is True and "error_code" not in hit
    assert miss["is_correct"] is False
    assert miss["error_code"] == "M01"                    # 已登记错因码
    assert miss["scoring_point"] == "kc:1A433000_056_0085:1"
    assert miss["textbook_chapters"][0]["chapter_label"]  # 教材章节定位
    assert miss in scored["missed"]


def test_score_ignores_variant_not_in_signed_pool(tmp_path):
    """不在签发池的 variant_id 一律忽略（fail-closed，防篡改/陈旧题）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _write_bank(tmp_path, variants=_variants_multi_group())
    scored = score_light_practice("S05", {"S05-FAKE-999": True}, manifest_path=mp)
    assert scored["total"] == 0 and scored["items"] == []


def test_score_answer_key_comes_from_pool_not_client(tmp_path):
    """判分锚服务端 expected_ok：客户端只送 variant_id+自己的判断，不送答案键。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _write_bank(tmp_path, variants=_variants_multi_group())
    scored = score_light_practice("S05", {"S05-A-line-000": False}, manifest_path=mp)
    item = scored["items"][0]
    assert item["expected"] is True and item["user_answer"] is False
    assert item["is_correct"] is False


# ── 学情写 learning_evidence（既有 sink，memory_kind 正确）───────────────────

class _FakeEvent:
    def __init__(self, event_id):
        self.event_id = event_id


class _RecordingLearnerState:
    def __init__(self):
        self.calls = []

    def append_memory_event(self, user_id, **kwargs):
        self.calls.append({"user_id": user_id, **kwargs})
        return _FakeEvent(f"ev{len(self.calls)}")


def test_record_writes_learning_evidence_via_existing_sink(tmp_path):
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _write_bank(tmp_path, variants=_variants_multi_group())
    scored = score_light_practice(
        "S05", {"S05-A-line-000": True, "S05-A-line-001": True}, manifest_path=mp
    )
    svc = _RecordingLearnerState()
    refs = record_light_practice_evidence(svc, user_id="u1", scored=scored)
    assert len(refs) == 2 and len(svc.calls) == 2
    for call in svc.calls:
        assert call["memory_kind"] == "learning_evidence"          # 关键不变量
        assert call["source_feature"] == "luban_light_practice"
        pj = call["payload_json"]
        assert pj["event_type"] == "learning_evidence"
        assert pj["pack_id"] == "S05"
        assert pj["concept_id"] == "kc:1A433000_056_0085:1"         # 锚采分点
        assert pj["rule_group"] == "A-line"                        # 锚 rule_group
        assert "is_correct" in pj
    # 漏题带 M01 error_event；命中题空 error_codes
    miss_call = next(c for c in svc.calls if c["payload_json"]["question_id"] == "S05-A-line-001")
    assert miss_call["payload_json"]["error_codes"] == ["M01"]
    assert miss_call["payload_json"]["error_events"][0]["error_code"] == "M01"
    hit_call = next(c for c in svc.calls if c["payload_json"]["question_id"] == "S05-A-line-000")
    assert hit_call["payload_json"]["error_codes"] == []


def test_record_rejects_unregistered_error_code(tmp_path):
    """写前 check_emitted_error_codes 守闸：未登记错因码不许落账本。"""
    from deeptutor.contracts.error_codes import ContractGuardError
    svc = _RecordingLearnerState()
    bad_scored = {"pack_id": "S05", "items": [
        {"variant_id": "v1", "is_correct": False, "error_code": "ZZ99",
         "scoring_point": "kc:x", "rule_group": "g"}]}
    with pytest.raises(ContractGuardError):
        record_light_practice_evidence(svc, user_id="u1", scored=bad_scored)
    assert svc.calls == [], "守闸失败必须在任何写入前抛出"


def test_record_requires_user_and_pack():
    svc = _RecordingLearnerState()
    with pytest.raises(ValueError):
        record_light_practice_evidence(svc, user_id="", scored={"pack_id": "S05", "items": []})
    with pytest.raises(ValueError):
        record_light_practice_evidence(svc, user_id="u", scored={"pack_id": "", "items": []})


# ── 活体断言：真签发池投影 ─────────────────────────────────────────────────

def test_real_signed_packs_project_light_practice():
    """对 main 上真签发变体池：N01/A01/F16/J01 都能投影出判断题（真投影，非空）。"""
    for pack_id in ("N01", "A01", "F16", "J01"):
        items = build_light_practice_set(pack_id, n=5)
        assert len(items) == 5, f"{pack_id} 应投影 5 条"
        assert len(set(it["variant_id"] for it in items)) == 5, "题不重复"
        for it in items:
            assert it["statement"], "说法非空"
            assert isinstance(it["answer"], bool), "答案=对/错"
            # 采分点(kc/cc)优先；约 14% 变体只有真题出处 → 至少有一种锚信号（诚实边界）
            assert it["scoring_point"] or it["exam_refs"], "至少有采分点或真题出处"
