# 鲁班动画包 Canonical Taxonomy 对齐注册表

- 日期: 2026-06-19
- 状态: `Proposed`
- 主线: 鲁班移动端提分闭环
- 上游计划: `2026-06-18-luban-animation-learning-system-master-plan.md`
- 决策对象: 60 个 motion learning pack 的 canonical taxonomy 候选绑定

## 0. 结论

动画包必须对齐 canonical taxonomy,但不能把 taxonomy code 当成动画包 ID。

正确分工:

| 字段 | 作用 | 学员端是否展示 |
|---|---|---|
| `pack_id` | 动画/练习资产稳定 ID,如 `J01`、`N01`、`F16` | 不直接展示 |
| `canonical_taxonomy_refs[]` | 知识权威锚点,用于盲点归因、题库召回、复测和覆盖率 | 不直接展示 |
| `student_title` | 学员可见考点名,由教研改写成自然语言 | 展示 |
| `priority_slot` | 生产优先级,如 P0-01 / P1-21 / P2-48 | 不展示 |

执行裁决:

1. 保留 `J01/N01/C01/F16` 等 pack_id,不改成 taxonomy code。
2. P0/P1 进入 source/storyboard 前必须有 `canonical_taxonomy_refs[]`。
3. P2 candidate 可以只绑定粗节点,但必须标 `needs_leaf_review`。
4. 学员端只能展示中文考点名和采分句,不得展示 `1A...` code。
5. 状态翻转到 production/signed 前,必须用当前 `taxonomy_index()` 重新校验 code 存在和语义匹配。

## 1. Taxonomy 快照

本注册表基于当前本地 compiled taxonomy 生成候选绑定:

| 项 | 值 |
|---|---|
| compiled file | `deeptutor/services/taxonomy/compiled/construction_2026_taxonomy.compiled.json` |
| source path | `/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/taxonomy/FINAL_CLEANED_TAXONOMY2026.json` |
| source sha256 | `26dbb542b31601d6b3255d53463d0007c0c7eaea5a24ad9c338b3742baa976c8` |
| total nodes | 2116 |
| leaf nodes | 1976 |
| unique codes | 2116 |

边界: 这是候选对齐快照,不是永久签发。taxonomy 曾发生日内改写,任何 pack 从 candidate 升级到 signed/production 前都必须重新跑 resolver 并记录当时 source hash。

## 2. 编译边界

LLM 做困难的知识组织工作: 从考点、真题 stem、讲义和已有动画包中提出候选 taxonomy 绑定。

确定性 gate 负责:

1. code 必须存在于 `taxonomy_index()`。
2. 学员端文案必须走 `student_taxonomy_label()` / `student_facing_label()` 或教研中文标题,不得 raw code fallback。
3. `canonical_taxonomy_refs[]` 只能做知识锚点,不得变成判分 authority。
4. 生产包必须同时有 `source_refs[]` 和 `authority.status`。
5. 发生 code 漂移时,保留 `pack_id`,更新 taxonomy refs 并记录 migration note。

## 3. Alignment Status

| 状态 | 含义 | 生产含义 |
|---|---|---|
| `direct` | 已找到直接命中的 taxonomy 节点 | 可进入 source/storyboard,仍需 source_ref |
| `composite` | 一个 pack 横跨多个 taxonomy 节点 | 允许做整合包,但 storyboard 要声明主/辅节点 |
| `coarse_review` | 只有粗章节或相邻节点,缺精确 leaf | 不得 production,先补 source/leaf review |
| `merged_child` | 子包默认并入父 pack | 不独立排产,除非 source_ref 证明独立高频 |
| `conditional_split` | 可拆,但需要后续证据 | P2 候选,不构成生产承诺 |

## 4. 60 Pack Taxonomy Alignment

