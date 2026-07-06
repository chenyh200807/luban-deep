# 鲁班判分「收入闸」对账里程碑计划（2026-07-05 两通道口径重整）

> Status: `Proposed / reconciled`（2026-07-05）。
> **本文只做两件事**：(1) 用 2026-07-05 已澄清的「判分两通道」口径,把 2026-06 一批金标/rubric/shadow 计划逐份对账,标 `仍有效 / 需更新 / superseded`;(2) 产出一份当前可执行的「判分收入闸」里程碑计划。
> **本文不改任何判分代码、不跑判分、不接 runtime、不新建 schema/表。** 纯规划。
> 单一权威纪律沿用既有 memory:采分点 ground truth 唯一 = grading 编译管道产物;governed gold 唯一 = 人工逐采分点裁决。本文不制造第二套。

---

## 0. 口径基准（本次对账的唯一标尺）

判分有两条**互不相干**的通道(已由独立 agent 用代码证据钉死):

| | 通道① 官方判分弹药 | 通道② rich-leaf 支撑上下文 |
|---|---|---|
| 载体 | `v_case_rubric_scored`(~174 qid / 1221 点,带官方答案 + 真实分值) | RichLeaf R5 / v3.2 token pack(5705 点,仅 205=3.6% 官方带分值) |
| 代码入口 | `rubric_grader_v1.py` `_rubric_bank()`(≈`:1195` 起,load+verify-gate 一次);`v_case_rubric_scored` 亦被 `m35_artifact_query.py` / `canonical_knowledge_manifest.py` / `run_luban_rubric_compile.py` 消费 | `rich_leaf_runtime.get_rich_leaf_context()`,结构上永远 `official_score_allowed=False` |
| runtime 语义 | grader 用它**逐采分点带分值判分**——这才是「每分怎么扣有教材出处」卖点的载体 | grader 只把它当 **grounding 文本**,架构上进不了①;`installed_runtime_supply` 是**无 runtime 读的死 flag** |
| 现状覆盖 | pack 锚定 258 真题里只覆盖 ~51 → **~80% 真题判分仍走 open-world 现编** | 5705 点里 96.4% 不带官方分值,不是判分弹药 |

**推论(本文所有裁决的根)**:
1. **真正的「判分收入闸」= 通道① 覆盖扩容**(51/258 → 目标),**不是** R5/深 pack。
2. 两通道要证明「改了判得更准」都卡在 **governed gold**:现唯一「gold」是合成 fixture + AI 面板,`fleiss_kappa=-0.05`(比随机差,见 `run_luban_arbitration_gold_panel.py` / `run_luban_m35_ai_governed_gold_labeling.py` 产物),**无一条人工逐采分点金标**。
3. 任何把 **R5 / 深 pack / rich-leaf 供给** 当「官方判分弹药」或「收入闸载体」的思路,**一律 superseded**——它们是通道②,`official_score_allowed=False` 是架构不变量,不是可开的 flag。

---

## 1. 逐份对账表

