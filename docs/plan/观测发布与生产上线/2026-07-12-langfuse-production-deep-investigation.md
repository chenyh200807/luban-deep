# 鲁班智考生产 Langfuse 全量调查报告(2026-07-12)

> 调查者:观测调查 agent(只读,keys 未离开服务器)。数据:26,927 traces(2026-03-25~07-11)、336,292 observations;核心样本=turn.runtime 全量 3,736 条元数据 + 分层抽样 188 turn 完整解剖(4,125 嵌套 observations)。角色识别按 observation name + system prompt 指纹。复现脚本在 Aliyun /tmp 与本机 scratchpad。

## 十四项发现(证据→解读→置信度)

**F1|trace 延迟≠用户等待:每 turn 背 ~16s 异步尾巴(高)** — 用户可感 root p50:practice 13.3s / mcq_grading 20.3s / review 15.0s / None 4.3s;trace latency 却是 32/38/30/15s——差值=回复后异步链(learner_state.refresh 179/188 turn、summary_maintainer 175/188、taxonomy_classifier 51/188)。不挡用户(架构决定正确),但:①任何按 trace latency 的看板/SLA 虚高一倍;②每 turn 实占服务器 ~30s,并发天花板被尾巴吃掉一半。

**F2|>60s 长尾(8.6%)的极端值全是观测假象(高)** — 最差 36,050s 的 trace root 实跑 5.8s,被 session 级 heartbeat 观测在其后 10 小时挂进同一 trace 拉长(trace 上下文传播 bug)。真实业务长尾上限 ~173s。修观测接线即可让 p99 从 5,415s 回到 ~110s。

**F3|各 scene 用户等待构成(p50,188 turn 解剖)** — practice(13.3s)=检索/embedding 扇出 32 次(sum 15.4s,并行后墙钟 3.1s)+主生成 9.3s(630 tok);mcq_grading(20.3s)=前置 4.4s+**主生成 16.8s(prompt 4,678 tok/输出 1,277 tok)**——判分慢的主导项是输出长度;review(15.0s)=**followup 判定器 2 次串行 ≈8s**+主生成 9.2s;None(4.3s)=followup_resolution 1.9s+分类器。主生成吞吐 ~60-76 tok/s → **耗时≈输出 token/65,输出长度是第一决定因子**。

**F4|followup 判定器:review 每 turn 同输入串行调 2 次(41/45,高)** — 样例两次调用 prompt 同为 1,530 tok、背靠背 4.1s+5.9s(此即 Battle1 批 2 已消的双跑,样本为部署前)。单次画像:deepseek-v4-flash,p50 3.9s/p90 5.9s;**延迟与 prompt 大小基本无关(pt<1000 3.7s vs ≥1000 4.0s),慢在输出 p50=216 tok 的 JSON(含 rationale)**——这修正了 06-29 报告"慢=prompt 大 45%"的推断,B2 主攻应为输出瘦身。

**F5|summary_maintainer=最贵隐形角色,57% 调用产出 NO_CHANGE(高)** — 每 turn 回复后必跑,prompt p50≈10k tok,耗时 p50 7.8s;抽样 248 次:142 次(57%)输出就是"NO_CHANGE"(中位 9 字符)。**占样本内全部 turn LLM 成本 52%,是主生成的 3.5 倍**——全库最大单点浪费。

**F6|learner_state.refresh:每 turn p50 16s 异步链(高)** — 7,108 次全量;含摘要 LLM 7.8s+~8s 其他;另有 70 refresh 失败+29 Summary timeout。

**F7|检索面:每出题 turn 32 次调用,最大错误源(高)** — search_unified 50,353 次 p50 0.5s/p90 3.0s;ERROR 榜首=ReadTimeout 1,135+ConnectTimeout 165+Supabase 5xx 171。9/60 出题 turn 题库直出(全程无 LLM,root 2.2-7.4s)却同样烧 ~30 次检索。

