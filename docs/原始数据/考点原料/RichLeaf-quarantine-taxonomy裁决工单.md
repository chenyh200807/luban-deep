# RichLeaf Quarantine — Taxonomy 层裁决工单

> 产出日期: 2026-06-21  ·  裁决人: taxonomy 裁决专家(AI)  ·  状态: **工单待 owner / taxonomy owner 决策**
>
> **红线遵守**: 本工单 **不自动重链、不改 canonical taxonomy(taxonomy-frozen-v1)、不改任何生产文件**。仅产建议 + 证据。
> 所有"重链候选"均为**语料搜索命中**,≠确证;置信度逐条标注,不确定项标 `NEEDS_HUMAN`。

## 来源

- quarantine 清单: `artifacts/luban_grading_artifacts/rich_leaf_per_leaf_pollution_fix_candidate_v3_20260621/runtime_token_pack_v30_frozen_full.candidate.json` → `quarantine.quarantine_rows`
- 教材语料(650 chunk): `FINAL_CLEANED_BOOK2026-{9-166v3,167-221v3,222-382}_fixed.json`
- canonical taxonomy(冻结): `deeptutor/services/taxonomy/compiled/construction_2026_taxonomy.compiled.json`

---

## 0. 总体裁决摘要

| bucket | 数量 | 裁决分布 |
|---|---|---|
| **mislink** | 22 | 重链候选 **1**(实为跨chunk续源,非真误链) · 确认无源 needs_source **0** · **保持现链(co-located/fan-out)21** |
| **over_subdivided** | 107 | 合并到父 **89** · 补源 needs_source **4** · 需人工 NEEDS_HUMAN **14** |

> **诚实校正(重要)**: 任务背景把 mislink 描述为"A类误链——chunk 里根本没该 leaf 内容"。**逐条核验后,22 个 mislink 的 named chunk 全部真实包含(或起始于)该 leaf 的原文**。没有一个是"指向无关 chunk"的经典误链。真实失败模式是 **co-located / 非原子可切**: chunk 内容正确,但同一 chunk 含多个原子 leaf,per-leaf 切分器无法原子隔离该 leaf 的 span → fail-closed 到 needs_source。
> 这意味着 **mislink 22 几乎不需要重链**(重链会制造新污染);需要的是 **per-leaf 切分器支持"多 leaf 共享同一 chunk"** 或承认 co-located 合法。仅 `1A422000-B126 管井构造要求` 因标题跨 chunk(033→034)需 owner 决定是否补续源 chunk。

---

## 1. mislink 22 裁决

裁决标记:
- `CO_LOCATED_FANOUT` = 多个原子 leaf 合法共享同一 chunk(如八类土 / 劳动力结构特征 / 支撑类),named chunk 正确,**不重链**。
- `CO_LOCATED` = 该 leaf 原文确在 named chunk 内,只是非整 chunk,**不重链**。
- `CO_LOCATED_SPAN` = leaf 标题在 named chunk 起始但细则续到相邻 chunk,**可选补续源**。

