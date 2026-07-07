"""复习核心 gap Layer 1 —— 实务闯关「全量作答」档（档位③）判分内核链路测试。

覆盖两条诚实边界：
1. 注入 ``grading_key.scoring_points`` 的 fixture → curated_rubric → 判分内核 →
   ``write_grading_error_events``（source_feature=construction_grading，promoting）→
   synthesize 后 weak_points 含该采分点 concept + 错题本落项。
2. 真实变体包无签发采分点供给 → grading_key None → 内核 open_skill 兜底 →
   证据 ``L0_observed`` / ``stable_truth_eligible=False``（如实封顶，被 certified
   闸挡，非 bug）。

同时钉死红线：对外投影剥离 keywords / required_terms（防再认泄漏）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.learner_state.service import LearnerStateService
import deeptutor.services.luban_lesson.full_answer_grading as fag
from deeptutor.services.luban_lesson.full_answer_grading import (
    FullAnswerNotAvailable,
    grade_full_answer,
    resolve_full_answer_inputs,
)

_PACK_ID = "T01"
_VARIANT_ID = "T01-A-hoist-000"
_NODE = "1A413030"
_SHA = "deadbeefcafefeed0011223344556677"


class _PathServiceStub:
    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def project_root(self):
        return self._root

    def get_user_root(self):
        return self._root

    def get_tutor_state_root(self):
        return self._root / "tutor_state"

    def get_learner_state_root(self):
        return self._root / "learner_state"

    def get_learner_state_outbox_db(self):
        return self._root / "runtime" / "outbox.db"

    def get_guide_dir(self):
        path = self._root / "workspace" / "guide"
        path.mkdir(parents=True, exist_ok=True)
        return path


class _FakeMemberService:
    def get_profile(self, user_id: str):
        return {"user_id": user_id, "display_name": "陈同学", "exam_date": ""}

    def get_today_progress(self, user_id: str):
        return {"today_done": 0, "daily_target": 30, "streak_days": 0}

    def get_chapter_progress(self, user_id: str):
        return []


class _DisabledCoreStore:
    is_configured = False


class _FakeMistakeBook:
    def __init__(self) -> None:
        self.saved: list[dict[str, object]] = []

    def save_item(self, **kwargs: object) -> dict[str, object]:
        self.saved.append(dict(kwargs))
        return {"ok": True}


def _make_service(tmp_path: Path) -> LearnerStateService:
    return LearnerStateService(
        path_service=_PathServiceStub(tmp_path),
        member_service=_FakeMemberService(),
        core_store=_DisabledCoreStore(),
    )


def _write_signed_pack(tmp_path: Path) -> Path:
    """写一个绿灯 + 已签发变体池 fixture，返回 manifest 路径。"""
    manifest_dir = tmp_path / "supply"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    bank = {
        "schema_version": 0,
        "pack_id": _PACK_ID,
        "status": "signed",
        "source_pack_sha256": _SHA,
        "variants": [
            {
                "variant_id": _VARIANT_ID,
                "rule_group": "A-hoist",
                "surface": "预制桩桩身混凝土强度达设计强度的50%时开始起吊",
                "expected_ok": False,
                "correct_statement": "桩身混凝土强度达设计强度的70%方可起吊，达100%方可运输、打桩",
                "anchor": f"kc:{_NODE}_090_0165:0",
                "extension": False,
            }
        ],
    }
    (manifest_dir / f"_{_PACK_ID}_variant_bank.v0.json").write_text(
        json.dumps(bank, ensure_ascii=False), encoding="utf-8"
    )
    manifest = {
        "projection_green": [_PACK_ID],
        "packs": [
            {"pack_id": _PACK_ID, "title": "预制桩起吊", "content_sha256": _SHA, "card_hosted": False}
        ],
    }
    manifest_path = manifest_dir / "_pack_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest_path


# ── 边界 1: resolve 只认签发池 ────────────────────────────────────────────────


def test_resolve_full_answer_inputs_builds_row_from_signed_variant(tmp_path) -> None:
    manifest_path = _write_signed_pack(tmp_path)
    row, grading_key, evidence_rows = resolve_full_answer_inputs(
        _PACK_ID, _VARIANT_ID, manifest_path=manifest_path
    )

    assert row["question_id"] == _VARIANT_ID
    assert row["node_code"] == _NODE  # 从 anchor 取规范节点码
    assert "70%" in row["correct_answer"]
    # 真实包无签发采分点供给 → 既有 resolver 返回 None（honest，落 open_skill）
    assert grading_key is None
    # anchor → kb_chunk RAG 接地证据
    assert evidence_rows and evidence_rows[0]["source"] == "kb_chunk"
    assert evidence_rows[0]["field"] == f"kc:{_NODE}_090_0165:0"


def test_resolve_full_answer_inputs_fail_closed_on_unknown_variant(tmp_path) -> None:
    manifest_path = _write_signed_pack(tmp_path)
    with pytest.raises(FullAnswerNotAvailable):
        resolve_full_answer_inputs(_PACK_ID, "NOPE-999", manifest_path=manifest_path)


# ── 边界 2: curated_rubric（注入 grading_key）→ promoting 全链 ────────────────


def test_curated_full_answer_promotes_weak_point_and_mistake_book(tmp_path, monkeypatch) -> None:
    manifest_path = _write_signed_pack(tmp_path)
    service = _make_service(tmp_path)
    mistake_book = _FakeMistakeBook()

    # 模拟「当签发采分点供给接线后」的 grading_key（既有 resolver 缝的产物形状）。
    # 不指向任何 published:False 供给——纯 fixture，只为证明 curated → promoting 全链。
    injected = {
        "scoring_points": [
            {"criterion": "混凝土强度达70%方可起吊", "keywords": ["70%"], "score": 1.0},
            {"criterion": "达100%方可运输打桩", "keywords": ["100%"], "score": 1.0},
        ]
    }
    monkeypatch.setattr(fag, "_resolve_grading_key", lambda _qid: injected)

    user_id = "student_layer1"
    # 同一漏点作答两次（漏「70%」采分点）→ 达 L1_repeated 阈值。
    verdicts = []
    for _ in range(2):
        verdicts.append(
            grade_full_answer(
                pack_id=_PACK_ID,
                variant_id=_VARIANT_ID,
                answer_text="达100%才可以运输打桩",  # 命中第二点、漏第一点(70%)
                user_id=user_id,
                learner_state_service=service,
                mistake_book_service=mistake_book,
                manifest_path=manifest_path,
            )
        )

    last = verdicts[-1]
    assert last["grading_mode"] == "curated_rubric"
    assert last["grading_source"] == "grading_key"
    assert last["writeback_count"] == 1
    # 逐采分点投影存在且**剥离**了 keywords/required_terms（防再认泄漏红线）
    criteria = {p["criterion"] for p in last["scoring_points"]}
    assert "混凝土强度达70%方可起吊" in criteria
    for point in last["scoring_points"]:
        assert "keywords" not in point
        assert "required_terms" not in point
        assert "evidence_text" not in point

    # construction_grading learning_evidence 真写出
    events = service.list_memory_events(user_id, limit=50)
    ev_features = {e.source_feature for e in events if e.memory_kind == "learning_evidence"}
    assert "construction_grading" in ev_features

    # synthesize 后 weak_points 含该采分点 concept
    projection = service.synthesize_learning_truth(user_id, dry_run=True)["projection"]
    weak_concepts = {str(w.get("concept_id") or "") for w in projection.get("weak_points") or []}
    assert _NODE in weak_concepts, projection.get("weak_points")

    # 错题本落项（错因银行）
    assert mistake_book.saved, "expected mistake book auto-write on missed scoring point"


# ── 边界 3: 真实包无签发采分点供给 → 非 curated → L0 封顶（诚实标注）─────────────


def test_real_pack_without_signed_scoring_points_is_l0_capped(tmp_path) -> None:
    """诚实边界：真实包 grading_key 解析为 None → 内核落 projected_rubric（从签发
    correct_statement 投影关键词，非 curated_rubric）→ 证据 L0 封顶，不进稳定掌握。
    这正是 certified-grading 闸的正确行为（非 bug）：没有签发采分点供给就没有
    curated 权威，promotion 到稳定/官方真值被拦。"""
    manifest_path = _write_signed_pack(tmp_path)
    service = _make_service(tmp_path)
    mistake_book = _FakeMistakeBook()

    verdict = grade_full_answer(
        pack_id=_PACK_ID,
        variant_id=_VARIANT_ID,
        answer_text="我一时想不起来具体数值",
        user_id="student_honest",
        learner_state_service=service,
        mistake_book_service=mistake_book,
        manifest_path=manifest_path,
    )

    # 无签发 grading_key.scoring_points → 绝不是 curated_rubric
    assert verdict["grading_source"] != "grading_key"
    assert verdict["grading_mode"] in {"projected_rubric", "open_skill"}
    # 证据如实 L0 封顶：不进稳定/官方掌握（certified 闸正确挡）
    assert verdict["evidence_level"] == "L0_observed"
    assert verdict["stable_truth_eligible"] is False
    # 对外投影同样不泄漏 keywords/required_terms
    for point in verdict["scoring_points"]:
        assert "keywords" not in point
        assert "required_terms" not in point
