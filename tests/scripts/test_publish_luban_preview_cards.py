from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from urllib.parse import quote

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
    assert sum(len(station.teach) for station in _mod.STATIONS.values()) == 74
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
    assert all(station.pack_dir not in {"P40_C02", "P40_A01_PROCESS", "P40_S07B"}
               for station in _mod.STATIONS.values())


def test_new_finished_audio_sources_are_tracked_for_clean_clone_rebuilds() -> None:
    pack_dirs = ("P40_B02", "P40_D14", "P40_N02", "P40_N03")
    expected = sorted(
        path.relative_to(REPO).as_posix()
        for pack_dir in pack_dirs
        for path in (_mod.FINISHED / pack_dir / "audio").glob("**/*.mp3")
    )
    tracked = set(
        subprocess.check_output(
            ["git", "ls-files", "--", *expected], cwd=REPO, text=True
        ).splitlines()
    )

    assert len(expected) == 96
    assert tracked == set(expected)


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


@pytest.mark.parametrize(("station_id", "candidate_count"), [("n01", 16), ("s05", 18), ("x01", 15)])
def test_candidate_review_packets_are_complete_and_never_machine_signed(
    station_id: str, candidate_count: int
) -> None:
    path = _mod._practice_review_packet_path(station_id.upper())
    packet = json.loads(path.read_text(encoding="utf-8"))

    assert packet["schema"] == "luban_practice_review_packet.v1"
    assert packet["candidate_count"] == candidate_count
    assert packet["human_gate"] == {
        "required_roles": ["teaching", "scoring"],
        "machine_must_not_sign": True,
    }
    signed_rows = 0
    for row in packet["items"]:
        decision = row["decision"]
        review = decision["review"]
        if review["status"] == "pending":
            # 未签发题必须整块留空——机器预填只允许进独立 candidates 文件。
            assert review["signatures"] == []
            assert decision["fact_id"] == ""
            assert decision["skeleton_id"] == ""
            assert decision["probe_role"] == ""
            assert decision["source_anchor"] == ""
            assert decision["source_sha256"] == ""
            continue
        # 已签发题必须携带完整的 owner 责任链,不接受裸机器签名。
        signed_rows += 1
        assert review["status"] == "signed"
        assert review["verdict"] == "approved"
        assert review["reviewed_content_sha256"] == row["content_sha256"]
        assert all(review["checks"][name] is True for name in review["checks"])
        roles = {sig["role"] for sig in review["signatures"]}
        assert roles == {"teaching", "scoring"}
        for sig in review["signatures"]:
            assert sig["reviewer_id"].startswith("owner")
            assert sig["signed_at"].strip()
        assert decision["fact_id"] and decision["skeleton_id"]
        assert decision["probe_role"] in {"anchor", "immediate_confirm", "d1_probe"}
        assert decision["source_anchor"]
        assert len(decision["source_sha256"]) == 64
        assert decision["revoked"] is False
    assert packet["eligible_count"] == signed_rows
    assert all(row["authoring_anchor"].startswith("compiled_html:") for row in packet["items"])
    assert all(len(row["authoring_sha256"]) == 64 for row in packet["items"])


@pytest.mark.parametrize("station_id", ["n01", "s05", "x01"])
def test_candidate_exact_bridge_url_stays_below_wechat_budget(station_id: str) -> None:
    authority = json.loads(
        (_mod.AUTHORITY_HOST / f"{station_id}.practice.authority.json").read_text(
            encoding="utf-8"
        )
    )
    surface = authority["surfaces"][0]
    by_id = {item["variant_id"]: item for item in authority["items"]}
    answers = [
        {
            "variant_id": variant_id,
            "selected_option_id": by_id[variant_id]["options"][0]["option_id"],
        }
        for variant_id in surface["variant_ids"]
    ]
    url = (
        "/packageDeeptutor/pages/luban/retest/retest?mode=forward&presentation=receipt"
        f"&pack_id={quote(authority['pack_id'])}"
        f"&practice_surface={quote(surface['surface_id'])}"
        f"&projection_receipt={quote(surface['projection_receipt'])}"
        f"&answers={quote(json.dumps(answers, ensure_ascii=False, separators=(',', ':')))}"
    )
    assert len(url) < 1800


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


