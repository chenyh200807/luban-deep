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
    mode = esc(node.get("mode", "default"))
    signature = esc(node.get("visual_signature") or f"{node.get('kind', 'node')}:{node.get('mode', 'default')}")
    return f'<g data-visible-node="{node_id}" data-visual-node-id="{node_id}" data-visual-kind="{kind}" data-visual-mode="{mode}" data-visual-signature="{signature}">{body}</g>'


def _primitive_step_ids(node: dict[str, Any]) -> set[str]:
    return {str(step.get("id")) for step in node.get("primitive_steps", []) if step.get("id")}


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


def _layout_label_badge(layout_id: str, text: object, cx: float, cy: float, *, tone: dict[str, str], width: float | None = None, size: int = 12) -> str:
    return f'<g data-layout-label="{esc(layout_id)}">{_label_badge(text, cx, cy, tone=tone, width=width, size=size)}</g>'


def _step_group(index: int, body: str, *, trace: bool = False, step_id: str | None = None) -> str:
    trace_attr = ' data-trace="1"' if trace else ""
    id_attr = f' data-primitive-step-id="{esc(step_id)}"' if step_id else ""
    return f'<g data-primitive-step="{index}"{id_attr}{trace_attr}>{body}</g>'


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


def _power_distribution_tree(node: dict[str, Any]) -> str:
    x = float(node.get("x", 26))
    y = float(node.get("y", 38))
    w = float(node.get("w", 308))
    h = float(node.get("h", 188))
    labels = _labels(node, ["总配电箱", "分配电箱", "开关箱", "用电设备"], 4)
    badges = _labels({"labels": node.get("badges", [])}, ["TN-S PE线", "漏保一级", "漏保二级"], 3)
    mode = str(node.get("mode", "normal"))
    title = node.get("text") or "三级配电树"
    cy = y + h * 0.55
    left = x + 34
    box_w = 62
    box_h = 42
    gap = (w - 68 - box_w * 4) / 3
    centers = [left + box_w / 2 + i * (box_w + gap) for i in range(4)]

    def box(index: int, cx: float, label: str, tone_name: str, cy_value: float | None = None, attrs: str = "") -> str:
        tone = _tone(tone_name)
        box_cy = cy if cy_value is None else cy_value
        attr_text = f" {attrs.strip()}" if attrs else ""
        return (
            f'<rect x="{cx - box_w / 2}" y="{box_cy - box_h / 2}" width="{box_w}" height="{box_h}" '
            f'rx="12" fill="{tone["fill"]}" stroke="{tone["stroke"]}" stroke-width="3"{attr_text}/>'
            + _svg_text(label, cx, box_cy + 5, size=_fit_font_size(label, box_w, 12, minimum=10), fill=tone["text"])
        )

    if mode == "shared_switch":
        shared_centers = [x + 48, x + 112, x + 178]
        branch_x = shared_centers[2]
        device_x = x + w - 34
        dev_a = (device_x, cy - 38)
        dev_b = (device_x, cy + 38)
        start_x = branch_x + box_w / 2 + 8
        end_x = device_x - box_w / 2 - 6
        branch_a = (
            f'<circle cx="{start_x}" cy="{cy}" r="4.5" fill="#ef4444"/>'
            f'<path data-shared-switch-branch="1" d="M{start_x} {cy} L{end_x} {dev_a[1]}" '
            f'stroke="#ef4444" stroke-width="5" stroke-linecap="round" fill="none"/>'
            f'<polygon points="{end_x},{dev_a[1]} {end_x - 10},{dev_a[1] - 7} {end_x - 10},{dev_a[1] + 7}" fill="#ef4444"/>'
        )
        branch_b = (
            f'<path data-shared-switch-branch="1" d="M{start_x} {cy} L{end_x} {dev_b[1]}" '
            f'stroke="#ef4444" stroke-width="5" stroke-linecap="round" fill="none"/>'
            f'<polygon points="{end_x},{dev_b[1]} {end_x - 10},{dev_b[1] - 7} {end_x - 10},{dev_b[1] + 7}" fill="#ef4444"/>'
        )
        device_boxes = (
            box(3, dev_a[0], labels[3], "danger", cy_value=dev_a[1], attrs='data-shared-switch-device="1"')
            + box(4, dev_b[0], str(node.get("second_device", "另一设备")), "danger", cy_value=dev_b[1], attrs='data-shared-switch-device="1"')
        )
        body = (
            _step_group(0, _svg_text(title, x + w / 2, y + 18, size=16, fill="#176b7a"))
            + _step_group(1, f'<path d="M{shared_centers[0] + box_w / 2} {cy} H{branch_x - box_w / 2}" stroke="#94a3b8" stroke-width="5" stroke-linecap="round"/>', trace=True)
            + _step_group(2, box(0, shared_centers[0], labels[0], "blue"))
            + _step_group(3, box(1, shared_centers[1], labels[1], "neutral"))
            + _step_group(4, box(2, branch_x, labels[2], "danger"))
            + _step_group(5, f'<g data-shared-switch="1">{branch_a}{branch_b}</g>', trace=True)
            + _step_group(5, f'<g data-shared-switch="1">{device_boxes}</g>')
            + _step_group(6, _label_badge("错误：一箱分两机", x + w / 2, y + h - 10, tone=_tone("danger"), width=142, size=11))
        )
        return _visual_group(node, body)

    if mode == "dedicated_switches":
        distribution_x = x + 58
        switch_x = x + 180
        device_x = x + w - 38
        top_y = cy - 38
        bottom_y = cy + 38
        second_device = str(node.get("second_device", "另一设备"))
        feed_paths = (
            f'<path d="M{distribution_x + box_w / 2 + 5} {cy} L{switch_x - box_w / 2 - 6} {top_y}" stroke="#16a34a" stroke-width="4" stroke-linecap="round" fill="none"/>'
            f'<path d="M{distribution_x + box_w / 2 + 5} {cy} L{switch_x - box_w / 2 - 6} {bottom_y}" stroke="#16a34a" stroke-width="4" stroke-linecap="round" fill="none"/>'
        )
        device_paths = (
            f'<path d="M{switch_x + box_w / 2 + 5} {top_y} H{device_x - box_w / 2 - 6}" stroke="#16a34a" stroke-width="4" stroke-linecap="round" fill="none"/>'
            f'<path d="M{switch_x + box_w / 2 + 5} {bottom_y} H{device_x - box_w / 2 - 6}" stroke="#16a34a" stroke-width="4" stroke-linecap="round" fill="none"/>'
        )
        body = (
            _step_group(0, _svg_text(title, x + w / 2, y + 18, size=16, fill="#176b7a"))
            + _step_group(1, feed_paths, trace=True)
            + _step_group(2, box(0, distribution_x, labels[0], "neutral"))
            + _step_group(3, box(1, switch_x, labels[1], "success", cy_value=top_y))
            + _step_group(4, box(2, switch_x, labels[2], "success", cy_value=bottom_y))
            + _step_group(5, device_paths, trace=True)
            + _step_group(5, box(3, device_x, labels[3], "amber", cy_value=top_y) + box(4, device_x, second_device, "amber", cy_value=bottom_y))
            + _step_group(6, _label_badge("正确：一机一箱", x + w / 2, y + h - 10, tone=_tone("success"), width=132, size=11))
        )
        return _visual_group(node, body)

    body = (
        _step_group(0, _svg_text(title, x + w / 2, y + 18, size=16, fill="#176b7a"))
        + _step_group(1, f'<path d="M{centers[0] + box_w / 2} {cy} H{centers[-1] - box_w / 2}" stroke="#94a3b8" stroke-width="6" stroke-linecap="round"/>', trace=True)
        + _step_group(2, box(0, centers[0], labels[0], "blue"))
        + _step_group(3, box(1, centers[1], labels[1], "neutral"))
        + _step_group(4, box(2, centers[2], labels[2], "success"))
        + _step_group(5, box(3, centers[3], labels[3], "amber"))
        + _step_group(6, f'<path d="M{x + 42} {y + h - 34} H{x + w - 42}" stroke="#16a34a" stroke-width="5" stroke-linecap="round" stroke-dasharray="10 7"/>', trace=True)
        + _step_group(7, _label_badge(badges[0], x + w / 2, y + h - 34, tone=_tone("success"), width=118, size=11))
        + _step_group(8, _label_badge(badges[1], centers[0], cy - 42, tone=_tone("amber"), width=88, size=10))
        + _step_group(9, _label_badge(badges[2], centers[2], cy - 42, tone=_tone("amber"), width=88, size=10))
    )
    return _visual_group(node, body)


