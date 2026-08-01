"""Same-question-same-answer FINAL grading-result cache (store + key authority).

WHY THIS EXISTS (codex 判分核不变量审计 §3.1/§3.2, I-11/I-12): tier-2/tier-3 scoring points are
LLM-generated and the per-point verdict has no cross-time determinism contract from the provider —
``temperature=0`` only lowers variance. So "同题同答同分" cannot be proven by input normalization
alone; it has to be MADE true by caching the FINAL graded event and replaying it.

WHAT THIS MODULE IS: the store + the key authority ONLY. The single cache SEAM lives inside
``rubric_grader_v1.grade_with_batch_judge_async`` (never in render / TutorBot / wrapper layers), so
there is exactly one place where a cached score can enter the system.

HARD RULES (audit §3.3 risk list, one guard each):
  1. 稳定错误 — a cache only makes the FIRST result sticky; it never makes it more correct. This
     module is only allowed to run after coverage/cap/authority are fixed upstream.
  2. 失效不完整 — EVERY authority/version fact is in the key (rubric digest, nominal, coverage state,
     scope cap, provenance, bank slot + content hash, extraction/adjudication prompt versions, model,
     provider binding, grader algorithm version, normalization-policy version). TTL is NOT versioning.
  3. 多 worker — the shared Valkey backend makes the cache cross-worker. No distributed lock: two
     workers racing the same key both write the SAME idempotent value, so last-write-wins is correct
     (a "single-flight" would only save duplicate LLM spend, not protect correctness).
  4. 隐私 — the key is a sha256 (the raw answer never leaves the process); the stored value has
     student_id / session_id / trace_id stripped and is re-bound to the CURRENT turn's identity on hit.
  5. 规范化过度 — normalization is deliberately conservative (NFKC + newline unification + outer strip
     only; interior whitespace is answer semantics) and its policy string is IN the key, so tightening
     it later invalidates rather than silently re-binds old entries.
  6. degraded/unknown — refused by ``is_cacheable_event``: a transient outage must never be frozen
     into a low/zero score.

Env (all registered in contracts/env_registry.yaml):
  LUBAN_GRADING_RESULT_CACHE              kill switch, DEFAULT ON ("0/false/off/no" disables)
  LUBAN_GRADING_RESULT_CACHE_URL          Valkey/Redis URL; unset -> falls back to the shared
                                          rate-limit Valkey (only when DEEPTUTOR_RATE_LIMIT_BACKEND=redis),
                                          else degrades to a per-process dict + TTL
  LUBAN_GRADING_RESULT_CACHE_TTL_SECONDS  default 86400 (0 disables writes)
  LUBAN_GRADING_RESULT_CACHE_MAX_ENTRIES  in-process fallback cap only (default 512)
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import time
from typing import Any
import unicodedata

logger = logging.getLogger(__name__)

# Bump ANY of these when its subject changes; every one is a key component, so a bump is a
# deterministic, total invalidation of the affected entries (TTL is not an invalidation mechanism).
CACHE_KEY_VERSION = "grading_result_cache.v1"
#: Student-answer normalization policy version. Bump when ``normalize_student_answer`` changes.
ANSWER_NORMALIZATION_VERSION = "answer_norm.v1"

_REDIS_KEY_PREFIX = "luban:grading_result"
#: Identity/telemetry fields that must NEVER be served from cache — they belong to the CURRENT turn.
_IDENTITY_FIELDS = ("student_id", "session_id", "trace_id", "turn_id", "request_id", "user_id")
#: Cache bookkeeping fields stripped before storing and re-stamped on read.
_CACHE_MARKER_FIELDS = ("grading_cache", "cache_key_version", "grading_cache_key")

_LOCAL_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_REDIS_CLIENT: Any | None = None
_REDIS_RESOLVED = False


# ── configuration ────────────────────────────────────────────────────────────────────────────────
def cache_enabled() -> bool:
    """Kill switch. DEFAULT ON — ``LUBAN_GRADING_RESULT_CACHE=0/false/off/no`` bypasses the seam."""
    return str(os.environ.get("LUBAN_GRADING_RESULT_CACHE", "")).strip().lower() not in (
        "0", "false", "off", "no")


def cache_ttl_seconds() -> float:
    raw = str(os.environ.get("LUBAN_GRADING_RESULT_CACHE_TTL_SECONDS") or "").strip()
    if not raw:
        return 86400.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 86400.0


def _max_entries() -> int:
    raw = str(os.environ.get("LUBAN_GRADING_RESULT_CACHE_MAX_ENTRIES") or "").strip()
    if not raw:
        return 512
    try:
        return max(1, int(raw))
    except ValueError:
        return 512


def _resolve_backend_url() -> str:
    """Explicit URL wins; otherwise reuse the already-running rate-limit Valkey (same client lib,
    same compose service ``valkey``) so production is cross-worker without a second connection
    string. Unset -> per-process dict."""
    explicit = str(os.environ.get("LUBAN_GRADING_RESULT_CACHE_URL") or "").strip()
    if explicit:
        return explicit
    backend = str(os.environ.get("DEEPTUTOR_RATE_LIMIT_BACKEND", "sqlite")).strip().lower()
    if backend != "redis":
        return ""
    return str(
        os.environ.get("DEEPTUTOR_RATE_LIMIT_REDIS_URL") or os.environ.get("REDIS_URL") or ""
    ).strip()


def _redis_client() -> Any | None:
    """Async Valkey/Redis client (redis>=4.2 built-in asyncio — zero new dependency), with short
    timeouts so a half-dead Valkey degrades to a miss instead of stalling a grading turn."""
    global _REDIS_CLIENT, _REDIS_RESOLVED
    url = _resolve_backend_url()
    if not url:
        return None
    if _REDIS_RESOLVED:
        return _REDIS_CLIENT
    _REDIS_RESOLVED = True
    try:
        from redis import asyncio as aredis

        _REDIS_CLIENT = aredis.Redis.from_url(
            url, decode_responses=True, socket_timeout=1.0, socket_connect_timeout=1.0,
        )
    except Exception:  # noqa: BLE001 — no shared store -> per-process dict (fail-open to a miss)
        logger.warning("grading_result_cache: Redis client init failed; using per-process dict",
                       exc_info=True)
        _REDIS_CLIENT = None
    return _REDIS_CLIENT


def reset_backend_for_tests() -> None:
    """Drop the memoized client + local entries (tests flip env between cases)."""
    global _REDIS_CLIENT, _REDIS_RESOLVED
    _REDIS_CLIENT = None
    _REDIS_RESOLVED = False
    _LOCAL_CACHE.clear()


# ── key authority ────────────────────────────────────────────────────────────────────────────────
def normalize_student_answer(text: Any) -> str:
    """Conservative normalization: Unicode NFKC + newline unification + OUTER strip.

    Interior whitespace is NOT collapsed: in a 案例 answer, line/space structure separates
    enumerated items, and collapsing it would hash two semantically different answers to one key
    (audit §3.3 risk 5). The policy string ``ANSWER_NORMALIZATION_VERSION`` is part of the key, so a
    future change invalidates instead of silently re-binding."""
    s = unicodedata.normalize("NFKC", str(text or ""))
    return s.replace("\r\n", "\n").replace("\r", "\n").strip()


def rubric_digest(rubric_points: list[dict[str, Any]] | None) -> str:
    """ORDERED digest of the scoring-point pool actually being graded. Order is load-bearing (the
    batch adjudicator keys on 1..n ordinals), so this is a list, not a set."""
    rows = []
    for point in rubric_points or []:
        if not isinstance(point, dict):
            continue
        rows.append([
            str(point.get("point_id") or ""),
            str(point.get("text") or ""),
            str(point.get("policy") or ""),
            [str(term) for term in (point.get("required_terms") or [])],
            _finite_or_none(point.get("score")),
            str(point.get("authority_source") or ""),
            _finite_or_none(point.get("official_total_score")),
            str(point.get("score_authority") or ""),
        ])
    return hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):  # NaN / ±inf
        return None
    return number


def build_cache_key(
    *,
    question_identity: str,
    student_answer: str,
    rubric_points: list[dict[str, Any]] | None,
    model: str = "",
    identity: dict[str, Any] | None = None,
) -> str:
    """sha256 over EVERY fact that can move the final score. Missing any of them would let a stale
    result outlive the change that should have invalidated it (audit §3.3 risk 2).

    ``identity`` carries the caller-known authority material (provenance, coverage state, scope cap,
    nominal full score, bank slot + content hash, prompt versions, provider binding, grader version).
    Unknown/absent values are recorded as "" — an upgrade that starts populating them changes the key,
    which is the desired invalidation."""
    ident = identity if isinstance(identity, dict) else {}
    payload = {
        "cache_key_version": CACHE_KEY_VERSION,
        "answer_normalization_version": ANSWER_NORMALIZATION_VERSION,
        # question identity: qid, or the case_group_id / merged sub-question identity for a bundle
        "question_identity": str(question_identity or ""),
        "student_answer": normalize_student_answer(student_answer),
        "rubric_digest": rubric_digest(rubric_points),
        "rubric_point_count": len(rubric_points or []),
        "nominal_full_score": _finite_or_none(ident.get("nominal_full_score")),
        "coverage_state": str(ident.get("coverage_state") or ""),
        "effective_scope_cap": _finite_or_none(ident.get("effective_scope_cap")),
        "rubric_provenance": str(ident.get("rubric_provenance") or ""),
        "bank_slot": str(ident.get("bank_slot") or ""),
        "bank_content_hash": str(ident.get("bank_content_hash") or ""),
        "extraction_prompt_version": str(ident.get("extraction_prompt_version") or ""),
        "adjudication_prompt_version": str(ident.get("adjudication_prompt_version") or ""),
        "model": str(model or ""),
        "provider_binding": str(ident.get("provider_binding") or ""),
        "grader_algorithm_version": str(ident.get("grader_algorithm_version") or ""),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def batch_cache_key(sub_keys: list[str]) -> str:
    """Ordered hash of child cache keys — a batch/bundle must not key on the parent qid alone
    (audit §3.2)."""
    return hashlib.sha256(
        json.dumps([str(k) for k in sub_keys], separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# ── cacheability + identity handling ─────────────────────────────────────────────────────────────
def is_cacheable_event(event: Any) -> bool:
    """Only a TERMINAL, trustworthy grading event may be frozen.

    Refuses: non-completed events / markers, ``degraded`` batches (incomplete adjudication),
    unknown-or-error coverage (fail-loud tri-state, audit §4.2), and any non-finite score. Freezing
    any of those would turn a transient outage into a permanently sticky wrong score."""
    if not isinstance(event, dict):
        return False
    if event.get("event_type") != "case_grading_completed":
        return False
    if event.get("degraded"):
        return False
    coverage_state = str(event.get("coverage_state") or "").strip().lower()
    if coverage_state in ("unknown", "error"):
        return False
    for field in ("awarded_score", "max_score"):
        if _finite_or_none(event.get(field)) is None:
            return False
    coverage = event.get("coverage")
    if coverage is not None and _finite_or_none(coverage) is None:
        return False
    return True


def strip_identity(event: dict[str, Any]) -> dict[str, Any]:
    """Value stored in the shared cache carries NO turn identity (audit §3.3 risk 4)."""
    stored = copy.deepcopy(event)
    for field in _IDENTITY_FIELDS + _CACHE_MARKER_FIELDS:
        stored.pop(field, None)
    return stored


def rebind_identity(stored: dict[str, Any], *, student_id: str = "") -> dict[str, Any]:
    """Re-attach the CURRENT turn's identity to an immutable cached score fact."""
    event = copy.deepcopy(stored)
    event["student_id"] = student_id
    return event


