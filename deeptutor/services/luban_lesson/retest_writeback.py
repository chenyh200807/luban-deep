from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from typing import Any

from deeptutor.services.learner_state.event_identity import canonical_event_id
from deeptutor.services.learner_state.evidence_lifecycle import (
    canonical_retest_item_events,
    is_canonical_luban_retest_terminal,
    validate_immediate_confirm_parent,
)
from deeptutor.services.learner_state.learner_signal import record_learner_signal
from deeptutor.services.luban_lesson.practice_html import is_compiled_practice_pack
from deeptutor.services.luban_lesson.read_model import (
    build_lesson_viewmodel,
    resolve_retest_items,
    retest_supply_identity,
)
from deeptutor.services.luban_lesson.retest_selection import (
    decode_retest_selection,
    verify_retest_selection,
)
from deeptutor.services.luban_lesson.review_due import (
    ReviewHorizonUnavailable,
    build_review_due_projection,
    resolve_due_review_probe,
)
from deeptutor.services.luban_lesson.variant_eligibility import (
    resolve_variant_probe_items,
    variant_probe_supply_identity,
)

SOURCE_FEATURE = "assessment_testset"
CLAIM_SOURCE_FEATURE = "luban_retest_claim"
ERROR_CODE = "unknown_error"
_REVIEW_FLAG = "LUBAN_REVIEW_MODULE_ENABLED"
_LIGHT_PRACTICE_FLAG = "LUBAN_LIGHT_PRACTICE_ENABLED"


class RetestIdempotencyConflict(RuntimeError):
    pass


class RetestProbeClaimUnavailable(RuntimeError):
    pass


