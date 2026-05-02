# PRD：鲁班智考 Assessment Blueprint（世界级摸底测评蓝图）

## 1. 文档信息

- 文档名称：鲁班智考 Assessment Blueprint PRD
- 文档路径：`docs/plan/2026-05-02-luban-assessment-blueprint-prd.md`
- 创建日期：2026-05-02
- 状态：Phase 0 implemented（coverage audit 已落地；生产 create/submit 链路尚未改造）
- 适用范围：微信小程序 assessment / report / profile、Supabase `questions_bank`、Learner State、Teaching Policy Layer、TutorBot 个性化教学
- 关联文档：
  - [2026-04-15-learner-state-memory-guided-learning-prd.md](2026-04-15-learner-state-memory-guided-learning-prd.md)
  - [2026-04-20-luban-adaptive-teaching-intelligence-prd.md](2026-04-20-luban-adaptive-teaching-intelligence-prd.md)
  - [2026-04-20-teaching-methods-matrix-prd.md](2026-04-20-teaching-methods-matrix-prd.md)
  - [../openmaic/ADR-006-supabase-knowledge-base-reuse.md](../openmaic/ADR-006-supabase-knowledge-base-reuse.md)

## 2. 一句话结论

鲁班智考的摸底测试不应再是“从硬编码题库取 20 道题”的页面功能，而应升级为一个版本化的 `Assessment Blueprint`：

> 用 Supabase `questions_bank` 作为题目资产 authority，用蓝图决定抽样、题量、计分与画像维度，用 Learner State 承接结果，用 Teaching Policy 把结果转成下一步教学动作。

世界级测评不是题更多，而是：

1. 题目来源可信
2. 覆盖结构可解释
3. 计分口径稳定
4. 心理与习惯信号不滥用
5. 结果能直接改变教学策略
6. 每次短缺、降级、偏差都能被 release gate 抓住

## 2.1 2026-05-02 当前 Supabase 只读核验

本 PRD 不是只引用旧快照。2026-05-02 对当前 `.env` 指向的 Supabase `questions_bank` 做了一次只读聚合核验，只输出数量，不读取或暴露题目正文：

| 指标 | 当前值 | 对 PRD 的影响 |
| --- | ---: | --- |
| `questions_bank` 总量 | 4638 | 足够支撑 20 题冷启动测评，但必须按蓝图分桶审计，不能只看总量 |
| `single_choice` | 1674 | 可作为第一版主力题型 |
| `multi_choice` | 978 | 可稳定纳入第一版 |
| `case_study` | 1961 | 资产充足，但移动端第一版应先做 mini case / structured judgment |
| `calculation` | 15 | 数量偏少，不能设为硬配额；第一版只能作为可选增强 |
| `REAL_EXAM` | 1050 | 可作为高权重来源，但需保留版权/授权边界 |
| `TEXTBOOK` | 1601 | 可作为概念与基础题来源 |
| `TEXTBOOK_ASSESSMENT` | 687 | 可作为练习题来源 |
| `node_code` 缺失 | 105 | 可接受，但 coverage gate 必须列出未归类题 |
| `source_chunk_id` 缺失 | 3320 | 第一版 provenance 硬要求应是 `questions_bank.id`；`source_chunk_id` 只能作为增强证据 |

因此，本文后续所有“来源可追溯”在 P0 的最低含义是：

- scored item 必须有稳定 `questions_bank.id`
- 能提供 `source_chunk_id / exam_year / grading_keywords / source_meta` 时必须保留
- 不得把 `source_chunk_id` 作为 P0 的唯一必填来源字段，否则会把大量现有题库资产误判为不可用

## 3. Root Cause 与设计门槛

### 3.1 当前真正的问题

前一次摸底缺陷暴露出的根因不是按钮文案，而是 `assessment count authority` 漂移：

- 欢迎页承诺 20 题
- 后端可能短交付
- 前端提交校验曾经按另一个题量口径提示未答
- 诊断报告把默认 0 分章节与真实测量结果混在一起

这说明 assessment 目前缺少一个明确的蓝图 authority。

### 3.2 Single Authority Hard Gate

本 PRD 的五个硬门槛：

1. `one business fact`
   - 一次摸底必须完整、可信地回答：这个学员当前的知识水平、错因倾向、学习习惯和教学偏好是什么。

