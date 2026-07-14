"""Finished 随堂练的构建时编译与运行时内容 authority。

题干、选项、答案和解析的 authoring authority 始终是显式注册的
``finished/*.practice.dc.html``。publisher 只在构建时调用本模块：

1. 按 HTML 格式而非 pack 名选择 parser；
2. 跳过当前服务端还不能严格重判的多选题，确定性选出 5 道单选；
3. 生成带 source SHA 的私有 sidecar，并将 public HTML 限定为同五题；
4. 运行时只从 manifest 登记的 sidecar 投影题面，不在请求期解释 HTML。

学生作答仍由 ``RetestWritebackService`` 重判并写 LearnerState；本模块
不写学习状态，public HTML 的本地分数也不是掌握度 authority。
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_COMPILED_DIR = _REPO / "deeptutor" / "services" / "luban_lesson" / "compiled"
_MANIFEST_PATH = _REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_pack_manifest.json"
_JS_STRING = r"(?P<quote>[\"'])(?P<value>(?:\\.|(?!\1).)*)\1"
PRACTICE_LIMIT = 5
SCHEMA_VERSION = "luban_compiled_practice.v1"
AUTHORITY_FIELDS = (
    "schema_version",
    "pack_id",
    "source_pack_sha256",
    "source_bundle_sha256",
    "surfaces",
    "items",
    "published_lesson_sha256",
)


class PracticeHtmlInvalid(ValueError):
    """成品练习无法满足可重判的固定五题合同。"""


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
        if char in {'"', "'", "`"}:
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


def _array_bounds(text: str, marker_pattern: str) -> tuple[int, int]:
    marker = re.search(marker_pattern, text)
    if marker is None:
        raise PracticeHtmlInvalid(f"practice_html_missing_array:{marker_pattern}")
    start = text.find("[", marker.start())
    if start < 0:
        raise PracticeHtmlInvalid(f"practice_html_unbalanced_array:{marker_pattern}")
    spans = _balanced_spans(text[start:], "[", "]")
    end = next((span[1] for span in spans if span[0] == 0), 0)
    if not end:
        raise PracticeHtmlInvalid(f"practice_html_unbalanced_array:{marker_pattern}")
    return start, start + end


def _array_after(text: str, marker_pattern: str) -> str:
    start, end = _array_bounds(text, marker_pattern)
    return text[start + 1 : end - 1]


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


def _string_array(block: str, name: str) -> list[str]:
    raw = _array_after(block, rf"\b{re.escape(name)}\s*:")
    return [_decode_js_string(match) for match in re.finditer(_JS_STRING, raw, re.DOTALL)]


def _question_identity(
    pack_id: str, surface_id: str, source_index: int, item: dict[str, Any]
) -> str:
    raw = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    surface = re.sub(r"[^a-z0-9]+", "-", surface_id.lower()).strip("-")
    return f"{pack_id}-html-{surface}-q{source_index + 1}-{digest}"


def _standard_candidates(html: str) -> tuple[str, str, list[dict[str, Any]]]:
    marker = r"\bPOOL\s*=" if re.search(r"\bPOOL\s*=\s*\[", html) else r"\bQ\s*="
    format_kind = "pool_deck" if marker.startswith(r"\bPOOL") else (
        "ord_method" if re.search(r"\bord\s*\(\)\s*\{", html) else "q_direct"
    )
    candidates: list[dict[str, Any]] = []
    for source_index, block in enumerate(_top_level_objects(_array_after(html, marker))):
        try:
            options = _options(block)
        except PracticeHtmlInvalid:
            continue  # 真多选暂不降格成单选，但不阻断同页其他合法题。
        stem = _field(block, "stem")
        if not stem:
            continue
        model_answer = _field(block, "model") or next(
            item["text"] for item in options if item["is_correct"]
        )
        candidates.append(
            {
                "source_index": source_index,
                "source_group": "POOL" if format_kind == "pool_deck" else "Q",
                "rule_group": _field(block, "tag") or "成品随堂练",
                "stem": stem,
                "model_answer": model_answer,
                "options": options,
                "block": block,
            }
        )
    return format_kind, marker, candidates


def _bank_candidates(html: str) -> tuple[str, list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    source_index = 0
    for group, marker in (("A", r"\bconst\s+A\s*="), ("Dg", r"\bconst\s+Dg\s*=")):
        blocks = _top_level_objects(_array_after(html, marker))
        for group_index, block in enumerate(blocks):
            texts = _string_array(block, "opts")
            correct_match = re.search(r"\bc\s*:\s*(\d+)", block)
            stem = _field(block, "stem")
            if not texts or correct_match is None or not stem:
                source_index += 1
                continue
            correct_index = int(correct_match.group(1))
            if correct_index < 0 or correct_index >= len(texts):
                raise PracticeHtmlInvalid("practice_html_bank_correct_index_invalid")
            options = [
                {
                    "text": text,
                    "is_correct": index == correct_index,
                    "source_error_code": "",
                    "temptation": "",
                    "loss_reason": "",
                    "fix": "",
                }
                for index, text in enumerate(texts)
            ]
            candidates.append(
                {
                    "source_index": source_index,
                    "source_group": group,
                    "source_group_index": group_index,
                    "rule_group": "·".join(
                        value for value in (_field(block, "ep"), _field(block, "topic")) if value
                    ) or "成品随堂练",
                    "stem": stem,
                    "model_answer": texts[correct_index],
                    "options": options,
                    "block": block,
                }
            )
            source_index += 1
    return "bank_drawn", candidates


def _select_five(candidates: list[dict[str, Any]], *, format_kind: str) -> list[dict[str, Any]]:
    if format_kind == "bank_drawn":
        regular = [item for item in candidates if item["source_group"] == "A"][:4]
        diagnostic = [item for item in candidates if item["source_group"] == "Dg"][:1]
        selected = regular + diagnostic
    else:
        diagnostic = [
            item for item in candidates if "诊断" in str(item.get("rule_group") or "")
        ]
        regular = [item for item in candidates if item not in diagnostic]
        selected = regular[:4] + diagnostic[-1:]
        if len(selected) < PRACTICE_LIMIT:
            selected_ids = {id(item) for item in selected}
            selected.extend(
                item for item in candidates if id(item) not in selected_ids
            )
    selected = selected[:PRACTICE_LIMIT]
    if len(selected) != PRACTICE_LIMIT:
        raise PracticeHtmlInvalid("practice_html_requires_five_single_choice_items")
    if len({item["stem"] for item in selected}) != PRACTICE_LIMIT:
        raise PracticeHtmlInvalid("practice_html_duplicate_selected_stem")
    return selected


def compile_practice_surface(
    pack_id: str,
    *,
    surface_id: str,
    html: str,
    source_path: str,
    source_html_sha256: str,
) -> dict[str, Any]:
    """从一个显式注册的 practice surface 编译五题。"""
    normalized_pack = str(pack_id or "").strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_-]{1,31}", normalized_pack):
        raise PracticeHtmlInvalid("practice_html_pack_invalid")
    surface = str(surface_id or "").strip()
    if not re.fullmatch(r"practice(?:[2-9][0-9]*)?\.html", surface):
        raise PracticeHtmlInvalid("practice_html_surface_invalid")
    source_sha = str(source_html_sha256 or "").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
        raise PracticeHtmlInvalid("practice_html_source_sha_invalid")
    if hashlib.sha256(html.encode("utf-8")).hexdigest() != source_sha:
        raise PracticeHtmlInvalid("practice_html_source_bytes_sha_mismatch")
    relative_path = str(source_path or "").strip()
    if not relative_path:
        raise PracticeHtmlInvalid("practice_html_source_path_missing")

    if "const {A,Dg}=this.bank()" in html:
        format_kind, candidates = _bank_candidates(html)
        marker = ""
    else:
        format_kind, marker, candidates = _standard_candidates(html)
    selected = _select_five(candidates, format_kind=format_kind)

    items: list[dict[str, Any]] = []
    for candidate in selected:
        canonical = {
            "answer_type": "single_choice",
            "rule_group": candidate["rule_group"],
            "stem": candidate["stem"],
            "model_answer": candidate["model_answer"],
            "options": candidate["options"],
        }
        variant_id = _question_identity(
            normalized_pack, surface, int(candidate["source_index"]), canonical
        )
        options = [
            {**option, "option_id": f"{variant_id}:option-{index + 1}"}
            for index, option in enumerate(canonical["options"])
        ]
        items.append(
            {
                **canonical,
                "options": options,
                "variant_id": variant_id,
                "surface_id": surface,
                "source_index": candidate["source_index"],
                "source_group": candidate["source_group"],
                "source_group_index": candidate.get("source_group_index"),
                "anchor": f"compiled_html:{relative_path}#Q{int(candidate['source_index']) + 1}",
                "source_html_sha256": source_sha,
            }
        )
    return {
        "surface": {
            "surface_id": surface,
            "source_path": relative_path,
            "source_html_sha256": source_sha,
            "format_kind": format_kind,
            "array_marker": marker,
            "presentation_order": [item["source_index"] for item in items],
            "variant_ids": [item["variant_id"] for item in items],
        },
        "items": items,
    }


def build_practice_authority(
    pack_id: str,
    *,
    source_pack_sha256: str,
    source_bundle_sha256: str,
    compiled_surfaces: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_pack = str(pack_id or "").strip().upper()
    for value, error in (
        (source_pack_sha256, "practice_html_pack_source_sha_invalid"),
        (source_bundle_sha256, "practice_html_bundle_source_sha_invalid"),
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(value or "")):
            raise PracticeHtmlInvalid(error)
    surfaces = [dict(compiled["surface"]) for compiled in compiled_surfaces]
    items = [dict(item) for compiled in compiled_surfaces for item in compiled["items"]]
    if not surfaces or len(items) != PRACTICE_LIMIT * len(surfaces):
        raise PracticeHtmlInvalid("practice_authority_surface_count_invalid")
    if len({item["variant_id"] for item in items}) != len(items):
        raise PracticeHtmlInvalid("practice_html_duplicate_question_identity")
    return {
        "schema_version": SCHEMA_VERSION,
        "pack_id": normalized_pack,
        "source_pack_sha256": source_pack_sha256,
        "source_bundle_sha256": source_bundle_sha256,
        "surfaces": surfaces,
        "items": items,
    }


def _replace_array(text: str, marker: str, blocks: list[str]) -> str:
    start, end = _array_bounds(text, marker)
    rendered = "\n" + ",\n".join(blocks) + "\n  "
    return text[: start + 1] + rendered + text[end - 1 :]


def transform_compiled_practice_html(
    pack_id: str, *, surface: dict[str, Any], items: list[dict[str, Any]], html: str
) -> str:
    """把 public 投影限定为 sidecar 同五题，并注入统一证据桥。"""
    format_kind = str(surface.get("format_kind") or "")
    if len(items) != PRACTICE_LIMIT:
        raise PracticeHtmlInvalid("practice_transform_requires_five_items")
    if format_kind == "bank_drawn":
        for group, marker in (("A", r"\bconst\s+A\s*="), ("Dg", r"\bconst\s+Dg\s*=")):
            source_blocks = _top_level_objects(_array_after(html, marker))
            indexes = [
                int(item["source_group_index"])
                for item in items
                if item.get("source_group") == group
            ]
            html = _replace_array(html, marker, [source_blocks[index] for index in indexes])
        order_methods = "  shuffle(a){ return a.slice(); }\n"
    else:
        marker = str(surface.get("array_marker") or "")
        source_blocks = _top_level_objects(_array_after(html, marker))
        indexes = [int(item["source_index"]) for item in items]
        html = _replace_array(html, marker, [source_blocks[index] for index in indexes])
        if format_kind == "ord_method":
            order_methods = (
                "  pickOrder(){ return [0,1,2,3,4]; }\n"
                "  fallbackOrder(){ return [0,1,2,3,4]; }\n"
                "  ord(){ return [0,1,2,3,4]; }\n"
            )
        elif format_kind == "pool_deck":
            order_methods = "  buildDeck(){ this._order={}; return this.POOL.slice(); }\n"
        else:
            order_methods = ""

    html = re.sub(r"\bSHOW_COUNT\s*=\s*\d+\s*;", "SHOW_COUNT = 5;", html)
    pack_js = json.dumps(str(pack_id or "").strip().upper(), ensure_ascii=False)
    surface_js = json.dumps(str(surface.get("surface_id") or ""), ensure_ascii=False)
    bridge = f"""
{order_methods}  __dtEvidenceAnswers(){{
    const source=Array.isArray(this.state.picks)?this.state.picks:(this.state.sel||{{}});
    return [0,1,2,3,4].map(i=>{{
      const selected=Number(source[i]);
      const permutation=typeof this.optPerm==='function'?this.optPerm(i):null;
      return Array.isArray(permutation)&&Number.isInteger(selected)
        ?Number(permutation[selected]):selected;
    }});
  }}
  __dtRedirectEvidence(onFailure){{
    const answers=this.__dtEvidenceAnswers();
    if(answers.length!==5||answers.some(v=>!Number.isInteger(v)||v<0||v>9)) return false;
    const wxm=window.wx&&window.wx.miniProgram;
    const inMini=(window.__wxjs_environment==='miniprogram')||/miniprogram/i.test(navigator.userAgent||'');
    if(!wxm||!inMini||!wxm.redirectTo) return false;
    const url='/packageDeeptutor/pages/luban/retest/retest?mode=forward&presentation=receipt&pack_id='+encodeURIComponent({pack_js})+'&practice_surface='+encodeURIComponent({surface_js})+'&answer_indexes='+encodeURIComponent(answers.join(','));
    wxm.redirectTo({{url:url,fail:onFailure}});
    return true;
  }}
  setState(patch,...args){{
    const done=patch&&(patch.finished===true||patch.phase==='result');
    if(done){{
      const fallback=()=>DCLogic.prototype.setState.call(this,patch,...args);
      if(this.__dtRedirectEvidence(fallback)) return;
    }}
    return super.setState(patch,...args);
  }}