def test_degrade_practice_entry_replaces_link_with_warm_copy_and_is_idempotent() -> None:
    html = (
        '<a href="practice.html" style="background:#2c8a5b;color:#fff;'
        'cursor:pointer;">做练习</a>'
        '<a href="practice2.html" style="flex:1;">全集做练习 →</a>'
        '<a href="lesson2.html">下一集</a>'
    )
    degraded, hits = _mod._degrade_practice_entry(html)
    assert hits == 2
    # 练习入口不再可点，改为教研签发中的暖文案。
    assert 'href="practice' not in degraded
    assert '做练习' not in degraded
    assert degraded.count(_mod.PRACTICE_GATE_COPY) == 2
    assert 'data-luban-practice-gate="pending"' in degraded
    assert "cursor:default" in degraded
    # 暖基调，绝不含"看穿/识破"类挑短语气。
    for banned in ("看穿", "识破", "揭穿", "露馅"):
        assert banned not in _mod.PRACTICE_GATE_COPY
    # 讲解页互链不受影响。
    assert 'href="lesson2.html"' in degraded
    # 幂等：降级态再跑一次不再命中。
    again, again_hits = _mod._degrade_practice_entry(degraded)
    assert again_hits == 0
    assert again == degraded


def test_hosted_reachability_gate_follows_supply_ready_for_whole_corpus() -> None:
    """全语料闸：非 supply_ready 的注册 pack 讲解页不得留可点练习入口。

    reachability 单一权威 = ``supply_ready``。此测试把发布产物层锁死，避免未来
    有人重发某个未签发 pack 时又放出可点的"做练习"入口（用户点进去必吃
    ``practice_not_released``）。同时校验 ``published_lesson_sha256`` 与降级后的
    托管 ``lesson.html`` 一致（runtime / manifest sha 校验的前提）。
    """
    from deeptutor.services.luban_lesson.practice_html import (
        compiled_practice_eligibility_summary,
    )

    entry_re = re.compile(r'<a\s+href="practice\d*\.html"', re.IGNORECASE)
    checked_ready = 0
    checked_gated = 0
    for authority_path in sorted(
        _mod.AUTHORITY_HOST.glob("*.practice.authority.json")
    ):
        sid = authority_path.name.split(".", 1)[0]
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
        supply_ready = bool(
            compiled_practice_eligibility_summary(authority)["supply_ready"]
        )
        lesson = _mod.HOST / sid / "lesson.html"
        if not lesson.is_file():
            continue
        # 无论闸态，authority 记录的 lesson sha 必须与托管产物一致。
        assert authority.get("published_lesson_sha256") == _sha(lesson), (
            f"{sid}: published_lesson_sha256 drifted from hosted lesson.html"
        )
        for hosted_lesson in sorted((_mod.HOST / sid).glob("lesson*.html")):
            html = hosted_lesson.read_text(encoding="utf-8")
            if supply_ready:
                continue
            assert not entry_re.search(html), (
                f"{sid}/{hosted_lesson.name}: non-supply_ready pack still exposes a "
                "clickable practice entry (reachability drifted from supply_ready)"
            )
        if supply_ready:
            checked_ready += 1
        else:
            checked_gated += 1
    assert checked_gated, "expected at least one gated (non-supply_ready) pack"


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
    assert 'value="{{ b.isList }}"' in rendered
    assert "b.type === 'ul' || b.type === 'ol'" not in rendered
    assert "entry_ticket" in rendered
    assert 'current.searchParams.get("entry_ticket")' not in rendered
    assert 'new URLSearchParams(String(current.hash||"").replace(/^#/,""))' in rendered
    assert "lesson-viewed" in rendered
    assert 'data-luban-ask-composer' in rendered
    assert 'data-luban-ask-history' in rendered
    assert rendered.index('data-luban-ask-thread') < rendered.index('data-luban-ask-composer')
    assert rendered.index('data-luban-ask-composer') < rendered.index('<textarea value="{{ askText }}"')


