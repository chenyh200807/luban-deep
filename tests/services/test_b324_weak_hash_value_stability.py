"""B324 weak-hash remediation regression guard.

These helpers use SHA1 for non-security purposes (dedupe / cache keys /
display refs / deterministic ids). The B324 fix adds
``usedforsecurity=False`` which MUST NOT change the produced digest values
(those values are persisted dedupe/cache keys). This test pins the exact
outputs so the fix is provably value-preserving.
"""
from __future__ import annotations

import hashlib

from deeptutor.services.assessment import blueprint_service as bp
from deeptutor.services.learner_state import learning_report_read_model as lrrm
from deeptutor.services.learner_state import mistake_book as mb
from deeptutor.services.learner_state import revalidation_queue as rq
from deeptutor.services.learner_state import training_intent as ti
from deeptutor.tutorbot.providers import openai_compat_provider as oc


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def test_selection_offset_stable():
    assert bp._selection_offset("seed1", "sec-A") == 1000 + (
        int(_sha1("seed1:sec-A:offset")[:8], 16) % 3000
    )


def test_opaque_ref_stable():
    assert lrrm._opaque_ref("ev-123") == "evidence-" + _sha1("ev-123")[:12]


def test_mistake_book_collection_etag_stable():
    assert mb._collection_etag([{"etag": "a"}, {"etag": "b"}]) == _sha1("a|b")[:16]


def test_revalidation_queue_long_id_fallback_stable():
    user_id = "u" * 90  # force human form > 80 chars -> sha1 fallback
    row = {"node_id": "n1", "ability_dimension": "code_application", "error_code": "E1"}
    raw = "|".join([user_id, "n1", "code_application", "E1"])
    assert rq._probe_id(user_id=user_id, row=row) == "rvp_" + _sha1(raw)[:16]


def test_intent_id_stable():
    out = ti._intent_id(b="2", a="1")
    raw = "|".join(["1", "2"])  # sorted keys a,b
    assert out == "lti_" + _sha1(raw)[:16]


def test_normalize_tool_call_id_stable():
    long_id = "x" * 40
    assert oc.OpenAICompatProvider._normalize_tool_call_id(long_id) == _sha1(long_id)[:9]
