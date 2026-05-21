# 2026-05-21 — DeepTutor 公共 Web 入口 QA-only 报告

> **测试线**: Public Web Auth + Navigation QA-only
> **时间**: 2026-05-21
> **基地址**: `http://127.0.0.1:3000`
> **模式**: QA-only (零代码修改、零提交、零环境改动)
> **报告范围**: 公共 Web 入口（Next.js dev server）所有 18 条路径 + 移动端布局 + console / network 健康
> **证据目录**: `.gstack/qa-reports/public-web-2026-05-21/`

---

## 1. Health Score

| 维度 | 评分 | 关键证据 |
|---|---|---|
| SSR 稳定性 | **10/10** | 18 个路径 0 个 5xx，0 个 21-byte ISE，最小 200 体积 17,304B (Next 404 fallback) |
| 鉴权边界清晰度 | **8/10** | 大部分受限页有明确 "暂不可用" 文案；折叠侧栏 Settings 图标过滤逻辑不一致 |
| 移动端布局 | **10/10** | 375×812 下 `/`, `/bi`, `/intro`, `/invite-test/apply` 无遮挡、无溢出 |
| Error UX | **6/10** | 4 个文档路径 404 (Next 默认页，不是白屏，但仍是死链)；FastAPI 离线导致 401 路径无法验证 |
| Console 卫生度 | **6/10** | 仅 HMR WebSocket 握手失败（dev 噪音），无 app 级错误 / hydration 错误 |
| 入口可发现性 | **5/10** | 4 个 QA 文档列出的路径不存在；侧栏匿名态强烈受限到 `/` + `/bi` |

**Composite Health: 8 / 10** — 公共 Web 入口在匿名态下表现稳健；剩余风险集中在 (a) 路径文档失同步与 (b) 后端 API 离线导致的鉴权链路无法端到端验证。

---

## 2. 关键发现速览

### ✅ 通过项
- **零 21-byte Internal Server Error**: 用户特别警惕的回归不存在。最小 200 响应是 27,383B (`/memory`)；所有 200 都是有完整 HTML 结构的 SSR 输出。
- **零应用级 5xx**: 18 个路径无任何 5xx 响应。
- **匿名态 UX 一致**: `/settings`, `/knowledge`, `/memory`, `/notebook`, `/agents`, `/co-writer`, `/guide` 全部用同一系列 "暂不可用 / 请使用已鉴权入口访问" 浅黄色提示卡（`RestrictedSurface` 组件），不会白屏。
- **移动端布局健康**: `/` 在 375×812 下 header=48px (top:0)，composer top=642 bottom=670，全部落在 vh=812 内，无重叠、无水平滚动。
- **BFF 入参校验工作正常**: `POST /api/invite-test/applications` 空 body 返回 `400 / 37B`，证明输入校验与错误返回都在工作。

### ⚠️ 主要问题
| 严重度 | 问题 | 影响 |
|---|---|---|
| P1 | `/chat`, `/learning-brain`, `/login` 三条路径不存在（Next.js 默认 404） | QA 文档/外链/书签会死链 |
| P2 | FastAPI (`:8001`) 未运行 | 无法验证真实 401 UI；本次 API 401 测试 BLOCKED |
| P2 | `/member` 用 `redirect()` 但 SSR 响应是 200 + Loading 骨架（非 307） | SEO 爬虫 / 监控工具看到 200 + 加载中文案，不会跟随重定向 |
| P3 | 折叠侧栏 `SECONDARY_NAV` 直接 map，未走 `visibleSecondaryNav` 过滤 (`SidebarShell.tsx:141`) | 匿名用户折叠侧栏会显示 Settings 图标，点进去是 "配置控制台暂不可用" |
| P3 | Next.js dev server HMR WebSocket 反复握手失败 (`ws://127.0.0.1:3000/_next/webpack-hmr` → `ERR_INVALID_HTTP_RESPONSE`) | 仅 dev 体验问题；不影响 prod |

---

## 3. 路径全表（curl 直采）