2. `one authority`
   - 题目资产 authority：Supabase `questions_bank`
   - 测评编排 authority：`AssessmentBlueprintService`
   - 作答会话 authority：`assessment_sessions`
   - 长期画像 authority：Learner State / `user_profiles` / `user_stats` / `user_goals`
   - 教学动作 authority：Teaching Policy Layer

3. `competing authorities`
   - 硬编码 `_ASSESSMENT_BANK`
   - 前端固定写死 20 题承诺
   - report 页面自行推断画像
   - TutorBot prompt 根据散落字段自行判断学习偏好

4. `canonical path`
   - `questions_bank` + profile probe bank -> `AssessmentBlueprintService` -> `assessment_sessions` -> submit scoring -> learner writeback -> report projection -> Teaching Policy

5. `delete or demote`
   - `_ASSESSMENT_BANK` 降级为本地开发 fallback，不再是生产 authority
   - 前端只展示后端返回的 `blueprint_version / delivered_count / sections`
   - report 不直接重算长期画像，只读 assessment profile projection

## 4. 非目标

第一版不做：

1. 临床心理测评、心理健康诊断、人格标签化
2. 新建第二套题库管理后台
3. 绕过 `questions_bank` 重新上传一套 assessment 专用题库
4. 把心理/习惯题混进知识得分分母
5. 用 LLM 即兴生成正式摸底题并直接计分
6. 用一次摸底永久锁死学员画像

## 5. 蓝图总结构

默认 `diagnostic_v1` 采用 20 个可见测评单元：

| Section | 数量 | 是否计入知识分 | Authority | 用途 |
| --- | ---: | --- | --- | --- |
| 知识能力题 | 14 | 是 | Supabase `questions_bank` | 估计章节掌握度、题型掌握度、错因入口 |
| 案例/综合判断题 | 2 | 是 | Supabase `questions_bank` | 检查应用能力、边界判断、案例读题 |
| 学习习惯题 | 2 | 否 | `profile_probe_bank` | 识别复习节奏、坚持风险、计划执行方式 |
| 心理/状态题 | 1 | 否 | `profile_probe_bank` | 识别压力反应、挫败恢复、节奏支持需求 |
| 教学偏好题 | 1 | 否 | `profile_probe_bank` | 识别讲解密度、提示方式、例题/原理偏好 |

知识分只使用前 16 题；profile probes 只影响 Teaching Policy 和 learner profile，不影响知识得分。

如果产品必须对外说“20 道题”，文案应改为“20 个诊断题”，并在结果页区分：

- `知识诊断分`
- `学习习惯画像`
- `教学偏好建议`

## 5.1 真实使用场景矩阵

世界级 PRD 必须先穿过真实场景，而不是只服务理想链路。

| 场景 | 用户状态 | 系统最该保证什么 | 设计要求 |
| --- | --- | --- | --- |
| 新用户首次进入 | 不知道自己水平，耐心有限 | 8-10 分钟内得到可信初诊和下一步 | 前 3 题不连续高压；结果页直接给学习动作 |
| 付费用户想验证效果 | 已学一段时间，关心进步 | 分数可比、错因可解释 | 必须保存 `blueprint_version`，避免不同版本分数混比 |
| 基础薄弱用户 | 容易被难题劝退 | 测到短板但不压垮 | 难题分散；低分反馈用行动建议，不用失败感文案 |
| 高水平用户 | 普通题区分度不够 | 能识别边界判断和案例迁移能力 | mini case / 多选 / 边界判断题要有足够权重 |
| 时间紧张用户 | 想快点知道方向 | 可暂停、可恢复、可解释未完成 | session 必须支持 resume；未完成报告只能标记 partial |
| 压力大用户 | 容易乱选或放弃 | 稳住节奏，不贴心理标签 | profile probes 只转成 pace / scaffold 策略 |
| 回访用户 | 已有历史画像 | 新旧证据能合并，不互相覆盖 | 当前测评高于陈旧画像；冲突进入候选，不全量覆盖 |
| 运营/教研用户 | 关心题库质量 | 能知道蓝图哪里缺题 | coverage report 要按章节/题型/来源/难度列缺口 |
| 网络异常/切后台 | 链路可能中断 | 不丢 session，不制造重复答卷 | create 幂等、submit 防重复、答案本地临时保存 |
| 乱答/秒选用户 | 数据低可信 | 不把低可信结果写成稳定画像 | 输出 `measurement_confidence=low`，只做弱写回 |

