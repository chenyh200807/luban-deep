import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "artifacts/luban_case_family_assets/diagram_microlesson/validate_video_first_preview.mjs"


def run_validator(rendered: Path, practice: Path) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for validate_video_first_preview.mjs")
    return subprocess.run(
        [node, str(VALIDATOR), str(rendered), str(practice)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def write_valid_pair(tmp_path: Path) -> tuple[Path, Path]:
    rendered = tmp_path / "topic.rendered.html"
    practice = tmp_path / "topic.practice.html"
    rendered.write_text(
        """<!doctype html><html><head><style>
        .lesson.orientation-adaptive{}.stage{aspect-ratio:4/5}.lesson.theater{}.lesson.controls-visible{}
        @media(orientation:landscape){.stage{aspect-ratio:4/3}}
        </style></head><body>
        <section class="lesson orientation-adaptive">
        <a href="topic.practice.html">开始闯关</a>
        <video playsinline poster="poster.png"></video>
	        <button class="center-play">播放视频</button>
	        <button id="theaterToggle" data-theater-toggle="1">全屏</button>
	        <input type="range">
        <button class="beat-dot">先学</button><button class="beat-dot">错觉</button><button class="beat-dot">采分</button>
        <script type="application/json" id="lessonData">{
          "video_beats":[
            {"id":"hook","stage":"hook"},
            {"id":"trap","stage":"trap"},
            {"id":"logic","stage":"logic"},
            {"id":"worked","stage":"worked"},
            {"id":"score","stage":"score"}
          ],
          "timing":{"segments":[
            {"kind":"teach","state":"hook","claim":true,"anchor":"exam_context.hook","text":"为什么学"},
            {"kind":"teach","state":"score","claim":true,"anchor":"teaching_spine.exam_phrase","text":"写采分句"},
            {"kind":"closing","state":"closing","claim":true,"anchor":"teaching_spine.exam_phrase","text":"收个尾,开始闯关"}
          ]}
        }</script>
        </section>
        </body></html>""",
        encoding="utf-8",
    )
    practice.write_text(
        """<!doctype html><html><body>
        <section class="q"><svg></svg><input><p>先作答</p></section>
        <section class="q"><svg></svg><input><p>先作答</p></section>
        <section class="q"><svg></svg><textarea></textarea><p>采分句</p></section>
        </body></html>""",
        encoding="utf-8",
    )
    return rendered, practice


def test_video_first_preview_validator_passes_valid_shell(tmp_path: Path) -> None:
    rendered, practice = write_valid_pair(tmp_path)

    result = run_validator(rendered, practice)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "video-first preview gate: PASS" in result.stdout


def test_video_first_preview_validator_fails_student_internal_token(tmp_path: Path) -> None:
    rendered, practice = write_valid_pair(tmp_path)
    practice.write_text(practice.read_text(encoding="utf-8") + "candidate", encoding="utf-8")

    result = run_validator(rendered, practice)

    assert result.returncode == 1
    assert "student_safe_tokens" in result.stdout


def test_video_first_preview_validator_fails_missing_closing(tmp_path: Path) -> None:
    rendered, practice = write_valid_pair(tmp_path)
    html = rendered.read_text(encoding="utf-8")
    html = html.replace('{"kind":"closing","state":"closing","claim":true,"anchor":"teaching_spine.exam_phrase","text":"收个尾,开始闯关"}', '{"kind":"teach","state":"score","claim":true,"anchor":"teaching_spine.exam_phrase","text":"写采分句"}')
    rendered.write_text(html, encoding="utf-8")

    result = run_validator(rendered, practice)

    assert result.returncode == 1
    assert "closing_segment" in result.stdout
