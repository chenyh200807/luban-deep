from __future__ import annotations

import hashlib
import hmac
import logging
import time

from deeptutor.services.runtime_env import env_flag, is_production_environment

logger = logging.getLogger(__name__)

INTERNAL_QA_BILLING_BYPASS_FLAG = "DEEPTUTOR_INTERNAL_QA_BILLING_BYPASS"
INTERNAL_QA_IDENTITY_PREFIXES = ("qa_", "test_", "operator_")


def internal_qa_billing_bypass_enabled() -> bool:
    """Return true only for explicit non-production billing bypass QA runs."""

    return (not is_production_environment()) and env_flag(
        INTERNAL_QA_BILLING_BYPASS_FLAG,
        default=False,
    )


def internal_qa_billing_bypass_allowed(*identity_values: object) -> bool:
    """Return true when the explicit QA billing bypass is scoped to QA identities."""

    if not internal_qa_billing_bypass_enabled():
        return False
    return any(_is_internal_qa_identity(value) for value in identity_values)


def is_internal_qa_identity(value: object) -> bool:
    """Public predicate: is this a throwaway QA/test/operator identity?"""

    return _is_internal_qa_identity(value)


def _is_internal_qa_identity(value: object) -> bool:
    normalized = str(value or "").strip().lower()
    return bool(normalized) and normalized.startswith(INTERNAL_QA_IDENTITY_PREFIXES)


# ---------------------------------------------------------------------------
# Eval-mode billing bypass (key-gated, production-capable)
#
# Unlike internal_qa_billing_bypass_* above (deliberately non-production only),
# this path is meant to let an authorized operator run a billable production
# eval without the per-turn wallet charge. It is designed so it can NEVER become
# a free-turn vulnerability:
#
#   * Fail closed: with no server key configured (the default in every
#     environment, including production) every signature check returns False, so
#     behaviour is unchanged and the gate stays fully enforced.
#   * Possession of a local secret is mandatory. The key never travels: the
#     client sends an HMAC-SHA256 signature over a fresh timestamp. Without the
#     key an attacker cannot forge a valid signature.
#   * Replay-bounded: a signature is only honoured within a short skew window.
#   * Blast-radius limited: even a valid signature only bypasses throwaway QA
#     identities (qa_/test_/operator_), optionally narrowed to an exact username
#     allowlist. A real paying user can NEVER be bypassed, so a leaked key can
#     never divert a real user's charge — at worst it grants free turns to
#     value-less QA accounts, and every grant is audited at the gate.
# ---------------------------------------------------------------------------

EVAL_BILLING_BYPASS_KEY_ENV = "DEEPTUTOR_EVAL_BYPASS_KEY"
EVAL_BILLING_BYPASS_USERS_ENV = "DEEPTUTOR_EVAL_BYPASS_USERS"
EVAL_BILLING_BYPASS_HEADER = "X-Eval-Bypass"
EVAL_BILLING_BYPASS_TOKEN_VERSION = "v1"
EVAL_BILLING_BYPASS_MAX_SKEW_SECONDS = 300
# Refuse weak/short keys: a too-short key is treated as unset (fail closed) so a
# careless one-character key can never silently open the bypass in production.
# This is a length FLOOR, not a strength recommendation — generate the key with
# `openssl rand -hex 32` (64 hex chars / 256 bits) and treat it as a production
# secret stored only in the server env and the operator's local env.
_MIN_EVAL_BYPASS_KEY_LENGTH = 32


def _env_value(name: str) -> str:
    from deeptutor.services.config.env_store import get_env_store

    return str(get_env_store().get(name, "") or "").strip()


def eval_billing_bypass_secret() -> str:
    """The server secret enabling eval-mode billing bypass, or "" if unconfigured.

    An empty or too-short key means the eval bypass is impossible: every
    signature check fails closed in every environment.
    """

    secret = _env_value(EVAL_BILLING_BYPASS_KEY_ENV)
    if len(secret) < _MIN_EVAL_BYPASS_KEY_LENGTH:
        return ""
    return secret


def eval_billing_bypass_configured() -> bool:
    return bool(eval_billing_bypass_secret())


def _eval_bypass_username_allowlist() -> tuple[str, ...]:
    raw = _env_value(EVAL_BILLING_BYPASS_USERS_ENV)
    if not raw:
        return ()
    return tuple(item.strip().lower() for item in raw.split(",") if item.strip())


def _identity_in_eval_scope(*identity_values: object) -> bool:
    """Blast-radius limit for eval bypass.

    Requires at least one identity in the throwaway QA cohort. If an exact
    username allowlist is configured, the identity must also be on it. Real
    paying users (non-cohort) are always rejected.
    """

    normalized = [str(v or "").strip().lower() for v in identity_values]
    normalized = [v for v in normalized if v]
    if not any(v.startswith(INTERNAL_QA_IDENTITY_PREFIXES) for v in normalized):
        return False
    allowlist = _eval_bypass_username_allowlist()
    if allowlist:
        return any(v in allowlist for v in normalized)
    return True


def make_eval_billing_bypass_token(secret: str, *, ts: int) -> str:
    """Build the ``X-Eval-Bypass`` header value for a unix timestamp.

    Shared by the verifier and the eval client so signing is single-authority:
    ``v1.<unix_ts>.<hex hmac_sha256(secret, str(ts))>``.
    """

    signature = hmac.new(secret.encode(), str(ts).encode(), hashlib.sha256).hexdigest()
    return f"{EVAL_BILLING_BYPASS_TOKEN_VERSION}.{ts}.{signature}"


def eval_billing_bypass_signature_valid(
    signature: object,
    *identity_values: object,
    now: int | None = None,
) -> bool:
    """Validate an ``X-Eval-Bypass`` token against the server key and identity.

    Returns True only when: a key is configured, the identity is in eval scope,
    the token is well-formed, fresh within the skew window, and the HMAC matches
    (constant-time compare). False otherwise — fail closed.
    """

    secret = eval_billing_bypass_secret()
    if not secret:
        # Feature off everywhere: not suspicious, stay silent (no key configured).
        return False

    def _reject(reason: str) -> bool:
        # A signature was presented but failed: audit it so abuse of a leaked key
        # (replay, forgery, identity mismatch) is visible. Never log the token/key.
        identities = ",".join(
            str(v or "").strip() for v in identity_values if str(v or "").strip()
        )
        logger.warning(
            "eval billing bypass REJECTED: reason=%s identities=%s", reason, identities
        )
        return False

    if not _identity_in_eval_scope(*identity_values):
        return _reject("identity_out_of_scope")
    token = str(signature or "").strip()
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != EVAL_BILLING_BYPASS_TOKEN_VERSION:
        return _reject("malformed_token")
    ts_str, sig_hex = parts[1], parts[2].lower()
    try:
        ts = int(ts_str)
    except ValueError:
        return _reject("bad_timestamp")
    current = int(now if now is not None else time.time())
    if abs(current - ts) > EVAL_BILLING_BYPASS_MAX_SKEW_SECONDS:
        return _reject("expired_or_skewed")
    expected = hmac.new(secret.encode(), ts_str.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig_hex):
        return _reject("signature_mismatch")
    return True