| 旧计划 | 判定 | 一句话理由(对 2026-07-05 口径) |
|---|---|---|
| `2026-06-04-luban-case-rubric-data-expansion-plan.md` | **仍有效(收入闸主轴,需并入本文阶段2)** | 它就是通道① 扩容(题库 218 case + 2026 教材 verbatim 锚源 → 采分点 + `source_ref`),与「收入闸=通道①扩容」完全同向。唯一需更新:它写作时把目标当「registry v1 结构化放量」,现在要明确其产物**终点是 `v_case_rubric_scored` 覆盖从 51→目标**,并**必须先有阶段0 governed gold 才能宣称「扩了更准」**(它自身的 quality gate 只保证 verify-on-write 不伪造,不证明判分变准)。 |
| `2026-06-01-luban-human-validation-slices-artifact-versioning-v1.md` | **仍有效(是阶段0 的直接前身,需升级)** | 它已建「PO 盲标 → human-vs-ledger / human-vs-artifact-first」正确方法论,并暴露真红灯:human-vs-artifact-first point-hit **0.5267** / MAE **4.6091**(通道① 现状判得比人差)。局限:**单标注人 = 无真 IRR**,131 行 directional。阶段0 的 governed gold 就是把它从「1 人 directional」升到「多标注人 + 裁决 + IRR」的治理级金标。 |
| `2026-06-04-luban-grading-metric-governance-qwk-plan.md` | **仍有效(度量口径,candidate_only 不变)** | QWK / normalized-per-question-delta 作诊断、raw delta 作护栏、§3 五条硬门永不被 QWK 抹平——这套度量治理与收入闸 A/B 直接复用。红线保留:`candidate_only`,**冻结定义在先**,不 retrofit,不因数字恰好过线就宣称生产精度。阶段1 A/B 的度量层直接采用它。 |
| `2026-06-03-luban-deepseek-production-shadow-v0-plan.md` | **需更新(降级为「成本线候选」,非收入闸)** | 它解决的是**未来生产成本**(DeepSeek 单模型 vs 4-model jury),不是**判得准不准 / 卖点覆盖**。结论停在 WEAK-GO,根因=list_rule 语义天花板。对收入闸的意义:它是通道① **判分器成本侧**的候选,**不是**闸本身;且它反复自证「无真人 gold 就不能宣称生产精度」——正好指向阶段0。保留为阶段1 之后的成本优化输入,不列入收入闸关键路径。 |
| `2026-06-01-luban-golden-v0-po-review-package.md` | **需更新(方法论素材,数据口径过时)** | v3「踩字口径 + conc=0.9885」是**两个 AI 同标准的一致性**,不是人类真相(其自身与 playbook 都标了这条天花板)。作为「采分点术语/踩字/构造像不像真人」的**抽查协议模板**仍可复用进阶段0;但 conc 数字**不得**当准确率证据,阶段0 用真人多标注取代它。 |
| `2026-06-04-luban-real-answer-runtime-test-integration-plan.md` | **仍有效(测试接入设计,收入闸 A/B 的挂载点)** | 它把「真实作答 → 经 QA harness 喂判分引擎做 shadow 对比」的 flag(`grading_engine_runtime_test`)设计清楚:挂 `learning_brain.py` harness(`:446`/`mode=ai_draft` `:472`),**不挂生产热路径**、不制造第二 authority、artifact-missing fail-closed。阶段1/阶段3 的 A/B 与 shadow 就跑在这个挂载点上。**无需更新,直接复用。** |
| `2026-06-04-luban-grading-engine-ai-draft-test-ab-plan.md` | **仍有效(A/B harness 前身,被 real-answer 计划承接)** | AI-Draft A/B + Registry v0 是阶段1 A/B 的底座(已落地在 `learning_brain.py` `_run_ai_draft_harness`)。需更新的只是**对照基准**:A/B 不再是「AI-Draft vs kernel」自说自话,而是**「通道① 编译 rubric vs open-world 现编」谁贴 governed gold**。 |
| `2026-06-22-luban-j01-scoring-points-to-nexus-supply-implementation-plan.md` | **SUPERSEDED(通道混淆,已自废 §0-§10)** | 该文自身的 2026-06-22 更正块已作废「新建 scoring 供给」前提。以本文口径再钉一层:J01 采分点 → **rich-leaf/Nexus 供给属于通道②**(`official_score_allowed=False`),**永远不是官方判分弹药**。「把采分点搬进 rich-leaf bundle 让判分取用」= 试图让通道② 承担通道① 职责,**架构上不成立,整体 superseded**。J01 采分点真值若要进判分,唯一路径 = 走 grading 编译管道进 `v_case_rubric_scored`(即阶段2 的通道① 扩容),不是 rich-leaf promotion。 |

**被本次理解推翻(supersede)的思路集中标注**:
- ❌ 「R5 / v3.2 rich-leaf(5705 点)是判分弹药」→ 通道②,`official_score_allowed=False`,不进①。
- ❌ 「`installed_runtime_supply` flag 打开 = 判分供给通电」→ 死 flag,无 runtime 读者。
- ❌ 「J01 采分点搬进 scoring bundle / Nexus 供给」→ 通道混淆,superseded。
- ❌ 「AI 面板 conc / consensus-gold ≈ 人类真相,可当准确率」→ 同源一致性,非 governed gold;`fleiss_kappa=-0.05` 已证 AI 面板此任务上不可当金标。

---

## 2. 「判分收入闸」里程碑计划

### 2.1 目标 / 非目标

**目标**
- G1 通道① `v_case_rubric_scored` 覆盖从 **51/258 真题**扩到目标覆盖(带官方答案 + 真实分值 + 教材 verbatim 溯源)。
- G2 用**人工 governed gold** 证明「通道① 编译 rubric 判分」在覆盖题上**显著优于 open-world 现编**(判得更准,不是覆盖更多而已)。
- G3 达到 GTM「免费批一道案例题」敢群发的可证伪门槛。

