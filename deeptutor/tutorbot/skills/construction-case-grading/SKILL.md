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
- 开放世界不拒答：查不到 Rubric 不是回落“死板拒答”的理由——编译好的 Rubric 库是弹药不是门槛，资产不足时按开放世界口径抽采分点做提分诊断。
- 不新建第二套题库：题目资产继续以 `questions_bank` / 当前 active question 为 authority。
- 不向用户展示置信度：内部可以有 `quality_signal`，用户只看到评分口径和可执行改进。

## 何时使用

用户明确要求以下任一任务时使用：

- 案例题批改、判分、打分、估分
- “我这题能拿几分”“漏了哪些采分点”
- “为什么这句话不给分”“帮我把答案改成得分表达”
- “下一题该练什么”
- 主观题/简答题/背景资料题提交了自己的作答（含拍照/手写 OCR 文本）

普通“案例题讲解/答题思路”仍可用 `construction-exam-tutor` 的案例讲解；只有涉及用户答案阅卷时进入本 Skill。

## 单一 Authority

本 Skill 只做阅卷动作，不抢既有系统权责：

| 业务事实 | Authority | 本 Skill 的职责 |
| --- | --- | --- |
| 题目资产 | `questions_bank`、当前 active question、或用户粘贴题干 | 只读取并投影评分框架 |
| 采分框架 | `grading_key.scoring_points`（隐藏 authority）→ `questions_bank.grading_rubric` → 题库字段投影 | 按降级阶梯选档，不自拼 |
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
- 采分点和 required_terms 必须带教材/题库原文溯源；不可凭模型常识杜撰采分点、条文号或关键数字。
- 错因标签只能使用 canonical 错因注册表中的 E 系列代码，禁止发明新标签。

## Anti-Patterns

- 没有 Rubric 却把推演采分点说成人工校准标准答案。
- 只有一句“加强管理”就给 full，而没有绑定用户原文证据和采分点。
- 用户只是要案例题思路时，直接进入批改并给分。
- 把内部 `quality_signal` 或写回资格直接展示给用户。
- 凭模型常识或相似题经验拼采分点、编关键词，却不标注任何 source_fields 溯源。
- 资产不足时拒答“无法批改”——开放世界口径下仍要给提分诊断。
- 批量/逐采分点 LLM 裁决用长复合 ID 当回填键——截断错配会静默判 0；必须用短序号 idx 由程序映射，回填不全覆盖时整批降级。
- 一道综合案例多个子问串判：把子问 2 的采分点拿来扣子问 1 的分。
- 把口号化整改套话（“加强教育、严格检查、完善制度”）匹配成程序性采分点的关键词命中。

## 三档阅卷模式

先判断当前输入属于哪一档，再输出对应口径：

| 模式 | 条件 | 用户可见结果 |
| --- | --- | --- |
| `curated_rubric` | 有人工校准或结构化 Rubric（`grading_key.scoring_points` 或 `questions_bank.grading_rubric`） | 明确得分、逐采分点命中、漏点、得分改写 |
| `projected_rubric` | 有题干、标准答案、解析、关键词、分值等资产，但无人工 Rubric；这些资产必须来自当前 active question、`questions_bank`、exact case retrieval 或明确题库证据 | 预计分或得分区间、推演采分点、漏点、得分改写 |
| `open_skill` | 用户只粘贴题干/答案，或题目资产不足 | 提分诊断、可能漏点、得分表达改写、建议补充信息/下一题 |

不要把 `projected_rubric` 或 `open_skill` 说成“低置信度”。用户看到的是“本次按采分点推演阅卷”或“本次按提分诊断处理”。

Authority guard：不得仅凭模型常识、普通 RAG 知识、相似题经验或用户题面里的暗示自行拼出 `projected_rubric`。如果没有当前题卡、题库命中、标准答案/解析/分值或结构化采分点，本轮只能是 `open_skill`，预计得分必须写“本次不硬估标准分”。

### 降级阶梯与如实声明

每一档缺什么资产降到哪一档、降级后输出怎么声明，必须逐级如实，禁止悄悄越级：

1. `grading_key.scoring_points` 存在 → `curated_rubric`（trace `grading_source=grading_key`）。
2. 无 grading_key，`questions_bank.grading_rubric` 非空 → `curated_rubric`（trace `grading_source=questions_bank`）。
3. 无结构化 Rubric，但有题库标准答案/解析/关键词/分值 → `projected_rubric`；输出声明“本次按采分点推演阅卷”，并说明采分点来自哪些字段。
4. 连投影资产也不足 → `open_skill`（trace `grading_source=open_skill_fallback`）；声明“本次按提分诊断处理”“本次不硬估标准分”。开放档仍按开放世界口径抽采分点做诊断——这是 V1 的设计形态，不是失败状态。
5. 任何一档都不许拒答；任何一档都不许冒充上一档的口径或精度。

## 阅卷流程