# ── store ────────────────────────────────────────────────────────────────────────────────────────
async def get_cached_event(cache_key: str) -> dict[str, Any] | None:
    if not cache_key or cache_ttl_seconds() <= 0:
        return None
    client = _redis_client()
    if client is not None:
        try:
            raw = await client.get(f"{_REDIS_KEY_PREFIX}:{CACHE_KEY_VERSION}:{cache_key}")
        except Exception:  # noqa: BLE001 — a cache read must never break grading
            logger.warning("grading_result_cache: shared read failed; treating as miss", exc_info=True)
            return None
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except Exception:  # noqa: BLE001 — corrupt entry -> miss
            return None
        return value if isinstance(value, dict) else None
    item = _LOCAL_CACHE.get(cache_key)
    if item is None:
        return None
    created, value = item
    if time.monotonic() - created > cache_ttl_seconds():
        _LOCAL_CACHE.pop(cache_key, None)
        return None
    return copy.deepcopy(value)


async def store_cached_event(cache_key: str, stored_event: dict[str, Any]) -> None:
    ttl = cache_ttl_seconds()
    if not cache_key or ttl <= 0 or not isinstance(stored_event, dict):
        return
    client = _redis_client()
    if client is not None:
        try:
            # Idempotent last-write-wins: concurrent workers computing the same key write the same
            # value, so no distributed lock / single-flight is needed for correctness.
            await client.set(
                f"{_REDIS_KEY_PREFIX}:{CACHE_KEY_VERSION}:{cache_key}",
                json.dumps(stored_event, ensure_ascii=False, separators=(",", ":")),
                ex=int(ttl),
            )
        except Exception:  # noqa: BLE001 — a cache write must never break grading
            logger.warning("grading_result_cache: shared write failed; skipping", exc_info=True)
        return
    if len(_LOCAL_CACHE) >= _max_entries():
        oldest = min(_LOCAL_CACHE, key=lambda key: _LOCAL_CACHE[key][0])
        _LOCAL_CACHE.pop(oldest, None)
    _LOCAL_CACHE[cache_key] = (time.monotonic(), copy.deepcopy(stored_event))


__all__ = [
    "ANSWER_NORMALIZATION_VERSION",
    "CACHE_KEY_VERSION",
    "batch_cache_key",
    "build_cache_key",
    "cache_enabled",
    "cache_ttl_seconds",
    "get_cached_event",
    "is_cacheable_event",
    "normalize_student_answer",
    "rebind_identity",
    "reset_backend_for_tests",
    "rubric_digest",
    "store_cached_event",
    "strip_identity",
]
