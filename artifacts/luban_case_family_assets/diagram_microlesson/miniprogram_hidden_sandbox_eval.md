# diagram_microlesson · 小程序隐藏沙盒验证

- **日期**: 2026-06-17
- **结论**: **PARTIAL**。隐藏沙盒页已就绪、DevTools 已真实打开项目（含隐藏页、无编译错误）、本地静态服务证明 F16/N01 可被加载；但"在 DevTools 模拟器里对 F16/N01 web-view 内容做程序化截图/交互"被一个**手动 DevTools 安全设置（服务端口）**挡住，未完成像素级 in-webview 截图。不是正式集成。

## 1. 采用复用 `pages/text/text` 还是新增隐藏页

**两者都查了，结论是新增隐藏页（任务授权的 fallback）**：

- `pages/text/text` 存在且是通用 `<web-view>`，但 `isAllowedHost()` 只放行 `*.yousenjiaoyu.com`，**localhost 会被拒回落首页**；且目标 HTTPS 原型 URL **当前 404（未部署）**。两条都让复用无法加载本卡。
- 故新增隐藏页 `packageDeeptutor/pages/internal/diagramWebviewTest/`（只含 `web-view`，`url` 由 query 传入，标注 *internal prototype only*，不接任何业务）。

> 生产路径仍优先复用 `pages/text/text`：只要把 2 个 HTML 发布到白名单 HTTPS 路径即可，零小程序改动（见第 8 节）。隐藏页只是"本地/内测即时验证"用。

## 2. 测试 URL

| 用途 | URL |
|---|---|
| 生产隐藏复用（**当前 404，需先部署**） | `https://test2.yousenjiaoyu.com/internal-prototypes/diagram-microlesson/F16_qigu.html` |
| 本地沙盒（本轮用，DevTools 模拟器 + 关闭"校验合法域名"） | `http://127.0.0.1:8799/F16_qigu.rendered.html` |
| 本地沙盒 N01 | `http://127.0.0.1:8799/N01_network_keypath.rendered.html` |
| 隐藏页路由 | `/packageDeeptutor/pages/internal/diagramWebviewTest/diagramWebviewTest?url=<encodeURIComponent(上面任一)>` |

本地服务（用完即杀，不常驻）：
```bash
cd artifacts/luban_case_family_assets/diagram_microlesson && python3 -m http.server 8799 --bind 127.0.0.1
```

## 3. 是否真实在 DevTools 打开

**是。** `cli islogin` → `{"login":true}`；`cli auto --project yousenwebview --trust-project` → `✔ auto` / `Using AppID: wx6d4fbd3776ea7d4d`，**项目（已含隐藏页注册）成功打开且无编译报错**——说明 app.json 注册与隐藏页结构有效。

## 4. 是否真实加载 F16/N01（webview 像素截图）

**否（PARTIAL）。** 程序化截图需 `miniprogram-automator`（已临时装于 /tmp）驱动，但 `automator.launch` 报 `Failed to launch ... make sure http port is open`：DevTools 的 **「设置 → 安全设置 → 服务端口(CLI/automation)」未开启**，这是 GUI 手动开关，无法 headless 打开；`connect` 同样依赖它。故未拿到 in-simulator 的 F16/N01 截图。

补充佐证（非 in-webview）：F16/N01 静态 HTML 已在 **Chromium 390px（CDP）** 真渲染验证过（见同目录 `F16_qigu.rendered.mobile*.png` / `N01_network_keypath.rendered.mobile.png`），`scrollWidth===390` 无横向滚动、旁白/错因跳转/复测反馈断言全过。web-view 用系统 WebView，外观与之高度一致，但**小程序 web-view 特有行为仍需真机/模拟器复核**。

> 注：即便开了服务端口，automator 的截图对 `web-view` 这类**原生层常常截为空白**，更可靠的是 macOS `screencapture` 抓模拟器窗口（脚本已内置兜底）。

## 5. iPhone / Android 待测项（需真机 + HTTPS 部署后）

- 自动旁白计时器在 iOS WKWebView 锁屏/切后台的节流与恢复。
- Android 各内核字体渲染、`scroll-behavior:smooth`、滚动惯性。
- 触摸区手感、step-tab 连点误触。
- web-view 全屏占满时小程序原生返回/分享行为。
- 真机 web-view 业务域名白名单实际放行（真机不认 localhost、不认"关闭校验"）。

## 6. 已知风险

1. **HTTPS 未部署**：原型 URL 404，复用路径与真机验证均被此阻塞。
2. **DevTools 服务端口手动开关**：自动化截图/交互的前置，无法 headless 打开。
3. **localhost 仅模拟器可用**：真机必须真实 HTTPS + 配 web-view 业务域名。
4. **automator 对 web-view 截图可能空白**（原生层），需 macOS 截屏兜底。
5. **app.json 处于改动态（未提交）**：注册了隐藏页；按第 8 节可一键撤销。

## 7. 为什么不会被普通用户看到

- 隐藏页**不在 `tabBar`、不在 `custom-tab-bar`、不被任何正式页面 `navigateTo` 引用**——只在 `app.json` 的 `packageDeeptutor.pages[]` 注册（不注册无法编译），但无任何入口。
- 仅能通过**显式输入路由**（DevTools 编译模式自定义启动页 / 手动 `navigateTo`）进入；普通用户无路径可达。
- 页面标题与注释均标 **internal prototype only**；不接业务接口、不写数据库、不写 learning evidence、不接评分/learner state。
- `urlCheck` 已**还原为 true**；localhost 加载只在 DevTools 临时关闭"校验合法域名"时可用，不影响线上。

## 8. 如何撤销

```bash
# 1) 删除隐藏页
rm -rf yousenwebview/packageDeeptutor/pages/internal/diagramWebviewTest
# (若 internal 目录已空) rmdir yousenwebview/packageDeeptutor/pages/internal

# 2) 从 app.json 的 packageDeeptutor.pages[] 删除这一行
#    "pages/internal/diagramWebviewTest/diagramWebviewTest"

# 3) project.config.json 已自动还原(urlCheck=true)，无需操作
# 4) 本地静态服务已杀；临时 automator 在 /tmp/mpauto，可 rm -rf
```
本轮**未 commit**，撤销后 yousenwebview 回到改动前。

## 生产接入（未来，本轮不做）

把 `F16_qigu.rendered.html` / `N01_network_keypath.rendered.html` 发布到 `https://test2.yousenjiaoyu.com/internal-prototypes/diagram-microlesson/`，微信后台配 web-view 业务域名，然后**复用** `/pages/text/text?url=...` 打开（无需隐藏页、零业务耦合）。隐藏页可随后按第 8 节删除。
