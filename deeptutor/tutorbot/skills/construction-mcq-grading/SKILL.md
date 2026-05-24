---
name: construction-mcq-grading
description: "建筑实务选择题阅卷 Skill。用于一建/二建建筑实务单选、多选、判断、组合选择题的答案判定、得分、错因诊断、选项排除、知识点回扣和下一题建议。用户说我选A、选这个对吗、批改选择题、单选多选判分、答案对不对时使用。"
metadata: {"nanobot":{"emoji":"✅"}}
always: false
---

# Construction MCQ Grading

这是建筑实务选择题阅卷 Skill，不是泛讲解 Skill。

核心定位：

- 确定性优先：有标准答案时先确定对错和得分，再解释。
- 讲错因，不堆知识：解释围绕用户为什么选错、哪个选项干扰、下次怎么判断。
- 不暴露置信度：用户看到“判定结果”和“改进动作”，内部质量信号只给系统。
- 复用现有题库：题目资产继续以 `questions_bank` / 当前 active question 为 authority。

## 何时使用

用户明确提交或追问选择题答案时使用：

- “我选 A，对吗”
- “这道多选我选 ACD，帮我判分”
- “批改这道选择题”
- “单选/多选/判断题答案对不对”
- “为什么 B 不对”
- “我为什么错”
- 当前 active question 是 `single_choice` / `multi_choice` / `multiple_choice` / `true_false`，且用户已作答

用户只是问“这道选择题选什么 / 讲一下这题”，但没有自己的作答时，可使用 `construction-exam-tutor` 的选择题讲解。

## 单一 Authority

| 业务事实 | Authority | 本 Skill 的职责 |
| --- | --- | --- |
| 标准答案 | `questions_bank.correct_answer` / active question `correct_answer` | 判定用户答案是否命中 |
| 题干与选项 | `questions_bank` / active question / 用户粘贴题目 | 保持题目锚点，解释选项 |
| 知识依据 | 题库解析、RAG、provenance | 解释错因和回扣考点 |
| 错因沉淀 | `LearnerStateService` | 输出可写回的 error signal |
| 下一题建议 | `assessment.teaching_policy` + 题库检索 | 输出 focus concept 和最小训练动作 |

## Forbidden Authority

- 不直接写 `LearnerStateService`、错题本、学习报告或长期学习画像。
- 不决定 TutorBot 路由；只有已经进入选择题阅卷场景时才执行。
- 不新建第二套题库、标准答案来源、评分规则或 RAG 模式。
- 不在没有 active question、用户粘贴题目或标准答案资产时硬判对错。
- 不把内部质量信号、置信度或写回资格直接展示给用户。

## Anti-Patterns

- 用户只说"讲一下这题"但未作答时，直接进入判分并暴露答案。
- 题库有标准答案时仍用自由推理重判正确选项。
- 多选评分规则不明时编造精确分值或考试扣分细则。
- 把"下一题建议"写成长期学习计划或直接写入 learner state。

## 阅卷流程

1. **绑定题目**
   - 优先使用当前 active question。
   - 如果用户粘贴完整题干和选项，使用用户题目。
   - 如果只有“我选 A”但没有 active question，先请用户补题目，不要硬判。

2. **归一化答案**
   - 单选：归一化为一个选项，如 `A`。
   - 多选：归一化为有序集合，如 `["A", "C", "D"]`。
   - 判断题：归一化为 `正确/错误` 或 `true/false`。
   - 支持中文表达：“我选甲”“第一个”“A和C”“ACD”。

3. **读取题库与知识资产**
   - 标准答案来自 `correct_answer`。
   - 选项解释优先使用 `option_reasoning`；如果线上表没有独立字段，从 `analysis` 中的“选项分析”恢复。
   - 易错点使用 `trap_type / pitfalls`。
   - 考点使用 `testing_focus / synthetic_queries / taxonomy.node_code`。
   - 精确规范、流程、数字题再补 RAG：线上优先查 `kb_chunks.metadata` 中的教材/讲义增强字段，以及 `standard_articles.logic_constraints`。
   - 资料利用细则见 `references/mcq-source-grounding.md`。

4. **判定与计分**
   - 有标准答案时，先给结果：正确 / 错误 / 部分正确。
   - 多选题按当前题库评分规则或考试规则处理；规则不明时不要编造精确分，只给命中/漏选/错选。
   - 标准答案缺失时，进入讲解诊断，不冒充正式判分。

5. **错因诊断**
   - 解释用户错在“知识点、概念混淆、选项陷阱、审题、关键词、常识化误判”中的哪一类。
   - 错因分类见 `references/mcq-error-taxonomy.md`。
   - 解释必须绑定到具体选项，不要泛泛说“基础不牢”。

6. **选项讲解**
   - 先讲用户所选项为什么对/错。
   - 再讲正确选项为什么成立。
   - 干扰项只讲必要部分，不展开成讲义。

7. **下一题建议**
   - 优先推荐同考点选择题或相邻案例小题。
   - 如果错因是“概念混淆”，建议下一题练相邻概念对比。
   - 如果错因是“审题错误”，建议下一题练问法识别。

## 用户可见输出

默认输出顺序：

1. **判定结果**：正确 / 错误 / 部分正确。
2. **得分**：有明确分值和规则时给；否则给“命中/漏选/错选”。
3. **你错在什么**：一句话钉住错因。
4. **选项拆解**：只讲和判断相关的选项。
5. **下次判断抓手**：一个可迁移规则。
6. **下一题建议**：一个最小训练动作。

不要默认输出长篇知识点讲义。

## 内部结构化结果

```json
{
  "grading_mode": "mcq_standard | mcq_explain_only",
  "question_type": "single_choice | multi_choice | true_false",
  "user_answer": ["A", "C"],
  "correct_answer": ["A", "D"],
  "is_correct": false,
  "partial": true,
  "score": 0.5,
  "max_score": 2,
  "option_results": [
    {
      "option": "C",
      "status": "wrong_selected",
      "reason": "该选项混淆了专项施工方案和施工组织设计",
      "error_tags": ["M03"]
    }
  ],
  "major_problem": "把相近程序概念混淆了",
  "next_task_signal": {
    "focus_concepts": ["专项施工方案", "施工组织设计"],
    "error_tags": ["M03"],
    "preferred_source": "questions_bank"
  },
  "internal_quality_signal": {
    "writeback_eligible": true
  }
}
```

`internal_quality_signal` 不直接展示给用户。

## 参考文件

- `references/mcq-grading-protocol.md`：选择题判分协议和边界场景。
- `references/mcq-error-taxonomy.md`：选择题错因分类和写回口径。
- `references/mcq-source-grounding.md`：选择题如何利用题库、教材、讲义、标准文件和 taxonomy。
