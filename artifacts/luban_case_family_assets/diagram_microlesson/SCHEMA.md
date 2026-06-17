# 图解微课卡 Schema（`luban_diagram_microlesson.v1`）

- **日期**: 2026-06-17
- **定位**: 把“母题图解卡”抽成 **窄 schema + 确定性 SVG renderer**。每个考点填一份 JSON, `render_card.py` 输出一张小程序 WebView 可承载的静态 HTML 卡。
- **当前第一张正式卡**: `F16_qigu.json` -> `F16_qigu.rendered.html`
- **视觉基线**: `../F16/F16_roof_waterproofing_micro_lesson_card_v1.html` 只作为 v0 visual baseline, 不作为知识或评分 authority。

## 单一权威边界

本 schema 不是第二套知识库、第二套评分器或第二套母题引擎。

它只渲染已经由上游提供的事实:

- 母题包 / 教研编译内容
- 已签发或候选判分工件
- `ERROR_CODE_REGISTRY` / canonical taxonomy
- source_ref / source_refs 指向的教材、真题、规范或教研依据

渲染器只负责:

- step reveal
- 确定性 SVG 展示
- 错因节点跳转
- 采分表达展示
- 复测题交互反馈

渲染器不得:

- 生成新采分点
- 修改分值
- 推断官方答案
- 把教学拆解点冒充已签发得分点
- 用 LLM 或文生图决定构造正确性

## 模板类型 `template_type`

同一个 `luban_diagram_microlesson.v1` schema 下登记**多种解释卡模板**，靠 `template_type` 分派到对应窄 renderer，**不另起平行系统、不抽通用大框架**。

已登记：

| template_type | 卡 | 状态 | renderer | 说明 |
|---|---|---|---|---|
| `process_step_reveal` | F16 起鼓割补 | rendered proof | `render_card.py` | 施工流程逐步揭示 + 8 步 + 采分点驱动（体验样板） |
| `layer_section_reveal` | （F16 剖面雏形） | 候选 | `render_card.py` | 剖面/构造节点分层（暂与 process 同 renderer） |
| `network_plan_keypath` | N01 网络计划关键线路 | rendered proof | `render_network_card.py` | 数据驱动自动成图：activities/dependencies → SVG 网络图，关键线路高亮（硬能力样板） |
| `answer_point_diagnosis_draft` | D01 采分点诊断 | **schema draft（无 renderer）** | — | 判分解释草案：命中/部分/漏点逐点判读（仅验证字段通用性，不是 production 模板） |

**F16 兼容规则**：F16 当前 JSON **未显式写 `template_type`**（不强行大改）。校验器与 renderer 从 `scenario.diagram_type` 推断：`roof_section_step_reveal → process_step_reveal`（含剖面表达，可视为 `layer_section_reveal` 的超集）。新卡一律显式写 `template_type`。

约束：

- 一个 `template_type` 对应一个**窄确定性 renderer**；renderer 只渲染，不做知识判断、不判分、不生产新知识。
- 新增 template_type 必须先在本文件登记字段，再写 JSON，再由 renderer 消费。
- 不为了支持多模板把已有 renderer 重构成复杂框架；模板间并列，不互相耦合。
- `answer_point_diagnosis_draft` 是 **draft**：只允许 schema 草案，**不得**做 production renderer、不得当签发 authority、不得 official_score。

## 共同 schema spine（三类模板共用）

所有解释卡（process/layer/network/diagnosis）共用同一条 spine，靠 `template_type` 选 body：

| spine 字段 | 说明 | 兼容别名（当前漂移，待收敛，不强改） |
|---|---|---|
| `schema_version` | 固定 `luban_diagram_microlesson.v1`，**不新增第二个** | — |
| `card_id` | 卡稳定 id | 旧卡用 `topic_id`（F16/D01）；校验器两者皆认 |
| `template_type` | 渲染模板分派键 | F16 缺失→从 `scenario.diagram_type` 推断 |
| `title` | 卡标题 | — |
| `student_goal` | 面向学生的学习目标（口语） | 旧卡用 `learning_goal`（F16/D01） |
| `authority` | 判分依据边界（含 `student_boundary`；候选标 `status`/`provenance.kind`） | F16 用 `judging_artifact_id`+混合，N01 用 `authority.status`，D01 用 `provenance.kind` |
| `scoring_points[]` | 候选/已签发采分点（network 类无此字段） | — |
| `common_errors[]` / `error_reveals[]` | 错因（display + 跳转/纠正） | 命名按模板：F16/D01 用 `common_errors`，N01 用 `error_reveals` |
| `practice` | 复测题（训练反馈，非正式考试） | — |
| `rendering_contract.student_safe_fields` | 学生端渲染白名单（D01 已落地，其余卡待补） | 缺省时退化为"只读 `authority.student_boundary` + 各模板已知展示字段" |

