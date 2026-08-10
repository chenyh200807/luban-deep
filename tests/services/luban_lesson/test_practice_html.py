from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest

import deeptutor.services.luban_lesson.practice_html as practice_html
from deeptutor.services.luban_lesson.practice_html import (
    PracticeHtmlInvalid,
    _array_after,
    _top_level_objects,
    build_practice_authority,
    compile_practice_surface,
    compiled_practice_eligibility_summary,
    decode_projection_receipt,
    load_compiled_practice,
    project_compiled_practice,
    resolve_compiled_practice_items,
    resolve_projection_receipt,
)

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "docs" / "原始数据" / "考点原料" / "成品" / "_pack_manifest.json"
PUBLIC = ROOT / "web" / "public" / "luban-preview"


def _compiled_n01_surface() -> dict[str, object]:
    source = (
        ROOT
        / "artifacts/luban_case_family_assets/diagram_microlesson/finished/P40_N01/P40_N01.practice.dc.html"
    )
    raw = source.read_text(encoding="utf-8")
    return compile_practice_surface(
        "N01",
        surface_id="practice.html",
        html=raw,
        source_path=str(source.relative_to(ROOT)),
        source_html_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


def _signed_review(
    item: dict[str, object],
    index: int,
    *,
    fact_id: str = "",
    probe_role: str = "anchor",
) -> dict[str, object]:
    return {
        "fact_id": fact_id or f"N01-fact-{index + 1}",
        "skeleton_id": f"N01-skeleton-{index + 1}",
        "probe_role": probe_role,
        "source_anchor": f"textbook:N01#fact-{index + 1}",
        "source_sha256": "a" * 64,
        "review": {
            "status": "signed",
            "verdict": "approved",
            "reviewed_content_sha256": item["content_sha256"],
            "signatures": [
                {
                    "role": "teaching",
                    "reviewer_id": "teacher-reviewer",
                    "signed_at": "2026-07-16T00:00:00Z",
                },
                {
                    "role": "scoring",
                    "reviewer_id": "scoring-owner",
                    "signed_at": "2026-07-16T00:00:00Z",
                },
            ],
            "checks": {
                "source_verified": True,
                "answer_verified": True,
                "diagnosis_verified": True,
                "longest_option_checked": True,
                "template_leakage_checked": True,
            },
        },
        "revoked": False,
        "revocation_refs": [],
    }


def test_v3_compiler_emits_item_governance_and_defaults_to_ineligible() -> None:
    compiled = _compiled_n01_surface()
    authority = build_practice_authority(
        "N01",
        source_pack_sha256="1" * 64,
        source_bundle_sha256="2" * 64,
        compiled_surfaces=[compiled],
    )

    assert authority["schema_version"] == "luban_compiled_practice.v3"
    assert all(item["fact_id"] == "" for item in authority["items"])
    assert all(item["skeleton_id"] == "" for item in authority["items"])
    assert all(item["review"]["status"] == "pending" for item in authority["items"])
    assert all(item["eligible"] is False for item in authority["items"])
    assert all(item["revoked"] is False for item in authority["items"])
    assert authority["surfaces"][0]["eligible_variant_ids"] == []

    receipt = decode_projection_receipt(
        authority["surfaces"][0]["projection_receipt"]
    )
    assert receipt["pack_id"] == "N01"
    assert receipt["ordered_variant_ids"] == authority["surfaces"][0]["variant_ids"]
    assert len(receipt["source_digest"]) == 64
    assert len(receipt["projection_digest"]) == 64


def _signed_authority_file(tmp_path: Path) -> tuple[dict[str, object], Path, str]:
    """构建一份 supply_ready 的 N01 v3 authority 并落盘；返回 (authority, path, receipt)。"""
    compiled = _compiled_n01_surface()
    compiled["surface"]["published_practice_sha256"] = "4" * 64
    selected_ids = set(compiled["surface"]["variant_ids"])
    reviews = {}
    selected = [
        (index, item)
        for index, item in enumerate(compiled["items"])
        if item["variant_id"] in selected_ids
    ]
    for selected_index, (index, item) in enumerate(selected):
        reviews[item["variant_id"]] = _signed_review(
            item,
            index,
            fact_id="N01-fact-triad" if selected_index == 0 else "",
        )
    extras = [
        (index, item)
        for index, item in enumerate(compiled["items"])
        if item["variant_id"] not in selected_ids
    ][:2]
    for role, (index, item) in zip(("immediate_confirm", "d1_probe"), extras):
        reviews[item["variant_id"]] = _signed_review(
            item, index, fact_id="N01-fact-triad", probe_role=role
        )
    authority = build_practice_authority(
        "N01",
        source_pack_sha256="1" * 64,
        source_bundle_sha256="2" * 64,
        compiled_surfaces=[compiled],
        review_records=reviews,
    )
    authority["published_lesson_sha256"] = "3" * 64
    path = tmp_path / "n01.practice.authority.json"
    path.write_text(json.dumps(authority, ensure_ascii=False), encoding="utf-8")
    return authority, path, authority["surfaces"][0]["projection_receipt"]


def test_projection_receipt_resolves_only_exact_signed_non_revoked_set(
    tmp_path: Path,
) -> None:
    authority, path, receipt = _signed_authority_file(tmp_path)
    resolved = resolve_projection_receipt("N01", receipt, authority_path=path)
    assert [item["variant_id"] for item in resolved] == authority["surfaces"][0][
        "variant_ids"
    ]

    reordered = decode_projection_receipt(receipt)
    reordered["ordered_variant_ids"] = list(reversed(reordered["ordered_variant_ids"]))
    reordered_receipt = base64.urlsafe_b64encode(
        json.dumps(
            reordered, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).decode("ascii").rstrip("=")
    with pytest.raises(PracticeHtmlInvalid, match="content_updated_retake"):
        resolve_projection_receipt("N01", reordered_receipt, authority_path=path)

    stale = copy.deepcopy(authority)
    stale["items"][0]["revoked"] = True
    stale["items"][0]["eligible"] = False
    stale["items"][0]["revocation_refs"] = ["content-review:N01:withdrawn"]
    path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PracticeHtmlInvalid, match="content_updated_retake"):
        resolve_projection_receipt("N01", receipt, authority_path=path)


def test_projection_receipt_resolution_projects_rows_without_answer_key(
    tmp_path: Path,
) -> None:
    """receipt 解析返回消费侧题面(与 project_compiled_practice 同形),绝不泄漏答案键。"""
    authority, path, receipt = _signed_authority_file(tmp_path)

    resolved = resolve_projection_receipt("N01", receipt, authority_path=path)

    assert [item["variant_id"] for item in resolved] == authority["surfaces"][0][
        "variant_ids"
    ]
    for row in resolved:
        assert row["answer_type"] == "single_choice"
        assert row["stem"] == row["surface"]
        assert row["options"]
        for option in row["options"]:
            assert set(option) == {"option_id", "text"}
        assert "is_correct" not in json.dumps(row, ensure_ascii=False)


def test_projection_receipt_resolution_pins_surface_and_pack_content_identity(
    tmp_path: Path,
) -> None:
    """surface/pack 内容身份与 receipt 不一致=供给漂移,同形 content_updated_retake。"""
    _authority, path, receipt = _signed_authority_file(tmp_path)

    # 一致时通过(surface_id + 当前 manifest content sha 双锚)。
    resolved = resolve_projection_receipt(
        "N01",
        receipt,
        surface_id="practice.html",
        expected_pack_sha256="1" * 64,
        authority_path=path,
    )
    assert len(resolved) == 5

    with pytest.raises(PracticeHtmlInvalid, match="content_updated_retake"):
        resolve_projection_receipt(
            "N01", receipt, surface_id="practice2.html", authority_path=path
        )
    with pytest.raises(PracticeHtmlInvalid, match="content_updated_retake"):
        resolve_projection_receipt(
            "N01", receipt, expected_pack_sha256="9" * 64, authority_path=path
        )


def test_projection_receipt_forged_digest_rejected(tmp_path: Path) -> None:
    """篡改 receipt(digest 对不上内容)→ 拒绝,不得复活任何题集。"""
    _authority, path, receipt = _signed_authority_file(tmp_path)

    forged = decode_projection_receipt(receipt)
    forged["projection_digest"] = "f" * 64
    forged_receipt = (
        base64.urlsafe_b64encode(
            json.dumps(
                forged, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )

    with pytest.raises(PracticeHtmlInvalid, match="content_updated_retake"):
        resolve_projection_receipt("N01", forged_receipt, authority_path=path)


def test_five_signed_anchors_do_not_bypass_seven_question_fact_triad_gate() -> None:
    compiled = _compiled_n01_surface()
    selected_ids = set(compiled["surface"]["variant_ids"])
    reviews = {
        item["variant_id"]: _signed_review(item, index)
        for index, item in enumerate(compiled["items"])
        if item["variant_id"] in selected_ids
    }
    authority = build_practice_authority(
        "N01",
        source_pack_sha256="1" * 64,
        source_bundle_sha256="2" * 64,
        compiled_surfaces=[compiled],
        review_records=reviews,
    )

    summary = compiled_practice_eligibility_summary(authority)
    assert summary["eligible_question_count"] == 5
    assert summary["anchors_ready"] is True
    assert summary["complete_fact_count"] == 0
    assert summary["supply_ready"] is False


def _anchors_only_authority_file(
    tmp_path: Path,
) -> tuple[dict[str, object], Path, str]:
    """构建一份"5 锚点已签发但不满 7 题三件套"的 authority 并落盘。

    这类 authority 的 surface 有非空 ``projection_receipt``(5 锚点合格),
    但 ``supply_ready`` 仍为 False(缺完整 fact 三件套)——正是 receipt 路径能
    真实抵达资格闸的场景:receipt 身份校验通过,却因供给尚未发布而退出。
    """
    compiled = _compiled_n01_surface()
    compiled["surface"]["published_practice_sha256"] = "4" * 64
    selected_ids = set(compiled["surface"]["variant_ids"])
    reviews = {
        item["variant_id"]: _signed_review(item, index)
        for index, item in enumerate(compiled["items"])
        if item["variant_id"] in selected_ids
    }
    authority = build_practice_authority(
        "N01",
        source_pack_sha256="1" * 64,
        source_bundle_sha256="2" * 64,
        compiled_surfaces=[compiled],
        review_records=reviews,
    )
    authority["published_lesson_sha256"] = "3" * 64
    path = tmp_path / "n01.practice.authority.json"
    path.write_text(json.dumps(authority, ensure_ascii=False), encoding="utf-8")
    return authority, path, authority["surfaces"][0]["projection_receipt"]


def test_projection_receipt_not_released_when_supply_not_signed(
    tmp_path: Path,
) -> None:
    """资格未就绪(供给未签发发布)=独立 ``practice_not_released``,不冒充漂移。"""
    authority, path, receipt = _anchors_only_authority_file(tmp_path)
    # 前置:这份 authority 的 surface receipt 非空(5 锚点合格)但 supply_ready False。
    assert receipt
    assert compiled_practice_eligibility_summary(authority)["supply_ready"] is False

    # 身份合法的 receipt 命中资格闸 → 独立错误码,绝不洗白成 content_updated_retake。
    with pytest.raises(PracticeHtmlInvalid, match="^practice_not_released$"):
        resolve_projection_receipt("N01", receipt, authority_path=path)


def test_projection_receipt_drift_still_content_updated_on_unreleased_pack(
    tmp_path: Path,
) -> None:
    """同一未发布 pack 上,真收据漂移(乱序)仍是 ``content_updated_retake``。

    资格未就绪与收据漂移是正交的两条终态:分流不能把漂移也误报成"未发布"。
    """
    _authority, path, receipt = _anchors_only_authority_file(tmp_path)
    reordered = decode_projection_receipt(receipt)
    reordered["ordered_variant_ids"] = list(reversed(reordered["ordered_variant_ids"]))
    reordered_receipt = (
        base64.urlsafe_b64encode(
            json.dumps(
                reordered, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        )
        .decode("ascii")
        .rstrip("=")
    )
    with pytest.raises(PracticeHtmlInvalid, match="^content_updated_retake$"):
        resolve_projection_receipt("N01", reordered_receipt, authority_path=path)


def test_figure_is_presentation_attachment_outside_identity_and_projects_through(
    tmp_path: Path,
) -> None:
    """题给图形合同:①不入 content_sha256 身份(签名裁决零触碰);②投影透传
    {label, caption, els, h, w};③无 figure 的题投影不带键(前端有才渲)。"""
    compiled = _compiled_n01_surface()
    baseline = [dict(item) for item in compiled["items"]]
    figure = {
        "label": "题给:示例面板",
        "caption": "看图判断",
        "els": [{"x": 8, "top": 8, "w": 100, "h": 34, "bg": "#2f6db0", "lab": "示例"}],
        "h": 96,
        "w": 334,
    }
    first_selected = compiled["surface"]["variant_ids"][0]
    for item in compiled["items"]:
        if item["variant_id"] == first_selected:
            item["figure"] = figure
    # ① 身份稳定: figure 挂载前后 content_sha256 逐题一致
    for before, after in zip(baseline, compiled["items"]):
        assert before["content_sha256"] == after["content_sha256"]

    compiled["surface"]["published_practice_sha256"] = "4" * 64
    selected_ids = set(compiled["surface"]["variant_ids"])
    reviews = {}
    selected = [
        (index, item)
        for index, item in enumerate(compiled["items"])
        if item["variant_id"] in selected_ids
    ]
    for selected_index, (index, item) in enumerate(selected):
        reviews[item["variant_id"]] = _signed_review(
            item,
            index,
            fact_id="N01-fact-triad" if selected_index == 0 else "",
        )
    extras = [
        (index, item)
        for index, item in enumerate(compiled["items"])
        if item["variant_id"] not in selected_ids
    ][:2]
    for role, (index, item) in zip(("immediate_confirm", "d1_probe"), extras):
        reviews[item["variant_id"]] = _signed_review(
            item, index, fact_id="N01-fact-triad", probe_role=role
        )
    authority = build_practice_authority(
        "N01",
        source_pack_sha256="1" * 64,
        source_bundle_sha256="2" * 64,
        compiled_surfaces=[compiled],
        review_records=reviews,
    )
    authority["published_lesson_sha256"] = "3" * 64
    path = tmp_path / "n01.practice.authority.json"
    path.write_text(json.dumps(authority, ensure_ascii=False), encoding="utf-8")

    rows = resolve_projection_receipt(
        "N01", authority["surfaces"][0]["projection_receipt"], authority_path=path
    )
    with_figure = [row for row in rows if "figure" in row]
    # ② 透传: 挂了 figure 的题带完整面板; ③ 其余题不带键
    assert [row["variant_id"] for row in with_figure] == [first_selected]
    assert with_figure[0]["figure"] == figure
    assert all("figure" not in row for row in rows if row["variant_id"] != first_selected)
    # 答案键红线不因新字段松动
    for row in rows:
        assert "is_correct" not in json.dumps(row, ensure_ascii=False)


def test_projection_receipt_rejects_legacy_identity() -> None:
    with pytest.raises(PracticeHtmlInvalid, match="content_updated_retake"):
        decode_projection_receipt("1,0,1,0,1")


def _compiled_pack_ids() -> list[str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [
        row["pack_id"]
        for row in manifest["packs"]
        if (row.get("practice") or {}).get("status") == "compiled"
    ]


def test_all_registered_finished_practices_compile_full_private_pools_and_five_question_projections() -> None:
    pack_ids = _compiled_pack_ids()
    authorities = [load_compiled_practice(pack_id) for pack_id in pack_ids]

    assert len(pack_ids) == 40
    assert all(authority is not None for authority in authorities)
    assert sum(len(authority["surfaces"]) for authority in authorities if authority) == 43
    # 649 = 641 + 2026-07-21 路线B批1(C01+2/C06+2/D11+1/F03+3 新 d1_probe 补三件套)。
    assert sum(len(authority["items"]) for authority in authorities if authority) == 649
    for authority in authorities:
        assert authority is not None
        assert len({item["variant_id"] for item in authority["items"]}) == len(
            authority["items"]
        )
        assert all(
            sum(option["is_correct"] for option in item["options"]) == 1
            for item in authority["items"]
        )
        for surface in authority["surfaces"]:
            assert len(surface["variant_ids"]) == 5
            assert set(surface["variant_ids"]).issubset(
                {item["variant_id"] for item in authority["items"]}
            )
            source = ROOT / surface["source_path"]
            assert source.is_file()
            assert hashlib.sha256(source.read_bytes()).hexdigest() == surface[
                "source_html_sha256"
            ]


def test_compiled_and_unavailable_pack_sets_are_exact() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    compiled = {
        row["pack_id"]
        for row in manifest["packs"]
        if (row.get("practice") or {}).get("status") == "compiled"
    }
    unavailable = {
        row["pack_id"]
        for row in manifest["packs"]
        if (row.get("practice") or {}).get("status") == "unavailable"
    }
    assert len(compiled) == 40
    # E06/Z01: 16ae6074c Layer-2 异源 jury 收口后 manifest 登记,practice 编译资产
    # 未上 → 诚实标 unavailable(0810 里程碑合并对账:先证不变量"集合=manifest
    # practice.status 投影"成立,再对齐钉的精确集)。
    assert unavailable == {"E01", "E06", "Z01"}


@pytest.mark.parametrize("pack_id", ["A01", "X01", "G03"])
def test_conflict_packs_remain_default_denied_until_exact_human_signatures(
    pack_id: str, pendingize_pack
) -> None:
    """人审签名不齐的包必须整包默认拒发。

    历史上 A01/X01/G03 是真实的内容冲突 pending 包;2026-07-20 补题批后全语料
    签发,改用合成 pending 夹具(同三包的真实 authority 重置 review)守住同一
    fail-closed 契约:review 全 pending ⇒ 零 eligible ⇒ 投影拒发。
    """
    canonical = pendingize_pack(pack_id)
    assert canonical is not None
    assert canonical["schema_version"] == "luban_compiled_practice.v3"
    assert all(item["eligible"] is False for item in canonical["items"])
    assert all(item["review"]["status"] == "pending" for item in canonical["items"])
    with pytest.raises(PracticeHtmlInvalid, match="selection_insufficient"):
        project_compiled_practice(pack_id, selection_key="qa_eval_candidate:2026196:forward")


def test_every_compiled_surface_fails_closed_unless_supply_ready() -> None:
    """数据驱动:supply_ready 的包放行且只发签发集合;其余一律 fail-close 不回退。"""
    for pack_id in _compiled_pack_ids():
        authority = load_compiled_practice(pack_id)
        assert authority is not None
        summary = compiled_practice_eligibility_summary(authority)
        eligible_ids = {
            item["variant_id"] for item in authority["items"] if item["eligible"] is True
        }
        for surface in authority["surfaces"]:
            surface_id = surface["surface_id"]
            if summary["supply_ready"]:
                rows = project_compiled_practice(
                    pack_id,
                    surface_id=surface_id,
                    selection_key=f"qa_eval_all_surfaces:2026196:{surface_id}",
                )
                assert rows, f"{pack_id}/{surface_id} supply_ready 却未发题"
                assert {row["variant_id"] for row in rows} <= eligible_ids
                roles = {
                    str(item.get("probe_role") or "")
                    for item in authority["items"]
                    if item["variant_id"] in {row["variant_id"] for row in rows}
                }
                assert roles == {"anchor"}
            else:
                assert surface["eligible_variant_ids"] == []
                with pytest.raises(PracticeHtmlInvalid, match="selection_insufficient"):
                    project_compiled_practice(
                        pack_id,
                        surface_id=surface_id,
                        selection_key=f"qa_eval_all_surfaces:2026196:{surface_id}",
                    )


def test_n01_first_batch_signed_supply_ready_and_serves_eligible_only() -> None:
    """首批签发终态钉死:N01 七题签发、fact 三件套齐、投影只出签发集合。"""
    canonical = load_compiled_practice("N01")
    assert canonical is not None
    summary = compiled_practice_eligibility_summary(canonical)
    assert summary["supply_ready"] is True
    assert summary["eligible_question_count"] == 7
    assert summary["complete_fact_ids"] == ["n01-fact-critical-work-zero-float"]
    eligible_ids = {
        item["variant_id"] for item in canonical["items"] if item["eligible"] is True
    }
    rows = project_compiled_practice("N01", selection_key="qa_eval_signed:2026196:forward")
    assert rows and {row["variant_id"] for row in rows} <= eligible_ids


def test_public_projection_contains_only_compiled_questions_and_server_bridge() -> None:
    for pack_id in _compiled_pack_ids():
        authority = load_compiled_practice(pack_id)
        assert authority is not None
        for surface in authority["surfaces"]:
            html = (PUBLIC / pack_id.lower() / surface["surface_id"]).read_text(
                encoding="utf-8"
            )
            marker = surface["array_marker"]
            if marker:
                assert len(_top_level_objects(_array_after(html, marker))) == 5
            assert "__dtRedirectEvidence" in html
            assert "this.optPerm(i)" in html
            assert "Number(permutation[selected])" in html
            assert "projection_receipt=" in html
            assert "&answers=" in html
            assert "answer_indexes" not in html
            assert f'encodeURIComponent("{pack_id}")' in html
            assert f'encodeURIComponent("{surface["surface_id"]}")' in html
            assert "网页预览作答仅供即时反馈" in html
            assert "满分手" not in html
            assert '"稳了"' not in html
            assert "采分点都拿到了" not in html
            assert "满分——采分点抓得稳" not in html
            # 服务端判分收权：公开页零答案键 + 交卷/结果渲染只走服务端。
            for leak_name, leak_pattern in (
                practice_html._PRACTICE_PUBLIC_LEAK_PATTERNS.items()
            ):
                assert not leak_pattern.search(html), (
                    f"{pack_id}/{surface['surface_id']}: {leak_name}"
                )
            assert "__dtSubmitRound" in html
            assert "__dtBaseRenderVals(){" in html
            assert "/api/v1/luban-preview/practice-submit" in html
            assert "__dtOverlayResult" in html


def test_sanitize_block_strips_answer_truth_and_rebuilds_options_from_authority() -> None:
    block = (
        '{ tag:"验收层级", typeHint:"单选", fig:"steps", figLabel:"四级",\n'
        '  stem:"验收分几级？",\n'
        '  model:"四级，自下而上。",\n'
        '  opts:[\n'
        '    { t:"三级，自上而下。", ok:false, code:"E06", tempt:"顺手", lose:"倒装", fix:"自下而上" },\n'
        '    { t:"四级，自下而上。", ok:true, fix:"三件齐", code:"" }\n'
        "  ] }"
    )
    item = {
        "stem": "验收分几级？",
        "options": [
            {"option_id": "v1:option-1", "text": "三级，自上而下。"},
            {"option_id": "v1:option-2", "text": "四级，自下而上。"},
        ],
    }
    sanitized = practice_html._sanitize_practice_block(
        block, item, format_kind="q_direct"
    )
    assert '"t": "三级，自上而下。"' in sanitized or '"t":"三级，自上而下。"' in sanitized.replace(" ", "")
    assert "tag:" in sanitized and "fig:" in sanitized and "stem:" in sanitized
    for leak_pattern in practice_html._PRACTICE_PUBLIC_LEAK_PATTERNS.values():
        assert not leak_pattern.search(sanitized)


def test_sanitize_block_fails_closed_on_unclassified_field() -> None:
    block = (
        '{ tag:"t", stem:"s", secret_answer:"D",\n'
        '  opts:[ { t:"a", ok:true, code:"" }, { t:"b", ok:false, code:"" } ] }'
    )
    item = {
        "stem": "s",
        "options": [
            {"option_id": "v1:option-1", "text": "a"},
            {"option_id": "v1:option-2", "text": "b"},
        ],
    }
    with pytest.raises(
        PracticeHtmlInvalid, match="practice_publish_field_unclassified:secret_answer"
    ):
        practice_html._sanitize_practice_block(block, item, format_kind="q_direct")


def test_sanitize_bank_block_neutralizes_correct_index_and_analysis() -> None:
    block = (
        '{ ep:"覆盖关", topic:"划分", fig:"divide", stem:"按什么划分？",\n'
        '  opts:["按工程量","按工种"], c:1,\n'
        '  ana:[ { s:"错", why:"张冠李戴", lose:"归错类", fix:"按工种" },\n'
        '        { s:"对", fix:"四类齐" } ] }'
    )
    item = {
        "stem": "按什么划分？",
        "options": [
            {"option_id": "v1:option-1", "text": "按工程量"},
            {"option_id": "v1:option-2", "text": "按工种"},
        ],
    }
    sanitized = practice_html._sanitize_practice_block(
        block, item, format_kind="bank_drawn"
    )
    # ``cur.ana[actual]`` 渲染路径保形状：ana 保留为等长空对象数组。
    assert "ana:[{}, {}]" in sanitized or "ana:[{},{}]" in sanitized.replace(" ", "")
    assert '"按工程量"' in sanitized and '"按工种"' in sanitized
    for leak_pattern in practice_html._PRACTICE_PUBLIC_LEAK_PATTERNS.values():
        assert not leak_pattern.search(sanitized)


def test_format_adapters_and_multi_surface_resolution_are_data_driven(
    pendingize_pack,
) -> None:
    a02 = load_compiled_practice("A02")
    s07 = load_compiled_practice("S07")
    s01 = load_compiled_practice("S01")
    assert a02 and a02["surfaces"][0]["format_kind"] == "bank_drawn"
    assert s07 and s07["surfaces"][0]["format_kind"] == "pool_deck"
    assert s01 and [surface["surface_id"] for surface in s01["surfaces"]] == [
        "practice.html",
        "practice2.html",
        "practice3.html",
    ]
    second_ids = s01["surfaces"][1]["variant_ids"]
    assert len(second_ids) == 5
    assert all(
        next(item for item in s01["items"] if item["variant_id"] == variant_id)["surface_id"]
        == "practice2.html"
        for variant_id in second_ids
    )
    # 2026-07-20 全语料签发后 practice2 已释放:多面解析必须精确出第二面题集。
    resolved = resolve_compiled_practice_items("S01", surface_id="practice2.html")
    assert resolved is not None
    assert [row["variant_id"] for row in resolved] == second_ids
    # fail-closed 契约不随世界态消失:合成 pending 世界态下同一面仍整体拒发。
    pendingize_pack("S01")
    with pytest.raises(PracticeHtmlInvalid, match="selection_insufficient"):
        resolve_compiled_practice_items("S01", surface_id="practice2.html")


def test_authority_sidecar_answer_tamper_fails_closed(tmp_path: Path) -> None:
    canonical = load_compiled_practice("F16")
    assert canonical is not None
    for option in canonical["items"][0]["options"]:
        option["is_correct"] = False
    path = tmp_path / "practice.authority.json"
    path.write_text(json.dumps(canonical, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PracticeHtmlInvalid, match="answer_invalid"):
        load_compiled_practice("F16", authority_path=path)


def test_authority_sidecar_rejects_practice_surface_gaps(tmp_path: Path) -> None:
    canonical = load_compiled_practice("B02")
    assert canonical is not None
    tampered = copy.deepcopy(canonical)
    tampered["surfaces"][1]["surface_id"] = "practice3.html"
    path = tmp_path / "practice.authority.json"
    path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PracticeHtmlInvalid, match="surface_set_invalid"):
        load_compiled_practice("B02", authority_path=path)


def test_manifest_digest_rejects_shape_valid_answer_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = ROOT / "deeptutor/services/luban_lesson/compiled/f16.practice.authority.json"
    original = source_path.read_bytes()
    tampered = json.loads(original)
    first_options = tampered["items"][0]["options"]
    correct_index = next(
        index for index, option in enumerate(first_options) if option["is_correct"]
    )
    replacement = 1 if correct_index == 0 else 0
    first_options[correct_index]["is_correct"] = False
    first_options[replacement]["is_correct"] = True

    compiled = tmp_path / "compiled"
    compiled.mkdir()
    (compiled / "f16.practice.authority.json").write_text(
        json.dumps(tampered, ensure_ascii=False), encoding="utf-8"
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "packs": [
                    {
                        "pack_id": "F16",
                        "practice": {
                            "status": "compiled",
                            "authority_path": "f16.practice.authority.json",
                            "authority_sha256": hashlib.sha256(original).hexdigest(),
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(practice_html, "_COMPILED_DIR", compiled)
    monkeypatch.setattr(practice_html, "_MANIFEST_PATH", manifest)

    with pytest.raises(PracticeHtmlInvalid, match="digest_mismatch"):
        load_compiled_practice("F16")


def test_unregistered_or_wrong_surface_never_falls_back_to_another_question_set() -> None:
    b02 = load_compiled_practice("B02")
    assert b02 is not None
    assert [surface["surface_id"] for surface in b02["surfaces"]] == [
        "practice.html", "practice2.html"
    ]
    assert load_compiled_practice("E01") is None
    with pytest.raises(PracticeHtmlInvalid, match="surface_not_found"):
        resolve_compiled_practice_items("B02", surface_id="practice3.html")
    with pytest.raises(PracticeHtmlInvalid, match="surface_not_found"):
        resolve_compiled_practice_items("S01", surface_id="practice4.html")
