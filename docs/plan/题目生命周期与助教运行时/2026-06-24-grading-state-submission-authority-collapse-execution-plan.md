# 判分态/作答提交单一权威收口执行计划（2026-06-24）

> **状态**: **Steps 1-5 全部实施 + live-verified GO（2026-06-24）**。test2 部署完整收口(含 Step 5 单一 chokepoint);凭空判分 SEV-1 闭环、硬约束40 保住、粘贴 MCQ 潜伏回归一并修复。PR #212(待 CI/review 合 main)。残留独立工单:删 deep_question force-grade 兜底(边际收益低,按需)。

## ★ Live 验证结果（2026-06-24,eval-design ≥3 轮）

| 轮次 | 非作答不凭空判分 | 真作答必判（硬约束40） | 揪出 |
|---|---|---|---|
| R1（Steps 1+2+4） | **0/3** | 3/3 | LLM interpret「提交优先」偏置 → Step 4.5 |
| R2（+4.5） | **1/3** | 3/3 | `_decision_from_fallback` 确定性判分 → Step 4.6 |
| R3+R4（+4.6,完整） | **6/6** | **6/6** | **GO** |

非作答轮 bot 现正确行为:*"好的,我不判答案,也不透露任何正确选项... 你选了A,能说说为什么觉得'听'是方法之一吗?"*（不凭空判分,改引导）。

**eval-design 铁律实证**:unit-green + enable_llm=False 端到端过,但 live R1 NO-GO——判分态有 unit 测试覆盖不到的 LLM 路径偏置;靠 DB-trace `turn_semantic_decision.reason` 逐轮看穿真路径(Langfuse 对 eval-bypass 不写,读 chat_history.db)。这是 multi-writer 实证:逐路径 live 揪逐路径 gate(whack-a-mole),单一 chokepoint(turn_runtime `_submission_action`,Step 5)是更彻底解。


> **主线归属**: [跨能力上下文连续性架构](2026-06-20-cross-capability-context-continuity-architecture.md) 的下一增量——闭合该计划列的"剩余 15+ 独立 submission/relation 闸增量收敛"。**不另起主线。**
> **诊断来源**: `artifacts/grading_state_authority_rootcause_2026-06-24.md` + `artifacts/student_army_eval_grading_2026-06-24.md`
> **必读**: `CONTRACT.md` + `contracts/index.yaml`（turn/session/stream/TutorBot）；AGENTS §5 根因 + §硬约束40「答题必有解析」。

## 0. 目标 / 非目标

**目标**: 把"学生这一轮是否提交了一个要被判分的作答 + 提交到哪一道题"这个**单一业务事实**收到唯一权威，消除 fast-path 篡夺语义裁决权且被屏蔽 LLM 翻案的架构病。

**非目标**: 不动 grading 计算/采分点真值（鲁班 V1）；不动硬约束40 的真作答必判保命路径；不新增第二聊天入口/第二套 authority；不给关键词分类器补排除正则（红线）。

## 1. 单一业务事实 + 单一权威

- **one business fact**: 「学生这一轮是否提交了要被判分的作答，以及提交到哪一道题」= 布尔 + 目标题ID，每轮裁决一次。
- **one authority**: `resolve_question_lifecycle_scene_decision`（`deeptutor/services/question_lifecycle_skills.py:188`）——设计文档自承的 single-decider，orchestrator 已只读它路由（orchestrator.py:332-341 / 376-380 / 433-446）。

## 2. 架构病（第一性命名）

**`fast-path-as-authority, shielded-from-veto`**：本该由"理解意图"回答的语义问题（这句话到底是不是交卷），被降格成关键词命中的字符串匹配；为保硬约束40（真作答必判）把这条 keyword 快路径设成"永不让 LLM 推翻"（semantic_router.py:760-766），于是快路径的高召回（把试探/质疑/否认都抓成提交）成了**无法被纠正的误判**。

**55 个 decider 散落 5 区域**（turn_runtime 上游双缓存 14 / semantic_router 13 / scene+orchestrator 16 / deep_question 入口 13 / grading emit 16）是病的**表现非病本身**：没有单一权威 + 没有 LLM 复核门 → 每个调用点都不得不自己再 `resolve_submission_attempt` 一次自保，复制扩散。

实测铁证：`resolve_submission_attempt("我猜是A但不确定,你先别判")` → 抽出 answer="A"；"刚才那题我还没做呢" → 返回 submission。Langfuse 真实 trace：g2 T5/T9 凭空判分、g5 质疑误判、g1 回指串题、g6 简答被 MCQ 抢占，全是此病。

