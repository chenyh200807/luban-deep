#!/usr/bin/env python3
"""Build OpenMAIC-style animation_ir.v0 previews from Deep Pack markdown.

This is intentionally a thin batch wrapper. Facts come from the pack markdown
and the 60-slot registry; visual stability comes from render_animation_ir_preview.py
and the animation_ir gates.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
WORKDIR = Path(__file__).resolve().parent
REGISTRY = ROOT / "docs/plan/鲁班移动端提分闭环/2026-06-19-luban-animation-pack-taxonomy-alignment-registry.md"
PACK_DIR = ROOT / "docs/原始数据/考点原料/成品"
REMOTION_SRC = WORKDIR / "remotion_demo/src"


@dataclass(frozen=True)
class RegistrySlot:
    slot: int
    pack_id: str
    student_title: str
    taxonomy_refs: list[str]
    status: str
    note: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_text(value: str) -> str:
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
    value = re.sub(r"kc:[A-Za-z0-9_\-:]+", "", value)
    value = re.sub(r"[🟢🔵🔴⚠️✅]", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("｜", "|").replace("\u3000", " ")
    value = re.sub(r"\s+", " ", value).strip(" |-")
    return value


def short(value: str, limit: int) -> str:
    value = clean_text(value)
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def compact_label(value: str, fallback: str) -> str:
    value = clean_text(value)
    value = re.split(r"[;；。,.，、（(]", value)[0].strip()
    if "→" in value:
        value = value.split("→", 1)[0].strip()
    if re.search(r"source|point_id|真题|锚|kc:", value, re.I) or len(value) < 2:
        value = fallback
    value = re.sub(r"(应|须|必须|不应|不得|一般|进行|采取|采用)", "", value)
    value = value.strip(":： ")
    return short(value or fallback, 8)


def compact_labels(values: list[str]) -> list[str]:
    fallbacks = ["对象", "条件", "依据", "采分", "错因", "结论"]
    labels: list[str] = []
    for idx, fallback in enumerate(fallbacks):
        labels.append(compact_label(values[idx] if idx < len(values) else "", fallback))
    return labels


def student_safe_card_id(prefix: str, pack_id: str) -> str:
    # Pack ids like E05 collide with internal error-code tokens in student-safe
    # gates. Keep the real pack_id in manifest/taxonomy metadata, but do not
    # expose E-code-shaped ids in the HTML preview surface.
    if re.fullmatch(r"E\d{2}", pack_id):
        return f"{prefix}_ECON{pack_id[1:]}"
    return f"{prefix}_{pack_id}"


def parse_registry() -> list[RegistrySlot]:
    rows: list[RegistrySlot] = []
    for line in read_text(REGISTRY).splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 6 or not cells[0].strip().isdigit():
            continue
        refs = re.findall(r"`([^`]+)`", cells[3])
        rows.append(
            RegistrySlot(
                slot=int(cells[0]),
                pack_id=clean_text(cells[1]),
                student_title=clean_text(cells[2]),
                taxonomy_refs=refs,
                status=clean_text(cells[4]),
                note=clean_text(cells[5]),
            )
        )
    return rows


def pack_markdown(slot: RegistrySlot) -> Path | None:
    direct = sorted(PACK_DIR.glob(f"{slot.pack_id}_*.md"))
    direct = [path for path in direct if "案例题作答层样板" not in path.name and "v4model" not in path.name]
    if direct:
        return direct[0]
    fuzzy = sorted(PACK_DIR.glob(f"*{slot.pack_id}*.md"))
    fuzzy = [path for path in fuzzy if "案例题作答层样板" not in path.name and "v4model" not in path.name]
    return fuzzy[0] if fuzzy else None


def extract_first_table_terms(markdown: str) -> list[str]:
    terms: list[str] = []
    in_r5 = False
    for raw in markdown.splitlines():
        line = raw.strip()
        if re.match(r"^##\s+5\b|^###\s+R5|R5\s*采分", line):
            in_r5 = True
            continue
        if in_r5 and line.startswith("## ") and "R5" not in line:
            break
        if in_r5 and line.startswith("|") and "---" not in line and "采分" not in line:
            cells = [clean_text(c) for c in line.strip("|").split("|")]
            for cell in cells[1:3]:
                if 4 <= len(cell) <= 44 and not re.search(r"锚|错因|source|point_id|真题", cell, re.I):
                    terms.append(cell)
                    break
        if len(terms) >= 6:
            break
    if len(terms) < 4:
        for line in markdown.splitlines():
            if "🟢" not in line:
                continue
            text = clean_text(re.sub(r"🟢|🔵|🔴", "", line))
            if 6 <= len(text) <= 52:
                terms.append(text)
            if len(terms) >= 6:
                break
    seen: set[str] = set()
    unique = []
    for term in terms:
        term = short(term, 28)
        if term and term not in seen:
            seen.add(term)
            unique.append(term)
    return unique[:6]


def extract_key_points(markdown: str, fallback_title: str) -> list[str]:
    points = extract_first_table_terms(markdown)
    if points:
        return points[:4]
    bullets = []
    for raw in markdown.splitlines():
        line = clean_text(raw)
        if line.startswith("- ") or line.startswith("1. "):
            bullets.append(short(line[2:], 36))
        if len(bullets) >= 4:
            break
    if bullets:
        return bullets[:4]
    return [f"{fallback_title}先判对象", "再判阈值/条件", "最后写采分句"]


def detect_archetype(title: str) -> str:
    if re.search(r"数值|参数|记忆|口诀|定义", title):
        return "value_memory_card"
    if re.search(r"网络|流水|挣值|计量|计价|进度款|索赔|费用|工期|计算", title):
        return "calculation_structure"
    if re.search(r"验收|论证|安全|事故|消防|动火|用电|起重|脚手架|支架|放行|等级|判断", title):
        return "decision_branch_reveal"
    if re.search(r"构造|节点|防水|幕墙|封堵|钢结构|连接|桩基|基坑|布置", title):
        return "section_or_spatial_reveal"
    if re.search(r"工序|顺序|施工|拆除|养护|抹灰|回填|治理", title):
        return "process_step_reveal"
    if re.search(r"对比|正误|规范|非规范|通病|错误做法|正确做法", title):
        return "contrast_reveal"
    return "scoring_diagnosis_reveal"


def scene_times(count: int, total: float = 138.0) -> list[tuple[float, float]]:
    unit = total / count
    return [(round(i * unit, 3), round((i + 1) * unit, 3)) for i in range(count)]


def node(kind: str, node_id: str, text: str, *, x: float, y: float, w: float = 176, h: float = 46, tone: str = "blue", subtext: str = "") -> dict[str, Any]:
    item: dict[str, Any] = {"id": node_id, "kind": kind, "text": short(text, 34), "x": x, "y": y, "w": w, "h": h, "tone": tone}
    if subtext:
        item["subtext"] = short(subtext, 32)
    return item


ARCHETYPE_VISUAL_REQUIRED: dict[str, list[str]] = {
    "process_step_reveal": ["process_flow"],
    "section_or_spatial_reveal": ["layer_stack", "roof_section"],
    "calculation_structure": ["network_graph", "formula_chain"],
    "decision_branch_reveal": ["decision_tree"],
    "contrast_reveal": ["contrast_pair"],
    "scoring_diagnosis_reveal": ["answer_scan"],
    "value_memory_card": ["memory_table"],
}


def archetype_visual_required(archetype: str) -> list[str]:
    return ARCHETYPE_VISUAL_REQUIRED.get(archetype, ["answer_scan"])


def diagram_node(kind: str, node_id: str, *, text: str = "", labels: list[str] | None = None, x: float = 30, y: float = 42, w: float = 300, h: float = 178, tone: str = "blue") -> dict[str, Any]:
    item: dict[str, Any] = {"id": node_id, "kind": kind, "text": short(text, 24), "x": x, "y": y, "w": w, "h": h, "tone": tone}
    if labels:
        item["labels"] = [short(label, 8) for label in labels[:6]]
    return item


def archetype_map_node(labels: list[str], archetype: str) -> dict[str, Any]:
    if archetype == "process_step_reveal":
        return diagram_node("process_flow", "prototype_map", text="流程先后", labels=labels, tone="success")
    if archetype == "section_or_spatial_reveal":
        return diagram_node("layer_stack", "prototype_map", text="构造层次", labels=labels, tone="blue")
    if archetype == "calculation_structure":
        return diagram_node("network_graph", "prototype_map", text="图上推演", labels=labels, tone="blue")
    if archetype == "decision_branch_reveal":
        return diagram_node("decision_tree", "prototype_map", text="判断树", labels=labels, tone="success")
    if archetype == "contrast_reveal":
        return diagram_node("contrast_pair", "prototype_map", text="正误对照", labels=labels, tone="danger")
    if archetype == "value_memory_card":
        return diagram_node("memory_table", "prototype_map", text="数值辨析", labels=labels, tone="amber")
    return diagram_node("answer_scan", "prototype_map", text="采分诊断", labels=labels, tone="success")


def archetype_rule_node(labels: list[str], archetype: str) -> dict[str, Any]:
    if archetype == "process_step_reveal":
        return diagram_node("process_flow", "rule_model", text="不能跳步", labels=labels, tone="amber")
    if archetype == "section_or_spatial_reveal":
        return diagram_node("layer_stack", "rule_model", text="先看层位", labels=labels, tone="success")
    if archetype == "calculation_structure":
        return diagram_node("formula_chain", "rule_model", text="算式口径", labels=labels, tone="amber")
    if archetype == "decision_branch_reveal":
        return diagram_node("decision_tree", "rule_model", text="对象→条件→结论", labels=labels, tone="success")
    if archetype == "contrast_reveal":
        return diagram_node("contrast_pair", "rule_model", text="红错绿对", labels=labels, tone="success")
    if archetype == "value_memory_card":
        return diagram_node("memory_table", "rule_model", text="数值别混", labels=labels, tone="amber")
    return diagram_node("answer_scan", "rule_model", text="命中/漏点", labels=labels, tone="success")


def archetype_trap_node(labels: list[str], archetype: str) -> dict[str, Any]:
    if archetype == "process_step_reveal":
        return diagram_node("process_flow", "trap_visual", text="错步会返工", labels=list(reversed(labels[:4])), tone="danger")
    if archetype == "section_or_spatial_reveal":
        return diagram_node("layer_stack", "trap_visual", text="错层就漏分", labels=labels, tone="danger")
    if archetype == "calculation_structure":
        return diagram_node("network_graph", "trap_visual", text="别只看单项", labels=labels, tone="danger")
    if archetype == "decision_branch_reveal":
        return diagram_node("decision_tree", "trap_visual", text="漏一道门", labels=labels, tone="danger")
    if archetype == "contrast_reveal":
        return diagram_node("contrast_pair", "trap_visual", text="错因定位", labels=labels, tone="danger")
    if archetype == "value_memory_card":
        return diagram_node("memory_table", "trap_visual", text="相近参数", labels=labels, tone="danger")
    return diagram_node("answer_scan", "trap_visual", text="只写结论", labels=labels, tone="danger")


def visual_for_scene(scene_id: str, title: str, terms: list[str], archetype: str) -> dict[str, Any]:
    t = terms + ["判对象", "判条件", "写依据", "写采分句"]
    if scene_id == "hook":
        return {
            "board": "warm_grid",
            "nodes": [
                node("pill", "wrong_start", "错觉:先背答案", x=54, y=68, w=252, h=48, tone="danger"),
                node("pill", "score_goal", "目标:写成采分闭环", x=58, y=142, w=244, h=56, tone="success", subtext="对象 → 条件 → 依据"),
            ],
        }
    if scene_id == "map":
        return {
            "board": "warm_grid",
            "nodes": [archetype_map_node(t, archetype)],
        }
    if scene_id == "rule":
        return {
            "board": "warm_grid",
            "nodes": [archetype_rule_node(t, archetype)],
        }
    if scene_id == "trap":
        return {
            "board": "warm_grid",
            "nodes": [archetype_trap_node(t, archetype)],
        }
    if scene_id == "score":
        return {
            "board": "paper",
            "nodes": [
                node("answer_box", "score_1", t[0], x=54, y=94, w=252, h=38, tone="success"),
                node("answer_box", "score_2", t[1], x=54, y=142, w=252, h=38, tone="blue"),
                node("answer_box", "score_3", t[2], x=54, y=190, w=252, h=38, tone="amber"),
            ],
        }
    if scene_id == "qa":
        return {
            "board": "warm_grid",
            "nodes": [
                node("dialogue_box", "student_q1", "学生问:先写哪个?", x=42, y=58, w=276, h=44, tone="blue"),
                node("dialogue_box", "student_q2", "学生问:少一句扣分吗?", x=42, y=114, w=276, h=44, tone="amber"),
                node("dialogue_box", "teacher_a", "老师:按采分链补齐", x=42, y=170, w=276, h=46, tone="success"),
            ],
        }
    return {
        "board": "closing",
        "nodes": [
            node("closing_text", "closing_sentence", "带走一句话", x=0, y=0, tone="success", subtext=f"{short(title, 12)}: 对象→条件→依据"),
            node("challenge_button", "challenge_cta", "开始闯关", x=90, y=166, w=180, h=44, tone="amber"),
        ],
    }


def actions(visible: list[str], focus: str) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = [{"kind": "camera", "verb": "push-in", "target": focus, "start": 0, "end": 0.24}]
    for index, node_id in enumerate(visible):
        start = round(0.04 + index * 0.15, 3)
        queue.append({"kind": "reveal", "target": node_id, "start": start, "end": round(start + 0.16, 3)})
    queue.append({"kind": "highlight", "target": focus, "start": 0.3, "end": 0.9})
    return queue


def build_ir(slot: RegistrySlot, md_path: Path, prefix: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    markdown = read_text(md_path)
    title = slot.student_title
    terms = extract_key_points(markdown, title)
    labels = compact_labels(terms)
    archetype = detect_archetype(title)
    card_id = student_safe_card_id(prefix, slot.pack_id)
    scene_specs = [
        ("hook", "先避坑", "wrong_start", "考场先别急着写术语", f"注意哈，这类题别先背答案，先判它要哪条采分链。"),
        ("map", "看结构", "prototype_map", "先看它属于哪类图", f"先把它画成图：{labels[0]}、{labels[1]}、{labels[2]}、{labels[3]}。"),
        ("rule", "判边界", "rule_model", "用图走一遍判断动作", "拿分动作不是背定义，是顺着图把对象、条件、依据走完。"),
        ("trap", "错法", "trap_visual", "先拆常见错法", "只写结果、不写依据，最容易漏采分点。"),
        ("score", "采分", "score_1", "把答案写成采分句", f"答题纸按三段写：{labels[0]}、{labels[1]}、{labels[2]}。"),
        ("qa", "三问", "student_q1", "三问集中放后面", "学生常问三个问题：先写哪个、少一句扣不扣分、能不能只写结论。都回到采分链。"),
        ("closing_challenge", "闯关", "closing_sentence", "收束到闯关", "最后收束一句哈：别背散点，把它写成对象、条件、依据三段式。现在开始闯关。"),
    ]
    times = scene_times(len(scene_specs))
    visual_library: dict[str, Any] = {}
    scenes: list[dict[str, Any]] = []
    chapters: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    for i, ((scene_id, label, focus, keycard, coach), (start, end)) in enumerate(zip(scene_specs, times)):
        visual = visual_for_scene(scene_id, title, labels, archetype)
        visual_library[scene_id] = visual
        visible_nodes = [item["id"] for item in visual["nodes"][:4]]
        scene = {
            "id": scene_id,
            "label": label,
            "start_sec": start,
            "end_sec": end,
            "scene": f"{archetype}_{scene_id}",
            "focus": focus,
            "enter": ["scene.fade_in", f"{focus}.reveal"],
            "hold": [f"{focus}.spotlight"],
            "exit": ["scene.fade_out"],
            "layout": {"portrait": "centered_board", "landscape": "stage_left_coach_right", "theater": "clean_board"},
            "camera": {"verb": "push-in" if i < 5 else "spotlight", "target": focus, "duration_sec": 0.45},
            "visible_nodes": visible_nodes,
            "actions": actions(visible_nodes, focus),
            "keycard": keycard,
            "coach": coach,
        }
        scenes.append(scene)
        chapters.append({"id": scene_id, "label": label, "start_sec": start})
        # Preview gates sample the whole scene, not just the narration onset.
        # Keep a safe subtitle alive for the full beat until real TTS timing is
        # generated, otherwise the card passes IR but fails mobile readability.
        segments.append({"startSec": start + 0.05, "durSec": max(1.0, end - start - 0.1), "speaker": "T", "kind": "coach", "text": coach})
        if scene_id == "qa":
            for offset, q in enumerate(["老师，先写哪个动作？", "少一个判断依据会丢分吗？", "我能不能只写结论？"]):
                segments.append({"startSec": start + 3.8 + offset * 3.0, "durSec": 2.4, "speaker": "S", "kind": "qa", "text": q})
    duration = times[-1][1]
    ir = {
        "schema_version": "luban_animation_ir.v0",
        "ir_id": f"{card_id}_animation_ir_v0",
        "card_id": card_id,
        "display": {"kicker": f"鲁班深母题 · Slot {slot.slot}", "title": title},
        "main_exam_action": f"把「{title}」写成采分链：先判对象，再判条件，最后写判断依据。",
        "teaching_spine": {
            "source_pack": str(md_path.relative_to(ROOT)),
            "archetype": archetype,
            "warm_correction": f"{title} 不是背散点，而是把题干转成可得分的判断链。",
        },
        "source_refs": {"pack_markdown": str(md_path.relative_to(ROOT)), "timing": f"{card_id}.lesson.timing.json"},
            "render_contract": {
                "renderer": "render_animation_ir_preview.py",
                "html_preview": f"{card_id}.animation_ir_preview.html",
                "remotion_renderer": f"remotion_demo/src/{card_id}AnimationIrPreview.tsx",
                "remotion_composition": f"{card_id}AnimationIrPreview",
                "practice_href": f"{card_id}.practice.html",
                "max_visible_nodes": 4,
                "archetype_visual_required": archetype_visual_required(archetype),
                "challenge_unlock_sec": scenes[4]["start_sec"],
                "one_active_scene": True,
            "one_active_keycard": True,
            "theater_requires_challenge_cta": True,
            "ai_ask_required": True,
        },
        "taxonomy_alignment": {
            "priority_slot": slot.slot,
            "pack_id": slot.pack_id,
            "status": slot.status,
            "canonical_taxonomy_refs": slot.taxonomy_refs,
            "note": slot.note,
        },
        "ai_context": {
            "context_id": card_id,
            "title": title,
            "main_exam_action": f"把「{title}」写成采分链：先判对象，再判条件，最后写判断依据。",
            "safe_summary": f"{title} 的学习重点是：{'; '.join(terms[:4])}。",
            "key_points": terms[:4],
            "handoff_mode": "context_id_plus_current_scene",
            "api_base": "https://test2.yousenjiaoyu.com",
        },
        "chapters": chapters,
        "scenes": scenes,
        "visual_library": visual_library,
    }
    timing = {
        "audio": "",
        "totalSec": duration,
        "segments": segments,
        "generated_from": f"{card_id}.animation_ir.v0.json",
    }
    source_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return ir, timing, source_hash


def write_practice(card_id: str, slot: RegistrySlot, terms: list[str]) -> Path:
    terms = terms + ["判断依据", "采分句"]
    out = WORKDIR / f"{card_id}.practice.html"
    title = html.escape(slot.student_title)
    options = "\n".join(
        f'<button class="option" type="button"><b>{html.escape(label)}</b><span>路径 + 判断依据</span></button>'
        for label in terms[:4]
    )
    out.write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>{title} · 闯关</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#eef5fb;color:#132033;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}}main{{max-width:520px;margin:0 auto;min-height:100dvh;padding:18px 14px 28px}}.top{{display:flex;justify-content:space-between;gap:12px;align-items:center}}a{{color:#176b7a;font-weight:900;text-decoration:none}}h1{{font-size:23px;line-height:1.2;margin:10px 0 12px}}.progress{{height:7px;border-radius:99px;background:#d8e5f0;overflow:hidden;margin:14px 0 18px}}.progress i{{display:block;width:20%;height:100%;background:#ff7a1a}}.card{{background:#fff;border:1px solid #cdddeb;border-radius:20px;padding:15px;box-shadow:0 16px 40px rgba(30,58,87,.12)}}.diagram{{background:#fffdf7;border:3px solid #eadfcb;border-radius:18px;padding:14px;margin-bottom:16px}}.flow{{display:flex;align-items:center;gap:8px;justify-content:space-between}}.dot{{flex:1;min-height:58px;border:3px solid #c9d9e8;border-radius:999px;display:grid;place-items:center;text-align:center;font-size:13px;font-weight:900;padding:8px;line-height:1.2}}.dot.hot{{border-color:#ff7a1a;color:#b45309;background:#fff7ed}}.stem{{font-size:18px;line-height:1.45;font-weight:900;margin:0 0 14px}}.options{{display:grid;gap:10px}}.option{{width:100%;min-height:58px;text-align:left;border:1px solid #d6e2ed;border-radius:14px;background:#fff;padding:10px 12px;color:#172437}}.option b{{display:block;font-size:16px;line-height:1.25}}.option span{{display:block;color:#60758c;font-size:12px;font-weight:800;margin-top:4px}}.bottom{{position:sticky;bottom:0;display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:14px 0;background:linear-gradient(180deg,rgba(238,245,251,0),#eef5fb 35%)}}.bottom button{{min-height:52px;border-radius:14px;border:1px solid #cdddeb;background:#fff;font-size:16px;font-weight:900;color:#6a7d91}}.bottom .primary{{background:#176b7a;color:white;border-color:#176b7a}}@media(orientation:landscape){{main{{max-width:920px}}.card{{display:grid;grid-template-columns:minmax(280px,1fr) minmax(320px,1fr);gap:18px;align-items:center}}.diagram{{margin-bottom:0}}}}</style></head>
<body><main><div class="top"><a href="{card_id}.animation_ir_preview.html">返回讲解</a><b>鲁班深母题 · 独立闯关</b></div><h1>{title}</h1><div class="progress"><i></i></div><section class="card"><div class="diagram"><div class="flow"><div class="dot">{html.escape(terms[0])}</div><div class="dot hot">{html.escape(terms[1])}</div><div class="dot">{html.escape(terms[2])}</div></div></div><div><p class="stem">第 1/5 问：这份学生答最可能漏掉哪一段采分动作？</p><div class="options">{options}</div></div></section><div class="bottom"><button type="button">上一题</button><button class="primary" type="button">先作答</button></div></main></body></html>""",
        encoding="utf-8",
    )
    return out


