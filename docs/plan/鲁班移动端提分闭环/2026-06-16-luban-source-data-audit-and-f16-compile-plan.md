# 鲁班母题引擎原始资料审计与 F16 首包编译计划

Status: Proposed / Source Audit
Date: 2026-06-16
Scope: `/Users/yehongchen/Developer/CYH_2/Markzuo/deeptutor/docs/原始数据`

## 0. 结论

`docs/原始数据` 不是一个可以被母题引擎直接递归读取的“干净原始数据仓”。它是一个混合落盘目录：原始 PDF、教材清洗 JSON、真题清洗 JSON、讲义增强 JSON、taxonomy 冻结件、Supabase 导入脚本、旧 HTML 原型、Graphify 可视化产物、DOCX 渲染截图、内嵌 `.git`、`.DS_Store` 混在一起。

母题引擎第一条硬规则应是：

```text
default exclude everything
  -> only compile registry allowlist
  -> every compiled span must carry source_path + source_sha256 + span_hash + authority_tier
```

这批资料足够支撑 F16 防水母题首包，但只能先签为 `provisional teaching/diagnosis candidate`。在 GB 55030 OCR、GB 50108/GB 50208 独立原文、图示题图片映射、official rubric、F16 taxonomy mapping 没闭合前，不能宣称“官方规范闭环”“图示题完全闭环”或“正式判分 authority”。

## 1. 专家分工

本轮用 6 个只读 subagent 专门分析原始资料：

| 专家 | 负责面 | 核心结论 |
| --- | --- | --- |
| 原始数据总库存 / 资料治理 | 目录规模、污染、重复、排除规则 | 不允许递归读目录，必须 registry allowlist |
| PDF/OCR/source_ref candidate | PDF 可检索性、OCR、权威分层 | 只有少数标准 PDF 可作为 source_ref candidate，进入 allowlist + hash span + reviewer 后才可消费；GB 55030 当前不可检索 |
| 2026 教材 JSON | 教材 chunk、taxonomy、span 规则 | `content_markdown + source_meta + chunk_id` 可做 source span，增强字段只能 candidate |
| 真题/题库/评分素材 | 2015-2025 真题、ZL、千题斩、案例模拟答卷 | 真题 JSON 可做 question binding，不是 official rubric |
| 讲义/教学素材 | 8 套讲义、6.21 防水讲义页 | 讲义只能做 B 层教学解释、误区、口诀、考情 |
| F16 防水专项 | 首包 source_refs、缺口、首日编译清单 | F16 可先做教材 + 真题绑定最小包，但必须标 provisional |

## 2. 本地命令证据

本轮主线程与专家只读核验得到：

```text
du -sh docs/原始数据                                     -> 4.6G
du -sh docs/原始数据/PDF                                 -> 4.1G
du -sh docs/原始数据/2026_副本                            -> 536M
du -sh docs/原始数据/2026_副本/2026教材                    -> 54M
du -sh docs/原始数据/2026_副本/题库                        -> 219M
du -sh docs/原始数据/2026_副本/讲义                        -> 11M
du -sh docs/原始数据/2026_副本/标准文件                    -> 41M
du -sh docs/原始数据/2026_副本/taxonomy                    -> 12M
```

排除 `.git` 后文件数与类型：

```text
find docs/原始数据 -path '*/.git/*' -prune -o -type f -print | wc -l -> 2046

.md        859
.png       611
.json      410
.pdf        95
.DS_Store   41
.py         10
.html        5
```

浅层入口统计会严重低估规模；真实编译对象在深层 `讲义/page_*.json`、题库 JSON、渲染 PNG、Graphify MD 中。

## 3. 资料分层

### 3.1 A 层：可作为 registered source_ref 的候选

A 层不是“看起来官方”的文件，而是能通过版本、路径、hash、页码或 chunk、文本可读性、人工抽样确认的源。

当前最明确：

