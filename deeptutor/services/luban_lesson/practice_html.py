"""F16 成品练习的编译/运行时 authority adapter。

内容 authority 是 ``finished/P40_F16/P40_F16.practice.dc.html``。publisher 在
构建期解析它并生成 tracked ``practice.authority.json``；生产运行时只读该 sidecar，
不反向把 ``web/public`` HTML 当内容源，也不在请求期重新解释 HTML。客户端投影会
剥离正确项与反馈，LearnerState 仍只由 ``RetestWritebackService`` 写入。
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_PILOT_AUTHORITY = {
    "F16": (
        _REPO
        / "deeptutor"
        / "services"
        / "luban_lesson"
        / "compiled"
        / "f16.practice.authority.json"
    ),
}
_JS_STRING = r"(?P<quote>[\"'])(?P<value>(?:\\.|(?!\1).)*)\1"
F16_PRACTICE_ORDER = (0, 1, 2, 3, 5)
F16_FINISHED_PRACTICE_SHA256 = (
    "0ebd0de58bbdbc692da4965d09555fd33f34d115ed95058eeccdaa9703a3c374"
)


class PracticeHtmlInvalid(ValueError):
    """编译练习结构不完整或不再满足固定五题合同。"""


def is_compiled_practice_pack(pack_id: str) -> bool:
    return str(pack_id or "").strip().upper() in _PILOT_AUTHORITY


def _balanced_spans(
    text: str, opener: str = "{", closer: str = "}"
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    stack: list[int] = []
    quote = ""
    escaped = False
    line_comment = False
    block_comment = False
    index = 0
    while index < len(text):
        char = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        if line_comment:
            if char in "\r\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if char == "*" and nxt == "/":
                block_comment = False
                index += 2
            else:
                index += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            index += 1
            continue
        if char in {"\"", "'", "`"}:
            quote = char
            index += 1
            continue
        if char == "/" and nxt == "/":
            line_comment = True
            index += 2
            continue
        if char == "/" and nxt == "*":
            block_comment = True
            index += 2
            continue
        if char == opener:
            stack.append(index)
        elif char == closer and stack:
            spans.append((stack.pop(), index + 1))
        index += 1
    return spans


def _top_level_objects(array_text: str) -> list[str]:
    spans = sorted(_balanced_spans(array_text))
    top_level = [
        span
        for span in spans
        if not any(other[0] < span[0] and span[1] < other[1] for other in spans)
    ]
    return [array_text[start:end] for start, end in top_level]


def _decode_js_string(match: re.Match[str] | None) -> str:
    if match is None:
        return ""
    try:
        return str(ast.literal_eval(match.group(0))).strip()
    except (SyntaxError, ValueError):
        return str(match.groupdict().get("value") or "").strip()


def _field(block: str, name: str) -> str:
    pattern = re.compile(rf"\b{re.escape(name)}\s*:\s*{_JS_STRING}", re.DOTALL)
    return _decode_js_string(pattern.search(block))


def _array_after(text: str, marker_pattern: str) -> str:
    marker = re.search(marker_pattern, text)
    if marker is None:
        raise PracticeHtmlInvalid(f"practice_html_missing_array:{marker_pattern}")
    start = text.find("[", marker.start())
    spans = _balanced_spans(text[start:], "[", "]")
    end = next((span[1] for span in spans if span[0] == 0), 0)
    if start < 0 or not end:
        raise PracticeHtmlInvalid(f"practice_html_unbalanced_array:{marker_pattern}")
    return text[start + 1 : start + end - 1]


def _options(question_block: str) -> list[dict[str, Any]]:
    blocks = _top_level_objects(_array_after(question_block, r"\bopts\s*:"))
    options: list[dict[str, Any]] = []
    for block in blocks:
        text = _field(block, "t")
        correct = re.search(r"\bok\s*:\s*(true|false)", block)
        if not text or correct is None:
            raise PracticeHtmlInvalid("practice_html_option_missing_text_or_answer")
        options.append(
            {
                "text": text,
                "is_correct": correct.group(1) == "true",
                "source_error_code": _field(block, "code"),
                "temptation": _field(block, "tempt"),
                "loss_reason": _field(block, "lose"),
                "fix": _field(block, "fix"),
            }
        )
    if len(options) < 2:
        raise PracticeHtmlInvalid("practice_html_question_needs_options")
    if sum(bool(item["is_correct"]) for item in options) != 1:
        raise PracticeHtmlInvalid("practice_html_question_needs_unique_correct_option")
    return options


def _question_identity(pack_id: str, source_index: int, item: dict[str, Any]) -> str:
    raw = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"{pack_id}-html-q{source_index + 1}-{digest}"


def compile_practice_authority(
    pack_id: str,
    *,
    html: str,
    source_path: str,
    source_html_sha256: str,
    source_pack_sha256: str,
    source_bundle_sha256: str,
) -> dict[str, Any]:
    """从 finished HTML 编译稳定题目 identity；只允许 publisher 在构建期调用。"""
    normalized_pack = str(pack_id or "").strip().upper()
    if normalized_pack != "F16":
        raise PracticeHtmlInvalid("practice_html_pack_not_supported")
    question_blocks = _top_level_objects(_array_after(html, r"\bQ\s*="))
    order = list(F16_PRACTICE_ORDER)
    if not question_blocks or max(order) >= len(question_blocks):
        raise PracticeHtmlInvalid("practice_html_order_out_of_range")

    source_sha = str(source_html_sha256 or "").strip()
    source_pack_sha = str(source_pack_sha256 or "").strip()
    source_bundle_sha = str(source_bundle_sha256 or "").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
        raise PracticeHtmlInvalid("practice_html_source_sha_invalid")
    if hashlib.sha256(html.encode("utf-8")).hexdigest() != source_sha:
        raise PracticeHtmlInvalid("practice_html_source_bytes_sha_mismatch")
    if source_sha != F16_FINISHED_PRACTICE_SHA256:
        raise PracticeHtmlInvalid("practice_html_selection_source_sha_mismatch")
    if not re.fullmatch(r"[0-9a-f]{64}", source_pack_sha):
        raise PracticeHtmlInvalid("practice_html_pack_source_sha_invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", source_bundle_sha):
        raise PracticeHtmlInvalid("practice_html_bundle_source_sha_invalid")
    relative_path = str(source_path or "").strip()
    if not relative_path:
        raise PracticeHtmlInvalid("practice_html_source_path_missing")
    items: list[dict[str, Any]] = []
    for source_index in order:
        block = question_blocks[source_index]
        canonical = {
            "answer_type": "single_choice",
            "rule_group": _field(block, "tag"),
            "stem": _field(block, "stem"),
            "model_answer": _field(block, "model"),
            "options": _options(block),
        }
        if not all(canonical[key] for key in ("rule_group", "stem", "model_answer")):
            raise PracticeHtmlInvalid("practice_html_question_missing_required_field")
        variant_id = _question_identity(normalized_pack, source_index, canonical)
        options = []
        for option_index, option in enumerate(canonical["options"]):
            options.append(
                {
                    **option,
                    "option_id": f"{variant_id}:option-{option_index + 1}",
                }
            )
        items.append(
            {
                **canonical,
                "options": options,
                "variant_id": variant_id,
                "source_index": source_index,
                "anchor": f"compiled_html:{relative_path}#Q{source_index + 1}",
                "source_html_sha256": source_sha,
            }
        )
    if len({item["variant_id"] for item in items}) != 5:
        raise PracticeHtmlInvalid("practice_html_duplicate_question_identity")
    return {
        "pack_id": normalized_pack,
        "source_path": relative_path,
        "source_html_sha256": source_sha,
        "source_pack_sha256": source_pack_sha,
        "source_bundle_sha256": source_bundle_sha,
        "presentation_order": order,
        "items": items,
    }


def _validate_authority(value: Any, *, expected_pack: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("pack_id") != expected_pack:
        raise PracticeHtmlInvalid("practice_authority_pack_mismatch")
    for key in (
        "source_html_sha256",
        "source_pack_sha256",
        "source_bundle_sha256",
        "published_lesson_sha256",
        "published_practice_sha256",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(value.get(key) or "")):
            raise PracticeHtmlInvalid(f"practice_authority_invalid:{key}")
    items = value.get("items")
    if not isinstance(items, list) or len(items) != 5:
        raise PracticeHtmlInvalid("practice_authority_requires_exactly_five_items")
    ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or item.get("answer_type") != "single_choice":
            raise PracticeHtmlInvalid("practice_authority_item_invalid")
        variant_id = str(item.get("variant_id") or "")
        options = item.get("options")
        if not variant_id or variant_id in ids or not isinstance(options, list):
            raise PracticeHtmlInvalid("practice_authority_item_identity_invalid")
        ids.add(variant_id)
        if len(options) < 2 or sum(
            option.get("is_correct") is True
            for option in options
            if isinstance(option, dict)
        ) != 1:
            raise PracticeHtmlInvalid("practice_authority_answer_invalid")
    return value


def load_compiled_practice(
    pack_id: str, *, authority_path: Path | None = None
) -> dict[str, Any] | None:
    """读取 publisher sidecar；非试点 pack 返回 ``None``，漂移时直接 fail-close。"""
    normalized_pack = str(pack_id or "").strip().upper()
    path = authority_path or _PILOT_AUTHORITY.get(normalized_pack)
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PracticeHtmlInvalid("practice_authority_unavailable") from exc
    authority = _validate_authority(value, expected_pack=normalized_pack)
    if authority_path is None:
        public = _REPO / "web" / "public" / "luban-preview" / normalized_pack.lower()
        projections = {
            "published_lesson_sha256": public / "lesson.html",
            "published_practice_sha256": public / "practice.html",
        }
        for key, projection in projections.items():
            try:
                actual = hashlib.sha256(projection.read_bytes()).hexdigest()
            except OSError as exc:
                raise PracticeHtmlInvalid("practice_public_projection_unavailable") from exc
            if actual != authority[key]:
                raise PracticeHtmlInvalid(f"practice_public_projection_sha_mismatch:{key}")
    return authority


def compiled_practice_bundle_sha(pack_id: str) -> str:
    practice = load_compiled_practice(pack_id)
    return str((practice or {}).get("source_bundle_sha256") or "")


def project_compiled_practice(
    pack_id: str, *, expected_pack_sha256: str = ""
) -> list[dict[str, Any]] | None:
    """客户端题面投影；不下发答案、模型答案或干扰项反馈。"""
    practice = load_compiled_practice(pack_id)
    if practice is None:
        return None
    expected_sha = str(expected_pack_sha256 or "").strip()
    if expected_sha and practice["source_pack_sha256"] != expected_sha:
        return None
    return [
        {
            "answer_type": "single_choice",
            "variant_id": item["variant_id"],
            "rule_group": item["rule_group"],
            "surface": item["stem"],
            "stem": item["stem"],
            "options": [
                {"option_id": option["option_id"], "text": option["text"]}
                for option in item["options"]
            ],
            "anchor": item["anchor"],
            "source_html_sha256": item["source_html_sha256"],
        }
        for item in practice["items"]
    ]


__all__ = [
    "PracticeHtmlInvalid",
    "F16_PRACTICE_ORDER",
    "F16_FINISHED_PRACTICE_SHA256",
    "compile_practice_authority",
    "compiled_practice_bundle_sha",
    "is_compiled_practice_pack",
    "load_compiled_practice",
    "project_compiled_practice",
]
