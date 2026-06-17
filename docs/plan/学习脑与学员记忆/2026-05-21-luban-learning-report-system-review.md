# 鲁班智考学情模块系统审查报告

> Status: **Review v1 / Optimization Backlog Proposed**
>
> Date: 2026-05-21
>
> Scope: 微信小程序 / 佑森 WebView 学情页、`learning-report-read-model`、Learning Brain、learning evidence 写入、typed graph、错题复盘与下一步训练。
>
> Related:
> - [2026-04-15-learner-state-memory-guided-learning-prd.md](2026-04-15-learner-state-memory-guided-learning-prd.md)
> - [2026-05-18-luban-learning-brain-gbrain-absorption-prd.md](2026-05-18-luban-learning-brain-gbrain-absorption-prd.md)
> - [2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md](2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md)
> - [2026-05-20-luban-learning-report-read-model-execution-plan.md](2026-05-20-luban-learning-report-read-model-execution-plan.md)

---

## 1. 一句话结论

学情模块的底层方向是正确的：已经从多个旧接口拼页面，收敛到 `GET /api/v1/mobile/learning-report`，并以 `learner_memory_events.learning_evidence` 作为完成数和 Learning Brain 的核心证据来源。

但它还没有达到“最重要板块”的产品完成度。当前系统更像一个技术正确的学习事实看板，还不是一个让学员一眼看懂、愿意每天回来看、能直接驱动下一轮训练的学习操作系统。

最关键的缺口有四个：

1. 证据还没有真正成为可点击、可复盘、可收藏、可追踪的“答题记录”。
2. 错题集现在只是 `wx.setStorageSync` 本机缓存，不是后端 learning authority。
3. “下一步训练”还没有把 concept / error / attempt / graph chain 带入真实出题入口。
4. `wx_miniprogram` 与 `yousenwebview/packageDeeptutor` 两套学情页能力已经发生漂移。

---

## 2. 审查目标

本次审查把学情模块作为一个系统，而不是单页 UI 或单个接口。

学情模块应回答学员的三个核心问题：

1. **我最近学得怎么样？**
   - 今天做了几题，近 3 天有没有练，正确率和掌握度有没有可信变化。

2. **我到底错在哪里？**
   - 哪道题、什么时间、我选了什么、正确答案是什么、为什么错、对应哪个知识点 / 采分点 / 易错点。

3. **我下一步应该做什么？**
   - 先练哪个知识点，为什么练它，练几题，练完后是否改善。

系统级目标不是“展示 Learning Brain 的内部结构”，而是把 Learning Brain 编译成学员能直接理解和行动的学习轨迹。

---

## 3. 当前系统地图

### 3.1 Canonical Data Flow

```text
出题 / 作答 / 批改
  -> construction_grading.writeback.write_grading_error_events
  -> learner_memory_events(memory_kind=learning_evidence)
  -> learning_synthesis.synthesize_learning_truth
  -> learning_brain_read_model.build_learning_brain_read_model
  -> learning_report_read_model.build_learning_report_read_model
  -> GET /api/v1/mobile/learning-report
  -> wx_miniprogram / yousenwebview 学情页
```

### 3.2 当前 Authority Map

| 业务事实 | 当前 authority | 审查判断 |
| --- | --- | --- |
| 今日完成 / 近 3 天完成 | `learner_memory_events.learning_evidence` | 正确，已避免旧 `daily_practice_counts` 误导 |
| 作答证据 | `learning_evidence.payload_json` | 方向正确，但缺 detail API / 点击回放 / 收藏 authority |
| 当前可信结论 | `learner_summaries.summary_structured_json.learning_brain`，缺失时 dry-run synthesis | 正确，但前端“当前可信结论”容易混入单次观察 |
| typed graph | `learning_synthesis.project_learning_graph` projection | 正确，但用户侧表达还应再产品化 |
| 掌握度 | `learning-report-read-model` 聚合旧 mastery + evidence cap | 已比 100% 粗暴算法好，但仍不够精细 |
| 错题集 | 当前 `yousenwebview` 本机 storage | 不合格，不能作为正式产品能力 |
| 下一步训练 | read model 文案 + `goPractice()` 泛跳转 | 不合格，行动链路没有带上训练意图 |

