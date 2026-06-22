# J01 采分点 → Nexus/rich_leaf 供给 实施计划

> **状态**: ⛔ **原 schema 决策(§1)与"新建供给"前提已作废** — 见下方「2026-06-22 调查更正」。本文 §0-§10 保留为调查前的初始设想(思考痕迹), 当前权威结论以更正块为准。
> **上游规范**: `2026-06-21-luban-l0-topic-routing-card-design.md`(深 pack→Nexus grain 分级供给 v2)

---

## ⛔ 2026-06-22 调查更正 (当前权威结论, 覆盖 §0-§10)

Gate 1 的 register-before-use 防撞名查证 + 只读调查 (Explore agent) 发现: **采分点 → 判分供给的完整架构早已存在, 原计划"新建 scoring 供给"会制造第二套真值**。本块为当前结论。

### 真相 (代码级证据)
1. **采分点判分真值的唯一源 = 已有 `scoring_point_compile` 管道**: `scripts/run_luban_rich_leaf_scoring_point_compile.py` 产 `luban_rich_leaf_scoring_point_compile.v1`(三 lane: m35_artifact / chunk_assessment / knowledge_card, 按 chunk_id 迁移, 无溯源不造点), 经 `grading_object_adapters.py::map_rich_leaf_unit` 收敛到 `luban_grading_object.v1`(KnowQL pillar① 两 divergent schema 之一, 测试钉死 "no second adapter is minted")。
2. **J01 接入形态 = (a) 已覆盖**: J01 的 7 个 leaf/chunk 与已有 rich-leaf token pack **完全同体系**(chunk_id 天然主键, 零对齐); J01 核心采分点(`kc:`/`ca:`/`m35:`)已在 `artifacts/luban_grading_artifacts/rich_leaf_v32_scoring_point_compile_20260613/runtime_token_pack_v32_scoring_points.json`(1612 units / 5705 点)里; **J01 文件的 `kc:`/`ca:` 就是从该 v3.2 产物逐字抄的**。
3. **`docs/原始数据/考点原料/_J01_compiled_source.json` 是采分点真值的第二副本(⚠️单一权威风险)**: 抄了管道产物 + 漏收 2 条 m35 golden 点 + 私加 11 个 `cc:` 逐句引用点(三 lane 都不产, 绕过 quote_verified / required_term verbatim 溯源硬门)。目前**无任何 .py 引用(孤儿数据)** → 趁现在**不得让它进入判分链做真值**。

### 修正后的真问题 (不是"编译 J01 采分点", 是"promotion")
- 真正卡住"40 pack 走 Nexus 判分"的是: **v3.2 候选产物(`candidate_only=true / runtime_install_allowed=false / canonical_truth_written=false`) → runtime 真值的 promotion gate** — 谁、什么门禁、A/B。本调查**未覆盖**此 promotion 路径, 是下一步要查的。
- **最小改动**: 不新建编译器 / 不新建 schema / 不喂 `_J01_compiled_source.json`; 把已有 v3.2 候选按既定 promotion 流程提升, J01 leaf 随管道一并覆盖, 判分走现成 `map_rich_leaf_unit`。

### 作废原 §1 的 schema 决策
- 原推荐"选项 A 新建 `luban_rich_leaf_scoring_bundle.v1`" = **制造第三个 divergent schema, 违反单一权威, 作废**。选项 B/C 同废(前提"无现成供给"被推翻)。

### 需 owner 决策 (下一步)
1. **`cc:` 11 个逐句引用点去留**: 倾向丢弃(非采分点形态, 是教材原句); 若有判分价值, 让编译器某条 lane 带溯源重新生成, 不原样灌入真值。
2. **m35 漏收**: promotion 必须走编译器 v3.2 产物(非 J01 文件), 否则丢 `Q13-1A421000:P2` / `Q2-1A436000-罚则:P1` 两条 golden。
3. **v3.2 候选 → runtime 真值的 promotion 路径/门禁**: 本调查未覆盖, 是 (a) 的实际工作量所在, 需先查清再写修正计划。
4. **`_J01_compiled_source.json` 定位**: 应定为一次性人工 review / 选 leaf 清单, **不得作真值源**; 是否有非代码消费者(shell/notebook)未穷尽。

