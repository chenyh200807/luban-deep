from __future__ import annotations

from deeptutor.services.observability.identity_bridge import enrich_trace_metadata_with_bi_identity


class _MemberService:
    def __init__(self, resolution: dict[str, str]) -> None:
        self.resolution = resolution
        self.calls: list[dict[str, object]] = []

    def resolve_trace_identity_for_bi(self, *, raw_user_id: str, metadata: dict[str, object]) -> dict[str, str]:
        self.calls.append({"raw_user_id": raw_user_id, "metadata": dict(metadata)})
        return dict(self.resolution)


def test_enrich_trace_metadata_uses_canonical_member_id_and_preserves_raw_id() -> None:
    service = _MemberService(
        {
            "status": "resolved",
            "canonical_user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            "member_user_id": "wx_live_alias",
            "raw_user_id": "legacy_chat_user_1",
            "matched_identity": "legacy_chat_user_1",
        }
    )
    metadata = {
        "user_id": "legacy_chat_user_1",
        "session_id": "session-1",
        "wx_openid": "oTHl56liveOpenid",
    }

    enriched = enrich_trace_metadata_with_bi_identity(metadata, member_service=service)

    assert enriched is metadata
    assert enriched["user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert enriched["raw_user_id"] == "legacy_chat_user_1"
    assert enriched["member_user_id"] == "wx_live_alias"
    assert enriched["identity_resolution_status"] == "resolved"
    assert enriched["identity_resolution_source"] == "member_console"
    assert enriched["identity_matched"] == "legacy_chat_user_1"
    assert "phone" not in enriched
    assert service.calls[0]["raw_user_id"] == "legacy_chat_user_1"


def test_enrich_trace_metadata_marks_unmapped_without_overwriting_user_id() -> None:
    service = _MemberService(
        {
            "status": "unmapped",
            "canonical_user_id": "",
            "member_user_id": "",
            "raw_user_id": "72af0948-a253-45b8-8b3b-a9eba9e5a1d6",
            "matched_identity": "",
        }
    )
    metadata = {"user_id": "72af0948-a253-45b8-8b3b-a9eba9e5a1d6"}

    enriched = enrich_trace_metadata_with_bi_identity(metadata, member_service=service)

    assert enriched["user_id"] == "72af0948-a253-45b8-8b3b-a9eba9e5a1d6"
    assert enriched["raw_user_id"] == "72af0948-a253-45b8-8b3b-a9eba9e5a1d6"
    assert enriched["identity_resolution_status"] == "unmapped"
    assert enriched["identity_resolution_source"] == "member_console"
    assert "member_user_id" not in enriched
    assert "identity_matched" not in enriched


def test_enrich_trace_metadata_redacts_phone_raw_identity_in_trace_metadata() -> None:
    service = _MemberService(
        {
            "status": "resolved",
            "canonical_user_id": "2d9eac15-5d26-4e93-941b-9ec6345ce6d9",
            "member_user_id": "wx_live_alias",
            "raw_user_id": "13800138000",
            "matched_identity": "13800138000",
        }
    )
    metadata = {"user_id": "13800138000"}

    enriched = enrich_trace_metadata_with_bi_identity(metadata, member_service=service)

    assert service.calls[0]["raw_user_id"] == "13800138000"
    assert enriched["user_id"] == "2d9eac15-5d26-4e93-941b-9ec6345ce6d9"
    assert enriched["raw_user_id"].startswith("phone:")
    assert enriched["identity_matched"].startswith("phone:")
    assert "13800138000" not in set(str(value) for value in enriched.values())
