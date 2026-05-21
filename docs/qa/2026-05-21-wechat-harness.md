# QA Report — wechat-harness (report-only)

| Field | Value |
|---|---|
| Date | 2026-05-21 |
| Target (intended) | `http://127.0.0.1:3031/wechat-harness` |
| Target (actually reachable) | `http://127.0.0.1:3000/wechat-harness` (same `web/` project, alt port) |
| Branch | `fix/markdown-streaming-render-newline-loss` |
| Mode | report-only (no source reads, no fixes, no commits) |
| Browser | gstack browse (Chromium headless) |
| Screenshot dir | `.gstack/qa-reports/screenshots-2026-05-21/` |
| Evidence dump | `.gstack/qa-reports/screenshots-2026-05-21/evidence-*` |
| Baseline JSON | `.gstack/qa-reports/baseline-wechat-harness-2026-05-21.json` |
| Reporter | gstack /qa-only |

---

## Health Score: 5 / 100

**评分逻辑**：可达的 dev server (`:3000`) 全站 SSR 500，目标 dev server (`:3031`) 未启动，FastAPI 后端 (`:8000`) 未启动。
- Console：100（没办法采到应用层错误，因为 SSR 在 HTML 出来之前就 500 了，浏览器只收到 21 字节裸文本）
- Links：N/A（页面没渲染，无链接可探）
- Functional：0（全站路由 SSR 失败）
- Visual / UX / Content / Accessibility：N/A（页面无内容）
- 复盖率（Boil-the-Lake）：原计划测试矩阵 0/9 完成

**这不是产品质量分，是环境就绪度分。** 应用功能在本次 QA 中 **未被覆盖**，详见底部 "未覆盖风险"。

---

## 环境就绪状态（写在最前，决定下一步）

| URL | 期望 | 实际 | 证据 |
|---|---|---|---|
| `http://127.0.0.1:3031/wechat-harness` | 200 + Next.js wechat-harness 页 | **无服务**，浏览器 `ERR_CONNECTION_REFUSED` | `screenshots-2026-05-21/p0-3031-no-service.png`（白屏） |
| `http://127.0.0.1:3000/wechat-harness` | （非用户指定）200 | **HTTP 500**，body 21 字节裸文本 `Internal Server Error`，无 `content-type` | `screenshots-2026-05-21/p0-3000-wechat-harness-500.png`（白底，左上角 mono 字体 "Internal Server Error"） |
| `http://127.0.0.1:8000/api/v1/health` | 200 | **无服务** | `screenshots-2026-05-21/p0-8000-backend-missing.png`（白屏） |
| `http://127.0.0.1:8000/` | 200/404 之类有响应 | **无服务** | 同上 |

**Listening 端口实测**（QA 开始前）：

```
node 78117 yehongchen 13u IPv6 ... TCP *:3000 (LISTEN)  ← next-server v16.2.6
（无 :3031）
（无 :8000）
```

**`:3000` 上的全站 SSR 状况**（curl 验证）：

| Path | HTTP | size | content-type |
|---|---|---|---|
| `/` | 500 | 21 | (空) |
| `/chat` | 500 | 21 | (空) |
| `/learning-brain` | 500 | 21 | (空) |
| `/settings` | 500 | 21 | (空) |
| `/login` | 500 | 21 | (空) |
| `/wechat-harness` | 500 | 21 | (空) |
| `/api/health` | 500 | 21 | (空) |
| `/favicon.ico` | 200 | 283 | image/x-icon |

唯一返回 200 的是静态 favicon。所有 SSR 路由 + 所有 API 路由统一返回 21 字节裸 `Internal Server Error`，没有 Next.js 自带的错误页 HTML（这种短到 21 字节、`content-type` 为空的响应不是 Next dev 默认错误页形态）。

**尝试拉起 `:3031` 的结果**：

```
$ PORT=3031 next dev -p 3031
▲ Next.js 16.2.6 (Turbopack)
- Local: http://localhost:3031
✓ Ready in 645ms
⨯ Another next dev server is already running.
  - Local: http://localhost:3000
  - PID:   78117
  - Dir:   /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/web
  Run kill 78117 to stop it.
```

