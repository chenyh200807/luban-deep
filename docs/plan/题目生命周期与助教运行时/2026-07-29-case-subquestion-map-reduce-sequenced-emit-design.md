# 案例题按小问 Map-Reduce + 顺序流出 — 执行器设计文档

- **日期**: 2026-07-29
- **状态**: Draft（第二拍立项交付物；只设计不实现）
- **基线**: main（#587 已合入：`deeptutor/tutorbot/response_mode.py:64-104` 案例结构形状路由 deep）
- **owner 需求原话**: "第一问已经有答案了就可以开始输出，第3第4问继续在后台运作，有答案了就输出"
- **目标**: 多小问案例题 deep 答疑的 TTFT 从 ~50s（静默检索期）降到 ~15s 量级；总时长 ≈ 最慢小问；质量不降。

---

## 0. 现状测绘（为什么现在是 ~50s）

多小问案例题粘贴 → #587 结构判据（`response_mode.py:73` `len>=120 且 「问题:」`）选 deep →
`build_mode_execution_policy` 给出 `workflow="full_agent_loop"`、`max_tool_rounds=4`
（`response_mode.py:309-323`）→ `TutorBotCapability.run`（`deeptutor/capabilities/tutorbot.py:150`）→
`manager.send_message`（`deeptutor/services/tutorbot/manager.py:960`）→
`AgentLoop._process_message`（`deeptutor/tutorbot/agent/loop.py:3937`）→
`_run_agent_loop`（`loop.py:2160`）。

关键串行链（一个 4-5 小问的案例）：

1. grounded RAG prefetch（`loop.py:4356 _maybe_prefetch_grounded_rag`）— 1 次检索。
2. agent loop 第 1..N 轮：模型判断「5 个小问的证据不够」（`loop.py:2192-2194` 注释实证），
   连续发 rag 调用把 `max_tool_rounds=4` 打满，每轮 = 1 次 LLM 往返 + 1 次检索，全程零 public content。
3. 收束轮（`loop.py:2243-2276` fall-through-to-understanding）才开始产出整篇答案 →
   第一问的第一个字要等**全部小问的检索都结束**。
4. 流出侧还有 80 字起播门（`capabilities/tutorbot.py:957-968 _should_start_public_delta_stream`）。

TTFT ≈ (prefetch + 3~4 轮检索往返) ≈ 40~50s；总时长 ≈ 所有小问检索之和 + 一次整篇生成。
病根是**执行形状**：N 个彼此独立的小问被塞进一条串行 agent loop。

---

## 1. 触发谓词与单一权威

### 1.1 判据（复用 #587 结构判据，收紧为 ≥2 小问）

新增**纯函数**（零 I/O、零 LLM、确定性）：

```python
# deeptutor/tutorbot/response_mode.py（与 select_response_mode 同模块、同权威族）

@dataclass(frozen=True)
class CaseSubquestionPlan:
    background: str                      # 首个小问标记之前的题面背景（含事件描述）
    subquestions: tuple[SubquestionSpec, ...]   # (ordinal_label, text, span)
    marker_style: str                    # "问题N：" | "问题：+编号列表"

def detect_case_subquestion_plan(user_message: str) -> CaseSubquestionPlan | None:
    ...
```

判定条件（全部满足才返回 plan，否则 `None`）：

- 长题面：`len(text) >= 120`（与 `response_mode.py:73` 同阈值，不另起第二个阈值权威）；
- 结构化小问段：匹配 `问题\s*[0-9一二两三四五六七八九十]{0,3}\s*[:：]` 的编号段 **≥2**，
  或单个「问题：」后跟 `^\s*[1-9][.、）)]` 编号列表 ≥2 项（#587 测例
  `tests/services/test_tutorbot_response_mode.py:177-196` 的生产形状正是后者）；
- 每个切出的小问段非空且 ≥6 字（防把标点噪声切成"小问"）；
- background 非空（案例题必有事件背景；无背景 → 更像题组，不触发）。

**误判方向不对称性**（继承 `response_mode.py:68-72` 的论证）：漏触发 = 维持现状串行 deep（无损）；
错触发在执行器内还有第二道 fail-closed（§2.1 前置条件不满足回落 `_run_agent_loop`）。
regex 在这里**只做结构抽取、不裁决内容真值**（`teaching_modes.py:247` 抗体；切分复述学生原文，
不生成任何事实断言）。

### 1.2 单一权威放哪：`build_mode_execution_policy`，新增 workflow 值

- **fast/deep 选择不动**：`select_response_mode`（`response_mode.py:170`）继续是 fast/deep 唯一裁决，
  多小问案例本来就命中 `deep_query_shape`。
- **执行形状收在 `ModeExecutionPolicy.workflow`**：`ModeWorkflow`（`response_mode.py:10`）新增第三值：

  ```python
  ModeWorkflow = Literal["single_shot_with_prefetch", "full_agent_loop", "case_subq_map_reduce"]
  ```

  `build_mode_execution_policy`（`response_mode.py:276`）新增可选参数
  `subquestion_plan: CaseSubquestionPlan | None` + `map_reduce_enabled: bool`；
  仅当 `selected_mode=="deep"` 且 plan 非空且 flag 开启时产出：

  ```python
  workflow="case_subq_map_reduce",
  execution_path="tutorbot_case_subq_map_reduce_policy",
  max_tool_rounds=2,        # per-subquestion 检索预算（>1 ⇒ 每个子调用保留收束轮语义）
  latency_budget_ms=60000,  # per-subquestion 硬预算（观测口径，非中断器；见 §2.4）
  ```

  其余字段与 deep 分支一致（`allow_deep_stage=True`、`preferred_model` 恒空——deep 链只跑主模型的
  硬不变量原样继承，`response_mode.py:306-308`）。

