# COMMANDER.md — 2026-08-09 生产事故三族终审(宏观架构指挥官)

生产 SHA 2496329261df。输入:F1.md / F2.md / F3.md 三份家族专家报告。本文所有 file:line 均为本人对仓库 `/Users/yehongchen/orca/workspaces/deeptutor/gar` 当前 checkout 的**独立抽查**,不转引专家报告。

---

## §1 五条 load-bearing 断言独立核验

### ① F1:orchestrator scene 权威向 turn-start 决策让位 — **CONFIRMED(路径修正 + 一处重要补充)**

- 专家写的路径 `deeptutor/services/session/orchestrator.py` **不存在**;实际文件是 `deeptutor/runtime/orchestrator.py`。行号本身对得上。
- 实证:`deeptutor/runtime/orchestrator.py:368` 进入 `lifecycle_scene == "practice_generation"` 分支后,:397-400 `if semantic_route == "deep_question" and next_action in {"route_to_followup_explainer", "route_to_grading"}` → :407-411 `_map_canonical_decision_to_capability`,**绕过** :412-415 的 `_prepare_practice_request_context`。:617 docstring 亲证:「any other deep_question route (e.g. `route_to_followup_explainer`) → no prep」。
- **补充(专家漏报)**:practice_generation 分支内 scene 权威其实有**三个**让位口,不止一个:(a) :376-386 `is_unresolved_switch_followup` → 默认聊天能力(context-continuity 不变量,有正当理由);(b) :387-396 `ask_clarifying_question` → 默认聊天能力;(c) :397-411 followup/grading 让位(本案病灶)。**收权刀必须只切 (c) 中的 `route_to_followup_explainer`**,(a)(b) 受跨能力上下文连续性不变量保护,不得连坐。
- F1 附带断言「route_to_grading 让位在此 scene 下是死代码」:**CONFIRMED with caveat**。scene 权威判 practice_generation 前已查作答 payload(`question_lifecycle_skills.py:1295-1320`:`_looks_like_full_case_answer_submission` / 两个 free-text 正则 / `resolve_submission_attempt`),故 scene=practice_generation 蕴含"无作答"→ 缓存决策 route_to_grading 理论上不可能同现。caveat:两层消费的 context 来源(显式 question_context vs metadata 回落)存在理论分叉可能,故我裁决**保留** route_to_grading 于让位集合(见 §3)。

### ② F1:「解析」否定词一票否决出题意图 — **CONFIRMED**

- `deeptutor/services/semantic_router.py:131-140` `_QUESTION_EXPLAINER_MARKERS`,:134 即 `"解析"`。
- :1121-1126 `_has_explicit_practice_generation_intent`:`if _has_question_explainer_intent(text): return False` — 位于任何肯定性判据**之前**,一票否决。
- :1136-1140 `_has_question_explainer_intent` = 裸 `marker in text` 子串测试,**零否定句感知**。「不要提前给答案和解析」必然命中。与 F1 本地重放结论一致。

### ③ F2:tutorbot 模板短路后主 LLM 永不运行 — **CONFIRMED**

- `deeptutor/capabilities/tutorbot.py:442-445` `build_question_lifecycle_clarification_response(...)`;:446-452 非空 → `_emit_lifecycle_terminal_response(execution_path="tutorbot_lifecycle_clarification")` → `return`。
- 主 LLM 机器(`_on_content_delta`,`call_kind="llm_final_response"` 流式装置)定义在 :487 之后 — return 发生在其之前,主 LLM 确实永不运行。
- 上游配套断言同步核验:`deeptutor/services/question_lifecycle_skills.py:342-350` 在 `low_information_exam_query` 为真时**照样调用** LLM scene proposal,:379-391 却无条件 `return scene=None + needs_clarification=True + business_gate_result="blocked_low_information_exam_query"`,proposal 只进 `llm_scene_candidate` 观赏字段 — LLM 付费判对、结果被弃,CONFIRMED。
- 模板文案 :900-907(「这道题我这边还没拿到完整的题干和选项…」)与 :898-899 注释自承「此罐头"何时该出"是 A 收权问题——回指应落主 LLM 而非这里」逐字在档,CONFIRMED。
- task#14 Layer2 逃生口 `_low_information_query_can_use_active_question`(:801 起,:812-823 注释)存在且依赖 `requested_question_item_index` 对 ACTIVE 题组解析 — 题组未注册即空转,CONFIRMED。