def write_remotion_wrapper(card_id: str) -> Path:
    path = REMOTION_SRC / f"{card_id}AnimationIrPreview.tsx"
    path.write_text(
        f"""import React from "react";
import ir from "../../{card_id}.animation_ir.v0.json";
import timing from "../../{card_id}.lesson.timing.json";
import {{
  AnimationIr,
  AnimationIrRenderer,
  animationIrDurationFrames,
}} from "./AnimationIrRenderer";

const animationIr = ir as AnimationIr;

export const {card_id}_IR_FPS = 30;
export const {card_id}_IR_DURATION_FRAMES = animationIrDurationFrames(animationIr, {card_id}_IR_FPS);

export const {card_id}AnimationIrPreview: React.FC = () => {{
  return <AnimationIrRenderer ir={{animationIr}} timing={{timing}} />;
}};
""",
        encoding="utf-8",
    )
    return path


def render_preview(ir_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(WORKDIR / "render_animation_ir_preview.py"), str(ir_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def run_gate(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    return {"cmd": cmd, "returncode": proc.returncode, "stdout_tail": proc.stdout[-4000:], "stderr_tail": proc.stderr[-4000:]}


def write_index(generated: list[dict[str, Any]], prefix: str) -> Path:
    rows = "\n".join(
        f"<tr><td>{item['slot']}</td><td>{html.escape(item['pack_id'])}</td><td>{html.escape(item['title'])}</td><td>{html.escape(item['status'])}</td><td><a href='{item['preview']}'>讲解</a> · <a href='{item['practice']}'>闯关</a></td><td>{html.escape(item.get('gate','pending'))}</td></tr>"
        for item in generated
    )
    out = WORKDIR / f"{prefix}_index.html"
    out.write_text(
        f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{prefix} 动画量产索引</title>
<style>body{{margin:0;background:#eef5fb;color:#152336;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}}main{{max-width:1100px;margin:0 auto;padding:24px 16px}}h1{{font-size:28px}}p{{color:#60758c;font-weight:800}}table{{width:100%;border-collapse:collapse;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 18px 50px rgba(30,58,87,.12)}}th,td{{padding:11px 12px;border-bottom:1px solid #e2edf5;text-align:left;vertical-align:top}}th{{background:#176b7a;color:white}}a{{color:#176b7a;font-weight:900}}</style></head><body><main><h1>{prefix} 教学动画量产索引</h1><p>OpenMAIC-style animation_ir.v0 首版批量预览；coarse_review 只作内部验证，不进学员默认入口。</p><table><thead><tr><th>Slot</th><th>Pack</th><th>标题</th><th>状态</th><th>入口</th><th>Gate</th></tr></thead><tbody>{rows}</tbody></table></main></body></html>""",
        encoding="utf-8",
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slots", default="1-40", help="slot range, e.g. 1-40")
    parser.add_argument("--prefix", default="P40")
    parser.add_argument("--validate-contract", action="store_true")
    parser.add_argument("--validate-preview", action="store_true")
    args = parser.parse_args()

    start, end = [int(part) for part in args.slots.split("-", 1)]
    slots = [slot for slot in parse_registry() if start <= slot.slot <= end]
    manifest: dict[str, Any] = {"schema_version": "luban_animation_ir_batch_manifest.v0", "prefix": args.prefix, "slots": args.slots, "generated": [], "blocked": []}
    for slot in slots:
        md_path = pack_markdown(slot)
        if not md_path:
            manifest["blocked"].append({"slot": slot.slot, "pack_id": slot.pack_id, "reason": "missing成品pack.md"})
            continue
        card_id = student_safe_card_id(args.prefix, slot.pack_id)
        ir, timing, source_hash = build_ir(slot, md_path, args.prefix)
        terms = ir["ai_context"]["key_points"]
        ir_path = WORKDIR / f"{card_id}.animation_ir.v0.json"
        timing_path = WORKDIR / f"{card_id}.lesson.timing.json"
        write_json(ir_path, ir)
        write_json(timing_path, timing)
        practice_path = write_practice(card_id, slot, terms)
        remotion_path = write_remotion_wrapper(card_id)
        render_result = render_preview(ir_path)
        gate_status = "rendered" if render_result.returncode == 0 else "render_failed"
        gates: dict[str, Any] = {"render": {"returncode": render_result.returncode, "stdout": render_result.stdout[-1000:], "stderr": render_result.stderr[-1000:]}}
        if args.validate_contract:
            gates["contract"] = run_gate(["node", str(WORKDIR / "validate_animation_ir_contract.mjs"), str(ir_path)])
            if gates["contract"]["returncode"] != 0:
                gate_status = "contract_failed"
        if args.validate_preview and gate_status != "contract_failed":
            html_path = WORKDIR / f"{card_id}.animation_ir_preview.html"
            gates["preview"] = run_gate(["node", str(WORKDIR / "validate_animation_ir_preview.mjs"), str(ir_path), str(html_path)])
            gate_status = "pass" if gates["preview"]["returncode"] == 0 else "preview_failed"
        manifest["generated"].append(
            {
                "slot": slot.slot,
                "pack_id": slot.pack_id,
                "card_id": card_id,
                "title": slot.student_title,
                "status": slot.status,
                "prototype": ir["teaching_spine"]["archetype"],
                "visual_required_kinds": ir["render_contract"]["archetype_visual_required"],
                "source_pack": str(md_path.relative_to(ROOT)),
                "source_sha256": source_hash,
                "ir": ir_path.name,
                "timing": timing_path.name,
                "preview": f"{card_id}.animation_ir_preview.html",
                "practice": practice_path.name,
                "remotion_wrapper": str(remotion_path.relative_to(WORKDIR)),
                "gate": gate_status,
                "gates": gates,
            }
        )
    index_path = write_index(manifest["generated"], args.prefix)
    manifest["index"] = index_path.name
    manifest_path = WORKDIR / f"{args.prefix}_animation_ir_batch_manifest.json"
    write_json(manifest_path, manifest)
    print(f"generated={len(manifest['generated'])} blocked={len(manifest['blocked'])}")
    print(f"manifest={manifest_path}")
    print(f"index={index_path}")
    if manifest["blocked"]:
        print("blocked:")
        for item in manifest["blocked"]:
            print(f"- slot {item['slot']} {item['pack_id']}: {item['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
