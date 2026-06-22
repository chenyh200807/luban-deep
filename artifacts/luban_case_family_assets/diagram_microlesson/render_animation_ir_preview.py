#!/usr/bin/env python3
"""Render a student-safe HTML preview from luban_animation_ir.v0.

This is the OpenMAIC-style path: animation IR declares scene/focus/enter/exit;
the renderer deterministically draws one active scene at a time. It does not
infer visual state from accumulated `reached-*` classes.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def js_json(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


TONES: dict[str, dict[str, str]] = {
    "danger": {"fill": "#fff7ed", "stroke": "#f97316", "text": "#9a3412"},
    "success": {"fill": "#ecfdf5", "stroke": "#10b981", "text": "#047857"},
    "blue": {"fill": "#eff6ff", "stroke": "#60a5fa", "text": "#1d4ed8"},
    "amber": {"fill": "#fffbeb", "stroke": "#f59e0b", "text": "#b45309"},
    "neutral": {"fill": "#f8fafc", "stroke": "#cbd5e1", "text": "#334155"},
}


def _tone(name: object) -> dict[str, str]:
    return TONES.get(str(name or "neutral"), TONES["neutral"])


def _visual_group(node: dict[str, Any], body: str) -> str:
    node_id = esc(node.get("id", "node"))
    kind = esc(node.get("kind", "node"))
    return f'<g data-visible-node="{node_id}" data-visual-node-id="{node_id}" data-visual-kind="{kind}">{body}</g>'


def _svg_text(text: object, x: object, y: object, *, size: int = 14, fill: str = "#0f1722", weight: int = 900, anchor: str = "middle") -> str:
    parts = str(text or "").split("\n")
    lines = []
    for index, part in enumerate(parts):
        dy = index * (size + 5)
        lines.append(
            f'<text x="{esc(x)}" y="{esc(float(y) + dy)}" text-anchor="{anchor}" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}">{esc(part)}</text>'
        )
    return "".join(lines)


def _fit_font_size(text: object, width: float, base: int, *, minimum: int = 10) -> int:
    longest = max((len(line) for line in str(text or "").split("\n")), default=0)
    if longest <= 0:
        return base
    # SVG text has no layout engine; keep labels inside their primitive instead
    # of relying on the browser to wrap or clip.
    estimated = int((max(width - 20, 24) / max(longest, 1)) * 1.08)
    return max(minimum, min(base, estimated))


def _labels(node: dict[str, Any], defaults: list[str], limit: int) -> list[str]:
    raw = [str(item) for item in node.get("labels", []) if item is not None]
    return (raw + defaults)[:limit]


def _label_badge(text: object, cx: float, cy: float, *, tone: dict[str, str], width: float | None = None, size: int = 12) -> str:
    label = str(text or "")
    if not label:
        return ""
    badge_w = width or max(54, min(116, len(label) * size * 0.92 + 22))
    badge_h = size + 13
    x = cx - badge_w / 2
    y = cy - badge_h / 2
    return (
        f'<rect x="{x}" y="{y}" width="{badge_w}" height="{badge_h}" rx="8" '
        f'fill="{tone["fill"]}" stroke="{tone["stroke"]}" stroke-width="1.6"/>'
        + _svg_text(label, cx, cy + size * 0.34, size=size, fill=tone["text"], weight=900)
    )


def _step_group(index: int, body: str, *, trace: bool = False) -> str:
    trace_attr = ' data-trace="1"' if trace else ""
    return f'<g data-primitive-step="{index}"{trace_attr}>{body}</g>'


def _roof_section(node: dict[str, Any]) -> str:
    x = float(node.get("x", 32))
    y = float(node.get("y", 150))
    w = float(node.get("w", 296))
    base_h = float(node.get("base_h", 58))
    return _visual_group(
        node,
        _step_group(
            0,
            f'<rect x="{x}" y="{y + 28}" width="{w}" height="{base_h}" rx="4" fill="#87919d"/>'
            f'<text x="{x + 12}" y="{y + 45}" font-size="10" font-weight="900" fill="#f8fafc">基层</text>',
        )
        + _step_group(1, f'<rect x="{x}" y="{y + 12}" width="{w}" height="16" fill="#c5b78f"/>')
        + _step_group(
            2,
            f'<rect x="{x}" y="{y}" width="{w}" height="12" fill="#34465b"/>'
            f'<text x="{x + 12}" y="{y + 9}" font-size="10" font-weight="900" fill="#e2edf7">卷材</text>',
        ),
    )


def _scaffold_frame(node: dict[str, Any]) -> str:
    x = float(node.get("x", 36))
    y = float(node.get("y", 50))
    w = float(node.get("w", 288))
    h = float(node.get("h", 176))
    labels = _labels(node, ["荷载先落架体", "立杆传到底座", "扫地杆锁底部", "连墙件防侧倒"], 4)
    post_x = [x + w * 0.18, x + w * 0.38, x + w * 0.62, x + w * 0.82]
    top_y = y + h * 0.22
    mid_y = y + h * 0.48
    low_y = y + h * 0.72
    base_y = y + h * 0.88
    brace_path = (
        f"M{post_x[0]} {base_y} L{post_x[1]} {top_y} "
        f"M{post_x[1]} {base_y} L{post_x[2]} {top_y} "
        f"M{post_x[2]} {base_y} L{post_x[3]} {top_y}"
    )
    title = node.get("text") or "临时支撑系统"
    return _visual_group(
        node,
        _step_group(0, _svg_text(title, x + w / 2, y + 10, size=16, fill="#176b7a"))
        + _step_group(
            1,
            f'<rect x="{x + 18}" y="{top_y - 18}" width="{w - 36}" height="14" rx="5" fill="#94a3b8"/>'
            f'<path d="M{x + 14} {base_y + 8} H{x + w - 14}" stroke="#8b8172" stroke-width="7" stroke-linecap="round"/>',
        )
        + _step_group(
            2,
            "".join(
                f'<path d="M{px} {top_y - 16} V{base_y}" stroke="#334155" stroke-width="5" stroke-linecap="round"/>'
                for px in post_x
            ),
            trace=True,
        )
        + _step_group(
            3,
            "".join(
                f'<path d="M{post_x[0] - 22} {yy} H{post_x[-1] + 22}" stroke="#64748b" stroke-width="4" stroke-linecap="round"/>'
                for yy in [top_y, mid_y, low_y]
            ),
            trace=True,
        )
        + _step_group(
            4,
            f'<path d="{brace_path}" stroke="#f59e0b" stroke-width="4" stroke-linecap="round" opacity=".92"/>'
            f'<path d="M{post_x[-1] + 8} {mid_y} H{x + w + 10}" stroke="#60a5fa" stroke-width="4" stroke-linecap="round" stroke-dasharray="8 6"/>',
            trace=True,
        )
        + _step_group(5, _label_badge(labels[0], x + w / 2, top_y - 34, tone=_tone("blue"), width=122, size=11))
        + _step_group(6, _label_badge(labels[1], x + 68, mid_y + 30, tone=_tone("success"), width=116, size=10))
        + _step_group(7, _label_badge(labels[2], x + w - 70, mid_y - 26, tone=_tone("amber"), width=122, size=10))
        + _step_group(8, _label_badge(labels[3], x + w - 76, top_y + 30, tone=_tone("blue"), width=116, size=10)),
    )


def _primitive_svg(node: dict[str, Any]) -> str:
    kind = str(node.get("kind", "note"))
    tone = _tone(node.get("tone"))
    x = float(node.get("x", 0))
    y = float(node.get("y", 0))
    w = float(node.get("w", 180))
    h = float(node.get("h", 42))
    text = node.get("text", "")
    subtext = node.get("subtext", "")
    if kind == "pill":
        title_size = _fit_font_size(text, w, 16, minimum=11)
        sub_size = _fit_font_size(subtext, w, 12, minimum=10)
        title_y = y + (h * 0.42 if subtext else h / 2 + title_size * 0.36)
        text_svg = _svg_text(text, x + w / 2, title_y, size=title_size, fill=tone["text"])
        if subtext:
            text_svg += _svg_text(subtext, x + w / 2, y + h * 0.76, size=sub_size, fill=tone["text"], weight=800)
        return _visual_group(
            node,
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{tone["fill"]}" stroke="{tone["stroke"]}" stroke-width="3"/>{text_svg}',
        )
    if kind == "roof_section":
        return _roof_section(node)
    if kind == "scaffold_frame":
        return _scaffold_frame(node)
    if kind == "bulge":
        cx = float(node.get("x", 180))
        by = float(node.get("base_y", 150))
        return _visual_group(
            node,
            f'<path d="M{cx - 34} {by} Q{cx} {by - 58} {cx + 34} {by} Z" fill="#34465b" stroke="#60a5fa" stroke-width="4"/>'
            + _svg_text(text, cx, by - 76, size=15, fill="#1d4ed8"),
        )
    if kind == "up_arrows":
        cx = x
        yy = y
        return _visual_group(
            node,
            f'<path d="M{cx - 16} {yy} V{yy - 32} M{cx} {yy} V{yy - 42} M{cx + 16} {yy} V{yy - 32}" stroke="#f59e0b" stroke-width="4" stroke-linecap="round"/>'
            f'<path d="M{cx - 22} {yy - 26} l6 -8 l6 8 M{cx - 6} {yy - 36} l6 -8 l6 8 M{cx + 10} {yy - 26} l6 -8 l6 8" fill="none" stroke="#f59e0b" stroke-width="3"/>',
        )
    if kind == "up_arrow":
        hh = float(node.get("h", 54))
        return _visual_group(
            node,
            f'<path d="M{x} {y} V{y - hh}" stroke="#ef4444" stroke-width="4" stroke-linecap="round"/>'
            f'<path d="M{x - 9} {y - hh + 12} l9 -13 l9 13" fill="none" stroke="#ef4444" stroke-width="4" stroke-linecap="round"/>',
        )
    if kind == "cut_cross":
        return _visual_group(
            node,
            f'<path d="M{x - 18} {y + 18} L{x + 18} {y - 18} M{x - 18} {y - 18} L{x + 18} {y + 18}" stroke="#ef4444" stroke-width="8" stroke-linecap="round"/>'
            + _svg_text(text, x, y - 42, size=16, fill="#b91c1c"),
        )
    if kind == "dry_zone":
        return _visual_group(
            node,
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="none" stroke="#60a5fa" stroke-width="5" stroke-dasharray="9 7"/>'
            + _svg_text(text, x + w / 2, y - 18, size=16, fill="#1d4ed8"),
        )
    if kind == "sweep_line":
        return _visual_group(
            node,
            f'<path d="M{x} {y} H{x + w}" stroke="#f59e0b" stroke-width="5" stroke-linecap="round"/>'
            + _svg_text(text, x + w / 2, y + 24, size=13, fill="#b45309"),
        )
    if kind == "membrane_strip":
        return _visual_group(
            node,
            f'<rect x="{x}" y="{y}" width="{w}" height="14" rx="5" fill="{tone["stroke"]}"/>'
            + _svg_text(text, x + w / 2, y - 18, size=16, fill=tone["text"]),
        )
    if kind == "coverage_bracket":
        x1 = float(node.get("x1", x))
        x2 = float(node.get("x2", x + w))
        yy = float(node.get("y", y))
        return _visual_group(
            node,
            f'<path d="M{x1} {yy - 12} v22 M{x2} {yy - 12} v22 M{x1} {yy} H{x2}" stroke="#10b981" stroke-width="4" fill="none"/>'
            + _svg_text(text, (x1 + x2) / 2, yy + 32, size=13, fill="#047857"),
        )
    if kind == "lap_curve":
        x1 = float(node.get("x1", x))
        x2 = float(node.get("x2", x + w))
        yy = float(node.get("y", y))
        return _visual_group(
            node,
            f'<path d="M{x1} {yy} C{x1 + 40} {yy + 26} {x2 - 40} {yy + 26} {x2} {yy}" stroke="#60a5fa" stroke-width="4" fill="none" stroke-dasharray="10 7"/>',
        )
    if kind == "water_layer":
        return _visual_group(
            node,
            f'<rect x="{x}" y="{y}" width="{w}" height="24" rx="7" fill="#60a5fa" opacity=".72"/>'
            + _svg_text(text, x + w / 2, y - 16, size=16, fill="#1d4ed8"),
        )
    if kind == "check_badge":
        return _visual_group(
            node,
            f'<circle cx="{x}" cy="{y}" r="24" fill="#ecfdf5" stroke="#10b981" stroke-width="4"/><text x="{x}" y="{y + 9}" text-anchor="middle" font-size="28" font-weight="900" fill="#047857">✓</text>',
        )
    if kind == "process_flow":
        labels = _labels(node, ["先判", "再做", "复核", "写分"], 4)
        step_gap = w / max(len(labels), 1)
        parts = [
            _step_group(0, _svg_text(text or "按顺序 reveal", x + w / 2, y + 30, size=15, fill=tone["text"])),
            _step_group(1, f'<path d="M{x + 34} {y + 88} H{x + w - 34}" stroke="#cbd5e1" stroke-width="8" stroke-linecap="round"/>', trace=True),
        ]
        for index, label in enumerate(labels):
            cx = x + step_gap * index + step_gap / 2
            circle_tone = _tone(["blue", "success", "amber", "neutral"][index % 4])
            size = _fit_font_size(label, 68, 13, minimum=10)
            parts.append(
                _step_group(
                    index + 2,
                    f'<circle cx="{cx}" cy="{y + 88}" r="31" fill="{circle_tone["fill"]}" stroke="{circle_tone["stroke"]}" stroke-width="4"/>'
                    f'<text x="{cx}" y="{y + 93}" text-anchor="middle" font-size="{size}" font-weight="900" fill="{circle_tone["text"]}">{esc(label)}</text>'
                    f'<text x="{cx}" y="{y + 142}" text-anchor="middle" font-size="12" font-weight="900" fill="#64748b">第{index + 1}步</text>',
                )
            )
        return _visual_group(node, "".join(parts))
    if kind == "layer_stack":
        labels = _labels(node, ["面层", "防水层", "找平层", "基层"], 4)
        colors = ["#60a5fa", "#10b981", "#c5b78f", "#87919d"]
        parts = [_step_group(0, _svg_text(text or "剖面分层", x + w / 2, y + 36, size=16, fill=tone["text"]))]
        layer_h = 28
        start_y = y + 70
        parts.append(_step_group(1, f'<rect x="{x + 28}" y="{start_y - 12}" width="{w - 56}" height="{len(labels) * layer_h + 8}" rx="18" fill="none" stroke="#eadfcb" stroke-width="3"/>'))
        for index, label in enumerate(labels):
            yy = start_y + index * layer_h
            parts.append(
                _step_group(
                    index + 2,
                    f'<rect x="{x + 38}" y="{yy}" width="{w - 76}" height="{layer_h - 4}" rx="6" fill="{colors[index % len(colors)]}" opacity=".88"/>'
                    f'<text x="{x + 18}" y="{yy + 18}" text-anchor="start" font-size="12" font-weight="900" fill="#334155">{esc(label)}</text>',
                )
            )
        return _visual_group(node, "".join(parts))
    if kind == "network_graph":
        labels = _labels(node, ["A", "B", "C", "D"], 4)
        coords = [(x + 36, y + 118), (x + 112, y + 72), (x + 112, y + 164), (x + 206, y + 118), (x + 282, y + 118)]
        parts = [
            _step_group(0, _svg_text(text or "图上推演", x + w / 2, y + 32, size=16, fill=tone["text"])),
            _step_group(1, f'<path d="M{coords[0][0] + 24} {coords[0][1]} C{x + 78} {y + 116} {x + 72} {y + 76} {coords[1][0] - 24} {coords[1][1]}" stroke="#94a3b8" stroke-width="5" fill="none"/>', trace=True),
            _step_group(2, f'<path d="M{coords[0][0] + 24} {coords[0][1]} C{x + 78} {y + 120} {x + 72} {y + 164} {coords[2][0] - 24} {coords[2][1]}" stroke="#cbd5e1" stroke-width="5" fill="none"/>', trace=True),
            _step_group(3, f'<path d="M{coords[1][0] + 24} {coords[1][1]} H{coords[3][0] - 24} M{coords[2][0] + 24} {coords[2][1]} C{x + 164} {y + 164} {x + 166} {y + 122} {coords[3][0] - 24} {coords[3][1]}" stroke="#60a5fa" stroke-width="5" fill="none"/>', trace=True),
            _step_group(4, f'<path d="M{coords[3][0] + 24} {coords[3][1]} H{coords[4][0] - 24}" stroke="#10b981" stroke-width="5" fill="none"/>', trace=True),
        ]
        node_labels = ["始", labels[0], labels[1], labels[2], "终"]
        for index, (cx, cy) in enumerate(coords):
            fill = "#fff7ed" if index in [0, 4] else "#eff6ff"
            stroke = "#f97316" if index in [0, 4] else "#60a5fa"
            parts.append(_step_group(index + 5, f'<rect x="{cx - 25}" y="{cy - 20}" width="50" height="40" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="3"/><text x="{cx}" y="{cy + 5}" text-anchor="middle" font-size="13" font-weight="900" fill="#172033">{esc(node_labels[index])}</text>'))
        return _visual_group(node, "".join(parts))
    if kind == "formula_chain":
        labels = _labels(node, ["口径", "数量", "单价", "扣减"], 4)
        start_x = x + 34
        box_w = max(48, (w - 92) / max(len(labels), 1))
        parts = [_step_group(0, _svg_text(text or "计算口径", x + w / 2, y + 44, size=16, fill=tone["text"]))]
        for index, label in enumerate(labels):
            bx = start_x + index * (box_w + 12)
            parts.append(
                _step_group(
                    index + 1,
                    f'<rect x="{bx}" y="{y + 82}" width="{box_w}" height="48" rx="14" fill="#fff7ed" stroke="#f59e0b" stroke-width="3"/>'
                    + _svg_text(label, bx + box_w / 2, y + 112, size=_fit_font_size(label, box_w, 13, minimum=10), fill="#b45309")
                    + (f'<path d="M{bx + box_w + 3} {y + 106} H{bx + box_w + 13}" stroke="#f97316" stroke-width="4" stroke-linecap="round"/>' if index < len(labels) - 1 else ""),
                    trace=index < len(labels) - 1,
                )
            )
        return _visual_group(
            node,
            "".join(parts) + _step_group(len(labels) + 1, f'<path d="M{x + 56} {y + 170} H{x + w - 56}" stroke="#f97316" stroke-width="6" stroke-linecap="round"/>', trace=True),
        )
    if kind == "decision_tree":
        labels = _labels(node, ["对象", "条件", "阈值", "结论"], 4)
        parts = [
            _step_group(0, _svg_text(text or "判断树", x + w / 2, y + 20, size=16, fill=tone["text"])),
            _step_group(
                1,
                f'<rect x="{x + 66}" y="{y + 30}" width="{w - 132}" height="38" rx="13" fill="#ecfdf5" stroke="#10b981" stroke-width="3"/>'
                + _svg_text(labels[0], x + w / 2, y + 55, size=13, fill="#047857"),
            ),
        ]
        gate_y = y + 100
        for index, label in enumerate(labels[1:4]):
            cx = x + 50 + index * ((w - 100) / 2)
            parts.append(
                _step_group(
                    index + 2,
                    f'<path d="M{x + w / 2} {y + 68} V{gate_y - 16} H{cx}" stroke="#94a3b8" stroke-width="3" fill="none"/>'
                    f'<rect x="{cx - 38}" y="{gate_y}" width="76" height="42" rx="12" fill="#f8fafc" stroke="#cbd5e1" stroke-width="3"/><text x="{cx}" y="{gate_y + 27}" text-anchor="middle" font-size="{_fit_font_size(label, 76, 12, minimum=10)}" font-weight="900" fill="#334155">{esc(label)}</text>',
                    trace=True,
                )
            )
        return _visual_group(node, "".join(parts))
    if kind == "contrast_pair":
        labels = _labels(node, ["错误做法", "正确做法", "错因", "采分"], 4)
        left = labels[0]
        right = labels[1] if len(labels) > 1 else "正确做法"
        return _visual_group(
            node,
            _step_group(0, _svg_text(text or "左右对照", x + w / 2, y + 28, size=16, fill=tone["text"]))
            + _step_group(
                1,
                f'<rect x="{x + 20}" y="{y + 62}" width="{w / 2 - 30}" height="102" rx="16" fill="#fff7ed" stroke="#f97316" stroke-width="4"/>'
                + _svg_text("错", x + 42, y + 88, size=18, fill="#9a3412")
                + _svg_text(left, x + 20 + (w / 2 - 30) / 2, y + 125, size=_fit_font_size(left, w / 2 - 46, 14, minimum=10), fill="#9a3412"),
            )
            + _step_group(
                2,
                f'<rect x="{x + w / 2 + 10}" y="{y + 62}" width="{w / 2 - 30}" height="102" rx="16" fill="#ecfdf5" stroke="#10b981" stroke-width="4"/>'
                + _svg_text("对", x + w / 2 + 32, y + 88, size=18, fill="#047857")
                + _svg_text(right, x + w / 2 + 10 + (w / 2 - 30) / 2, y + 125, size=_fit_font_size(right, w / 2 - 46, 14, minimum=10), fill="#047857"),
            ),
        )
    if kind == "answer_scan":
        labels = _labels(node, ["对象", "条件", "依据", "采分句"], 4)
        states = [("#ecfdf5", "#10b981", "hit"), ("#fffbeb", "#f59e0b", "partial"), ("#fef2f2", "#ef4444", "miss"), ("#eff6ff", "#60a5fa", "fix")]
        row_top = y + 62
        row_h = 28
        board_bottom = 240
        default_gap = 38
        row_gap = float(node.get("row_gap", min(default_gap, max(28, (board_bottom - row_top - row_h) / max(len(labels) - 1, 1)))))
        parts = [_step_group(0, _svg_text(text or "答案逐句扫描", x + w / 2, y + 34, size=16, fill=tone["text"]))]
        for index, label in enumerate(labels):
            yy = row_top + index * row_gap
            fill, stroke, tag = states[index % len(states)]
            parts.append(_step_group(index + 1, f'<rect x="{x + 30}" y="{yy}" width="{w - 60}" height="28" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="2"/><text x="{x + 44}" y="{yy + 19}" text-anchor="start" font-size="12" font-weight="900" fill="#172033">{esc(label)}</text><text x="{x + w - 46}" y="{yy + 19}" text-anchor="middle" font-size="11" font-weight="900" fill="#64748b">{tag}</text>'))
        return _visual_group(node, "".join(parts))
    if kind == "memory_table":
        labels = _labels(node, ["数值", "条件", "例外", "记忆钩子"], 4)
        parts = [_svg_text(text or "参数辨析", x + w / 2, y + 32, size=16, fill=tone["text"])]
        for index, label in enumerate(labels):
            yy = y + 58 + index * 36
            parts.append(f'<rect x="{x + 38}" y="{yy}" width="{w - 76}" height="28" rx="8" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/><text x="{x + 56}" y="{yy + 19}" text-anchor="start" font-size="12" font-weight="900" fill="#334155">{esc(label)}</text>')
        return _visual_group(node, "".join(parts))
    if kind == "answer_box":
        return _visual_group(
            node,
            f'<rect x="{x}" y="{y}" width="{w}" height="38" rx="11" fill="{tone["fill"]}" stroke="{tone["stroke"]}" stroke-width="2"/>'
            + _svg_text(text, x + w / 2, y + 24, size=13, fill=tone["text"]),
        )
    if kind == "dialogue_box":
        return _visual_group(
            node,
            f'<rect x="{x}" y="{y}" width="{w}" height="42" rx="12" fill="{tone["fill"]}" stroke="{tone["stroke"]}" stroke-width="2"/>'
            + _svg_text(text, x + w / 2, y + 26, size=13, fill=tone["text"]),
        )
    if kind == "note":
        title_size = _fit_font_size(text, w, 13, minimum=10)
        return _visual_group(
            node,
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{tone["fill"]}" stroke="{tone["stroke"]}" stroke-width="2" stroke-dasharray="7 5"/>'
            + _svg_text(text, x + w / 2, y + h / 2 + title_size * 0.36, size=title_size, fill=tone["text"]),
        )
    if kind == "closing_text":
        return _visual_group(
            node,
            _svg_text(text, 180, 90, size=18, fill="#047857") + _svg_text(subtext, 180, 132, size=19, fill="#0f1722"),
        )
    if kind == "challenge_button":
        return _visual_group(
            node,
            f'<rect x="90" y="166" width="180" height="44" rx="22" fill="#ffd27f"/><text x="180" y="194" text-anchor="middle" font-size="17" font-weight="900" fill="#0f1722">{esc(text)}</text>',
        )
    if kind == "flow_arrow":
        x1 = float(node.get("x1", x))
        x2 = float(node.get("x2", x + w))
        yy = float(node.get("y", y))
        stroke = tone["stroke"]
        label_text = str(text or "")
        badge_w = max(54, min(116, len(label_text) * 12 * 0.92 + 22))
        line_start = x1 + badge_w + 12 if label_text else x1
        if line_start > x2 - 30:
            line_start = x1
        label = _label_badge(label_text, x1 + badge_w / 2, yy, tone=tone, width=badge_w, size=12) if label_text else ""
        return _visual_group(
            node,
            f'<path d="M{line_start} {yy} H{x2}" stroke="{stroke}" stroke-width="5" stroke-linecap="round"/>'
            f'<path d="M{x2 - 12} {yy - 8} L{x2} {yy} L{x2 - 12} {yy + 8}" fill="none" stroke="{stroke}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
            + label,
        )
    if kind == "threshold_meter":
        value = max(0, min(1, float(node.get("value", 0.62))))
        marker = x + w * value
        label_y = float(node.get("label_y", y - 12 if y + 52 > 244 else y + 48))
        label_size = _fit_font_size(text, w, 13, minimum=10)
        return _visual_group(
            node,
            f'<rect x="{x}" y="{y}" width="{w}" height="18" rx="9" fill="#e2e8f0"/>'
            f'<rect x="{x}" y="{y}" width="{w * value}" height="18" rx="9" fill="{tone["stroke"]}" opacity=".85"/>'
            f'<path d="M{marker} {y - 8} V{y + 30}" stroke="#f97316" stroke-width="4" stroke-linecap="round"/>'
            + _svg_text(text, x + w / 2, label_y, size=label_size, fill=tone["text"]),
        )
    raise ValueError(f"unsupported visual primitive kind: {kind}")


def _visual_svg(scene: dict[str, Any], visual_library: dict[str, Any]) -> str | None:
    visual = visual_library.get(str(scene.get("id")))
    if not visual:
        return None
    board = str(visual.get("board", "warm_grid"))
    if board == "paper":
        background = '<rect x="28" y="30" width="304" height="210" rx="18" fill="#fffdf7" stroke="#eadfcb" stroke-width="4"/>' + _svg_text("答题纸这样写", 54, 72, size=15, fill="#176b7a", anchor="start")
    elif board == "closing":
        background = '<rect x="24" y="34" width="312" height="198" rx="22" fill="#ecfdf5" stroke="#10b981" stroke-width="3"/>'
    else:
        background = '<rect x="12" y="18" width="336" height="234" rx="22" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><path d="M44 66 H316 M44 120 H316 M44 174 H316 M88 40 V230 M180 40 V230 M272 40 V230" stroke="#f0e7d8" stroke-width="1.2"/>'
    nodes = "".join(_primitive_svg(node) for node in visual.get("nodes", []))
    label = esc(scene.get("label", "教学图"))
    return f'<svg viewBox="0 0 360 270" role="img" aria-label="{label}">{background}{nodes}</svg>'


def _section_svg(scene_id: str) -> str:
    overlays: dict[str, str] = {
        "hook": """
          <g data-visible-node="wrong_phrase"><rect x="48" y="70" width="264" height="44" rx="12" fill="#fff7ed" stroke="#f97316" stroke-width="3"/><text x="180" y="98" text-anchor="middle" font-size="18" font-weight="900" fill="#9a3412">错觉:只写“修补防水层”</text></g>
          <g data-visible-node="score_goal"><rect x="76" y="138" width="208" height="54" rx="14" fill="#ecfdf5" stroke="#10b981" stroke-width="3"/><text x="180" y="161" text-anchor="middle" font-size="15" font-weight="900" fill="#047857">目标:写出修补闭环</text><text x="180" y="181" text-anchor="middle" font-size="13" font-weight="800" fill="#047857">治因 → 闭合 → 检验</text></g>
        """,
        "disease": """
          <g data-visible-node="roof_section"><rect x="32" y="176" width="296" height="52" rx="4" fill="#87919d"/><rect x="32" y="160" width="296" height="16" fill="#c5b78f"/><rect x="32" y="148" width="296" height="12" fill="#34465b"/></g>
          <g data-visible-node="bulge"><path d="M146 148 Q180 92 214 148 Z" fill="#34465b" stroke="#7fc7ff" stroke-width="3"/><text x="180" y="88" text-anchor="middle" font-size="16" font-weight="900" fill="#7fc7ff">气/水汽顶起卷材</text></g>
          <g data-visible-node="vapour_arrows"><path d="M164 144 V116 M180 144 V108 M196 144 V116" stroke="#ffd27f" stroke-width="4" stroke-linecap="round"/><path d="M158 120 l6 -8 l6 8 M174 112 l6 -8 l6 8 M190 120 l6 -8 l6 8" fill="none" stroke="#ffd27f" stroke-width="3"/></g>
        """,
        "cut": """
          <g data-visible-node="roof_section"><rect x="32" y="176" width="296" height="52" rx="4" fill="#87919d"/><rect x="32" y="160" width="296" height="16" fill="#c5b78f"/><rect x="32" y="148" width="296" height="12" fill="#34465b"/></g>
          <g data-visible-node="cut_cross"><path d="M162 162 L198 126 M162 126 L198 162" stroke="#ef4444" stroke-width="8" stroke-linecap="round"/><text x="180" y="106" text-anchor="middle" font-size="17" font-weight="900" fill="#fecaca">割开放气</text></g>
          <g data-visible-node="gas_escape"><path d="M180 128 V84" stroke="#fecaca" stroke-width="4"/><path d="M170 94 l10 -14 l10 14" fill="none" stroke="#fecaca" stroke-width="4"/></g>
          <g data-visible-node="direct_cover_trap"><text x="180" y="235" text-anchor="middle" font-size="14" font-weight="900" fill="#f97316">不先放气,直接盖层还会再鼓</text></g>
        """,
        "dry": """
          <g data-visible-node="roof_section"><rect x="32" y="176" width="296" height="52" rx="4" fill="#87919d"/><rect x="32" y="160" width="296" height="16" fill="#c5b78f"/><rect x="32" y="148" width="296" height="12" fill="#34465b"/></g>
          <g data-visible-node="dry_zone"><rect x="120" y="142" width="120" height="38" rx="8" fill="none" stroke="#7fc7ff" stroke-width="5" stroke-dasharray="9 7"/><text x="180" y="118" text-anchor="middle" font-size="17" font-weight="900" fill="#7fc7ff">排气干燥</text></g>
          <g data-visible-node="old_glue"><path d="M126 184 H234" stroke="#ffd27f" stroke-width="5" stroke-linecap="round"/><text x="180" y="210" text-anchor="middle" font-size="14" font-weight="900" fill="#ffd27f">清除旧胶结料 / 清基层</text></g>
        """,
        "add": """
          <g data-visible-node="roof_section"><rect x="32" y="176" width="296" height="52" rx="4" fill="#87919d"/><rect x="32" y="160" width="296" height="16" fill="#c5b78f"/><rect x="32" y="148" width="296" height="12" fill="#34465b"/></g>
          <g data-visible-node="reinforcement_layer"><rect x="112" y="136" width="136" height="14" rx="5" fill="#10b981"/><text x="180" y="118" text-anchor="middle" font-size="17" font-weight="900" fill="#bbf7d0">增铺附加层</text></g>
          <g data-visible-node="edge_coverage"><path d="M112 156 v18 M248 156 v18 M112 166 H248" stroke="#bbf7d0" stroke-width="4" fill="none"/><text x="180" y="198" text-anchor="middle" font-size="14" font-weight="900" fill="#bbf7d0">盖过病害边缘</text></g>
        """,
        "seal": """
          <g data-visible-node="roof_section"><rect x="32" y="176" width="296" height="52" rx="4" fill="#87919d"/><rect x="32" y="160" width="296" height="16" fill="#c5b78f"/><rect x="32" y="148" width="296" height="12" fill="#34465b"/></g>
          <g data-visible-node="new_membrane_lap"><rect x="88" y="128" width="184" height="14" rx="5" fill="#60a5fa"/><text x="180" y="108" text-anchor="middle" font-size="17" font-weight="900" fill="#bfdbfe">新卷材搭接</text></g>
          <g data-visible-node="lap_joint"><path d="M88 150 C126 174 230 174 272 150" stroke="#bfdbfe" stroke-width="4" fill="none" stroke-dasharray="10 7"/></g>
          <g data-visible-node="seal_edge"><text x="180" y="204" text-anchor="middle" font-size="14" font-weight="900" fill="#bfdbfe">边缘和搭接缝封严</text></g>
        """,
        "test": """
          <g data-visible-node="roof_section"><rect x="32" y="176" width="296" height="52" rx="4" fill="#87919d"/><rect x="32" y="160" width="296" height="16" fill="#c5b78f"/><rect x="32" y="148" width="296" height="12" fill="#34465b"/></g>
          <g data-visible-node="water_layer"><rect x="32" y="116" width="296" height="24" rx="6" fill="#7fc7ff" opacity=".72"/><text x="180" y="99" text-anchor="middle" font-size="17" font-weight="900" fill="#bfdbfe">蓄水 / 淋水检验</text></g>
          <g data-visible-node="result_tick"><circle cx="180" cy="198" r="24" fill="#052e1a" stroke="#10b981" stroke-width="4"/><text x="180" y="207" text-anchor="middle" font-size="26" font-weight="900" fill="#bbf7d0">✓</text></g>
        """,
    }
    return f"""<svg viewBox="0 0 360 270" role="img" aria-label="屋面卷材起鼓割补教学图">
      <rect x="12" y="18" width="336" height="234" rx="22" fill="#101b28" stroke="#24364b" stroke-width="2"/>
      {overlays.get(scene_id, overlays["disease"])}
    </svg>"""


def _answer_paper_svg() -> str:
    return """<svg viewBox="0 0 360 270" role="img" aria-label="答题纸采分句">
      <rect x="28" y="32" width="304" height="206" rx="18" fill="#fffdf7" stroke="#eadfcb" stroke-width="4"/>
      <text x="54" y="72" font-size="15" font-weight="900" fill="#176b7a">答题纸这样写</text>
      <g data-visible-node="answer_paper"><rect x="54" y="96" width="252" height="36" rx="10" fill="#ecfdf5" stroke="#10b981" stroke-width="2"/><text x="180" y="120" text-anchor="middle" font-size="14" font-weight="900" fill="#047857">割开放气 + 排气干燥 + 清旧胶</text></g>
      <g data-visible-node="score_sentence"><rect x="54" y="144" width="252" height="36" rx="10" fill="#eff6ff" stroke="#60a5fa" stroke-width="2"/><text x="180" y="168" text-anchor="middle" font-size="14" font-weight="900" fill="#1d4ed8">附加层 + 搭接封严 + 蓄水检验</text></g>
      <g data-visible-node="score_atoms"><text x="180" y="210" text-anchor="middle" font-size="13" font-weight="900" fill="#b45309">不是写结论,是写采分动作</text></g>
    </svg>"""


def _dialogue_svg() -> str:
    return """<svg viewBox="0 0 360 270" role="img" aria-label="常见错误答疑">
      <rect x="18" y="26" width="324" height="218" rx="22" fill="#101b28" stroke="#24364b" stroke-width="2"/>
      <g data-visible-node="mini_section"><rect x="46" y="164" width="268" height="42" rx="4" fill="#87919d"/><rect x="46" y="150" width="268" height="14" fill="#c5b78f"/><rect x="46" y="138" width="268" height="12" fill="#34465b"/></g>
      <g data-visible-node="current_question"><rect x="46" y="54" width="268" height="42" rx="12" fill="#321a1c" stroke="#ef4444" stroke-width="2"/><text x="180" y="80" text-anchor="middle" font-size="14" font-weight="900" fill="#fecaca">能不能省掉基层/附加层/检验?</text></g>
      <g data-visible-node="teacher_answer"><rect x="62" y="106" width="236" height="36" rx="12" fill="#16321f" stroke="#10b981" stroke-width="2"/><text x="180" y="129" text-anchor="middle" font-size="14" font-weight="900" fill="#bbf7d0">漏闭合,就漏分</text></g>
    </svg>"""


def _closing_svg() -> str:
    return """<svg viewBox="0 0 360 270" role="img" aria-label="收尾闯关">
      <rect x="24" y="34" width="312" height="198" rx="22" fill="#10251a" stroke="#10b981" stroke-width="3"/>
      <g data-visible-node="closing_sentence"><text x="180" y="92" text-anchor="middle" font-size="18" font-weight="900" fill="#bbf7d0">三步闭环</text><text x="180" y="132" text-anchor="middle" font-size="20" font-weight="900" fill="#ecfdf5">治病因 → 恢复闭合 → 检验</text></g>
      <g data-visible-node="challenge_cta"><rect x="90" y="166" width="180" height="44" rx="22" fill="#ffd27f"/><text x="180" y="194" text-anchor="middle" font-size="17" font-weight="900" fill="#0f1722">开始闯关</text></g>
    </svg>"""


def _scene_visual(scene: dict[str, Any], visual_library: dict[str, Any] | None = None) -> str:
    if visual_library:
        rendered = _visual_svg(scene, visual_library)
        if rendered:
            return rendered
    sid = str(scene["id"])
    if sid == "score":
        return _answer_paper_svg()
    if sid == "qa_closure":
        return _dialogue_svg()
    if sid == "closing_challenge":
        return _closing_svg()
    return _section_svg(sid)


def _scene_actions(scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive a deterministic OpenMAIC-style action queue for preview playback."""
    explicit = scene.get("actions")
    if isinstance(explicit, list) and explicit:
        return explicit
    nodes = list(scene.get("visible_nodes", []))
    actions: list[dict[str, Any]] = []
    for index, node_id in enumerate(nodes):
        start = round(0.04 + index * 0.14, 3)
        actions.append({"kind": "reveal", "target": node_id, "start": start, "end": round(start + 0.18, 3)})
    focus = scene.get("focus")
    if focus:
        actions.append({"kind": "highlight", "target": focus, "start": 0.22, "end": 0.92})
    camera = scene.get("camera", {})
    actions.append(
        {
            "kind": "camera",
            "verb": camera.get("verb", "spotlight"),
            "target": camera.get("target", focus or (nodes[0] if nodes else "scene")),
            "start": 0,
            "end": min(0.42, float(camera.get("duration_sec", 0.42) or 0.42)),
        }
    )
    return actions