| leaf_id | leaf_name | named chunk | 核验证据(原文在chunk) | 裁决 | 置信度 |
|---|---|---|---|---|---|
| 1A413000-B001 | 一类土（松软土） | 1A413000_075_0143 | 岩土分类八类，"一类土：松软土"在同一chunk | CO_LOCATED_FANOUT | high(原文逐字核验) |
| 1A413000-B002 | 二类土（普通土） | 1A413000_075_0143 | 八类土分类同chunk | CO_LOCATED_FANOUT | high(原文逐字核验) |
| 1A413000-B003 | 三类土（坚土） | 1A413000_075_0143 | 八类土分类同chunk | CO_LOCATED_FANOUT | high(原文逐字核验) |
| 1A413000-B004 | 四类土（砂砾坚土） | 1A413000_075_0143 | 八类土分类同chunk | CO_LOCATED_FANOUT | high(原文逐字核验) |
| 1A413000-B005 | 五类土（软石） | 1A413000_075_0143 | 八类土分类同chunk | CO_LOCATED_FANOUT | high(原文逐字核验) |
| 1A413000-B006 | 六类土（次坚石） | 1A413000_075_0143 | 八类土分类同chunk | CO_LOCATED_FANOUT | high(原文逐字核验) |
| 1A413000-B007 | 七类土（坚石） | 1A413000_075_0143 | 八类土分类同chunk | CO_LOCATED_FANOUT | high(原文逐字核验) |
| 1A413000-B008 | 八类土（特坚石） | 1A413000_075_0143 | 八类土分类同chunk | CO_LOCATED_FANOUT | high(原文逐字核验) |
| 1A413000-B026 | 施工期间变形监测对象 | 1A413000_072_0139 | "在施工期间应对以下对象进行变形监测"原文在chunk | CO_LOCATED | high(原文逐字核验) |
| 1A413000-B034 | 基坑开挖前水泥土搅拌桩桩身强度检验 | 1A413000_080_0151 | "基坑开挖前应检验水泥土搅拌桩的桩身强度"原文在chunk | CO_LOCATED | high(原文逐字核验) |
| 1A413000-B072 | 墙底注浆的混凝土强度条件 | 1A413000_078_0149 | "混凝土达到设计强度后方可进行墙底注浆"原文在chunk | CO_LOCATED | high(原文逐字核验) |
| 1A436000-B017 | 主体工程施工主要安全隐患 | 1A436000_113_0187 | "主体工程容易发生的事故类型"原文在chunk(11.3.3) | CO_LOCATED | high(原文逐字核验) |
| 1A438000-B035 | 劳动力结构特征：性别构成 | 1A438000_157_0255 | "女性工人少，男性工人多"原文在劳动力结构特征chunk | CO_LOCATED_FANOUT | high(原文逐字核验) |
| 1A438000-B041 | 劳动力结构特征：技术等级构成 | 1A438000_157_0255 | "技术工少，普通工多"原文在劳动力结构特征chunk | CO_LOCATED_FANOUT | high(原文逐字核验) |
| 1A438000-B097 | 劳动力结构特征：年龄构成 | 1A438000_157_0255 | "青年工人少，中老年工人多"原文在劳动力结构特征chunk | CO_LOCATED_FANOUT | high(原文逐字核验) |
| 1A421010-B012 | 建筑工程施工许可的相关管理规定 | 1A421000_003_0003 | "4.1.3 施工许可管理规定"原文在chunk | CO_LOCATED | high(原文逐字核验) |
| 1A422000-B053 | 屋面工程施工有关规定 | 1A422000_040_0064 | "5.4.1 屋面工程施工作有关规定"原文在chunk | CO_LOCATED | high(原文逐字核验) |
| 1A422000-B126 | 管井构造要求 | 1A422000_033_0055 | "(4) 管井的构造应符合下列要求"标题起始在033_0055,细则续到034_0056(跨chunk) | CO_LOCATED_SPAN; 备选续源chunk 1A422000_034_0056(管井滤管构造要求) | high(原文逐字核验) |
| 1A422000-B152 | 钢筋混凝土支撑要求 | 1A422000_033_0055 | "(9) 钢筋混凝土支撑应符合下列要求"原文在chunk | CO_LOCATED_FANOUT | high(原文逐字核验) |
| 1A422000-B153 | 钢结构支撑要求 | 1A422000_033_0055 | "(10) 钢结构支撑应符合下列要求"原文在chunk | CO_LOCATED_FANOUT | high(原文逐字核验) |
| 1A422000-B155 | 锚杆布置规定 | 1A422000_033_0055 | "(8) 锚杆布置应符合以下规定"原文在chunk | CO_LOCATED_FANOUT | high(原文逐字核验) |
| 1A434000-B018 | 屋面工程施工过程检查与检验 | 1A434000_068_0104 | "屋面工程施过程检查与检验"原文在chunk | CO_LOCATED | high(原文逐字核验) |

**mislink 结论**: 重链候选 = **1**(`1A422000-B126`,仅"可选补续源"而非纠错),确认无源 = **0**,其余 **21** 保持现链。**建议 owner 不做重链**,改为在 per-leaf 切分层接受 co-located/fan-out(根因在切分器原子假设,非 taxonomy 链路)。

---

## 2. over_subdivided 107 裁决

裁决依据(结构证据):
- **53/107** 的 leaf 父码(如 `1A411001`/`1A411002`)**根本不在 canonical taxonomy**(`nodes_by_code` 无此码)→ 孤儿合成节点。
- 父码命中 canonical 的,绝大多数落在 **level 1–3 抽象中间节点**(建筑工程技术/建筑设计/施工成本管理 等),教材**无对应原子小节**。
- 仅 **20/107** 的 named chunk 与 leaf 父码同 7 位前缀(其余跨节点漂移);仅 **32/107** leaf 名核心词在 named chunk 逐字出现。

裁决标记:
- `MERGE/DELETE` = 父码不在 canonical taxonomy 的孤儿合成节点 → 合并回真实父 leaf 或删除(owner 定父)。
- `MERGE_TO_PARENT` = 抽象类目标签(如"建筑设计经济效益要求"),教材无原子源 → 合并到父概念。
- `NEEDS_SOURCE` = leaf 名核心词在 named chunk 逐字出现 **且** 节点对齐,可能是独立考点但需补源/复核。
- `NEEDS_HUMAN` = 内容在跨节点 chunk 出现,合并 or 补源不确定,需人工。

