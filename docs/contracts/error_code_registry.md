# Error Code Registry

> **Single source of truth for `E0X` (case grading) and `M0X` (MCQ) error codes.**
>
> Python mirror: [`deeptutor/contracts/error_codes.py`](../../deeptutor/contracts/error_codes.py).
> The Python module is what runtime code references; this Markdown is the
> human-readable contract. Both must move together.

## Adding or modifying codes

1. Edit **`deeptutor/contracts/error_codes.py`** (`ERROR_CODE_REGISTRY`).
2. Edit **this file** to mirror.
3. Run `python scripts/check_contract_guard.py` — it cross-checks every emit
   site against `ERROR_CODE_REGISTRY`.
4. If a new `structured_rules.type` was introduced in the grading bank, also
   confirm its `ability_dimension` mapping with教研 before adding here.

A registered code MUST carry an `ability_dimension` in the canonical set
(`question_reading`, `code_application`, `calculation`, `expression`,
`transfer`, `review_execution`); otherwise the registry refuses to load.

## Authority order (recap)

```
grader (case_kernel / mcq) emits error_code
  → learning_evidence.error_events[*].error_code
    → learning_synthesis groups by (concept_id, error_code)
      → learning_report_read_model / learning_brain_read_model render labels
```

`learning_synthesis` falls back to `unknown_error` when the grader did not
attribute a code. That fallback is registered below.

## E series — case / essay grading

| code | label | ability_dimension | typical cause |
| --- | --- | --- | --- |
| E01 | 知识点缺失 | code_application | 学员根本没识别出本题该应用哪一个规范 / 知识点 |
| E02 | 采分点遗漏 | expression | 内容方向对，但漏写了关键得分点（最常见） |
| E03 | 关键词缺失 | expression | 表述不到位，关键名词未出现 |
| E04 | 口号化表达 | expression | 写成"加强管理 / 提高质量"等无具体指标的话 |
| E05 | 审题错误 | question_reading | 误读题干场景或限定条件 |
| E06 | 程序顺序错误 | transfer | 步骤次序与规范不符（如先审批后编制） |
| E07 | 概念混淆 | code_application | 把两个相邻规范/概念搞反 |
| E08 | 背景信息提取失败 | question_reading | 案例背景中关键条件没看到 |
| E09 | 计算错误 | calculation | 数值或公式算错 |
| E10 | 规范适用错误 | code_application | 用了错误条款或错误版本 |
| E11 | 迁移失败 | transfer | 单点知识点会，综合题不会迁移 |
| E12 | 表达冗余 | expression | 写了无关内容拖低有效得分密度 |

## M series — MCQ grading

| code | label | ability_dimension | typical cause |
| --- | --- | --- | --- |
| M01 | 知识点不熟 | code_application | 选项考查的基础知识没掌握 |
| M02 | 关键词误读 | question_reading | 题干中关键词被忽略或读偏 |
| M03 | 概念混淆 | code_application | 两个相似概念混在一起 |
| M04 | 选项陷阱 | question_reading | 中了高频干扰项 |
| M05 | 审题方向错误 | question_reading | 选了"错的说法是" / "正确的说法是" 反向题 |
| M06 | 多选漏选 | question_reading | 多选题没把全部应选项选完 |
| M07 | 多选错选 | question_reading | 多选题误选了干扰项 |
| M08 | 规范数字混淆 | code_application | 把不同条款数字串错（耐火极限 1.5h / 1.0h / 0.5h 等） |
| M09 | 题干条件提取不完整 | question_reading | 没有把题干所有限定条件都看到 |
| M10 | 用常识替代规范判断 | code_application | 凭直觉而非规范条文判断 |

## Fallback

| code | label | ability_dimension | usage |
| --- | --- | --- | --- |
| unknown_error | 未归因错误 | review_execution | 当 grader 返回的 `error_code` 为空时由 `learning_synthesis` / `learning_evidence` 兜底使用 |

## Cross-check policy

- `scripts/check_contract_guard.py` greps for emitted codes and validates them
  against `ERROR_CODE_REGISTRY` via `check_emitted_error_codes`.
- A new `error_code` introduced by a grader without first appearing here is a
  hard contract failure — the guard exits non-zero and CI blocks the PR.
- Local label maps in `learning_report_read_model._ERROR_LABELS` and
  `learning_brain_read_model._ERROR_LABELS` are tolerated for now (they
  pre-date this registry); they MUST be a strict subset of the registry and
  will be consolidated in a follow-up surgical refactor.
