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
  **harness `ws_timeout`/漏捕不等于 turn 未完成**：先查 DB `turns` + `turn_events`
  的 terminal `result`；若 DB 已 completed，以 DB 终态为准。driver 必须尽量逐 turn
  fail-soft/增量落盘，避免单个 `ConnectError` 丢整个人格样本。
- 多 persona（乱聊 / 专业 / 攻击钓鱼 / 套话），重点 **长对话 ≥10 轮**：
  出题→答题→追问→再出题，混入切换能力、回指"刚才那题"、非答题轮、未作答追问、
  点名选项追问、粘贴 MCQ/案例题判分。判官独立于被测。
- 评分维度：稳定性 / 语义理解 / 学员满意度。**注意满意度虚高陷阱**——学员可能
  对"编造判分"满意；判官要核事实，不只看流畅度。
- 压测：并发 ~10 舒适 / 15-20 功能天花板（瓶颈=事件循环阻塞，非 CPU/mem）。
  要压测放一个后台 agent 实时监测，吃不消降并发；先报最大并行。
  若并发 8 已出现 `ConnectError`、公网 502/readyz timeout、p95 >60s 或样本未完整落盘，
  本轮只标 partial evidence，先降到 3/5/8 梯度重测；不得继续宣称 10/15-20 舒适。

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
| 质疑轮(只反驳未作答)→ 凭空判分"你答了D得0分" + 附和编造修订叙事 | 质疑被误触发阅卷态 + 不重 grounding 无条件附和 | 质疑轮禁判分态 + 强制重走 RAG 核验 | ❌ **2026-06-24 live**(g5 T3/4/7 凭空判分;T10 DeepSeek conf=1.0 编造"罚款2020修订4%→8%",task#20 簇A) |
| 非答题轮凭空判分后→捏造"系统记录显示你提交了C"为前轮幻觉背书 | 会话内即时自强化幻觉(非跨会话 notebook,PR#204 只断了 notebook 写入侧) | 判分态收权根治(不进判分就无幻觉判分可背书) | ❌ **2026-06-24 新形态**(g2 T10) |
| DB `turn_semantic_decision.next_action=ask_clarifying_question` 但最终仍判分/生成/泄标准答案 | canonical decision 被 lifecycle fallthrough / deep_question full-submission fallback 当弱提示 | orchestrator 对 `semantic_route=chat` 直接回 TutorBot/chat; deep_question 收到同一 decision fail-closed clarification | ✅ 本地 TDD+contract 已修(2026-06-25),live 待部署复验 |
| 粘贴案例并要求直接采分点评→bot 自造 4m 软土题并反向成为后续判分对象 | 学生真实题面/作答对象与 bot 自造题 active_object 多 writer | 待收口 assessment object authority:自造练习题不得覆盖用户粘贴案例 authority | ❌ 2026-06-25 live 复现(p04) |
| 终端输出出现"长期画像提示"/M07 画像提示等内部学情 meta | user-visible sink/画像投影边界泄漏 | 待查 learner_state 是否真有该画像;无论真假,学生输出 sink 不得裸露内部标签 | 🔵 2026-06-25 新模式 |
| 〔N〕在判分/教学合成路径泄露(bot 承诺不带仍输出"正确答案:A〔1〕") | 判分 emit 绕过 citations 剥离权威,coerce sink 不剥〔N〕(dormant authority) | strip_orphan_public_markers 收口到 coerce_user_visible_answer(复用 citations 剥离,不造第二权威) | 🔵 task#27 已诊断未实施 |
| 一建他科(市政/机电/公路)+建筑工程白名单漏词(沟槽开挖)被科目门误拒 | 关键词白名单判语义,unknown_topic→拒("静态闸越权承担语义判断") | 反转:单一 helper 只 out_of_scope 拒,unknown 放行+非专项标注;判据用 RAG/教材覆盖非白名单 | ✅ 代码完成待 live(task#8) |
| 出题考点精度漂移/逐字重复出题 | 主题槽位被对话噪声劫持 / 去重失效(异源拆出独立病) | 出题 prompt 主题约束隔离对话填充词 / 出题调度去重 | 🔵 task#8/task#28 |

## 红线
- 不绕 AGENTS.md 单一权威；不新增第二聊天 WS 入口；surgical diff；阿里云只写
  `/root/deeptutor`；测试不因环境缺失跳过；自动 commit 工具慎用（先确认分支干净）。
- 本 skill 是开发/QA workflow，**不是 TutorBot runtime skill**，禁止被
  `deeptutor/tutorbot/skills/` 产品 loader 加载，禁止复制到全局。

## 本轮起点
先和用户对焦：聚焦哪几类问题（语义理解/判分/承接/稳定性/全扫）、要不要先从
Langfuse 真实生产 trace 挖线索、派多少 persona、跑多少轮——再开跑。
