# 考点深度原料（Deep Exam-Point Pack）

> **本目录不是新 authority，是已有权威的实例化。**
> 每份文件 = 一个考点的 R1-R8 **签发候选草稿**，实例化 `case_family_structure` 七层 schema，
> 用于 `2026-06-18-深母题引擎底座数据资产实施判断.md` §七 说的 **pack manifest**（三张表之一）。

## 它对齐谁（register-before-use）

| 维度 | 唯一权威（不在本目录重造） | 本目录怎么用 |
|---|---|---|
| 资产结构 schema | `docs/plan/鲁班移动端提分闭环/2026-06-16-luban-deep-archetype-asset-schema-v2.md`（L0-L7） | 实例化 L1-L6，不增层、不立新 schema |
| 考点身份/清单 | `2026-06-18-luban-animation-learning-system-master-plan.md`（L40+L20） | 用既有 pack_id（如 **Q02=大体积混凝土温控**），不另起名 |
| 知识点身份 | canonical taxonomy `FINAL_CLEANED_TAXONOMY2026.json` | 用 `node_code` 引用，不另起知识树 |
| 错因轴 | `deeptutor/contracts/error_codes.py` `ERROR_CODE_REGISTRY`（E01-E12/M01-M10） | R8 误区**映射**到 error_code，禁自造错因码 |
| 教材溯源 | textbook verbatim lane | R1-R6 内容必须可溯源到教材/规范原文 + sha |
| 判分/学情真相 | signed grading artifact / `CaseGradingSkillKernel` / `LearnerStateService` | 本目录**只发候选、不写分数/错因结论/学情** |

**红线**：本目录是 teaching/diagnosis 候选层，永不作为 official score / canonical 错因 / learner truth 的第二来源。

## 相对 L0-L7 的三点增量（折进既有层，不另立）

L0-L7 已覆盖不变量/出题人/表征/变体/误区/复测。针对"喂动画讲解 + AI 极高理解 + 诊断下药"，本目录的每份 pack 额外补三块 teaching-tier context：

1. **跨章知识点聚拢**：一个考点的知识点散落在材料章/施工章/质量章，本 pack 把它们聚到一处（现 schema 是单母题/单不变量视角，不聚拢）→ 喂 L1/L3。
2. **原理因果层**：因果链（如 水化热→温升→内外温差→温度应力→裂缝），让讲解"深刻"、让 AI 真懂 → 喂 L3 表征 + 动画。
3. **动画分镜原料**：视觉隐喻/reveal 顺序/aha 时刻/旁白锚点 → 喂 `animation-learning-system` 的 A/B/C/D 生产形态。

## 溯源三色（每条 claim 必标）

- 🟢 **锚定**：教材/编译采分点/真题，附 source_ref
- 🔵 **通识**：工程原理/教材物理常识，安全但未逐条挂 chunk
- 🔴 **待验证**：需真题库拉取或真人/专家裁决，**禁编造**（R7 边界答案、真题频次细节多在此）

> 🔴 越少 = pack 越强。🔴 项就是"AI 专家团 + 真题 + 你终审"该夯实的精确位置。

## 进入 active 的门槛

见判断文档 §六 Pass Criteria（每字段 sha、R2 一句话解释≥5场景、R5 只引用 signed refs、R7 补 30-50 条真人边界、R8 全映射 error_code…）。本目录文件默认 `candidate_teaching_prototype`，**不授权 runtime 消费**。

## 文件

- `Q02_大体积混凝土温控.md` — 首个 pack（混凝土 184 旗舰子点；P0-12）
