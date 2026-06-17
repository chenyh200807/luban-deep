# Design: 学习脑对外 · 下一题劫持 MVP

- 文档名称：鲁班智考·学习脑对外·下一题劫持 MVP 设计文档
- 文档路径：`docs/plan/2026-05-19-luban-learning-brain-external-next-question-hijack-design.md`
- 创建日期：2026-05-19
- 状态：Draft v1（office hours 产出，待 plan-eng-review）
- Mode：Startup, Pre-product
- Branch：`codex/gbrain-learning-brain`
- 主线归属：学习事实编译 / Evidence-first Memory（[`docs/plan/INDEX.md`](../INDEX.md)）
- 父 PRD：[`2026-05-18-luban-learning-brain-gbrain-absorption-prd.md`](2026-05-18-luban-learning-brain-gbrain-absorption-prd.md)
- 相关计划：
  - [`2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md`](2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md)
  - [`2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md`](2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md)
  - [`2026-05-13-luban-case-grading-error-map-prd.md`](../题目生命周期与助教运行时/2026-05-13-luban-case-grading-error-map-prd.md)
  - [`2026-04-15-learner-state-memory-guided-learning-prd.md`](2026-04-15-learner-state-memory-guided-learning-prd.md)

> **使用方式**：本设计是 office hours `/gstack-office-hours` 产出，目的是把"学习脑对外"在 pre-product 阶段的 wedge / persona / 入口 / 留存指标 一次性钉死，把后续 implementation plan 的输入条件 lock。**不替代** Learning Brain 父 PRD 与既有实施计划；只是在它们之上锚定"对外体验"这条尚未贯彻的支线。

## 1. Problem Statement

鲁班智考 Learning Brain backend 已经 live verified（compiled truth、evidence chain、typed graph、nightly synthesis 全部跑通），但真用户的微信小程序入口**尚未接 learning_brain 路由** —— `deeptutor/api/routers/learning_brain.py` 当前只有 `/harness-projection` 和 `/harness-case-grading` 两个 dev 端点，**0 个生产端点**。

Retention 弱的根因不是分类质量、不是 RAG 召回精度、不是 evidence chain 的可见度 —— 是"消费学习脑产出"这个动作**没有寄生在用户已有的高频动作（每天 30 分钟+ 翻错题本）上**。当前用户即使想消费学习脑产出，也没有合法物理路径。

本设计要解决的就是这一段断裂：把 Learning Brain 的 `training_uses_question` typed edge 真接到练习页"下一题"按钮上，让消费动作物理可发生。

## 2. Demand Evidence

来自 office hours D4 / D5 / D6 / D7：

- **Q1 demand（D4 + D5）**：用户能点名某个学生在用 Learning Brain；但**重复行为不确定 / 太随机** → awareness 信号存在，retention 信号未证据化。
- **Q2 status quo（D6 + D7）**：目标用户每天 **30 分钟+** 坐在错题本 / 纸质笔记 / Excel 上 → 痛点存在、市场存在。
- **行业证据（Phase 2.75 landscape）**：A+ 错题本、橙果错题本 等成熟 App 停在"拍照→分类→打印"的工具属性，没人把它升级到"学习路径决策"层 —— 这是 Learning Brain 多走 3 步可以变现的差异化空间。
- **团队投资意图**：最近 5 个 commit（ISSUE-001 visible chain 系列 + Localize Learning Brain）显示团队已经在投资"可见"，但这条 chain 当前的暴露面是 `/wechat-harness` dev mirror，**不是生产微信小程序**。

## 3. Status Quo

| 角色 | 当前行为 | 痛感 |
| --- | --- | --- |
| **个人考证生** | 手写错题本 + Excel 整理 + 群里发题问问题 + 偶尔搜真题视频 | 每日 30 min+，跨天靠手 |
| **行业 App（A+ / 橙果）** | 拍照→分类→打印；考试宝 / 万题库 = 真题刷题 + 模考报告 | 两类都没有"基于个人证据的下一题决策" |
| **培训机构班主任** | 面批 + 群语音 + 经验制定练习清单 | 重人力、不可规模化 |