| Slot | Pack ID | Student title | Canonical taxonomy refs | Status | Note |
|---:|---|---|---|---|---|
| 1 | J01 | 危大工程范围 + 专项方案 + 专家论证 | `1A431030-E01`; `1A436000-B029`; `1A436000-B158` | `direct` | 已有 J01 原型;主锚点用专家论证,范围/超过一定规模作辅锚 |
| 2 | S01 | 脚手架/高大模板支架验收 | `1A436032`; `1A436000-B005`; `1A413046-R03` | `composite` | 脚手架安全、模板支架检查、脚手架构造三类节点合并 |
| 3 | S02 | 起重吊装安全 | `1A436000-B006`; `1A436000-B153`; `1A436000-B155` | `direct` | 起重吊装检查、作业安全、安装拆卸范围 |
| 4 | C02 | 进度款/计量计价 | `1A432000-C17`; `1A432000-C19`; `1A432000-C24` | `direct` | 进度款支付与计算公式 |
| 5 | B02 | 基坑支护选型与降水/监测 | `1A413022`; `1A413034`; `1A413036`; `1A413000-B033` | `composite` | 支护、监测、降水、报警条件组合包 |
| 6 | Q01 | 混凝土养护与裂缝防治 | `1A413040-R28`; `1A413000-C10` | `direct` | 养护与温度测量,裂缝防治 source_ref 需补 |
| 7 | A01 | 检验批/分部分项验收程序 | `1A434020-B018`; `1A434020-B006`; `1A434020-B001` | `direct` | 检验批、分项、分部、主体结构验收 |
| 8 | N01 | 双代号网络计划关键线路/总时差 | `1A433000-B041`; `1A433000-G03` | `direct` | 已有 N01 原型;关键线路/时间参数主锚 |
| 9 | K01 | 索赔成立与工期/费用计算 | `1A432000-B001`; `1A432000-B002`; `1A432000-B015`; `1A432000-B057` | `composite` | 工期索赔、费用索赔、发包人原因、索赔计算 |
| 10 | Q03 | 质量通病: 蜂窝麻面/空鼓裂缝 | `1A434030`; `1A434032`; `1A434000-B037`; `1A434000-B011` | `coarse_review` | 通病节点存在,蜂窝麻面缺精确 leaf;不得直接 production |
| 11 | C04 | 模板拆除顺序与条件 | `1A413040-R25`; `1A413040-R26`; `1A413040-R27`; `1A436000-B114` | `direct` | 拆除要求、要点、顺序和安全控制 |
| 12 | Q02 | 大体积混凝土温控裂缝 | `1A413074`; `1A413033-R05`; `1A413033-R08`; `1A413033-R09` | `direct` | 大体积混凝土施工、测温与温控 |
| 13 | C01 | 施工缝留置与处理 | `1A413040-R20`; `1A413040-R29`; `1A434000-B037` | `direct` | 已有 C01 原型;施工缝/后浇带和接槎通病 |
| 14 | C05 | 钢筋连接选用 | `1A413040-R44`; `1A434000-B063` | `direct` | 钢筋连接与质量控制 |
| 15 | C06 | 砌体留槎与构造柱 | `1A413081`; `1A413083`; `1A413042-R03`; `1A413030-G01` | `coarse_review` | 留槎/构造柱缺精确 leaf;只能先锚砖砌体/填充墙/洞口留置 |
| 16 | C07 | 钢结构连接: 焊接/高强螺栓 | `1A413043`; `1A413084`; `1A413040-R33`; `1A413040-R64`; `1A434000-B082` | `direct` | 钢结构施工、构件连接、高强螺栓安装与主控 |
| 17 | S05 | 临时用电: 三级配电两级保护 | `1A431050`; `1A431051`; `1A431052`; `1A431010-C03` | `direct` | 临电组织设计、管理、安全技术 |
| 18 | S06 | 高处作业/临边洞口防护 | `1A436035`; `1A436000-B177`; `1A436000-B180` | `direct` | 高处作业基本要求和隐患 |
| 19 | S07 | 安全事故等级判定与上报 | `1A436000-B023`; `1A436000-B066`; `1A436040`; `1A436041` | `coarse_review` | 事故等级/分类可锚,上报程序需补 source_ref |
| 20 | N02 | 网络计划工期优化与赶工费用 | `1A433000-B042`; `1A433012`; `1A433000-B041` | `direct` | 网络计划优化及关键线路基础 |
| 21 | D11 | 抹灰工序与质量控制 | `1A434030-E01`; `1A422000-B012` | `direct` | 抹灰工程与交接处防裂 |
| 22 | D12 | 饰面砖/板施工质量与空鼓防治 | `1A413064`; `1A413130`; `1A434000-B054`; `1A434034` | `composite` | 饰面工程、饰面砖、装饰质量通病 |
| 23 | D13 | 幕墙防火/防雷/层间封堵构造 | `1A413134`; `1A413065-R10`; `1A413065-R11`; `1A413065-R12` | `direct` | 幕墙防火、防雷、构造要求 |
| 24 | D14 | 吊顶/门窗/地面装饰质量综合 | `1A413062`; `1A413063`; `1A413061-R10`; `1A434034` | `composite` | 综合包;细拆 D15/D16 前不得混成一个评分点 |
| 25 | G01 | 基坑开挖与降水方法选择 | `1A413037`; `1A413036`; `1A413000-B081`; `1A413000-B071` | `direct` | 土方开挖、降水技术、深基坑开挖 |
| 26 | G02 | 土方回填压实与检测 | `1A413039`; `1A413000-B020`; `1A436000-B043` | `direct` | 回填、填筑压实、安全措施 |
| 27 | G03 | 桩基施工与质量问题 | `1A413032`; `1A413067`; `1A413068`; `1A413069` | `direct` | 桩基础、预制桩、灌注桩、检测 |
| 28 | G04 | 地基验槽与地基处理 | `1A413048`; `1A413000-B041`; `1A413025` | `direct` | 天然地基验槽与基坑验槽 |
| 29 | F16 | 屋面防水起鼓割补 | `1A434000`; `1A434000-B016`; `1A413103` | `composite` | 已有 F16 样板;现有 JSON 粗锚 `1A434000`,需补割补 source_ref |
| 30 | F02 | 卷材防水施工顺序与搭接方向 | `1A413103`; `1A413051-R03`; `1A413112`; `1A422000-B021` | `direct` | 屋面/卷材防水层施工 |
| 31 | F03 | 防水构造层次: 屋面/地下 | `1A413100`; `1A413102`; `1A413050-R20`; `1A413050-R21`; `1A413112` | `composite` | 防水等级、基本要求、构造层次 |
| 32 | F04 | 防水细部节点: 阴阳角/管根/女儿墙 | `1A413050-R07`; `1A413050-R20`; `1A413050-R21`; `1A413050-R23` | `coarse_review` | 细部节点缺专门 leaf;需 source_ref 明确节点 |
| 33 | F05 | 渗漏治理诊断 | `1A434033`; `1A434000-B016`; `1A434000-B067` | `direct` | 屋面防水通病、防水施工缝渗漏 |
| 34 | X01 | 施工平面布置原则 | `1A431040`; `1A431041`; `1A431042` | `direct` | 平面布置图设计和管理 |
| 35 | X02 | 临设、道路、材料堆场布置 | `1A431040`; `1A437000-B011`; `1A437000-B026`; `1A438000-B060` | `composite` | 平面布置叠加仓库/堆场/材料进场 |
| 36 | X03 | 文明/绿色/环保施工措施 | `1A437020`; `1A437021`; `1A437023`; `1A437000-B071`; `1A437000-B087` | `composite` | 文明施工、绿色施工、环保要求合并 |
| 37 | R01 | 现场消防布置、动火、检查、验收流程 | `1A437030`; `1A437031`; `1A437032`; `1A437000-B060`; `1A437000-B061`; `1A422026` | `composite` | 施工现场消防 + 消防审查验收规定 |
| 38 | N03 | 流水施工参数与工期 | `1A433011`; `1A433000-B030`; `1A433000-B031`; `1A433000-B014` | `direct` | 流水参数、组织形式、计算 |
| 39 | E05 | 挣值法/偏差分析 | `1A435020-B010`; `1A435020-B011`; `1A435020-B017` | `direct` | 挣值法应用、计算、核心概念 |
| 40 | A02 | 隐蔽工程验收 + 材料进场复验/见证取样 | `1A434020-B018`; `1A422000-B061`; `1A422000-B150`; `1A438000-B060` | `composite` | 验收、见证取样、材料进场合并包 |
| 41 | E01 | 工程量清单计价 | `1A432000-B037`; `1A432000-B053` | `direct` | 清单计价方式 |
| 42 | E02 | 预付款、起扣点、进度款细分 | `1A432000-C19`; `1A432000-C20`; `1A432000-C17`; `1A432000-C24` | `direct` | 预付款、进度款、结算款计算 |
| 43 | E03 | 措施费、暂列金额、暂估价判断 | `1A432000-C08`; `1A432000-C35`; `1A435000` | `coarse_review` | 暂列/暂估未命中精确 leaf;需计价 source_ref |
| 44 | E04 | 竣工结算与价款调整 | `1A432000-C29`; `1A432000-C30`; `1A432000-C08`; `1A432000-C35` | `direct` | 竣工结算、价款确定与调整 |
| 45 | K03 | 工程变更与签证 | `1A432000-C14`; `1A432000-B056`; `1A432000-B058` | `coarse_review` | 工程变更有节点,签证需 source_ref 补证 |
| 46 | K05 | 工期顺延与费用补偿边界 | `1A432000-B001`; `1A432000-B002`; `1A432000-B015`; `1A432000-B057` | `composite` | 默认作为 K01/K06 的迁移包 |
| 47 | K06 | 合同责任事件归属矩阵 | `1A432000-B004`; `1A432000-B015`; `1A432000-B016`; `1A432000-C13` | `composite` | 责任事件矩阵,吸收 K02 |
| 48 | R02/R03 | 耐火等级、疏散距离、防火分区基础数值判断 | `1A411020-R16`; `1A411020-R15`; `1A411020-R22` | `coarse_review` | 疏散/防火构造有节点,耐火等级/防火分区缺精确 leaf |
| 49 | R04 | 防火封堵与幕墙层间防火 | `1A413134`; `1A413065-R11`; `1A413065-R12`; `1A412010-B152` | `composite` | 可与 D13 联动,封堵需补 source_ref |
| 50 | N04 | 时标网络计划与前锋线判断 | `1A433000-G02`; `1A433000-B041`; `1A433000-B042` | `composite` | 前锋线有节点,时标网络需 source_ref |
| 51 | G05 | 支护结构监测报警与处置 | `1A413034`; `1A413000-B033`; `1A413000-B036` | `direct` | 基坑监测、报警条件、测量监测 |
| 52 | K04 | 合同价款调整触发与计算边界 | `1A432000-C08`; `1A432000-C09`; `1A432000-C35` | `direct` | 默认从 E04/K05 条件拆分 |
| 53 | K02 | 不可抗力责任划分 | `1A432000-B004` | `merged_child` | 默认并入 K06 |
| 54 | R05 | 消防验收流程 | `1A422026`; `1A437032`; `1A437000-B061` | `conditional_split` | 默认并入 R01;独立需验收流程 source_ref |
| 55 | X05 | 季节性施工措施: 雨期/冬期/高温 | `1A413080`; `1A413000-C03`; `1A413000-C26`; `1A413000-C28`; `1A413000-C19` | `conditional_split` | 场景变体,默认不独立锁定 |
| 56 | F06 | 防水材料性能与进场复验 | `1A412031`; `1A412010-B053`; `1A412010-B148`; `1A412010-B149`; `1A422000-B061` | `merged_child` | 默认并入 A02,防水为场景 |
| 57 | D17 | 装饰材料进场复验与见证取样 | `1A422000-B061`; `1A422000-B150`; `1A422000-B157`; `1A434020-B022` | `merged_child` | 默认并入 A02 |
| 58 | X04 | 绿色施工措施 | `1A437013`; `1A437020`; `1A437021`; `1A437000-B087`; `1A437000-B091` | `merged_child` | 默认并入 X03 |
| 59 | D15 | 门窗安装、防渗漏质量控制细分候选 | `1A413061-R10`; `1A422000-B156`; `1A422000-B157`; `1A434000-B066` | `conditional_split` | 从 D14 拆分需 source_ref |
| 60 | D16 | 地面基层与面层质量细分候选 | `1A413063`; `1A413063-R02`; `1A413063-R03`; `1A434000-B011` | `conditional_split` | 从 D14 拆分需 source_ref |

