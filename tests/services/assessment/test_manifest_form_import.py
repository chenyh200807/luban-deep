"""manifest 钉选导入(表单 v2 续命件):构建、sha 失配拒绝、案例自带题面。"""

from __future__ import annotations

import json
from typing import Any

import pytest

from deeptutor.services.assessment import manifest_form_import as mfi
from deeptutor.services.assessment.blueprint import (
    MANIFEST_SOURCE_TYPE,
    get_assessment_blueprint,
)
from deeptutor.services.assessment.blueprint_service import (
    AssessmentBlueprintService,
    QuestionCandidate,
    _build_scored_question,
    _form_from_persisted_row,
    _form_to_persisted_row,
)
from tests.services.assessment.test_compiled_practice_provider import _item

BLUEPRINT = get_assessment_blueprint("pass_readiness_architecture_v2")
MANIFEST_SHA = "f" * 64

_FAMILY_PACKS = {
    "主体结构": "C01",
    "安全": "J01",
    "进度": "N01",
    "质量验收": "G01",
    "防水": "F02",
}

# 选编定稿 family_matrix 的单选配比(与 blueprint v2 section counts 一致)。
_FAMILY_SINGLE_COUNTS = {
    "主体结构": 5,
    "安全": 4,
    "进度": 3,
    "质量验收": 4,
    "防水": 4,
}

_MATERIALS = {
    "CASE_A": {"family": "主体结构", "text": "某高层办公楼后浇带专项方案载明:①…⑤…。"},
    "CASE_B": {"family": "质量验收", "text": "某办公楼各单位质量检测管理做了以下工作:①…。"},
    "CASE_C": {"family": "进度", "text": "某项目双代号网络计划关键线路与工期资料如下:…。"},
}


def _authorities() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for family, pack in _FAMILY_PACKS.items():
        out[pack] = {
            "items": [
                _item(f"{pack}-v{i}", fact_id=f"{pack}-fact-{i}") for i in range(5)
            ]
        }
    return out


def _compiled_loader(authorities: dict[str, Any]):
    def load(pack_id: str) -> dict[str, Any]:
        pack = str(pack_id or "").strip().upper()
        if pack not in authorities:
            raise mfi.ManifestFormImportError(f"compiled_authority_missing:{pack}")
        return authorities[pack]

    return load


def _bank_row(qb_id: int) -> dict[str, Any]:
    options = [
        {"key": key, "value": f"选项{key} of qb{qb_id}"} for key in ("A", "B", "C", "D")
    ]
    return {
        "id": qb_id,
        "question_stem": f"练习册多选题干 {qb_id}",
        "question_type": "multi_choice",
        "source_type": "textbook_exercise",
        "options": options,
        "correct_answer": "AB",
        "content_hash": f"dbhash-{qb_id}",
        "node_code": "1A413040",
        "source_meta": {},
    }


def _bank_task_sha(row: dict[str, Any]) -> str:
    return mfi._normalized_sha256(
        str(row["question_stem"]) + json.dumps(mfi._norm_bank_options(row), ensure_ascii=False)
    )


def _case_sha(material_id: str, task_id: str) -> str:
    return mfi._normalized_sha256(_MATERIALS[material_id]["text"] + task_id)


