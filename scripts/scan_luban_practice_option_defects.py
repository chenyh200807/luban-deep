#!/usr/bin/env python3
"""扫描鲁班随堂练选择题的可猜性缺陷(选项长度偏置/正确项存储位偏置/口语化破绽词)。

背景(2026-07-18 owner 指令):随堂练单选题存在系统性可猜缺陷——
84% 的题正确项是最长选项、100% 的题正确项存储在第 0 位。本扫描器是
该修复战役的机械门禁:修复前后各跑一次,给出逐题指标与总量分布。

只读工具:从 tracked 源 HTML 逐 surface 编译(与发布器同一 compile 路径),
不写任何权威产物。输出逐包 JSON(供改写 agent 消费)+ 汇总表。

判定口径:
  * longest_correct   —— 正确项字数严格最大(含并列不算);
  * pos0_correct      —— 正确项在源 opts 数组第 0 位;
  * casual_distractor —— 干扰项含口语化破绽词(就够了/看着定/都行/随便/无所谓/
                          怎么方便怎么);正确项永远正式语体,这些词等于免费排除法;
  * len_band          —— 全部选项字数落在均值 ±35% 内视为均衡。

目标位分配(--assign):对每个 surface 内的单选题确定性分配正确项目标存储位,
保证 surface 内各位次数量差 ≤1(hash 有序 + 最少桶优先,可重跑逐字节一致)。

Usage:
    python3 scripts/scan_luban_practice_option_defects.py            # 全量扫描汇总
    python3 scripts/scan_luban_practice_option_defects.py c01 f16    # 只扫指定站点
    python3 scripts/scan_luban_practice_option_defects.py --assign --out-dir /tmp/x
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.luban_lesson.practice_html import (  # noqa: E402
    compile_practice_surface,
)
from scripts.publish_luban_preview_cards import FINISHED, STATIONS, _sha256  # noqa: E402

CASUAL_MARKERS = (
    "就够了",
    "看着定",
    "都行",
    "随便",
    "无所谓",
    "怎么方便怎么",
    "留哪都行",
    "现场看着",
)


def _hash_int(*parts: object) -> int:
    raw = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12], 16)


def scan_station(station_id: str) -> list[dict[str, object]]:
    st = STATIONS[station_id]
    src = FINISHED / st.pack_dir
    rows: list[dict[str, object]] = []
    for hosted_name, src_name in st.practice.items():
        path = src / src_name
        compiled = compile_practice_surface(
            station_id.upper(),
            surface_id=hosted_name,
            html=path.read_text(encoding="utf-8"),
            source_path=str(path.relative_to(REPO)),
            source_html_sha256=_sha256(path),
        )
        for item in compiled["items"]:
            options = item["options"]
            lens = [len(str(opt["text"])) for opt in options]
            correct_index = next(
                index for index, opt in enumerate(options) if opt["is_correct"]
            )
            mean_len = sum(lens) / len(lens)
            rows.append(
                {
                    "pack_id": station_id.upper(),
                    "surface_id": hosted_name,
                    "source_index": item["source_index"],
                    "variant_id": item["variant_id"],
                    "stem": item["stem"],
                    "option_count": len(options),
                    "option_lengths": lens,
                    "correct_index": correct_index,
                    "correct_len": lens[correct_index],
                    "longest_correct": lens[correct_index] > max(
                        value for index, value in enumerate(lens) if index != correct_index
                    ),
                    "pos0_correct": correct_index == 0,
                    "casual_distractors": [
                        index
                        for index, opt in enumerate(options)
                        if not opt["is_correct"]
                        and any(marker in str(opt["text"]) for marker in CASUAL_MARKERS)
                    ],
                    "len_band_ok": all(
                        abs(value - mean_len) <= 0.35 * mean_len for value in lens
                    ),
                }
            )
    return rows


def assign_targets(rows: list[dict[str, object]]) -> None:
    """surface 内确定性均衡分配正确项目标存储位(写进每行 target_correct_index)。"""
    by_surface: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        by_surface.setdefault((str(row["pack_id"]), str(row["surface_id"])), []).append(row)
    for (pack_id, surface_id), group in by_surface.items():
        buckets: dict[int, int] = {}
        ordered = sorted(
            group,
            key=lambda row: _hash_int(pack_id, surface_id, row["source_index"], row["stem"]),
        )
        for row in ordered:
            count = int(row["option_count"])
            preference = sorted(
                range(count),
                key=lambda position: (
                    buckets.get(position, 0),
                    _hash_int(pack_id, surface_id, row["source_index"], position),
                ),
            )
            target = preference[0]
            buckets[target] = buckets.get(target, 0) + 1
            row["target_correct_index"] = target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stations", nargs="*", help="station ids(默认全部)")
    parser.add_argument("--assign", action="store_true", help="附带目标位分配")
    parser.add_argument("--out-dir", default="", help="逐包 JSON 输出目录(缺省不落盘)")
    args = parser.parse_args()
    stations = [name.lower() for name in args.stations] or sorted(STATIONS)
    all_rows: list[dict[str, object]] = []
    for station_id in stations:
        all_rows.extend(scan_station(station_id))
    if args.assign:
        assign_targets(all_rows)
    if args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        by_pack: dict[str, list[dict[str, object]]] = {}
        for row in all_rows:
            by_pack.setdefault(str(row["pack_id"]), []).append(row)
        for pack_id, rows in by_pack.items():
            path = out_dir / f"{pack_id.lower()}.option_defects.json"
            path.write_text(
                json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
            )
    total = len(all_rows)
    longest = sum(1 for row in all_rows if row["longest_correct"])
    pos0 = sum(1 for row in all_rows if row["pos0_correct"])
    casual = sum(1 for row in all_rows if row["casual_distractors"])
    band = sum(1 for row in all_rows if row["len_band_ok"])
    print(f"items={total}")
    print(f"longest_correct={longest} ({100 * longest / max(total, 1):.0f}%)")
    print(f"pos0_correct={pos0} ({100 * pos0 / max(total, 1):.0f}%)")
    print(f"casual_distractor_items={casual} ({100 * casual / max(total, 1):.0f}%)")
    print(f"len_band_ok={band} ({100 * band / max(total, 1):.0f}%)")
    dist: dict[int, int] = {}
    for row in all_rows:
        dist[int(row["correct_index"])] = dist.get(int(row["correct_index"]), 0) + 1
    print("correct_index_distribution=", dict(sorted(dist.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