1. **绑定题目**：优先当前 active question / `questions_bank` 行；用户粘贴完整题干则用用户题干；只有答案没题干时说明无法精确阅卷并请补题干，可先给表达诊断但不硬打分。
2. **读取可用资产**：题干、背景资料、问法、标准答案、解析、分值、题型、考点、关键词、来源、pitfalls。字段见 `references/data-authority.md`；题库资产不足时按 `references/source-grounding.md` 补教材、讲义、标准文件、taxonomy 证据，不自由发挥。
3. **选档**：按上面降级阶梯定 `curated_rubric` / `projected_rubric` / `open_skill`。
4. **生成或读取采分框架**：`curated_rubric` 只用给定采分点；`projected_rubric` 从标准答案、解析、关键词、pitfalls、考点投影临时采分点，每个采分点记录 `source_fields` 溯源；`open_skill` 识别题型和考点给诊断，不冒充标准评分。
5. **切分用户答案**：拆成可引用原文证据句；多子问案例先把答案归位到对应子问，再逐子问独立判。口号化表达不能替代程序性采分点。
6. **逐采分点匹配**：每个 full / partial 必须有用户原文证据；没有证据句不给 full；只写大方向缺关键词通常为 partial 或 miss。计算题、网络计划、索赔费用不能让 LLM 单独承担最终计算 authority，没有确定性算法或标准解时只给过程诊断。
7. **生成错因**：错因绑定到具体采分点或答案句，标签落在 canonical E 系列上，见 `references/error-taxonomy.md`。
8. **改写得分答案**：短句、分点、关键词前置；保留题目问法——问“不妥之处”先指出不妥再写正确做法，问“理由”补依据。
9. **推荐下一题**：优先题库同考点/同错因案例题；题库无合适题才建议生成变式题，生成题必须经过 validator，不直接进入正式题库。

空答、答非所问、跨章节综合案例、OCR 噪声答案等边界处理见 `references/grading-protocol.md`。

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

与消费侧 `CaseGradingResult`（`construction_grading/schema.py`）对齐，避免从 Markdown 反解析：

```json
{
  "question_id": "q_2021_case2_3",
  "grading_mode": "projected_rubric",
  "score_awarded": 1.0,
  "max_score": 4.0,
  "rubric_items": [
    {
      "criterion": "超过一定规模的危大工程应组织专家论证",
      "max_score": 2.0,
      "awarded_score": 0.0,
      "status": "miss",
      "keywords": ["专家论证"],
      "evidence_text": "",
      "source_fields": ["correct_answer", "analysis"]
    },
    {
      "criterion": "施工单位应编制专项施工方案",
      "max_score": 2.0,
      "awarded_score": 1.0,
      "status": "partial",
      "keywords": ["专项施工方案", "编制"],
      "evidence_text": "施工单位未编制专项方案",
      "source_fields": ["grading_keywords"]
    }
  ],
  "evidence_refs": [
    {"source": "questions_bank", "field": "analysis", "value": "..."}
  ],
  "error_events": [
    {
      "error_code": "E02",
      "severity": 0.8,
      "concept_tag": "2A312011",
      "evidence": "超过一定规模的危大工程应组织专家论证",
      "diagnosis": "漏写采分点：未写出超过一定规模危大工程需专家论证。"
    }
  ],
  "rewrite_answer": "该做法不妥。施工单位应编制专项施工方案，并按规定审核、审批；超过一定规模的危大工程还应组织专家论证。方案实施前应进行安全技术交底，实施过程中按方案施工并检查验收，发现问题及时整改闭环。",
  "next_training_signal": {
    "concept": "2A312011",
    "focus": "危大工程专项施工方案",
    "mode": "projected_rubric",
    "grading_source": "questions_bank",
    "case_grading_mode": "projected_rubric",
    "penalty_rules_applied": []
  }
}
```

- `rubric_items[].status` 取值 `full | partial | miss`；每个 full/partial 的 `evidence_text` 必须是用户原文。
- `rubric_items[].source_fields` 是采分点溯源（来自哪些题库/教材字段），`projected_rubric` 下不可为空。
- `error_events` 是 `GradingErrorEvent` 形状：`error_code / severity / concept_tag / evidence / diagnosis`。
- `next_training_signal.grading_source` 是单写 trace 标签：`grading_key | questions_bank | open_skill_fallback`。
- 内部质量信号（写回资格、是否需老师复核）只给系统、评测和老师工作台，不直接展示给用户。

## 工具使用

- 优先用现有题库/active question/RAG；不要为了每次批改都联网。
- 当题目涉及可能变化的规范条文、时限、门槛、官方考试政策，且本地知识库没有可靠来源时，才使用 web search，并优先官方或权威来源。
- 联网结果只能补依据，不能替代题目 Rubric 或用户答案证据。

## 参考文件

- `references/data-authority.md`：现有本地源题库字段、case 题覆盖情况、Supabase 对账要求、采分框架 authority 链。
- `references/source-grounding.md`：2026 教材、讲义、标准文件、taxonomy 如何进入阅卷动作；采分点教材溯源硬规则。
- `references/grading-protocol.md`：评分动作、输出 schema、批量/逐项裁决协议、边界与疑难场景。
- `references/error-taxonomy.md`：canonical E 系列错因分类和写回规则。
