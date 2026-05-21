# 2026-05-21 — QA Triage Rollup

| Field | Value |
|---|---|
| 日期 | 2026-05-21 |
| 模式 | **只读整理**（无 edit / commit / PR / 不修源码） |
| 目的 | 把当日多条 QA 测试线的发现聚合，识别共同根因、Web-only vs 小程序 vs 监控类问题、过时 QA target、必须真机复测的项 |
| 触发命令 | `/qa-only` triage by user |

---

## 0. 报告候选清单

| 报告 | 状态 | 用于 triage |
|---|---|---|
| `docs/qa/2026-05-21-public-web-auth-navigation-qa.md` | ✅ 存在 (14.4KB) | 是 |
| `docs/qa/2026-05-21-deeptutor-runtime-environment-blocked.md` | ⚠️ **未找到**（filesystem 搜索 0 命中） | — |
| `docs/qa/2026-05-21-wechat-harness-coverage-calibration.md` | ✅ 存在 (20.8KB) | 是 |
| `docs/qa/2026-05-21-wechat-harness-rerun.md` | ✅ 存在 (12.9KB) | 是 |

**关于缺失项**：用户指名的 `deeptutor-runtime-environment-blocked.md` 在 `docs/qa/` 下不存在。从内容主题判断，最接近的等价文件是同日 09:29 落盘的 `docs/qa/2026-05-21-wechat-harness.md`（10.4KB）——这是当日最早一份 QA，整篇都在记录 FastAPI :8000 down / Web :3000 SSR 500 / Next dev 单例锁等环境就绪问题。**本 rollup 在涉及 "FastAPI down" 主题时把 `wechat-harness.md` 作为该缺失报告的代理来源交叉引用，并在引用处明确标注**。如果 `deeptutor-runtime-environment-blocked.md` 是另一条尚未落盘的 QA 测试线的产物，可在它生成后重新跑 triage 把它并入。

---

## 1. 重复指向同一根因：FastAPI :8001 down

### 1.1 根因聚合

四份报告里有三份直接命中"FastAPI 后端不可达"这条线：

| 报告 | 描述 | 当时观察到的端口 / 状态 |
|---|---|---|
| `wechat-harness.md` (代理 *runtime-environment-blocked*) | **P0-3**：FastAPI 后端 `:8000` 没有运行；强烈怀疑也是 `:3000` 全站 SSR 500 的上游原因（SSR server component 调后端 ECONNREFUSED） | :8000 → 连接拒绝 |
| `wechat-harness-rerun.md` | **环境恢复纪录**：根因不是 :8000 而是 `:8001`；正确启动后 `:8001/api/v1/system/status` 返回 401（鉴权工作）；同时记录 `web/node_modules/micromark-core-commonmark/dev/lib/` 损坏是 SSR 500 的另一条线 | :8001 → 200 (启动后) |
| `public-web-auth-navigation-qa.md` | **P2**：FastAPI (`:8001`) 未运行；BLOCKED 真实 401 UI 边界测试 | :8001 → 连接拒绝（rerun 报告启的进程后续被关掉了） |
| `wechat-harness-coverage-calibration.md` | 间接：`wx_miniprogram/utils/endpoints.js` 多基地址 fallback `:8001 → :8012 → 远端`；coverage 矩阵 #12 标记"必须真机测" | — |

### 1.2 端口纠错（contract drift 之一）

`wechat-harness.md` 用了 `:8000`，`wechat-harness-rerun.md` 纠正为 `:8001`。**项目实际约定是 `:8001`**（见 rerun §2、`web/.env.local` 注释、`wx_miniprogram/utils/endpoints.js` fallback 顺序）。

凡是写"FastAPI :8000"的 QA target 都是过时的，应统一更新为 `:8001`。

### 1.3 启动失败的次因（独立工单）

`wechat-harness-rerun.md` §"环境恢复纪录" 记录了一个 dev workflow 痛点：
> `python -m deeptutor.api.run_server` 走 `uvicorn.run(..., reload=True)`，macOS 上 multiprocessing.spawn worker subprocess 在 import 阶段静默卡死（worker PID alive、CPU 0.0%、RSS 6MB、socket CLOSED）

绕过用 `uvicorn deeptutor.api.main:app --no-reload`。这是**为什么 FastAPI 反复 down**的真正根因——只要开发者用项目内置的 `run_server` 入口在 macOS 上启，就会卡死。**这是 dev workflow 工单，不是发布 blocker**。

### 1.4 triage 结论

