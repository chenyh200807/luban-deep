# 建筑实务选择题错因分类

错因代码的单一 authority 是 canonical 错因注册表（`deeptutor/contracts/error_codes.py`，与 `docs/contracts/error_code_registry.md` 镜像）。本表与注册表对齐；**禁止发明注册表之外的新标签**——contract guard 会校验 emit site，未注册代码会被拒绝。

| Code | 错因（canonical label） | 能力维度 | 判定口径 |
| --- | --- | --- | --- |
| M01 | 知识点不熟 | code_application | 对考点本身不了解，只能猜选 |
| M02 | 关键词误读 | question_reading | 忽略“应/不应、正确/错误、最/宜/必须”等题眼 |
| M03 | 概念混淆 | code_application | 混淆相近概念、流程、责任主体或材料构造 |
| M04 | 选项陷阱 | question_reading | 被绝对化、偷换主体、扩大条件、时间顺序干扰 |
| M05 | 审题方向错误 | question_reading | 题目问“不妥/错误/不包括”，用户按正确项选 |
| M06 | 多选漏选 | question_reading | 多选题遗漏正确选项 |
| M07 | 多选错选 | question_reading | 多选题选入错误选项 |
| M08 | 规范数字混淆 | code_application | 规范数字、比例、时限、强度、间距混串 |
| M09 | 题干条件提取不完整 | question_reading | 没把题干给定场景和条件带入判断 |
| M10 | 用常识替代规范判断 | code_application | 用现场经验或生活常识替代考试规则 |

无法归因时使用注册表的 `unknown_error`（未归因错误，review_execution），不要硬套最接近的 M 码，也不要留空自创描述性标签。

## 标签选择指引

- 每条 error event 绑定**一个**最主要错因；同一选项有多重原因时选对纠正动作最有指导意义的那个。
- 多选同时漏选和错选：分别记 `M06`（每个漏选项一条）和 `M07`（每个错选项一条），不合并。
- `M06`/`M07` 是行为标签；若能进一步看出漏/错选背后的知识原因（概念混淆、数字串扰），在 `diagnosis` 文本里说明，但 `error_code` 仍记行为标签——`option_reasoning.error_type` 可作为 diagnosis 依据。
- `M02` vs `M05`：漏看个别题眼词是 M02；整体答题方向反了（求错选对）是 M05。
- `M01` vs `M03`：完全不知道该考点是 M01；知道但和相邻概念搞混是 M03。
- `M08` 仅用于数字/参数类混串；非数字的规范条文用错属于 M01 或 M10。

## error event 形状

每条错因写成 `GradingErrorEvent` 形状，缺一不可：

```json
{
  "error_code": "M07",
  "severity": 0.8,
  "concept_tag": "2A312011",
  "evidence": "C",
  "diagnosis": "错选 C：把专项施工方案审批混同为施工组织设计审批。"
}
```

- `evidence`：选项字母或用户答案原文片段，必须绑定具体选项，不只写“知识薄弱”。
- `severity` 参考：错选/方向错 0.8，漏选 0.7，题眼误读 0.6 左右；按实际影响微调。
- `concept_tag`：优先 `taxonomy.node_code`，其次 `testing_focus`。

## 写回口径

- 有标准答案（`grading_source=grading_key|questions_bank`）且有用户答案：可写入正式选择题错因 event。
- 开放裁决（`authority_source=open_world`）：只写轻量诊断 event，不更新 mastery；不要把一次开放裁决固化成“用户不会某考点”。
- 空答 / 答非所问 / 归一化失败：不写错因 event。
- 本 Skill 只产出 event 载荷，不直接写 `LearnerStateService`。
