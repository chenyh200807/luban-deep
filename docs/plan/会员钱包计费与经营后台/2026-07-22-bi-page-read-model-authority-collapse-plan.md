# BI v2 页面读模型收权与会员 360 根治计划

状态：Implemented locally · PR pending（2026-07-22）
主线：`2026-05-23-luban-bi-member-growth-backoffice-ui-ux-plan.md` 的根因修复，不新建 BI 产品概念。

## 1. 决策结论

本轮不是视觉微调。共同根因是：页面缺少一个带可用性状态的 canonical read snapshot，前端因而并发拼接昂贵读取，并把延迟、失败或缺失证据自行解释为 0、暂无或精确业务事实。

唯一事实链：底层 authority → 既有 fat service read model → `available / stale / insufficient_evidence` → thin renderer。禁止新增第二套 BI cache、router 或前端估算 authority。

## 2. 已确认根因

1. 总览同时请求 overview、trend、anomalies，每个入口重复扫描同一上下文；一次页面访问接近 15 组底层扫描。
2. 内部账号快照曾发起两次最长 8 秒的同步 Supabase 请求并阻塞事件循环。
3. 会员 360 的详情和行为串行读取，快速 A→B 会被 A 的迟到响应覆盖；失败被改写成“暂无”。
4. 会员表把 `created_at` 冒充首充、`review_due` 冒充备注数、反馈数硬编码 0、分类风险冒充精确小数。
5. 订单收入 authority 未接入，但前端把金额证据不足渲染成 `¥0`。
6. 反馈中心挂载即加载三套工作台；BI 又继承聊天工作区 provider 与加载文案。

## 3. 最小实施边界

- overview 内复用同一 `_BiContext` 生成趋势；BI v2 首屏只读一次 overview。
- 内部账号从一批审计行派生状态和列表，远程同步 IO 移出 event loop；会员 overview 使用同一排除集。
- 会员 360 并行取详情和 engagement，以 request identity 丢弃陈旧响应；loading、error、empty 分开。
- 删除无 authority 的会员伪字段；未知不再转成 trial、0 或 not_started。
- 账务只展示钱包账本已确认的人工实收；证据不足显示待确认。
- 反馈按当前 workspace 首次进入再取；BI 使用独立业务加载态。

不改 TutorBot、WebSocket、支付写链、会员写 authority，不新增顶层导航与 schema。

## 4. Pass criteria

- overview 单次调用 `_load_context == 1`；刷新失败保留 last-known-good，不闪 0。
- 内部账号快照单次远程 GET，慢 IO 期间 event loop 继续 tick。
- 会员 overview 明确携带内部账号 authority availability，并排除当前 internal user IDs。
- A→B 快速切换最终只显示 B；详情/行为任一失败显示独立错误。
- 源码中不再存在 `created_at→首充`、`review_due→备注数`、反馈数硬编码 0、风险精确小数映射。
- 金额缺失的充值事件不得显示 `¥0`；只显示“待确认”。
- feedback 首屏只读取当前 workspace；BI 不挂载 chat provider。
- 相关 Python/Node tests、typecheck、contract guard、浏览器三入口回归通过。

## 5. 红线、false progress 与剩余不确定性

- 只加前端缓存但保留服务端重复扫描，不算性能修复。
- 只把 `¥0` 改成破折号但不传 revenue status，不算 truth 修复。
- 只并行会员 360 请求但没有 stale-response guard，仍可能串户。
- 本地代码与 `test2` 部署版本可能 drift；PR 合并前只能验证源码与测试，live closure 必须记录部署 SHA 后复测。
- 在线支付订单 authority 仍是 pending；本轮只保证诚实展示，不虚构收入闭环。

## 6. Owner 与交付

- Backend owner：`BIService` / `MemberConsoleService` 单一读模型与测试。
- Frontend owner：BI v2 thin renderer、会员 360 状态机与浏览器回归。
- Release owner：PR → main 后记录 merge SHA、部署 SHA，再执行 test2 live 验收；部署前不得宣称已上线。

## 7. 2026-07-25 续轮：执行模型与快照时刻（本计划的下半程）

本轮不是新主线，是第 3、4 节的补完。上一轮立的是「读模型**怎么算**」的单一权威，
没有立「**算几次 / 存在哪 / 能多旧**」的权威，因此收权之后成本仍随消费者数量线性增长
（`_load_all_members` 调用点由 3 涨到 8 即是判决性证据）。

### 7.1 本轮完成（全部零新鲜度语义变化）