| leaf_id | leaf_name | 父码 | 父码taxonomy层级 | named chunk | named chunk所属node | 名核心词在chunk | 裁决 | 置信度 |
|---|---|---|---|---|---|---|---|---|
| 1A411011-G01 | 建筑消能减震与隔震构造 | 1A411011 | level4:建筑物分类与构成 | 1A411011_013_0024 | 1A411011 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A410000-E01 | 结构设计——圈梁 | 1A410000 | level1:建筑工程技术 | 1A411011_033_0060 | 1A411011 | 是 | NEEDS_HUMAN (content present but in cross-node chunk) | low |
| 1A411001-E02 | 建筑设计——建筑物的类别 | 1A411001 | **不在taxonomy** | 1A411011_001_0001 | 1A411011 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A411001-E03 | 建筑设计——建筑高度 | 1A411001 | **不在taxonomy** | 1A411011_002_0003 | 1A411011 | 是 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A411002-E01 | 建筑构造设计要求 | 1A411002 | **不在taxonomy** | 1A411011_016_0029 | 1A411011 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A411002-E02 | 建筑设计——楼梯构造要求 | 1A411002 | **不在taxonomy** | 1A411011_017_0032 | 1A411011 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A411002-E03 | 建筑设计——设计类别 | 1A411002 | **不在taxonomy** | 1A411011_003_0007 | 1A411011 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A411003-E01 | 建筑设计——地面构造要求 | 1A411003 | **不在taxonomy** | 1A411011_016_0028 | 1A411011 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A411004-E01 | 建筑设计——室内物理环境 | 1A411004 | **不在taxonomy** | 1A411011_009_0017 | 1A411011 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A411004-E02 | 建筑设计——龙骨构造要求 | 1A411004 | **不在taxonomy** | 1A411011_021_0041 | 1A411011 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A411021-E01 | 建筑构造设计要求 | 1A411021 | **不在taxonomy** | 1A411011_019_0037 | 1A411011 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A411023-E01 | 建筑设计构造要求——墙体 | 1A411023 | **不在taxonomy** | 1A411011_017_0031 | 1A411011 | 是 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A412001-E01 | 结构构造——混凝土结构 | 1A412001 | **不在taxonomy** | 1A411011_026_0048 | 1A411011 | 是 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A412001-E02 | 结构设计——安全性 | 1A412001 | **不在taxonomy** | 1A411011_024_0045 | 1A411011 | 是 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A412001-E03 | 结构设计——建筑物的类别 | 1A412001 | **不在taxonomy** | 1A411011_027_0050 | 1A411011 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A412002-E01 | 结构作用——荷载 | 1A412002 | **不在taxonomy** | 1A411011_029_0053 | 1A411011 | 是 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A412002-E02 | 结构设计——荷载 | 1A412002 | **不在taxonomy** | 1A411011_029_0053 | 1A411011 | 是 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A412020-E01 | 钢结构设计构造——防腐 | 1A412020 | level3:装饰装修工程材料 | 1A411011_034_0061 | 1A411011 | 是 | NEEDS_HUMAN (content present but in cross-node chunk) | low |
| 1A412022-E01 | 结构设计作用(荷载) | 1A412022 | level4:木材和木制品的特性与应用 | 1A411011_029_0053 | 1A411011 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A412031-E01 | 结构构造设计要求 | 1A412031 | level4:建筑防水材料的特性与应用 | 1A411011_033_0060 | 1A411011 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A412032-E01 | 结构抗震设计构造要求 | 1A412032 | level4:建筑防火材料的特性与应用 | 1A411011_011_0021 | 1A411011 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A413001-E01 | 结构设计——结构三性 | 1A413001 | **不在taxonomy** | 1A411011_029_0052 | 1A411011 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A413002-E01 | 抗震措施——砌体结构 | 1A413002 | **不在taxonomy** | 1A411011_012_0022 | 1A411011 | 是 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A413003-E01 | 装配式装饰装修模块化设计 | 1A413003 | **不在taxonomy** | 1A411011_037_0065 | 1A411011 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A413012-E01 | 结构构造——变形缝 | 1A413012 | level4:施工测量的方法和要求 | 1A411011_023_0044 | 1A411011 | 是 | NEEDS_HUMAN (content present but in cross-node chunk) | low |
| 1A414010-E05 | 装配式混凝土结构——运输 | 1A414010 | **不在taxonomy** | 1A411011_035_0062 | 1A411011 | 是 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A414020-E03 | 结构构造设计要求——混凝土结构 | 1A414020 | **不在taxonomy** | 1A411011_031_0055 | 1A411011 | 是 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A436010-E01 | 抗震措施——消能减震 | 1A436010 | level3:施工安全生产管理计划 | 1A411011_013_0024 | 1A411011 | 是 | NEEDS_HUMAN (content present but in cross-node chunk) | low |
| 1A411010-R07 | 建筑设计经济效益要求 | 1A411010 | level3:建筑设计 | 1A411011_004_0009 | 1A411011 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A411010-R21 | 建筑设计程序 | 1A411010 | level3:建筑设计 | 1A411011_003_0007 | 1A411011 | 是 | NEEDS_SOURCE candidate (content present + node aligned) | medium |
| 1A411010-R36 | 砌体结构房屋 | 1A411010 | level3:建筑设计 | 1A411011_012_0022 | 1A411011 | 是 | NEEDS_SOURCE candidate (content present + node aligned) | medium |
| 1A411010-R37 | 总体规划符合性要求 | 1A411010 | level3:建筑设计 | 1A411011_004_0009 | 1A411011 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A411010-R44 | 技术措施合理性要求 | 1A411010 | level3:建筑设计 | 1A411011_004_0009 | 1A411011 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A411020-R01 | 地面构造 | 1A411020 | level3:建筑构造设计要求 | 1A411011_016_0028 | 1A411011 | 是 | NEEDS_HUMAN (content present but in cross-node chunk) | low |
| 1A411020-R07 | 散水（明沟） | 1A411020 | level3:建筑构造设计要求 | 1A411011_017_0031 | 1A411011 | 是 | NEEDS_HUMAN (content present but in cross-node chunk) | low |
| 1A411020-R25 | 吊顶的装修构造及施工要求 | 1A411020 | level3:建筑构造设计要求 | 1A411011_021_0041 | 1A411011 | 是 | NEEDS_HUMAN (content present but in cross-node chunk) | low |
| 1A411030-R14 | 建筑美观要求 | 1A411030 | level3:建筑结构体系和设计作用（荷载） | 1A411011_025_0047 | 1A411011 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A411040-R11 | 钢结构构造 | 1A411040 | level3:建筑结构设计构造要求 | 1A411011_034_0061 | 1A411011 | 是 | NEEDS_HUMAN (content present but in cross-node chunk) | low |
| 1A411000-E01 | 建筑设计与构造 | 1A411000 | level2:建筑设计与构造 | 1A411011_030_0054 | 1A411011 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A412010-G01 | 防火堵料分类与应用 | 1A412010 | level3:结构工程材料 | 1A412010_066_0130 | 1A412010 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A411003-E03 | 建筑防水——影响保温材料导热系数的因素 | 1A411003 | **不在taxonomy** | 1A412010_067_0131 | 1A412010 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A412030-E01 | 水泥——应用 | 1A412030 | level3:建筑功能材料 | 1A412010_043_0075 | 1A412010 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A414010-E01 | 功能材料——防水材料 | 1A414010 | **不在taxonomy** | 1A412010_064_0125 | 1A412010 | 是 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A414011-E01 | 水泥的性能和应用 | 1A414011 | **不在taxonomy** | 1A412010_043_0074 | 1A412010 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A414020-E01 | 功能材料——保温材料 | 1A414020 | **不在taxonomy** | 1A412010_067_0131 | 1A412010 | 是 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A414020-E02 | 建筑装饰装修材料 | 1A414020 | **不在taxonomy** | 1A412010_055_0110 | 1A412010 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A414023-E01 | 建筑玻璃的特性与应用 | 1A414023 | **不在taxonomy** | 1A412010_058_0114 | 1A412010 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A434001-E01 | 装修工程——涂饰 | 1A434001 | **不在taxonomy** | 1A412010_060_0118 | 1A412010 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A414012-E01 | 建筑钢材的性能和应用 | 1A414012 | **不在taxonomy** | 1A412000_040_0068 | 1A412000 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A432012-E01 | 建筑材料分类和分级 | 1A432012 | level4:施工总承包投标流程与要求 | LEC_1A413060_P0035_001 |  | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A413010-E01 | 工程测量技术 | 1A413010 | level3:施工测量 | 1A413000_069_0135 | 1A413000 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A413032-R03 | 桩基检测技术 | 1A413032 | level4:桩基础施工 | 1A413030_092_0173 | 1A413030 | 是 | NEEDS_SOURCE candidate (content present + node aligned) | medium |
| 1A413030-G01 | 砌体墙临时施工洞口留置规定 | 1A413030 | level3:地基与基础工程施工 | 1A413030_106_0208 | 1A413030 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A411001-E01 | 建筑物的类别 | 1A411001 | **不在taxonomy** | 1A413030_122_0230 | 1A413030 | 是 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A411003-E02 | 建筑设计——设计类别 | 1A411003 | **不在taxonomy** | 1A413030_127_0240 | 1A413030 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A414000-E01 | 装饰装修——幕墙工程 | 1A414000 | **不在taxonomy** | 1A413030_146_0283 | 1A413030 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A414010-E02 | 室内防水——防水砂浆施工 | 1A414010 | **不在taxonomy** | 1A413030_131_0251 | 1A413030 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A414010-E06 | 钢筋工程 | 1A414010 | **不在taxonomy** | 1A413030_100_0190 | 1A413030 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A414020-E04 | 装修工程——幕墙安装 | 1A414020 | **不在taxonomy** | 1A413030_147_0284 | 1A413030 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A415010-E01 | 防水工程——地下防水 | 1A415010 | **不在taxonomy** | 1A413030_131_0251 | 1A413030 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A415030-E01 | 地基与基础工程施工 | 1A415030 | **不在taxonomy** | 1A413030_088_0163 | 1A413030 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A415032-E01 | 桩基础施工 | 1A415032 | **不在taxonomy** | 1A413030_092_0173 | 1A413030 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A415033-E01 | 混凝土基础施工 | 1A415033 | **不在taxonomy** | 1A413030_096_0181 | 1A413030 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A415041-E01 | 混凝土结构工程施工 | 1A415041 | **不在taxonomy** | 1A413030_103_0196 | 1A413030 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A415044-E01 | 装配式混凝土结构工程施工 | 1A415044 | **不在taxonomy** | 1A413030_116_0224 | 1A413030 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A415045-E01 | 钢-混凝土组合结构工程施工 | 1A415045 | **不在taxonomy** | 1A413030_119_0227 | 1A413030 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A415065-E01 | 涂饰、裱糊等工程施工 | 1A415065 | **不在taxonomy** | 1A413030_142_0277 | 1A413030 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A434010-E01 | 地基处理技术 | 1A434010 | level3:项目质量计划管理 | 1A413030_088_0163 | 1A413030 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A413042-R01 | 临时施工洞口设置规定 | 1A413042 | level4:砌体结构工程施工 | 1A413030_106_0208 | 1A413030 | 是 | NEEDS_HUMAN (content present but in cross-node chunk) | low |
| 1A413040-R38 | 防止预制构件断裂滑脱的吊运要求 | 1A413040 | level3:主体结构工程施工 | 1A413030_105_0201 | 1A413030 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A413050-R24 | 水泥砂浆防水层施工 | 1A413050 | level3:屋面与防水工程施工 | 1A413030_131_0251 | 1A413030 | 是 | NEEDS_HUMAN (content present but in cross-node chunk) | low |
| 1A413000-G01 | 全站仪测量 | 1A413000 | level2:建筑工程施工技术 | 1A413000_070_0136 | 1A413000 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A413000-G02 | 地下连续墙施工 | 1A413000 | level2:建筑工程施工技术 | 1A413000_077_0148 | 1A413000 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A413000-G03 | 复合土钉墙构造与施工 | 1A413000 | level2:建筑工程施工技术 | 1A413000_078_0149 | 1A413000 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A415021-E01 | 岩土的分类和性能 | 1A415021 | **不在taxonomy** | 1A413000_075_0144 | 1A413000 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A415022-E01 | 基坑支护施工 | 1A415022 | **不在taxonomy** | 1A413000_079_0150 | 1A413000 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A415024-E01 | 土石方开挖施工 | 1A415024 | **不在taxonomy** | 1A413000_084_0157 | 1A413000 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A435000-G01 | 施工成本管理环节 | 1A435000 | level2:施工成本管理 | 1A435000_089_0147 | 1A435000 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A421000-E02 | 相关法规——安全管理 | 1A421000 | **不在taxonomy** | 1A436000_008_0011 | 1A436000 | 是 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A431022-E01 | 危险性较大的分部分项工程安全管理 | 1A431022 | level4:项目管理绩效评价方法与内容 | 1A436000_008_0011 | 1A436000 | 是 | NEEDS_HUMAN (content present but in cross-node chunk) | low |
| 1A421064-E01 | 项目管理信息化 | 1A421064 | **不在taxonomy** | 1A437000_131_0212 | 1A437000 | 是 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A430000-E01 | 项目管理实务 | 1A430000 | **不在taxonomy** | 1A437000_145_0231 | 1A437000 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A431030-E01 | 危大工程专家论证——主要内容 | 1A431030 | level3:施工组织设计 | 1A437000_010_0013 | 1A437000 | 是 | NEEDS_HUMAN (content present but in cross-node chunk) | low |
| 1A422000-G01 | 检验批划分与屋面工程质量验收 | 1A422000 | level1:第4章 相关法规 | 1A422000_021_0029 | 1A422000 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A422000-G02 | 室内环境污染物验收 | 1A422000 | level1:第4章 相关法规 | 1A422000_022_0031 | 1A422000 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A414010-E04 | 装配式混凝土结构 | 1A414010 | **不在taxonomy** | 1A422000_039_0063 | 1A422000 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A421000-E01 | 相关法规 | 1A421000 | **不在taxonomy** | 1A422000_022_0031 | 1A422000 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A430000-E02 | 项目管理实务——绿色施工 | 1A430000 | **不在taxonomy** | 1A422000_055_0081 | 1A422000 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A431020-E01 | 基坑支护——地下连续墙 | 1A431020 | level3:施工项目管理机构 | 1A422000_032_0054 | 1A422000 | 是 | NEEDS_HUMAN (content present but in cross-node chunk) | low |
| 1A434012-E01 | 装修工程——室内环境质量检测 | 1A434012 | level4:项目质量计划应用 | 1A422000_025_0040 | 1A422000 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A434030-E01 | 装饰装修——抹灰工程 | 1A434030 | level3:工程质量通病防治 | 1A422000_042_0068 | 1A422000 | 是 | NEEDS_HUMAN (content present but in cross-node chunk) | low |
| 1A434040-E01 | 建筑内部装饰装修防火设计——应用场景 | 1A434040 | level3:工程质量验收管理 | 1A422000_045_0071 | 1A422000 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A431000-G01 | 项目管理绩效评价 | 1A431000 | level1:建筑工程项目管理实务 | 1A431000_005_0005 | 1A431000 | 是 | NEEDS_SOURCE candidate (content present + node aligned) | medium |
| 1A420000-E01 | 建筑工程项目施工管理 | 1A420000 | **不在taxonomy** | 1A431000_006_0006 | 1A431000 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |
| 1A431012-E01 | 资质管理——各级资质的承揽范围 | 1A431012 | level4:施工企业资质 | 1A431000_002_0002 | 1A431000 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A432010-G01 | 投标保证金与废标规定 | 1A432010 | level3:工程招标投标 | 1A432001_024_0028 | 1A432001 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A432010-G02 | 评标委员会组成要求 | 1A432010 | level3:工程招标投标 | 1A432001_024_0028 | 1A432001 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A432010-G03 | 投标工作要求与禁止性规定 | 1A432010 | level3:工程招标投标 | 1A432001_025_0030 | 1A432001 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A432020-G01 | 合同通用条款与专用条款 | 1A432020 | level3:工程合同管理 | 1A432002_028_0036 | 1A432002 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A432020-G02 | 甲供材料管理责任边界 | 1A432020 | level3:工程合同管理 | LEC_1A432020_P0026_001 |  | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A433000-G01 | 工期费用优化与赶工费计算 | 1A433000 | level2:施工进度管理 | 1A433000_057_0086 | 1A433000 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A433000-G02 | 实际进度前锋线比较法 | 1A433000 | level2:施工进度管理 | 1A433000_060_0090 | 1A433000 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A433000-G03 | 网络计划时间参数与关键线路 | 1A433000 | level2:施工进度管理 | 1A433000_056_0085 | 1A433000 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A433000-G04 | 网络图绘制规则（母线法） | 1A433000 | level2:施工进度管理 | LEC_1A433000_P0018_001 |  | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A434020-G01 | 钢筋进场复验检验批扩大规则 | 1A434020 | level3:项目施工质量检查与检验 | LEC_1A431070_P0033_001 |  | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A434020-G02 | 建筑节能工程验收与现场检验 | 1A434020 | level3:项目施工质量检查与检验 | 1A434020_086_0143 | 1A434020 | 否 | MERGE_TO_PARENT (abstract label, no atomic source) | medium |
| 1A415043-E01 | 钢结构工程施工 | 1A415043 | **不在taxonomy** | 1A434000_074_0116 | 1A434000 | 否 | MERGE/DELETE (orphan: parent not in canonical taxonomy) | high-structural |

