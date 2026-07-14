#!/usr/bin/env python3
"""发布 finished 深母题教学卡到 web/public/luban-preview/<站点>/（打包层，纯确定性）。

背景：
- 卡唯一源 = ``artifacts/luban_case_family_assets/diagram_microlesson/finished/<PACK>/``
  （teach/practice .dc.html + support.js + assets/ + audio/）。托管副本永远由本脚本
  派生，不手改生成物。
- 2026-07-05 owner 真机反馈两个问题在打包层治本：
  1. **没有声音**：托管漏了 ``audio/``（根因链 = ``.gitignore`` 全局 ``*.mp3``
     把 11 段配音静默挡在 commit df688f571 之外 → 线上 404 → 回落 webSpeak 在微信
     web-view 静默失败）。本脚本无条件拷贝 audio/，.gitignore 已加窄豁免。
  2. **按钮触发真全屏 + 自适应**：把 owner 参考实现（起重吊装安全 S02 卡 +
     ``全屏播放_回灌母版.md`` §B）的「模拟全屏 + 舞台 min(vw/390,vh/462) 等比缩放 +
     点屏唤出控制条」机制以锚定替换（fail-closed：锚不中即报错退出）回灌进每张
     teach 卡。2026-07-05 owner 澄清推翻"进入即自动全屏"：入场保持原正常版式，
     只有点卡内既有「全屏」按钮（stage 角标 + 控制条各一枚，均绑 ``{{ fullscreen }}``）
     才进入全屏，再点退回正常版式（同一 toggle 方法双向接管，不新增第二按钮）。
- 微信 web-view 外链字体静默失败：fonts.googleapis.com 三行外链替换为共享自托管
  子集 ``../fonts/fonts.css``（Noto Sans SC 可变字重 + Long Cang，子集覆盖全部
  finished 卡出现过的字符；生成命令见 web/public/luban-preview/fonts/README.md）。
- finished 卡的 ``support.js`` 原本在启动时从 unpkg 拉 React/ReactDOM，国内弱网会让
  整张卡白屏。发布器把固定版本 URL 锚定改写到 ``../vendor/`` 同域文件；React
  启动依赖与按需 Babel 后备均自托管，SRI 仍校验相同字节，源卡保持只读。
- 2026-07-05 owner 真机反馈（第三轮）普通模式两问题在打包层治本：
  3. **普通态没铺满 + 露纯黑底**：卡源 max-width:390px + body #101315 → 宽视口两侧
     /下方露近黑底。治法 = ``.lz-card{zoom:var(--lz-fit)}``（zoom 参与布局：滚动高度
     /点击热区随缩放走，无 transform 的热区漂移/滚动截断问题），JS 按
     ``min(innerWidth/390, 2.0)`` 设 --lz-fit（cap 2.0：768 iPad 竖屏 1.97 仍满铺，
     >780px 桌面封顶居中防过度放大）；html/body 背景改为卡自身 .lz-card 深墨底色
     （逐卡运行时提取，锚不中即 fail-closed），残留边距与卡浑然一体。全屏态
     ``body.luban-fs .lz-card{zoom:1!important}`` 归位，退出全屏回到宽度自适应态。
  4. **「问追AI」保持在教学卡内**：微信 ``web-view`` 会覆盖原生层，不能由站点页
     可靠地叠一个抽屉；问答层因此必须由教学卡本身拥有。发布层不得把 ``openAsk``
     改写为跳转聊天页——那会丢掉正在看的视频和时间轴。卡内既有抽屉从底部推入，
     关闭后仍留在同一教学画面；实际答疑能力仍由既有 TutorBot 主链路负责，不在此
     打包器新增聊天协议或会话 authority。

用法::

    python3 scripts/publish_luban_preview_cards.py           # 发布全部注册站点
    python3 scripts/publish_luban_preview_cards.py f16 c02   # 只发布指定站点
    python3 scripts/publish_luban_preview_cards.py --practice-only --check
                                                        # 从 tracked HTML 重编并核对派生物
    python3 scripts/publish_luban_preview_cards.py \\
      --finished-root /absolute/path/to/finished             # 显式使用外部 finished 成品根

站点注册表 = 本文件 STATIONS：新增托管卡在这里登记（station id = pack_id 小写，
manifest 的 card_hosted 按 web/public/luban-preview/<pack_id小写>/lesson.html 扫描）。
上下/中下集均保留独立入口：lesson.html、lesson2.html、lesson3.html。集内链接
由发布器确定性重写，不改 pack 级 read_model / 练习权威。
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from deeptutor.services.luban_lesson.practice_html import (
    build_practice_authority,
    compile_practice_surface,
    transform_compiled_practice_html,
)
from scripts.build_luban_pack_manifest import MANIFEST_PATH as PACK_MANIFEST_PATH
from scripts.build_luban_pack_manifest import build_manifest

FINISHED = REPO / "artifacts" / "luban_case_family_assets" / "diagram_microlesson" / "finished"
HOST = REPO / "web" / "public" / "luban-preview"
AUTHORITY_HOST = REPO / "deeptutor" / "services" / "luban_lesson" / "compiled"
FONTS_CSS = HOST / "fonts" / "fonts.css"
JWEIXIN_JS = HOST / "vendor" / "jweixin.js"
TUTORBOT_SHEET_RUNTIME = HOST / "vendor" / "luban-tutorbot-sheet-runtime.js"
_TUTORBOT_SHEET_RUNTIME_SOURCES = (
    REPO / "yousenwebview" / "packageDeeptutor" / "utils" / "markdown.js",
    REPO / "yousenwebview" / "packageDeeptutor" / "utils" / "workflow-status.js",
)
SUPPORT_RUNTIME_ASSETS = (
    HOST / "vendor" / "babel-7.26.4.min.js",
    HOST / "vendor" / "babel-7.29.0.min.js",
    HOST / "vendor" / "react-18.3.1.production.min.js",
    HOST / "vendor" / "react-dom-18.3.1.production.min.js",
)

_SUPPORT_RUNTIME_URL_GROUPS = (
    (
        (
            "https://unpkg.com/@babel/standalone@7.26.4/babel.min.js",
            "../vendor/babel-7.26.4.min.js",
        ),
        (
            "https://unpkg.com/@babel/standalone@7.29.0/babel.min.js",
            "../vendor/babel-7.29.0.min.js",
        ),
    ),
    ((
        "https://unpkg.com/react@18.3.1/umd/react.production.min.js",
        "../vendor/react-18.3.1.production.min.js",
    ),),
    ((
        "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js",
        "../vendor/react-dom-18.3.1.production.min.js",
    ),),
)


@dataclass(frozen=True)
class Station:
    pack_dir: str                       # finished/ 下的目录名
    teach: dict[str, str]               # 托管名 -> 源文件名（lesson.html 必须在场）
    practice: dict[str, str]            # 托管名 -> 源文件名（支持多幕闯关）
    href_map: dict[str, str] = field(default_factory=dict)  # 卡内互链重写


def _source_name(pack: str, surface: str, stage: str) -> str:
    suffix = f".{stage}" if stage else ""
    return f"{pack}.{surface}{suffix}.dc.html"


def _hosted_name(surface: str, index: int) -> str:
    return f"{surface}.html" if index == 0 else f"{surface}{index + 1}.html"


def _staged_station(
    pack: str,
    *,
    teach_stages: tuple[str, ...] = ("",),
    practice_stages: tuple[str, ...] = ("",),
) -> Station:
    """从一个 finished 成品目录派生托管文件名和全部卡内互链。

    目录名和文件前缀始终同源；C02 与 S07 的版本选择只在 STATIONS 明示，
    不在发布循环里猜测或降级到同名旧目录。
    """
    teach = {
        _hosted_name("lesson", index): _source_name(pack, "teach", stage)
        for index, stage in enumerate(teach_stages)
    }
    practice = {
        _hosted_name("practice", index): _source_name(pack, "practice", stage)
        for index, stage in enumerate(practice_stages)
    }
    href_map = {src: hosted for hosted, src in {**teach, **practice}.items()}
    return Station(
        pack_dir=pack,
        teach=teach,
        practice=practice,
        href_map=href_map,
    )


def _p40(pack: str) -> Station:
    return _staged_station(pack)


STATIONS: dict[str, Station] = {
    "a01": _staged_station("P40_A01", teach_stages=("up", "down")),
    "a02": _staged_station("P40_A02", teach_stages=("up", "down")),
    "b02": _staged_station(
        "P40_B02",
        teach_stages=("up", "down"),
        practice_stages=("up", "down"),
    ),
    "c01": _staged_station("P40_C01", teach_stages=("up", "down")),
    # C02 唯一使用独立 C02 成品目录，不回退到历史 P40_C02 目录。
    "c02": _staged_station("C02", teach_stages=("up", "down")),
    "c04": _p40("P40_C04"),
    "c05": _staged_station("P40_C05", teach_stages=("up", "down")),
    "c06": _staged_station("P40_C06", teach_stages=("up", "down")),
    "c07": _staged_station("P40_C07", teach_stages=("up", "down")),
    "d11": _p40("P40_D11"),
    "d12": _staged_station("P40_D12", teach_stages=("up", "down")),
    "d13": _staged_station("P40_D13", teach_stages=("up", "down")),
    "d14": _staged_station("P40_D14", teach_stages=("up", "middle", "down")),
    "e05": _p40("P40_E05"),
    "f02": _p40("P40_F02"),
    "f03": _staged_station("P40_F03", teach_stages=("up", "down")),
    "f04": _staged_station("P40_F04", teach_stages=("up", "down")),
    "f05": _staged_station("P40_F05", teach_stages=("up", "down")),
    "f16": _p40("P40_F16"),
    "g01": _staged_station("P40_G01", teach_stages=("up", "down")),
    "g02": _p40("P40_G02"),
    "g03": _staged_station("P40_G03", teach_stages=("up", "middle", "down")),
    "g04": _staged_station("P40_G04", teach_stages=("up", "down")),
    "j01": _p40("P40_J01"),
    "k01": _staged_station("P40_K01", teach_stages=("up", "down")),
    "n01": _staged_station("P40_N01", teach_stages=("up", "down")),
    "n02": _staged_station("P40_N02", teach_stages=("up", "down")),
    # N03 最终成品已拆为上下集；旧单页登记会静默继续托管历史版本。
    "n03": _staged_station("P40_N03", teach_stages=("up", "down")),
    "q01": _staged_station("P40_Q01", teach_stages=("up", "down")),
    "q02": _staged_station("P40_Q02", teach_stages=("up", "down")),
    "q03": _staged_station("P40_Q03", teach_stages=("up", "down")),
    "r01": _staged_station("P40_R01", teach_stages=("up", "down")),
    "s01": _staged_station(
        "P40_S01",
        teach_stages=("up", "middle", "down"),
        practice_stages=("up", "middle", "down"),
    ),
    "s02": _p40("P40_S02"),
    "s05": _p40("P40_S05"),
    "s06": _staged_station("P40_S06", teach_stages=("up", "down")),
    # S07 必须使用安全事故成品；P40_S07B 的 dc runtime 实为 N03 流水施工旧错版。
    "s07": _p40("P40_S07"),
    "x01": _staged_station("P40_X01", teach_stages=("up", "down")),
    "x02": _staged_station("P40_X02", teach_stages=("up", "down")),
    "x03": _staged_station("P40_X03", teach_stages=("up", "middle", "down")),
}

# ───────────────────────── 字体（全部 html） ─────────────────────────

_FONT_LINKS_OLD = (
    '<link rel="preconnect" href="https://fonts.googleapis.com"/>\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;900'
    '&family=Long+Cang&display=swap" rel="stylesheet"/>'
)
_FONT_LINKS_NEW = '<link href="../fonts/fonts.css" rel="stylesheet"/>'

# 卡内问答是学习舞台的第二层，不是一次路由跳转。动画只属于呈现层，不能影响
# openAsk/closeAsk 的状态语义或播放器时间轴。
_ASK_SHEET_MOTION_CSS = (
    "<style data-luban-ask-sheet-motion>"
    "@keyframes lzAskSheetIn{from{transform:translateY(100%);opacity:.72}"
    "to{transform:translateY(0);opacity:1}}"
    "</style>"
)

# teach/practice 卡额外注入微信 JSSDK（practice 保存学习证据时复用）
_JWEIXIN_TAG = '<script src="../vendor/jweixin.js"></script>'


def _render_tutorbot_sheet_runtime() -> tuple[str, str]:
    """Bundle the *existing* chat Markdown/workflow kernels for the H5 sheet.

    ``web-view`` cannot render the Mini Program's WXML components, but it must
    not reimplement their semantics.  This generated browser wrapper embeds
    the exact source modules and only projects their already-parsed blocks into
    the card's DC template vocabulary.
    """
    markdown_source, workflow_source = [path.read_text(encoding="utf-8") for path in _TUTORBOT_SHEET_RUNTIME_SOURCES]
    digest = hashlib.sha256((markdown_source + "\n/* workflow */\n" + workflow_source).encode("utf-8")).hexdigest()[:16]
    rendered = f'''/* Generated by scripts/publish_luban_preview_cards.py. Do not edit. */
(function(global) {{
  var markdown = (function() {{ var module={{exports:{{}}}}; var exports=module.exports;
{markdown_source}
    return module.exports;
  }})();
  var workflow = (function() {{ var module={{exports:{{}}}}; var exports=module.exports;
{workflow_source}
    return module.exports;
  }})();
  function parts(spans) {{
    return (Array.isArray(spans) ? spans : []).map(function(part) {{
      var kind=String((part&&part.type)||"text");
      var style="";
      if(kind==="bold"||kind==="bold_italic") style+="font-weight:850;";
      if(kind==="italic"||kind==="bold_italic") style+="font-style:italic;";
      if(kind==="code") style+="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:#171b1d;border-radius:4px;padding:1px 4px;color:#f3cd91;";
      return {{text:String((part&&part.text)||""),style:style}};
    }});
  }}
  function inlineText(spans) {{ return parts(spans).map(function(part) {{ return part.text; }}).join(""); }}
  function project(block, index) {{
    var source=block&&typeof block==="object"?block:{{}};
    var kind=String(source.type||"paragraph");
    var result={{id:String(source.id||("sheet-"+index)),type:kind,parts:parts(source.content),label:String(source.label||""),variant:String(source.variant||"highlight")}};
    if(kind==="ul"||kind==="ol") {{
      result.items=(Array.isArray(source.items)?source.items:[]).map(function(item, itemIndex) {{
        return {{marker:kind==="ol"?String((item&&item.index)||itemIndex+1)+".":"•",parts:parts(item&&item.content)}};
      }});
    }} else if(kind==="blockquote") {{
      result.lines=(Array.isArray(source.lines)?source.lines:[]).map(parts);
    }} else if(kind==="code_block") {{
      result.code=String(source.content||"");
      result.language=String(source.language||"text");
    }} else if(kind==="table") {{
      result.headers=(Array.isArray(source.headers)?source.headers:[]).map(function(cell) {{ return inlineText(cell&&cell.content); }}).join(" · ");
      result.rows=(Array.isArray(source.rows)?source.rows:[]).map(function(row) {{
        return {{cells:(Array.isArray(row)?row:[]).map(function(cell) {{ return inlineText(cell&&cell.content); }}).join(" · ")}};
      }});
    }}
    return result;
  }}
  function projectMarkdown(text) {{
    return markdown.parseWithIds(String(text||"")).filter(function(block) {{ return block&&block.type!=="blank"; }}).map(project);
  }}
  function isPublicEvent(event) {{
    var source=event&&typeof event==="object"?event:{{}};
    if(String(source.visibility||"").trim().toLowerCase()==="internal") return false;
    return String(((source.metadata||{{}}).visibility)||"").trim().toLowerCase()!=="internal";
  }}
  function finalResponse(event) {{
    var metadata=(event&&event.metadata&&typeof event.metadata==="object")?event.metadata:{{}};
    var nested=(metadata.metadata&&typeof metadata.metadata==="object")?metadata.metadata:{{}};
    var response=metadata.response;
    if(typeof response!=="string"||!response.trim()) response=metadata.assistant_content;
    if((typeof response!=="string"||!response.trim())&&nested) response=nested.response;
    if(typeof response!=="string"||!response.trim()) response=nested.assistant_content;
    return typeof response==="string"?response.trim():"";
  }}
  global.LubanTutorbotSheetRuntime={{
    projectMarkdown:projectMarkdown,
    workflow:workflow,
    toWorkflowEvent:workflow.toWorkflowEvent,
    isPublicEvent:isPublicEvent,
    finalResponse:finalResponse
  }};
}})(window);
'''
    return rendered, digest


def _tutorbot_sheet_runtime_tag() -> str:
    _runtime, digest = _render_tutorbot_sheet_runtime()
    return f'<script src="../vendor/luban-tutorbot-sheet-runtime.js?v={digest}"></script>'


def _ensure_tutorbot_sheet_runtime() -> str:
    rendered, digest = _render_tutorbot_sheet_runtime()
    TUTORBOT_SHEET_RUNTIME.parent.mkdir(parents=True, exist_ok=True)
    if not TUTORBOT_SHEET_RUNTIME.is_file() or TUTORBOT_SHEET_RUNTIME.read_text(encoding="utf-8") != rendered:
        staged = TUTORBOT_SHEET_RUNTIME.with_suffix(".js.staging")
        staged.write_text(rendered, encoding="utf-8")
        staged.replace(TUTORBOT_SHEET_RUNTIME)
    return f'<script src="../vendor/luban-tutorbot-sheet-runtime.js?v={digest}"></script>'

# 用户进入讲懂卡就是明确播放意图：只预热首段 b0，缩短第一次点播放到出声；
# 其余音频仍按讲解进度懒加载，避免一次下载整卡 5MB 左右的配音。
_AUDIO_BASE_RE = re.compile(r'audioBase\s*=\s*["\']([^"\']+)["\']\s*;')
_AUDIO_VERSION_RE = re.compile(r'audioVersion\s*=\s*["\']([^"\']+)["\']\s*;')
_AUDIO_PRELOAD_SRC_RE = re.compile(
    r'<audio data-luban-prewarm preload="auto" src="([^"]+)" '
    r'aria-hidden="true" style="display:none"></audio>'
)


def _audio_preload_element(text: str) -> str:
    base_match = _AUDIO_BASE_RE.search(text)
    version_match = _AUDIO_VERSION_RE.search(text)
    if not base_match or not version_match:
        raise TransformError("anchor [audio-preload] missing audioBase/audioVersion")
    base = base_match.group(1)
    version = version_match.group(1)
    if not base.startswith("audio/") or ".." in base or not base.endswith("/"):
        raise TransformError(f"anchor [audio-preload] unsafe audioBase: {base}")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", version):
        raise TransformError(f"anchor [audio-preload] unsafe audioVersion: {version}")
    return (
        '<audio data-luban-prewarm preload="auto" '
        f'src="{base}b0.mp3?v={version}" aria-hidden="true" '
        'style="display:none"></audio>'
    )


def _version_audio_assets(text: str, src: Path) -> str:
    base_match = _AUDIO_BASE_RE.search(text)
    if not base_match:
        raise TransformError("anchor [audio-version] missing audioBase")
    base = base_match.group(1)
    if not base.startswith("audio/") or ".." in base or not base.endswith("/"):
        raise TransformError(f"anchor [audio-version] unsafe audioBase: {base}")
    audio_dir = src / base
    audio_files = sorted(audio_dir.glob("*.mp3"))
    if not audio_files:
        raise TransformError(f"finished pack incomplete: {audio_dir} missing mp3")
    digest = hashlib.sha256()
    for path in audio_files:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    version = digest.hexdigest()[:16]
    rendered, count = _AUDIO_VERSION_RE.subn(
        lambda _match: f'audioVersion="{version}";', text, count=1
    )
    if count != 1:
        raise TransformError("anchor [audio-version] missing audioVersion")
    return rendered


def _validate_audio_assets(src: Path) -> None:
    manifests = sorted((src / "audio").glob("**/manifest.json"))
    if not manifests:
        raise TransformError(f"finished pack incomplete: {src} missing audio manifest")
    missing: list[str] = []
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise TransformError(f"invalid audio manifest: {manifest_path}: {exc}") from exc
        for segment in manifest.get("segments") or []:
            segment_id = str(segment.get("id") or "").strip()
            if not segment_id or not (manifest_path.parent / f"{segment_id}.mp3").is_file():
                missing.append(str(manifest_path.parent / f"{segment_id or '<empty>'}.mp3"))
    if missing:
        raise TransformError("finished pack incomplete: missing audio " + ", ".join(missing))


def _self_host_support_runtime(text: str) -> str:
    """将 dc runtime 的固定外网依赖收口到同域、版本化的共享 vendor 资产。"""
    rendered = text
    for variants in _SUPPORT_RUNTIME_URL_GROUPS:
        matched = [pair for pair in variants if rendered.count(pair[0]) == 1]
        unexpected_duplicates = [pair[0] for pair in variants if rendered.count(pair[0]) > 1]
        if len(matched) != 1 or unexpected_duplicates:
            raise TransformError(
                "anchor [support-runtime] expected one pinned variant: "
                + ", ".join(remote for remote, _local in variants)
            )
        remote_url, local_url = matched[0]
        rendered = rendered.replace(remote_url, local_url, 1)
    return rendered


def _strip_trailing_whitespace(text: str) -> str:
    """规范化派生 HTML，避免 finished 源里的行尾空格污染发布提交。"""
    return "\n".join(line.rstrip() for line in text.split("\n"))

# ─────────────── 普通态宽度自适应 + 深墨底色（teach 卡 · 打包层） ───────────────
#
# zoom 而非 transform:scale：zoom 参与布局（文档滚动高度、点击热区、margin:0 auto
# 居中全部随缩放自然生效），transform 需要手动补偿滚动高度且易热区漂移。
# WKWebView（微信 iOS）/ XWeb（Android）/ 桌面 Chromium 均支持 zoom。
_FIT_ZOOM_CAP = 2.0  # 768 iPad 竖屏 (1.97) 仍满铺；>780px 桌面封顶居中防过度放大

_BODY_CSS_OLD = "html,body{margin:0;padding:0;}"


def _fit_css(card_bg: str) -> str:
    return (
        f"html,body{{margin:0;padding:0;background:{card_bg};}}\n"
        "  .lz-card{zoom:var(--lz-fit,1);margin:0 auto;}\n"
        "  body.luban-fs .lz-card{zoom:1!important;}"
    )


_CARD_BG_RE = re.compile(r'class="lz-card"[^>]*?background:(#[0-9a-fA-F]{3,8})')
_BODY_BG_RE = re.compile(r"body\{background:#[0-9a-fA-F]{3,8};font-family")

# ──────────────────── 全屏回灌（teach 卡 · 参考 S02/§B） ────────────────────

_FS_CSS_NEW = (
    "body.luban-fs .lz-card{position:fixed!important;top:0!important;right:0!important;"
    "bottom:0!important;left:0!important;width:100%!important;max-width:100%!important;"
    "height:100vh!important;height:100dvh!important;overflow:hidden!important;"
    "z-index:9999!important;box-shadow:none!important;background:#000!important}"
    "body.luban-fs{overflow:hidden}"
    "body.luban-fs .lz-chrome{display:none!important}"
    "body.luban-fs .lz-stagewrap{position:absolute!important;top:0!important;right:0!important;"
    "bottom:0!important;left:0!important;display:flex!important;align-items:center!important;"
    "justify-content:center!important}"
    "body.luban-fs .lz-stage{width:390px!important;height:462px!important;flex:none!important;"
    "transform:scale(var(--fs-scale,1))!important;transform-origin:center center!important}"
)

_DIDMOUNT_APPEND = (
    "document.head.appendChild(s); }\n"
    "    this.updateFitZoom();\n"
    "    this._onResize=()=>{ if(this.state.fs) this.updateFsScale(); this.updateFitZoom(); };\n"
    "    window.addEventListener('resize', this._onResize);\n"
    "    window.addEventListener('orientationchange', this._onResize);"
)

_UNMOUNT_NEW = (
    "  componentWillUnmount(){ this._dead=true; if(this._raf)cancelAnimationFrame(this._raf); "
    "this.stopSpeak(); if(this._hideT)clearTimeout(this._hideT); "
    "try{ window.removeEventListener('resize',this._onResize); "
    "window.removeEventListener('orientationchange',this._onResize); }catch(e){} }"
)

_FULLSCREEN_NEW = """  fullscreen(){ const n=!this.state.fs; this.setState({fs:n,ctrlHidden:false}); document.body.classList.toggle('luban-fs',n);
    if(n){ this.updateFsScale(); this.scheduleHide(); } else if(this._hideT){ clearTimeout(this._hideT); this._hideT=null; }
    try{ const el=this._phone||document.documentElement; let p;
      if(!n){p=(document.exitFullscreen||function(){}).call(document);} else {p=(el.requestFullscreen||function(){}).call(el);}
      if(p&&p.catch)p.catch(function(){}); }catch(e){} }
  updateFsScale(){ try{ const sc=Math.min(window.innerWidth/390, window.innerHeight/462); document.body.style.setProperty('--fs-scale', String(sc)); }catch(e){} }
  scheduleHide(){ if(this._hideT){clearTimeout(this._hideT);this._hideT=null;} if(this.state.fs&&!this.state.ctrlHidden){ this._hideT=setTimeout(()=>{ if(this.state.playing)this.setState({ctrlHidden:true}); },3500); } }
  tapToggle(){ if(!this.state.fs)return; const h=!this.state.ctrlHidden; this.setState({ctrlHidden:h}); if(!h)this.scheduleHide(); }
  updateFitZoom(){ try{ const z=Math.min(window.innerWidth/390, __LZ_FIT_CAP__); document.body.style.setProperty('--lz-fit', String(z)); }catch(e){} }"""

_OPENASK_OLD = "openAsk(){ this.setState({askOpen:true,playing:false}); }"
_ASK_SHEET_STYLE_OLD = (
    "background:#181b1e;border-top:2px solid #cf4436;border-radius:20px 20px 0 0;"
    "box-shadow:0 -8px 30px rgba(0,0,0,.5);height:88vh;display:flex;flex-direction:column;"
    "overflow:hidden;"
)
_ASK_SHEET_STYLE_NEW = _ASK_SHEET_STYLE_OLD + (
    "animation:lzAskSheetIn .24s cubic-bezier(.22,.8,.28,1) both;will-change:transform;"
)

_RVALS_APPEND = (
    # stopPropagation:角标在 lz-stagewrap(tapToggle 点屏显隐)内,不截断冒泡则
    # 点角标进全屏的同一击会立即把控制条切成隐藏(owner 真机复现)。
    'fullscreen:(e)=>{if(e&&e.stopPropagation)e.stopPropagation();this.fullscreen();},'
    'phoneRef:el=>this.phoneRef(el),'
    'fsIcon:this.state.fs?"⊠":"⛶",'
    "fs:this.state.fs,"
    "capO:(!this.state.fs||!this.state.ctrlHidden)?1:0,"
    "cornerO:(!this.state.fs||!this.state.ctrlHidden)?1:0,"
    'cornerPE:(!this.state.fs||!this.state.ctrlHidden)?"auto":"none",'
    "fsBarO:(this.state.fs&&!this.state.ctrlHidden)?1:0,"
    'fsBarPE:(this.state.fs&&!this.state.ctrlHidden)?"auto":"none",'
    "fsBarY:(this.state.fs&&!this.state.ctrlHidden)?0:18,"
    "tapToggle:()=>this.tapToggle(),"
)

_CORNER_STYLE_APPEND = "opacity:{{ cornerO }};pointer-events:{{ cornerPE }};transition:opacity .25s ease;"
_CAPSULE_STYLE_APPEND = "opacity:{{ capO }};transition:opacity .25s ease;"

_MUTE_BTN_FSBAR = (
    '        <button onClick="{{ toggleMute }}" style="flex:none;height:40px;padding:0 14px;'
    "border-radius:20px;border:1px solid rgba(255,255,255,.28);background:rgba(0,0,0,.35);"
    'color:#fff;font-size:12px;font-weight:800;cursor:pointer;white-space:nowrap;">'
    "{{ narrLabel }}</button>\n"
)


def _fs_bar_html(with_mute: bool) -> str:
    mute = _MUTE_BTN_FSBAR if with_mute else ""
    return f"""
    <!-- FULLSCREEN 浮层控制条（点屏显隐 · 播放时自动隐藏 · 发布层回灌） -->
    <sc-if value="{{{{ fs }}}}" hint-placeholder-val="{{{{ false }}}}">
    <div style="position:absolute;left:0;right:0;bottom:0;z-index:10001;padding:16px 20px calc(16px + env(safe-area-inset-bottom));background:linear-gradient(180deg,rgba(0,0,0,0),rgba(0,0,0,.68));opacity:{{{{ fsBarO }}}};pointer-events:{{{{ fsBarPE }}}};transform:translateY({{{{ fsBarY }}}}px);transition:opacity .25s ease,transform .25s ease;">
      <div style="display:flex;align-items:center;gap:13px;max-width:820px;margin:0 auto;">
        <button onClick="{{{{ toggle }}}}" style="flex:none;width:46px;height:46px;border-radius:50%;border:none;background:#cf4436;color:#fff;font-size:17px;cursor:pointer;">{{{{ playIcon }}}}</button>
        <div style="flex:1;min-width:0;">
          <input type="range" min="0" max="{{{{ DUR }}}}" step="0.1" value="{{{{ t }}}}" onChange="{{{{ seek }}}}" onInput="{{{{ seek }}}}" style="width:100%;accent-color:#cf4436;cursor:pointer;height:6px;"/>
          <div style="display:flex;justify-content:space-between;font-size:11px;color:#e7e4da;margin-top:4px;font-variant-numeric:tabular-nums;"><span>{{{{ tLabel }}}}</span><span>{{{{ curTitle }}}}</span><span>{{{{ totalLabel }}}}</span></div>
        </div>
{mute}        <button onClick="{{{{ fullscreen }}}}" title="退出全屏" style="flex:none;width:46px;height:46px;border-radius:50%;border:1px solid rgba(255,255,255,.28);background:rgba(0,0,0,.35);color:#fff;font-size:19px;cursor:pointer;">⊠</button>
      </div>
    </div>
    </sc-if>

    <!-- ASK-AI OVERLAY -->"""


class TransformError(RuntimeError):
    pass


def _sub(text: str, pattern: str | re.Pattern[str], repl: str, name: str,
         expected: int = 1, literal_pattern: bool = True, group_repl: bool = False) -> str:
    """锚定替换：命中数 != expected 即 fail-closed。

    group_repl=True 时 repl 按 re 反向引用语义解释（\\1 等）；否则按字面文本插入。
    """
    if literal_pattern:
        pattern = re.compile(re.escape(pattern))  # type: ignore[arg-type]
    elif isinstance(pattern, str):
        pattern = re.compile(pattern, re.M)
    replacement = repl if group_repl else (lambda _m: repl)
    new, n = pattern.subn(replacement, text)
    if n != expected:
        raise TransformError(f"anchor [{name}] matched {n} times (expected {expected})")
    return new


_FS_CSS_LINE_RE = re.compile(r"^(\s*)s\.textContent='body\.luban-fs[^\n]*$", re.M)
_FULLSCREEN_OLD_RE = re.compile(
    r"^  fullscreen\(\)\{ const n=!this\.state\.fs; this\.setState\(\{fs:n\}\);"
    r".*?\n(?:.*\n)*?.*?\}catch\(e\)\{\} \}$", re.M)
_UNMOUNT_OLD_RE = re.compile(r"^  componentWillUnmount\(\)\{[^\n]*$", re.M)
_STATE_RE = re.compile(r"fs:false ?, ?muted:false \};")
_RVALS_OLD = 'fullscreen:()=>this.fullscreen(),phoneRef:el=>this.phoneRef(el),fsIcon:this.state.fs?"⊠":"⛶",'
_TOGGLE_END_OLD = "else { this.setSpeechPaused(true); } } }"
_TOGGLE_END_NEW = "else { this.setSpeechPaused(true); } }\n    if(this.state.fs)this.scheduleHide(); }"
_CORNER_FS_RE = re.compile(
    r'(<button onClick="\{\{ fullscreen \}\}" title="全屏" style="position:absolute;top:8px;right:10px;[^"]*)(">)')
_CORNER_MUTE_RE = re.compile(
    r'(<button onClick="\{\{ toggleMute \}\}" title="旁白朗读开关" style="position:absolute;top:8px;left:10px;[^"]*)(">)')
_CAPSULE_RE = re.compile(
    r'(<div style="position:absolute;top:10px;left:50%;transform:translateX\(-50%\);z-index:40;[^"]*)(">)')
_AUTOSTART_RE = re.compile(r"^\s*this\._autoTimer=setTimeout\([^\n]*\n", re.M)
_SUBMIT_ASK_RE = re.compile(
    r"^  async submitAsk\(\)\{.*?^  \}\n(?:\s*\n)*(?=  [A-Za-z_]\w*\()", re.M | re.S
)
_AUTHORING_CLAUDE_RE = re.compile(r"window\.claude(?:\.complete)?")
_ASK_RESPONSE_RE = re.compile(
    r'          <sc-if value="\{\{ hasAnswer \}\}" hint-placeholder-val="\{\{ false \}\}">.*?'
    r"          </sc-if>",
    re.S,
)
_ASK_RESPONSE_THREAD = '''          <sc-if value="{{ hasAnswer }}" hint-placeholder-val="{{ false }}">
          <div data-luban-ask-thread style="display:flex;flex-direction:column;gap:10px;">
            <div style="align-self:flex-end;max-width:82%;display:flex;gap:8px;align-items:flex-start;flex-direction:row-reverse;">
              <div style="flex:none;width:26px;height:26px;border-radius:50%;background:#e8e4d8;color:#3a3329;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:900;">我</div>
              <div style="background:#f2eee3;color:#292820;border-radius:13px 13px 4px 13px;padding:9px 11px;font-size:12.5px;line-height:1.55;font-weight:650;">{{ askText }}</div>
            </div>
            <div style="background:#2b2620;border:1px solid #4a3d2a;border-radius:13px;padding:13px 14px;display:flex;gap:10px;align-items:flex-start;">
              <div style="flex:none;width:28px;height:28px;border-radius:50%;background:#cf4436;color:#fff;display:flex;align-items:center;justify-content:center;font-family:'Long Cang',cursive;font-size:18px;">师</div>
              <div style="flex:1;min-width:0;">
                <div data-luban-workflow-status style="border:1px solid #527463;border-radius:12px;padding:10px 11px;background:#242820;margin-bottom:10px;">
                  <div style="display:inline-flex;border:1px solid #527463;border-radius:999px;padding:3px 8px;color:#93c4a8;font-size:10px;font-weight:900;margin-bottom:6px;">{{ askWorkflowBadge }}</div>
                  <div style="font-size:13px;color:#f1e6cf;font-weight:850;line-height:1.45;">{{ askWorkflowTitle }}</div>
                  <div style="margin-top:3px;font-size:11px;color:#b9b59f;line-height:1.55;">{{ askWorkflowSub }}</div>
                  <button data-luban-workflow-toggle onClick="{{ toggleAskWorkflow }}" style="margin-top:8px;border:0;background:transparent;padding:0;color:#93c4a8;font-size:10.5px;font-weight:800;cursor:pointer;">{{ askWorkflowToggleText }}</button>
                  <sc-if value="{{ askWorkflowExpanded }}" hint-placeholder-val="{{ false }}">
                    <sc-for list="{{ askWorkflowEntries }}" as="step" hint-placeholder-count="5">
                      <div style="margin-top:7px;padding-top:7px;border-top:1px solid #3a4438;font-size:10.5px;color:#c9c5ae;line-height:1.45;">{{ step.badge }} · {{ step.title }}</div>
                    </sc-for>
                  </sc-if>
                </div>
                <sc-for list="{{ askBlocks }}" as="b" hint-placeholder-count="5">
                  <sc-if value="{{ b.type === 'heading' }}" hint-placeholder-val="{{ false }}"><div style="margin:11px 0 6px;color:#fff4dc;font-size:16px;line-height:1.45;font-weight:900;"><sc-for list="{{ b.parts }}" as="p"><span style="{{ p.style }}">{{ p.text }}</span></sc-for></div></sc-if>
                  <sc-if value="{{ b.type === 'paragraph' }}" hint-placeholder-val="{{ false }}"><div style="margin:8px 0;color:#f1e6cf;font-size:13.5px;line-height:1.75;font-weight:500;"><sc-for list="{{ b.parts }}" as="p"><span style="{{ p.style }}">{{ p.text }}</span></sc-for></div></sc-if>
                  <sc-if value="{{ b.type === 'callout' }}" hint-placeholder-val="{{ false }}"><div style="margin:9px 0;padding:10px;border-left:3px solid #7fb69a;background:#202920;border-radius:8px;"><div style="display:inline-flex;color:#a8d1b4;font-size:10px;font-weight:900;margin-bottom:4px;">{{ b.label }}</div><div style="color:#eef3e9;font-size:13px;line-height:1.7;"><sc-for list="{{ b.parts }}" as="p"><span style="{{ p.style }}">{{ p.text }}</span></sc-for></div></div></sc-if>
                  <sc-if value="{{ b.type === 'ul' || b.type === 'ol' }}" hint-placeholder-val="{{ false }}"><sc-for list="{{ b.items }}" as="item"><div style="display:flex;gap:7px;margin:7px 0;color:#f1e6cf;font-size:13px;line-height:1.7;"><span style="flex:none;color:#cf8a44;font-weight:900;">{{ item.marker }}</span><div style="flex:1;"><sc-for list="{{ item.parts }}" as="p"><span style="{{ p.style }}">{{ p.text }}</span></sc-for></div></div></sc-for></sc-if>
                  <sc-if value="{{ b.type === 'blockquote' }}" hint-placeholder-val="{{ false }}"><div style="margin:9px 0;padding:8px 10px;border-left:3px solid #cf8a44;background:#251f19;color:#e9dec7;font-size:12.5px;line-height:1.7;"><sc-for list="{{ b.lines }}" as="line"><div><sc-for list="{{ line }}" as="p"><span style="{{ p.style }}">{{ p.text }}</span></sc-for></div></sc-for></div></sc-if>
                  <sc-if value="{{ b.type === 'code_block' }}" hint-placeholder-val="{{ false }}"><div style="margin:9px 0;padding:9px 10px;border-radius:8px;background:#101415;color:#dfe7df;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;line-height:1.55;white-space:pre-wrap;">{{ b.code }}</div></sc-if>
                  <sc-if value="{{ b.type === 'table' }}" hint-placeholder-val="{{ false }}"><div style="margin:9px 0;border:1px solid #4a3d2a;border-radius:8px;overflow:hidden;"><div style="padding:7px 9px;background:#30291f;color:#f3cd91;font-size:11px;font-weight:900;">{{ b.headers }}</div><sc-for list="{{ b.rows }}" as="row"><div style="padding:7px 9px;border-top:1px solid #3a3127;color:#efe4ce;font-size:11.5px;line-height:1.55;">{{ row.cells }}</div></sc-for></div></sc-if>
                </sc-for>
              </div>
            </div>
          </div>
          </sc-if>'''
_ASK_ERROR_THREAD = '''          <sc-if value="{{ askError }}" hint-placeholder-val="{{ false }}">
          <div data-luban-ask-error style="margin-top:12px;border:1px solid #80503c;background:#2b211d;color:#f0c9a8;border-radius:12px;padding:11px 12px;font-size:12.5px;line-height:1.6;">{{ askError }}</div>
          </sc-if>'''
_ASK_STATE_OLD = 'askAnswer:"", fs:false'
_ASK_STATE_NEW = ('askAnswer:"", askRawResponse:"", askBlocks:[], askWorkflowEntries:[], '
                  'askWorkflowBadge:"", askWorkflowTitle:"", askWorkflowSub:"", askWorkflowExpanded:false, askWorkflowToggleText:"查看处理摘要", '
                  'askWorkflowActive:false, askStreaming:false, askError:"", fs:false')
_ASK_RENDER_VALS_OLD = '''askOpen:this.state.askOpen,askText:this.state.askText,askLoading:this.state.askLoading,askAnswer:this.state.askAnswer,
      hasAnswer:!!this.state.askAnswer,askIdle:!this.state.askLoading&&!this.state.askAnswer,'''
_ASK_RENDER_VALS_NEW = '''askOpen:this.state.askOpen,askText:this.state.askText,askLoading:this.state.askLoading,askBlocks:this.state.askBlocks,askWorkflowEntries:this.state.askWorkflowEntries,askWorkflowBadge:this.state.askWorkflowBadge,askWorkflowTitle:this.state.askWorkflowTitle,askWorkflowSub:this.state.askWorkflowSub,askWorkflowExpanded:this.state.askWorkflowExpanded,askWorkflowToggleText:this.state.askWorkflowToggleText,askError:this.state.askError,
      hasAnswer:!!this.state.askStreaming||!!this.state.askBlocks.length||!!this.state.askWorkflowActive,askIdle:!this.state.askLoading&&!this.state.askStreaming&&!this.state.askError,'''
_ASK_RENDER_VALS_S07_OLD = '''askOpen:this.state.askOpen, askText:this.state.askText, askLoading:this.state.askLoading,
      askAnswer:this.state.askAnswer, hasAnswer:!!this.state.askAnswer,
      askIdle:!this.state.askLoading && !this.state.askAnswer,'''
_ASK_RENDER_VALS_S07_NEW = '''askOpen:this.state.askOpen, askText:this.state.askText, askLoading:this.state.askLoading,
      askBlocks:this.state.askBlocks, askWorkflowEntries:this.state.askWorkflowEntries, askWorkflowBadge:this.state.askWorkflowBadge, askWorkflowTitle:this.state.askWorkflowTitle, askWorkflowSub:this.state.askWorkflowSub, askWorkflowExpanded:this.state.askWorkflowExpanded, askWorkflowToggleText:this.state.askWorkflowToggleText, askError:this.state.askError, hasAnswer:!!this.state.askStreaming || !!this.state.askBlocks.length || !!this.state.askWorkflowActive,
      askIdle:!this.state.askLoading && !this.state.askStreaming && !this.state.askError,'''


def _inline_tutorbot_ask_method(pack_id: str) -> str:
    """Render a thin browser transport over the existing TutorBot turn stream."""
    return '''  async submitAsk(){
    const q=(this.state.askText||"").trim(); if(!q||this.state.askLoading)return;
    const runtime=window.LubanTutorbotSheetRuntime;
    const entryTicket=String(window.__lubanCardEntryTicket||"").trim();
    if(!runtime||!runtime.workflow||!entryTicket){ this.setState({askError:"学习身份已过期，请返回小程序重新打开这一站。"}); return; }
    let bi=0; for(let i=0;i<this.beats.length;i++){ if(this.state.t>=this.beats[i][1]) bi=i; }
    const beat=this.beats[bi]||[];
    const isFollowup=bi>=this.narr.length;
    const followup=isFollowup?(this.qa[bi-this.narr.length]||{}):{};
    const captionText=isFollowup?(String(followup.q||"")+"。"+String(followup.a||"")):String(this.narr[bi]||"");
    const keycard=isFollowup?("学生追问 · 第 "+(bi-this.narr.length+1)+" / "+this.qa.length+" 问"):String(this.keycards[bi]||"");
    const payload={contextId:"__PACK_ID__",cardId:"__PACK_ID__",question:q,entryTicket:entryTicket,
      currentScene:{id:String(beat[0]||bi+1),label:String(beat[3]||"当前画面").slice(0,80),keycard:keycard.slice(0,160),coach:captionText.slice(0,320)},
      currentCaption:{speaker:isFollowup?"学员追问":"鲁班讲解",text:captionText.slice(0,260)},
      time:Number(this.state.t||0)};
    let rawResponse="", workflowEntries=[], lastSeq=0, completed=false, reconnects=0, socket=null;
    const self=this;
    const renderWorkflow=function(active, extra){
      const summary=runtime.workflow.summarizeWorkflow(workflowEntries,active!==false);
      const expanded=!!self.state.askWorkflowExpanded;
      self.setState(Object.assign({askWorkflowEntries:workflowEntries,askWorkflowBadge:summary.badge||"",askWorkflowTitle:summary.headline||"",askWorkflowSub:summary.subline||"",askWorkflowActive:active!==false,askWorkflowToggleText:expanded?"收起处理摘要":(summary.toggleText||"查看处理摘要")},extra||{}));
    };
    const setResponse=function(next, append){
      rawResponse=append?rawResponse+String(next||""):String(next||"");
      self.setState({askLoading:false,askStreaming:true,askRawResponse:rawResponse,askAnswer:rawResponse,askBlocks:runtime.projectMarkdown(rawResponse),askError:""});
    };
    const fail=function(message){
      if(completed)return; completed=true;
      renderWorkflow(false,{askLoading:false,askStreaming:true,askError:String(message||"TutorBot 暂时没有接通，请留在本页稍后重试。")});
    };
    const finish=function(){ if(completed)return; completed=true; renderWorkflow(false,{askLoading:false,askStreaming:true}); };
    const consume=function(event){
      if(!event||typeof event!=="object"||completed)return;
      const seq=typeof event.seq==="number"?event.seq:0;
      if(seq&&seq<=lastSeq)return; if(seq)lastSeq=seq;
      const type=String(event.type||"");
      if(type==="content"){ if(runtime.isPublicEvent(event))setResponse(event.content,true); return; }
      const workflowEvent=runtime.toWorkflowEvent(event);
      if(workflowEvent){ workflowEntries=runtime.workflow.appendWorkflowEntry(workflowEntries,workflowEvent); renderWorkflow(true,{askStreaming:true}); return; }
      if(type==="result"){ if(runtime.isPublicEvent(event)){ const finalText=runtime.finalResponse(event); if(finalText)setResponse(finalText,false); } return; }
      if(type==="error"){ const metadata=event.metadata||{}; if(metadata.turn_terminal)fail(event.content||"TutorBot 暂时不可用，请稍后重试。"); return; }
      if(type==="done")finish();
    };
    const socketUrl=function(path){
      const u=new URL(String(path||"/api/v1/ws"),window.location.href);
      u.protocol=u.protocol==="https:"?"wss:":"ws:"; return u.toString();
    };
    const connect=function(stream){
      if(completed)return;
      try{
        socket=new WebSocket(socketUrl(stream.url),[String(stream.protocol||"luban-preview-v1"),String(stream.ticket||"")]);
        socket.onopen=function(){ if(completed)return; socket.send(JSON.stringify({type:"subscribe_turn",turn_id:String(stream.turn_id||""),after_seq:lastSeq||0})); };
        socket.onmessage=function(message){ try{consume(JSON.parse(String(message.data||"")));}catch(_){ } };
        socket.onclose=function(){
          if(completed)return;
          if(reconnects>=5){ fail("流式连接中断，请留在本页稍后重试。"); return; }
          reconnects+=1; workflowEntries=runtime.workflow.appendWorkflowEntry(workflowEntries,{type:"status",eventType:"reconnect",data:"retry",content:"正在续接本轮回答…",seq:lastSeq||0}); renderWorkflow(true,{askStreaming:true});
          setTimeout(function(){connect(stream);},400*reconnects);
        };
        socket.onerror=function(){};
      }catch(err){ fail("流式连接暂时不可用，请留在本页稍后重试。"); }
    };
    this.setState({askLoading:true,askAnswer:"",askRawResponse:"",askBlocks:[],askWorkflowEntries:[],askWorkflowBadge:"",askWorkflowTitle:"",askWorkflowSub:"",askWorkflowExpanded:false,askWorkflowToggleText:"查看处理摘要",askWorkflowActive:true,askStreaming:true,askError:""});
    renderWorkflow(true,{askWorkflowExpanded:false,askWorkflowToggleText:"查看处理摘要"});
    try{
      const res=await fetch("/api/v1/luban-preview/ai-ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      const data=await res.json().catch(()=>({}));
      if(!res.ok)throw new Error(String(data.detail||"TutorBot 答疑暂时不可用"));
      const stream=data&&data.stream;
      if(!stream||!stream.ticket||!stream.turn_id)throw new Error("TutorBot 流式回合未创建");
      connect(stream);
    }catch(err){ fail((err&&err.message)||"TutorBot 暂时没有接通，请留在本页稍后重试。"); }
  }
  toggleAskWorkflow(){
    const expanded=!this.state.askWorkflowExpanded;
    this.setState({askWorkflowExpanded:expanded,askWorkflowToggleText:expanded?"收起处理摘要":"查看处理摘要"});
  }
'''.replace("__PACK_ID__", pack_id)


def _card_entry_bridge(pack_id: str) -> str:
    """Keep the H5 capability out of the request URL and bridge card links."""
    return '''<script data-luban-card-entry-bridge>
(function(){
  var ticket="";
  try{
    var current=new URL(window.location.href);
    var capability=new URLSearchParams(String(current.hash||"").replace(/^#/,""));
    ticket=String(capability.get("entry_ticket")||"").trim();
    if(ticket){ window.__lubanCardEntryTicket=ticket; window.history.replaceState(window.history.state,document.title,current.pathname+(current.search||"")); }
  }catch(_){ }
  function closestAnchor(node){ while(node&&node!==document){ if(String(node.tagName||"").toUpperCase()==="A")return node; node=node.parentNode; } return null; }
  function carryCapability(url){ if(!ticket)return url; url.hash="entry_ticket="+encodeURIComponent(ticket); return url; }
  document.addEventListener("click",function(event){
    var anchor=closestAnchor(event.target); if(!anchor||event.defaultPrevented)return;
    var href=String(anchor.getAttribute("href")||"").trim(); if(!href||href.charAt(0)==="#")return;
    var next; try{ next=new URL(anchor.href,window.location.href); }catch(_){return;}
    if(next.origin!==window.location.origin)return;
    var file=next.pathname.split("/").pop()||"";
    if(/^lesson(?:\\d+)?\\.html$/i.test(file)){ if(ticket){ event.preventDefault(); window.location.assign(carryCapability(next).toString()); } return; }
    if(!/^practice(?:\\d+)?\\.html$/i.test(file))return;
    event.preventDefault();
    if(!ticket){ window.alert("学习身份已过期，请返回小程序重新打开这一站。"); return; }
    fetch("/api/v1/luban-preview/lesson-viewed",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({contextId:"__PACK_ID__",cardId:"__PACK_ID__",entryTicket:ticket})})
      .then(function(response){ if(!response.ok)throw new Error("lesson evidence rejected"); window.location.assign(carryCapability(next).toString()); })
      .catch(function(){ window.alert("学习记录未确认，请留在本页稍后重试后再做练习。"); });
  },true);
})();
</script>'''.replace("__PACK_ID__", pack_id)


def transform_teach(text: str, pack_id: str, *, sheet_runtime_tag: str | None = None) -> str:
    # 1. 字体自托管 + 微信 JSSDK（练习完成收据仍使用）+ 卡内问答上推动画。
    preload_element = _audio_preload_element(text)
    text = _sub(
        text,
        _FONT_LINKS_OLD,
        _FONT_LINKS_NEW + "\n" + _JWEIXIN_TAG + "\n" + (sheet_runtime_tag or _tutorbot_sheet_runtime_tag())
        + "\n" + _card_entry_bridge(pack_id) + "\n" + _ASK_SHEET_MOTION_CSS,
        "font-links",
    )
    text = _sub(text, "<body>", "<body>\n" + preload_element, "audio-preload")
    # 所有当前教学卡都使用这一份抽屉骨架。锚点漂移即 fail-closed，避免把未知
    # 容器误判成可覆盖的教学舞台。
    text = _sub(text, _ASK_SHEET_STYLE_OLD, _ASK_SHEET_STYLE_NEW, "ask-sheet-motion")
    # 发布产物不能依赖作者环境才存在的 window.claude 预览钩子。这个替换只负责
    # 浏览器 transport；回答、知识口径和会话仍由服务端 TutorBot runtime 唯一决定。
    text = _sub(
        text,
        _SUBMIT_ASK_RE,
        _inline_tutorbot_ask_method(pack_id),
        "inline-tutorbot-ask",
        literal_pattern=False,
    )
    # 复用对话页的最小阅读顺序：学生问题气泡 → TutorBot 结论/依据卡。回答正文
    # 原样来自服务端，发布层不切段、不重写、不伪造结构化判断。
    text = _sub(
        text,
        _ASK_RESPONSE_RE,
        _ASK_RESPONSE_THREAD + "\n" + _ASK_ERROR_THREAD,
        "ask-response-thread",
        literal_pattern=False,
    )
    text = _sub(text, _ASK_STATE_OLD, _ASK_STATE_NEW, "ask-error-state")
    if _ASK_RENDER_VALS_OLD in text:
        text = _sub(text, _ASK_RENDER_VALS_OLD, _ASK_RENDER_VALS_NEW, "ask-error-render")
    elif _ASK_RENDER_VALS_S07_OLD in text:
        text = _sub(
            text,
            _ASK_RENDER_VALS_S07_OLD,
            _ASK_RENDER_VALS_S07_NEW,
            "ask-error-render-s07",
        )
    else:
        raise TransformError("anchor [ask-error-render] not found")
    # 同时清掉作者注释中对预览桥的提及，避免未来有人误以为它是发布时依赖。
    text = _AUTHORING_CLAUDE_RE.sub("authoring preview bridge", text)
    # 新一批 finished 已内置全屏/控制条结构（ctrlHidden），不能再把旧母版的
    # 锚定回灌重复套进去。卡内 askOpen 是唯一展示 authority，不把它分叉为
    # 小程序 native 聊天页。
    if "ctrlHidden:false" in text:
        return text
    # S07 安全事故成品使用另一套已自带双向全屏的母版（multiline `next` 版本）。
    # 不把旧单行母版的整套控制条再次套入；问答仍在同一张教学卡里。
    if "const next=!this.state.fs;" in text and "document.body.classList.toggle('luban-fs', next);" in text:
        return text
    # 1b. 普通态宽度自适应 + html/body 底色改为卡自身深墨（逐卡提取，fail-closed）
    bg_m = _CARD_BG_RE.search(text)
    if not bg_m:
        raise TransformError("anchor [card-bg] not found on .lz-card")
    card_bg = bg_m.group(1)
    text = _sub(text, _BODY_CSS_OLD, _fit_css(card_bg), "fit-css")
    text = _sub(text, _BODY_BG_RE, f"body{{background:{card_bg};font-family",
                "body-bg", literal_pattern=False)
    # 2. 全屏 CSS（保留原缩进）
    m = _FS_CSS_LINE_RE.search(text)
    if not m:
        raise TransformError("anchor [fs-css-line] not found")
    text = _FS_CSS_LINE_RE.sub(lambda mm: f"{mm.group(1)}s.textContent='{_FS_CSS_NEW}';", text, count=1)
    # 3. componentDidMount 收尾：resize 监听 + 进入即全屏
    text = _sub(
        text,
        r"document\.head\.appendChild\(s\);\s*\}",
        _DIDMOUNT_APPEND,
        "didmount-append",
        literal_pattern=False,
    )
    # 4. state 加 ctrlHidden
    text = _sub(text, _STATE_RE, "fs:false, ctrlHidden:false, muted:false };",
                "state-ctrlHidden", literal_pattern=False)
    # 5. componentWillUnmount 清理
    text = _sub(text, _UNMOUNT_OLD_RE, _UNMOUNT_NEW, "unmount", literal_pattern=False)
    # 6. fullscreen() 替换 + 新方法（updateFsScale/scheduleHide/tapToggle/updateFitZoom）
    fs_methods = (_FULLSCREEN_NEW
                  .replace("__LZ_FIT_CAP__", str(_FIT_ZOOM_CAP)))
    text = _sub(text, _FULLSCREEN_OLD_RE, fs_methods, "fullscreen-method", literal_pattern=False)
    # 7. toggle() 播放后调度自动隐藏
    text = _sub(text, _TOGGLE_END_OLD, _TOGGLE_END_NEW, "toggle-schedulehide")
    # 8. renderVals 补键
    text = _sub(text, _RVALS_OLD, _RVALS_APPEND, "rvals-append")
    # 9. 模板：header/controls 挂 lz-chrome
    text = _sub(text, "<!-- HEADER -->\n    <div style=",
                '<!-- HEADER -->\n    <div class="lz-chrome" style=', "header-chrome")
    text = _sub(text, "<!-- CONTROLS -->\n    <div style=",
                '<!-- CONTROLS -->\n    <div class="lz-chrome" style=', "controls-chrome")
    # 10. 舞台包 lz-stagewrap + lz-stage
    text = _sub(text, '\n    <div style="position:relative;width:100%;height:462px;',
                '\n    <div class="lz-stagewrap" onClick="{{ tapToggle }}">'
                '\n    <div class="lz-stage" style="position:relative;width:100%;height:462px;',
                "stage-wrap-open")
    text = _sub(text, "\n    </div>\n\n    <!-- CONTROLS -->",
                "\n    </div>\n    </div>\n\n    <!-- CONTROLS -->", "stage-wrap-close")
    # 11. 舞台角按钮全屏时可隐藏
    text = _sub(text, _CORNER_FS_RE, r"\1" + _CORNER_STYLE_APPEND + r"\2",
                "corner-fsbtn", literal_pattern=False, group_repl=True)
    if _CORNER_MUTE_RE.search(text):  # G01 无旁白按钮
        text = _sub(text, _CORNER_MUTE_RE, r"\1" + _CORNER_STYLE_APPEND + r"\2",
                    "corner-mutebtn", literal_pattern=False, group_repl=True)
    if _CAPSULE_RE.search(text):  # 钥匙卡胶囊仅部分卡有
        text = _sub(text, _CAPSULE_RE, r"\1" + _CAPSULE_STYLE_APPEND + r"\2", "capsule-opacity",
                    literal_pattern=False, group_repl=True)
    # 12. 全屏浮层控制条（插在 ASK-AI 弹层前，.lz-card 直接子元素）
    with_mute = "narrLabel:" in text
    text = _sub(text, "\n    <!-- ASK-AI OVERLAY -->", _fs_bar_html(with_mute), "fsbar-insert")
    # 13. 剥离无手势自动开播（N01 有 520ms auto-start）：移动端 audio.play() 无用户
    #     手势必被拒（CDP 实测 NotAllowedError）→ 首拍旁白必哑。统一回海报点击开播。
    text = _AUTOSTART_RE.sub("", text)
    return text


def _inline_practice_tutorbot_ask_method(pack_id: str) -> str:
    """练习页只负责 TutorBot transport；题目理解与回答仍由服务端唯一决定。"""
    return '''  async submitAsk(){
    const userQ=(this.state.askText||"").trim(); if(!userQ||this.state.askLoading)return;
    const runtime=window.LubanTutorbotSheetRuntime;
    const entryTicket=String(window.__lubanCardEntryTicket||"").trim();
    if(!runtime||!entryTicket){ this.setState({askLoading:false,askAnswer:"学习身份已过期，请返回小程序重新打开这一站。"}); return; }
    const state=this.state||{};
    const questionIndex=Number(state.qi!=null?state.qi:(state.idx!=null?state.idx:0));
    let c=null;
    if(typeof this.curCtx==="function"){ try{ c=this.curCtx(); }catch(_){ c=null; } }
    if(!c){
      let q=null;
      if(Array.isArray(state.drawn))q=state.drawn[questionIndex];
      if(!q&&typeof this.qAt==="function"){ try{ q=this.qAt(questionIndex); }catch(_){ q=null; } }
      if(!q&&Array.isArray(this.Q))q=this.Q[questionIndex];
      q=q||{};
      const opts=Array.isArray(q.opts)?q.opts.map(function(opt,index){
        const value=opt&&typeof opt==="object"?(opt.t||opt.text||opt.label||""):opt;
        return String.fromCharCode(65+index)+". "+String(value||"");
      }).join("\\n"):"";
      let mine="（还没作答）";
      if(typeof state.sel==="number"){
        if(state.sel>=0)mine=String.fromCharCode(65+state.sel);
      }else if(state.sel!=null&&typeof state.sel!=="object"&&String(state.sel).trim())mine=String(state.sel);
      else if(state.sel&&state.sel[questionIndex]!=null)mine=String(state.sel[questionIndex]);
      c={q:q,opts:opts,mine:mine,sub:!!(state.revealed||(state.sub&&state.sub[questionIndex]))};
    }
    const currentQuestion=c.q||{};
    const correctOption=Array.isArray(currentQuestion.opts)&&typeof currentQuestion.c==="number"
      ?currentQuestion.opts[currentQuestion.c]:"";
    const correctText=correctOption&&typeof correctOption==="object"
      ?(correctOption.t||correctOption.text||correctOption.label||""):correctOption;
    let contextLine="";
    if(typeof this.ctxLine==="function"){ try{ contextLine=String(this.ctxLine()||""); }catch(_){ contextLine=""; } }
    if(!contextLine)contextLine="题干："+String(currentQuestion.stem||currentQuestion.q||"").slice(0,180)+" ｜ 我的选择："+String(c.mine||"（还没作答）")+(c.sub?" ｜ 已对答案":" ｜ 未对答案");
    const payload={contextId:"__PACK_ID__",cardId:"__PACK_ID__",question:userQ,entryTicket:entryTicket,
      currentScene:{id:"practice-"+(questionIndex+1),label:String(currentQuestion.tag||currentQuestion.topic||currentQuestion.ep||"当前练习").slice(0,80),keycard:String(currentQuestion.model||currentQuestion.ans||currentQuestion.correct||correctText||"").slice(0,160),coach:String(c.opts||"").slice(0,320)},
      currentCaption:{speaker:"学员作答",text:contextLine.slice(0,260)},time:0};
    let rawResponse="",lastSeq=0,completed=false,reconnects=0;
    const self=this;
    const fail=function(message){ if(completed)return; completed=true; self.setState({askLoading:false,askAnswer:String(message||"TutorBot 暂时不可用，请稍后重试。")}); };
    const render=function(next,append){ rawResponse=append?rawResponse+String(next||""):String(next||""); self.setState({askLoading:true,askAnswer:rawResponse||"鲁班正在整理答案…"}); };
    const consume=function(event){
      if(!event||typeof event!=="object"||completed)return;
      const seq=typeof event.seq==="number"?event.seq:0; if(seq&&seq<=lastSeq)return; if(seq)lastSeq=seq;
      const type=String(event.type||"");
      if(type==="content"){ if(runtime.isPublicEvent(event))render(event.content,true); return; }
      if(type==="result"){ if(runtime.isPublicEvent(event)){ const finalText=runtime.finalResponse(event); if(finalText)render(finalText,false); } return; }
      if(type==="error"&&event.metadata&&event.metadata.turn_terminal){ fail(event.content); return; }
      if(type==="done"){ completed=true; self.setState({askLoading:false}); }
    };
    const socketUrl=function(path){ const u=new URL(String(path||"/api/v1/ws"),window.location.href); u.protocol=u.protocol==="https:"?"wss:":"ws:"; return u.toString(); };
    const connect=function(stream){
      if(completed)return;
      let socket;
      try{
        socket=new WebSocket(socketUrl(stream.url),[String(stream.protocol||"luban-preview-v1"),String(stream.ticket||"")]);
        socket.onopen=function(){ socket.send(JSON.stringify({type:"subscribe_turn",turn_id:String(stream.turn_id||""),after_seq:lastSeq||0})); };
        socket.onmessage=function(message){ try{consume(JSON.parse(String(message.data||"")));}catch(_){ } };
        socket.onclose=function(){ if(completed)return; if(reconnects>=5){fail("流式连接中断，请稍后重试。");return;} reconnects+=1; setTimeout(function(){connect(stream);},400*reconnects); };
        socket.onerror=function(){};
      }catch(_){ fail("流式连接暂时不可用，请稍后重试。"); }
    };
    this.setState({askLoading:true,askAnswer:""});
    try{
      const res=await fetch("/api/v1/luban-preview/ai-ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      const data=await res.json().catch(()=>({}));
      if(!res.ok)throw new Error(String(data.detail||"TutorBot 答疑暂时不可用"));
      const stream=data&&data.stream;
      if(!stream||!stream.ticket||!stream.turn_id)throw new Error("TutorBot 流式回合未创建");
      connect(stream);
    }catch(err){ fail((err&&err.message)||"TutorBot 暂时不可用，请稍后重试。"); }
  }
'''.replace("__PACK_ID__", pack_id)


def transform_practice(
    text: str,
    *,
    pack_id: str,
    compiled_surface: dict[str, object],
    items: list[dict[str, object]],
) -> str:
    """Thin publisher wrapper：共享 runtime/鉴权桥接后交给内容内核。"""
    text = _sub(
        text,
        _FONT_LINKS_OLD,
        _FONT_LINKS_NEW + "\n" + _JWEIXIN_TAG + "\n" + _tutorbot_sheet_runtime_tag()
        + "\n" + _card_entry_bridge(pack_id),
        "font-links",
    )
    text = _sub(
        text,
        _SUBMIT_ASK_RE,
        _inline_practice_tutorbot_ask_method(pack_id),
        "practice-tutorbot-ask",
        literal_pattern=False,
    )
    text = _AUTHORING_CLAUDE_RE.sub("authoring preview bridge", text)
    return transform_compiled_practice_html(
        pack_id,
        surface=compiled_surface,
        items=items,
        html=text,
    )


def _rewrite_hrefs(text: str, href_map: dict[str, str]) -> str:
    for old, new in href_map.items():
        # finished 卡既有普通 HTML <a href="…">，也有 x-dc 脚本对象
        # ``{href:"…"}``。只改 href 值，绝不做宽泛文件名替换以免污染讲解文本。
        text = re.sub(
            rf'(?P<prefix>href\s*[:=]\s*)(?P<quote>["\']){re.escape(old)}(?P=quote)',
            lambda match: f"{match.group('prefix')}{match.group('quote')}{new}{match.group('quote')}",
            text,
        )
    return text


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render_pack_manifest() -> str:
    """返回由最终托管卡和 sidecar 决定的唯一 manifest 投影。"""
    return json.dumps(build_manifest(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def _refresh_pack_manifest() -> None:
    """发布完成后再同步 manifest，避免登记到尚未写完的 sidecar。"""
    PACK_MANIFEST_PATH.write_text(_render_pack_manifest(), encoding="utf-8")


def _assert_manifest_registers_authority(pack_id: str, authority_path: Path) -> None:
    """运行时只信 manifest 登记的 sidecar；发布校验也必须复现这一约束。"""
    try:
        manifest = json.loads(PACK_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TransformError(f"pack manifest unreadable: {exc}") from exc
    row = next(
        (
            item
            for item in manifest.get("packs") or []
            if str(item.get("pack_id") or "").strip().upper() == pack_id.upper()
        ),
        None,
    )
    practice = row.get("practice") if isinstance(row, dict) else None
    expected = practice.get("authority_sha256") if isinstance(practice, dict) else None
    if expected != _sha256(authority_path):
        raise TransformError(f"practice manifest authority drift: {pack_id}")


def _practice_source_bundle_sha(src: Path, st: Station) -> str:
    """只绑定注册练习源；teach/audio 变化不得改写题目 authority。"""
    files = [
        {
            "surface_id": hosted_name,
            "source_path": source_name,
            "source_html_sha256": _sha256(src / source_name),
        }
        for hosted_name, source_name in st.practice.items()
    ]
    payload = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _pack_source_sha(pack_id: str) -> str:
    manifest_path = REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_pack_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = manifest.get("packs") if isinstance(manifest, dict) else manifest
    row = next(
        (item for item in rows if str(item.get("pack_id") or "").upper() == pack_id),
        None,
    )
    if not row:
        raise TransformError(f"manifest pack missing: {pack_id}")
    source = manifest_path.parent / str(row.get("file") or "")
    actual = _sha256(source)
    if actual != str(row.get("content_sha256") or ""):
        raise TransformError(f"manifest content sha drift: {pack_id}")
    return actual


def _compile_practice_outputs(
    station_id: str, st: Station, *, finished_root: Path
) -> tuple[dict[str, str], dict[str, object]]:
    src = finished_root / st.pack_dir
    _ensure_tutorbot_sheet_runtime()
    pack_id = station_id.upper()
    if not src.is_dir():
        raise TransformError(f"finished pack missing: {src}")
    missing = [name for name in st.practice.values() if not (src / name).is_file()]
    if missing:
        raise TransformError(
            f"finished practice incomplete: {src} missing {', '.join(missing)}"
        )
    rendered_practice: dict[str, str] = {}
    compiled_surfaces: list[dict[str, object]] = []
    for hosted_name, src_name in st.practice.items():
        practice_source = src / src_name
        source_text = practice_source.read_text(encoding="utf-8")
        logical_source = (
            "artifacts/luban_case_family_assets/diagram_microlesson/finished/"
            f"{st.pack_dir}/{src_name}"
        )
        compiled = compile_practice_surface(
            pack_id,
            surface_id=hosted_name,
            html=source_text,
            source_path=logical_source,
            source_html_sha256=_sha256(practice_source),
        )
        rendered = _strip_trailing_whitespace(
            _rewrite_hrefs(
                transform_practice(
                    source_text,
                    pack_id=pack_id,
                    compiled_surface=compiled["surface"],
                    items=compiled["items"],
                ),
                st.href_map,
            )
        )
        compiled["surface"]["published_practice_sha256"] = hashlib.sha256(
            rendered.encode("utf-8")
        ).hexdigest()
        rendered_practice[hosted_name] = rendered
        compiled_surfaces.append(compiled)
    authority = build_practice_authority(
        pack_id,
        source_pack_sha256=_pack_source_sha(pack_id),
        source_bundle_sha256=_practice_source_bundle_sha(src, st),
        compiled_surfaces=compiled_surfaces,
    )
    return rendered_practice, authority


def publish(station_id: str, st: Station, *, finished_root: Path = FINISHED) -> list[str]:
    src = finished_root / st.pack_dir
    dst = HOST / station_id
    if not src.is_dir():
        raise TransformError(f"finished pack missing: {src}")
    required = [*st.teach.values(), *st.practice.values(), "support.js"]
    missing = [name for name in required if not (src / name).is_file()]
    if missing:
        raise TransformError(f"finished pack incomplete: {src} missing {', '.join(missing)}")
    _validate_audio_assets(src)
    _ensure_tutorbot_sheet_runtime()

    # 先把所有页面变换成功，再写入托管目录；任一锚点失配不留下半张新卡。
    rendered_teach = {}
    for hosted_name, src_name in st.teach.items():
        source = (src / src_name).read_text(encoding="utf-8")
        source = _version_audio_assets(source, src)
        rendered_teach[hosted_name] = _strip_trailing_whitespace(
            _rewrite_hrefs(transform_teach(source, station_id.upper()), st.href_map)
        )
    rendered_practice, authority = _compile_practice_outputs(
        station_id, st, finished_root=finished_root
    )
    authority["published_lesson_sha256"] = hashlib.sha256(
        rendered_teach["lesson.html"].encode("utf-8")
    ).hexdigest()
    support = _self_host_support_runtime(
        (src / "support.js").read_text(encoding="utf-8")
    )
    for hosted_name, text in rendered_teach.items():
        preload_match = _AUDIO_PRELOAD_SRC_RE.search(text)
        if not preload_match:
            raise TransformError(f"published page missing first-audio preload: {hosted_name}")
        preload_path = preload_match.group(1).split("?", 1)[0]
        if not (src / preload_path).is_file():
            raise TransformError(
                f"published page first audio missing: {hosted_name} -> {preload_path}"
            )

    # 先在同一父目录组装完整纯派生树，再整体切换；任何变换/拷贝失败都不碰线上旧树。
    # 整树替换也会清掉 C02_progress_payment 等历史 IR 预览残留。
    HOST.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f".{station_id}.staging-", dir=HOST))
    written: list[str] = []
    try:
        for hosted_name, text in rendered_teach.items():
            (staged / hosted_name).write_text(text, encoding="utf-8")
            written.append(hosted_name)

        for hosted_name, text in rendered_practice.items():
            (staged / hosted_name).write_text(text, encoding="utf-8")
            written.append(hosted_name)

        (staged / "support.js").write_text(support, encoding="utf-8")
        written.append("support.js")
        for sub in ("assets", "audio"):
            if (src / sub).is_dir():
                shutil.copytree(
                    src / sub,
                    staged / sub,
                    ignore=shutil.ignore_patterns(".DS_Store"),
                )
                written.append(sub + "/")

        # mkdtemp intentionally keeps the incomplete tree private (0700). The
        # atomically published directory is a public runtime asset and must be
        # traversable by the container's non-root user.
        staged.chmod(0o755)
        backup = dst.with_name(f".{dst.name}.previous")
        if backup.exists():
            shutil.rmtree(backup)
        if dst.exists():
            dst.rename(backup)
        try:
            staged.rename(dst)
        except Exception:
            if backup.exists() and not dst.exists():
                backup.rename(dst)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if staged.exists():
            shutil.rmtree(staged)

    AUTHORITY_HOST.mkdir(parents=True, exist_ok=True)
    authority_path = AUTHORITY_HOST / f"{station_id}.practice.authority.json"
    authority_path.write_text(
        json.dumps(authority, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    written.append(f"server-authority/{station_id}")
    return written


def _practice_only_outputs(
    station_id: str, st: Station, *, finished_root: Path
) -> tuple[dict[str, str], dict[str, object]]:
    dst = HOST / station_id
    lesson = dst / "lesson.html"
    support = dst / "support.js"
    if not lesson.is_file() or not support.is_file():
        raise TransformError(f"hosted card incomplete: {dst} needs lesson.html + support.js")
    rendered, authority = _compile_practice_outputs(
        station_id, st, finished_root=finished_root
    )
    authority["published_lesson_sha256"] = _sha256(lesson)
    return rendered, authority


def check_practice_only(
    station_id: str, st: Station, *, finished_root: Path = FINISHED
) -> list[str]:
    rendered, authority = _practice_only_outputs(
        station_id, st, finished_root=finished_root
    )
    dst = HOST / station_id
    for hosted_name, text in rendered.items():
        if not (dst / hosted_name).is_file() or (dst / hosted_name).read_text(
            encoding="utf-8"
        ) != text:
            raise TransformError(f"practice projection drift: {station_id}/{hosted_name}")
    authority_path = AUTHORITY_HOST / f"{station_id}.practice.authority.json"
    expected = json.dumps(authority, ensure_ascii=False, indent=2) + "\n"
    if not authority_path.is_file() or authority_path.read_text(encoding="utf-8") != expected:
        raise TransformError(f"practice authority drift: {station_id}")
    _assert_manifest_registers_authority(station_id, authority_path)
    return [*rendered, f"server-authority/{station_id}"]


def publish_practice_only(
    station_id: str, st: Station, *, finished_root: Path = FINISHED
) -> list[str]:
    rendered, authority = _practice_only_outputs(
        station_id, st, finished_root=finished_root
    )
    dst = HOST / station_id
    HOST.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f".{station_id}.practice-staging-", dir=HOST))
    try:
        for hosted_name, text in rendered.items():
            (staged / hosted_name).write_text(text, encoding="utf-8")
        authority_staged = staged / f"{station_id}.practice.authority.json"
        authority_staged.write_text(
            json.dumps(authority, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for hosted_name in rendered:
            (staged / hosted_name).replace(dst / hosted_name)
        AUTHORITY_HOST.mkdir(parents=True, exist_ok=True)
        authority_staged.replace(
            AUTHORITY_HOST / f"{station_id}.practice.authority.json"
        )
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return [*rendered, f"server-authority/{station_id}"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="发布注册的鲁班 finished 成品卡")
    parser.add_argument(
        "--finished-root",
        type=Path,
        default=FINISHED,
        help="finished 成品根目录；默认当前仓 artifacts 下的 finished",
    )
    parser.add_argument(
        "--practice-only",
        action="store_true",
        help="只从注册 practice HTML 重建练习页与服务端 sidecar，不改 lesson/support/assets",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="与 --practice-only 联用；只核对 tracked source 与派生物，零写入",
    )
    parser.add_argument("stations", nargs="*", help="可选站点 ID；缺省发布全部注册站点")
    args = parser.parse_args(argv)
    if args.check and not args.practice_only:
        parser.error("--check requires --practice-only")
    if not FONTS_CSS.is_file():
        print(f"publish: 缺共享字体 {FONTS_CSS}（先提交自托管字体子集）", file=sys.stderr)
        return 1
    if not JWEIXIN_JS.is_file():
        print(f"publish: 缺自托管微信 JSSDK {JWEIXIN_JS}（curl res.wx.qq.com/open/js/jweixin-1.6.0.js）",
              file=sys.stderr)
        return 1
    missing_runtime = [str(path) for path in SUPPORT_RUNTIME_ASSETS if not path.is_file()]
    if missing_runtime:
        print(f"publish: 缺自托管卡片 runtime {missing_runtime}", file=sys.stderr)
        return 1
    finished_root = args.finished_root.expanduser().resolve()
    if not finished_root.is_dir():
        print(f"publish: finished 根目录不存在 {finished_root}", file=sys.stderr)
        return 1
    targets = args.stations or sorted(STATIONS)
    unknown = [t for t in targets if t not in STATIONS]
    if unknown:
        print(f"publish: 未注册站点 {unknown}（注册表见 STATIONS）", file=sys.stderr)
        return 1
    failures: list[str] = []
    for sid in targets:
        try:
            if args.practice_only and args.check:
                written = check_practice_only(
                    sid, STATIONS[sid], finished_root=finished_root
                )
            elif args.practice_only:
                written = publish_practice_only(
                    sid, STATIONS[sid], finished_root=finished_root
                )
            else:
                written = publish(sid, STATIONS[sid], finished_root=finished_root)
            print(f"{sid}: {' '.join(written)}")
        except TransformError as exc:
            failures.append(f"{sid}: {exc}")
    if failures:
        print("publish FAILED (fail-closed, 未中锚不落盘该文件):", file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1
    if not args.check:
        _refresh_pack_manifest()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
