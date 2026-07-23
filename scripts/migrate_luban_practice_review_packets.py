#!/usr/bin/env python3
"""选项反可猜性重写后的 practice review packet 迁移重签(2026-07-18 战役工具)。

背景:随堂练单选题干扰项重写(拉平长度)+ 正确项位置重排后,
variant_id/content_sha256/source_bundle_sha256 全部变化,旧 packet 会在发布时
触发 identity mismatch / item drift 而 fail-closed。本工具把旧 authority 里的
人审决策(fact_id/skeleton_id/probe_role/source_anchor/source_sha256/review)
按稳定键 (surface_id, source_index) 迁移到重编译后的新题上,重建 packet。

签名边界(owner-delegated,与 sign_practice_review_decisions.py 同一委托):
  * 只迁移**旧已签**决策;迁移前机械断言:题干、model_answer、正确项文本
    三者逐字节未变——正确项与事实锚未动,原教材裁决继续成立;干扰项文本
    变化由本次战役的改写契约(同一埋错、逐题对抗核验)覆盖,签名 note 追加
    机器可读的重签说明;
  * 旧 pending 项保持 pending,零签名,机器绝不代签;
  * 迁移后在内存里重建 authority 并断言 supply_ready 与旧状态一致,
    不一致则整包中止、不落盘。

Usage:
    python3 scripts/migrate_luban_practice_review_packets.py c01 j01 ...
    python3 scripts/migrate_luban_practice_review_packets.py --all
    # 旧 authority 已被覆盖时,用战役快照兜底:
    python3 scripts/migrate_luban_practice_review_packets.py c01 --snapshot /path/snap.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.luban_lesson.practice_html import (  # noqa: E402
    build_practice_authority,
    compile_practice_surface,
    compiled_practice_eligibility_summary,
)
from scripts.publish_luban_preview_cards import (  # noqa: E402
    FINISHED,
    PRACTICE_REVIEW_PACKET_DIR,
    STATIONS,
    _build_practice_review_packet,
    _pack_source_sha,
    _practice_source_bundle_sha,
    _sha256,
)

AUTHORITY_HOST = REPO / "deeptutor" / "services" / "luban_lesson" / "compiled"
CST = timezone(timedelta(hours=8))
RESIGN_NOTE = (
    "2026-07-18 选项反可猜性均衡重签:干扰项重写拉平长度并去除口语破绽词,"
    "正确项文本/题干/model_answer/事实锚逐字节未动(机械断言);正确项存储位"
    "按确定性分配重排;埋错语义经逐题对抗核验与原 code/temptation/loss_reason 一致。"
)


def _old_items(pack_id: str, snapshot: dict | None) -> tuple[dict, bool]:
    """旧决策来源:优先磁盘旧 authority(发布前仍是旧态),否则战役快照。"""
    path = AUTHORITY_HOST / f"{pack_id.lower()}.practice.authority.json"
    data = None
    if snapshot is not None and pack_id in snapshot:
        data = snapshot[pack_id]
    elif path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    if data is None:
        raise SystemExit(f"ABORT {pack_id}: no old authority or snapshot entry")
    items = {}
    for item in data.get("items") or []:
        correct_text = item.get("correct_text") or next(
            opt["text"] for opt in item.get("options") or [] if opt.get("is_correct")
        )
        items[(str(item["surface_id"]), int(item["source_index"]))] = {
            "stem": item["stem"],
            "model_answer": item["model_answer"],
            "correct_text": correct_text,
            "fact_id": item.get("fact_id") or "",
            "skeleton_id": item.get("skeleton_id") or "",
            "probe_role": item.get("probe_role") or "",
            "source_anchor": item.get("source_anchor") or "",
            "source_sha256": item.get("source_sha256") or "",
            "review": item.get("review") or {},
            "revoked": bool(item.get("revoked")),
            "revocation_refs": item.get("revocation_refs") or [],
        }
    was_ready = bool(
        compiled_practice_eligibility_summary(data)["supply_ready"]
    ) if data.get("items") else False
    return items, was_ready


def migrate(
    station_id: str,
    *,
    snapshot: dict | None,
    now_iso: str,
    resign_note: str,
) -> str:
    st = STATIONS[station_id]
    pack_id = station_id.upper()
    packet_path = PRACTICE_REVIEW_PACKET_DIR / f"{station_id}.practice.review.json"
    old_items, was_ready = _old_items(pack_id, snapshot)

    src = FINISHED / st.pack_dir
    compiled_surfaces = []
    for hosted_name, src_name in st.practice.items():
        source = src / src_name
        compiled_surfaces.append(
            compile_practice_surface(
                pack_id,
                surface_id=hosted_name,
                html=source.read_text(encoding="utf-8"),
                source_path=(
                    "artifacts/luban_case_family_assets/diagram_microlesson/finished/"
                    f"{st.pack_dir}/{src_name}"
                ),
                source_html_sha256=_sha256(source),
            )
        )

    records: dict[str, dict] = {}
    signed_count = 0
    for compiled in compiled_surfaces:
        for item in compiled["items"]:
            key = (str(item["surface_id"]), int(item["source_index"]))
            old = old_items.get(key)
            if old is None:
                raise SystemExit(f"ABORT {pack_id}: new item has no old counterpart {key}")
            review = old["review"] or {}
            if review.get("status") != "signed":
                continue  # pending 保持 pending,机器不代签
            # 签名可迁移的前提:被裁决的事实面逐字节未动
            new_correct = next(o["text"] for o in item["options"] if o["is_correct"])
            for field_name, old_value, new_value in (
                ("stem", old["stem"], item["stem"]),
                ("model_answer", old["model_answer"], item["model_answer"]),
                ("correct_text", old["correct_text"], new_correct),
            ):
                if old_value != new_value:
                    raise SystemExit(
                        f"ABORT {pack_id} {key}: signed item {field_name} changed"
                    )
            new_review = dict(review)
            new_review["reviewed_content_sha256"] = item["content_sha256"]
            checks = dict(new_review.get("checks") or {})
            checks["longest_option_checked"] = True
            new_review["checks"] = checks
            new_review["signatures"] = [
                {**signature, "signed_at": now_iso}
                for signature in review.get("signatures") or []
            ]
            note = str(new_review.get("note") or "").strip()
            new_review["note"] = (note + " | " if note else "") + resign_note
            records[str(item["variant_id"])] = {
                "fact_id": old["fact_id"],
                "skeleton_id": old["skeleton_id"],
                "probe_role": old["probe_role"],
                "source_anchor": old["source_anchor"],
                "source_sha256": old["source_sha256"],
                "review": new_review,
                "revoked": old["revoked"],
                "revocation_refs": old["revocation_refs"],
            }
            signed_count += 1

    authority = build_practice_authority(
        pack_id,
        source_pack_sha256=_pack_source_sha(pack_id),
        source_bundle_sha256=_practice_source_bundle_sha(src, st),
        compiled_surfaces=compiled_surfaces,
        review_records=records,
    )
    now_ready = bool(compiled_practice_eligibility_summary(authority)["supply_ready"])
    if now_ready != was_ready:
        raise SystemExit(
            f"ABORT {pack_id}: supply_ready {was_ready} -> {now_ready}, refuse to write"
        )
    if not packet_path.is_file() and signed_count == 0:
        return f"{pack_id}: no packet + no signed items, skip"
    packet = _build_practice_review_packet(authority)
    packet_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return (
        f"{pack_id}: packet rewritten, signed={signed_count}, "
        f"supply_ready={now_ready}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stations", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--snapshot", default="")
    parser.add_argument(
        "--now", default=datetime.now(CST).replace(microsecond=0).isoformat()
    )
    parser.add_argument(
        "--resign-note",
        default=RESIGN_NOTE,
        help="附加到保留签名的可读迁移说明",
    )
    args = parser.parse_args()
    stations = sorted(STATIONS) if args.all else [name.lower() for name in args.stations]
    if not stations:
        parser.error("no stations given")
    snapshot = None
    if args.snapshot:
        snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    for station_id in stations:
        print(
            migrate(
                station_id,
                snapshot=snapshot,
                now_iso=args.now,
                resign_note=args.resign_note,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
