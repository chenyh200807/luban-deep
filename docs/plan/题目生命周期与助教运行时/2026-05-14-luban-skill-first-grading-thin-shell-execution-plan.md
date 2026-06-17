# 鲁班智考 Skill-first 阅卷薄外壳执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用最小结构化外壳把现有建筑实务阅卷 Skills 真正接入日常练题主链路，形成可产品化的“AI 主观题阅卷系统 + 错因图谱 + 个性化变式训练”P0 能力。

**Architecture:** 不另起炉灶，不新建第二套 Rubric 题库、不新增聊天路由、不新增 learner state 概念。继续复用 `deep_question` 的题目 authority、`construction_grading` 的结构化评分结果、TutorBot Skill 的表达协议、Learner State 的 memory event 写回；只补齐四个薄能力：自然触发、结构化判分、错因写回、下一题选择。

**Tech Stack:** Python / pytest / DeepTutor `deep_question` / `construction_grading` / TutorBot Skills / Supabase `questions_bank` 与知识库字段 / 微信小程序题卡 / Langfuse trace。

---

## 0. 核心判断

当前不应该执行一份“大改造式 PRD”。更稳妥的执行口径是：

```text
现有题库与知识库 authority
  -> deep_question 出题与 active question 保存
  -> construction_grading_result 结构化判分
  -> construction case/mcq Skill 负责解释、错因语言、得分表达、下一题建议
  -> learner memory event 写回
  -> 下一轮 deep_question 优先检索现有题库/相似题，必要时生成候选变式
```

这个计划的本质不是“让 Skills 自己打分”，也不是“重建 Rubric 中台”。它是给 Skills 加一层足够薄的产品化外壳，让它们在普通学员真实使用时稳定被调用、稳定拿到题目 authority、稳定输出错因和下一题信号。

## 1. First Principles 门槛

### 1.1 一等业务事实

> 学员在练题时提交答案后，系统必须基于服务端保存的题目 authority 先生成结构化阅卷结果，再用 Skill 方式把结果讲清楚，并把错因沉淀为后续训练依据。

### 1.2 单一 Authority

| 业务事实 | 唯一 authority | 不允许成为 authority 的对象 |
| --- | --- | --- |
| 题目、选项、标准答案、解析 | 服务端 active question object / `questions_bank` / 题目生成 metadata | 微信前端 redacted context、最终 Markdown、用户粘贴的题干片段 |
| 分数与判定 | `construction_grading_result` | Skill prompt 自由发挥、普通 TutorBot 讲解、前端显示状态 |
| 错因事件 | `construction_grading_result.error_events` 写入 learner memory event | 对话总结里的自然语言判断 |
| 下一题推荐 | `next_training_signal` + 题库检索/相似题选择 | LLM 随机出题并直接给答案 |

### 1.3 P0 不新增的东西

- 不新增 WebSocket 路由，继续走 `/api/v1/ws`。
- 不新增 `AssessmentResult` 独立模块；P0 继续用现有 `construction_grading_result`，最多在文档里把它视为“AssessmentResult 的当前实现形态”。
- 不新建完整 Rubric 题库；P0 使用三档来源：`curated_rubric`、`projected_rubric`、`open_skill`。
- 不让用户看到“置信度低”。质量分层只用于内部 gate、日志、老师复核或灰度，不作为用户可见卖点。
- 不把 Skills 做成另一个评分引擎；Skills 是阅卷动作协议和表达协议，最终分数仍来自结构化结果。

## 2. 普通学员真实使用场景

这组场景决定 Skills 必须怎样被激活。

### 2.1 场景 A：学员让系统出题

用户说：

```text
给我 5 道建筑实务安全管理相关选择题
```

必须发生：

1. `deep_question` 生成或检索 5 道题。
2. 小程序只显示题目和选项，不显示答案。
3. 服务端 active question object 保存题目身份、标准答案、解析、知识点、来源字段。
4. 用户点击任意题卡选项后，系统用服务端 authority 判分。
5. 正确答案不得被判 0 分。

### 2.2 场景 B：学员答完后要类似题

用户说：

```text
再给我 5 道相关题
```

必须发生：

1. 这句话被识别为 generation/follow-up training，不是重批上一题。
2. 下一题优先来自现有 Supabase 题库相似题。
3. 如果是 AI 生成题，默认只给题目和选项，不给答案。
4. 新题进入 active question object，成为下一轮唯一 authority。

### 2.3 场景 C：学员粘贴案例题答案求批改

用户说：

