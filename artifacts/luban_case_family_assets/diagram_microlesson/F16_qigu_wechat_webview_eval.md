# F16 图解母题卡 · 微信小程序 WebView 技术验证

- **日期**: 2026-06-17
- **被验证物**: `diagram_microlesson/F16_qigu.rendered.html`（v0.2，自包含静态 HTML）
- **小程序工程**: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/yousenwebview`（appid `wx6d4fbd3776ea7d4d`）
- **结论**: **PARTIAL（部分通过）** —— 承载路径已查清且可行，但"在小程序 WebView 里真渲染这张卡"被 HTTPS 域名白名单卡住，本轮不部署，故未真机验证。

## 1. 验证范围

只验证"这张静态 HTML 卡能否进小程序 WebView"，含：自动旁白计时器、step reveal、错因跳转、复测反馈、移动端字号/换行、触摸区、无横向滚动、离线/静态资源策略、web-view 域名约束。**不做正式集成、不改聊天入口、不改评分链路。**

## 2. 是否真实打开微信项目

**否（有意不开）。** 已做的真实检查：

- `cli islogin` → `{"login":true}`（DevTools 已登录、IDE server 正常）。
- 只读勘察了 `yousenwebview` 工程结构与既有 web-view 承载方式。

**为什么不 `cli open` 跑预览**：小程序 web-view 受 `project.config.json` 的 `urlCheck:true` + host 白名单约束，**只能加载白名单内的 HTTPS 网页**，`file://` / 本地 HTML 不可直接加载。本轮约定不部署、不开隧道，所以即使打开项目也无法真正把这张卡加载进 web-view —— 那只是表演，不产生有效证据。故不开，诚实记 partial。

## 3. 是否真实进入 packageDeeptutor 临时页

**否，且本轮不应该建临时页。** 关键发现：工程**已有通用 web-view 承载页**，无需新建第二套：

| 既有页面 | 作用 |
|---|---|
| `pages/text/text` | 通用 `<web-view src="{{url}}">`，带 `sanitizeAbsoluteUrl()` + `isAllowedHost()` 白名单（`*.yousenjiaoyu.com` 等） |
| `pages/view/view` | 解析 query 后 `redirectTo` 到 `pages/text/text` |
| `tests/test_text_url_allowlist.js` | 白名单单测（允许 yousen 域名透传、外域回落安全首页） |

→ 正确做法（thin wrapper）：**复用 `pages/text/text`，不加新页**。要展示这张卡，只需把 HTML 发到白名单 HTTPS 地址，然后 `/pages/text/text?url=<encoded https url>`。本轮未改 `yousenwebview` 任何文件。

## 4. HTML 静态卡在小程序 WebView 下的可行性判断

**可行，但有前置条件**：必须先把 `F16_qigu.rendered.html` 发布到白名单 HTTPS 域名（如 `https://test2.yousenjiaoyu.com/...`）。一旦能加载，这张卡的特性其实**非常契合** web-view：

- 单文件、CSS/JS/SVG 全内联、**零外链零子请求** → 加载后完全离线可用，不受 web-view 网络/资源策略影响。
- 不依赖任何小程序 JSAPI、不需要 `wx.miniProgram` 通信（它只是自洽教学卡）。

## 5. 哪些能力"理论可用"（标准 WebView 行为，高置信）

| 能力 | 判断 | 依据 |
|---|---|---|
| step reveal（class 切换 + SVG 图层高亮） | 可用 | 纯 DOM/CSS，WebView 通用 |
| 错因跳转（hash + scrollIntoView） | 可用 | 标准 DOM API |
| 复测反馈（DOM 文案 + 跳回 review_step） | 可用 | 标准 DOM API |
| 无横向滚动 | 可用 | 已在 390px 实测 `scrollWidth===390` |
| 触摸区 ≥44px | 可用 | 已实测 step-tab 52.75 / option 52 / play 46 / error 75 |
| 字号/换行 | 大概率可用 | 用 `-apple-system/PingFang SC` 字体栈 + 弹性布局，已做移动端断点 |
| 自动旁白计时器（setTimeout） | 前台可用 | 标准定时器；**后台/锁屏行为需真机确认（见风险）** |

## 6. 哪些能力"必须真机验证"

1. 自动字幕计时器在 **iOS WKWebView 锁屏/切后台**时是否被节流/暂停（前台学习场景影响小，但要确认恢复行为）。
2. **Android** 各厂商内核下的字体渲染与 `scroll-behavior:smooth`、滚动惯性差异。
3. 真机 web-view 业务域名白名单实际放行（DevTools 可用"不校验合法域名"绕过，真机不行）。
4. 触摸滚动 + step-tab 连点的手感与误触。

## 7. 最大风险

1. **web-view 域名/HTTPS 限制**：`urlCheck:true`，只放行白名单 HTTPS；微信后台还需配"业务域名"并放 `校验文件`。未配＝真机白屏。
2. **本地 file HTML ≠ 小程序可访问 URL**：DevTools 模拟器 + "不校验合法域名"可临时加载本地/隧道 HTTPS，但 `file://` 在 web-view 一律不可用；真机必须真实 HTTPS。
3. **字幕自动播放 + 计时器后台行为**：`setTimeout` 在 WebView 退后台可能被挂起，回前台需要能继续（当前实现暂停/继续逻辑可兜底，但要真机回归）。
4. **iOS / Android WebView 差异**：WKWebView vs 各家 Android 内核，字体、smooth scroll、定时器精度不一致。
5. **web-view 全屏特性**：web-view 页会占满并盖住小程序原生导航，分享/返回需在外层小程序页处理（复用 `pages/text` 已有的行为即可）。

## 8. 建议的正式接入方式（future，本轮不执行）

1. 把 `render_card.py` 产物发布到白名单静态路径，例如 `https://test2.yousenjiaoyu.com/diagram/F16_qigu.html`（对象存储/CDN/后端静态目录均可），微信后台把该域名加入 **web-view 业务域名**并上传校验文件。
2. **复用** `/pages/text/text?url=<encodeURIComponent(https url)>` 打开，零新页面、零业务耦合。
3. 灰度顺序：DevTools 模拟器（开"不校验合法域名"）→ 内部体验号真机 → 3-5 学员（见 B 轨）。
4. 学员可读性验证**不必等小程序**：直接把 HTML AirDrop 到 iPhone 用 Safari 打开（Safari 可开本地 file，web-view 不行），即可先跑 B 轨。

## 9. 明确

**本轮不是正式集成。** 未改 `yousenwebview` 任何文件、未建临时页、未部署、未接业务状态/评分/learner state。A 轨结论为 **PARTIAL**：技术路径与可行性已确认，真机/真渲染待"发布到白名单 HTTPS + 配业务域名"后再做。