**非目标(明确排除)**
- ✗ R5 / rich-leaf / 深 pack 通道② 的任何扩容——**明确排除出收入闸**。它是 grounding,不改判分弹药覆盖。
- ✗ DeepSeek 单模型成本优化(是成本线,不是收入闸;阶段1 之后按需)。
- ✗ 接生产热路径 / 改 `case_kernel` / 让 RAG 进评分 authority / 新建 schema 或表 / 远端写。

### 2.2 单一权威（铁律，全程不破）

- **采分点真值** 唯一 = grading 编译管道(`run_luban_rubric_compile.py` → `v_case_rubric_scored`;采分点 + `required_terms` 必带 textbook `source_ref`)。不新建第二套 lookup、不从深 pack/rich-leaf 复制真值。
- **governed gold** 唯一 = **人工逐采分点裁决**(多标注人 + 分歧仲裁 + IRR)。AI 面板只作**候选与预标**,`fleiss_kappa=-0.05` 已证其不能单独当金标。
- **判分 authority** 唯一 = `CaseGradingSkillKernel` / 通道① rubric;shadow/AI-Draft 永远 `candidate_only`;写 mastery 唯一经 teacher-final。

### 2.3 阶段化

```
阶段0  J01 最小 governed gold(~150 条人工逐采分点 hit/miss)      ← 一切的前提
  │        我方搭标注 harness,教研人工标
  ▼
阶段1  金标 A/B:通道① 编译 rubric  vs  open-world 现编,谁贴 gold
  │        我方自动化,挂 real-answer 计划的 harness flag
  ▼
阶段2  通道① rubric 覆盖扩容(51/258 → 目标)                     ← 收入闸主体
  │        复用 case-rubric-data-expansion 计划,每扩一批回阶段0/1 验准
  ▼
阶段3  GTM「免费批一道案例题」敢群发门槛
```

---

### 阶段0 — J01 最小 governed gold（前提，不可跳）

**做什么**:对 J01 覆盖的案例题,产出 **~150 条人工逐采分点 hit/miss 金标**(每条 = 某学生答案 × 某采分点 × 人工裁决 hit/partial/miss + 得分 + 依据 span)。这是全项目**第一份治理级人类金标**,取代现有合成 fixture + AI 面板。

**谁做**:
- 我方(自动化):搭**标注 harness** —— 复用 `human-validation-slices` v1 的盲标包结构(question / official_answer / scoring_points / student_answer,PO 不见 ledger/预测)+ `golden-v0-po-review` 的踩字抽查协议;从 `v_case_rubric_scored` 的 J01 子集确定性抽样(优先 open-world 现编题 + 边界/罚则题);**多标注人 + 分歧仲裁 + IRR** 脚手架我方写。
- 教研(人工):**逐采分点标 hit/miss + 得分 + 依据**。AI 面板可作**预标草稿**降低工作量,但最终 authority = 人。

**验收标准**:
- ≥150 条人工逐采分点标注落盘(`artifacts/luban_governed_gold/j01_*/`,gitignore-able,可复现)。
- **≥2 名标注人** 交叉,报告**真 IRR**(Cohen/Fleiss κ);κ 低的采分点进仲裁,不直接入 gold。
- 每条带**依据 span**(逐字来自学生答案)+ 采分点 `source_ref`(教材 verbatim)。
- 金标冻结:`content_hash` + `version_id`,**定义/阈值冻结在先**。

**防假绿 / 防自证(eval-design)**:
- **泄漏**:标注人盲于 ledger / 任何模型预测(v1 盲标规则)。抽样确定性、种子固定。
- **金标治理**:gold = 人,非 AI 面板;`fleiss_kappa=-0.05` 是「AI 面板不可当金标」的直接反例,写进文档当红线。
- **循环度量**:不能用「生成金标的同一模型」去评判分器(阶段1 的臂公平前提)。
- **可证伪**:κ 报告 + 仲裁记录必须可被第三方复算;单标注人 directional 不得称 gold。

---

### 阶段1 — 金标 A/B：通道① 编译 rubric vs open-world 现编

**做什么**:在阶段0 的 J01 governed gold 上,让**同一批学生答案**分别经 **(A) 通道① 编译 rubric 判分** 与 **(B) open-world 现编判分**,对齐 gold 比准确性。回答唯一问题:**编译 rubric 是否显著判得更准?**