| 来源 | 路径 | 可用性 |
| --- | --- | --- |
| 屋面工程质量验收规范 | `/docs/原始数据/PDF/行业标准文件/18、GB+50207-2012屋面工程质量验收规范（清晰版）.pdf` | `pdftotext` 可稳定抽出防水、淋水/蓄水、验收资料等文字，可优先做屋面验收 registered source_ref candidate |
| 2026 教材 core JSON | `/docs/原始数据/2026_副本/2026教材/第二次加强/v3_production_core*.json` | 可作为教材 span 的机器入口，但必须只信 `content_markdown/source_meta/chunk_id/original_chunk_id` |
| 2026 教材 PDF | `/docs/原始数据/PDF/教材/2026一建《建筑》电子版教材.pdf` | 可定位章节，文本层有 OCR 错字；registered source_ref 建议以 JSON span + PDF 页码互证 |
| taxonomy 当前候选 | `/docs/原始数据/2026_副本/taxonomy/FINAL_CLEANED_TAXONOMY2026.json` | 可做 taxonomy mapping 候选，但 F16 不是原生 node code |

### 3.2 B 层：教学解释 / 变式 / 误区素材

| 来源 | 路径 | 合理用途 |
| --- | --- | --- |
| 防水讲义 JSON | `/docs/原始数据/2026_副本/讲义/2025.6.21佑森教育闫力齐授课一建建筑实务《防水&节能&装修工程》专用讲义，版权所有，侵权必究_v8/` | 考情、口诀、误区、干扰项解释、讲解素材 |
| 真题 JSON analysis / key_parameters / structured_rules | `/docs/原始数据/2026_副本/题库/*/FINAL_CLEANED_EXAM_*.json` | 题目绑定、答案 key、候选采分点、变式槽位 |
| ZL500 / 千题斩 | `/docs/原始数据/2026_副本/题库/864考证宝典ZL/FINAL_CLEANED_ZL500.json`、`/docs/原始数据/2026_副本/题库/章节千题斩SMR/FINAL_CLEANED_QIANTIZAN.json` | MCQ 轻练、same-node 复测、干扰项候选 |
| Graphify cards | `/docs/原始数据/PDF/建筑实务11.20_副本/graphify-out-full-2026-textbook/cards-from-json-all/` | 人读索引和线索，不可直接当原始 source |

### 3.3 C 层：候选 / 待 OCR / 人工校验

| 来源 | 风险 |
| --- | --- |
| `/docs/原始数据/PDF/行业标准文件/14、GB 55030—2022建筑与市政工程防水通用规范.pdf` | 40 页，`pdftotext` 主要抽到水印/乱码，关键词无命中；必须 targeted OCR |
| `/docs/原始数据/PDF/行业标准文件/19、GB50210-2018建筑装饰装修工程质量验收标准.pdf` | 当前 image-heavy，不可直接做室内/外墙防水 registered source_ref |
| `/docs/原始数据/PDF/真题/2021年一级建造师《建筑实务》考试真题及答案解析.pdf` | 扫描型，27 页约 99 字符 |
| `/docs/原始数据/PDF/真题/2022年一级建造师《建筑实务》补考真题及答案解析.pdf` | 扫描型，文本层几乎不可用；另有 0 page 风险报告 |
| 历史副本 PDF | `/PDF/一建建筑实务（智能体资料）_副本`、`/PDF/建筑实务11.20_副本` 存在重复、版本混杂 |

### 3.4 必须 hard exclude

这些不能进入母题引擎编译：

```text
/docs/原始数据/2026_副本/.git/
/docs/原始数据/PDF/建筑实务11.20_副本/graphify-out*/
/docs/原始数据/2026_副本/题库/docx_render_check*/
/docs/原始数据/2026_副本/scripts/
/docs/原始数据/2026_副本/_*.html.old_axis
所有 .DS_Store / .gitignore / HTML / JS / ICO / SVG / GraphML / Canvas / Python 脚本
```

`docx_render_check` 和 `docx_render_check_v2` 合计 611 张 PNG，只是渲染检查截图。没有 chunk/question/image manifest 前，不能作为题图 authority。