```
路径                            HTTP   Body 大小    备注
─────────────────────────────────────────────────────────
/                              200   92,338 B     Workspace chat composer（匿名态）
/intro                         200  119,972 B     Marketing landing
/chat                          404   17,304 B     ⚠ 路由不存在
/learning-brain                404   17,314 B     ⚠ 路由不存在
/settings                      200   27,402 B     RestrictedSurface "配置控制台暂不可用"
/login                         404   17,305 B     ⚠ 路由不存在
/wechat-harness                200  298,873 B     16 case + 实时流 / 最终态 / 历史 hydrate
/bi                            200   56,809 B     管理员登录 + "等待 BI 接口" 占位
/agents                        200   33,953 B     "TutorBot agents unavailable"
/co-writer                     200   33,909 B     "Co-writer unavailable"
/guide                         200   34,901 B     "Guide unavailable"
/member                        200   42,535 B     ⚠ Server redirect 但 HTTP 仍是 200
/knowledge                     200   27,633 B     "知识库工作台暂不可用"
/memory                        200   27,383 B     "记忆工作台暂不可用"
/notebook                      200   27,673 B     "Question notebook unavailable"
/playground                    200   33,960 B     "实验场 / 探索 DeepTutor 的核心模块..."
/invite-test                   200   44,962 B     内测申请 landing
/invite-test/apply             200   52,693 B     内测申请表
```

---

## 4. 问题详述（P 级）

### 4.1 P1 — `/chat`, `/learning-brain`, `/login` 路由不存在

**复现**:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/chat
# → 404
curl -s http://127.0.0.1:3000/chat | grep '<title>'
# → <title>404: This page could not be found.</title>
```

**证据**: `02-404-login.png`（Next.js 默认 404）

**根因**: `web/app/` 目录下没有 `chat/`, `learning-brain/`, `login/` 子目录。Web 端的聊天入口实际是 `/`（workspace 根），TutorBot chat 在 `/agents/[botId]/chat`；Learning Brain 在小程序端（`wx_miniprogram/`），Web 没有独立页面；项目走匿名首发策略，没有 `/login` 路径。

**Web 实际路由清单**（来自 `find web/app -name "page.tsx"`）:
```
(workspace)/page.tsx              → /
(workspace)/agents/page.tsx       → /agents
(workspace)/agents/[botId]/chat   → /agents/:botId/chat
(workspace)/bi/page.tsx           → /bi
(workspace)/co-writer/page.tsx    → /co-writer
(workspace)/guide/page.tsx        → /guide
(workspace)/member/page.tsx       → /member  (redirect)
(workspace)/playground/page.tsx   → /playground
(utility)/knowledge/page.tsx      → /knowledge
(utility)/memory/page.tsx         → /memory
(utility)/notebook/page.tsx       → /notebook
(utility)/settings/page.tsx       → /settings
intro/page.tsx                    → /intro
invite-test/page.tsx              → /invite-test
invite-test/apply/page.tsx        → /invite-test/apply
wechat-harness/page.tsx           → /wechat-harness
```

**建议**（不修复，仅记录）:
- 要么补建 `/chat` (alias 到 `/`)、`/learning-brain` (引导到小程序)、`/login` (展示鉴权入口说明)；
- 要么在 QA 文档与对外文档中明确："Web 公共入口只列出述清单内路径，`/chat /learning-brain /login` 不存在于 Web 端"。

---

### 4.2 P2 — FastAPI (`:8001`) 未运行，401 UI 边界测试 BLOCKED

**复现**:
```bash
lsof -i :8001 -sTCP:LISTEN
# → (空)
curl -s -o /dev/null -w "%{http_code}\n" --max-time 3 http://127.0.0.1:8001/health
# → 000 (connection refused, curl exit 7)
ps aux | grep -E "(uvicorn|fastapi|deeptutor)" | grep -v grep
# → 只有 web tmux dev session，没有 FastAPI 进程
```

**`web/.env.local` 实际配置**: `NEXT_PUBLIC_API_BASE=__CURRENT_ORIGIN__`，意味着客户端 API 调用会回落到 `http://127.0.0.1:3000` 自身，而 Next.js 只有 `/api/invite-test/applications` 一条 BFF 路由，其它 `/api/v1/...` 请求都会落到 Next.js 404。

