# F16 防水工程 — Step 0 Existing Artifact Scan

> Plan: docs/plan/鲁班移动端提分闭环/2026-06-11-luban-mobile-case-family-asset-production-plan.md §4 Step 0
> Date: 2026-06-12
> Scope: read-only 盘点，无任何资产生产或状态翻转

## 1. Existing rubric / registry / grading artifact references

| Asset | Location | 实测状态 | F16 可复用性 |
|---|---|---|---|
| M32 Grading-to-Brain 防水纵切 | `artifacts/luban_grading_artifacts/grading_to_brain_m32_waterproof_20260608/` | GO，但 grading ledger 仅 1 条合成题 `waterproof_case_001`（1 个采分点 `waterproof_exact_required_001` 聚合物水泥防水砂浆） | 闭环结构样板（evidence→claim→PCP→NBA→retest），**不是题池、不是判分资产包** |
| `topic_waterproof` runtime shard | `deeptutor/services/construction_grading/runtime_supply/v_topic_waterproof/topic_waterproof.json` | `release_candidate`，`published=false`，`official_score_allowed=false`，44 nodes，content_hash `615f6443…`，文件 sha256 前缀 `471695aff6c3e0a4` | 仅 teaching context / topic supply；不得作 answer key 或 scoring truth（与 M0 §4.2 一致） |
| Registry v0 published 判分 artifacts | `artifacts/luban_grading_artifacts/registry_v0_20260604/question_grading_artifacts.jsonl`（20 题，18 published） | 零道防水**主体**案例题；但 **Q18-1A434000（published）的 P10/P11 是屋面卷材防水起鼓割补法工序采分点**（P10 exact_required 0.75 分：放气/擦干/清除旧胶结料；P11 high_risk_review 0.75 分：喷灯烘烤/分层剥开/重贴新卷材），纯文字、无图依赖 | **F16 spike 首选判分 authority**：semi-write task 用 `task_scope.covered_scoring_point_ids = [Q18.P10, Q18.P11]` 复用已签发点，零新编译开工 |
| M2 候选案例题 | `artifacts/luban_grading_artifacts/case_rubric_expansion_m2_20260604/candidate_case_questions.json`（30 题） | `M2-2015-31-00/01/02/03`（2015 真题第 31 题，4 小问，含官方答案）为防水相关案例题；其中 **31-02 为屋面卷材防水找错题**（泛水高度 250mm / 阴阳角 45°或圆弧 / 附加层） | F16 案例题首选源；官方真题 + 官方答案，provenance 完整 |
| M3 采分点候选 | `artifacts/luban_grading_artifacts/case_rubric_structuring_m3_20260604/scoring_point_candidates.json` | `M2-2015-31-02` 已抽取 8 个采分点候选（带 `official_answer_span`、`policy_type`、`required_terms`），但全部 `needs_jury_review=true`、`confidence=0.5`、`max_score=null` | 半成品：抽点工作可复用，但必须走 jury review + max_score 裁定 + 签发后才能进判分链路 |

## 2. Canonical taxonomy node matches

- Runtime 钉扎的 taxonomy authority：`deeptutor/services/construction_grading/runtime_supply/v_canonical_taxonomy_index/canonical_taxonomy_index.json`
  - `canonical_taxonomy_version: FINAL_CLEANED_TAXONOMY2026`，`content_hash: 22a402276a23dd9da54652c93ceabeac9a5c15f3c2c764e4a02b3b2c27390d48`
  - 文件 sha256：`ef9848604ac2449b9c5082f14bb9a9c4e6548eae25d17de529628ea3a8fdfe5b`
  - 1642 个 book-derived 叶子（`1A411011-B001` 形态），其中 **118 个叶子 keyword 含"防水"**
