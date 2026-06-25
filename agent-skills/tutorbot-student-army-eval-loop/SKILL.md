---
name: tutorbot-student-army-eval-loop
description: "Use this to proactively pressure-test DeepTutor TutorBot on test2 with a multi-persona student army (long conversations: 出题→答题→追问→再出题, plus switch/回指/non-answer/未作答/粘贴判分/钓鱼攻击), then run the full discover→root-cause→fix→verify→sediment loop. Trigger words: 模拟学员/学员军团/端到端测试/student army/live eval/长对话压测/挖问题/语义理解 satisfaction/并发承载. This is a continuously-maintained skill: every run appends new bug patterns and ironclad rules below."
---

# TutorBot 学员军团端到端 Eval 闭环（持续维护）

主动派模拟学员军团在 test2 真实链路上长对话压测 TutorBot，挖出语义理解 / 判分 /
上下文承接 / 稳定性问题，并跑完 **发现 → 根因 → 治本 → 验证 → 沉淀** 闭环。

这个 skill **编排并复用** 既有窄 skill，不重复它们：
- 根因诊断 → `deeptutor-authority-debugging` + `root-cause-debugging`
- 微信入口/渲染证据边界 → `wechat-tutorbot-real-entry-qa`
- 验证纪律 → `deeptutor-test-verification-gate`
- 部署 → `deeptutor-aliyun-release`（全局）
- billable eval 排雷 → `eval-design`（全局）

**这个 skill 是活文档**：每次用完，把新发现的 bug 模式、新铁律、harness 改进
回写到本文件（见 §6 维护协议）。它越用越强。

## 0. Authority Order（不可协商）
1. 当前任务的用户指令。
2. `AGENTS.md` 硬门 + 项目规则；`CONTRACT.md` + `contracts/index.yaml`（turn/
   session/stream/replay/TutorBot/trace/public 边界）。
3. `docs/plan/INDEX.md`（PRD/roadmap/能力状态）。
4. 本仓库 `agent-skills/*/SKILL.md`。
先读相关 memory：`student-army-live-eval-method-and-findings`、
`bot-self-reinforcing-hallucination-and-pollution-diagnosis`、
`single-authority-collapse-playbook`、`cross-model-judge-catches-fabrication-same-source-misses`、
`mcq-grading-*`、`cross-capability-context-continuity-invariant`。
读 `artifacts/tutorbot_fix_test_journal.md` 顶部几条避免重复踩坑。

## 1. 测试阶段（端到端模拟学员）
- 真实链路：test2 公网 + 小程序 WebSocket（`/api/v1/ws` 是唯一聊天入口）。
  harness = `scripts/run_student_turn.py` + eval-bypass header；账号池 `/tmp/cc_pool.json`。
  抓答案优先读 DB（`/app/data/user/chat_history.db`），harness WS 捕获可能漏。
  查 DB 时按 `conversation_id` 拉 **所有** `sessions` row；同一 conversation 可能同时有 canonical
  session 与 TutorBot 内部投影 session，后者会把注入给 LLM 的"参考证据/局部工作记忆投影"
  envelope 另存成 user 内容。核 ground truth 时不要只取最新/第一条 session。
  开跑前先核 release truth：本地 `origin/main`、same-SHA Tests/Deploy Gate、test2 host env、
  container env、`.Created`/health、容器内关键代码 grep 必须对齐；否则先同步 test2，别拿旧
  lineage 做 TutorBot 结论。
  **harness `ws_timeout`/漏捕不等于 turn 未完成**：先查 DB `turns` + `turn_events`
  的 terminal `result`；若 DB 已 completed，以 DB 终态为准。driver 必须尽量逐 turn
  fail-soft/增量落盘，避免单个 `ConnectError` 丢整个人格样本。
  `scripts/run_student_turn.py turn` 支持 `--output-jsonl` 逐 turn 追加结构化结果（含
  `conversation_id/turn_id/client_turn_id/status/latency/ws_error/db_reconciled`），并可用
  `--db-path` 对本地只读 `chat_history.db` 做同步对账。只有远端 DB 时，用只读命令拉取：
  `python scripts/run_student_turn.py db-reconcile --db-path /app/data/user/chat_history.db --turn-id <turn_id> --conversation-id <conversation_id>`；
  该模式只读 `turns`、terminal `turn_events.result.metadata.response` 和同 conversation
  的 `messages.content`，不得写远端文件。