```text
请批改这道案例题，我这样写能得几分：
……
```

必须发生：

1. 若当前 active object 是案例题，优先使用当前题目 authority。
2. 若用户粘贴了完整题干，则构建一次临时题目 bundle，但标记为 `open_skill`，不得伪装成已校准 Rubric。
3. `CaseGradingSkillKernel` 先输出结构化 `CaseGradingResult`。
4. Skill 表达层再输出：预计得分、采分点命中、漏点、错因、得分表达改写、下一题建议。
5. 错因写入 learner memory event，作为后续推荐依据。

### 2.4 场景 D：学员问“为什么错”

用户说：

```text
为什么我选 B 错了？
```

必须发生：

1. 进入当前题 follow-up，不重新出题，不重新判分。
2. 使用上一轮 `construction_grading_result` 和服务端题目 authority 解释。
3. 不允许普通讲解 prompt 覆盖上一轮分数。

### 2.5 场景 E：长对话后继续练题

用户在多轮聊天后说：

```text
继续给我练刚才薄弱的点
```

必须发生：

1. 不靠最近一条 Markdown 猜测薄弱点。
2. 从 learner memory event / 最近 grading result 的 `next_training_signal` 读取错因与知识点。
3. 优先检索现有题库。
4. 如果上下文不足，系统可以温和澄清训练方向，但不编造“已掌握画像”。

## 3. 文件责任边界

P0 实施只允许在以下边界内做小步改造。

| 文件 | 责任 |
| --- | --- |
| `deeptutor/services/construction_grading/schema.py` | 继续作为结构化评分结果 schema authority；必要时只补内部字段，不改用户显示语义。 |
| `deeptutor/services/construction_grading/mcq.py` | 选择题确定性判分；不得交给 LLM 判断正确/错误。 |
| `deeptutor/services/construction_grading/case_kernel.py` | 案例题三档阅卷入口；负责把题目字段、标准答案、关键词、知识库证据投影为结构化评分。 |
| `deeptutor/services/construction_grading/deep_question_adapter.py` | `deep_question` 与 `construction_grading_result` 的适配层；保证评分先于 Skill 表达。 |
| `deeptutor/services/construction_grading/writeback.py` | 把错因事件写入 learner memory event；P0 不新建错因图谱表。 |
| `deeptutor/services/question_followup.py` | 识别答题、问解析、再出题、相关题等自然 follow-up；不新增第二套 router。 |
| `deeptutor/agents/question/agents/submission_grader_agent.py` | 渲染结构化阅卷结果给最终回答，但不得重新计算分数。 |
| `deeptutor/services/tutorbot_teaching_modes.py` 或现有 Skill 注入入口 | 保证 case/mcq grading Skill 在正确场景被注入为表达协议。 |
| `wx_miniprogram/` | 题卡只提交用户答案和题目 ID，不提交或覆盖标准答案。 |

P0 不创建：

- `deeptutor/services/case_grading/` 平行目录。
- `assessment_result` 新包。
- `rubric_items` 新业务表。
- 新的 `/api/v1/mobile/...` 聊天路由。

## 4. 执行阶段

### Phase 0：锁住现有回归底线

**目标：** 先证明当前问题不会被后续计划继续放大。

**Files:**
- Read: `docs/plan/2026-05-13-luban-grading-chain-regression-matrix.md`
- Test: `tests/core/test_deep_question_submission_grading.py`
- Test: `tests/services/test_question_followup.py`
- Test: `tests/api/test_unified_ws_turn_runtime.py`
- Test: `wx_miniprogram/tests/test_ai_message_state.js`

- [ ] **Step 0.1：运行现有阅卷链路回归矩阵**

```bash
pytest \
  tests/api/test_unified_ws_turn_runtime.py::test_redacted_public_followup_context_does_not_override_grading_authority \
  tests/api/test_unified_ws_turn_runtime.py::test_answered_active_question_can_generate_related_questions_without_regrading \
  tests/services/test_question_followup.py::test_canonical_presentation_keeps_choice_aliases_as_interactive_cards \
  tests/services/test_question_followup.py::test_merge_redacted_single_submission_with_authoritative_question_set \
  tests/services/test_question_followup.py::test_merge_redacted_batch_submission_restores_all_authoritative_items_by_id \
  tests/core/test_deep_question_submission_grading.py \
  -q
node wx_miniprogram/tests/test_ai_message_state.js
```

Expected:

```text
all selected pytest tests pass
node wx_miniprogram/tests/test_ai_message_state.js passes
```

