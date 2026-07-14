from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "publish_luban_preview_cards", REPO / "scripts" / "publish_luban_preview_cards.py"
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["publish_luban_preview_cards"] = _mod
_spec.loader.exec_module(_mod)


def test_registry_has_exact_40_finished_topics_and_canonical_variants() -> None:
    assert len(_mod.STATIONS) == 40
    assert _mod.STATIONS["c02"].pack_dir == "C02"
    assert _mod.STATIONS["s07"].pack_dir == "P40_S07"
    assert _mod.STATIONS["b02"].teach == {
        "lesson.html": "P40_B02.teach.up.dc.html",
        "lesson2.html": "P40_B02.teach.down.dc.html",
    }
    assert _mod.STATIONS["b02"].practice == {
        "practice.html": "P40_B02.practice.up.dc.html",
        "practice2.html": "P40_B02.practice.down.dc.html",
    }
    assert _mod.STATIONS["d14"].teach == {
        "lesson.html": "P40_D14.teach.up.dc.html",
        "lesson2.html": "P40_D14.teach.middle.dc.html",
        "lesson3.html": "P40_D14.teach.down.dc.html",
    }
    assert _mod.STATIONS["n02"].teach == {
        "lesson.html": "P40_N02.teach.up.dc.html",
        "lesson2.html": "P40_N02.teach.down.dc.html",
    }
    assert _mod.STATIONS["n03"].teach == {
        "lesson.html": "P40_N03.teach.up.dc.html",
        "lesson2.html": "P40_N03.teach.down.dc.html",
    }
    assert set(_mod.STATIONS["s01"].teach) == {
        "lesson.html", "lesson2.html", "lesson3.html"
    }
    assert set(_mod.STATIONS["s01"].practice) == {
        "practice.html", "practice2.html", "practice3.html"
    }
    registered_sources = {
        name for station in _mod.STATIONS.values() for name in station.practice.values()
    }
    assert "P40_C02.practice.up.dc.html" not in registered_sources
    assert "P40_C02.practice.down.dc.html" not in registered_sources
    assert all("S07B" not in name for name in registered_sources)