**over_subdivided 结论**: 合并(MERGE/DELETE + MERGE_TO_PARENT) = **89** · 补源候选 NEEDS_SOURCE = **4** · 需人工 NEEDS_HUMAN = **14**。

> 注意: 这 107 个的根因是 RichLeaf 历史 taxonomy 过度细分(memory: taxonomy dedup/rebuild + 51 重复 code 战役),把抽象中间节点当原子叶展开。**合并/删除属于改 canonical taxonomy 的范畴 → 冻结需 owner 授权 + 变更窗口**,本工单只给建议不执行。

---

## 3. owner 决策清单(下一步谁做、做到什么算过)

1. **mislink(切分器层,不碰 taxonomy)**: 决定 per-leaf 切分器是否承认 co-located/fan-out(多 leaf 共享 1 chunk)。算过标准: 21 个 CO_LOCATED leaf 不再 fail-closed 到 needs_source,且不引入跨 leaf 串源。`1A422000-B126` 单独决定是否登记 `034_0056` 为续源。
2. **over_subdivided(taxonomy 层,需授权 + 变更窗口)**: taxonomy owner 审 89 个 MERGE 建议,逐个确认合并目标父 leaf(尤其 53 个孤儿父码),在冻结解禁窗口内执行。算过标准: 合并后无 orphan leaf 引用 + RichLeaf re-link 通过两闸。
3. **14 个 NEEDS_HUMAN + 4 个 NEEDS_SOURCE**: 人工逐条核对教材是否确有独立考点,再定合并 or 补源。