**谁做**:我方(自动化)。挂 `2026-06-04-luban-real-answer-runtime-test-integration-plan.md` 设计的 `grading_engine_runtime_test` flag(`learning_brain.py` harness 层,QA-gated,不碰生产热路径),A/B 并排跑,落 `artifacts/`。度量层用 `grading-metric-governance-qwk-plan` 的 QWK + normalized-per-question-delta + §3 五条硬门。

**验收标准**:
- 报告 **通道①(A) vs open-world(B)** 对 gold 的:point-hit agreement、QWK、normalized-per-question-delta,以及 §3 五条硬门(exact_required / penalty / unsupported / evidence_span / textbook-provenance)。
- **判定门(冻结在先)**:通道① 在覆盖题上 point-hit 与 QWK **显著优于** open-world,且五条硬门 A 组全过。
- 明确基线红灯参照:human-vs-artifact-first 历史 point-hit **0.5267** / MAE **4.6091** —— A 组必须显著改善才算通道① 有价值。

**防假绿 / 防自证**:
- **臂公平**:A/B 用**同一批答案、同一 gold、同一度量、同一 prompt 骨架**,只差「rubric 来自编译库 vs 现编」。不给 A 组喂 gold 信息(否则泄漏)。
- **循环度量**:评判用的 gold **不能**由 A 组或 B 组的同源模型生成(阶段0 已保证 gold=人)。
- **度量效度**:raw delta 只作护栏不单独解释;QWK 阈值冻结在先(0.85/0.75 参照 ASAP,不 retrofit)。
- **方差**:样本量 + 置信区间;≥150 条够不够检出效应先做 power 粗估,不够就先扩 gold。
- **可证伪**:预注册「什么结果算 B 赢 / 算无差异」再跑,不看到数字再定义赢。

---

### 阶段2 — 通道① rubric 覆盖扩容（51/258 → 目标）

**做什么**:**这才是收入闸主体**。复用 `2026-06-04-luban-case-rubric-data-expansion-plan.md` 的生产管道(题库 218 case + 2026 教材 verbatim 锚 → 采分点 + `source_ref` → verify-on-write → 4-model 候选 → 教研复核 → 编译进 `v_case_rubric_scored`),把覆盖从 51/258 扩到目标。

**谁做**:
- 我方(自动化):编译管道、verify-on-write 教材锚定闸、4-model 候选、audit packet。
- 教研(人工):把候选升 authority(draft→published 的唯一闸门),高风险/计算/罚则重点复核。

**验收标准**:
- `v_case_rubric_scored` 覆盖真题数从 51 单调上升(每批报真实新增 qid,不伪造)。
- **每扩一批,抽样回阶段0 的 governed gold 协议标注 + 阶段1 A/B 验准** —— 覆盖增长必须伴随「判得更准」证据,否则只是覆盖数字虚高。
- 采分点 + `required_terms` 全部 textbook verbatim 溯源(`enrich_rubric_textbook_provenance.py` 口径);无源不入库。

**防假绿 / 防自证**:
- **不把覆盖数当准确率**:覆盖↑ 与 准确↑ 是两个指标,分开报;扩容后必须重跑阶段1 A/B。
- **金标治理**:新覆盖题的 gold 增量仍走人工裁决,不用 AI 面板补 gold。
- **回归**:已覆盖题的判分不因扩容退化(冻结样本回归)。

---

### 阶段3 — GTM「免费批一道案例题」敢群发门槛

**做什么**:定义并验证「敢把免费批改案例题当获客钩子群发」的**可证伪门槛**——真机上一道真题批改稳、不崩、不编造、判分贴 gold。

**谁做**:我方(自动化真机 eval + content-truth 闸)+ 教研(小样本人工验收)。

**验收标准(冻结在先,全过才敢群发)**:
- 群发候选题**在通道① 覆盖内**(不走 open-world;open-world 题不群发)。
- 真机端到端:粘题不崩、批改稳定、`content-truth` 闸(`2026-06-24-scoring-point-provenance-verification-gate-plan.md` 闸-4)在线拦硬事实编造。
- 判分对该题 governed gold:五条硬门全过 + point-hit / QWK 达阶段1 门。
- 异源裁判抽检(防同源盲点)。

**防假绿 / 防自证**:
- **live 终态验证**:只信真机拉持久化 messages 的终态,不信流式抓包(memory:流式必误判)。
- **可证伪**:预定义「什么情况不群发」;任一硬门破 → NO-GO,不为 GTM 放松踩字。

