# OpenMAIC-Inspired Luban Animation IR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 OpenMAIC 可学习的生产机制吸收到鲁班深母题动画卡生产线中，形成“母题事实 -> 可审阅 outline -> 演进后的 lesson/action IR -> 确定性 renderer -> runtime gate -> 可复查 bundle”的量产底座。**关键纪律:在现有 `luban_teaching_animation.v0`(`lesson.json`,MVP 已两轮红到绿验证可用)内演进,不另起新 IR、不重写 renderer。**

**Architecture:** LLM 只生成结构、脚本、镜头和练习编排；在现有 `luban_teaching_animation.v0` 的 beat 上**新增 `animation_action[]` 白名单字段(camera/highlight/reveal/keycard)**作表现层编译产物,`outline` 作生成前中间产物(不进 schema);`card_bundle_manifest` 作资产清单。现有 `render_*.py`(`render_archetype_journey.py` 等)**复用、不重写**,只按白名单 action 渲染,不产生知识、不判分、不写学情。质量由现成的 schema gate / layout gate / practice gate / judge,加上**新补的 data-id gate 与 timing gate** 共同收口。

**Tech Stack:** 现有 `luban_teaching_animation.v0` lesson schema(演进) / JSON Schema / Python validators / Node.js runtime validators / zero-dependency static HTML renderer(复用现有 `render_*.py`) / Playwright or CDP screenshot harness / Aliyun TTS asset manifest / existing `agent-skills/luban-diagram-microlesson` skill.

---

- **日期**: 2026-06-19
- **状态**: `Partially Implemented (J01 deterministic slice passed, 2026-06-19)`
- **主线**: 鲁班移动端提分闭环
- **上游输入**:
  - `2026-06-17-luban-explainer-motion-template-engine-v0-principles.md`
  - `2026-06-18-luban-animation-learning-system-master-plan.md`
  - `2026-06-19-luban-animation-pack-taxonomy-alignment-registry.md`
- OpenMAIC 代码审计结论: outline-first、typed action IR、stage shell/renderer 分离、keep-alive interactive host、runtime eval/report、server-managed provider、manifest export。

## 2026-06-19 执行记录

已完成 J01 端到端确定性切片,并把方法增量并入 `agent-skills/luban-diagram-microlesson`:

- 在现有 `luban_teaching_animation.v0` 内演进 `animation_action[]`,不新建 `LubanLessonIR`。
- `validate_animation_action_schema.py`、`validate_data_id_targets.mjs`、`validate_timing_sync.mjs`、`validate_video_first_preview.mjs`、`build_card_bundle_manifest.py`、`gate.sh J01` 已落地。
- `render_archetype_journey.py` 复用现有 journey renderer,输出 orientation-adaptive 学习舞台,并收紧 student-safe manifest 边界。
- `render_archetype_practice.py` 输出独立 practice HTML,每题有 SVG 判断图,选项包含结论/错因/判断依据,末题为采分句输出。
- `gate.sh J01` 当前串联 schema/action/timing/render/practice/data-id/runtime/practice-preview/bundle-manifest,不生成 MP4。
- 最新证据:`artifacts/luban_case_family_assets/diagram_microlesson/reports/J01/20260619-204342-40446/gate.md`。
- 2026-06-19 review 修复:theater 不再由 gate 直接加 class 假通过,必须点击真实 `[data-theater-toggle]`;`sync_keyword` 必须命中对应 timing 文本/keycard;bundle manifest 纳入 timing.audio 且输出 bundle-root 相对路径;practice renderer 不再硬编码危大阈值,改从 master `R3_scenario_templates` 取。
- 最新修复后证据:`artifacts/luban_case_family_assets/diagram_microlesson/reports/J01/20260619-221902-82398/gate.md`。

未完成项不能偷换成完成:

- N01/S02 尚未接入同一套 `gate.sh`。
- judge 修订 prompt 模板仍待补齐。
- learner evidence / 留存验证仍未跑。
- M1 starter pack pilot 仍未启动。

## 0. Executive Decision

采用 OpenMAIC 的“结构化中间表示 + 确定性渲染 + 真实 runtime gate”方法，但不复制 OpenMAIC 的泛课堂形态。**且不另起新 IR——在现有 `luban_teaching_animation.v0` 上演进。**

鲁班要建的是考试提分动画卡生产线，不是通用 AI 课堂平台。当前最优路径是:

```text
Deep Archetype / Mother Question facts
  -> Card Outline Review (生成前中间产物,不进 schema)
  -> 演进后的 luban_teaching_animation.v0 lesson.json
       (beat 上新增 animation_action[] 白名单: camera/highlight/reveal/keycard)
  -> 复用现有 render_*.py (render_archetype_journey 等)
  -> Runtime gates and judge reports (复用现成 + 新补 data-id/timing 两道)
  -> card_bundle_manifest (资产清单)
  -> WeChat/WebView preview and later mini-program integration
```

> 明确不新建 `LubanLessonIR`、不按新 IR 重写 renderer、不另起三层新 schema。现有 `lesson.json` 已经是验证可用的动画 IR,本计划是在它内部演进。

第一阶段只证明这条链能在 3 个代表卡上稳定闭环:

| Pack | 角色 | 验证重点 |
|---|---|---|
| `N01` 网络计划 | 图结构/计算白板标杆 | timing sync、关键线路 data-id、进度拖动、横竖屏布局 |
| `J01` 危大专家论证 | 判断树标杆 | outline review、decision branch、阈值/边界档、采分句 |
| `S02` 起重吊装安全 | 流程 + 判断组合标杆 | procedural-skill、错误步骤后果反馈、流程化纠错；现有原型文件名前缀暂为 `A01_crane_lifting_safety` |

`S01/F16/C01` 保留为回归样本，不在第一阶段扩产。`A01_crane_lifting_safety` 在本计划内仅作为 S02 的历史原型文件名，后续 manifest 要收敛到业务 pack id `S02`。

## 1. Non-Goals

1. 不照搬 OpenMAIC 源码、提示词、UI、组件树、DSL 命名。
2. 不新增聊天入口；不得引入 OpenMAIC stateless `/api/chat` 思路，DeepTutor 仍以 `/api/v1/ws` 为唯一聊天入口。
3. 不让 renderer 计算采分点、官方答案、学习画像或 taxonomy 结论。
4. 不默认生成 MP4。HTML 预览和小程序 WebView 验证阶段只生成 HTML、audio、timing、poster、manifest；MP4 只在明确要导出视频或发布素材时生成。
5. 不把 raw HTML/iframe 作为 production 学习卡 authority。静态 HTML 只作为当前 preview 壳；生产方向是结构化 IR 被确定性 renderer 消费。
6. 不在未过 gate 前批量生产 20/40/60 卡。

## 2. Authority Split

| 业务事实 | 唯一 authority | 本计划中的消费者 |
|---|---|---|
| 考点/错因/出题人逻辑 | Deep Archetype Pack / 母题资产 schema | outline builder、lesson IR compiler |
| 知识归因/召回/复测锚点 | canonical taxonomy registry | pack manifest、练习引用 |
| 采分点/判分 | signed grading artifact / `CaseGradingSkillKernel` | 只读展示、采分句练习 |
| 动画呈现 | 演进后的 `luban_teaching_animation.v0` lesson.json + beat 内 `animation_action[]` | 复用现有 `render_*.py` |
| 音频/字幕/镜头同步 | timing manifest | player、timing gate |
| 媒体资源 | card bundle manifest | preview、WeChat WebView |
| 学情结论 | `LearnerStateService` / learning evidence | 不由本计划写入 |

### Thin Wrappers / Fat Skills

- Thin wrapper: HTML preview shell、mobile controls、renderer adapter、TTS route wrapper、export wrapper。
- Fat skill/kernel: `agent-skills/luban-diagram-microlesson`、IR compiler、schema validator、timing validator、practice interaction validator。
- 红线: wrapper 内不得堆 prompt、regex、教学判断、打分判断、错因归因。

## 3. Target File Structure

### Plan / Skill

- Modify: `docs/plan/INDEX.md`
- Modify later: `agent-skills/luban-diagram-microlesson/SKILL.md`
- Modify later: `agent-skills/luban-diagram-microlesson/references/production-workflow.md`
- Modify later: `agent-skills/luban-diagram-microlesson/references/learning-stage-shell.md`
- Create later: `agent-skills/luban-diagram-microlesson/references/openmaic-inspired-ir-gates.md`

### Schema / IR(演进现有 v0,不新建 IR)

- Modify: `artifacts/luban_case_family_assets/diagram_microlesson/SCHEMA.md`(在 `luban_teaching_animation.v0` 内记录 beat 新增 `animation_action[]` 白名单字段)
- Modify: 现有 `luban_teaching_animation.v0` lesson schema 定义——在 beat 上加 `animation_action[]`(camera/highlight/reveal/keycard 白名单);`outline` 作生成前中间产物,**不进 schema**
- Register: `contracts/schema_registry.yaml` 登记 `animation_action[]` 与 `card_bundle_manifest`(标 content/asset schema、**非 grading**),不撞现有 `luban_diagram_microlesson.v1`
- **不新建** `LubanLessonIR`、不新建独立 `luban_lesson_ir.schema.json` / `luban_animation_action.schema.json` / `luban_card_bundle.schema.json` 三层新 schema——全部在现有 v0 内演进

