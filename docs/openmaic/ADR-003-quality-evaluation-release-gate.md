# ADR-003: Quality Evaluation And Release Gate

状态：Accepted

日期：2026-04-24

---

## 1. 决策

P0 新增 `LessonQualityEvaluator`，作为课堂内容质量的唯一机器评测 authority。

它不替代人工教研审核，也不新增第二套发布状态机。它只负责把 `lesson_ir`、来源、考试蓝图、评分规则和生成 trace 转成一份可复现的 `quality_report`。

发布仍由既有状态机控制：

- `exam_classrooms.status`
- `review_items.status`

`quality_report` 是发布 gate 的主输入，`review_items` 是便于人工流转的 issue projection。

---

## 2. Root Cause

上一版计划已经收住了 transport、content truth、review lifecycle 的分裂，但仍有一个隐藏风险：

> 系统可以生成“结构完整”的课堂，却无法证明它讲得准、像老师、像考试、可复现、可发布。

如果只靠人工审核补救，系统会退化成“AI 初稿 + 人工重做”，无法支撑一键成课的商业价值。

因此 P0 需要质量工厂，而不是更多功能。

---

## 3. 一等业务事实

系统真正要维护的一等事实是：

> 用户一键生成后得到的是一份可播放、可批改、可导出、可追溯、可信的建筑实务课堂，而不是一份看起来完整的 JSON。

---

## 4. Authority 边界

唯一质量评测 writer：

- `LessonQualityEvaluator`

允许它写入：

- `lesson_ir.quality_report`
- 从 `quality_report` 派生出的 `review_items`
- `classroom_jobs.output.quality_summary`

禁止：

- `LessonQualityEvaluator` 直接修改教学内容
- `LessonQualityEvaluator` 直接发布课堂
- `review_items.status` 直接代表课堂发布状态
- exporter 绕过 `quality_report` 直接导出 draft

内容修复必须回到 `LessonIRService`。

---

## 5. 输入与输出

输入：

```json
{
  "lesson_ir": "...",
  "source_manifest": "...",
  "knowledge_coverage_report": "...",
  "exam_blueprint": "...",
  "rubric_policy": "...",
  "generation_trace": "..."
}
```

输出：

```json
{
  "score_total": 87,
  "dimensions": {
    "schema_validity": 100,
    "source_grounding": 92,
    "knowledge_coverage": 88,
    "exam_relevance": 88,
    "teaching_flow": 84,
    "mobile_playback_quality": 84,
    "interaction_quality": 78,
    "case_rubric_quality": 90,
    "export_readiness": 95
  },
  "blockers": [],
  "warnings": [
    {
      "scene_key": "s03",
      "type": "weak_citation",
      "message": "裂缝控制措施缺少明确教材来源"
    }
  ],
  "publishable": true
}
```

---

## 6. 质量维度

P0 至少覆盖四层质量：

- 结构质量：schema、key、timeline、renderer/export 可消费
- 来源质量：关键结论可追溯到 `source_manifest` 与 source chunk
- 知识覆盖质量：topic / quiz / case / rubric 是否命中现有 RAG evidence
- 教学质量：讲解顺序、白板、测验、案例题符合教学逻辑
- 考试质量：考点命中、评分点、扣分点、`weak_tags` 符合一建建筑实务
- 移动端播放质量：小程序首屏、scene 切换、hide/show、输入、降级策略可用

P0 不要求模型自动解决所有内容质量问题，但必须能稳定发现 blocker/high 风险。

---

## 7. Severity 与发布规则

`review_items.severity` 固定为：

- `blocker`
- `high`
- `medium`
- `low`
- `info`

发布 gate：

- 存在未解决 `blocker/high`：不能 `approved`
- 存在未解决 `medium`：允许 `approved`，但必须进入 release notes
- 存在未解决 `low/info`：不阻塞发布
- 重大事实错误：零容忍，必须是 `blocker`
- 版权 / 来源 blocker：零容忍，必须先按 ADR-004 处理
- 关键知识库覆盖缺口：必须标记为 `source_gap`，不得静默发布
- case 无 rubric evidence：必须是 `blocker`
- `questions_bank` provenance 丢失：必须是 `blocker`

分数规则：

- `score_total < 75`：只能保持 `draft`
- `75 <= score_total < 85`：进入 `review_required`
- `score_total >= 85` 且无未解决 `blocker/high`：允许人工批准为 `approved`

`resolved review item` 只表示问题已处理或风险被接受，不代表内容天然正确。

---

## 8. Gate 算法

```python
def compute_classroom_status(quality_report, review_items, human_decision):
    if quality_report.score_total < 75:
        return "draft"
    if quality_report.has_blocker:
        return "review_required"
    if has_open_blocker_or_high_review_item(review_items):
        return "review_required"
    if quality_report.source_policy_result == "failed":
        return "review_required"
    if quality_report.has_unresolved_source_gap:
        return "review_required"
    if human_decision == "approved" and quality_report.score_total >= 85:
        return "approved"
    return "review_required"
```

说明：

- `published` 仍是发布动作，不由质量评测直接写入。
- 导出正式文件必须来自 `approved` snapshot。

---

## 9. 非目标

本 ADR 不解决：

- 资料解析和版权分级字段，见 ADR-004
- 课堂问答 transport，见 ADR-002
- `lesson_ir` 写入和 snapshot，见 ADR-001
- 教研专家评分细则的全部题库建设

---

## 10. 必测项

- `test_quality_evaluator_writes_quality_report_only`
- `test_quality_score_below_75_keeps_draft`
- `test_quality_score_75_to_84_requires_review`
- `test_open_blocker_or_high_prevents_approval`
- `test_medium_issue_enters_release_notes`
- `test_resolved_review_item_does_not_mutate_lesson_ir`
- `test_export_blocked_until_approved_snapshot`
- `test_unresolved_source_gap_requires_review`