def _pit_threshold_board(node: dict[str, Any]) -> str:
    x = float(node.get("x", 10))
    y = float(node.get("y", 18))
    w = float(node.get("w", 340))
    h = float(node.get("h", 224))
    mode = str(node.get("mode", "method"))
    step_ids = _primitive_step_ids(node)
    compact = mode == "score"
    sparse_labels = mode in {"problem", "score"}
    title = str(node.get("text") or "基坑降水剖面")
    rule_title = str(node.get("rule_title") or "判据")
    rule_main = str(node.get("rule_main") or "题干对象先入图")
    rule_sub = str(node.get("rule_sub") or "再扫成采分句")

    ground_y = y + 54
    pit_left = x + w * 0.22
    pit_right = x + w * 0.58
    pit_bottom = y + h * 0.62
    pit_mid = (pit_left + pit_right) / 2
    axis_x = x + w * 0.13
    right_x = x + w * 0.76
    rule_y = y + h - 47
    main_size = _fit_font_size(rule_main, w - 126, 18, minimum=11)
    sub_size = _fit_font_size(rule_sub, w - 126, 12, minimum=9)

    def step(step_id: str, index: int, body: str, *, trace: bool = False) -> str:
        if step_id not in step_ids:
            return body
        return _step_group(index, body, trace=trace, step_id=step_id)

    layer_fill = (
        f'<g data-engineering-object="soil-layers" data-visual-signature-part="section-layers">'
        f'<rect x="{pit_left}" y="{ground_y}" width="{pit_right - pit_left}" height="{pit_bottom - ground_y}" fill="#0b2e3f" opacity=".52"/>'
        f'<path d="M{pit_left} {ground_y + 18} H{pit_right}" stroke="#5fb5d8" stroke-width="1.4" stroke-dasharray="5 5" opacity=".82"/>'
        f'<path d="M{pit_left} {ground_y + 49} H{pit_right}" stroke="#e2c995" stroke-width="6" opacity=".62"/>'
        f'<rect x="{pit_left}" y="{pit_bottom - 17}" width="{pit_right - pit_left}" height="17" fill="#12344a" opacity=".85"/>'
        f'<path d="M{pit_left + 7} {ground_y + 10} l-15 16 M{pit_left + 28} {ground_y + 10} l-36 36 M{pit_right - 28} {pit_bottom - 16} l-22 22 M{pit_right - 8} {pit_bottom - 16} l-22 22" '
        f'stroke="#2e6a85" stroke-width="1.2" opacity=".6"/></g>'
    )
    pit_outline = (
        f'<g data-engineering-object="pit-section" data-visual-signature-part="pit-section">'
        f'<path d="M{x + 24} {ground_y} H{x + w - 26}" stroke="#c8f0ff" stroke-width="3.2" stroke-linecap="round"/>'
        f'<path d="M{pit_left} {ground_y} V{pit_bottom} H{pit_right} V{ground_y}" stroke="#e8f8ff" stroke-width="3.4" fill="none" stroke-linejoin="round"/>'
        f'<path d="M{axis_x} {ground_y - 10} V{pit_bottom}" stroke="#6bc9f5" stroke-width="2.4"/>'
        f'<path d="M{axis_x - 7} {ground_y - 2} l7 -14 l7 14 M{axis_x - 7} {pit_bottom - 14} l7 14 l7 -14" stroke="#6bc9f5" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
        f'<text transform="translate({axis_x - 17} {(ground_y + pit_bottom) / 2}) rotate(-90)" text-anchor="middle" font-size="12" font-weight="900" fill="#86d9ff">开挖深度 H</text>'
        f'<text x="{x + 30}" y="{ground_y - 8}" font-size="12" font-weight="900" fill="#beeaff">地面 ±0.000</text></g>'
    )
    threshold_3m = (
        f'<g data-engineering-object="3m-threshold" data-visual-signature-part="threshold-line">'
        f'<circle cx="{axis_x}" cy="{ground_y + 45}" r="4.8" fill="#f5a623"/>'
        f'<path data-threshold-line="3m" d="M{axis_x} {ground_y + 45} H{x + w - 38}" stroke="#f5a623" stroke-width="3" stroke-dasharray="7 7"/>'
        + ("" if sparse_labels else f'<text x="{x + w - 34}" y="{ground_y + 50}" text-anchor="end" font-size="13" font-weight="900" fill="#ffb832">>3m 井点</text>')
        + "</g>"
    )
    threshold_6m_label = "5m超限" if mode == "layer" else "本题 6m"
    threshold_6m = (
        f'<g data-engineering-object="case-depth-threshold" data-visual-signature-part="danger-line">'
        f'<circle cx="{axis_x}" cy="{pit_bottom}" r="4.8" fill="#ff5b61"/>'
        f'<path data-threshold-line="case-depth" d="M{axis_x} {pit_bottom} H{x + w - 38}" stroke="#ff5b61" stroke-width="3" stroke-dasharray="7 7"/>'
        + ("" if sparse_labels else f'<text x="{x + w - 34}" y="{pit_bottom + 5}" text-anchor="end" font-size="13" font-weight="900" fill="#ff6b70">{threshold_6m_label}</text>')
        + "</g>"
    )
    pipe_well = (
        f'<g data-engineering-object="pipe-well" data-visual-signature-part="pipe-well">'
        f'<path d="M{right_x} {ground_y - 2} V{pit_bottom - 8}" stroke="#ffb184" stroke-width="5" stroke-linecap="round" opacity=".95"/>'
        f'<circle cx="{right_x}" cy="{ground_y - 6}" r="9" fill="#092435" stroke="#ffb184" stroke-width="3"/>'
        + ("" if sparse_labels else f'<text x="{right_x}" y="{ground_y - 21}" text-anchor="middle" font-size="12" font-weight="900" fill="#ffcfb5">管井</text>')
        + "</g>"
    )
    pipe_cross = (
        f'<g data-engineering-object="pipe-well-eliminated" data-visual-signature-part="elimination-mark">'
        f'<path d="M{right_x - 18} {ground_y + 18} L{right_x + 18} {pit_bottom - 12} M{right_x + 18} {ground_y + 18} L{right_x - 18} {pit_bottom - 12}" '
        f'stroke="#ff4d52" stroke-width="5" stroke-linecap="round"/></g>'
    )
    light_wells = (
        f'<g data-engineering-object="light-well-points" data-visual-signature-part="light-well-row">'
        f'<path d="M{pit_left - 12} {ground_y + 8} V{pit_bottom - 14} M{pit_left + 8} {ground_y + 8} V{pit_bottom - 20} M{pit_right - 8} {ground_y + 8} V{pit_bottom - 20} M{pit_right + 12} {ground_y + 8} V{pit_bottom - 14}" '
        f'stroke="#65d4ff" stroke-width="3.4" stroke-linecap="round"/>'
        f'<path d="M{pit_left - 18} {ground_y + 19} H{pit_left + 14} M{pit_right - 14} {ground_y + 19} H{pit_right + 18}" stroke="#65d4ff" stroke-width="2.2" stroke-dasharray="5 4"/>'
        + ("" if sparse_labels else f'<text x="{pit_mid}" y="{ground_y - 20}" text-anchor="middle" font-size="12" font-weight="900" fill="#9ee8ff">轻型井点</text>')
        + "</g>"
    )
    recharge = (
        f'<g data-engineering-object="recharge-well-route" data-visual-signature-part="recharge-route">'
        f'<path d="M{x + w - 62} {ground_y - 2} V{pit_bottom - 26}" stroke="#ffc75f" stroke-width="4.2" stroke-linecap="round"/>'
        f'<circle cx="{x + w - 62}" cy="{ground_y - 7}" r="8" fill="#092435" stroke="#ffc75f" stroke-width="3"/>'
        f'<path d="M{x + w - 62} {ground_y + 34} C{x + w - 88} {ground_y + 26} {x + w - 116} {ground_y + 28} {pit_right + 10} {ground_y + 42}" stroke="#ffc75f" stroke-width="3.5" fill="none" stroke-dasharray="7 5"/>'
        + ("" if compact else f'<text x="{x + w - 82}" y="{ground_y + 19}" text-anchor="middle" font-size="11" font-weight="900" fill="#ffd98a">回灌</text><text x="{pit_right + 18}" y="{ground_y + 35}" font-size="11" font-weight="900" fill="#ffd98a">防沉降</text>')
        + "</g>"
    )
    pressure = (
        f'<g data-engineering-object="artesian-inrush-pressure" data-visual-signature-part="pressure-arrows">'
        f'<path d="M{pit_mid - 30} {pit_bottom + 1} V{pit_bottom - 35} M{pit_mid} {pit_bottom + 1} V{pit_bottom - 43} M{pit_mid + 30} {pit_bottom + 1} V{pit_bottom - 35}" '
        f'stroke="#ff5b61" stroke-width="4" stroke-linecap="round"/>'
        f'<path d="M{pit_mid - 37} {pit_bottom - 27} l7 -10 l7 10 M{pit_mid - 7} {pit_bottom - 35} l7 -10 l7 10 M{pit_mid + 23} {pit_bottom - 27} l7 -10 l7 10" '
        f'stroke="#ff5b61" stroke-width="3" fill="none" stroke-linecap="round"/>'
        + ("" if compact else f'<text x="{pit_mid}" y="{pit_bottom - 50}" text-anchor="middle" font-size="12" font-weight="900" fill="#ff7a80">承压水突涌口</text>')
        + "</g>"
    )
    relief_route = (
        f'<g data-engineering-object="pressure-relief-route" data-visual-signature-part="relief-route">'
        f'<path data-threshold-line="relief-boundary" d="M{pit_right + 18} {pit_bottom - 52} H{x + w - 38}" stroke="#65d4ff" stroke-width="3" stroke-dasharray="6 5"/>'
        + ("" if compact else f'<text x="{pit_right + 22}" y="{pit_bottom - 62}" font-size="11" font-weight="900" fill="#9ee8ff">减压 / 封底隔渗</text>')
        + "</g>"
    )
    layer_fix = (
        f'<g data-engineering-object="layer-depth-control" data-visual-signature-part="layer-depth-control">'
        f'<path data-threshold-line="5m-overlimit" d="M{pit_right + 30} {ground_y + 32} V{pit_bottom}" stroke="#ff5b61" stroke-width="4" stroke-dasharray="6 5"/>'
        f'<path data-threshold-line="3m-control" d="M{pit_right + 46} {ground_y + 32} V{ground_y + 77}" stroke="#19c37d" stroke-width="4"/>'
        + ("" if compact else f'<text x="{pit_right + 53}" y="{ground_y + 58}" font-size="12" font-weight="900" fill="#19d58c">≤3m</text><text x="{pit_right + 36}" y="{pit_bottom + 14}" font-size="12" font-weight="900" fill="#ff6b70">5m</text>')
        + "</g>"
    )
    scan_trace = (
        f'<g data-engineering-object="object-to-score-trace" data-visual-signature-part="answer-trace">'
        f'<path d="M{pit_left + 12} {ground_y + 10} C{x + 120} {y + 25} {x + 210} {y + 28} {x + w - 58} {y + 40}" '
        f'stroke="#65d4ff" stroke-width="3" fill="none" stroke-dasharray="7 5"/>'
        f'<text x="{x + w - 96}" y="{y + 33}" font-size="11" font-weight="900" fill="#9ee8ff">对象→采分句</text></g>'
    )

    base_board = (
        f'<rect data-engineering-object="pit-blueprint-board" data-visual-signature-part="board-frame" x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="#061f2d" stroke="#245f7b" stroke-width="2.4" opacity=".98"/>'
    )
    step0 = (
        base_board
        + _svg_text(title, x + w / 2, y + 18, size=17, fill="#eaf8ff")
        + layer_fill
        + pit_outline
    )

    rule_card = (
        f'<g data-rule-card="blueprint" data-engineering-object="bottom-rule-card" data-visual-signature-part="rule-card">'
        f'<rect x="{x + 16}" y="{rule_y}" width="{w - 32}" height="45" rx="12" fill="#061b28" stroke="#1f526b" stroke-width="2.2"/>'
        f'<rect x="{x + 28}" y="{rule_y + 10}" width="58" height="22" rx="11" fill="#2a2e26" stroke="#f5a623" stroke-width="1.2"/>'
        f'<text x="{x + 57}" y="{rule_y + 26}" text-anchor="middle" font-size="13" font-weight="900" fill="#ffb832">{esc(rule_title)}</text>'
        f'<text x="{x + 99}" y="{rule_y + 22}" text-anchor="start" font-size="{main_size}" font-weight="900" fill="#eaf8ff">{esc(rule_main)}</text>'
        f'<text x="{x + 99}" y="{rule_y + 38}" text-anchor="start" font-size="{sub_size}" font-weight="850" fill="#b9e7f8">{esc(rule_sub)}</text></g>'
    )
    parts = [step("draw_section", 0, step0), step("drop_thresholds", 1, threshold_3m + threshold_6m, trace=True)]
    if "scan_depth_axis" in step_ids:
        parts[-1] = step("scan_depth_axis", 1, threshold_3m + threshold_6m, trace=True)

    if mode in {"problem", "method"}:
        parts.append(step("eliminate_pipe", 2, pipe_well + pipe_cross))
        parts.append(step("attach_light_well", 3, light_wells))
    elif mode == "scan":
        parts.append(pipe_well + pipe_cross + light_wells)
        parts.append(step("trace_to_sentence", 2, scan_trace, trace=True))
        parts.append(step("write_answer_atom", 3, ""))
    elif mode == "inrush":
        parts.append(step("route_recharge", 2, recharge, trace=True))
        parts.append(step("reveal_pressure", 3, pressure))
        parts.append(step("route_relief", 4, relief_route, trace=True))
    elif mode == "layer":
        parts.append(step("mark_five_meter", 2, layer_fix, trace=True))
        parts.append(step("overlay_three_meter", 3, light_wells))
    elif mode == "score":
        parts.append(step("collect_score_lines", 2, pipe_well + pipe_cross + light_wells + recharge + pressure + relief_route + layer_fix, trace=True))
        parts.append(step("compress_labels", 3, ""))
    else:
        parts.append(pipe_well + light_wells)
    parts.append(rule_card)
    return _visual_group(
        node,
        "".join(parts),
    )


def _blueprint_rule_card(
    *,
    x: float,
    y: float,
    w: float,
    title: object,
    main: object,
    sub: object,
) -> str:
    main_size = _fit_font_size(main, w - 142, 20, minimum=12)
    sub_size = _fit_font_size(sub, w - 142, 12, minimum=9)
    return (
        f'<g data-rule-card="blueprint"><rect x="{x}" y="{y}" width="{w}" height="54" rx="14" fill="#061b28" stroke="#1f526b" stroke-width="2.5"/>'
        f'<path d="M{x + 1} {y + 10} Q{x + 1} {y + 2} {x + 9} {y + 2} V{y + 52} Q{x + 1} {y + 52} {x + 1} {y + 44} Z" fill="#f5a623"/>'
        f'<rect x="{x + 16}" y="{y + 10}" width="66" height="26" rx="13" fill="#2a2e26" stroke="#f5a623" stroke-width="1.5"/>'
        f'<text x="{x + 49}" y="{y + 29}" text-anchor="middle" font-size="14" font-weight="950" fill="#ffb832">{esc(title)}</text>'
        f'<text x="{x + 96}" y="{y + 24}" text-anchor="start" font-size="{main_size}" font-weight="950" fill="#eaf8ff">{esc(main)}</text>'
        f'<text x="{x + 96}" y="{y + 44}" text-anchor="start" font-size="{sub_size}" font-weight="850" fill="#b9e7f8">{esc(sub)}</text></g>'
    )