### Renderer / Gates(复用现有 renderer,只补 2 道新门)

- **复用,不重写**: 现有 `render_*.py`(`render_archetype_journey.py` 等)——按新增的 `animation_action[]` 白名单渲染
- **复用现成 gate**: `validate_schema_drafts.py`(schema)、`validate_learning_stage_runtime.mjs`(layout)、`validate_video_first_preview.mjs`(practice)、production-workflow §2 的独立 judge
- Create(仅 2 道新门): `artifacts/luban_case_family_assets/diagram_microlesson/validate_data_id_targets.mjs`
- Create(仅 2 道新门): `artifacts/luban_case_family_assets/diagram_microlesson/validate_timing_sync.mjs`
- Modify/Create: `artifacts/luban_case_family_assets/diagram_microlesson/gate.sh`(把现成 4 道 + 新补 2 道串起来)
- Register: `contracts/registries.yaml` 登记 2 道新门(否则 dormant)

### Tests

- Create: `tests/scripts/test_luban_animation_action_schema.py`(测 v0 beat 上 `animation_action[]` 白名单/未知 action 拒绝)
- Create: `tests/scripts/test_luban_card_bundle_manifest.py`
- Create: `tests/scripts/test_luban_animation_gate_scripts.py`(测新补的 data-id / timing 两道门)

## 4. Milestone Plan

### M0: Reality Lock and Baseline Freeze

**Objective:** 冻结现有 N01/J01/S02(当前文件前缀 `A01_crane_lifting_safety`)/S01/F16 的真实状态，避免新计划把旧 demo 状态误当生产底座。

**Files:**
- Read: `artifacts/luban_case_family_assets/diagram_microlesson/N01_network_video_first.lesson.json`
- Read: `artifacts/luban_case_family_assets/diagram_microlesson/N01_network_video_first.lesson.timing.json`
- Read: `artifacts/luban_case_family_assets/diagram_microlesson/J01_danger_work_expert_argumentation.lesson.json`
- Read: `artifacts/luban_case_family_assets/diagram_microlesson/A01_crane_lifting_safety.lesson.json`
- Read: `artifacts/luban_case_family_assets/diagram_microlesson/S01_scaffold_template_acceptance.lesson.json`
- Create: `artifacts/luban_case_family_assets/diagram_microlesson/golden/BASELINE.md`

- [ ] Step 1: Record baseline inventory.
  - Command: `python - <<'PY'\nfrom pathlib import Path\nroot=Path('artifacts/luban_case_family_assets/diagram_microlesson')\nfor p in sorted(root.glob('*.lesson.json')):\n    print(p.name)\nPY`
  - Expected: lists current lesson JSON files without generating new assets.
- [ ] Step 2: Classify each current artifact as `prototype`, `golden`, `regression_sample`, or `discard`.
- [ ] Step 3: Write `golden/BASELINE.md` with N01/J01/S02 as target MVP, record `A01_crane_lifting_safety` as S02's historical prototype prefix, and keep S01/F16/C01 as regression samples.
- [ ] Step 4: Run existing validators.
  - Command: `python artifacts/luban_case_family_assets/diagram_microlesson/validate_schema_drafts.py`
  - Command: `node artifacts/luban_case_family_assets/diagram_microlesson/validate_learning_stage_runtime.mjs artifacts/luban_case_family_assets/diagram_microlesson/N01_network_video_first.rendered.html`
- [ ] Step 5: Commit only baseline docs if execution branch is clean enough; otherwise leave staged decision to user.

**Pass Criteria:**
- Baseline file exists.
- No new MP4 is generated.
- N01/J01/S02 target roles are explicit.

### M1: 在 v0 内演进 typed action(不新建 IR)

**Objective:** 把“画面怎么动”从 HTML 隐式动画里提到结构里——在现有 `luban_teaching_animation.v0` 的 beat 上**新增 `animation_action[]` 白名单字段**,renderer 按它渲;不另起新 IR、不重写 renderer。

