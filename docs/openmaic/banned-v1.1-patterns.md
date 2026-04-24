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

## 8. Source / quality

禁止：

- 生成器创建未注册 citation
- citation 指向不在 `source_manifest` 的 source
- `web_unverified / unknown / forbidden` 源进入 `published`
- 未通过 legal review 的内容做公开/商业导出
- 用人工审核替代 `LessonQualityEvaluator`
- 用一个总分掩盖重大事实错误
- `LessonQualityEvaluator` 直接修改 `lesson_ir`

## 9. Frontend surface

禁止：

- 把 Web-only player 当作 P0 学员端交付完成
- 先实现 Web player，再把微信小程序当二期适配
- 在 Web player 和微信小程序 player 之间维护两套 scene 解释器
- 覆写 `yousenwebview/packageDeeptutor` 的宿主路由、登录、会员、点数或 workspace shell 适配
- 把 HTML export 误当成 Web 主产品表面
- 把 React 组件当作跨端共享核心
- 在 `lesson_ir` 里嵌入 raw HTML、inline script、iframe、external CSS
- 通过 WebView/iframe 承载 P0 课堂播放器
- 把小程序稳定消费浏览器式 EventSource 当成 P0 依赖

## 10. 使用方式

PR review 中只要出现上述任一模式，默认打回，除非先新增 ADR 并通过架构评审。