def _inspection_blueprint_board(node: dict[str, Any]) -> str:
    x = float(node.get("x", 10))
    y = float(node.get("y", 18))
    w = float(node.get("w", 400))
    h = float(node.get("h", 255))
    mode = str(node.get("mode", "overview"))
    labels = _labels(node, ["材料样品", "复验闸", "见证章", "隐蔽剖面", "覆盖板", "验收记录"], 6)
    title = str(node.get("text") or "材料复验 + 隐蔽验收")
    rule_title = str(node.get("rule_title") or "采分")
    rule_main = str(node.get("rule_main") or "先复验，再覆盖")
    rule_sub = str(node.get("rule_sub") or "样品、见证、记录都在覆盖前闭合")

    poster = h >= 340
    narrow = w < 500
    top_y = y + (h * 0.13 if poster else 42)
    field_top = y + (h * 0.15 if poster else 50)
    flow_y = y + (h * 0.37 if poster else 116)
    ground_y = y + (h * 0.63 if poster else 174)
    rule_y = y + h - (92 if poster else 57)
    divider_x = x + w * 0.50
    material_x = x + w * 0.135
    gate_x = x + w * 0.27
    lab_x = x + w * 0.395
    hidden_x = x + w * 0.70
    section_w = w * (0.40 if poster else 0.355)
    section_h = h * (0.50 if poster else 0.494)
    section_x = hidden_x - section_w / 2
    section_y = y + (h * 0.215 if poster else 53)
    if narrow:
        material_x = x + 56
        gate_x = x + 138
        lab_x = x + 208
    sample_w = 70 if narrow else 84
    sample_h = 58 if narrow else 70
    gate_bar_gap = 21 if narrow else 25
    gate_w = 54 if narrow else 66
    gate_h = 44 if narrow else 48
    lab_w = 58 if narrow else 76
    lab_h = 58 if narrow else 70
    lane_label_size = 11 if narrow else 12
    cover_line_y = section_y + (20 if poster else 12)
    mid_line_y = section_y + section_h * 0.51
    section_ground_y = section_y + section_h
    wrong = mode in {"branch", "qa"}
    hidden_emphasis = mode in {"hidden", "branch", "score", "qa", "closing"}
    record_emphasis = mode in {"witness", "hidden", "score", "closing"}
    material_emphasis = mode in {"overview", "material", "retest", "witness", "score"}
    show_lane_lab = mode != "material"

    scaffold = (
        f'<text x="{x + w / 2}" y="{y + 20}" text-anchor="middle" font-size="18" font-weight="950" fill="#eaf8ff">{esc(title)}</text>'
        f'<g data-engineering-object="inspection_blueprint_frame">'
        f'<path d="M{x + 20} {top_y + 16} H{x + w - 20} M{x + 20} {ground_y} H{x + w - 20}" stroke="#c8f0ff" stroke-width="3" stroke-linecap="round"/>'
        f'<path d="M{divider_x} {field_top} V{ground_y + 3}" stroke="#235270" stroke-width="2.2" stroke-dasharray="8 8"/>'
        f'<text x="{x + 106}" y="{top_y + 1}" text-anchor="middle" font-size="12" font-weight="900" fill="#9ee8ff">材料进场链</text>'
        f'<text x="{hidden_x}" y="{top_y + 1}" text-anchor="middle" font-size="12" font-weight="900" fill="#9ee8ff">覆盖前工程剖面</text>'
        f'<path data-threshold-line="before_cover_control" d="M{x + 24} {cover_line_y} H{x + w - 26}" stroke="#ff5b61" stroke-width="3.2" stroke-dasharray="8 7"/>'
        f'<circle cx="{x + 24}" cy="{cover_line_y}" r="5" fill="#ff5b61"/>'
        f'<text x="{x + w - 28}" y="{cover_line_y - 6}" text-anchor="end" font-size="12" font-weight="950" fill="#ff6b70">禁盖线</text>'
        f'</g>'
    )
    lane_lab = (
        f'<rect data-layout-item="material.witness-stamp" x="{lab_x - lab_w / 2}" y="{flow_y - lab_h / 2}" width="{lab_w}" height="{lab_h}" rx="13" fill="#092435" stroke="#ffb184" stroke-width="3.2"/>'
        f'<circle cx="{lab_x}" cy="{flow_y - lab_h * 0.18}" r="{10 if narrow else 12}" fill="#331b12" stroke="#ffb184" stroke-width="2.6"/>'
        f'<path d="M{lab_x - lab_w * 0.26} {flow_y + lab_h * 0.18} H{lab_x + lab_w * 0.26}" stroke="#ffb184" stroke-width="4.2" stroke-linecap="round"/>'
        f'<text data-layout-label="material.witness-label" x="{lab_x}" y="{flow_y + lab_h / 2 + 16}" text-anchor="middle" font-size="{lane_label_size}" font-weight="900" fill="#ffcfb5">{esc(labels[2])}</text>'
    ) if show_lane_lab else ""
    material_lane = (
        f'<g data-engineering-object="material_retest_lane" data-visual-signature-part="material_retest_lane">'
        f'<path d="M{x + 34} {flow_y} H{section_x - 14}" stroke="#f5a623" stroke-width="3.8" stroke-dasharray="9 7"/>'
        f'<rect x="{x + 40}" y="{flow_y - 58}" width="{section_x - x - 92}" height="116" rx="16" fill="#061b28" stroke="#1f526b" stroke-width="2.6" opacity=".92"/>'
        f'<rect data-layout-item="material.sample" x="{material_x - sample_w / 2}" y="{flow_y - sample_h / 2}" width="{sample_w}" height="{sample_h}" rx="13" fill="#092435" stroke="#65d4ff" stroke-width="3.2"/>'
        f'<path d="M{material_x - sample_w * 0.28} {flow_y - 12} H{material_x + sample_w * 0.26} M{material_x - sample_w * 0.28} {flow_y + 6} H{material_x + sample_w * 0.18}" stroke="#9ee8ff" stroke-width="3.4" stroke-linecap="round"/>'
        f'<circle cx="{material_x + sample_w * 0.30}" cy="{flow_y + sample_h * 0.26}" r="7" fill="#19c37d"/>'
        f'<path d="M{gate_x - gate_bar_gap} {flow_y - 46} V{flow_y + 46} M{gate_x + gate_bar_gap} {flow_y - 46} V{flow_y + 46}" stroke="#f5a623" stroke-width="5.6" stroke-linecap="round"/>'
        f'<rect data-layout-item="material.retest-gate" x="{gate_x - gate_w / 2}" y="{flow_y - gate_h / 2}" width="{gate_w}" height="{gate_h}" rx="12" fill="#291f12" stroke="#f5a623" stroke-width="3.0"/>'
        f'<text data-layout-label="material.retest-gate-label" x="{gate_x}" y="{flow_y + 5}" text-anchor="middle" font-size="{13 if narrow else 14}" font-weight="950" fill="#ffb832">{esc(labels[1])}</text>'
        f'{lane_lab}'
        f'<text data-layout-label="material.sample-label" x="{material_x}" y="{flow_y + sample_h / 2 + 16}" text-anchor="middle" font-size="{lane_label_size}" font-weight="900" fill="#9ee8ff">{esc(labels[0])}</text>'
        f'</g>'
    )
    hidden_window = (
        f'<g data-engineering-object="hidden_work_section" data-visual-signature-part="hidden_work_section">'
        f'<rect x="{section_x}" y="{section_y}" width="{section_w}" height="{section_h}" rx="3" fill="#0b2e3f" opacity=".82"/>'
        f'<path d="M{section_x} {mid_line_y} H{section_x + section_w}" stroke="#5fb5d8" stroke-width="1.6" stroke-dasharray="5 5"/>'
        f'<path d="M{section_x} {mid_line_y + 31} H{section_x + section_w}" stroke="#e2c995" stroke-width="5.5" opacity=".75"/>'
        f'<path d="M{section_x} {section_y} V{section_ground_y} H{section_x + section_w} V{section_y}" stroke="#e8f8ff" stroke-width="3.6" fill="none"/>'
        f'<path data-threshold-line="hidden_before_cover" d="M{section_x - 12} {cover_line_y} H{section_x + section_w + 12}" stroke="#ff5b61" stroke-width="3.5" stroke-dasharray="8 7"/>'
        f'<circle cx="{section_x - 12}" cy="{cover_line_y}" r="5" fill="#ff5b61"/>'
        f'<rect x="{section_x + 20}" y="{section_y - 23}" width="{section_w - 40}" height="16" rx="4" fill="#092435" stroke="#c8f0ff" stroke-width="2.4"/>'
        f'</g>'
    )
    record_link = (
        f'<g data-engineering-object="witness_record_chain" data-visual-signature-part="witness_record_chain">'
        f'<path d="M{lab_x + 30} {flow_y - 8} C{lab_x + 62} {flow_y - 42} {section_x - 22} {flow_y - 38} {section_x + 6} {flow_y - 8}" stroke="#65d4ff" stroke-width="3.2" fill="none" stroke-dasharray="7 6"/>'
        f'<rect x="{section_x + section_w - 42}" y="{section_y + 42}" width="52" height="62" rx="8" fill="#092435" stroke="#65d4ff" stroke-width="2.8"/>'
        f'<path d="M{section_x + section_w - 31} {section_y + 61} H{section_x + section_w - 1} M{section_x + section_w - 31} {section_y + 76} H{section_x + section_w - 7} M{section_x + section_w - 31} {section_y + 91} H{section_x + section_w - 2}" stroke="#9ee8ff" stroke-width="3" stroke-linecap="round"/>'
        f'<text x="{section_x + section_w - 16}" y="{section_y + 117}" text-anchor="middle" font-size="11" font-weight="900" fill="#9ee8ff">{esc(labels[5])}</text>'
        f'</g>'
    )
    wrong_branch = (
        f'<g data-threshold-line="wrong_branch" data-engineering-object="wrong_branch_elimination" data-visual-signature-part="wrong_branch_elimination">'
        f'<path d="M{x + 44} {flow_y + 47} H{section_x - 16}" stroke="#ff5b61" stroke-width="4" stroke-dasharray="8 7"/>'
        f'<path d="M{section_x - 48} {flow_y + 29} L{section_x - 16} {flow_y + 61} M{section_x - 16} {flow_y + 29} L{section_x - 48} {flow_y + 61}" stroke="#ff5b61" stroke-width="5.2" stroke-linecap="round"/>'
        f'<text x="{section_x - 72}" y="{flow_y + 71}" text-anchor="end" font-size="12" font-weight="900" fill="#ff6b70">有证即用 / 盖后补验</text>'
        f'</g>'
    )
    if narrow:
        material_detail = (
            f'<g data-engineering-object="material_certificate_split" data-visual-signature-part="material_certificate_split">'
            f'<rect x="{x + 40}" y="{flow_y - 54}" width="{w - 80}" height="130" rx="18" fill="#061b28" stroke="#1f526b" stroke-width="2.8" opacity=".94"/>'
            f'<path d="M{x + 74} {flow_y} H{x + w - 72}" stroke="#f5a623" stroke-width="4.2" stroke-dasharray="10 8"/>'
            f'<rect x="{x + 62}" y="{flow_y - 46}" width="76" height="70" rx="14" fill="#092435" stroke="#65d4ff" stroke-width="3.4"/>'
            f'<text x="{x + 100}" y="{flow_y - 18}" text-anchor="middle" font-size="13" font-weight="950" fill="#9ee8ff">合格证</text>'
            f'<path d="M{x + 80} {flow_y + 4} H{x + 122} M{x + 80} {flow_y + 20} H{x + 116}" stroke="#9ee8ff" stroke-width="3.4" stroke-linecap="round"/>'
            f'<path d="M{x + 150} {flow_y - 34} L{x + 174} {flow_y + 34} M{x + 174} {flow_y - 34} L{x + 150} {flow_y + 34}" stroke="#ff5b61" stroke-width="5.2" stroke-linecap="round"/>'
            f'<rect x="{x + 192}" y="{flow_y - 42}" width="78" height="72" rx="15" fill="#291f12" stroke="#f5a623" stroke-width="3.6"/>'
            f'<text x="{x + 231}" y="{flow_y - 13}" text-anchor="middle" font-size="14" font-weight="950" fill="#ffb832">样品</text>'
            f'<path d="M{x + 211} {flow_y + 12} H{x + 251}" stroke="#f5a623" stroke-width="4.6" stroke-linecap="round"/>'
            f'<path d="M{x + 278} {flow_y} H{x + 292}" stroke="#19c37d" stroke-width="4.4" stroke-linecap="round"/>'
            f'<rect x="{x + 300}" y="{flow_y - 42}" width="68" height="76" rx="14" fill="#0c2c22" stroke="#19c37d" stroke-width="3.4"/>'
            f'<text x="{x + 334}" y="{flow_y - 10}" text-anchor="middle" font-size="13" font-weight="950" fill="#9bf3c8">复验</text>'
            f'<text x="{x + 334}" y="{flow_y + 13}" text-anchor="middle" font-size="13" font-weight="950" fill="#9bf3c8">合格</text>'
            f'<text x="{x + w / 2}" y="{flow_y + 58}" text-anchor="middle" font-size="13" font-weight="950" fill="#ff6b70">有证 ≠ 直接使用</text>'
            f'</g>'
        )
    else:
        material_detail = (
        f'<g data-engineering-object="material_certificate_split" data-visual-signature-part="material_certificate_split">'
        f'<rect x="{x + 34}" y="{y + 68}" width="{section_x - x - 78}" height="{ground_y - y - 88}" rx="18" fill="#061b28" stroke="#1f526b" stroke-width="2.8" opacity=".94"/>'
        f'<path d="M{x + 64} {flow_y} H{section_x - 62}" stroke="#f5a623" stroke-width="4.2" stroke-dasharray="10 8"/>'
        f'<rect x="{x + 62}" y="{flow_y - 46}" width="92" height="86" rx="14" fill="#092435" stroke="#65d4ff" stroke-width="3.4"/>'
        f'<text x="{x + 108}" y="{flow_y - 20}" text-anchor="middle" font-size="13" font-weight="950" fill="#9ee8ff">合格证</text>'
        f'<path d="M{x + 82} {flow_y + 2} H{x + 136} M{x + 82} {flow_y + 20} H{x + 126}" stroke="#9ee8ff" stroke-width="3.6" stroke-linecap="round"/>'
        f'<rect x="{x + 204}" y="{flow_y - 42}" width="90" height="76" rx="15" fill="#291f12" stroke="#f5a623" stroke-width="3.6"/>'
        f'<text x="{x + 249}" y="{flow_y - 14}" text-anchor="middle" font-size="14" font-weight="950" fill="#ffb832">样品</text>'
        f'<path d="M{x + 220} {flow_y + 12} H{x + 278}" stroke="#f5a623" stroke-width="5" stroke-linecap="round"/>'
        f'<path d="M{x + 164} {flow_y - 30} L{x + 188} {flow_y + 34} M{x + 188} {flow_y - 30} L{x + 164} {flow_y + 34}" stroke="#ff5b61" stroke-width="5.4" stroke-linecap="round"/>'
        f'<path d="M{x + 302} {flow_y} H{section_x - 86}" stroke="#19c37d" stroke-width="4.6" stroke-linecap="round"/>'
        f'<rect x="{section_x - 78}" y="{flow_y - 36}" width="62" height="72" rx="14" fill="#0c2c22" stroke="#19c37d" stroke-width="3.4"/>'
        f'<text x="{section_x - 47}" y="{flow_y - 7}" text-anchor="middle" font-size="13" font-weight="950" fill="#9bf3c8">复验</text>'
        f'<text x="{section_x - 47}" y="{flow_y + 15}" text-anchor="middle" font-size="13" font-weight="950" fill="#9bf3c8">合格</text>'
        f'<text x="{x + 176}" y="{flow_y + 58}" text-anchor="middle" font-size="13" font-weight="950" fill="#ff6b70">有证 ≠ 直接使用</text>'
        f'</g>'
        )
    retest_matrix = (
        f'<g data-engineering-object="retest_matrix" data-visual-signature-part="retest_matrix">'
        f'<rect x="{x + 30}" y="{y + 60}" width="178" height="104" rx="12" fill="#061b28" stroke="#1f526b" stroke-width="2.5"/>'
        f'<text x="{x + 119}" y="{y + 80}" text-anchor="middle" font-size="12" font-weight="950" fill="#eaf8ff">材料对象复验格</text>'
        f'<path d="M{x + 42} {y + 94} H{x + 196} M{x + 42} {y + 118} H{x + 196} M{x + 42} {y + 142} H{x + 196} M{x + 104} {y + 88} V{y + 156}" stroke="#235270" stroke-width="1.7"/>'
        f'<text x="{x + 72}" y="{y + 111}" text-anchor="middle" font-size="11" font-weight="900" fill="#9ee8ff">钢筋</text>'
        f'<text x="{x + 150}" y="{y + 111}" text-anchor="middle" font-size="10" font-weight="900" fill="#ffcfb5">强度/伸长/重量</text>'
        f'<text x="{x + 72}" y="{y + 135}" text-anchor="middle" font-size="11" font-weight="900" fill="#9ee8ff">水泥</text>'
        f'<text x="{x + 150}" y="{y + 135}" text-anchor="middle" font-size="10" font-weight="900" fill="#ffcfb5">强度/安定性</text>'
        f'<text x="{x + 72}" y="{y + 159}" text-anchor="middle" font-size="11" font-weight="900" fill="#9ee8ff">保温</text>'
        f'<text x="{x + 150}" y="{y + 159}" text-anchor="middle" font-size="10" font-weight="900" fill="#ffcfb5">导热/密度/燃烧</text>'
        f'</g>'
    )
    witness_detail = (
        f'<g data-engineering-object="witness_route_map" data-visual-signature-part="witness_route_map">'
        f'<rect x="{x + 34}" y="{y + 68}" width="{section_x - x - 78}" height="{ground_y - y - 88}" rx="18" fill="#061b28" stroke="#1f526b" stroke-width="2.8" opacity=".94"/>'
        f'<path d="M{x + 74} {flow_y - 12} C{x + 144} {y + 64} {x + 238} {y + 64} {section_x - 66} {flow_y - 12}" stroke="#65d4ff" stroke-width="4.2" fill="none" stroke-dasharray="9 7"/>'
        f'<circle cx="{x + 82}" cy="{flow_y - 12}" r="26" fill="#092435" stroke="#65d4ff" stroke-width="3.6"/>'
        f'<text x="{x + 82}" y="{flow_y - 7}" text-anchor="middle" font-size="11" font-weight="950" fill="#9ee8ff">取样</text>'
        f'<circle cx="{x + 205}" cy="{y + 78}" r="28" fill="#291f12" stroke="#f5a623" stroke-width="3.8"/>'
        f'<text x="{x + 205}" y="{y + 83}" text-anchor="middle" font-size="12" font-weight="950" fill="#ffb832">见证</text>'
        f'<circle cx="{section_x - 70}" cy="{flow_y - 12}" r="26" fill="#092435" stroke="#ffb184" stroke-width="3.6"/>'
        f'<text x="{section_x - 70}" y="{flow_y - 7}" text-anchor="middle" font-size="11" font-weight="950" fill="#ffcfb5">送检</text>'
        f'<rect x="{x + 112}" y="{flow_y + 30}" width="{section_x - x - 196}" height="34" rx="17" fill="#092435" stroke="#65d4ff" stroke-width="2.8"/>'
        f'<text x="{(x + section_x) / 2 - 18}" y="{flow_y + 53}" text-anchor="middle" font-size="13" font-weight="950" fill="#9ee8ff">记录由见证链闭合</text>'
        f'</g>'
    )
    hidden_scan = (
        f'<g data-engineering-object="hidden_shutter_scan" data-visual-signature-part="hidden_shutter_scan">'
        f'<path d="M{section_x + 8} {section_y + 28} H{section_x + section_w - 8}" stroke="#65d4ff" stroke-width="3.4" stroke-dasharray="7 6"/>'
        f'<path d="M{section_x + 8} {section_y + 56} H{section_x + section_w - 8}" stroke="#65d4ff" stroke-width="3.4" stroke-dasharray="7 6"/>'
        f'<path d="M{section_x + 8} {section_y + 84} H{section_x + section_w - 8}" stroke="#65d4ff" stroke-width="3.4" stroke-dasharray="7 6"/>'
        f'<rect x="{section_x - 16}" y="{section_y + 16}" width="14" height="82" rx="7" fill="#65d4ff" opacity=".72"/>'
        f'<text x="{section_x + section_w / 2}" y="{section_y + 112}" text-anchor="middle" font-size="12" font-weight="950" fill="#9ee8ff">基层 / 保温 / 热桥 / 隔汽层</text>'
        f'</g>'
    )
    score_sheet = (
        f'<g data-engineering-object="answer_scan_sheet" data-visual-signature-part="answer_scan_sheet">'
        f'<rect x="{x + 36}" y="{y + 58}" width="174" height="116" rx="12" fill="#061b28" stroke="#1f526b" stroke-width="2.5"/>'
        f'<text x="{x + 123}" y="{y + 80}" text-anchor="middle" font-size="13" font-weight="950" fill="#eaf8ff">答题纸扫描</text>'
        f'<path d="M{x + 54} {y + 101} H{x + 192} M{x + 54} {y + 124} H{x + 192} M{x + 54} {y + 147} H{x + 192}" stroke="#65d4ff" stroke-width="2.5" stroke-linecap="round"/>'
        f'<text x="{x + 62}" y="{y + 97}" font-size="11" font-weight="950" fill="#ffb832">1 材料复验合格</text>'
        f'<text x="{x + 62}" y="{y + 120}" font-size="11" font-weight="950" fill="#ffb832">2 见证取样送检</text>'
        f'<text x="{x + 62}" y="{y + 143}" font-size="11" font-weight="950" fill="#ffb832">3 覆盖前隐蔽验收</text>'
        f'<text x="{x + 62}" y="{y + 166}" font-size="11" font-weight="950" fill="#ffb832">4 合格后使用/覆盖</text>'
        f'</g>'
    )
    rule = _blueprint_rule_card(x=x + 18, y=rule_y, w=w - 36, title=rule_title, main=rule_main, sub=rule_sub)

    body = _step_group(0, scaffold)
    if mode == "material":
        body += _step_group(1, material_lane + hidden_window, trace=True)
    elif mode == "retest":
        body += _step_group(1, retest_matrix + hidden_window, trace=True)
    elif material_emphasis or mode in {"overview", "branch", "closing"}:
        body += _step_group(1, material_lane, trace=True)
    if mode == "witness":
        body += _step_group(2, witness_detail + hidden_window, trace=True)
    elif record_emphasis or mode in {"overview", "branch", "closing"}:
        body += _step_group(2, record_link, trace=True)
    if hidden_emphasis or mode in {"overview", "branch", "closing"}:
        body += _step_group(3, hidden_window + (hidden_scan if mode == "hidden" else ""))
    if wrong:
        body += _step_group(4, wrong_branch, trace=True)
    body += _step_group(5, (score_sheet if mode == "score" else "") + rule)
    return _visual_group(node, body)