## 4. Target User & Narrowest Wedge

**Persona A（office hours D13 钉死）**：25-35 岁在职考证生，要考二建 / 一建 / 监理 / 造价为职业晋升 / 加薪 / 公司挂证。

特征：
- 付费者 = 使用者 = 决策者（单边推销，GTM 简单）
- 碎片时间使用（每天 30 min 左右）
- 考前 3-6 个月是"杀手锁"窗口期
- 强结果导向：考过 = 多 30% 薪 / 公司给奖；考不过 = 隔年再来
- 错题本是他们**唯一**在跨天累计学习进度的物理介质

**Narrowest wedge**：在**答题页**（`wx_miniprogram/pages/assessment/assessment.wxml:140` 的"下一题"按钮）里嵌入「上次你在 ×× 漏了 N 次」+ Learning Brain 选出的命中题。**用户不需要打开任何"学习脑报告页"，只在做下一题这个动作的瞬间消费 LB 产出**。

> **入口纠正记录**：spec review 发现首版 Approach A 把入口锚定在 `pages/practice/`，但 verify 后 `pages/practice/` 是模式选择页，**真正的"下一题"按钮在 `pages/assessment/`**。已统一修订到答题页。

## 5. Constraints

- **Hard（父 PRD §3 line 109）**：不新增 grounded mode / learning brain mode / case brain mode 等入口模式。
- **Hard（AGENTS §Concept Discipline）**：`/api/v1/ws` 是唯一聊天 WebSocket、RAG 是唯一知识召回工具、TutorBot 是唯一执行身份。
- **Hard（AGENTS §3 Surgical Changes）**：本次只改 §10 Dependencies 列出的文件；不顺手清理；不动 `web/app/wechat-harness/*`、`deeptutor/agents/`、`deeptutor/tutorbot/`、`pages/report/*`。
- **Hard（AGENTS §3.6 Branch & Worktree）**：继续在 `codex/gbrain-learning-brain` 分支干，不新建 worktree。
- **Hard（AGENTS §3.7 Aliyun SSH）**：远端写操作只允许在 `/root/deeptutor` 内。
- **Resource**：1 个工程师，**~1 周 dev + ~2 周 招募&观察 = ~3 周端到端**（人工时）/ ~30 min（CC 协助 dev）。Pre-product 阶段 dev 是最短的部分，招募 20 个 25-35 在职考证生 + 观察 7 天才是关键路径。
- **复用**：`learning_brain_read_model.py`、`RAGService.evidence_bundle`、`learner_memory_events`、`questions_bank`。

## 6. Premises

| # | 表述 | 状态 |
| --- | --- | --- |
| A | Pre-product 阶段必须钉一个 persona；钉死 = 25-35 在职考证生 | Agreed (D10 + D13) |
| B | 学习脑对外入口必须寄生在现有"做错题→看错因→下一题推荐"流上，不新建页面 / 不新增 mode | Agreed (D11)，与父 PRD §3 line 109 一致 |
| C' | retention 衡量指标 = 连续 N 天 `training_uses_question` typed edge 被触发（即下一题推荐被作答），不是"报告打开数" | Agreed after subagent 修订 (D15) |

## 7. Cross-Model Perspective

二意见来自独立 Claude subagent（Codex CLI 因本机 arch-specific binary 缺失自动回退）。Subagent 没有看过 D1-D14 的对话，只读了 context block 和 repo 文件。

1. **Steelman**：把 GBrain 的 `compiled truth + timeline + typed graph + evidence-first memory` 四件套，专门收窄到"建筑实务考证"垂类 —— 每次做错题、批改、RAG 命中、人工修正，都沉淀成可追溯、可聚合的学习事实，让"下一题推荐"和"诊断话术"不再是 LLM 现编，而是有 evidence chain 兜底。

2. **Most load-bearing quote（subagent verbatim）**：
   > **"能点名学生名字，但重复行为不确定是否真有 / 太随机"** —— 这一句直接证伪 retention 假设。`L1_repeated` evidence 需要跨 session 多次错同一类采分点，但 25-35 在职考生一天 30 分钟碎片，单设备单 session 拿不到第 2 个数据点。**先让 ledger 长出第 2 个事件，再谈编译质量**。

