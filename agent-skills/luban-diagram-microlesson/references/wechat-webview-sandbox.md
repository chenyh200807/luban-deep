# 微信小程序 web-view 承载静态卡 / 隐藏沙盒

把 diagram_microlesson 生成的静态 HTML 放进真实小程序看效果时,绕不开的事实和套路。

## 不可省的两条(微信机制,不是 bug)
1. **web-view 不能读本地文件**,必须给它能访问的 http(s) 网址 → 本地起静态服务或部署。
2. **localhost 不在合法域名** → DevTools「详情→本地设置」勾「不校验合法域名、web-view 业务域名…」(一个勾选);真机不认 localhost、不认这个勾,必须真实 HTTPS + 后台配 web-view 业务域名。

开发者工具**只渲染小程序页面(WXML)**,不是通用 HTML 浏览器;静态 HTML 只能进 `<web-view>`。

## 工程事实(yousenwebview)
- project root: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/yousenwebview`(机器上有 9 个副本,**DevTools 容易开错副本→"完全没有你新建的页面"**;先确认开的是这个绝对路径)。
- 已有通用承载页 `pages/text/text`(`<web-view src>` + host 白名单 `*.yousenjiaoyu.com` + `urlCheck:true`):部署到白名单 HTTPS 后 **复用它**,零小程序改动,无需新页。
- localhost 调试需自建隐藏页(白名单挡 localhost):`packageDeeptutor/pages/internal/diagramWebviewTest/`(仅 web-view,url 走 query,默认本地 F16,`?card=n01` 切;标 internal prototype only;在 app.json subpackages 注册但不进任何 tabBar/导航→普通用户进不去)。
- 进隐藏页:DevTools「编译模式」→ 启动页面填该路由(默认即本地 F16)。

## 本地服务
`cd <diagram_microlesson> && python3 -m http.server 8799 --bind 127.0.0.1`(轻量,用完即杀)。

## automator 截图的坑
- `miniprogram-automator` 的 launch/connect 需 DevTools「安全设置→服务端口」**手动开启**(GUI 开关,无法 headless);未开 → `Failed to launch ... make sure http port is open`。
- automator 截图常**截不到 web-view 原生层**(空白) → 用 macOS `screencapture` 抓模拟器窗口兜底。

## 撤销隐藏沙盒
删 `packageDeeptutor/pages/internal/diagramWebviewTest/` + 从 app.json 删那一行;`project.config.json` 的 urlCheck 测后还原 true。
