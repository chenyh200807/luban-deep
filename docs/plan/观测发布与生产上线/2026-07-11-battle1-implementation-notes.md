# Battle 1 实施偏离账本（append-only，新条目在顶）

> 规则：实施中遇到 edge case 一律选保守方案并在此记录偏离；每条含【任务/偏离/原因/影响面/验证】。fix-test 日志（含失败尝试）同记于此。

## 2026-07-11 对抗审查（内部异上下文证伪代理）：3 MAJOR 打穿→当日治本
- **审查方式**：fresh-context 对抗代理，8 攻击面，可执行复现+33 万例穷举对拍。Codex 异源对抗因其额度耗尽（重置 07-12 01:02）延后，命令：`node ~/.claude/plugins/cache/openai-codex/codex/1.0.5/scripts/codex-companion.mjs adversarial-review --background --base b3e9ab09 --scope branch`（在 deeptutor-battle1 目录）。
- **MAJOR-1（已修）**：单跑丢失旧双跑意外生效的 deep_question demote 守卫——可执行复现证实同输入新旧执行能力分歧（deep_question vs chat）。修=守卫确定性上移进 select_capability（_demote_non_question_deep_selection，谓词与旧 demote 分支逐条一致）；2 个 parity 测试（demote 命中+提交轮豁免）。**owner 待决**：该守卫对服务端选择是否应长期保留（删除=独立产品决策，非重构副作用）。
- **MAJOR-2（已修）**：count_tokens 单 pass 对病态 ASCII（hex 0.50/base64 0.46/emoji 0.52）低估→可构造 20 条 base64 消息真实爆窗（true=2.02×budget）。字符类启发式**无法**紧致上界 BPE（实测证死）——修=结构性安全：模糊带（approx≤budget<approx×2.2）经 count_tokens_precise（tiktoken，仅有界文本 ≤~25KB）终判+装箱终验用精确计数；热路径仍 O(n)。base64 攻击回归测试钉死。
- **MAJOR-3（已修）**：灰度 flag 开+轻模型配置时，mcq_grading/无 rubric case 判分轮（FAST 合法承载 structured_submission）吃轻模型且无 V1 权威覆盖。修=_mode_policy 对判分信号（scene∈{mcq,case}_grading 或 selection_reason==structured_submission）fail-closed 清空 fast_preferred_model；"判分永不吃轻"从注释升级为结构不变量+组合测试。
- **MINOR-B（已修）**：写线程判定从进程级名字前缀（sqlite-writer_0 多实例共名）改实例级 threading.get_ident() 捕获。
- **MINOR 记账未改**：①"flag 关=bit-for-bit"真实条件是 LLM_FAST_MODEL unset（utility_model 与 flag 正交，by design 但表述需准确）；②branch B prefetched 轮 3 条 WARNING 日志 spam→建议降 debug（批7）；③golden #1 锁的是反事实场景，建议补 candidate-is-None 不变量断言（批7）；④close() 生产不调用（单例无害，测试卫生）。
- **未打穿面（审查员验证法在案）**：回放并发 happens-before 反证自洽；19 读 fn 无 DML；think 状态机 33 万穷举+2 万 fuzz 逐字节等价；finalize no-op 证明"元数据门层互斥"比实施者声称更强；visibility 迁移新旧互操作安全。

## 2026-07-11 两个潜伏回放 bug（批4a 揭出，非引入；治本已落）
- **潜伏 bug①**：subscribe_turn 的 catchup 桥接"入队即推进 last_seq"——消费循环用同一 last_seq 去重，catchup 送出的每条事件**必然被自我丢弃**。该机制自诞生起从未成功投递过任何事件；旧 store 全局锁把竞争窗口压至 ~0（catchup 恒空）故休眠。W2-T2 解锁读路径后窗口变宽，测试对 44→67 顺序性 flake 揭出尸体。**治本**=catchup 改直接 yield（与跨 worker tail 同构），去重职责归消费循环单点。
- **潜伏 bug②**：turn_events 表无 visibility 列——**回放视图（backlog/catchup/tail/resume）丢 visibility 字段**，与 live fan-out payload 不等价；internal 事件回放后按"缺失=public"语义被当 public（泄漏隐患）。**治本**=加列迁移（legacy 行 '' 省略键保持历史形状）+ 写入/重建补齐，回放与 live 逐字段等价。
- **定位方法**：症状端逐层证伪（先疑测试替身→再疑事务→最后全时间线探针 commit/fanout/attach/catchup 打 monotonic 时戳）——探针实证 seq2 已 fan-out(nsubs=1)+catchup 已含[2] 却未达消费者，一步锁死消费端去重。
- **验证数字**：44→67 毒化对 8/8 全绿（修前 6/8 红）；session 域 114 passed（含新 visibility 往返测试）。
- **教训**：解除一把"顺手串行化一切"的全局锁=同时揭开它掩盖的全部时序假设；回放三消费面必须有字段等价测试而不只有 seq 等价。

