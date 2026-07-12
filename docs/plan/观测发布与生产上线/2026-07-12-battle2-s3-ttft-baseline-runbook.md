# Battle2 S3 — TTFT/TTFVT 基线采集 Runbook(部署#1 后照跑)

> 状态:Ready(随 perf/battle2-speed-cost-20260712 S3 观测基座落地)
> 归属:Battle2 速度与成本战役 · 组A 观测基座(S3 T1-T4)
> 纪律:observe-only fail-open;本 runbook 的读数是 Battle2 后续任何「变快了」宣称的唯一对照组(自证陷阱纪律:只信独立、可证伪、可重复的终态观测)。

## 交付内容回顾(验收对象)

| 跳 | 内容 | 落点 |
|---|---|---|
| T1 | `update_observation` 增加 `completion_start_time` 直通(Langfuse 写入唯一出口) | `deeptutor/services/observability/langfuse_adapter.py` |
| T2 | 三个流式 generation 调用点捕获首 chunk UTC wall-clock 并导出 | `openai_compat_provider.py` / `anthropic_provider.py` / `services/llm/factory.py` |
| T3 | turn 级 TTFVT Prometheus histogram(`deeptutor_turn_first_useful_content_ms`,label 仅 `content_source`)+ **multiworker 合并**(UVICORN_WORKERS=2 硬伤修复) | `api/runtime_metrics.py` / `session/turn_runtime.py` / `observability/multiworker_metrics.py` |
| T4 | 本 runbook | 本文件 |

统一口径:LLM 调用级 TTFT 权威 = provider 循环首 chunk 时刻(`completion_start_time`,Langfuse 服务端派生 `timeToFirstToken = completionStartTime - startTime`);turn 级 TTFVT 权威 = turn_runtime 既有 `_first_useful_content_observation`(sanitize/persist 之后观测)。两者不互相竞争,前端 `first_visible_content_rendered` surface ack 仅作交叉核对。

## 步骤 1(硬前置门):容器内核 SDK 签名

```bash
docker exec <api容器> python -c "import inspect,langfuse;from langfuse._client.span import LangfuseObservationWrapper as W;print(langfuse.__version__,'completion_start_time' in inspect.signature(W.update).parameters)"
```

必须输出 `<version> True`。**核不过则 T1/T2 观测静默缺失,先升 SDK 再继续,后续步骤全部作废。**

已核结果(开发期,2026-07-12):本地 4.2.0 与生产钉的 4.7.1(干净 venv 实测)`W.update` 与 `Langfuse.start_observation` 均含 `completion_start_time` → GO。

## 步骤 2:打 5 个流式 turn

test2 真入口(微信 automator true-entry 法或既有 curl/ws smoke)发 5 个会走流式回答的普通问题 turn。要求覆盖 `content.delta` 首字路径(普通聊天即可);至少 1 个走 `result.response` 一次性路径(如判分类)更好。

## 步骤 3:Langfuse 读数(TTFT)

```bash
curl -s -u $LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY \
  "$LANGFUSE_HOST/api/public/observations?type=GENERATION&name=tutorbot.llm.stream&limit=50"
```

断言:步骤 2 的新 turn 对应 generation 的 `completionStartTime` 非 null,且 `completionStartTime - startTime` 为正数量级合理(百 ms~数 s)。`name=llm.stream`(factory 路径)同查。

分位数双路径:
- Langfuse UI → Generations 表 → Time to First Token 列排序/聚合;
- UI 不聚合则 observations API 导出 JSON + 5 行脚本算 p50/p95。

## 步骤 4:Prometheus 读数(TTFVT,必须两 worker 合并视图)

```bash
curl -s :8000/metrics | grep deeptutor_turn_first_useful_content_ms
```