3. **Premise 挑战（已采纳为 C' 修订）**：原 Premise C "消费学习脑产出"默认 = "打开报告页"，与 Premise B（不新建页面）矛盾。改写为 "消费 = `training_uses_question` typed edge 触发（下一题推荐被作答）"。

4. **48h 原型建议**（与本设计 Approach A 高度对齐）：
   - 加生产端点 `GET /api/v1/learning-brain/next-training`
   - 加 `select_next_training_question(user_id) -> question_id` 到 `learning_brain_read_model.py`
   - 改 `wx_miniprogram/pages/practice/` 让"下一题"按钮调该端点 + 一行解释
   - **不做**：SR 调度器、新报告页、push 通知、老师端、wechat-harness 同步改造、nightly synthesis 产品化

**Cross-model synthesis**：

| 维度 | Claude（主） | Subagent（冷读） | 结论 |
|---|---|---|---|
| 入口寄生在动作流 | ✓ | ✓ | 一致 |
| 报告页 vs 练习页谁是入口 | 没明确分 | 明确：练习页是入口，报告页是 projection | 采纳 subagent |
| Premise C 是否含糊 | 没察觉 | 抓到"消费"歧义 | 采纳 subagent，已修订为 C' |
| 48h MVP 文件锚 | 只到 router 级 | 到 `select_next_training_question()` 方法级 | 采纳 subagent |
| AC 形态 | D7 但没阈值 | 20 用户 7 天 → D3 ≥ 8 触发 | 采纳 subagent |

## 8. Approaches Considered

### 8.1 Approach A — Minimal "下一题劫持"（chosen）
- Effort: S（人 ~1 周 dev / ~3 周 端到端含招募观察 / CC ~30 min）· Risk: Low · Completeness 6/10
- 复用 `learning_brain_read_model.py` 已有的 `training_uses_question` edge + `learner_memory_events` 数据
- 改：加生产端点 + 加 read_model 方法 + 改两个**答题页**（`wx_miniprogram/pages/assessment/` + `yousenwebview/packageDeeptutor/pages/assessment/`）"下一题"按钮 + 新增 `training_uses_question` memory event emission（见 §11）
- 不做：streak、批改页 inline、push、老师端

### 8.2 Approach B — A + streak + 批改页 inline 解释
- Effort: M（人 ~2-3 周 / CC ~2 hr）· Risk: Med · Completeness 8/10
- 在 A 之上加：练习页顶部 streak banner（连续 N 天）、批改页 inline 出现"上次你在 ×× 漏了 N 次"
- 多 backend：streak 计数 × 跨设备同步（要新存储或复用 `learner_summaries` 字段）

### 8.3 Approach C — B + 微信小程序订阅消息推送
- Effort: L（人 ~3-4 周 / CC ~3 hr）· Risk: High · Completeness 9/10
- 接微信小程序"一次性订阅消息"，每天 8 pm 推"今天卡点题"
- 已知风险：订阅一次性限制、用户授权率、微信审核

## 9. Recommended Approach

**Approach A**（user D16 选定）。

理由：Pre-product 期最便宜的实验是先证明 Premise B（入口寄生）能拉出 Premise C'（typed edge 触发）。**如果 A 都拉不出 retention 信号，streak / push 都救不了；如果 A 拉得出，再投资 B 的 ritual feedback 才有信息含量**。

## 10. Open Questions