## 4. 2026 教材 JSON 审计

### 4.1 结构

第一次清洗是数组，无顶层 `meta`：

| 文件 | blocks |
| --- | ---: |
| `FINAL_CLEANED_BOOK2026-9-166.json` | 308 |
| `FINAL_CLEANED_BOOK2026-167-221.json` | 81 |
| `FINAL_CLEANED_BOOK2026-222-382.json` | 261 |

第二次加强包括：

| 类型 | 形态 | 用途 |
| --- | --- | --- |
| `FINAL_CLEANED_BOOK2026-*v3_fixed.json` | `{meta, content_blocks}` 完整增强块 | 人工审计、增强信息候选 |
| `v3_production_core*` | `{meta, content_blocks}` 瘦核心 | 最适合做 source span |
| `v3_production_enrichment*` | chunk_id -> enrichment | 只做候选讲解/误区/题干素材 |
| `v3_production_index*` | topic/node/anchor map | 检索索引，不能替代 taxonomy authority |

可作为 source span authority：

```text
content_markdown
source_meta.page_num
source_meta.original_anchor
source_meta.file_path / source_name / output_dir
chunk_id
original_chunk_id
taxonomy.node_code / path / topic
```

只能 candidate：

```text
knowledge_cards
assessment
synthetic_queries
suggested_tool_call
related_knowledge
process_stage
knowledge_enhancement
raw_llm_output
content_type_auto / confidence / enriched
visual_data.description / ocr_correction_note
enrichment 包
index 包
```

### 4.2 F16 防水关键 chunk

主教材施工源优先使用：

```text
/docs/原始数据/2026_副本/2026教材/第二次加强/v3_production_core9-166.json
/docs/原始数据/2026_副本/2026教材/第二次加强/FINAL_CLEANED_BOOK2026-9-166v3_fixed.json
```

| 主题 | chunk_id | 页 | 用途 |
| --- | --- | ---: | --- |
| 屋面防水等级/做法 | `1A413030_122_0230` | 122 | 防水等级、设防做法 |
| 屋面构造层次 | `1A413030_123_0231` | 123 | 屋面防水构造 |
| 屋面卷材施工 | `1A413030_123_0234` | 123 | 先细部后大面、搭接、铺贴方向 |
| 屋面涂膜施工 | `1A413030_124_0235` | 124 | 涂膜工艺 |
| 地下防水做法 | `1A413030_130_0247` | 130 | 明挖法地下工程防水 |
| 结构接缝设防 | `1A413030_130_0248` | 130 | 接缝防水设防 |
| 防水混凝土 | `1A413030_130_0249` | 130 | 防水混凝土要求 |
| 施工缝/止水 | `1A413030_131_0250` | 131 | 止水带/止水条/注浆管 |
| 水泥砂浆防水层 | `1A413030_131_0251` | 131 | 砂浆防水 |
| 地下卷材防水层 | `1A413030_131_0252`, `1A413030_132_0253` | 131-132 | 地下卷材 |
| 地下/涂膜防水 | `1A413030_133_0254` | 133 | 涂膜/地下 |
| 室内楼地面防水 | `1A413030_133_0255` | 133 | 室内防水 |
| 室内构造/施工 | `1A413030_133_0256`, `1A413030_134_0257` | 133-134 | 管根、地漏、翻起高度 |
| 外墙防水 | `1A413030_134_0258`, `1A413030_134_0259` | 134 | 外墙防水设计/施工 |

验收/通病交叉证据：

