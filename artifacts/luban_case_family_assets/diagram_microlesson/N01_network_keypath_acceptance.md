# N01 网络计划关键线路 · schema-first proof 验收

- **日期**: 2026-06-17
- **产物**: `N01_network_keypath.json` → `render_network_card.py` → `N01_network_keypath.rendered.html`
- **定位**: 鲁班解释引擎的**硬能力样板**（数据驱动自动图解），区别于 F16 的"体验样板"。
- **状态**: schema-first proof **完成**；非产品化、非小程序接入、非量产。

## 1. 本轮目标

证明一条硬链路：**题目数据 → 自动画网络图 → 高亮关键线路 → 错因 → 复测**。
不是"画一个像网络图的图"，而是"由 activity/duration/dependencies 确定性地算出并验证关键线路与时差"。

## 2. 为什么第二张选网络计划关键线路

- F16 是"施工流程/构造剖面"，图是**固定模板**，不能证明"数据驱动自动成图"。
- 网络计划关键线路的核心业务事实是**计算**：紧前紧后 + 顺推逆推 → 总时差为 0 的线路。它逼迫引擎从 JSON 数据**自动布局节点/边并高亮关键路径**，这是 F16 模板做不到的硬能力。

## 3. schema 字段（template_type=network_plan_keypath）

| 字段 | 作用 |
|---|---|
| `question_data.activities[]` | `{id,label,duration}`，5-7 项 |
| `question_data.dependencies[]` | `{from,to}`，含 START/END，构成 DAG |
| `question_data.expected.critical_path` | 候选答案：关键线路节点序列 |
| `question_data.expected.project_duration` | 候选答案：总工期 |
| `question_data.expected.float{}` | 候选答案：每项 `total_float`/`free_float` |
| `explanation_steps[]` | `id/title/focus/script/evidence_refs`；focus∈{dependencies,early_time,late_time,critical_path} |
| `error_reveals[]` | `id/title/jump_step_id/script/correction_hint` |
| `practice` | `question/options/answer/review_step_id/correct_script/incorrect_script` |
| `authority.status` | `candidate_teaching_prototype`（诚实标注，不冒充官方） |

## 4. 数据如何生成网络图（确定性，无 LLM）

1. `build_graph()`：activities + START/END 建节点，dependencies 建有向边。
2. `topo_order()`：Kahn 拓扑排序（DAG，检测环）。
3. **rank 分列布局**：`rank(n)=max(rank(pred))+1` → x 按 rank 分列，y 按列内顺序排（"按层级 x、按路径 y"）。
4. `network_svg()`：先画边（带箭头 marker），再画节点（方框+工作名+工期）。

验收实测：节点 7（5 活动 + START/END），边 8（= dependencies 数）。

## 5. 如何高亮关键线路（来自数据，build 期校验）

- 关键线路**不由前端判断**：前端只读 JSON `expected.critical_path`，把"两端都在关键集合"的边标 `critical` class。
- build 期有独立确定性校验器 `compute_cpm()`（顺推 ES/EF、逆推 LS/LF、TF=LS−ES、FF）：
  - **校验** JSON 的 `expected`（critical_path / project_duration / 每项 float）必须与计算结果**逐一相等**，不等就 `raise`，渲染失败。
  - **派生** ES/EF/LS/LF 供"顺推/逆推"两步展示。
- 实测：关键边 4 条 = 开始→A→C→E→结束；总工期 10；非关键 B(总时差3/自由1)、D(总时差2/自由2)。

> 这是"硬能力"的关键：候选答案被独立 CPM 计算交叉验证过，不是手画了一条红线。

## 6. error_reveals 如何跳到对应解释步骤

点错因卡 → 跳到 `jump_step_id` 对应步骤 + 显示该错因专项讲解 + 顶部横幅纠正 + `dataset.activeError`。实测：
- "把最长单个工作误认为关键线路" → `highlight_critical_path`（并 focus-critical 高亮）；
- "只看工期不看逻辑关系" → `read_dependencies`；
- "混淆总时差和自由时差" → `backward_pass`。

## 7. practice 如何复测

四选一判断关键线路。答对 → 显示 `correct_script`、`dataset.practiceResult=correct`；答错 → 显示 `incorrect_script` 并跳回 `review_step_id`（highlight_critical_path）、`dataset.practiceResult=incorrect`。不写 learner state。

## 8. 单一权威边界

- **前端 renderer 不判断**：浏览器 JS 只做 step reveal / 错因跳转 / 复测反馈，零计算。
- **确定性校验器独立**：`compute_cpm()` 在 build 期跑，是校验器/派生器，可日后抽成独立编译器；它校验候选答案，不产生"官方评分口径"。
- **候选诚实标注**：`authority.status=candidate_teaching_prototype`，`source_refs` 标 `candidate_teaching_example`，不编造真题来源、不冒充官方 scoring key。
- **不接**：RAG / 前端 LLM / TTS / 音频 / 外链 / 小程序入口 / learner state / 真实评分。
- **不另起系统**：复用同一个 `diagram_microlesson` 目录与 `luban_diagram_microlesson.v1`，只新增一个 `template_type`，未抽通用大框架（窄 renderer 与 F16 并列，不互相重构）。

## 9. 本轮没做什么

- 没做漂亮 UI / 动画 / 拖拽 / Canvas / Remotion。
- 没做完整网络计划教学平台（双代号、时标网络、资源优化等都没做）。
- 没量产更多卡；没接小程序；没部署；没做学员验证。
- 没把前端变成计算器；没把候选 float 冒充官方采分。

## 10. 下一步如果要产品化，需要什么

1. 把 `compute_cpm()` 抽成**独立校验/编译器**，对所有网络计划卡做入库前自洽校验（register-before-use）。
2. 真题绑定：把 candidate 例子替换/补充为带 `source_ref` 的真题，并由上游签发。
3. 与 F16 一起进 3-5 人学员验证（见 `F16_qigu_product_validation_plan.md` 同款流程，换网络计划题）。
4. 验证通过后再考虑：第三个 template_type、最小模板 registry、HTTPS 发布 + 小程序 web-view 接入（见 `F16_qigu_wechat_webview_eval.md`）。

## 11. 验收结果

| 项 | 结果 |
|---|---|
| `json.tool` / `py_compile` | OK |
| build 渲染 | `activities=5 nodes=7 edges=8 critical_path=START-A-C-E-END duration=10 non_critical=[B,D]` |
| 节点数 = 活动 + START/END | 7 ✓ |
| 边数 = dependencies | 8 ✓ |
| 关键线路边带 critical class | 4（开始→A→C→E→结束）✓ |
| 至少一个非关键工作 total_float>0 | B(TF3/FF1)、D(TF2/FF2) ✓ |
| 错因卡跳对应解释步骤 | longest→critical / ignore→deps / confuse→backward ✓ |
| 复测答错跳 review_step_id | highlight_critical_path ✓ |
| 复测答对反馈 | ✓ |
| 390px 无横向滚动 | scrollWidth=390 ✓ |
| 触摸区 ≥44px | step52 / opt48 / err63 / ctrl46 ✓ |
| 无外链 / 无音频 | ✓ |
| 学生 UI 无 source_ref/schema/renderer/candidate 等内部词 | ✓ |

验收方式：`json.tool` + `py_compile` + build 渲染 + `rg` 外链扫描 + 纯 CDP（Node 原生 WebSocket 驱动 Chrome，零依赖）DOM 断言 + 截图。
