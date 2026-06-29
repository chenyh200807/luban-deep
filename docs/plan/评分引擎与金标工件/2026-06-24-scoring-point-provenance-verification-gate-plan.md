# 采分点原子事实溯源核验闸 — 防"4000万"类编造系统性方案

> **状态**:Proposed（2026-06-24）
> **触发**:端到端回归 + 三厂异源 + 教材仲裁，实测 bot 判分输出含教材里不存在的硬事实（"二级资质合同额4000万以下"、"屋面防水方针以防为主以排为辅"、"室内防水工作年限25年"），证据见 [`artifacts/factcheck_textbook_grounding_2026-06-24.md`](../../../artifacts/factcheck_textbook_grounding_2026-06-24.md)。
> **单一 authority**:本计划**不造第二套采分点管道**。在现有 `knowledge_unification.py`（4 层权威分层）+ `concept_registry.py`（`source_nodes[]` provenance）+ `runtime_llm_adjudicator.py` 之上**加确定性核验闸**。采分点真值源仍是 `scoring_point_compile.v1` →`luban_grading_object.v1`（见 memory `scoring-point-truth-is-grading-compile-pipeline-not-deep-pack`）。
> **相关 contract**:涉及 grade/批改运行时，实现前先读 `CONTRACT.md` + `contracts/index.yaml`。

## 1. 目标 / 非目标

**目标**:让采分点库里**每一条原子硬事实**（数值/阈值/条号/术语/criterion 的存在性）都**确定性可溯源到答案级 verbatim 跨度**，无溯源者**编译期拦下、不进生产判分**；运行时 bot **禁现场生成采分点**，无库条目即 fail-closed 声明而非 improvise。

**非目标**:不重做专家团；不替换现有编译管道；不追求"软推理"（判断逻辑/易错点叙事）零 LLM——那部分 LLM 仍主力。本闸只管**硬事实**。

## 2. 问题重定义（关键认知）

"4000万"不是"LLM 不够强"，是**provenance 挂了但没逐条核验**——现有 `knowledge_unification` 自承 "UNIFICATION not re-signing"。错误分三型，越往后越难：

| 型 | 例 | 本质 | 难度 |
|---|---|---|---|
| (a) 错值 | 找坡 3% 写成 5% | 引用跨度里数值对不上 | 易（归一化字面匹配） |
| (b) 脱书值 | 防水工作年限 25 年 | 答案级源里**根本没有这个跨度** | 中（"无 verbatim 跨度即拦"） |
| (c) **幽灵 criterion** | 二级资质"合同额4000万" | 断言一个**不存在的判据维度**（二级无合同额项） | **难（要结构镜像，纯文本匹配抓不到）** |

**铁律**:区分**硬事实**与**软推理**。硬事实=确定性溯源、**零 LLM 真值**；软推理=LLM 可做但**禁引入新硬事实**。永远不要用"LLM 是否一致"代替"这个数字是否字面出现在引用的答案级跨度里"——同源盲点已实证（同源 deepseek-chat 把全部编造放过）。

## 3. 系统性方案：分层确定性溯源闸

### 闸-1 原子事实 verbatim 核验（编译期，BLOCKING）— 治 (a)(b)
- 把每条采分点**分解为原子硬事实**（每个数值/条号/术语/criterion）。
- 每条原子硬事实必须绑定**答案级 tier**（`textbook_verbatim` / `standard_verbatim`，**lecture/question 不算答案级**）的 verbatim 跨度。
- **确定性核验**（非 LLM）:声明值经**归一化**（数值/单位/同义：4万m²≡40000㎡）后必须字面出现在引用跨度。对不上 → quarantine，**不 promote**。
- 这正是本轮人工做的（"4000万 全教材搜不到"）的**自动化 + 全量化**（非抽样）。
- **遵从本主线先验（关键）**:`2026-06-03 calc validator POC`（INDEX 评分引擎主线）已证 **label 正则抽期望值不可靠（假阳性），需结构化 `expected_value` 字段才能当 guardrail**。故闸-1 **绑结构化数值字段，不靠正则抽** ——讲义 chunk 已带 `rule_numeric / granularity=parameter`（page_5 找坡即 4 rules/16 params 结构化），编译期把采分点的硬事实对齐到这些结构化 param，比对结构化值，绕开正则脆性。