收敛方向（**本轮不强改**，只登记）：新卡统一用 `card_id` / `student_goal` / `authority.status`；旧卡 F16 暂保留 `topic_id`/`learning_goal`，由校验器兼容。

### 已登记待收敛 drift（v0 复审 + 多专家审计追加，随下一张新卡顺手统一，不为收敛单独大改 F16）

| drift | 现状 | 权威应是 | 收敛动作 |
|---|---|---|---|
| `max_score` 多写 | F16 `exam_binding.max_score` 在每个 `used_by_steps` 步重抄一份 + `scoring_points.max_score` 一份（P10 共 4 处镜像） | `scoring_points[].max_score` | `exam_binding` 只持 `score_point_id` 指针，分值由 renderer 经 id 解析；改分只动一处 |
| 两个 `kind` 双轴 | `exam_binding.kind ∈ {signed_candidate, teaching_step}`（绑定类型）与 `authority.status`/`provenance.kind`（成熟度）都含 `signed_candidate`，语义轴不同却同词 | 成熟度唯一在 `authority.status`/`provenance.kind` | `exam_binding.kind` 收敛为纯绑定类型 `{scored, teaching}`，成熟度词从该 enum 移除 |
| `correction_hint` 承载位 | F16 在 `narration.error_reveals[]`，D01 在 `common_errors[]` | `common_errors[]`（错因固有属性） | narration 若需播报则引用，不重存 |
| `practice` 正确答案结构 | F16/D01 用 `options[].is_correct`（每项布尔），N01 用 `practice.answer`（单一正确 id） | 单一正确 id（`answer`，泄漏面更小） | 新卡统一 `answer`；F16 暂保留由 renderer 兼容 |
| review 锚点目标空间 | F16/N01 `review_step_id` 指 step/explanation_step，D01（diagnosis body 无 step）无定义 | 统一 `review_anchor`，各 body 指各自主 body id | 待 D01 进 renderer 时定义 |

> 这些均为 drift，不是硬冲突：读取侧已由 `validate_schema_drafts.py` 的 `authority_status()` 等单一 resolver 兼容收口；登记是为防"知道但没记"，量产前随新卡统一。

## 互斥 body（每张卡只能有一个主 body）

| template_type | 主 body 字段 |
|---|---|
| `process_step_reveal` / `layer_section_reveal` | `steps[]` |
| `network_plan_keypath` | `question_data.{activities, dependencies, expected}` |
| `answer_point_diagnosis_draft` | `question` + `model_answer_skeleton` + `student_sample` + `diagnosis[]` |

- `steps[]`、`question_data.activities`、`diagnosis[]` **三者只能其一**作为主 body，不得混用。
- `scoring_points` / `common_errors` / `practice` 是 spine，可被多种 body 共用（`diagnosis[].scoring_point_id` 引用 `scoring_points[].id`，是引用不是再判分）。

## 学生端安全规则（`rendering_contract.student_safe_fields`）

- `student_safe_fields` 是**渲染白名单**：renderer 只允许把白名单内字段渲染到学生 UI。
- raw `source_ref` / `scoring_point_id` / `artifact id` / `error_code` / schema 内部结构**一律不得进入学生 UI**（D01 用 `internal_only_fields` 显式列出）。
- renderer 必须用 `display_label` / `student_boundary` / `student_comment` 等面向学生的字段，**不得把内部 id 当学生文案**。
- 学生 UI 禁止出现 `source_ref` / `P 编号` / `schema` / `renderer` / `candidate` 等内部词。

## authority 规则

