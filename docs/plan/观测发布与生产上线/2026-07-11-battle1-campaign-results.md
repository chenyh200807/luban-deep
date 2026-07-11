# Battle1 架构审计修复战役 — 成果记录（收线）

> **给后续 agent 的一句话**：这份记录说明"我们做了哪些优化、为什么、改了哪里、怎么验证的"。
> 战役全过程细节见同目录 `2026-07-11-luban-arch-audit-battle1-remediation-plan.md`（计划）+
> `2026-07-11-battle1-implementation-notes.md`（逐刀偏离账本+fix-test 日志）+
> `2026-07-11-luban-arch-audit-battle1-design-appendix.json`（5 家族手术设计+指挥官裁决）。

- **状态**: Implemented（分支 `perf/arch-audit-battle1-20260711`，10 commit，已合 origin/main via 本里程碑）
- **来源**: 2026-07-11 六专家架构审计（23 agent，17 条 MUST 全经独立对抗验证）
- **病因（指挥官第一性裁决）**: 系统不信任自己已拥有的单一真值与已签发的单一裁决——每个消费点以"全量重算 / 重复执行 / 手工复制 / 全局互斥"重复支付本已付过的成本，且把传输粒度错绑成持久化与计算粒度，使名义并发 64 塌缩为实测 ~10。

## 做了哪些优化（按收益排序）

| # | 优化 | 改在哪 | 解决什么 | 预期收益 |
|---|---|---|---|---|
| 1 | **删 SQLite 全进程全局锁** → 单写线程+常驻连接，19 个读走无锁 WAL 快照 | `services/session/sqlite_store.py` | 所有用户所有会话的读写此前串行过一把 `asyncio.Lock`，WAL 并发读能力被浪费 | 并发 ~10→逼近 64 的第一杠杆 |
| 2 | **清除事件循环 4 类同步阻塞** | `context_builder.py`(count_tokens 单 pass)、`tutorbot/agent/loop.py`(think 剥离增量状态机)、`api/routers/unified_ws.py`+`api/dependencies/rate_limit.py`(Redis→redis.asyncio)、装箱去 O(n²) | 同步 tiktoken 全量重编码 / O(n²) 流式正则 / 半死 Redis 冻结事件循环 1s / O(n²) 装箱 | 每 turn 省数十~数百 ms 事件循环阻塞，尾延迟下降 |
| 3 | **消路由决策双跑** → orchestrator 公共 select/execute 边界，每轮只选一次 | `runtime/orchestrator.py`、`services/session/turn_runtime.py` | 路由每轮跑两次，含重复 LLM 分类器（尤其 followup 判定器，占首答前阻塞 ~79%，p99 17-19s） | 路由段 LLM 计费砍半、TTFT 降 |
| 4 | **场景分类器硬超时** fail-open | `services/question_lifecycle_skills.py`（`DEEPTUTOR_ROUTING_LLM_TIMEOUT_S`=6s） | 慢 provider 挂死路由前置 | 消灭数十秒长尾 |
| 5 | **模型档位死接线接通** | `services/llm/config.py`(`resolve_fast_tier_model`)、`response_mode.py`、`capabilities/tutorbot.py`、`memory.py` | `preferred_model` 钩子全链铺好但永远为空，一个模型打天下 | 摘要/subagent 可降档省 3-10× 成本；打开 A/B 能力 |
| 6 | **输出端修正链收权** → `_finalize_visible_answer` 单一管道 | `tutorbot/agent/loop.py` | 8 级修正链在 4 处手抄、集合有差异（patch spiral） | 新增修正器=改一处；行为一致性有结构保证 |

## 额外治本（战役揭出的两个潜伏 bug）

被旧全局锁掩盖、解锁后才暴露：
- **回放 catchup 自毁**：`subscribe_turn` 的追赶桥接"入队即推进 last_seq"，消费端同 seq 去重把追赶事件全部自我丢弃——**该机制从诞生起从未成功投递过任何事件**。修=改直出 yield。
- **回放丢 visibility 字段**：`turn_events` 表无 visibility 列，回放视图与 live fan-out 不等价，internal 事件回放后按"缺失=public"有泄漏隐患。修=加列迁移+写入/重建，回放与 live 逐字段等价。

## 对抗审查（内部异上下文证伪代理，8 攻击面+可执行复现+33 万穷举）

打穿 3 个 MAJOR，当日全部治本（commit `13375f0f`）：
1. **单跑丢失 demote 守卫**（复现证实同输入新旧路由分歧 deep_question vs chat）→ 守卫确定性上移进 `select_capability`。**owner 待决**：该守卫对服务端选择是否长期保留。
2. **count_tokens 病态 ASCII 低估**（base64 0.46/hex 0.50 可构造真实爆窗）→ 模糊带经 `count_tokens_precise` 有界终判（结构性安全，非系数彩票）。
3. **判分轮吃轻模型**（灰度开时 mcq/无 rubric case）→ `_mode_policy` 判分信号 fail-closed；"判分永不吃轻"升级为结构不变量。

未打穿面（审查员验证法在案）：回放 happens-before 反证自洽 / 19 读 fn 无 DML / think 状态机 33 万穷举逐字节等价 / finalize no-op 元数据门互斥 / visibility 迁移新旧互操作安全。

**Codex 异源对抗未跑成**（其额度耗尽，07-12 01:02 重置）：`cd deeptutor-battle1 && node ~/.claude/plugins/cache/openai-codex/codex/1.0.5/scripts/codex-companion.mjs adversarial-review --background --base b3e9ab09 --scope branch`。

## 两个承诺数字（对结果负责）

1. 单 worker 并发 ~10 → 逼近名义 64（精确值待部署后微基准取证）
2. 每 turn 路由 LLM 调用减半（spy 断言"每轮≤1"钉死）

## 明确未做（挂账，非本战役范围）

- **W2-T3** CONTENT delta 批量落库 + 内存 seq 分配器（最重一刀，合并门=live 3 轮断线重连实测）—— 这是并发天花板再抬一截的关键，**下一个战役优先**
- **W1-T1** token 估算增量缓存、**W1-T5** session adapter async 化
- **批 7**：事件循环 lag 哨兵、W5 golden 测试登记、微基准取证（把"~10→64"从推断变实测）
- 六专家审计的其他 MUST（供给消费 supply manifest 反射闸、编译管道脱单机、CI 暗测试纳管、金标 150 条人工标注）见 `2026-07-11` 审计报告

## 遗留的 MINOR（批 7 收）

- branch B prefetched 轮 3 条 WARNING 日志 spam → 降 debug
- finalize golden #1 建议补 candidate-is-None 不变量断言
- "flag 关=bit-for-bit" 精确条件是 `LLM_FAST_MODEL` unset（utility_model 与 flag 正交）
- `SQLiteSessionStore.close()` 生产不调用（单例无害，测试卫生）
