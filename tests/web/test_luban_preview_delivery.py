from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def test_luban_preview_cache_policy_separates_media_from_entry_html() -> None:
    source = (ROOT / "web/next.config.js").read_text(encoding="utf-8")

    for extension in ("mp3", "woff2", "png"):
        assert f"source: '/luban-preview/:path*.{extension}'" in source
    assert "public, max-age=31536000, immutable" in source
    assert "public, max-age=86400, stale-while-revalidate=604800" in source
    assert "public, max-age=3600, stale-while-revalidate=86400" in source
    assert "public, max-age=0, must-revalidate" in source
    assert "source: '/luban-preview/vendor/:path*'" in source


def test_shared_card_runtime_is_self_hosted_and_integrity_pinned() -> None:
    root = ROOT / "web/public/luban-preview"
    expected = {
        "babel-7.26.4.min.js": "a12872ea8da3d29b2a296c51bfac7c482e81419c755f2207a49ad9b77200f4ea",
        "babel-7.29.0.min.js": "2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0",
        "react-18.3.1.production.min.js": "d949f1c3687aedadcedac85261865f29b17cd273997e7f6b2bfc53b2f9d4c4dd",
        "react-dom-18.3.1.production.min.js": "35f4f974f4b2bcd44da73963347f8952e341f83909e4498227d4e26b98f66f0d",
    }
    for name, expected_digest in expected.items():
        data = (root / "vendor" / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == expected_digest

    support_files = sorted(root.glob("*/support.js"))
    assert len(support_files) == 37
    for support in support_files:
        source = support.read_text(encoding="utf-8")
        assert "unpkg.com" not in source
        assert '"../vendor/react-18.3.1.production.min.js"' in source
        assert '"../vendor/react-dom-18.3.1.production.min.js"' in source


def test_all_37_hosted_lessons_preload_only_the_first_audio_segment() -> None:
    root = ROOT / "web/public/luban-preview"
    entry_lessons = sorted(root.glob("*/lesson.html"))
    lessons = sorted(root.glob("*/lesson*.html"))

    assert len(entry_lessons) == 37
    for lesson in lessons:
        source = lesson.read_text(encoding="utf-8")
        assert all(line == line.rstrip() for line in source.splitlines())
        assert source.count("<audio data-luban-prewarm") == 1
        assert "b0.mp3?v=" in source
        assert re.search(r'audioVersion="[0-9a-f]{16}";', source)
        preload = re.search(r'src="(audio/[^"]*b0\.mp3)\?v=', source)
        assert preload is not None
        assert (lesson.parent / preload.group(1)).is_file()


def test_all_hosted_audio_manifests_have_every_declared_mp3() -> None:
    root = ROOT / "web/public/luban-preview"

    assert not list(root.glob("**/.DS_Store"))
    manifests = sorted(root.glob("*/audio/**/manifest.json"))
    assert len(manifests) >= 37
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for segment in manifest.get("segments") or []:
            segment_id = str(segment.get("id") or "")
            assert segment_id
            assert (manifest_path.parent / f"{segment_id}.mp3").is_file()