- [ ] **Step 0.2：若失败，只修 authority 断点**

失败处理顺序固定：

1. 先看 active question object 是否保存完整题目。
2. 再看 redacted 前端 context 是否覆盖了服务端标准答案。
3. 再看 `construction_grading_result` 是否生成。
4. 最后看 Skill 表达是否误改了分数。

禁止先补正则猜答案。

### Phase 1：自然触发 Skill，不靠用户说专业术语

**目标：** 普通学员不用说“调用 construction-case-grading skill”，只要说“批改、判分、我选 B、再来五道题”，系统就走正确链路。

**Files:**
- Modify: `deeptutor/services/question_followup.py`
- Modify: `deeptutor/services/tutorbot_teaching_modes.py` 或当前 TutorBot Skill 注入入口
- Test: `tests/services/test_question_followup.py`
- Test: `tests/services/test_tutorbot_teaching_modes.py`

- [ ] **Step 1.1：补自然语言触发用例**

新增或扩展测试，覆盖这些输入：

```python
examples = [
    ("我选B", "submission"),
    ("第2题选B", "submission"),
    ("为什么错", "explain_previous_grading"),
    ("再给我5道相关题", "generate_related_questions"),
    ("请批改这道案例题，我这样写能得几分", "case_grading"),
]
```

Expected:

```text
case_grading 场景注入 construction-case-grading Skill
mcq submission 场景注入 construction-mcq-grading Skill 或等价评分表达协议
generate_related_questions 不触发重批上一题
```

- [ ] **Step 1.2：实现最小触发归一化**

实现原则：

1. 已有 active question 时，优先由 `question_followup` 判断。
2. 没有 active question 但用户明确说“批改案例题/能得几分”，进入 case grading。
3. “再给题/相关题/类似题/继续练”进入 generation，不进入 grading。
4. Skill 只作为表达协议注入，不负责写分数 authority。

- [ ] **Step 1.3：运行触发测试**

```bash
pytest \
  tests/services/test_question_followup.py \
  tests/services/test_tutorbot_teaching_modes.py \
  -q
```

Expected:

```text
普通学员话术能够稳定映射到 submission / explanation / generation / case_grading
```

### Phase 2：把案例题 Skill 变成结构化判分执行器

**目标：** 案例题不是裸 prompt 直接打分，而是 `CaseGradingSkillKernel` 先生成结构化结果，Skill 再表达。

**Files:**
- Modify: `deeptutor/services/construction_grading/case_kernel.py`
- Modify: `deeptutor/services/construction_grading/schema.py`
- Test: `tests/services/construction_grading/test_case_grading_kernel.py`
- Test: `tests/core/test_deep_question_submission_grading.py`

- [ ] **Step 2.1：定义三档阅卷输入 bundle**

`CaseGradingSkillKernel.grade(...)` 的输入必须能区分：

```python
grading_mode in ["curated_rubric", "projected_rubric", "open_skill"]
```

判定规则：

| 模式 | 来源 | P0 行为 |
| --- | --- | --- |
| `curated_rubric` | 题目已有结构化 `grading_rubric` | 严格逐项判分 |
| `projected_rubric` | 有标准答案、解析、关键词、source_meta | 从现有字段投影采分点，再判分 |
| `open_skill` | 用户粘贴题干或题库字段不足 | 给“预计得分区间/诊断”，不伪装成精确人工分 |

用户可见文案不显示“置信度”，但必须显示更稳妥的表达：

```text
按当前题目资料和考试采分逻辑估算，本题约……
```

- [ ] **Step 2.2：增强 projected rubric 生成**

投影优先级：

1. `grading_rubric`
2. `correct_answer` / `standard_answer`
3. `analysis` / `explanation`
4. `keywords` / `knowledge_points`
5. `source_meta`
6. RAG 检索到的教材、讲义、标准片段

每个投影采分点必须产生：

```python
{
    "criterion": "应写出的采分点",
    "required_meaning": "必须表达的含义",
    "score": 1.0,
    "keywords": ["关键词"],
    "source": "question_field:correct_answer 或 kb_chunk:<id>"
}
```

- [ ] **Step 2.3：保持结构化输出先于最终表达**

`CaseGradingResult` 至少要包含：

```python
{
    "type": "case",
    "authority": "construction_grading",
    "grading_mode": "projected_rubric",
    "total_score": 4.0,
    "max_score": 6.0,
    "rubric_results": [...],
    "error_events": [...],
    "rewrite_answer": "...",
    "next_training_signal": {...}
}
```