Next.js 16 在同一项目目录下加了单例锁——第二个 `next dev` 哪怕 listen 成功，也会拒绝服务请求并立即退出。完整日志：`.gstack/qa-reports/screenshots-2026-05-21/evidence-next-3031-singleton-rejection.log`。

**结论**：当前主机环境无法直接 QA `wechat-harness` 业务行为。先解决环境，再继续。

---

## P0 — 阻塞发布

### P0-1. 用户指定的 `:3031` 没有任何服务

- **页面 / 视口**：`http://127.0.0.1:3031/wechat-harness`，所有视口
- **复现步骤**：
  1. `curl --max-time 3 http://127.0.0.1:3031/wechat-harness`
  2. 浏览器打开同一 URL
- **期望**：HTTP 200，渲染 `/wechat-harness` 客户端骨架
- **实际**：TCP 拨号失败，HTTP code `000`，浏览器空白页（ERR_CONNECTION_REFUSED）
- **证据**：`.gstack/qa-reports/screenshots-2026-05-21/p0-3031-no-service.png`
- **阻塞发布**：是（QA 矩阵 0% 覆盖，无法判断本次提交是否回归）

### P0-2. `:3000` 上 next dev 进程仍在运行但**全站 SSR 500**

- **页面 / 视口**：`http://127.0.0.1:3000` 下所有路由，桌面端 1280x720
- **复现步骤**：
  1. `curl http://127.0.0.1:3000/wechat-harness` → HTTP 500，body 21 字节 `Internal Server Error`，无 `content-type`
  2. 同样查 `/`、`/chat`、`/learning-brain`、`/settings`、`/login`、`/api/health` 全部 500
  3. 浏览器 console: `Failed to load resource: the server responded with a status of 500 (Internal Server Error)`
- **期望**：dev 模式至少返回 Next.js 自带错误页（含错误堆栈 HTML、`content-type: text/html`、几 KB body）
- **实际**：每个路由都是 21 字节裸字符串 `Internal Server Error`，无 HTML 包装，无 `content-type` header
- **证据**：
  - 截图：`.gstack/qa-reports/screenshots-2026-05-21/p0-3000-wechat-harness-500.png`
  - 原始 body：`.gstack/qa-reports/screenshots-2026-05-21/evidence-3000-500-body.txt`（21 bytes）
- **观察（仅作记录，未做根因诊断）**：响应形态（短裸文本、空 ct、所有路径同响应）通常对应以下几类——Next.js worker 进程 crash + 父进程兜底、上游 proxy/前置 middleware 拦截、或自定义 server.js 全局 catch 兜底。**没读源码不下结论**。
- **阻塞发布**：是

### P0-3. FastAPI 后端 `:8000` 没有运行

- **页面 / 视口**：`http://127.0.0.1:8000/*`
- **复现步骤**：`curl --max-time 3 http://127.0.0.1:8000/api/v1/health` 与 `curl ... /`
- **期望**：FastAPI health 路由 200
- **实际**：HTTP code `000`，连接被拒
- **证据**：`.gstack/qa-reports/screenshots-2026-05-21/p0-8000-backend-missing.png`
- **影响**：即便 `:3031` 起得来，wechat-harness 走 `/api/v1/ws` 流式聊天主链路会立刻失败；学情 / 报告 / 出题接口同样无后端。**强烈怀疑**这也是 `:3000` 全站 500 的上游原因（Next dev SSR 在 server component 里调后端会因 ECONNREFUSED 抛 unhandled exception），但**未做根因**。
- **阻塞发布**：是

---

## P1 / P2 / P3

本次 QA **未覆盖任何应用层场景**，因此 P1/P2/P3 列表全部空缺。先解决 P0 才能产出 P1+ 的发现。

---

## 未覆盖风险（原计划测试范围，本轮全部 0% 覆盖）

下列项目按你指定的测试范围排，每一条都没有走过——不要把它们当作"已验证 OK"。