### 闸-2 结构镜像 / 负空间检测（编译期）— 治 (c)
- 采分点的**判据维度集合** ⊆ 源的维度集合。源（讲义结构化表，page_5 已带 `rule_numeric/granularity=parameter`）二级={高度,面积,跨度}，采分点多出{合同额}=无源维度 → 拦。
- 难点：需结构化源表示；分期，先覆盖有结构化表的考点（资质/防水参数等），prose 型考点后置。

### 闸-3 专家团角色降权（编译期流程）
- 专家团/对抗只做**软推理**（为何是采分点、易错点、教学）；**只能引用过闸-1 的硬事实，禁自铸数值/条号**。
- 对抗用于**教学质量**，不作硬事实真值闸（同源盲点）。

### 闸-4 运行时 fail-closed 收口（运行时）
- bot 判分**只取过闸的编译库采分点**；无库条目 → **不现编**，降级"这道题超出已签发范围/我没有权威采分点"。
- p10 资质题就该在此被拦（它是 bot 现场 improvise，根本没走库）。关联 task#20 簇A 判分态收权（另一窗口工单 `artifacts/student_army_eval_grading_2026-06-24.md`）。

## 4. 实施阶段（已按 2026-06-24 spike 证据修正 phasing）

> **修正依据**:P0 闸-1 离线扫描已跑（`artifacts/scoring_point_provenance_scan_FINDING_2026-06-24.md`）。结果:**编译库数值层零确认编造**（concepts/teaching_cards/rules 共 917 含量化字段实例全部有源；exam_patterns 5 个答案侧"无源"全良性=计算答案/场景值+1 例 provenance 链太窄）。**"4000万"不在库里,是运行时现编。故 phasing 反转:闸-4 才是真 P0,闸-1 降级为回归护栏。**

- **~~P0 闸-1 离线扫描~~ 已完成**:库已证干净;扫描器 `scripts/scan_scoring_point_provenance.py`（自标定+对抗变异验证通过）保留作 promotion gate 与回归护栏。
- **P0（真）= 闸-4 运行时硬事实接地**（非"无库即拒判"——撞 open-world 硬约束40；正解是"开放判分也要 grounded,硬事实须溯源证据,软推理才可推理"）。
  - **P0.1 已落地（prompt 契约层,2026-06-24）**:根因是 `authority drift`——单一权威 `core/grounding.py:GROUNDING_CLAUSE` 已禁编造具体数值/规范编号,但 `submission_grader_agent.py` open-world directive 那句"或专业推理"局部抵触它。修法=**删抵触收回单一权威**(directive 收紧:专业推理只管判断逻辑,硬事实依据回归 GROUNDING_CLAUSE),不加新概念/第二权威。TDD `test_open_world_hard_fact_grounding.py` 3 passed + 回归 23 passed。⚠️**软约束,需 live ≥3 轮一致才算 done,且未 commit/未部署。**
  - **P0.2 已完成(2026-06-24)**:审计单一权威覆盖面——`GROUNDING_CLAUSE`/`prepend_grounding` 铺到所有判分/教学入口(submission_grader/followup/generator/chat/teaching_modes 全继承);`deep_question.py:836` 开放世界判分**委托 SubmissionGraderAgent**,故 P0.1 一处修复同时覆盖 deep_question;MCQ skill(construction-mcq-grading)本就要求"基于 RAG 证据裁决"无"专业推理"逃生口。**结论:submission_grader directive 是唯一一处局部抵触单一权威的 drift,已修;无第二处要改。**
  - **P1 backstop = 确定性 runtime 核验(已 live 验证 P0.1 有效后,降为 defense-in-depth)**:把 open-world 输出的硬事实 vs 注入证据做闸-1 式 verbatim 核验,无源硬事实剥授权框架/标未核(非拒判)。落点 `runtime_llm_adjudicator.py`。**当前不实施**:①P0.1 已 live 3 轮证有效(4000万消失/改用教材正确值3000万以上),P1 是兜底非急需;②判分 runtime 正被另一窗口 grading-collapse-clean 收口中,此时插 runtime gate 会撞其收权工作——**待该分支落定后由 owner 协调接线**,避免在收口中途新增 gate(root-cause skill:别在多 writer 收敛途中加第 N+1 个 decider)。
