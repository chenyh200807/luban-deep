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
- 不拒答：标准答案三路兜底全部落空时，转入 RAG-grounded 开放世界裁决，不发“缺少标准答案”拒答。
- 讲错因，不堆知识：解释围绕用户为什么选错、哪个选项干扰、下次怎么判断。
- 不暴露置信度：用户看到“判定结果”和“改进动作”，内部质量信号只给系统。
- 复用现有题库：题目资产继续以 `questions_bank` / 当前 active question 为 authority。

## 何时使用

用户明确提交或追问选择题答案时使用：

- “我选 A，对吗”
- “这道多选我选 ACD，帮我判分”
- “批改这道选择题”
- “单选/多选/判断题答案对不对”
- “为什么 B 不对”“我为什么错”
- 批量提交："q1 A，q3 C，q5 B"“第1题A 第2题BD”
- 当前 active question 是 `single_choice` / `multi_choice` / `multiple_choice` / `true_false`，且用户已作答

用户只是问“这道选择题选什么 / 讲一下这题”，但没有自己的作答时，可使用 `construction-exam-tutor` 的选择题讲解。

## 单一 Authority

| 业务事实 | Authority | 本 Skill 的职责 |
| --- | --- | --- |
| 标准答案的**值/内容** | `grading_key.correct_answer`（active_object 隐藏答案）→ `questions_bank.correct_answer` | 判定用户答案是否命中 |
| 选项**字母↔值**的映射 | **学员当前题面**（active question / 用户粘贴题目）——唯一权威 | 把正确的值映射回学员题面对应字母；按学员题面字母比对用户作答 |
| 题干与选项 | `questions_bank` / active question / 用户粘贴题目 | 保持题目锚点，解释选项 |

> **题面字母对齐（硬约束）**：题库 / grounding 的 `correct_answer` 字母和选项顺序是**题库内部坐标**，常与学员当前看到的题面不一致（同一值“5%”题库是 D、学员题面可能是 A）。判分流程必须：①用 `correct_answer` 定正确的**值**；②回到**学员当前题面的 Options** 找出值匹配的字母作为对用户的“正确答案”；③按学员所选字母在**学员题面**里对应的值判对错。grounding 里的题库字母/编号只能取“值”，**绝不可直接当作对用户的答案字母输出**——直接搬题库字母会把答对的判成答错。
| 知识依据 | 题库解析、RAG（`kb_chunks` / `standard_articles`）、provenance | 解释错因和回扣考点；开放世界裁决的唯一证据来源 |
| 错因沉淀 | `LearnerStateService` | 输出可写回的 error signal |
| 下一题建议 | `assessment.teaching_policy` + 题库检索 | 输出 focus concept 和最小训练动作 |

### 标准答案兜底链（不拒答硬约束）

判定 authority 按顺序兜底，每一档必须在输出和 trace 中如实声明，不许冒充上一档：

1. `grading_key.correct_answer`：active_object 注入的隐藏标准答案，最高 authority（trace `grading_source=grading_key`）。
2. `questions_bank.correct_answer`：题库精确命中（trace `grading_source=questions_bank`）。
3. 三路恢复全部落空 → **开放世界裁决**（trace `authority_source=open_world`）：基于 RAG 证据（教材 `kb_chunks`、`standard_articles`）裁决每个选项，明确告知用户“本次按教材依据裁决，非题库标准答案”。禁止拒答。
4. 无 authority 时确定性内核返回 `grading_source=llm_judge` 的占位结果——`is_correct=false`、`score=0` 是占位值不是判定，进入开放裁决前必须清空（runtime 中间态把 `is_correct` 置空、去掉 score 和占位 grading result；最终结果里 `is_correct` 必须是开放裁决的真实结论），禁止把占位值当“答错”输出给用户。

### 编译资产边界

MCQ 判分内核（`construction_grading/mcq.py`）**不消费 case 编译采分点库**。MCQ 的 authority 链就是上面的 `grading_key → questions_bank → open_world` 三级，不经过 `v_case_rubric_scored`、`rubric_provenance` 三级链、`list_spec` / `calculation_spec` 等案例题编译判定字段——那些属于 `construction-case-grading` 的编译链路。禁止把 case 采分点库错用到选择题（例如用案例采分点给选项“踩点给分”）。未来 MCQ 编译资产（如 `option_reasoning` 编译回填）接入时另行扩展本节，当前不得假装存在。

## Forbidden Authority

- 不直接写 `LearnerStateService`、错题本、学习报告或长期学习画像。
- 不决定 TutorBot 路由；只有已经进入选择题阅卷场景时才执行。
- 不新建第二套题库、标准答案来源、评分规则或 RAG 模式。
- 不在没有 active question、用户粘贴题目时硬判对错；但有题干无标准答案时必须走开放裁决，不许拒答。
- 不把内部质量信号、置信度或写回资格直接展示给用户。
- 错因标签只能使用 canonical 错因注册表中的 M 系列代码（见 `references/mcq-error-taxonomy.md`），禁止发明新标签。

## Anti-Patterns

- 用户只说“讲一下这题”但未作答时，直接进入判分并暴露答案。
- 题库有标准答案时仍用自由推理重判正确选项。
- 标准答案缺失时回复“缺少标准答案，无法判分”——必须走 RAG-grounded 开放裁决。
- 把 `grading_source=llm_judge` 的占位 `is_correct=false` 当真实判定，告诉用户“你答错了”。
- 多选评分规则不明时编造精确分值或考试扣分细则。
- 批量判分时让 LLM 回填长复合题目 ID（如 `quiz_batch::ch3::q17_v2`）——长 ID 会被截断错配导致静默判 0；必须用短序号 `idx(1..n)` 让 LLM 回填，由程序映射回真实 ID，且回填不覆盖全部条目时整批降级重裁，不许把缺失条目默认判 0。
- 把“下一题建议”写成长期学习计划或直接写入 learner state。
- 开放裁决时不引用任何教材/规范证据就直接断言正确选项。