## 4. 红线/伪进展提示

- **不要拿本工单的"重链候选/合并建议"直接批量改库**——语料搜索命中 ≠ 教研确证;批量重链=制造新污染(memory: 异源裁判抓出同源放过的编造)。
- **改 canonical taxonomy 前先 grep schema_registry + 验 taxonomy sha**(memory: 命名 schema 前先 grep 注册表;canonical taxonomy 当天可被改写多次)。
- 不为这些缺口造第二套 authority/补丁映射表;合并直接落回 canonical taxonomy 单一权威。

---

# 5. 【根因复审 · 2026-06-21 第二轮】两个 bucket 的真根因均在切分器层,taxonomy 几乎不用动

> 复审人: taxonomy 根因专家(AI) · 方法: root-cause-debugging(先找 authority/writer-reader 断点,不追症状) · 对 §1/§2 的关键纠正 + 实证。
> **结论先行: mislink 22 与 over_subdivided 107 的真根因都不是 "taxonomy 过度细分",而是 per-leaf 切分器的 leaf-name↔heading 匹配层(`_title_matches_core`)。需 owner 授权改冻结 taxonomy 的数量 = 0~极少。**

## 5.1 实证方法(可复跑)

- canonical: `nodes_by_code`(2112 节点),key 形如 `1A411001-E02`(带后缀),**不是**裸 7 位 `1A411001`。
- 切分器: `scripts/luban_rich_leaf_subsection.py`,逐 chunk 跑 `slice_leaf_subsection` 看 OK/ABSTAIN + `_title_matches_core` tier。
- quarantine 源: `runtime_token_pack_v30_frozen_full.candidate.json` → 158 行(over_subdivided 107 / unsliceable 23 / mislink 22 / fail_closed_collision 6)。