**F8|heartbeat agent:1,510 次真实 LLM 调用只为报心跳(高)** — 838 prompt tok/2.9s/次,纯开销,且制造 F2 的 trace 污染。

**F9|Supabase health check 在热路径(中高)** — turn 内 0.6 次/turn(~0.3s/次)。

**F10|成本解剖(高)** — deepseek-v4-flash 占 85-90%;**gte-rerank 第二大**(单次喂 ~36k tok,峰值日占 22%);角色占比:摘要维护 52% > 主生成 15% ≈ rerank 14% > followup 4.5% > 分类器 1%;峰值日全是评测战役日,自然流量日仅 $0.3-0.9。

**F11|异常面(2,751 ERROR,高)** — 6 月 1,391 条为峰;检索超时/5xx ~1,470;5 月 Supabase 402 计费事故 450 条(已消);7-08 仍有 dashscope key 无效 burst;07-05 一波"account not in good standing"。

**F12|start_turn setup 干净(高)** — p50=11.3ms;唯一慢项 followup_resolution(1,324 turn 命中,p90 2.3s/p99 9.8s/max 24.2s)。

**F13|Battle1 部署前后对比:样本不足(4 turn),不下结论(诚实声明)** — 需 1-2 天流量后重跑(脚本可复用)。

**F14|TTFT 全库未埋(高)** — 所有 GENERATION 的 completionStartTime/timeToFirstToken 均 null。**无法回答"用户几秒看到第一个字"——观测体系最大盲区。**

## 速度加强清单(预期收益÷成本排序)

| # | 建议 | 预期收益 | 成本 | 级别 |
|---|---|---|---|---|
| 1 | review 去重 followup 判定器 2→1 | p50 -4s(-27%) | **已由 Battle1 批 2 修复,待 F13 复测确认** | — |
| 2 | followup/分类器**输出瘦身**(短枚举 JSON≤50 tok 去 rationale) | 单次 3.9→~1.5s | 低 | 接线(B2 已批,方向已按 F4 修正) |
| 3 | mcq_grading 主生成输出减半(判分结构收紧/分段流式) | p50 -6~8s(20.3→~13s) | 中 | 接线 |
| 4 | 埋 TTFT + 客户端真流式渐显 | 感知延迟砍到 TTFT 级 | 低 | 接线 |
| 5 | 检索扇出收窄/缓存;题库直出跳过全量扇出 | p50 -1~2s,p90 -5s,顺带砍最大错误源 | 中 | 架构 |
| 6 | health check 移出热路径 | -0.2~0.3s | 极低 | 接线 |
| 7 | Supabase 检索超时预算+快速降级 | p90 尾部 -3~7s | 中 | 架构 |
| 8 | 修 heartbeat trace 污染+改非 LLM 心跳 | 看板 p99 回真实,省 1,510 次调用 | 低 | 接线 |

## 架构优化建议(结构性)

1. **摘要维护器降频/门控(最大单点)**:57% NO_CHANGE+10k tok/次+52% 成本 → 改"有新学习证据才跑/每 N turn/先用便宜信号做门"。预期砍 ~40-50% 总 LLM 成本,每 turn 服务器占用 ~30s→~15s(并发再翻倍)。
2. **followup 判定收敛单一权威**:setup 的 followup_resolution+turn 内判定器,同一件事最多算 3 遍(§5.7 同构病)。
3. **rerank 瘦身**:减候选或只对最终路径 rerank。
4. **异步尾巴排队化**:refresh/摘要/分类放低优先级队列,战役日保护前台 turn。
5. **观测修正**:trace 封口口径/heartbeat 传播/TTFT 埋点——不修则一切速度结论继续被假象污染。
6. 模型分层对判定器/分类器主要收益在延迟(3.9s→亚秒)非成本。

## 数据局限

摄取延迟(部署后仅 4 turn);TTFT 字段全空只能近似推断;188 详情样本集中 07-05~07-11(现行架构);Langfuse 内账≠官方账单(历史覆盖率 ~18.6%),绝对成本只作相对比较。
