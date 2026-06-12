# 鲁班案例题 + rubric 数据扩产计划（v1 registry 真正前置）

> Status: `In progress`（2026-06-04）。**这是 `QuestionGradingArtifact Registry v1` 的真正前置——
> 不是数据缺失，而是结构化 + 教材逐字锚定 + 复核 pipeline 未放量。**
> 红线：不伪造 source_ref、不把 MCQ 塞进 case registry、不把 node-level 6134 资产直接当 question rubric、
> 不把题库 explanation/official_answer 当 textbook 强锚、不接 production runtime、不改 kernel/RAG、不新增表。

## 0. 背景（重大更正）

> **更正**：早前 `registry_v1_20260604/` 的 `data_blocked / 0 candidates` 结论**错误**——只扫了当前 repo。
> 真实外部题库存在：`/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/`：
> - `题库/`：2015–2025 一建建筑实务真题，**218 道 case_study**（带 stem + correct_answer + score）。
> - `2026教材/第二次加强/FINAL_CLEANED_BOOK2026-*_fixed.json`：650 content_blocks，**唯一 textbook verified 锚源**。
>
> 因此**数据充足**。Registry v1 的真正瓶颈是：`official_answer → 采分点结构化 → typed_policy → 2026 教材
> content_markdown verbatim 锚定 → LLM jury 候选 → PO 复核 → AuditPacket`。题库 explanation/official_answer
> 只作 weak source。M2 抽首批 30 候选；M3 已结构化（138 采分点 / 28 verbatim 教材锚 / 16 published_candidate_not_final
> / 14 draft），见 `artifacts/luban_grading_artifacts/case_rubric_structuring_m3_20260604/`。

## 1. 目标

把 registry 从 20 题扩到可规模化题库，**真实生成新的 `QuestionGradingArtifact` 输入**——
每道新案例题带可发布/可草稿的采分点 + 教材锚定 source_refs。published 不强求，但每一条都必须真实可溯源。

## 2. 数据单元（每道案例题最小字段）

```jsonc
{
  "question_id": "...",
  "question_text": "...",
  "official_answer": "...",
  "node_code": "1A4xxxxx",
  "student_answer_samples": [],            // 可选，用于 typed_policy 校准 / 盲化
  "gold_scoring_points": [
    {
      "point_id": "P1",
      "label": "...",
      "max_score": 2,
      "policy_type": "exact_required|list_rule|calculation|penalty_rule|figure_label|high_risk_review",
      "required_terms": ["..."],            // exact_required 必须有
      "list_rule": {"denominator": 4, "terms": ["..."]},   // list_rule 必须有
      "calculation_spec": {...},            // calculation 必须有
      "penalty_rule": {...},
      "source_refs": [
        {"source_type": "textbook", "chunk_id": "1A4..._00x", "textbook_quote": "<原文>", "verified": true}
      ],
      "verification_status": "verified|weak|unverified",
      "auto_certifiable": true              // 仅 verified textbook 强证据点
    }
  ],
  "typed_policy": {...},
  "provenance": {...},
  "content_hash": "..."
}
```

## 3. authority 顺序（硬约束）

1. **教材 `content_markdown` / PDF 原文** —— 最高 source authority（采分点术语原文）。
2. **官方答案** —— 识别采分点结构（不当 textbook 强锚）。
3. **多模型 rubric extraction** —— **只作候选**（4-model：GPT5.5+Opus4.8+DeepSeek-V4+Qwen3.7），不当 authority。
4. **teacher / PO review** —— 才能把候选升为 authority（draft→published 的唯一闸门）。
5. **node-level 6134 资产** —— 只作 **search / index seed**（按 node 检索候选教材锚），不直接当题目采分点。

> 与既有 memory 一致：采分点必须来自对应教材原文（textbook provenance chunk_id + quote），近义不算。

## 4. 数据生产流程

```
案例题收集（历年真题 / 命题）
  → official_answer 解析（识别采分点结构）
  → 4-model rubric candidate extraction（只产候选 + 分歧标注）
  → 教材原文锚定 verify-on-write（required_term 必须在 node 的 textbook chunk 中逐字出现 → chunk_id+quote）
  → typed_policy classification（exact_required / list_rule / calculation / penalty_rule / figure / high_risk）
  → teacher / PO review（升 authority；高风险/计算/罚则重点复核）
  → QuestionGradingArtifact draft / published（quality gate）
  → registry publish gate（ArtifactRuntimeGate 消费）
```

每题产出一个 **audit packet**（候选 → 锚定 → 复核 → 终态 的可追溯链）。

## 5. 最小批量（第一批）

- 目标：**新增 20–30 道案例题**。
- 至少 **100–150 个 scoring points**。
- published **不强求**（取决于教材锚定 + 复核结果），但必须真实；draft 允许，draft 不 auto-certify。
- 教材覆盖：优先补当前 registry 已 draft/blocked 的薄弱 node（如 Q20 计算类、Q15 开放类）。

## 6. 质量门（与 v0/v1 一致，不复制 gate 逻辑）

- `verified` textbook source_ref 才能 `auto_certifiable=true`。
- `official_answer_weak`（仅官方答案、无教材锚）→ 不可 auto。
- node 资产命中但**题目语境不明** → 不可 auto（防 loose-match 伪造）。
- calculation 必须有 `calculation_spec`；list_rule 必须有 denominator / item set；exact_required 必须有 required_terms。
- `high_risk_review` 永不 auto。
- 每题必须能生成 audit packet（无 packet 不入库）。

## 7. 与 runtime 的关系

- runtime 继续只读 `QuestionGradingRegistry → ArtifactRuntimeGate`（不新增第二套 lookup）。
- 新题未 published → gate fail-closed / draft-only（`artifact_missing` 或 `artifact_not_published`，不 auto-certify）。
- teacher-final 仍是 Learning Brain 写入 authority；AI auto-certification 受 artifact gate 控制（已在 e2e 闭环验证）。

## 8. 里程碑

| 阶段 | 交付 | 门 |
|---|---|---|
| M1 数据 schema 冻结 | 案例题数据单元 + audit packet schema | 与现有 QuestionGradingArtifact schema 对齐 |
| M2 第一批采集 | 20–30 题 official_answer + node_code | 真题/命题来源可溯 |
| M3 4-model 候选 + 教材 verify-on-write | rubric 候选 + chunk_id/quote 锚定 | required_term 逐字命中教材 chunk |
| M4 teacher/PO 复核 | 升 authority 的复核结果 | 高风险/计算/罚则全复核 |
| M5 v1 编译放量 | `build_luban_question_grading_registry_v1.py` 吃新源 → registry_v1 | 不伪造、quality gate 全过、gate 可消费 |

## 9. 下一步执行 prompt（M1）

冻结「案例题 + audit packet」数据 schema（对齐 QuestionGradingArtifact），定义 verify-on-write 教材锚定规则
（required_term ↔ node textbook chunk 逐字匹配），产出 1–2 道样例题的 audit packet 作 schema 验证；
不接 runtime、不伪造、不新增表。
