# 数据盘点索引 (Data / Asset Inventory Index)

> 本目录收录鲁班智考所有**数据资产盘点**记录:原始资料、编译产物、考点统计、供给估算、母题适用性压测、计算公式、真题分值视觉核查、分值抽取等。
>
> **约定(每次数据盘点必做):**
> 1. 每做一次数据盘点 → 写一份 `YYYY-MM-DD-<主题>.md` 落本目录;
> 2. 在本 INDEX 表格加一行;
> 3. 文档须含:**范围/方法、关键发现、缺口与诚实边界、数据来源路径(可复查)、结论**;
> 4. 抽样未覆盖的明确标注,不假装读全;有版本/重复风险须标当前 canonical 版;
> 5. **细节密度**:确切路径、schema 版本、逐项计数、真实样本记录都要落进去,不要压成一句话总结;
> 6. **结论被后续盘点推翻时,在新文档里显式订正旧结论**(留迭代痕迹,不静默改);
> 7. **抽取/编译类盘点**:产物落 `docs/原始数据/数据盘点/extractions/`(**注意 `/artifacts/*` 被 .gitignore,仅 `luban_case_family_assets/` 白名单——抽取产物入库放 docs 下**),方法/schema/验证落本目录,二者互相引用,**以后可复用**。

## 盘点记录