---

## 4. 已经做对的部分

### 4.1 Read Model 收权方向正确

`deeptutor/services/learner_state/learning_report_read_model.py` 已经把多个旧输入源收敛成统一 response：

- `overview`
- `progress_feedback`
- `mastery`
- `radar_dimensions`
- `learning_brain`
- `learner_facing`
- `next_training`
- `source_status / degraded / freshness`

这符合 `thin wrappers, fat skills`：页面不应自己拼学情事实。

### 4.2 近 3 天完成数口径正确

当前完成数来自 `learning_evidence` attempt 事件，并区分：

- `attempt_count`
- `today_done`
- `recent_three_done`
- `unique_question_count`
- `today_unique_questions`
- `recent_three_unique_questions`

这解决了“刚做了很多题但近 3 天显示 0”的根因方向。

### 4.3 掌握度已加入低样本保护

`_calibrated_mastery()` 已经避免“一题答对显示 100% 掌握”。这比之前直接把单题正确映射成 100% 更稳。

但这只是第一层保护，不代表掌握度算法已经成熟。

### 4.4 机器码可读性已有明显改善

当前 read model 和页面侧已经开始把：

- `M06 / M07`
- `1A432000`
- `question_tests_concept`
- `practice / ...`
- event hash

转成中文标签或隐藏。这是正确方向。

### 4.5 自动化基线通过

本次审查实际执行：

```bash
pytest -q tests/services/learner_state/test_learning_report_read_model.py tests/services/learner_state/test_learning_brain_read_model.py
node yousenwebview/tests/test_report_snapshot_dedupe.js
node wx_miniprogram/tests/test_report_learning_brain.js
```

结果：

- 后端 Learning Report / Learning Brain：`29 passed`
- `yousenwebview` 学情页：`49 assertions passed`
- `wx_miniprogram` 学情页：`PASS`

---

## 5. P0 缺口：必须优先解决

### P0-1. 错题集不是后端能力，只是本机缓存

现状：

- `yousenwebview/packageDeeptutor/pages/report/report.js` 使用 `wx.getStorageSync / wx.setStorageSync`
- UI 显示为“我的错题集”
- 后端 Learning Brain、nightly synthesis、learner state 完全不知道收藏行为

问题：

- 换手机、清缓存、重装小程序会丢。
- 无法跨端同步。
- 无法进入 nightly synthesis。
- 无法作为下一题训练和错题复习的 authority。
- 名称“我的错题集”会让用户以为这是正式云端能力。

建议：

1. 如果短期不做后端，必须改名为“本机错题收藏”，降低承诺。
2. 正式方案应新增后端 `mistake_book` authority：
   - `POST /api/v1/mobile/mistake-book/items`
   - `DELETE /api/v1/mobile/mistake-book/items/{attempt_key}`
   - `GET /api/v1/mobile/mistake-book`
   - 保存 `user_id / attempt_key / event_id_ref / question_id / saved_at / tags / note / archived_at`
3. `learning-report-read-model` 返回错题收藏状态，前端不再独立判断。

### P0-2. 证据流还不能真正点击回到“当时作答记录”

现状：

- `learner_facing.recent_attempts` 已包含题干、选项、用户答案、正确答案、解析摘要。
- `yousenwebview` 可以弹 modal 查看详情。
- 但这不是一个可定位的答题记录详情页或详情接口。

问题：

- 证据卡没有稳定后端 detail endpoint。
- 无法完整展示当时的题卡、用户选择、系统解析、知识库证据、RAG 命中、trace。
- 证据流与历史记录 / 聊天 turn / active question 没有可点击闭环。
- 用户无法从“我薄弱”直接钻到“我当时到底哪里错了”。

建议新增 `attempt-detail-read-model`：