- `signed_candidate`：来自已签发/候选判分工件，可用于**候选采分点展示**（如 F16 P10/P11）。
- `candidate_teaching_prototype`：仅教学验证用（N01/D01），**不得**冒充签发 authority。
- `official_score_allowed=false`，除非上游签发；候选/草案卡出现 `official_score_allowed=true` 即校验失败。
- renderer **不得**根据 `diagnosis` 或 `critical_path` **重新判分**，只能展示已编译 verdict。
- `compute_cpm()` 只是 **build-time 自洽校验器/派生器**（校验 N01 的 `expected` 与确定性 CPM 一致并派生 ES/EF 供展示），**不是 official scoring authority**；日后可抽成独立网络计划编译器，仍不得让前端 renderer 现场判断。

## network_plan_keypath 字段

```jsonc
{
  "schema_version": "luban_diagram_microlesson.v1",
  "card_id": "N01_network_keypath",
  "template_type": "network_plan_keypath",
  "title": "网络计划关键线路判断",
  "student_goal": "面向学生的学习目标(口语)",
  "authority": {
    "status": "candidate_teaching_prototype",
    "student_boundary": "面向学生的边界(不露 source_ref / candidate / P 编号)",
    "source_refs": ["candidate_teaching_example::..."]
  },
  "question_data": {
    "stem": "...",
    "activities": [{"id": "A", "label": "A", "duration": 3}],   // 5-7 项
    "dependencies": [{"from": "START", "to": "A"}],               // 含 START/END, DAG
    "expected": {
      "critical_path": ["START", "A", "C", "E", "END"],
      "project_duration": 10,
      "float": {"A": {"total_float": 0, "free_float": 0}}
    }
  },
  "explanation_steps": [
    {"id": "...", "title": "...", "focus": ["dependencies|early_time|late_time|critical_path"],
     "script": "老师口吻讲解", "evidence_refs": ["..."]}
  ],
  "error_reveals": [
    {"id": "...", "error_code": "candidate_network_error", "title": "...",
     "jump_step_id": "命中 explanation_steps.id", "script": "...", "correction_hint": "..."}
  ],
  "practice": {
    "question": "...", "options": [{"id": "A", "text": "..."}], "answer": "B",
    "review_step_id": "命中 explanation_steps.id", "correct_script": "...", "incorrect_script": "..."
  }
}
```

必填字段：`activities`、`durations`(在 activities 内)、`dependencies`、`expected.critical_path`、`expected.project_duration`、`expected.float`、`explanation_steps`、`error_reveals`、`practice`。

约束（`render_network_card.py` 校验）：

- `activities` 5-7 项；`dependencies` 构成 DAG，必须有并行路径；至少一个非关键工作 `total_float>0`。
- **renderer 不自行判定考试口径**：前端只读 `expected`，把两端都在关键集合的边标 `critical`，不计算。
- **确定性计算器是独立校验器/编译器**，不是前端：build 期 `compute_cpm()` 顺推/逆推，**校验** JSON 的 `expected` 与计算一致（不一致 raise），并**派生** ES/EF/LS/LF 供展示。日后可抽成独立编译器，仍不得让前端 renderer 现场判断。
- `explanation_steps[].evidence_refs` 必填；当前样板是教学候选必须标 `authority.status=candidate_teaching_prototype`。
- **不得把 candidate 的 critical_path / float 冒充 official scoring key**；不编造真题来源。
- `error_reveals[].jump_step_id` / `practice.review_step_id` 必须命中 `explanation_steps[].id`；`practice.answer` 必须命中某 option。
- 学生 UI 不得出现 `source_ref` / `schema` / `renderer` / `candidate` / `P 编号` 等内部词；`authority.status` 仅内部用。
- 渲染器暴露断言钩子：`dataset.activeStep` / `dataset.activeError` / `dataset.practiceResult`；节点 `.node[data-node-id]`、边 `.edge[data-from][data-to]`(关键边加 `.critical`)、时差 `.float[data-total-float][data-free-float]`。

## 顶层字段（F16 流程/剖面类，默认模板）

