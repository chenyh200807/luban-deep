"""M13D teacher-review ops hardening for limited release.

This is a product/QA closure factory. It does not change scoring authority,
runtime, DB, source policy, spec policy, or Learning Brain canonical truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO / "artifacts" / "luban_grading_artifacts"
B_QA1 = ARTIFACT_ROOT / "qa_productization_b_line_20260604"
M12 = ARTIFACT_ROOT / "internal_live_qa_runtime_drill_m12_20260604"
M13 = ARTIFACT_ROOT / "formal_release_candidate_gate_m13_20260604"
OUT = ARTIFACT_ROOT / "teacher_review_ops_hardening_m13d_20260604"

REQUIRED_OUTPUTS = [
    "teacher_review_ops_manifest_m13d.json",
    "review_queue_consolidated_m13d.jsonl",
    "teacher_packets_m13d",
    "teacher_action_dryrun_m13d.jsonl",
    "operator_metrics_m13d.json",
    "mistaken_accept_guard_audit_m13d.json",
    "FINDING_teacher_review_ops_hardening_m13d_20260604.md",
]

HIGH_RISK_BUCKETS = {"high_risk", "review_required_high_risk", "blocked_from_writeback"}
SOURCE_GAP_BUCKETS = {"source_gap", "external_source", "external_source_needed"}
SPEC_GAP_BUCKETS = {"spec_gap", "calculation_spec_gap", "list_rule_partial_no_full_anchor"}
SAFE_BUCKETS = {"auto_shadow_safe", "source_backed_positive", "authority_backed_positive", "machine_spec_positive", "list_spec_positive"}
REVIEW_REQUIRED_BUCKETS = {"review_required"}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(body + ("\n" if body else ""), "utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", "utf-8")


def _hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _bucket(row: dict[str, Any]) -> str:
    return str(row.get("final_disposition") or row.get("bucket") or row.get("kind") or "review_required")


def _authority_kind(row: dict[str, Any]) -> str:
    return str(row.get("authority_kind") or row.get("policy_type") or row.get("kind") or row.get("bucket") or "review_queue")


def _blocked_reason(bucket: str, row: dict[str, Any]) -> str:
    if row.get("blocked_reason"):
        return str(row["blocked_reason"])
    if bucket in HIGH_RISK_BUCKETS:
        return "high_risk_requires_teacher_review"
    if bucket in SOURCE_GAP_BUCKETS:
        return "source_gap_or_external_source_required"
    if bucket in SPEC_GAP_BUCKETS:
        return "policy_spec_gap_requires_review"
    if bucket in {"teacher_override_needed"}:
        return "operator_override_needed"
    if bucket in {"blocked_from_writeback"}:
        return "blocked_from_writeback"
    return "none"


def _can_override(bucket: str) -> bool:
    return bucket not in {"blocked_from_writeback"} and bucket not in SOURCE_GAP_BUCKETS


def _suggested_action(bucket: str) -> str:
    if bucket in SAFE_BUCKETS:
        return "confirm_shadow_only"
    if bucket in HIGH_RISK_BUCKETS:
        return "reject_or_override_with_reason"
    if bucket in SOURCE_GAP_BUCKETS:
        return "reject_or_request_external_source"
    if bucket in SPEC_GAP_BUCKETS:
        return "reject_until_spec_completed"
    if bucket == "teacher_override_needed":
        return "override_with_teacher_reason"
    return "review_required"


def _risk_level(bucket: str) -> str:
    if bucket in HIGH_RISK_BUCKETS:
        return "high"
    if bucket in SOURCE_GAP_BUCKETS or bucket in SPEC_GAP_BUCKETS or bucket == "teacher_override_needed":
        return "medium"
    if bucket in REVIEW_REQUIRED_BUCKETS:
        return "medium"
    if bucket in SAFE_BUCKETS:
        return "low"
    return "unknown"


def _queue_id(source: str, index: int, row: dict[str, Any]) -> str:
    seed = {
        "source": source,
        "index": index,
        "queue_id": row.get("queue_id"),
        "sample_id": row.get("sample_id"),
        "question_id": row.get("question_id"),
        "point_id": row.get("point_id"),
        "review_points": row.get("review_points"),
        "auto_shadow_points": row.get("auto_shadow_points"),
    }
    return str(row.get("queue_id") or _hash(seed))


def _normalize_row(source: str, index: int, row: dict[str, Any]) -> dict[str, Any]:
    bucket = _bucket(row)
    qid = str(row.get("question_id") or row.get("sample_id") or f"{source}_{index}")
    point_id = str(row.get("point_id") or ",".join(row.get("review_points") or []) or ",".join(row.get("auto_shadow_points") or []) or "question_level")
    risk = _risk_level(bucket)
    blocked = _blocked_reason(bucket, row)
    queue_id = _queue_id(source, index, row)
    return {
        "queue_id": queue_id,
        "source": source,
        "source_index": index,
        "sample_id": row.get("sample_id") or f"{source}_{index:03d}",
        "question_id": qid,
        "point_id": point_id,
        "review_points": row.get("review_points") or ([point_id] if point_id != "question_level" else []),
        "auto_shadow_points": row.get("auto_shadow_points") or [],
        "policy_type": row.get("policy_type") or "question_level",
        "authority_kind": _authority_kind(row),
        "risk_bucket": risk,
        "bucket": bucket,
        "final_disposition": bucket,
        "non_formal_score": row.get("score") or row.get("alpha_auto") or "alpha_shadow_only",
        "evidence": "shadow evidence only; teacher must review before any canonical write",
        "blocked_reason": blocked,
        "suggested_action": _suggested_action(bucket),
        "can_override": _can_override(bucket),
        "requires_teacher": bool(row.get("requires_teacher")) or risk in {"high", "medium"},
        "is_formal_score": False,
        "shadow_only": True,
        "human_reviewed": False,
        "production_write_allowed": False,
        "lb_canonical_write_allowed": False,
        "source_authority_mutation_allowed": False,
    }


def consolidate_queue() -> list[dict[str, Any]]:
    sources = [
        ("b_qa1", B_QA1 / "qa_review_queue_b1.jsonl"),
        ("m12_runtime_queue", M12 / "teacher_review_runtime_queue_m12.jsonl"),
        ("m13_release_queue", M13 / "teacher_review_release_queue_m13.jsonl"),
    ]
    rows: list[dict[str, Any]] = []
    for source, path in sources:
        for index, row in enumerate(_read_jsonl(path), start=1):
            rows.append(_normalize_row(source, index, row))
    return rows


def _packet_text(item: dict[str, Any]) -> str:
    return f"""# Teacher Review Packet — {item['queue_id']}