### ④ F3:num_questions>3 闸 + 既有并行样板 — **CONFIRMED(闸比专家说的还窄)**

- `deeptutor/capabilities/deep_question.py:754` `if int(num_questions or 1) > 3: return False`(topic 版);:710 followup 版同款。
- **补充**:`_should_use_lightweight_topic_generation`(:740-761)的准入不止 fast+N≤3,还要求:无 followup context(:751-752)、题型限 choice/judge(:755-757)、topic 需权威锚且 resolved≠raw(:758-761)。即轻路径窄门比 F3 报告描述的更窄——**从答题面板追问入口出题(携带 followup context)永远进重路径,哪怕只出 1 题**。
- 并行样板:`deeptutor/agents/question/coordinator.py:830` `_lightweight_batch_generate`,:845 注释自述 fallback 逐题并行,:933 `results = await asyncio.gather(*[_one(t) for t in templates])` — 生产在跑。
- 串行病灶:coordinator.py:541-626 `_generation_loop` 朴素 `for` 循环逐题 `await generator.process`(:555-576),`generated_questions` 作为 `previous_questions` 串行去重链(:573,:598-600),零并行。CONFIRMED。
- deadline 链同步核验:`turn_runtime.py:2671-2673`(75/180/300 三档常量)、:2841-2859 watchdog `task.cancel()` 处决式终止、:6571-6582 CancelledError 分支调 `_safe_terminal_assistant_content(status=...)` **未传 failure_kind**、:710-723 `_safe_terminal_assistant_content` status≠completed 一律弃流换模板(:720-721 注释「provisional transport, never canonical」)、:674-695 `map_turn_failure_to_public_text` kind 枚举 = {tool_budget_exhausted, provider*, model_empty_answer, model_output_truncated, orphaned_on_restart} — **`deadline_exceeded` 缺席**,F3 §7 违规判定 CONFIRMED。

### ⑤ F1:批量解析器无 arity 检查 — **CONFIRMED**

- `deeptutor/services/question_followup.py:1155` `resolve_submission_attempt`:批量解析仅 `len(items) > 1` 启用(:1163);带序号分支要求 `numbered and items`(:1168)——单题上下文 items=[] 直接跳过;末尾兜底 :1201-1208 无条件 `_extract_single_submission(message, normalized)` 落 `kind:"single"`。「1、c 2.c 3.c」对 items=[] 的 stale 单题 → 蒸馏成 "C",无任何「序号数 > 上下文题数」检查。
- 配套确认:ambiguous 形状已存在(:1192-1199,单答多题方向),下游已消化 ambiguous(`question_lifecycle_skills.py:1324-1326` `kind=="ambiguous" → return None`;:366-378 `ambiguous_multi_submission` → needs_clarification)。F1 Step3「零新增分支」成立。

**五条全部 CONFIRMED,无 REFUTED。** 唯一事实性修正:orchestrator 路径应为 `deeptutor/runtime/orchestrator.py`。

---

## §2 架构裁决:几个病,病因命名

### 病灶拓扑