| 文件 | chunk_id | 用途 |
| --- | --- | --- |
| `167-221v3_fixed` | `1A422000_040_0064` | 屋面工程质量验收、雨后/淋水/蓄水 |
| `167-221v3_fixed` | `1A422000_041_0065` | 卷材/涂膜防水层施工规范 |
| `167-221v3_fixed` | `1A422000_042_0066` | 细部构造、防渗漏节点 |
| `222-382_fixed` | `1A434000_068_0103`, `1A434000_068_0104` | 防水材料进场验收、屋面过程检查 |
| `222-382_fixed` | `1A434000_075_0117` | 防水混凝土裂缝/渗漏通病 |
| `222-382_fixed` | `1A434000_076_0118`, `1A434000_076_0119`, `1A434000_077_0120` | 屋面卷材流淌、起鼓、女儿墙漏水 |
| `222-382_fixed` | `1A434000_081_0130`, `1A434020_085_0138`, `1A434020_085_0139` | 地下、卫生间、外墙防水验收划分 |

### 4.3 F16 taxonomy mapping

`FINAL_CLEANED_TAXONOMY2026.json` 未发现 `F16` 字面编码。F16 是产品/母题资产层编号，不是 taxonomy 原生 node code。

F16 `taxonomy_ref.node_codes` 候选：

```text
1A413050
1A413051-R03
1A413051-R04
1A413050-R07
1A413050-R13..R17
1A413050-R20..R25
1A413050-R36..R40
1A412010-B053 / B148 / B151
1A434000-B004 / B016 / B037 / B049 / B067 / B068
1A434033
```

必须另建 F16 mapping 表，不能把 `case_family_id=F16` 写进 taxonomy 当作新权威。

## 5. PDF/OCR 审计

PDF 总量 95 份。显式分类目录只有 31 份，历史/副本目录还有 64 份，存在重复和版本混杂。

| PDF 类别 | 文件数 | 判断 |
| --- | ---: | --- |
| 教材 | 1 | 2026 教材 PDF 可定位章节，但 OCR 错字明显 |
| 行业标准 | 21 | 少数可直接检索；GB 50207 最可用 |
| 真题 | 2 | 2021/2022 扫描型，不可直接做机器 registered source_ref |
| 讲义 | 7 | 显式讲义目录没有防水讲义；防水讲义在历史副本 |

抽样结果：

| 文件 | 文本层情况 | 处理建议 |
| --- | --- | --- |
| `GB 50207-2012屋面工程质量验收规范（清晰版）.pdf` | 130 页，约 113,669 字符，能稳定抽防水/淋水/蓄水/验收资料 | A 层优先，页码级 source |
| `GB 55030—2022建筑与市政工程防水通用规范.pdf` | 40 页，约 5,788 字符，关键词无命中，主要是水印/碎片 | targeted OCR + 人工抽样后再用 |
| `2026一建《建筑》电子版教材.pdf` | 382 页，约 401,320 字符，但错字多 | B/A- 辅助；与 JSON chunk 互证 |
| `2021真题.pdf` | 27 页，约 99 字符 | OCR 后再用 |
| `2022补考真题.pdf` | 23 页，约 23 字符 | OCR 后再用 |
| 防水讲义 PDF | 38 页，约 38 字符 | 只作为扫描底稿；优先读讲义 JSON |

## 6. 真题 / 题库审计

题库目录：

```text
/docs/原始数据/2026_副本/题库
```

规模：

```text
636 files
219M
13 JSON
1 DOCX
1 MD
611 PNG
10 .DS_Store
```

年度真题 JSON 格式为 `meta/stats/chunks`：

| 年份 | chunks / exercises |
| --- | --- |
| 2015 | 35 / 52 |
| 2016 | 35 / 53 |
| 2017 | 34 / 35 |
| 2018 | 48 / 48 |
| 2019 | 48 / 52 |
| 2020 | 53 / 56 |
| 2021 | 46 / 59 |
| 2022 | 44 / 44 |
| 2023 | 38 / 61 |
| 2024 | 40 / 38 |
| 2025 | 43 / 57 |

注意：`stats.total_exercises` 与实际 `exercises` 在 2018、2024、2025 有漂移，编译应以实际解析为准。

可用字段：

```text
question_binding = chunk_id + source_meta + taxonomy + exercise index/type
answer_key = exercises[].question_data.correct_answer
analysis = question_data.analysis / option_reasoning
variant slots = key_parameters / structured_rules
```