def _manifest() -> dict[str, Any]:
    tasks: list[dict[str, Any]] = [
        {"task_id": f"P{i}", "kind": "profile_probe", "scored": False} for i in (1, 2, 3)
    ]
    index = 0
    for family, pack in _FAMILY_PACKS.items():
        for i in range(_FAMILY_SINGLE_COUNTS[family]):
            index += 1
            tasks.append(
                {
                    "task_id": f"S{index:02d}",
                    "kind": "compiled_practice_item",
                    "family": family,
                    "pack_id": pack,
                    "answer_type": "single_choice",
                    "scored": True,
                    "source": {
                        "kind": "compiled_practice_authority",
                        "variant_id": f"{pack}-v{i}",
                    },
                    "content_sha256": "c" * 64,  # 与 _item 固定 content_sha256 一致
                }
            )
    for i in range(10):
        row = _bank_row(14000 + i)
        tasks.append(
            {
                "task_id": f"M{i + 1:02d}",
                "kind": "bank_transitional_multi",
                "family": "主体结构",
                "answer_type": "multiple_choice",
                "scored": True,
                "source": {
                    "kind": "questions_bank",
                    "qb_id": row["id"],
                    "db_content_hash": row["content_hash"],
                },
                "stem": row["question_stem"],
                "content_sha256": _bank_task_sha(row),
            }
        )
    case_specs = [
        ("CA1", "CASE_A", "real_exam_case_variant", "multiple_choice", "BCD"),
        ("CA2", "CASE_A", "compiled_practice_item_variant", "single_choice", "B"),
        ("CB1", "CASE_B", "real_exam_case_variant", "multiple_choice", "CD"),
        ("CB2", "CASE_B", "real_exam_case_variant", "multiple_choice", "ACE"),
        ("CC1", "CASE_C", "real_exam_case_variant", "single_choice", "A"),
        ("CC2", "CASE_C", "real_exam_case_variant", "single_choice", "B"),
    ]
    for task_id, material, kind, answer_type, answer_key in case_specs:
        n_options = 5 if len(answer_key) > 1 else 4
        source: dict[str, Any] = {"kind": kind, "year": 2018, "exam_anchor": "案例(三)问题3"}
        family = _MATERIALS[material]["family"]
        if kind == "compiled_practice_item_variant":
            source["base_variant_id"] = f"{_FAMILY_PACKS[family]}-v4"
            source["base_content_sha256"] = "c" * 64
        tasks.append(
            {
                "task_id": task_id,
                "kind": "case_variant",
                "family": family,
                "pack_id": _FAMILY_PACKS[family],
                "material": material,
                "answer_type": answer_type,
                "scored": True,
                "source": source,
                "stem": f"针对{task_id},选出能得分的作答。",
                "options": [
                    {"key": chr(65 + j), "value": f"{task_id} 选项{chr(65 + j)}"}
                    for j in range(n_options)
                ],
                "answer_key": answer_key,
                "content_sha256": _case_sha(material, task_id),
                "difficulty": "真题2018案例锚",
            }
        )
    return {
        "schema": mfi.MANIFEST_SCHEMA,
        "form_id": "pass_readiness_form_main_v2",
        "blueprint": BLUEPRINT.version,
        "materials": {key: dict(value) for key, value in _MATERIALS.items()},
        "tasks": tasks,
    }


def _resolver(rows: dict[int, dict[str, Any]] | None = None):
    table = rows if rows is not None else {14000 + i: _bank_row(14000 + i) for i in range(10)}

    def resolve(qb_id: int) -> dict[str, Any] | None:
        return table.get(int(qb_id))

    return resolve


def _build(manifest: dict[str, Any] | None = None, **overrides: Any):
    kwargs: dict[str, Any] = dict(
        blueprint=BLUEPRINT,
        manifest_sha256=MANIFEST_SHA,
        bank_row_resolver=_resolver(),
        compiled_loader=_compiled_loader(_authorities()),
    )
    kwargs.update(overrides)
    return mfi.build_manifest_form(manifest or _manifest(), **kwargs)


def test_manifest_builds_full_39_unit_form_with_pinned_sources() -> None:
    form = _build()
    assert form.form_id == "pass_readiness_form_main_v2"
    assert len(form.units) == 39
    scored = [unit for unit in form.units if unit.scored]
    assert len(scored) == 36
    by_section: dict[str, int] = {}
    for unit in form.units:
        by_section[unit.section_id] = by_section.get(unit.section_id, 0) + 1
    assert by_section == {section.id: section.count for section in BLUEPRINT.sections}
    # 20 单选钉到 manifest 指定 variant_id(非自动选题)。
    compiled = [
        unit.item
        for unit in scored
        if isinstance(unit.item, QuestionCandidate)
        and unit.item.source_type == "COMPILED_PRACTICE"
    ]
    assert len(compiled) == 20
    assert {c.source_question_id for c in compiled} == {
        f"{pack}-v{i}"
        for family, pack in _FAMILY_PACKS.items()
        for i in range(_FAMILY_SINGLE_COUNTS[family])
    }


