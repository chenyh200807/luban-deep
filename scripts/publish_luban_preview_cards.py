#!/usr/bin/env python3
"""发布 finished 深母题教学卡到 web/public/luban-preview/<站点>/（打包层，纯确定性）。

背景：
- 卡唯一源 = ``artifacts/luban_case_family_assets/diagram_microlesson/finished/<PACK>/``
  （teach/practice .dc.html + support.js + assets/ + audio/）。托管副本永远由本脚本
  派生，不手改生成物。
- 2026-07-05 owner 真机反馈两个问题在打包层治本：
  1. **没有声音**：F16 托管漏了 ``audio/``（根因链 = ``.gitignore`` 全局 ``*.mp3``
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

站点注册表 = 本文件 STATIONS：新增托管卡在这里登记（station id = pack_id 小写，
manifest 的 card_hosted 按 web/public/luban-preview/<pack_id小写>/lesson.html 扫描）。
C02 上下集：消费端只认单入口 lesson.html —— lesson.html=上集，集内「下集」链接
lesson2.html（卡自带上下集互链，发布时只重写 href，不改 read_model 契约）。
"""
from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FINISHED = REPO / "artifacts" / "luban_case_family_assets" / "diagram_microlesson" / "finished"
HOST = REPO / "web" / "public" / "luban-preview"
FONTS_CSS = HOST / "fonts" / "fonts.css"
JWEIXIN_JS = HOST / "vendor" / "jweixin.js"


@dataclass(frozen=True)
class Station:
    pack_dir: str                       # finished/ 下的目录名
    teach: dict[str, str]               # 托管名 -> 源文件名（lesson.html 必须在场）
    practice: str                       # practice 源文件名
    href_map: dict[str, str] = field(default_factory=dict)  # 卡内互链重写


def _p40(pack: str) -> Station:
    return Station(
        pack_dir=pack,
        teach={"lesson.html": f"{pack}.teach.dc.html"},
        practice=f"{pack}.practice.dc.html",
        href_map={
            f"{pack}.practice.dc.html": "practice.html",
            f"{pack}.teach.dc.html": "lesson.html",
        },
    )


STATIONS: dict[str, Station] = {
    "f16": _p40("P40_F16"),
    "n01": _p40("P40_N01"),
    "j01": _p40("P40_J01"),
    "f02": _p40("P40_F02"),
    "g01": _p40("P40_G01"),
    # S07B 是 S07 pack 的成品卡变体（manifest 无独立 S07B slot）：托管在 s07 站位，
    # S07 当前未签发（published=False + barred），卡就绪等签发。
    "s07": _p40("P40_S07B"),
    "c02": Station(
        pack_dir="C02",
        teach={
            "lesson.html": "C02.teach.up.dc.html",
            "lesson2.html": "C02.teach.down.dc.html",
        },
        practice="C02.practice.dc.html",
        href_map={
            "C02.teach.up.dc.html": "lesson.html",
            "C02.teach.down.dc.html": "lesson2.html",
            "C02.practice.dc.html": "practice.html",
        },
    ),
}

# ───────────────────────── 字体（全部 html） ─────────────────────────

_FONT_LINKS_OLD = (
    '<link rel="preconnect" href="https://fonts.googleapis.com"/>\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;900'
    '&family=Long+Cang&display=swap" rel="stylesheet"/>'
)
_FONT_LINKS_NEW = '<link href="../fonts/fonts.css" rel="stylesheet"/>'

# teach 卡额外注入微信 JSSDK（自托管，避免外链依赖；practice 卡不需要）
_JWEIXIN_TAG = '<script src="../vendor/jweixin.js"></script>'

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
_OPENASK_NEW = "openAsk(){ if(this.wxAsk())return; this.setState({askOpen:true,playing:false}); }"

_RVALS_APPEND = (
    'fullscreen:()=>this.fullscreen(),phoneRef:el=>this.phoneRef(el),'
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
    text = _sub(text, _FONT_LINKS_OLD, _FONT_LINKS_NEW + "\n" + _JWEIXIN_TAG, "font-links")
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
    text = _sub(text, "document.head.appendChild(s); }", _DIDMOUNT_APPEND, "didmount-append")
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


def transform_practice(text: str) -> str:
    return _sub(text, _FONT_LINKS_OLD, _FONT_LINKS_NEW, "font-links")


def _rewrite_hrefs(text: str, href_map: dict[str, str]) -> str:
    for old, new in href_map.items():
        text = text.replace(f'href="{old}"', f'href="{new}"')
    return text


def publish(station_id: str, st: Station) -> list[str]:
    src = FINISHED / st.pack_dir
    dst = HOST / station_id
    if not src.is_dir():
        raise TransformError(f"finished pack missing: {src}")
    dst.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    for hosted_name, src_name in st.teach.items():
        text = (src / src_name).read_text(encoding="utf-8")
        text = transform_teach(text, st.pack_dir)
        text = _rewrite_hrefs(text, st.href_map)
        (dst / hosted_name).write_text(text, encoding="utf-8")
        written.append(hosted_name)

    text = (src / st.practice).read_text(encoding="utf-8")
    text = transform_practice(text)
    text = _rewrite_hrefs(text, st.href_map)
    (dst / "practice.html").write_text(text, encoding="utf-8")
    written.append("practice.html")

    shutil.copy2(src / "support.js", dst / "support.js")
    written.append("support.js")
    for sub in ("assets", "audio"):
        if (src / sub).is_dir():
            shutil.copytree(src / sub, dst / sub, dirs_exist_ok=True)
            written.append(sub + "/")
    return written


def main(argv: list[str]) -> int:
    if not FONTS_CSS.is_file():
        print(f"publish: 缺共享字体 {FONTS_CSS}（先提交自托管字体子集）", file=sys.stderr)
        return 1
    if not JWEIXIN_JS.is_file():
        print(f"publish: 缺自托管微信 JSSDK {JWEIXIN_JS}（curl res.wx.qq.com/open/js/jweixin-1.6.0.js）",
              file=sys.stderr)
        return 1
    targets = argv or sorted(STATIONS)
    unknown = [t for t in targets if t not in STATIONS]
    if unknown:
        print(f"publish: 未注册站点 {unknown}（注册表见 STATIONS）", file=sys.stderr)
        return 1
    failures: list[str] = []
    for sid in targets:
        try:
            written = publish(sid, STATIONS[sid])
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