- **F1 与 F2 的主干是同一个病,且字面上是同一次断裂**:F2 的断链轮(10:32「第二题答案」)消费的正是 F1 出题轮(10:23,trace 2184bed7)未注册的同一个题组、同一个 session。turn-0 病灶完全共享:同一个「解析」假阳性(semantic_router.py:1125-1126)+ 同一次 scene 权威让位(orchestrator.py:397-411)+ 同一次零注册(deep_question followup 出口回写旧对象)。F1 的误判(3 答蒸成 C 判旧题)和 F2 的拒答(逃生口无题组可锚)是**同一未注册题组的两次下游塌方**。
- **F2 另含一个独立病灶**:确定性闸的话语终局权(question_lifecycle_skills.py:379-391 弃 LLM 判定 + tutorbot.py:442-452 模板吞轮)。说它独立,是因为即便 F1 修好(题组注册、逃生口通电),这个终局权在其他场景(memory:预算耗尽收束轮、≥8 次同族修复史)仍会咬人——它是元病在**消费侧**的又一实例,不是 F1 病灶的重复。
- **F3 在机制层是独立病**(编排预算病:入口收单到 50、编排串行闷烧、deadline 处决式砍头,三层互不通气,`N×单题耗时 vs 预算`无人裁决)——它与 F1/F2 不共享任何代码病灶。但它的**终局形态**(8 题成品被 :713-723 + :2857 无条件清零、失败无 typed marker)与 F1 的「scene 判对被让位」、F2 的「LLM 判对被闸弃」是同一个元病的第三张脸。

### 裁决:机制层三群病灶,架构层两个病,第一性层一个元病

架构层两个病:
1. **裁决权与登记权碎裂**(F1+F2 主干):「这轮是不是出题轮」有 4 套并行判据(scene 权威 / action 家族 / semantic_router 显式闸 / turn_runtime fallback),仲裁规则让被词表毒化的那套压过判对的那套;「bot 出的题」有 3 条产线只有 2 条接了唯一注册链。
2. **交付合同缺失**(F3):预算、编排、入口三个权威各自正确、互不通气,预算撞墙时没有部分交付协议。

**元病一句话(第一性,不含模块名)**:

> **这个系统把"防御"实现成了"终局":每一道为防止产出坏结果而设的确定性护栏,都被同时授予了无偿作废上游正确成果——正确的语义判定、已生成的合格内容——的权力;而全系统没有一条守恒律要求"已经做对的工作必须被登记、被交付、或至少留下类型化的尸检痕迹"。于是每次事故里所有组件都在按设计正常工作,合力把真值扔进无痕的黑洞。**

三族的同构证据:F1 scene 权威判对(confidence 1)被让位;F2 最便宜的 LLM 判对(0.95)被闸清零、1700 tokens history 预算已分配却无人消费;F3 LLM 11/12 次干成活、8 题成品在货架上被连锅倒掉且不留 kind。**"下游确定性层无条件否决/丢弃上游已做对的结果"就是元病**——该直觉正确。补一刀精确化:元病不只是"否决",而是"否决无成本、无痕迹":否决方从不需要证明自己比被否决方更接近事实(闸是 regex,被否决的是带完整 history 的 LLM;让位方是被否定句毒化的子串测试,被让位的是 confidence 1 的确定性 scene 权威),事后也无 typed marker 可审计。

---

## §3 收口方案终审(逐项:采纳/修形/降级/缓行)