- **P1 = 闸-1 接编译期 BLOCKING**:库已干净→作 promotion 前 register-before-use 回归护栏，防未来污染。先做 P1.0 provenance 链补全（exam_pattern answer 阈值要链到含该值的 sibling chunk，否则闸-1 误报，见 §3 副产品工单）。
- **P2 = 闸-2 结构镜像**（先结构化考点）。
- **P3 = 闸-3 专家团降权**。

## 5. 验收标准

- 闸-1:对一批**已知含编造**的采分点（本轮 R01/R02/R03/R09 + 扩样）召回率；对**已知正确**（R04/R05 找坡）零误杀（验证归一化）。判官标定式：已知编造必拦 / 已知正确必放。
- 闸-4:构造"无库考点"请求，bot 必 fail-closed，**零** improvise 采分点（确定性不变量）。
- 全链:抽样采分点的"硬事实 100% 有答案级 verbatim 跨度"覆盖率。

## 6. 红线 / 伪进展

- **伪进展**:加更多对抗 LLM 投票——同源盲点，plausible 编造全体放过（实测）。
- **伪进展**:"采分点有 provenance 字段"——字段≠核验；现状就是 attach 不 verify。必须 BLOCKING 闸真拦 unmatched。
- **红线**:先归一化再匹配，否则误杀（4万m² vs 40000㎡、"不小于3%" vs "≥3%"）。
- **红线**:源自身可能污染（S01 真题全编造教训），verbatim signing lane 是地基，要先硬；标准 verbatim 签发是已知 follow-up lane（`knowledge_unification` 自述）。
- **红线**:负空间(c)纯文本抓不到，别假装闸-1 覆盖了它；老实分期。
- **和解本主线"确定性术语匹配 < LLM 理解"（已三次坐实）**:那个负结果是在**判分层**（用确定性 list_rule/正则去给学生答案评分，退化 gold）。本闸-1 不是判分，是**编译期溯源核验**（采分点声明的数字是否字面出现在引用的教材跨度）——目的、对象、阶段都不同，不与该负结果冲突。判分仍是 LLM（生产单模 qwen 关思考），本闸只防"采分点库里混进无源硬事实"。**实现时务必守住这条边界，别把确定性匹配误用回判分。**

## 7. 相关代码入口

- `deeptutor/services/construction_grading/knowledge_unification.py`（4 层权威 + provenance，待加核验）
- `deeptutor/services/construction_grading/concept_registry.py`（`source_nodes[]`）
- `deeptutor/services/construction_grading/runtime_llm_adjudicator.py`（运行时判分，闸-4 落点）
- 教材源:`docs/原始数据/2026_副本/讲义/*_v8/page_N.json`（结构化表）
- 关联 memory:`scoring-point-truth-is-grading-compile-pipeline-not-deep-pack`、`luban-scoring-points-must-trace-to-textbook`、`authority-ladder-textbook-adjudicates-llm-panels`、`cross-model-judge-catches-fabrication-same-source-misses`

## 8. ② content-truth 核验闸收口（2026-06-29，闸-4 扩到规范条文号，DONE / live≥3 全绿）

**背景**：2026-06-29 满意度 rerun 揪出新主病——grounding 异源核准确率 84%→73%，bot 现场编造**规范条文号/版本**（GB50016"2019版"不存在、GB50500"2024版"§8.11.8 不存在、自造"题库权威记录全国统一"）。这是 reachability/consumption 病的 **verification 半边**（见 memory `satisfaction-drags-map-one-reachability-disease-plus-orthogonal-stability`），与本计划闸-4「运行时硬事实接地」同根。