**Files:**
- Modify: 现有 `luban_teaching_animation.v0` lesson schema——beat 上加 `animation_action[]`
- Modify: 现有 `lesson.json`(J01 优先,见 §5)——给 beat 填 `animation_action[]`
- Modify: `SCHEMA.md`
- Register: `contracts/schema_registry.yaml`——登记 `animation_action[]`(content schema,非 grading)
- Test: `tests/scripts/test_luban_animation_action_schema.py`

**beat 新增字段(在现有 v0 beat 内,不是新顶层 schema):**

```jsonc
// 现有 luban_teaching_animation.v0 lesson.json 的某个 beat,新增:
"animation_action": [
  { "type": "camera",    "target": "data-id:network-graph" },
  { "type": "highlight", "target": "data-id:critical-path" },
  { "type": "reveal",    "target": "data-id:slack-row" },
  { "type": "keycard",   "target": "data-id:keycard-critical-path" }
]
```

`outline` 作生成前中间产物,不进 schema。

**Action whitelist(camera/highlight/reveal/keycard 为本期落地的核心四类;其余按现有 v0 既有语义保留):**

```json
[
  "camera",
  "highlight",
  "reveal",
  "keycard"
]
```

- [ ] Step 1: Write failing schema tests for `animation_action[]` 白名单 and forbidden unknown action type.
- [ ] Step 2: 在现有 `luban_teaching_animation.v0` schema 定义里加 `animation_action[]` 白名单字段(演进,不新建文件)。
- [ ] Step 3: 给 J01 现有 `lesson.json` 的 beat 填 `animation_action[]`(优先 J01,见 §5);N01/S02 在扩产时跟进,不先动内容。
- [ ] Step 4: 在 `contracts/schema_registry.yaml` 登记 `animation_action[]`(标 content schema、非 grading),不撞 `luban_diagram_microlesson.v1`。
- [ ] Step 5: Add `SCHEMA.md` section: `animation_action[]` is presentation compile artifact, not grading/knowledge authority。
- [ ] Step 6: Run tests.
  - Command: `pytest tests/scripts/test_luban_animation_action_schema.py -q`

**Pass Criteria:**
- Unknown action type fails.
- Missing `data-id` target fails.
- `animation_action[]` 已登记进 `schema_registry.yaml`(否则 register-before-use 拦)。
- 现有 J01 `lesson.json` 加完 `animation_action[]` 后仍通过现有 `validate_schema_drafts.py`。

### M2: 复用现有 renderer 渲完整 stage(不新建 shell renderer)

**Objective:** 用统一 stage 解决手机/横屏/全屏/进度拖动/节点跳转,而不是每张卡手写 UI——**在现有 `render_*.py`(`render_archetype_journey.py` 等)上扩展,不新建 `render_learning_stage_shell.py`**。

**Files:**
- Modify: 现有 `render_archetype_journey.py`(等 `render_*.py`)——按 `animation_action[]` 渲 stage
- Modify: `validate_learning_stage_runtime.mjs`(现成 layout gate,复用)
- Create: `validate_data_id_targets.mjs`(新补门之一)

**Renderer contract:**

```text
input: 演进后的 luban_teaching_animation.v0 lesson.json (beat 含 animation_action[]) + assets
output: static rendered HTML
must expose:
  [data-card-id]
  [data-stage-shell]
  [data-beat-id]
  [data-action-id]
  [data-visual-node-id]
  [data-practice-id]
  window.__LUBAN_LESSON_MANIFEST__
must not:
  compute scoring
  infer taxonomy
  mutate source facts
  require external JS/CSS for core playback
```

- [ ] Step 1: Write shell runtime smoke that opens rendered HTML and asserts shell hooks exist.
- [ ] Step 2: 在现有 `render_*.py` 上扩展 stage 渲染(先 J01,见 §5),不新建 renderer。
- [ ] Step 3: Add full-screen theater mode: normal screen shows compact shell; full-screen shows only lesson stage; tap reveals controls.
- [ ] Step 4: Add draggable progress bar with beat snapping.
- [ ] Step 5: Replace numeric `1..8` with named beat chips: `先学 / 错觉 / 读图 / 顺推 / 逆推 / 时差 / 线路 / 采分`.
- [ ] Step 6: Add landscape layout: stage left, compact beat/controls right or bottom depending viewport.
- [ ] Step 7: Run mobile and landscape screenshot gates.

**Pass Criteria:**
- 390x844 mobile: no horizontal scroll, no clipped main stage, controls not covering key content.
- 844x390 landscape: stage remains readable, controls do not force vertical scroll.
- Fullscreen mode contains only learning stage + transient controls.
- Every action target resolves to an existing `data-*` node.

### M3: Timing Sync and Audio Manifest