| 项 | 优先级 | 归类 |
|---|---|---|
| FastAPI :8001 这一刻仍未运行 | P0（本地开发） / P1（CI） | **环境前置** — 不是产品 bug，但阻塞所有依赖后端的 QA |
| `:8000` vs `:8001` 端口约定混乱 | P2 | **文档 contract drift** — 修 README + QA brief |
| `run_server` reload 模式 worker spawn 卡死 (macOS) | P3 | **dev workflow 独立工单** — 不阻塞发布 |
| `web/node_modules/micromark-core-commonmark/dev/lib/` 损坏曾导致 21-byte ISE | P3 (已自愈) | **历史故障** — `npm ci` 已恢复；本次 public-web QA 重新探活 18 路径 0 个 21-byte ISE 确认未复现 |

---

## 2. Web-only 问题（不影响小程序 release）

这些问题影响 Next.js Web dev/prod，**不在小程序代码路径上**。

| # | 问题 | 报告来源 | 严重度 | 是否影响 release |
|---|---|---|---:|---|
| W1 | `/chat`、`/learning-brain`、`/login` 路由不存在（Next.js 默认 404） | public-web-auth §4.1 | P1→**重分类 P3** (见 §6 判断 1) | 否，是 QA target 过时 |
| W2 | `/member` Server Component `redirect()` 在 SSR 层表现为 200 + Loading 骨架，非 307 | public-web-auth §4.3 | P2→**重分类 P3** (见 §6 判断 3) | 否，仅监控/SEO 视角问题 |
| W3 | `SidebarShell.tsx:141` 折叠侧栏 `SECONDARY_NAV.map` 未走 `visibleSecondaryNav` 过滤，匿名用户折叠态看到 Settings 图标 | public-web-auth §4.4 | P3 | 否，1-line UI 过滤修复（见 §6 判断 2） |
| W4 | Turbopack dev mode `webpack-hmr` WebSocket 反复握手失败（dev noise） | public-web-auth §4.5 + wechat-harness-rerun §P3-2 | P3 | **否**（见 §6 判断 4） |
| W5 | 移动 375×812 下 `/wechat-harness` 主内容 DOM 未渲染（首屏 + 三次 scroll 截图全一致） | wechat-harness-rerun §P2-1 | P2 | 否，harness 是开发工具，不直接对学习者 |
| W6 | `/wechat-harness` 中 e16 case row 点击后 detail panel 未切换 | wechat-harness-rerun §P3-1 | P3 (未确认是 bug 还是 e15 默认 lock) | 否 |
| W7 | `/wechat-harness` "运行闭环" **不打真后端**，仅输出 client-side render model JSON | wechat-harness-rerun §P3-3 | P3（设计意图） | **不是 bug**，是 harness scope；但暗示 §3 中真后端流程必须另测 |

**Web-only 综合判断**：没有任何 P0/P1 阻塞 Web 发布。最值得修的是 W3（1-line fix）和 W5（移动端 harness DOM 缺失，影响开发者手机调试）。其余都是文档 / 监控 / dev noise 类。

---

## 3. 影响小程序 release 的问题

这些问题在 `wx_miniprogram/*` 代码路径或小程序运行时上，**Web QA 物理不可覆盖**。来源主要是 coverage-calibration 报告的覆盖矩阵 + 风险清单。

### 3.1 P0 — 商业敏感、必须真机回归

| # | 问题 | 来源 | 真机复测必要性 |
|---|---|---|---|
| M-P0-1 | **progressive_disclosure 答案泄露**：`sanitizeProgressiveDisclosure` 只在 `progressive_disclosure` 路径下脱敏；如果后端把 `correct_answer` / `scoring_points` 塞进 fallback markdown、MCQ option text、callout block，**当前 sanitize 拦不住** | coverage-calibration §4 风险 #3、§7 Gap-2 | **必须**：负面 fixture + 真机 + 抓包 grep `correct_answer\|scoring_points` |
| M-P0-2 | **DSML / 内部 token / tool call 泄露**：`INTERNAL_PATTERNS` (ai-message-state.js:8-15) 只匹配 6 种 pattern；未来新出现的内部 token 类型会漏 | coverage-calibration §4 风险 #6 | **必须**：真机 + 长会话压力测 |

这两项不解决，**单次截图就能毁掉信任**——商业风险大于功能风险。

### 3.2 P1 — 真实流式 / 鉴权 / 学情链路

