# Banned v1.1 Patterns

以下模式来自 v1.1 时代的冲突设计，当前一律禁止进入新实现。

## 1. Transport

禁止：

- `/api/exam-classrooms/{id}/ask` 作为 streaming endpoint
- 新增第二条课堂聊天 WebSocket
- SSE 承担聊天 token stream
- 播放器本地维护第二套 pending turn 状态

## 2. Data authority

禁止：

- `classroom_scenes` 作为 primary table
- `classroom_actions` 作为 primary table
- `exam_questions` 作为 primary table
- projection 表反写 `lesson_ir`
- exporter 直接修 `lesson_ir`
- reviewer 直接修 `lesson_ir`

## 3. Status

禁止：

- `scene.review_status` 作为发布状态机
- `approved / needs_review / rejected` 作为 scene 顶层生命周期
- `review_items.status` 直接等于课堂发布状态
- 为 job 新增第二套 warning 状态机

## 4. Naming

禁止：

- `course.json`
- `exam_courses`
- `TeachStudio`
- `course / classroom` 在 API、表名、schema 名里并行表达同一业务事实

## 5. Learner-state

禁止：

- 互动课堂模块直接写 `user_stats`
- `weak_tags` 直接当长期薄弱点真相
- 错题本、掌握度表成为第二套 learner truth

## 6. Capability / routing

禁止：

- 在 P0 里新增 `exam_classroom` first-class capability
- 在 router 或 adapter 里偷偷做 capability selection
- 未注册 request schema 的 public config 直接上线

## 7. P0 范围漂移

禁止把以下内容重新拉回 P0 blocker：

- 课堂内自由问答
- 多角色 TTS
- 动态 AI 同学追问
- PBL
- 交互仿真
- MP4
- Script / DOCX 导出

## 8. 使用方式

PR review 中只要出现上述任一模式，默认打回，除非先新增 ADR 并通过架构评审。