## 5.2 结果负责的产品底线

第一版宁可少一点“智能感”，也不能牺牲可信度。

1. 能完整交付正式测评时，才展示正式诊断。
2. 不能完整交付时，允许展示“题库维护中 / 暂不可测”，不允许伪装成正式报告。
3. 用户已答完实际交付题时，不得再用另一个题量口径提示“还有未答”。
4. 低可信作答可以生成临时建议，但不能写入稳定 learner profile。
5. 心理/状态题不能单独决定教学策略，必须和作答行为、历史学习信号一起看。

## 6. 知识能力蓝图

### 6.1 抽样维度

每道知识题必须有以下 metadata：

- `question_id`
- `source_table=questions_bank`
- `source_type`
- `question_type`
- `node_code`
- `chapter`
- `topic`
- `difficulty`
- `ability_dimension`
- `provenance.question_id`
- `provenance.source_chunk_id`（如果存在）
- `provenance.exam_year`（如果存在）
- `grading_keywords` or `rubric_ref`

### 6.2 默认 16 题结构

| 维度 | 数量 | 说明 |
| --- | ---: | --- |
| 地基基础 / 深基坑 | 2 | 高频、高风险、安全与技术综合 |
| 主体结构 / 混凝土 / 钢筋 | 3 | 建筑实务核心基本盘 |
| 防水 / 装饰 / 机电 | 3 | 常见质量控制与工序判断 |
| 模板脚手架 / 安全管理 | 2 | 安全与专项方案 |
| 施工组织 / 网络计划 | 2 | 进度计划、关键线路、组织设计 |
| 合同索赔 / 质量验收 | 2 | 案例题高频管理判断 |
| 综合案例 / 计算 | 2 | 应用与迁移能力 |

### 6.3 题型比例

默认比例：

- `single_choice`: 8
- `multi_choice`: 4
- `case_study` mini case: 3
- `calculation` or structured judgment: 1

当前 Supabase `calculation` 仅 15 条，所以 P0 不把 `calculation` 设为硬配额。更稳健的做法是：

- 若目标章节/难度能取到合格 calculation，则纳入 1 题。
- 若取不到，降级为 `structured judgment`，但必须在 session metadata 记录 `calculation_replaced=true`。
- 如果 `structured judgment` 也不足，才 fail-closed。
- 不允许静默把综合能力位替换成普通单选后仍声称蓝图满足。

### 6.4 难度比例

默认比例：

- 易：30%
- 中：50%
- 难：20%

第一题不应太难；前 3 题用于建立信心和校准答题节奏。难题必须分散，不能连续压垮新用户。

### 6.5 抽样算法

第一版不需要复杂自适应 IRT，但需要确定、可审计的分层抽样。

推荐算法：

1. 从 `diagnostic_v1` 读取 section quota。
2. 将 `questions_bank` 候选按 `chapter/topic/question_type/source_type/difficulty` 分桶。
3. 每个桶先过滤：
   - 有稳定 `questions_bank.id`
   - stem/options/answer 可解析
   - 题型能被当前小程序渲染
   - 未被当前用户近期做过，或间隔已足够
4. 每个桶优先级：
   - `REAL_EXAM`
   - `TEXTBOOK_ASSESSMENT`
   - `TEXTBOOK`
5. 同一测评内不得出现同源重复题或过近变体。
6. 抽样结果保存完整 `sampling_trace`，便于线上复盘。

P0 不做完全实时自适应。原因：

- 冷启动题量只有 20，实时自适应会增加实现复杂度和可解释成本。
- 当前更大的风险是 count/provenance/coverage 不稳，而不是自适应不够聪明。
- 可以在后续 `diagnostic_v2` 做 two-stage adaptive：前 8 题粗测，后 8 题按弱项加权。

### 6.6 题目质量审计

进入正式蓝图的题目必须通过最小质量门：

1. 题干完整，不依赖丢失图片或外部附件。
2. 选项完整，单选只有一个标准答案，多选答案集合可解析。
3. 解析或评分关键词存在；没有解析的题只能进入低权重池。
4. 题目不含明显过时规范，或能通过 `standard_code / source_meta` 指向版本。
5. 案例题在小程序端可读，不出现一屏塞满长材料。
6. 题目版权/授权状态未确认时，只用于内部教学，不做公开导出。

