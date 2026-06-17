#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path
from typing import Any


DEFAULT_PACKET = Path("artifacts/luban_human_validation_v1/po_slice_20260603_heldout/agentic_grading_packet.json")
DEFAULT_OUTPUT = Path("artifacts/luban_human_validation_v1/po_slice_20260603_heldout/阅卷审阅册_老师用.md")
DEFAULT_PUBLIC_SLICE_NAME = "held-out validation slice 20260603"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _clean(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").strip()


def _wrap_block(value: Any) -> str:
    text = _clean(value)
    return "\n".join(textwrap.wrap(text, width=88, replace_whitespace=False, drop_whitespace=False)) if text else ""


def _case_max_score(tasks: list[dict[str, Any]]) -> float:
    by_point: dict[str, float] = {}
    for task in tasks:
        for point in task.get("scoring_points") or []:
            by_point[str(point.get("point_id"))] = float(point.get("max_score") or 0)
    return round(sum(by_point.values()), 4)


def _points_markdown(points: list[dict[str, Any]]) -> str:
    lines = [
        "| 采分点 | 满分 | 判定(hit/partial/miss) | 得分 | 备注 |",
        "|---|---:|---|---:|---|",
    ]
    for point in points:
        lines.append(f"| {point.get('point_id')} | {point.get('max_score')} |  |  |  |")
    return "\n".join(lines)


def _point_reference(points: list[dict[str, Any]]) -> str:
    lines = []
    for point in points:
        parts = [
            f"- `{point.get('point_id')}` 满分 `{point.get('max_score')}`",
            f"  - 采分点：{_clean(point.get('label'))}",
        ]
        if point.get("official_basis"):
            parts.append(f"  - 官方依据：{_clean(point.get('official_basis'))}")
        if point.get("list_rule"):
            parts.append(f"  - 列举规则：{_clean(point.get('list_rule'))}")
        if point.get("penalty_rule"):
            parts.append(f"  - 罚则：{_clean(point.get('penalty_rule'))}")
        lines.extend(parts)
    return "\n".join(lines)


def _group_tasks(tasks: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        grouped.setdefault(str(task.get("case_id")), []).append(task)
    return [(case_id, grouped[case_id]) for case_id in sorted(grouped)]


def build_review_book(
    *,
    packet_path: Path = DEFAULT_PACKET,
    output_path: Path = DEFAULT_OUTPUT,
    public_slice_name: str = DEFAULT_PUBLIC_SLICE_NAME,
) -> dict[str, Any]:
    packet = _read_json(packet_path)
    tasks = list(packet.get("tasks") or [])
    grouped = _group_tasks(tasks)
    lines = [
        "# 鲁班一建建筑实务 held-out 阅卷审阅册（老师用）",
        "",
        f"Slice: `{public_slice_name}`",
        "",
        "## 填写规则",
        "",
        "- 只按题干、标准答案、采分点、学生答案判分。",
        "- 不看任何模型输出或内部对照结果。",
        "- `human_hit` 只填 `hit` / `partial` / `miss`。",
        "- `human_score` 范围为 `0..满分`。",
        "- 踩字口径：教材/规范术语原文优先；近义、大白话、口号按采分点要求保守处理。",
        "",
    ]
    guideline = _clean(packet.get("grading_guideline"))
    if guideline:
        lines.extend(["## 总评分口径", "", guideline, ""])

    point_row_count = 0
    for index, (case_id, case_tasks) in enumerate(grouped, start=1):
        first = case_tasks[0]
        points = list(first.get("scoring_points") or [])
        point_row_count += len(points) * len(case_tasks)
        lines.extend(
            [
                f"# {index}. {case_id} （满分 {_case_max_score(case_tasks)} 分）",
                "",
                "## 题干",
                "",
                _wrap_block(first.get("stem")),
                "",
                "## 标准答案",
                "",
                _wrap_block(first.get("official_answer")),
                "",
                "## 采分点",
                "",
                _point_reference(points),
                "",
            ]
        )
        for task in sorted(case_tasks, key=lambda row: str(row.get("student_id"))):
            lines.extend(
                [
                    f"### 学生 {task.get('student_id')}",
                    "",
                    "#### 学生作答",
                    "",
                    _wrap_block(task.get("student_answer")),
                    "",
                    f"**给 {task.get('student_id')} 打分**:",
                    "",
                    _points_markdown(points),
                    "",
                ]
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {
        "output": str(output_path),
        "slice_id": packet.get("slice_id"),
        "case_count": len(grouped),
        "task_count": len(tasks),
        "point_row_count": point_row_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a blind held-out teacher review book.")
    parser.add_argument("--packet", default=str(DEFAULT_PACKET))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--public-slice-name", default=DEFAULT_PUBLIC_SLICE_NAME)
    args = parser.parse_args()
    result = build_review_book(
        packet_path=Path(args.packet),
        output_path=Path(args.output),
        public_slice_name=args.public_slice_name,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
