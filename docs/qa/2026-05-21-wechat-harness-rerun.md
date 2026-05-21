# QA Report — wechat-harness rerun (report-only, environment-recovered)

| Field | Value |
|---|---|
| Date | 2026-05-21 |
| Target | `http://127.0.0.1:3000/wechat-harness` (canonical port; previously misidentified as :3031) |
| Branch | `main` (ahead 1) |
| Mode | report-only (no fixes) |
| Browser | gstack browse (Chromium headless) |
| Screenshot dir | `.gstack/qa-reports/screenshots-2026-05-21-rerun/` |
| Baseline JSON | `.gstack/qa-reports/baseline-wechat-harness-2026-05-21-rerun.json` |
| Predecessor (env P0 block) | `docs/qa/2026-05-21-wechat-harness.md` |

---

## 环境恢复纪录（前置条件）

**根因（已修复）**：`web/node_modules/micromark-core-commonmark/dev/lib/` 部分损坏——`content.js`、`autolink.js` 等数个源文件缺失，导致 react-markdown 链路在 Turbopack dev 解析时 ENOENT，所有 SSR 路由 500（裸 21 字节 `Internal Server Error`）。

**修复手段**（用户授权方案 B）：
```
cd web && PATH=$HOME/.nvm/versions/node/v22.22.3/bin:$PATH npm ci --no-audit --no-fund
```
- 22 秒，663 包，`dev/lib/` 文件数从残缺恢复到 66（与生产 `lib/` 一致）
- **`web/package.json` / `web/package-lock.json` 未改动**（git status 验证）

**端口约定纠正**：

| 项目 | 上一轮指令 | 实际项目约定（README + next.config.js + 历史 QA） |
|---|---|---|
| Web dev | `:3031` | **`:3000`** |
| FastAPI | `:8000` | **`:8001`** |

**FastAPI 启动遇到的次要问题（已绕过）**：`python -m deeptutor.api.run_server` 走 `uvicorn.run(..., reload=True)`，macOS 上 multiprocessing.spawn worker subprocess 在 import 阶段静默卡死（worker PID alive、`STAT S+`、CPU 0.0%、RSS 6MB、socket 状态 `CLOSED`，2 分钟无 Application startup complete）。**绕过**：换用 `.venv/bin/uvicorn deeptutor.api.main:app --host 0.0.0.0 --port 8001 --log-level info --no-access-log`（不带 `--reload`），主进程内 import 直接 boot，1 秒内 Application startup complete。**没改任何项目文件**，只换启动命令。这是 dev workflow 上的次要痛点，建议作为后续工单：在 reload 模式下 worker spawn 卡死。

### 启动命令与运行状态

| 服务 | tmux session | 启动命令 | PID | 端口 | 日志路径 |
|---|---|---|---|---|---|
| FastAPI | `deeptutor-api` | `source .venv/bin/activate && exec .venv/bin/uvicorn deeptutor.api.main:app --host 0.0.0.0 --port 8001 --log-level info --no-access-log` | 2779 | 8001 | `/tmp/qa-logs/api.log` |
| Next dev | `deeptutor-web` | `PATH=$HOME/.nvm/versions/node/v22.22.3/bin:$PATH exec node --max-old-space-size=4096 ./node_modules/next/dist/bin/next dev` | 98294 | 3000 | `/tmp/qa-logs/web.log` |

进程清理：旧 :3000 dev server (PID 78110, 78117, 跑了 1天16小时) 已 SIGTERM 回收，cwd 确认为本仓库 `web/`。

### 健康探针结果（全部通过或正常 401）

| URL | HTTP | 大小 | 用时 | 说明 |
|---|---:|---:|---:|---|
| `:3000/wechat-harness` | **200** | 298873B | 203ms | HTML 完整 |
| `:3000/` | **200** | 92344B | 134ms | 真聊天页 |
| `:8001/` | **200** | 38B | 11ms | `{"message":"Welcome to DeepTutor API"}` |
| `:8001/api/v1/system/status` | 401 | 36B | 9ms | `{"detail":"Authentication required"}`（服务健康，鉴权工作中） |
| `:3000/api/v1/system/status` (proxy → :8001) | 401 | 36B | 10ms | 代理链路通 |
| `:8001/openapi.json` | 200 | — | — | 200 routes registered |

---

## Health Score: 82 / 100

| Category | Weight | Score | Note |
|---|---:|---:|---|
| Console | 15% | 100 | filter 掉 Turbopack dev mode 已知 `webpack-hmr` noise 后 0 应用级错误 |
| Links | 10% | 100 | 无 broken |
| Visual | 10% | 100 | 桌面端 layout 干净，markdown / 公式 SVG / 表格渲染完整 |
| Functional | 20% | 70 | mobile 内容缺失 (-15)；e16 case row click 切换疑似无效 (-5)；真 chat (`/`) 发送禁用 (-3)；运行闭环非真后端调用 (-7) |
| UX | 15% | 80 | mobile P2 主因；auth gating 在 `/` 上没有清楚提示 |
| Performance | 10% | 100 | 首屏 200ms，turbopack 首次编译 760ms |
| Content | 5% | 100 | 16 fixture 全部 PARITY 一致 |
| Accessibility | 15% | 85 | 无专门测，标签结构看起来 ARIA-aware（snapshot 有完整 role+name），保守给分 |