不可越权：

```text
真题 JSON != official rubric
analysis != published grading artifact
模拟学生答案 != real learner truth
图示题文本 != image evidence
```

### 6.1 F16 命中真题

| 年份 | 文件 / chunk | 用途 |
| --- | --- | --- |
| 2015 | `FINAL_CLEANED_EXAM_V2015.json` / `EXAM_XW2015_CASE_2` | 女儿墙节点找错，强 F16 深题候选，但依赖图2 |
| 2018 | `FINAL_CLEANED_EXAM_V2018.json` / `EXAM_1A413020_P0006_02` | 地下室外墙卷材、迎水面、双层卷材不得垂直，适合 MCQ/鉴别题 |
| 2019 | `FINAL_CLEANED_EXAM_V2019.json` / `EXAM_1A434000_P0013_01` | 屋面卷材铺贴方法、顺序、方向，适合程序型子能力 |
| 2022 | `FINAL_CLEANED_EXAM_V2022.json` | 防水砂浆、防水混凝土、卷材材料客观题，适合参数化轻练 |
| 2023 | `FINAL_CLEANED_EXAM_V2023.json` / `EXAM_1A433000_P0011_01` | 后浇带防水构造命名，依赖图1-7 |
| 2023 | `FINAL_CLEANED_EXAM_V2023.json` / `EXAM_1A434000_P0015_01` | 屋面卷材流淌、钉钉子法，可做 shadow grading |
| 2025 | `FINAL_CLEANED_EXAM_V2025.json` / `EXAM_1A413000_P0012_02` | 屋面卷材流淌分类与治理，适合复测变体 |
| 2025 | `FINAL_CLEANED_EXAM_V2025.json` / 第13题 | 地下室防水卷材外防内贴法，适合轻练/复测 |

### 6.2 题库优先级

1. 2017 屋面卷材起鼓割补法：既有 F16 扫描显示 Q18 P10/P11 已有 published scoring point，可最快形成 semi-write 闭环。
2. 2015 `EXAM_XW2015_CASE_2` 女儿墙节点找错：经典深题，但先补图2绑定。
3. 2023 `EXAM_1A434000_P0015_01` 屋面卷材流淌：有近三年模拟学生答案，可做 shadow grading。
4. 2025 `EXAM_1A413000_P0012_02` 卷材流淌分类与治理：适合复测变体。
5. 2019 `EXAM_1A434000_P0013_01`：无图依赖，适合程序型 F16 子能力。
6. 2018 `EXAM_1A413020_P0006_02` + ZL/千题斩地下室外墙卷材题：做 MCQ 轻练、same-node retest。
7. 2022 防水砂浆/防水混凝土/卷材材料客观题：补参数化轻练池。
8. 2024 暂不进主编译，只作为安全/施工条件补充题。

## 7. 讲义审计

讲义目录：

```text
/docs/原始数据/2026_副本/讲义
```

规模：

```text
8 个总 JSON
327 个 page_*.json
288 个去重源页
540 个教学 chunks
```

讲义只进 B 层：

```text
allowed:
  teaching explanation
  misconception wording
  mnemonic
  exam pattern
  distractor explanation
  weak answer examples

forbidden:
  official answer authority
  official scoring
  source_ref claim when conflicting with textbook/spec/exam
  long copyrighted reproduction
```

### 7.1 6.21 防水讲义优先页

