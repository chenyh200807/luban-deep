# 鲁班智考架构审计修复战役 Battle 1 —— 实施计划

> **For agentic workers:** 逐批执行本计划（batch 内可并行、batch 间串行提交）。手术级设计细节（函数级改法+代码片段+测试断言）在同目录附录
> [`2026-07-11-luban-arch-audit-battle1-design-appendix.json`](./2026-07-11-luban-arch-audit-battle1-design-appendix.json)
> （designs[0..4] = W1..W5 家族设计，commander = 指挥官裁决）。实施者必须先读自己家族的设计 JSON + 指挥官对本家族的 challenge，再动手。

- **状态**: Draft → Executing（2026-07-11）
- **分支**: `perf/arch-audit-battle1-20260711`（worktree `deeptutor-battle1`，基线 origin/main `b3e9ab09`）
- **来源**: 2026-07-11 六专家审计（23 agent，17 条 MUST 全部经独立对抗验证存活）→ 5 家族治本设计 + 宏观指挥官裁决
- **三大原则**: thin wrappers fat skills / first principles / less is more。修法必须**减少** decider/writer/重复计算，禁止加闸式补丁。

## 病因裁决（指挥官）

**1 主病 + 1 独立病。** 主病（W1/W2/W3/W5 四个症状面）：

> 系统不信任自己已经拥有的单一真值与已签发的单一裁决——每个消费点都以「全量重算、重复执行、手工复制、全局互斥」的方式重复支付本已付过的成本，并把传输粒度错绑成持久化与计算粒度，使名义并发 64 塌缩为实测 ~10。

独立病（W4）：模型档位概念全链路零 writer 的死接线（打样宽度≠承诺宽度），药方与主病同源=单一权威收口。

## 目标 / 非目标

**目标（对结果负责的两个数字）**：
1. 单 worker 有效并发从实测 ~10 提升至接近 `_MAX_CONCURRENT_TURNS=64` 名义值（微基准取证分层：PRAGMA 单独 / +锁治理 / 全量）。
2. 每 turn 路由 LLM 调用次数减半（双跑→至多一次，测试断言钉死）。

**非目标（本战役明确不做）**：
- 不重写 ~9500 行路由层（冻结+模型换代后的"删除里程碑"另案）。
- 不开多 worker、不动 `/api/v1/ws` 单一入口、不改 WS 帧结构。
- 不在生产置位任何新 flag（`LLM_FAST_MODEL` / `LUBAN_FAST_TURN_LIGHT_MODEL_ENABLED` 战役期内保持未设，违者按红线复盘）。
- 指挥官砍/推迟清单：W1-T1 的 provider usage 回写（跨时点第二输入源，**砍**）；W5-T2 边界事实 lane（YAGNI，第 2 条事实出现再建）；W3-T3 metadata 契约字段（瘦身为测试断言）；W1-T6 AST 静态闸（降级可选后补）；W4-T7 生产通电与 A/B（运营节奏，出战役）。

## 实施批次（指挥官定序，batch 内并行、batch 间串行合并）