| # | 问题 | 来源 | 真机复测必要性 |
|---|---|---|---|
| M-P1-1 | **WS reconnect + resume_from with seq**：网络抖动 / 后台前台切换时不丢 token、不重复 token | coverage-calibration §4 风险 #1、Gap-1 | **必须**：真机 + 飞行模式 / Wi-Fi 切换 |
| M-P1-2 | **流式 token 边界换行丢失**（当前分支 `fix/markdown-streaming-render-newline-loss` 主题） | coverage-calibration §4 风险 #2、Gap-3；wechat-harness.md "未覆盖" 段；rerun §"未覆盖风险" | **必须**：微信开发者工具 + 真机；Web harness 三帧 fixture 不够细 |
| M-P1-3 | **401 token 过期 → relaunch login → pending turn 不丢** | coverage-calibration §4 风险 #5 + #7 | **必须**：真机 + token TTL 桩 |
| M-P1-4 | **学情页假满分 / 假进度**：learning-report API 返回为空 / 错位时 UI 是否会"假满分"误导 | coverage-calibration §4 风险 #4；wechat-harness.md "未覆盖" 段 | **必须**：真后端 staging + 极端数据测 |

### 3.3 P2 — 多端差异 / 性能 / 商业化文案

| # | 问题 | 来源 | 真机复测必要性 |
|---|---|---|---|
| M-P2-1 | iOS / Android / devtools 三端 `_IS_DEVTOOLS` 分支不一致 | coverage-calibration §4 风险 #10 | 三端真机各跑一次 |
| M-P2-2 | wxml long list `setData` 卡顿（MAX_MESSAGES=200 单条多 blocks） | coverage-calibration §4 风险 #9 | 真机性能 baseline |
| M-P2-3 | wallet / quota / 503 FEATURE_DISABLED 文案被吞 | coverage-calibration §4 风险 #12 | mock backend + 真机 |
| M-P2-4 | citation 引用渲染（小程序 rich-text 节点 ↔ web 不一致） | coverage-calibration §4 风险 #11 | 真机视觉回归 |

### 3.4 P3 — 边缘场景

| # | 问题 | 来源 |
|---|---|---|
| M-P3-1 | 多基地址 `:8001 → :8012 → 远端` fallback 卡死 | coverage-calibration §4 风险 #8 |
| M-P3-2 | Hero 区域拖拽（HERO_MAX_DRAG_PX=84 / 阻尼 0.32 / 震动阈值 40） | coverage-calibration §4 风险 — Smoke 列里 |
| M-P3-3 | history tombstone（已删对话不再出现） | coverage-calibration §4 风险 |

### 3.5 Web Harness 的真实覆盖率

`wechat-harness-coverage-calibration.md` 量化了一个**反通胀**结论：

> Web harness `PARITY 16/16` 是**渲染契约层**的 100%，**用户场景层**只有 ≈ **18%**。
> 上一轮报告把 "PARITY 16/16" 当作端到端覆盖代表是高估，真实可信覆盖率 **15–25%**。

→ **重要 implication**：小程序 release 不能只看 harness 绿。**至少 §3.1–§3.4 中的 M-P0 / M-P1 必须真机或真后端验证**才能发车。

---

## 4. 过时 QA target / 文档 contract drift

| # | drift 项 | 当前 QA target / 文档 | 实际项目约定 | 来源 |
|---|---|---|---|---|
| D1 | Web 公共入口路径表 | QA brief 列了 `/chat`、`/learning-brain`、`/login` | Web 实际无这 3 个路由；聊天入口是 `/` (workspace) + `/agents/[botId]/chat` (鉴权后)；Learning Brain 在小程序端；项目走匿名首发，没有 `/login` | public-web-auth §4.1 |
| D2 | FastAPI 端口 | 部分 QA 文档写 `:8000` | 实际 `:8001`（rerun 报告纠正） | wechat-harness.md (用 :8000) → wechat-harness-rerun.md (纠正为 :8001) |
| D3 | Web dev 端口 | 用户指令一度用 `:3031` | 实际 `:3000`（rerun 报告纠正） | 同上 |
| D4 | "PARITY 16/16 = 端到端覆盖" 表述 | 历史 QA 报告把 harness PARITY 当作小程序整体覆盖 | 实际只覆盖渲染契约 18%（用户场景权重加权） | coverage-calibration §3 |
| D5 | `wechat-harness.md` Health Score 5/100 | 看起来像产品质量分 | 实际是环境就绪度分（报告里有声明但易误读）；rerun 后跳到 82/100 | wechat-harness.md → wechat-harness-rerun.md |

**triage 结论**：D1–D3 是**单点文档修正**，D4–D5 是**报告评分语义不一致**。建议为 QA brief 增加一段 "PARITY ≠ 端到端覆盖" 的固定声明，避免下次再被高估解读。

