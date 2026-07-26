# 层盲区表 · asyncio / 并发

**用途**:Stop Gate 的「层盲区」一栏需要回答「本次改动落在哪层、该层还有哪些高频反模式
本次没扫」。本表让那一栏从**做功**变成**查表**。

**产出方式**:2026-07-26 第一轮盲区侦察。异源模型(Codex)独立列 12 项 + 本地 AST 扫描
4 项,两路互不可见。合并后 16 项,**重叠 0 项**——这就是异源的价值。

**证据级别**:全部 **E1(静态文本级)**。命中数已逐条复现,但**未证明生产可达**。
本表是雷达,不是工单。修与不修按各自的生产表现判断。

**指纹复现**:异源给的 9 条指纹全部实跑,命中数分毫不差(56/21/12/9/6/5/4/3/1)。

---

## 最高优先:一个解药变成的新瓶颈

### A0 · `to_thread` 无背压(56 处)

```bash
rg -n --glob '*.py' 'asyncio\.to_thread\(' deeptutor
rg -n 'set_default_executor|ThreadPoolExecutor\(max_workers' --glob '*.py' deeptutor  # 确认有无自定义池
```

**本仓**:56 处。`turn_runtime.py`(7)、`luban_preview.py`(7)、`learner_state/runtime.py`(5)、
`agent/tools/web.py`(4)、`bi_service.py`(4)…**未发现 `set_default_executor`**,
即 56 处全部共享 Python 默认池 `min(32, cpu+4)`。

**为什么它排第一**:`asyncio.to_thread` 是本仓治「同步阻塞全家桶」的**标准修法**
(retest 一役就是这么修的)。但它把阻塞从事件循环搬到了一个**共享且有限**的池里,
没有背压、没有分池、没有队列上限。

**表现**:事件循环指标正常(不再饥饿),但 HTTP p95/p99 随并发上升;线程池队列长度与
等待时间增长。**症状从"全体饿死"变成"排队变慢",更难归因。**

**决策影响**:下面 A1 那 42 处如果按标准修法全改 `to_thread`,池里会变成 98 个调用点
抢 22 个 worker。**修之前先给默认 executor 定容并分池,否则是把问题挪个地方。**

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
`routers/bi.py`(3)、`routers/tutor_state.py`(3)、`services/bi_service.py`(3)——**全在用户请求入口**。

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