- **为什么不是新 workflow 之外的方案**：
  - 不新增 executor selector / router 层——`workflow` 字段就是现成的"执行形状"声明位，
    turn.md:112-115 已把 execution_path 作为公开观测口径；新增一个值是 additive。
  - 不放 `question_lifecycle_scene`——scene 是 question-domain 业务事实权威（判分/出题/澄清），
    "答疑执行形状"是 response-mode policy，域不同（`response_mode.py:230-233` 同款划界论证）。
  - 不新增 capability——turn.md 硬约束 1 与"TutorBot 是业务身份不是 transport"（turn.md:50）；
    执行形状变化不改变 capability 身份。

### 1.3 双调用点与重算约定

`build_mode_execution_policy` 现有两类消费者：
`TutorBotCapability._mode_policy`（`capabilities/tutorbot.py:1059`）与 turn_runtime canonical
mode-selection（`turn_runtime.py:5414` 只选 fast/deep，不建 policy）。plan 检测在
`_mode_policy` 内调用一次并写进 `session_metadata["mode_execution_policy"]["workflow"]`
（经 `capabilities/tutorbot.py:221-231` 现有通道下传 manager → `runtime_metadata`）。

`AgentLoop` 在 dispatch 处**用同一纯函数确定性重算 plan**（拿到 `workflow=="case_subq_map_reduce"`
时重新调 `detect_case_subquestion_plan(current_message)`），而不是序列化 plan 对象下传——
同一纯函数、同一输入、同一输出，这是仓库已有的合法模式
（`response_mode.py:214-233`：`active_object_requires_deep_mode` 被 start_turn 与 `_mode_policy`
双调用，单一权威=函数本身）。loop 端重算失败/为 None → fail-closed 回落 `full_agent_loop`
（消费者只读、不自建第二判据）。

### 1.4 与判分链的相位关系（scene 前置事实闸）

dispatch 位置在 `loop.py:_process_message` 的既有序列**之后**，优先级从高到低：

1. `_run_case_grading_direct`（`loop.py:4283`）— 判分 scene 已被 turn_runtime 盖章的作答提交轮，
   走判分主链，**先于且完全旁路** map-reduce；
2. `_maybe_run_exact_rag_fast_path`（`loop.py:4296`）— exact 题库命中快路径；
3. prefetched exact authority（`loop.py:4371-4418`）— 原题官方答案覆盖整案例
   （`covered_subquestions[].authoritative_answer`，`loop.py:1510`）时确定性作答；
4. fast 分支（`loop.py:4419`）；
5. **【新】map-reduce dispatch**（workflow 命中 + 前置条件满足）；
6. 兜底 `_run_agent_loop`（`loop.py:4499`）。

defense-in-depth：`detect` 之外，dispatch 处还消费结构化事实闸——
`question_lifecycle_scene ∈ {case_grading, mcq_grading}` 或本轮为 submission action 时不触发
（这些轮根本到不了第 5 步，但闸要显式写出防未来重排序）。

---

## 2. 执行计划

### 2.1 拆解（确定性，不用 LLM）

`detect_case_subquestion_plan` 的切分结果直接就是执行计划：

- `background` = 首个小问标记前的全部文本（案例背景 + 事件）；
- `subquestions[i]` = 第 i 个编号段的原文（含学生自己的编号字样）。

**前置条件（loop 端 dispatch 时逐条验证，任一失败 → 回落串行 deep，记 trace
`subq_map_reduce_fallback_reason`）**：

- 重算 plan 非空且小问数 ∈ [2, 8]（>8 视为异常粘贴，串行处理更稳）；
- 本轮无 media 附件（多模态子调用拆分是后续阶段，v1 不做）；
- `_prefetched_exact_question` 未覆盖本案例（覆盖时第 3 步已经短路，双保险）。

### 2.2 子调用形状：复用 `_run_agent_loop`，不造轻量单发

每个小问一个**独立的 `_run_agent_loop` 调用**（`loop.py:2160`），不是裸 LLM 单发：

- **保留自带检索**：子 loop 自己决定是否调 rag、查什么（`max_tool_rounds=2`），
  per-sub 的 `rag_rounds`/`rag_saturation` 账本独立（`loop.py:2187-2204`），
  不跨子调用共享饱和判定（共享会把"兄弟查过了"误判成"我查过了"）。
- **收束轮语义原样继承**：`max_tool_rounds=2 > 1` ⇒ `closure_round_enabled=True`
  （`loop.py:2243`），检索打满仍无答案时先收束再失败（律4，turn.md:181-185）；
  `forced_closure_round` marker 是 per-sub `runtime_metadata` 私有（见下），聚合导出为
  `subq_forced_closure_ordinals` 观测字段。