---

## 5. 必须真实微信开发者工具复测的项

把 §3 拍平成"真机/devtools 必跑清单"，对应 coverage-calibration §5 的 Smoke S1–S15：

| Smoke # | 场景 | 触发风险 (来自 §3) |
|---|---|---|
| S1 | 首次安装 + wxLogin + bindPhone | — |
| S2 | onShow 进聊天 + conversation list ≤ 1.5s | M-P2-2 |
| **S3** | 请求 5 道选择题 → 全程流式 → 最终 MCQ ×5 → grep payload 不含 `correct_answer` / `scoring_points` | **M-P0-1** |
| S4 | 流式中途切后台 30s → resume 不重新开 turn | M-P1-1 |
| **S5** | 飞行模式 5s 后自动重连 resume_from with seq | **M-P1-1** |
| **S6** | MCQ 答题：DOM inspector 确认 `grading_key` 不在 wxml 节点 | **M-P0-1** |
| S7 | follow-up "为什么 C 错" 上下文延续 | — |
| **S8** | 学情页 8D 雷达 / 章节掌握度 / 易错点 真数据非全 0 非全 100 | **M-P1-4** |
| S9 | Learning Brain projection current_truth / evidence_flow / next_training | M-P1-4 |
| **S10** | 401 token 过期 → relaunch → pending turn 不丢 | **M-P1-3** |
| S11 | 429 文案 + 升级按钮 | M-P2-3 |
| S12 | 503 FEATURE_DISABLED 灰显该功能不阻塞其他 | M-P2-3 |
| S13 | 5xx GET 自动重试 2 次 / POST 不重试 | — |
| S14 | 150+ 消息滚顶 setData ≥ 30fps | M-P2-2 |
| S15 | iOS + Android + devtools 三端同 fixture 节点树一致 | M-P2-1 |

**粗体 5 项**（S3 / S5 / S6 / S8 / S10）是 release 硬门槛——对应 M-P0 + M-P1 主线，**任何一项不过 release 应回退**。

---

## 6. 用户特别判断（4 个判断点）

### 判断 1: `/chat`、`/learning-brain`、`/login` 404 → **QA target 过时（不是产品 bug）**

**证据**：
- `find web/app -name "page.tsx"` 完整路由表里没这 3 个（public-web-auth §3）。
- `/chat` 真实对应路径：`/` (workspace 上的 ChatComposer) + `/agents/[botId]/chat` (鉴权后 TutorBot)。
- `/learning-brain` 是小程序专属页面 (`wx_miniprogram/pages/...`)，Web 无对应。
- `/login` 项目走匿名首发；鉴权由 BI / Settings 等触发的 admin login modal 承担（见 `/bi` 的 ADMIN ACCESS 区块），没有统一登录页。
- `/intro` 上所有 CTA 实证都指向 `/invite-test/apply`（public-web-auth §5 表），**没有外部链接指向这 3 个 404 路径**。

**判断**：
- **不是产品 bug**：Web 公共入口设计本来就不需要这 3 个路径。
- **是 QA target 过时**：QA brief 把小程序的页面名 / 通用 SaaS 习惯（`/login`）当成 Web 路径。
- **修法**：更新 QA brief + 任何外部文档（如 README、help center、marketing emails）里出现的这 3 个路径——但 grep 实证目前**没有任何外部 link 指向这 3 个 404**，所以仅 QA brief 一处需要改。

### 判断 2: `SidebarShell.tsx:141` 匿名 Settings 图标 → **可修复的小范围 Web bug**

**证据**：
- 位置精确：`web/components/sidebar/SidebarShell.tsx:141`
- diff 范围：**1 行**，`SECONDARY_NAV.map((item) => {...})` → `visibleSecondaryNav.map((item) => {...})`
- 风险：极低；不动鉴权逻辑、不改路由、不改可见性以外的渲染。
- 影响：匿名用户折叠态侧栏不再看到 Settings 齿轮（点进去看到 "配置控制台暂不可用" 的死链体验消失）。

**判断**：**是。可修复，1-line fix，建议归入下一次 sidebar 相关 PR 一并解决**。不是 P0/P1，但属于"修起来比留着便宜"的桶。

### 判断 3: `/member` Server Component redirect 200 skeleton → **监控/SEO 问题，非真实用户问题**

**证据**：
- 浏览器实测：跳到 `/bi?tab=member-ops`（RSC client-side router 完成）——public-web-auth §4.3。
- curl 实测：HTTP 200 + 0 redirects，body 是 `(workspace)/loading.tsx` 骨架。
- Next.js App Router 已知行为：Server Component 里 `redirect()` 对 RSC payload 走流式重定向，对 document GET 通过 client router 完成跳转——这不是 bug 是设计。

