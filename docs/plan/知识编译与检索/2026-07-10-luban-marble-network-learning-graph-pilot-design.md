# 鲁班 Marble 式网络计划学习图试点设计

**日期**：2026-07-10  
**状态**：Exploratory source-only trial authorized / runtime prohibited  
**类型**：Source-only pilot design  
**上位计划**：`2026-06-07-luban-knowledge-graph-remediation-plan.md`  
**数据入口**：`docs/原始数据/数据盘点/`  
**专家复核**：总指挥 / 知识架构 / hostile red team

## 0. 决策

有条件 GO：只做“一建建筑实务·网络计划”单主题、离线 candidate、source-only 的最小学习图试点。

明确 NO-GO：

- 不修全量 642 节点图；
- 不新建 Marble 服务、数据库、路由、registry 或第二套知识图 authority；
- 不接 `runtime_supply`、TutorBot 默认路径、LearnerState、GBrain 或 official scoring；
- 不把关键词共现、embedding 相似度、raw-hit 数或 LLM 常识直接签成 prerequisite；
- 不做 3D viewer，不把可视化当价值证明。

试点只回答一个问题：

> 一条经逐字来源支持、经教研签发的 prerequisite，能否比现有图更准确地选择前置补救知识，并保持判分与学情 authority 零漂移？

## 1. 现实锁定

### 1.1 已有资产

- Topic OKF 已覆盖网络计划，能路由到教材、讲义、真题、taxonomy 与 9 个候选采分点；它只负责导航，不负责签边。
- 当前 tracked graph supply 标记为 `release_candidate / published=false / official_score_allowed=false`。
- 当前 runtime resolver 已能把 `graph_neighbors` / `remediation` 放入 teaching pack。

### 1.2 当前不能继承为真相的部分

1. 当前 graph supply 只有 adjacency、`has_content`、`name_path`，逐边 reason/provenance 已在 compact 阶段丢失。
2. 当前网络计划存在确定性坏边：时间参数、关键线路、网络图绘制被错误指向水泥包装或剪力墙设计。
3. UUID 只是节点附属字段；node map、edge、adjacency、weak/mastery/remediation 仍以可能冲突的 code 路由。
4. `_load_graph()` 校验 hash 与 teaching tier，但不校验 `status/published` 或 master manifest pin。
5. `graph_neighbors/remediation` 虽进入 pack，现有 grounding formatter 仍只渲染教材、规范、讲义、真题；不能声称图已改变 LLM 教学输出。
6. Topic OKF 的 raw hits 包含 taxonomy backups、keywords、synthetic queries 等导航噪声；3187 hits 不是 3187 条独立证据。
7. ignored artifact 与 tracked runtime supply 是不同快照，现有 manifest 缺 source artifact hash、taxonomy hash、generator commit 与完整输入清单，lineage 不能机器闭合。
8. 当前 master manifest 对 graph shard 的 pin 与 shard 内部 hash 不一致，而 schema registry 又把该供应标作 `runtime_canonical`；这组元数据不能覆盖 `published=false` 的事实。

## 2. 三种方案

### A. 只复刻 Marble 可视化

优点：快、直观。  
缺点：不改善补救决策，不解决坏边、identity、发布与消费问题。  
裁决：拒绝。

### B. 在现有 canonical graph 内做 source-only candidate slice

优点：复用 taxonomy、OKF、采分点和既有 runtime contract；不制造第二 authority；最容易用 before/after 证明价值。  
缺点：必须先补逐边 provenance、identity 和发布门，不能直接复用当前 adjacency。  
裁决：推荐。

### C. 新建独立 Marble learning graph

优点：schema 看起来更干净。  
缺点：必然与 canonical graph、`construction_learning_graph.py`、LearnerState 和 runtime supply 竞争 authority。  
裁决：拒绝。

## 3. 单一 authority

### 3.1 One business fact

本试点维护的唯一业务事实是：

> 学习目标 B 是否必须建立在概念 A 已掌握的基础上，以及这项判断由什么逐字来源支持。

### 3.2 One authority

