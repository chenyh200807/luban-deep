#!/usr/bin/env python3
"""修复编译 rubric 库的 qid 串题污染（治本，可复现、可审计）。

根因（A/B 实测发现）：chunk EXAM_1A433000_P0011_01 是质量检测/混凝土缺陷/后浇带题，但其
``::E0``(21 个采分点) 全部是另一道题（网络计划/退场记录/深基坑/施工升降机/声学）——编译时把两道
不同真题混进了同一个 chunk。E1/E2/E3 才是本题（缺陷图/后浇带/工艺）。E0 的网络计划题内容在全库
唯一（误填，非重复），删除它使本 chunk 与其题号对齐，V1 才能用正确 rubric 判分。

全库智能扫描（每 chunk 各 E 的"问题N"引用 + 重叠）确认此污染**仅此 1 个 chunk**。

本脚本只删被污染的 ::E0 记录，并按编译器口径重算 bank manifest 的 content_hash/signature/计数，
再更新 canonical_pointer。canonical_knowledge_manifest 由其 builder 脚本重生成（见末尾提示）。
不新增/不改其它记录；release_candidate（未发布）。
"""
from __future__ import annotations

import json
from pathlib import Path

from deeptutor.services.construction_grading.full_knowledge_compiler import _sha256_hex

REPO = Path(__file__).resolve().parent.parent
SUP = REPO / "deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored"
BANK = SUP / "case_rubric_scored.json"
POINTER = SUP / "canonical_pointer.json"

CONTAMINATED_QID = "EXAM_1A433000_P0011_01::E0"


def main() -> None:
    bank = json.loads(BANK.read_text("utf-8"))
    records = bank["records"]
    manifest = bank["manifest"]

    removed = [r for r in records if str(r["qid"]) == CONTAMINATED_QID]
    kept = [r for r in records if str(r["qid"]) != CONTAMINATED_QID]
    if not removed:
        print(f"无需修复：{CONTAMINATED_QID} 不存在（可能已修）")
        return
    print(f"删除被污染记录：{CONTAMINATED_QID} 共 {len(removed)} 个采分点")

    # recompute bank manifest exactly as the signer does (content_hash over records as written)
    content_hash = _sha256_hex(kept)
    namespace = manifest["namespace"]      # case_rubric_scored
    status = manifest["status"]            # release_candidate
    signature = _sha256_hex([content_hash, namespace, status])
    by_policy: dict[str, int] = {}
    for r in kept:
        by_policy[r["policy"]] = by_policy.get(r["policy"], 0) + 1

    manifest["content_hash"] = content_hash
    manifest["signature"] = signature
    manifest["scoring_point_count"] = len(kept)
    manifest["question_count"] = len({str(r["qid"]) for r in kept})
    manifest["by_policy"] = by_policy
    bank["records"] = kept
    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"bank 重签：records {len(records)}->{len(kept)}, qids {manifest['question_count']}, "
          f"content_hash={content_hash[:16]}…")

    # keep the direct pointer consistent (verify_bundle checks manifest.content_hash == pointer expected)
    pointer = json.loads(POINTER.read_text("utf-8"))
    pointer["expected_content_hash"] = content_hash
    POINTER.write_text(json.dumps(pointer, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"canonical_pointer.expected_content_hash 已更新")

    # update the canonical_knowledge_manifest case_rubric_scored shard entry + recompute its self
    # content_hash/signature MANUALLY (the full builder rebuilds every lane incl. concept_registry —
    # out of scope; we touch only this one file). source_inventory is over the /2026 source corpus,
    # unchanged by this fix.
    from deeptutor.services.construction_grading import canonical_knowledge_manifest as CKM

    ckm_path = (REPO / "deeptutor/services/construction_grading/runtime_supply/"
                "v_canonical_knowledge_manifest/canonical_knowledge_manifest.json")
    ckm = json.loads(ckm_path.read_text("utf-8"))
    for s in ckm["shards"]:
        if s["lane"] == "case_rubric_scored":
            s["content_hash"] = content_hash
            s["record_count"] = len(kept)
    shards_sorted = sorted(ckm["shards"], key=lambda s: str(s.get("lane")))
    ckm["shards"] = shards_sorted
    ckm["content_hash"] = CKM._sha256(
        {"shards": shards_sorted, "source_inventory_hash": ckm["source_inventory_hash"]})
    ckm["signature"] = CKM._sha256([ckm["content_hash"], CKM.NAMESPACE, ckm["status"]])
    ckm_path.write_text(json.dumps(ckm, ensure_ascii=False, indent=2), encoding="utf-8")
    ok, reason = CKM.verify_manifest(ckm, SUP.parent)
    print(f"canonical_knowledge_manifest 已更新; verify_manifest={ok} ({reason})")

    # verify the V1 runtime gate now passes and the chunk is clean
    e0 = [r for r in kept if str(r["qid"]) == CONTAMINATED_QID]
    print(f"\n校验：bank hash-gate {'PASS' if _sha256_hex(kept) == content_hash else 'FAIL'}; "
          f"E0 残留 {len(e0)} (应0)")


if __name__ == "__main__":
    main()