## 阅卷流程

1. **绑定题目**
   - 优先使用当前 active question；用户粘贴完整题干和选项时用用户题目。
   - 只有“我选 A”但没有 active question：先请用户补题目，不要硬判。

2. **归一化答案**
   - 单选归一为单个选项；多选归一为有序集合 `["A","C","D"]`；判断题归一为 `true/false`。
   - 支持中文与噪声表达：“我选甲”“第一个”“A和C”"ACD""(A)""A、C、D"，以及拍照/手写 OCR 噪声。细则见 `references/mcq-grading-protocol.md`。
   - 归一化失败或存在歧义（如"AC D"可能是 ACD 或 AC+D）时先复述确认，不要猜。

3. **读取题库与知识资产**
   - 标准答案按兜底链取；选项解释优先 `option_reasoning`，缺失时从 `analysis` 的“选项分析”恢复。
   - 易错点用 `trap_type / pitfalls`；考点用 `testing_focus / synthetic_queries / taxonomy.node_code`。
   - 精确规范、流程、数字题再补 RAG：`kb_chunks.metadata` 增强字段 + `standard_articles.logic_constraints`。
   - 资料利用细则见 `references/mcq-source-grounding.md`。

4. **判定与计分**
   - **先对齐题面字母**：标准答案先取“正确的值”，再回到学员当前题面 Options 找出值匹配的字母（见上“题面字母对齐”硬约束）；不要直接把题库 `correct_answer` 字母当作对用户的答案。
   - 有标准答案：先给结果（正确 / 错误 / 部分正确），多选必须区分漏选和错选。
   - 多选部分得分按题库评分规则或考试规则处理；规则不明时只给命中/漏选/错选，不编造精确分。
   - 标准答案缺失：开放世界裁决，输出口径“按教材依据裁决”，不冒充题库标准答案。
   - 组合选项题（①②③、组合为选项）、争议题、空答、答非所问等边界处理见 `references/mcq-grading-protocol.md`。

5. **错因诊断**
   - 错因落在 canonical M 系列标签上（`references/mcq-error-taxonomy.md`），必须绑定到具体选项，不要泛泛说“基础不牢”。
   - 多选同时存在漏选和错选时分别记 `M06` / `M07`。

6. **选项讲解**
   - 先讲用户所选项为什么对/错，再讲正确选项为什么成立；干扰项只讲必要部分。

7. **下一题建议**
   - 优先同考点选择题或相邻案例小题；“概念混淆”练相邻概念对比；“审题错误”练问法识别。

## 用户可见输出

默认输出顺序：

1. **判定结果**：正确 / 错误 / 部分正确；开放裁决时先声明评分口径。
2. **得分**：有明确分值和规则时给；否则给“命中/漏选/错选”。
3. **你错在什么**：一句话钉住错因。
4. **选项拆解**：只讲和判断相关的选项。
5. **下次判断抓手**：一个可迁移规则。
6. **下一题建议**：一个最小训练动作。

不要默认输出长篇知识点讲义。开放裁决时话术用“本次按教材依据裁决”，不说“低置信度”“AI 不确定”。

## 内部结构化结果

与消费侧 `MCQGradingResult`（`construction_grading/schema.py`）对齐：

```json
{
  "question_id": "q_2023_az_017",
  "question_type": "multi_choice",
  "user_answer": "AC",
  "correct_answer": "AD",
  "selected_options": ["A", "C"],
  "missed_options": ["D"],
  "extra_options": ["C"],
  "is_correct": false,
  "score_awarded": 0.5,
  "max_score": 2.0,
  "evidence_refs": [
    {"source": "questions_bank", "field": "correct_answer", "value": "AD"}
  ],
  "error_events": [
    {
      "error_code": "M07",
      "severity": 0.8,
      "concept_tag": "2A312011",
      "evidence": "C",
      "diagnosis": "错选 C：把专项施工方案审批混同为施工组织设计审批。"
    },
    {
      "error_code": "M06",
      "severity": 0.7,
      "concept_tag": "2A312011",
      "evidence": "D",
      "diagnosis": "漏选 D，该选项属于标准答案。"
    }
  ],
  "next_training_signal": {
    "concept": "2A312011",
    "focus": "危大工程专项施工方案",
    "option_count": 4,
    "grading_source": "questions_bank"
  }
}
```

- `error_events` 的每条都是 `GradingErrorEvent` 形状：`error_code / severity / concept_tag / evidence / diagnosis`，`evidence` 放选项字母或答案原文片段。
- `next_training_signal.grading_source` 是单写 trace 标签：`grading_key | questions_bank | llm_judge`；开放裁决整体由 `authority_source=open_world` 标注。
- 内部结果不直接展示给用户。

## 参考文件

- `references/mcq-grading-protocol.md`：选择题判分协议、多选部分得分语义、批量判分、组合选项题、争议题、空答/答非所问、OCR 噪声、开放裁决协议。
- `references/mcq-error-taxonomy.md`：选择题 canonical 错因标签（M 系列）和写回口径。
- `references/mcq-source-grounding.md`：选择题如何利用题库、教材、讲义、标准文件和 taxonomy，以及开放裁决证据链。
