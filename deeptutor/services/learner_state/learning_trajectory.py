"""多跳学习轨迹查询（gbrain ``find_trajectory`` 的本项目版）。

一次调用查通：错因 → 训练 → 改善证据 → 复测建议。

纯只读组合层：所有事实来自 ``learning_synthesis`` 的投影（weak_points /
stale_claims / improvement_signals / typed_graph），本模块不计算新事实、
不写任何状态、不构成第二权威。complement：``learning_synthesis`` 已有的
``find_concept_evidence`` / ``trace_training_recommendation`` 是单跳原语，
这里只做跨跳组合。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def group_typed_edges(projection: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    """把投影的 typed_graph.edges 按 edge_type 分组（NBA graph_chain 的标准形状）。"""
    proj = projection if isinstance(projection, dict) else {}
    graph = proj.get("typed_graph") if isinstance(proj.get("typed_graph"), dict) else {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in list(graph.get("edges") or []):
        if not isinstance(edge, dict):
            continue
        edge_type = _text(edge.get("edge_type"))
        if edge_type:
            grouped[edge_type].append(dict(edge))
    return dict(grouped)


def find_learning_trajectory(
    projection: dict[str, Any] | None,
    *,
    concept_id: str = "",
    concept_query: str = "",
) -> dict[str, Any]:
    """在一个投影内走完整条学习轨迹。

    跳 1 错因：该概念下的 active 弱点 + improving 的旧错因；
    跳 2 训练：error_points_to_training 边；
    跳 2.5 用题：training_uses_question 边；
    跳 3 改善：improvement_signals + training_improved_error 边；
    跳 4 复测建议：有改善证据 → 建议复测固化（canonical 促升仍只认
    teacher-final / real_retest，本建议不是促升）。
    """
    cid = _text(concept_id)
    query = _text(concept_query)
    base = _base_result(concept_id=cid, concept_query=query)
    if not cid and not query:
        return {**base, "status": "invalid_query"}

    proj = projection if isinstance(projection, dict) else {}
    claims = [
        dict(item)
        for item in [*list(proj.get("weak_points") or []), *list(proj.get("stale_claims") or [])]
        if isinstance(item, dict)
    ]
    matched = [claim for claim in claims if _claim_matches(claim, concept_id=cid, concept_query=query)]
    if not matched:
        return {**base, "status": "no_match"}

    error_ids = sorted({
        f"{_text(claim.get('concept_id'))}:{_text(claim.get('error_code'))}"
        for claim in matched
        if _text(claim.get("concept_id")) and _text(claim.get("error_code"))
    })
    error_id_set = set(error_ids)
    edges = group_typed_edges(proj)
    evidence_ids: list[str] = []
    for claim in matched:
        for ref in list(claim.get("supporting_event_ids") or []):
            _append_unique(evidence_ids, ref)

    trainings: list[dict[str, Any]] = []
    training_ids: set[str] = set()
    for edge in edges.get("error_points_to_training", []):
        from_id = _node_id(edge, "from")
        to_id = _node_id(edge, "to")
        if from_id in error_id_set and to_id:
            trainings.append({
                "training_id": to_id,
                "error_id": from_id,
                "evidence_event_id": _text(edge.get("evidence_event_id")),
            })
            training_ids.add(to_id)
            _append_unique(evidence_ids, edge.get("evidence_event_id"))

    practice_question_ids: list[str] = []
    for edge in edges.get("training_uses_question", []):
        if _node_id(edge, "from") in training_ids:
            _append_unique(practice_question_ids, _node_id(edge, "to"))
            _append_unique(evidence_ids, edge.get("evidence_event_id"))

    matched_concept_ids = {_text(claim.get("concept_id")) for claim in matched}
    improvements: list[dict[str, Any]] = []
    for signal in list(proj.get("improvement_signals") or []):
        if not isinstance(signal, dict):
            continue
        signal_concept = _text(signal.get("concept_id"))
        signal_error = f"{signal_concept}:{_text(signal.get('error_code'))}"
        if signal_concept in matched_concept_ids:
            improvements.append({
                "error_id": signal_error,
                "evidence_event_id": _text(signal.get("event_id")),
                "observed_at": _text(signal.get("observed_at")),
                "source": "improvement_signal",
            })
            _append_unique(evidence_ids, signal.get("event_id"))
    for edge in edges.get("training_improved_error", []):
        to_id = _node_id(edge, "to")
        if to_id in error_id_set:
            improvements.append({
                "error_id": to_id,
                "training_id": _node_id(edge, "from"),
                "evidence_event_id": _text(edge.get("evidence_event_id")),
                "source": "typed_graph",
            })
            _append_unique(evidence_ids, edge.get("evidence_event_id"))

    return {
        **base,
        "status": "ok",
        "matched_claims": [_claim_view(claim) for claim in matched],
        "errors": error_ids,
        "trainings": trainings,
        "practice_question_ids": practice_question_ids,
        "improvements": _dedupe_improvements(improvements),
        "retest_recommendation": _retest_recommendation(improvements=improvements),
        "evidence_event_ids": evidence_ids,
    }


def get_learning_trajectory_for_user(
    service: Any,
    user_id: str,
    *,
    concept_id: str = "",
    concept_query: str = "",
) -> dict[str, Any]:
    """缓存优先的用户级轨迹查询：先读 dream cycle 巩固的 compiled 投影缓存，
    miss 才回退 turn 式 dry-run 合成（不持久化）。"""
    projection: dict[str, Any] = {}
    source = "compiled_cache"
    reader = getattr(service, "read_compiled_learning_truth", None)
    if callable(reader):
        try:
            cached = reader(user_id)
        except Exception:  # noqa: BLE001 — 只读查询必须 fail-open 到回退路径
            cached = None
        if isinstance(cached, dict) and cached:
            projection = cached
    if not projection and hasattr(service, "synthesize_learning_truth"):
        source = "dry_run_synthesis"
        # 回退路径加事件窗口上界，避免大历史用户在 turn 内做无界合成。
        result = service.synthesize_learning_truth(user_id, dry_run=True, event_limit=200)
        if isinstance(result, dict) and isinstance(result.get("projection"), dict):
            projection = result["projection"]
    trajectory = find_learning_trajectory(projection, concept_id=concept_id, concept_query=concept_query)
    trajectory["user_id"] = str(user_id or "").strip()
    trajectory["projection_source"] = source
    return trajectory


def _base_result(*, concept_id: str, concept_query: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source": "learning_synthesis_projection",
        "is_second_authority": False,
        "concept_id": concept_id,
        "concept_query": concept_query,
        "matched_claims": [],
        "errors": [],
        "trainings": [],
        "practice_question_ids": [],
        "improvements": [],
        "retest_recommendation": {"due_now": False, "reason": "未匹配到该概念的学习证据。"},
        "evidence_event_ids": [],
    }


def _claim_matches(claim: dict[str, Any], *, concept_id: str, concept_query: str) -> bool:
    claim_concept = _text(claim.get("concept_id"))
    if concept_id:
        return claim_concept == concept_id
    label = _text(claim.get("concept_label") or claim.get("label"))
    return bool(concept_query) and (concept_query in label or concept_query in claim_concept)


def _claim_view(claim: dict[str, Any]) -> dict[str, Any]:
    return {
        "concept_id": _text(claim.get("concept_id")),
        "error_code": _text(claim.get("error_code")),
        "concept_label": _text(claim.get("concept_label") or claim.get("label")),
        "evidence_level": _text(claim.get("evidence_level")),
        "decay_state": _text(claim.get("decay_state")) or "active",
        "claim_status": _text(claim.get("claim_status")),
        "supporting_event_ids": [
            _text(item) for item in list(claim.get("supporting_event_ids") or []) if _text(item)
        ],
    }


def _retest_recommendation(*, improvements: list[dict[str, Any]]) -> dict[str, Any]:
    if improvements:
        return {
            "due_now": True,
            "reason": "已有训练改善证据，建议安排复测固化（canonical 促升仍只认 teacher-final / real_retest）。",
        }
    return {
        "due_now": False,
        "reason": "尚无改善证据：先完成针对性训练，再安排复测。",
    }


def _dedupe_improvements(improvements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in improvements:
        evidence_id = _text(item.get("evidence_event_id"))
        # 同一证据的跨来源条目折叠；evidence 缺失时用 training_id 兜底，
        # 避免多个无证据边被误折叠成一条。
        key = (
            _text(item.get("error_id")),
            evidence_id,
            "" if evidence_id else _text(item.get("training_id")),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _node_id(edge: dict[str, Any], side: str) -> str:
    node = edge.get(side) if isinstance(edge.get(side), dict) else {}
    return _text(node.get("id"))


def _append_unique(items: list[str], value: Any) -> None:
    text = _text(value)
    if text and text not in items:
        items.append(text)


def _text(value: Any) -> str:
    return str(value or "").strip()


__all__ = [
    "find_learning_trajectory",
    "get_learning_trajectory_for_user",
    "group_typed_edges",
]