- 风险（**当日实证**）：本报告上午记录的文件 sha256 `ef984860…` 在同日 18:00 前已变为 `0990ec30…`（manifest content_hash 同步变为 `c07c2d77…`）——taxonomy 一天内多次改写被当场证实。结论：sha 钉扎只能是**写入时快照 + status 翻转时 reviewer 人工重验**（计划 §3.1 修订版），任何"自动降级"承诺在当前零自动化检测的现实下都是死文字。F16 资产创建时须以当时的 runtime index 现值重新钉扎，不要抄本报告中的历史 sha。

## 3. Question pool and source_refs coverage

- 客观题/轻练池：`artifacts/assessment_testset/p0a/p0a-phase-minus-1-current/coverage_waterproof.md`
  - 391 candidate / 159 eligible / 12 delivered recommendation；answer-key 覆盖 391/391
  - 排除项需避开：figure refs 55、long-stem 43、table refs 5、missing_options 206、semantic duplicates 25
  - → light practice 与"同采分点不同题"复测池**可用**，选题须过移动端渲染筛
- 案例题源：
  - 首选 `M2-2015-31-02`（官方 2015 真题、官方答案、M3 已抽 8 点）
  - ⚠️ 31-02 题面依赖"图2 女儿墙防水节点施工做法示意图"——移动端 figure 渲染风险；进入 Step 1 时必须裁决：补图渲染 / 文字化改写（需审）/ 换 2016-2025 真题中无图防水案例题
  - 备选源：`/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/题库/`（2015-2025 真题 + 章节千题斩 + 864考证宝典），Step 1 检索无图防水案例题
- mistake_tag 现状：`mistake_tag` 在 `deeptutor/` 代码中**零命中**；现有错误事件 authority 是 `GradingErrorEvent`（`deeptutor/services/construction_grading/schema.py:32`，字段 `error_code/severity/concept_tag/evidence/diagnosis`）。P0A 按 M0 锁定 display-only，canonical 写入需 contract + readback test。

## 4. Gap list

| # | Gap | 阻塞什么 | 处置 |
|---|---|---|---|
| G1 | ~~无 published 防水案例题判分 artifact~~ → **已缩小**：Q18 P10/P11 已签发可直接复用；纯防水主体题（如 2015-31-02）仍需 jury → 签发 | 真实 AI 批改的扩展面 | Spike 用 Q18 P10/P11；扩展时再推 31-02 的 8 个候选点走 jury review → max_score 裁定 → 签发 |
| G2 | `case_family` F16 本体不存在 | 一切下游绑定 | Step 1-2 产出 `case_family.yaml`，taxonomy_ref 钉 §2 hash |
| G3 | ~~canonical mistake_tag 清单不存在~~ → **已消解**：错因 canonical authority 已存在（`error_codes.py` ERROR_CODE_REGISTRY，23 个受管 code），mistake_tag 是其采分点粒度 qualified reference | 错因复练、错题本归因 | 映射（不发明）：P10/P11 → E06/E03；display-only 直至 contract 冻结 |
| G4 | light / semi-write / retest task 不存在 | 今日任务、半写训练 | Step 4 设计；light 用候选 14075/14079/12888；retest 走 `same_node` 阶梯（P10/P11 无 same_point 题，已全库证实）|
| G5 | 防水案例题普遍依赖构造图/节点图（这是考点形态本身，非个别题问题） | 移动端真实作答体验 | Spike 阶段用 `task_scope` 子集规避（Q18 P10/P11 纯文字）；P0A 扩展前裁决题面图片渲染路径（题库 docx 源含图，`docx_render_check*` 目录已有渲染检查工作） |
| G6 | `question_binding` 清单不存在 | 复测绑定规则 | Step 2 之后，与 G4 一起产出 |

## 5. Step 0 reject check

- [x] 未在检查既有签发资产前开始人工搜题（本报告即先扫描）
- [x] artifact 质量已抽查：registry 3 个"防水"假阳性已识别并排除；M3 采分点候选的 `needs_jury_review` 半成品状态已如实记录

## 6. Step 1 源筛选结论（2026-06-12 同日完成；同日经专家团对抗复审更正）