| 项 | 裁决 | 理由与修形 |
|---|---|---|
| F1① 删 orchestrator 让位 | **采纳,但收窄刀口** | 只从 :397-400 集合中删 `route_to_followup_explainer`;**保留** `route_to_grading`(§1① caveat:近死代码但保硬约束40 的双保险,删除收益为零、理论风险非零);**不得动** :376-396 的 unresolved-switch 与 clarify 两个让位口(受 context-continuity 不变量保护,memory:禁 fail-closed)。这是删一个字符串的刀,不是删整个分支的刀。 |
| F1② 退役 `_has_explicit_practice_generation_intent` 三处 | **采纳** | 与①不是同一刀但同向:①收仲裁权,②删第二把尺。②落地后 4 套判据全部回归 scene 权威同款(`looks_like` + 无作答),4 实现→1 判据。专家明确拒绝"给词表加否定感知"(那是第 N+1 把尺)——正确,符合"不把语义降级成模式匹配"。风险:历史上该 veto 可能为拦「讲讲这类题」而设,但此类消息 `looks_like_practice_generation_request` 本就不命中(F1 已论证),且 fallback 路径(turn_runtime.py:1499)裸用 looks_like 跑了很久没出事,是活体先例。 |
| F1③ 批量 arity 归 ambiguous | **采纳,必须显式单向** | 只在「可解析出的带序号答案数 **>** 上下文题数」时返回 ambiguous;**答少于题(部分作答)是合法提交,不得拦**(§4-d)。复用 :1192-1199 既有 ambiguous 形状,零新分支,与 E8 成对称闭环。 |
| F2 6a 删模板短路,fall-through 主 LLM | **采纳,但降为 PR3 并加权限面约束** | 方向正确(84d1efc58 已在 deep_question 侧做过同款,这是补齐 tutorbot 侧,decider −1)。**约束:闸只被撤"话语面终局权",不撤"数据面权限否决"**——`exact_question_blocked_reason` 等 metadata 必须原样保留,exact-question 权威继续锁死,主 LLM 在无权威状态下运行并带 prompt 提示。否则 §4-f 的安全边界破口(索要考试原题→主 LLM 现编)。这是 6a 不能进 PR1 的原因:需要独立的防编造 live 回归。 |
| F2 6b 题组注册收口到轮末唯一持久化点 | **降级:本次不做 writer,改 observe-only marker** | **这是 F1 Step4 与 F2 6b 的正面冲突点,专家们没有互相看到**:F1 把 tutorbot.py:833-880 的"从渲染输出解析题组再注册"定性为待收编的旁路豁免;F2 6b 却要把同款输出解析**推广**为轮末通用机制。过"新增层有罪推定":6b 在唯一汇点新造一个基于文本模式匹配的"本轮是否产了题"decider——把语义事实降级成 regex,且有真实回归通道(bot 复述/terse re-present 旧题会被误判为新题组改写 active_object,f5d95d0df 家族)。裁决:PR1 的路由修正已让出题走结构化注册产线(deep_question.py:5290-5345),6b 要防的残余场景只剩"讲解轮 LLM 自发越权出题"——对此先落 **observe-only typed marker(`unregistered_question_set_emitted`)** 于轮末,拿生产数据证明频次后再议注册权(memory:observe-only 旗标每跳显式导出;单一权威收口 playbook:测绘→收权)。 |
| F2 6c 澄清对象退役 | **采纳,随 6a** | 6a 落地后 `question_lifecycle_clarification` 写 active_object + 真题压栈的 mirror-state 自然消亡,属同刀清理。 |
| F3 A 重路径生成段并行化 | **采纳,主修** | 复用 :933 同款 gather,`asyncio.Semaphore(4)` 封顶,标准库原语非新调度器。代价(失去 previous_questions 串行去重)可接受——ideation 已按 concentration 去重(coordinator.py:288-300)。idea 两轮合一/放宽 BATCH_SIZE 一并做,低风险。 |
| F3 B deadline 90% 收束交付 | **采纳,与 A 合为同一刀** | A 把 for 循环改成并发任务集后,B 就是把 `gather` 写成 `asyncio.wait(tasks, timeout=T)` + 收集 done + 差额声明——**同一处代码,不是第二个 PR**。分开做反而两次动同一函数。约束:收束权留在 capability 内,turn_runtime 180s 仍是最后防线(F3 已自警,同意);T 用 capability 本地常量,**不**跨层向 turn_runtime 讨预算(那会造第二 terminal authority)。已知残缺:若 turn 实际吃 fast=75s 档,本地常量收束不到——记入"本次不修"的 deadline 权威不同源病,不在这刀里治。部分交付以 completed 终态单条正文交付,不碰流式合同(微信客户端渲染 result.response 为终态,memory)。 |
| F3 C 入口 clamp + typed marker | **拆开:marker 必修进 PR2;clamp 采纳(50→20);首句声明砍掉** | `deadline_exceeded` marker 是 AGENTS.md 铁律的现行违规(§1④),补齐与既有 turn_failure 机制同构,零风险必做。clamp 50→20 一行。"回复首句声明本轮出 N 道"是文案工程,A 落地后 20 题物理可达,声明无必要——砍(less is more)。 |

