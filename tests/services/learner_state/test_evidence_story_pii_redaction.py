from __future__ import annotations

import json

from deeptutor.services.learner_state.evidence_story_read_model import (
    build_evidence_story_read_model,
)
from deeptutor.services.learner_state.redaction import redact_chat_text
from tests.services.learner_state.test_evidence_story_read_model import (
    _case_event,
    _conversation_event,
)


def test_redaction_module_removes_raw_chat_pii_from_story_payload() -> None:
    raw = "我是王小明，电话 13800138000，邮箱 a@example.com，住在北京市朝阳区1号"
    story = build_evidence_story_read_model(
        user_id="openid_private_13800138000",
        evidence_events=[_conversation_event(), _case_event(event_id="evt_miss_1")],
    )
    rendered = json.dumps(story, ensure_ascii=False)

    assert "13800138000" not in rendered
    assert "a@example.com" not in rendered
    assert "王小明" not in redact_chat_text(raw)
    assert "openid_private" not in rendered
    assert "[手机号]" in redact_chat_text(raw)
    assert "[邮箱]" in redact_chat_text(raw)
    assert "[姓名]" in redact_chat_text(raw)
    assert "[地址]" in redact_chat_text(raw)