质量门不是教研后台，而是 release gate 的输入。P0 可以先做脚本审计，不需要先做完整管理界面。

## 7. 学习习惯、心理状态与偏好蓝图

### 7.1 设计原则

这些题只服务教学，不做标签化判断。

允许输出：

- `pace_need`
- `scaffold_need`
- `review_rhythm`
- `frustration_recovery`
- `explanation_preference`
- `practice_preference`

禁止输出：

- 临床心理标签
- 人格定型标签
- “你就是冲动型/焦虑型”这类高解释度标签
- 低证据下的永久画像更新

### 7.1.1 Probe 设计底线

profile probes 必须像学习诊断题，不像问卷调查。

推荐形态：

1. 场景选择，而不是抽象自评。
   - 好：`做错一道网络计划题后，你通常最想先看什么？`
   - 差：`你是否是焦虑型学习者？`

2. 行为选择，而不是人格判断。
   - 好：`时间只剩 20 天，你更愿意每天短练还是周末集中补？`
   - 差：`你的自控力怎么样？`

3. 允许“我不确定”。
   - 用户无法判断自己偏好时，不强迫归类。

4. 结果只转成教学动作。
   - `短骨架优先`
   - `先例题再原理`
   - `错题后先同类微练`

5. 不在 UI 上展示内部标签。
   - 内部可以是 `pace_need=short_steps`
   - 外显只能是“我会先用短步骤带你稳住节奏”

### 7.2 学习习惯 probes

目标：判断系统接下来怎样安排练习。

示例维度：

- `review_rhythm`
  - 每天短练 / 周末集中 / 考前冲刺
- `planning_style`
  - 跟计划 / 看状态 / 需要外部提醒
- `error_review_style`
  - 看解析 / 记错因 / 做同类题 / 找老师讲
- `persistence_risk`
  - 卡住后继续尝试 / 等讲解 / 容易跳过

### 7.3 心理/状态 probes

目标：判断教学节奏和支持方式。

示例维度：

- `pressure_response`
  - 时间紧会更专注 / 会慌 / 会乱选 / 会拖延
- `frustration_recovery`
  - 错题后愿意复盘 / 需要短反馈 / 需要先降低难度
- `confidence_calibration`
  - 高信心高正确 / 高信心低正确 / 低信心高正确 / 低信心低正确

注意：

- `confidence_calibration` 可以由知识题作答后的自评题推断。
- 不允许把它变成“自信/自卑”标签。

### 7.4 教学偏好 probes

目标：判断 TutorBot 首轮怎么教。

示例维度：

- `explanation_density`
  - 先结论 / 先步骤 / 先原理 / 先例题
- `hint_style`
  - 直接指出错因 / 提问引导 / 对比选项 / 给口诀
- `practice_mode`
  - 同类题打穿 / 混合练习 / 案例专项 / 速刷选择题

## 8. Scoring 与画像输出

### 8.1 计分分层

结果必须分三层，不得混算：

1. `ability_score`
   - 只来自知识能力题和案例题
   - 分母为已交付的 scored items

2. `diagnostic_profile`
   - 来自知识题表现 + profile probes
   - 表达为可教学的中性信号

3. `teaching_policy_seed`
   - 给 Teaching Policy Layer 的初始策略
   - 不直接展示后台字段

### 8.1.1 测量信心

任何一次测评都必须输出 `measurement_confidence`：

| 信心等级 | 条件 | 写回策略 |
| --- | --- | --- |
| `high` | 完成全部 20 个单元；耗时合理；无明显乱答；题源完整 | 可写 `last_assessment`，可生成 Teaching Policy seed |
| `medium` | 完成全部题，但耗时异常或 profile probes 缺少部分信号 | 可写结果，但 profile 更新只进入候选 |
| `low` | 未完成、秒选、明显规律作答、频繁切出导致数据弱 | 只展示临时建议，不写稳定画像 |

低信心不是惩罚用户，而是保护系统不把噪声当事实。

### 8.1.2 乱答与异常行为

P0 至少记录：

- 总耗时
- 每题耗时
- 连续相同选项
- 空题数
- 中途退出/恢复次数
- profile probes 是否全部选择极端项

这些信号只影响 `measurement_confidence`，不直接影响知识题正确率。

### 8.2 结果结构

建议返回：