def test_all_registered_practice_outputs_rebuild_from_tracked_sources() -> None:
    manifest = json.loads(
        (REPO / "docs/原始数据/考点原料/成品/_pack_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    registrations = {row["pack_id"]: row["practice"] for row in manifest["packs"]}
    checked = 0
    for station_id, station in _mod.STATIONS.items():
        # Clean CI worktrees intentionally do not materialize every ignored
        # finished teaching/audio bundle.  Only compare a derived practice page
        # when the matching registered teaching source is present; production
        # publication supplies an explicit finished root and is fail-closed for
        # all 37 packs.
        source_dir = _mod.FINISHED / station.pack_dir
        if any(not (source_dir / name).is_file() for name in station.teach.values()):
            continue
        rendered, authority = _mod._practice_only_outputs(
            station_id, station, finished_root=_mod.FINISHED
        )
        checked += 1
        for hosted_name, text in rendered.items():
            assert (_mod.HOST / station_id / hosted_name).read_text(
                encoding="utf-8"
            ) == text
        assert (_mod.AUTHORITY_HOST / f"{station_id}.practice.authority.json").read_text(
            encoding="utf-8"
        ) == json.dumps(authority, ensure_ascii=False, indent=2) + "\n"
        assert registrations[station_id.upper()]["authority_sha256"] == _mod._sha256(
            _mod.AUTHORITY_HOST / f"{station_id}.practice.authority.json"
        )
    assert checked >= 1


def test_registered_practice_sources_survive_autocrlf_checkout_byte_exact(
    tmp_path: Path,
) -> None:
    prefix = str(tmp_path) + "/"
    for station in _mod.STATIONS.values():
        for source_name in station.practice.values():
            source = _mod.FINISHED / station.pack_dir / source_name
            relative = source.relative_to(_mod.REPO)
            attributes = subprocess.check_output(
                ["git", "check-attr", "text", "whitespace", "--", str(relative)],
                cwd=_mod.REPO,
                text=True,
            )
            assert f"{relative}: text: unset" in attributes
            assert f"{relative}: whitespace: unset" in attributes
            subprocess.run(
                [
                    "git",
                    "-c",
                    "core.autocrlf=true",
                    "checkout-index",
                    f"--prefix={prefix}",
                    "--",
                    str(relative),
                ],
                cwd=_mod.REPO,
                check=True,
            )
            assert (tmp_path / relative).read_bytes() == source.read_bytes()


def test_practice_only_check_does_not_touch_lesson_or_support() -> None:
    station_id = "f16"
    lesson = _mod.HOST / station_id / "lesson.html"
    support = _mod.HOST / station_id / "support.js"
    before = (_mod._sha256(lesson), _mod._sha256(support))

    written = _mod.check_practice_only(
        station_id, _mod.STATIONS[station_id], finished_root=_mod.FINISHED
    )

    assert written == ["practice.html", "server-authority/f16"]
    assert (_mod._sha256(lesson), _mod._sha256(support)) == before


def test_s07_registry_cannot_regress_to_the_n03_runtime() -> None:
    station = _mod.STATIONS["s07"]
    assert station.pack_dir == "P40_S07"
    assert station.teach == {"lesson.html": "P40_S07.teach.dc.html"}


def test_n03_uses_the_final_two_part_teaching_source() -> None:
    station = _mod.STATIONS["n03"]

    assert station.pack_dir == "P40_N03"
    assert station.teach == {
        "lesson.html": "P40_N03.teach.up.dc.html",
        "lesson2.html": "P40_N03.teach.down.dc.html",
    }


def test_rewrite_hrefs_handles_html_and_x_dc_script_links() -> None:
    rendered = _mod._rewrite_hrefs(
        '<a href="P40_A01.teach.down.dc.html">下集</a>'
        ' {href:"P40_A01.teach.down.dc.html"}'
        " { href : 'P40_A01.teach.down.dc.html' }",
        {"P40_A01.teach.down.dc.html": "lesson2.html"},
    )
    assert "P40_A01.teach.down.dc.html" not in rendered
    assert rendered.count("lesson2.html") == 3


def test_audio_preload_targets_first_versioned_segment() -> None:
    element = _mod._audio_preload_element(
        'audioBase="audio/up/";\naudioVersion="20260713-a01";'
    )
    assert element == (
        '<audio data-luban-prewarm preload="auto" '
        'src="audio/up/b0.mp3?v=20260713-a01" aria-hidden="true" '
        'style="display:none"></audio>'
    )


def test_teach_transform_replaces_authoring_preview_ai_with_tutorbot_adapter() -> None:
    source = (
        _mod.FINISHED / "P40_F16" / "P40_F16.teach.dc.html"
    ).read_text(encoding="utf-8")

    rendered = _mod.transform_teach(source, "F16")

    assert "window.claude" not in rendered
    assert 'contextId:"F16"' in rendered
    assert 'fetch("/api/v1/luban-preview/ai-ask"' in rendered
    assert "entryTicket:entryTicket" in rendered
    assert "currentCaption:{speaker:isFollowup?\"学员追问\":\"鲁班讲解\"" in rendered
    assert "keycard:keycard.slice(0,160)" in rendered
    assert "if(reconnects>=5)" in rendered
    assert "new WebSocket" in rendered
    assert 'type:"subscribe_turn"' in rendered
    assert "LubanTutorbotSheetRuntime" in rendered
    assert "lzAskSheetIn" in rendered
    assert "data-luban-ask-thread" in rendered
    assert "data-luban-ask-error" in rendered
    assert "data-luban-workflow-status" in rendered
    assert "data-luban-workflow-toggle" in rendered
    assert 'onClick="{{ toggleAskWorkflow }}"' in rendered
    assert 'value="{{ askWorkflowExpanded }}"' in rendered
    assert "askWorkflowExpanded:false" in rendered
    assert "toggleAskWorkflow()" in rendered
    assert "askBlocks" in rendered
    assert "entry_ticket" in rendered
    assert 'current.searchParams.get("entry_ticket")' not in rendered
    assert 'new URLSearchParams(String(current.hash||"").replace(/^#/,""))' in rendered
    assert "lesson-viewed" in rendered


def test_audio_manifest_missing_segment_fails_closed(tmp_path: Path) -> None:
    audio = tmp_path / "audio"
    audio.mkdir()
    (audio / "manifest.json").write_text(
        '{"segments":[{"id":"b0"},{"id":"b1"}]}', encoding="utf-8"
    )
    (audio / "b0.mp3").write_bytes(b"mp3")

    with pytest.raises(_mod.TransformError, match="b1.mp3"):
        _mod._validate_audio_assets(tmp_path)


def test_audio_version_is_derived_from_audio_bytes(tmp_path: Path) -> None:
    audio = tmp_path / "audio" / "up"
    audio.mkdir(parents=True)
    clip = audio / "b0.mp3"
    clip.write_bytes(b"first")
    source = 'audioBase="audio/up/"; audioVersion="manual-time";'

    first = _mod._version_audio_assets(source, tmp_path)
    clip.write_bytes(b"second")
    second = _mod._version_audio_assets(source, tmp_path)

    assert 'audioVersion="manual-time"' not in first
    assert first != second


def test_support_runtime_urls_are_rewritten_to_same_origin_vendor_assets() -> None:
    source = "\n".join(
        (
            'var BABEL_URL = "https://unpkg.com/@babel/standalone@7.29.0/babel.min.js";',
            'var REACT_URL = "https://unpkg.com/react@18.3.1/umd/react.production.min.js";',
            'var REACT_DOM_URL = "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js";',
        )
    )

    rendered = _mod._self_host_support_runtime(source)

    assert "unpkg.com" not in rendered
    assert '"../vendor/babel-7.29.0.min.js"' in rendered
    assert '"../vendor/react-18.3.1.production.min.js"' in rendered
    assert '"../vendor/react-dom-18.3.1.production.min.js"' in rendered

    older = _mod._self_host_support_runtime(
        source.replace(
            "@babel/standalone@7.29.0/babel.min.js",
            "@babel/standalone@7.26.4/babel.min.js",
        )
    )
    assert '"../vendor/babel-7.26.4.min.js"' in older


def test_support_runtime_rewrite_fails_closed_when_pinned_anchor_drifts() -> None:
    with pytest.raises(_mod.TransformError, match="support-runtime"):
        _mod._self_host_support_runtime('var REACT_URL = "react-next.js";')


def test_support_transform_failure_keeps_existing_hosted_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    finished = tmp_path / "finished"
    source = finished / "PACK"
    audio = source / "audio"
    audio.mkdir(parents=True)
    (source / "teach.html").write_text(
        'audioBase="audio/"; audioVersion="old";', encoding="utf-8"
    )
    (source / "practice.html").write_text("practice", encoding="utf-8")
    (source / "support.js").write_text('var REACT_URL = "drifted";', encoding="utf-8")
    (audio / "manifest.json").write_text(
        '{"segments":[{"id":"b0"}]}', encoding="utf-8"
    )
    (audio / "b0.mp3").write_bytes(b"new-audio")

    host = tmp_path / "host"
    old = host / "x01"
    (old / "audio").mkdir(parents=True)
    (old / "lesson.html").write_text("old-lesson", encoding="utf-8")
    (old / "support.js").write_text("old-support", encoding="utf-8")
    (old / "audio" / "b0.mp3").write_bytes(b"old-audio")
    monkeypatch.setattr(_mod, "HOST", host)
    monkeypatch.setattr(
        _mod,
        "transform_teach",
        lambda text, _pack: text
        + '\n<audio data-luban-prewarm preload="auto" src="audio/b0.mp3?v=test" '
        'aria-hidden="true" style="display:none"></audio>',
    )
    monkeypatch.setattr(
        _mod,
        "compile_practice_surface",
        lambda *_args, **_kwargs: {
            "surface": {"surface_id": "practice.html"},
            "items": [{"variant_id": str(index)} for index in range(5)],
        },
    )
    monkeypatch.setattr(
        _mod,
        "transform_practice",
        lambda text, **_kwargs: text,
    )
    monkeypatch.setattr(
        _mod,
        "build_practice_authority",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(_mod, "_pack_source_sha", lambda _pack: "0" * 64)
    station = _mod.Station(
        pack_dir="PACK",
        teach={"lesson.html": "teach.html"},
        practice={"practice.html": "practice.html"},
    )

    with pytest.raises(_mod.TransformError, match="support-runtime"):
        _mod.publish("x01", station, finished_root=finished)

    assert (old / "lesson.html").read_text(encoding="utf-8") == "old-lesson"
    assert (old / "support.js").read_text(encoding="utf-8") == "old-support"
    assert (old / "audio" / "b0.mp3").read_bytes() == b"old-audio"
    assert not list(host.glob(".x01.staging-*"))


def test_publish_makes_completed_station_directory_publicly_traversable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "finished" / "PACK"
    audio = source / "audio"
    audio.mkdir(parents=True)
    (source / "teach.html").write_text("teach", encoding="utf-8")
    (source / "practice.html").write_text("practice", encoding="utf-8")
    (source / "support.js").write_text("support", encoding="utf-8")
    (audio / "b0.mp3").write_bytes(b"audio")

    host = tmp_path / "host"
    monkeypatch.setattr(_mod, "HOST", host)
    monkeypatch.setattr(_mod, "AUTHORITY_HOST", tmp_path / "authority")
    monkeypatch.setattr(_mod, "_validate_audio_assets", lambda _src: None)
    monkeypatch.setattr(_mod, "_version_audio_assets", lambda text, _src: text)
    monkeypatch.setattr(
        _mod,
        "transform_teach",
        lambda _text, _pack: (
            '<audio data-luban-prewarm preload="auto" '
            'src="audio/b0.mp3?v=test" aria-hidden="true" '
            'style="display:none"></audio>'
        ),
    )
    monkeypatch.setattr(
        _mod,
        "_compile_practice_outputs",
        lambda *_args, **_kwargs: ({"practice.html": "practice"}, {}),
    )
    monkeypatch.setattr(_mod, "_self_host_support_runtime", lambda text: text)
    station = _mod.Station(
        pack_dir="PACK",
        teach={"lesson.html": "teach.html"},
        practice={"practice.html": "practice.html"},
    )

    _mod.publish("x01", station, finished_root=tmp_path / "finished")

    assert stat.S_IMODE((host / "x01").stat().st_mode) == 0o755


def test_derived_html_strips_trailing_whitespace_without_losing_final_newline() -> None:
    assert _mod._strip_trailing_whitespace("first  \nsecond\t\n") == "first\nsecond\n"

from deeptutor.services.luban_lesson.practice_html import (
    _array_after,
    _top_level_objects,
    compile_practice_surface,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (
    ROOT
    / "artifacts/luban_case_family_assets/diagram_microlesson/finished/P40_F16"
)
PUBLIC = ROOT / "web/public/luban-preview/f16"
AUTHORITY = (
    ROOT
    / "deeptutor/services/luban_lesson/compiled/f16.practice.authority.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f16_compile_is_deterministic_and_public_hashes_match_authority() -> None:
    source_html = (SOURCE / "P40_F16.practice.dc.html").read_text(encoding="utf-8")
    public_html = (PUBLIC / "practice.html").read_text(encoding="utf-8")
    assert len(_top_level_objects(_array_after(public_html, r"\bQ\s*="))) == 5
    kwargs = {
        "surface_id": "practice.html",
        "html": source_html,
        "source_path": "tracked-f16",
        "source_html_sha256": hashlib.sha256(source_html.encode()).hexdigest(),
    }
    assert compile_practice_surface("F16", **kwargs) == compile_practice_surface(
        "F16", **kwargs
    )

    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    surface = authority["surfaces"][0]
    assert authority["published_lesson_sha256"] == _sha(PUBLIC / "lesson.html")
    assert surface["published_practice_sha256"] == _sha(PUBLIC / "practice.html")
    assert surface["presentation_order"] == [0, 1, 2, 3, 5]
    assert "__dtRedirectEvidence" in public_html
    assert "presentation=receipt&pack_id=" in public_html
    assert "&answer_indexes=" in public_html
    assert "practice_surface=" in public_html
    assert "网页预览作答仅供即时反馈" in public_html
    assert "满分手" not in public_html
    assert '"稳了"' not in public_html
    assert "采分点都拿到了" not in public_html
    assert "是否形成学习记录，以小程序服务端正式收据为准" in public_html


def test_f16_publish_copies_all_audio_and_manifest_byte_for_byte() -> None:
    source_audio = SOURCE / "audio"
    public_audio = PUBLIC / "audio"
    source_mp3 = sorted(source_audio.glob("*.mp3"))

    assert len(source_mp3) == 11
    assert all(_sha(path) == _sha(public_audio / path.name) for path in source_mp3)
    assert _sha(source_audio / "manifest.json") == _sha(public_audio / "manifest.json")
