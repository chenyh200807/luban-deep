# 层盲区表 · asyncio / 并发

**用途**:Stop Gate 的「层盲区」一栏需要回答「本次改动落在哪层、该层还有哪些高频反模式
本次没扫」。本表让那一栏从**做功**变成**查表**。

**产出方式**:2026-07-26 第一轮盲区侦察。异源模型(Codex)独立列 12 项 + 本地 AST 扫描
4 项,两路互不可见。合并后 16 项,**重叠 0 项**——这就是异源的价值。

**证据级别**:全部 **E1(静态文本级)**。命中数已逐条复现,但**未证明生产可达**。
本表是雷达,不是工单。修与不修按各自的生产表现判断。

**指纹复现**:异源给的 9 条指纹全部实跑,命中数分毫不差(56/21/12/9/6/5/4/3/1)。

---

## 最高优先:唯一判据 —— 这段阻塞释放 GIL 吗?

> **2026-07-26 修订**:初版结论「98 调用点抢 22 worker」已被证伪(两个池物理隔离)。
> 保留这行是因为**它错得典型**:把并发瓶颈默认当 IO 问题,没先问 GIL。原文见 git 历史。

### 事实一:两个线程池是**物理隔离**的(实测)

```python
asyncio.to_thread(...)        → 线程 asyncio_0            默认 executor,min(32,cpu+4)=22
anyio.to_thread.run_sync(...) → 线程 AnyIO worker thread  CapacityLimiter,默认 40
```

FastAPI 同步 `def` 路由走 **anyio 池(40)**;`asyncio.to_thread` 走 **默认 executor(22)**。
**两者不互抢**,原文"98 抢 22"是错的。本仓 `anyio` limiter 未被调过,用默认 40。

### 事实二:GIL 决定线程池有没有用(实测)

```
624KB JSON  loads+dumps(indent=2)     单次 10.2ms
            4 线程并行                 36.4ms  ≈ 单次×4(36.7ms)
            并行加速比                 1.01x   → 纯 GIL-bound
```

**判据(唯一):**

| 阻塞是否释放 GIL | 例子 | 挪进线程池有用吗 | 正确修法 |
|---|---|---|---|
| **释放** | 同步网络 IO、`fsync`、SQLite C 层 | ✅ 有用,O(并发)→O(1) | 改同步 `def` 或独立池 |
| **不释放** | `json.loads/dumps`、`deepcopy`、纯计算 | ❌ **结构上无效** | **删掉开销本身,别换池** |

异源实测三臂对照(复刻 `member_console` 的 RLock + 624KB JSON,并发 40):

| 臂 | wall | loop-lag p50 | max |
|---|---|---|---|
| A 现状 | 491ms | 490 | 490 |
| B 改 `def` | **503ms(更慢)** | 59 | **418(只降 15%)** |

"事件循环指标转绿、p95 不变或更差"——字面兑现。**GIL-bound 的活,换池只是换个地方排队。**

### 事实三:本仓已有先例与守卫,改 `def` 不是"零新增概念"

- 已有 4 个同步 `def` 路由(`mobile.py:3151/3165/3174`、`lesson_progress.py:39`),
  **每一个都配了解释注释 + 回归钉**(`tests/api/test_mobile_event_loop_discipline.py` 白名单)。
  批量改 N 条 = N 条注释 + 白名单扩到 N 项,**不是零成本**。
- **PR #564(`63452eaad`)已明确拒绝过统一改 `def`**:"demoting the whole chain would force
  `asyncio.run` boundaries"。最终用的是混合方案 + 行为断言。**别重提已被否决的方案。**
- **ContextVar 语义变更**:anyio 走 `copy_context()`,同步路由体内 `ContextVar.set()` 会被丢弃。
  本仓有 4 组 request 期 ContextVar(含日志字段、langfuse usage scope)。

### 事实四:判据是「单请求阻塞时长 × 并发」,不是 QPS

生产 ~35 turn/天、93 真实会员——**QPS 极低**。但生产已因此伤过用户**两次,都发生在并发 3**:
2026-07-05(0.13s→7.2s,55x)、2026-07-21(交卷 5xx 撞 15s 死线)。
**那两起的阻塞是 3-5s 同步 Supabase 网络(GIL-releasing),线程池对它确实有特效。**

---

## A 组 · 本地 AST 扫描(4 项)

### A1 · `async def` 无 await + 跨层同步 IO(42 处,下界)

单层 AST 只抓到 **4**;跨 2 跳追踪抓到 **42**(第 1 层 1 / 第 2 层 41 / 第 3 层 0)。
**单层指纹覆盖率仅 2.4%**——IO 藏在第二跳。