```json
{
  "quiz_id": "quiz_x",
  "blueprint_version": "diagnostic_v1",
  "requested_count": 20,
  "delivered_count": 20,
  "sections": [
    {"id": "knowledge", "count": 16, "scored": true},
    {"id": "learner_profile", "count": 4, "scored": false}
  ],
  "score": {
    "ability_score": 68,
    "knowledge_items_answered": 16,
    "profile_items_answered": 4,
    "measurement_confidence": "high"
  },
  "diagnostic_profile": {
    "chapter_mastery": {},
    "error_pattern": "",
    "confidence_calibration": "",
    "review_rhythm": "",
    "explanation_preference": ""
  },
  "teaching_policy_seed": {
    "primary_method": "worked_example",
    "secondary_method": "targeted_micro_drill",
    "pace": "short_steps",
    "evidence_level": "medium",
    "expires_after_interactions": 5
  }
}
```

### 8.3 显示表达

可以对用户说：

- “你现在最需要先稳住网络计划里的关键线路判断。”
- “你不是全不会，而是容易在责任归属和工期影响之间混淆。”
- “你更适合先看短骨架，再做同类题巩固。”

不要说：

- “根据画像你属于冲动型学习者。”
- “系统判断你心理压力较大。”
- “你是低自控型学习者。”

## 9. 数据与服务设计

### 9.1 新增服务

建议新增：

- `AssessmentBlueprintService`
  - 加载蓝图版本
  - 检查题库覆盖
  - 生成抽样计划
  - 校验 delivered count

- `AssessmentItemRepository`
  - 只读读取 Supabase `questions_bank`
  - 返回标准 `AssessmentItem`
  - 不暴露 Supabase 原始行给页面或 TutorBot

- `AssessmentScoringService`
  - 计分
  - 章节 mastery
  - 错因维度
  - profile probe scoring

- `AssessmentWritebackService`
  - 写 `assessment_sessions`
  - 写 Learner State event
  - 写 `user_stats.knowledge_map`
  - 写 `user_profiles` 的稳定偏好候选
  - 写 `user_goals` 的目标/备考信息

### 9.2 不新增的东西

不新增：

- `psychological_profile` 独立长期表
- `learning_habit_profile` 独立长期表
- assessment 专用聊天 WebSocket
- assessment 专用 TutorBot 身份
- assessment 专用知识库

心理、习惯、偏好都是 learner profile 的字段或候选事件，不是新身份。

### 9.3 Supabase 读取边界

`questions_bank` 当前已有 4638 条题库资产，结构包含：

- `id`
- `question_type`
- `source_type`
- `exam_year`
- `node_code`
- `source_chunk_id`
- `grading_keywords`
- `grading_rubric`
- `tags`
- `attributes`
- `source_meta`

第一版应复用这些字段，不要求立即改 Supabase schema。

如果现有字段缺少：

- `difficulty`
- `chapter`
- `ability_dimension`
- `blueprint_eligible`

优先从 `node_code / tags / attributes / source_meta` 归一化为 runtime projection；只有 projection 无法稳定支持时，才考虑新增 migration。

### 9.4 数据安全与权限边界

1. 小程序端绝不能接触 Supabase service role key。
2. 所有 Supabase 读取由后端服务完成。
3. `assessment_sessions` 中可以保存题目快照和答案 key，但不得把 service role key、原始 Supabase 行、敏感授权信息写入 session。
4. 如果未来新增公开 Data API 表，必须先确认 RLS 和 GRANT，不允许为了小程序方便直接暴露题库表。
5. profile probes 属于学习偏好数据，不是医疗健康数据；文案和字段命名都要避开心理诊断边界。

### 9.5 会话幂等与恢复

P0 必须支持：

1. `create` 幂等
   - 同一用户短时间重复点击开始，不生成多个正式 session。

2. `resume`
   - 已创建未提交的 assessment session 可以继续作答。

3. `submit` 防重复
   - 重复提交同一 session 返回同一结果，不重复写 learner events。

4. 本地临时答案恢复
   - 小程序切后台/崩溃后，优先恢复未提交答案。

5. 过期策略
   - 未完成 session 超过合理窗口后标记 expired，不参与正式报告。

如果 P0 暂时来不及做全部恢复，最低替代方案是：

- create 时返回 `active_session_id`
- 前端再次进入时提示“继续上次测评 / 重新开始”
- 重新开始必须显式废弃旧 session