- 多 persona（乱聊 / 专业 / 攻击钓鱼 / 套话），重点 **长对话 ≥10 轮**：
  出题→答题→追问→再出题，混入切换能力、回指"刚才那题"、非答题轮、未作答追问、
  点名选项追问、粘贴 MCQ/案例题判分。判官独立于被测。
- 评分维度：稳定性 / 语义理解 / 学员满意度。**注意满意度虚高陷阱**——学员可能
  对"编造判分"满意；判官要核事实，不只看流畅度。
- 压测：并发 ~10 舒适 / 15-20 功能天花板（瓶颈=事件循环阻塞，非 CPU/mem）。
  要压测放一个后台 agent 实时监测，吃不消降并发；先报最大并行。
  若并发 8 已出现 `ConnectError`、公网 502/readyz timeout、p95 >60s 或样本未完整落盘，
  本轮只标 partial evidence，先降到 3/5/8 梯度重测；不得继续宣称 10/15-20 舒适。
  2026-06-25 实测 5 并发出现 `ConnectionClosedError`, 3 并发长跑 p95 仍接近 90s；
  后续长对话样本采集默认先用 1-2 并发，只有 p95 <60s 且 DB/harness 完整一致后再上梯度。

## 2. 诊断阶段（铁律——血泪换来的，违反必走弯路）
- 先问本质：坏掉的**一等业务事实**是什么？唯一 authority 是谁？最后一个正确点/
  第一个错误点在哪？故障成簇先放**宏观指挥官 agent** 裁决"是不是同一病因"。
- **铁律①：evidence 里有脏数据 ≠ RAG 召回脏了。** evidence 由多路组装（RAG /
  working_memory 投影 / overlay / compiled truth）。定位污染**必须 dump 实际注入给
  LLM 的文本，看每段来源标题**，别假设 RAG 就去改召回。
- **铁律②：连续 live 证伪还在同一前提上改判据/补过滤 = 打地鼠，立即停**，退回做
  ground-truth 诊断（dump 真实数据 / 查真实字段值）。
- **铁律③：判"幻觉 vs 确定性误命中/拼装"的第一信号 = 同一输入是否逐字复现**
  （幻觉会变，确定性拼装逐字同）；先确认这段输出是 LLM 生成还是确定性拼装的。
- **铁律③.5（2026-06-24 判分态收口血泪）：unit-green + enable_llm=False 端到端过 ≠ live 工作。**
  判分/路由类的真权威常散在 unit 测试够不着的 **LLM 分类器路径**（prompt 偏置如"提交优先"）
  + 多条确定性保底路径。**必须 live 验 ≥3 轮 + DB-trace `turn_semantic_decision.reason`**
  （Langfuse 对 eval-bypass turn 不写，改读容器 `chat_history.db` 的 events_json/metadata_json）
  逐轮看穿"哪条路径判的分"——reason 字段会自述是 LLM("提交优先原则")还是确定性
  ("deterministic fallback 命中")。逐路径 gate = whack-a-mole（skill 警告），单一 chokepoint
  收口（turn_runtime `_submission_action_for_user_message`）才彻底，但风险高须 live 充分后做。
- **铁律③.6（2026-06-25 terminal truth）：DB payload 里 `turn_semantic_decision` 正确 ≠ 终端输出尊重它。**
  若 metadata 写着 `next_action=ask_clarifying_question`，但 `result.response` 仍判分/生成/泄标准答案，
  最后正确点是 semantic router，第一错误点在 orchestrator lifecycle fallthrough 或 capability
  fallback。修法不是再调 router 判据，而是让终端路由/执行 sink 把 canonical decision 当硬控制信号。
- **铁律③.7（2026-06-25 generation bypass）：prompt/generator schema 绿 ≠ 出题终端经过了 generator。**
  若输出逐字稳定、延迟很低、且复验补了 generator 仍无效，立即 dump DB `templates_ready` metadata；
  questions_bank short-circuit 可能直接把题库原题 QAPair 送到终端，绕过 batch generator/schema。