def test_case_tasks_carry_manifest_face_and_manifest_provenance() -> None:
    form = _build()
    cases = [
        unit.item
        for unit in form.units
        if isinstance(unit.item, QuestionCandidate)
        and unit.item.source_type == MANIFEST_SOURCE_TYPE
    ]
    assert len(cases) == 6
    ca1 = next(c for c in cases if c.source_meta["manifest_task_id"] == "CA1")
    # 案例材料并入题干(v1 作答链无独立材料渲染面)。
    assert _MATERIALS["CASE_A"]["text"] in ca1.question_stem
    assert ca1.answer == "BCD"
    assert ca1.question_type == "multi_choice"
    assert ca1.source_meta["provenance"] == f"manifest:{MANIFEST_SHA}"
    section = next(s for s in BLUEPRINT.sections if s.id == "pr2_case_quality")
    client, stored = _build_scored_question("q_01", section, ca1)
    assert client["provenance"]["source_table"] == f"manifest:{MANIFEST_SHA}"
    assert "answer" not in client and stored["answer"] == "BCD"


def test_case_sections_assigned_by_family_topic_match() -> None:
    form = _build()
    by_section: dict[str, set[str]] = {}
    for unit in form.units:
        item = unit.item
        if isinstance(item, QuestionCandidate) and item.source_type == MANIFEST_SOURCE_TYPE:
            by_section.setdefault(unit.section_id, set()).add(
                str(item.source_meta["manifest_task_id"])
            )
    assert by_section["pr2_case_quality"] == {"CB1", "CB2"}  # 质量验收 topic 命中
    assert by_section["pr2_case_schedule"] == {"CC1", "CC2"}  # 进度 topic 命中
    assert by_section["pr2_case_safety"] == {"CA1", "CA2"}  # 主体结构落剩余位


def test_compiled_content_sha_mismatch_fails_the_form() -> None:
    manifest = _manifest()
    task = next(t for t in manifest["tasks"] if t["task_id"] == "S01")
    task["content_sha256"] = "0" * 64
    with pytest.raises(mfi.ManifestFormImportError, match="compiled_content_sha256_mismatch"):
        _build(manifest)


def test_compiled_item_must_be_eligible() -> None:
    authorities = _authorities()
    authorities["C01"]["items"][0]["revoked"] = True
    with pytest.raises(mfi.ManifestFormImportError, match="compiled_item_not_eligible"):
        _build(compiled_loader=_compiled_loader(authorities))


def test_bank_db_content_hash_mismatch_fails() -> None:
    rows = {14000 + i: _bank_row(14000 + i) for i in range(10)}
    rows[14000]["content_hash"] = "drifted"
    with pytest.raises(mfi.ManifestFormImportError, match="bank_db_content_hash_mismatch"):
        _build(bank_row_resolver=_resolver(rows))


def test_bank_face_sha_mismatch_fails() -> None:
    rows = {14000 + i: _bank_row(14000 + i) for i in range(10)}
    rows[14000]["question_stem"] = "被换过的题干"
    with pytest.raises(mfi.ManifestFormImportError, match="bank_content_sha256_mismatch"):
        _build(bank_row_resolver=_resolver(rows))


def test_bank_row_missing_fails() -> None:
    with pytest.raises(mfi.ManifestFormImportError, match="bank_row_missing"):
        _build(bank_row_resolver=_resolver({}))


def test_case_material_sha_mismatch_fails() -> None:
    manifest = _manifest()
    manifest["materials"]["CASE_A"]["text"] = "被篡改的案例材料"
    with pytest.raises(mfi.ManifestFormImportError, match="case_content_sha256_mismatch"):
        _build(manifest)


def test_case_base_variant_pin_mismatch_fails() -> None:
    manifest = _manifest()
    task = next(t for t in manifest["tasks"] if t["task_id"] == "CA2")
    task["source"]["base_content_sha256"] = "0" * 64
    with pytest.raises(mfi.ManifestFormImportError, match="case_base_content_sha256_mismatch"):
        _build(manifest)


def test_blueprint_mismatch_fails() -> None:
    manifest = _manifest()
    manifest["blueprint"] = "pass_readiness_architecture_v1"
    with pytest.raises(mfi.ManifestFormImportError, match="manifest_blueprint_mismatch"):
        _build(manifest)


