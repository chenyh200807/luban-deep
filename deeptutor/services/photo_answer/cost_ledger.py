"""Session cost ledger: the single budget authority of the photo-answer layer.

Plan §3.3 (v3, Codex C1):
- units are micros (1 元 = 1_000_000);
- every paid action goes through reserve -> settle/refund — there is no
  call path that spends provider money outside this ledger;
- the "auto" channel is capped by the session soft cap;
- the "user_escalation" channel (user-triggered re-recognition) may break
  the soft cap once per session, bounded by the hard cap.

Concurrency: all checks run inside a single `begin immediate` SQLite
transaction so concurrent reserves serialize instead of double-spending.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from deeptutor.services.photo_answer.models import PhotoAnswerError
from deeptutor.services.photo_answer.store import PhotoAnswerStore

AUTO = "auto"
USER_ESCALATION = "user_escalation"


class BudgetExceeded(PhotoAnswerError):
    """The reservation would push the session over its budget cap."""


class EscalationLimitReached(PhotoAnswerError):
    """user_escalation is allowed once per session (plan §3.3)."""


class CostLedger:
    def __init__(self, store: PhotoAnswerStore) -> None:
        self._store = store

    # ---------- queries ----------

    def spent_micros(self, session_id: str) -> int:
        with self._store.connect() as conn:
            row = conn.execute(
                "select coalesce(sum(actual_micros),0) from photo_answer_cost_entries"
                " where session_id=? and state='settled'",
                (session_id,),
            ).fetchone()
        return int(row[0])

    def reserved_micros(self, session_id: str) -> int:
        with self._store.connect() as conn:
            row = conn.execute(
                "select coalesce(sum(reserved_micros),0) from photo_answer_cost_entries"
                " where session_id=? and state='reserved'",
                (session_id,),
            ).fetchone()
        return int(row[0])

    def list_entries(self, session_id: str) -> list[dict[str, Any]]:
        with self._store.connect() as conn:
            rows = conn.execute(
                "select * from photo_answer_cost_entries where session_id=? order by created_at",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- reserve / settle / refund ----------

    def reserve(
        self,
        session_id: str,
        *,
        amount_micros: int,
        channel: str,
        note: str = "",
        now: float | None = None,
    ) -> str:
        if channel not in (AUTO, USER_ESCALATION):
            raise ValueError(f"Unknown ledger channel: {channel}")
        amount = int(amount_micros)
        if amount <= 0:
            raise ValueError("Reservation amount must be positive micros")
        ts = float(now if now is not None else time.time())
        entry_id = f"pal-{uuid.uuid4().hex}"
        with self._store.connect() as conn:
            conn.execute("begin immediate")
            session = conn.execute(
                "select cost_budget_soft_micros, cost_budget_hard_micros"
                " from photo_answer_sessions where id=?",
                (session_id,),
            ).fetchone()
            if session is None:
                raise KeyError(f"Unknown session {session_id}")
            committed = conn.execute(
                "select"
                "  coalesce(sum(case when state='settled' then actual_micros else 0 end),0),"
                "  coalesce(sum(case when state='reserved' then reserved_micros else 0 end),0)"
                " from photo_answer_cost_entries where session_id=?",
                (session_id,),
            ).fetchone()
            in_flight = int(committed[0]) + int(committed[1])
            if channel == USER_ESCALATION:
                used = conn.execute(
                    "select count(*) from photo_answer_cost_entries"
                    " where session_id=? and channel=? and state in ('reserved','settled')",
                    (session_id, USER_ESCALATION),
                ).fetchone()[0]
                if int(used) >= 1:
                    raise EscalationLimitReached(
                        "user_escalation already used for this session"
                    )
                cap = int(session["cost_budget_hard_micros"])
            else:
                cap = int(session["cost_budget_soft_micros"])
            if in_flight + amount > cap:
                raise BudgetExceeded(
                    f"Reservation {amount} micros over {channel} cap"
                    f" ({in_flight}+{amount} > {cap})"
                )
            conn.execute(
                """
                insert into photo_answer_cost_entries
                  (id, session_id, channel, state, reserved_micros, actual_micros,
                   note, created_at, updated_at)
                values (?,?,?, 'reserved', ?, 0, ?, ?, ?)
                """,
                (entry_id, session_id, channel, amount, note, ts, ts),
            )
        return entry_id

    def settle(
        self,
        entry_id: str,
        *,
        actual_micros: int,
        provider_usage_id: str = "",
        now: float | None = None,
    ) -> None:
        ts = float(now if now is not None else time.time())
        with self._store.connect() as conn:
            conn.execute("begin immediate")
            row = conn.execute(
                "select state from photo_answer_cost_entries where id=?", (entry_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown ledger entry {entry_id}")
            if str(row["state"]) != "reserved":
                # Idempotent replay of a settled entry is a no-op; settling a
                # refunded entry is a programming error worth surfacing.
                if str(row["state"]) == "settled":
                    return
                raise PhotoAnswerError(f"Cannot settle entry in state {row['state']}")
            conn.execute(
                """
                update photo_answer_cost_entries
                set state='settled', actual_micros=?, provider_usage_id=?, updated_at=?
                where id=?
                """,
                (int(actual_micros), provider_usage_id, ts, entry_id),
            )

    def refund(self, entry_id: str, *, now: float | None = None) -> None:
        ts = float(now if now is not None else time.time())
        with self._store.connect() as conn:
            conn.execute("begin immediate")
            row = conn.execute(
                "select state from photo_answer_cost_entries where id=?", (entry_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown ledger entry {entry_id}")
            if str(row["state"]) != "reserved":
                if str(row["state"]) == "refunded":
                    return
                raise PhotoAnswerError(f"Cannot refund entry in state {row['state']}")
            conn.execute(
                "update photo_answer_cost_entries set state='refunded', updated_at=? where id=?",
                (ts, entry_id),
            )