```jsonc
{
  "schema_version": "luban_diagram_microlesson.v1",
  "topic_id": "roof_membrane_bulge_repair",
  "title": "屋面卷材防水 · 起鼓割补",
  "taxonomy_ref": "1A434000",
  "visual_baseline": {
    "path": "artifacts/luban_case_family_assets/F16/F16_roof_waterproofing_micro_lesson_card_v1.html",
    "role": "v0 visual baseline only"
  },
  "authority": {
    "judging_artifact_id": "Q18-1A434000::qga_v0_20260604",
    "judging_authority_label": "培训机构(佑森)教研估分，非官方阅卷",
    "source_boundary": "...(内部口径, 含 source_ref 字样, 只进 HTML 注释, 不给学生看)",
    "student_boundary": "...(面向学生的考试依据边界说明; 不得出现 source_ref / 母题包 / P 编号等内部词)"
  },
  "learning_goal": "...",
  "scenario": {
    "caption": "...",
    "diagram_type": "roof_section_step_reveal",
    "diagram_disclaimer": "..."
  }
}
```

## 8 步 `steps[]`

正式卡必须是 8 步。每一步至少包含:

| 字段 | 说明 |
|---|---|
| `id` | 稳定 step id, 供 SVG layer、错因跳转、URL `#step=N` 使用 |
| `no` | 1-8 |
| `tab` | 手机端步骤按钮短标题 |
| `action` | 当前步骤主标题 |
| `brief` | 一句话解释 |
| `why` | 图上 callout 使用, 说明为什么这一步必要 |
| `scoring_expression` | 学生应该怎么写才接近采分表达 |
| `common_loss` | 常见丢分说法 |
| `exam_binding` | 此步骤和采分点/教学拆解点的关系 |

### `exam_binding`

```jsonc
{
  "kind": "signed_candidate | teaching_step",
  "score_point_id": "P10",
  "label": "放气",
  "max_score": "0.75",
  "source_refs": ["Q18-1A434000::qga_v0_20260604#P10"]
}
```

约束:

- `signed_candidate`: 来自已签发或候选判分工件, 可以显示候选分值。
- `teaching_step`: 教学拆解点, 不能冒充分值点。
- 如果没有分值, `max_score` 必须为 `null`。

## 采分点 `scoring_points[]`

用于汇总已签发或候选采分点:

```jsonc
{
  "id": "P10",
  "tier": "exact_required",
  "max_score": "0.75",
  "keywords": ["放气", "擦干", "清除旧胶结料"],
  "source_ref": "Q18-1A434000::qga_v0_20260604",
  "used_by_steps": ["cut_bulge", "vent_dry", "clean_prime"]
}
```

已登记 tier:

| tier | 展示含义 |
|---|---|
| `exact_required` | 须写到关键词 |
| `high_risk_review` | 高风险表达 |
| `list_rule` | 列举规则 |
| `calculation` | 计算规则 |

## 错因跳转 `common_errors[]`

```jsonc
{
  "id": "direct_cover",
  "text": "在鼓泡处直接加铺一层新卷材。",
  "error_code": "E06",
  "why": "程序顺序错误...",
  "jump_step_id": "vent_dry"
}
```

约束:

- `jump_step_id` 必须命中 `steps[].id`。
- `error_code` 只用于 display, 必须来自既有错因 taxonomy。
- 点击错因卡后只跳到对应图解节点, 不重新判分。

## 旁白 `narration`

字幕式旁白。文本**只能**来自本字段, 绑定 `step_id`; 渲染器不接 TTS、不在前端临场生成、无音频文件。

```jsonc
{
  "kind": "subtitle_autoplay",
  "voice": "teacher_warm",
  "total_seconds_hint": 82,
  "opening": {
    "seconds": 7,
    "script": "这题不是背八个动作……"
  },
  "steps": [
    {
      "step_id": "identify_bulge",
      "seconds": 9,
      "script": "先别急着写维修……"
    }
  ],
  "error_reveals": [
    {
      "error_id": "missing_reinforcement",
      "jump_step_id": "reinforcement_layer",
      "seconds": 7,
      "script": "...(解释这类答案为什么丢分, 5-8 秒, 手机 2-3 行)",
      "correction_hint": "...(一句话纠正, 进顶部横幅)"
    }
  ],
  "practice_feedback": {
    "correct_script": "...(答对: 你抓住了哪个核心得分逻辑)",
    "incorrect_script": "...(答错: 你漏的是哪一层闭环)"
  }
}
```

约束:

- `steps[].step_id` 必须命中 `steps[].id`; `steps[].seconds` 8-12; `script` 非空, 不冒充采分点。
- `opening` 可选; `seconds` 6-8; 播放时先于 step1 显示, 但 activeLayer 保持 step1。
- `error_reveals[].error_id` 必须命中 `common_errors[].id`; `jump_step_id` 必须命中 `steps[].id`; `seconds` 5-8; `script`+`correction_hint` 非空。
- `practice_feedback.correct_script` / `incorrect_script` 非空; `review_step_id` 复用 `practice.review_step_id`, 不在此重复。
- 播放从 opening/第 1 步自动切到最后一步, 字幕在图下方, 同步高亮 SVG layer, 可暂停/继续。
- 手动翻步 / 错因跳转 / 复测作答会暂停自动旁白并改写字幕。
- 渲染器暴露断言钩子: `dataset.narrPlaying` / `dataset.narrIndex` / `dataset.narrMode`(idle|opening|step|manual_step|error|practice_correct|practice_incorrect) / `dataset.activeError`。
- 全部旁白文本来自本字段; 不接 TTS、不在前端生成、无音频文件。
- 学生端禁止露出 `source_ref` / `母题包` / `P10`/`P11` / `schema` / `本系统` 等内部词。

## 复测题 `practice`

```jsonc
{
  "kind": "retest_mcq",
  "title": "复测题：判断漏点",
  "review_step_id": "reinforcement_layer",
  "stem": "...",
  "options": [
    {
      "id": "B",
      "text": "...",
      "is_correct": true,
      "feedback": "..."
    }
  ],
  "next_action": "..."
}
```

约束:

- 必须只有一个正确答案。
- 复测题是训练反馈, 不是正式考试题。
- `review_step_id` 可选, 必须命中 `steps[].id`; 答错时渲染器跳回该 step 并显示"你漏了这一步"横幅。缺省回退 `reinforcement_layer`。
- 答对时显示"你已经抓住核心漏点"正向反馈, 不跳转。
- 答错时可跳回对应 step, 但不能写入真实 learner state。

### 学生端答案泄漏边界（静态卡固有约束，诚实登记）

- `#cardData` JSON **只透传 `practice.review_step_id`**（答错回跳用），**不得**透传 `options[].is_correct` / `feedback`（`render_card.py` 已收口；`steps`/`narration` 同样经 `client_*` 白名单投影）。
- 选项对错由按钮 `data-correct` 承载，这是**静态卡前端判分的固有项**：无服务端时，"哪个选项正确 + 选项级 feedback" 必然在前端 DOM 可得。
- 因此复测题在静态卡下**仅作训练自检**，view-source 能看穿答案 = 学生自欺，危害低；**非防作弊场景**。正式计分 / 防作弊需服务端判分，超出本 renderer 职责，不在 schema 层假装解决。

## 输出文件

```bash
python3 render_card.py F16_qigu.json F16_qigu.rendered.html
```

输出 HTML 特性:

- 无 CDN
- 无外链图片
- CSS / JS / SVG 全内联
- 可通过 `?step=6` 或 `#step=6` 打开指定步骤
- 顶部快速导航(看工序 / 错因自查 / 复测一题)
- 侧栏四张讲解卡: 为什么这么做 / 这样写才得分 / 你常漏什么 / 来源·边界
- 错因节点跳转, 跳转后显示"你漏了这一步"横幅(`#jumpNote`)
- 复测题对/错反馈 + 答错回跳 `review_step_id`
- 移动端(<=520px)聚焦 viewBox `210 150 470 350`, 隐藏浮动 callout, 首屏不横向滚动
- `document.documentElement.dataset.activeLayer` 暴露当前激活图层, 便于 DOM 断言
- 适合小程序 WebView 静态卡评估

## Register-before-use 纪律

1. 新考点先填 schema, 不直接手写成品 HTML。
2. 所有得分点必须绑定 `source_ref`。
3. 教学拆解点必须标 `kind=teaching_step`, 不展示分值。
4. 图形可以先由 renderer 的固定模板承载; 后续如果要支持更多构造图, 再升级为几何 schema。
5. 每次渲染后至少验证:
   - JSON 合法
   - renderer 可运行
   - HTML 无外链
   - 390px 手机截图无横向溢出
   - 错因跳转和复测题可交互