**重复/同刀归并总结**:F1①+② = 一把刀的两刃(收仲裁权+删冗余尺),同 PR;F3 A+B = 字面同一函数,同 PR;6a+6c 同 PR。**全案零新增状态、零新增层**,唯一新增物是两个 typed marker(deadline_exceeded、unregistered_question_set_emitted)——marker 是审计痕迹不是 authority,过有罪推定。

---

## §4 举一反三压测(思想实验,对最终方案)

**a) 「我选B,再出3题」(判分+出题混合)** — 方案后行为:判分优先,正确。三重保险仍在:scene 层 `_FREE_TEXT_MCQ_OPTION_SELECTION_RE` 命中"我选B"→ has_answer_payload → 不判 practice_generation(question_lifecycle_skills.py:1295-1320);action 层 `_practice_generation_action_for_explicit_request` 本就要求 `resolve_submission_attempt` 为 None(question_turn_policy.py:494-503,F1② 不动这一条);orchestrator 保留的 route_to_grading 让位是第三重。**方案漏洞(既有,非回归)**:"再出3题"半句被静默丢弃,判分轮不会衔接出题——记 backlog,不在本战役修。

**b) 「出5道题,不要解析」** — F1② 后「解析」不再毒化,route_to_generation ✓,N=5。PR2 前串行 ≈39+5×13.7≈107s<180s 可活;PR2 后 ≈60s。**方案漏洞**:「不要解析」是否接到 `require_explanation=False`(coordinator.py:547)未核实——大概率仍附解析,体验瑕疵非事故级,记 live 观察项。

**c) 答题面板入口「换个考点出题」** — 携带旧题 followup context。`looks_like` 应命中("出题");scene=practice_generation;PR1 后不再让位 → 出题产线。`_requests_current_question_exclusion`(deep_question.py:708)已有排除当前题机制。**方案漏洞**:①topic 是否真锚到"不同考点"是生成质量问题,PR1 不保证,live 回归必测;②§1④ 发现携带 followup context 必进重路径——出 3 题也吃 Idea Agent 全套(≈70s),PR2 后可忍,长期应放宽轻路径准入(记本次不修)。

**d) 3 题只答 2 题(「1、c 2.c」对 3 题组)** — items=3>1 → `_parse_batch_submission` 出 2 答 → kind=batch 部分提交 → E8 merge(turn_runtime.py:6949-6960)逐项并回。F1③ 的 arity 闸是**单向**(答数>题数才 ambiguous),此场景不触发——方案已按 §3 修形显式化。无漏洞。

**e) 出 10 题成功后批量作答 10 题** — 生成侧 PR2 覆盖。判分侧:`_parse_batch_submission` 对 10 items 结构上可行,但**判分链若逐项走 LLM 解析/讲评,10 项串行可能复演 F3 的预算病**(b20d5cbd1 清剿是判"对错口径",不是判"耗时")。**方案漏洞(真缺口)**:本战役三 PR 均未覆盖判分侧 N=10 的耗时;裁决:PR2 live 回归必须加"出10题→答10题"全链一案,若判分轮>90s 则把 F3-A 的并行化同款刀开进判分链(下一战役,先测量后动刀,memory:修复不得插队度量)。

**f) F2 修后 needs_clarification fall-through 是否放进该拒的(索要考试原题)** — 这是 6a 最大的真风险:模板拒答虽僵化,但**不会编造**;主 LLM 无权威却被要求回答「2025真题第3题答案」时可能现编(memory:排除法泄露/编译库现编家族)。§3 修形已立边界:**闸保留数据面否决(exact-question 权威锁死、metadata 原样导出),只撤话语面终局权**,并在 prompt 注入"无该题真值时明说拿不到、请学员补题干"。live 回归钉子:「2025年真题第3题答案」→ 回复必须不含具体选项/答案断言(异源裁判核,memory:异源必须)。此钉不绿,6a 不上线。