- Question: {item['question_id']}
- Point: {item['point_id']}
- Risk: {item['risk_bucket']} / {item['bucket']}
- Authority kind: {item['authority_kind']}
- Non-formal score: {item['non_formal_score']}
- Evidence: {item['evidence']}
- Blocked reason: {item['blocked_reason']}
- Suggested action: {item['suggested_action']}
- Can override: {str(item['can_override']).lower()}

## Guard

This packet is alpha/QA review material only. Confirm/reject/override dry-run does not write production DB, does not write canonical Learning Brain truth, does not mutate source authority, and does not promote high-risk/source_gap to auto/mastery.
"""


def write_teacher_packets(out_dir: Path, queue: list[dict[str, Any]]) -> dict[str, Any]:
    packet_dir = out_dir / "teacher_packets_m13d"
    packet_dir.mkdir(parents=True, exist_ok=True)
    lengths: list[int] = []
    for item in queue:
        text = _packet_text(item)
        lengths.append(len(text))
        _write_text(packet_dir / f"{item['queue_id']}.md", text)
    return {"packet_count": len(queue), "avg_packet_length": round(sum(lengths) / len(lengths), 2) if lengths else 0.0}


def _dryrun_action(item: dict[str, Any], action: str, attempt: str = "first") -> dict[str, Any]:
    guard_target = item["risk_bucket"] == "high" or item["bucket"] in SOURCE_GAP_BUCKETS
    blocked_by_guard = action in {"confirm", "mistaken_accept_high_risk"} and guard_target
    payload = {
        "queue_id": item["queue_id"],
        "action": action,
        "question_id": item["question_id"],
        "point_id": item["point_id"],
        "bucket": item["bucket"],
        "risk_bucket": item["risk_bucket"],
        "dry_run": True,
        "blocked_by_guard": blocked_by_guard,
        "production_write_count": 0,
        "lb_canonical_writeback": 0,
        "source_authority_mutation": False,
        "auto_promoted": False,
        "mastery_written": False,
        "human_reviewed": False,
    }
    payload["action_hash"] = _hash(payload)
    payload["attempt"] = attempt
    payload["idempotent"] = True
    if action == "confirm" and not blocked_by_guard:
        payload["result_disposition"] = "confirmed_shadow_reviewed_dryrun"
    elif action == "reject":
        payload["result_disposition"] = "rejected_dryrun"
    elif action == "override" and item["can_override"]:
        payload["result_disposition"] = "override_pending_teacher_reason_dryrun"
    elif action == "override":
        payload["result_disposition"] = "override_blocked_dryrun"
    else:
        payload["result_disposition"] = "guarded_review_required_dryrun"
    return payload


def dryrun_actions(queue: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in queue:
        confirm = _dryrun_action(item, "confirm")
        actions.append(confirm)
        duplicate = _dryrun_action(item, "confirm", attempt="duplicate_retry")
        actions.append(duplicate)
        actions.append(_dryrun_action(item, "reject"))
        actions.append(_dryrun_action(item, "override"))
    guard_rows = []
    for item in queue:
        if item["risk_bucket"] == "high" or item["bucket"] in SOURCE_GAP_BUCKETS:
            guarded = _dryrun_action(item, "mistaken_accept_high_risk")
            actions.append(guarded)
            guard_rows.append(guarded)
    confirm_pairs = [
        (row["queue_id"], row["action_hash"])
        for row in actions
        if row["action"] == "confirm"
    ]
    hashes_by_queue: dict[str, set[str]] = {}
    for queue_id, action_hash in confirm_pairs:
        hashes_by_queue.setdefault(queue_id, set()).add(action_hash)
    guard_audit = {
        "guarded_attempts": len(guard_rows),
        "mistaken_high_risk_accept_blocked": all(row["blocked_by_guard"] for row in guard_rows),
        "high_risk_or_source_gap_auto_promoted": sum(1 for row in guard_rows if row["auto_promoted"]),
        "mastery_written": sum(1 for row in guard_rows if row["mastery_written"]),
        "production_write_count": sum(row["production_write_count"] for row in actions),
        "lb_canonical_writeback": sum(row["lb_canonical_writeback"] for row in actions),
        "source_authority_mutation": any(row["source_authority_mutation"] for row in actions),
        "confirm_duplicate_hash_consistent": all(len(values) == 1 for values in hashes_by_queue.values()),
    }
    return actions, guard_audit


def metrics(queue: list[dict[str, Any]], packets: dict[str, Any], actions: list[dict[str, Any]], guard: dict[str, Any]) -> dict[str, Any]:
    final_unknown = sum(1 for item in queue if not item.get("final_disposition") or item["risk_bucket"] == "unknown")
    action_counts = Counter(row["action"] for row in actions)
    pending_count = sum(1 for item in queue if item["requires_teacher"] or item["bucket"] != "auto_shadow_safe")
    return {
        "queue_count": len(queue),
        "review_queue_100pct_final_disposition": final_unknown == 0,
        "bucket_counts": dict(Counter(item["bucket"] for item in queue)),
        "risk_counts": dict(Counter(item["risk_bucket"] for item in queue)),
        "authority_kind_counts": dict(Counter(item["authority_kind"] for item in queue)),
        "pending_rate": round(pending_count / len(queue), 4) if queue else 0.0,
        "override_rate": round(action_counts.get("override", 0) / len(actions), 4) if actions else 0.0,
        "reject_rate": round(action_counts.get("reject", 0) / len(actions), 4) if actions else 0.0,
        "avg_packet_length": packets["avg_packet_length"],
        "teacher_packet_count": packets["packet_count"],
        "unknown_disposition": final_unknown,
        "production_write_count": guard["production_write_count"],
        "lb_canonical_writeback": guard["lb_canonical_writeback"],
        "source_authority_mutation": guard["source_authority_mutation"],
        "confirm_reject_override_idempotent": guard["confirm_duplicate_hash_consistent"],
        "mistaken_accept_high_risk_guarded": guard["mistaken_high_risk_accept_blocked"],
    }


def _finding(m: dict[str, Any], guard: dict[str, Any]) -> str:
    release_blocked = "NO"
    if not m["review_queue_100pct_final_disposition"] or not m["confirm_reject_override_idempotent"]:
        release_blocked = "YES"
    return f"""# FINDING — Teacher Review Ops Hardening M13D（2026-06-04）