断言:
1. `_bucket{content_source="content.delta",le="..."}` 桶计数非零,`le="+Inf"` == `_count`;
2. **合并视图核验**:`_count` ≥ 步骤 2 的 turn 数(生产 UVICORN_WORKERS=2,`/metrics/prometheus` 走 `multiworker_metrics.collect_merged_snapshots` 文件合并;若多次 scrape 数值在两套之间跳动=合并断了,回查 worker_metrics/*.json dump 是否新鲜);
3. 分位数 PromQL:

```promql
histogram_quantile(0.95, sum(rate(deeptutor_turn_first_useful_content_ms_bucket[24h])) by (le, content_source))
```

worker 重启对策:rate()/increase() 天然免疫 counter 重置,验收时用 `increase(...[1h])` 双核。

## 步骤 5:跨层交叉核对

turn TTFVT p50 ≈ `start_turn_setup` + `provider_first_chunk` + 事件 persist 开销。若 TTFVT 与 Langfuse TTFT 差异 > 2s,按 turn_event_log 的 `latency_timeline`/`capability_stream_stage_timings_ms` 定位中间跳(路由分类器/工具链/persist)。另与 `deeptutor_surface_first_render_coverage_ratio` 及 surface ack 的 `first_visible_content_rendered` 对照,确认端侧感知与服务端观测同向。

## 启动核验读数(2026-07-12,部署#1=08dc27eb 后步骤1-5实测)

- 步骤1 SDK 签名门:容器内 `langfuse 4.7.1 True` → GO。
- 步骤2:eval-runner(claude_ttft_bl*)真 WS 入口 3 轮×2 消息=6 流式 turn,全部 passed:true。
- 步骤3 Langfuse:部署后新 generation `completionStartTime` 非 null 11/11(tutorbot.llm.stream 6 + llm.stream 5;更早的 null 全为部署前历史,符合预期)。LLM 级 TTFT 实测:tutorbot.llm.stream 1.39-1.91s,llm.stream(factory 路径)3.54-4.57s,模型 deepseek-v4-flash。
- 步骤4 Prometheus(X-Metrics-Token,127.0.0.1:8001/metrics/prometheus):`deeptutor_turn_first_useful_content_ms` count=6 与打的 6 turn 逐一对上;分桶 3≤4s/1≤8s/2≤16s,`+Inf`==count;合并视图 ✓。
- 步骤5 交叉核对:turn TTFVT 均值 ~6.1s vs LLM TTFT ~1.4-1.9s,差 ~2-4s=生成开始前的路由/followup 判定器段——与 Langfuse 深查"followup 判定器占首答前阻塞主因"结论同向,正是灰度序(B2/B4)要消的段。基线窗自本读数起算。
- 部署#1教训:首跑 SSH 在备份步被断,容器 env 已更新但镜像里代码是旧的(md5 与宿主源码不一致)=「env 新代码旧」假绿;重跑完整构建后 md5 逐字一致才放行。**核部署必须 md5 比对容器文件 vs 宿主源码,env SHA 对齐不算数。**

## 步骤 6:采 24-48h(目标 7 天)基线并写回本文件

| 指标 | p50 | p95 | 采样窗 | 备注 |
|---|---|---|---|---|
| Langfuse timeToFirstToken(tutorbot.llm.stream) | _待填_ | _待填_ | _待填_ | |
| TTFVT content.delta(Prometheus) | _待填_ | _待填_ | _待填_ | |
| TTFVT result.response(Prometheus) | _待填_ | _待填_ | _待填_ | |
| completionStartTime 非 null 占比 | _待填_ | — | 24h | <90% 则按 provider_name 定位缺口 provider |

## 客户端真流式核查结论(S3-T6,零代码改动)

已核(2026-07-12,只读):
1. `ws-stream.js:496-507` — 每个 public `content` 事件逐条 `cb.onToken`,传输层无攒批无去抖;
2. `chat.js:1404-1415 _onToken` — 累积 `_buf`,但 `_flushCount===0` 首 token **立即** `_flush`(首字零延迟);之后按机型分档节流 flush;
3. `helpers.js getAnimConfig` — flushThrottleMs 高端 100 / 中端 120 / 低端 200ms,是 setData 合批渲染优化而非「流式变一次性」;
4. Markdown 每 3-5 次 flush 才解析一次(`chat.js:1417-1426`),>24000 字符再减半——防重排,不影响首字;
5. `chat.js:1472-1493` — `first_visible_content_rendered` surface ack 已回传,可与服务端 TTFVT 交叉核对。

结论:客户端是真流式,无需修。不建议动 flushThrottleMs(低端机 200ms 是性能保护,属前端性能另案)。唯一备忘:`_onFinal` 用 `result.response` 整体替换流式文本(既有已知设计),与 TTFT 无关。