class RetestCompletionInProgress(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _request_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_answers(value: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in list(value or []):
        item = dict(raw or {})
        variant_id = str(item.get("variant_id") or "").strip()
        if not variant_id or variant_id in seen:
            raise ValueError("retest_duplicate_or_missing_variant_id")
        choice = item.get("choice_ok")
        selected_option_id = str(item.get("selected_option_id") or "").strip()
        has_boolean_choice = isinstance(choice, bool)
        has_option_choice = bool(selected_option_id)
        if has_boolean_choice == has_option_choice:
            raise ValueError(f"retest_answer_requires_exactly_one_choice:{variant_id}")
        seen.add(variant_id)
        normalized = {"variant_id": variant_id}
        if has_boolean_choice:
            normalized["choice_ok"] = choice
        else:
            normalized["selected_option_id"] = selected_option_id
        answers.append(normalized)
    return sorted(answers, key=lambda item: item["variant_id"])


def _edge(edge_type: str, from_type: str, from_id: str, to_type: str, to_id: str) -> dict[str, Any]:
    return {
        "edge_type": edge_type,
        "from": {"type": from_type, "id": from_id},
        "to": {"type": to_type, "id": to_id},
        "source_feature": SOURCE_FEATURE,
        "confidence": 0.9,
    }


def _learning_change_status(*, mode: str, score_ratio: float) -> str:
    if mode == "forward":
        return "practice_recorded"
    return "verification_passed" if score_ratio >= 1.0 else "verification_failed"


def _flag_enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _require_rollout_enabled(mode: str) -> None:
    if not _flag_enabled(_REVIEW_FLAG):
        raise ValueError("luban_review_module_disabled")
    if mode == "forward" and not _flag_enabled(_LIGHT_PRACTICE_FLAG):
        raise ValueError("luban_light_practice_disabled")


class RetestWritebackService:
    def __init__(
        self,
        *,
        learner_state_service: Any,
        review_probe_resolver: Any | None = None,
        review_exam_date_resolver: Any | None = None,
        training_intent_validator: Any | None = None,
    ) -> None:
        self._learner_state = learner_state_service
        self._review_probe_resolver = review_probe_resolver
        self._review_exam_date_resolver = review_exam_date_resolver
        self._training_intent_validator = training_intent_validator

    def complete(
        self,
        *,
        user_id: str,
        completion_id: str,
        selection_id: str,
        pack_id: str,
        mode: str,
        day_index: int,
        answers: list[dict[str, Any]],
        training_intent_id: str = "",
        probe_id: str = "",
    ) -> dict[str, Any]:
        normalized_user = str(user_id or "").strip()
        normalized_completion = str(completion_id or "").strip()
        normalized_pack = str(pack_id or "").strip().upper()
        requested_mode = "forward" if str(mode or "").strip().lower() == "forward" else "review"
        if not normalized_user:
            raise ValueError("user_id_required")
        if not normalized_completion:
            raise ValueError("retest_completion_id_required")
        if not normalized_pack:
            raise ValueError("retest_pack_id_required")
        try:
            normalized_day = int(day_index)
        except (TypeError, ValueError) as exc:
            raise ValueError("retest_day_index_invalid") from exc
        client_probe = str(probe_id or "").strip()
        client_mode = "review" if client_probe else requested_mode
        normalized_answers = _normalize_answers(answers)
        if not normalized_answers or len(normalized_answers) > 10:
            raise ValueError("retest_answer_count_invalid")
        normalized_selection = str(selection_id or "").strip()
        client_intent_id = client_probe if client_mode == "review" else str(training_intent_id or "").strip()
        legacy_request = {
            "completion_id": normalized_completion,
            "pack_id": normalized_pack,
            "mode": client_mode,
            "day_index": normalized_day,
            "selection_id": normalized_selection,
            "answers": normalized_answers,
            "training_intent_id": client_intent_id,
            "probe_id": client_probe,
        }
        legacy_request_hash = _request_hash(legacy_request)
        request_hash = _request_hash(
            {
                "selection_id": normalized_selection,
                "answers": normalized_answers,
            }
        )
        existing_events = self._events_for_completion(
            user_id=normalized_user,
            completion_id=normalized_completion,
        )
        terminal_rows = [
            event
            for event in existing_events
            if getattr(event, "payload_json", {}).get("completion_terminal") is True
        ]
        if terminal_rows and (
            len(terminal_rows) != 1
            or not all(is_canonical_luban_retest_terminal(event) for event in terminal_rows)
        ):
            raise RetestIdempotencyConflict(normalized_completion)
        existing_terminal = terminal_rows[0] if terminal_rows else None
        if existing_terminal is not None:
            terminal_payload = dict(getattr(existing_terminal, "payload_json", {}) or {})
            existing_hash = str(terminal_payload.get("request_hash") or "")
            hash_version = int(terminal_payload.get("request_hash_version") or 0)
            expected_hash = request_hash if hash_version == 3 else legacy_request_hash
            if existing_hash != expected_hash:
                raise RetestIdempotencyConflict(normalized_completion)
            if not any(
                getattr(event, "payload_json", {}).get("learning_signal_type") == "station_completed"
                for event in existing_events
            ):
                terminal_mode = "review" if str(terminal_payload.get("practice_mode") or "") == "review" else "forward"
                terminal_pack = str(terminal_payload.get("pack_id") or "").strip().upper()
                terminal_probe = str(terminal_payload.get("probe_id") or "").strip()
                terminal_intent = str(terminal_payload.get("training_intent_id") or "").strip()
                if terminal_pack != normalized_pack:
                    raise RetestIdempotencyConflict(normalized_completion)
                _require_rollout_enabled(terminal_mode)
                lesson = build_lesson_viewmodel(terminal_pack)
                station = record_learner_signal(
                    self._learner_state,
                    user_id=normalized_user,
                    signal_type="station_completed",
                    concept_id=terminal_pack,
                    concept_label=str(lesson.get("title") or terminal_pack),
                    completion_id=normalized_completion,
                    practice_mode=terminal_mode,
                    training_intent_id=terminal_intent,
                    probe_id=terminal_probe,
                )
                existing_events.append(station)
            return self._replay_result(existing_events, terminal=existing_terminal)

        self._assert_request_consistency(
            existing_events,
            completion_id=normalized_completion,
            request_hash=request_hash,
        )
        selection = decode_retest_selection(normalized_selection, user_id=normalized_user)
        if selection is None:
            raise ValueError("retest_selection_invalid")
        selection_pack = str(selection.get("pack_id") or "").strip().upper()
        normalized_mode = str(selection.get("mode") or "").strip()
        normalized_day = int(selection.get("day_index") or 0)
        normalized_probe = str(selection.get("probe_id") or "").strip()
        cycle_anchor = str(selection.get("cycle_anchor") or "").strip()
        selected_variant_ids = [str(item or "").strip() for item in list(selection.get("variant_ids") or [])]
        if selection_pack != normalized_pack or sorted(selected_variant_ids) != [
            item["variant_id"] for item in normalized_answers
        ]:
            raise ValueError("retest_selection_invalid")
        intent_id = normalized_probe if normalized_mode == "review" else str(training_intent_id or "").strip()
        # kind-aware 分派（单一权威红线）：按 selection token 的 supply_kind 决定
        # 供给 identity，绝不重跑路由决策。signed_variant-on-compiled = 变体探针
        # 消费（confirm/d1_probe），走 variant_probe_supply_identity（内含
        # resolve_variant_supply 绿灯签发闸）；否则维持 retest_supply_identity
        # （compiled_html 与 legacy signed-bank 路径逐字节不变）。
        selection_supply_kind = str(selection.get("supply_kind") or "").strip()
        is_variant_probe = (
            selection_supply_kind == "signed_variant"
            and is_compiled_practice_pack(selection_pack)
        )
        supply = (
            variant_probe_supply_identity(selection_pack)
            if is_variant_probe
            else retest_supply_identity(selection_pack, mode=normalized_mode)
        )
        if not verify_retest_selection(
            normalized_selection,
            user_id=normalized_user,
            pack_id=selection_pack,
            day_index=normalized_day,
            mode=normalized_mode,
            variant_ids=[item["variant_id"] for item in normalized_answers],
            supply_kind=supply.get("kind", ""),
            supply_digest=supply.get("digest", ""),
            probe_id=normalized_probe,
            cycle_anchor=cycle_anchor,
        ):
            raise ValueError("retest_selection_invalid")
        _require_rollout_enabled(normalized_mode)
        if normalized_mode == "review":
            due_probe = self._require_due_probe(
                user_id=normalized_user,
                pack_id=selection_pack,
                probe_id=normalized_probe,
            )
            if canonical_event_id(due_probe.get("cycle_anchor")) != canonical_event_id(
                cycle_anchor
            ):
                raise ValueError("retest_probe_cycle_mismatch")
        elif intent_id and not self._intent_matches_pack(
            user_id=normalized_user,
            training_intent_id=intent_id,
            pack_id=selection_pack,
        ):
            raise ValueError("retest_training_intent_mismatch")

        lesson = build_lesson_viewmodel(normalized_pack)
        if is_variant_probe:
            # 变体探针 canonical 解析同一分派：精确解析当前仍 eligible 的变体行；
            # 任一 id 缺失/漂移 → None → 视作空集 → answer_set_mismatch（fail-closed）。
            resolved = resolve_variant_probe_items(
                normalized_pack,
                [item["variant_id"] for item in normalized_answers],
            )
            canonical_items = resolved if resolved is not None else []
        else:
            canonical_items = resolve_retest_items(
                normalized_pack,
                variant_ids=[item["variant_id"] for item in normalized_answers],
                mode=normalized_mode,
            )
        canonical_by_id = {
            str(item.get("variant_id") or "").strip(): dict(item)
            for item in canonical_items
            if str(item.get("variant_id") or "").strip()
        }
        if set(canonical_by_id) != {item["variant_id"] for item in normalized_answers}:
            raise ValueError("retest_answer_set_mismatch")

        issued_roles = {
            str(item.get("probe_role") or "").strip()
            for item in canonical_items
        }
        immediate_confirm = (
            normalized_mode == "forward"
            and issued_roles == {"immediate_confirm"}
        )
        if immediate_confirm:
            confirm_facts = {
                str(item.get("fact_id") or "").strip()
                for item in canonical_items
                if str(item.get("fact_id") or "").strip()
            }
            parent_events = list(
                self._learner_state.list_memory_events(normalized_user, limit=None)
                or []
            )
            if not validate_immediate_confirm_parent(
                parent_events,
                pack_id=normalized_pack,
                parent_terminal_id=cycle_anchor,
                fact_ids=confirm_facts,
            ):
                raise ValueError("retest_confirm_parent_invalid")
        elif normalized_mode == "forward" and cycle_anchor:
            raise ValueError("retest_forward_cycle_anchor_invalid")

        title = str(lesson.get("title") or normalized_pack).strip()
        scored: list[dict[str, Any]] = []
        for answer in normalized_answers:
            canonical = canonical_by_id[answer["variant_id"]]
            if canonical.get("answer_type") == "single_choice":
                selected_option_id = str(answer.get("selected_option_id") or "").strip()
                if not selected_option_id or "choice_ok" in answer:
                    raise ValueError(
                        f"retest_single_choice_answer_required:{answer['variant_id']}"
                    )
                options = {
                    str(option.get("option_id") or ""): dict(option)
                    for option in canonical.get("options") or []
                    if str(option.get("option_id") or "")
                }
                selected = options.get(selected_option_id)
                if selected is None:
                    raise ValueError(
                        f"retest_selected_option_invalid:{answer['variant_id']}"
                    )
                correct = next(
                    (option for option in options.values() if option.get("is_correct") is True),
                    None,
                )
                if correct is None:
                    raise ValueError("retest_compiled_practice_answer_missing")
                scored.append(
                    {
                        **canonical,
                        "selected_option": selected,
                        "correct_option": correct,
                        "is_correct": bool(selected.get("is_correct")),
                        "scoring_authority": "compiled_html_server_rescore",
                    }
                )
                continue
            if "selected_option_id" in answer or not isinstance(answer.get("choice_ok"), bool):
                raise ValueError(f"retest_boolean_answer_required:{answer['variant_id']}")
            expected_ok = bool(canonical.get("expected_ok"))
            scored.append(
                {
                    **canonical,
                    "learner_choice_ok": bool(answer["choice_ok"]),
                    "is_correct": bool(answer["choice_ok"]) == expected_ok,
                    "scoring_authority": "signed_variant_server_rescore",
                }
            )

        correct_count = sum(1 for item in scored if item["is_correct"])
        score_ratio = correct_count / len(scored)
        phase = "transfer_case" if normalized_mode == "forward" else "verification_probe"
        result_status = "verified" if normalized_mode == "review" and score_ratio >= 1.0 else "not_verified"
        if normalized_mode == "review":
            claim = self._claim_review_probe(
                user_id=normalized_user,
                probe_id=normalized_probe,
                cycle_anchor=cycle_anchor,
                completion_id=normalized_completion,
                request_hash=request_hash,
            )
            claim_status = str(claim.get("status") or "")
            winner_completion = str(claim.get("completion_id") or "").strip()
            winner_hash = str(claim.get("request_hash") or "").strip()
            if claim_status == "conflict" or winner_hash != request_hash:
                raise RetestIdempotencyConflict(normalized_probe)
            if claim_status == "replay":
                try:
                    winner_events = self._events_for_completion(
                        user_id=normalized_user,
                        completion_id=winner_completion,
                        authoritative=True,
                    )
                except Exception as exc:
                    raise RetestCompletionInProgress(winner_completion) from exc
                winner_terminals = [
                    event
                    for event in winner_events
                    if getattr(event, "payload_json", {}).get("completion_terminal") is True
                    and is_canonical_luban_retest_terminal(event)
                    and str(getattr(event, "payload_json", {}).get("request_hash") or "")
                    == request_hash
                ]
                if not winner_terminals:
                    raise RetestCompletionInProgress(winner_completion)
                if len(winner_terminals) != 1:
                    raise RetestIdempotencyConflict(winner_completion)
                return self._replay_result(winner_events, terminal=winner_terminals[0])
            if claim_status != "acquired" or winner_completion != normalized_completion:
                raise RetestProbeClaimUnavailable(
                    "retest_probe_atomic_claim_invalid_response"
                )
        claim = self._learner_state.append_memory_event(
            normalized_user,
            source_feature=CLAIM_SOURCE_FEATURE,
            source_id=normalized_completion,
            memory_kind="learning_evidence",
            payload_json={
                "event_type": "retest_completion_claim",
                "retest_completion_id": normalized_completion,
                "request_hash": request_hash,
                "request_hash_version": 3,
                "pack_id": normalized_pack,
                "practice_mode": normalized_mode,
                "day_index": normalized_day,
                "variant_ids": [item["variant_id"] for item in normalized_answers],
                "probe_id": normalized_probe,
                "cycle_anchor": cycle_anchor,
            },
            dedupe_key=f"luban_retest_claim:{normalized_user}:{normalized_completion}",
        )
        if str(getattr(claim, "payload_json", {}).get("request_hash") or "") != request_hash:
            raise RetestIdempotencyConflict(normalized_completion)
        claimed_events = self._events_for_completion(
            user_id=normalized_user,
            completion_id=normalized_completion,
        )
        self._assert_request_consistency(
            claimed_events,
            completion_id=normalized_completion,
            request_hash=request_hash,
        )
        event_ids: list[str] = []
        public_items: list[dict[str, Any]] = []
        for item in scored:
            variant_id = str(item["variant_id"])
            is_correct = bool(item["is_correct"])
            rule_group = str(item.get("rule_group") or variant_id).strip()
            concept_id = f"pack:{normalized_pack}:rule:{rule_group}"
            promotion_allowed = normalized_mode == "review"
            is_single_choice = item.get("answer_type") == "single_choice"
            # 变体探针判断题（signed_variant-on-compiled）——canonical 行带 probe_role；
            # 据此附加错后诊断文案，legacy signed-bank 判断题（无 probe_role）不受影响。
            is_variant_probe_item = not is_single_choice and bool(item.get("probe_role"))
            selected_option = dict(item.get("selected_option") or {})
            correct_option = dict(item.get("correct_option") or {})
            scoring_authority = str(
                item.get("scoring_authority") or "signed_variant_server_rescore"
            )
            error_id = f"{concept_id}:{ERROR_CODE}"
            submission_id = f"{normalized_completion}:{variant_id}"
            typed_edges = [
                _edge("question_tests_concept", "question", variant_id, "concept", concept_id),
                _edge("submission_answered_question", "submission", submission_id, "question", variant_id),
            ]
            if is_correct:
                typed_edges.append(
                    _edge(
                        "training_improved_error",
                        "next_training",
                        intent_id or f"{normalized_pack}:practice",
                        "error",
                        error_id,
                    )
                )
            else:
                typed_edges.extend(
                    [
                        _edge("submission_triggered_error", "submission", submission_id, "error", error_id),
                        _edge(
                            "error_points_to_training",
                            "error",
                            error_id,
                            "next_training",
                            intent_id or f"{normalized_pack}:practice",
                        ),
                    ]
                )
            evidence_level = "L2_real_retest" if normalized_mode == "review" else ""
            payload = {
                "event_type": "learning_evidence",
                "evidence_source": SOURCE_FEATURE,
                "assessment_type": f"luban_{normalized_mode}_variant",
                "retest_completion_id": normalized_completion,
                "request_hash": request_hash,
                "request_hash_version": 3,
                "day_index": normalized_day,
                "practice_mode": normalized_mode,
                "pack_id": normalized_pack,
                "target_pack_id": normalized_pack,
                "probe_id": normalized_probe,
                "cycle_anchor": cycle_anchor,
                "question_id": variant_id,
                "source_question_id": variant_id,
                "answer_type": "single_choice" if is_single_choice else "boolean",
                "learner_answer": str(selected_option.get("option_id") or "")
                if is_single_choice
                else ("ok" if item["learner_choice_ok"] else "not_ok"),
                "correct_answer": str(correct_option.get("option_id") or "")
                if is_single_choice
                else ("ok" if bool(item.get("expected_ok")) else "not_ok"),
                "is_correct": is_correct,
                "knowledge_points": [f"{title} · {rule_group}"],
                "concept_id": concept_id,
                "concept_label": f"{title} · {rule_group}",
                "error_codes": [] if is_correct else [ERROR_CODE],
                "error_events": []
                if is_correct
                else [
                    {
                        "error_code": ERROR_CODE,
                        "concept_tag": concept_id,
                        "diagnosis": "用户选择与编译 HTML canonical option 不一致"
                        if is_single_choice
                        else "签发变体判断与 canonical expected_ok 不一致",
                    }
                ],
                "source_error_code": str(selected_option.get("source_error_code") or "")
                if is_single_choice and not is_correct
                else "",
                "answer_feedback": {
                    "correct_statement": str(item.get("model_answer") or ""),
                    "temptation": str(selected_option.get("temptation") or ""),
                    "loss_reason": str(selected_option.get("loss_reason") or ""),
                    "fix": str(selected_option.get("fix") or ""),
                }
                if is_single_choice
                else {
                    # 变体探针判断题：错后诊断文案逐字来自已签发 decision（无 fix
                    # 字段——不造）；legacy 判断题保持空 answer_feedback（零回归）。
                    "correct_statement": str(item.get("correct_statement") or ""),
                    "temptation": str(item.get("temptation") or ""),
                    "loss_reason": str(item.get("loss_reason") or ""),
                }
                if is_variant_probe_item
                else {},
                "score_awarded": 1.0 if is_correct else 0.0,
                "max_score": 1.0,
                "score_ratio": score_ratio,
                "measurement_confidence": "high_real_retest"
                if normalized_mode == "review"
                else ("medium_compiled_html" if is_single_choice else "medium_signed_variant"),
                "quality": {
                    "authority": scoring_authority,
                    "writeback_eligible": True,
                    "measurement_confidence": "high"
                    if normalized_mode == "review"
                    else "medium",
                    "evidence_level": evidence_level,
                },
                "claim_promotion_allowed": promotion_allowed,
                "official_score_allowed": False,
                "training_intent_id": intent_id,
                "prescription_phase": phase,
                "next_training_signal": {
                    "concept": concept_id,
                    "concept_label": f"{title} · {rule_group}",
                    "error_code": ERROR_CODE,
                    "target_error_code": ERROR_CODE,
                },
                "typed_edges": typed_edges,
                "source_refs": [
                    str(item.get("anchor") or ""),
                    (
                        f"compiled_html:{normalized_pack}:{item.get('source_html_sha256')}"
                        if is_single_choice
                        else f"signed_variant:{normalized_pack}:{variant_id}"
                    ),
                ],
            }
            # Additive provenance from the canonical issued item.  Compiled
            # anchor MCQs also carry fact_id/probe_role; persisting them lets
            # restart/cross-device projections determine whether a wrong fact
            # has a safe immediate-confirm supply without guessing from today’s
            # mutable catalog.  Historical rows without these fields remain
            # fail-closed.
            fact_id = str(item.get("fact_id") or "").strip()
            probe_role = str(item.get("probe_role") or "").strip()
            if fact_id:
                payload["fact_id"] = fact_id
            if probe_role:
                payload["probe_role"] = probe_role
            event = self._learner_state.append_memory_event(
                normalized_user,
                source_feature=SOURCE_FEATURE,
                source_id=submission_id,
                memory_kind="learning_evidence",
                payload_json=payload,
                dedupe_key=(
                    f"luban_retest_item:{normalized_user}:"
                    f"{normalized_completion}:{variant_id}"
                ),
            )
            existing_hash = str(getattr(event, "payload_json", {}).get("request_hash") or "")
            if existing_hash != request_hash:
                raise RetestIdempotencyConflict(normalized_completion)
            event_id = str(getattr(event, "event_id", "") or "")
            event_ids.append(event_id)
            public_item = {
                "variant_id": variant_id,
                "is_correct": is_correct,
                "event_id": event_id,
            }
            if is_single_choice:
                public_item.update(
                    {
                        "selected_option_id": str(selected_option.get("option_id") or ""),
                        "correct_option_id": str(correct_option.get("option_id") or ""),
                        "correct_statement": str(item.get("model_answer") or ""),
                        "feedback": dict(payload["answer_feedback"]),
                    }
                )
            elif is_variant_probe_item:
                public_item.update(
                    {
                        "correct_statement": str(item.get("correct_statement") or ""),
                        "feedback": dict(payload["answer_feedback"]),
                    }
                )
            public_items.append(public_item)

        completion_authority = (
            "compiled_html_server_rescore"
            if scored and all(item.get("answer_type") == "single_choice" for item in scored)
            else "signed_variant_server_rescore"
        )

        terminal_payload = {
            "event_type": "learning_evidence",
            "evidence_source": SOURCE_FEATURE,
            "assessment_type": f"luban_{normalized_mode}_completion",
            "retest_completion_id": normalized_completion,
            "completion_terminal": True,
            "request_hash": request_hash,
            "request_hash_version": 3,
            "day_index": normalized_day,
            "practice_mode": normalized_mode,
            "pack_id": normalized_pack,
            "target_pack_id": normalized_pack,
            "probe_id": normalized_probe,
            "cycle_anchor": cycle_anchor,
            "score_awarded": float(correct_count),
            "max_score": float(len(scored)),
            "score_ratio": score_ratio,
            "claim_promotion_allowed": normalized_mode == "review",
            "official_score_allowed": False,
            "training_intent_id": intent_id,
            "prescription_phase": phase,
            "prescription_result": {"status": result_status, "score_ratio": score_ratio},
            "item_event_refs": list(event_ids),
            "quality": {
                "authority": completion_authority,
                "writeback_eligible": True,
                "progress_countable": False,
                "measurement_confidence": "high" if normalized_mode == "review" else "medium",
                "evidence_level": "L2_real_retest" if normalized_mode == "review" else "L0_observed",
            },
        }
        terminal = self._learner_state.append_memory_event(
            normalized_user,
            source_feature=SOURCE_FEATURE,
            source_id=f"{normalized_completion}:terminal",
            memory_kind="learning_evidence",
            payload_json=terminal_payload,
            dedupe_key=f"luban_retest_terminal:{normalized_user}:{normalized_completion}",
        )
        if str(getattr(terminal, "payload_json", {}).get("request_hash") or "") != request_hash:
            raise RetestIdempotencyConflict(normalized_completion)
        if not is_canonical_luban_retest_terminal(terminal):
            raise RetestIdempotencyConflict(normalized_completion)
        terminal_event_id = str(getattr(terminal, "event_id", "") or "")
        event_ids.append(terminal_event_id)

        station = record_learner_signal(
            self._learner_state,
            user_id=normalized_user,
            signal_type="station_completed",
            concept_id=normalized_pack,
            concept_label=title,
            completion_id=normalized_completion,
            practice_mode=normalized_mode,
            training_intent_id=intent_id,
            probe_id=normalized_probe,
        )
        change = _learning_change_status(mode=normalized_mode, score_ratio=score_ratio)
        return {
            "completion_id": normalized_completion,
            "pack_id": normalized_pack,
            "mode": normalized_mode,
            "sync_status": "synced",
            "score": {"correct_count": correct_count, "question_count": len(scored)},
            "items": public_items,
            "learning_event_refs": event_ids,
            "terminal_event_id": terminal_event_id,
            "station_event_id": str(getattr(station, "event_id", "") or ""),
            "learning_change": {
                "status": change,
                "authority": "learner_memory_events -> learning_synthesis",
                "reason": completion_authority,
            },
        }

    def _events_for_completion(
        self,
        *,
        user_id: str,
        completion_id: str,
        authoritative: bool = False,
    ) -> list[Any]:
        reader_name = (
            "list_retest_completion_events_authoritative"
            if authoritative
            else "list_memory_events"
        )
        reader = getattr(self._learner_state, reader_name, None)
        if not callable(reader):
            return []
        if authoritative:
            return list(reader(user_id, completion_id) or [])
        return [
            event
            for event in list(reader(user_id, limit=None) or [])
            if str(getattr(event, "payload_json", {}).get("retest_completion_id") or "").strip()
            == completion_id
            or (
                getattr(event, "payload_json", {}).get("learning_signal_type") == "station_completed"
                and str(getattr(event, "payload_json", {}).get("completion_id") or "").strip()
                == completion_id
            )
        ]

    def _claim_review_probe(
        self,
        *,
        user_id: str,
        probe_id: str,
        cycle_anchor: str,
        completion_id: str,
        request_hash: str,
    ) -> dict[str, Any]:
        claimer = getattr(self._learner_state, "claim_retest_probe", None)
        if not callable(claimer):
            raise RetestProbeClaimUnavailable(
                "retest_probe_atomic_authority_unavailable"
            )
        try:
            result = claimer(
                user_id=user_id,
                probe_id=probe_id,
                cycle_anchor=cycle_anchor,
                completion_id=completion_id,
                request_hash=request_hash,
            )
        except RetestProbeClaimUnavailable:
            raise
        except Exception as exc:
            raise RetestProbeClaimUnavailable(
                "retest_probe_atomic_authority_unavailable"
            ) from exc
        if not isinstance(result, dict):
            raise RetestProbeClaimUnavailable(
                "retest_probe_atomic_claim_invalid_response"
            )
        return dict(result)

    @staticmethod
    def _assert_request_consistency(
        events: list[Any], *, completion_id: str, request_hash: str
    ) -> None:
        bound_hashes: list[str] = []
        for event in events:
            payload = dict(getattr(event, "payload_json", {}) or {})
            if getattr(event, "source_feature", "") == CLAIM_SOURCE_FEATURE:
                bound_hashes.append(str(payload.get("request_hash") or ""))
                continue
            if (
                getattr(event, "source_feature", "") == SOURCE_FEATURE
                and payload.get("event_type") == "learning_evidence"
                and payload.get("completion_terminal") is not True
            ):
                bound_hashes.append(str(payload.get("request_hash") or ""))
        if bound_hashes and (
            any(not item for item in bound_hashes)
            or set(bound_hashes) != {request_hash}
        ):
            raise RetestIdempotencyConflict(completion_id)

    def _replay_result(self, events: list[Any], *, terminal: Any) -> dict[str, Any]:
        if not is_canonical_luban_retest_terminal(terminal):
            completion_id = str(
                getattr(terminal, "payload_json", {}).get("retest_completion_id") or ""
            )
            raise RetestIdempotencyConflict(completion_id)
        terminal_payload = dict(getattr(terminal, "payload_json", {}) or {})
        correct_count = int(float(terminal_payload.get("score_awarded") or 0))
        question_count = int(float(terminal_payload.get("max_score") or 0))
        request_hash = str(terminal_payload.get("request_hash") or "")
        item_events = canonical_retest_item_events(events, terminal=terminal)
        if not request_hash or item_events is None:
            raise RetestIdempotencyConflict(
                str(terminal_payload.get("retest_completion_id") or "")
            )
        item_refs = [str(getattr(event, "event_id", "") or "") for event in item_events]
        mode = str(terminal_payload.get("practice_mode") or "forward")
        station = next(
            (event for event in events if getattr(event, "payload_json", {}).get("learning_signal_type") == "station_completed"),
            None,
        )
        terminal_id = str(getattr(terminal, "event_id", "") or "")
        return {
            "completion_id": str(terminal_payload.get("retest_completion_id") or ""),
            "pack_id": str(terminal_payload.get("pack_id") or ""),
            "mode": mode,
            "sync_status": "synced",
            "score": {"correct_count": correct_count, "question_count": question_count},
            "items": [self._replay_public_item(event) for event in item_events],
            "learning_event_refs": [*item_refs, terminal_id],
            "terminal_event_id": terminal_id,
            "station_event_id": str(getattr(station, "event_id", "") or ""),
            "learning_change": {
                "status": _learning_change_status(mode=mode, score_ratio=(correct_count / question_count) if question_count else 0.0),
                "authority": "learner_memory_events -> learning_synthesis",
                "reason": str(
                    (terminal_payload.get("quality") or {}).get("authority")
                    or "signed_variant_server_rescore"
                ),
            },
        }

    @staticmethod
    def _replay_public_item(event: Any) -> dict[str, Any]:
        payload = dict(getattr(event, "payload_json", {}) or {})
        item = {
            "variant_id": str(payload.get("question_id") or ""),
            "is_correct": bool(payload.get("is_correct")),
            "event_id": str(getattr(event, "event_id", "") or ""),
        }
        if payload.get("answer_type") == "single_choice":
            feedback = dict(payload.get("answer_feedback") or {})
            item.update(
                {
                    "selected_option_id": str(payload.get("learner_answer") or ""),
                    "correct_option_id": str(payload.get("correct_answer") or ""),
                    "correct_statement": str(feedback.get("correct_statement") or ""),
                    "feedback": feedback,
                }
            )
        elif payload.get("probe_role"):
            # 变体探针判断题 replay：从持久化 payload 复原错后诊断文案。
            feedback = dict(payload.get("answer_feedback") or {})
            item.update(
                {
                    "correct_statement": str(feedback.get("correct_statement") or ""),
                    "feedback": feedback,
                }
            )
        return item

    def _require_due_probe(self, *, user_id: str, pack_id: str, probe_id: str) -> dict[str, Any]:
        if not probe_id:
            raise ValueError("retest_probe_id_required")
        if self._review_probe_resolver is not None:
            due = self._review_probe_resolver(user_id=user_id, pack_id=pack_id, probe_id=probe_id)
            if due:
                return dict(due)
            raise ValueError("retest_probe_not_due")
        if self._review_exam_date_resolver is None:
            raise ReviewHorizonUnavailable("member_profile_resolver_required")
        events = list(self._learner_state.list_memory_events(user_id, limit=None) or [])
        projection = build_review_due_projection(
            user_id=user_id,
            events=events,
            now_iso=datetime.now(timezone.utc).isoformat(),
            exam_date_iso=str(self._review_exam_date_resolver(user_id) or "").strip(),
        )
        due = resolve_due_review_probe(
            projection,
            pack_id=pack_id,
            probe_id=probe_id,
        )
        if due is not None:
            return due
        raise ValueError("retest_probe_not_due")

    def _intent_matches_pack(self, *, user_id: str, training_intent_id: str, pack_id: str) -> bool:
        if self._training_intent_validator is not None:
            return bool(self._training_intent_validator(
                user_id=user_id,
                training_intent_id=training_intent_id,
                pack_id=pack_id,
            ))
        events = list(self._learner_state.list_memory_events(user_id, limit=None) or [])
        return any(
            str(getattr(event, "payload_json", {}).get("training_intent_id") or "").strip()
            == training_intent_id
            and str(getattr(event, "payload_json", {}).get("target_pack_id") or "").strip().upper()
            == pack_id
            for event in events
        )


__all__ = [
    "ERROR_CODE",
    "RetestCompletionInProgress",
    "RetestIdempotencyConflict",
    "RetestProbeClaimUnavailable",
    "RetestWritebackService",
]