> **诊断修正**: 早先 solo 诊断指向 `teaching_modes.detect_construction_exam_scene`（teaching_modes.py:705-821）是**指错**——codegraph + grep 实证它**0 生产 caller**（死代码，仅测试引用 + harness authority guard 禁止调用）。关键词 scene 逻辑被复制两份：死的在 teaching_modes，活的在 qls。真权威是 qls:188。

## 3. 收口设计（less is more，先减后加）

核心：给 `resolve_submission_attempt` 的返回**加 confidence 维度**（它已能返回 kind=single/batch/numbered/ambiguous——不新增 decider，只让现有探测器输出置信而非布尔），把"是否提交"的最终裁决收到 qls:188 一处。判定矩阵：

- **(A) HIGH 置信作答**（显式 prefix「我选/我的答案是/判断:」+ 干净选项/判断词/整案作答，**无**质疑/试探/否认 marker）→ 确定性快路径直接钉 grading scene，LLM 不参与（**保硬约束40 + 保速度**）。
- **(B) LOW 置信/模糊**（试探"我猜"、保留"你先别判"、否认"还没做"、质疑、回指、简答被歧义遮蔽）→ `resolve_submission_attempt` 返回 kind=low_confidence，qls:188 把 scene 置 None，交 orchestrator 的 `_resolve_turn_semantic_decision`（LLM 语义权威）裁决"是不是真在交卷"。
- **(C) LLM 判为非作答/追问/质疑** → route_to_followup_explainer，不判分。

其余散在 turn_runtime/semantic_router/deep_question 的"自己再 resolve 一次"全部 demote 成读 qls:188 的 canonical decision。净效果：**55 decider → 1 裁决点 + 1 高置信快路径 + 既有 backstop，行数净减**。

**HARD 约束**：confidence 的 HIGH 必须用**正向高精确信号**（显式提交 prefix 存在性）定义，LOW = 非 HIGH。**禁止用排除否定词正则**（那是第 N+1 个打地鼠点，红线）。

## 4. 保硬约束40（真作答永远必判）

保命路径完全不动，只动"误判为提交"的低置信侧。三层托底全 keep：
1. HIGH 置信作答仍走确定性快路径直接判分（qls:1058-1068 高置信分支 + orchestrator.py:376-380 mcq_grading_bypass + turn_runtime.py:1371 case pre-stamp 高置信版）——真作答不经 LLM、必判。
2. semantic_router.py:1153-1177 `_decision_from_fallback` submission 分支 keep——canonical 完全缺失时仍能命中即 route_to_grading，但只对 HIGH 生效。
3. deep_question.py:4616-4670 backstop + 4467 三路兜底 + 830 open_world keep——进入判分轮绝不空输出/拒答。

**反向 regress 防护**（最大风险）：LOW 置信 + active 题存在时，LLM 若拒判**必须降级为显式追问"你是要交卷吗"**，绝不静默 route_to_general_chat（semantic_router.py:805-832 ambiguity gate keep）。

## 5. 实施序（从病因出发，风险低→高，每步独立 live 可验）