- **铁律③.8（2026-06-25 current surface authority）：完整新题面先成为本轮对象，不等于旧对象不会二次抢权。**
  需要同时查两处：turn-start resolver 是否把当前完整 MCQ / case surface 投影成 `question_followup_context`
  和 `active_object`；以及 resolver 的 public-submission merge / turn-end result merge 是否又把旧
  candidate / RESULT `active_object` 的 `question_id`、`correct_answer`、`user_answer` 合回来。只修
  "skip stale candidate" 不够，第二次 merge 是常见复发点。
- **铁律③.9（2026-06-25 current submission terminal binding）：对象身份正确 ≠ 终端判分事实正确。**
  live 若出现 stream 片段看似按当前题批改，但 DB `result.metadata.response` / assistant message 又落回
  generic TutorBot fallback、旧题文案或 low-info clarification，说明当前完整 submission 没有原子绑定
  `question_lifecycle_scene` / action / marked reference。修法是让当前 full MCQ/case submission 在
  capability 前绑定对象 + learner answer + 显式 `标准答案|正确答案|参考答案` + terminal scene；
  不是新增第二 router，也不是让 LLM prompt 承诺"不要沿用上一题"。
- **铁律③.10（2026-06-25 public stream read-model）：content stream 正确 ≠ terminal read-model 正确。**
  如果 public `content` stream 已把当前题答案流给学生，但后到 `result.metadata.response` 携带旧题 /
  fallback 文案，DB assistant message、mobile history、replay 会被 terminal result 翻案。验证必须同时核
  public `content`、public `result.metadata.response`、`messages.role=assistant.content`；修法落在
  `turn_runtime` terminal sink：已有 public final-answer stream 时，`result.response` 只能投影同一份
  stream；没有 stream 时才由 result 承担终局答案。不要给旧题词补黑名单。
- **铁律③.11（2026-06-25 learner-state truth）：conversation_synthesis 观察 ≠ 长期画像事实。**
  live 出现"你反复..."、M07 画像等个性化断言时，先 dump learner-state 持久态，区分
  structured grading/answer evidence 与 conversation_synthesis observation。修法是让 PCP/long-term
  profile 只读 canonical evidence；观察可进图谱/候选，不得自动晋升为 stable claim。
- **铁律③.12（2026-06-25 visible sink）：内部 meta/citation 泄露不能按 emit 路径补。**
  `参考证据`、`局部工作记忆`、`长期画像提示`、孤儿 `〔N〕` 这类学生不可见内容，必须由
  `coerce_user_visible_answer`/citation assembler 单一 sink 处理，并覆盖 stream delta 与 terminal
  result。不要在 grader/followup/generator 各补一套剥离。
- **异源核（同源不能自证）**：根因判断 + "无编造/已修好"结论必须异源在环。
  Codex 额度耗尽用 `deepseek-v4-pro`@api.deepseek.com（`DEEPSEEK_API_KEY`，OpenAI
  兼容）：给中立证据 + 对立假设让它独立选，**别 prime**。异源也可能共享错前提，
  只有 dump ground truth 能终审。多源时可加 `qwen-max-latest`@dashscope。

## 3. 修复阶段（铁律）
- **先收权再补逻辑**：找唯一 authority，其余 decider 降级只读；别加第 N+1 个
  "检查别人有没有踩坏"的门。
- **断环优先写入侧**（错误不进长期态）> 注入侧降级（LLM 仍会沿用记忆里的数字）
  > prompt 约束（LLM 可能不遵守）。
- **对新增层有罪推定**：新字段/router/classifier/wrapper/fallback 默认错，先证明
  没造第二套 authority、没把语义降级成正则。
- active case/written context 只说明有待处理对象，不证明当前 turn 新提交了答案；当前 turn
  submission authority 必须先判定是否真提交。无显式答案前缀且明确退出判分/切到学习计划时，
  写入侧 fail-open 为 follow-up/chat，不让旧判分态继续抢权。
- TDD：先写测试看 RED。改 contract-protected 文件必须**同 commit** 更新 registered
  domain test + contract surface（否则 contract_guard FAIL；注意 sensitive vs
  protected 是两类要求）。packaged 副本（如 `deeptutor/contracts/index.yaml`）要同步。
- 干净 PR：从 `origin/main` 建 clean worktree 重应用增量，别从脏分支带共享文件。

## 4. 验证阶段（治"假绿"）
- **当前 main base** + **live 连跑 ≥3 轮一致**（2/3=没修好）。
- **确定性不变量，不靠 LLM**：验证"写入链断没断"用**清白持久态 → 触发 → 查持久态
  0→0**，别用 LLM response（受单次幻觉 + 旧污染双噪声，会把噪声当信号）。
