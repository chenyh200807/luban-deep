from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from typing import Any

from deeptutor.services.learner_state.evidence_lifecycle import (
    is_canonical_luban_retest_terminal,
)
from deeptutor.services.learner_state.learner_signal import record_learner_signal
from deeptutor.services.luban_lesson.read_model import (
    build_lesson_viewmodel,
    resolve_retest_items,
    retest_supply_identity,
)
from deeptutor.services.luban_lesson.retest_selection import verify_retest_selection
from deeptutor.services.luban_lesson.review_due import build_review_due_projection

SOURCE_FEATURE = "assessment_testset"
CLAIM_SOURCE_FEATURE = "luban_retest_claim"
ERROR_CODE = "unknown_error"
_REVIEW_FLAG = "LUBAN_REVIEW_MODULE_ENABLED"
_LIGHT_PRACTICE_FLAG = "LUBAN_LIGHT_PRACTICE_ENABLED"


class RetestIdempotencyConflict(RuntimeError):
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
        training_intent_validator: Any | None = None,
    ) -> None:
        self._learner_state = learner_state_service
        self._review_probe_resolver = review_probe_resolver
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
        normalized_probe = str(probe_id or "").strip()
        normalized_mode = "review" if normalized_probe else requested_mode
        normalized_answers = _normalize_answers(answers)
        if not normalized_answers or len(normalized_answers) > 10:
            raise ValueError("retest_answer_count_invalid")
        normalized_selection = str(selection_id or "").strip()
        intent_id = normalized_probe if normalized_mode == "review" else str(training_intent_id or "").strip()
        canonical_request = {
            "completion_id": normalized_completion,
            "pack_id": normalized_pack,
            "mode": normalized_mode,
            "day_index": normalized_day,
            "selection_id": normalized_selection,
            "answers": normalized_answers,
            "training_intent_id": intent_id,
            "probe_id": normalized_probe,
        }
        request_hash = _request_hash(canonical_request)
        existing_events = self._events_for_completion(
            user_id=normalized_user,
            completion_id=normalized_completion,
        )
        self._assert_request_consistency(
            existing_events,
            completion_id=normalized_completion,
            request_hash=request_hash,
        )
        terminal_rows = [
            event
            for event in existing_events
            if getattr(event, "payload_json", {}).get("completion_terminal") is True
        ]
        if terminal_rows and not all(
            is_canonical_luban_retest_terminal(event) for event in terminal_rows
        ):
            raise RetestIdempotencyConflict(normalized_completion)
        existing_terminal = terminal_rows[0] if terminal_rows else None
        if existing_terminal is not None:
            existing_hash = str(getattr(existing_terminal, "payload_json", {}).get("request_hash") or "")
            if existing_hash != request_hash:
                raise RetestIdempotencyConflict(normalized_completion)
            if not any(
                getattr(event, "payload_json", {}).get("learning_signal_type") == "station_completed"
                for event in existing_events
            ):
                _require_rollout_enabled(normalized_mode)
                lesson = build_lesson_viewmodel(normalized_pack)
                station = record_learner_signal(
                    self._learner_state,
                    user_id=normalized_user,
                    signal_type="station_completed",
                    concept_id=normalized_pack,
                    concept_label=str(lesson.get("title") or normalized_pack),
                    completion_id=normalized_completion,
                    practice_mode=normalized_mode,
                    training_intent_id=intent_id,
                    probe_id=normalized_probe,
                )
                existing_events.append(station)
            return self._replay_result(existing_events, terminal=existing_terminal)
        supply = retest_supply_identity(normalized_pack, mode=normalized_mode)
        if not verify_retest_selection(
            normalized_selection,
            user_id=normalized_user,
            pack_id=normalized_pack,
            day_index=normalized_day,
            mode=normalized_mode,
            variant_ids=[item["variant_id"] for item in normalized_answers],
            supply_kind=supply.get("kind", ""),
            supply_digest=supply.get("digest", ""),
        ):
            raise ValueError("retest_selection_invalid")
        _require_rollout_enabled(normalized_mode)
        if normalized_mode == "review":
            self._require_due_probe(
                user_id=normalized_user,
                pack_id=normalized_pack,
                probe_id=normalized_probe,
            )
        elif intent_id and not self._intent_matches_pack(
            user_id=normalized_user,
            training_intent_id=intent_id,
            pack_id=normalized_pack,
        ):
            raise ValueError("retest_training_intent_mismatch")

        lesson = build_lesson_viewmodel(normalized_pack)
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
        claim = self._learner_state.append_memory_event(
            normalized_user,
            source_feature=CLAIM_SOURCE_FEATURE,
            source_id=normalized_completion,
            memory_kind="learning_evidence",
            payload_json={
                "event_type": "retest_completion_claim",
                "retest_completion_id": normalized_completion,
                "request_hash": request_hash,
                "pack_id": normalized_pack,
                "practice_mode": normalized_mode,
                "day_index": normalized_day,
                "variant_ids": [item["variant_id"] for item in normalized_answers],
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
                "day_index": normalized_day,
                "practice_mode": normalized_mode,
                "pack_id": normalized_pack,
                "target_pack_id": normalized_pack,
                "probe_id": normalized_probe,
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
            "day_index": normalized_day,
            "practice_mode": normalized_mode,
            "pack_id": normalized_pack,
            "target_pack_id": normalized_pack,
            "probe_id": normalized_probe,
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

    def _events_for_completion(self, *, user_id: str, completion_id: str) -> list[Any]:
        reader = getattr(self._learner_state, "list_memory_events", None)
        if not callable(reader):
            return []
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
        item_refs = [str(item or "") for item in terminal_payload.get("item_event_refs") or []]
        by_event_id = {
            str(getattr(event, "event_id", "") or ""): event
            for event in events
            if str(getattr(event, "event_id", "") or "")
        }
        item_events = [by_event_id.get(event_id) for event_id in item_refs]
        if (
            not request_hash
            or len(item_refs) != question_count
            or len(set(item_refs)) != question_count
            or any(event is None for event in item_events)
            or any(
                getattr(event, "source_feature", "") != SOURCE_FEATURE
                or getattr(event, "payload_json", {}).get("event_type") != "learning_evidence"
                or getattr(event, "payload_json", {}).get("completion_terminal") is True
                or str(getattr(event, "payload_json", {}).get("request_hash") or "")
                != request_hash
                for event in item_events
                if event is not None
            )
            or sum(
                bool(getattr(event, "payload_json", {}).get("is_correct"))
                for event in item_events
                if event is not None
            )
            != correct_count
        ):
            raise RetestIdempotencyConflict(
                str(terminal_payload.get("retest_completion_id") or "")
            )
        item_events = [event for event in item_events if event is not None]
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
        return item

    def _require_due_probe(self, *, user_id: str, pack_id: str, probe_id: str) -> dict[str, Any]:
        if not probe_id:
            raise ValueError("retest_probe_id_required")
        if self._review_probe_resolver is not None:
            due = self._review_probe_resolver(user_id=user_id, pack_id=pack_id, probe_id=probe_id)
            if due:
                return dict(due)
            raise ValueError("retest_probe_not_due")
        events = list(self._learner_state.list_memory_events(user_id, limit=None) or [])
        projection = build_review_due_projection(
            user_id=user_id,
            events=events,
            now_iso=datetime.now(timezone.utc).isoformat(),
        )
        for item in list(projection.get("due") or []):
            if not isinstance(item, dict):
                continue
            if (
                str(item.get("pack_id") or "").strip().upper() == pack_id
                and str(item.get("probe_id") or "").strip() == probe_id
                and item.get("retest_available") is True
            ):
                return dict(item)
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
    "RetestIdempotencyConflict",
    "RetestWritebackService",
]