| 日期 | 文档 | 一句话结论 |
|---|---|---|
| 2026-06-16 | [原始数据资料盘点](2026-06-16-原始数据资料盘点.md) | `docs/原始数据`(4.6G):11 年真题(337 选+218 案例)+ ZL500(403)+ 千题斩(630)+ 650 知识卡 + 规范库;真实考生作答=0;分点 rubric 在结构化 JSON≈0(**但 PDF 解析里有,见视觉核查**) |
| 2026-06-16 | [真题考点实证频次](2026-06-16-真题考点实证频次.md) | 11 年案例题考点(方向性):混凝土 184 / 安全 119 / 进度 68 / 质量 50 / 防水 46;**防水非案例旗舰,首个案例母题应选混凝土/进度/安全** |
| 2026-06-16 | [编译资产盘点](2026-06-16-编译资产盘点.md) | **编译引擎已建 ~80% 卡在 shadow**:RichLeaf v3.2 5705 采分点 + 313 深编译叶 + per_question 482 采分点 + 边界 gold + MAE 0.0749 判分器;缺逐点分值/真人签字/真实作答。**2026-06-18 补当前实测**:runtime supply 10 pointer 中 4 published / 6 unpublished;PGO 482/482 point score null;artifacts 厚不等于 release truth |
| 2026-06-16 | [编译资产·母题适用性压测](2026-06-16-编译资产母题适用性压测.md) | 两考点试拼母题 8 模块:**合格原料非成品,大部分够+局部二次优化**;骨架优秀级;**M4 分值经三次迭代订正→见真题PDF视觉核查** |
| 2026-06-16 | [计算公式汇总盘点](2026-06-16-计算公式汇总盘点.md) | 公式汇总 PDF 26 条;计算型母题"数值判据层"权威原料,强在计价/造价/挣值/索赔;网络计划时间参数+流水+规范限值不在此表 |
| 2026-06-16 | [真题PDF分值视觉核查](2026-06-16-真题PDF分值视觉核查.md) | **视觉读真题 PDF 解析:每个采分点的分值齐全**(含计算步骤分/0.5分粒度/部分给分规则);订正"per-point 分值缺"——分值在 PDF 解析里;M4 是"视觉抽取"非缺料(佑森估分,非官方) |
| 2026-06-16 | [真题分值抽取方法与首份验证](2026-06-16-真题分值抽取方法与首份验证.md) | **可复用抽取协议** + 2025 首份验证(产物 `docs/数据盘点/extractions/2025_jianzhu_case_rubric.jsonl`,80 采分点/8 种 point_type 全覆盖)。**关键发现:踩点制"给分点池 ≥ 小题满分",判分=Σ命中×点分 封顶**(案例4 Σ=30/案例5 Σ=29 超 20 属正常) |
| 2026-06-16 | [★给分逻辑(分值引擎基础)](2026-06-16-给分逻辑(分值引擎基础).md) | **分值候选引擎地基**:从 431 采分点反推给分逻辑——**1.0 分/单元**(非列举型 80%)+ 小题满分 3-7 + 列举二态(逐项1分/开放列举"写N项得N分")+ 项数>满分则 0.5/单元 + **踩点池封顶 min(Σ命中,满分)**;输出 `proposed_point_scores`,`score_authority=engine_rule_derived`,`official_score_allowed=false`; signed grading artifact / `CaseGradingSkillKernel` 签发后才可 official 判分 |
| 2026-06-16 | [★母题引擎·资产利用全图](2026-06-16-母题引擎资产利用全图.md) | **capstone**:每个引擎组件用哪份资产+现状+装配顺序。**做顶尖母题引擎的资产已备齐~80%、大多已建(shadow)**;6层流水线(来源/编译/生成/判分/诊断/前台)料全就位;**唯一真缺=真实考生作答×专家裁决判分一致性**(留存采);差异化=踩点分值候选×score_assigner proposed scores×313深编译×多模型校准×结构化错因 的复利链,不是题量 |
| 2026-06-16 | [深题供给估算](2026-06-16-深题供给估算.md) | 早期估算:6134 采分点仅 ~1-2% 可直接做深题;已被"313 深编译叶"结论取代 |
| 2026-06-17 | [★多LLM专家裁决判分一致性记录盘点](2026-06-17-多LLM专家裁决判分一致性记录盘点.md) | **找回大量多 LLM 盲审+仲裁+对抗+A-B+金标记录**(arbitration_gold_panel 共识 90% 复现参考金标 / four_arm judge MAE 0.075 点P 1.0 / m35 带对抗检察官+变异测试 / ~40 consensus_gold 子目录)。**订正《全图》"唯一真缺口"**:拆成三件——专家裁决(不缺,已验证)、真实考生作答(仍缺,语料全合成/archetype/fixture)、金标 directional→governed_gold(仍开口,卡额度墙弃票非分歧,纯 API 路线已验证修法) |
| 2026-06-17 | [OpenMAIC 图解引擎评估](2026-06-17-openmaic-图解引擎评估.md) | **第二意见**:白板 3/10,不适合做规范级建筑构造剖面;交互 HTML/SVG diagram 6.5/10,可借鉴为鲁班图解微课静态互动卡;不要引入 AGPL/课堂 App,只学习 SVG 流程图、step reveal 和离线资源内联思路 |
| 2026-06-18 | [原始数据当前快照与可用性分析](2026-06-18-原始数据当前快照与可用性分析.md) | 当前实测原始资产 1107 文件 / 4.75GB(排除 `.git`/`.DS_Store`/本次盘点文档);结构化主力=11 年真题 555 题 + 章节练习 1033 题 + 2026 教材 650 blocks + taxonomy 1976 叶 + 8 部规范 5077 nodes。**补测编译资产**:knowledge_compiler 189 文件、grading_artifacts 3314 文件、runtime_supply 57 文件;边界仍是 shadow/workbench ≠ release truth。 |
| 2026-06-18 | [深母题引擎底座数据资产实施判断](2026-06-18-深母题引擎底座数据资产实施判断.md) | 现有资产足够做第一条深母题引擎竖切，但底座应是 source registry → candidate compiler → gate/review → signed runtime_supply 的签发型 Deep Archetype Pack；F16 做留存薄切片，F01 做深判分旗舰，禁止把 artifacts/workbench、PGO score-null 或样例母题原型冒充 active release truth。 |
| 2026-06-19 | [清洗 JSON 源账本 v0](2026-06-19-清洗JSON源账本v0.md) | **清洗 JSON 不再按 PDF 原件假设处理**:登记 `docs/原始数据/2026_副本` 下 383 个 JSON(真题 11 / 标准 8 / 讲义 335 / 教材 18 / taxonomy 9 / 练习 2),产物为 `json_source_ledger_v0`;统一 `authority_status=raw_evidence_ledger`、`runtime_consumable=false`、`official_score_allowed=false`,作为 OKF/编译候选输入账本。 |
| 2026-06-19 | [OKF Dry Consumer v0](2026-06-19-OKF-dry-consumer-v0.md) | **OKF compiled pack 已可干消费**:读取 1 case / 5 rubrics / 15 scoring points,生成 `okf_dry_consumer_v0/receipt.json`;状态 `dry_consumed_non_runtime`,继续拒绝 runtime / canonical / LearnerState / GBrain / official score 写入。 |
| 2026-06-19 | [OKF Source Alignment v0](2026-06-19-OKF-source-alignment-v0.md) | **source alignment blocker 已解除**:25/25 canonical cases 对齐到清洗真题 JSON case chunk;9 个 case 达到小问 ordinal match,16 个先为 case-level only;继续 `runtime_consumable=false`。 |
| 2026-06-19 | [OKF Candidate Scope v0](2026-06-19-OKF-candidate-scope-v0.md) | **OKF source-layer 第一阶段目标已落地**:生成 25 cases / 117 rubrics / 431 scoring points 的 candidate artifacts 与 `scoring_point_index.json`;状态 `source_layer_candidate_complete`,非 signed runtime supply。 |
| 2026-06-19 | [OKF 落地差距报告 v0](2026-06-19-OKF落地差距报告v0.md) | **目标差距已归零**:canonical rubric 目标 25 cases / 117 rubrics / 431 scoring points;当前 OKF candidate scope 25 / 117 / 431;剩余 0 / 0 / 0。下一步进入签发前验证,继续 `runtime_consumable=false`。 |
| 2026-06-19 | [全数据资产 AI 速览 v1](2026-06-19-全数据资产AI速览v1.md) | **目标改为全数据资产总账**:生成 `data_asset_brief_v1`,让 AI 一分钟知道 1107 原始文件 / 383 清洗 JSON / 95 PDF / 615 图片 / 555 真题 / 1033 章节题 / 650 教材 blocks / 5077 标准节点 / 431 候选 scoring points;状态 `asset_inventory_only`,非 runtime supply。 |
| 2026-06-19 | [PDF 源账本 v1](2026-06-19-PDF源账本v1.md) | **PDF 逐文件账本已生成**:95 个 PDF 全部 hash/分类/候选派生状态建账;39 个有候选结构化派生引用,56 个仍需编译或映射;状态 `raw_pdf_evidence_ledger`,非 runtime supply / 非 official score authority。 |
| 2026-06-19 | [编译资产收录 v1](2026-06-19-编译资产收录v1.md) | **artifacts 编译资产已纳入总账**:索引 5,059 文件 / 21 分组 / 545 manifest-like 快照;payload 保留原路径,状态 `compiled_asset_inventory_only`,非 runtime truth / 非 official score authority。 |
| 2026-06-19 | [编译资产 Authority Map v1](2026-06-19-编译资产AuthorityMap-v1.md) | **编译资产消费边界已建图**:21 group 全部分类;真实 runtime pointer / manifest 15 条,其中 4 published+hash-gated、11 candidate/blocked;`artifacts/*` 直读 runtime 允许数=0。 |
| 2026-06-19 | [资产缺口地图 v1](2026-06-19-资产缺口地图v1.md) | **OKF/source/runtime 缺口地图已生成**:9 个开放缺口项(P1 5 / P2 4);P1 包含真题内容缺口 139、P1 PDF 21、OKF case-level-only 16、OKF candidate 未签发 25、`v_case_rubric_scored` live-reader policy conflict 1;状态 `asset_gap_map_only`。 |
| 2026-06-19 | [OKF Bundle v0](okf_bundle_v0/index.md) | **回归 Google-style OKF 极简形态并补 L1 内容卡**:只输出 Markdown + YAML frontmatter + links;新增真题年份、案例 rubric、教材、标准、讲义、章节练习 content cards,让 AI 可扫读核心内容结构,但不镜像全文、不接 runtime。 |
| 2026-06-19 | [OKF-like rubric pilot v0](okf_pilot/rubric_v0/index.md) | **最小 OKF-like 小样**:从 `case_rubric_canonical.json` 切 2021 案例一,生成 1 case / 5 rubric / 15 scoring point 的 Markdown review projections 与 compiled JSON inspection artifacts;保留 `authority=training_org_analysis_yousen`、`not_official=true`、`official_score_allowed=false`,补 question/rubric provenance 与 machine non-runtime guard,不接 runtime。 |