- [ ] **Step 2.4：运行案例题结构化测试**

```bash
pytest \
  tests/services/construction_grading/test_case_grading_kernel.py \
  tests/core/test_deep_question_submission_grading.py::test_build_submission_context_attaches_authoritative_case_grading_result \
  -q
```

Expected:

```text
case result 先生成
final response 只引用 result
Skill 不重新打最终分
```

### Phase 3：选择题保持确定性，补错因与下一题信号

**目标：** 选择题不让 LLM 判对错，但要让 Skill 派上用场：解释错因、知识点、下一题方向。

**Files:**
- Modify: `deeptutor/services/construction_grading/mcq.py`
- Modify: `deeptutor/services/construction_grading/schema.py`
- Test: `tests/services/construction_grading/test_mcq_grading.py`
- Test: `tests/core/test_deep_question_submission_grading.py`

- [ ] **Step 3.1：确保正确答案判满分**

输入：

```python
question = {
    "question_id": "q-admin-law",
    "type": "single_choice",
    "options": {"A": "法律", "B": "行政法规", "C": "部门规章", "D": "地方性法规"},
    "correct_answer": "B",
}
user_answer = "B"
```

Expected:

```python
result.score == result.max_score
result.status == "correct"
result.error_events == []
```

- [ ] **Step 3.2：错答时输出可训练错因**

错因不只写“错了”，至少映射：

```python
{
    "error_code": "E07_CONCEPT_CONFUSION",
    "concept_tag": "法规层级",
    "diagnosis": "把行政法规与部门规章/法律层级混淆",
    "next_training_focus": "法规层级判断题"
}
```

- [ ] **Step 3.3：运行选择题测试**

```bash
pytest \
  tests/services/construction_grading/test_mcq_grading.py \
  tests/core/test_deep_question_submission_grading.py::test_build_submission_context_attaches_authoritative_mcq_grading_result \
  -q
```

Expected:

```text
选择题分数完全确定性
解释层不能把正确答案改成 0 分
```

### Phase 4：错因图谱先用 learner memory event，不建新图数据库

**目标：** P0 先沉淀“错因事件流”，不用一开始建复杂图谱表。

**Files:**
- Modify: `deeptutor/services/construction_grading/writeback.py`
- Modify: `deeptutor/services/construction_grading/deep_question_adapter.py`
- Test: `tests/services/construction_grading/test_audit_and_writeback.py`

- [ ] **Step 4.1：把评分结果写成统一 memory event**

选择题事件：

```python
{
    "event_type": "construction_grading_error",
    "source": "construction_grading",
    "question_type": "mcq",
    "question_id": "...",
    "score_ratio": 0.0,
    "error_events": [...],
    "next_training_signal": {...}
}
```

案例题事件：

```python
{
    "event_type": "construction_grading_error",
    "source": "construction_grading",
    "question_type": "case",
    "question_id": "...",
    "grading_mode": "projected_rubric",
    "score_ratio": 0.5,
    "error_events": [...],
    "next_training_signal": {...}
}
```

- [ ] **Step 4.2：写回门槛**

写回规则：

1. 有 `user_id` 才写。
2. 有结构化 `error_events` 才写。
3. 正确题可以写 mastery/positive event，但 P0 可先不写，避免 learner state 噪音。
4. 重复提交同一题同一答案时，不重复写入同一错因事件。

- [ ] **Step 4.3：运行写回测试**

```bash
pytest tests/services/construction_grading/test_audit_and_writeback.py -q
```

Expected:

```text
错误选择题和案例题都能写入 learner memory event
无用户身份或无错因时不污染 learner state
```

### Phase 5：个性化变式训练先做“题库优先推荐”

**目标：** 先利用现有题库和知识库，不急着让 LLM 随机生成题。

**Files:**
- Create: `deeptutor/services/construction_grading/recommendation.py`
- Modify: `deeptutor/services/construction_grading/deep_question_adapter.py`
- Modify: `deeptutor/services/question_followup.py`
- Test: `tests/services/construction_grading/test_recommendation.py`
- Test: `tests/api/test_unified_ws_turn_runtime.py`

- [ ] **Step 5.1：实现 next training selector**

输入：

```python
{
    "concept_tags": ["危大工程", "专项施工方案"],
    "error_codes": ["E02_MISSING_RUBRIC_ITEM", "E03_KEYWORD_MISSING"],
    "question_type": "case",
    "subject": "建筑实务"
}
```

输出：