def test_teaching_card_keeps_first_answer_when_second_question_starts() -> None:
    source = (
        _mod.FINISHED / "P40_F16" / "P40_F16.teach.dc.html"
    ).read_text(encoding="utf-8")
    rendered = _mod.transform_teach(source, "F16")
    match = _mod._SUBMIT_ASK_RE.search(rendered)
    assert match is not None
    runtime, _digest = _mod._render_tutorbot_sheet_runtime()
    script = "global.window={};\n" + runtime + """
global.window.__lubanCardEntryTicket="entry-ticket";
global.window.location={href:"https://example.test/luban-preview/f16/lesson.html"};
let fetchCount=0;
global.fetch=async()=>{fetchCount+=1;return {ok:true,json:async()=>({stream:{url:"/api/v1/ws",protocol:"luban-preview-v1",ticket:"stream-ticket",turn_id:"turn-1"}})}};
let socket=null;
global.WebSocket=class { constructor(){socket=this;} send(){} };
""" + f"class TeachingCard {{\n{match.group(0)}\n" + """
  setState(next){ this.state={...this.state,...next}; }
}
(async()=>{
  const card=new TeachingCard();
  card.beats=[["b0",0,10,"当前"]]; card.narr=["讲解"]; card.qa=[]; card.keycards=["要点"];
  card.state={askText:"第一问",askQuestion:"",askHistory:[],askLoading:false,askBlocks:[],askError:"",askWorkflowEntries:[],askWorkflowExpanded:false,t:0};
  await card.submitAsk();
  socket.onmessage({data:JSON.stringify({type:"content",seq:1,content:"第一答"})});
  card.setState({askText:"过早的第二问"});
  await card.submitAsk();
  if(fetchCount!==1)throw new Error("second turn started before first done");
  if(card.state.askHistory.length!==0)throw new Error("partial first answer was archived");
  socket.onmessage({data:JSON.stringify({type:"done",seq:2})});
  card.setState({askText:"第二问"});
  await card.submitAsk();
  if(card.state.askHistory.length!==1)throw new Error("first turn was not archived");
  if(card.state.askHistory[0].question!=="第一问")throw new Error("first question was replaced");
  if(card.state.askHistory[0].blocks[0].parts[0].text!=="第一答")throw new Error("first answer was replaced");
  if(card.state.askQuestion!=="第二问")throw new Error("second submitted question was not snapshotted");
  if(card.state.askText!=="")throw new Error("composer was not cleared for the next message");
  if(fetchCount!==2)throw new Error("second turn did not start after first done");
})().catch((error)=>{console.error(error);process.exit(1);});
"""
    checked = subprocess.run(
        ["node", "-"], input=script, text=True, capture_output=True, check=False
    )
    assert checked.returncode == 0, checked.stderr


def test_practice_transform_replaces_authoring_preview_ai_with_same_tutorbot_stream() -> None:
    source_path = (
        _mod.FINISHED / "P40_B02" / "P40_B02.practice.up.dc.html"
    )
    source = source_path.read_text(encoding="utf-8")
    compiled = _mod.compile_practice_surface(
        "B02",
        surface_id="practice.html",
        html=source,
        source_path=str(source_path),
        source_html_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
    )

    rendered = _mod.transform_practice(
        source,
        pack_id="B02",
        compiled_surface=compiled["surface"],
        items=compiled["items"],
    )

    assert "window.claude" not in rendered
    assert "LubanTutorbotSheetRuntime" in rendered
    assert 'fetch("/api/v1/luban-preview/ai-ask"' in rendered
    assert 'type:"subscribe_turn"' in rendered
    assert 'contextId:"B02"' in rendered
    assert "entry_ticket" in rendered
    assert "currentScene" in rendered
    assert "currentCaption" in rendered
    assert "carryCapability(next).toString()" in rendered


def test_practice_tutorbot_context_supports_drawn_question_templates() -> None:
    source_path = _mod.FINISHED / "P40_A02" / "P40_A02.practice.dc.html"
    source = source_path.read_text(encoding="utf-8")
    compiled = _mod.compile_practice_surface(
        "A02",
        surface_id="practice.html",
        html=source,
        source_path=str(source_path),
        source_html_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
    )

    rendered = _mod.transform_practice(
        source,
        pack_id="A02",
        compiled_surface=compiled["surface"],
        items=compiled["items"],
    )

    assert 'typeof this.curCtx==="function"' in rendered
    assert "Array.isArray(state.drawn)" in rendered
    assert 'typeof this.qAt==="function"' in rendered
    assert "Array.isArray(this.Q)" in rendered
    assert "currentQuestion.stem||currentQuestion.q" in rendered
    assert 'contextId:"A02"' in rendered