- 概念身份：现有 canonical taxonomy 的内容派生 UUID；code 仅作兼容标签。
- 静态前置关系：现有 canonical graph 将来的 signed prerequisite shard；试点只生成 candidate projection，不成为第二 authority。
- 学员会不会：LearnerState / Learning Brain 唯一负责，图谱不得写回。
- 判分对不对：signed rubric / answer authority 唯一负责，图谱不得进入 `required_terms`、score 或 release truth。

### 3.3 Competing authorities

本试点必须显式降级：

- 当前未签发 `graph_adjacency.json`；
- `construction_learning_graph.py` 中 `pending_review` 的 pack prerequisite；
- Topic OKF 关键词命中与 raw-hit 计数；
- lecture/LLM semantic mapping 生成的未复核关系；
- 前端卡片、viewer 或微课中自带的顺序关系。

### 3.4 Canonical path

```text
raw JSON / PDF / 教材 / 讲义 / 真题
  -> source ledger / Topic OKF 路由
  -> LLM candidate compiler（拆概念、提候选边、找反例）
  -> deterministic source gate（hash / pointer / endpoint / DAG / dedupe）
  -> 两名独立教研 reviewer 做语义签发
  -> immutable source-only pilot artifact
  -> dry consumer before/after
  -> 价值门通过后，另立 implementation/release 授权
```

原则：**LLM 维护候选知识组织；确定性门与教研签字保护 release authority。**

## 4. 试点范围

范围锁定为 8 个 topic-local 微目标；v0 不允许 `related`、`easy_confuse`、`applies_to` 等关系扩张。这些微目标是 existing canonical taxonomy 的 candidate projection，不另建运行时 ID namespace。

| 序号 | 微目标 | canonical refs | 可观察 mastery evidence |
|---|---|---|---|
| 01 | 读懂工作与逻辑关系 | parent `1A433000`; atomic identity pending | 能从文字关系识别紧前、紧后、平行工作，并区分实工作/虚工作 |
| 02 | 双代号网络图合法绘制 | parent `1A433000`; `G04` 仅兼容标签 | 给定逻辑关系，画出唯一开始/结束、编号不重复、无循环、虚工作使用正确的图 |
| 03 | 顺推 ES/EF | parent `1A433000`; `G03` 仅兼容标签 | 正确执行“前看取大”，算出所有工作的 ES/EF 与计算工期 |
| 04 | 逆推 LS/LF | parent `1A433000`; `G03` 仅兼容标签 | 从项目工期逆推 LS/LF，边界与紧后工作约束正确 |
| 05 | 区分并计算 TF/FF | parent `1A433000`; `G03` 仅兼容标签 | 能计算 TF/FF，并解释两者分别影响总工期还是紧后工作 |
| 06 | 识别关键工作与全部关键线路 | parent `1A433000`; `G03` 仅兼容标签 | 能处理多关键线路，不把“最长单项工作”误当关键线路 |
| 07 | 判断进度偏差与工期索赔影响 | `1A433000-G02`, `1A432000-B001` | 能用“偏差 vs FF/TF、是否位于关键线路”判断紧后、总工期与索赔影响 |
| 08 | 工期/费用优化 | `1A433000-B010` | 只压缩关键工作；多关键线路时按最低增费组合压缩并重新计算 |

hostile source audit 后的边裁决：

```text
active hard:   01 -> 02, 02 -> 03, 05 -> 07, 06 -> 08
active soft:   03 -> 04, 05 -> 06
pending hard:  04 -> 05（04 缺“以项目工期为终点边界、紧后取小”的完整逐字 span）
rejected:      06 -> 07（概念过宽）, 07 -> 08（不是必要依赖）
```

`hard` 仅用于“缺少前置能力时，目标题无法被正确求解或题意本身不成立”的关系。讲义展示顺序、替代表征、口诀、分类背景只能是 `soft`，不得锁题。A/B 只注入上述 4 hard + 2 soft，并携带 strength；pending/rejected 不进入 graph arm。

现有资产只作为取证入口：讲义网络计划页用于绘图与 ES/EF/LS/LF/TF/FF 规则，N01 确定性样例用于数值重算，2021/2023 真题可作小问级 assessment，2022/2024/2025 若现有 alignment 仅到 case level，就必须保留 `case_level_only`，不能冒充官方逐点 rubric。`1A433000-B029` 实际是流水节拍/步距/工期，不得再映射为 CPM 时间参数；`G02/G03/G04` 是待并回父级的 abstract label，不能单独作为 source authority。

