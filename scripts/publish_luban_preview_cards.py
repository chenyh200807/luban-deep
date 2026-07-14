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
  4. **「问追AI」接通问鲁班**：唯一聊天入口铁律——不在卡内做第二套聊天。注入自托管
     ``../vendor/jweixin.js``；小程序 web-view 环境（__wxjs_environment / UA 双检 +
     wx.miniProgram 在场）下 openAsk 改跳
     ``/packageDeeptutor/pages/chat/chat?entrySource=teach_card&pack_id=<pack>``
     （scene_title 取当前幕 beats[bi][3]，取不到省略）；非微信环境保持原卡内追问
     浮层，不报错。

用法::

    python3 scripts/publish_luban_preview_cards.py           # 发布全部注册站点
    python3 scripts/publish_luban_preview_cards.py f16 c02   # 只发布指定站点
    python3 scripts/publish_luban_preview_cards.py --practice-only --check
                                                        # 从 tracked HTML 重编并核对派生物
    python3 scripts/publish_luban_preview_cards.py \\
      --finished-root /absolute/path/to/finished             # 显式使用外部 finished 成品根

站点注册表 = 本文件 STATIONS：新增托管卡在这里登记（station id = pack_id 小写，
manifest 的 card_hosted 按 web/public/luban-preview/<pack_id小写>/lesson.html 扫描）。
C02 上下集：消费端只认单入口 lesson.html —— lesson.html=上集，集内「下集」链接
lesson2.html（卡自带上下集互链，发布时只重写 href，不改 read_model 契约）。
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

FINISHED = REPO / "artifacts" / "luban_case_family_assets" / "diagram_microlesson" / "finished"
HOST = REPO / "web" / "public" / "luban-preview"
AUTHORITY_HOST = REPO / "deeptutor" / "services" / "luban_lesson" / "compiled"
FONTS_CSS = HOST / "fonts" / "fonts.css"
JWEIXIN_JS = HOST / "vendor" / "jweixin.js"
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

    目录名和文件前缀始终同源；C02 与 S07B 的版本选择只在 STATIONS 明示，
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
    "n03": _p40("P40_N03"),
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

# teach/practice 卡额外注入微信 JSSDK（practice 保存学习证据时复用）
_JWEIXIN_TAG = '<script src="../vendor/jweixin.js"></script>'

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
  updateFitZoom(){ try{ const z=Math.min(window.innerWidth/390, __LZ_FIT_CAP__); document.body.style.setProperty('--lz-fit', String(z)); }catch(e){} }
  wxAsk(){ try{
      const wxm=window.wx&&window.wx.miniProgram;
      const inMini=(window.__wxjs_environment==='miniprogram')||/miniprogram/i.test(navigator.userAgent||'');
      if(!wxm||!inMini) return false;
      let st=''; try{ let bi=0; for(let i=0;i<this.beats.length;i++){ if(this.state.t>=this.beats[i][1]) bi=i; } st=String((this.beats[bi]&&this.beats[bi][3])||''); }catch(e){}
      if(this.state.playing){ this.setState({playing:false}); this.setSpeechPaused(true); }
      wxm.navigateTo({url:'/packageDeeptutor/pages/chat/chat?entrySource=teach_card&pack_id=__LZ_PACK__'+(st?'&scene_title='+encodeURIComponent(st):'')});
      return true; }catch(e){ return false; } }"""

_OPENASK_OLD = "openAsk(){ this.setState({askOpen:true,playing:false}); }"
_OPENASK_NEW = "  openAsk(){ if(this.wxAsk())return; this.setState({askOpen:true,playing:false}); }"

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


def transform_teach(text: str, pack_id: str) -> str:
    # 1. 字体自托管 + 微信 JSSDK（自托管）
    preload_element = _audio_preload_element(text)
    text = _sub(text, _FONT_LINKS_OLD, _FONT_LINKS_NEW + "\n" + _JWEIXIN_TAG, "font-links")
    text = _sub(text, "<body>", "<body>\n" + preload_element, "audio-preload")
    # 新一批 finished 已内置全屏/控制条结构（ctrlHidden），不能再把旧母版的
    # 锚定回灌重复套进去。只做所有卡共用的字体/JSSDK/问鲁班桥接；这仍是同一
    # 打包入口，且 bridge 锚不中就 fail-closed，不会把陌生模板误判为可发布。
    if "ctrlHidden:false" in text:
        if "wxAsk(){" not in text:
            wx_ask = _FULLSCREEN_NEW[_FULLSCREEN_NEW.index("  wxAsk(){"):].replace("__LZ_PACK__", pack_id)
            text = _sub(text, _OPENASK_OLD, wx_ask + "\n" + _OPENASK_NEW, "openask-wx")
        return text
    # S07 安全事故成品使用另一套已自带双向全屏的母版（multiline `next` 版本）。
    # 不把旧单行母版的整套控制条再次套入；只接入同一问鲁班桥接。
    if "const next=!this.state.fs;" in text and "document.body.classList.toggle('luban-fs', next);" in text:
        if "wxAsk(){" not in text:
            wx_ask = _FULLSCREEN_NEW[_FULLSCREEN_NEW.index("  wxAsk(){"):].replace("__LZ_PACK__", pack_id)
            text = _sub(text, _OPENASK_OLD, wx_ask + "\n" + _OPENASK_NEW, "openask-wx")
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
    # 6. fullscreen() 替换 + 新方法（updateFsScale/scheduleHide/tapToggle/updateFitZoom/wxAsk）
    fs_methods = (_FULLSCREEN_NEW
                  .replace("__LZ_FIT_CAP__", str(_FIT_ZOOM_CAP))
                  .replace("__LZ_PACK__", pack_id))
    text = _sub(text, _FULLSCREEN_OLD_RE, fs_methods, "fullscreen-method", literal_pattern=False)
    # 6b. openAsk：小程序 web-view 内改跳问鲁班 chat 页（非微信环境保持原浮层）
    text = _sub(text, _OPENASK_OLD, _OPENASK_NEW, "openask-wx")
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


def transform_practice(
    text: str,
    *,
    pack_id: str,
    compiled_surface: dict[str, object],
    items: list[dict[str, object]],
) -> str:
    """Thin publisher wrapper：字体/JSSDK 处理后交给内容内核。"""
    text = _sub(
        text,
        _FONT_LINKS_OLD,
        _FONT_LINKS_NEW + "\n" + _JWEIXIN_TAG,
        "font-links",
    )
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