---

## §5 实施序(按病因排序:连锁消解最多、风险最低者先)

### PR1 — 出题轮裁决权收权 + arity 对称闭环(治病1主干,F1+F2 的 turn-0 同源病灶)
改动:F1②(semantic_router.py:1121-1129 函数退役 + :654-657、:812-822 合取项删除;question_turn_policy.py:496-497 删)→ F1①(orchestrator.py:397-400 集合删 `route_to_followup_explainer` 一个字符串)→ F1③(question_followup.py:1201 前加单向 arity 闸归 ambiguous)。
回归:
- 既有测试:`tests/services/test_semantic_router.py`、`test_semantic_router_eval_cases.py`、`test_question_lifecycle_scene_derivation.py`、`test_question_lifecycle_scene_single_writer.py`、`test_question_followup.py`、`test_question_turn_policy 族(qtpk)`、`tests/runtime/test_orchestrator_autoroute.py`、`test_orchestrator_single_selection.py`、`tests/core/test_deep_question_active_object.py`。
- 新增钉子(进上述既有文件,不建新文件):(i) F1 原文消息+活跃单题 → route_to_generation 且注册 question_set;(ii)「1、c 2.c 3.c」+单题 → ambiguous 非 single-C;(iii)「我选B,再出3题」→ grading;(iv)「1、c 2.c」+3 题组 → batch 部分提交不被 arity 闸拦。
- live(test2,答题面板追问入口三条件复现):重放 F1 脚本 → 出 3 题 → 批答 3 → 全判;再发「第二题答案」→ 应经 task#14 逃生口正常应答(**此案即 PR1 单独治愈 F2 事故实例的证据**)。
连锁消解:F1 误判、F1 学情污染源头、F2 断链轮、逃生口通电,一刀四消。全部是删除,回归风险最低。

### PR2 — 出题交付合同(治病2)+ 尸检痕迹补铁律
改动:F3 A+B 同刀(coordinator.py:541-626 `_generation_loop` → `asyncio.wait(tasks, timeout=本地常量)` + Semaphore(4) + done 收集 + 差额声明;idea BATCH_SIZE 放宽);C1 typed marker(turn_runtime.py:6571-6596 分支落 `turn_failure={"kind":"deadline_exceeded"}`,:684-694 mapper 加档);C2 clamp(question_followup.py:788,50→20)。
回归:
- 既有测试:`tests/agents/question/`、`tests/services/test_terminal_error_semantics.py`、turn_runtime 族;新增 mapper 单测(deadline_exceeded → 专属文案)与 coordinator 部分交付单测(注入 1 个挂死任务 → 返回 N-1 题+差额)。
- live:test2「出10道选择题」→ <90s 全量交付;注入低预算复现收束 → 部分交付+`deadline_exceeded` 在 trace/BI 可见;§4-e 全链案(出10答10)耗时测量。
明确:**不动 180s 数字,不动 watchdog,不造跨层讨预算协议。**

### PR3 — 确定性闸撤话语终局权(治元病消费侧实例,风险最高故最后)
改动:F2 6a(tutorbot.py:442-452 短路删除 → fall-through 主 LLM,gate 结果降级为 prompt 提示;orchestrator.py:444-453 needs_clarification 分支只写 metadata 不改选 capability——注意保留数据面权限 metadata 原样)+ 6c(`question_lifecycle_clarification` 不再写 active_object)+ 6b 降级件(轮末 observe-only `unregistered_question_set_emitted` marker)。
回归:
- 既有测试:`tests/tutorbot/test_agent_loop_question_lifecycle.py`、`test_case_grading_generation_falls_through.py`(同族先例)、`tests/services/test_question_lifecycle_skills.py`、`test_question_lifecycle_acceptance.py`。
- live 三钉:(i)「第二题答案」(PR1 后应已好,验证 6a 不劣化);(ii)「2025年真题第3题答案」→ 不编造(异源裁判核,§4-f,不绿不上线);(iii) 预算耗尽收束轮家族一案不再吐罐头。