"""
    close = re.search(r"\n}\s*</script>\s*</body>", html)
    if close is None:
        raise PracticeHtmlInvalid("practice_html_component_close_missing")
    html = html[: close.start()] + "\n" + bridge + html[close.start() :]
    notice = (
        '<div data-deeptutor-practice-authority="server" '
        'style="font-size:10px;line-height:1.6;text-align:center;color:#7b7f80;padding:8px 16px 14px;">'
        '网页预览作答仅供即时反馈；是否形成学习记录，以小程序服务端正式收据为准。</div>'
    )
    if "</x-dc>" not in html:
        raise PracticeHtmlInvalid("practice_html_root_close_missing")
    html = html.replace("</x-dc>", notice + "\n</x-dc>", 1)
    for old, new in (
        ("满分手", "本轮全对"),
        ('"\u7a33\u4e86"', '"\u672c\u8f6e\u5df2完成"'),
        ("采分点都拿到了", "本轮题目已答完"),
        ("满分——采分点抓得稳", "本轮 5 题全对"),
    ):
        html = html.replace(old, new)
    return html


def _validate_authority(value: Any, *, expected_pack: str) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != SCHEMA_VERSION
        or value.get("pack_id") != expected_pack
        or set(value) != set(AUTHORITY_FIELDS)
    ):
        raise PracticeHtmlInvalid("practice_authority_pack_mismatch")
    for key in ("source_pack_sha256", "source_bundle_sha256", "published_lesson_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(value.get(key) or "")):
            raise PracticeHtmlInvalid(f"practice_authority_invalid:{key}")
    surfaces = value.get("surfaces")
    items = value.get("items")
    if not isinstance(surfaces, list) or not surfaces or not isinstance(items, list):
        raise PracticeHtmlInvalid("practice_authority_surfaces_invalid")
    ids: set[str] = set()
    by_surface: dict[str, list[str]] = {}
    for item in items:
        if not isinstance(item, dict) or item.get("answer_type") != "single_choice":
            raise PracticeHtmlInvalid("practice_authority_item_invalid")
        variant_id = str(item.get("variant_id") or "")
        surface_id = str(item.get("surface_id") or "")
        options = item.get("options")
        if not variant_id or variant_id in ids or not surface_id or not isinstance(options, list):
            raise PracticeHtmlInvalid("practice_authority_item_identity_invalid")
        ids.add(variant_id)
        by_surface.setdefault(surface_id, []).append(variant_id)
        if len(options) < 2 or sum(
            option.get("is_correct") is True
            for option in options
            if isinstance(option, dict)
        ) != 1:
            raise PracticeHtmlInvalid("practice_authority_answer_invalid")
    surface_ids = [str(surface.get("surface_id") or "") for surface in surfaces]
    if (
        len(set(surface_ids)) != len(surface_ids)
        or set(surface_ids) != set(by_surface)
        or len(items) != PRACTICE_LIMIT * len(surfaces)
    ):
        raise PracticeHtmlInvalid("practice_authority_surface_set_invalid")
    for surface in surfaces:
        surface_id = str(surface.get("surface_id") or "")
        if (
            not re.fullmatch(r"practice(?:[2-9][0-9]*)?\.html", surface_id)
            or not re.fullmatch(r"[0-9a-f]{64}", str(surface.get("source_html_sha256") or ""))
            or not re.fullmatch(r"[0-9a-f]{64}", str(surface.get("published_practice_sha256") or ""))
            or list(surface.get("variant_ids") or []) != by_surface.get(surface_id)
            or len(by_surface.get(surface_id) or []) != PRACTICE_LIMIT
        ):
            raise PracticeHtmlInvalid("practice_authority_surface_invalid")
    return value


def _registration(pack_id: str) -> tuple[Path, dict[str, Any]] | None:
    try:
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    row = next(
        (
            item
            for item in manifest.get("packs") or []
            if str(item.get("pack_id") or "").strip().upper() == pack_id
        ),
        None,
    )
    practice = dict((row or {}).get("practice") or {})
    relative = str(practice.get("authority_path") or "")
    if practice.get("status") != "compiled" or not re.fullmatch(
        r"[a-z0-9_-]+\.practice\.authority\.json", relative
    ):
        return None
    return _COMPILED_DIR / relative, practice


def is_compiled_practice_pack(pack_id: str) -> bool:
    normalized = str(pack_id or "").strip().upper()
    return bool(normalized and _registration(normalized))


def load_compiled_practice(
    pack_id: str, *, authority_path: Path | None = None
) -> dict[str, Any] | None:
    """只读 manifest 显式登记的 sidecar；缺失/漂移均 fail-close。"""
    normalized = str(pack_id or "").strip().upper()
    registration = None if authority_path is not None else _registration(normalized)
    if authority_path is None and registration is None:
        return None
    path = authority_path or registration[0]
    try:
        raw = path.read_bytes()
        if registration is not None:
            expected_authority_sha = str(
                registration[1].get("authority_sha256") or ""
            )
            if (
                not re.fullmatch(r"[0-9a-f]{64}", expected_authority_sha)
                or hashlib.sha256(raw).hexdigest() != expected_authority_sha
            ):
                raise PracticeHtmlInvalid("practice_authority_digest_mismatch")
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PracticeHtmlInvalid("practice_authority_unavailable") from exc
    authority = _validate_authority(value, expected_pack=normalized)
    if registration is not None:
        practice = registration[1]
        if (
            practice.get("source_bundle_sha256") != authority["source_bundle_sha256"]
            or practice.get("source_pack_sha256") != authority["source_pack_sha256"]
            or int(practice.get("surface_count") or 0) != len(authority["surfaces"])
        ):
            raise PracticeHtmlInvalid("practice_authority_registration_mismatch")
        public = _REPO / "web" / "public" / "luban-preview" / normalized.lower()
        projections = [
            (str(authority["published_lesson_sha256"]), public / "lesson.html"),
            *[
                (
                    str(surface["published_practice_sha256"]),
                    public / str(surface["surface_id"]),
                )
                for surface in authority["surfaces"]
            ],
        ]
        for expected_sha, projection in projections:
            try:
                actual = hashlib.sha256(projection.read_bytes()).hexdigest()
            except OSError as exc:
                raise PracticeHtmlInvalid("practice_public_projection_unavailable") from exc
            if actual != expected_sha:
                raise PracticeHtmlInvalid("practice_public_projection_sha_mismatch")
    return authority


def compiled_practice_bundle_sha(pack_id: str) -> str:
    practice = load_compiled_practice(pack_id)
    return str((practice or {}).get("source_bundle_sha256") or "")


def _surface_items(practice: dict[str, Any], surface_id: str) -> list[dict[str, Any]]:
    requested = str(surface_id or "practice.html").strip()
    surface = next(
        (item for item in practice["surfaces"] if item.get("surface_id") == requested),
        None,
    )
    if surface is None:
        raise PracticeHtmlInvalid("practice_authority_surface_not_found")
    by_id = {item["variant_id"]: item for item in practice["items"]}
    return [by_id[variant_id] for variant_id in surface["variant_ids"]]


def resolve_compiled_practice_items(
    pack_id: str, *, surface_id: str = "", variant_ids: list[str] | None = None
) -> list[dict[str, Any]] | None:
    practice = load_compiled_practice(pack_id)
    if practice is None:
        return None
    if variant_ids is not None:
        wanted = [str(item or "").strip() for item in variant_ids]
        matches = [
            _surface_items(practice, str(surface["surface_id"]))
            for surface in practice["surfaces"]
        ]
        selected = next(
            (items for items in matches if [item["variant_id"] for item in items] == wanted),
            None,
        )
        if selected is None:
            raise PracticeHtmlInvalid("practice_authority_variant_set_not_found")
        return selected
    return _surface_items(practice, surface_id or "practice.html")


def project_compiled_practice(
    pack_id: str, *, expected_pack_sha256: str = "", surface_id: str = ""
) -> list[dict[str, Any]] | None:
    practice = load_compiled_practice(pack_id)
    if practice is None:
        return None
    expected_sha = str(expected_pack_sha256 or "").strip()
    if expected_sha and practice["source_pack_sha256"] != expected_sha:
        return None
    items = _surface_items(practice, surface_id or "practice.html")
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
        for item in items
    ]


__all__ = [
    "AUTHORITY_FIELDS",
    "PRACTICE_LIMIT",
    "PracticeHtmlInvalid",
    "build_practice_authority",
    "compile_practice_surface",
    "compiled_practice_bundle_sha",
    "is_compiled_practice_pack",
    "load_compiled_practice",
    "project_compiled_practice",
    "resolve_compiled_practice_items",
    "transform_compiled_practice_html",
]