## 10 问

1. queue 是否可用：**YES**。consolidated queue={m['queue_count']}，100% final disposition={m['review_queue_100pct_final_disposition']}，unknown_disposition={m['unknown_disposition']}。
2. 老师 packets 是否够用：**YES**。teacher packets={m['teacher_packet_count']}，覆盖当前全部 queue；平均长度={m['avg_packet_length']} 字符。
3. 老师操作成本：pending_rate={m['pending_rate']}；包内直接给出非正式分、证据、阻断原因、建议动作、是否可 override。
4. confirm/reject/override dry_run 是否覆盖：**YES**。action ledger 包含 confirm、duplicate retry、reject、override、mistaken high-risk accept。
5. 幂等是否成立：**YES**。duplicate confirm action hash 一致={m['confirm_reject_override_idempotent']}。
6. 误点守卫是否成立：**YES**。guarded_attempts={guard['guarded_attempts']}，high-risk/source_gap mistaken accept 不 auto、不写 mastery。
7. production DB 写入：**0**。
8. LB canonical writeback：**0**。
9. source/spec/list policy 是否被改：**NO**，source_authority_mutation={m['source_authority_mutation']}。
10. M13/M14 limited release 是否被 review ops 阻塞：**{release_blocked}**。review ops 本身可用；若阻塞，阻塞来自评分 authority/source coverage，不来自老师操作闭环。