## 5.2 对 §2 over_subdivided 的重大纠正:**107/107 leaf_id 本身就在 canonical,没有孤儿**

§2 把 53 个判成 "父码不在 canonical → 孤儿合成节点 → MERGE/DELETE",**这是用错 key 的假警报**:它查的是**裸 7 位父码**(`1A411001`),而 canonical 的真实节点 key 是**带后缀的 leaf 码本身**(`1A411001-E01/-E02/-E03`)。

实测(`nodes_by_code` 精确命中):
- **107/107 over_subdivided 的 leaf_id 全部是 canonical 已注册节点**(0 个 absent)。例:`1A411001-E02 建筑设计——建筑物的类别` 就是 canonical `L5` 节点原文。
- 裸父码 `1A411001..1A415065` 等 33 个确实不在 `nodes_by_code`——**因为 canonical 这一层根本不用裸父码当节点**,而非 "节点丢失"。

**含义**: 按 §2 去 MERGE/DELETE 这 89 个,等于**删除 canonical 真实节点**——是制造数据损坏,不是治理。`over_subdivided` bucket 名也具误导:这些 leaf 不是 "taxonomy 把抽象层错展成叶",而是**切分器在多-leaf chunk 内对这些 canonical 叶切不开 span** → fail-closed,与 mislink 同一根因。