## 抽取产物(`docs/原始数据/数据盘点/extractions/`)

| 产物 | 状态 |
|---|---|
| `2025/2024/2023/2021/2022bukao_jianzhu_case_rubric.jsonl` | ✅ 全 6 份抽完(80/67/89/85/110 采分点) |
| `ALL_jianzhu_case_rubric.jsonl`(**431 采分点 / 5 年**) | ✅ 合并 + **5 份独立专家复核(高准确率,仅 2024 漏 1 字已订正;OCR可疑多为佑森源数据自身错字)** |
| **`case_rubric_canonical.json`(历史文件名;真题案例 rubric 候选)** | ✅ **全 431 采分点结构化(5年/25案例/117小题,judging rule 内嵌),一个没跳——signed grading artifact 的分值候选输入,不是 official score authority** |
| `per_question_score_backfill.jsonl`(桥) | ✅ 合并法回填 **179/199(89%)**(2021/23/24/25,切片含多采分点则累加吃掉 granularity collapse);**per_question 结构乱,判分应直接用 signed artifact / rubric 候选输入,此为旧消费者桥**;2015-2020+2022正考无源**待补(不跳过)** |
| `json_source_ledger_v0/` | ✅ 清洗 JSON raw evidence ledger:`manifest.json`、`sources.jsonl`、`summary.json`;登记 `2026_副本` 下 383 个 JSON,保留 hash / bucket / JSON shape / runtime guard,**非 runtime supply / 非 official scoring authority** |
| `okf_dry_consumer_v0/` | ✅ OKF dry consumer receipt:`receipt.json`、`receipt.md`;证明 `okf_rubric_pilot_v0` compiled artifacts 可被读取且 guard 全 false,**非 runtime supply / 非 official scoring authority** |
| `okf_source_alignment_v0/` | ✅ OKF source alignment:`report.json`、`report.md`、`case_alignment.jsonl`;25/25 canonical cases 对齐清洗真题 JSON chunk,其中 9 ordinal match / 16 case-level only,**非 runtime supply / 非 official scoring authority** |
| `okf_candidate_scope_v0/` | ✅ OKF full candidate scope:`manifest.json`、`cases.jsonl`、`rubrics.jsonl`、`scoring_points.jsonl`、`scoring_point_index.json`;覆盖 25 cases / 117 rubrics / 431 scoring points,**非 runtime supply / 非 official scoring authority** |
| `okf_landing_gap_v0/` | ✅ OKF source-layer gap report:`report.json`、`report.md`;比较 canonical rubric 目标、JSON ledger 原料、OKF pilot、dry consumer、source alignment、candidate scope,输出剩余 0 cases / 0 rubrics / 0 scoring points,**非 runtime supply / 非 official scoring authority** |
| `okf_rubric_pilot_v0/` | ✅ OKF-like 试点 compiled inspection artifacts:`manifest.json`、`question_context_pack.json`、`scoring_point_index.json`;当前仅 2021 案例一,用于验证 canonical extraction → generated review projection → compiled inspection pack 的可追溯形状,**非 official score authority / 非 runtime supply** |
| `data_asset_brief_v1/` | ✅ AI-first 全数据资产总账:`manifest.json`、`asset_buckets.json`、`ai_brief.md`;聚合 raw profile / JSON ledger / OKF candidate scope,输出 1107 原始文件、383 JSON、95 PDF、615 图片、555 真题、1033 章节题等一页式入口,**asset_inventory_only / 非 runtime supply / 非 official scoring authority** |
| `pdf_source_ledger_v1/` | ✅ PDF raw evidence ledger:`manifest.json`、`pdf_sources.jsonl`、`summary.md`;95 个 PDF 全部逐文件 hash/分类/候选派生状态建账,39 个有候选结构化派生引用、56 个仍需编译或映射,**raw_pdf_evidence_ledger / 非 runtime supply / 非 official scoring authority** |
| `compiled_asset_ledger_v1/` | ✅ 编译资产 inventory ledger:`manifest.json`、`asset_groups.json`、`files.jsonl`、`manifest_refs.jsonl`、`manifest_snapshots/`;索引 `artifacts/` 与 `runtime_supply/` 5,059 文件,复制 545 个小型 manifest-like 快照,**compiled_asset_inventory_only / 非 runtime supply / 非 official scoring authority** |
| `compiled_asset_authority_map_v1/` | ✅ 编译资产 authority map:`manifest.json`、`group_authority.json`、`runtime_pointers.jsonl`、`consumer_policy.json`;21 group 分类,15 条真实 runtime pointer / manifest 审计,4 published+hash-gated / 11 candidate-blocked,**authority_map_only / 非 runtime install / 非 official scoring authority** |
| `asset_gap_map_v1/` | ✅ 资产缺口地图:`manifest.json`、`gap_summary.json`、`gap_items.jsonl`、`action_queues.json`、`next_actions.json`;9 个开放缺口项(P1 5 / P2 4),含 JSON claim review、PDF compile/provenance、OKF 小问级 alignment、runtime consumer evidence 和 live-reader policy conflict,**asset_gap_map_only / 非 runtime supply / 非 official scoring authority** |

## 待办盘点(下次补)

- [x] 抽全 6 份真题分值(431 采分点)+ 5 份独立专家复核(2026-06-16 完成,高准确率)
- [ ] **回填 `per_question_grading_object` 的 `score:null`**(对齐真题分值,标 authority=yousen)+ 写封顶判分规则
- [ ] **给分逻辑:跑留一年交叉验证 + 落 `score_assigner` 函数**(分值引擎,authority=engine_rule_derived)
- [ ] RichLeaf v3.2 token pack 与 313 深编译 runner 是否已合流
- [ ] 各年案例 `correct_answer` 逐年核实(范文 vs 分点)
- [ ] `rubric_compile_20260607` / `blocked_point_rubric_normalization_m35` 深读
- [ ] 真题 node 级精确高频排序;安全/危大、质量/验收 母题适用性压测
- [ ] 网络计划/流水公式结构化 + 计算公式汇总编译成 formula registry
- [ ] 核案例 sub_q 总分结构(案例四/五 Σ>20——踩点制 or 分值结构)