def render(ir_path: Path) -> str:
    ir = json.loads(ir_path.read_text(encoding="utf-8"))
    base = ir_path.parent
    timing_path = base / ir["source_refs"]["timing"]
    timing = json.loads(timing_path.read_text(encoding="utf-8")) if timing_path.exists() else {}
    audio = ir["source_refs"].get("audio", "")
    audio_url = audio
    if audio:
        audio_path = base / audio
        if audio_path.exists():
            audio_url = f"{audio}?v={int(audio_path.stat().st_mtime)}"
    practice_href = ir.get("render_contract", {}).get("practice_href", "")
    max_nodes = int(ir.get("render_contract", {}).get("max_visible_nodes", 4))
    display = ir.get("display", {})
    title = display.get("title", "鲁班动画教案")
    kicker = display.get("kicker", f"鲁班深母题 · {ir.get('card_id', '')}")
    ai_context = {
        "contextId": ir.get("ai_context", {}).get("context_id", ir.get("card_id", "")),
        "title": ir.get("ai_context", {}).get("title", title),
        "mainExamAction": ir.get("ai_context", {}).get("main_exam_action", ir["main_exam_action"]),
        "safeSummary": ir.get("ai_context", {}).get("safe_summary", ir.get("teaching_spine", {}).get("warm_correction", "")),
        "keyPoints": ir.get("ai_context", {}).get("key_points", []),
        "handoffMode": ir.get("ai_context", {}).get("handoff_mode", "context_id_plus_current_scene"),
        "apiBase": ir.get("ai_context", {}).get("api_base", ""),
    }

    scenes = ir["scenes"]
    visual_library = ir.get("visual_library", {})
    student_data = {
        "title": title,
        "kicker": kicker,
        "subtitle": ir["main_exam_action"],
        "totalSec": timing.get("totalSec", scenes[-1]["end_sec"]),
        "challengeUnlockSec": ir.get("render_contract", {}).get(
            "challenge_unlock_sec",
            next((s["start_sec"] for s in scenes if s["id"] == "score"), scenes[-1]["start_sec"]),
        ),
        "audio": audio_url,
        "practiceHref": practice_href,
        "maxVisibleNodes": max_nodes,
        "aiAskRequired": bool(ir.get("render_contract", {}).get("ai_ask_required", False)),
        "aiContext": ai_context,
        "chapters": ir["chapters"],
        "segments": [
            {
                "start": seg.get("startSec", 0),
                "end": seg.get("startSec", 0) + seg.get("durSec", 0),
                "text": seg.get("text", ""),
                "speaker": seg.get("speaker", "T"),
                "kind": seg.get("kind", ""),
            }
            for seg in timing.get("segments", [])
        ],
        "scenes": [
            {
                "id": s["id"],
                "label": s["label"],
                "start": s["start_sec"],
                "end": s["end_sec"],
                "focus": s["focus"],
                "camera": s["camera"]["verb"],
                "keycard": s["keycard"],
                "coach": s["coach"],
                "visibleNodes": s["visible_nodes"],
                "visual": visual_library.get(s["id"], {}),
                "actions": _scene_actions(s),
            }
            for s in scenes
        ],
    }
    chapters_html = "".join(
        f'<button class="chapter" type="button" data-t="{c["start_sec"]}">{esc(c["label"])}</button>'
        for c in ir["chapters"]
        if c["id"] != "challenge"
    )
    scenes_html = "\n".join(
        f"""<section class="scene" data-scene-id="{esc(s["id"])}" data-focus="{esc(s["focus"])}" data-visible-count="{len(s["visible_nodes"])}">
  <div class="visual">{_scene_visual(s, visual_library)}</div>
  <div class="coach-card" data-info-node="keycard"><b>{esc(s["keycard"])}</b><span>{esc(s["coach"])}</span></div>
</section>"""
        for s in scenes
    )
    css = """
*{box-sizing:border-box}
:root{--player-h:132px}
html,body{margin:0;max-width:100%;overflow-x:hidden}
body{background:#0d1723;color:#eef3f8;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}
.lesson{max-width:460px;margin:0 auto;min-height:100dvh;padding:14px 12px calc(var(--player-h) + 14px + env(safe-area-inset-bottom))}
.top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.kicker{font-size:12px;font-weight:900;color:#ffd27f;margin:0 0 6px}.top h1{font-size:22px;line-height:1.2;margin:0}
.time{border:1px solid #31445c;border-radius:999px;padding:7px 10px;color:#cfe0f0;font-size:12px;font-weight:900;white-space:nowrap}
.subtitle{margin:10px 0 12px;color:#9fb0c2;font-size:13px;font-weight:800;line-height:1.5}
.stage{--camera-scale:1;--camera-x:0px;--camera-y:0px;position:relative;background:#13202e;border:1px solid #24364b;border-radius:20px;min-height:430px;display:grid;align-items:center;overflow:hidden;cursor:pointer;touch-action:manipulation}
.stage:focus-visible{outline:3px solid #ffd27f;outline-offset:3px}
.scene{display:none;min-width:0;padding:16px}.scene.active{display:grid;min-width:0;gap:12px;padding-bottom:88px;animation:sceneIn .2s ease-out}
.visual{position:relative;min-width:0;max-width:100%;min-height:270px;display:grid;place-items:center;transform:translate3d(var(--camera-x),var(--camera-y),0) scale(var(--camera-scale));transition:transform .12s linear;will-change:transform}
.visual svg{width:100%;max-width:100%;height:auto;display:block}
[data-visible-node]{opacity:0;transform-box:fill-box;transform-origin:center;will-change:opacity,transform,filter}.node-focus{filter:drop-shadow(0 0 9px rgba(255,210,127,.75))}
.coach-card{min-width:0;max-width:100%;overflow-wrap:anywhere;border-left:4px solid #ffd27f;background:#172434;border-radius:14px;padding:12px 13px;box-shadow:0 12px 30px rgba(0,0,0,.22);transition:opacity .18s,transform .18s}
.coach-card b{display:block;color:#ffd27f;font-size:15px;line-height:1.35;margin-bottom:6px}.coach-card span{display:block;color:#dbe6f1;font-size:14px;line-height:1.55;font-weight:800}
.caption-line{position:relative;z-index:4;min-height:40px;padding:10px 13px;border-radius:13px;background:rgba(9,17,27,.84);border:1px solid rgba(207,224,240,.18);box-shadow:0 14px 32px rgba(0,0,0,.28);color:#eef6ff;font-size:14px;font-weight:900;line-height:1.45;text-align:center;backdrop-filter:blur(8px)}
.caption-line[data-speaker="S"]{color:#d7e9ff;border-color:rgba(96,165,250,.35)}
.center-play{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);z-index:5;border:0;border-radius:999px;background:#ffd27f;color:#0f1722;font-size:17px;font-weight:900;padding:16px 24px;box-shadow:0 18px 44px rgba(0,0,0,.35)}
.lesson.started .center-play{display:none}
.ask-ai{position:absolute;right:12px;top:12px;z-index:7;min-width:52px;min-height:44px;border:1px solid rgba(255,210,127,.52);border-radius:999px;background:rgba(13,23,35,.82);color:#ffd27f;font-size:13px;font-weight:900;box-shadow:0 14px 32px rgba(0,0,0,.28);backdrop-filter:blur(8px)}
.ask-ai:focus-visible,.ask-send:focus-visible,.ask-copy:focus-visible,.ask-close:focus-visible{outline:3px solid #ffd27f;outline-offset:2px}
.ask-panel[hidden]{display:none}.ask-panel{position:fixed;inset:0;z-index:65;display:grid;align-items:end;background:rgba(2,6,12,.5);padding:14px}
.ask-sheet{width:min(560px,100%);margin:0 auto;border:1px solid #2f4560;border-radius:20px;background:#101b2a;box-shadow:0 24px 70px rgba(0,0,0,.48);padding:14px;color:#eef6ff}
.ask-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:10px}.ask-head b{display:block;font-size:16px;line-height:1.35}.ask-head span{display:block;margin-top:4px;color:#9fb0c2;font-size:12px;font-weight:800;line-height:1.45}
.ask-close{width:44px;height:44px;border:1px solid #31445c;border-radius:999px;background:#162234;color:#dceafe;font-weight:900}.ask-current{border-left:4px solid #ffd27f;border-radius:12px;background:#172434;padding:10px 12px;color:#dbeafe;font-size:13px;font-weight:850;line-height:1.45;margin-bottom:10px}
.ask-input{width:100%;min-height:86px;resize:vertical;border:1px solid #31445c;border-radius:14px;background:#0d1723;color:#eef6ff;padding:11px 12px;font:inherit;font-size:14px;line-height:1.5}
.ask-actions{display:flex;gap:10px;margin-top:10px}.ask-send,.ask-copy{flex:1;min-height:46px;border-radius:14px;border:1px solid #31445c;font-weight:900}.ask-send{background:#ffd27f;color:#101826;border-color:#ffd27f}.ask-copy{background:#162234;color:#dceafe}.ask-status{min-height:18px;margin:8px 2px 0;color:#9fb0c2;font-size:12px;font-weight:800;line-height:1.35}
.ask-answer{margin-top:10px;border:1px solid rgba(255,210,127,.3);border-radius:14px;background:#0d1723;padding:11px 12px;color:#eef6ff;font-size:13px;font-weight:800;line-height:1.55;white-space:pre-wrap}
.challenge-inline{display:none;align-items:center;justify-content:center;margin:12px 0 0;min-height:48px;border-radius:14px;border:1px dashed #3a4a60;color:#9fb0c2;text-decoration:none;font-weight:900}
.challenge-inline.ready{color:#ffd27f;border-color:#6d5327;background:#1a150c}
.theater-hint{position:fixed;left:50%;bottom:calc(var(--player-h) + 18px + env(safe-area-inset-bottom));z-index:45;transform:translateX(-50%) translateY(8px);opacity:0;pointer-events:none;border:1px solid rgba(207,224,240,.2);border-radius:999px;background:rgba(9,17,27,.78);color:#eaf3ff;font-size:13px;font-weight:900;padding:8px 13px;transition:opacity .18s,transform .18s}
.lesson.theater.show-hint .theater-hint{opacity:1;transform:translateX(-50%)}
.player{position:fixed;left:0;right:0;bottom:0;background:rgba(13,23,35,.96);border-top:1px solid #233148;backdrop-filter:blur(10px);padding:10px 12px calc(10px + env(safe-area-inset-bottom));z-index:20;transition:opacity .18s ease,transform .18s ease}
.player-inner{max-width:460px;margin:0 auto}.row{display:flex;align-items:center;gap:10px}
.play,.theater,.challenge{border:1px solid #3a4a60;background:#162234;color:#cfe0f0;font-weight:900;border-radius:999px;height:48px;min-width:48px}
.play{width:58px;border:0;background:#ffd27f;color:#0f1722;font-size:20px}.theater{width:60px}
.challenge{min-width:72px;text-decoration:none;display:flex;align-items:center;justify-content:center;color:#8fa3b8;border-color:#2b3b50;background:#172434}
.challenge.ready{color:#ffd27f;border-color:#5a421c;background:#211a0c}
.progress{flex:1;min-width:0}.ptime{display:flex;justify-content:space-between;color:#9fb0c2;font-size:12px;font-weight:800;margin-bottom:2px}
.bar{height:8px;border-radius:999px;background:#26344a;overflow:hidden}.fill{height:100%;width:0;background:#ffd27f}
.scrubber{width:100%;height:44px;accent-color:#ffd27f;margin:0}
.chapters{display:flex;gap:6px;margin-top:8px;overflow-x:auto;padding-bottom:1px;scrollbar-width:none}.chapters::-webkit-scrollbar{display:none}
.chapter{flex:0 0 auto;min-width:64px;border:1px solid #2b3b50;background:#172434;color:#9fb0c2;border-radius:12px;min-height:44px;padding:0 9px;font-weight:900}
.chapter.on{background:#ffd27f;color:#0f1722;border-color:#ffd27f}
@keyframes sceneIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.lesson.theater{max-width:none;padding:0;background:#0d1723}
.lesson.theater .top,.lesson.theater .subtitle,.lesson.theater .challenge-inline{display:none}
.lesson.theater .stage{position:fixed;inset:0;border:0;border-radius:0;min-height:0;transition:inset .18s ease}
.lesson.theater.controls-visible .stage{inset:0 0 calc(var(--player-h) + env(safe-area-inset-bottom)) 0}
.lesson.theater .scene{height:100%;align-content:center;padding:clamp(18px,6vh,52px) 18px 18px}
.lesson.theater .visual{min-height:0}.lesson.theater .visual svg{max-height:min(52dvh,460px)}
.lesson.theater .coach-card{margin-top:4px}
.lesson.theater .caption-line{font-size:15px}
.lesson.theater.controls-visible .caption-line,.lesson.theater.controls-visible .coach-card{display:none}
.lesson.theater:not(.controls-visible) .ask-ai{opacity:0;pointer-events:none}
.lesson.theater .player{z-index:40;opacity:0;transform:translateY(105%);pointer-events:none}
.lesson.theater.controls-visible .player{opacity:1;transform:none;pointer-events:auto}
@media (orientation:landscape),(min-width:760px){
  .lesson{max-width:980px}.stage{min-height:420px}
  .scene.active{grid-template-columns:minmax(0,1fr) minmax(230px,320px);grid-template-rows:minmax(0,1fr) auto;align-items:center}
  .visual{grid-column:1;grid-row:1 / span 2}.caption-line{grid-column:2;grid-row:1;align-self:end}.coach-card{grid-column:2;grid-row:2;align-self:start}
  .visual{min-height:330px}
  .lesson.theater .scene.active{grid-template-columns:minmax(0,1fr) minmax(220px,300px)}
  .lesson.theater .visual svg{max-height:min(68dvh,620px)}.lesson.theater .caption-line{left:8%;right:8%;bottom:20px}
}
@media (orientation:landscape) and (max-height:520px){
  .lesson{max-width:none;min-height:auto;padding:8px 10px 0}.subtitle{display:none}.top h1{font-size:20px}
  .stage{min-height:calc(100dvh - var(--player-h) - 54px)}
  .scene.active{padding:8px 12px;gap:8px}
  .visual{min-height:0}.visual svg{max-height:calc(100dvh - var(--player-h) - 72px)}
  .caption-line{min-height:0;padding:7px 9px;font-size:12px;line-height:1.35}.coach-card{padding:8px 10px}.coach-card b{font-size:13px}.coach-card span{font-size:12px;line-height:1.4}
  .player{position:relative;margin:10px -12px 0;transform:none;opacity:1;pointer-events:auto}
  .player-inner{max-width:none}.lesson.theater .player{position:fixed;margin:0}
  .lesson.theater .scene{padding:14px 18px}.lesson.theater .visual svg{max-height:58dvh}
}
@media(max-width:420px){
  .top h1{font-size:20px}.stage{min-height:430px}.scene{padding:12px}
  .coach-card b{font-size:14px}.coach-card span{font-size:13px}.caption-line{font-size:13px}.chapter{font-size:12px}
}
@media(max-width:370px){
  .lesson{padding:12px 12px 0}
  .player{position:relative;margin:10px -12px 0;transform:none;opacity:1;pointer-events:auto}
  .player-inner{max-width:none}.lesson.theater .player{position:fixed;margin:0}
}
"""
    return f"""<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(title)} · IR 预览</title><style>{css}</style></head>
<body>
<main class="lesson orientation-adaptive" data-card-id="{esc(ir['card_id'])}" data-stage-shell="animation-ir-preview" data-animation-ir-preview="v0">
  <div class="top"><div><p class="kicker">{esc(kicker)}</p><h1>{esc(title)}</h1></div><div class="time"><span id="cur">0:00</span> / <span id="tot">0:00</span></div></div>
  <p class="subtitle">{esc(ir['main_exam_action'])}</p>
  <div class="stage" id="stage" data-stage-shell="visual-stage" tabindex="0" aria-label="动画学习舞台，轻点显示或隐藏控制">
    {scenes_html}
    <div class="caption-line" id="captionLine" data-caption="1" data-speaker="T" role="status" aria-live="polite"></div>
    <div class="theater-hint" id="theaterHint" aria-hidden="true">轻点显示控制</div>
    <button class="ask-ai" id="askAi" type="button" data-ai-ask-entry="1" aria-label="带当前画面问 AI">问 AI</button>
    <button class="center-play" id="centerPlay" type="button" aria-label="播放讲解">播放讲解</button>
  </div>
  <div class="ask-panel" id="askPanel" data-ai-ask-panel="1" hidden>
    <div class="ask-sheet" role="dialog" aria-modal="true" aria-labelledby="askTitle">
      <div class="ask-head"><div><b id="askTitle">带着当前画面问 AI</b><span>会自动带上本卡考点、当前画面、字幕和采分主线。</span></div><button class="ask-close" id="askClose" type="button" aria-label="关闭 AI 答疑">×</button></div>
      <div class="ask-current" id="askCurrent"></div>
      <textarea class="ask-input" id="askInput" placeholder="比如：这一步为什么要先判口径？"></textarea>
      <div class="ask-actions"><button class="ask-copy" id="askCopy" type="button">复制上下文</button><button class="ask-send" id="askSend" type="button">发送到答疑</button></div>
      <div class="ask-status" id="askStatus" role="status" aria-live="polite"></div>
      <div class="ask-answer" id="askAnswer" hidden></div>
    </div>
  </div>
  <a class="challenge-inline" href="{esc(practice_href)}" data-challenge-cta="inline" aria-disabled="true">先看采分句再闯关 →</a>
  <div class="player controls" id="player">
    <div class="player-inner">
      <div class="row">
        <button class="play" id="play" type="button" aria-label="播放讲解" aria-pressed="false">▶</button>
        <button class="theater" id="theaterToggle" data-theater-toggle="1" type="button" aria-label="进入全屏学习模式" aria-pressed="false">全屏</button>
        <div class="progress"><div class="ptime"><span id="cur2">0:00</span><span id="tot2">0:00</span></div><div class="bar"><div class="fill" id="fill"></div></div><input class="scrubber" id="scrubber" type="range" min="0" max="{student_data['totalSec']}" value="0" step="0.05" aria-label="拖动播放进度"></div>
        <a class="challenge" href="{esc(practice_href)}" data-challenge-cta="controls" aria-disabled="true">采分后闯关</a>
      </div>
      <div class="chapters">{chapters_html}</div>
    </div>
  </div>
  <audio id="au" preload="metadata"{' src="' + esc(audio_url) + '"' if audio_url else ''}></audio>
</main>
<script type="application/json" id="irPreviewData">{js_json(student_data)}</script>
<script>
const DATA=JSON.parse(document.getElementById('irPreviewData').textContent);
const lesson=document.querySelector('.lesson'),au=document.getElementById('au'),play=document.getElementById('play'),centerPlay=document.getElementById('centerPlay'),scrubber=document.getElementById('scrubber'),fill=document.getElementById('fill');
const cur=document.getElementById('cur'),cur2=document.getElementById('cur2'),tot=document.getElementById('tot'),tot2=document.getElementById('tot2'),theaterToggle=document.getElementById('theaterToggle'),stage=document.getElementById('stage'),player=document.getElementById('player'),captionLine=document.getElementById('captionLine');
const askAi=document.getElementById('askAi'),askPanel=document.getElementById('askPanel'),askClose=document.getElementById('askClose'),askCurrent=document.getElementById('askCurrent'),askInput=document.getElementById('askInput'),askCopy=document.getElementById('askCopy'),askSend=document.getElementById('askSend'),askStatus=document.getElementById('askStatus'),askAnswer=document.getElementById('askAnswer');
const scenes=[...document.querySelectorAll('.scene')],chapters=[...document.querySelectorAll('.chapter')];
const challengeLinks=[...document.querySelectorAll('[data-challenge-cta]')];
const fmt=s=>{{s=Math.max(0,Math.floor(s||0));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');}};
const hasAudio=Boolean(DATA.audio);
let raf=0,hideTimer=0,hintTimer=0,lastScene='',virtualTime=0,virtualPlaying=false,lastTick=0;
const getTime=()=>hasAudio?Number(au.currentTime||0):virtualTime;
const isPaused=()=>hasAudio?au.paused:!virtualPlaying;
const setTime=t=>{{const next=Math.max(0,Math.min(DATA.totalSec,Number(t)||0));if(hasAudio)au.currentTime=next;else virtualTime=next;return next;}};
const audioReadyPromise=hasAudio&&location.protocol.startsWith('http')?fetch(DATA.audio).then(r=>{{if(!r.ok)throw new Error('audio fetch '+r.status);return r.blob();}}).then(blob=>new Promise(resolve=>{{const url=URL.createObjectURL(blob);au.addEventListener('loadedmetadata',resolve,{{once:true}});au.src=url;au.load();}})).catch(()=>undefined):Promise.resolve();
tot.textContent=tot2.textContent=fmt(DATA.totalSec);
const scoreStart=Number(DATA.challengeUnlockSec??(DATA.scenes.find(s=>s.id==='score')||DATA.scenes.at(-2)||DATA.scenes.at(-1)).start);
const clamp01=x=>Math.max(0,Math.min(1,x));
const ease=x=>{{x=clamp01(x);return 1-Math.pow(1-x,3);}};
function sceneAt(t){{return DATA.scenes.find(s=>t>=s.start-0.05&&t<s.end-0.05)||DATA.scenes[DATA.scenes.length-1];}}
function segmentAt(t){{return (DATA.segments||[]).find(s=>t>=s.start-0.18&&t<s.end+0.18)||null;}}
function syncPlayerHeight(){{lesson.style.setProperty('--player-h',Math.ceil(player.getBoundingClientRect().height||132)+'px');}}
if('ResizeObserver' in window)new ResizeObserver(syncPlayerHeight).observe(player);
window.addEventListener('resize',syncPlayerHeight);
function scoreReady(t=Number(getTime()||scrubber.value||0)){{return t>=scoreStart-0.1||t>=DATA.totalSec-0.5;}}
function updateChallenge(t){{const ready=scoreReady(t);lesson.classList.toggle('challenge-ready',ready);challengeLinks.forEach(link=>{{link.classList.toggle('ready',ready);link.setAttribute('aria-disabled',ready?'false':'true');link.textContent=link.dataset.challengeCta==='inline'?(ready?'用采分句闯关 →':'先看采分句再闯关 →'):(ready?'闯关':'采分后闯关');}});}}
function showHint(){{if(!lesson.classList.contains('theater'))return;clearTimeout(hintTimer);lesson.classList.add('show-hint');hintTimer=setTimeout(()=>lesson.classList.remove('show-hint'),1400);}}
function setControls(visible=true,auto=true){{clearTimeout(hideTimer);lesson.classList.toggle('controls-visible',visible);if(visible)lesson.classList.remove('show-hint');else showHint();if(visible&&auto&&lesson.classList.contains('theater')&&!isPaused())hideTimer=setTimeout(()=>setControls(false,false),2600);}}
function setPlayState(isPlaying){{play.textContent=isPlaying?'⏸':'▶';play.setAttribute('aria-label',isPlaying?'暂停讲解':'播放讲解');play.setAttribute('aria-pressed',isPlaying?'true':'false');}}
function applyMotion(activeEl,active,t){{if(!activeEl)return;const dur=Math.max(.001,active.end-active.start),p=clamp01((t-active.start)/dur),nodes=[...activeEl.querySelectorAll('[data-visible-node]')],actions=active.actions||[];const cameraAction=actions.find(a=>a.kind==='camera')||{{verb:active.camera,start:0,end:.28}},cameraVerb=cameraAction.verb||active.camera;const cameraPush=cameraVerb==='push-in'||cameraVerb==='spotlight'||cameraVerb==='answer-paper'||cameraVerb==='trace';const cameraP=ease((p-(cameraAction.start||0))/Math.max(.05,(cameraAction.end||.28)-(cameraAction.start||0)));stage.style.setProperty('--camera-scale',String(1+(cameraPush?0.035*cameraP:0)));stage.style.setProperty('--camera-y',(cameraVerb==='pull-back'?String(-8*ease(p)):'0')+'px');nodes.forEach((node,i)=>{{const name=node.dataset.visibleNode||'';const reveal=actions.find(a=>a.kind==='reveal'&&a.target===name)||{{start:.04+i*.14,end:.22+i*.14}};const v=ease((p-reveal.start)/Math.max(.05,reveal.end-reveal.start));const highlighted=actions.some(a=>a.kind==='highlight'&&(a.target===name||name===a.target||name.includes(a.target))&&p>=a.start&&p<=a.end)||name===active.focus||name.includes(active.focus);const steps=[...node.querySelectorAll('[data-primitive-step]')];if(steps.length){{node.style.opacity=v>.01?'1':'0';node.style.transform=`translateY(${{(1-v)*8}}px) scale(${{0.98+v*0.02}})`;steps.forEach((step,si)=>{{const sv=ease((v-si*.16)/.24);step.style.opacity=String(sv);step.style.transformBox='fill-box';step.style.transformOrigin=step.dataset.trace==='1'?'left center':'center';step.style.transform=step.dataset.trace==='1'?`scaleX(${{sv}})`: `translateY(${{(1-sv)*7}}px) scale(${{0.97+sv*0.03}})`;}});}}else{{node.style.opacity=String(v);node.style.transform=`translateY(${{(1-v)*10}}px) scale(${{0.96+v*0.04}})`;}}node.classList.toggle('node-focus',highlighted);}});if(active.id!==lastScene){{scenes.forEach(scene=>{{if(scene!==activeEl)scene.querySelectorAll('[data-visible-node]').forEach(node=>{{node.style.opacity='0';node.style.transform='translateY(10px) scale(.96)';node.classList.remove('node-focus');node.querySelectorAll('[data-primitive-step]').forEach(step=>{{step.style.opacity='0';step.style.transform='translateY(7px) scale(.97)';}});}});}});lastScene=active.id;}}}}
function paint(){{const t=Number(getTime()||scrubber.value||0);const active=sceneAt(t);const seg=segmentAt(t);lesson.classList.toggle('paused',isPaused());lesson.classList.toggle('playing',!isPaused());let activeEl=null;scenes.forEach(el=>{{const on=el.dataset.sceneId===active.id;el.classList.toggle('active',on);if(on)activeEl=el;}});const coach=activeEl?.querySelector('.coach-card');if(activeEl&&coach&&captionLine.parentElement!==activeEl)activeEl.insertBefore(captionLine,coach);const motionT=!lesson.classList.contains('started')&&t<0.05?active.start+Math.max(1,(active.end-active.start)*0.55):t;applyMotion(activeEl,active,motionT);chapters.forEach(el=>el.classList.toggle('on',t>=Number(el.dataset.t)&&Number(el.dataset.t)>=active.start-0.1));fill.style.width=(Math.min(t,DATA.totalSec)/DATA.totalSec*100)+'%';scrubber.value=String(Math.min(t,DATA.totalSec));cur.textContent=cur2.textContent=fmt(t);captionLine.hidden=!seg;captionLine.textContent=seg?.text||'';captionLine.dataset.speaker=seg?.speaker||'T';updateChallenge(t);syncPlayerHeight();}}
function tickVirtualClock(){{if(!hasAudio&&virtualPlaying){{const now=performance.now();if(lastTick)virtualTime+=Math.max(0,(now-lastTick)/1000);lastTick=now;if(virtualTime>=DATA.totalSec){{virtualTime=DATA.totalSec;virtualPlaying=false;setPlayState(false);setControls(true,false);}}}}}}
function loop(){{tickVirtualClock();paint();if(!isPaused())raf=requestAnimationFrame(loop);}}
function startLoop(){{cancelAnimationFrame(raf);raf=requestAnimationFrame(loop);}}
function seek(t){{const next=setTime(t);if(next>0.2)lesson.classList.add('started');scrubber.value=String(next);paint();setControls(true);}}
async function playAudio(){{lesson.classList.add('started');if(!hasAudio){{virtualPlaying=true;lastTick=performance.now();setPlayState(true);setControls(true);startLoop();return Promise.resolve();}}await audioReadyPromise;return au.play().then(()=>{{setPlayState(true);setControls(true);startLoop();}}).catch(()=>{{paint();}});}}
function toggle(){{if(isPaused())playAudio();else{{if(hasAudio)au.pause();else virtualPlaying=false;setPlayState(false);setControls(true,false);paint();}}}}
function pauseForAsk(){{if(hasAudio)au.pause();else virtualPlaying=false;setPlayState(false);setControls(true,false);paint();}}
function currentAskContext(){{const t=Number(getTime()||0);const active=sceneAt(t);const seg=segmentAt(t);return {{type:'luban_ai_ask',cardId:lesson.dataset.cardId||'',contextId:DATA.aiContext?.contextId||lesson.dataset.cardId||'',title:DATA.aiContext?.title||DATA.title,mainExamAction:DATA.aiContext?.mainExamAction||DATA.subtitle,currentScene:{{id:active.id,label:active.label,focus:active.focus,keycard:active.keycard,coach:active.coach}},currentCaption:seg?{{speaker:seg.speaker,text:seg.text,start:seg.start,end:seg.end}}:null,safeSummary:DATA.aiContext?.safeSummary||'',keyPoints:DATA.aiContext?.keyPoints||[],time:t}};}}
function askTextPayload(context){{return ['【当前画面】'+context.currentScene.label+' · '+context.currentScene.keycard,'【字幕】'+(context.currentCaption?.text||'暂无'),'【本卡主线】'+context.mainExamAction,'【安全上下文】'+context.safeSummary,'【我的问题】'+(askInput.value.trim()||'请解释我当前画面容易卡住的点。')].join('\\n');}}
function openAskPanel(){{pauseForAsk();const context=currentAskContext();askCurrent.textContent=`当前: ${{context.currentScene.label}}｜${{context.currentScene.keycard}}｜${{context.currentCaption?.text||context.currentScene.coach}}`;askInput.value='';askStatus.textContent='';askAnswer.hidden=true;askAnswer.textContent='';askPanel.hidden=false;setControls(true,false);requestAnimationFrame(()=>askInput.focus());}}
function closeAskPanel(){{askPanel.hidden=true;askStatus.textContent='';askAnswer.hidden=true;askAnswer.textContent='';stage.focus();}}
async function copyAskContext(){{const context=currentAskContext();const text=askTextPayload(context);try{{await navigator.clipboard.writeText(text);askStatus.textContent='已复制当前画面上下文，可以粘贴给答疑。';}}catch{{askStatus.textContent='复制失败，请长按选中文本后手动复制。';}}}}
function previewAskAnswer(context){{const points=(context.keyPoints||[]).slice(0,3).map(point=>'• '+point).join('\\n');const question=askInput.value.trim()||'我现在最容易卡在哪里？';return `预览答疑：你问「${{question}}」\\n\\n先看当前画面：${{context.currentScene.label}}。这一幕抓的是「${{context.currentScene.keycard}}」。\\n${{context.currentScene.coach}}\\n\\n答题主线：${{context.mainExamAction}}\\n${{points?'\\n可带走的依据：\\n'+points:''}}\\n\\n正式小程序里，这个入口会把 contextId、当前画面和问题发给 TutorBot，由后端读取母题数据继续追问。`;}}
function askApiUrl(){{const base=String(DATA.aiContext?.apiBase||'').replace(/\/$/,'');return base?base+'/api/v1/luban-preview/ai-ask':'/api/v1/luban-preview/ai-ask';}}
async function sendAskContext(){{const payload=currentAskContext();payload.question=askInput.value.trim();const message={{type:'luban_ai_ask',payload}};try{{window.wx?.miniProgram?.postMessage({{data:message}});}}catch{{}}try{{window.parent?.postMessage(message,'*');}}catch{{}}askSend.disabled=true;askStatus.textContent='正在带着当前画面问 AI...';askAnswer.hidden=true;try{{const res=await fetch(askApiUrl(),{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}});const data=await res.json().catch(()=>({{}}));if(!res.ok)throw new Error(data.detail||'AI 答疑暂时不可用');askAnswer.textContent=data.answer||previewAskAnswer(payload);askAnswer.hidden=false;askStatus.textContent=data.source==='tutorbot_runtime'?'已接入 TutorBot 实时答疑。':'实时 AI 暂时降级，先给你本卡答疑。';}}catch(err){{askAnswer.textContent=previewAskAnswer(payload);askAnswer.hidden=false;askStatus.textContent='实时 AI 暂不可用，先显示本卡预览答疑。';}}finally{{askSend.disabled=false;}}}}
play.addEventListener('click',toggle);centerPlay.addEventListener('click',playAudio);au.addEventListener('timeupdate',paint);au.addEventListener('play',()=>setPlayState(true));au.addEventListener('pause',()=>setPlayState(false));au.addEventListener('ended',()=>{{setPlayState(false);seek(DATA.totalSec);setControls(true,false);}});
scrubber.addEventListener('input',()=>seek(scrubber.value));chapters.forEach(btn=>btn.addEventListener('click',()=>{{seek(btn.dataset.t);playAudio();}}));
stage.addEventListener('click',e=>{{if(e.target===centerPlay)return;if(lesson.classList.contains('theater'))setControls(true);}});
stage.addEventListener('keydown',e=>{{if((e.key==='Enter'||e.key===' ')&&lesson.classList.contains('theater')){{e.preventDefault();setControls(true);}}}});
player.addEventListener('click',e=>e.stopPropagation());
askAi.addEventListener('click',e=>{{e.stopPropagation();openAskPanel();}});
askClose.addEventListener('click',closeAskPanel);askCopy.addEventListener('click',copyAskContext);askSend.addEventListener('click',sendAskContext);
askPanel.addEventListener('click',e=>{{if(e.target===askPanel)closeAskPanel();}});
document.addEventListener('keydown',e=>{{if(e.key==='Escape'&&!askPanel.hidden)closeAskPanel();}});
challengeLinks.forEach(link=>link.addEventListener('click',e=>{{if(scoreReady())return;e.preventDefault();seek(scoreStart);playAudio();}}));
async function setTheater(on){{lesson.classList.toggle('theater',on);theaterToggle.textContent=on?'退出':'全屏';theaterToggle.setAttribute('aria-label',on?'退出全屏学习模式':'进入全屏学习模式');theaterToggle.setAttribute('aria-pressed',on?'true':'false');if(on){{showHint();try{{await stage.requestFullscreen?.();}}catch{{}}}}else{{lesson.classList.remove('show-hint');if(document.fullscreenElement){{try{{await document.exitFullscreen();}}catch{{}}}}}}setControls(true);syncPlayerHeight();paint();}}
theaterToggle.addEventListener('click',()=>setTheater(!lesson.classList.contains('theater')));
document.addEventListener('fullscreenchange',()=>{{if(!document.fullscreenElement&&lesson.classList.contains('theater')){{lesson.classList.remove('theater');theaterToggle.textContent='全屏';theaterToggle.setAttribute('aria-label','进入全屏学习模式');theaterToggle.setAttribute('aria-pressed','false');setControls(true,false);paint();}}}});
window.__IR_PLAYER__={{seek,paint,state:()=>({{time:Number(getTime()||0),scene:sceneAt(Number(getTime()||0)).id,hasAudio,playing:!isPaused()}})}};
syncPlayerHeight();seek(0);setPlayState(false);setControls(false,false);
</script></body></html>"""


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: render_animation_ir_preview.py <animation_ir.v0.json>", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    out = src.with_name(src.name.replace(".animation_ir.v0.json", ".animation_ir_preview.html"))
    out.write_text(render(src), encoding="utf-8")
    print(f"✅ {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