1. **`select_next_training_question(user_id)` 选择策略**：P0 用"最近 N 天 weakest `concept_id` 命中题"（简单）。P1 再上 SR-style 间隔。
2. **"一行解释"文案规范**：使用模板字符串 `"上次你在《{concept_label}》{missed_action}了 {miss_count} 次"`，占位符来自 typed graph 节点：`{concept_label}` ← `concept` 节点 display name；`{missed_action}` ← `error_label`（如"漏了审批步骤"/"算错单位换算"）；`{miss_count}` ← `learner_memory_events` 中该 `(learner_id, concept_id, error_id)` 最近 N 天的去重计数。**此聚合查询为新增**（既有 read_model 没有按 `(concept_id, error_id)` group by 的方法），需在 `learning_brain_read_model.py` 同次提交里加。P1 看用户反馈决定上不上 LLM 改写。i18n key：`learning_brain.next_training.preamble_template`。
3. **冷启动**：判定条件 = 该用户 `learner_memory_events` 中无任何 `concept_miss` 类事件。fallback 到 `questions_bank` 按章节随机抽 + 返回 payload 标记 `cold_start=true`，不阻塞流。**Cold_start 题目 NOT 计入 §11 AC 的 typed edge 触发计数**——否则会污染 retention 信号。
4. **Empty-candidate**：用户有 `learner_memory_events` 但本周无 weakest concept 命中题（题库空），返回 200 + `{question: null, reason: "no_candidate"}`，前端 fallback 到既有"下一题"逻辑，**同样 NOT 计入 typed edge 触发计数**。
5. **20 用户 7 天 D3 ≥ 8 的 AC 招募**：通过微信社群 + 公众号 + 内测群发起 invite（写到 §12 Assignment）。预估招募窗口 ~7 天，端到端 §6 已含此估算。
6. **灰度开关**：用现有 `env_flag` 模式新增 `LB_NEXT_TRAINING_ENABLED`（默认 off）+ user_id allowlist（环境变量逗号分隔，无需新存储）。约 5 行代码。
7. **鉴权 & user_id 来源**：新端点放在 **`deeptutor/api/routers/learning_brain.py`**（既有 router，mount 在 `/api/v1/learning-brain`，与 `/harness-*` 同 router）。**复用 `mobile.py:114 _resolve_authenticated_user_id(authorization: str | None)`**：P0 直接 `from deeptutor.api.routers.mobile import _resolve_authenticated_user_id`，P1 抽到共享 auth 模块。**禁止照搬 `/harness-projection` 的 query-string user_id 写法**（dev only，无鉴权）。

## 11. Success Criteria

**单一可证伪 AC**：上线后**端到端 3 周内**（含招募窗口），邀请 **20 个** 25-35 在职考证生使用产品，**D3 留存中 ≥ 8 人**在答题页触发了至少 1 次 `training_uses_question` typed edge（即真的做了 LB 选出的下一题）。

阈值含义：
- **< 8 人**：wedge 不成立，回到 brainstorm。可能是入口寄生位置不对、文案太弱、LB 选题精度不够。
- **8-12 人**：入口寄生有效，开始投资 Approach B 的 streak banner。
- **> 12 人**：强 retention 信号，加预算做 SR 调度器 + 批改页 inline。

### 11.1 度量来源（重要：trace_events 表不存在，改用 learner_memory_events）

Spec review 发现 repo 内**不存在 `trace_events` 表**，也**没有任何 `training_uses_question` trace emission**。因此 AC 不能依赖 Langfuse / ClickHouse trace，必须改用既有的 `learner_memory_events`（事件账本，已 live）。

**新增改动**（已纳入 §14 #3）：在新端点的"题目被作答"回包路径上，写一条 `learner_memory_events` 记录：

```python
# 在 select_next_training_question 选出 question_id 并被 client 成功作答后
LearnerMemoryEvent(
    event_type="training_uses_question",
    learner_id=...,
    concept_id=...,
    question_id=...,
    source_edge_id=...,  # from training_uses_question typed edge
    cold_start=False,    # cold_start 与 empty-candidate 不写入此事件类型
    ts=now(),
)
```

**测量 query 草案**（用既有 `learner_memory_events` 表 + Supabase / Postgres 查询）：

```sql
SELECT learner_id, COUNT(DISTINCT date_trunc('day', ts)) AS active_days, COUNT(*) AS edges
FROM learner_memory_events
WHERE event_type = 'training_uses_question'
  AND cold_start = FALSE
  AND learner_id IN (邀请名单)
  AND ts >= 上线日期
  AND ts <  上线日期 + INTERVAL '7 days'
GROUP BY learner_id;
```