**Objective:** 音频、字幕、关键词、镜头动作对齐，解决“画面比声音快/像幻灯片”的核心体验问题。

**Files:**
- Create: `validate_timing_sync.mjs`(新补门之二)
- Modify: `build_lesson_narration.mjs`
- Modify: `build_aliyun_lesson_narration.mjs`
- Modify: 现有 `render_*.py`(复用,不新建)
- Create: `tests/scripts/test_luban_card_bundle_manifest.py`

**Timing contract:**

```json
{
  "audio": {"path": "N01.lesson.mp3", "duration_ms": 169000},
  "segments": [
    {
      "id": "beat-critical-path",
      "start_ms": 82000,
      "end_ms": 101000,
      "text": "关键线路看的是零总时差...",
      "actions": ["focus-critical-path", "trace-critical-path"],
      "keywords": ["关键线路", "总时差", "零"]
    }
  ]
}
```

- [ ] Step 1: Define strict segment/action anchor rule: every `speak` action longer than 2 seconds must have at least one visible action or intentional `hold`.
- [ ] Step 2: Implement timing validator.
- [ ] Step 3: Make player drive visual state from timing, not from independent CSS animation duration.
- [ ] Step 4: Add end-card closing narration segment.
- [ ] Step 5: Ensure MP4 is not generated by default.

**Pass Criteria:**
- Key terms appear within +/- 500ms of narration anchor.
- No beat changes more than 300ms before related narration starts unless marked `anticipation`.
- Playback can seek forward/backward and reconstruct visual state deterministically.
- End narration exists and auto switches primary CTA to `开始闯关`.

### M4: Procedural Practice and Challenge Page

**Objective:** 把练习独立成页面，并按 OpenMAIC procedural-skill 的原则做“判断/操作/后果反馈”，不是 checklist。

**Files:**
- Modify: 现有 `render_*.py`(复用,不新建)
- Modify: existing practice renderer(复用现有,练习门复用 `validate_video_first_preview.mjs`)
- Note: practice gate 复用现成 `validate_video_first_preview.mjs`,不新建 `validate_practice_interaction.mjs`

**Practice contract:**

```json
{
  "practice": [
    {
      "id": "q1",
      "type": "path_duration_basis",
      "prompt": "这张网络图的关键线路、总工期和判断依据是什么?",
      "visual_ref": "network-variant-1",
      "options": [
        {
          "id": "A",
          "path": "开始-A-C-E-结束",
          "duration": 10,
          "basis": "A/C/E 总时差均为 0",
          "is_correct": true
        }
      ],
      "feedback": {
        "correct": "用路径、工期、依据三件套表达。",
        "incorrect": "只比单项工期会漏掉逻辑关系。"
      }
    }
  ]
}
```

- [ ] Step 1: Practice page separated from lecture page.
- [ ] Step 2: Every question has visual diagram or variation diagram.
- [ ] Step 3: Options use structured form: `路径 + 工期 + 判断依据` for N01; `对象 + 时点 + 验收/放行依据` for S02/J01.
- [ ] Step 4: Add score phrase output question.
- [ ] Step 5: Add feedback state and review jump back to lesson beat.

**Pass Criteria:**
- Student can finish challenge without scrolling through lesson.
- Incorrect feedback points to exact wrong reasoning, not generic encouragement.
- Practice state survives page switch within preview shell.

### M5: Gate and Judge Loop

**Objective:** 把“自查机制”做成 blocking gate，不再靠肉眼发现比例、声音、排版问题。

**Files:**
- Modify/Create: `gate.sh`(把现成 4 道 + 新补 2 道串起来)
- Create: `validate_timing_sync.mjs`(新补门之二)
- Create: `validate_data_id_targets.mjs`(新补门之一)
- Register: `contracts/registries.yaml`(登记 2 道新门,否则 dormant)
- 复用现成: schema(`validate_schema_drafts.py`)/ layout(`validate_learning_stage_runtime.mjs`)/ practice(`validate_video_first_preview.mjs`)/ judge(production-workflow §2)

**Gate levels(复用现成 4 道 + 新补 2 道):**

| Gate | 来源 | Type | Blocking |
|---|---|---|---|
| schema | 复用 `validate_schema_drafts.py` | deterministic | yes |
| layout / overflow | 复用 `validate_learning_stage_runtime.mjs` | deterministic | yes |
| practice interaction | 复用 `validate_video_first_preview.mjs` | deterministic | yes |
| **data-id target** | **新补** `validate_data_id_targets.mjs` | deterministic | yes |
| **timing sync** | **新补** `validate_timing_sync.mjs` | deterministic | yes |
| screenshot wall | 复用现有 screenshot harness | deterministic artifact | yes |
| VLM/LLM teaching judge | 复用 production-workflow §2 独立 judge | semantic report | report-only first, blocking after calibration |