def test_form_bank_requires_rotation_min_unless_replicated(tmp_path) -> None:
    path = tmp_path / "form_v2_manifest.json"
    path.write_text(json.dumps(_manifest(), ensure_ascii=False), encoding="utf-8")
    kwargs: dict[str, Any] = dict(
        blueprint=BLUEPRINT,
        bank_row_resolver=_resolver(),
        compiled_loader=_compiled_loader(_authorities()),
    )
    with pytest.raises(mfi.ManifestFormImportError, match="form_rotation_short"):
        mfi.build_manifest_form_bank([path], **kwargs)
    bank = mfi.build_manifest_form_bank([path], replicate_to_min=True, **kwargs)
    assert len(bank.forms) == 3
    assert bank.form_source == "manifest_pinned"
    assert [form.form_id for form in bank.forms] == [
        "pass_readiness_form_main_v2",
        "pass_readiness_form_main_v2__r2",
        "pass_readiness_form_main_v2__r3",
    ]
    assert [form.form_index for form in bank.forms] == [1, 2, 3]


def test_persisted_roundtrip_revalidates_manifest_form(tmp_path) -> None:
    form = _build()
    row = _form_to_persisted_row(BLUEPRINT.version, form, question_bank_size=39)
    restored = _form_from_persisted_row(row, BLUEPRINT)
    assert len(restored.units) == 39
    restored_case = next(
        unit.item
        for unit in restored.units
        if isinstance(unit.item, QuestionCandidate)
        and unit.item.source_type == MANIFEST_SOURCE_TYPE
    )
    assert restored_case.answer


def test_service_entry_persists_and_serves_pinned_form(tmp_path, monkeypatch) -> None:
    path = tmp_path / "form_v2_manifest.json"
    path.write_text(json.dumps(_manifest(), ensure_ascii=False), encoding="utf-8")

    saved: dict[str, Any] = {}
    rows = {14000 + i: _bank_row(14000 + i) for i in range(10)}

    class _Provider:
        def get_candidates(self, section, **kwargs):  # pragma: no cover - not used
            raise AssertionError("manifest 模式不得走自动选题")

        def question_bank_size(self) -> int:
            return 4635

        def save_form_bank(self, blueprint, form_bank) -> None:
            saved["blueprint"] = blueprint.version
            saved["form_bank"] = form_bank

        def _supabase_config(self):
            return "https://stub", "key"

        def _query(self, base_url, api_key, filters):
            qb_id = int(str(filters.get("id", "eq.0")).split(".", 1)[1])
            row = rows.get(qb_id)
            return [row] if row else []

    monkeypatch.setattr(
        mfi, "_default_compiled_loader", _compiled_loader(_authorities())
    )
    service = AssessmentBlueprintService(blueprint=BLUEPRINT, provider=_Provider())
    summary = service.generate_and_persist_forms_from_manifest(
        [str(path)], replicate_to_min=True
    )
    assert summary["form_source"] == "manifest_pinned"
    assert summary["form_count"] == 3
    assert saved["blueprint"] == BLUEPRINT.version

    payload = service.create_session(user_id="u1", count=39)
    assert payload["form_source"] == "manifest_pinned"
    assert payload["delivered_count"] == 39
    case_rows = [
        q
        for q in payload["session_questions"]
        if str(q.get("provenance", {}).get("source_table") or "").startswith("manifest:")
    ]
    assert len(case_rows) == 6


# ── 机器码不得冒充学员诊断(2026-08-07 线上实测拦截) ──────────────────
# manifest 的 cause/dimension 多为分类枚举(concept_boundary /
# case_scoring_point),直接投到证据卡上,学员会看到一串英文标识符。


def test_machine_codes_never_reach_learner_facing_diagnosis() -> None:
    from deeptutor.services.assessment.manifest_form_import import _learner_facing

    for code in ("concept_boundary", "case_scoring_point", "construction_logic", "e10"):
        assert _learner_facing(code) == "", f"机器码泄露到学员面: {code}"
    for prose in ("质量验收", "抗渗与后浇带必须不少于 14d", "GB 50204-2015 §8.1"):
        assert _learner_facing(prose) == prose, f"正常人话被误伤: {prose}"