```text
GET /api/v1/mobile/learning-attempts/{attempt_key}
```

返回：

- 题干、题型、选项、正确答案、用户答案
- 是否正确、得分、采分点命中
- 每个选项解析 / 案例题评分点解析
- 错因、知识点、采分点、教材或规范证据
- 关联聊天 turn / trace / RAG refs
- 是否已收藏错题
- 下一步训练入口参数

### P0-3. “下一步训练”没有带着 Learning Brain 意图进入出题链路

现状：

- `learning_report_read_model._next_action_card()` 生成了“先做 3 道某章节专项题”的文案。
- 前端 `goPractice()` 只是跳到通用练习页：
  - `wx_miniprogram/pages/report/report.js`：`/pages/practice/practice`
  - `yousenwebview/packageDeeptutor/pages/report/report.js`：`route.practice()`

问题：

- 用户点“开始训练”后，系统可能不知道要练哪个 concept / error / question pattern。
- typed graph 的 `错因 -> 训练 -> 改善/未改善` 没有转成真实 route 参数或出题请求。
- 学情页与出题页之间没有 action contract。

建议：

定义 `LearningTrainingIntent`：

```jsonc
{
  "source": "learning_report",
  "intent_id": "...",
  "concept_id": "1A432000",
  "concept_label": "工程招标投标与合同管理",
  "error_code": "M06",
  "error_label": "多选漏选",
  "attempt_refs": ["attempt-..."],
  "training_mode": "case_repair | mcq_discrimination | rubric_recall",
  "question_count": 3,
  "difficulty": "adaptive"
}
```

前端点击下一步训练时，把 intent 传给练习页或聊天页，由 `deep_question` 消费，而不是泛跳转。

### P0-4. wx 与 yousen 两套学情页能力不一致

现状：

- `yousenwebview/packageDeeptutor/pages/report` 已有更丰富的：
  - 真实作答证据
  - 查看当时解析
  - 收藏错题
  - 我的错题集
- `wx_miniprogram/pages/report` 仍是较早版本：
  - 最近做题复盘
  - 系统判断
  - 依据来自哪些作答
  - 下一步训练
  - 但没有同等的错题收藏 / detail 交互

问题：

- 双壳层产品体验漂移。
- 测试通过不代表两个真实入口体验一致。
- 后续修 bug 容易只修其中一个 surface。

建议：

1. 明确未来主入口是 `yousenwebview/packageDeeptutor` 还是 `wx_miniprogram`。
2. 抽一个 shared report view-model module，两个壳层只做薄渲染。
3. 双端测试必须共享同一组 fixture：
   - 空态
   - 单题答错
   - 同题二刷
   - 一题答对但低样本
   - 有错题收藏
   - degraded source

### P0-5. “当前可信结论”容易混入单次观察

现状：

- `learner_facing.diagnoses` 会直接从最近 events 聚合。
- 单次错题也可能出现在“当前可信结论”区，只是标成“刚发现”。

问题：

“当前可信结论”这个标题本身暗示稳定判断，但单次错题只能叫“最近观察”。这会削弱 evidence-first memory 的可信度。

建议 UI 和 schema 分层：

- `stable_truths`：L1/L2/L3，显示在“当前可信结论”
- `recent_observations`：L0，显示在“最近作答观察”
- `conflicts_or_needs_confirmation`：冲突或待确认，显示在“还需要验证”

---

## 6. P1 缺口：应作为下一轮系统优化

### P1-1. 掌握度算法仍然偏粗

当前 `_calibrated_mastery()` 做了低样本 cap，但还没有充分考虑：

- 题目难度
- 单选 / 多选 / 案例题权重
- 章节覆盖率
- 最近性衰减
- 连续答对的稳定性
- 同一题反复刷的权重折扣
- 错因严重度
- 人工确认

建议升级为 `MasteryEstimator`：

```text
mastery = coverage_weight
        * difficulty_weight
        * recency_weight
        * correctness_signal
        * evidence_confidence
```

并输出置信区间：

