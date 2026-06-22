# 深 pack → Nexus/KnowQL grain 分级供给 规范 v2

> **本文档经过两次收敛**: ①初版「自建 L0 路由卡」→ ②「pack 做成 TutorBot skill」→ ③本版「pack 走 Nexus/KnowQL grain 分级供给」。
> **为什么最终落到 Nexus**: 深 pack 是确定性结构化编译资料(point_id/leaf/question_id 唯一 key), 第一性原理上属于**确定性检索**; 做成 skill(description 语义自选)或塞 RAG(向量模糊召回)= 在确定性资料上加语义不确定性 = 错配 + 降级 + 多一套机制伤单一权威。
> **状态**: candidate 设计。

---

## 0. 一句话结论

40 个深 pack **走 Nexus/KnowQL**(确定性按 leaf_code/question_id 取), **不做成 skill, 不进 RAG**。取用按 **grain 分级**(采分点切片 / 章节 / 整 pack, 一般取一点、疑难才全塞)。判分侧考点已确定直接取; 对话答疑侧需一个轻量"问题→考点"前置路由(确定性 trigger + 语义兜底)。

---

## 1. 第一性原理: 检索机制要匹配资料形态

| 资料形态 | 匹配的检索 | 理由 |
|---|---|---|
| **确定性结构化**(深 pack: point_id/leaf/question_id) | **Nexus/KnowQL**(确定性 key 取) | 采分点要精确, 一个 leaf 取错就判错分; 可治理 register-before-use |
| 语义/散文(概念、规范解释) | **RAG**(向量召回) | 相似度召回够用, 无唯一 key |
| agent 行为/教学模式 | **skill**(怎么当老师/讲义导航) | 装"行为", 非知识弹药主检索 |

把确定性资料硬塞进语义机制(skill 的 progressive discovery 语义自选 / RAG 模糊召回)= 人为引入不确定性, 是降级。**这是本文档从「做成 skill」回撤的根因。**

---

## 2. 单一权威分流: 三套机制各司其职 + 一个前置分流决策

担忧: skills / RAG / Nexus 三套并存 → 系统不知道用哪个, 或都用了(浪费)。
**解法不是三选一, 是「按资料形态单一分流」+「一个单一前置分流决策」**:

```
用户输入 / 当前 turn
  → 单一前置分流决策 (这轮是: 案例采分 / 知识问答 / 教学行为?)
      ├─ 案例采分(深 pack)  → Nexus/KnowQL  (确定性取采分点弹药)
      ├─ 知识问答(概念散文) → RAG           (向量召回)
      └─ 教学/出题行为      → skill          (construction-exam-tutor 等)
```

"都用了 = 浪费"的根因正是**缺这个单一前置分流**, 让三套各自抢着往 context 塞。
> 实证: `always: false` 解析 bug 曾让 **全部 15 个 always:false skill 每轮被注入**(case-grading+mcq-grading+lecture+knowledge-base 全挤进 context)——这正是"都用了"的字面发生。已修(commit `d0c86585f`): 现只 memory 常驻, 其余按需。修 bug 是恢复单一分流的前提之一。

既有硬要求(本规范遵循): **案例题→Nexus**(采分点细节、确定性); **知识性问答→RAG**。深 pack 是案例采分型 → Nexus。

---

## 3. grain 分级: "取多细"是 Nexus 的粒度维, 不是另一套系统

分级思想(一般取一点、疑难才全塞)**保留**, 落成 Nexus 供给的 **grain**:

| grain | 内容 | token | 取用 |
|---|---|---|---|
| **G1 采分点切片** | 该考点采分点(必写关键词/标准表达) | ~几百 | 绝大多数判分/答疑**够了** |
| **G2 章节** | R5 全章 / R8 误区 / R7 边界 | ~几千 | 追问、中等难度 |
| **G3 整 pack** | R1-R8 全套 | ~4万 | 疑难/深度论证才取 |

**token 账(J01 具象, 与早先 L0 表同账, 宿主换 Nexus 后更准)**:
- 一般问答: 前置路由(小) + G1 切片 ~ 几百 ≈ **2-3k token**
- 疑难升 G3: ~43k(仅疑难付)
- 旧方案全塞单 pack: 41k(每次付); 41 pack 全塞: 190万(爆 1M)

Nexus 比 L0 更优: 判分时 question_id 自带 → **确定性取 G1**, 不像 L0 还要语义路由一次, **更准不会选错考点**。

---

## 4. 对话答疑的"问题→考点"前置路由 (L0 判别思想的唯一落点)

判分时考点确定(题带 question_id/leaf); **对话答疑时考点不确定**, Nexus 需要前置路由确定"取哪个 pack 的 leaf"。这是早先 L0「判别性」思想的**唯一存活落点**, 但它落在 **Nexus 前置, 不是独立 L0 系统、不是 skill**:

确定性优先 + 语义兜底(三层递降):
1. **question_id**(若题在上下文) — 确定
2. **discriminative_trigger**(考点独有判别词, 数据驱动) — 确定性命中
3. **语义兜底**(母题不变量一句话, 模型判) — 前两层不命中才上

判别词跨考点**唯一性**是命门(防路由到错考点 → 取错弹药), 编译时 fail-closed 闸保证(与 RichLeaf 污染闸同构)。这是早先 L0 设计**唯一保留的硬资产**。

---

## 5. 判分侧 (deep_question 已经这么做, 大概率零改)

`deep_question` 当前已走 `rich_leaf_runtime.get_rich_leaf_context(leaf_code)` + rag + compiled grounding = **按 leaf_code 确定性取**(就是 Nexus 那条)。所以:
- 判分侧**不需要新增 progressive discovery**(考点已确定, 语义自选是过度设计)
- pack → Nexus 供给(rich_leaf/rubric)后, deep_question **代码大概率零改**, 只是 bundle 内容来源换成深 pack 编译产物
- `official_score_allowed=false` / judgment 归判分内核, 不变

---

## 6. 编译: 单一源(signed pack) → Nexus 供给 (复用 RichLeaf 管道)

```
深 pack(R1-R8 + 作答层, signed 唯一源)
  → build (复用 rich_leaf 编译 + fail-closed 闸模式, 不另起一套)
      ├─ G1/G2/G3 grain 切片 → rich_leaf bundle(leaf_code 索引)
      ├─ 采分点 rubric        → rubric PGO(question_id 索引)
      └─ 前置路由元数据        → discriminative_triggers + linked_question_ids(数据驱动)
  → 跑判别性 fail-closed 闸(触发词跨考点唯一 / key 存在性) → 全过才发
```

| 供给字段 | 派生自(唯一源) |
|---|---|
| grain 切片内容 | pack R1-R8 / 作答层(signed 逐字派生) |
| rubric 采分点 | signed R5 |
| discriminative_triggers | pack R2/R8 关键词 + 跨考点唯一性闸 |
| linked_question_ids | `_<ID>_exam_evidence.json` 真实题号 |
| leaf_code / question_id | canonical taxonomy / 真题 |

---

## 7. 红线

1. **深 pack 走确定性检索(Nexus/KnowQL), 不做 skill、不进 RAG**(确定性资料配确定性检索)。
2. **单一前置分流决策**: 案例采分/知识问答/教学行为三分流, 不让三套机制各自抢注入。
3. **判分归内核**: 供给只给弹药, `official_score_allowed=false`, judgment 归 grading 内核。
4. **真题锚只用证据包真实题号**, 禁编造。
5. **单一源派生**: 供给从 signed pack 编译, 不手写、不造第二 authority。
6. **判别词跨考点唯一**(前置路由 fail-closed 闸), 防误路由。
7. **register-before-use**: 供给进 runtime 需 signed gate; leaf_code/question_id 必须真实存在。

---

## 8. 与既有资产关系

| 既有 | 关系 |
|---|---|
| **rich_leaf bundle / rubric PGO** | **直接宿主**(Nexus 供给); 深 pack 是源, bundle 是判分/答疑投影。 |
| **deep_question** | 已按 leaf_code 取 rich_leaf, 是判分侧现成消费者, 大概率零改。 |
| **lecture skill** | **不同形态**: 讲义=知识/教学性走 skill 合理; 深 pack=采分性走 Nexus。二者本就该走不同机制, 不矛盾。 |
| **RAG(compiled_truth_source)** | 知识性问答宿主; 深 pack 不进这里(它是采分非散文)。 |
| **always bug fix(`d0c86585f`)** | 恢复 skill 按需注入, 是"单一前置分流"成立的前提之一。 |
| **case-answer-layer / 60-slot 注册表 / canonical taxonomy** | 编译上游(内容源 / pack_id / taxonomy)。 |

---

## 9. 待验证

- **前置路由判别度**: 40 考点 discriminative_triggers 跨考点冲突率(编译跑唯一性闸看 block 率)。
- **grain 切分粒度**: G1 采分点切片的"判分角度"与"答疑角度"字段是否需各一套, 还是共享。
- **deep_question 零改假设**: bundle 源切到深 pack 后, deep_question 是否真零改(待接一个考点验证)。
- **单一前置分流决策的实现点**: 案例/知识/行为分流挂在哪(orchestrator? scene? ), 与现有 question_lifecycle scene 的关系——避免再加第二个分流决策(多头)。
- **先接一个考点端到端**(J01: 采分点→rich_leaf 供给→deep_question 判分)实测 token 与判分精度, 再铺 40。