## 5. 生产前硬门

P0/P1 pack 进入 storyboard 前必须补齐:

1. `canonical_taxonomy_refs[]`: 至少一个 code,且当前 `taxonomy_index()` 可解析。
2. `taxonomy_alignment_status`: 不得为空。
3. `primary_taxonomy_ref`: 主锚点只能有一个。
4. `supporting_taxonomy_refs[]`: 组合包的辅锚点。
5. `student_title`: 不含 raw code 的中文标题。
6. `source_refs[]`: 教材/真题/规范/教研依据,不得只靠 taxonomy 名称。

确定性检查入口:

```bash
python scripts/check_luban_animation_taxonomy_alignment.py
```

新增 pack manifest 时必须额外传入待检查文件:

```bash
python scripts/check_luban_animation_taxonomy_alignment.py --manifest artifacts/luban_case_family_assets/diagram_microlesson/<pack_id>.schema.json
```

禁止事项:

1. 不把 `pack_id` 改成 `1A...`。
2. 不把 `canonical_taxonomy_refs[]` 当判分点。
3. 不把 `coarse_review` pack 投产给学员默认入口。
4. 不把 P2 `merged_child` 当独立排产。
5. 不在学员 UI 暴露 taxonomy code。

## 6. 下一步

1. M1 12 个先补 `primary_taxonomy_ref` 和 `supporting_taxonomy_refs[]` 到 pack manifest。
2. 对 `coarse_review` 项开 source/leaf review,优先 Q03、C06、S07、F04、R02/R03、E03、K03。
3. 把 renderer schema 的 `taxonomy_ref` 收敛为 `primary_taxonomy_ref` + `supporting_taxonomy_refs[]`,旧字段只做兼容 alias。
4. 每次 pack 状态翻转时记录 taxonomy source sha 和 resolver 结果。