- `mastery_point`
- `confidence`
- `sample_count`
- `coverage_ratio`
- `status: insufficient_evidence | emerging | stable`

### P1-2. 作答解析质量依赖上游写入，read model 只能被动展示

`learning_report_read_model` 只能从 payload 中读取：

- `explanation`
- `analysis`
- `solution`
- `answer_analysis`
- `system_explanation`
- `grading_explanation`
- `feedback`
- `summary`

如果批改链路没有把高质量解析写入 `learning_evidence`，学情页只能展示空洞解释。

建议把答后解释写入 schema 明确化：

```jsonc
{
  "explanation": {
    "summary": "...",
    "why_user_wrong": "...",
    "option_analysis": [
      {"option": "A", "judgement": "wrong", "reason": "..."}
    ],
    "knowledge_points": ["..."],
    "common_traps": ["..."],
    "memory_anchor": "...",
    "next_time_rule": "..."
  }
}
```

read model 只做投影，不在页面层拼教学解释。

### P1-3. Evidence refs 还没有转成学员可理解来源

`learning_evidence.payload_json.evidence_refs` 已有：

- `grading_result`
- `active_question`
- `answer_history`
- `trace`
- `rag_evidence`

但前端展示更多是“第 N 条批改证据”或作答摘要，没有形成学员可理解的来源层：

- “来自你今天 09:20 的作答”
- “来自《建筑实务》防水工程知识点”
- “来自本题标准答案解析”
- “来自老师人工修正”

建议 read model 输出 `evidence_sources_display`，分为：

- 作答记录
- 标准解析
- 知识库依据
- 人工修正
- 训练结果

### P1-4. Nightly synthesis 与在线 read model 的边界还需更清楚

当前 read model 在 compiled truth 缺失时会 dry-run synthesis，这对即时可见有价值。

但产品上应区分：

- “刚刚做完题的即时观察”
- “夜间整理后的稳定判断”

建议：

- 页面显示 `last_synthesized_at`
- 标记“刚刚生成 / 已夜间整理”
- stable truth 必须来自 persisted compiled projection 或人工确认
- dry-run 只展示在“即时观察”区，不伪装成长期结论

### P1-5. 页面信息结构仍然偏工程视角

当前模块名称包括：

- 学习大脑
- 当前可信结论
- 真实作答证据
- 证据流
- 训练闭环
- 下一步训练

概念是对的，但用户不一定理解“证据流”和“训练闭环”。

建议重构为用户语言：

1. **今天复盘**
   - 今天做了几题，近 3 天练了几次，最常错什么。

2. **我错在哪**
   - 按真实题目卡展示，每张卡可点开。

3. **为什么这样判断**
   - 简短列出 2-3 条证据，不堆技术链路。

4. **下一步练什么**
   - 一个主 CTA + 2 个备选训练。

5. **我的错题**
   - 云端错题集，支持继续练 / 标记已掌握 / 取消收藏。

---

## 7. P2 缺口：数据飞轮与运营能力

### P2-1. 老师 / 运营侧还缺学习事实审计入口

需要能看：

- 某个学员为什么被判断为“主体结构多选漏选”
- 哪些证据支持
- 哪些证据冲突
- 最近是否改善
- 是否需要人工修正

### P2-2. 错题与题库资产没有反向闭环

当大量学员在同一 knowledge point / error_code 上错，应反推：

- 题库覆盖不足
- 解析不够好
- rubric 模糊
- 训练路径需要改

### P2-3. 还没有真正的学习干预实验

学情页的价值需要用指标验证：

- 进入学情页后下一次练习转化率
- 点击“下一步训练”后的完成率
- 错题收藏后复习率
- 同一错因 3 天后的改善率
- 学员是否觉得“看懂了自己错在哪”

---

## 8. 推荐下一步执行顺序

### Phase A：证据详情与错题集收权（P0）

目标：让每条证据都能点开，错题集成为后端能力。

交付：