- **消息构造**（prompt-cache 友好）：

  ```
  system(ContextBuilder 同款) + history(只读共享) + runtime_instruction(共享)
    + user: 【案例背景】{background}\n【本轮只解答】{subquestions[i].原文}
    + system(子调用合成指令): 只回答该小问；背景仅供理解；不要复述其他小问；不要输出总起/总结段。
  ```

  共享前缀（system+history+instruction）逐字节一致 → openai-compat provider 的 prompt cache
  在 N 个子调用间命中前缀（与 `loop.py:2196-2199` 保 cache 前缀的既有纪律同向）。
- **runtime_metadata 隔离**：每个子调用拿 `dict(runtime_metadata)` 深拷贝入口副本
  （`_run_agent_loop:2172` 本来就 copy，但 `external_runtime_metadata` 回写通道
  `loop.py:2171,2210,2263` 必须断开——per-sub 的 `turn_failure`/`forced_closure_round`/
  `_prefetched_exact_question` 绝不许互相污染，聚合由 orchestrator 统一收）。
- **会话状态只读**：子调用**不各自 `_save_turn`、不写 session**（否决项 §6.2-③）。
  turn 结束时一次性 `_save_turn`：user message + 拼接后最终 assistant 文本；
  子调用的工具 transcript 不进 session history（N 份 transcript 会把后续轮 context 撑爆；
  与 exact fast path 只存最终文本的既有先例同形，`loop.py:4323-4331`）。
- **并发上限**：`asyncio.Semaphore(3)`，按小问顺序启动（问 1 最先拿到 slot，保 TTFT）。

### 2.3 顺序缓冲 emit（sequenced emitter）

新增 orchestrator 方法 `AgentLoop._run_case_subquestion_map_reduce(...)`，内部结构：

```
per-sub delta 通道:  sub[i].on_content_delta → asyncio.Queue[i]（终止哨兵 None）
emitter 协程（唯一 on_content_delta 消费者，单写者）:
    for i in 0..N-1:
        emit 确定性小节头 "## {subquestions[i].ordinal_label}\n"
        drain Queue[i] → 外层 on_content_delta   # i 已终止则一次性排空=缓冲重放
        emit 小节尾换行
```

语义保证：

- **问 1 完成即流出**：问 1 的 delta 从它的第一个 token 起实时流出（emitter 指针在 0）；
- **问 2 先完成则缓冲**：Queue[1] 积压，指针移到 1 时一次性排空（用户视角=瞬间打出）；
- **外层 delta 序 = 拼接终态序**：`streamed_public_text` 是逐小问拼接的严格前缀
  （turn.md:144 对齐契约的前提，见 §3.2）；
- **单写者不变量**：只有 emitter 触碰外层 `on_content_delta`，
  capability 侧 `_on_content_delta` 的 buffer/gate 机制（`capabilities/tutorbot.py:487-518`）
  零改动即可工作；小节头 `## 问题N` 令 `_should_start_public_delta_stream` 的
  起播正则/80 字门快速满足（实现时把 `问题\s*[0-9一二…]+` 加入 `tutorbot.py:967` 起播正则，
  1 行 additive）。
- **进度投影**：每个小问启动/完成时经 `_on_progress` → `stream.progress` 发
  public-safe `status_kind=turn_status` 投影（"正在解答第 N 问（共 M 问）"），
  turn.md:143 已允许该形状（understanding/writing 是例举非穷举）；纯 UI 提示级，
  不携带任何 authority。

### 2.4 单问失败 → 占位诚实标注继续（partial-failure 语义）

- 子调用产出 `final_content=None` + per-sub typed `turn_failure`（`loop.py:541 _record_turn_failure`
  的既有 kinds：`tool_budget_exhausted`/`provider_error`/`provider_timeout`/
  `model_empty_answer`/`model_output_truncated`）或超 per-sub 预算（60s，
  `asyncio.wait_for` 包子调用 → 归一为 `provider_timeout`）时：
  - **不 fail 整 turn**；emitter 在该小问槽位输出**占位段**，然后继续后续小问。
- **占位文案单一权威**：新增 `map_subquestion_failure_to_public_text(kind)`，
  与 `turn_runtime.map_turn_failure_to_public_text`（`turn_runtime.py:671`）同族、同文件旁置，
  kind→文案映射复用同一张表加"第 N 问"前缀（例：`"（第N问本轮没有完成解答，请把这一问单独再发一次）"`）。
  这不是"per-branch 模板冒充答案"（律4 禁令，turn.md:168-169）——它是 **typed failure
  结构化事实支撑的替换级产出**，与 terminal mapper 同一合法性来源，且占位段永远显式自标失败、
  绝不冒充解答内容。
- **全部小问失败** → 不拼占位墙：整 turn 落标准 typed failure（kind 取首个非空 per-sub kind），
  走既有律4 链路（`loop.py:4513-4544` → capability failure payload `tutorbot.py:637-669` →
  turn_runtime 律4 RESULT 处理 `turn_runtime.py:6225-6248`），`status=failed`、不计费。
