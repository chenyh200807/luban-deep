from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from typing import Any


_LOG = logging.getLogger(__name__)
_DEV_DEFAULT_SECRET = "dev-attempt-ref-secret"
_KID_V1 = "v1"


def _secret() -> bytes:
    # Single authority: reuse the shared fail-closed production detector instead
    # of maintaining a second, drift-prone definition of "production".
    from deeptutor.services.runtime_env import is_production_environment

    raw = (os.getenv("DEEPTUTOR_ATTEMPT_REF_SECRET") or "").strip()
    if not raw and is_production_environment():
        raise RuntimeError(
            "DEEPTUTOR_ATTEMPT_REF_SECRET is required in production; refuse to fall back to dev default."
        )
    return (raw or _DEV_DEFAULT_SECRET).encode("utf-8")


def _log_secret_fingerprint() -> None:
    digest = hashlib.sha1(_secret()).hexdigest()[:8]
    _LOG.info("attempt_ref secret fingerprint=%s kid=%s", digest, _KID_V1)


_log_secret_fingerprint()


def sign_attempt_ref(*, user_id: str, event_id: str, question_id: str = "") -> str:
    user = str(user_id or "").strip()
    event = str(event_id or "").strip()
    if not user or not event:
        raise ValueError("sign_attempt_ref requires non-empty user_id and event_id")
    body = {
        "u": user,
        "e": event,
        "q": str(question_id or "").strip(),
        "k": _KID_V1,
        "v": 1,
    }
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(_secret(), raw, hashlib.sha256).hexdigest()[:24]
    return base64.urlsafe_b64encode(raw + b"." + sig.encode("ascii")).decode("ascii").rstrip("=")


def verify_attempt_ref(token: str, *, user_id: str) -> dict[str, Any] | None:
    user = str(user_id or "").strip()
    if not user:
        return None
    try:
        token_text = str(token or "")
        padded = token_text + "=" * (-len(token_text) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        body_raw, sig_raw = raw.rsplit(b".", 1)
        expected = hmac.new(_secret(), body_raw, hashlib.sha256).hexdigest()[:24].encode("ascii")
        if not hmac.compare_digest(sig_raw, expected):
            return None
        body = json.loads(body_raw.decode("utf-8"))
    except Exception:
        return None
    if str(body.get("k") or "") != _KID_V1:
        return None
    if str(body.get("u") or "") != user:
        return None
    event_id = str(body.get("e") or "").strip()
    if not event_id:
        return None
    return {"event_id": event_id, "question_id": str(body.get("q") or "").strip()}


__all__ = ["sign_attempt_ref", "verify_attempt_ref"]