## 10. 运行时流程

### 10.1 创建测评

1. 客户端请求 `/api/v1/assessment/create`
2. 后端选择默认蓝图 `diagnostic_v1`
3. `AssessmentBlueprintService` 生成抽样计划
4. `AssessmentItemRepository` 从 Supabase `questions_bank` 拉取候选题
5. 服务端补入 4 个 profile probes
6. 校验：
   - requested_count == 20
   - delivered_count == 20
   - scored_count == 16
   - profile_count == 4
   - 每个 scored item 有 provenance
7. 写入 `assessment_sessions`
8. 返回题目与 section metadata

创建失败的用户体验：

- Supabase 连接失败：提示“题库维护中，稍后再试”，不返回 dev fallback。
- 蓝图覆盖不足：提示“当前诊断题库正在补全”，并记录 blocker。
- 本地开发环境：允许 `mode=dev_fallback`，但 UI 必须显示“本地调试题”，不得生成正式 learner profile。

### 10.2 提交测评

1. 客户端提交 answers
2. 服务端只按 session 中的 items 计分
3. scored items 进入 ability score
4. profile items 进入 preference / habit / state signals
5. 写 `last_assessment`
6. 写 Learner State event
7. 生成 `teaching_policy_seed`
8. report 页面读取 assessment profile projection

提交后的教学承接：

1. 结果页只给 1 个主攻方向和 1 个下一步动作，不把所有画像都铺出来。
2. 点击“开始学习”进入 TutorBot 时，必须带上 `teaching_policy_seed` 或其服务端引用。
3. TutorBot 第一轮必须显性体现测评结果，例如：
   - “先不扩新知识，我们先把网络计划里的关键线路判断稳住。”
4. 5 轮内如果用户行为与 seed 冲突，Teaching Policy 必须降级或改写 seed。

### 10.3 短缺处理

任何蓝图短缺必须 fail-closed：

- 如果 Supabase 无法满足 16 个 scored items，不创建正式测评。
- 如果 profile probes 不足 4 个，不创建正式测评。
- 如果题源缺 provenance，不创建正式测评。
- 如果临时 fallback 生效，必须返回 `mode=dev_fallback`，前端不得展示为正式诊断。

## 11. Release Gate

每次发布前必须通过：

1. `assessment_blueprint_coverage_gate`
   - 每个 section 候选题数量 >= 需求量 * 3

2. `assessment_count_contract_gate`
   - requested/delivered/scored/profile 数量完全一致

3. `assessment_provenance_gate`
   - scored items 全部有 `questions_bank.id` 或等价 provenance

4. `assessment_no_psych_label_gate`
   - 输出不包含临床/人格标签化字段

5. `assessment_writeback_gate`
   - submit 后能写入 `last_assessment`、Learner State event、Teaching Policy seed

6. `assessment_ui_truth_gate`
   - 小程序只展示后端返回的 section/count，不写死题量

7. `assessment_report_projection_gate`
   - report 不重算画像，只读 assessment profile projection

8. `assessment_resume_idempotency_gate`
   - create 重复点击、切后台恢复、重复 submit 都不会生成互相冲突的 session truth

9. `assessment_measurement_confidence_gate`
   - 秒选、未完成、规律作答必须输出 low/medium confidence，不能稳定写入 learner profile

10. `assessment_teaching_action_gate`
   - 完成测评后的第一轮 TutorBot 必须消费 `teaching_policy_seed`，并可在 trace 中看到采用或降级原因

## 12. 实施阶段

### Phase 0：蓝图落地与覆盖审计

目标：

- 固化 `diagnostic_v1` 蓝图
- 扫描 Supabase `questions_bank` 覆盖
- 输出 coverage report
- 找出缺 metadata 的题目

验收：

- 本文档进入 `docs/plan/INDEX.md`
- coverage report 能列出每个 section 候选数量
- 缺口不再靠页面侧猜测

具体产物：

- `scripts/audit_assessment_blueprint_coverage.py`
- `tmp/assessment_blueprint_coverage_<date>.json`
- `docs/plan` 中记录 coverage 摘要和未决缺口

2026-05-02 Phase 0 实施证据：