- **部分成功** → turn `status=completed`；**不设 turn 级 `turn_failure`**
  （设了会被 `turn_runtime.py:6259-6264` 强制翻 failed）；失败明细进 result metadata：

  ```
  subq_map_reduce: {total, succeeded, failed: [{ordinal, kind}], ttft_ms, per_sub_ms: [...]}
  ```

  `kind` 只留类别码（公开边界不泄原始错误体，与律4 error_code 同纪律）。

### 2.5 收尾（reduce = 确定性拼接，不加二次 LLM 总结）

`final_response = "\n\n".join(小节头 + per-sub finalize 后文本或占位段)`。

- **per-sub 各自过 `_finalize_visible_answer` 全链**（`loop.py:970-1039`，
  `finalize_path="case_subq_map_reduce"`——该参数仅观测标签，不门控修正器，
  遵守 `loop.py:988-992` 的钉死约定）；拼接后**不再整体重跑** finalize
  （修正链幂等性未按整篇拼接文本验证过，且 `_strip_leading_meta_narration` 只该吃每段开头独白）。
- 拼接头（`## 问题N`）是确定性 runtime 产物，复述学生自己的编号，无内容真值断言。
- **不做 LLM 二次总结/润色**（否决项 §6.2-⑥）：会把总时长退化回"max(小问)+整篇生成"，
  且引入第二个可编造层。

---

## 3. turn 模型整合（关键难点）

### 3.1 UsageLedger scope：ContextVar 继承天然聚合，须钉住线程纪律

- usage 聚合的机制现状：turn_runtime 在 `_run_turn` 入口进入
  `observability.usage_scope(scope_id=turn_id, ...)`（`turn_runtime.py:5489-5495`），
  scope 是 **ContextVar**（`langfuse_adapter.py:634 _current_usage_scope.set`）；
  每次 LLM 调用经 `record_usage`（`langfuse_adapter.py:669-702`）：
  `scope.add(...)` 内存聚合 + `UsageLedger.record_usage_event(turn_id=scope.turn_id, ...)` 落 SQLite。
- **并行子调用的聚合是免费的**：`asyncio.create_task` / `asyncio.gather` 复制当前 context，
  所有子调用的 `record_usage` 命中**同一个** `_UsageScopeState` 与同一 `turn_id`——
  UsageLedger 行天然归属本 turn，`get_current_usage_summary`（`langfuse_adapter.py:729`）
  的 turn 终态汇总、billing capture 折算（`turn_runtime.py:1308
  _billing_capture_amount_from_usage_summary`）零改动。
- **必须钉住的实现约束**：`_UsageScopeState.add`（`langfuse_adapter.py:277-297`）是裸 `+=`，
  只在事件循环单线程下安全。契约条款：**子调用的 usage 记录必须发生在事件循环线程**
  （现状即如此：provider streaming 在 loop 线程回调）；若未来任何 provider 把 usage 回调
  挪进 `to_thread`，须先给 `add` 上锁。验收测试：并行 N 子调用 fake provider，
  断言 scope 总量 = 各子调用之和、UsageLedger `has_usage_for_turn` 单 turn_id。
- manager 端注意：`external_turn_id` 存在时 manager 不再另开 scope
  （`manager.py:1172-1181` 的既有分支），map-reduce 不改此契约。
- 观测：`llm_stream_telemetry` 的 `call_site` 新增 `"subq_map_reduce"`（`loop.py:2279-2284`
  `_record_llm_stream_telemetry` 传参即可），`iteration` 编码为 `sub_ordinal*100+round`
  或新增 `sub_ordinal` 字段（择一，实施时定，additive）。

### 3.2 流式顺序保证与 `result.response` 终态拼装（turn.md:144 对齐）

- turn_runtime 消费的是 capability 的**单一事件流**（`turn_runtime.py:6174 async for`），
  事件序 = emit 序；`streamed_assistant_content` 按序累计（`turn_runtime.py:6305-6306`）。
  emitter 的单写者设计（§2.3）保证 public content delta 序 == 小问序。
- **终态 = 各小问拼接**：capability 的 `final_response = response or "".join(chunks)`
  （`tutorbot.py:670`）中 manager 返回值 `response` 即 §2.5 的拼接文本；
  `chunks`（capability 收到的全部 delta）与之逐字节一致（emitter 只流出 finalize 后文本——
  见下一条流式-终态一致性设计）。
- **流式-终态一致性的实现选择**：per-sub 答案先跑 finalize 再流出。即子调用运行时
  delta **不直接进 emitter**，而是 per-sub 聚满 → finalize → `_emit_visible_text_deltas`
  （`loop.py:653`）切块送 emitter 队列。代价：每个小问内部仍是"完成后一次性流出"；
  收益：**问 1 的 TTFT = 问 1 完成时刻（~15s）**而非整案完成时刻（~50s），owner 目标达成，
  且流文本恒等于终态拼接，turn.md:144 的同源对齐天然成立、
  `_replace_public_result_response_with_stream`（`turn_runtime.py:410-448`）的
  suffix 豁免分支根本不会触发。
  - *为什么不做小问内 token 级实时流*：`_run_agent_loop` 的检索轮独白/收束轮修复都可能
    撤回已流文本（`loop.py:2469-2499` repair 路径），单答案流式靠 capability 的
    起播/熔断门兜底；多小问拼接下一旦问 2 流到一半被 repair 重写，已流出的前缀无法撤回，
    终态与流文本异源 → 直接违反 turn.md:144。per-sub finalize-then-emit 把这个坑整个绕掉。
    小问粒度（问 1 十几秒出全文）已满足感知目标；小问内 token 流是后续可选优化
    （需先解决 repair 撤回语义）。