| Step | 改动 | 风险 | live 验证 |
|---|---|---|---|
| **0** | ~~删 `teaching_modes.py:705-821 detect_construction_exam_scene`~~ **跳过**:它虽 0 生产 caller,但有 harness authority guard 专门禁用它（有意绊线）+ 测试测其行为,删除 churn>价值,保留绊线 | — | — |
| **1** ✅ **DONE** | 不改 `resolve_submission_attempt` 返回形状（避免破 74 个 exact-dict 测试),改为**新增纯函数** `question_followup.py:submission_confidence(message, ctx)→high/low/None`（复用 `_LEADING_SUBMISSION_PREFIX`+`_match_option_key_by_value`,正向"剥前缀后是否纯答案 token"判据,无排除正则守红线）。**不改任何 consumer** | 纯增量 | ✅ TDD 11 测试 GREEN + 全文件 120 passed 零回归 + 9 真实 ground-truth 消息全对（'我猜A但先别判'/质疑/回指=LOW,'我选B'/'B'=HIGH,'我不会'/'讲考点'=None) |
| **2** ✅ **DONE(确定性层)** | `qls:1058-1068` 接 `submission_confidence`:非 LOW(HIGH/batch/numbered)→钉 grading scene(保硬约束40),LOW→不钉、fall through 既有 question_review 路径。**首子句判据**(不是整句):混合轮"我答B,再出3题"仍 HIGH;质疑/回指语义留给 Step 3-4 LLM+历史,confidence 不误降 | 低 | ✅ TDD GREEN + 两全文件 138 passed 零回归 + ground-truth 端到端(enable_llm=False):'我猜A但先别判'→question_review(不再凭空判分)/'我选B'+'我答B再出3题'→mcq_grading/'还没做'+'讲考点'→None。**live 验证待 Step3+ deploy** |
| **3** | ~~orchestrator case/mcq 接 LLM 门~~ **被 Step 2 吸收**:Step 2 后 mcq_grading/case_grading scene 已 HIGH-only,LOW 永远到不了这两个分支(落 question_review→已有 LLM 门 / None→tutorbot),故"给 grading 分支加 LLM 门"无 LOW 可拦=空操作。无需单独实现 | — | — |
| **4** ✅ **DONE** | semantic_router.py:760 守卫接 `submission_confidence`:HIGH 缓存提交仍永不翻案(保硬约束40),LOW 缓存"提交"允许 history-aware LLM 复核翻案。当场算 confidence 不依赖跨层缓存透传(避开 risk-four)。打破 shielded-from-veto——这是 Step 2 之外**第二条并行力路径**(turn_runtime 缓存→守卫)的收口 | 中 | ✅ TDD GREEN(LOW 缓存提交→重交 LLM→非 route_to_grading;HIGH→shielded→route_to_grading)+ 176 passed 零回归(semantic_router/stack/orchestrator×2/deep_question 判分)。commit 372416d51 |
| **5** ✅ **DONE + live GO** | **单一 chokepoint 收口**:`turn_runtime._submission_action_for_user_message`(最上游 submission action 构造点)gate confidence——HIGH 才构造提交动作,LOW 不构造→下游不缓存 submission(未来新下游路径自动继承,止 whack-a-mole);per-path gate 保留作 defense。**顺带修 4.5/4.6 潜伏回归**:submission_confidence 由"首子句"改"任一子句剥前缀=干净答案 token"(修粘贴题面+末尾"我选A,直接批改"被 false-LOW)。contract surface contracts/turn.md 同 commit 记不变量 | 中 | ✅ TDD;广回归 476 passed(修 Step5 前 2 个粘贴 MCQ 失败);**live 非作答 3/3 + 真作答 3/3 + 粘贴MCQ必判✓ = GO**。commit 54cf8c2ac |

> **注**: 原 Step 5(删 deep_question fabrication 兜底)未做——chokepoint gate + per-path defense 已让 LOW 非作答 live 6/6+3/3 不判分;删 force-grade 兜底是更激进清理,边际收益低、风险高,按"先证 router 覆盖再删"原则留独立工单。

**跨缓存透传**（风险四）：Step 1 加 confidence 时必须让 `_normalize_question_followup_action` 透传，否则 start_turn 判 HIGH、_run_turn 重算丢 confidence 退回旧行为。

## 6. 验收（每步）+ 必复跑测试

- **确定性不变量**（不靠 LLM）：非答题轮后"判分计数=0"；真作答轮"route_to_grading 稳定产出"。
- **live ≥3 轮一致**（同 base origin/main）才宣称该 step 收口完成；2/3=没修好。
- 必复跑：`test_deep_question_submission_grading.py`（全量）、`test_question_followup.py`、`test_question_lifecycle_skills.py`（主改点）、`test_orchestrator_*.py`（Step3 后）、`test_semantic_router*.py`（Step4 后）、`test_mcq_grading.py`、`test_mcq_option_surface_grading.py`、`test_deep_question_case_rubric_v1.py`、ground-truth 6 失败签名 live 回放 + 真作答必判三连跑。
- contract-protected（deep_question/orchestrator）：同 commit 更 registered domain test + contract surface；packaged `deeptutor/contracts/index.yaml` 同步。

## 7. 边界 / 同源核

- 本计划的 decider 测绘 + 收口设计由 Claude 同源 workflow（5 区域专家 + 1 指挥官）产出，**file:line 可验证**（55 decider 已 grep/codegraph 抽样核实，如 teaching_modes 死代码已确认）。设计本身镜像已有正确模式（question_review/practice_generation），非新发明。
- 真正的验收是 TDD + ≥3 轮 live，不是"设计看起来对"。
- 选项重排字母错位（g1 T6，[[mcq-grading-uses-bank-option-letter-not-presented-surface]] 姊妹路径）是收口后的**独立第二步**（进判分后投影到当前题面），不在本计划主收口内。