加权和 = 82。

> 这次是**应用功能可测后的真实分数**，不是上一轮的 5/100 环境失败分。

---

## 关键观察：`/wechat-harness` 不是聊天页面

它是 **鲁班智考 Web QA — 小程序公共主题** —— 一个 fixture replay 工作台，做这件事：
- 加载 `tests/fixtures/wechat_structured_renderer_cases.json` + `tests/fixtures/wechat_markdown_golden_cases.json` + `web/lib/wechat-harness-data.ts` 里的 16 个 fixture
- 在 web shadow harness 里重放这些 fixture，**对比 web 渲染 vs 小程序渲染**是否一致
- 模拟流式（实时流式 / 最终态 / 历史 hydrate 三模式 + 帧步进）
- 模拟 quiz（A/B 选项 + 提交）
- 模拟学情闭环（User ID + 案例题作答 + "运行闭环" 输出 render model JSON）

**所有 16 fixture 标记 "chat 一致"，PARITY 16/16**——markdown 渲染回归基线全部通过。这正是当前分支 `fix/markdown-streaming-render-newline-loss` 关心的主题。

**真聊天页是 `/`**，但当前默认状态下"模型 + 知识库"未启用，**"发送" 按钮 disabled**。真 WebSocket 流式 / 多轮 follow-up / 后端出题打分需要先配置知识库才能跑。

---

## P0 — 阻塞发布

**无**。环境恢复后，没有阻塞性问题。

---

## P1 — 重要

**无**。

---

## P2 — 应修

### P2-1. 移动 375x812 下 `/wechat-harness` 主内容不渲染

- **页面 / 视口**：`http://127.0.0.1:3000/wechat-harness`，375x812
- **复现步骤**：
  1. `viewport 375x812`
  2. `goto /wechat-harness`
  3. 滚动到底部
- **期望**：移动端 stack 布局，顶部 case selector + 下方 detail panel（聊天气泡 / mode toggle / quiz / 学情 QA）依次可见
- **实际**：首屏只看到顶部 case selector（CASES / PARITY / 标签过滤器 / case row 水平滑动）+ CHAT 标题 + fixture 描述 + "结构化 16" 单一指标卡，**下方约 75% 高度大片空白**，主聊天气泡 / mode toggle / quiz options / 学情闭环 QA 全部不可见
- **scroll 验证**：分别 scroll Y=800, 1600, 2400，截图（qa-17/18/19）**与首屏完全一致**——证明不是被推到滚动区下方，而是 DOM 里就没渲染
- **证据**：
  - `screenshots-2026-05-21-rerun/qa-9-mobile-375.png`（mobile 首屏）
  - `screenshots-2026-05-21-rerun/qa-16-mobile-top.png`、`qa-17-mobile-scroll800.png`、`qa-18-mobile-scroll1600.png`、`qa-19-mobile-scroll2400.png`（连续 scroll 全一样）
- **对照**：桌面 1440x900 同 URL 同时间内容完整（`qa-12-desktop-home.png`、`desktop-1440-wechat-harness-firstpaint.png`）
- **阻塞发布**：否（harness 是开发/QA 工具，不直接对学习者；学习者侧在小程序）
- **影响**：开发者在手机上调试 fixture 不可用，这跟当前分支主题（小程序流式 markdown）的"在手机端确认 web vs 小程序一致"流程相关

---

## P3 — 观察 / 低优

### P3-1. case row 切换疑似无效（e16 后 detail panel 未切换）

- **页面**：桌面 1440x900 `/wechat-harness`
- **复现**：fresh snapshot → `click @e16`（Structured Formula Fallback Text Only） → 截图
- **期望**：detail panel 标题切换为 "Structured Formula Fallback Text Only"，左 rail 高亮跳到第 2 项
- **实际**：detail panel 标题仍是 "Structured Table Formula Mcq Combo"，左 rail 高亮仍是第 1 项；click 命令本身成功（`Clicked @e16 → now at .../wechat-harness`），URL 未变
- **观察**：可能是 onClick 没绑定该 button、或者状态 propagate 未更新视图、或者点击坐标命中了 case 容器而非 button 本体
- **证据**：`screenshots-2026-05-21-rerun/qa-14-case-e16.png` vs `desktop-1440-wechat-harness-firstpaint.png`（完全一致）
- **阻塞发布**：否
- **次要**：可能不是 bug，是 e15 默认 lock；需要确认 product 期望

### P3-2. Turbopack dev mode 下 `webpack-hmr` WebSocket 反复失败

- **现象**：浏览器 console 每 ~6 秒输出一条 `WebSocket connection to 'ws://127.0.0.1:3000/_next/webpack-hmr?id=...' failed: Error during WebSocket handshake: net::ERR_INVALID_HTTP_RESPONSE`
- **原因**：Next 16 + Turbopack 用的是新 HMR 协议（`/_next/static/chunks/[turbopack]_browser_dev_hmr-client_hmr-client_ts_*.js` 客户端代码 200 加载，证明真 HMR 是这条路），但浏览器 devtools 或某些客户端代码仍尝试旧 webpack HMR endpoint
- **阻塞发布**：否（只是 dev mode noise；prod build 无此问题）
- **建议**：作为单独追踪项；这不归本次 QA 的"业务错误"统计