| 页 | 主题 | F16 用途 |
| --- | --- | --- |
| `page_13_13.json` | 防水混凝土施工缝与卷材起鼓治理 | 最贴 F16 Q18 P10/P11；用于起鼓治理、割补法、十字切开、抽气灌胶讲解 |
| `page_6_6-2.json` | 屋面防水铺贴方法 | 搭接、铺贴方向、节点/宽度误区 |
| `page_11_11.json` | 防水施工要点 | 搭接宽度、渗漏风险 |
| `page_7_7-2.json` | 涂膜胎体增强 | 搭接宽度不足的干扰项 |
| `page_5_5.json` | 屋面防水层次构造 | 结构层序 flowchart |
| `page_8_8-2.json` | 屋面防水验收 | 检验批/抽检陷阱 |
| `page_9_9-2.json` | 混凝土防水 | same-node 扩展，不伪装 same-point |
| `page_10_10.json` | 砂浆防水 | 有“沙浆”疑似 OCR/术语风险 |
| `page_12_12.json` | 室内防水构造 | 室内防水扩展 |
| `page_1_1.json` | 考情 | “为什么学防水”的动机说明 |

讲义风险：

```text
版权：source_meta 含“版权所有，侵权必究”
OCR/清洗：有 validation warnings、chunk 缺 content_markdown、术语错写
教师解释：knowledge_cards/exam_matrix/mnemonics 不等于规范
外部图片：visual_data.related_image_path 指向 repo 外路径
taxonomy 噪声：后续节能/装修页可能仍挂防水 node
```

## 8. F16 首包设计

F16 首包不应吞下整个防水章。首包建议聚焦：

```text
屋面卷材 / 屋面涂膜
地下室防水
施工缝 / 止水带
验收 / 淋水蓄水
质量通病：卷材流淌、起鼓、女儿墙漏水
```

室内防水、外墙防水、防水材料性能可作为 same-node 扩展，不作为第一轮 LearnerState 结论。

### 8.1 首包可用证据按主题

| 主题 | 可用证据 | 首包用途 |
| --- | --- | --- |
| 屋面卷材/涂膜 | `1A413030_122_0230`, `1A413030_123_0234`, `1A413030_125_0237`; GB 50207/GB 50345 防水节点; 2016/2023/2025 真题 | 屋面等级、铺贴顺序、搭接、细部节点、涂膜验收 |
| 地下室防水 | `1A413030_130_0247`; 2025 外防内贴真题 | 地下防水等级、P6/P8、外设防水层 |
| 施工缝/止水带 | `1A413030_130_0248`, `1A413030_131_0250`; 2023 图1-7 文本 | 止水条、止水带、止水钢板、注浆管 |
| 验收/淋水蓄水 | `1A422000_040_0064`, `1A434000_068_0103`, `1A434000_068_0104`; GB 50207 PDF | 完工验收、材料进场复验、隐蔽验收 |
| 质量通病 | `1A434000_075_0117`, `1A434000_076_0118`, `1A434000_076_0119`; 2023/2025 真题 | 渗漏、卷材流淌、起鼓、钉钉子法、切割法 |
| 材料性能 | `1A412010_064_0125`; 2025 真题; taxonomy `1A412010-B053` | SBS/APP、高分子卷材、卷材性能 |

### 8.2 今日优先编译 10 源

| 优先级 | 源 / 片段 | 用途 | 状态 |
| --- | --- | --- | --- |
| 1 | GB 55030 PDF targeted OCR 片段 | gap blocker / source_ref candidate | 待 OCR |
| 2 | GB 50207 PDF 屋面防水/验收页码级 span | source_ref candidate | 可启动 |
| 3 | `v3_production_core9-166.json` 的 `1A412010_064_0125` | 防水材料 | 可启动 |
| 4 | `1A413030_122_0230`, `123_0234`, `125_0237` | 屋面卷材/细部 | 可启动 |
| 5 | `1A413030_130_0247`, `130_0248`, `131_0250` | 地下/接缝/止水 | 可启动 |
| 6 | `1A413030_133_0255`..`134_0259` | 室内/外墙扩展 | 可作为 B/A- |
| 7 | `1A422000_040_0064`, `1A434000_068_0103/0104`, `076_0118/0119` | 验收/通病 | 可启动 |
| 8 | 2015/2016/2023/2025 真题 JSON 防水片段 | question binding | 图示题需 manifest |
| 9 | 防水讲义 `page_13_13`, `page_6_6-2`, `page_11_11` | teaching / misconception | B 层 |
| 10 | `FINAL_CLEANED_TAXONOMY2026.json` 防水节点 + F16 mapping 草表 | gap blocker | 待人工确认 |