- mobile `done` 前合成 result 的兜底（`turn_runtime.py:6265-6292`）、旧客户端 result 投影
  （`turn_runtime.py:325`）均消费同一份拼接流文本，无需改动。
- citations：per-sub 的 sources 经共享 `_on_tool_result` 汇入 `citation_sources`
  （`tutorbot.py:552-560`），citation bundle 在 result 物化前统一装配（turn.md:38 契约不变）。

### 3.3 部分失败的 turn 终态

| 情形 | turn status | 学员所见 | 计费 |
|---|---|---|---|
| 全部小问成功 | `completed` | 拼接答案 | 正常 capture（chargeable） |
| 部分成功 | `completed` | 成功小问答案 + 失败小问占位诚实标注 | 正常 capture（已交付可用内容；占位段不是失败文案兜底整篇） |
| 全部失败 | `failed`（律4 typed failure） | terminal mapper 文案 | 不计费（turn.md:200 失败文案不可计费） |

裁决理由：`completed with 诚实标注`（而非新增 `partial` 状态）——turn FSM 终态集合是
硬契约（turn.md:30、律4-5 CAS 终态吸收，`turn_runtime.py` update_turn_status 语义），
新增第四终态波及 store/replay/billing observer/mobile read-model 全链，收益只是观测粒度，
而观测粒度已由 `subq_map_reduce` metadata 覆盖。部分成功轮的
`chargeable_assistant_content` 判定走既有 observer（turn.md:104），占位段不影响
"完整可交付回答"判定的理由：交付物是"逐小问解答集合"，成功小问即真实交付；
全失败路径已兜住"零交付仍计费"的假绿。

### 3.4 active_object / 判分链 / exact_authority 衔接

- **多小问案例答疑不注册 active_object**：TutorBot 自由文本解析是 display-only
  （turn.md:68），拆出的小问**不得**被物化成 `question_followup_context` / `question_set`
  active_object——这是答疑不是出题，注册会让下一轮"我答问题1：…"被误路由成对 bot 自产
  参考答案的判分（未签名参考不得成为判分权威，turn.md:74 + S4 案例 `loop.py:1508` 注释链）。
  现有 authority-gated 注册路径（exact authority `tutorbot.py:881-926`、practice generation
  `tutorbot.py:808-880`）原样保留，map-reduce 不新增 writer。
- **turn-start 相位零改动**：demote/保活判据（turn.md §S4(b)）发生在 turn_runtime，
  早于 capability 执行；map-reduce 只是 capability 内执行形状。
- **exact_authority**：整案命中在 dispatch 前短路（§1.4 第 2/3 步）。子调用**内**的 rag
  exact 命中（`loop.py:2388-2403`）per-sub 隔离消费（本小问答案用原题证据）；
  turn 级 `turn_summary["exact_question"]`（`tutorbot.py:537-538`，经共享 `_on_tool_result`）
  在多子调用下有互踩风险 → 契约：**≥2 个不同 `question_id` 的 exact 命中时，
  turn 级 exact_question 置空、`authority_applied=False`**（fail-closed 不注册，
  防把 A 小问的原题登记成整案 active_object）；单一命中保持现状。
- **判分链**：作答提交轮永远先被 scene 盖章走 `_run_case_grading_direct`（§1.4），
  map-reduce 与判分零交集；下一轮学员针对某小问追问/作答时，因本轮未注册 active_object，
  行为与今天"对普通 deep 答疑追问"完全一致（无回归面）。

---

## 4. admission 契约对齐（指挥官裁决：权力/证据相称律）

2026-07-29 指挥官裁决：注入/决策点须声明
`(criteria_kind: 语义锚|结构化事实|flag|fragment, payload_level: 提示|指令|替换, evidence_ref)`，
汇点断言"载荷 ≤ 判据允许上限"（碎片判据封顶提示级；替换级只许结构化事实）。
本执行器的全部新增注入/决策点声明如下（step① admission 类型化落地前，本表即契约文本；
落地后逐点转为声明对象过 guard）：

| # | 注入/决策点 | criteria_kind | payload_level | evidence_ref | 相称性论证 |
|---|---|---|---|---|---|
| 1 | workflow=case_subq_map_reduce 选择（§1.2） | 结构化事实(确定性 marker 计数+切分 span,非语义猜测)+flag | 指令(执行形状路由,不改任何终局文本) | `detect_case_subquestion_plan` 返回的 marker spans,进 trace `subq_plan_markers` | 路由级权力 ≤ 结构化事实;且有 loop 端 fail-closed 回落 |
| 2 | 子调用合成指令"只答第 N 问"（§2.2） | 结构化事实(切分产物原文引用) | 指令 | plan.subquestions[i].span | 指令只限定范围,不注入事实断言 |
| 3 | 小节头 `## 问题N`（§2.3,进入学员可见正文=替换级家族） | 结构化事实(学生自己的编号原样复述) | 替换(确定性拼装终局文本骨架) | plan.subquestions[i].ordinal_label | 替换级 ← 结构化事实,合法;头部零内容真值 |
| 4 | 失败占位段（§2.4） | 结构化事实(per-sub typed `turn_failure.kind`) | 替换 | per-sub turn_failure 记录 + `subq_map_reduce.failed[]` | 与 terminal mapper 同一合法性来源;显式自标失败 |
| 5 | 进度投影"正在解答第 N 问"（§2.3） | flag(执行进度状态位) | 提示(public-safe status,不进正文/终态) | emitter 指针状态 | 提示级 ≤ flag,合规 |
| 6 | 全失败 → turn typed failure kind 归并（§2.4） | 结构化事实(N 个 typed kinds) | 替换(经既有唯一 terminal mapper) | subq failures 列表 | 复用既有汇点,不新建 mapper |

