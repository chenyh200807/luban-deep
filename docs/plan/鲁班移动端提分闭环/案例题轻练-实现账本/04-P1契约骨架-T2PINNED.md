# 04 · P-1 契约骨架 / schema 注册 / T2-PINNED 裁断

> 执行账本。设计见 [v1.3 计划](../2026-07-08-luban-case-question-light-practice-capability-plan.md) §2.5。分支 `feat/luban-case-light-practice-p-1`(worktree `deeptutor-p1-worktree`)。

## 交付(commit `a9f48b579`)
- `deeptutor/services/construction_grading/case_light_practice_contract.py`:
  - `LubanCaseScoringPoint` frozen dataclass(15 字段 = §2.5② 全字段)+ `PointType` 6 型(程序/条件/记录/合取子/列举项/计算步)+ 非平点结构 `ordering_group`/`conjunction_group`/`list_cap`。
  - claim ceiling 结构性 False:`OFFICIAL_SCORE_ALLOWED`/`CANONICAL_WRITE_ALLOWED`/`RUNTIME_INSTALL_ALLOWED`。构造期硬校验 `authority_source==official_answer`(通道①)、`answer_key_authority` 合法域(含 `exam_reference_answer`)。
  - `assert_qid_allowed`(§2.5① 代码级白名单门,fail-closed)、`validate_source_scoring_point_id`(RTG5 种子)、`score_conjunction_group`(找错∧改正,缺任一得 0)。
- `runtime_supply/case_light_practice/case_light_practice_whitelist.v0.json`:**空**占位,fail-closed 拒一切 qid,待双教研验收后填。
- schema:`luban_case_scoring_point.v1` 进 `contracts/schema_registry.yaml` **T2 runtime-canonical PINNED**;闭包 212→213,**CLOSED orphans=0**。
- `contracts/index.yaml`(根 + packaged mirror)`luban_grading_engine` domain 补 protected file + 3 required tests。
- 测试:`test_case_light_practice_schema.py` / `_whitelist_gate.py` / `_conjunction_scoring.py`。

## 验证证据(反自证,真跑)
3 测试 17 passed;`check_schema_registry.py --closure` = CLOSED(213/orphans=0);`test_schema_registry.py` 37 passed;`check_contract_guard.py --base origin/main --head HEAD` = passed,且 `[luban_grading_engine] protected=case_light_practice_contract.py | tests=(3 域测试)` protected 域**真触发**非 trivial skip。

## T2-PINNED 裁断理由(备审)
§1.5C 要求采分点 schema 有**字段级保护、不许 T2 挂名**。核 `check_schema_registry.py:455` 后确认:本仓 guard 的 drift/authority 检查**硬编码只对 `luban_grading_object.v1` 跑**——真正字段保护来自"frozen dataclass + 内省对账测试"(= P2#9 给 context_pack/evidence_bundle 上 T2 PINNED 的同一手法),不来自 guard。故:
- **不往 T1"唯一 grading 对象"加第二个 canonical**(守单一权威,不与 `luban_grading_object.v1` 竞争);
- **改用 T2 PINNED**(canonical_fields + `needs_field_canonicalization:false` + 内省对账)给字段保护。
既满足 §1.5C(是"独立 typed schema"非"T2 挂名"),又不僭越成第二判分权威——采分点只读视图,判分权威仍归 `rubric_grader_v1`。