- **执行模型**：`_load_context_since` 降为同步 `def`（实测 awaits=0，纯删减），
  `_load_business_context` 成为**context 路径**的 `asyncio.to_thread` 边界（与 `sqlite_store._run_read`
  同范式）；`get_overview` 的会员快照、`get_commerce` 全方法一并离开事件循环。
  **注意这不是「全 BI 的唯一边界」**——全仓 `to_thread` 共 9 处（本轮新增 5 处），
  且 `get_overview` 自身仍有阻塞 IO 留在循环上，见 §7.4。
- **补完病B-4**：`bi.py:/member/dashboard` 与 `member.py:/dashboard` 降同步 `def`——
  2026-07-05 那轮只改了 mobile 三条，这两条调同一个 3–5s 的 `get_dashboard` 却被漏下。
  守卫 `tests/api/test_mobile_event_loop_discipline.py` 泛化为 `(router, path)` 映射，
  成为事件循环纪律的唯一权威；BI 那半用行为断言（执行期间事件循环必须继续 tick）。
- **物理物化**：`turn_events(type, created_at DESC)` 与 `turns(created_at DESC)` 索引。
  实测（SQL 从源码 AST 提取、fresh connection）：整条 `_load_context_since` 的 SQL
  **17.10ms → 0.66ms**，其中 `turn_events` 两条 8.28/8.20ms → 0.11/0.04ms。
- **会员池派生收权**：`get_overview` / `get_member_stats` / `get_commerce` 过去各写一遍
  「取会员 + 过滤 registered」，收敛为单一 `_registered_members_snapshot`，
  重算判断点 **3 → 1**。
- **快照时刻接线**：后端 `generated_at` 此前在前端整条链是断的——类型无字段、builder 不读、
  面板用 `Date.now()` 现编却标注「实时数据」。这违反 §1「禁止前端估算 authority」，
  且使任何缓存都无法验证。现已接通，缺失时显式显示「快照时刻未知」。
- 传输轴（与读模型正交）：ECharts 改按需注册，brotli 309,807 → 173,732（−43.9%）。
- 传输轴补轮（PR #564 合并后）：`BiV2MemberOpsPanel` 改 `dynamic()`。它是 `BiV2Surface`
  里唯一还静态 import 的 panel（其余 6 个早已是 dynamic），而默认落地区是 overview，
  于是这 3,866 行 TSX（panel 2,550 + Member360Drawer 747 + ConversationReviewDrawer 569）
  被无条件放进 shell。实测确认它**不含** echarts（`MemberOpsCockpit` 自身已是 dynamic），
  所以省下的是纯 TSX 体积。

### 7.2 本轮未做，且**必须先由 owner 拍板**

会员快照与 `_BiContext` 的物化（TTL + 文件 mtime 双失效信号）**未实施**。
它是单请求延迟的大头（会员链每次 3~12 次同步 Supabase 往返），但它改变一件
owner 可感知的事：**BI 读数可以陈旧到 60 秒**。判例是 §1 已对「谁算内部账号」
接受了同样的 60s，但那是既有决定，不构成本轮的自动授权。

放行条件（缺一不可）：① 物化必须同时输出快照时刻——7.1 的接线已使其可行；
② 失效必须同时接受 TTL 与 `member_console.json` 的 mtime（只 TTL 则运营改完等 60s，
只 mtime 则 Supabase 侧变更永不可见）；③ 失败必须 fail-open 且自报 `stale`，
不得沿用现状把目录故障洗白成「0 个会员」。

**④ 必须先修 `packages_changed` 恒真——这是本轮实测出的前置阻塞，也是一个独立的现存缺陷。**

`_load_unlocked`（`member_console/service.py`）在 `packages_changed` 为真时于**读路径**调
`_save_unlocked`。用生产快照实测（`md5=a40f905…`）：`_normalize_package_catalog` 把磁盘上
`starter_19.teaching_video_limit` 的 `30` 规范化成 `None`，两者永不相等 ⇒ **条件恒真**。

后果有三层，依次加重：
1. 每个 BI / member dashboard 请求都做一次全量 `json.dumps(indent=2)`（实测 11ms）+ `os.fsync`；
2. 该写盘**全程持 `LOCK_EX`**，是跨 worker 的串行化点（生产 `UVICORN_WORKERS=2`）；
3. 它每次都改 mtime，因此**上面 ②的 mtime 失效信号会永远命中失效分支，缓存等于没加**。

不可顺手改：`teaching_video_limit` 是计费权益字段（30 / null 决定教学视频额度），
磁盘值与规范化结果分歧属于数据-代码分歧，改哪一边都要 owner 按计费口径拍板，
误改是资损。故本轮只留证据，不动代码。

### 7.3 本轮明确不做