### 单一权威铁律 (本次教训)
采分点 ground truth **唯一** = 编译器 v3.2 产物(promotion 后的 runtime 真值) → `map_rich_leaf_unit` → `luban_grading_object.v1`。深 pack **只引用不拥有评分**(产品战略既定); `_J01_compiled_source.json` 是引用副本非真值。**造新供给/复制采分点的任何倾向 = 红线。**

---

## 0. 为什么是这个计划 (实测缺口 → 可执行)

2026-06-22 J01 端到端实测确认 (真实数据):
- ✅ 取用入口现成: `rich_leaf_runtime.get_rich_leaf_context(leaf_code)` 确定性取, 已内建 `official_score_allowed=False`; deep_question 已调它 → 判分侧零改。
- ✅ token 账兑现: G1 单 leaf 切片 ~1240 token / 取 2-3 leaf ~3000-9000 / G3 整 pack ~20800 → 一般判分是整 pack 的 ~10-15%。
- ⚠️ **真缺口**: 现有 bundle 装的是 RichLeaf 编译的 **teaching context**(字段 `concepts/exam_patterns/rules/teaching_cards`, `tier=teaching_context_not_answer_key`), **不含 J01 的 signed R5 判分采分点**。两者覆盖同考点但不同内容、不同用途。
- ✅ key 对齐比预期简单: J01 采分点 `point_id = kc:1A436000_008_0011:0` **内嵌 canonical code** `1A436000` → 路由 key 可从 point_id 确定性解析, 不靠 leaf_name 模糊匹配。

---

## 1. 核心 schema 治理决策 (本计划最重要的决策, 需 owner 拍板)

### 张力
现有 `luban_rich_leaf_context_bundle.v1`:
- 语义: **teaching context**(教学辅助), `tier=teaching_context_not_answer_key`, `official_score_allowed=False`, 有 `signature`/`content_hash` 签名治理。
- 采分点性质不同: **判分弹药**(signed R5, 有 point_id/quote/required_terms/page 溯源), 是"判分依据"非"教学辅助"。

把采分点塞进现有 teaching bundle = 混两种 tier/用途 → 重蹈 RichLeaf 污染覆辙(不同性质内容挤一个 record)。

### 决策选项 (owner 三选一)

**选项 A — 新建独立 scoring 供给 (推荐)**
- 新 schema `luban_rich_leaf_scoring_bundle.v1`(与 teaching bundle 平行, 不混)。
- 采分点编译进独立 bundle, `tier=signed_scoring_point`, authority=`signed_r5`。
- 取用: 新增 `get_rich_leaf_scoring(leaf_code)` 或复用 runtime 加 `kind` 参数。
- **优点**: tier 不混 (单一权威清晰); teaching/scoring 各自治理; 不动现有 teaching bundle (零回归)。
- **缺点**: 多一个 bundle 文件 + 一个取用入口 (但语义正交, 非第二 authority)。

**选项 B — 现有 bundle record 加 `scoring_points` 字段**
- compiled_context 加第 5 字段 `scoring_points`, schema 升 `.v2`。
- **优点**: 单 bundle、单取用入口。
- **缺点**: 同 record 混 teaching+scoring 两 tier; 违反 RichLeaf "一 record 一性质" 教训; schema 升版本要重签全量 1595 record (signature/content_hash 全变, 影响面大)。

**选项 C — grain 作为 record 内分层**
- record 加 `grains: {G1_scoring, G2_section, G3_pack}` 结构, schema 升 `.v2`。
- **优点**: grain 显式建模, 一个 record 含全 grain。
- **缺点**: 改动最大; 现有 1595 record 全要回填 grain 结构; 过度工程 (J01 一个考点不需要这么重)。

### 推荐: **选项 A**
理由 (root-cause + less-is-more):
1. **tier 不混 = 单一权威**: teaching 是 teaching、scoring 是 scoring, 各自 signed gate, 不互相污染 (RichLeaf 教训的正解)。
2. **零回归**: 不动现有 teaching bundle 的 1595 record/signature, 判分现状不变。
3. **grain 暂不显式建模**: J01 阶段 G1=scoring bundle 的采分点切片, G3=整 pack 文件路径引用, **G2/grain 字段等真有疑难需求再加**(less is more, 不预造)。
4. flag 解耦: 新 scoring 供给配自己的 enable flag, 默认 OFF, 与现有 `LUBAN_RICH_LEAF_RUNTIME_ENABLED` 不耦合。