> 仍需人工的真问题(缩小后): 极少数 leaf 名是抽象类目标签(如 `建筑设计经济效益要求`),教材确无对应原子小节——这类是**召回侧 "该 leaf 在这本教材无原子源"**,治本是承认 "无源即合法 quarantine / 挂父 anchor",**不是删 canonical 节点**。

## 5.3 对 §1 mislink 22 的根因分桶(任务 A 的核心交付)

逐条实证后,**22 个无一是 taxonomy 过度细分(a),也无一是 "列表切分能力不足"(b 的字面版)**——切分器**已经**支持列表/编号项(`_ENUM_LINE_RE` 产 level-8 伪标题,八类土的 `#### ① 一类土` 被干净解析成 8 个 ATX 标题)。真断点在**匹配层**,分两类:

| 子桶 | 数量 | 机制 | 证据 | 治本层 |
|---|---|---|---|---|
| **A · 标点/书写形式不匹配** | **8** | heading `一类土：松软土` vs leaf 核 `一类土（松软土）`,判别词 `一类土/松软土` 完全相同,只差分隔符(`：`vs`（）`)→ `_title_matches_core` 三档全 miss → ABSTAIN | 八类土 B001-B008,全部 8 个 | **切分器(可做)** |
| **B · 语义标签 ≠ 教材书写** | **14** | leaf 名是教研编辑标签(`钢筋混凝土支撑要求`/`劳动力结构特征：技术等级构成`/`施工期间变形监测对象`),教材 heading 是描述句(`钢筋混凝土支撑应符合下列要求`/`技术工少，普通工多`)或合法 CO_LOCATED span,无字面交集 | 支撑类/劳动力/监测对象等 | **不动(确定性切分器结构上够不着,合法 quarantine 或人工)** |

**A 桶实证可救**: 在 `_title_matches_core` 比较前加**一行标点归一化**(`（）()：:，,、`空白 全去掉再比),八类土 chunk `1A413000_075_0143` 立即 **8/8 sliced OK**,且每个 leaf 的 sibling-negative 检查全过(不串源)。这是 less-is-more 修法:**不新增 wrapper、不重写列表解析(已支持)、不碰 taxonomy**,只让 EXACT/FORWARD 比较对标点不敏感。

**B 桶不该硬救**: 它们是 `确定性静态闸边界` 的反面——确定性切分器靠 "leaf 核字面出现在 heading" 工作,而 B 桶的 leaf 名本就**不以教材原句书写**。给它补模糊/语义匹配 = 把语义问题降级成字符串问题(root-cause skill 红线),且 "错切=新污染"。B 桶应保持 fail-closed quarantine,由教研人工把 leaf 名 span 锚定(或承认 CO_LOCATED_FANOUT 合法),**不写进切分器**。

## 5.4 治本边界(任务 C)

| 层 | 范围 | 数量 | 是否需 owner 授权 | 值不值得 |
|---|---|---|---|---|
| **切分器(本 context 可做)** | `_title_matches_core` 加标点归一化 | 救 mislink-A **8**;对 over_subdivided **0 外溢**(全量实跑确认,见 §5.5 中置信) | **否**(不碰 taxonomy,单点改一个比较函数,fat-skill 单一 seam) | **值得**——一行归一化救 8 个真考点(八类土是高频考点),零新概念零新 authority,符合 less-is-more |
| **taxonomy(冻结,需授权)** | 删/合并 canonical 节点 | **0**——§2 的 89 MERGE/DELETE 经复审是假警报(107/107 leaf_id 在 canonical),**不应执行** | 不适用(无需改) | **不该做**——会删真实节点 |
| **召回/教研人工(非切分非 taxonomy)** | B 桶 14 + 抽象无源 leaf + `1A422000-B126` 跨 chunk 续源 | ~14-18 | 否(人工裁决,不改冻结结构) | 按价值挑高频考点人工锚 span,低频留 quarantine |

## 5.5 诚实置信度 + 需 owner 授权清单

