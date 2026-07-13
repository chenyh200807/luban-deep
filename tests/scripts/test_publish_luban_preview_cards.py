from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "publish_luban_preview_cards", REPO / "scripts" / "publish_luban_preview_cards.py"
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["publish_luban_preview_cards"] = _mod
_spec.loader.exec_module(_mod)


def test_registry_has_exact_37_finished_topics_and_canonical_variants() -> None:
    assert len(_mod.STATIONS) == 37
    assert _mod.STATIONS["c02"].pack_dir == "C02"
    assert _mod.STATIONS["s07"].pack_dir == "P40_S07B"
    assert set(_mod.STATIONS["s01"].teach) == {
        "lesson.html", "lesson2.html", "lesson3.html"
    }
    assert set(_mod.STATIONS["s01"].practice) == {
        "practice.html", "practice2.html", "practice3.html"
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


def test_derived_html_strips_trailing_whitespace_without_losing_final_newline() -> None:
    assert _mod._strip_trailing_whitespace("first  \nsecond\t\n") == "first\nsecond\n"
