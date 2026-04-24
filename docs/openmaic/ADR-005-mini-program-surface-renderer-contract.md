# ADR-005: Mini-program Surface And Renderer Contract

状态：Accepted

日期：2026-04-24

---

## 1. 决策

P0 的学员端唯一主表面是微信小程序：

- 标准实现：`wx_miniprogram`
- 佑森宿主交付包：`yousenwebview/packageDeeptutor`

Web/Admin 只承担教研审核、运营管理、导出预览和后续后台职责。HTML export 是导出 artifact，不是 P0 学员端主产品表面。

小程序播放器不以 React DOM 作为运行基础。`wx_miniprogram`、HTML export、PPTX export 共享的是 `Scene Runtime Core` 的语义解释规则，而不是共享 UI 组件。

---

## 2. Root Cause

v1.2 已经明确微信小程序是 P0 主表面，但 v1.1 技术蓝图和任务素材仍保留 Web-first 惯性：

- Next.js / React / Tailwind / Zustand
- React Scene Renderer
- `web/components/exam-classroom`
- `web/app/exam-classroom`

如果不补本 ADR，研发容易走向：

```text
先做 Web Player
-> 再适配小程序
-> Web / 小程序 / HTML export 各自解释 lesson_ir
-> 播放、导出、审核结果不一致
```

这会重新制造第二套甚至第三套 scene authority。

---

## 3. 一等业务事实

系统必须稳定维护的一等事实是：

> 同一份 `lesson_ir` 在微信小程序、HTML export、PPTX export 中表现可以不同，但语义解释、timeline、降级策略和校验规则必须一致。

---

## 4. Authority 边界

唯一内容真相仍是：

- `exam_classrooms.lesson_ir`

唯一内容 writer 仍是：

- `LessonIRService`

P0 新增渲染解释 authority：

- `Scene Runtime Core`

`Scene Runtime Core` 负责：

- 解释 scene / block / action / question 的语义
- 校验 action timeline 是否引用存在的 block / actor / question
- 标准化 block payload
- 输出平台无关的 render model
- 定义降级策略

平台 adapter 只负责把 render model 映射到目标表面：

- `wx-renderer-adapter`：WXML / WXSS / Canvas / 小程序音频
- `html-export-adapter`：Static HTML / React build
- `pptx-export-adapter`：PptxGenJS / image fallback

禁止：

- 小程序、HTML export、PPTX export 各自重新解释 `lesson_ir`
- 在 `lesson_ir` 里嵌入任意 HTML/CSS/JS
- 把 React 组件当作跨端共享核心
- 通过 WebView/iframe 承载 P0 课堂播放器

---

## 5. 推荐目录

```text
packages/exam-classroom-runtime/
  scene_vm.ts
  action_interpreter.ts
  block_normalizer.ts
  layout_tokens.ts
  validation.ts
  fallback_policy.ts

wx_miniprogram/components/exam-classroom/
  classroom-player/
  slide-scene/
  whiteboard-scene/
  quiz-scene/
  case-scene/

yousenwebview/packageDeeptutor/components/exam-classroom/
  classroom-player/
  slide-scene/
  whiteboard-scene/
  quiz-scene/
  case-scene/

render-export-service/
  html-adapter/
  pptx-adapter/
```

说明：

- `packages/exam-classroom-runtime` 不能依赖 DOM、React、Window、Document、微信全局对象。
- 小程序 adapter 可以依赖 `wx` API，但不能反向污染 runtime core。
- HTML/PPTX adapter 可以有自己的布局实现，但必须复用 runtime core 输出的 render model。

---

## 6. Lesson IR render constraints

`Lesson IR` 必须增加平台可渲染约束：

```ts
type RenderConstraints = {
  allowed_platforms: Array<'wx_miniprogram' | 'html_export' | 'pptx_export'>
  forbidden_payloads: Array<'raw_html' | 'inline_script' | 'iframe' | 'external_css'>
  max_block_text_chars: number
  max_scene_payload_kb: number
  requires_canvas?: boolean
  has_audio?: boolean
  fallback_render_mode?: 'static_card' | 'image' | 'text_only'
}
```

P0 禁止 `lesson_ir` 包含：

- raw HTML
- inline script
- iframe
- external CSS
- browser-only event handlers
- 任意动态 JS simulation

---

## 7. Mini-program job progress

后端可以继续为 Web/Admin 提供 SSE：

- `GET /api/exam-classrooms/jobs/{job_id}/events`

但 P0 小程序端不能强依赖浏览器 EventSource。

小程序 P0 默认使用轮询/增量事件：

```text
GET /api/exam-classrooms/jobs/{job_id}?include_events_after={seq}
```

或：

```text
GET /api/exam-classrooms/jobs/{job_id}/events-lite?after={seq}
```

事件必须有：

- `seq`
- `job_id`
- `event_type`
- `status`
- `payload`
- `created_at`

小程序端必须支持：

- 断网恢复
- app hide/show 后恢复
- 重复事件按 `seq` 去重
- `outline_ready / scene_ready / quality_check / course_ready` 不丢
- 最坏情况下只靠轮询完成一键生成体验

---

## 8. WxTurnSocketManager

课堂问答仍统一走 `/api/v1/ws`。

小程序端必须通过一个 `WxTurnSocketManager` 管理 turn socket：

- `connect / reconnect`
- heartbeat
- app hide/show resume
- auth token refresh
- pending turn recovery
- `ClassroomGroundingContext` attach
- `trace_id` correlation

禁止：

- job progress、chat、TTS、review 各自开独立 turn socket
- 小程序端把整段 `lesson_ir` 拼进 `message.content`
- 小程序端自己选择 capability

---

## 9. Mini-program player UX contract