- **高置信(实证,可直接据此行动)**: ① over_subdivided 107/107 leaf_id 在 canonical(精确 key 命中,非搜索)→ §2 的 MERGE/DELETE **不要执行**。② mislink-A 8 个标点归一化即救(实跑 8/8 OK)。③ 切分器已支持列表/编号项(代码 + 实跑双证)。
- **中置信(已量化)**: 标点归一化对 over_subdivided **零外溢**(全量实跑: baseline 5/107 OK → 标点归一化后仍 5/107,+0)。原因: over_subdivided 107 的 `named chunk` 普遍挂在与 leaf 不同的 node(多落 `1A411011` 系)且该 chunk 内**根本没有**对应 leaf 标签的 heading——是 "本教材该 chunk 无此 leaf 原子源",不是标点差异。故 over_subdivided 的治本是**召回/教研侧的 "无源即合法 quarantine"**,既不是切分器标点修法、也不是删 canonical 节点。另 4/107 引用 `LEC_*` 讲义 chunk(无 `content_markdown`),属 lecture lane,需单独看讲义源。B 桶 14 的精确边界仍需人工。
- **需 owner / 教研人工裁决(不可由 AI 擅定)**:
  1. **taxonomy owner**: 确认复审结论——撤销 §2 的 89 条 "删/合并 canonical 节点" 建议(它们是错的)。**冻结 taxonomy 本轮无需改任何节点**。
  2. **切分器 owner**: 批准 `_title_matches_core` 标点归一化的单点增强(本 context 可产 candidate,不直接落生产)。算过标准: mislink-A 8 个 sliced OK + 全量 re-run 不新增串源(sibling-negative 不回归)。
  3. **教研人工**: B 桶 14 + 抽象无源 leaf,逐条定 "锚 span / 承认 CO_LOCATED / 标本教材无源"。`1A422000-B126` 单独定是否登记 `034_0056` 续源。
- **本轮未擅自做**: 未改 canonical taxonomy、未改切分器生产文件、未重链。仅产复审结论 + 实证 + candidate 边界。
## 5.6 执行记录(切分器标点归一化已落 candidate, 未 promote 生产)

**已做(窄实现, 三方验证后执行)**:

- `scripts/luban_rich_leaf_subsection.py`: 加 `_normalize_separators` (只去分隔/结构标点 `：:（）()【】「」，,、；;／/` 空白 `·`), **只参与 `_title_matches_core` 的 EXACT(tier3)/FORWARD(tier2)**;tier1 safe-reverse(`全站仪⊂全站仪测量`)与 unsafe-substring-reverse 拒绝(`窗⊄天窗`)逻辑**一字不动**。无分词/无编辑距离/无同义词/无新依赖。
- `tests/scripts/test_luban_rich_leaf_subsection.py`: +3 测试(八类土标点变体 8/8 切对且不串源;近似项不误切;归一化不放宽 unsafe reverse)。`test_luban_rich_leaf_subsection.py`+`test_luban_rich_leaf_frozen_full_compile.py` 共 **33 passed**。
- `verify_pack.py`: 加可选 `--semantic-audit`(只读报告, 列每个被引用 point_id 的 leaf/quote/statement 供人工核名实);**不改 pass/fail 判定**(补 Codex 指出的 "只验 point_id 存在不验语义" 边界)。

**全量重编译验证(candidate 写 `/tmp/luban_v4_validation/`, 未覆盖生产 v3/v3.0 bundle)** — baseline 用 norm=identity monkeypatch 模拟改前, candidate 用真归一化, 同一 build 函数对比:

| 指标 | baseline(改前) | candidate(改后) | delta |
|---|---|---|---|
| compiled_unit_count | 1454 | 1466 | **+12** |
| mislink | 22 | 14 | **−8** |
| over_subdivided | 107 | 107 | **+0(零外溢)** |
| 八类土 chunk `1A413000_075_0143` 入 quarantine | 9 | 0 | 全救 |
| 全 pack intra-chunk 同 ctx 碰撞(污染) | — | **0** | 仍 0 |
| baseline-clean → candidate-quarantined(回归) | — | **0** | 零回归 |

- 八类土 8 子(B001-B008)+ 父 B042 各切到**自己的 heading 段**, 9 个 compiled_context **指纹互异**(无共享内容=无名实不符)。
- 额外救 4 个(B042 父级 preamble、B013/B037 流水施工、B145 脚手架计算书`脚手架计算书：`尾冒号)均为真实分隔符变体, 经逐条核 span 头确认切到本主题, **非误切**;零回归实证支持。

**未做(标工单, less-is-more)**:

- **挖矿 fail-closed 前移门(专家 A 建议)**: mine/编译产出后按完整 scoring_points payload 分簇, ≥2 leaf 且名义判别词不在共享 quote → quarantine 告警。**本轮不实现**: ① 现有 `enforce_no_intra_chunk_pollution` 已在编译闸做 fail-closed 同指纹拦截;② 切分器 positive+negative 检查已在**源头**挡 distinct-payload 错切;③ 当前 candidate 实测污染 0、碰撞 0, 风险非现存。新增分簇判别词比对 = 对非现存风险的防御性过度工程, 违 less-is-more。列为工单, 待未来出现 fingerprint 漏掉的 distinct-payload 错切实例时再做。