**禁止清单**（相称律的反面钉死）：切分 regex 的匹配结果不得用于改写小问原文、
不得据此合并/重排/删减学生的小问、不得生成"你其实想问的是…"类语义改写——
碎片/结构判据永远不携带对学生输入的改写权力。

防复发：Phase 1 落地时附 contract-guard 域测试
（`tests/tutorbot/test_case_subq_admission_contract.py`）：枚举执行器全部进入学员可见文本的
写入点，断言每一处都能回指到上表 evidence_ref 类型（结构化事实对象非裸 str）。

---

## 5. 灰度路径

单一 flag：`DEEPTUTOR_CASE_SUBQ_MAP_REDUCE_MODE ∈ {off, shadow, live}`，默认缺省=off，
**未显式配置 fail closed**（与 `LUBAN_M35_ARTIFACT_SHADOW_ENABLED` 同款纪律，turn.md:92）。
cohort 授权只认服务端可信注入，客户端 config 不得自授权（M35/PGO 同款，turn.md:92-93）。

### Stage 0 — off + 谓词影子（零成本，随 Phase 0 代码合入即开）

- flag=off 时执行链零变化；`_mode_policy` 处并行记录 observe-only trace：
  `subq_plan_shadow = {would_trigger, subq_count, marker_style}`（不含题面原文，防 PII 扩散）。
- 产出：真实流量中触发率、切分分布、误触发样本（人审 20 例），校准 §1.1 判据。
- 验收：差分测试证 flag=off 时对既有 turn 全链 byte-identical（复用
  `tests/services/test_tutorbot_response_mode.py` + 新增差分断言）。

### Stage 1 — shadow（后台跑 map-reduce 只记录不投放，预算封顶）

- flag=shadow：主链仍走串行 deep 并投放；tracked background task（turn.md:43 的
  tracked-task 纪律）跑真实 map-reduce 执行，产物只落 trace/Langfuse
  （`subq_shadow_result = {per_sub_ms, ttft_ms, failures, cost}` + 影子答案入内部观测，
  **不进任何 public 事件、不进 session、不写 active_object、不计费**——usage 记录带
  `capability="tutorbot_subq_shadow"` 隔离口径，防污染 billable 对账）。
- **预算闸**：shadow 双倍消耗 LLM，服务端 cohort（qa/test/operator）+ 每日 shadow 次数上限
  （建议 50 turn/日）；生产真实学员流量不进 shadow。
- 产出：同 turn 双臂配对数据（同题、同上下文、同模型）——这是 Stage 2 eval 的
  最干净配对来源。

### Stage 2 — eval 对比（质量不降 + TTFT 数据；执行前过 eval-design skill 排雷）

设计要点（防假绿，按 eval-design 纪律逐条声明）：

- **配对与臂公平**：同一题面双臂（串行 deep vs map-reduce），同模型、同温度、同 KB、
  同 runtime_instruction；题集 = Stage 0 影子命中的真实生产案例（≥30 题，覆盖 2/3/4/5 小问
  分层）+ 既有病例回归题（87ad350f 形状）。臂间唯一差异 = 执行形状（这正是被测变量；
  确认无夹带：prompt 内容差异仅 §2.2 合成指令，需在报告中原文列出）。
- **质量指标（主）**：per-subquestion 维度的裁决——异源 judge（非答案生成模型的另一家 provider，
  memory: 异源裁判揪同源放过的编造），盲评（judge 不见臂标识）、位置对换（A/B 顺序随机），
  逐小问打 {覆盖、正确性、教材口径一致}；教材权威可裁处引入 KB 证据对照
  （memory: 事实权威阶梯=教材>面板）。**禁**整篇 pairwise "哪个更好" 单指标
  （长度偏置 + 拼接格式偏置双重污染）。
- **质量红线（证伪判据）**：map-reduce 臂 per-sub 正确性劣于串行臂超过非劣界
  （建议 −5pp，95% CI）即 NO-GO；特别盯"跨小问依赖题"（问 3 需引用问 2 结论的题）——
  这是 map-reduce 的结构性弱点，题集须显式含 ≥5 道此类题并单独出数。
- **TTFT 指标**：不自建计时器——直接用既有
  `server_turn_start_to_first_useful_content_ms`（turn.md:151，
  `turn_runtime.py:6140-6167` 已在生产采集），双臂同口径；同时报 p50/p90 总时长与
  `subq_map_reduce.per_sub_ms`。harness 陷阱：eval 并发会把 provider 排队时间算进 TTFT——
  逐题串行跑，或双臂交替同速率。