**真根因（专家 C 真码确诊）**：不是没内容源——规范源 `standard` doc_type 已接进检索（`retrieval_plan.py` standard_clause / `supabase.py` search_standard_chunks / `kbv5.py`）。病在**消费侧无结构闸**：唯一反编造是 `core/grounding.py` 注入的 system-prompt 软约束（docstring 自认"必要不充分"），没有结构强制把 bot 写出的 GB/JGJ 条文号去本轮 KB `standard` 召回核一遍（`grep verify.*clause` = 0）。

**治本（接通 + 扩 fail-closed，非加门，PR #302 合 main = `ccd5731eb`）**：
- 纯验证器 `content_truth_guard_response`（`deeptutor/tutorbot/teaching_modes.py`，post-gen 矫正器既定家，镜像 `correct_construction_exam_boundary_fact_response`）：regex **只抽取** GB/JGJ 编号+版本年，真值由本轮 `standard` 召回证据裁决（单一汇点 fail-closed，regex 不承担理解）。
- 接入 `tutorbot/agent/loop.py`：现有 degraded guard 同层（4 个 finalization 站）接 `_content_truth_guard`，证据取自 `runtime_metadata['rag_rounds'][*]['sources'][*]['content']`（单一真值源，已接检索，不新建第二 authority）。
- 判定：无规范编号→不动（防过矫正，普通教学/闲聊零影响）；编号在本轮召回→放行；核不到（RAG miss）或 `rag_retrieval_degraded`→诚实降级 caveat（从"规范依据"降为"通用判断方向，以教材为准"），**不 nuke 正文**，不回落 V0，G2 闸保留。

**验证（live≥3 终态 + 异源核 + SEV 双绿）**：
- TDD（先 RED）：`tests/tutorbot/test_content_truth_guard.py` 10 项含 eval-design #5 metric 自测（干净放行/编造拦各命中）；隔离污染已证非回归（baseline `a64373f70` 同样 12 fail）。
- CI 双口径 contract guard PASS（`[luban_grading_engine] passed | protected=loop.py | tests=test_content_truth_guard.py`），两份 index.yaml byte-identical，verify_runtime_assets PASS。
- 部署三方对齐：origin=host=container=`ccd5731eb`，dirty=false，gate 入容器。
- **live≥3（`scratchpad/verify_content_truth_gate.py`，9 turns）**：5 个 cite 规范编号**全 5/5 带 caveat（gate fired）**，4 个无编号（clean 未误伤），**0 个裸编号作权威输出**。p0 工期索赔每轮引 `GB50500-2024`（eval 揪出的编造）→ 3/3 全被降级。
- **DeepSeek 异源核（self_test PASS）**：被 caveat 的 `GB50500-2024` = **fabricated(0.95)**「尚未发布，现行 GB50500-2013，无 8.11.8 条」= gate 拦的确含真编造；GB55034-2022/GB5725/JGJ80-2016 = accurate（真编号本轮未召回被 caveat = owner 拍板 trade-off，正文保留+诚实 hedge，(C) 补内容长尾可降这类）。
- SEV 双绿：倒诬 HOLD（顶住"选项顺序"施压不改判）、答案泄露 HOLD（拒泄露未答题答案）——caveat append 未回归 SEV。

**残留 / 下一步（不阻塞本收口）**：(C) 补内容长尾——从 caveat 命中日志定位本轮该召回却没召回的真规范（GB55034/GB5725/JGJ80），走召回侧而非前置，降对真编号的 caveat 噪声。reachability 全战役剩 ①正向路由家族整体收口（满意度边际最大）+ ③稳定性 scoped 专项。

## 9. ② content-truth 改造成 owner 三层 review loop（2026-06-29，#307/#309/#310，DONE / live≥3 全绿）

**为什么改 §8**：§8 的 #302 是"软 caveat"——核不到就 append 否定式提示。owner 复盘拍板：**闭嘴/否定让学员觉得系统没用**。新原则=**信当下 LLM 能力，宁可大方输出 + 诚实声明，绝不输出端抑制；准确性靠"后台审 + 持续纠"的 review loop 收敛**。这同时把"准确性保证"从输出抑制搬到离线 loop，顺手起步内容飞轮。

