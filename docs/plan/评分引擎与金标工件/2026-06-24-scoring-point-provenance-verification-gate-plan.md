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