**当前观察到的降级**:
- `/bi` 在 API 离线下不报错，UI 显示 "BOSS WORKBENCH > 加载中 1..5 / 等待 BI 接口" 占位卡片（见 `09-bi-desktop.png`）。**这是优雅降级**，不是白屏。
- 但因为后端不在，**无法验证**真正 401 路径（如 BI 管理员登录失败、过期 token、未授权 KB 操作等）的 UI 表现。

**未覆盖风险**:
- 后端返回 401 时 Web 是否会显示明确登录提示？是否会无限重试？是否会泄漏内部 token？— **本次无法回答**。
- 客户端 API 调用若同源 fallback 到 3000 后命中 Next 404 而非后端 401，错误展示是否会被用户混淆为 "页面不存在" 而非 "未授权"？— **本次无法回答**。

**建议**: 在下次 QA 之前确保 FastAPI 启动（按项目 runbook 跑 `uvicorn deeptutor.app:app --port 8001`），或在本次报告基础上单开一线测 401 路径。

---

### 4.3 P2 — `/member` SSR 行为：HTTP 200 + 加载骨架，而非 307

**复现**:
```bash
curl -s -I --max-time 5 http://127.0.0.1:3000/member | head -2
# HTTP/1.1 200 OK
# Vary: ...

curl -s -L --max-redirs 5 -o /dev/null -w "redirects=%{num_redirects}\n" http://127.0.0.1:3000/member
# → redirects=0  (curl 看不到 redirect)
```

**源码**: `web/app/(workspace)/member/page.tsx`:
```tsx
import { redirect } from "next/navigation";
export default function MemberPage() {
  redirect("/bi?tab=member-ops");
}
```

**实际行为**: 浏览器端能跟随到 `/bi?tab=member-ops`（RSC 流式重定向），但 SSR 直返 200 + `(workspace)/loading.tsx` 骨架。监控、curl、SEO 爬虫看到的是 "200 OK + Loading workspace" 而非 307。

**影响**:
- 监控可能误报 `/member` 为 "stuck on loading" 而非已废弃。
- SEO 爬虫不会更新到新路径。

**根因（已知 Next.js App Router 行为）**: Server Component 中 `redirect()` 对 RSC 请求返回 RSC payload，对 HTML/document 请求返回的并不是标准的 30x，而是依赖 client router 完成跳转。

---

### 4.4 P3 — 折叠侧栏 Settings 图标过滤逻辑不一致

**位置**: `web/components/sidebar/SidebarShell.tsx:140-156`

```tsx
const visibleSecondaryNav = SECONDARY_NAV.filter(() => authEnabled);   // 行 87 — 展开态用这个
// ...
{SECONDARY_NAV.map((item) => { /* 折叠态 */ })}                         // 行 141 — 没用过滤
```

**结果**: 匿名用户折叠侧栏后会看到 Settings 齿轮图标（不该出现），点击进入 `/settings` 才看到 "配置控制台暂不可用"。

**修复指引（仅记录）**: 折叠态 map 应改用 `visibleSecondaryNav`。

---

### 4.5 P3 — HMR WebSocket 反复握手失败（dev 噪音）

**console 样本**:
```
[error] WebSocket connection to 'ws://127.0.0.1:3000/_next/webpack-hmr?id=...' failed:
        Error during WebSocket handshake: net::ERR_INVALID_HTTP_RESPONSE
```

间隔 1s 重试，约 10 次后会成功并进入 `[HMR] connected` 状态。仅影响 dev server；生产构建不会有 webpack-hmr 端点。

---

## 5. "看似能用但实际无效" 检查