**三层设计（全部上线，main = `84f5216a5`）**：
- **L1 永远输出 + 诚实 hedge**（`teaching_modes.py`）：核不到的规范编号不再否定式降级，保留全文 + append 大方 hedge（"以上内容由 AI 生成…建议你以教材或官方规范原文核对，我不保证 100% 准确"），命名编号。抽出 `assess_unverifiable_standard_codes` 作唯一"核不到"判定点（L1 与 L2 共享，不双实现）。
- **L2 低置信内部记录**（`loop.py` `_content_truth_guard` + `_export_content_truth_metadata`，manager/capability/turn_runtime 多跳）：runtime 只 **flag**——把核不到的编号记进 `content_truth_low_confidence_claims`，经多跳 metadata 管线送进**单一事件 sink `TurnEventLog`**（复用，不新建）。学员看不到，不裁决不抑制不新增 runtime decider。
- **L3 离线评审 agent**（`services/observability/content_truth_review_queue.py` + `scripts/review_content_truth_queue.py`）：镜像 `failed_turn_promotion`，读 TurnEventLog→去重队列（排合成 turn）→**authority-ladder（教材原文 *_v8 alltext > 异源 DeepSeek）**仲裁 accurate/fabricated/uncertain→**PII-safe** 纠错数据集喂内容升级。离线**非 runtime 门**。`--self-test` 过 eval-design #5。

**接通真断点（eval-design 教训：unit-green ≠ live works，连追三 PR）**：
- #307 只接终端事件 allow-list（turn_runtime ~869）→ live TurnEventLog **0 条 claims**。
- #309 补 manager 多跳（runtime_metadata→trace/merged/session）+ boundary A（`_summarize_assistant_events`）→ live 仍 **0 条**。
- #310 找到真断点：`process_direct` 靠 `metadata.update(response.metadata)` 回流给 manager，只有 **OutboundMessage 的 response_metadata** 里的键能回去；而 claims stamp 在 loop **内部 runtime_metadata（inbound 的 COPY）**，从不进 response_metadata → 死在 loop 内。`degraded_*` 能工作是因为 manager **自己 re-derive**，根本不靠 loop 回流。修法=新增 `_export_content_truth_metadata` 在 5 个 finalization emit 点把 claims 导出进 response_metadata（镜像 `_export_case_grading_metadata`）。**观测 observe-only 旗标若 stamp 在 loop 内部 copy，必须在每一跳显式导出/转发，否则静默丢失。**

**验证（live≥3 终态，部署 `84f5216a5`，QA 真入口驱动 + X-Eval-Bypass 绕 billing）**：
- L1：9 turns 跨 3 轮，**silent=0**（永不沉默），4/4 带编号 turn 全 append hedge，无编号 turn 不动（防过矫正）——确定性不变量 3 轮一致。
- L2：6 个带 claims 的 turn 跨 3 轮**全部落 TurnEventLog**（`with_claims=6/19`）。
- L3：`--self-test` PASS（已知真→accurate / 已知编造→fabricated）；真实队列离线评审产 PII-safe 纠错数据集（0 PII 泄露，全 redacted）；DeepSeek 异源 live 跑——run1 把 `GB50500-2024` 判 **fabricated**（满意度 eval 揪出的"2024版"不存在），run2 转 uncertain（DeepSeek 单源噪声→ladder 以教材为顶权威、异源不判死则保守 uncertain，不冤判）。
- CI 双口径 contract guard 全过（turn + luban_grading_engine），两份 index.yaml byte-identical；focused 测试绿；回归 431 passed。

**诚实边界 / 下一步**：(a) 教材仲裁这轮 textbook=N 全部——因可用 *_v8 是建筑实务讲义子集，不覆盖清单计价/防护/安全网标准；ladder 正确保守判 uncertain，**要提精度需补全规范语料**（正是 review loop 要喂的"内容升级"）。(b) DeepSeek 单跑有噪声（异源信号非金标），多跑投票或接教材全集可降。(c) review loop 是异步纠错非即时保真——准确性靠 loop 收敛，这是 owner 拍板的 trade-off（辅导信任 > 自信编造，且不闭嘴）。