**真实用户视角**：几乎无影响（除非禁用 JS / RSS reader / 命令行客户端）。

**实际受影响**：
- Uptime 监控：会看到 200 OK + "Loading workspace"，误报 "卡死"。
- SEO 爬虫：不会更新 URL canonical。
- 内部 health-check 脚本：如果检测特定字符串可能误报。

**判断**：**主要是监控/SEO 问题**。如果目前项目暂无 Uptime monitor / SEO indexing 对 `/member` 有要求，**可 deprioritize**。若未来上 monitor，可改为：
- 把 `redirect()` 提到 middleware 层做 302
- 或直接删掉 `/member` 路由（既然要永久跳走，没必要保留 entry）

### 判断 4: HMR WebSocket failure → **仅 dev noise**

**证据**：
- 只在 `next dev` (Turbopack) 模式出现。
- 路径：`ws://127.0.0.1:3000/_next/webpack-hmr`。
- 真实 HMR 走 `[turbopack]_browser_dev_hmr-client` 路径（wechat-harness-rerun §P3-2 明确观察到）。
- prod build (`next build && next start`) 不包含 webpack-hmr endpoint。

**判断**：**仅 dev noise**。prod 用户不会看到。建议：
- 不阻塞 release。
- 如果想清理 dev 体验，可作为独立 backlog 项（next 16 + Turbopack 上游 issue，可能已有 fix）。
- **不要为此分配 P0/P1 工时**。

---

## 7. 综合优先级建议（按 release 决策粒度）

### Release 硬门槛（不通过则回退）

| 项 | 类型 | 责任方 |
|---|---|---|
| Smoke S3（答案不泄露 in MCQ + 流式） | 真机 + 抓包 | 小程序 QA |
| Smoke S5（飞行模式 5s resume） | 真机 | 小程序 QA |
| Smoke S6（DOM grep grading_key 不在 wxml） | 真机 | 小程序 QA |
| Smoke S8（学情页非全 0 非全 100） | 真后端 + 真机 | 小程序 QA + backend |
| Smoke S10（401 + pending turn 不丢） | 真机 | 小程序 QA |

### 应修但不阻塞（下一个迭代窗口）

| 项 | 来源 | 改动量 |
|---|---|---|
| `SidebarShell.tsx:141` collapsed sidebar 过滤一致性 | W3 | 1 行 |
| QA brief 删除 `/chat` `/learning-brain` `/login`，加 PARITY ≠ 端到端覆盖声明 | D1 / D4 | 文档 |
| README + 任何 internal runbook 把 FastAPI 端口统一为 `:8001` | D2 | 文档 |
| 把 `ws-stream.js` 纯函数下沉到 `tests/contracts/` | coverage-calibration Gap-1 | ~300 LOC |
| 加 progressive_disclosure 负面 fixture | coverage-calibration Gap-2 | ~150 LOC fixture |
| 流式 token 边界细粒度 fixture（当前分支主题） | coverage-calibration Gap-3 | ~280 LOC |

### 独立工单（不影响发布）

| 项 | 来源 |
|---|---|
| `python -m deeptutor.api.run_server` reload-mode worker spawn 卡死 (macOS) | wechat-harness-rerun §"环境恢复纪录" |
| Turbopack HMR webpack-hmr 端点 noise | W4 |
| `/member` SSR 行为对监控/SEO 的优化（若有需求） | W2 / 判断 3 |
| `/wechat-harness` 移动端主内容缺失（开发者手机调试痛点） | W5 |

---

## 8. 没动什么

- ❌ 不修源码、不改测试、不改配置、不改依赖
- ❌ 不 commit / stash / reset / clean / 不开 PR / 不切分支
- ❌ 不重启 / 不 kill 任何进程
- ❌ 不 npm install / npm ci
- ✅ 只 Read 了上面列出的 3 份 QA 报告 + 用 `find` 验证缺失项 + 用 `grep` 交叉引用 `wechat-harness.md` 主题
- ✅ 本 triage 写到 `docs/qa/2026-05-21-qa-triage-rollup.md`

---

## 9. 待补充

如果 `docs/qa/2026-05-21-deeptutor-runtime-environment-blocked.md` 是另一条 QA 测试线正在产出的报告，请在它落盘后告知，把它单独合入本 triage 的 §1（FastAPI down 根因聚合）和 §4（contract drift 端口约定）即可，其它结构无需重排。
