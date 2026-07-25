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
  `_load_business_context` 成为唯一 `asyncio.to_thread` 边界（与 `sqlite_store._run_read` 同范式）；
  `get_overview` 的会员快照、`get_commerce` 全方法一并离开事件循环。
- **补完病B-4**：`bi.py:/member/dashboard` 与 `member.py:/dashboard` 降同步 `def`——
  2026-07-05 那轮只改了 mobile 三条，这两条调同一个 3–5s 的 `get_dashboard` 却被漏下。
  守卫 `tests/api/test_mobile_event_loop_discipline.py` 泛化为 `(router, path)` 映射，
  成为事件循环纪律的唯一权威；BI 那半用行为断言（执行期间事件循环必须继续 tick）。
- **物理物化**：`turn_events(type, created_at DESC)` 与 `turns(updated_at DESC)` 索引。
- **快照时刻接线**：后端 `generated_at` 此前在前端整条链是断的——类型无字段、builder 不读、
  面板用 `Date.now()` 现编却标注「实时数据」。这违反 §1「禁止前端估算 authority」，
  且使任何缓存都无法验证。现已接通，缺失时显式显示「快照时刻未知」。
- 传输轴（与读模型正交）：ECharts 改按需注册，brotli 309,807 → 173,732（−43.9%）。

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