AC 判定：`active_days >= 3 AND edges >= 1` 的 `learner_id` 数量 ≥ 8。

## 12. The Assignment

> **在接下来 7 天内，先做一件真实世界的事**：用手机录 3 段视频（每段 5 分钟），跟拍你"能点名"的那 3 个 25-35 岁在职考证生**实际做错题**的过程。不剪辑、不解说。记录：
>
> 1. 他们打开了什么页面？多久？
> 2. 翻了多久错题本？
> 3. 做完一道错题之后的下一秒做了什么？（继续看错因？关掉换 App？点了"下一题"？）
> 4. 中间因为什么停下来？被什么打断？
>
> 不要先告诉用户你在录什么，只问："我能跟拍你 5 分钟做题的样子吗？"
>
> 录完看完之后，写一段 200 字到本文档 §15 "What I noticed" 下方，回答：
>
> **他们的"下一题"按钮在他们的实际动作里出现在什么位置？是顶部？右下角？还是根本没动这按钮？**

这个 assignment 的目的是验证 **Premise B 的物理可行性** —— 如果用户实际动作里"下一题"按钮根本不被点，那么 Approach A 的整套设计是空中楼阁，写代码之前就该发现。

录完视频之前，**不要写任何 production 代码**。这条约束是 surgical changes 在 product 层的延伸：未经 demand observation 的实现等同于"为不存在的需求造轮子"。

## 13. Distribution Plan

- **部署管线**：复用现有 FastAPI router 流；新增 2 个端点（`GET /api/v1/learning-brain/next-training` + `POST /api/v1/learning-brain/training-used`）挂在既有 `learning_brain.router`（main.py:502 mount 前缀 `/api/v1/learning-brain`），鉴权 import 自 mobile router。无新 docker image、无新 worker。
- **微信小程序发布**：走既有发布管线（`wx_miniprogram` + `yousenwebview` 各发一次），不变。
- **阿里云部署**：按 AGENTS §3.7 只写 `/root/deeptutor`。

## 14. Dependencies & Surgical Change List

**复用，不改**：
- `questions_bank` 已 live，无 schema 变更
- `learner_memory_events` 已写入（最近 commit 已恢复 visible chain）
- `learning_brain_read_model.py` 已有 `training_uses_question` edge（`read_model.py:39, 101, 172-211`）
- `RAGService.evidence_bundle`、`CaseGradingSkillKernel`、`LearnerStateService` 全链路

**Surgical 改动文件清单（P0，本次必做）**：

1. **`deeptutor/api/routers/learning_brain.py`** — 加 **两个**生产端点（mount 前缀 `/api/v1/learning-brain` 已存在）：

   **1a. `GET /api/v1/learning-brain/next-training`**：调 `select_next_training_question(learner_id)`，把 read-model DTO 投影为 HTTP response schema 后返回：

   ```python
   class NextTrainingResponse(BaseModel):
       question: dict | None       # questions_bank row，或 None（empty-candidate）
       cold_start: bool            # True = 用户无 learner_memory_events 数据
       reason: str | None          # "no_candidate" / "cold_start" / None
       preamble_text: str | None   # "上次你在《X》漏了 2 次审批步骤"
       source_edge_id: str | None  # typed-graph training_uses_question edge id
   ```

   注：`NextTrainingResponse` 是 HTTP 层 model；read-model 内部返回 `NextTrainingCandidate` DTO（包含完整 edge metadata + 调试字段），router 层做 trimming 投影。

   **1b. `POST /api/v1/learning-brain/training-used`**：客户端在学生作答完 next-training 选出的题之后调用，写 `training_uses_question` `learner_memory_event`：

   ```python
   class TrainingUsedRequest(BaseModel):
       source_edge_id: str
       question_id: str
       submission_id: str       # 既有 case_grading 链路返回的 submission id
       elapsed_ms: int          # 学生作答耗时
   class TrainingUsedResponse(BaseModel):
       event_id: str            # learner_memory_events 主键
       accepted: bool
   ```

   两个端点都用 §10.7 的 auth 复用方案；`source_edge_id` 服务器侧 cross-check `learner_id`，**防止前端伪造 event**。