def test_all_published_practice_tutorbot_methods_are_valid_javascript() -> None:
    pages = sorted(_mod.HOST.glob("*/practice*.html"))
    assert len(pages) == 43
    classes = []
    for index, page in enumerate(pages):
        match = _mod._SUBMIT_ASK_RE.search(page.read_text(encoding="utf-8"))
        assert match is not None, page
        classes.append(f"class PracticeCard{index} {{\n{match.group(0)}\n}}")

    checked = subprocess.run(
        ["node", "--check", "-"],
        input="\n".join(classes),
        text=True,
        capture_output=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr


def test_practice_tutorbot_keeps_single_turn_authority_until_done() -> None:
    page = _mod.HOST / "a02" / "practice.html"
    match = _mod._SUBMIT_ASK_RE.search(page.read_text(encoding="utf-8"))
    assert match is not None
    script = """
global.window={
  LubanTutorbotSheetRuntime:{isPublicEvent:()=>true,finalResponse:(event)=>event.content||""},
  __lubanCardEntryTicket:"entry-ticket",
  location:{href:"https://example.test/luban-preview/a02/practice.html"}
};
global.fetch=async()=>({ok:true,json:async()=>({stream:{url:"/api/v1/ws",protocol:"luban-preview-v1",ticket:"stream-ticket",turn_id:"turn-1"}})});
let socket=null;
global.WebSocket=class { constructor(){socket=this;} send(){} };
""" + f"class PracticeCard {{\n{match.group(0)}\n" + """
  setState(next){ this.state={...this.state,...next}; }
}
(async()=>{
  const card=new PracticeCard();
  card.state={askText:"为什么",askLoading:false,drawn:[{stem:"题干",opts:["甲","乙"],c:0}],idx:0,sel:-1,revealed:false};
  await card.submitAsk();
  if(!card.state.askLoading)throw new Error("turn unlocked before stream event");
  socket.onmessage({data:JSON.stringify({type:"content",seq:1,content:"第一段"})});
  if(!card.state.askLoading)throw new Error("turn unlocked on content");
  socket.onmessage({data:JSON.stringify({type:"done",seq:2})});
  if(card.state.askLoading)throw new Error("turn remained locked after done");
})().catch((error)=>{console.error(error);process.exit(1);});
"""
    checked = subprocess.run(
        ["node", "-"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr


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
        "_compile_practice_outputs",
        lambda *_args, **_kwargs: ({"practice.html": "practice"}, {}),
    )
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
    assert "&projection_receipt=" in public_html
    assert "&answers=" in public_html
    assert "&answer_indexes=" not in public_html
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


def test_variant_audit_packet_writes_pending_decision_cards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_mod, "PRACTICE_REVIEW_PACKET_DIR", tmp_path)
    written = _mod.write_variant_audit_packet("s05")
    packet = json.loads((tmp_path / "s05.variant.review.json").read_text("utf-8"))
    assert written  # 相对 REPO 路径由 CLI 打印；此处只关心产物本身
    assert packet["schema"] == "luban_variant_review_packet.v1"
    assert packet["pack_id"] == "S05"
    assert packet["bank_status"] == "signed"
    assert packet["candidate_count"] == 75
    # 2026-07-17 owner 委托签发落地(S05 74 签/1 排除,eligible 68 = 74 - 6 extension)。
    # 守卫精神不变:机器绝不自铸签名 —— 每条 eligible 决策必须携带完整签名链
    # (owner-delegated reviewer + 签名信封摘要 + checks 全真),pending 必须零签名。
    assert packet["eligible_count"] == 68
    assert packet["human_gate"]["machine_must_not_sign"] is True
    signed_rows = [r for r in packet["items"] if r["decision"]["review"]["status"] == "signed"]
    pending_rows = [r for r in packet["items"] if r["decision"]["review"]["status"] == "pending"]
    assert len(signed_rows) == 74
    assert len(pending_rows) == 1  # 被裁决排除的 50kW 事实项保持未签
    for row in signed_rows:
        review = row["decision"]["review"]
        assert review["signatures"], "signed 决策必须有签名记录"
        assert all(
            str(sig.get("reviewer_id", "")).startswith("owner-delegated:")
            for sig in review["signatures"]
        )
        envelope = review.get("signature_envelope_sha256", "")
        assert isinstance(envelope, str) and len(envelope) == 64
        assert all(review["checks"].values())
    for row in pending_rows:
        review = row["decision"]["review"]
        assert review["signatures"] == []
        assert not any(review["checks"].values())


def test_variant_audit_packet_kind_is_wired_into_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_mod, "PRACTICE_REVIEW_PACKET_DIR", tmp_path)
    assert _mod.main(["--write-practice-audit-packet", "--kind", "variant", "s05"]) == 0
    assert (tmp_path / "s05.variant.review.json").is_file()
    # --kind variant 只能与审核包模式联用（不允许污染发布/检查路径）。
    with pytest.raises(SystemExit):
        _mod.main(["--kind", "variant", "s05"])