### 本次不修(留档,防"顺手治百病")
1. **deadline 预算权威不同源**(turn_runtime.py:2808-2817 读 requested mode,执行用 effective mode)——独立 authority 病,牵动全部 timeout 档位,需单独测绘;本案歪打正着未致害。
2. **tutorbot.py:833-880 输出解析旁路注册收编**——F1 Step4 中期项,等 `unregistered_question_set_emitted` 数据。
3. **轻路径准入放宽**(followup context/题型/topic 锚三条窄门,deep_question.py:751-761)——PR2 后重路径已可活,放宽是性能优化非止血。
4. **「不要解析」→ require_explanation 接线**、**判分轮衔接"再出N题"半句**——体验层 backlog。
5. **判分链 N=10 并行化**——先度量(PR2 live 案)后动刀。
6. **F1 事故已写入的学情污染(learner_state 摘要)清洗**——数据修复作业,走运维通道,不混入代码 PR。

---

## §6 对 owner 追问的终答:「是系统能力问题还是架构限制?」

**裁决:三族事故中,模型能力零责任;全部损失由架构自伤造成。这不是"能力不够所以护栏兜底",而是"护栏拥有终局权所以能力被作废"。**

证据链(全部出自三份报告的 trace 实证 + 本人源码复核):

1. **能力在每一个关键点上都已做对。** F1:场景权威确定性判出 practice_generation(confidence 1,trace 在档);出题 LLM 实际产出 3 道合格新题;对照组同 SHA 同日 3 题全判——识别、生成、判分三种能力当天都被证明存在。F2:全链最便宜的 deepseek-v4-flash 只凭 history 就判对 mcq_grading(0.95,理由完整复述三题时间线)。F3:12 次 LLM 调用 11 次产出合格题,唯一瑕疵(q_1 畸形)被 repair 链 8 秒自愈。
2. **作废能力成果的,全部是确定性代码,且每一处都无条件、无痕迹。** 「解析」二字的裸子串测试否决出题意图(semantic_router.py:1125-1126);仲裁规则让被毒化的缓存决策压过 confidence 1 的 scene 权威(orchestrator.py:397-411);regex 闸把付费买来的正确 LLM 判定塞进观赏字段(question_lifecycle_skills.py:379-391);罐头模板在主 LLM 的 1700 token history 预算已分配的情况下终结轮次(tutorbot.py:442-452);watchdog 把 8 道成品连协程栈一起蒸发且不留 failure kind(turn_runtime.py:2857、:713-723、:674-695)。
3. **同一句话从不同的门进来结局不同,是架构病的铁证。** F1 对照组从普通聊天入口进,同样的话判对了;事故组从答题面板追问入口进,判错了——差别不在用户、不在模型,在于哪一组 decider 恰好被唤醒。能力问题不会随入口变化,架构病会。
4. **历史修复模式印证病在结构:同族修复 ≥8 次仍复发**(F2 §5 表格),每次修一个 producer/一个罐头/一个子预算,从未撤销"确定性层可终结轮次/可作废上游成果"的权力本身——patch spiral 是 multi-decider 病的签名,不是能力病的签名。

一句话终答:**这个系统的 LLM 已经好到能在每次事故里把活干对,而架构还停留在"不信任何人、宁可错杀"的防御性终局设计;当下每一分体验损失,买单的不是模型智商,是护栏的无偿否决权。修复方向因此不是换模型、加 prompt、上更强的分类器,而是三刀收权:让判对的层拥有它已经挣得的裁决权(PR1),让做完的工作拥有被交付的合同(PR2),让防御闸退回"高置信快路径+数据面权限"的本分(PR3)。**

---

*落盘完成 2026-08-10。核验方法:五断言逐条源码抽查(§1),全部 file:line 可复核;未做 live 复现的推断已标注 PLAUSIBLE/caveat。*
