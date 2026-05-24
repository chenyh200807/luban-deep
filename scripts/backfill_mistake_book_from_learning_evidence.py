#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deeptutor.services.construction_grading.writeback import (
    _is_mistake_book_candidate,
    _mistake_book_concept,
    _mistake_book_error_label,
    _mistake_book_note,
    _mistake_book_subject_id,
    _mistake_book_tags,
    _mistake_book_title,
)
from deeptutor.services.learner_state.attempt_refs import sign_attempt_ref
from deeptutor.services.learner_state.mistake_book import MistakeBookService, SupabaseMistakeBookStore


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _service_key() -> str:
    return str(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or "").strip()


def _rest_headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }


def fetch_learning_evidence_rows(
    *,
    base_url: str,
    service_key: str,
    user_ids: set[str] | None,
    limit: int | None,
    page_size: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    normalized_limit = None if limit is None or limit < 0 else int(limit)
    with httpx.Client(timeout=30.0) as client:
        while True:
            remaining = None if normalized_limit is None else max(normalized_limit - len(rows), 0)
            if remaining == 0:
                break
            batch_limit = min(page_size, remaining) if remaining is not None else page_size
            params: dict[str, Any] = {
                "select": "event_id,user_id,source_bot_id,memory_kind,payload_json,created_at",
                "memory_kind": "eq.learning_evidence",
                "order": "created_at.asc",
                "limit": batch_limit,
                "offset": offset,
            }
            if user_ids and len(user_ids) == 1:
                params["user_id"] = f"eq.{next(iter(user_ids))}"
            response = client.get(
                f"{base_url.rstrip('/')}/rest/v1/learner_memory_events",
                headers=_rest_headers(service_key),
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
            raw_batch = [dict(item) for item in payload if isinstance(item, dict)]
            batch = list(raw_batch)
            if user_ids and len(user_ids) > 1:
                batch = [row for row in batch if str(row.get("user_id") or "").strip() in user_ids]
            rows.extend(batch)
            if len(raw_batch) < batch_limit:
                break
            offset += batch_limit
    return rows


def build_mistake_book_payload(row: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    user_id = str(row.get("user_id") or "").strip()
    event_id = str(row.get("event_id") or "").strip()
    payload_json = row.get("payload_json") if isinstance(row.get("payload_json"), dict) else {}
    source_bot_id = str(row.get("source_bot_id") or "").strip()
    if not user_id:
        return None, "missing_user_id"
    if not event_id:
        return None, "missing_event_id"
    if not _is_mistake_book_candidate(payload_json):
        return None, "not_wrong_attempt"
    try:
        attempt_ref = sign_attempt_ref(
            user_id=user_id,
            event_id=event_id,
            question_id=str(payload_json.get("question_id") or "").strip(),
        )
    except Exception:
        return None, "invalid_attempt_ref"
    return {
        "user_id": user_id,
        "attempt_ref": attempt_ref,
        "subject_id": _mistake_book_subject_id(payload_json=payload_json, source_bot_id=source_bot_id),
        "bot_id": source_bot_id,
        "title": _mistake_book_title(payload_json),
        "concept_label": _mistake_book_concept(payload_json),
        "error_label": _mistake_book_error_label(payload_json),
        "note": _mistake_book_note(payload_json),
        "tags": _mistake_book_tags(payload_json),
        "event_id": event_id,
    }, "candidate"


def backfill_rows(
    rows: Iterable[dict[str, Any]],
    *,
    store: Any,
    service: Any,
    apply: bool,
    restore_archived: bool,
    sample_limit: int = 20,
) -> dict[str, Any]:
    summary: Counter[str] = Counter()
    per_user: dict[str, Counter[str]] = defaultdict(Counter)
    samples: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for row in rows:
        summary["seen"] += 1
        payload, status = build_mistake_book_payload(row)
        if payload is None:
            summary[f"skipped_{status}"] += 1
            continue
        user_id = str(payload["user_id"])
        event_id = str(payload["event_id"])
        per_user[user_id]["candidates"] += 1
        current = store.get_item(user_id, event_id)
        if current and current.get("archived_at") and not restore_archived:
            summary["existing_archived_skipped"] += 1
            per_user[user_id]["existing_archived_skipped"] += 1
            action = "skip_archived"
        elif current and not current.get("archived_at"):
            summary["existing_active_skipped"] += 1
            per_user[user_id]["existing_active_skipped"] += 1
            action = "skip_existing"
        else:
            action = "insert"
            if apply:
                try:
                    service.save_item(
                        user_id=user_id,
                        attempt_ref=str(payload["attempt_ref"]),
                        subject_id=str(payload["subject_id"]),
                        bot_id=str(payload["bot_id"]),
                        title=str(payload["title"]),
                        concept_label=str(payload["concept_label"]),
                        error_label=str(payload["error_label"]),
                        note=str(payload["note"]),
                        tags=list(payload["tags"] or []),
                    )
                except Exception as exc:
                    summary["write_errors"] += 1
                    per_user[user_id]["write_errors"] += 1
                    errors.append({"user_id": user_id, "event_id": event_id, "error": str(exc)})
                    action = "write_error"
                else:
                    summary["inserted"] += 1
                    per_user[user_id]["inserted"] += 1
            else:
                summary["would_insert"] += 1
                per_user[user_id]["would_insert"] += 1
        if len(samples) < sample_limit:
            samples.append({
                "action": action,
                "user_id": user_id,
                "event_id": event_id,
                "title": str(payload["title"]),
                "concept_label": str(payload["concept_label"]),
                "error_label": str(payload["error_label"]),
            })
    return {
        "ok": summary.get("write_errors", 0) == 0,
        "apply": bool(apply),
        "restore_archived": bool(restore_archived),
        "summary": dict(summary),
        "users": {user_id: dict(counter) for user_id, counter in sorted(per_user.items())},
        "samples": samples,
        "errors": errors[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill learner_mistake_book_items from historical learning_evidence.")
    parser.add_argument("--user-id", action="append", default=[], help="Backfill one user. Repeatable.")
    parser.add_argument("--all-users", action="store_true", help="Scan all users in learner_memory_events.")
    parser.add_argument("--apply", action="store_true", help="Write rows. Default is dry-run.")
    parser.add_argument("--restore-archived", action="store_true", help="Re-add rows the user previously removed. Off by default.")
    parser.add_argument("--limit", type=int, default=None, help="Max learning_evidence rows to scan.")
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--env-file", default=str(PROJECT_ROOT / ".env"))
    args = parser.parse_args()

    user_ids = {str(item or "").strip() for item in list(args.user_id or []) if str(item or "").strip()}
    if args.all_users and user_ids:
        raise SystemExit("Use either --all-users or --user-id, not both.")
    if not args.all_users and not user_ids:
        raise SystemExit("Provide --user-id <id> or --all-users. Default mode is dry-run; add --apply to write.")
    _load_dotenv(Path(args.env_file))
    base_url = str(os.getenv("SUPABASE_URL") or "").strip()
    key = _service_key()
    if not base_url or not key:
        raise SystemExit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY/SUPABASE_KEY are required.")
    rows = fetch_learning_evidence_rows(
        base_url=base_url,
        service_key=key,
        user_ids=None if args.all_users else user_ids,
        limit=args.limit,
        page_size=max(1, int(args.page_size or 500)),
    )
    result = backfill_rows(
        rows,
        store=SupabaseMistakeBookStore(base_url=base_url, service_key=key),
        service=MistakeBookService(store=SupabaseMistakeBookStore(base_url=base_url, service_key=key)),
        apply=bool(args.apply),
        restore_archived=bool(args.restore_archived),
    )
    result["mode"] = "apply" if args.apply else "dry_run"
    result["user_filter"] = sorted(user_ids) if user_ids else "all"
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