对外部题库 `FastAPI20251222/docs/2026/题库/`（2015-2025 真题年度 JSON）扫描，防水密度 ≥3 的案例 chunk 共 16 个。关键结论：

1. **防水案例题几乎都带构造图/缺陷图**（2015-31 图2 女儿墙节点、2021 屋面构造、2023 图1-7 后浇带防水构造、2025 保障房案例均带图）。"找错题/构造命名题"的错误就藏在图里，无图无法作答——G5 不是选题问题，是题型形态。
2. **Spike 主判分载体定为 Q18-1A434000 P10/P11**（published、纯文字防水工序点；`artifact_id=Q18-1A434000::qga_v0_20260604`），semi-write `task_scope` 只声明这两个点，范围外点 `not_evaluated`。
3. **模拟学生答卷源**：`近三年案例题_按学生答卷排版.md` 按高/中/低水平分层（如 `Q2023-01__S01` high/excellent），可直接支撑 shadow grading replay；注意它是**模拟作答**，不得当真实学生数据。
4. 扩展候选（带图裁决后）：`M2-2015-31-02`（屋面卷材防水找错，8 个采分点候选已在 M3 抽取）、2021 案例一（防水x56，劳动用工+屋面构造）、2023 案例一（质量检测+后浇带防水构造）。

### 6.1 对抗复审更正（2026-06-12，三处初版错误结论收回）

1. **31-02 不是 P10/P11 的同采分点复测题**（初版误判）。31-02 考屋面防水**设计规范**（泛水高度 250mm、阴阳角 45°/圆弧、附加层），P10/P11 考起鼓卷材**割补工序**——不同能力维度。全题库扫描（2015-2025 真题 chunks + 30 题候选 + 客观题池）确认：割补法/起鼓工序**没有第二道题**（2017 案例二即 Q18 同源题）。P10/P11 的复测在 P0A 只能走 `same_node` 阶梯（silver），不得伪装成 point-level 干净提升证据。
2. **M32 合成点 `waterproof_exact_required_001` 从 spike 判分点中移除**（初版误纳）。它来自合成题 + topic shard（`official_score_allowed=false`），按计划 §3.1 修订版"teaching shard 与合成题的点不得作为判分点"，只保留为闭环结构参考。
3. **mistake_tag 不映射 `concept_tag`，映射 `error_code`**（初版字段误指）。错因 canonical authority = `deeptutor/contracts/error_codes.py` 的 `ERROR_CODE_REGISTRY`（E01-E12/M01-M10）；`concept_tag` 装的是 taxonomy node code，不是错因。

### Spike M1 资产包组成（更正版，对照 M0 §4.3）

| M0 要求 | 落点 |
|---|---|
| 1 个 case_family | `F16`，taxonomy_ref 以创建时刻 runtime index 现值钉扎，knowledge_nodes 从 118 个防水叶子中选绑 |
| 1 个完整案例题/小问 | Q18-1A434000 防水小问（屋面卷材防水起鼓割补法），question_binding 带 `sub_question_ref` |
| 3-5 个 scoring_point_id | **active**：Q18.P10、Q18.P11（authority_refs 引用 `Q18-1A434000::qga_v0_20260604`）；**draft**：从 31-02 的 8 个候选中选 2-3 个最强点（如泛水高度、阴阳角做法），带 official_answer_span source_ref，走 jury -> registry v1 publish 后转 active |
| 每点 1-2 个 mistake_tag | error_code 引用：P10/P11 → `E06 程序顺序错误` + `E03 关键词缺失`；display-only 直至 contract 冻结 |
| 1 light task | 客观题池候选 14075 / 14079 / 12888（防水材料基础，有选项无图非长题干）|
| 1 semi-write task | Q18 防水小问，`task_scope={P10,P11}`，`evidence_weight=diagnostic`；**task_scope runtime contract 落地前停在 `p0a_candidate`（shadow）** |
| retest binding | `binding_level=same_node`：防水客观题池 + 31-02（签发后，作同节点深化而非同点复测）；诚实标注无 `same_point` 复测题可用 |