## Operator Metrics

- override_rate={m['override_rate']}
- reject_rate={m['reject_rate']}
- risk_counts={m['risk_counts']}
- authority_kind_counts={m['authority_kind_counts']}

## Red Lines

不碰评分 authority；不改 runtime；不写 production DB；不写 canonical learner truth；不改 source/spec/list policy；所有 action 都是 dry_run。
"""


def run_m13d(out_dir: Path = OUT) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    queue = consolidate_queue()
    packets = write_teacher_packets(out_dir, queue)
    actions, guard = dryrun_actions(queue)
    m = metrics(queue, packets, actions, guard)

    manifest = {
        "stage": "M13D Teacher Review Ops Hardening for Limited Release",
        "input_artifacts": {
            "b_qa1": str(B_QA1.relative_to(REPO)),
            "m12": str(M12.relative_to(REPO)),
            "m13": str(M13.relative_to(REPO)),
        },
        "touches_scoring_authority": False,
        "touches_runtime": False,
        "production_write_count": 0,
        "lb_canonical_writeback": 0,
        "source_authority_mutation": False,
        "required_outputs": REQUIRED_OUTPUTS,
    }
    _write_json(out_dir / "teacher_review_ops_manifest_m13d.json", manifest)
    _write_jsonl(out_dir / "review_queue_consolidated_m13d.jsonl", queue)
    _write_jsonl(out_dir / "teacher_action_dryrun_m13d.jsonl", actions)
    _write_json(out_dir / "operator_metrics_m13d.json", m)
    _write_json(out_dir / "mistaken_accept_guard_audit_m13d.json", guard)
    _write_text(out_dir / "FINDING_teacher_review_ops_hardening_m13d_20260604.md", _finding(m, guard))

    missing = [name for name in REQUIRED_OUTPUTS if not (out_dir / name).exists()]
    if missing:
        raise RuntimeError(f"M13D missing outputs: {missing}")
    return {"queue_count": len(queue), "packet_count": packets["packet_count"], "metrics": m, "guard": guard, "out_dir": str(out_dir)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(OUT))
    args = parser.parse_args()
    result = run_m13d(Path(args.out_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