---

## 2. grain 字段方案 (最小可用, 不预造)

J01 阶段只做 **G1 + G3 引用**, 不建完整 grain 枚举:

| grain | 实现 | 来源 | token |
|---|---|---|---|
| **G1 采分点切片** | scoring bundle 的 record (按 leaf_code) | signed R5 采分点 | ~每 leaf 几百 |
| **G3 整 pack** | record 存 `pack_ref: {path}` 指针, 不内联 | pack md 文件 | ~20800 (疑难才解引用取) |
| G2 章节 | **暂不做** | — | 真有中等难度需求再加 |

scoring bundle record 结构 (新 schema):
```json
{
  "leaf_id": "1A436000",                    // 从 point_id 解析的 canonical code
  "leaf_name_path": "施工安全管理 > 危大工程范围",
  "scoring_points": [                         // G1: signed R5 逐字, 不改写
    {"point_id": "kc:1A436000_008_0011:0", "statement": "...", "required_terms": [...],
     "quote": "...", "page_ref": "..."}
  ],
  "pack_ref": {"pack_id": "J01", "path": "docs/原始数据/考点原料/成品/J01_*.md"},  // G3 指针
  "authority": "signed_r5",
  "tier": "signed_scoring_point",
  "official_score_allowed": false,           // 判分仍归内核, 供给只给弹药
  "source_ref": {...}                        // 溯源 (沿用现有 source_ref 形状)
}
```

---

## 3. key 对齐方案 (确定性, 不模糊)

J01 采分点 point_id 内嵌 canonical code → 确定性解析:
```
kc:1A436000_008_0011:0
   └──────┘
   canonical leaf_code = 1A436000  (正则: kc:([0-9A-Z]+)_...)
```
- 编译时从每个采分点 point_id 解析 canonical code 作 `leaf_id`。
- **fail-closed 闸**: 解析不出 canonical code / code 不在 canonical taxonomy → block 该采分点 (不瞎挂)。
- 一个 leaf_id 聚合其下所有采分点 (J01 的 7 unit → 按 canonical code 归并)。
- **不依赖 leaf_name 模糊匹配** (那是 RichLeaf 污染源)。

---

## 4. 编译流程 (复用 RichLeaf 编译 + fail-closed 闸模式)

`build_j01_scoring_supply.py` (复用 `run_luban_rich_leaf_*` 的编译+闸骨架, 不另起):
```
读 _J01_compiled_source.json (signed R5 采分点)
  → 按 point_id 解析 canonical leaf_code (§3)
  → 按 leaf_code 聚合采分点 → G1 record
  → 附 pack_ref (G3 指针)
  → 跑 fail-closed 闸:
      · canonical code 存在性 (在 FINAL_CLEANED_TAXONOMY2026.json)
      · point_id 真在 compiled_source (register-before-use)
      · 采分点逐字未改写 (与 signed R5 byte 对齐)
      · 无跨 leaf 污染 (同 RichLeaf enforce_no_intra_chunk_pollution 思路)
  → 全过 → 写 scoring bundle + signature/content_hash
```

| record 字段 | 派生自 (唯一源) |
|---|---|
| leaf_id | point_id 内嵌 canonical code (§3) |
| scoring_points | signed R5 (逐字, 不改写) |
| pack_ref | 60-slot 注册表 pack_id + pack 路径 |
| authority/tier | 固定 signed_r5 / signed_scoring_point |

---

## 5. 取用接入 (判分侧, 最小改动)

- 新增 `rich_leaf_runtime.get_scoring_points(leaf_code) -> list | None`(镜像 `get_rich_leaf_context`, fall-open 语义一致)。
- **deep_question 是否接**: 本计划**先只做供给 + 取用入口 + 单测**, **不改 deep_question 判分主链路**(那是开 flag 进生产判分, 需 A/B, 见 §7)。先让供给可被取、可验证, 判分接入是独立下一步。
- 新 flag `LUBAN_RICH_LEAF_SCORING_ENABLED` 默认 OFF。

---

## 6. 验证 (TDD + 实测)