- **成本指标**：UsageLedger 按 turn_id 出双臂 token/cost；map-reduce 臂背景重复 ×N，
  预期 input 膨胀，验收线 = median cost ≤ 串行臂 2.5×（prompt cache 命中应显著压低，
  实测为准，不信静态推断）。
- **方差**：非确定性生成 → 每题每臂 ≥2 次采样，报告臂间差的置信区间而非点估计。
- **计费身份**：eval runner 走既有 eval 身份纪律（AGENTS §Eval Runner Identity），
  不产生会员活跃。

### Stage 3 — cohort 放量

- flag=live + 服务端 cohort：qa/operator 全量 → 内部账号 → 真实学员 5% → 50% → 100%，
  每档 ≥3 天生产观测。
- 放量看板（既有 BI/Prometheus 通道）：TTFVT 直方图（`record_first_useful_content`，
  `turn_runtime.py:6159-6167`）、`subq_map_reduce.failed` 率（红线 <5%/sub）、
  turn failed 率对比、成本/turn、投诉信号。
- **回滚 = flag→off**，零数据迁移（本设计无 schema/状态写入面）；
  任何 SEV：占位段刷屏、拼接错序、计费异常 → 立即回滚，事故样本转 Stage 2 回归题集。

---

## 6. 风险清单与否决项

### 6.1 风险（保留但受控）

| 风险 | 后果 | 控制 |
|---|---|---|
| 跨小问依赖（问 N 引用问 N−1 结论） | 子调用看不见兄弟答案，可能答非所指 | v1 不做依赖推断（保确定性）；背景全文共享缓解大半；eval Stage 2 专项出数；若实测劣化 → v2 引入"前序小问已完成答案注入后续子调用"（代价：尾部小问退化半串行，需重新过 admission 表） |
| 成本膨胀（背景 ×N 重复） | input token ~N× | prompt cache 前缀设计（§2.2）+ Stage 2 成本验收线 + 小问数上限 8 |
| provider 并发限流 | 子调用排队，总时长劣化 | Semaphore(3)；`chat_with_retry` 既有重试；per-sub 60s 预算兜底 |
| 检索重复（各 sub 独立查相近 query） | RAG 负载 ×N | v1 接受并出观测数（per-sub rag_rounds 汇总）；饱和账本不共享是有意为之（§2.2） |
| `_UsageScopeState.add` 线程安全 | 并发计数丢失 | 契约钉死 usage 记录留在事件循环线程（§3.1）+ 聚合断言测试 |
| turn 级 exact_question 互踩 | 错误 active_object 注册 | ≥2 不同命中 fail-closed 置空（§3.4） |
| 小问内无 token 级流式 | 单个超长小问内部仍有等待感 | per-sub 进度投影（§2.3）；token 级流式列为 v2（须先解 repair 撤回语义，§3.2） |
| 慢尾小问拖总时长 | 总时长 ≈ max(sub) | 这就是设计目标上界；per-sub 60s 预算 + 占位继续保整体不悬挂 |

### 6.2 否决项（及理由，防后人重提）

1. **LLM 拆题** — 否决。拆题 LLM 调用本身吃掉 3~5s TTFT 预算；产出不确定（同题不同拆），
   eval 不可复现；admission 相称律下"语义猜测判据 → 决定执行结构+终局文本骨架"是
   碎片判据携带替换级权力的典型病；确定性 regex 可审计、可回归（#587 已证此形状可靠）。
2. **无序 emit（谁先完成谁先流）** — 否决。学员看到问 3 答案先于问 1 是阅读灾难；
   更硬的理由：流文本序 ≠ 终态拼接序 ⇒ `result.response` 与已流内容异源，
   直接违反 turn.md:144 对齐契约（`_replace_public_result_response_with_stream` 会用
   流序文本覆盖终态，历史 read-model 与学员所见永久错序）。
3. **子调用共享 conversation history 可写態 / 各自 `_save_turn`** — 否决。
   session.messages 并发追加竞态（memory: 并行提交者会扫走未提交工作同族病）；
   N 份工具 transcript 入 history 撑爆后续轮 context；且违反"canonical session 只写
   真实用户输入+终态答案"纪律（turn.md:119）。
4. **每个小问开真 turn（N 个 child turn_id）** — 否决。turn FSM/billing observer/
   session read-model/replay 全部按单 turn 契约铸死（turn.md 硬约束 4、律5 CAS）；
   usage ContextVar 聚合已免费解决多子调用记账，child turn 是零收益的契约爆破。
5. **在 turn_runtime 层做拆分与并行** — 否决。turn_runtime 朝 transport-only 瘦身是
   既定方向（turn.md §QTPK S1"TurnRuntime 朝 transport-only 瘦身"）；执行形状属
   capability/loop 层；turn_runtime 只消费单一事件流的既有契约（§3.2）恰好使它
   对 map-reduce 完全无感——这是本设计最大的架构红利，不许倒灌。
6. **reduce 端 LLM 总结/润色拼接文本** — 否决。总时长退化（+整篇生成时间），
   引入第二编造层（拼接是确定性的，总结是概率的），且总结文本会覆盖已流出内容
   （再次撞 turn.md:144）。
