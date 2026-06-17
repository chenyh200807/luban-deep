# 零依赖 CDP 截图 + DOM 断言

本机没装 puppeteer/playwright,但有 Chrome.app + Node(自带全局 `WebSocket`)。直接连 Chrome DevTools Protocol,不装库。

## 步骤
1. 启动: `Google Chrome --headless=new --remote-debugging-port=9333 --hide-scrollbars --allow-file-access-from-files --disable-gpu --user-data-dir=$(mktemp -d) about:blank &`
2. `GET http://127.0.0.1:9333/json` 找 `type==="page"` 的 `webSocketDebuggerUrl`,`new WebSocket(url)`。
3. id 关联请求/响应;`Page.enable`+`Runtime.enable`;`Emulation.setDeviceMetricsOverride {width:390,height:844,deviceScaleFactor:2,mobile:true,screenWidth:390,screenHeight:844}` 模拟手机。
4. 导航别等 `Page.loadEventFired`(会竞态超时),改轮询 `Runtime.evaluate document.readyState==="complete" && location.href` 开头。仅改 hash(如 `#step=8`)不会重载页面/不重跑脚本——测深链要整页 navigate。
5. 交互断言:`Runtime.evaluate {returnByValue:true}` 跑 `el.click()` 后读 `document.documentElement.dataset.*` 等状态。
6. 截图:`Page.captureScreenshot {captureBeyondViewport:true}` 整页,或 `clip:{x,y,width:390,height:844,scale:1}` 取首屏(看固定底部条)。
7. 收尾 kill chrome + rm profile。脚本放 /tmp,不入仓。

## 渲染器配合
把当前态暴露成 `document.documentElement.dataset.*`(activeLayer/narrMode/screen…)便于断言。

## next-guard 自匹配假阳性
`agent-owned-next-guard.sh --check` 用 pattern 匹配进程 args。和 `pgrep -af '...next dev'` 或 `ps|grep next-server` **放进同一条复合命令**,会匹配到正在执行该命令的 zsh 自身(owner=claude-code,rss≈3MB,pid 每次变),误报 "AI-agent-owned Next root"。判真假:看 args 是不是你刚跑的命令 + rss 极小 + `ps -A|grep next-server` 无真实进程。**单独运行 guard**(命令行不带 next-server/next dev/postcss 触发词)即可避免。

## Web 内存守则
截图/Web 工作前先跑 `~/.codex/bin/codex-memory-snapshot.sh`;别让 Claude Code 拥有长跑的 next dev/node 树。