```bash
python scripts/scan_asyncio_blocking.py            # 人读报告(唯一权威判据)
python scripts/scan_asyncio_blocking.py --json     # 机器消费
python scripts/scan_asyncio_blocking.py --check 42 # 超基线才非 0(可选,默认不设门)
```

**数字权威 = 该脚本的当前输出**,本表引用的是 2026-07-26 基线。两者不一致时以脚本为准
并回填本表。

**本仓聚集**:`routers/mobile.py`(8)、`routers/member.py`(8)、`routers/photo_answer.py`(6)、
`routers/bi.py`(3)、`routers/tutor_state.py`(3)、`services/bi_service.py`(3)。

**⚠ 命中 ≠ 路由**:42 处里 **12 处根本不是 FastAPI 路由**(`bi_service.get_member_stats`、
`dependencies/auth.get_current_user`、`channels/matrix.start` 等——它们**是被 await 的协程**)。
对这 12 处改 `def` 会**打炸调用方**。用扫描器结果做修复决策前,必须先按「是不是路由」分流。

**修复优先级(按上面的 GIL 判据,不是按命中数)**:
1. **删开销**(GIL-bound,换池无效):`service.py:1911` `json.dumps(indent=2)` 10.2ms→1.7ms;
   `_load_member_snapshot:2903` `deepcopy` 5.1ms;加 mtime 缓存(本仓已有此模式:
   `luban_lesson/read_model.py:63`)。
2. **腾池**:`photo_answer.py:283` → `photo_answer/service.py:104 def process_job` 是**同步
   BackgroundTask**,十秒级 OCR/VLM 占着 anyio 那 40 个令牌——**它正占着别人要搬进去的池**。
3. **只改真符合判据的少数几条**(阻塞释放 GIL 且 ≥100ms)。
4. 验收看 `deeptutor_turn_loop_lag_max_seconds` / `_over_200ms_total`,**不是 p50**。

**已抽验真阳性**:`bi.py:200 bi_learning_preference` 无 await,同步调 `get_engagement_breakdown()`
**6 次** DB 聚合;`mobile.py:3001 billing_wallet` → `_teaching_video_limit_for_user` →
`member_service.get_teaching_video_limit`,**三层深**。

**表现**:并发天花板 ≈ worker 数;单请求慢即全体饿死;POST 撞前端死线报 5xx。

**关键教训**:`bi.py` 头部注释写着「薄 handler 只组装/转发」——
**thin wrapper ≠ 非阻塞。逻辑薄与执行不占事件循环是两个正交维度。**

### A2 · `async def` 内直接阻塞调用(3 处)

```bash
rg -n --glob '*.py' -U 'async def[\s\S]{0,2000}?(time\.sleep|subprocess\.(run|call|Popen|check_output)|requests\.)' deeptutor
```

**本仓**:`observability/arr_runner.py:534`(subprocess.run)、`channels/feishu.py:350`(time.sleep)、
`math_animator/renderer.py:159`(subprocess.Popen)。

### A3 · `create_task` 结果未保存(7 处)

```bash
rg -n --glob '*.py' '^\s*(asyncio\.)?create_task\(' deeptutor
```

**本仓**:`agent/loop.py:3753`、`research_pipeline.py:951`、`deep_solve.py:224`、
`deep_research.py:133`、`knowledge/progress_tracker.py:67,72`、`rag/service.py:61`。

**表现**:task 被 GC **静默消失**,无异常无日志。后台工作偶发不执行,无法复现。

### A4 · `gather` 无 `return_exceptions`(6 处)

```bash
rg -n --glob '*.py' -U 'asyncio\.gather\((?:(?!return_exceptions)[^)])*\)' deeptutor
```

**本仓**:`rag/pipelines/supabase.py:1656`、`chat/agentic_pipeline.py:1191`、
`solve/agents/planner_agent.py:314`、`benchmark/exam_quality_eval.py:213`、
`rag/pipeline.py:162`、`runtime/safety.py:137`。

---

## B 组 · 异源侦察(12 项,按命中降序)