```python
{
    "preferred_source": "questions_bank",
    "query": {
        "subject": "建筑实务",
        "concept_tags": ["危大工程", "专项施工方案"],
        "exclude_question_ids": ["current_question_id"]
    },
    "fallback": "generate_candidate_with_validator"
}
```

- [ ] **Step 5.2：推荐优先级**

排序公式先用简单规则：

```text
priority = exam_weight * 0.35
         + weakness_score * 0.35
         + recent_error_frequency * 0.20
         + forgetting_factor * 0.10
```

P0 中如果缺少 learner 历史，则退化为：

```text
priority = current_error_severity * 0.60
         + question_source_quality * 0.25
         + recent_not_practiced * 0.15
```

- [ ] **Step 5.3：AI 生成题必须 behind validator**

如果题库没有足够相似题，才生成候选变式。候选题必须通过四项校验：

1. 不泄露答案。
2. 有唯一标准答案或明确评分依据。
3. 题干信息足够。
4. 能映射回目标 `concept_tags` 和 `error_codes`。

没通过校验时，返回题库中次相关题，不展示不稳定生成题。

- [ ] **Step 5.4：运行推荐测试**

```bash
pytest tests/services/construction_grading/test_recommendation.py -q
pytest tests/api/test_unified_ws_turn_runtime.py::test_answered_active_question_can_generate_related_questions_without_regrading -q
```

Expected:

```text
答完题后“再给相关题”优先基于上一轮 next_training_signal 选题
不会重新批改上一题
不会输出答案
```

### Phase 6：最终回答只做表达，不做二次评分

**目标：** 用户看到的是专业阅卷反馈，但最终 Markdown 不再承担分数 authority。

**Files:**
- Modify: `deeptutor/agents/question/agents/submission_grader_agent.py`
- Modify: TutorBot Skill prompt 注入入口
- Test: `tests/core/test_deep_question_submission_grading.py`

- [ ] **Step 6.1：最终回答模板固定读取 result**

最终表达必须从 `construction_grading_result` 读取：

```text
得分
判定
命中点/漏点
错因类型
得分表达改写
下一题方向
```

禁止：

```text
让 LLM 根据题干和答案重新估分
```

- [ ] **Step 6.2：用户不可见内部质量字段**

内部可以有：

```python
internal_quality = {
    "grading_mode": "projected_rubric",
    "needs_teacher_review": False,
    "evidence_strength": "medium",
}
```

用户可见表达只说：

```text
按当前题目资料和考试采分逻辑估算……
这类表达通常拿不到满分，因为缺少……
```

不展示：

```text
置信度 0.63
系统不确定
建议用户自己判断
```

- [ ] **Step 6.3：运行最终回答测试**

```bash
pytest tests/core/test_deep_question_submission_grading.py -q
```

Expected:

```text
final response 引用结构化 result
Skill 表达层不覆盖 result.score
```

### Phase 7：真实链路验收

**目标：** 不以单测代替产品可用性；必须覆盖本地、微信、小程序、阿里云、Langfuse。

**Files:**
- Read: `docs/plan/2026-05-13-luban-grading-chain-regression-matrix.md`
- Runtime: local `deeptutor serve --port 8001`
- Runtime: 微信开发者工具
- Runtime: Aliyun `/root/deeptutor`
- Runtime: Langfuse traces

- [ ] **Step 7.1：本地 API 回归**

```bash
pytest \
  tests/services/construction_grading \
  tests/core/test_deep_question_submission_grading.py \
  tests/api/test_unified_ws_turn_runtime.py \
  -q
```

Expected:

```text
construction_grading services pass
deep_question submission grading pass
unified ws turn runtime pass
```

- [ ] **Step 7.2：微信开发者工具多场景**

手工场景：

1. 生成 5 道选择题，只出现题目和选项。
2. 第 1 题、第 2 题、第 5 题都可交互。
3. 回答正确选项，显示满分。
4. 回答错误选项，显示错因和正确知识点。
5. 追问“为什么错”，不重新出题。
6. 说“再给我 5 道相关题”，生成新题，不给答案。
7. 粘贴案例题答案，输出采分点、漏点、错因、得分表达。

- [ ] **Step 7.3：阿里云实机 smoke**

上线后只允许写 `/root/deeptutor` 内文件。验证命令按现有部署 runbook 执行，完成后检查：

```text
/readyz OK
/api/v1/chat/start-turn OK
/api/v1/ws 可订阅
```

业务 smoke：

```text
生成 5 题 -> 答第 2 题正确 -> 满分
答完后要相关 5 题 -> 新题组，无答案泄露
案例题求批改 -> 结构化阅卷反馈
```

