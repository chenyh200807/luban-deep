# Battle2 配对基线批结果 — 部署#2 前后同题串行对比(压缩列车终报)

> owner 拍板:自然流量≈0,24-48h 基线窗采不到样本,压缩为**部署前后合成配对批**(同一套题/同一 eval 身份/串行/贴着部署跑控时段漂移)。
> 设计过 eval-design 排雷:漂移哨兵、可证伪声明先行、指标对准刀落位置(成本+异步尾巴,非只看 TTFT)。
> 原始工件:`battle2-paired-batch-artifacts/`(逐 turn 日志/Langfuse 读数/Prometheus 差分/可复跑驱动)。

## 实验设置

- 两臂各 42 turn:8 会话×4 turn(5 聊天连续性+3 出题判分)+10 漂移哨兵(前5后5,固定 ping),全程串行,fresh conversation。
- PRE 臂:SHA `08dc27eb`(仅观测基座),窗口 2026-07-12T07:21:42→07:28:52Z,42/42 passed。
- 部署#2:SHA `34707970`(组B 摘要门控+组C RAG/heartbeat 小杠杆+组D 判分收紧;**行为 flag 全部默认关**;容器 md5 与宿主源码逐字核验)。
- POST 臂:窗口 07:42:55→07:49:38Z,42/42 passed。间隔 <25 分钟,provider 时段基本同质。

## 配对结果(PRE → POST)

| 指标 | PRE | POST | Δ |
|---|---|---|---|
| TTFVT 均值 content.delta(Prometheus) | 5302ms | 4602ms | **-13.2%** |
| TTFT tutorbot.llm.stream p50/p95 | 1378/2216ms | 1293/3518ms | -6.2% / +58.8%⚠ |
| 每 trace generation 数 avg/p95 | 2.39/4 | 2.10/3 | **-12.1% / -25%** |
| Token 输入/输出 | 622,870 / 35,847 | 443,341 / 30,907 | **-28.8% / -13.8%** |
| 成本(全批) | $0.6811 | $0.4923 | **-27.7%** |
| Trace 总时长(含异步尾巴)主 p50/p95 | 23159/34750ms | 15409/27114ms | **-33.5% / -22.0%** |
| 客户端墙钟主 p50/p95 | 9578/17201ms | 8903/15478ms | -7.0% / -10.0% |
| 主区间 Langfuse TTFT p50 | 4524ms | 3301ms | -27.0% |

**哨兵漂移核对**:相同 ping TTFT p50 +18.0%(<30% 阈)→ 无 provider 漂移混淆;方向为 provider 略变慢,若有影响是**压低** POST 优势,不虚增。

**可证伪判定(先行声明)**:TTFVT 恶化>10%?否(-13.2% 改善)→ 未触发回滚红线。

**部署#2 新计数器首秀**(旧版无此观测,这就是观测基座的价值):summary_maintainer 42 决策全覆盖(实跑 31/throttle 跳过 11=**26% skip 率**,evidence 通道 25/fail_open 6);turn_response_mode fast/primary=30。

## 诚实边界

1. n=32 主 turn/臂、LLM 非确定性,成本差 -27.7% 是**方向性信号**而非精确效应量;两批响应内容非逐字相同。
2. tutorbot.llm.stream TTFT p95 +58.8%(2216→3518ms)是唯一恶化项,小样本尾部(n≈31),p50 为改善;**灰度期继续盯此 p95**。
3. 摘要门控在合成 fresh 会话里 skip 率 26%(throttle 通道),自然长会话/学情刷新场景的 skip 率(设计预期 55-65%)要靠生产计数器在真实流量下读;十四天赎罪条款仍然有效。
4. Langfuse 名匹配 "summary"/"heartbeat" 两臂均 0:summary maintainer 的 LLM 调用名不含 summary(藏在 llm.complete 下)——**名字口径搜索不可靠,唯一权威读数=Prometheus 专用计数器**。
5. 行为 flag(DEEPTUTOR_MCQ_FEEDBACK_COMPACT / LUBAN_FOLLOWUP_FAST_TIER_ENABLED)本批全关,其收益不在此数;开闸走各自差分门+灰度序。

## 结论

无 flag 项(摘要门控+RAG 合并/超时+heartbeat 确定性门)在生产部署后:**每 turn 成本 -27.7%、异步尾巴 -33.5%(p50)、TTFVT 改善 13%、零回归红线触发**。42/42 turn 全 completed(聊天连续性+出题判分链)即为本次部署的 live 行为回归证据。

## 发布事实(审计线索)

- PR-2 #449(组B+C+093a4083)/ PR-3 #450(组D)/ #452(快赢包:泄露断言修+赎罪条款+语料备份 manifest)全部 CI 11/11 绿后合并。
- 部署#2 `34707970`:容器 just-now+env SHA+md5 三文件逐字+公网+observability+compact prompt 烘焙(en/zh)六层核验。
- 部署#1 曾出现「env 新代码旧」假绿(SSH 断在中段,镜像用旧代码构建完成),md5 比对揭穿后重跑治愈——**核部署必须 md5 比对容器文件 vs 宿主源码**。
