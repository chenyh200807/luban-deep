# F16 屋面卷材防水起鼓割补 · 图解母题卡 v0.2 验收报告

- **日期**: 2026-06-17
- **范围**: 同一个 `diagram_microlesson` 入口；无第二套 schema / renderer / 目录
- **产物**: `F16_qigu.json` → `render_card.py` → `F16_qigu.rendered.html`

## 1. 本轮目标

把"有旁白的图解卡"升级为**错因驱动的图解微课闭环**：

> 看图 → 听老师讲 → 点错因 → 跳到对应工序 → 老师专项解释为什么错 → 做复测题 → 按对错跳回关键步骤并解释 → 知道下次怎么写。

不是堆功能，重点是"像老师讲"，并把视觉卡与旁白卡**合并成一个闭环**。

## 2. 改了哪些文件

| 文件 | 改动 |
|---|---|
| `SCHEMA.md` | 登记 `authority.student_boundary`、`narration.opening`、`narration.error_reveals[]`、`narration.practice_feedback`；登记断言钩子与学生端不泄漏规则 |
| `F16_qigu.json` | 写入上述字段；把 reinforcement_layer 的 `why` 从内部口吻改为学生口吻 |
| `render_card.py` | 校验新字段；客户端 data/narration 脱敏；旁白引擎重写（opening 时间线 + narrMode + 错因/复测/手动联动）；底部"考试依据"去 raw source_ref/artifact；采分表/侧栏去内部词；顶栏去 dev 术语 |
| `F16_qigu.rendered.html` | 重新生成 |
| 截图 PNG | 重新生成 3 张 + 新增 2 张 |
| `F16_qigu_v0_2_acceptance.md` | 本报告 |

## 3. schema 新增字段

```jsonc
"authority": { "student_boundary": "面向学生的考试依据边界说明(无 source_ref / 母题包 / P 编号)" }
"narration": {
  "opening": { "seconds": 6-8, "script": "..." },
  "error_reveals": [
    { "error_id": "命中 common_errors.id", "jump_step_id": "命中 steps.id",
      "seconds": 5-8, "script": "为什么这类答案丢分", "correction_hint": "一句话纠正(进横幅)" }
  ],
  "practice_feedback": { "correct_script": "...", "incorrect_script": "..." }
}
```

约束（renderer 校验，先登记再消费）：`opening.seconds` 6-8；`error_reveals[].error_id` 必须命中 `common_errors`、`jump_step_id` 必须命中 `steps`、`seconds` 5-8、`script`+`correction_hint` 非空；`practice_feedback` 两条 script 非空；`review_step_id` 复用 `practice.review_step_id`，不重复登记。

## 4. 学生端体验链路

1. **看图**：移动端聚焦剖面大图，默认高亮"识别起鼓"（`identify_bulge`）。
2. **听老师讲**：点"▶ 听老师讲 82 秒"→ 先放 `opening`（讲学习目标，保持 step1 高亮）→ 自动从 step1 讲到 step8，字幕在图下方逐步切换，SVG 图层同步高亮，可暂停/继续。
3. **点错因**：点任一错因卡 → 暂停自动旁白 → 跳到对应工序 → 图下方字幕给出**这类答案为什么丢分**的专项讲解 → 顶部横幅同步"你刚点的是「…」，真正漏的是「…」+ 一句纠正"。
4. **做复测题**：
   - 答对 → 字幕讲清"你抓住了哪个核心得分逻辑"；
   - 答错 → 跳回 `review_step_id`（附加层）→ 字幕讲清"你漏的是哪一层闭环"。
5. **手动翻步**：点步骤标签/上一步下一步 → 自动旁白暂停 → 字幕显示该步的普通讲解。

每个状态都暴露给 DOM：`dataset.narrPlaying / narrIndex / narrMode / activeError / activeLayer`。

## 5. 单一权威边界

