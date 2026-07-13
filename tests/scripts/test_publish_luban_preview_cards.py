from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
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


def test_registry_has_exact_37_finished_topics_and_canonical_variants() -> None:
    assert len(_mod.STATIONS) == 37
    assert _mod.STATIONS["c02"].pack_dir == "C02"
    assert _mod.STATIONS["s07"].pack_dir == "P40_S07"
    assert set(_mod.STATIONS["s01"].teach) == {
        "lesson.html", "lesson2.html", "lesson3.html"
    }
    assert set(_mod.STATIONS["s01"].practice) == {
        "practice.html", "practice2.html", "practice3.html"
    }


def test_s07_registry_cannot_regress_to_the_n03_runtime() -> None:
    station = _mod.STATIONS["s07"]
    assert station.pack_dir == "P40_S07"
    assert station.teach == {"lesson.html": "P40_S07.teach.dc.html"}


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
    monkeypatch.setattr(_mod, "transform_practice", lambda text, _station: text)
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


def test_derived_html_strips_trailing_whitespace_without_losing_final_newline() -> None:
    assert _mod._strip_trailing_whitespace("first  \nsecond\t\n") == "first\nsecond\n"

from deeptutor.services.luban_lesson.practice_html import _array_after

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


def test_f16_publish_is_deterministic_and_preserves_finished_content() -> None:
    tracked = [
        PUBLIC / "lesson.html",
        PUBLIC / "practice.html",
        AUTHORITY,
    ]
    before = {str(path.relative_to(ROOT)): _sha(path) for path in tracked}

    subprocess.run(
        [sys.executable, str(ROOT / "scripts/publish_luban_preview_cards.py"), "f16"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert {str(path.relative_to(ROOT)): _sha(path) for path in tracked} == before
    source_html = (SOURCE / "P40_F16.practice.dc.html").read_text(encoding="utf-8")
    public_html = (PUBLIC / "practice.html").read_text(encoding="utf-8")
    assert _array_after(public_html, r"\bQ\s*=") == _array_after(source_html, r"\bQ\s*=")

    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    assert authority["source_html_sha256"] == _sha(SOURCE / "P40_F16.practice.dc.html")
    assert authority["published_lesson_sha256"] == _sha(PUBLIC / "lesson.html")
    assert authority["published_practice_sha256"] == _sha(PUBLIC / "practice.html")
    assert authority["presentation_order"] == [0, 1, 2, 3, 5]
    assert "正在确认这 5 题" in public_html
    assert "inQuiz:!this.state.finished&&!this.state.autoSaving" in public_html
    assert "正在提交本次作答，马上生成正式结果" in public_html
    assert "服务端正在重新判定并更新你的学习记录" not in public_html
    assert "setTimeout(()=>this.saveEvidence(),0)" in public_html
    assert "presentation=receipt&answer_indexes=" in public_html
    assert "网页预览 · 不写入学习记录" in public_html
    assert "满分手" not in public_html
    assert '"稳了"' not in public_html
    assert "采分点都拿到了" not in public_html
    assert "是否形成学习记录以小程序正式收据为准" in public_html
    assert "保存学习证据 · 查看正式收据" not in public_html


def test_f16_publish_copies_all_audio_and_manifest_byte_for_byte() -> None:
    source_audio = SOURCE / "audio"
    public_audio = PUBLIC / "audio"
    source_mp3 = sorted(source_audio.glob("*.mp3"))

    assert len(source_mp3) == 11
    assert all(_sha(path) == _sha(public_audio / path.name) for path in source_mp3)
    assert _sha(source_audio / "manifest.json") == _sha(public_audio / "manifest.json")