1. **编译器单测**: J01 采分点 → scoring bundle, 断言 record 数 = canonical leaf 数、采分点 byte 对齐 signed R5、fail-closed 闸拦造假 (改一个 point_id 使其 canonical code 不存在 → 编译报错)。
2. **取用单测**: `get_scoring_points("1A436000")` 返回该 leaf 采分点, 不存在 leaf → None (fall open)。
3. **token 实测**: 打印 G1 单 leaf / 多 leaf / G3 引用解引用的真实 token, 对照 §0 预期 (G1 ~1240, 整 pack ~20800)。
4. **判别性**: J01 的 canonical code 与现有 teaching bundle 同 code 的 record 不冲突 (两 bundle 平行, 同 code 不同 tier 可共存)。
5. **回归**: 现有 teaching bundle + `LUBAN_RICH_LEAF_RUNTIME_ENABLED` 行为 byte 不变 (新供给完全独立)。

---

## 7. Owner Gate (分两道, 不可跳)

**Gate 1 — schema 决策 (本计划执行前)**:
- owner 批准 §1 选项 A (或改选 B/C)。
- 确认新 schema `luban_rich_leaf_scoring_bundle.v1` 命名 (先 grep schema_registry 防撞名, register-before-use)。
- 确认 J01 采分点的 R7 边界档 🔴 状态: 供给只给采分点弹药, 不给判分档位 (判分归内核)。

**Gate 2 — 进生产判分 (本计划之后, 独立 PR)**:
- 本计划产物 (供给+取用+单测) 是 **candidate, flag OFF, 零判分影响**。
- 开 `LUBAN_RICH_LEAF_SCORING_ENABLED` 进 deep_question 判分前需:
  - near-live A/B shadow (对照 J01 真题判分: 有采分点供给 vs 现状)。
  - frozen sample audit (采分点 byte 对齐 signed R5)。
  - 异源裁判抽检 (防同源盲点; memory 教训)。
- 与现有 rich_leaf flag 的 A/B 同纪律 (memory: richleaf promote owner 后续)。

---

## 8. 红线

1. **采分点 signed R5 逐字派生, 不改写不另造** (ground truth 归 R5)。
2. **判分归内核**: 供给只给弹药, `official_score_allowed=false`, 不给判分档位。
3. **tier 不混**: scoring 供给独立, 不塞进 teaching bundle (RichLeaf 污染教训)。
4. **key 确定性**: 从 point_id 解析 canonical code, 不靠 leaf_name 模糊匹配; 解析不出/code 不存在 → fail-closed block。
5. **flag OFF + 不改判分主链路**: 本计划零判分影响; 进生产走 Gate 2 独立 PR + A/B。
6. **register-before-use**: 新 schema grep 防撞名; point_id/canonical code 存在性闸。
7. **不预造 grain**: J01 阶段只 G1+G3 引用, G2/完整 grain 枚举真有需求再加 (less is more)。

---

## 9. 交付物

| # | 产物 | 类型 |
|---|---|---|
| 1 | `build_j01_scoring_supply.py` 编译器 | 新脚本 |
| 2 | scoring bundle (J01) + manifest/signature | 新供给 (candidate) |
| 3 | `rich_leaf_runtime.get_scoring_points` 取用入口 + flag | 改 rich_leaf_runtime |
| 4 | 编译器单测 + 取用单测 + token 实测 | 新测试 |
| 5 | token/判别性实测报告 | 文档/报告 |

**不在本计划**: deep_question 判分接入 (Gate 2 独立 PR)、其余 40 pack (J01 证闭环后按模板扩)、G2 章节 grain。

---

## 10. 待验证 / 不确定

- **canonical code 聚合粒度**: J01 7 unit 解析出几个不同 canonical code? 若多 unit 同 code, 采分点合并是否有跨 unit 语义冲突 (需编译时核)。
- **pack_ref 解引用成本**: G3 取整 pack 是运行时读文件还是预存? 频率低, 倾向运行时读 (不常驻)。
- **scoring vs teaching 双 bundle 的对话侧协调**: 对话答疑要 teaching, 判分要 scoring, 前置路由 (规范 §4) 怎么知道取哪个 bundle — 留待"单一前置分流决策"一并设计。
- **R7 边界档 🔴**: J01 R7 未经裁决, 供给标注但不固化为判分规则 (Gate 1 确认)。
