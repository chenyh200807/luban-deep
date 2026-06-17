# 鲁班解释型动效模板引擎 v0 · schema spine 收口复审

- **日期**: 2026-06-17
- **范围**: F16 / N01 / D01 三类模板的 schema spine 收口（只读复审 + 最小登记 + 轻量校验器），**不做 renderer、不做 UI、不做第四张卡**。
- **结论**: **schema spine 成立**。三类卡共用同一条 spine + 互斥 body，由 `validate_schema_drafts.py` 守门，3/3 OK。命名有漂移（已登记兼容，待收敛），未发现破坏单一权威的硬冲突。

## 1. 当前真实资产状态

| 卡 | 文件 | 状态 | 类型 | 定位 |
|---|---|---|---|---|
| F16 | `F16_qigu.json` / `render_card.py` / `F16_qigu.rendered.html` | **rendered proof** | `process_step_reveal`（从 `scenario.diagram_type` 推断） | 体验样板 |
| N01 | `N01_network_keypath.json` / `render_network_card.py` / `.rendered.html` | **rendered proof** | `network_plan_keypath` | 硬能力样板 |
| D01 | `D01_answer_point_diagnosis.schema_draft.json` | **schema draft（无 renderer）** | `answer_point_diagnosis_draft` | 判分解释 schema 草案 |

- rendered proof：F16、N01。
- schema draft：D01（本轮把其 `template_type` 由 `answer_point_diagnosis` 收口为 `answer_point_diagnosis_draft`，杜绝被当 production）。

## 2. 共同 schema spine（三类共用）

`schema_version`（固定 `luban_diagram_microlesson.v1`，不新增第二个）、`card_id`、`template_type`、`title`、`student_goal`、`authority`（含 `student_boundary`）、`scoring_points[]`（network 类无）、`common_errors[]`/`error_reveals[]`、`practice`、`rendering_contract.student_safe_fields`（D01 已落地，其余待补）。

**命名漂移（已登记兼容，本轮不强改）**：
- id：F16/D01 用 `topic_id`，N01 用 `card_id`。
- 目标：F16/D01 用 `learning_goal`，N01 用 `student_goal`。
- 候选标记：F16 用 `judging_artifact_id`+混合，N01 用 `authority.status`，D01 用 `provenance.kind`。
- 错因：F16/D01 用 `common_errors`，N01 用 `error_reveals`。

收敛方向：新卡统一 `card_id`/`student_goal`/`authority.status`；旧卡 F16 暂保留别名由校验器兼容（避免大改已 proof 的 F16）。

## 3. 三类 template body 差异（互斥）

| template_type | 主 body |
|---|---|
| `process_step_reveal` / `layer_section_reveal` | `steps[]` |
| `network_plan_keypath` | `question_data.{activities, dependencies, expected}` |
| `answer_point_diagnosis_draft` | `question` + `model_answer_skeleton` + `student_sample` + `diagnosis[]` |

`steps[]` / `question_data.activities` / `diagnosis[]` 三者只能其一为主 body；`scoring_points`/`common_errors`/`practice` 是 spine 可共用。

## 4. 第二权威风险审查

| 风险点 | 裁决 | 缓解 |
|---|---|---|
| `scoring_points` vs `diagnosis` | **无冲突**（D01 `diagnosis[].scoring_point_id` 是**引用**，`status` 是 JSON 内**已编译候选 verdict**，非前端再判） | 校验器要求 status∈{hit,partial,miss} 且引用命中；principles 规定 renderer 不重判 |
| `expected.critical_path` vs renderer/`compute_cpm` | **无冲突**（前端只读 `expected`；`compute_cpm` 是 build 期校验/派生器） | SCHEMA/principles 明确 compute_cpm 非 scoring authority |
| `source_ref` vs `student_boundary` | **不同层不冲突**（内部 vs 学生面） | `rendering_contract` 显式分 student_safe / internal_only |
| `steps` vs `diagnosis` | **互斥已守门** | 校验器 body 互斥检查 |
| candidate vs signed | **最大风险点**：D01 `scoring_points[].source_ref`=`diagram_microlesson_compile::...` 形似签发实为候选 | 校验器强制 candidate→`official_score_allowed` 不得 true；provenance/authority 标 candidate；量产闸要求签发后才升格 |
| renderer display vs authority truth | 受控 | "renderer 不判分/不改 authority/不产知识" 写入 principles + SCHEMA |

**结论**：无破坏单一权威的硬冲突；唯一需长期盯防的是"候选 source_ref 形似签发"——已用校验器 + 量产闸 + 文档三重约束。

## 5. 正式登记 vs draft 保留

- **正式登记进 SCHEMA.md**：template_type 注册表（process_step_reveal / layer_section_reveal / network_plan_keypath / **answer_point_diagnosis_draft**）、F16 兼容推断规则、共同 spine、互斥 body、学生端安全规则、authority 规则。
- **仍停留 draft**：D01 `answer_point_diagnosis_draft` —— 只登记为 draft，**不是 production 模板**，无 renderer；`decision_tree_judgment` 仍是候选（未动）。

## 6. `validate_schema_drafts.py` 规则与输出

规则（纯 JSON 结构、无外部依赖、不判分、不扫 HTML）：schema_version 固定；template_type（F16 可推断并报 inferred）；body 互斥；N01 必备 activities/dependencies/expected.{critical_path,project_duration,float} 且 candidate 不得 official_score；D01 必备 question/model_answer_skeleton/student_sample/diagnosis 且 status∈{hit,partial,miss}、scoring_point_id 命中、必须 candidate/draft、不得 production_ready；student safety：student_boundary 必存、student_safe_fields 若有须含展示字段且不含内部 id。

实测输出：
```
F16_qigu.json: OK template_type=process_step_reveal (inferred) body=steps authority=candidate_or_signed_mixed student_safe=boundary_only
N01_network_keypath.json: OK template_type=network_plan_keypath body=network authority=candidate_teaching_prototype student_safe=boundary_only
D01_answer_point_diagnosis.schema_draft.json: OK template_type=answer_point_diagnosis_draft body=diagnosis authority=candidate_teaching_prototype student_safe=contract+boundary
汇总: 3/3 OK
```

## 7. 对 renderer 体系的裁决

- **现在不抽公共 renderer**。
- F16（`render_card.py`）/ N01（`render_network_card.py`）两个窄 renderer **暂时允许并列**，不互相重构。
- 等**第三个 rendered proof** 出现、或 F16+N01 **学员验证通过**后，再考虑抽公共层。过早抽象＝沉没成本。

## 8. 下一步建议

1. **F16 + N01 先做 3-5 人学员验证**（复用 `F16_qigu_product_validation_plan.md` 流程，网络计划换题）。
2. **N01 绑定真题 `source_ref`**（替换 `candidate_teaching_example`），并把 `compute_cpm` 抽成独立编译器做入库前自洽校验。
3. **D01 暂缓 renderer**，先补：已签发 `source_ref` + 真实学生答卷样本 + 人审/gold 校准，再谈生产判分解释。
4. 命名收敛（card_id/student_goal/authority.status）随下一张新卡顺手统一，不为收敛单独大改 F16。

## 9. 红线

- 不量产（三条量产闸未过不铺）。
- 不生产接入（不接小程序/评分/learner state/TTS/部署）。
- 不把 draft（D01）当 authority；不把 `candidate_teaching_prototype` 当签发。
- 不让 renderer 判分；`compute_cpm` 只是 build 期校验器。
- 不让生成式视频进入知识核心表达层。
- 学生端不露 `source_ref` / `P 编号` / `schema` / `renderer` / `candidate` 等内部词。
