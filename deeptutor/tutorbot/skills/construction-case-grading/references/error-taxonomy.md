# 建筑实务案例题错因分类

错因代码的单一 authority 是 canonical 错因注册表（`deeptutor/contracts/error_codes.py`，与 `docs/contracts/error_code_registry.md` 镜像）。本表与注册表对齐；**禁止发明注册表之外的新标签**——contract guard 会校验 emit site。错因必须绑定到具体答案句、具体采分点或具体缺失含义，不要只写“安全管理薄弱”这种泛结论。

| Code | 错因 | 能力维度 | 判定口径 |
| --- | --- | --- | --- |
| E01 | 知识点缺失 | code_application | 完全不知道该考点或写成无关内容 |
| E02 | 采分点遗漏 | expression | 知道大方向，但漏掉标准答案中的关键环节 |
| E03 | 关键词缺失 | expression | 意思接近，但未写出阅卷能识别的关键词 |
| E04 | 口号化表达 | expression | 用“加强管理、严格检查、注意安全”等空话代替可得分程序 |
| E05 | 审题错误 | question_reading | 问“不妥之处”却写成泛泛措施，或没有按问点作答 |
| E06 | 程序顺序错误 | transfer | 审核、审批、论证、交底、实施、验收等顺序混乱 |
| E07 | 概念混淆 | code_application | 专项施工方案/施工组织设计/技术交底等概念混用 |
| E08 | 背景信息提取失败 | question_reading | 题干里给出隐含条件，但答案没有识别 |
| E09 | 计算错误 | calculation | 进度、费用、索赔、流水、时差等计算错误 |
| E10 | 规范适用错误 | code_application | 用了错误规范、旧规则或不适用的判断标准 |
| E11 | 迁移失败 | transfer | 原题会，换工程背景后不能写出同一采分链条 |
| E12 | 表达冗余 | expression | 写了很多但没有得分关键词，影响答题效率 |

无法归因时使用注册表的 `unknown_error`（未归因错误，review_execution），不要硬套最接近的 E 码。

V1 编译链（`rubric_grader_v1`）的 mistake_type 与 E 码的固定映射（代码 `_registered_learning_error_code`，不要另行发挥）：`wrong_content` → E07；`omitted` / `near_synonym_not_exact` / `list_incomplete` → E02。

## 标签选择指引

- 每条 error event 绑定一个最主要错因；同一采分点同时缺关键词又顺序乱时，选对纠正动作最有指导意义的那个。
- `E02` vs `E03`：整个环节没写是 E02；环节写了但措辞不可得分是 E03。
- `E04` 只在口号替代了可得分程序时记；用户在程序之外多写口号属于 E12。
- `E05` 优先级最高：方向答错时先记 E05，不再逐点叠加 E02。
- `E09` 必须有具体的计算过程证据，不能因为最终数字错就直接记。
- `E11` 用于变式/换背景练习场景，需要有“原题已会”的依据（如 learner 历史或用户自述）。

## error event 形状

每条错因写成 `GradingErrorEvent` 形状（消费侧 `learning_evidence` / 学习大脑按此读取）：

```json
{
  "error_code": "E02",
  "severity": 0.8,
  "concept_tag": "2A312011",
  "evidence": "超过一定规模的危大工程应组织专家论证",
  "diagnosis": "漏写采分点：未写出超过一定规模危大工程需专家论证。"
}
```

- `evidence`：用户答案原文片段（partial/wrong 时），或漏掉的采分点 criterion（miss 时）。注意：是 `evidence` 键，不是 `evidence_span`；没有 `mistake_type` 键。
- `severity` 参考：漏整个采分点 0.8，关键词缺失/口号化 0.6，表达冗余 0.4；按失分占比微调。
- `concept_tag`：优先 `taxonomy.node_code`。

## 写回规则

- `curated_rubric`：可写入正式错因 event。
- `projected_rubric`：采分点和错因可写入候选 event，聚合前需要质量门控。
- `open_skill`：只写轻量诊断 event；如果题干/答案不完整，不更新长期 mastery。
- 空答 / 答非所问 / OCR 无法辨认：不写正式错因 event。

写回事件至少包含：

- `question_id` 或 `source_ref`
- `grading_mode`
- `concept_tags`
- `error_tags`
- `lost_score` 或 `severity`
- `evidence_text` 或 `missing_meaning`
- `next_task_signal`

不要把一次低质量开放诊断直接固化成“用户不会某考点”。