- **renderer 不判分**：只做确定性渲染（step reveal、字幕定时、图层高亮、跳转），不计算对错、不生成采分点。
- **narration 不前端生成**：所有旁白文本来自 `F16_qigu.json` 的 `narration`，绑定 `step_id`/`error_id`；无 TTS、无音频、无外链、无前端 LLM。
- **教学步骤不冒充采分点**：`exam_binding.kind` 区分 `signed_candidate`（候选采分点）与 `teaching_step`（教学理解步骤）；候选采分点仍只来自 P10/P11 + source_ref，本轮未新增任何采分点或规范数值。
- **source_ref 不暴露给学生**：客户端 data 剥离 `source_refs`/`score_point_id`；采分表、侧栏"这一步算不算分"、底部"考试依据"均改为学生语言；raw source_ref / artifact id 只留在 HTML 注释（内部 provenance）。
- **单一入口**：未新增第二套 schema / renderer / 目录；未引入 OpenMAIC。

## 6. 验收结果

| 项 | 结果 |
|---|---|
| render 输出 | `steps=8 scoring_points=2 errors=4 practice=yes` ✓ |
| `json.tool` / `py_compile` | OK ✓ |
| 外链/音频扫描（http/cdn/@import/img/script src/link/mp3/wav/audio） | 空 ✓ |
| 学生端内部词扫描（source_ref/母题包/母题/P10/P11/本系统/schema/SVG renderer/WebView/LLM，排除 HTML 注释与 JS 代码注释） | 无 UI 泄漏 ✓ |
| 390px `scrollWidth===390` | ✓ |
| 默认 `activeLayer===identify_bulge` | ✓ |
| 点播放：`narrPlaying=true`、先 opening 再 step1 | ✓（index0=opening→index1=step1） |
| 自动推进：narrIndex 前进、activeLayer 同步 step_id、字幕变化 | ✓（index2→cut_bulge） |
| 暂停：`narrPlaying=false`、narrIndex 稳定 | ✓ |
| 错因 missing_reinforcement：layer=reinforcement_layer、hash=#step=6、narrMode=error、activeError=missing_reinforcement、字幕专项解释 | ✓ |
| 复测答错：narrMode=practice_incorrect、layer=review_step、字幕解释为什么错 | ✓ |
| 复测答对：narrMode=practice_correct、字幕解释为什么对 | ✓ |
| 手动 step tab：自动旁白暂停、narrMode=manual_step | ✓ |
| 触摸区 ≥44px：step-tab 52.75 / option 52 / play 46 / error-card 75 | ✓ |
| 无 AI-agent-owned Next dev | ✓ |

验收方式：`render_card.py` + `json.tool` + `py_compile` + `rg` 外链扫描 + 纯 CDP（Node 原生 WebSocket 驱动 Chrome，零依赖）做 DOM 断言与截图。

## 7. 仍未做的事（本轮不该做）

- **未接 TTS**：仍是字幕式旁白（按约束）。
- **未接真实小程序 WebView**：仍是静态 HTML 评估件。
- **未接真实母题包生产流水线**：authority 仍是固定候选工件。
- **未接真实学生作答数据**：复测题与错因为静态训练，不写 learner state。

## 8. 下一步建议

1. **接母题包/判分工件签发**：让 `authority` 与候选采分点由上游签发驱动，而不是手填。
2. **错因来源对齐 E 系列错因 taxonomy**：`error_reveals` 与 canonical 错因码对齐，便于跨卡复用。
3. **小程序 WebView 真机回归**：在微信开发者工具里验证自动播放、触摸、字幕换行。
4. **铺第二张卡前先抽 renderer 公共部分**：当 2-3 张卡稳定后，再考虑把 narration 引擎与 CSS 收敛为复用模板（现在不做，避免过早抽象）。
5. **TTS 预留**：narration 已是结构化文本 + 时长，将来接 TTS 只需把字幕时长换成音频时长，不必改数据结构。