| 元素 | 状态 | 验证方法 |
|---|---|---|
| `/` 发送按钮 (`@e15`) | ✅ 明确 `disabled` | snapshot 显式标记 `[disabled]`，符合预期（没启用 KB 来源） |
| `/` 模型下拉 (`@e12`) | ✅ 明确 `disabled` | snapshot `[disabled]: 模型`，伴随 "请先启用知识库来源" 提示 |
| `/` Fast/Deep/工具/Reference 按钮 | ⚠ 未验证点击行为 | browse daemon 被并发线污染，无法稳定点击；建议单线复测 |
| `/bi` 刷新/导出 JSON 按钮 | ⚠ 未点击 | 后端离线时点击行为未知，建议单线 + 后端可用时复测 |
| `/bi` 管理员登录按钮 | ⚠ 未提交 | 后端离线，提交后预期会失败；UI 错误反馈未验证 |
| `/intro` "申请内测体验" CTA | ✅ HTML link → `/invite-test/apply` (200) | curl 跟踪 |
| `/invite-test/apply` 表单提交 | ✅ POST `/api/invite-test/applications` 空 body → 400 (37B) | BFF 校验生效 |

---

## 6. 截图证据清单

存放路径: `.gstack/qa-reports/public-web-2026-05-21/`

| 文件 | 说明 |
|---|---|
| `01-home-desktop.png` | `/` 桌面端（chat workspace，匿名态） |
| `01-home-intro-desktop.png` | `/intro` 桌面端（其它测试线遗留时的截图） |
| `02-404-login.png` | `/login` Next.js 默认 404 |
| `03-settings-desktop.png` | `/settings` "配置控制台暂不可用" |
| `04-wechat-harness-desktop.png` | `/wechat-harness` 桌面端（16 case 列表 + 闭环面板） |
| `05-home-mobile-375.png` | `/` 移动端 375×812 |
| `06-bi-mobile-375.png` | `/bi` 移动端 |
| `07-intro-mobile-375.png` | `/intro` 移动端 |
| `08-invite-apply-mobile-375.png` | `/invite-test/apply` 移动端 |
| `09-bi-desktop.png` | `/bi` 桌面端（管理员登录 + "等待 BI 接口" 占位） |

---

## 7. 未覆盖风险

1. **API 401 真实路径**: FastAPI 未运行，无法验证后端返回 401 时 Web 的 UI 表现（建议下次 QA 前先确保后端启动）。
2. **登录后状态**: 整次 QA 均在匿名态进行，未注入鉴权 token，已鉴权用户的页面表现未覆盖。
3. **交互点击链路**: browse daemon 与其它 QA 测试线并发，部分按钮点击行为未稳定验证（建议单线 + 串行复测 Fast/Deep/工具/Reference/刷新/导出 等交互按钮）。
4. **生产构建差异**: 本次跑在 `next dev`（带 HMR），未在 `next build && next start` 下复测，prod 与 dev 路由表理论上一致但 redirect 行为可能不同。
5. **国际化**: 没有切换语言验证（`/settings` 等限流面板使用 i18n key，未验证英文展示）。
6. **多 tab / refresh 行为**: 未测试多 tab 之间的状态同步与 `localStorage` 主题持久化（已验证 `deeptutor-theme:light` 写入）。

---

## 8. 测试方法 / 工具

- **HTTP 探测**: `curl -s -o /dev/null -w "%{http_code} %{size_download}"`
- **DOM/Console**: `gstack-browse` (Chromium daemon)，已知共享 daemon 与其它 QA 测试线，关键断言改用 curl 抓取以避免并发污染
- **路由静态分析**: `find web/app -name "page.tsx"` + 源码 `grep`
- **进程探测**: `lsof -iTCP -sTCP:LISTEN`, `ps aux`

---

## 9. 结论

公共 Web 入口在匿名态下整体健康。**用户原始诉求中最关键的 "不能再出现 21 字节 ISE" 已完全满足**：18 条路径下零 21 字节响应、零 5xx、所有 200 都有完整 SSR 体积（最小 27,383B）。

剩余三个待跟进项：
- **P1**: `/chat` `/learning-brain` `/login` 三条路径不存在于 Web — 需要决定补路由还是更新文档。
- **P2**: FastAPI 离线 — 阻塞了真实 401 UI 的端到端验证，下次 QA 前需先启 backend。
- **P2**: `/member` SSR 行为对监控/SEO 工具表现不直观。

其余 P3 项（折叠侧栏 Settings 图标、HMR 噪音）不影响产品发布。

> **本次仅 QA-only，未修改任何代码、配置、提交或环境状态。**
