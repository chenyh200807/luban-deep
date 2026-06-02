from __future__ import annotations

from deeptutor.services.source_compiler.scoring_point_asset_compiler import (
    compile_scoring_point_assets,
    normalized_contains,
)


def _chunk(
    *,
    chunk_id: str = "chunk-1",
    content_markdown: str,
    content_type: str = "normative_rule",
    node_code: str = "1A421000",
    grading_keywords: list[str] | None = None,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "content_markdown": content_markdown,
        "content_type": content_type,
        "taxonomy": {"node_code": node_code, "node_name": "建筑工程"},
        "source_meta": {"page_num": 12},
        "assessment": {"grading_keywords": grading_keywords or []},
    }


def test_normalized_contains_allows_punctuation_shape_but_not_missing_text() -> None:
    content = "验槽时必须具备勘察、设计、建设、监理和施工等单位共同参加。"

    assert normalized_contains(content, "勘察设计建设监理和施工")
    assert not normalized_contains(content, "勘察设计造价监理和施工")


def test_textbook_anchor_requires_real_chunk_and_quote() -> None:
    rows, report = compile_scoring_point_assets(
        [_chunk(chunk_id="", content_markdown="应设置明显标志和安全防护设施。", grading_keywords=["安全防护设施"])],
        run_id="pytest",
        source_path="book.json",
        compiled_at="now",
    )

    assert rows == []
    assert report["invalid_textbook_anchor_count"] == 0
    assert report["discarded_candidates"]["empty_chunk_id"] >= 1


def test_short_common_seed_is_expanded_or_discarded() -> None:
    rows, report = compile_scoring_point_assets(
        [
            _chunk(
                content_markdown="施工现场应设置连续封闭的围挡，围挡应坚固、稳定、整洁、美观。",
                grading_keywords=["围挡"],
            )
        ],
        run_id="pytest",
        source_path="book.json",
        compiled_at="now",
    )

    assert rows
    assert all(point["required_terms"][0] != "围挡" for point in rows)
    assert report["loose_anchor_violation_count"] == 0


def test_numeric_rule_compiles_as_calculation_without_fragment_anchor() -> None:
    rows, report = compile_scoring_point_assets(
        [
            _chunk(
                content_markdown="钢筋理论重量应按707.2kg计算，允许偏差为±3%。",
                content_type="rule_numeric",
                grading_keywords=["707.2kg", "2kg"],
            )
        ],
        run_id="pytest",
        source_path="book.json",
        compiled_at="now",
    )

    assert rows
    assert rows[0]["point_type"] == "calculation"
    assert rows[0]["anchor_source"] == "calculation"
    assert "707.2kg" in rows[0]["calculation"]["expected_values"]
    assert "2kg" not in rows[0]["required_terms"]
    assert report["loose_anchor_violation_count"] == 0


def test_markdown_headings_are_not_scoring_point_terms() -> None:
    rows, report = compile_scoring_point_assets(
        [
            _chunk(
                content_markdown=(
                    "### 4.1 建筑工程建设相关规定\n"
                    "**（1）城市道路占用、挖掘的相关规定**\n"
                    "- 经批准挖掘城市道路的，应当在施工现场设置明显标志和安全防护设施。"
                ),
                grading_keywords=["安全防护设施"],
            )
        ],
        run_id="pytest",
        source_path="book.json",
        compiled_at="now",
    )

    terms = [row["required_terms"][0] for row in rows if row["required_terms"]]
    assert "4.1 建筑工程建设相关规定" not in terms
    assert "城市道路占用、挖掘的相关规定" not in terms
    assert any("安全防护设施" in term for term in terms)
    assert report["quality_gate"] == "pass"


def test_markdown_residue_is_removed_from_terms() -> None:
    rows, report = compile_scoring_point_assets(
        [
            _chunk(
                content_markdown=(
                    "**人工费**：包括计时工资或计件工资、奖金、津贴补贴。\n"
                    "#### （5）施工保证措施：参考基坑工程要求"
                ),
                grading_keywords=["人工费"],
            )
        ],
        run_id="pytest",
        source_path="book.json",
        compiled_at="now",
    )

    terms = [row["required_terms"][0] for row in rows if row["required_terms"]]
    assert all("**" not in term and "####" not in term for term in terms)
    assert "人工费" in terms
    assert report["quality_gate"] == "pass"