- 部署 test2 用 `redeploy_aliyun_fast.sh`；金标=容器 `grep code` + `printenv` +
  `.Created` + contract_guard PASS，别只信 `docker compose ps`。修复合 main 后
  redeploy main 回 test2 保 lineage。
- 诚实边界：主病根治 ≠ 残留全清；纯 prompt 压不住强幻觉就明说，列独立残留议题。

## 5. 沉淀阶段（每次必做，失败也是资产）
- `artifacts/tutorbot_fix_test_journal.md` 追加（倒序）：问题→根因→**失败尝试及
  原因**→成功修法→验证(带数字)→教训。
- task 台账记状态 + 残留；contract surface 记不变量。
- 跨会话方法论 → memory（除非用户说"记一下"，先在报告里提议是否写 memory）。
- **回写本 skill**（见 §6）。

## 6. 维护协议（这是"持续维护"的机制 —— 别跳过）
每次用完这个 skill，在结束前做一遍：
1. 新发现的 bug 模式 → 追加到 §7 模式库（一行：症状 / 根因类型 / 落点 / 状态）。
2. 新踩出的铁律 / 反模式 → 追加到 §2/§3 对应阶段。
3. harness / 诊断手法改进（新脚本、新 DB 查法、新 dump 技巧）→ 记到 §1。
4. 若某模式已根治且 live 稳 → 在 §7 标 ✅，保留作回归清单（防复发）。
5. 改完本 skill 用 `git diff --check` 过一遍；提交走 narrow commit。
保持本文件 < 400 行：同类模式合并，过时的细节删，链到日志/memory 而非复制。