- [ ] **Step 7.4：Langfuse trace 验收**

至少确认三类 trace：

```text
MCQ submission trace:
  construction_grading_result.authority = construction_grading
  score = max_score when answer is correct

Case grading trace:
  construction_grading_result.type = case
  grading_mode in curated_rubric/projected_rubric/open_skill
  error_events present when answer misses points

Next question trace:
  action = generate_related_questions
  does not regrade previous question
```

## 5. 风险与替代方案

| 风险 | 表现 | P0 处理 |
| --- | --- | --- |
| Supabase 题库字段不完整 | 无标准答案、无解析、无关键词 | 选择题不进入判分；案例题降级 `open_skill`，给诊断不伪装精确分 |
| projected rubric 不稳定 | 案例题采分点投影质量波动 | 做 20-50 道 golden samples；高频题再沉淀 curated rubric |
| Skill 表达覆盖分数 | 用户答对仍被说 0 分 | final response 只读 `construction_grading_result.score` |
| learner writeback 污染 | 一次错题永久影响画像 | P0 只写 memory event，不直接改重型 mastery；推荐读取最近事件 |
| 个性化生成题不可靠 | 题干不足、答案泄露 | P0 题库优先；生成题必须 validator 通过 |
| 长对话上下文漂移 | 用户说“继续”时系统不知道继续什么 | 优先读取 active object / recent grading result / learner memory event，不靠 Markdown 猜 |

## 6. 交付切片

### Slice 1：先保正确判分

交付：

- 选择题正确答案不再判 0。
- 5 道题全部可交互。
- 再出题不泄露答案。

验证：

```bash
pytest \
  tests/services/test_question_followup.py \
  tests/core/test_deep_question_submission_grading.py \
  tests/api/test_unified_ws_turn_runtime.py \
  -q
node wx_miniprogram/tests/test_ai_message_state.js
```

### Slice 2：案例题结构化阅卷可用

交付：

- 案例题输出结构化 `CaseGradingResult`。
- 用户看到采分点、漏点、错因、得分表达改写。
- Skill 不再直接决定最终分。

验证：

```bash
pytest \
  tests/services/construction_grading/test_case_grading_kernel.py \
  tests/core/test_deep_question_submission_grading.py \
  -q
```

### Slice 3：错因沉淀与下一题推荐

交付：

- 错因写入 learner memory event。
- “再给相关题”优先基于错因和知识点选题。
- 题库优先，生成题 behind validator。

验证：

```bash
pytest \
  tests/services/construction_grading/test_audit_and_writeback.py \
  tests/services/construction_grading/test_recommendation.py \
  tests/api/test_unified_ws_turn_runtime.py::test_answered_active_question_can_generate_related_questions_without_regrading \
  -q
```

### Slice 4：线上真实闭环

交付：

- 阿里云实机链路可用。
- 微信小程序多场景可用。
- Langfuse 能看到 grading result / action / writeback 证据。

验证：

```text
本地 pytest + node test
微信开发者工具多场景
阿里云 /readyz + start-turn + /api/v1/ws
Langfuse trace 三类验收
```

## 7. Done Definition

这份计划完成，不以“代码写完”为准，以以下结果为准：

1. 学员自然说“我选 B”“批改这道案例题”“再给我 5 道相关题”，系统都能进入正确链路。
2. 选择题正确答案稳定判满分，错误答案稳定输出错因。
3. 案例题先有结构化 `construction_grading_result`，再有 Skill 风格表达。
4. 错因至少以 learner memory event 方式沉淀，能被下一题推荐读取。
5. 下一题训练优先利用现有题库，不泄露答案。
6. 本地测试、微信开发者工具、阿里云实机、Langfuse trace 四类证据齐全。
7. 没有新增第二套评分 authority、第二套聊天路由、第二套 learner state。

## 8. 当前最优执行顺序

按收益/风险比排序：

1. **先修选择题 authority 与题卡交互。** 这是当前用户已经看见的硬 bug，且最容易验证。
2. **再把案例题结构化 result 做稳。** 这是 AI 主观题阅卷系统的核心。
3. **再做错因 writeback。** 不改重型画像，只写 memory event，风险最低。
4. **最后做下一题推荐。** 先题库优先，变式生成只做候选，不直接上线为主路径。

不要反过来先做复杂推荐、复杂 Rubric 中台或复杂 learner graph。那会让系统变宽、变慢、变难验证，却不一定提升用户第一感知。

