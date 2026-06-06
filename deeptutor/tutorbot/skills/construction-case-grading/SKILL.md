---
name: construction-case-grading
description: "建筑实务案例题阅卷 Skill。用于一建/二建建筑实务案例题答案批改、判分、估分、采分点命中、漏分诊断、得分表达改写、错因归类和下一题建议。用户说批改、判分、打分、估分、这题能得几分、漏了哪些采分点、答案怎么改成得分答案时使用。"
metadata: {"nanobot":{"emoji":"🧾"}}
always: false
---

# Construction Case Grading

这是建筑实务案例题的阅卷 Skill，不是泛讲解 Skill。

核心定位：

- Skill-first：先用建筑实务阅卷动作理解题干、答案和得分表达。
- Rubric-calibrated：有结构化 Rubric 时严格按 Rubric 给分；没有 Rubric 时仍做采分点推演和提分诊断。
- 不新建第二套题库：题目资产继续以 `questions_bank` / 当前 active question 为 authority。
- 不向用户展示置信度：内部可以有 `quality_signal`，用户只看到评分口径和可执行改进。

## 何时使用

用户明确要求以下任一任务时使用：

- 案例题批改、判分、打分、估分
- “我这题能拿几分”
- “漏了哪些采分点”
- “为什么这句话不给分”
- “帮我把答案改成得分表达”
- “下一题该练什么”
- 主观题/简答题/背景资料题提交了自己的作答

普通“案例题讲解/答题思路”仍可用 `construction-exam-tutor` 的案例讲解；只有涉及用户答案阅卷时进入本 Skill。

## 单一 Authority

本 Skill 只做阅卷动作，不抢既有系统权责：

| 业务事实 | Authority | 本 Skill 的职责 |
| --- | --- | --- |
| 题目资产 | `questions_bank`、当前 active question、或用户粘贴题干 | 只读取并投影评分框架 |
| 知识来源 | `rag` / 题库 provenance / 用户题干 | 需要依据时检索，不新增 grounded mode |
| 分数与诊断 | 本 Skill 的结构化阅卷动作 | 输出一次 grading result |
| 错因沉淀 | `LearnerStateService` memory/progress event | 只产生可写回事件，不建新画像库 |
| 下一题策略 | `assessment.teaching_policy` + 题库检索 | 只给 concept/error signal 和候选建议 |

## Forbidden Authority

- 不直接写 `LearnerStateService`、错题本、学习报告或长期学习画像。
- 不决定 TutorBot 路由；只有已经进入案例题阅卷场景时才执行。
- 不新建第二套题库、标准答案来源、Rubric 数据库或 RAG 模式。
- 不在只有用户答案、没有题干或上下文时硬打标准分。
- 不让 LLM 单独承担精确计算题、网络计划、费用索赔等确定性计算 authority。

## Anti-Patterns

- 没有 Rubric 却把推演采分点说成人工校准标准答案。
- 只有一句"加强管理"就给 full，而没有绑定用户原文证据和采分点。
- 用户只是要案例题思路时，直接进入批改并给分。
- 把内部 `quality_signal` 或写回资格直接展示给用户。

## 三档阅卷模式

先判断当前输入属于哪一档，再输出对应口径：

| 模式 | 条件 | 用户可见结果 |
| --- | --- | --- |
| `curated_rubric` | 有人工校准或结构化 Rubric | 明确得分、逐采分点命中、漏点、得分改写 |
| `projected_rubric` | 有题干、标准答案、解析、关键词、分值等资产，但无人工 Rubric；这些资产必须来自当前 active question、`questions_bank`、exact case retrieval 或明确题库证据 | 预计分或得分区间、推演采分点、漏点、得分改写 |
| `open_skill` | 用户只粘贴题干/答案，或题目资产不足 | 提分诊断、可能漏点、得分表达改写、建议补充信息/下一题 |

不要把 `projected_rubric` 或 `open_skill` 说成“低置信度”。用户看到的是“本次按采分点推演阅卷”或“本次按提分诊断处理”。

Authority guard：不得仅凭模型常识、普通 RAG 知识、相似题经验或用户题面里的暗示自行拼出 `projected_rubric`。如果没有当前题卡、题库命中、标准答案/解析/分值或结构化采分点，本轮只能是 `open_skill`，预计得分必须写“本次不硬估标准分”。

## 阅卷流程

1. **绑定题目**
   - 优先使用当前 active question / `questions_bank` 行。
   - 若用户粘贴完整题干，使用用户题干。
   - 若只有答案没有题干，先说明无法精确阅卷，并请用户补题干；可给通用表达诊断但不硬打分。

