# ADR-001: Lesson IR Authority

状态：Accepted

日期：2026-04-22

---

## 1. 决策

`exam_classrooms.lesson_ir` 是 P0 唯一课程内容真相。

这意味着：

- `scene / action / question / citation / quality_report / export manifest` 都以内嵌于同一份 `Lesson IR` 的方式存在
- 任何播放器、审核器、导出器、重生成器都围绕同一份 `lesson_ir` 运作
- 其他表只能是 projection / index / operational log

---

## 2. 背景

v1.1 存在三个典型 root cause：

1. `Lesson IR` 被称为课程操作系统，但又把 `scene / action / question` 拆成独立 primary truth
2. 审核、导出、局部重生成没有唯一 writer
3. 任何模块都可能直接更新 JSONB，导致 authority 漂移

这会让系统反复落入：

- 双写
- 覆盖
- 投影反客为主
- 导出和审核基于不同版本内容

---

## 3. 决策原因

选择 `lesson_ir` 作为唯一真相，是因为它同时满足：

1. 对播放器是完整的
2. 对导出是完整的
3. 对审核是完整的
4. 对局部重生成可定位
5. 对 projection 可重建

相比之下，拆成多张 primary table 的问题是：

- 概念更多
- writer 更多
- 合并点更多
- revision 更难统一

不符合 `first principles + less is more`。

---

## 4. 唯一 writer

P0 只允许一个内容 writer：

- `LessonIRService`

所有 `lesson_ir` 写入必须经过 `LessonIRService`。

禁止：

- router 直接 update JSONB
- worker 直接 update JSONB
- exporter 直接修内容
- reviewer 直接修内容
- SQL 脚本直接 patch `lesson_ir`

建议接口：

```python
class LessonIRService:
    def get(classroom_id, *, tenant_id) -> LessonIR: ...
    def create_draft(classroom_id, lesson_ir, *, tenant_id, actor_id) -> LessonIRRevision: ...
    def patch_scene(
        classroom_id,
        scene_key,
        patch,
        *,
        expected_revision,
        tenant_id,
        actor_id,
        reason,
    ) -> LessonIRRevision: ...
    def replace_scene_from_job(
        classroom_id,
        scene_key,
        new_scene_ir,
        *,
        job_id,
        expected_revision,
        tenant_id,
    ) -> LessonIRRevision: ...
    def approve(classroom_id, *, expected_revision, reviewer_id) -> ReleaseSnapshot: ...
    def publish(classroom_id, *, release_version, publisher_id) -> PublishedClassroom: ...
```

---

## 5. Revision / CAS

必须引入 revision 或 etag。

规则：

- 每次内容变更都会提升 `lesson_ir_revision`
- scene 重生成必须带 `expected_revision`
- 若当前 revision 已变化，则返回：
  - `stale_revision`
  - 或 `rebase_required`

禁止：

- 无版本检查的全量覆盖
- job 结果覆盖人工审核后的内容

---

## 6. Approved snapshot / export snapshot

导出不能直接读取“当前 draft”。

导出必须绑定：

- `release_version`
- `lesson_ir_revision`
- `lesson_ir_hash`

导出记录建议包含：

- `classroom_id`
- `export_type`
- `release_version`
- `lesson_ir_revision`
- `lesson_ir_hash`
- `artifact_uri`

这样才能回答：

- 这个 PPT/HTML/ZIP 是哪一版课堂导出的？

---

## 7. Projection 规则

P0 暂不要求 projection 表。

如果后续增加 projection，只允许：

- `classroom_scene_index`
- `classroom_action_index`
- `classroom_question_index`

硬约束：

- 命名必须带 `_index` 或 `_projection`
- 来源唯一是 `lesson_ir`
- 可以丢，可以重建
- 不得反写 `lesson_ir`

---

## 8. 审核定位规则

`review_items` 不能依赖外部 `scene` 表主键。

审核定位只能基于逻辑 key：

- `scene_key`
- `question_key`
- `action_key`
- `block_key`

原因：

- 这些 key 才是 `lesson_ir` 内稳定锚点
- projection 表或 UI id 不具备 canonical 意义

---

## 9. 非目标

本 ADR 不解决：

- 课堂问答 transport
- capability 提升条件
- PBL / 仿真 schema 扩展

这些由其他 ADR 或 P1 方案处理。

---

## 10. 必测项

- `test_lesson_ir_service_is_only_writer`
- `test_patch_scene_requires_expected_revision`
- `test_scene_regeneration_cannot_overwrite_newer_revision`
- `test_export_uses_approved_snapshot_only`
- `test_projection_is_rebuildable_from_lesson_ir`
- `test_projection_mutation_does_not_change_lesson_ir`