### /wechat-harness 主页面（移动端 375x812 + 桌面端 1440x900）
- 首屏渲染、骨架加载
- AppShell 入口、底部导航、可视区域裁切
- WebSocket `/api/v1/ws` 连接建立
- 聊天主链路：用户发问 → 流式回包 → 渲染 markdown
- 出题、采分点、follow-up 上下文延续
- 历史 / 报告 / 学情可见行为
- 答案/采分点提前泄露风险

### 公共 Web 入口
- 主页 `/`
- 登录 / 匿名状态判断
- 顶部 / 侧边导航可点性

### 关注问题清单（**未覆盖**，需要环境恢复后单独跑）
- 首屏 / 移动端遮挡、按钮不可点、文字溢出
- WebSocket / 流式输出失败、卡住、重复输出、乱码
- 出题后答案 / 采分点提前泄露
- 用户 follow-up 后上下文丢失
- 学情 / 报告数据：空 / 假满分 / 假进度 / 加载失败
- console error、network 4xx/5xx、hydration error
- 需要登录但状态不清楚

### 小程序侧（Web QA 物理不可覆盖）
- `wx_miniprogram/utils/ai-message-state.js` 有未提交改动（git status 显示 `M`）
- `wx_miniprogram/utils/render-schema.js` 有未提交改动
- 当前分支名 `fix/markdown-streaming-render-newline-loss` 强烈暗示问题域是**流式 markdown 渲染时换行丢失**——这是小程序里富文本渲染的高风险面
- **Web QA 工具无法覆盖小程序**，建议在微信开发者工具或真机回归：
  - 流式 token 落入渲染节点时换行/段落是否保留
  - markdown 末尾 token 未完成时是否出现 "粘连段"
  - 多轮回复混合出题 / 解析 / 普通文本时换行差异

---

## 下一轮建议测试范围（不修复，仅建议）

按优先级：

1. **环境前置（必须）**：
   - 终止当前 `:3000` 上的 `next-server` (PID 78117)，或在它的日志 `web/.next/dev/logs/next-development.log` 里捞 SSR 500 的真实堆栈
   - 启动 FastAPI 后端 `:8000`（项目惯用 `uvicorn deeptutor.api.app:app --reload --port 8000` 之类的入口，具体看 runbook，不在本报告 scope）
   - 在 `:3031` 起 web dev server（先确保 `:3000` 那个被回收，否则 Next 16 单例锁会再次拒绝）
   - 跑两个 curl 健康探针：`http://127.0.0.1:3031/wechat-harness` 应 200，`http://127.0.0.1:8000/api/v1/health` 应 200

2. **/wechat-harness 主链路（环境 OK 后第一刀切）**：
   - 桌面 1440x900 首屏 + 移动 375x812 首屏（截图）
   - WebSocket 连接 → 提问 → 流式回包 → markdown 换行（**对应当前分支主题**）
   - 出题流程：是否在用户答题前泄露答案/采分点
   - follow-up 一轮内上下文延续
   - 学情 / 报告 tab 数据真实性 vs 假满分

3. **公共 Web 入口（环境 OK 后第二刀切）**：
   - 主页 SSR 健康 + 导航可点
   - 登录 / 匿名状态边界
   - console error / network 4xx-5xx 全局扫一遍

4. **小程序回归（Web QA 不覆盖，单独走微信开发者工具）**：
   - 流式 markdown 换行回归（当前分支主题）
   - 出题 / 解析混排
   - 历史会话回放

---

## 测试方法学说明

- 所有信息仅来自 **浏览器 + curl + lsof + ps**，**没有读项目源码**。
- `web/.nvmrc=22` 但当前 shell `node v24.14.1`，**不作为根因**——`:3000` 上 next-server 已经成功 boot 到 listen 阶段，500 是请求时错。
- QA 进行中我**临时启动**了一个 :3031 上的 next dev 用于探活，几秒内被 Next 16 单例锁自动退出，未对仓库做任何写入，git working tree 与开始时一致（dirty 是用户已有状态）。
- 报告写完未对任何业务代码、配置、CI 做改动。