| # | 反模式 | 命中 | 指纹 | 本仓样例 | 生产表现 / 告警口径 |
|---|---|---|---|---|---|
| B1 | 每次新建 httpx client,连接池不复用 | **21** | `rg -n 'async with httpx\.AsyncClient\(' deeptutor` | `member_console/service.py:3632`、`wechat_pay.py:156`、`agent/tools/web.py:200` | TLS/建连耗时抬升,FD/TIME_WAIT 增长;告警 connect_ms p95、连接错误率 |
| B2 | 固定间隔 sleep 重试,无退避与抖动 | **20** | `rg -nP 'asyncio\.sleep\((1\|5\|8\|0\.1\|0\.04\|0\.15)\)' deeptutor` | `research_pipeline.py:259`、`channels/discord.py:79`、`channels/telegram.py:286` | 故障时同相重试形成尖峰;告警 retry/s、上游 429/5xx 的秒级周期峰 |
| B3 | 无界 `asyncio.Queue()` | **12** | `rg -n 'asyncio\.Queue\(\)' deeptutor` | `events/event_bus.py:84`、`routers/question.py:84`、`bus/queue.py:17` | 慢消费者时 qsize 与 RSS 单调上涨(与 2026-06-06 内存事故同族);告警 qsize、RSS、消费滞后秒数 |
| B4 | 遗留 `get_event_loop()` 依赖隐式 loop | **9** | `rg -n 'asyncio\.get_event_loop\(\)' deeptutor` | `embedding/client.py:205`、`rag/pipelines/llamaindex.py:389`、`routers/question.py:124` | worker/线程中 `RuntimeError: no current event loop`,或任务绑错 loop;按异常类型计数 |
| B5 | 同 key task 覆写式登记 | **7** | `rg -n '\[[^]]+\]\s*=\s*asyncio\.create_task\(' deeptutor` | `channels/mochat.py:625`、`telegram.py:718`、`matrix.py:470` | 旧任务未回收→重复发送/轮询;告警 active tasks ÷ 活跃 key 数、重复消息率 |
| B6 | `gather(return_exceptions=True)` 的异常被丢弃 | **6** | `rg -n 'await asyncio\.gather\(.*return_exceptions=True' deeptutor` | `channels/manager.py:91`、`learner_state/runtime.py:108`、`guide_manager.py:661` | 子任务失败但父流程显示成功;告警「启动数−成功−显式失败」不守恒 |
| B7 | 按 key 缓存 `asyncio.Lock` 无容量上限 | **6** | `rg -n 'setdefault\(.*asyncio\.Lock\(\)' deeptutor` | `learner_state/service.py:219`、`session/sqlite_adapter.py:308`、`agent/memory.py:286` | 高基数 ID 使 lock map/RSS 长期增长;告警 lock-map size vs 独立用户数 |
| B8 | 压制 `CancelledError` 弱化 shutdown | **5** | `rg -n 'contextlib\.suppress\(asyncio\.CancelledError' deeptutor` | `session/turn_runtime.py:2739, 3083, 4418` | 重启后残留请求/写入仍在跑;告警 shutdown 超时、重启后 active task 数、重复副作用 |
| B9 | `shield()` 阻断取消向内传播 | **4** | `rg -n 'asyncio\.shield\(' deeptutor` | `turn_runtime.py:3084, 4419`、`channels/matrix.py:238` | 客户端断开后下游 LLM/DB 继续跑(烧钱);告警 disconnect 后 span 时长、ghost completion 数 |
| B10 | 每次新建默认 `ThreadPoolExecutor()` | **3** | `rg -n 'ThreadPoolExecutor\(\)' deeptutor` | `embedding/client.py:209`、`question_extractor.py:216, 250` | 突发并发时线程创建/上下文切换飙升;告警线程数、CPU sys%、p99 |
| B11 | 取消与普通异常合并捕获 | **1** | `rg -n 'except \(asyncio\.CancelledError, Exception\)' deeptutor` | `agent/loop.py:3728` | 取消被当业务失败吞掉,停服拖延;告警 shutdown grace 超时 |

---

## 未验证 / 本表的边界

**异源自述未验证**:
- 未启动服务或连接生产观测面,无法确认静态命中在真实入口、真实并发、当前发布 SHA 下可达。
- 未逐条做控制流审计——B5/B8/B9 有可能是**受控的清理路径**,需逐处检查旧任务回收与异常记录。
- 未取队列长度、executor backlog、连接池指标与生产 p95,故**无法给出故障频率与优先级**。

**本地扫描边界**:
- A1 的 42 是**下界**:跨层追踪只做 2 跳,跨模块调用按名字启发式(含 service/store/client/repo)。
  全集需要全仓符号解析。
- A1 只抽验了 **2/42** 真阳性,其余未逐个确认。

**本表未覆盖的 asyncio 子话题**(下一轮侦察候选):
await 缺 timeout、async 上下文管理器泄漏、`run_until_complete` 嵌套、
`threading.Lock` 用在 async 路径、asyncgen 未 `aclose`、信号处理与优雅停机。

## 工具

`scripts/scan_asyncio_blocking.py`(2026-07-26 落地,`contracts/registries.yaml` 登记为
**`operational`** 而非 `pr_gate`)——判据含启发式,设成阻断门会制造假红,而假红比没门更糟。
它是**尺子不是门**:你主动去量,不是它自动拦你。

下一轮候选:把 B 组 11 条 rg 指纹也收进同一个脚本,让整层可一键复扫。