2. **`deeptutor/services/learner_state/learning_brain_read_model.py`** — 加 `select_next_training_question(learner_id, *, top_k=1, exclude_recent_days=7) -> NextTrainingCandidate` 方法（read-model DTO，包含完整 edge metadata；router 层投影为 HTTP `NextTrainingResponse`）。多候选 tie-break 用 (miss_count desc, ts desc)。同时新增 `count_recent_misses_by_concept_error(learner_id, *, lookback_days=30) -> dict[(concept_id, error_id), int]` 聚合（§10.2 文案模板 `miss_count` 占位符的数据来源）。

3. **`deeptutor/services/learner_state/supabase_writer.py` + `learner_memory_events` 写入路径** — 新增 `training_uses_question` 事件类型 emission（client 作答成功后回调写入；`cold_start=True` 与 `reason=no_candidate` **不写入**此事件类型）。这是 §11 AC 度量的物理基础。

4. **`wx_miniprogram/pages/assessment/*.{js,wxml,wxss}`** — `assessment.wxml:140` "下一题"按钮 `onClick` 改为先调 `/api/v1/learning-brain/next-training`，若返回 `question != null` 则用其加载题 + 顶部显示 `preamble_text`；若返回 `null`（cold_start / empty-candidate）则 fallback 到既有 `onNext` 逻辑。

5. **`yousenwebview/packageDeeptutor/pages/assessment/*.{js,wxml,wxss}`** — 同上（双小程序入口；先确认两端共享 backend session-id 与 WeChat openid 中间件，预期 yes 但需验证）。

6. **`tests/api/test_learning_brain_router.py`** — 两个新端点的测试：
   - `next-training`：happy path（has edge）/ cold_start / empty-candidate / auth-required / 灰度 off → 404
   - `training-used`：happy path / source_edge_id mismatch（403）/ duplicate write（idempotency）/ auth-required

7. **`tests/services/learner_state/test_learning_brain_read_model.py`** — `select_next_training_question` 测试：has-edge / empty / multi-concept tie-break。

8. **`tests/services/learner_state/test_supabase_writer.py`** — `training_uses_question` 事件写入测试。

9. **环境变量**：新增 `LB_NEXT_TRAINING_ENABLED`（默认 `false`）+ `LB_NEXT_TRAINING_ALLOWLIST`（逗号分隔 learner_id）。**两个端点共用同一对开关**：灰度 off → `next-training` 与 `training-used` 同时 404。allowlist 不在内的 caller 也是 404。两个变量 + 5 行 router 代码做灰度。

**P1 / 流程项（本次不必做）**：

- `contracts/learner-state.md` — 增补 `training_uses_question` event 的 contract 字段说明（只新增 read + 一个 event type，影响面小，可在 P1 一起做）
- `docs/plan/INDEX.md` — 把本设计 doc 挂到「学习事实编译 / Evidence-first Memory」主线作为子条目（AGENTS §Plan Directory Discipline 流程要求，与 dev 并行）

**不改**：`web/app/wechat-harness/*`、`deeptutor/agents/`、`deeptutor/tutorbot/`、`wx_miniprogram/pages/report/*`、`yousenwebview/packageDeeptutor/pages/report/*`、`wx_miniprogram/pages/practice/*`（不是入口）。

## 15. Endpoint Contract & Boundary Conditions (新增，spec review 要求)

### 15.1 Request

```
GET /api/v1/learning-brain/next-training
Headers: 既有 WeChat openid 鉴权中间件
Query params: (无；learner_id 从 session 解出)
```

### 15.2 `next-training` Response

见 §14 #1a `NextTrainingResponse` Pydantic schema。

### 15.3 `next-training` Boundary matrix