范围门：超过 12 个节点或 15 条边立即停止并重新审设计，防止从试点膨胀成全图工程。

## 5. 最小数据形状

### 5.1 Candidate topic

```json
{
  "concept_uuid": "content-derived canonical uuid",
  "canonical_code": "compatibility label only",
  "name_path": "施工进度管理 > ...",
  "kind": "conceptual | procedural | representational | calculation | judgment",
  "description": "single teachable idea",
  "mastery_evidence": [
    {
      "evidence_id": "stable candidate-local id",
      "criterion": "observable learner performance",
      "assessment_refs": ["stable ref without copied answer or score"]
    }
  ],
  "source_refs": [
    {"ledger_id": "...", "path": "...", "pointer_or_page": "...", "sha256": "..."}
  ],
  "artifact_status": "candidate",
  "runtime_consumable": false,
  "official_score_allowed": false
}
```

### 5.2 Candidate prerequisite

方向约定固定为：`prerequisite_uuid` 是学习 `topic_uuid` 前必须掌握的概念。

```json
{
  "topic_uuid": "dependent concept",
  "prerequisite_uuid": "required prior concept",
  "strength": "hard | soft",
  "reason": "why this must come first",
  "support_type": "explicit_statement | derivable_sequence",
  "evidence_refs": ["source span with path/pointer/hash"],
  "counterexample": "when this edge should not apply",
  "review_status": "candidate | approved | rejected",
  "reviewers": [],
  "compiler_model": "audit metadata only",
  "runtime_consumable": false
}
```

真题只能证明“考过、如何应用、怎样观察掌握”，不能单独证明 prerequisite；前置关系必须有教材/讲义的显式教学顺序，或可逐字复核的计算依赖。

### 5.3 Bundle manifest

bundle 级必须记录：

```json
{
  "schema_version": "learning_graph_pilot.v0",
  "graph_id": "canonical-graph-network-planning-candidate",
  "status": "candidate",
  "source_inventory_hash": "...",
  "content_hash": "...",
  "published": false,
  "runtime_consumable": false,
  "official_score_allowed": false,
  "learner_truth_write_allowed": false,
  "rollback_pointer": null
}
```

### 5.4 Derived-only fields

下列字段只能由 artifact 重算，不得成为概念 authority：

- centrality / depth / unlock count / reverse adjacency；
- 真题频次、候选分值；
- learner priority；
- 推荐顺序；
- source hit 数、难度、可用题数；
- “识别 → 判断 → 做题 → 书写 → 迁移”的展示轴。

实际学员 mastery 状态也是派生消费结果，不属于本 artifact；这里的 `mastery_evidence` 只定义“观察到什么才算会”，不声称某个学员已经会。

## 6. 编译与验证职责

### LLM candidate compiler

- 从限定 source slice 拆分可教学原子；
- 提议 prerequisite、hard/soft、reason；
- 为每条边主动生成反例与拒绝理由；
- 提议 mastery evidence 与可绑定 assessment；
- 不得写 canonical、published 或 runtime supply。

### Deterministic gates

- 排除 backup taxonomy、keywords、synthetic queries、generated assessment 等非原始证据字段；
- 验证 ledger ID、repo path、JSON Pointer/page、sha256；
- 验证 concept UUID、端点存在、无自环、无重复、无互逆、DAG；
- 对 N01 等数值样例用独立 CPM 实现重算 ES/EF/LS/LF/TF/FF、关键线路与工期，并逐字段等于 candidate；
- 输入顺序打乱后输出 byte-identical；
- 校验所有 runtime/write/score guard 均为 false；
- 将当前已知四条网络计划坏边写成真实 artifact regression fixtures。

### Human semantic gate

- 每条边必须由两名独立 reviewer 裁决；
- 方向分歧未解决时只能 rejected/pending；
- “相关但非前置”一律拒签；
- reviewer 只能 down-rank/reject，不得凭常识补 source。

## 7. 效果实验

### 7.1 Source-only dry consumer

先冻结 20 个网络计划补救样本，至少覆盖：

