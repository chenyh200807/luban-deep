# 鲁班知识图谱 系统性修复计划（专家面板综合）

**日期**: 2026-06-07
**状态**: 计划（待批准执行）
**输入**: 10 人专家面板（6 问题专家 + 数据地基/运行时集成/评估/对抗简化 4 架构视角），产物 `artifacts/luban_grading_artifacts/`（expert_panel）。
**对象**: canonical 知识图谱 v1（481 节点 / 1779 边）+ 其地基 canonical taxonomy。

---

## 0. 一句话结论与战略转向

复审证明：当前图谱是**能跑的 v1 脚手架，但未满足系统需求**——边有逻辑错（5 环 / 10 矛盾）、47% related 注水、零边 QA、地基（taxonomy 码）非全局唯一、且**被 0 行 tutor 运行时代码消费**。

**战略转向（最重要）**：不要把"修边"当目标。专家对抗评审的硬数据显示图谱目前只服务可视化/目录，不在判题/辅导路径上。因此修复顺序必须是 **先固地基 + 先证消费价值，再谈边的精修**，而不是反过来。否则是在流沙上给没人读的工件抛光（boil-the-ocean 反模式）。

---

## 1. 三条贯穿全局的架构决策（先于 6 个具体问题）

### D1. 节点身份与码解耦（P0，阻塞一切）
**问题**：`id = code#ordinal` 是位置性 ID；311 个码真冲突覆盖 2257 节点（60.6%）；recompile 重排会让已持久化的 `taxonomy_id`（学情、薄弱点、学习路径锚点）静默指向另一个概念。
**决策**：引入**全局唯一、幂等、内容派生的 node uuid**（纯函数：规范化 name_path + name + 语义指纹 → sha256），code 降为展示/分类标签，不再当主键/路由键。
**为什么**：uuid 幂等（同概念跨 recompile 不变）+ 消歧（同码不同概念必不同）。这是边质量、内容覆盖、学情持久化一切可信的前提。
**不确定性**：500 个"同码同名"无法纯机器判定是真冗余（可合并）还是上游漏给不同名的不同考点（应保留）→ 需抽审一批（见 §3 P0）。

### D2. 判题权威结构性隔离（P0，不可协商）
**决策**：图谱信号（边/节点，含 1152 条未 QA 的 LLM 边）**结构上**永不出现在 `LubanContextPack.rubric_context / source_context / diagnostic_policy / required_terms`；只走 `learner_context` 教学旁路，带 `kind=graph_teaching_hint, authority=non_authoritative, is_answer_key=False`。
**验收断言**：一条自动化测试——注入任意图谱 hint 后，`build_deep_question_grading_result` 的 `release_truth / answer_key_authority / official_release_score / required_terms` 在 100% 样本上**逐字不变**。靠测试，不靠纪律。

### D3. 两套边的边界（静态图谱 vs 动态学情）
**事实**：项目已有第二套"可行动边"——`learner_state` 的 error_points_to_training / training_uses_question（已有 `audit_learning_brain_actionable_edge_coverage.py` 审计）。
**决策**：
- **图谱边 = 静态课程结构**（概念级"X 的前置是 Y"、"X 与 Z 跨章相关"）——回答"知识地图长什么样"。
- **learner_state = 动态个人证据**（这个用户真做错了什么、该练什么）——回答"这个学生现在在哪、下一步练什么"。
- **组合而非竞争**：图谱给地图，learner_state 给位置。前置补救 = learner_state 定位薄弱点 → 图谱回答"它的前置概念是什么" → 是否已掌握仍由 learner_state（唯一 learner-truth，`is_second_memory_authority=False` 不破）裁定。**图谱绝不写回学情。**

---

## 2. 分阶段计划（按依赖与价值排序）