BI v1（`BiPageClient` 及其 `loadBiWorkbench` 的 8× 同参放大、8 个无 debounce 输入）——
线上 `BI_BACKOFFICE_V2_SHELL_ENABLED` 已开，v1 是死路径，改它属超范围。
`directory.py` 的 `in.(...)` URL 长度墙（会员数约 250~450 触发 414）是正确性悬崖不是性能问题，
应单独立项。全仓 222 个零 await handler 的体检同理。

### 7.4 对抗性 review 发现、本轮未修（下一轮的输入）

本轮的对抗性 review 给出 1 BLOCKER + 6 MAJOR。BLOCKER（`generated_at` 读错对象导致 §7.1 第 4 条
形同虚设）与两条 MAJOR（无用的 `turns(updated_at)` 索引、被夸大 18 倍的性能数字）已在本轮修掉。
以下四条留给下一轮，都不是本轮改动引入的回归，而是**收口未完成的部分**：

1. **`get_overview` 自身仍有 4 处阻塞 IO 在事件循环上**：两次 usage-ledger 读、
   经 `get_non_business_identity_ids` 的会员目录取数、一次文件读。它们在
   `_load_business_context` 边界之外，而本轮的行为守卫孤立调用
   `_load_business_context`、从不调 `get_overview`，**结构上看不见它们**。
   下一轮应让守卫直接打 `get_overview`。
2. **`asyncio.to_thread` 用的是事件循环默认 executor，与 `sqlite_store._run_read` 同一个池**
   （22 workers）。BI 的长扫描会占住一个 slot，TutorBot 的 session 读排在它后面
   ——比阻塞循环好，但是**部分位移而非隔离**。代码库已有专用 executor 的样板
   （`sqlite_store.py` 的 writer executor），下一轮按它接。
3. **`member.py` 的 `list_members` 裸调，而 `bi.py` 同一方法已包 `to_thread`**：
   本轮修的那对不对称，隔一个路由还活着。根因是修法与守卫都按**手工维护的 path 白名单**
   匹配，而非按不变量匹配；真正的收口需要按「调用了哪些已知阻塞方法」判定。

4. **`page.tsx` 把 BI v1 与 v2 两套都静态 import**（`BiPageClient` + `BiV2Surface`），
   由服务端 flag 二选一渲染。App Router 只为 RSC payload 实际引用到的 client reference
   发 script，所以浏览器**很可能不会**下载没被渲染的那一支——但两套都进
   client-reference-manifest，而 `route_budgets.mjs` 是按 manifest 求和的，
   于是 `/bi` 的预算把两套都算了进去。**这条不要照推断改**：需要一次
   `next build` + DevTools network 定论浏览器到底下不下载 v1，再决定是否把不走的那支
   改成 `dynamic()`。（受内存护栏约束，本地不跑 build。）

5. **性能预算门结构上不可能 FAIL —— 它比「`/bi` 没登记」严重得多。**
   `route_budgets.mjs:158` 的判定是
   `budget && row.comparableBudget && sizeKb > budget ? "FAIL" : "OK"`，
   而 `comparableBudget`（:111）= `manifest.entryJSFiles` 存在与否 —— 那是 **Turbopack**
   的 client-reference-manifest 字段。项目的 `npm run build` 是 `next build --webpack`，
   webpack manifest 没有该字段 ⇒ `comparableBudget` **恒 false** ⇒ **status 恒 OK**。
   CI 日志里的铁证：`OK /settings 364KB / budget 180KB (estimated webpack)` —— 超预算
   一倍仍然 OK；那句 "(estimated webpack)" 就是脚本自己在声明"这个数字不可比"。
   ⇒ 所以「把 `/bi` 加进 `ROUTE_BUDGETS_KB`」**并不能**让门生效，登记了也照样恒绿。
   这是 dormant authority 的教科书形态：门接在 CI 上、每次都跑、每次都绿、
   结构上永远拦不住任何东西。修它要先决定量测口径（改用 turbopack 构建取真值，
   还是让脚本支持 webpack manifest），属独立议题。
   **在它被修好之前，任何"CI 会挡住体积回归"的说法都不成立。**

另有一条治理缺口：**`tests/web/` 不在任何 CI 分片里**（全 workflow 零命中），
所以新增的两个 web 守卫只在本地生效。直接接进 shard 会立刻变红
（该目录已有 4 个 pre-existing failure），正确顺序是先修那 4 个再接。
**在接进 CI 之前不要再往 `tests/web/` 加守卫**——一个 CI 不跑的守卫只会制造
"以为有保护"的假象，那正是本文件 §7.4 开头批评的那种控制回路缺陷。
（补轮的 MemberOps `dynamic()` 因此**没有**配套守卫；等目录接进 CI 后再补
"BiV2Surface 的每个 panel 都必须是 dynamic import" 这条断言。）
