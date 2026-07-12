# Battle2 速度与成本战役 — 实施计划

> 手术级设计在同目录 [`2026-07-12-battle2-speed-cost-design-appendix.json`](./2026-07-12-battle2-speed-cost-design-appendix.json)(designs[0..3]=S1/S2/S3/S5 家族,commander=全局指挥官裁决——**对实施有约束力**)。证据基座=[`2026-07-12-langfuse-production-deep-investigation.md`](./2026-07-12-langfuse-production-deep-investigation.md)。

- **状态**: Executing (2026-07-12,分支 perf/battle2-speed-cost-20260712,基线 5791967d)
- **病因(指挥官第一性命名)**: **「守门权错配」**——把"要不要干活、干多宽"的裁量权外包给最贵的执行组件(LLM 自判变化/自判任务/全宽输出、网络探活、全量重检索),而系统已持有的廉价确定性信号(增量账本/格式契约/缓存真值/超集结果/已算出的时刻)无人消费。Battle1 治"重复计算真值",Battle2 治同一根上的"重复购买判断与宽度"。
- **owner 已批**: 五项全开(摘要门控/判分输出减半/TTFT/B2B4 灰度/小杠杆包)。

## 编组与实施序(指挥官定)

- **第0步**: 各家族刀落前 Langfuse 复核本族关键数字(52%·57% NO_CHANGE/heartbeat 1,510/rerank 36k/search_unified 超时/32 扇出)——折入各组 pre-flight。
- **PR-0(已发 #446)**: B2/B4 分支合 main,flag 默认关零行为,占 contracts/env_registry 基线。
- **组A 观测基座**: S3 全部(langfuse adapter completionStartTime 直通→provider 首 chunk 捕获→TTFVT histogram→基线 runbook)+ **multiworker_metrics 合并支持**(指挥官抓出的两设计共同硬伤:UVICORN_WORKERS=2 下漏合并=分位数低估一半)。heartbeat 空 Context 修复(S4-T2)因同文件原子性移入组C(偏离指挥官 PR 编组,记账)。
- **组B S1 摘要门控**(组A 的 runtime_metrics 落定后开工): T1 计数门+证据直通+fail-open 游标→T4 门命中率埋点(同 PR,判别位纪律)→T2 source 瘦身 10k→4-5k(砍双份摘要注入/全量 progress JSON/未消费的远端 read_snapshot)→T3 摘要降档 fast-tier。阈值=3(不做 env,revert 即回滚)。
- **组C S5 小杠杆**: heartbeat 确定性门+空 Context(T1/T2)→health check SWR 出热路径(T3)→search_unified 超时预算(T5,默认值先按成功请求 p95 校准,不盲用 4.0)→rerank 文档字符 cap(T6,代码进默认 0)→批量 embed+q0 双 RPC 合一(T4①②,oracle 测试硬前置:超集派生==旧 RPC 逐字段一致,不绿即弃)。
- **组D S2 判分收紧**(最后合,用户可见风险最高): T4 确定性去套话(零 LLM,可先单独出)→T1 schema v2 收紧(逐项解析只展开错选+正确项;采分点/易错点仅本题特异性)→T3 差分质量门(自证红测+全绿硬前置;blocking 只留:正确字母在场/套话黑名单零命中/必备段非空/降幅≥45%)→T2 max_tokens cap **必须随 flag**(指挥官改判:无条件 cap 会让 flag-off 旧臂截断触发 repair 双倍成本)→T5 灰度 flag DEEPTUTOR_MCQ_FEEDBACK_COMPACT。

## 发布列车(指挥官定,4 PR+2 部署)

PR-0(#446,即刻)→PR-1(组A 观测基座)→**部署#1(D+1,今日不再第三次部署)**+采 24-48h TTFT/TTFVT 基线(唯一合法对照组)→PR-2(组B+组C 成本刀)→PR-3(组D 判分)→**部署#2(D+2~3)**→灰度 toggle 序(每次只开一个,间隔≥24h,触红线先关最近 toggle):T+0 无 flag 项生效验收 48h;T+2d DEEPTUTOR_MCQ_FEEDBACK_COMPACT(先 test2 QA 真机 3 轮持久化终态人眼核,≥30 judged turns 才许宣称);T+3d LUBAN_FOLLOWUP_FAST_TIER_ENABLED(盯回指维度);T+5d+ rerank cap。两个行为 flag 各带 14 天赎罪条款。

## 红线(指挥官定,节选)

判分差分门任一裁决字段不一致→S2 停手;explanation 缺段/repair 率上升→cap flag off+revert;TTFVT 较基线恶化>10%→回滚最近 toggle;S1 skip 率>85% 或 changed≈0→revert 门;heartbeat 漏执行→revert;检索 exact 采纳率降/degraded 率 2x→参数回滚;样本<30 不许宣称收益;禁 trace latency 口径。

## 砍单/挂账

S4-T4③ exact-text 串行短路(伤 85% 多数人 p50 换 15% 成本,方向性错误,砍);变体数/rerank_window 收窄待最小召回 eval;memory_service 同病兄弟/search_unified DB 三合一/legacy provider TTFT——挂账不混本列车。