---

## 3. 相关代码入口 + 依赖旧计划复用

**代码入口(只读参照,本文不改)**
- 通道① 判分弹药:`deeptutor/services/construction_grading/rubric_grader_v1.py`(`_rubric_bank()` ≈`:1195`,load+verify-gate);`v_case_rubric_scored` 亦被 `m35_artifact_query.py` / `canonical_knowledge_manifest.py` 消费。
- 通道① 编译/溯源:`scripts/run_luban_rubric_compile.py`、`scripts/enrich_rubric_textbook_provenance.py`、`scripts/run_luban_per_question_grading_object_full_compile.py`。
- A/B 测试挂载点:`deeptutor/api/routers/learning_brain.py`(`:446` harness、`:472` `mode=ai_draft`、`:63` `_run_ai_draft_harness`),QA-gated,不碰生产热路径。
- 判分 authority(不碰):`deeptutor/services/construction_grading/case_kernel.py` `grade()`;写回唯一口 `writeback.py:17`;teacher-review 写回 `teacher_review_writeback.py:44`。
- AI 面板 gold(降级为候选/预标,非金标):`scripts/run_luban_arbitration_gold_panel.py`、`scripts/run_luban_m35_ai_governed_gold_labeling.py`、`scripts/run_luban_grading_verdict_ab.py`。
- 通道②(排除出收入闸,仅参照):`rich_leaf_runtime.get_rich_leaf_context()`;`installed_runtime_supply`(死 flag)。

**依赖旧计划复用**
- 阶段0 ← `human-validation-slices-artifact-versioning-v1`(盲标包结构) + `golden-v0-po-review`(踩字抽查协议) + `ai-anchored-golden-production-playbook`(AI 预标方法,但只作候选)。
- 阶段1 ← `real-answer-runtime-test-integration`(flag 挂载点) + `grading-metric-governance-qwk`(度量) + `grading-engine-ai-draft-test-ab`(A/B 底座)。
- 阶段2 ← `case-rubric-data-expansion`(生产管道,直接主轴)。
- 阶段3 ← `2026-06-24-scoring-point-provenance-verification-gate-plan`(content-truth 闸-4)。
- 成本侧(非关键路径,阶段1 后按需)← `deepseek-production-shadow-v0`。

---

## 4. Plan Directory Discipline — 挂载说明

本文挂进 `docs/plan/INDEX.md` 的 **`评分引擎与金标工件/`** 主线(§目录分组:「案例题评分、golden eval、M35 scoring artifacts、AI governed gold、rubric 数据和评分质量门」)。

建议 INDEX 追加条目(接在 `2026-06-10-luban-m35-no-go-to-go-ai-governed-gold-execution-plan.md` 之后,§鲁班评分引擎总控入口区块):

```
- [2026-07-05-luban-grading-revenue-gate-reconciled-milestone-plan.md](评分引擎与金标工件/2026-07-05-luban-grading-revenue-gate-reconciled-milestone-plan.md) — `Reconciled milestone plan / 判分收入闸 / Proposed`,把 2026-06 一批金标/rubric/shadow 计划按「判分两通道」口径逐份对账并给出可执行里程碑。核心口径:收入闸 = 通道①(`v_case_rubric_scored`,~174 qid/1221 点,官方答案+真实分值,rubric_grader_v1 `_rubric_bank`)覆盖扩容(现 51/258→目标),通道②(rich-leaf R5/v3.2,`official_score_allowed=False`,`installed_runtime_supply` 死 flag)明确排除。两通道证明「判得更准」都卡在 governed gold(现唯一 gold 是合成 fixture+AI 面板 fleiss_kappa=-0.05,无人工逐采分点金标)。阶段0 J01 最小 governed gold(~150 条人工逐采分点 hit/miss,我方搭 harness+教研标+≥2 标注人真 IRR)→ 阶段1 金标 A/B(通道① 编译 rubric vs open-world 现编谁贴 gold,挂 real-answer 计划 flag)→ 阶段2 通道① 覆盖扩容(复用 case-rubric-data-expansion)→ 阶段3 GTM 免费批一道案例题群发门槛。superseded:R5/深 pack/J01→Nexus 供给当官方判分弹药、AI 面板 conc 当人类真相。全程 candidate_only、不接 runtime、不碰 kernel、不新建 schema/表。
```

(挂载条目由后续 docs PR 落地;本 agent 只写计划正文,INDEX 追加建议如上。)