- 已新增版本化蓝图代码：`deeptutor/services/assessment/blueprint.py`
- 已新增纯覆盖审计：`deeptutor/services/assessment/coverage.py`
- 已新增只读审计脚本：`scripts/audit_assessment_blueprint_coverage.py`
- 已生成真实 Supabase 聚合报告：`tmp/assessment_blueprint_coverage_diagnostic_v1.json`
- 定向测试：`tests/services/assessment/test_blueprint_coverage.py`、`tests/scripts/test_audit_assessment_blueprint_coverage.py`

真实审计结果摘要：

| 指标 | 结果 |
| --- | --- |
| blueprint version | `diagnostic_v1` |
| requested / scored / profile | 20 / 16 / 4 |
| audit status | `pass` |
| blocker issues | 0 |
| scored section 最低 required candidates | 6 |
| scored section 当前最低 candidate_count | 1203（综合案例 / 计算） |
| profile probes | Phase 0 以内置版本化题库计入，不依赖 Supabase |

Phase 0 审计边界：

- 当前报告按 `question_type/source_type/source_chunk_id` 做聚合覆盖，只证明“题型与来源资产量足够支撑 P0 蓝图”。
- 当前报告尚未证明 `node_code -> chapter/topic` 的精确章节分桶质量；这必须进入 Phase 1 前置 gate。
- 当前报告将 `questions_bank.id` 作为 P0 provenance 硬门槛，`source_chunk_id` 继续作为增强证据和后续回填任务。

若审计发现某个 section 候选题不足：

- 优先调整蓝图分桶，不立即改产品承诺
- 如果核心能力位不足，产品不发布正式测评
- 如果只是 calculation 不足，用 structured judgment 替代并记录

### Phase 1：服务端蓝图 authority

目标：

- 实现 `AssessmentBlueprintService`
- 让 `/assessment/create` 从蓝图创建 session
- `_ASSESSMENT_BANK` 只作为 dev fallback

验收：

- 请求 20 必须正式返回 20
- Supabase 不可用时不得伪装成正式测评
- session 中保存 blueprint/version/section/provenance

最小可交付范围：

- 不做实时自适应
- 不做完整教研后台
- 不做复杂 IRT
- 先用分层抽样 + 质量门 + fail-closed

### Phase 2：profile probes 与 Teaching Policy seed

目标：

- 加入学习习惯、心理状态、教学偏好题
- 提交后生成 `teaching_policy_seed`
- 写 Learner State event

验收：

- profile probes 不进入 ability score
- 输出没有标签化语言
- TutorBot 下一轮能消费 seed 改变教学动作

最小可交付范围：

- 4 道 profile probes 先做内置版本化题库，不必先建 Supabase 表
- 输出 3-5 个稳定 policy seed 字段
- 只做低风险教学动作：`worked_example / minimal_scaffold / targeted_micro_drill / pace_recovery`

### Phase 3：线上观测与效果回流

目标：

- 记录每次蓝图版本、题目来源、完成率、耗时、后续练习命中率
- 比较不同 profile seed 对提分/留存/复习完成的影响

验收：

- BI 可看 assessment funnel
- Langfuse/observer 可追踪 policy seed 是否被使用
- 能回答“哪种教学策略对哪类学员真的有效”

第一批观测指标：

- start -> first_answer -> submit 完成率
- 平均耗时 / 中位耗时
- 各 section 空题率
- low confidence 占比
- 题目曝光频次与正确率
- 测评后 24 小时内是否开始学习
- 测评后 7 天内目标章节练习完成量
- Teaching Policy seed 被采用/降级/覆盖比例

## 13. 验收标准

P0 必须满足：

1. 正式摸底永远不会出现“承诺 20，实际不足 20”的链路。
2. 正式摸底题目来自 Supabase `questions_bank` 或明确 dev fallback。
3. 知识分与学习习惯/偏好画像分离。
4. profile probes 不产生心理诊断或人格标签。
5. report / chat / Teaching Policy 消费同一份 assessment profile。
6. 题库短缺时 fail-closed，不允许静默降级。
7. 所有 scored items 可追溯来源。

## 13.1 不确定性与验证方案

当前仍存在以下不确定性，不能在 PRD 里假装已经解决：