### Phase P0 — 地基与安全门（阻塞项，必须先做）
| 项 | 内容 | 确定性 | 验收 |
|---|---|---|---|
| P0-1 (#5) | 节点全局唯一 uuid（内容派生纯函数）+ code 降级为标签；compiler 输出 ambiguous 工单不再静默丢弃 | deterministic | distinct uuid == 节点总数；同源随机打乱重编译 uuid diff==0（幂等回归） |
| P0-2 (D2) | 判题权威结构隔离断言测试 | deterministic | 注入图谱 hint 后判题权威字段 0 漂移 |
| P0-3 (#5 抽审) | 500 同码同名 + 311 同码不同名 抽样裁决（真冗余 merge / 不同概念 re-key） | hybrid（抽审）| ambiguous code 100% 落档（合并/重分配/确认分层） |

### Phase P1 — 逻辑自洽 + 证明一个消费场景（止血 + 兑现价值）
| 项 | 内容 | 确定性 | 验收 |
|---|---|---|---|
| P1-1 (#2) | `enforce_prerequisite_dag` 纯函数门：对称冲突消解（lecture > llm；树祖先关系→降级 part_of；否则 confidence/字典序）+ Kahn 拓扑破环 + audit 报告；接进 assemble_graph + CI 断言 | deterministic | prerequisite cycles==0、mutual==0；CI 含含环输入断言抛错 |
| P1-2 (#2) | 对当前 5 对冲突一次性人工方向校准（领域常识，~15 分钟）写 `prerequisite_overrides.json` | manual | 5 对方向经人审落档 |
| P1-3 (#1) | `prune_related` 纯函数：删同父兄弟（用 CanonicalTaxonomy 真实父指针，**不**用字符串 rsplit，依赖 P0-1）+ 无向对称归一（合并 265 互逆对）+ 标记 cross_chapter | deterministic | related 兄弟占比≤10%、互逆对==0；related 1157→约545 |
| P1-4 (#6/D3) | **证明一个消费场景**：2 个真实章节端到端 demo——错题(learner_state)→图谱取前置概念→四源教学上下文呈现前置补救。teaching 旁路、flag 门控、运行时 DAG 去环+depth 上限 | hybrid | before/after 对比展示"图谱边参与→辅导输出改变"；判题权威不变 |

### Phase P2 — 质量与信号增厚（价值确认后再投入）
| 项 | 内容 | 确定性 | 验收 |
|---|---|---|---|
| P2-1 (eval) | 边 QA harness：DAG 无环率/related 信息增益/跨章前置准确率(人审高风险层)/证据轴覆盖率；基线快照 + CI 回归 | hybrid | 指标可重复 bit 级一致；基线入库 |
| P2-2 (#4) | 跨章前置/概念互链增召回：先专家种子+课程序列（高精度），再题库共现锚定（客观 provenance）；LLM 仅判候选 | hybrid | 跨章前置从 19→目标≥80，每条带≥1 客观证据轴；精度人审≥90% |
| P2-3 (#1-C) | related 教学价值锚定：题库/采分点共现生成带证据边（替代 LLM 主观相关） | deterministic | 共现边带题号+采分点 provenance |
| P2-4 (#3) | 889 空节点三态切分：真缺口(补内容)/不该有内容(标注豁免)/源冗余(P0 已 re-key 合并) | hybrid | 每个空节点有三态标签；真缺口进编译 backlog |

---

## 3. 关键不确定性与验证/替代

| # | 不确定性 | 验证方法 | 替代方案 |
|---|---|---|---|
| U1 | 题库案例题是否真带多 node_code 标注（决定 #4-共现 与 #1-C 价值） | 回原始题库源核实 exercises 是否保留多节点；bundle 内目前每题单 predicted_node | 若无多标注：#4 退回专家种子+课程序列；#1-C 退回教材交叉引用共现 |
| U2 | 500 同码同名是真冗余还是漏命名的不同概念 | 抽审 30-50 个（人/LLM）估真冗余率 | 保守：默认保留（re-key 为不同 uuid），只 merge 人工确认的 |
| U3 | confidence 不可作过滤器（实测兄弟 0.739 > 跨主题 0.65） | 已实测证实 | 用结构判据（是否跨树）替代分数门——全计划已采纳 |
| U4 | #6 prompt 渲染注入点未逐字定位（four-source→LLM prompt 末段拼装） | 动工前用 codegraph 追 `luban_canonical_knowledge` 的读取/渲染点 | 若注入点复杂：先做 P2-1 告警门（不进答案路径），延后 P1-4 |
| U5 | 图谱消费价值是否成立（对抗评审质疑） | P1-4 的 before/after demo 即为价值验证门 | 若 demo 无显著改善：图谱定位收敛为 kmap/覆盖分析，停止边精修 |

---

## 4. 量化"做好了"的判据（done metrics）
- 地基：每个真实概念恰好一个 uuid；resolver 主路径可达率 26%→100%；幂等重编译身份 diff==0。
- 逻辑：prerequisite cycles==0、mutual==0（CI 守）；related 兄弟占比≤10%、互逆==0。
- 权威：注入图谱 hint 后判题权威字段 100% 样本 0 漂移；学生面图谱信号 100% 指向 has_content 节点。
- 信号：跨章前置≥80 且每条带客观证据；进 tutor 默认路径的边 ≥80% 带客观证据轴。
- 价值：≥1 个辅导场景在 2 章端到端 demo，有 before/after 改变证据。

---

## 5. 执行顺序（依赖闭环）
P0-1（uuid 地基）→ P0-2（权威门）→ P1-1/P1-2（DAG 自洽）→ P1-3（related 提纯，依赖 P0-1 真实父指针）→ P1-4（证消费价值，门槛：U5 通过才继续 P2）→ P2-*（增厚，价值确认后）。
**P0-3 与 U1/U2 的抽审可与 P1 并行。**

---

## 6. 范围外/红线（不变）
判题权威始终是本地逐字 signed bundle；图谱/四源是教学层（`official_score_allowed` 结构性 False）；远端写（Supabase）需带凭据人工执行；不改 learner-truth 唯一权威（LB claim lifecycle）。