## 7. 已知问题模式库（持续追加 —— 也是回归清单）
| 症状 | 根因类型 | 落点 / 修法 | 状态 |
|---|---|---|---|
| 做完题不给答案/解析 | mcq_grading 路由缺口（active_capability 预选绕过） | orchestrator 补 mcq_grading 一等分支 | ✅ 已修 |
| 闲聊后"刚才那题"召回失败/丢活跃题 | 跨能力上下文承接（连续性只加执行层没加路由层） | conversation_context_text 无条件注入 + 单一 relation 权威 | ✅ 主修 |
| 选项重排时判对判错/倒诬学生 | 判分用题库字母非当前题面 | 判分前投影到当前选项面 | ❌ **2026-06-24 live 复现**(g1 T6,bot 自承"按原题选项顺序判卷")——修法 commit 落地但 live 链路未生效,查未部署/未接线 |
| 判分缺标准答案就拒答 | 三路兜底失败未回落开放世界 | RAG-grounded open-world 裁决 | ✅ 已修 |
| 粘贴 MCQ 误命中题库案例题，拼别题整篇"标准作答"（含别题"中标价1.7亿"） | exact_authority 确定性误命中（题型不匹配） | 题型门 fail-closed（query 非 case_like 撤 case 命中） | ✅ 已修 PR#202 |
| judge 编造背景数字"中标价1.7亿"且跨会话复现 | bot 判分输出经 notebook→working_memory→当 EVIDENCE 回灌的自强化幻觉循环 | 写入侧断环：notebook 不写判分输出到 working_memory_projection | ✅ 已修 PR#204；残留单次 judge 幻觉源头 |
| 〔N〕孤儿注脚泄露给学生 | 引用渲染层未剥孤儿标记 | coerce_user_visible_answer 单一 sink footer-aware strip | ✅ 已修 |
| 真诚概念追问→反篡改薄答罐头 | 确定性渲染器在 FollowupAgent 前拦截 | 删 brush-off 渲染器 + 收窄渲染闸 | ✅ 已修 |
| 内部链路/工具命令 meta 泄露 | 内部输出未脱敏 | looks_like_internal_output + coerce sink | ✅ 主修 |
| WS 跨 worker 流式死 | in-process 执行表 per-worker | store-tail 单一事件权威 | ✅ 已修 PR#190 |
| 首 token 无界 90s 超时 | 无超时上限 | 首 token 超时门 | ✅ 已修 |
| 切换/timeout 后拒答死循环 | 状态污染 | （待复验） | ⚠️ 观察 |
| 简答/案例判分请求→被 MCQ 生成器抢占,判 bot 自己生成的 MCQ | 判分对象路由错(锚到 bot 自造题非用户真题) | 判分态/判分对象单一 decider 收权 | ❌ **2026-06-24 live 复现**(g6 8处,task#20 簇A) |
| 回指"刚才那题"→串到别题且编造作答记录("你答了C/多选B和C") | 判分对象=哪道题的权威失守 | 判分对象只能是真实活跃题,无活跃题 fail-closed | ❌ **2026-06-24 live 复现**(g1 T9/g4 T10,task#20 簇A) |
| 非答题轮("我不会/先别判/还没做")→ 凭空判分 | "是否提交作答"散在确定性关键词+LLM 偏置多 writer(fast-path-as-authority) | submission_confidence 单一信号:HIGH 必判(硬约束40)/LOW 不判;qls scene+semantic_router 守卫+interpret backstop+fallback 全 gate | ✅ **2026-06-24 收口 live GO 6/6**(Steps 1-4.6,plan 判分态收口;凭空判分不再,真作答必判;PR#212)。⚠️残 whack-a-mole:逐路径 gate,单一 chokepoint(turn_runtime _submission_action,Step5)更彻底 |
| 案例题批改后说"只给复盘计划/现在聊学习计划"仍继续判分 | active case context 被误当成 current submission authority,主观题抽取把任意长文本写成新答案 | `question_followup.resolve_submission_attempt` 写入侧收权:无显式答案前缀且命中退出判分/学习计划意图→非 submission;显式答案仍提交 | ✅ 本地 TDD+contract 已修(2026-06-25),live 待部署复验 |
| 质疑轮(只反驳未作答)→ 凭空判分"你答了D得0分" + 附和编造修订叙事 | 质疑被误触发阅卷态 + 不重 grounding 无条件附和 | 质疑轮禁判分态 + 强制重走 RAG 核验 | ❌ **2026-06-24 live**(g5 T3/4/7 凭空判分;T10 DeepSeek conf=1.0 编造"罚款2020修订4%→8%",task#20 簇A) |
| 非答题轮凭空判分后→捏造"系统记录显示你提交了C"为前轮幻觉背书 | 会话内即时自强化幻觉(非跨会话 notebook,PR#204 只断了 notebook 写入侧) | 判分态收权根治(不进判分就无幻觉判分可背书) | ❌ **2026-06-24 新形态**(g2 T10) |
| DB `turn_semantic_decision.next_action=ask_clarifying_question` 但最终仍判分/生成/泄标准答案 | canonical decision 被 lifecycle fallthrough / deep_question full-submission fallback 当弱提示 | orchestrator 对 `semantic_route=chat` 直接回 TutorBot/chat; deep_question 收到同一 decision fail-closed clarification | ✅ 本地 TDD+contract 已修(2026-06-25),live 待部署复验 |
| 粘贴案例并要求直接采分点评→bot 自造 4m 软土题并反向成为后续判分对象 | 学生真实题面/作答对象与 bot 自造题 active_object 多 writer | 待收口 assessment object authority:自造练习题不得覆盖用户粘贴案例 authority | ❌ 2026-06-25 live 复现(p04) |
| 明确要求"单选/A-D/只出题"→lightweight 生成 A-E 五个选项 | 主因=questions_bank short-circuit 把 A-E/BDE 多选原题当 choice 直出;次因=batch generator 解析端也未执行 A-D schema | bank short-circuit 仅允许 A-D+单答案 choice 直出;batch generator 同步硬校验 raw option keys | ✅ 已修 #228/#229;test2 live 3/3 只出 A-D、无答案泄露(2026-06-25) |
| 明确要求"先不要告诉答案"仍直接泄答案/解析 | 出题偏好没有成为终端输出 contract,生成器/渲染器仍把答案解析暴露给学生 | 显式 reveal preference 覆盖 stale config;TutorBot visible response 与 orchestrator reveal flags 服从同一 authority | ✅ #231 已修;test2 live 只出题无答案/解析(2026-06-25) |
| 完整粘贴 MCQ 要判分,答案 B 可判但改 D/重贴后误入"案例题逐采分点/无 authority" | MCQ 题型识别、active object、case grading fallback 竞争判分 authority | 自包含 MCQ + 明确我的答案 优先进入 MCQ grading full-submission authority;显式改答走同一 submission authority | ✅ #232 已修;test2 live A→B 改答正确(2026-06-25);重贴/D 边界继续扩样本 |
| active MCQ 后问知识点("电气管线、给排水管道、设备安装最低保修期几年")却输出阅卷结论 | sticky `deep_question` preselect 越过 submission/active-object authority | orchestrator 对非提交/非追问/非出题/非题目审查 turn 降级默认 TutorBot/chat,不进入阅卷终端 | ✅ #232 已修;test2 live active MCQ 后知识问答不判分(2026-06-25) |
| DB 同一 conversation 出现 canonical session + TutorBot 内部投影 session,内部 session 把"参考证据/局部工作记忆投影"存成 user 内容 | TutorBot bridge/agent loop 把 LLM prompt envelope 当成 mirror session user 内容持久化 | 写入侧断环:bridge 传 `raw_user_content`,AgentLoop/SQLiteSessionAdapter 只把真实用户输入写入 user 消息,LLM envelope 仅用于本轮注入 | ✅ 本地 TDD+contract 已修(2026-06-25),live 待部署复验 |
| 明确"不要再出题/给复盘计划"仍被判成 practice generation,随后以"非建筑实务主题"拒绝 | deterministic practice-generation fast-path 没有 fail-open 于显式否定出题语义 | 在既有 `looks_like_practice_generation_request` 中把显式否定出题降级为非生成请求,交回 semantic_router/general chat;不新增 router | ✅ 本地 TDD+contract 已修(2026-06-25),live 待部署复验 |
| 建筑复盘/混凝土模板防水/沟槽开挖请求 | 2026-06-25 live 当前不再复现为科目门误拒;残留主要是 topic precision drift/题源不忠于请求主题 | 不再用白名单/黑名单补科目门;后续单独收 topic-source authority 与近期题干 dedupe | ⚠️ 当前 live 已放行,内容漂移待修 |
| 终端输出出现"长期画像提示"/M07 画像提示等内部学情 meta | user-visible sink/画像投影边界泄漏 + conversation_synthesis observation 被长期画像读取 | PCP/stable personalization 只读 structured evidence;学生输出统一走 coerce_user_visible_answer 剥内部标题 | ✅ 本地 TDD+contract 已修(2026-06-25),live 待部署复验 |
| 〔N〕在判分/教学合成路径泄露(bot 承诺不带仍输出"正确答案:A〔1〕") | citation assembler / visible sink 没有统一剥 orphan body marker | strip_orphan_reference_markers 与 coerce_user_visible_answer 单一 sink 剥无 footer 支撑的 body markers,保留合法 footer 引用 | ✅ 本地 TDD+contract 已修(2026-06-25),live 待部署复验 |
| 一建他科(市政/机电/公路)+建筑工程白名单漏词(沟槽开挖)被科目门误拒 | 关键词白名单判语义,unknown_topic→拒("静态闸越权承担语义判断") | 反转:单一 helper 只 out_of_scope 拒,unknown 放行+非专项标注;判据用 RAG/教材覆盖非白名单 | ✅ 代码完成待 live(task#8) |
| 新出题请求仍消费上一题 next_training_signal 或重复题库原题 | question supply authority 被旧 active_object 与 question_bank short-circuit 争抢 | 仅权威锚点缺失时读取 next_training_signal;bank short-circuit 必须尊重题型/reveal/近期 dedupe | ✅ 本地 TDD+contract 已修(2026-06-25),live 待部署复验 |
| 出题考点精度漂移/逐字重复出题 | 主题槽位被对话噪声劫持 / 去重失效(异源拆出独立病) | 出题 prompt 主题约束隔离对话填充词 / 出题调度去重 | ⚠️ 已收一层 supply authority,仍需 live 扩样本 |
| 用户切换到新 MCQ / 案例点评,系统仍按上一道 MCQ active object 判分("关键线路"题) | current grading object identity 多 writer:旧 active_object/candidate 与下游 RESULT 可二次覆盖当前题面 | 完整 MCQ/case submission 共享投影 helper 上移到 `question_lifecycle_skills`; turn-start 只允许同题 context 保权,不匹配则当前题面成 active_object; turn-end grading RESULT 不得用不同 object_id 旧对象覆盖当前对象 | ✅ 本地 TDD+contract 已修(2026-06-25),live 待部署复验 |
| 当前新 MCQ stream 看似判对,但 DB `result.response`/assistant message 又落回旧 TN-S 题或 generic fallback；自然案例题被 low-info gate 拒绝 | current submission 只绑定了对象身份,未原子绑定 scene/action/reference; terminal sink 与 low-info gate 仍抢权 | turn-start 从 `question_lifecycle_skills` 当前 context/action 薄盖 `mcq_grading`/`case_grading`;显式标准答案只认 `标准答案/正确答案/参考答案`;完整 `案例题...问...我的答案` 逃逸 low-info | ✅ 本地 TDD+contract 已修(2026-06-25),live 待部署复验 |
| public content stream 已判当前题,但 terminal result/DB assistant message 被旧 TN-S/fallback response 覆盖 | terminal read-model authority drift: 后到 `result.metadata.response` 覆盖已流出的同源 public final content | `turn_runtime` 在持久化/发布 public RESULT 前,若已捕获 public content stream,强制 `result.metadata.response` 对齐 stream;无 stream 时仍保留 result authority | ✅ 本地 TDD+contract 已修(2026-06-25),live 待部署复验 |
| 完整案例同句含"我的答案100mm。标准答案150mm"却给满分 | case submission extraction 把 marked reference 混进 `user_answer`,阅卷器把标准答案当学生命中 | `question_lifecycle_skills` 当前案例投影原子拆 `user_answer` 与 `correct_answer/reference_answer`;不改 grader/router | ✅ 本地 TDD+contract 已修(2026-06-26),live 待部署复验 |
| 完整自包含 MCQ 判当前题,但 DB active_object/q_followup 仍旧题,下一轮"刚才那题/B不对"串回旧题 | self-contained current surface 没覆盖 stale active object/result metadata | `deep_question` full MCQ/case fallback 使用当前投影生成 active_object 并写回 metadata;旧 active object 降级 previous | ✅ 本地 TDD+contract 已修(2026-06-26),live 待部署复验 |
| A-D 题里问"如果我选E,对不对"→把不存在 E 当错选项讲 | invalid option follow-up 不被 option challenge predicate 捕获,落 generic LLM 可见输出 | follow-up challenge predicate 覆盖 A-E 但 submission 仍只认当前 options;brief renderer 用当前 options 确定性说明 E 不存在 | ✅ 本地 TDD+contract 已修(2026-06-26),live 待部署复验 |
| active question 下问"正确答案到底是什么"→TutorBot 泛化回答并编造"你选过C" | correct-answer follow-up marker 太窄,未进入 question_review,raw history 被 LLM 当作作答历史 | `_FOLLOWUP_MARKERS` 覆盖正确/标准/参考答案请求,让 active question 走 question_review/reference authority | ✅ 本地 TDD+contract 已修(2026-06-26),live 待部署复验 |
| "再出一道不同考点..." semantic 已 route_to_generation 但 visible 非建筑拒绝 | generation topic/context authority 可能被空 topic 或旧状态污染;当前本地 `unknown_topic -> allow` 未稳定复现 | 不在未复现处补规则;部署后 live ≥3 轮复验,若复现再 dump `templates_ready`/topic trace 定位 | ⚠️ 复验残留(2026-06-26) |
| 5 并发出现 `ConnectionClosedError`, DB turn 全 completed 但 harness 漏捕 | 公网/WS 捕获稳定性独立遮蔽面;DB terminal result 才是 turn truth | 长对话采集先 1-2 并发;harness 逐 turn JSONL 落盘并用 DB completed/result 对账 | ✅ harness 已修;系统并发稳定性仍需 live 压测 |

## 红线
- 不绕 AGENTS.md 单一权威；不新增第二聊天 WS 入口；surgical diff；阿里云只写
  `/root/deeptutor`；测试不因环境缺失跳过；自动 commit 工具慎用（先确认分支干净）。
- 本 skill 是开发/QA workflow，**不是 TutorBot runtime skill**，禁止被
  `deeptutor/tutorbot/skills/` 产品 loader 加载，禁止复制到全局。

## 本轮起点
先和用户对焦：聚焦哪几类问题（语义理解/判分/承接/稳定性/全扫）、要不要先从
Langfuse 真实生产 trace 挖线索、派多少 persona、跑多少轮——再开跑。