- [ ] Step 1: `gate.sh J01` 串起现成 4 道 + 新补 2 道 deterministic gates。
- [ ] Step 2: Save artifacts under `artifacts/.../reports/<card_id>/<timestamp>/`.
- [ ] Step 3: Emit Markdown report with pass/fail, screenshots, failed selectors, timing drift.
- [ ] Step 4: 在 `contracts/registries.yaml` 登记 2 道新门(否则 dormant,不会被真正调用)。
- [ ] Step 5: Run gate for J01,过了再扩 N01/S02。
- [ ] Step 6: Add repair-loop prompt template that only changes presentation(`animation_action[]`/lesson.json), not source facts.

**Pass Criteria:**
- J01(再 N01/S02)can be regenerated and gated from 演进后的 lesson.json。
- A failed selector, overflow, timing drift, or practice missing visual causes non-zero exit.
- 2 道新门已登记 `registries.yaml`(否则视为 dormant)。
- Judge feedback is structured as `{axis, beat_id, severity, issue, fix}`.

### M6: 方法增量并入 production-workflow(本 plan 随后归档)

**Objective:** 把这次 OpenMAIC 吸收后的方法增量**并入 `production-workflow.md`**(编排权威),把造法增量沉到 `agent-skills/luban-diagram-microlesson`(造法权威);本 plan 不做第三个长期编排权威,落地后归档 `Implemented`。

**Files:**
- Modify: `agent-skills/luban-diagram-microlesson/references/production-workflow.md`(并入 typed action + 2 道新门 + bundle 方法增量)
- Modify: `agent-skills/luban-diagram-microlesson/SKILL.md`
- Modify: `agent-skills/luban-diagram-microlesson/references/learning-stage-shell.md`
- Modify later: `docs/plan/INDEX.md`(本 plan 标 `Implemented`)

- [ ] Step 1: Add rule: LLM generates `card_outline` 和 beat 内 `animation_action[]`(在现有 v0 内),not final pixels;不新建 IR。
- [ ] Step 2: Add rule: loop may revise presentation(`animation_action[]`/lesson.json) only; mother-question facts, grading artifacts, taxonomy refs cannot be silently changed.
- [ ] Step 3: Add rule: MP4 not generated by default; only HTML/audio/timing/manifest unless explicitly requested.
- [ ] Step 4: Add rule: every new card must pass `gate.sh`(现成 4 道 + data-id/timing 2 道新门)。
- [ ] Step 5: Add procedural-skill practice rules。
- [ ] Step 6: 方法增量并入 `production-workflow.md` 后,本 plan 在 `docs/plan/INDEX.md` 标 `Implemented`,不保留为长期权威。

**Pass Criteria:**
- 方法增量已并入 `production-workflow.md`(编排权威),不另立第三个编排权威。
- Skill has explicit OpenMAIC-derived principles without copying OpenMAIC text.
- Skill routes future work to evolve-v0 + 复用 renderer + gates,before visual polish。
- Skill records Ethan/student voice and Longanhuan/narrator voice defaults if still current.

### M7: M1 Starter Pack Pilot

**Objective:** 在不量产的前提下，用 12 个 starter packs 验证生产线覆盖 A/B/C/D 四类形态。

**Input:** `2026-06-18-luban-animation-learning-system-master-plan.md` M1 12 pack list.

- [ ] Step 1: For each pack, create only `card_outline` first.
- [ ] Step 2: Human/LLM review outline for: why learn, common loss, visual mode, score phrase, practice form.
- [ ] Step 3: Generate IR only for packs whose outline passes.
- [ ] Step 4: Gate each IR through deterministic gates.
- [ ] Step 5: Batch screenshot wall review.

**Expansion Gate:**
- Do not start more than 12 starter packs until at least 3 representative cards pass deterministic gates and one small learner review.
- Do not start 20-card production until D1/D7 or equivalent retention signal supports the format.

## 5. 执行顺序(J01 优先,先证一张端到端全绿 + 留存,不先建 IR 编译器)

**第一步就在 MVP 已两轮红到绿的 J01 上做完整闭环——过了再扩 N01/S02,再 fan out 60。** N01 仍是最能暴露 IR/timing/bbox 硬问题的回归样本,但不作为第一张端到端验证卡,因为 J01 已有两轮红到绿底子、能最快到留存验证而不返工。