def _lifting_threshold_board(node: dict[str, Any]) -> str:
    x = float(node.get("x", 10))
    y = float(node.get("y", 18))
    w = float(node.get("w", 400))
    h = float(node.get("h", 255))
    mode = str(node.get("mode", "overview"))
    title = str(node.get("text") or "正式起吊前四道门")
    rule_title = str(node.get("rule_title") or "判定")
    rule_main = str(node.get("rule_main") or "先过门，再起吊")
    rule_sub = str(node.get("rule_sub") or "危大、条件、试吊、限位合格后放行")
    poster = h >= 340
    narrow = w < 500
    base_y = y + (h * 0.66 if poster else 170)
    tower_x = x + w * 0.22
    jib_y = y + (h * 0.15 if poster else 58)
    hook_x = x + w * 0.62
    load_y = y + (h * 0.46 if poster else 130)
    axis_x = x + w * 0.085
    rule_y = y + h - (92 if poster else 55)
    load_w = 96 if poster else 76
    load_h = 56 if poster else 46
    danger_label = "≥10kN" if narrow else "危大 ≥10kN"
    proof_label = "论证" if narrow else "论证另判"
    show_danger = mode in {"overview", "gate_map", "danger", "precheck", "trial", "limit", "qa", "score", "closing"}
    show_condition = mode in {"gate_map", "precheck", "score", "closing"}
    show_trial = mode in {"trial", "score", "closing"}
    show_limit = mode in {"limit", "qa", "score", "closing"}
    wrong = mode in {"limit", "qa"}

    crane = (
        f'<text x="{x + w / 2}" y="{y + 20}" text-anchor="middle" font-size="17" font-weight="950" fill="#eaf8ff">{esc(title)}</text>'
        f'<g data-engineering-object="crane_load" data-visual-signature-part="crane_load"><path d="M{x + 28} {base_y} H{x + w - 22}" stroke="#c8f0ff" stroke-width="3" stroke-linecap="round"/>'
        f'<path d="M{tower_x - 52} {base_y} H{tower_x + 72} M{tower_x - 42} {base_y + 11} H{tower_x - 6} M{tower_x + 22} {base_y + 11} H{tower_x + 60}" stroke="#c8f0ff" stroke-width="4.4" stroke-linecap="round"/>'
        f'<rect x="{tower_x - 34}" y="{base_y - 22}" width="68" height="22" rx="5" fill="#092435" stroke="#c8f0ff" stroke-width="2.6"/>'
        f'<path d="M{tower_x} {base_y} V{jib_y} H{hook_x + 92}" stroke="#e8f8ff" stroke-width="4.6" fill="none" stroke-linecap="round"/>'
        f'<path d="M{tower_x + 12} {jib_y + 26} L{tower_x + 78} {jib_y} M{tower_x + 38} {base_y} L{tower_x + 112} {jib_y}" stroke="#65d4ff" stroke-width="3" stroke-dasharray="8 6"/>'
        f'<path d="M{tower_x + 20} {jib_y + 54} L{hook_x - 10} {jib_y} M{tower_x + 54} {jib_y + 98} L{hook_x + 62} {jib_y}" stroke="#235270" stroke-width="2" stroke-dasharray="8 7"/>'
        f'<path d="M{hook_x} {jib_y} V{load_y - 27}" stroke="#9ee8ff" stroke-width="3"/>'
        f'<path d="M{hook_x - 12} {load_y - 27} h24 l-6 16 h-12 z" fill="#092435" stroke="#9ee8ff" stroke-width="2.4"/>'
        f'<path d="M{hook_x - 20} {load_y - 10} L{hook_x - load_w / 2} {load_y + 12} M{hook_x + 20} {load_y - 10} L{hook_x + load_w / 2} {load_y + 12}" stroke="#9ee8ff" stroke-width="2.8" stroke-linecap="round"/>'
        f'<rect x="{hook_x - load_w / 2}" y="{load_y - 10}" width="{load_w}" height="{load_h}" rx="9" fill="#0b2e3f" stroke="#ffb184" stroke-width="3.4"/>'
        f'<path d="M{hook_x - load_w / 2 + 10} {load_y + load_h - 1} H{hook_x + load_w / 2 - 10}" stroke="#ffcfb5" stroke-width="3" stroke-linecap="round"/>'
        f'<text x="{hook_x}" y="{load_y + 20}" text-anchor="middle" font-size="18" font-weight="950" fill="#ffcfb5">12kN</text></g>'
    )
    danger_lines = (
        f'<g data-threshold-line="lifting_thresholds" data-visual-signature-part="lifting_thresholds"><path d="M{axis_x} {base_y - 103} V{base_y - 16}" stroke="#6bc9f5" stroke-width="2.4"/>'
        f'<path d="M{axis_x - 7} {base_y - 95} l7 -14 l7 14 M{axis_x - 7} {base_y - 29} l7 14 l7 -14" stroke="#6bc9f5" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
        f'<circle cx="{axis_x}" cy="{base_y - 73}" r="5" fill="#f5a623"/><path d="M{axis_x} {base_y - 73} H{x + w - 38}" stroke="#f5a623" stroke-width="3" stroke-dasharray="8 7"/>'
        f'<text x="{x + w - 34}" y="{base_y - 69}" text-anchor="end" font-size="13" font-weight="950" fill="#ffb832">{danger_label}</text>'
        f'<circle cx="{axis_x}" cy="{base_y - 28}" r="5" fill="#ff5b61"/><path d="M{axis_x} {base_y - 28} H{x + w - 38}" stroke="#ff5b61" stroke-width="3" stroke-dasharray="8 7"/>'
        f'<text x="{x + w - 34}" y="{base_y - 24}" text-anchor="end" font-size="13" font-weight="950" fill="#ff6b70">{proof_label}</text></g>'
    )
    condition_panel = (
        f'<g data-engineering-object="site_condition_panel" data-visual-signature-part="site_condition_panel"><rect x="{x + 244}" y="{y + 50}" width="118" height="68" rx="12" fill="#061b28" stroke="#1f526b" stroke-width="2.2"/>'
        f'<path d="M{x + 260} {y + 78} h72" stroke="#65d4ff" stroke-width="3" stroke-linecap="round"/>'
        f'<path d="M{x + 296} {y + 78} c12 -16 28 -16 40 0" stroke="#f5a623" stroke-width="3" fill="none"/>'
        f'<text x="{x + 303}" y="{y + 106}" text-anchor="middle" font-size="12" font-weight="900" fill="#9ee8ff">风 / 基础 / 警戒</text></g>'
    )
    trial_panel = (
        f'<g data-threshold-line="trial_lift_band" data-engineering-object="trial_lift_axis" data-visual-signature-part="trial_lift_axis"><path d="M{hook_x + 62} {load_y + 34} V{load_y - 8}" stroke="#6bc9f5" stroke-width="2.4"/>'
        f'<path d="M{hook_x + 56} {load_y + 26} l6 12 l6 -12 M{hook_x + 56} {load_y + 4} l6 -12 l6 12" stroke="#6bc9f5" stroke-width="2.4" fill="none"/>'
        f'<text x="{hook_x + 70}" y="{load_y + 16}" font-size="12" font-weight="950" fill="#9ee8ff">200-500mm</text>'
        f'<path d="M{x + 176} {base_y - 3} H{x + 302}" stroke="#19c37d" stroke-width="4" stroke-dasharray="8 7"/>'
        f'<text x="{x + 236}" y="{base_y + 17}" text-anchor="middle" font-size="12" font-weight="900" fill="#19d58c">离地四查</text></g>'
    )
    limit_panel = (
        f'<g data-engineering-object="limit_stop_release" data-visual-signature-part="limit_stop_release"><rect x="{x + 254}" y="{y + 124}" width="110" height="48" rx="12" fill="#092435" stroke="{"#ff5b61" if wrong else "#19c37d"}" stroke-width="2.8"/>'
        f'<text x="{x + 309}" y="{y + 154}" text-anchor="middle" font-size="12" font-weight="950" fill="{"#ff6b70" if wrong else "#9bf3c8"}">{"限位故障" if wrong else "合格放行"}</text>'
        + (
            f'<path d="M{x + 268} {y + 132} L{x + 350} {y + 166} M{x + 350} {y + 132} L{x + 268} {y + 166}" stroke="#ff5b61" stroke-width="4" stroke-linecap="round"/>'
            if wrong
            else f'<circle cx="{x + 270}" cy="{y + 148}" r="9" fill="#19c37d"/><path d="M{x + 265} {y + 148} l4 5 l9 -12" stroke="#061b28" stroke-width="3" fill="none" stroke-linecap="round"/>'
        )
        + '</g>'
    )
    danger_compare = (
        f'<g data-engineering-object="danger_threshold_compare" data-visual-signature-part="danger_threshold_compare">'
        f'<rect x="{hook_x - load_w / 2 - 8}" y="{load_y - 18}" width="{load_w + 16}" height="{load_h + 16}" rx="14" fill="none" stroke="#f5a623" stroke-width="3.4" stroke-dasharray="8 6"/>'
        f'<path d="M{hook_x + load_w / 2 + 12} {load_y + 6} H{x + w - 170}" stroke="#f5a623" stroke-width="3.2" stroke-dasharray="8 7"/>'
        f'<circle cx="{hook_x + load_w / 2 + 20}" cy="{load_y + 6}" r="5" fill="#f5a623"/>'
        f'</g>'
    )
    gate_map_panel = (
        f'<g data-engineering-object="four_gate_map" data-visual-signature-part="four_gate_map">'
        f'<rect x="{x + 42}" y="{y + 66}" width="292" height="74" rx="14" fill="#061b28" stroke="#1f526b" stroke-width="2.4"/>'
        f'<path d="M{x + 70} {y + 103} H{x + 308}" stroke="#65d4ff" stroke-width="3" stroke-linecap="round"/>'
        f'<circle cx="{x + 72}" cy="{y + 103}" r="13" fill="#291f12" stroke="#f5a623" stroke-width="2.6"/><text x="{x + 72}" y="{y + 108}" text-anchor="middle" font-size="10" font-weight="950" fill="#ffb832">门槛</text>'
        f'<circle cx="{x + 150}" cy="{y + 103}" r="13" fill="#092435" stroke="#65d4ff" stroke-width="2.6"/><text x="{x + 150}" y="{y + 108}" text-anchor="middle" font-size="10" font-weight="950" fill="#9ee8ff">条件</text>'
        f'<circle cx="{x + 228}" cy="{y + 103}" r="13" fill="#092435" stroke="#65d4ff" stroke-width="2.6"/><text x="{x + 228}" y="{y + 108}" text-anchor="middle" font-size="10" font-weight="950" fill="#9ee8ff">试吊</text>'
        f'<circle cx="{x + 306}" cy="{y + 103}" r="13" fill="#0c2c22" stroke="#19c37d" stroke-width="2.6"/><text x="{x + 306}" y="{y + 108}" text-anchor="middle" font-size="10" font-weight="950" fill="#9bf3c8">放行</text>'
        f'</g>'
    )
    condition_grid = (
        f'<g data-engineering-object="site_condition_scan_grid" data-visual-signature-part="site_condition_scan_grid">'
        f'<rect x="{x + 236}" y="{y + 50}" width="136" height="106" rx="13" fill="#061b28" stroke="#1f526b" stroke-width="2.5"/>'
        f'<text x="{x + 304}" y="{y + 71}" text-anchor="middle" font-size="12" font-weight="950" fill="#eaf8ff">作业条件扫描</text>'
        f'<path d="M{x + 248} {y + 86} H{x + 360} M{x + 248} {y + 113} H{x + 360} M{x + 304} {y + 80} V{y + 147}" stroke="#235270" stroke-width="1.6"/>'
        f'<text x="{x + 276}" y="{y + 103}" text-anchor="middle" font-size="11" font-weight="900" fill="#9ee8ff">天气</text>'
        f'<text x="{x + 332}" y="{y + 103}" text-anchor="middle" font-size="11" font-weight="900" fill="#9ee8ff">基础</text>'
        f'<text x="{x + 276}" y="{y + 132}" text-anchor="middle" font-size="11" font-weight="900" fill="#9ee8ff">索具</text>'
        f'<text x="{x + 332}" y="{y + 132}" text-anchor="middle" font-size="11" font-weight="900" fill="#9ee8ff">吊点</text>'
        f'<path d="M{x + 252} {y + 91} H{x + 356}" stroke="#f5a623" stroke-width="3.4" stroke-dasharray="7 6"/>'
        f'</g>'
    )
    trial_detail = (
        f'<g data-engineering-object="trial_lift_measure_band" data-visual-signature-part="trial_lift_measure_band">'
        f'<rect x="{x + 190}" y="{load_y + 4}" width="92" height="28" rx="14" fill="#0c2c22" stroke="#19c37d" stroke-width="2.8"/>'
        f'<text x="{x + 236}" y="{load_y + 23}" text-anchor="middle" font-size="11" font-weight="950" fill="#9bf3c8">先离地四查</text>'
        f'<path d="M{x + 178} {load_y + 38} H{x + 304}" stroke="#19c37d" stroke-width="3.4" stroke-dasharray="8 7"/>'
        f'</g>'
    )
    limit_detail = (
        f'<g data-engineering-object="limit_fault_lockout" data-visual-signature-part="limit_fault_lockout">'
        f'<path d="M{x + 252} {y + 118} H{x + 368} V{y + 178} H{x + 252} Z" fill="none" stroke="#ff5b61" stroke-width="2.4" stroke-dasharray="8 7"/>'
        f'<text x="{x + 310}" y="{y + 188}" text-anchor="middle" font-size="11" font-weight="950" fill="#ff6b70">停用 · 排故 · 复查</text>'
        f'</g>'
    )
    score_chain = (
        f'<g data-engineering-object="lifting_answer_chain" data-visual-signature-part="lifting_answer_chain">'
        f'<rect x="{x + 42}" y="{y + 62}" width="170" height="108" rx="13" fill="#061b28" stroke="#1f526b" stroke-width="2.5"/>'
        f'<text x="{x + 127}" y="{y + 83}" text-anchor="middle" font-size="13" font-weight="950" fill="#eaf8ff">答题纸四道门</text>'
        f'<text x="{x + 58}" y="{y + 106}" font-size="11" font-weight="950" fill="#ffb832">1 判危大/论证门槛</text>'
        f'<text x="{x + 58}" y="{y + 127}" font-size="11" font-weight="950" fill="#ffb832">2 查天气基础索具吊点</text>'
        f'<text x="{x + 58}" y="{y + 148}" font-size="11" font-weight="950" fill="#ffb832">3 90%以上先试吊四查</text>'
        f'<text x="{x + 58}" y="{y + 169}" font-size="11" font-weight="950" fill="#ffb832">4 合格后正式起吊</text>'
        f'</g>'
    )
    rule = _blueprint_rule_card(x=x + 18, y=rule_y, w=w - 36, title=rule_title, main=rule_main, sub=rule_sub)

    body = _step_group(0, crane)
    if show_danger:
        body += _step_group(1, danger_lines + (danger_compare if mode == "danger" else ""), trace=True)
    if show_condition:
        if mode == "gate_map":
            body += _step_group(2, gate_map_panel)
        elif mode == "precheck":
            body += _step_group(2, condition_grid)
        else:
            body += _step_group(2, condition_panel)
    if show_trial:
        body += _step_group(3, trial_panel + (trial_detail if mode == "trial" else ""), trace=True)
    if show_limit:
        body += _step_group(4, limit_panel + (limit_detail if mode in {"limit", "qa"} else ""))
    body += _step_group(5, (score_chain if mode == "score" else "") + rule)
    return _visual_group(node, body)