def test_variant_audit_packet_missing_bank_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_mod, "PRACTICE_REVIEW_PACKET_DIR", tmp_path)
    monkeypatch.setattr(_mod, "VARIANT_BANK_DIR", tmp_path / "empty")
    with pytest.raises(_mod.TransformError):
        _mod.write_variant_audit_packet("s05")


def test_variant_audit_packet_reuses_signing_gate_no_raw_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """对抗审查 B3：审核包入口必须走 manifest sha + signed 同一签发闸——
    sha 漂移或 candidate 状态的 bank 一律 fail-closed，禁 raw 第二 loader。"""
    bank_dir = tmp_path / "banks"
    bank_dir.mkdir()
    (bank_dir / "_pack_manifest.json").write_text(
        json.dumps(
            {
                "projection_green": ["S05"],
                "packs": [{"pack_id": "S05", "content_sha256": "a" * 64}],
            }
        ),
        encoding="utf-8",
    )
    bank_path = bank_dir / "_S05_variant_bank.v0.json"
    monkeypatch.setattr(_mod, "PRACTICE_REVIEW_PACKET_DIR", tmp_path)
    monkeypatch.setattr(_mod, "VARIANT_BANK_DIR", bank_dir)

    # sha 漂移：bank signed 但与 manifest 登记的 pack sha 失配
    bank_path.write_text(
        json.dumps(
            {
                "pack_id": "S05",
                "status": "signed",
                "source_pack_sha256": "b" * 64,
                "variants": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(_mod.TransformError):
        _mod.write_variant_audit_packet("s05")

    # candidate 状态：未签发 bank 不产人审包
    bank_path.write_text(
        json.dumps(
            {
                "pack_id": "S05",
                "status": "candidate",
                "source_pack_sha256": "a" * 64,
                "variants": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(_mod.TransformError):
        _mod.write_variant_audit_packet("s05")


def _write_variant_audit_fixture(
    bank_dir: Path, *, green: list[str], with_blocklist: bool = True
) -> None:
    bank_dir.mkdir(parents=True, exist_ok=True)
    (bank_dir / "_pack_manifest.json").write_text(
        json.dumps(
            {
                "projection_green": green,
                "packs": [{"pack_id": "S05", "content_sha256": "a" * 64}],
            }
        ),
        encoding="utf-8",
    )
    (bank_dir / "_S05_variant_bank.v0.json").write_text(
        json.dumps(
            {
                "pack_id": "S05",
                "status": "signed",
                "source_pack_sha256": "a" * 64,
                "variants": [],
            }
        ),
        encoding="utf-8",
    )
    if with_blocklist:
        (bank_dir / "_variant_blocklist.json").write_text(
            json.dumps({"variants": []}), encoding="utf-8"
        )


def test_variant_audit_packet_requires_projection_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """对抗审查二轮 B2：pack 不在 projection_green（撤回/未发布）时，
    审核包路径同样不得旁路 canonical 绿灯门。"""
    bank_dir = tmp_path / "banks"
    _write_variant_audit_fixture(bank_dir, green=[])
    monkeypatch.setattr(_mod, "PRACTICE_REVIEW_PACKET_DIR", tmp_path)
    monkeypatch.setattr(_mod, "VARIANT_BANK_DIR", bank_dir)
    with pytest.raises(_mod.TransformError):
        _mod.write_variant_audit_packet("s05")
    # 同一 fixture 放回绿灯即可产包（证明失败确实来自绿灯门）
    _write_variant_audit_fixture(bank_dir, green=["S05"])
    assert _mod.write_variant_audit_packet("s05")


def test_variant_audit_packet_rejects_unreadable_blocklist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """对抗审查二轮 B3：撤发 authority 不可读时 writer 必须 fail-closed，
    不得把 blocked=None 静默交给 builder 产出人审包。"""
    bank_dir = tmp_path / "banks"
    _write_variant_audit_fixture(bank_dir, green=["S05"], with_blocklist=False)
    monkeypatch.setattr(_mod, "PRACTICE_REVIEW_PACKET_DIR", tmp_path)
    monkeypatch.setattr(_mod, "VARIANT_BANK_DIR", bank_dir)
    with pytest.raises(_mod.TransformError):
        _mod.write_variant_audit_packet("s05")


# --- projection receipt 单一来源（artifact surface.projection_receipt 唯一权威）---

_EMBEDDED_RECEIPT_TEST_RE = re.compile(
    r"'&projection_receipt='\+encodeURIComponent\(\"([A-Za-z0-9_-]*)\"\)"
)


def _tamper_receipt(receipt: str) -> str:
    return receipt[:-1] + ("A" if receipt[-1] != "A" else "B")


def test_signed_decision_merge_keeps_html_receipt_byte_equal_to_artifact() -> None:
    """N01 人审 packet 已签发：decision 合并改变 receipt，HTML 必须跟 artifact 同步。

    2026-07 生产 SEV-1 根因：HTML 内嵌 receipt 在 decision 合并前计算（pending 态，
    digest 22fe9552…），artifact receipt 在合并后重算（digest 9e270564…），
    服务端 resolve_projection_receipt 按 artifact 校验 → 五题提交 100% 被拒。
    """
    station_id = "n01"
    station = _mod.STATIONS[station_id]
    rendered, authority = _mod._practice_only_outputs(
        station_id, station, finished_root=_mod.FINISHED
    )
    surface = authority["surfaces"][0]

    # 场景前提：签发（decision 合并）后 receipt 确实与 pending 期不是同一份。
    source_text = (
        _mod.FINISHED / station.pack_dir / station.practice["practice.html"]
    ).read_text(encoding="utf-8")
    pending_receipt = compile_practice_surface(
        "N01",
        surface_id="practice.html",
        html=source_text,
        source_path="tracked-n01",
        source_html_sha256=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
    )["surface"]["projection_receipt"]
    assert pending_receipt != surface["projection_receipt"]

    # 单一来源断言：HTML 内嵌 receipt 逐字节等于最终 artifact 的 receipt。
    embedded = _EMBEDDED_RECEIPT_TEST_RE.findall(rendered["practice.html"])
    assert embedded == [surface["projection_receipt"]]


def test_compile_outputs_fail_close_when_embedded_receipt_diverges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """守卫：HTML 嵌入若与 artifact receipt 不同步（第二次计算复活）必 fail-close。"""
    real = _mod.transform_compiled_practice_html

    def tampered(pack_id, *, surface, items, html):
        fake = dict(surface)
        fake["projection_receipt"] = _tamper_receipt(str(surface["projection_receipt"]))
        return real(pack_id, surface=fake, items=items, html=html)

    monkeypatch.setattr(_mod, "transform_compiled_practice_html", tampered)
    with pytest.raises(_mod.TransformError, match="receipt"):
        _mod._practice_only_outputs(
            "n01", _mod.STATIONS["n01"], finished_root=_mod.FINISHED
        )


def test_check_fails_close_when_published_html_receipt_drifts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """守卫（--check 路径）：发布产物中 HTML 内嵌 receipt != artifact receipt 必 FAIL。"""
    station_id = "n01"
    host = tmp_path / "host"
    shutil.copytree(_mod.HOST / station_id, host / station_id)
    authority_dir = tmp_path / "authority"
    authority_dir.mkdir()
    authority_name = f"{station_id}.practice.authority.json"
    shutil.copy2(_mod.AUTHORITY_HOST / authority_name, authority_dir / authority_name)

    hosted = host / station_id / "practice.html"
    text = hosted.read_text(encoding="utf-8")
    receipt = _EMBEDDED_RECEIPT_TEST_RE.search(text).group(1)
    hosted.write_text(text.replace(receipt, _tamper_receipt(receipt)), encoding="utf-8")

    monkeypatch.setattr(_mod, "HOST", host)
    monkeypatch.setattr(_mod, "AUTHORITY_HOST", authority_dir)
    with pytest.raises(_mod.TransformError, match="receipt"):
        _mod.check_practice_only(
            station_id, _mod.STATIONS[station_id], finished_root=_mod.FINISHED
        )


def test_embedded_projection_receipt_requires_exactly_one_receipt() -> None:
    with pytest.raises(_mod.TransformError, match="receipt"):
        _mod._embedded_projection_receipt("<html></html>", context="x")
    duplicated = (
        "'&projection_receipt='+encodeURIComponent(\"abc\")"
        "'&projection_receipt='+encodeURIComponent(\"def\")"
    )
    with pytest.raises(_mod.TransformError, match="receipt"):
        _mod._embedded_projection_receipt(duplicated, context="x")
    single = "'&projection_receipt='+encodeURIComponent(\"abc-DEF_123\")"
    assert _mod._embedded_projection_receipt(single, context="x") == "abc-DEF_123"