| Day | Work | Exit Criteria |
|---:|---|---|
| 1 | M0 baseline + golden target selection(J01 为第一端到端卡) | `BASELINE.md` exists; no new generated media |
| 2 | M1 在 v0 内给 J01 beat 加 `animation_action[]` + 登记 schema_registry | action schema test pass;`validate_schema_drafts.py` 仍绿 |
| 3 | 补 timing gate(总时长 >~150s 判 REVISE,拦 J01 当前 3:27)+ data-id gate,登记 registries | 2 道新门 blocking 且非 dormant |
| 4-5 | 复用 `render_archetype_journey` 渲 J01 完整 journey(讲懂+闯关+看穿,控时 ~2 分钟) | mobile/landscape/fullscreen + timing/data-id gate pass |
| 6 | M3 timing sync + 音画对齐 | J01 timing drift report passes |
| 7 | M4 独立练习页(复用现有 practice renderer) | J01 challenge page passes 现成 practice gate |
| 8 | `gate.sh J01` + 独立 judge 全绿 → 上手机留存验证 | J01 报告全绿;留存信号采集 |
| 9 | 扩 N01/S02(复用同一 renderer,不复制控件) | no renderer-specific UI duplication |
| 10 | M6 方法增量并入 production-workflow,本 plan 归档 `Implemented` | future-card workflow documented |

## 6. 单一权威定位 + Subagent Operating Model

**本 plan 定位 = 一次性施工单(construction ticket),不是第三个长期编排权威。** 落地 typed action(`animation_action[]`)+ 2 道新门(data-id/timing)+ bundle 后,方法增量**并入 `production-workflow.md`**,plan 在 `docs/plan/INDEX.md` 归档 `Implemented`。

- **造法权威** = `agent-skills/luban-diagram-microlesson`(怎么造一张卡)。
- **编排权威** = `luban-learning-pack-factory`(怎么编排量产)。
- 本 plan 与上述两者在“生产编排”上不重复;它只承载本次 OpenMAIC 吸收的施工动作,做完即归档。

Use one fresh subagent per task family:

| Agent | Ownership | Output |
|---|---|---|
| Action/Schema Architect | v0 内 `animation_action[]` 演进 + 登记 | schema 演进、`schema_registry.yaml` 登记、action schema 测试 |
| Stage Renderer | 复用 `render_*.py` 扩展 stage/controls/layout | 现有 `render_archetype_journey.py` 等的扩展、layout gate 复用 |
| Timing QA | audio/timing/player sync | `validate_timing_sync.mjs`(新门)、timing reports |
| Practice Designer | independent challenge page | 复用现有 practice renderer + 现成 practice gate |
| Judge/Gate Engineer | gate 串联/报告 | `gate.sh`、`validate_data_id_targets.mjs`(新门)、`registries.yaml` 登记、report artifacts |
| Skill Editor | skill docs + 归档 | `agent-skills/luban-diagram-microlesson/*`、`production-workflow.md` 并入、`INDEX.md` 标 Implemented |

Coordination rules:

1. Each subagent gets disjoint file ownership.
2. No `git add -A`.
3. No agent-owned long-running Next dev server.
4. Generated screenshots/reports are allowed only under the card report path, not scattered in root.
5. Any source-fact change requires explicit note and cannot be hidden inside IR repair.

## 7. Blocking Risks and Mitigations

| Risk | Root Cause | Mitigation |
|---|---|---|
| UI 一改就坏 | 每张卡手写 layout | 复用统一 `render_*.py` stage + 复用 `validate_learning_stage_runtime.mjs` layout gate |
| 音画不同步 | CSS animation 和 audio timeline 双轨 | audio timing drives visual state |
| LLM 生成 HTML 不稳定 | LLM 画像素 | LLM 只产出 `animation_action[]`(在 v0 内),renderer 渲像素 |
| selector 指空 | 跨调用 selector 约定松 | mandatory `data-id` target validation(新补 data-id gate) |
| 练习不像考试 | 只做知识回忆 | options must include basis/score phrase |
| 质量门只报不拦 | report-only 太多 | deterministic gates blocking; VLM judge first report-only |
| 资源污染 runtime truth | imported/generated media 无 manifest | card bundle manifest with status/verdict/hash |
| 过早量产 | demo polish 诱导 | M1 starter only; expansion gated on learner evidence |

## 8. Final Acceptance

本计划完成时必须满足:

1. J01(再 N01/S02)的 `lesson.json` 已含 beat 内 `animation_action[]`、timing、manifest、rendered HTML、practice page。
2. 三张卡均可由同一套复用的 `render_*.py` 渲染，不再各写一套控件和布局。
3. 进度条可拖动，节点可跳转，fullscreen 只显示学习舞台和临时 controls。
4. 音频、字幕、关键词、关键视觉动作有 timing anchors。
5. 练习页独立，题目有图，选项结构化，至少一题要求输出采分句。
6. `gate.sh`(现成 4 道 + data-id/timing 2 道新门)对 J01/N01/S02 blocking pass,2 道新门已登记 `registries.yaml`。
7. 方法增量并入 `production-workflow.md`,记录: outline-first、在 v0 内演进 typed action(不新建 IR)、复用 deterministic renderer、no MP4 by default、repair only changes presentation not mother facts;本 plan 归档 `Implemented`。

## 9. Stop Conditions

立即停止扩产并回到计划复审:

1. 三张 MVP 卡任一无法通过 deterministic gates。
2. 复用的 `render_*.py` 需要读取 raw source_ref、scoring_point_id、taxonomy code 才能生成学生 UI。
3. 修一个卡的 UI 需要复制修改另一张卡的控件代码(说明 renderer 抽象错了,先修边界)。
4. timing sync 只能靠手调 CSS，而不能由 timing manifest 重建状态。
5. LLM repair 修改了母题事实、采分点、taxonomy refs 或 official/candidate 边界(只许改 `animation_action[]`/presentation)。
6. 用户测试显示“看完觉得好看但不会写采分句”。

## 10. First Execution Recommendation

**先在 J01 上做完整端到端闭环(讲懂+闯关+看穿,控时 ~2 分钟),过 `gate.sh` + 独立 judge 全绿,再上手机留存验证。** 过了再扩 N01/S02,再 fan out 60。**先证一张端到端全绿 + 留存,不先建 IR 编译器。**

理由:

1. J01 已两轮红到绿,有最快到留存验证而不返工的底子——这是 gated-on-retention 最该早做的验证。
2. 第一步只补 timing+data-id 两道门 + 给 J01 `lesson.json` 加 `animation_action[]` + 复用 `render_archetype_journey` 渲完整 journey,不动母题内容,保持 less is more。
3. N01(网络图/关键线路/总时差)仍是最能暴露 IR/timing/bbox 硬问题的回归样本,但放在 J01 全绿之后扩,避免同时重构多张卡。

J01 过 gate + 留存后,再用同一套复用的 `render_*.py` 接 N01/S02。若接入第二张卡时需要复制 renderer 代码,说明抽象仍然错了,应先修 renderer 边界,而不是继续做新卡。

---

## 11. 修订记录

**本版(`Proposed 评审修订版 2026-06-19`)已按三路专家(对比取舍 / 单一权威 / 工程量风险)评审结论整合进正文,正文即修正后可直接执行版本。** 评审 6 条修正落点:

1. **废 `LubanLessonIR`**:不另起三层新 IR schema、不按新 IR 重写 renderer——改为在现有 `luban_teaching_animation.v0`(`lesson.json`,MVP 两轮红到绿)内演进,beat 加 `animation_action[]` 白名单(camera/highlight/reveal/keycard);outline 作生成前中间产物,不进 schema。(落进 Goal/Architecture/§0/§2/§3/M1/M2)
2. **register-before-use**:`animation_action[]` 与 `card_bundle_manifest` 登记 `contracts/schema_registry.yaml`(content/asset、非 grading),不撞 `luban_diagram_microlesson.v1`。(落进 §3/M1)
3. **复用 renderer + 只补 2 门**:复用现有 `render_*.py`;schema/layout/practice/judge 复用现成,只补 data-id + timing 两道新门,串进 `gate.sh`,登记 `registries.yaml`。(落进 §3/M2-M5)
4. **J01 优先**:第一步在 J01 上补 2 门 + 加 `animation_action[]` + 渲完整 journey(~2 分钟)过 `gate.sh`+judge + 上手机留存;过了再扩 N01/S02,再 fan out 60。先证端到端全绿 + 留存,不先建 IR 编译器。(落进 §5/§10)
5. **施工单定位**:本 plan = 一次性施工单,方法增量并入 `production-workflow.md` 后归档 `Implemented`;不做第三个长期编排权威(造法权威=`luban-diagram-microlesson`,编排权威=`luban-learning-pack-factory`)。(落进 §6/M6)
6. **头部状态**:Goal/Architecture 对齐“演进现有 IR + 复用 renderer”,状态标 `Proposed (评审修订版 2026-06-19)`。