| 不确定性 | 风险 | 验证方案 | 替代方案 |
| --- | --- | --- | --- |
| `difficulty` 是否能从现有字段稳定归一化 | 难度比例无法可靠执行 | Phase 0 抽样 200 题人工/脚本对照 | P0 先按题型和章节抽样，难度只做软约束 |
| `chapter/topic` 是否能从 `node_code/tags` 稳定映射 | 章节 mastery 失真 | 建立 node_code -> chapter 映射表并抽查 | 先按高频 topic query 分桶，不直接展示细章节雷达 |
| profile probes 是否真的提升提分 | 可能只是“看起来懂用户” | A/B：有 seed vs 无 seed，比较后续练习完成与正确率 | P0 只用 probes 调整节奏，不用于强诊断 |
| 16 题知识分是否足够稳定 | 单次误差较大 | 计算重测一致性，观察同一用户 7 天内波动 | 报告显示区间/信心等级，不显示过度精确分 |
| case_study 在小程序端体验是否可接受 | 材料过长导致放弃 | DevTools + 真机完成率测试 | P0 使用 mini case，完整案例放到后续学习 |
| source_chunk_id 缺失较多 | provenance 误判失败 | 以 `questions_bank.id` 作为 P0 硬 provenance | 后续补 metadata 回填任务 |
| 心理/状态题文案是否会冒犯用户 | 用户反感或误解 | 小样本可用性访谈 + 运营反馈 | 使用更中性的学习场景题，不直接问心理状态 |

## 13.2 当前条件下的最优可交付方案

如果今天就开始实施，最稳路线不是一步到位做全套智能测评，而是：

1. **先做 coverage audit**
   - 证明每个蓝图 section 都有足够题。

2. **再做服务端蓝图创建**
   - 替换生产硬编码题库。

3. **profile probes 先内置版本化**
   - 不急着上 Supabase schema，避免为了 4 道 probes 开新表。

4. **Teaching Policy seed 先小而硬**
   - 只影响首轮教学动作、节奏和练习推荐。

5. **上线先灰度**
   - 只给内部/少量真实用户，观察完成率、低信心率、题目异常。

这条路线的好处是：

- 最少新概念
- 最少 schema 风险
- 能最快修掉线上 count authority 问题
- 能真实验证“测评是否改变教学结果”
- 后续可以平滑升级到 `diagnostic_v2`

## 14. 想你可能还没想到的点

1. **摸底不是越长越好**
   - 20 个单元足够冷启动；真正世界级的是后续 adaptive micro-check，而不是第一次塞 60 题。

2. **心理题不能像心理测试**
   - 备考产品里，用户需要的是“系统怎么帮我学”，不是“系统给我贴标签”。

3. **profile probes 应该有撤销权**
   - 用户后续行为如果和初始偏好冲突，Teaching Policy 要允许覆盖，而不是死守第一次摸底。

4. **题库覆盖要按蓝图看，不按总量看**
   - `questions_bank` 有 4638 条不等于每个 blueprint section 都够用；必须按章节、题型、难度、来源分别看。

5. **测评结果必须变成教学动作**
   - 如果结果页只展示雷达图，但 TutorBot 下一轮不改变教法，这套测评就只是仪式感。

6. **不要把案例题硬塞进选择题体验**
   - 案例题可以先做 mini case / structured judgment，等渲染和评分成熟后再放完整 case。

7. **蓝图要版本化**
   - 学员的历史报告必须知道自己是按 `diagnostic_v1` 还是 `diagnostic_v2` 测出来的，否则后续分数不可比。

## 15. 相关代码入口

当前入口：

- `deeptutor/api/routers/mobile.py`
  - `/api/v1/assessment/create`
  - `/api/v1/assessment/{quiz_id}/submit`

- `deeptutor/services/member_console/service.py`
  - `create_assessment`
  - `submit_assessment`
  - `get_assessment_profile`

- `deeptutor/services/rag/pipelines/supabase.py`
  - Supabase `questions_bank` 读取与 normalization 现有能力

- `wx_miniprogram/pages/assessment/assessment.js`
- `yousenwebview/packageDeeptutor/pages/assessment/assessment.js`

建议新增入口：

- `deeptutor/services/assessment/blueprint.py`
- `deeptutor/services/assessment/repository.py`
- `deeptutor/services/assessment/scoring.py`
- `tests/services/assessment/test_blueprint.py`
- `tests/services/assessment/test_scoring.py`
- `wx_miniprogram/tests/test_assessment_blueprint_contract.js`
- `yousenwebview/tests/test_package_assessment_blueprint_contract.js`