| 批 | 任务 | 触碰文件（生产面） | 要点 | 风险/回滚 |
|---|---|---|---|---|
| 1 | W2-T1 PRAGMA `synchronous=NORMAL`（2 行止血）；W1-T2 `count_tokens` 单 pass 近似+装箱去 O(n²)+langfuse 兜底同改；W1-T4 think 剥离增量状态机 | `sqlite_store.py` / `context_builder.py`+`langfuse_adapter.py` / `loop.py` | 三刀零接口变化独立可回滚。W1-T4 **oracle 必须按指挥官挑战 #1 修正**：以整段重放旧 `_stream_delta`（含 emitted_stream_len clip 语义）为对拍基准，非旧 regex(全文) | 低；单文件 revert |
| 2 | W3-T1 消路由双跑（select/execute 公共边界，~40 行）；W3-T2 半刀=仅 `DEEPTUTOR_ROUTING_LLM_TIMEOUT_S` 硬超时（fast-tier pin 不落） | `orchestrator.py` / `turn_runtime.py` / `question_lifecycle_skills.py` | **传 `resolved_capability` 原值**给 handle（指挥官挑战 #W3-1：canonical 归一有副作用，canonical 名只喂 turn 侧账本）；"每轮≤1 次路由 LLM"以测试 spy 断言钉死（不加 metadata 字段）。**先例校准**（[2026-06-29 Phase1 证伪报告](../题目生命周期与助教运行时/2026-06-29-scene-classifier-nonblocking-phase1-bottleneck-falsified.md)）：生产活体数据证明 scene 分类 LLM 只跑 0.9-2.0% 的 turn，真正的首答前阻塞 LLM 是 followup 意图判定器（占 ~79%，p99 17-19s）——**双跑消除的主要价值正是砍掉 followup 判定器的第二次执行**；给 scene 分类器 pin fast 模型属"优化 <1% turn 的错轴"，仅保留硬超时作廉价韧性，fast-tier pin 从本批出列（followup 判定器 B2/B4 优化属另案需 owner 授权） | 中低；保留漂移观察器兜底 |
| 3 | W5-T0 golden 行为快照（先行全绿）→ W5-T1 `_finalize_visible_answer` 单一管道收权，4 处手抄链→4 个单行调用（净删 ~75 行） | `loop.py` | T0 的 no-op 参数化证明是 T1 合并硬前置；branch B（prefetched）缺 2 修正器的差异按 no-op 证明统一（新增 skip 日志直接 debug 级） | 中；golden 快照即回滚判据 |
| 4 | W2-T2 单写线程+常驻连接+删全局锁+读写分离 → W2-T3 内存 seq 分配器+CONTENT delta 批量落库(≤250ms 或下一事件)+订阅 attach 前 flush；并行 W1-T3 Redis 异步化（redis.asyncio） | `sqlite_store.py`+`turn_runtime.py` / `unified_ws.py`+`rate_limit.py` | 本战役最重一刀。前置：43 处 `_run` 调用逐 fn grep DML 分类（存疑归写路径）；生产 db 按 type 取证 CONTENT 为唯一高频型；终态事件仍即时落库且 done 同事务含全部缓冲 | 中；**W2-T3 合并门=live 3 轮断线重连实测**（见验收），失败当日回滚 T3（T1/T2 独立保留） |
| 5 | W1-T1 token 估算增量化（**砍③真值回写**，只留①增量+②冷启动 to_thread）→ W4-T1..T5 模型档位（`LLM_FAST_MODEL` 单一 accessor `resolve_fast_tier_model`、policy 填 `preferred_model`（flag 默认关）、摘要/subagent 独立降档、failover 裁决不加中间跳、更新死接线测试）→ W3-T2 fast-tier 接线（import W4 accessor，**禁止自落 env 键**） | `memory.py` / `provider_runtime.py`+`llm/config.py`+`response_mode.py`+`capabilities/tutorbot.py`+`loop.py` | memory.py 冲突：W1-T1 先、W4-T3 rebase，**同一实施者**；W4 测试(c) tokenizer 锚断言针对 W1-T1 后新形状重写；零配置零变化=bit-for-bit 守门测试 | 低-中；从 .env 删键即秒级回退 |
| 6 | W1-T5 session adapter async 化（get_or_create 走 store async 边界+持久化游标替代全量比对+LRU 上限） | `sqlite_adapter.py`+7 调用点 | 前置：rg 全库（含 scripts/）确认无 sync 调用面（`save()` 的 asyncio.run 分支是历史证据）；发现 sync 面按设计 uncertainty#2 退路 | 中高（族内最大波及面）；接口不变可独立 revert |
| 7 | 收尾：W1-T6 事件循环 lag 哨兵（接 TurnRuntimeMetrics/Prometheus，真闭环）；W4-T6 fast/deep 占比 observe-only 埋点；契约登记清账（两份 index.yaml）；W2-T4 微基准分层取证（给 owner"少切一刀"决策依据） | `runtime_metrics.py` 等 | 静态 AST 闸不做战役承诺（止血带≠闭环） | 低 |

## 红线（任一触发→停手/回滚，无例外）

1. 回放三消费面（resume after_seq / 跨 worker tail / 同 worker catchup）live 实测出现 seq 空洞、重复或终态丢失 → W2-T3 当日回滚。
2. W1-T4 模糊对拍在 oracle 修正后仍有无法解释的分歧 → 保留旧 regex，任务撤出战役。
3. contract_guard FAIL 或 protected 文件改动无同 PR 登记域测试 → 禁止合并（memory.py/loop.py/unified_ws.py/turn_runtime.py/orchestrator.py 全在保护面；新测试须同步登记**两份** index.yaml）。
4. deep/判分路径出现轻模型可达路径 → 拒收该 diff。
5. 部署后容器内 SHA 对拍失败或 `/api/v1/ws` 真机三步冒烟（start-turn+subscribe+断线 resume）失败 → 按 release checklist 回滚。
6. 实施中冒出设计外的新 flag/新路由/新 fallback/新 state 字段/新 wrapper → 停手回设计评审（有罪推定）。
7. 全量 pytest 出现 coroutine never awaited 或新增隔离污染 → 冻结合并链先定位。
8. W2-T2 读写分类错误在生产暴露（BUSY/锁等待日志）→ 当日把该 fn 回归写路径，不加新闸。
9. 战役期间 `LLM_FAST_MODEL`/`LUBAN_FAST_TURN_LIGHT_MODEL_ENABLED` 在生产被置位 → 越权，立即回退并复盘。
10. 五条硬不变量本体被触碰（/api/v1/ws 唯一入口、seq 单调、订阅 catchup、conversation_context_text 无条件注入、scene 失败 fail-open）→ 停手。