- 网络图绘制与虚工作；
- 时间参数、总时差、自由时差；
- 单条/多条关键线路；
- 非关键工作延误；
- 工期调整与工期索赔。

对照：

- Baseline：现有四源上下文，不读取 pilot prerequisite；
- Graph candidate：同一四源上下文，加 approved source-only prerequisite projection。

使用同一离线评估模型、同一 prompt、同一 source pack 做成对测试；唯一变量是是否加入 approved prerequisite projection。结果由不知道组别的教研 reviewer 盲评。这一步不调用生产 TutorBot、不写 learner truth。

### 7.2 Pass criteria

1. 节点/边 source refs 可解析率 100%，broken refs=0，LLM-only refs=0。
2. active hard/soft 边均经两名 reviewer；pending/rejected edge 进入 graph arm=0；误把 related 签成 hard prerequisite=0。
3. dangling/self-loop/duplicate/mutual/cycle 均为 0。
4. concept UUID 与输出 hash 对输入顺序幂等。
5. 正确补救选择率 ≥80%，且比 baseline 提升 ≥15 个百分点；20 个样本中净增至少 3 个正确 case。
6. unsupported teaching claim=0。
7. 注入任意 graph hint 后，`release_truth / answer_key_authority / official_release_score / required_terms` 在固定样本上逐字不变。
8. 核心 02–08 每个微目标至少有一项确定性 probe 或稳定真题引用；case-level 引用冒充小问级=0。

### 7.3 后续真实消费门

只有 source-only dry consumer 全绿后，才允许另开 implementation plan 讨论：

- published/master-manifest gate；
- formatter 显式渲染 active remediation；
- captured LLM request 证明前置补救真实进入 prompt；
- 同一 SHA 的 before/after 输出；
- no-graph rollback。

这些不属于本设计稿授权范围。

## 8. Stop conditions

任一条件成立即停止扩图：

- source-only 审核后不足 4 条有教学意义的 prerequisite；
- 需要靠常识、LLM confidence、关键词共现或 raw hits 补齐边；
- 20 样本未提升 ≥15pp，或只改变 payload、不改变补救选择；
- 任一判分字段漂移、图谱写回 LearnerState、出现第二 graph authority；
- identity、lineage、manifest/hash/published 状态无法收敛；
- 试点需要新增 DB、route、registry 或新 ID namespace。

停止后降级为 source index / lesson outline / coverage analysis，不继续精修 prerequisite。

## 9. False progress

以下均不能称为试点成功：

- 3D 图或 viewer 可打开；
- 节点数、边数、raw-hit 数增加；
- DAG 无环；
- helper/unit tests 绿色；
- `graph_neighbors` 出现在 payload；
- loader 能读取 unpublished candidate；
- schema registry 标注 `runtime_canonical`；
- 生成了更多微课卡。

真正闭环必须是：

```text
逐字 source
  -> candidate edge
  -> deterministic + double review
  -> immutable artifact
  -> correct remediation choice lift
  -> zero authority drift
```

## 10. 计划中的实施文件（待用户批准本设计后）

设计通过后，下一阶段才允许编写 implementation plan，计划产物为：

- `docs/原始数据/数据盘点/2026-07-10-Marble式网络计划学习图试点.md`
- `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/manifest.json`
- `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/topics.jsonl`
- `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/dependencies.jsonl`
- `docs/原始数据/数据盘点/extractions/learning_graph_pilot_v0/evaluation.json`
- `docs/原始数据/数据盘点/scripts/build_learning_graph_pilot.py`
- `tests/scripts/test_build_learning_graph_pilot.py`

实施遵守 TDD：先写真实坏边与 contract RED 测试，确认因功能缺失而失败，再写最少 builder/validator 使其通过。

## 11. Owner 与裁决权

- Source/knowledge compiler owner：候选生成、source refs 与 reproducibility。
- 建筑实务教研 reviewer：prerequisite 语义与方向签发。
- Canonical graph owner：identity、manifest、版本和 rollback；未来唯一 release authority。
- Learning Brain owner：学员位置与 mastery authority，不接受图谱写入。
- Grading owner：判分隔离与零漂移 gate。
- 产品/评估 owner：20 样本 before/after 与价值继续门。

用户是是否从 source-only pilot 进入 runtime implementation 的最终授权者。
