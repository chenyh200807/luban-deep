from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.luban_lesson import playback


def _publish_manifest(root: Path) -> None:
    pack_dir = root / "f16"
    pack_dir.mkdir(parents=True)
    (pack_dir / "playback-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "luban_playback_manifest.v1",
                "pack_id": "F16",
                "episodes": [
                    {
                        "object_id": "F16:lesson:2",
                        "episode_index": 2,
                        "lesson_file": "lesson2.html",
                        "content_revision": "revision-episode-2",
                        "duration_ms": 20_000,
                        "sections": [
                            {
                                "id": "section-1",
                                "index": 1,
                                "label": "第一节",
                                "group": "讲解",
                                "start_ms": 0,
                                "end_ms": 10_000,
                            },
                            {
                                "id": "section-2",
                                "index": 2,
                                "label": "第二节",
                                "group": "练习",
                                "start_ms": 10_000,
                                "end_ms": 20_000,
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@pytest.fixture
def published_playback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    root = tmp_path / "luban-preview"
    _publish_manifest(root)
    monkeypatch.setattr(playback, "_PUBLIC_PREVIEW_ROOT", root)
    return root


def _fact(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": "event-valid-0001",
        "action": "checkpoint",
        "object_id": "F16:lesson:2",
        "section": "section-1",
        "playback_session_id": "session-valid-0001",
        "sequence": 1,
        "content_revision": "revision-episode-2",
        "position_ms": 9_000,
        "from_position_ms": 8_000,
        "to_position_ms": 9_000,
        "watched_delta_ms": 1_000,
        "reason": "auto",
    }
    payload.update(overrides)
    return payload


def test_manifest_validator_projects_server_owned_episode_and_section(
    published_playback: Path,
) -> None:
    fact = playback.normalize_playback_fact(
        _fact(),
        pack_id="f16",
        object_id="F16:lesson:2",
    )

    assert fact["object_id"] == "F16:lesson:2"
    assert fact["lesson_file"] == "lesson2.html"
    assert fact["content_revision"] == "revision-episode-2"
    assert fact["duration_ms"] == 20_000
    assert fact["progress_pct"] == 45
    assert fact["section_index"] == 1
    assert fact["section_label"] == "第一节"
    assert fact["section_group"] == "讲解"
    assert fact["section_progress_pct"] == 90


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"content_revision": "stale-revision"}, "content revision mismatch"),
        ({"object_id": "F16:lesson:1"}, "object_id does not match"),
        ({"section": "not-published"}, "section is not published"),
        ({"position_ms": 21_001}, "playback position out of range"),
        (
            {"section": "section-2", "position_ms": 5_000},
            "position does not match section",
        ),
        (
            {"action": "seek", "watched_delta_ms": 1},
            "seek cannot claim watched time",
        ),
        (
            {"watched_delta_ms": 999},
            "checkpoint interval does not match watched time",
        ),
        (
            {
                "section": "section-2",
                "position_ms": 11_000,
                "from_position_ms": 9_000,
                "to_position_ms": 11_000,
                "watched_delta_ms": 2_000,
            },
            "checkpoint interval crosses a section boundary",
        ),
    ],
)
def test_manifest_validator_fails_closed_for_client_claims_outside_authority(
    published_playback: Path,
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(playback.PlaybackFactInvalid, match=message):
        playback.normalize_playback_fact(
            _fact(**overrides),
            pack_id="F16",
            object_id="F16:lesson:2",
        )


def test_manifest_validator_rejects_episode_not_bound_by_published_manifest(
    published_playback: Path,
) -> None:
    with pytest.raises(
        playback.PlaybackFactInvalid,
        match="playback episode not published",
    ):
        playback.resolve_published_playback_episode(
            pack_id="F16",
            object_id="F16:lesson:9",
        )