7. **把拆出的小问注册成 question_set active_object** — 否决。turn.md:68：普通文本
   题目解析 display-only；bot 侧无签名答案权威，注册即为下一轮误判分埋雷（§3.4）。
8. **新增 capability / 新 WS 路由 / 新 streaming 协议** — 否决。turn.md 硬约束 1/2；
   执行形状变化全部收在 `ModeWorkflow` 既有声明位。
9. **单小问失败即 fail 整 turn** — 否决。与 owner 目标（继续后续小问）直接冲突；
   已交付的成功小问被 terminal mapper 文案整体丢弃 = 把部分成功洗成全失败，
   比诚实占位更不诚实。全失败仍走 typed failure（§2.4），假绿面无扩大。

---

## 7. 分阶段实施计划与验收判据

### Phase 0 — 契约与谓词（1 PR，零行为）

- 内容：本设计文档落 `docs/plan/`；`detect_case_subquestion_plan` 纯函数 + `ModeWorkflow`
  第三值 + `build_mode_execution_policy` 新参数（flag 缺省 off ⇒ 生产不可达）；
  turn.md additive 修订（TutorBot 规则节：新增 execution_path 值、workflow 值、
  subq_map_reduce metadata 字段、partial-failure completed 语义、多 exact 命中 fail-closed 条款）；
  Stage 0 谓词影子 trace。
- 验收：谓词单测（≥15 正例含 #587 生产形状 `test_tutorbot_response_mode.py:177-196`
  同款、≥10 反例：单小问/纯长文/MCQ 题组/判分提交轮）；flag=off 差分测试全链 byte-identical；
  `tests/api/test_unified_ws_turn_runtime.py` 等 turn.md 必测项全绿。

### Phase 1 — 执行器（1-2 PR，flag 后）

- 内容：`AgentLoop._run_case_subquestion_map_reduce`（dispatch 接线 §1.4 位次、
  sequenced emitter、per-sub 隔离与预算、partial-failure、
  `map_subquestion_failure_to_public_text`、usage 聚合、telemetry 导出）；
  起播正则 1 行扩充（`tutorbot.py:967`）；admission guard 域测试（§4）。
- 验收（fake provider 可控时延，全部确定性断言）：
  - 问 1 首 delta 时刻 < 问 2 子调用完成时刻（TTFT 语义）；
  - 问 2 先于问 1 完成时，外层 delta 序仍为 1→2（缓冲重放）；
  - `result.metadata.response` == 外层 delta 拼接（byte-identical）；
  - 单问 typed failure → completed + 占位段 + `subq_map_reduce.failed` 正确；
  - 全失败 → turn failed + terminal mapper 文案 + 不计费；
  - usage scope 总量 = Σ 子调用（并行下）；session history 仅 user+终态 assistant 两条；
  - 无 active_object / question_followup_context 写入（display-only 断言）；
  - 前置条件不满足 → 回落串行 deep 且 `subq_map_reduce_fallback_reason` 记录。

### Phase 2 — shadow 与观测（1 PR + 运行期）

- 内容：flag=shadow 通道（tracked background task、预算闸、shadow usage 隔离口径）、
  Langfuse/BI 导出、TTFVT 看板切片（按 execution_path 分组——字段已在既有 metric 维度内）。
- 验收：shadow 开启时公开事件流/终态/计费与 off 完全一致（差分）；shadow 数据在
  Langfuse 可查且带完整 per_sub 时延；预算闸达到上限后 shadow 静默停。

### Phase 3 — eval（无代码，执行 Stage 2 设计；先过 eval-design skill）

- 验收（GO 判据，全部满足才进 Phase 4）：per-sub 正确性非劣（−5pp 界内，95% CI）；
  跨小问依赖题单项非劣；TTFT p50 降幅 ≥50%（预期 50s→≤20s）；总时长不劣于串行臂；
  成本 median ≤2.5×；eval 报告含臂间 prompt 差异原文与全部否决样本。

### Phase 4 — cohort 放量（运维）

- 验收：每档 cohort ≥3 天，看板四指标（TTFVT/per-sub 失败率/turn failed 率/成本）无劣化；
  100% 后保留 flag ≥2 周作回滚肌肉；收官时 memory + methodology-log 记录终态，
  Stage 0 影子代码在毕业 PR 中拆除（60% 清理自律）。

---

## 附：你没问但（盲区主动申报）

1. **小问内 token 级流式是本设计刻意让出的地盘**（§3.2）：owner 若期望"问 1 内部也逐字打出"，
   需要先解决 agent loop repair 路径的流撤回语义，工作量与本设计相当，建议作为独立第三拍。
2. **deep_question capability 未覆盖**：本设计只接 TutorBot 答疑链。deep_question 的出题/判分
   有自己的执行形状；若未来"多小问案例判分"也要并行化，是另一份设计（判分链的
   score authority 并行化风险等级完全不同）。
3. **`_looks_like_deep_query` 的 300 字纯长文分支**（`response_mode.py:75`）不触发 map-reduce
   （无小问标记 ⇒ plan=None），这是有意的：无结构锚点的长文拆分只能靠 LLM，已被否决项①封死。
