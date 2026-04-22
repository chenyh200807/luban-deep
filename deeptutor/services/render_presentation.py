from __future__ import annotations

from typing import Any


SCHEMA_VERSION = 1


def _coerce_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    return ""


def _normalize_enum(value: Any, allowed: list[str], fallback: str) -> str:
    raw = _coerce_text(value)
    if raw in allowed:
        return raw
    return fallback


def _normalize_string_array(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        text = _coerce_text(item)
        if text:
            out.append(text)
    return out


def _coerce_positive_int(value: Any, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback


def _normalize_option_map(raw_options: Any) -> tuple[list[dict[str, str]], dict[str, str]]:
    if not isinstance(raw_options, dict):
        return [], {}
    options: list[dict[str, str]] = []
    option_map: dict[str, str] = {}
    for raw_key in sorted(raw_options.keys(), key=lambda item: str(item or "").upper()):
        key = _coerce_text(raw_key).upper()
        value = _coerce_text(raw_options.get(raw_key))
        if not key or not value:
            continue
        options.append({"key": key, "text": value})
        option_map[key] = value
    return options, option_map


def _build_choice_followup_context(
    qa_pair: dict[str, Any],
    *,
    index: int,
    option_map: dict[str, str],
) -> dict[str, Any]:
    metadata = qa_pair.get("metadata") if isinstance(qa_pair.get("metadata"), dict) else {}
    return {
        "question_id": _coerce_text(qa_pair.get("question_id") or f"q_{index}"),
        "question": _coerce_text(qa_pair.get("question") or ""),
        "question_type": "choice",
        "options": option_map,
        "correct_answer": _coerce_text(qa_pair.get("correct_answer") or ""),
        "explanation": _coerce_text(qa_pair.get("explanation") or ""),
        "difficulty": _coerce_text(qa_pair.get("difficulty") or ""),
        "concentration": _coerce_text(
            qa_pair.get("concentration")
            or qa_pair.get("knowledge_point")
            or qa_pair.get("topic")
            or ""
        ),
        "knowledge_context": _coerce_text(
            qa_pair.get("knowledge_context")
            or metadata.get("knowledge_context")
            or qa_pair.get("explanation")
            or ""
        ),
    }


def build_mcq_block_from_result_summary(
    result_summary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    # "result_summary" here means legacy per-message result metadata, not session compressed_summary.
    if not isinstance(result_summary, dict):
        return None
    results = result_summary.get("results")
    if not isinstance(results, list) or not results:
        return None

    questions: list[dict[str, Any]] = []
    for item in results:
        qa_pair = item.get("qa_pair") if isinstance(item, dict) else None
        if not isinstance(qa_pair, dict):
            continue
        question_type = _coerce_text(qa_pair.get("question_type")).lower()
        if question_type != "choice":
            continue
        options, option_map = _normalize_option_map(qa_pair.get("options"))
        if len(options) < 2:
            continue
        index = len(questions) + 1
        followup_context = _build_choice_followup_context(
            qa_pair,
            index=index,
            option_map=option_map,
        )
        correct_answer = _coerce_text(qa_pair.get("correct_answer")).upper()
        multi_select = qa_pair.get("multi_select") is True or len(correct_answer) > 1
        questions.append(
            {
                "index": index,
                "stem": _coerce_text(qa_pair.get("question") or "") or "请选择正确选项",
                "hint": "",
                "question_type": "multi_choice" if multi_select else "single_choice",
                "options": options,
                "followup_context": followup_context,
                "question_id": followup_context["question_id"],
            }
        )

    if not questions:
        return None

    return {
        "type": "mcq",
        "schema_version": SCHEMA_VERSION,
        "questions": questions,
        "submit_hint": (
            "多题作答，先分别点选，再提交答案。"
            if len(questions) > 1
            else "请选择后提交答案"
        ),
        "receipt": "",
        "review_mode": False,
    }


def _normalize_mcq_option(raw_option: Any) -> dict[str, Any] | None:
    if not isinstance(raw_option, dict):
        return None
    key = _coerce_text(raw_option.get("key") or raw_option.get("option_key")).upper()
    text = _coerce_text(raw_option.get("text") or raw_option.get("value") or raw_option.get("label"))
    if not key or not text:
        return None
    return {
        "key": key,
        "text": text,
        "selected": bool(raw_option.get("selected")),
    }


def _normalize_mcq_question(raw_question: Any, fallback_index: int) -> dict[str, Any] | None:
    if not isinstance(raw_question, dict):
        return None
    followup_context = raw_question.get("followup_context") or raw_question.get("followupContext")
    if not isinstance(followup_context, dict):
        followup_context = None
    options_source = raw_question.get("options")
    options: list[dict[str, Any]] = []
    if isinstance(options_source, dict):
        for raw_key in sorted(options_source.keys(), key=lambda item: str(item or "").upper()):
            option = _normalize_mcq_option(
                {"key": raw_key, "text": options_source.get(raw_key)}
            )
            if option and option["key"] and option["text"]:
                options.append(option)
    elif isinstance(options_source, list):
        for raw_option in options_source:
            option = _normalize_mcq_option(raw_option)
            if option and option["text"]:
                options.append(option)
    if len(options) < 2:
        return None

    question_type = _coerce_text(raw_question.get("question_type") or raw_question.get("questionType")).lower()
    if "multi" in question_type:
        normalized_question_type = "multi_choice"
    else:
        normalized_question_type = "single_choice"

    question_id = _coerce_text(
        raw_question.get("question_id")
        or raw_question.get("questionId")
        or (followup_context.get("question_id") if followup_context else "")
    )
    if not question_id and followup_context:
        question_id = _coerce_text(followup_context.get("question_id"))

    index = fallback_index
    raw_index = _coerce_text(raw_question.get("index"))
    if raw_index.isdigit():
        index = max(int(raw_index), fallback_index)

    return {
        "index": index,
        "stem": _coerce_text(raw_question.get("stem") or raw_question.get("question") or "") or "请选择正确选项",
        "hint": _coerce_text(raw_question.get("hint") or ""),
        "question_type": normalized_question_type,
        "options": options,
        "followup_context": followup_context,
        "question_id": question_id,
    }


def _normalize_mcq_block(raw_block: Any) -> dict[str, Any] | None:
    block = raw_block if isinstance(raw_block, dict) else {}
    raw_questions = block.get("questions")
    if not isinstance(raw_questions, list):
        return None
    questions: list[dict[str, Any]] = []
    for index, raw_question in enumerate(raw_questions, start=1):
        question = _normalize_mcq_question(raw_question, index)
        if not question:
            continue
        questions.append(question)
    if not questions:
        return None
    return {
        "type": "mcq",
        "schema_version": SCHEMA_VERSION,
        "questions": questions,
        "submit_hint": _coerce_text(block.get("submit_hint") or block.get("submitHint") or "请选择后提交答案"),
        "receipt": _coerce_text(block.get("receipt") or ""),
        "review_mode": bool(block.get("review_mode") or block.get("reviewMode")),
    }


def _normalize_table_cell(raw_cell: Any) -> dict[str, Any]:
    if isinstance(raw_cell, dict):
        return {
            "text": _coerce_text(raw_cell.get("text") or raw_cell.get("content") or raw_cell.get("value")),
            "align": _normalize_enum(raw_cell.get("align"), ["left", "center", "right"], "left"),
            "highlight": bool(raw_cell.get("highlight")),
        }
    return {
        "text": _coerce_text(raw_cell),
        "align": "left",
        "highlight": False,
    }


def _normalize_table_row(raw_row: Any) -> list[dict[str, Any]]:
    if isinstance(raw_row, dict):
        raw_row = raw_row.get("cells") if isinstance(raw_row.get("cells"), list) else raw_row.get("items")
    if not isinstance(raw_row, list):
        return []
    row: list[dict[str, Any]] = []
    for raw_cell in raw_row:
        row.append(_normalize_table_cell(raw_cell))
    return row


def _normalize_table_payload(raw_table: Any) -> dict[str, Any] | None:
    if isinstance(raw_table, list):
        raw_table = {"rows": raw_table}
    if not isinstance(raw_table, dict):
        return None
    headers = _normalize_table_row(raw_table.get("headers"))
    rows: list[list[dict[str, Any]]] = []
    raw_rows = raw_table.get("rows")
    if isinstance(raw_rows, list):
        for raw_row in raw_rows:
            row = _normalize_table_row(raw_row)
            if row:
                rows.append(row)
    if not headers and not rows:
        return None
    payload: dict[str, Any] = {
        "headers": headers,
        "rows": rows,
    }
    caption = _coerce_text(raw_table.get("caption") or "")
    if caption:
        payload["caption"] = caption
    mobile_strategy = _normalize_enum(
        raw_table.get("mobile_strategy") or raw_table.get("mobileStrategy"),
        ["scroll", "compact_cards"],
        "scroll",
    )
    if mobile_strategy != "scroll" or "mobile_strategy" in raw_table or "mobileStrategy" in raw_table:
        payload["mobile_strategy"] = mobile_strategy
    return payload


def _normalize_table_block(raw_block: Any) -> dict[str, Any] | None:
    payload = _normalize_table_payload(raw_block)
    if not payload:
        return None
    return {
        "type": "table",
        "schema_version": SCHEMA_VERSION,
        **payload,
    }


def _normalize_steps_item(raw_item: Any) -> dict[str, Any] | None:
    if isinstance(raw_item, dict):
        title = _coerce_text(
            raw_item.get("title")
            or raw_item.get("text")
            or raw_item.get("label")
            or raw_item.get("content")
        )
        detail = _coerce_text(raw_item.get("detail") or raw_item.get("summary") or raw_item.get("description"))
        if not (title or detail):
            return None
        item: dict[str, Any] = {
            "index": _coerce_positive_int(raw_item.get("index"), 0),
            "title": title or "",
        }
        if detail:
            item["detail"] = detail
        status = _normalize_enum(raw_item.get("status"), ["done", "doing", "todo"], "todo")
        if "status" in raw_item:
            item["status"] = status
        return item
    text = _coerce_text(raw_item)
    if not text:
        return None
    return {
        "index": 0,
        "title": text,
    }


def _normalize_steps_block(raw_block: Any) -> dict[str, Any] | None:
    block = raw_block if isinstance(raw_block, dict) else {}
    raw_items = block.get("steps") if isinstance(block.get("steps"), list) else block.get("items")
    if not isinstance(raw_items, list):
        return None
    steps: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items, start=1):
        item = _normalize_steps_item(raw_item)
        if not item:
            continue
        item_index = int(item.get("index") or 0) or index
        step: dict[str, Any] = {
            "index": item_index,
            "title": _coerce_text(item.get("title")) or f"步骤{item_index}",
        }
        detail = _coerce_text(item.get("detail"))
        if detail:
            step["detail"] = detail
        status = _normalize_enum(item.get("status"), ["done", "doing", "todo"], "todo")
        if "status" in item:
            step["status"] = status
        steps.append(step)
    if not steps:
        return None
    normalized: dict[str, Any] = {
        "type": "steps",
        "schema_version": SCHEMA_VERSION,
        "title": _coerce_text(block.get("title") or block.get("heading")),
        "steps": steps,
    }
    style = _coerce_text(block.get("style") or block.get("layout"))
    if style:
        normalized["style"] = style
    return normalized


def _normalize_chart_scalar(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)):
        return value
    return _coerce_text(value)


def _normalize_chart_point(raw_point: Any) -> Any | None:
    if isinstance(raw_point, dict):
        point: dict[str, Any] = {}
        for key in ("label", "name", "x", "y", "value"):
            if key in raw_point:
                normalized_value = _normalize_chart_scalar(raw_point.get(key))
                if normalized_value != "":
                    point[key] = normalized_value
        return point or None
    normalized_value = _normalize_chart_scalar(raw_point)
    return normalized_value if normalized_value != "" else None


def _normalize_chart_series(raw_series: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_series, list):
        return []
    series: list[dict[str, Any]] = []
    for item in raw_series:
        if not isinstance(item, dict):
            continue
        normalized_item: dict[str, Any] = {}
        name = _coerce_text(item.get("name") or item.get("label"))
        if name:
            normalized_item["name"] = name
        series_type = _coerce_text(item.get("type") or item.get("series_type"))
        if series_type:
            normalized_item["type"] = series_type
        data = item.get("data")
        if isinstance(data, list):
            normalized_data: list[Any] = []
            for point in data:
                normalized_point = _normalize_chart_point(point)
                if normalized_point is not None:
                    normalized_data.append(normalized_point)
            if normalized_data:
                normalized_item["data"] = normalized_data
        color = _coerce_text(item.get("color"))
        if color:
            normalized_item["color"] = color
        if normalized_item:
            series.append(normalized_item)
    return series


def _normalize_chart_axis(raw_axis: Any) -> dict[str, Any]:
    if not isinstance(raw_axis, dict):
        return {}
    axis: dict[str, Any] = {}
    label = _coerce_text(raw_axis.get("label") or raw_axis.get("title"))
    if label:
        axis["label"] = label
    unit = _coerce_text(raw_axis.get("unit"))
    if unit:
        axis["unit"] = unit
    categories = _normalize_string_array(raw_axis.get("categories"))
    if categories:
        axis["categories"] = categories
    for key in ("min", "max"):
        value = raw_axis.get(key)
        if isinstance(value, (int, float, bool)):
            axis[key] = value
    return axis


def _normalize_chart_legend(raw_legend: Any) -> dict[str, Any]:
    if not isinstance(raw_legend, dict):
        return {}
    legend: dict[str, Any] = {}
    show = raw_legend.get("show")
    if isinstance(show, bool):
        legend["show"] = show
    position = _coerce_text(raw_legend.get("position"))
    if position:
        legend["position"] = position
    labels = _normalize_string_array(raw_legend.get("labels") or raw_legend.get("items"))
    if labels:
        legend["labels"] = labels
    return legend


def _normalize_chart_block(raw_block: Any) -> dict[str, Any] | None:
    block = raw_block if isinstance(raw_block, dict) else {}
    chart_type = _coerce_text(block.get("chart_type") or block.get("chartType"))
    title = _coerce_text(block.get("title") or block.get("heading"))
    caption = _coerce_text(block.get("caption") or "")
    summary = _coerce_text(block.get("summary") or "")
    series = _normalize_chart_series(block.get("series"))
    axes_raw = block.get("axes")
    axes: dict[str, Any] = {}
    if isinstance(axes_raw, dict):
        x_axis = _normalize_chart_axis(
            axes_raw.get("x") or axes_raw.get("x_axis") or axes_raw.get("xAxis")
        )
        y_axis = _normalize_chart_axis(
            axes_raw.get("y") or axes_raw.get("y_axis") or axes_raw.get("yAxis")
        )
        if x_axis:
            axes["x"] = x_axis
        if y_axis:
            axes["y"] = y_axis
    legend = _normalize_chart_legend(block.get("legend"))
    fallback_table = _normalize_table_payload(block.get("fallback_table") or block.get("fallbackTable"))
    if not (chart_type or title or caption or series or axes or legend or fallback_table or summary):
        return None
    return {
        "type": "chart",
        "schema_version": SCHEMA_VERSION,
        "chart_type": chart_type,
        "title": title,
        "caption": caption,
        "series": series,
        "axes": axes,
        "legend": legend,
        "fallback_table": fallback_table,
        "summary": summary,
    }


def _normalize_formula_block(raw_block: Any) -> dict[str, Any] | None:
    block = raw_block if isinstance(raw_block, dict) else {}
    raw_type = _coerce_text(block.get("type") or block.get("kind")).lower()
    if raw_type in {"formula_inline", "inline"}:
        formula_type = "formula_inline"
    else:
        formula_type = "formula_block"
    latex = _coerce_text(block.get("latex") or "")
    display_text = _coerce_text(block.get("display_text") or block.get("displayText")) or latex
    svg_url = _coerce_text(block.get("svg_url") or block.get("svgUrl"))
    copy_text = _coerce_text(block.get("copy_text") or block.get("copyText")) or latex or display_text
    if not (latex or display_text or svg_url or copy_text):
        return None
    return {
        "type": formula_type,
        "schema_version": SCHEMA_VERSION,
        "latex": latex,
        "display_text": display_text,
        "svg_url": svg_url,
        "copy_text": copy_text,
    }


def _normalize_text_block(raw_block: Any) -> dict[str, Any] | None:
    block = raw_block if isinstance(raw_block, dict) else {}
    text = _coerce_text(block.get("text") or block.get("content"))
    if not text:
        return None
    return {
        "type": _coerce_text(block.get("type")),
        "schema_version": SCHEMA_VERSION,
        "text": text,
    }


def _normalize_recap_block(raw_block: Any) -> dict[str, Any] | None:
    block = raw_block if isinstance(raw_block, dict) else {}
    title = _coerce_text(block.get("title") or block.get("heading")) or "教学总结"
    summary = _coerce_text(block.get("summary") or block.get("text") or block.get("content"))
    bullets = _normalize_string_array(block.get("bullets") or block.get("points") or block.get("items"))
    if not (summary or bullets):
        return None
    normalized: dict[str, Any] = {
        "type": "recap",
        "schema_version": SCHEMA_VERSION,
        "title": title,
        "summary": summary,
    }
    if bullets:
        normalized["bullets"] = bullets
    return normalized


def _normalize_raw_block(raw_block: Any) -> dict[str, Any] | None:
    if not isinstance(raw_block, dict):
        return None
    block_type = _coerce_text(raw_block.get("type")).lower()
    if not block_type:
        return None
    if block_type == "mcq":
        return _normalize_mcq_block(raw_block)
    if block_type == "table":
        return _normalize_table_block(raw_block)
    if block_type == "steps":
        return _normalize_steps_block(raw_block)
    if block_type == "chart":
        return _normalize_chart_block(raw_block)
    if block_type in {"formula_inline", "formula_block", "inline", "block"}:
        return _normalize_formula_block(raw_block)
    if block_type in {
        "paragraph",
        "heading",
        "callout",
        "quote",
        "code",
        "image",
    }:
        return _normalize_text_block(raw_block)
    if block_type == "recap":
        return _normalize_recap_block(raw_block)
    if block_type == "summary":
        normalized = dict(raw_block)
        normalized["type"] = "recap"
        return _normalize_recap_block(normalized)
    if block_type == "list":
        items = _normalize_string_array(raw_block.get("items"))
        if not items:
            return None
        return {
            "type": "list",
            "schema_version": SCHEMA_VERSION,
            "items": items,
        }
    return None


def _contains_block_type(blocks: list[dict[str, Any]], block_type: str) -> bool:
    return any(block.get("type") == block_type for block in blocks)


def build_canonical_presentation(
    *,
    content: str,
    result_summary: dict[str, Any] | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    normalized_blocks: list[dict[str, Any]] = []
    if isinstance(blocks, list):
        for item in blocks:
            block = _normalize_raw_block(item)
            if block:
                normalized_blocks.append(block)
    mcq_block = build_mcq_block_from_result_summary(result_summary)
    if mcq_block and not _contains_block_type(normalized_blocks, "mcq"):
        normalized_blocks.append(mcq_block)
    if not normalized_blocks:
        return None
    return {
        "schema_version": SCHEMA_VERSION,
        "blocks": normalized_blocks,
        "fallback_text": _coerce_text(content or ""),
        "meta": {
            "streamingMode": "block_finalized",
        },
    }


__all__ = [
    "SCHEMA_VERSION",
    "build_canonical_presentation",
    "build_mcq_block_from_result_summary",
]