P0 小程序播放器采用移动学习模式，不复刻 Web 横屏课堂舞台。

四种模式：

- `classroom_mode`：老师字幕 + 当前 scene + 底部控制
- `whiteboard_mode`：白板全屏 + 分步讲解
- `quiz_mode`：题目优先，播放暂停
- `case_mode`：长文本输入 + rubric 反馈

P0 scene 建议：

- 60-150 秒
- 或 1 个核心知识点
- 或 1 个互动任务

`LessonQualityEvaluator` 必须把移动端可读性纳入 `interaction_quality`，或新增 `mobile_playback_quality` 子维度。

---

## 10. Whiteboard and simulation

白板共享的是 `WhiteboardIR`，不是 SVG renderer。

推荐路径：

```text
WhiteboardIR
  -> wx_canvas_renderer
  -> static_image_fallback
  -> pptx_vector_or_image_export
  -> html_svg_renderer
```

P0.5 招牌仿真必须是小程序原生仿真，不是任意 HTML simulation、iframe、WebView 或动态 JS。

```ts
type SimulationIR = {
  simulation_type: 'network_plan_critical_path'
  nodes: Array<Node>
  edges: Array<Edge>
  tasks: Array<Task>
  scoring_rules: Array<Rule>
  feedback_templates: Array<Feedback>
  platform_support: Array<'wx_miniprogram' | 'html_export'>
}
```

---

## 11. Mini-program source upload

小程序上传资料不能绕过 `SourceIngestionService`。

链路：

```text
wx.chooseMessageFile / wx.chooseMedia
-> POST /api/sources/upload-sessions
-> wx.uploadFile 或分片上传
-> SourceIngestionService
-> source_manifest_id / source_ingestion_id
-> POST /api/exam-classrooms/jobs
```

规则：

- 生成 job 不直接接收 raw file
- job 只能接收 `source_manifest_id` / `source_ingestion_id`
- 小程序上传资料默认 `private_study`
- 机构教研审核后才能升级到 `internal_training / commercial_course`
- 上传失败、解析失败、低置信度必须进入 `review_required`

---

## 12. Export in mini-program

小程序端不是正式导出的主要操作界面。

职责划分：

- `wx_miniprogram`：查看导出状态、触发轻量导出请求、获取分享链接、复制链接、查看 HTML 预览入口。
- Web/Admin：教研审核、PPTX/HTML/ZIP 正式导出、品牌模板设置、release notes、批量导出。

小程序端不要把“下载并本地打开 PPTX/ZIP”作为核心体验。

---

## 13. packageDeeptutor selective sync contract

`packageDeeptutor` 是宿主交付包，不是 `wx_miniprogram` 的 raw mirror。

建议维护 sync manifest：

```yaml
source: wx_miniprogram
target: yousenwebview/packageDeeptutor
include:
  - components/exam-classroom/**
  - pages/exam-classroom/**
  - services/exam-classroom/**
exclude:
  - app.ts
  - app.js
  - app.json
  - auth/**
  - billing/**
  - tenant-shell/**
host_adapters:
  auth: yousen_auth_adapter
  membership: yousen_membership_adapter
  points: yousen_points_adapter
  workspace: yousen_workspace_adapter
```

禁止整包覆盖 `packageDeeptutor`。

---

## 14. Mini-program Release Gate

P0 必须新增小程序 release gate：

- 微信开发者工具 smoke 通过
- iOS 真机 smoke 通过
- Android 真机 smoke 通过
- 弱网/断网/恢复后 job 状态可恢复
- app hide/show 后播放器状态不乱
- classroom payload 不超预算
- 首屏进入课堂不白屏
- 单 scene 渲染失败只降级当前 scene
- 音频失败自动字幕回退
- case 长文本输入不丢失
- quiz/case 提交后不会重复扣点
- `packageDeeptutor` selective sync smoke 通过

P0 One-click Generation Gate 增加小程序指标：

| 指标 | P0 合格线 |
| --- | --- |
| 小程序课堂首屏可交互时间 | <= 3 秒，弱网 <= 6 秒 |
| 课堂 payload 压缩后大小 | 建议 <= 500KB，超出则分页/懒加载 |
| 单 scene 切换耗时 | <= 500ms |
| 播放器 fatal error | 0 |
| 单 scene 降级成功率 | 100% |
| quiz/case 提交成功率 | >= 98% |
| 音频失败字幕回退成功率 | 100% |
| hide/show 后恢复成功率 | >= 95% |
| 小程序真机 smoke 覆盖 | iOS + Android |
| 宿主包 smoke | 100% |

---

## 15. 非目标

本 ADR 不解决：

- 完整 Web/Admin 后台设计
- 任意 HTML simulation 运行沙箱
- 多 Agent 动态课堂
- 多角色实时 TTS
- MP4 视频
- 小程序内直接编辑 PPTX / ZIP

---

## 16. 必测项

- `test_scene_runtime_core_has_no_dom_or_wx_dependency`
- `test_lesson_ir_rejects_raw_html_inline_script_iframe`
- `test_wx_renderer_consumes_scene_runtime_render_model`
- `test_html_export_consumes_scene_runtime_render_model`
- `test_pptx_export_consumes_scene_runtime_render_model`
- `test_wx_job_progress_polling_recovers_after_resume`
- `test_wx_job_events_deduplicate_by_seq`
- `test_wx_ws_reconnect_preserves_turn_trace`
- `test_wx_grounding_context_sent_as_metadata`
- `test_wx_does_not_append_lesson_ir_to_message_content`
- `test_wx_upload_creates_source_ingestion_before_generation`
- `test_package_deeptutor_sync_preserves_host_routes`
- `test_package_deeptutor_sync_preserves_membership_adapter`
- `test_package_deeptutor_sync_preserves_points_adapter`