### 8.3 最小可签发包

建议首包结构：

```text
runtime_supply/v_f16_source_audit_candidate_<date>/
  manifest.json
  source_registry.json
  excluded_paths_report.json
  f16_taxonomy_mapping_candidate.json
  f16_source_refs.jsonl
  f16_question_bindings.jsonl
  f16_teaching_material_refs.jsonl
  f16_gap_report.json
  validator_report.json
```

签发口径：

```text
allowed:
  release_candidate for QA / retention teaching context
  MCQ light practice
  semi-write exercise with existing published scoring point refs
  candidate misconception mapping

forbidden:
  official scoring default
  canonical learner truth write
  same_point LearnerState claim when only same_node retest exists
  figure-based grading before image manifest
  source_ref claim from講义 / enrichment / graphify cards
```

## 9. Registry 字段

每个进入编译的文件或 span 至少登记：

```text
registry_id
source_path
source_sha256
size_bytes
mime_type
extension
document_kind
source_lane
authority_tier
lifecycle_stage
include_policy
candidate_only
exclude_reason
year
subject
provider_or_publisher
exam_year
page_count
ocr_status
parent_source_id
derived_from_sha256
transform_stage
tool_or_script
generated_at
taxonomy_version
node_count_or_row_count
dedupe_group_id
duplicate_of
superseded_by
approval_status
```

Span 级字段：

```text
span_id
registry_id
chunk_id
original_chunk_id
json_pointer
page_num
original_anchor
normalized_text_sha256
span_hash
taxonomy_node_codes
authority_tier
source_quote_allowed
consumer_allowed
```

## 10. 单一权威边界

| 业务事实 | 唯一 authority | 本资料的角色 |
| --- | --- | --- |
| 教材/规范原文 | source registry + hash span | 提供 source_ref，不直接运行 |
| taxonomy | canonical taxonomy authority | `FINAL_CLEANED_TAXONOMY2026.json` 是候选/输入，F16 需 mapping |
| 评分 | published grading artifact + CaseGradingSkillKernel | 真题答案解析只能候选，不能替代 rubric |
| 错因码 | `ERROR_CODE_REGISTRY` | 讲义/题库只能映射，不新建错因码 |
| 学情 | `LearnerStateService` / learning evidence authority | 模拟学生答案不能写 learner truth |
| 运行消费 | `CompiledContextPack` / `/api/v1/ws` | source audit 只产 runtime supply candidate |

## 11. Stop Conditions

出现以下情况，F16 首包不得升级为可判分或默认运行：

```text
GB 55030 仍未 OCR / 未抽样通过
GB 50108 / GB 50208 独立原文仍缺失但却声称地下防水规范闭环
2015 图2 / 2023 图1-7 仍无 image manifest
真题解析被写成 official rubric
讲义参数覆盖教材/规范参数
F16 被写进 taxonomy 当作原生 node
Graphify cards / enrichment 字段被当 registered source_ref
same_node 复测被说成 same_point LearnerState 结论
candidate-only 字段进入 official scoring prompt
```

## 12. 最小下一步

1. 建立 `source_registry` allowlist，不允许引擎递归读取 `docs/原始数据`。
2. 先登记 GB 50207 PDF、2026 教材 core JSON、2015/2018/2019/2023/2025 真题 JSON、防水讲义 `page_13_13` 等 F16 首包源。
3. 对 GB 55030、GB 50210、2021/2022 真题 PDF、防水讲义 PDF 做 targeted OCR，只抽 F16 相关页。
4. 建 `f16_taxonomy_mapping_candidate.json`，把 F16 映射到真实 node codes，不改 canonical taxonomy。
5. 为 2015 图2、2023 图1-7 建 image manifest，否则图示题只保留 candidate。
6. 首包只做 teaching/diagnosis QA 和留存实验，不做 official scoring default。