2. **读取可用资产**
   - 从题库或上下文读取：题干、背景资料、问法、标准答案、解析、分值、题型、考点、关键词、来源、pitfalls。
   - 原始题库字段参考 `references/data-authority.md`。
   - 若题库资产不足，按 `references/source-grounding.md` 读取教材、讲义、标准文件、taxonomy 的补充证据，不直接自由发挥。

3. **选择三档模式**
   - 有结构化 Rubric：`curated_rubric`。
   - 有标准答案/解析/关键词/分值：`projected_rubric`。
   - 资产不足但题干和答案可读：`open_skill`。

4. **生成或读取采分框架**
   - `curated_rubric`：只用给定采分点，不新增采分点给分。
   - `projected_rubric`：从标准答案、解析、关键词、pitfalls、考点投影临时采分点。
   - `open_skill`：识别题型和考点，给诊断，不冒充标准评分。

5. **切分用户答案**
   - 把用户答案拆成可引用原文证据句。
   - 口号化表达如“加强管理、严格检查、注意安全”不能替代程序性采分点。

6. **逐采分点匹配**
   - 每个 full / partial 都必须有用户原文证据。
   - 没有证据句，不给 full。
   - 用户只写大方向但缺关键词，通常为 partial 或 miss。
   - 计算题、网络计划、索赔费用等不能让 LLM 单独承担最终计算 authority；没有确定性算法或标准解时只给过程诊断。

7. **生成错因**
   - 错因必须绑定到具体采分点或具体答案句。
   - 错因分类见 `references/error-taxonomy.md`。

8. **改写得分答案**
   - 不写长篇讲义。
   - 把用户答案改成短句、分点、关键词前置的考试表达。
   - 保留题目问法：问“不妥之处”就先指出不妥，再写正确做法；问“理由”就补依据。

9. **推荐下一题**
   - 优先推荐现有题库中同考点/同错因的案例题。
   - 只有题库无合适题时，才建议生成变式题；生成题必须经过 validator，不能直接进入正式题库。

## 用户可见输出

按这个顺序输出，保持短而准：

1. **评分口径**：标准采分点评分 / 采分点推演阅卷 / 提分诊断。
2. **预计得分**：只在 `curated_rubric` 或 `projected_rubric` 足够时给；否则写“本次不硬估标准分”。
3. **命中的采分点**：列用户原文证据和为什么给分。
4. **漏分点**：列缺失含义，不只贴标准答案。
5. **最大问题**：一句话说清主要错因。
6. **得分表达改写**：给可直接背写的版本。
7. **下一题建议**：一个最小训练动作。

## 内部结构化结果

实现服务时应返回结构化结果，避免从 Markdown 反解析：

```json
{
  "grading_mode": "curated_rubric | projected_rubric | open_skill",
  "display_policy": "standard_score | score_band | diagnostic_only",
  "score": 8.0,
  "score_band": [7, 9],
  "max_score": 12,
  "rubric_results": [
    {
      "rubric_item_id": "r1",
      "criterion": "应组织专家论证",
      "status": "partial",
      "awarded_score": 0.5,
      "max_score": 1,
      "evidence_text": "施工单位未编制专项方案",
      "missing_meaning": "未写出超过一定规模危大工程需专家论证",
      "error_tags": ["E02", "E03"],
      "reason": "识别到专项方案问题，但未命中专家论证采分点"
    }
  ],
  "major_problems": ["把程序性采分点写成了管理口号"],
  "rewrite_answer": "该做法不妥。施工单位应编制专项施工方案，并按规定审核、审批；超过一定规模的危大工程还应组织专家论证。方案实施前应进行安全技术交底，实施过程中按方案施工并检查验收，发现问题及时整改闭环。",
  "next_task_signal": {
    "focus_concepts": ["危大工程专项施工方案"],
    "error_tags": ["E02", "E03"],
    "preferred_source": "questions_bank"
  },
  "internal_quality_signal": {
    "writeback_eligible": true,
    "needs_teacher_review": false
  }
}
```

`internal_quality_signal` 只给系统、评测和老师工作台使用，不直接展示给用户。

## 工具使用

- 优先用现有题库/active question/RAG；不要为了每次批改都联网。
- 当题目涉及可能变化的规范条文、时限、门槛、官方考试政策，且本地知识库没有可靠来源时，才使用 web search，并优先官方或权威来源。
- 联网结果只能补依据，不能替代题目 Rubric 或用户答案证据。

## 参考文件

- `references/data-authority.md`：现有本地源题库字段、case 题覆盖情况、Supabase 对账要求。
- `references/source-grounding.md`：2026 教材、讲义、标准文件、taxonomy 如何进入阅卷动作。
- `references/grading-protocol.md`：评分动作、输出 schema、边界场景。
- `references/error-taxonomy.md`：错因分类和写回规则。