| 用户状态 | `select_next_training_question` 返回 | Response | 是否写 `training_uses_question` event | AC 计入 |
| --- | --- | --- | --- | --- |
| 无 `learner_memory_events.concept_miss` 事件 | `cold_start=True, question=$random_from_bank` | 200 + `cold_start=True` | **否** | **否** |
| 有事件、本周有命中题 | `cold_start=False, question=$LB_pick` | 200 + `preamble_text + source_edge_id` | **是**（作答成功后由 client 调 `/training-used` 触发） | **是** |
| 有事件、本周无命中题 | `cold_start=False, question=None, reason="no_candidate"` | 200 + `question=null` | **否** | **否** |
| 鉴权失败 | (中间件拦截) | 401 | 否 | 否 |
| 灰度未启用 | (router 短路) | 404 | 否 | 否 |

### 15.4 `training-used` Request / Response

```
POST /api/v1/learning-brain/training-used
Headers: 既有 WeChat openid 鉴权中间件
Body: TrainingUsedRequest  (见 §14 #1b)
Response: TrainingUsedResponse  (见 §14 #1b)
```

### 15.5 `training-used` Boundary matrix

| 输入状态 | 服务器校验结果 | Response | learner_memory_events 写入 | AC 计入 |
| --- | --- | --- | --- | --- |
| 合法：`source_edge_id` 属于 caller learner_id，从未提交过 | pass | 200 + `accepted=True, event_id=<uuid>` | **写一条 `training_uses_question`** | **是** |
| `source_edge_id` 不属于 caller learner_id | 校验失败 | 403 | 否 | 否 |
| 同 `source_edge_id` 重复提交 | idempotent 命中 | 200 + `accepted=True, event_id=<已存在 uuid>` | 否（已写过） | 是（之前那次已计） |
| `source_edge_id` 不存在 / 已过期（超出 `exclude_recent_days`） | 校验失败 | 404 | 否 | 否 |
| 鉴权失败 | 中间件拦截 | 401 | 否 | 否 |
| 灰度未启用 | router 短路 | 404 | 否 | 否 |

### 15.6 调用时序

### 15.7 端到端调用时序

```
[assessment.wxml] 学生作答完成 → onSubmit
   ↓
[assessment.js] 调用 /mobile/case-grading（既有，不动）→ 返回批改结果
   ↓
[assessment.js] 学生点击"下一题"按钮（wxml:140）
   ↓
[assessment.js] 新增：调用 /api/v1/learning-brain/next-training（loading state: "正在挑下一题..."）
   ↓
[learning_brain_read_model.select_next_training_question]
   ↓
[learning_brain router] 返回 NextTrainingResponse
   ↓
[assessment.js] 若 question != null：渲染 preamble_text + 加载 question → 学生作答
   ↓
[assessment.js] onSubmit 成功后：调用 /api/v1/learning-brain/training-used（新写一条 learner_memory_event）
   ↓ （如果 cold_start / no_candidate）
[assessment.js] fallback：使用既有 onNext 逻辑
```

`/api/v1/learning-brain/training-used` 是配套写事件的 endpoint，与 `next-training` 一对（避免前端能直接造 event）。

## 16. What I noticed about how you think

- **你倾向于把"技术 live verified"等同于"产品 live verified"** —— D2 你选了"对学生 / 老师体验改进"作为话题，但 D5 暴露的事实是：技术管线 verified，但**真的微信小程序入口 0 个生产端点**（router 只有两个 `/harness-*` dev 端点）。这是工程师常见的 confidence bias。诊断：你需要在团队里设一个"产品入口审计"的角色，专门盯"backend 已能产出 → 前端 surface 是否能消费"这条 chain。
- **D8 你答 D（三个 persona 都没钉死）是这次 office hours 最诚实的一刻**。能在 brainstorm 里说"我没钉"比假装钉了重要 100 倍。后续 D13 你也没纠结就选了 A。这种"能 admit + 能快速 commit"的组合是 founder 心智的关键信号。
- **D15 你接受了 subagent 对 Premise C 的修订** —— 没有为面子守住自己的原始表述，直接选了"消费 = typed edge 触发"。在跨模型审查里能让步给更对的版本，是少数人能做的事。

— 实地视频观察记录（assignment 完成后请写在此处） —

```
（待填）
```