## 验收标准

- **单元/契约门**：改动域全部登记测试绿（基线已取证：session store 67 + 路由/response_mode/WS 301 全绿）；`contract_guard` 全量通过；新增测试全部登记进两份 index.yaml。
- **回放等价门**（W2）：同一事件流改造前后 `get_turn_events` 视图逐字段等价测试；崩溃窗口测试（done 事务含全部缓冲）。
- **路由计数门**（W3）：spy 断言"路由 LLM 每轮至多一次"，覆盖 scene=None 带 hint 轮与 question_review followup 轮。
- **行为保持门**（W5）：4 条 finalize 路径 golden 快照改造前后逐字一致。
- **零配置零变化门**（W4）：`LLM_FAST_MODEL` 未设时行为 bit-for-bit 不变（守门测试）。
- **容量取证门**（W2-T4）：微基准三档（T1 单独 / T1+T2 / 全量）在开发机+Aliyun 各跑一轮，写入取证报告；若瓶颈转移则如实报告为下一战役，不宣称全部解决。
- **合并→生产门**（出本 worktree 后）：W2-T3 必须过 live 3 轮断线重连实测才可合 main；真机三步冒烟过后才可部署（deeptutor-aliyun-release checklist）。

## 不确定性清单（设计已给验证法/退路，实施时逐项核销）

1. W2：43 处 `_run` 调用读写分类可能有隐藏写 → 逐 fn grep DML，存疑归写路径（只损并发不损正确性）。
2. W2：`_persist_and_publish` 是否严格 turn task 内顺序 await → grep 全部 `on_event=`/`emit=` 传递点；fallback=seq 分配+缓冲 append 挪进 flush_lock 临界区。
3. W2：既有测试对 `append_turn_event` 逐条形状的 mock 断言 → 批量化后按批量语义更新断言，PR 逐条列明。
4. W1-T3：redis.asyncio pipeline 在生产 valkey 的一致性 → 本地 valkey 容器实测；退路=仅 rate_limit 异步化+连接计数 sync 缩短 timeout 0.3s。
5. W1-T5：7 个调用点是否全在 async 上下文 → rg 全库含 scripts/；sync 面保留模块内私有 helper。
6. W4：`LLM_FAST_MODEL` 选型在 dashscope 端点的可服务性 → 通电前 curl 冒烟（本战役不通电，出列）。
7. W3：6s 超时未经 p95 校准 → 先只开超时+观测 scene=None 降级率，Langfuse trace 校准后收紧。
8. W5：branch B 极端 authoritative_answer 数字格式 → T0 参数化三种形状钉死。

## 偏离账本

实施偏离（edge case 选保守方案）记入同目录 [`2026-07-11-battle1-implementation-notes.md`](./2026-07-11-battle1-implementation-notes.md)（随本战役 PR 入 main）。

## 相关代码入口

`deeptutor/services/session/{sqlite_store,turn_runtime,context_builder}.py`、`deeptutor/runtime/orchestrator.py`、`deeptutor/services/question_lifecycle_skills.py`、`deeptutor/tutorbot/agent/{loop,memory}.py`、`deeptutor/tutorbot/session/sqlite_adapter.py`、`deeptutor/tutorbot/response_mode.py`、`deeptutor/api/routers/unified_ws.py`、`deeptutor/api/dependencies/rate_limit.py`、`deeptutor/services/config/provider_runtime.py`、`deeptutor/services/llm/config.py`。

## 后续战役（本计划不含，挂账）

供给消费 supply manifest 反射闸、编译管道脱单机（源语料上 OSS/版本控制）、CI 暗测试纳管、金标 150 条人工标注（非代码，owner 侧）、路由层删除里程碑（模型换代触发）、blue-green 发版。以上见六专家审计报告与 INDEX.md 挂载项。