1. `GET /api/v1/mobile/learning-attempts/{attempt_key}`
2. `GET/POST/DELETE /api/v1/mobile/mistake-book`
3. `learning-report-read-model` 返回 `attempt_refs` 与 bookmark 状态。
4. 双端学情页点击证据卡进入详情。
5. e2e：作答错误 -> 学情出现证据 -> 点开详情 -> 收藏错题 -> 刷新仍存在。

### Phase B：下一步训练 Intent 闭环（P0）

目标：学情页不是报告终点，而是下一轮练习入口。

交付：

1. 定义 `LearningTrainingIntent` schema。
2. 学情页 CTA 带上 concept/error/attempt refs。
3. `deep_question` 消费 intent 并优先出对应训练题。
4. 后续批改写回 `training_improved_error` 或 `training_not_improved_error`。

### Phase C：双端 ViewModel 统一（P0/P1）

目标：wx 与 yousen 不再各写一套学情理解。

交付：

1. 抽 shared normalizer / view model。
2. 双端只负责渲染。
3. 同一 fixture 驱动两端测试。

### Phase D：掌握度模型升级（P1）

目标：从“正确率 + cap”升级到“证据充分度 + 章节覆盖 + 难度 + 最近性”。

交付：

1. `MasteryEstimator`
2. `sample_count / coverage_ratio / confidence`
3. UI 不再只显示百分比，而显示“证据不足 / 正在形成 / 稳定掌握”。

### Phase E：学情页信息架构重做（P1）

目标：页面从工程看板变成学员学习复盘。

建议第一屏：

```text
今天复盘
- 今天做了 N 题
- 近 3 天 N 次练习
- 当前最该补：主体结构 / 多选漏选

我错在哪
- 题目卡 1：你选 A，正确 B，错因是...
- 题目卡 2：...

下一步
- 先做 3 道主体结构多选辨析题
```

---

## 9. Release / 验收建议

学情模块以后每次发布必须至少跑这 8 个场景：

1. 新用户无记录：不显示假掌握，不显示假弱点。
2. 单题答错：出现最近作答观察，但不升级为稳定结论。
3. 同题二刷：attempt=2，unique=1。
4. 单题答对：不显示 100% 掌握。
5. 多题同错因：升级为重复薄弱点。
6. 点下一步训练：进入对应 concept/error 的训练，不泛跳。
7. 收藏错题：刷新、重登、换端仍存在。
8. 训练后改善：Learning Brain 显示“已改善”，不继续压在薄弱点里。

上线观察：

- `/api/v1/mobile/learning-report` p95 < 800ms
- 5xx < 0.1%
- degraded < 1%
- 学情页旧接口 RPS 连续 7 天为 0
- “下一步训练”点击后完成率进入 BI
- 错题收藏后 7 天内复习率进入 BI

---

## 10. 当前风险判断

| 风险 | 等级 | 判断 |
| --- | --- | --- |
| 错题集本机缓存造成用户数据丢失 | P0 | 必须收权或降级文案 |
| 下一步训练泛跳导致 Learning Brain 不驱动教学 | P0 | 必须定义 training intent |
| 双端学情体验漂移 | P0 | 必须统一 view model |
| 单次观察被误读成可信结论 | P0 | 必须拆 stable truth / observation |
| 掌握度仍过粗 | P1 | 需要 estimator 升级 |
| 解析质量取决于上游 payload | P1 | 需要 grading explanation schema |
| 生产 14 天观察未完成 | P1 | 不应宣称 Done |

---

## 11. 最终建议

不要继续在页面上堆更多 Learning Brain 内部字段。下一轮优化应做减法和收权：

1. 把“证据”变成可点击的真实作答记录。
2. 把“错题集”变成后端 authority。
3. 把“下一步训练”变成可执行 intent。
4. 把“当前可信结论”拆成稳定结论和单次观察。
5. 把 wx / yousen 两套页面收敛到同一 view model。

做到这五点，学情模块才会从“技术上能展示学习事实”，升级为“学员真正能看懂、能行动、能持续变好”的核心产品板块。