## 2026-07-11 W3-T1/T2 消路由双跑+硬超时（批2）
- **实施**：orchestrator 新增公共 `select_capability`；`handle(context, *, preselected_capability=None)` 可选纯加法；turn_runtime 单次选择后把 selector **原值**传入（canonical 名仍只喂 turn 侧账本，按指挥官挑战）；场景分类 LLM 加 `DEEPTUTOR_ROUTING_LLM_TIMEOUT_S`（默认 6s，超时走既有 scene=None fail-open）。
- **失败尝试①**：初版无条件调 `select_capability` + 无条件传 kwarg → 89 个测试红。根因=旧代码的 getattr 防御是为 orchestrator 测试替身（只实现 handle）而存在。修：getattr 公共名保留 duck-typing（私有 API 依赖仍消灭），kwarg 仅预选真值时传。
- **失败尝试②**：12 个替身定义旧私有名 `_select_capability`（契约化石）→ 按公共契约重命名；替身 `handle(self, context)` 不收新 kwarg → 统一放宽 `**_kwargs`（62 处，test_unified_ws_turn_runtime.py + redteam 1 处）。改替身不改被测语义。
- **隐性消费者裁决**：第二跑的 `_prepare_preselected_capability_context` 对第一跑已选能力是冗余（语义路由主路径 :543-560 第一跑已备好提交/练习上下文，canonical 用 setdefault）；第二跑对第一跑决策的 demote 翻案权被移除=收权本意。demote/mcq-bypass 对客户端显式预选路径原样保留（无第一跑时 handle 自选全管线）。
- **登记**：tests/runtime/test_orchestrator_single_selection.py（4 用例含端到端 spy"路由 LLM≤1"）登记进两份 index.yaml capability domain；DEEPTUTOR_ROUTING_LLM_TIMEOUT_S 登记 env_registry；contract guard + env guard PASS。
- **验证数字**：单一选择 4/4；lifecycle 23/23（含超时降级+env 解析）；redteam 87/87；characterization 2 失败=基线预存在（stash 复测证实）。

## 2026-07-11 W1-T4 think剥离增量状态机（批1c）
- **实施**：`_ThinkStripStreamer`（clean/think_open/partial/orphan 四态+已决前缀折叠+跳扫规则），级联正则逐字保留只跑小尾部；oracle=旧 _stream_delta 整段重放（含 emitted clip，按指挥官挑战#1）。
- **验证**：600 例模糊对拍逐 delta 逐字节一致一次全绿+前缀单调+6 个定向用例；tests/tutorbot 目录级 before/after 失败集合完全一致（13 个预存在隔离污染项，非本改动引入；单跑全 PASS）——暗测试污染问题再次实证，归批 7/后续战役纳管。
- **登记去向**：tests/tutorbot/ 不在 CI shard；建议随批 7 登记进 luban_grading_engine domain（contracts/index.yaml:640 区）。

## 2026-07-11 W1-T2 count_tokens 单 pass（批1b）
- **偏离**：设计断言"CJK≈1 token/字是轻微高估"被离线校准**证伪**——cl100k 对中文实际 ~1.24 token/字，1.0 系数是 19-36% 低估（方向危险）。按设计 uncertainty#3 预案上调：ascii÷3 + CJK×1.3，实测中文散文 ratio 1.02-1.05、最坏混合技术文本低估 16%、英文高估（安全向）。
- **headroom 论证**：history budget=context window×35%，最坏 16% 低估→实际 ~42%，余量充足，无爆窗风险。
- **失败尝试**：测试预置期望值抄错（1236 vs 真值 936）导致一次假红，已用离线脚本重新生成全部真值。
- **验证**：test_context_builder.py 11 passed；session 全域+WS 回归 292 passed。

## 2026-07-11 W2-T1 PRAGMA synchronous（批1a）
- **偏离**：设计前提"运行时新连接回落 synchronous=FULL"在本机被证伪——macOS SQLite 3.51 编译带 `SQLITE_DEFAULT_WAL_SYNCHRONOUS=1`，WAL 库上新连接默认已是 NORMAL(1)（实测：fresh conn=2，WAL 后新 conn=1）。
- **裁决**：修复保留但语义从"性能修复"降为"跨环境确定性钉扎"——生产容器（Debian python 镜像）编译默认未验证，显式 PRAGMA 消除环境彩票；测试断言 WAL+NORMAL 不变量（本机非 RED，属不变量文档化）。
- **影响面**：`sqlite_store.py:_connect` +7 行注释+1 行 PRAGMA；生产收益待部署后在容器内 `PRAGMA synchronous` 取证（若容器默认已 NORMAL 则本刀零收益零风险）。
- **验证**：tests/services/session/test_sqlite_store.py 40 passed。

## 2026-07-11 执行方式偏离（全局）
- Fable/Opus subagent 均撞账号 session limit（21:20 SGT 重置）→ 批 1 起改为主控内联逐刀执行+每刀窄提交；设计与指挥官裁决仍为唯一施工蓝图。
