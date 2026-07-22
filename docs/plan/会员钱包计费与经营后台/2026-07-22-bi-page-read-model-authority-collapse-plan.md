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