def _grade_threshold_board(node: dict[str, Any]) -> str:
    """Generic graded-axis classification board.

    Renders a title, one horizontal graded axis per entry in ``axes`` (each with
    a name, a left->right track split into ``bands`` labelled segments, and a
    probe marker positioned at the ``hit_index`` band), and a final result light
    showing ``result.label``. Nothing domain-specific is hardcoded; all text
    comes from node data.

    primitive_steps DOM ordering (the preview/contract gates align
    ``primitive_steps[]`` to emitted ``data-primitive-step="N"`` groups by index):
      index 0        -> title reveal (plain group)
      index 1..n     -> probe-slide for axis i (i=0..n-1), trace group (sweep)
      index n+1      -> take-highest / result-light reveal (plain group, final)
    """
    x = float(node.get("x", 10))
    y = float(node.get("y", 18))
    w = float(node.get("w", 320))
    h = float(node.get("h", 200))
    title = str(node.get("text") or "量尺取档")
    rule_main = str(node.get("rule_main") or "任一达高级即按高级")

    raw_axes = node.get("axes")
    axes = raw_axes if isinstance(raw_axes, list) and raw_axes else []
    if not axes:
        # Defensive fallback so the primitive never crashes on a malformed IR.
        axes = [{"name": label, "bands": ["一般", "较大", "重大", "特别重大"], "probe": "—", "hit_index": 0}
                for label in _labels(node, ["指标一", "指标二", "指标三"], 3)]
    axes = axes[:4]

    result = node.get("result") if isinstance(node.get("result"), dict) else {}
    result_label = str(result.get("label") or "—")

    danger = _tone("danger")
    success = _tone("success")
    neutral = _tone("neutral")
    amber = _tone("amber")

    title_size = _fit_font_size(title, w - 24, 16, minimum=12)
    rule_y = y + h - 38

    base_board = (
        f'<rect data-engineering-object="grade-board" data-visual-signature-part="board-frame" '
        f'x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{neutral["fill"]}" '
        f'stroke="{neutral["stroke"]}" stroke-width="2.2"/>'
    )
    step0 = base_board + _svg_text(title, x + w / 2, y + 20, size=title_size, fill=neutral["text"])

    # Axis band layout — evenly distribute axes between title and the rule card.
    axes_top = y + 36
    axes_bottom = rule_y - 8
    n = max(len(axes), 1)
    row_gap = (axes_bottom - axes_top) / n
    name_w = w * 0.26
    track_x = x + 14 + name_w
    track_w = w * 0.62
    track_right = track_x + track_w

    axis_parts: list[str] = []
    for i, axis in enumerate(axes):
        if not isinstance(axis, dict):
            axis = {}
        name = str(axis.get("name") or f"指标{i + 1}")
        bands = [str(b) for b in axis.get("bands", []) if b is not None] or ["一般", "较大", "重大", "特别重大"]
        bands = bands[:5]
        probe = str(axis.get("probe") or "—")
        try:
            hit_index = int(axis.get("hit_index", 0))
        except (TypeError, ValueError):
            hit_index = 0
        hit_index = max(0, min(hit_index, len(bands) - 1))

        row_cy = axes_top + row_gap * i + row_gap / 2
        track_y = row_cy - 8
        cell_w = track_w / len(bands)
        name_size = _fit_font_size(name, name_w + 2, 13, minimum=11)

        cells = ""
        for b_idx, band in enumerate(bands):
            cx = track_x + cell_w * b_idx
            hit = b_idx == hit_index
            cell_tone = success if hit else neutral
            band_size = _fit_font_size(band, cell_w + 4, 11, minimum=11)
            cells += (
                f'<rect x="{cx}" y="{track_y}" width="{cell_w}" height="16" '
                f'fill="{cell_tone["fill"]}" stroke="{cell_tone["stroke"]}" '
                f'stroke-width="{2 if hit else 1}"/>'
                + _svg_text(band, cx + cell_w / 2, track_y + 12, size=band_size, fill=cell_tone["text"], weight=800)
            )

        name_svg = _svg_text(name, x + 12, row_cy + 4, size=name_size, fill=neutral["text"], weight=900, anchor="start")

        probe_cx = track_x + cell_w * hit_index + cell_w / 2
        probe_tone = success if probe and probe != "—" else amber
        probe_size = _fit_font_size(probe, cell_w + 24, 11, minimum=11)
        # trace=True so the probe step animates as a left->right sweep into its band.
        probe_marker = _step_group(
            i + 1,
            f'<path d="M{track_x} {track_y - 9} H{probe_cx}" stroke="{probe_tone["stroke"]}" '
            f'stroke-width="2.4" stroke-dasharray="5 4"/>'
            f'<path d="M{probe_cx} {track_y - 12} l-5 -8 h10 z" fill="{probe_tone["stroke"]}"/>'
            + _label_badge(probe, probe_cx, track_y - 18, tone=probe_tone, size=probe_size),
            trace=True,
        )
        axis_parts.append(
            f'<g data-engineering-object="grade-axis-{i}" data-visual-signature-part="grade-axis">'
            + name_svg + cells + "</g>"
            + probe_marker
        )

    result_step = _step_group(
        len(axes) + 1,
        f'<g data-engineering-object="grade-result" data-visual-signature-part="result-light">'
        f'<rect x="{x + 14}" y="{rule_y}" width="{w - 28}" height="30" rx="11" '
        f'fill="{danger["fill"]}" stroke="{danger["stroke"]}" stroke-width="2"/>'
        + _svg_text(rule_main, x + 18, rule_y + 19, size=_fit_font_size(rule_main, (w - 28) * 0.58, 12, minimum=11), fill=danger["text"], weight=850, anchor="start")
        + _label_badge(result_label, track_right - 4, rule_y + 15, tone=danger, size=12)
        + "</g>",
    )

    parts = [_step_group(0, step0)] + axis_parts + [result_step]
    return _visual_group(node, "".join(parts))


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
    if kind == "power_distribution_tree":
        return _power_distribution_tree(node)
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
    if kind == "process_flow" and str(node.get("mode", "")) == "hidden_sample_objects":
        labels = _labels(node, ["合格证", "材料样品", "复验闸", "见证章", "隐蔽剖面"], 5)
        yy = y + 92
        entry_x = x + w * 0.18
        gate_x = x + w * 0.43
        stamp_x = x + w * 0.64
        hidden_x = x + w * 0.84
        parts = [
            _step_group(0, _svg_text(text or "材料样品与隐蔽剖面", x + w / 2, y + 28, size=15, fill=tone["text"])),
            _step_group(1, f'<path d="M{x + 42} {yy + 42} H{x + w - 42}" stroke="#cbd5e1" stroke-width="6" stroke-linecap="round"/>', trace=True),
        ]
        parts.append(
            _step_group(
                2,
                f'<g data-layout-item="hidden.entry">'
                f'<g data-layout-shape="hidden.entry">'
                f'<rect x="{entry_x - 40}" y="{yy - 30}" width="80" height="58" rx="17" fill="#ecfdf5" stroke="#10b981" stroke-width="3.4"/>'
                f'<path d="M{entry_x - 23} {yy - 12} H{entry_x - 4} M{entry_x - 23} {yy + 1} H{entry_x - 7}" stroke="#2563eb" stroke-width="3.2" stroke-linecap="round"/>'
                f'<circle cx="{entry_x - 21}" cy="{yy + 15}" r="7" fill="#93c5fd" stroke="#1d4ed8" stroke-width="2.5"/>'
                f'<circle cx="{entry_x + 23}" cy="{yy - 12}" r="11" fill="#d1fae5" stroke="#047857" stroke-width="2.8"/>'
                f'<rect x="{entry_x + 5}" y="{yy + 3}" width="27" height="9" rx="4" fill="#a7f3d0"/>'
                f'<path d="M{entry_x - 26} {yy + 32} H{entry_x + 30}" stroke="#047857" stroke-width="4.2" stroke-linecap="round"/>'
                f'</g>'
                + _layout_label_badge("hidden.entry", "材料进场", entry_x, y + 158, tone=_tone("blue"), width=70, size=10)
                + '</g>',
            )
        )
        parts.append(
            _step_group(
                3,
                f'<g data-layout-item="hidden.gate">'
                f'<g data-layout-shape="hidden.gate">'
                f'<path d="M{gate_x - 22} {yy + 30} V{yy - 29} M{gate_x + 22} {yy + 30} V{yy - 29}" stroke="#f59e0b" stroke-width="5.4" stroke-linecap="round"/>'
                f'<rect x="{gate_x - 20}" y="{yy - 20}" width="40" height="44" rx="10" fill="#fff7ed" stroke="#f59e0b" stroke-width="3.2"/>'
                f'<path d="M{gate_x - 8} {yy - 5} H{gate_x + 10} M{gate_x - 8} {yy + 8} H{gate_x + 7}" stroke="#f97316" stroke-width="3.2" stroke-linecap="round"/>'
                f'<circle cx="{gate_x - 14}" cy="{yy - 5}" r="3.7" fill="#10b981"/><circle cx="{gate_x - 14}" cy="{yy + 8}" r="3.7" fill="#10b981"/>'
                f'</g>'
                + _layout_label_badge("hidden.gate", labels[2], gate_x, y + 158, tone=_tone("amber"), width=62, size=10)
                + '</g>',
            )
        )
        parts.append(
            _step_group(
                4,
                f'<g data-layout-item="hidden.stamp">'
                f'<g data-layout-shape="hidden.stamp">'
                f'<rect x="{stamp_x - 20}" y="{yy - 28}" width="40" height="51" rx="12" fill="#fff7ed" stroke="#f97316" stroke-width="3.2"/>'
                f'<path d="M{stamp_x - 9} {yy - 2} H{stamp_x + 9} M{stamp_x - 14} {yy + 14} H{stamp_x + 14}" stroke="#9a3412" stroke-width="4.2" stroke-linecap="round"/>'
                f'<circle cx="{stamp_x}" cy="{yy - 13}" r="8.5" fill="#fed7aa" stroke="#f97316" stroke-width="2.6"/>'
                f'</g>'
                + _layout_label_badge("hidden.stamp", labels[3], stamp_x, y + 158, tone=_tone("danger"), width=56, size=10)
                + '</g>',
            )
        )
        parts.append(
            _step_group(
                5,
                f'<g data-layout-item="hidden.cut">'
                f'<g data-layout-shape="hidden.cut">'
                f'<rect x="{hidden_x - 25}" y="{yy - 32}" width="50" height="62" rx="11" fill="#f8fafc" stroke="#94a3b8" stroke-width="3.2"/>'
                f'<rect x="{hidden_x - 18}" y="{yy - 22}" width="36" height="9" rx="4" fill="#cbd5e1"/>'
                f'<rect x="{hidden_x - 18}" y="{yy - 8}" width="36" height="9" rx="4" fill="#a7f3d0"/>'
                f'<rect x="{hidden_x - 18}" y="{yy + 6}" width="36" height="9" rx="4" fill="#fde68a"/>'
                f'<path d="M{hidden_x - 25} {yy - 43} H{hidden_x + 25}" stroke="#ef4444" stroke-width="4.6" stroke-linecap="round" stroke-dasharray="7 6"/>'
                f'<circle cx="{hidden_x + 22}" cy="{yy + 23}" r="8.5" fill="#10b981" stroke="#047857" stroke-width="2.6"/>'
                f'</g>'
                + _layout_label_badge("hidden.cut", labels[4], hidden_x, y + 158, tone=_tone("neutral"), width=62, size=10)
                + '</g>',
            )
        )
        return _visual_group(node, "".join(parts))
    if kind == "process_flow" and str(node.get("mode", "")) == "acceptance_objects":
        labels = _labels(node, ["报验单", "检验批车", "验收闸", "记录表"], 4)
        points = [
            (x + 46, y + 88),
            (x + 126, y + 88),
            (x + 208, y + 88),
            (x + 286, y + 88),
        ]
        parts = [
            _step_group(0, _svg_text(text or "现场对象流转", x + w / 2, y + 28, size=15, fill=tone["text"])),
            _step_group(1, f'<path d="M{x + 38} {y + 118} H{x + w - 30}" stroke="#cbd5e1" stroke-width="7" stroke-linecap="round"/>', trace=True),
        ]
        doc_x, doc_y = points[0]
        cart_x, cart_y = points[1]
        gate_x, gate_y = points[2]
        rec_x, rec_y = points[3]
        parts.append(
            _step_group(
                2,
                f'<rect x="{doc_x - 26}" y="{doc_y - 34}" width="52" height="66" rx="8" fill="#eff6ff" stroke="#60a5fa" stroke-width="4"/>'
                f'<path d="M{doc_x + 8} {doc_y - 34} L{doc_x + 26} {doc_y - 16} H{doc_x + 8} Z" fill="#dbeafe" stroke="#60a5fa" stroke-width="3"/>'
                f'<path d="M{doc_x - 14} {doc_y - 8} H{doc_x + 14} M{doc_x - 14} {doc_y + 6} H{doc_x + 10}" stroke="#2563eb" stroke-width="4" stroke-linecap="round"/>'
                + _svg_text(labels[0], doc_x, y + 154, size=_fit_font_size(labels[0], 74, 12, minimum=9), fill="#1d4ed8"),
            )
        )
        parts.append(
            _step_group(
                3,
                f'<rect x="{cart_x - 34}" y="{cart_y - 17}" width="68" height="36" rx="11" fill="#ecfdf5" stroke="#10b981" stroke-width="4"/>'
                f'<path d="M{cart_x - 23} {cart_y - 20} H{cart_x + 22}" stroke="#047857" stroke-width="5" stroke-linecap="round"/>'
                f'<circle cx="{cart_x - 20}" cy="{cart_y + 28}" r="8" fill="#047857"/><circle cx="{cart_x + 22}" cy="{cart_y + 28}" r="8" fill="#047857"/>'
                + _svg_text(labels[1], cart_x, y + 154, size=_fit_font_size(labels[1], 78, 12, minimum=9), fill="#047857"),
            )
        )
        parts.append(
            _step_group(
                4,
                f'<path d="M{gate_x - 30} {gate_y + 30} V{gate_y - 32} M{gate_x + 30} {gate_y + 30} V{gate_y - 32}" stroke="#f59e0b" stroke-width="7" stroke-linecap="round"/>'
                f'<rect x="{gate_x - 35}" y="{gate_y - 20}" width="70" height="24" rx="10" fill="#fff7ed" stroke="#f59e0b" stroke-width="4"/>'
                f'<path d="M{gate_x - 20} {gate_y - 8} H{gate_x + 20}" stroke="#f97316" stroke-width="5" stroke-linecap="round"/>'
                + _svg_text(labels[2], gate_x, y + 154, size=_fit_font_size(labels[2], 78, 12, minimum=9), fill="#b45309"),
            )
        )
        parts.append(
            _step_group(
                5,
                f'<rect x="{rec_x - 28}" y="{rec_y - 35}" width="56" height="66" rx="9" fill="#fffdf7" stroke="#e0cfae" stroke-width="4"/>'
                f'<rect x="{rec_x - 14}" y="{rec_y - 43}" width="28" height="13" rx="6" fill="#ffd27f" stroke="#e0a83d" stroke-width="3"/>'
                f'<path d="M{rec_x - 16} {rec_y - 8} H{rec_x + 16} M{rec_x - 16} {rec_y + 7} H{rec_x + 12}" stroke="#8b5e1f" stroke-width="4" stroke-linecap="round"/>'
                f'<rect x="{rec_x - 32}" y="{rec_y + 32}" width="64" height="11" rx="4" fill="#cbd5e1"/>'
                f'<rect x="{rec_x - 24}" y="{rec_y + 45}" width="48" height="10" rx="4" fill="#94a3b8"/>'
                + _svg_text(labels[3], rec_x, y + 154, size=_fit_font_size(labels[3], 78, 12, minimum=9), fill="#6b4e16"),
            )
        )
        return _visual_group(node, "".join(parts))
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
    if kind == "pit_threshold_board":
        return _pit_threshold_board(node)
    if kind == "inspection_blueprint_board":
        return _inspection_blueprint_board(node)
    if kind == "lifting_threshold_board":
        return _lifting_threshold_board(node)
    if kind == "grade_threshold_board":
        return _grade_threshold_board(node)
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
            )
            + _step_group(
                3,
                f'<path d="M{x + 32} {y + 188} H{x + w - 32}" stroke="#60a5fa" stroke-width="5" stroke-linecap="round" stroke-dasharray="10 7"/>'
                + _label_badge(labels[3], x + w / 2, y + 188, tone=_tone("blue"), width=132, size=11),
                trace=True,
            )
        )
    if kind == "answer_scan":
        labels = _labels(node, ["对象", "条件", "依据", "采分句"], 4)
        states = [("#ecfdf5", "#10b981", "命中"), ("#fffbeb", "#f59e0b", "半中"), ("#fef2f2", "#ef4444", "漏"), ("#eff6ff", "#60a5fa", "补")]
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
            _step_group(
                0,
                f'<path d="M{line_start} {yy} H{x2}" stroke="{stroke}" stroke-width="5" stroke-linecap="round"/>'
                f'<path d="M{x2 - 12} {yy - 8} L{x2} {yy} L{x2 - 12} {yy + 8}" fill="none" stroke="{stroke}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'
                + label,
                trace=True,
            ),
        )
    if kind == "threshold_meter":
        value = max(0, min(1, float(node.get("value", 0.62))))
        marker = x + w * value
        label_y = float(node.get("label_y", y - 12 if y + 52 > 244 else y + 48))
        label_size = _fit_font_size(text, w, 13, minimum=10)
        return _visual_group(
            node,
            _step_group(
                0,
                f'<rect x="{x}" y="{y}" width="{w}" height="18" rx="9" fill="#e2e8f0"/>'
                f'<rect x="{x}" y="{y}" width="{w * value}" height="18" rx="9" fill="{tone["stroke"]}" opacity=".85"/>'
                f'<path d="M{marker} {y - 8} V{y + 30}" stroke="#f97316" stroke-width="4" stroke-linecap="round"/>'
                + _svg_text(text, x + w / 2, label_y, size=label_size, fill=tone["text"]),
                trace=True,
            ),
        )
    raise ValueError(f"unsupported visual primitive kind: {kind}")


