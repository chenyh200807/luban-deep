from __future__ import annotations

import re
from typing import Any, Iterable

from deeptutor.services.first_run.manifest import load_first_run_manifest
from deeptutor.services.luban_lesson import list_lesson_catalog


_MODULE_LABELS = {
    "assessment": "微信小程序 · 测评",
    "chat": "微信小程序 · 问鲁班",
    "first_run": "微信小程序 · 首次体验",
    "history": "微信小程序 · 历史记录",
    "learning": "微信小程序 · 学习首页",
    "learning_report": "微信小程序 · 学情",
    "notebook": "微信小程序 · 笔记本",
    "practice": "微信小程序 · 练习",
    "profile": "微信小程序 · 我的",
}
_MICROLESSON_ID = re.compile(r"^(?P<pack>.+):tp:(?P<episode>\d+)$")


def _content_indexes() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """从现有 authority 构建只读名称索引；失败时宁缺毋滥，并允许下次请求重试。"""
    pack_labels: dict[str, str] = {}
    episode_labels: dict[str, str] = {}
    question_labels: dict[str, str] = {}
    try:
        lessons, points = list_lesson_catalog()
        pack_labels = {
            str(item.get("pack_id") or ""): str(item.get("title") or "").strip()
            for item in lessons
            if str(item.get("pack_id") or "").strip()
        }
        for point in points:
            pack_id = str(point.get("pack_id") or "").strip()
            episode = int(point.get("episode_index") or 0)
            title = str(point.get("title") or pack_labels.get(pack_id) or "").strip()
            episode_label = str(point.get("episode_label") or "").strip()
            if pack_id and episode and title:
                episode_labels[f"{pack_id}:tp:{episode}"] = " · ".join(
                    part for part in (title, episode_label) if part
                )
    except Exception:
        pass
    try:
        questions = list(load_first_run_manifest().get("questions") or [])
        question_labels = {
            str(item.get("question_id") or ""): str(item.get("concept_label") or "").strip()
            for item in questions
            if str(item.get("question_id") or "").strip()
        }
    except Exception:
        pass
    return pack_labels, episode_labels, question_labels


def _display_for_row(
    row: dict[str, Any],
    *,
    pack_labels: dict[str, str],
    episode_labels: dict[str, str],
    question_labels: dict[str, str],
) -> tuple[str, str, str]:
    key = str(row.get("key") or "").strip()
    object_type = str(row.get("object_type") or "").strip()
    if key in _MODULE_LABELS:
        return _MODULE_LABELS[key], "页面访问与操作合计", "module"
    if object_type == "microlesson" or _MICROLESSON_ID.fullmatch(key):
        label = episode_labels.get(key)
        return (
            f"微课｜{label}" if label else f"未识别微课（原始 ID：{key}）",
            "微信小程序 · 学习 · 视频/微课",
            "video",
        )
    if object_type == "station" or key in pack_labels:
        title = pack_labels.get(key)
        return (
            f"课程站｜{title}" if title else f"未识别课程站（原始 ID：{key}）",
            "微信小程序 · 学习 · 课程站",
            "station",
        )
    question_id = key.removeprefix("question:")
    if question_id in question_labels:
        return (
            f"首次体验题｜{question_labels[question_id]}",
            "微信小程序 · 首次体验 · 答题",
            "question",
        )
    if key.startswith("script:first-run"):
        return "首次体验答题流程", "微信小程序 · 首次体验", "flow"
    return f"未识别内容（原始 ID：{key or '空'}）", "微信小程序 · 具体内容待补充映射", "unknown"


def project_product_behavior_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """给行为聚合添加可读投影，不改写原始 key，不创建第二份行为事实。"""
    pack_labels, episode_labels, question_labels = _content_indexes()
    projected: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        label, context, kind = _display_for_row(
            row,
            pack_labels=pack_labels,
            episode_labels=episode_labels,
            question_labels=question_labels,
        )
        row.update(
            display_label=label,
            display_context=context,
            content_kind=kind,
        )
        projected.append(row)
    return projected


__all__ = ["project_product_behavior_rows"]