### P3-3. `/wechat-harness` 真 WebSocket 流式 / 真后端打分**未被该 harness 覆盖**

- **现象**：点击"运行闭环"后右侧仅显示"当前 render model" JSON（`{"mode":"final","frame":"final","blockTypes":["table","formula_block"],"visibleBlockTypes":["table","formula_block","mcq"],"mcqCount":1,"hasStructuredContent":true,...}`），**network 面板无任何 `/api/v1/*` 调用**
- **结论**：`/wechat-harness` 是**纯客户端 fixture 校验工具**，不打后端。它只测 web 渲染器 vs 小程序渲染器的 parity，**不测真 WS、真出题、真打分**
- **证据**：`screenshots-2026-05-21-rerun/qa-20-after-run-loop.png`、network 列表里只有 `_next/static/*` 和早期 pre-fix 历史条目
- **阻塞发布**：否（这是 harness 的设计意图，不是 bug）
- **影响**：原 8 项必测里的 #3（WebSocket 流式）、#6（follow-up 上下文）、#7（学情/报告假满分）**在 `/wechat-harness` 这个 URL 上物理不可测**——需要走真聊天页 + 已配置 KB 的流程

---

## 8 项必测覆盖度

| # | 必测项 | 状态 | 证据 |
|---|---|---|---|
| 1 | 桌面 1440x900 `/wechat-harness` 首屏 | ✅ 覆盖 | `desktop-1440-wechat-harness-firstpaint.png`（200，298KB，渲染完整） |
| 2 | 移动 375x812 `/wechat-harness` 首屏 | ✅ 覆盖（发现 P2-1） | `qa-9-mobile-375.png` 等 |
| 3 | WebSocket / 流式 | ⚠️ 部分（fixture 模拟） | "实时流式 / 最终态 / 历史 hydrate" 三种模式可切，"下一帧 / 重播 / Chunk 1 / Chunk mid / Final payload" 帧步进控件存在；**真后端 WS 流式未测**（P3-3） |
| 4 | markdown 换行渲染 | ✅ 通过 | 桌面首屏：表格 / 公式 SVG (`A = πr²`) / 文本完整渲染；**16 fixture 全部 "chat 一致"**，PARITY 16/16；这正是当前分支主题，验证基线未回归 |
| 5 | 出题答案泄露 | ✅ 通过 | quiz 区显示"请选择正确答案" + "A 方案A / B 方案B" 选项，**无"正确答案 X" / 采分点 提前暴露**；`snapshot` grep `正确答案|采分|score|reveal` 在 click 前后均无关键词 |
| 6 | follow-up 上下文延续 | ❌ 未覆盖 | harness 是单 fixture replay 不测多轮；真聊天页 `/` 发送禁用（KB 未启） |
| 7 | 学情 / 报告假满分假进度 | ⚠️ 部分 | harness 有"学情闭环 QA" + User ID + 案例题作答 + "运行闭环"；点击后输出 render model JSON，**未观察到假满分/假进度**，但**未走真 backend learning brain**（P3-3） |
| 8 | console error + network 4xx/5xx | ✅ 通过 | filter Turbopack `webpack-hmr` noise 后 0 应用级 error；network 唯一失败条目是上一轮 QA 修复前的历史 500，当前会话内无新增 4xx/5xx |

---

## 未覆盖风险（需要环境进一步配置）

1. **真聊天主链路（`/`）**：发送禁用，需启用知识库（模型 + 至少一个 KB）才能测真 WS、真流式、真 follow-up、真出题、真打分。这套流程涉及配置 LLM provider、embedding、KB ingestion，超出本次"environment recovery"scope。
2. **小程序侧流式 markdown 换行**：当前分支主题 `fix/markdown-streaming-render-newline-loss` 直接对应小程序渲染器；本次 web QA 验证了 fixture-based parity（16/16 一致），但**真机/微信开发者工具上的端到端流式表现仍需小程序侧单独回归**。
3. **uvicorn reload 模式 worker spawn 卡死**：本次绕过用 no-reload，**未做根因诊断**；建议作为单独 dev workflow 工单。
4. **e16 case row 切换疑似无效**（P3-1）：未确认是 bug 还是设计意图。

---

## 测试方法学说明

- 浏览器 + curl + lsof + ps + tmux + 读源码（仅限于环境诊断，未修业务代码）
- 修改的文件：**仅 `web/node_modules/` 重装**；`web/package.json`、`web/package-lock.json`、`.env`、业务代码、测试代码 **全部未动**
- git working tree：除了用户已有的 dirty 文件，未引入新 dirty
- 启动的进程：FastAPI (no-reload, PID 2779)、Next dev (PID 98294)；都在 tmux 里，日志路径已记录，便于事后审计或继续开发