def _visual_svg(scene: dict[str, Any], visual_library: dict[str, Any]) -> str | None:
    visual = visual_library.get(str(scene.get("id")))
    if not visual:
        return None
    board = str(visual.get("board", "warm_grid"))
    is_poster = board == "blueprint_poster"

    def blueprint_background(width: int, height: int, *, poster: bool, wide: bool = False) -> str:
        h_lines = " ".join(f"M0 {line} H{width}" for line in range(44, height, 60))
        v_lines = " ".join(f"M{line} 0 V{height}" for line in range(52, width, 80))
        if poster:
            badge = str(scene.get("keycard") or "")[:9]
            badge_w = max(118, min(170, len(badge) * 12 + 36))
            badge_size = _fit_font_size(badge, badge_w, 12, minimum=10)
            label_x = max(210, 28 + badge_w + 36)
            header = (
                f'<rect x="28" y="36" width="{badge_w}" height="30" rx="15" fill="#2a2e26" stroke="#f5a623" stroke-width="1.6"/>'
                f'<text x="{28 + badge_w / 2}" y="56" text-anchor="middle" font-size="{badge_size}" font-weight="900" fill="#ffb832">{esc(badge)}</text>'
                f'<text x="{label_x}" y="60" text-anchor="middle" font-size="{22 if not wide else 24}" font-weight="950" fill="#eaf8ff">{esc(scene.get("label", "教学图"))}</text>'
            )
        else:
            header = ""
        return (
            f'<rect x="0" y="0" width="{width}" height="{height}" rx="0" fill="#092434"/>'
            f'<path d="{h_lines} {v_lines}" stroke="#123447" stroke-width="1.1" opacity=".72"/>'
            f'<rect x="10" y="{16 if poster else 14}" width="{width - 20}" height="{height - (32 if poster else 28)}" rx="24" fill="none" stroke="#235270" stroke-width="2"/>'
            f'{header}'
        )

    def wide_node(node: dict[str, Any]) -> dict[str, Any]:
        copy = dict(node)
        if copy.get("kind") in {"inspection_blueprint_board", "lifting_threshold_board"}:
            copy.update({"x": 26, "y": 30, "w": 868, "h": 360})
        return copy

    if board == "paper":
        background = '<rect x="28" y="30" width="304" height="210" rx="18" fill="#fffdf7" stroke="#eadfcb" stroke-width="4"/>' + _svg_text("答题纸这样写", 54, 72, size=15, fill="#176b7a", anchor="start")
    elif board in {"blueprint", "blueprint_poster"}:
        blueprint_h = 640 if is_poster else 300
        background = blueprint_background(420, blueprint_h, poster=is_poster)
    elif board == "closing":
        background = '<rect x="24" y="34" width="312" height="198" rx="22" fill="#ecfdf5" stroke="#10b981" stroke-width="3"/>'
    else:
        background = '<rect x="12" y="18" width="336" height="234" rx="22" fill="#fffdf7" stroke="#eadfcb" stroke-width="3"/><path d="M44 66 H316 M44 120 H316 M44 174 H316 M88 40 V230 M180 40 V230 M272 40 V230" stroke="#f0e7d8" stroke-width="1.2"/>'
    nodes = "".join(_primitive_svg(node) for node in visual.get("nodes", []))
    label = esc(scene.get("label", "教学图"))
    view_box = "0 0 420 640" if is_poster else ("0 0 420 300" if board == "blueprint" else "0 0 360 270")
    if is_poster:
        wide_background = blueprint_background(920, 420, poster=True, wide=True)
        wide_nodes = "".join(_primitive_svg(wide_node(node)) for node in visual.get("nodes", []))
        portrait_svg = f'<svg class="visual-svg-portrait" viewBox="{view_box}" role="img" aria-label="{label}">{background}{nodes}</svg>'
        wide_svg = f'<svg class="visual-svg-wide" viewBox="0 0 920 420" role="img" aria-label="{label}">{wide_background}{wide_nodes}</svg>'
        return portrait_svg + wide_svg
    return f'<svg viewBox="{view_box}" role="img" aria-label="{label}">{background}{nodes}</svg>'


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
        "captionMode": ir.get("render_contract", {}).get("caption_mode", "timing"),
        "layoutMode": ir.get("render_contract", {}).get("layout_mode", ""),
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
                "caption": s.get("caption", s.get("coach", s.get("keycard", ""))),
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
.visual svg.visual-svg-wide{display:none}
[data-visible-node]{opacity:0;transform-box:fill-box;transform-origin:center;will-change:opacity,transform,filter}.node-focus{filter:drop-shadow(0 0 9px rgba(255,210,127,.75))}
.coach-card{min-width:0;max-width:100%;overflow-wrap:anywhere;border-left:4px solid #ffd27f;background:#172434;border-radius:14px;padding:12px 13px;box-shadow:0 12px 30px rgba(0,0,0,.22);transition:opacity .18s,transform .18s}
.coach-card b{display:block;color:#ffd27f;font-size:15px;line-height:1.35;margin-bottom:6px}.coach-card span{display:block;color:#dbe6f1;font-size:14px;line-height:1.55;font-weight:800}
.caption-line{position:relative;z-index:4;min-height:0;max-height:48px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;padding:9px 12px;border-radius:13px;background:rgba(9,17,27,.84);border:1px solid rgba(207,224,240,.18);box-shadow:0 14px 32px rgba(0,0,0,.28);color:#eef6ff;font-size:14px;font-weight:900;line-height:1.35;text-align:center;backdrop-filter:blur(8px)}
.caption-line[data-speaker="S"]{color:#d7e9ff;border-color:rgba(96,165,250,.35)}
.center-play{display:none}
.lesson.started .center-play{display:none}
.top-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex:0 0 auto;flex-wrap:wrap}
.ask-ai{position:relative;z-index:7;min-width:52px;min-height:44px;border:1px solid rgba(255,210,127,.52);border-radius:999px;background:rgba(13,23,35,.82);color:#ffd27f;font-size:13px;font-weight:900;box-shadow:0 14px 32px rgba(0,0,0,.28);backdrop-filter:blur(8px)}
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
.challenge{flex:0 0 68px;min-width:68px;text-decoration:none;display:flex;align-items:center;justify-content:center;color:#8fa3b8;border-color:#2b3b50;background:#172434;font-size:13px;white-space:nowrap}
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
@media (min-width:1120px){
  .lesson{max-width:980px}.stage{min-height:420px}
  .scene.active{grid-template-columns:minmax(0,1fr) minmax(230px,320px);grid-template-rows:minmax(0,1fr) auto;align-items:center}
  .visual{grid-column:1;grid-row:1 / span 2}.caption-line{grid-column:2;grid-row:1;align-self:end}.coach-card{grid-column:2;grid-row:2;align-self:start}
  .visual{min-height:330px}
  .lesson.theater .scene.active{grid-template-columns:minmax(0,1fr) minmax(220px,300px)}
  .lesson.theater .visual svg{max-height:min(68dvh,620px)}.lesson.theater .caption-line{left:8%;right:8%;bottom:20px}
}
@media (max-width:1119px) and (min-height:521px){
  .lesson{padding-bottom:0}
  .player{position:relative;margin:10px -12px 0;transform:none;opacity:1;pointer-events:auto}
  .player-inner{max-width:none}.lesson.theater .player{position:fixed;margin:0}
}
@media (orientation:landscape) and (max-height:520px){
  .lesson{max-width:none;min-height:auto;padding:8px 10px 0}.subtitle{display:none}.top h1{font-size:20px}
  .stage{min-height:calc(100dvh - var(--player-h) - 54px)}
  .scene.active{padding:8px 12px;gap:8px}
  .visual{min-height:0}.visual svg{max-height:calc(100dvh - var(--player-h) - 72px)}
  .caption-line{min-height:0;max-height:42px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;padding:7px 9px;font-size:12px;line-height:1.35}.coach-card{padding:8px 10px}.coach-card b{font-size:13px}.coach-card span{font-size:12px;line-height:1.4}
  .player{position:relative;margin:10px -12px 0;transform:none;opacity:1;pointer-events:auto}
  .player-inner{max-width:none}.lesson.theater .player{position:fixed;margin:0}
  .lesson.theater .scene{padding:14px 18px}.lesson.theater .visual svg{max-height:58dvh}
}
@media(max-width:420px){
  .lesson{padding:12px 12px 0}
  .top h1{font-size:20px}.subtitle{margin:8px 0 10px;font-size:12px;line-height:1.35}
  .stage{min-height:410px}.scene.active{gap:8px;padding:10px 10px 18px}
  .visual{min-height:250px}.visual svg{max-height:258px}
  .coach-card{padding:8px 10px}.coach-card b{font-size:13px;line-height:1.25;margin-bottom:3px}.coach-card span{font-size:12px;line-height:1.35}
  .caption-line{min-height:0;padding:7px 9px;font-size:12px;line-height:1.35}.chapter{font-size:12px}
  .player{position:relative;margin:10px -12px 0;transform:none;opacity:1;pointer-events:auto}
  .player-inner{max-width:none}.lesson.theater .player{position:fixed;margin:0}
}
@media(max-width:370px){
  .stage{min-height:410px}.visual{min-height:235px}.visual svg{max-height:244px}
}
.lesson[data-caption-mode="visual_brief"] .subtitle{margin:6px 0 8px;font-size:12px;line-height:1.35;color:#8fa8bc}
.lesson[data-caption-mode="visual_brief"] .scene.active{gap:8px;padding:10px 10px 16px}
.lesson[data-caption-mode="visual_brief"] .visual{min-height:300px}
.lesson[data-caption-mode="visual_brief"] .caption-line{max-height:34px;padding:6px 9px;border-radius:10px;font-size:12px;line-height:1.3}
.lesson[data-caption-mode="visual_brief"] .coach-card{border-left-width:3px;border-radius:10px;padding:7px 10px}
.lesson[data-caption-mode="visual_brief"] .coach-card b{font-size:12px;line-height:1.2;margin-bottom:2px}.lesson[data-caption-mode="visual_brief"] .coach-card span{font-size:11.5px;line-height:1.28}
@media(max-width:420px){
  .lesson[data-caption-mode="visual_brief"] .stage{min-height:430px}
  .lesson[data-caption-mode="visual_brief"] .visual{min-height:286px}
  .lesson[data-caption-mode="visual_brief"] .visual svg{max-height:294px}
}
@media(min-width:1120px){
  .lesson[data-caption-mode="visual_brief"] .visual{min-height:380px}
  .lesson[data-caption-mode="visual_brief"] .visual svg{max-height:420px}
}
@media (orientation:landscape) and (max-height:520px){
  .lesson[data-caption-mode="visual_brief"] .stage{min-height:calc(100dvh - var(--player-h) - 54px)}
  .lesson[data-caption-mode="visual_brief"] .visual{min-height:0}
  .lesson[data-caption-mode="visual_brief"] .visual svg{max-height:calc(100dvh - var(--player-h) - 86px)}
}
.lesson.theater:not(.controls-visible) .scene.active{align-content:start;padding:clamp(12px,2.2vh,20px) 18px 18px}
.lesson.theater:not(.controls-visible) .visual{min-height:0;place-items:start center}
.lesson.theater:not(.controls-visible) .visual svg{max-height:min(60dvh,520px)}
@media(max-width:420px){
  .lesson.theater:not(.controls-visible) .scene.active{padding:12px 18px 18px}
  .lesson.theater:not(.controls-visible) .visual{min-height:0}
  .lesson.theater:not(.controls-visible) .visual svg{max-height:55dvh}
}
.lesson[data-layout-mode="blueprint_poster"] .subtitle{display:none}
.lesson[data-layout-mode="blueprint_poster"] .top{margin-bottom:8px}
.lesson[data-layout-mode="blueprint_poster"] .stage{height:calc(100dvh - var(--player-h) - 116px);min-height:430px;background:#071f2e}
.lesson[data-layout-mode="blueprint_poster"] .scene.active{position:relative;width:100%;height:100%;min-height:0;overflow:hidden;grid-template-columns:1fr;grid-template-rows:minmax(0,1fr);align-content:stretch;align-items:stretch;gap:0;padding:0}
.lesson[data-layout-mode="blueprint_poster"] .visual{grid-column:1;grid-row:1;min-height:0;overflow:hidden;width:100%;height:100%;align-self:stretch;place-items:center;padding:0}
.lesson[data-layout-mode="blueprint_poster"] .visual svg{width:auto;height:100%;max-width:100%;max-height:100%;object-fit:contain}
.lesson[data-layout-mode="blueprint_poster"] .caption-line{grid-column:1;grid-row:1;align-self:auto;justify-self:auto;position:absolute;z-index:6;left:50%;right:auto;bottom:76px;width:min(520px,calc(100% - 28px));transform:translateX(-50%);max-height:28px;padding:5px 9px;border-radius:999px;font-size:11.5px;line-height:1.25;background:rgba(6,19,30,.78)}
.lesson[data-layout-mode="blueprint_poster"] .coach-card{grid-column:1;grid-row:1;align-self:auto;justify-self:auto;position:absolute;z-index:5;left:14px;right:14px;bottom:14px;max-width:none;min-height:52px;padding:7px 11px 7px 13px;border-left-width:4px;border-radius:12px;background:rgba(6,24,36,.86)}
.lesson[data-layout-mode="blueprint_poster"] .coach-card b{display:inline;color:#ffb832;font-size:13px;line-height:1.2;margin:0 10px 0 0}
.lesson[data-layout-mode="blueprint_poster"] .coach-card span{display:inline;color:#d9efff;font-size:12px;line-height:1.25}
@media (orientation:landscape) and (max-height:520px){
  .lesson[data-layout-mode="blueprint_poster"] .stage{height:calc(100dvh - var(--player-h) - 86px);min-height:172px}
  .lesson[data-layout-mode="blueprint_poster"] .scene.active{grid-template-columns:1fr;grid-template-rows:1fr;padding:0;gap:0}
  .lesson[data-layout-mode="blueprint_poster"] .visual{grid-column:1;grid-row:1}
  .lesson[data-layout-mode="blueprint_poster"] .visual svg.visual-svg-portrait{display:none}
  .lesson[data-layout-mode="blueprint_poster"] .visual svg.visual-svg-wide{display:block}
  .lesson[data-layout-mode="blueprint_poster"] .visual svg{width:auto;height:100%;max-width:100%;max-height:100%}
  .lesson[data-layout-mode="blueprint_poster"] .caption-line{left:auto;right:18px;bottom:80px;width:min(300px,30vw);transform:none}
  .lesson[data-layout-mode="blueprint_poster"] .coach-card{left:auto;right:18px;bottom:18px;width:min(330px,32vw)}
  .lesson[data-layout-mode="blueprint_poster"] .coach-card span{display:none}
}
@media (min-width:1120px){
  .lesson[data-layout-mode="blueprint_poster"] .visual svg.visual-svg-portrait{display:none}
  .lesson[data-layout-mode="blueprint_poster"] .visual svg.visual-svg-wide{display:block}
}
.lesson.theater[data-layout-mode="blueprint_poster"] .stage{height:100dvh;min-height:100dvh}
.lesson.theater[data-layout-mode="blueprint_poster"]:not(.controls-visible) .scene.active{align-content:stretch;align-items:stretch;padding:0}
.lesson.theater[data-layout-mode="blueprint_poster"]:not(.controls-visible) .visual{place-items:stretch center}
.lesson.theater[data-layout-mode="blueprint_poster"]:not(.controls-visible) .visual svg{width:100%;height:100%;max-height:none}
.lesson.theater[data-layout-mode="blueprint_poster"]:not(.controls-visible) .caption-line,
.lesson.theater[data-layout-mode="blueprint_poster"]:not(.controls-visible) .coach-card{display:none}
"""
    return f"""<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(title)} · IR 预览</title><style>{css}</style></head>
<body>
<main class="lesson orientation-adaptive" data-card-id="{esc(ir['card_id'])}" data-caption-mode="{esc(student_data['captionMode'])}" data-layout-mode="{esc(student_data['layoutMode'])}" data-stage-shell="animation-ir-preview" data-animation-ir-preview="v0">
  <div class="top"><div><p class="kicker">{esc(kicker)}</p><h1>{esc(title)}</h1></div><div class="top-actions"><div class="time"><span id="cur">0:00</span> / <span id="tot">0:00</span></div><button class="ask-ai" id="askAi" type="button" data-ai-ask-entry="1" aria-label="带当前画面问 AI">问 AI</button></div></div>
  <p class="subtitle">{esc(ir['main_exam_action'])}</p>
  <div class="stage" id="stage" data-stage-shell="visual-stage" tabindex="0" aria-label="动画学习舞台，轻点显示或隐藏控制">
    {scenes_html}
    <div class="caption-line" id="captionLine" data-caption="1" data-speaker="T" role="status" aria-live="polite"></div>
    <div class="theater-hint" id="theaterHint" aria-hidden="true">轻点显示控制</div>
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
function annotatePrimitiveSteps(){{DATA.scenes.forEach(scene=>{{const sceneEl=scenes.find(el=>el.dataset.sceneId===scene.id);const visualNodes=Array.isArray(scene.visual?.nodes)?scene.visual.nodes:[];if(!sceneEl||!visualNodes.length)return;visualNodes.forEach(nodeDef=>{{const nodeEls=[...sceneEl.querySelectorAll('[data-visible-node]')].filter(el=>el.dataset.visibleNode===nodeDef.id);const stepDefs=Array.isArray(nodeDef.primitive_steps)?nodeDef.primitive_steps:[];if(!nodeEls.length||!stepDefs.length)return;nodeEls.forEach(nodeEl=>{{[...nodeEl.querySelectorAll('[data-primitive-step]')].forEach((stepEl,index)=>{{const declaredId=String(stepEl.dataset.primitiveStepId||'');const declaredIndex=Number(stepEl.dataset.primitiveStep);const stepDef=(declaredId&&stepDefs.find(step=>String(step.id||'')===declaredId))||stepDefs[Number.isFinite(declaredIndex)?declaredIndex:index];if(!stepDef)return;const domainObjects=Array.isArray(stepDef.domain_objects)?stepDef.domain_objects.join(' / '):String(stepDef.domain_object||'');stepEl.dataset.primitiveStepId=String(stepDef.id||'');stepEl.dataset.stepKind=String(stepDef.kind||'');stepEl.dataset.domainObject=domainObjects;stepEl.dataset.stepTarget=`${{nodeDef.id}}.${{stepDef.id}}`;stepEl.dataset.stepConsumed='0';}});}});}});}});}}
function primitiveStepTrace(active,activeEl,p){{if(!active||!activeEl)return[];const actions=(active.actions||[]).filter(action=>action.kind==='primitive_step');return actions.map(action=>{{const target=String(action.target||'');const step=activeEl.querySelector(`[data-step-target="${{target}}"]`);const start=Number(action.start??0),end=Number(action.end??start+.01);const activeNow=p>=start&&p<=end;return{{target,kind:step?.dataset.stepKind||'',domainObject:step?.dataset.domainObject||'',status:step?'consumed':'missing',active:step?activeNow:false,opacity:step?Number(getComputedStyle(step).opacity||0):0}};}});}}
function syncPlayerHeight(){{lesson.style.setProperty('--player-h',Math.ceil(player.getBoundingClientRect().height||132)+'px');}}
if('ResizeObserver' in window)new ResizeObserver(syncPlayerHeight).observe(player);
window.addEventListener('resize',syncPlayerHeight);
function scoreReady(t=Number(getTime()||scrubber.value||0)){{return t>=scoreStart-0.1||t>=DATA.totalSec-0.5;}}
function updateChallenge(t){{const ready=scoreReady(t);lesson.classList.toggle('challenge-ready',ready);challengeLinks.forEach(link=>{{link.classList.toggle('ready',ready);link.setAttribute('aria-disabled',ready?'false':'true');link.textContent=link.dataset.challengeCta==='inline'?(ready?'用采分句闯关 →':'先看采分句再闯关 →'):'闯关';}});}}
function showHint(){{if(!lesson.classList.contains('theater'))return;clearTimeout(hintTimer);lesson.classList.add('show-hint');hintTimer=setTimeout(()=>lesson.classList.remove('show-hint'),1400);}}
function setControls(visible=true,auto=true){{clearTimeout(hideTimer);lesson.classList.toggle('controls-visible',visible);if(visible)lesson.classList.remove('show-hint');else showHint();if(visible&&auto&&lesson.classList.contains('theater')&&!isPaused())hideTimer=setTimeout(()=>setControls(false,false),2600);}}
function setPlayState(isPlaying){{play.textContent=isPlaying?'⏸':'▶';play.setAttribute('aria-label',isPlaying?'暂停讲解':'播放讲解');play.setAttribute('aria-pressed',isPlaying?'true':'false');}}
function applyMotion(activeEl,active,t){{if(!activeEl)return;const dur=Math.max(.001,active.end-active.start),p=clamp01((t-active.start)/dur),nodes=[...activeEl.querySelectorAll('[data-visible-node]')],actions=active.actions||[];const cameraAction=actions.find(a=>a.kind==='camera')||{{verb:active.camera,start:0,end:.28}},cameraVerb=cameraAction.verb||active.camera;const cameraPush=cameraVerb==='push-in'||cameraVerb==='spotlight'||cameraVerb==='answer-paper'||cameraVerb==='trace';const cameraP=ease((p-(cameraAction.start||0))/Math.max(.05,(cameraAction.end||.28)-(cameraAction.start||0)));stage.style.setProperty('--camera-scale',String(1+(cameraPush?0.035*cameraP:0)));stage.style.setProperty('--camera-y',(cameraVerb==='pull-back'?String(-8*ease(p)):'0')+'px');nodes.forEach((node,i)=>{{const name=node.dataset.visibleNode||'';const reveal=actions.find(a=>a.kind==='reveal'&&a.target===name)||{{start:.04+i*.14,end:.22+i*.14}};const v=ease((p-reveal.start)/Math.max(.05,reveal.end-reveal.start));const highlighted=actions.some(a=>a.kind==='highlight'&&(a.target===name||name===a.target||name.includes(a.target))&&p>=a.start&&p<=a.end)||name===active.focus||name.includes(active.focus);const steps=[...node.querySelectorAll('[data-primitive-step]')];if(steps.length){{node.style.opacity=v>.01?'1':'0';node.style.transform=`translateY(${{(1-v)*8}}px) scale(${{0.98+v*0.02}})`;steps.forEach((step,si)=>{{const stepIndex=Number.isFinite(Number(step.dataset.primitiveStep))?Number(step.dataset.primitiveStep):si;const stepAction=actions.find(action=>action.kind==='primitive_step'&&action.target===step.dataset.stepTarget);const sv=stepAction?ease((p-Number(stepAction.start||0))/Math.max(.03,Number(stepAction.end||0)-Number(stepAction.start||0))):ease((v-stepIndex*.16)/.24);const activeStep=stepAction?p>=Number(stepAction.start||0)&&p<=Number(stepAction.end||0):sv>.05;step.dataset.stepConsumed=stepAction?'1':'fallback';step.dataset.stepActive=activeStep?'1':'0';step.style.opacity=String(sv);step.style.transformBox='fill-box';step.style.transformOrigin=step.dataset.trace==='1'?'left center':'center';step.style.transform=step.dataset.trace==='1'?`scaleX(${{sv}})`: `translateY(${{(1-sv)*7}}px) scale(${{0.97+sv*0.03}})`;}});}}else{{node.style.opacity=String(v);node.style.transform=`translateY(${{(1-v)*10}}px) scale(${{0.96+v*0.04}})`;}}node.classList.toggle('node-focus',highlighted);}});if(active.id!==lastScene){{scenes.forEach(scene=>{{if(scene!==activeEl)scene.querySelectorAll('[data-visible-node]').forEach(node=>{{node.style.opacity='0';node.style.transform='translateY(10px) scale(.96)';node.classList.remove('node-focus');node.querySelectorAll('[data-primitive-step]').forEach(step=>{{step.style.opacity='0';step.style.transform='translateY(7px) scale(.97)';step.dataset.stepActive='0';}});}});}});lastScene=active.id;}}}}
function paint(){{const t=Number(getTime()||scrubber.value||0);const active=sceneAt(t);const seg=segmentAt(t);lesson.classList.toggle('paused',isPaused());lesson.classList.toggle('playing',!isPaused());let activeEl=null;scenes.forEach(el=>{{const on=el.dataset.sceneId===active.id;el.classList.toggle('active',on);if(on)activeEl=el;}});const coach=activeEl?.querySelector('.coach-card');if(activeEl&&coach&&captionLine.parentElement!==activeEl)activeEl.insertBefore(captionLine,coach);const motionT=!lesson.classList.contains('started')&&t<0.05?active.start+Math.max(1,(active.end-active.start)*0.55):t;applyMotion(activeEl,active,motionT);chapters.forEach(el=>el.classList.toggle('on',t>=Number(el.dataset.t)&&Number(el.dataset.t)>=active.start-0.1));fill.style.width=(Math.min(t,DATA.totalSec)/DATA.totalSec*100)+'%';scrubber.value=String(Math.min(t,DATA.totalSec));cur.textContent=cur2.textContent=fmt(t);const visualBrief=DATA.captionMode==='visual_brief';const captionText=visualBrief?(active.caption||seg?.text||''):(seg?.text||'');captionLine.hidden=!captionText;captionLine.textContent=captionText;captionLine.dataset.speaker=visualBrief?'T':(seg?.speaker||'T');updateChallenge(t);syncPlayerHeight();}}
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
window.__IR_PLAYER__={{seek,paint,state:()=>{{const t=Number(getTime()||0),active=sceneAt(t),activeEl=scenes.find(el=>el.dataset.sceneId===active.id),dur=Math.max(.001,active.end-active.start),p=clamp01((t-active.start)/dur);return{{time:t,scene:active.id,hasAudio,playing:!isPaused(),primitiveTrace:primitiveStepTrace(active,activeEl,p)}};}}}};
annotatePrimitiveSteps();syncPlayerHeight();seek(0);setPlayState(false);setControls(false,false);
</script></body></html>"""


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: render_animation_ir_preview.py <animation_ir.v0.json>", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    out = src.with_name(src.name.replace(".animation_ir.v0.json", ".animation_ir_preview.html"))
    out.write_text(render(src), encoding="utf-8")
    print(f"✅ {out.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
