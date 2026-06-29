# Forward-Reachability Collapse（fail-closed 非对称）病因 + forward-liveness 实证 + 治本计划

> **状态**: Release+QA 工程师 root-cause + forward-liveness 活体 eval 产物。被测基线 = **部署 main `033ffbc85`**（test2 已三方对齐上线，含 #297 出口科目门对称化 + 出题科目门反转）。
> **触发**: 学生军团 5/6 跑发现新主病——收权战役把 SEV 侧（"何时该拒"）收成单一权威且可达做完了，但**对偶面"何时该 ACT、正确能力可达"没做**。
> **关系**: 本计划是 [2026-06-27 reachability/consumption 根因计划](2026-06-27-reachability-consumption-root-cause-and-fix-plan.md) 的 **forward 对偶 child**（同一根病 reachability/consumption，方向相反：那份治 fail-open「该拒没拒」，本份治 fail-closed「该 ACT 没 ACT」），统一挂 [2026-06-26 控制面收权 umbrella](2026-06-26-fast-mode-orchestrator-simplification-architecture-plan.md)。**不新建第二权威**，只补对称面的到达/消费保证。
> **三原则**: thin wrappers fat skills / first principles / less is more。绝不治标。

## 病因一句话（first principles，不含模块名）

> **收权把 canonical「该信什么」建成单一权威且让"拒绝出口"可达（SEV 侧做完）；但对偶——「该用哪个正确能力 ACT」的 forward 事实，在 dispatch 处没有被结构性 consume，于是门在不确定时 fail-closed 吐预设罐头，而不是 fall-through 到有上下文的主 LLM。病不在"算不出该 ACT"，而在"forward 事实的到达性/被消费性没保证 + fail-closed 非对称（拒绝有出口、ACT 无兜底）"。**

这是姊妹计划 reachability/consumption 病的 forward 镜像：那份的 `dormant authority`/`unconsumed island` 是"canonical 真值没被下游读"；本份是"**刚算好的 forward 事实（刚生成的题 / 当前案例题）没被判分/出题 dispatch 读**，门遂 fail-closed"。

## forward-liveness 实证（部署 main `033ffbc85`，n=3/家族，确定性断言为主 + 持久化 /messages 终态核验）

harness：`scratchpad/army_forward_liveness.py`（DB-读取驱动 = POST start-turn + 轮询 `/api/v1/conversations/{cid}/messages` 终态，绕开 WS；qa_ 账号签名 X-Eval-Bypass）。确定性断言已过 11/11 度量自测（eval-design #5）。判官双保险 = 确定性断言（主 ground truth）+ 持久化终态人核（独立确认），强于 LLM 判官字段。

| 家族 | 场景 | 部署 main 结果 | 判定（分离 phantom vs 真洞） |
|---|---|---|---|
| **S1 对答案拒判** | 出 3 题 → "q1 B q2 C q3 A"(批量)/"我选B"(裸答) → 应判分 | **0/6 PASS（3/3 轮复现）** | ❌ **真洞**。#297 未触及。终态实锤：学生发系统自称可解析的 `q1 B q2 C q3 A`，bot 重显第1题 + "这道题你还没作答" |
| **S2 出题路由** | "出道流水施工题" → 应出建筑可作答题 | **9/9 PASS** | ✅ 直接出题路由正常。**但 smoke/full 的英语题/锚点乱码是上下文依赖**（零基础概念教学后要"最简单题"才触发），本场景未复现 ≠ 完全证伪，列**残留风险** |
| **S3 topic 放行** | 长尾考点(水泥/沟槽开挖) + p11 式"已给考点" → 不要求复述魔法词 | **9/9 PASS** | ✅ **phantom（#297 部署后消失）**。验证了"先分离部署滞后"的价值——这洞在 stale f5749c6ca 上真，部署 main 后没了 |
| **S4 主观判分** | bot 出案例题 → 作答 → 应诊断 grounded 判分 | **T2 confound / T3 卡死真** | ⚠️ **部分 confound**：harness 喂固定答案没匹配 bot 动态生成的题，"凭空满分"是假阳性（bot 实际正确检测答非所问）；但 **T3"再出新案例题"→bot 仍吐判分拒答模板无法 fall-through 出题 = 真卡死**。凭空判分真证据在 full-eval p8.r3（已 ground-truth 确认），本 harness 未干净隔离 |

**结论：#297 部署修掉了 S3（topic phantom）；S1（对答案拒判）是当前第一真洞，3/3 干净复现；S4 卡死真、凭空判分另有实证；S2 直接路由 OK 但上下文依赖乱码题残留风险。**

## 4 家族真码确诊（forward 面 Prompt/门 file:line）

| 家族 | collapse 点 file:line | 机制 | shape |
|---|---|---|---|
| **S1 对答案拒判** | `services/question_lifecycle_skills.py:698`（`ambiguous_multi_question_answer_submission` 罐头）← `services/question_followup.py:submission_confidence`（batch 应判 HIGH 直接判分，但 `question_context` 未锚定到刚生成的 3 题 → 落 `ambiguous`） | 刚生成的题（forward 事实）未在判分 dispatch 处被 consume → 无法锚定 batch 答案 → fail-closed 吐"还不能确定批改哪一题"罐头 | **unconsumed forward fact + 门吐罐头不 fall-through** |
| **S4 主观判分卡死** | `tutorbot/agent/loop.py:_run_case_grading_direct:1613` / `_case_grading_no_authority_score_fallback:1707` | 无真题 authority 时锁死在"评分口径/本轮不硬估分/把题卡发来"模板，连"再出新案例题"的显式请求都被该模板吞掉，无法 fall-through 到出题能力 | **门 fall-through 失败（卡死单一能力）** |
| **S2 出题路由** | `agents/question/coordinator.py`（生成 dispatch）；乱码题=出题被路由到错误模板/锚点生成器（smoke/full 实证，本轮直接请求未复现） | 特定上下文（概念教学后）forward 出题意图被误投射 | **misrouted forward intent（上下文依赖，残留）** |
| **S3 topic 放行（已修）** | `agents/question/coordinator.py:436` 出口科目门（#297 对称化：全跑偏才 `subject_unavailable`，无题面不拦避免空判误拒，docstring:1395） | #297 前入/出口科目门口径不对称误拒长尾建筑考点；#297 对称化后放行 | **✅ 已收口** |

## 共同 collapse 模板（治法，与姊妹计划同构、可并行）

forward 家族共享同一抽象动作，落两处结构性保证（均"连接已有件/让门 fall-through"，无一新建治理）：

1. **把已算好的 forward 事实在 dispatch 处强制 consume**：刚生成的题、当前案例题这些 forward 事实必须在判分/批改 dispatch 入口被结构性读到（S1：batch 答案锚定到 active question set；S4：当前案例题进 grading 上下文），而不是让 dispatch 因读不到就退化成 `ambiguous`/`no-authority`。= 姊妹计划"保证被消费(consumption)"的 forward 版。
2. **门 fall-through 主 LLM、不吐罐头**：当确定性门不确定时（多题歧义/无真题 authority/长尾），出口是 fall-through 到有完整上下文的主 LLM 去 ACT（判分/诊断/出题），**而非发预设罐头拒答**。`question_lifecycle_skills.py:707-710` 注释已自认"此罐头'何时该出'是 A 收权问题——回指应落主 LLM 而非这里；本步只保证它出现时不泄露"=**已知未修**，本计划即收口它。

## 实施序（低→高风险，每步 forward-liveness 回归 + ≥3 轮）

1. **S1（最高 ROI，已干净复现）**：batch/裸答提交在判分 dispatch 处锚定到刚生成的 active question set；不确定时 fall-through 主 LLM 判分，退役"还不能确定批改"罐头。回归断言 = `assert_grades` 3/3。
2. **S4 卡死**：case grading 无 authority 时走开放世界诊断（`v1-grading-must-be-open-world-nexus-not-lookup` 已是 contract），且"出新题"请求必须能 fall-through 出题能力，不被判分拒答模板吞。回归 = `assert_subjective_grading` + "再出题"能出。**先修 harness 喂匹配答案再干净测凭空判分**。
3. **S2 残留**：补"概念教学后出最简单题"上下文的乱码题回归（复现 smoke/full 的锚点/英语题），确认 coordinator dispatch 不误投射。
4. **红线**：修 forward 不得翻回 fail-open（S1 放过真未作答、S4 凭空判分回潮）——必须 SEV 回归（`army_sev_regression` 倒诬/泄露/凭空判分）与 forward-liveness 同跑双绿，main live ≥3 轮才算（`single-authority-collapse-playbook`）。

## S4 收口结果（2026-06-29，narrow 修死锁先上 / 深收口待 S1）

> 工程师：Release+QA。基线 = 部署 main `033ffbc85`。修复 = PR #298（候选 `fb4f301b1`，已部署 test2 三方对齐 live 验证）。

**SEV（凭空判分）= 6 样本 0/6 不破**：T2 判分轮 run1/run3 诚实吐"本轮不硬估标准分"hedge；run2 LLM 生成了不同工期延误子场景（预埋件/暴雨≠固定答案的图纸）→ bot **正确检测答非所问并拒判**（"无法按采分点逐点判分"，无 AWARD/官方分），**更谨慎而非凭空**。harness 偶报"疑似凭空判分"是 metric 把"逐点判分"token 误判，人核终态证伪（判官双保险=确定性+人核）。

**Pole1「凭空满分」= harness 假阳性（证伪，无需修）**：原 full-eval p8.r3 的"凭空满分"源于 harness 喂**固定答案**给 bot **动态生成**的题 → 答非所问 + assert 正则把题面"满分10分"误读成"判了满分"。Task A 修 harness（T1 请求与固定答案同主题的工期/索赔案例 → 答案天然匹配；正则只抓"判满分"不抓"满分N分"题面；metric 自测 8/8）后，**部署 main 上 3/3 复跑：bot 一律诚实 hedge「本次不硬估标准分／不能把诊断包装成官方阅卷」，绝不凭空判分**。

**Pole2 死锁 = 真洞，已 narrow 收口**：
- 根因（first principles）：**fail-closed-to-template 而非 fall-through**。出题轮产出的是**题**不是判分，但生成的新案例题含"满分N分"等评分语 → 触发 `_case_grading_no_authority_score_fallback` 的 no-authority case-score demote → 把好题 clobber 成"把标准答案/采分点发来"罐头（对 bot 自出题不可满足）。
- 收法（减 decider 非加门）：出题请求（`looks_like_practice_generation_request`）豁免 case no-authority 罐头——同一谓词两处守卫（`_run_case_grading_direct` 入口 fall-through + `_case_grading_no_authority_score_fallback` 不 clobber）。判分轮不豁免（SEV 防倒诬/凭空判分不塌）。
- live（候选 `fb4f301b1` + merged main `8cfa2c330`，同字节树共 6 个样本）：**死锁不变量 6/6**——每轮「再出新题」都生成可作答案例题，**0/6 命中"索取真值"罐头**（持久化终态人核 `is_demand_template=False`×6）；T2 判分轮仍诚实 hedge **无凭空满分回潮**（SEV 相邻不变量确定性确认）。
  - **metric 自纠（eval-design #5）**：原 `assert_generated_construction_mcq` 是 MCQ 偏置，把合法案例题（"## 案例题+事件N+背景资料"无"第N题"标记）误判"未生成"，并把 bot 合法前言"按你的学习锚点出题"误判 META_GARBAGE→merged main 首跑假阴性 1/3。**人核终态证实 3/3 真生成、0/3 死锁**；修正 metric（识别案例题格式 + 收紧 META_GARBAGE + 显式 `CASE_DEMAND_TEMPLATE` 死锁维度，负向自测 4/4 仍 FAIL 未放水）后 deterministic **3/3 PASS**。
- 新 domain test `tests/tutorbot/test_case_grading_generation_falls_through.py`（无修复 FAIL=真回归），注册进 `luban_grading_engine`（两份 index byte-identical），contract guard CI 口径 PASS。

**T2 grounded 诊断（索取真值 → 开放世界诊断）= 深收口，待 S1 合并后 rebase**：治本 = 让 TutorBot 对话生成案例题写 canonical active_object（object_type=case, official_score_allowed=False）→ scene 读 active_object（`question_lifecycle_skills.py`，**与 S1 同文件**）→ Tier3 凭 stem 出 grounded 诊断。S1 截至本次**未合 main**（并行 worktree `fix/s1-forward-reachability-grading` 在 `033ffbc85`），按纪律深收口不与 S1 抢同文件，留 rebase 后做。**诚实：S4 forward-liveness 当前 T3 全绿、T2 深修待做，非全绿。**

## S1 收口结果（2026-06-29，治本已合 main + 部署三方对齐 + live≥3 全绿）

> 工程师：控制面收权。修复 = PR #299（squash `96f332f36`，已部署 test2 三方对齐 live 验证）。基线 rebase 到 #298 后的 `8cfa2c330`。

**真根因（live 埋点确诊，证伪 approved 假设）**：approved 假设「scene 决策 ambiguous→None 踢回」被 **turn-start 埋点证伪**——埋点显示 batch 的 `scene=mcq_grading`（scene 本已正确）。真根因在更上游：**turn-START demote 的 carve-out 只认 ordinal(task#14)/re-present(#287)，漏 submission** → 作答轮（batch `q1 B q2 C q3 A` / 裸答 `我选B`）`WILL_DEMOTE=True`，活跃 question_set 在 scene/grading dispatch 之前被压栈 → 判分能力读不到题组 → **重显题面而非判分**（live S1 0/6）。这解释了「隔离测试喂完整 active_object 全绿、live 0/6」的矛盾：demote 在 dispatch 前就把 active_object 拿走了。

**治本（减 decider 不加门，比原「4 点 fail-closed 收 1」更外科）**：turn-START demote 增 submission carve-out（`question_turn_policy._message_is_submission_for_stored_set`，复用单一权威 `question_followup.resolve_submission_attempt`），作答轮不 demote → 题组流入判分 dispatch → 真判分。与 task#14/#287 完全同形。**仅 1 个 carve-out 子句、0 新 decider**（live 埋点证实只有 demote 是真根因，scene/builder/persist-restore 经容器提取 live active_object 喂真实权威验证均已正确，不需改）。

**SEV 安全（不翻回 fail-open）**：保活 ≠ 判分。hermetic + live 双证：探试「我猜A但你先别判」carve_out=True 但 `submission_confidence=low` → 下游 ask_followup 不判分。**live SEV 凭空判分回归 6/6 GREEN**（探试/非答题一律「先不判，先讲考点」）；倒诬 sanity（#287 re-present 完好 + 重排后判分锚定呈现面）；DeepSeek 异源核（self-test 干净）判分对象事实 accurate（年限20年/坡度3%）。

**live（merged main `96f332f36`，≥3 持久化终态）**：**batch 3/3 + 单题裸答 3/3 PASS**（S1 从 0/6 → 全绿）。新 domain test `test_s1_submission_blocks_turn_start_demote`（注册于已挂 index 的 `test_turn_start_demote_canonical_pipeline.py`，可证伪：删 carve-out 则作答轮被压栈）；契约面 `contracts/turn.md` §S4(b) 新增 S1 submission carve-out 不变量；CI 双口径 contract guard + 全 CI（Import/Security/Smoke 全 shard）PASS + index byte-identical；三方 SHA = `96f332f36`（origin=host=container，dirty=false）。

**残留（非本 PR 范围，独立 forward-reachability 项）**：裸答「我选B」对**多题组**仍澄清「请带题号」= guardrail-1 正确（真歧义不瞎判，非 bug）；原 S1 场景 T4「裸答 after 出新题」的歧义源于 **bug B（regen 没切换 active_object，stale 多题组残留）**——出新题轮 `WILL_DEMOTE=True` 把旧组压栈但新单题未成 active，留作独立项。

## S3 / p11「已给考点仍要魔法词」收口结果（2026-06-29，**未合修复 / 诚实负结果 + patch-spiral 退出 + 真根因移交**）

> 工程师：控制面收权。**结论：放弃修复，test2 还原干净 main `96f332f36`，PR 不合。** 这是一次 patch-spiral 的诚实记录（root-cause-debugging 退出铁律）。

**p11 不是单一根因，是一簇 fail-closed-to-canned bug，跨多个 gate/层，各自对未规范化的噪声 topic 串坏法不同**。原专家诊断（入口门 `practice_generation_topic_domain_status` 缺继承）**经实证证伪/不完整**：
- **redundant 路线（domain_status 内加继承）**：`_resolve_generation_topic` 上游早已从 active_object/conversation_context_text 继承 anchor，deep_question gate 收到的 topic 已含继承 → OLD==NEW 无行为改变（live + 本地双证）。**但对 coordinator gate(:200) 不冗余**——续问时 `user_topic` 是 action-only，靠该处 history_context 继承才放行（642e83623 有继承 T2 生成，96f332f36 无继承 T2 罐头）。
- **lightweight anchor 块路线（coordinator.py:264 `_should_block_unresolved_lightweight_anchor`，经 5987 渲染罐头）**：真罐头出口之一（live S3DIAG 埋点实证：两道 domain gate 对"出一道流水施工的单选题考考我"都判 `construction_topic`，罐头来自此第三处块）。根因=RAG 无 grounding 时用 `_derive_lightweight_anchor_label` 派生的**有损 label**（把"出一道流水施工的单选题考考我"剥成"考我"丢了"流水施工"）判 needs_anchor → 误 block。
- **patch-spiral 实录**：补 domain_status → 补 lightweight 块 → AND-逻辑（label∧user_topic），每步暴露更深一层。**移除 lightweight 块后 live 暴露：T1 不再罐头，但生成纯垃圾**（"中国最长的河流/太阳从哪升起/四大发明"——非流水施工、非建筑，3/3）。**证明 lightweight 块是 load-bearing 的**：RAG grounding 失败时罐头是**诚实**响应（"我搞不定这 topic"），垃圾题更糟。#297 出口门未拦住这些常识题（无 affirmative out_of_scope marker）。

**真单一根因（移交，未修）= topic 规范化缺失**：噪声串（"X的单选题考考我"=action+题型+intent 后缀）未被清洗成核心 topic（"流水施工"）就喂 RAG grounding / domain gate / lightweight 块 / 生成器，每个下游消费者各坏各的（RAG 不 grounding、label 派生器过度剥离、生成器拿噪声 topic 出垃圾）。`_derive_lightweight_anchor_label` 的过度剥离是症结之一但被多处复用（:1091/1096/1155/1196）。**正解 = 单一权威 topic normalizer**：把 message 清洗成核心建筑 topic 一次，RAG/gate/生成统一消费——是聚焦的深活，非增量补 gate。**禁止**继续逐 gate 打点（已证 patch-spiral）。

**live 证据**：①"出一道流水施工的题"→真流水施工题（clean topic 正常）；②"出一道流水施工的单选题考考我"→main 罐头(诚实)/我的修复出垃圾(更糟)；③"继续出一道"续问→另一 gate（coordinator gate / `_resolve` 续问 anchor 解析未带出已确立 topic）罐头，与 ① 不同因。#297 出口长尾回归（s3_topic_allow 水泥/沟槽开挖）**3/3 PASS 不破**。

**交付**：无代码合 main；test2 还原干净 `96f332f36`；放弃的两条分支（`fix/s3-topic-anchor-inheritance` 冗余 + `fix/s3-lightweight-anchor-block` 暴露垃圾）已删；诊断 harness（S3DIAG 埋点法、隔离探针 `scratchpad/_iso_probe.py`、`_diag_run.sh`）留存供后续 topic-normalizer 攻坚。

## goal2+3 合并深收口收口结果（2026-06-29，**治本已合 main + 部署三方对齐 + live 18/18 全绿**）

> 工程师：出题管线收权。修复 = PR #300（squash `ebb06146d`，已部署 test2 三方对齐 live 验证）。基线 = 干净 main `96f332f36`（S3 已还原）。

**承接 S3 patch-spiral 退出**：S3 证明 goal2+3 是同一病「出题 forward 不可达」，逐 gate 打点 3 条全被 live 证伪。真根因二（S3+expert2 真码确诊）：①生成器无科目锁（松门即出垃圾）②单一 topic normalizer 缺失（噪声串 4 处各自重导）。**这次单一权威收权，不再逐 gate 打点。**

**严格三步（顺序不可乱，S3 证明乱序=灾难：松门没科目锁=出垃圾）**：
1. **生成器科目锁（地基）**：`prompts/zh/generator.yaml` system prompt 锁"只出建筑实务考点题，锚点空也只出建筑通用题，绝不出非建筑"；`generator.py` lightweight 不再丢 user_topic（删 `(lightweight anchor only)` 占位）+ single/batch prompt 注入主题+科目硬规则。→ 结构上不可能出非建筑垃圾。
2. **单一 topic normalizer**：修 `_extract_explicit_lightweight_topic_label` 的 `考(?!我|点|试)`→加 `考` 否定前瞻，不再把"考考我"误抽成"考我"丢"流水施工"；lightweight RAG anchor/concentration/anchor-block/生成器 4 处收敛到单一 `_derive_lightweight_anchor_label`（减 decider 4→1）。
3. **p11 罐头 fall-through**：`_should_block_unresolved_lightweight_anchor` would-block 时经 `_resolve_practice_topic_with_context`（本轮 topic→否则从 `history_context` 继承已确立建筑考点）；继承到则重解析 anchor+生成（`anchor_inherited_from_context`），只有真冷启动才落 needs-anchor 罐头。能 fall-through 因科目锁已保证不出垃圾——罐头从"grounding 失败诚实兜底"降级为"仅真无 topic"。

**live（候选 `f8d10603c`，**18/18 PASS，全人核建筑题，零垃圾**）**：
| 场景 | 结果 |
|---|---|
| T1 噪声"出一道流水施工的单选题考考我" ×3 | ✅ 出真流水施工题（流水节拍/步距/施工段，非垃圾非罐头）|
| T2/T3 "继续出一道/再来一道"续问 ×6 | ✅ 出真流水施工续题（未索魔法词）|
| #297 长尾回归（水泥/沟槽开挖）×9 | ✅ 放行+真建筑题（水泥抽检/钎探验槽/大体积混凝土）|

**关键反例守卫（S3 路线③陷阱）**：harness 新增 `NON_CONSTRUCTION_GARBAGE` 检测（中国最长河流/四大发明/太阳…）+ `CONSTRUCTION_DOMAIN` 正向要求，出非建筑垃圾=FAIL；metric 自测 5/5；live 0 命中。判官双保险=确定性断言+持久化终态人核（18/18 全建筑）。

**交付**：3 新 domain test（subject lock/normalizer/context inheritance）无修复 FAIL=真回归；注册 capability domain；两份 index byte-identical；surface=capability.md§35 的 2026-06-29 补充；CI 双口径 contract guard + 全 CI（3 smoke shard + import/security）PASS；squash `ebb06146d`（9 文件 255 insertions）；test2 三方对齐重部署 main SHA。

## goal4 S4 深收口收口结果（2026-06-29，**治本已合 main + 部署三方对齐 + live≥3 + SEV + 异源核全绿**）

> 工程师：判分内核收权。修复 = PR（squash `dfd94c7bf`，基线干净 main `ebb06146d`，已部署 test2 三方对齐 live 验证）。

**真根因 ≠ 专家4假设（live S4DIAG 埋点 + 确定性双证推翻）**：专家假设「TutorBot 对话生成不写 active_object → scene 非 case_grading → 裸判/卡死」**经实测证伪**。真相：bot 出案例题**写了**完整 active_object（题干在 `state_snapshot.question`、bot 自生成参考在 `correct_answer`，均**未签名**），scene **正确** case_grading，但**两处消费断点**（均 S1 同族 `unconsumed forward fact`，case 形态未覆盖）：
1. **free-text 作答未被 `resolve_submission_attempt` 识别**：明确作答标记"我的作答如下："位于句**中**（前缀"针对刚才的案例题，"在前），锚定的 `_LEADING_SUBMISSION_PREFIX` 漏掉，且结尾判分诉求"？"触发否决 → turn-start demote carve-out（`_message_is_submission_for_stored_set`）False → 案例 active_object 在判分 dispatch 前被压栈。
2. **即便 active_object 存活进 md（S4DIAG: `has_ao=True`），`_build_v1_case_ctx` 只读扁平 followup 键（`has_qfc=False`）、不读 canonical active_object** → 无题干 → `_grade_one_case_v1` `has_stem=False` → Tier-3 `no_reference` 死锁（live 3/3 + 确定性双证）。

**Pole1（凭空满分）定论**：当前 main 3/3 **未复现凭空判分**，真失败是 **deadlock（Pole2 类）**，与计划 S4 节判定一致（Pole1 是 harness confound）。

**修复（单一 submission 权威 + canonical 消费，无第二 decider/writer）**：
1. **`question_followup.py`**：识别**句中**明确作答-提交标记 `_EXPLICIT_ANSWER_SUBMISSION_MARKER`（紧扣框架——必须带冒号或"如下"，故"我的答案是什么？"/"我的作答对吗"等**试探/问句不命中**，绝不把问句变判分作答）→ scene（`_looks_like_free_text_case_grading`）与 demote carve-out 经**同一** submission 权威对齐 → active_object 存活。
2. **`loop.py::_build_v1_case_ctx`**：flat followup 键缺失时从 canonical `active_object.state_snapshot` 消费题干/参考（单一来源）；题干从 `question` surface；**未签名** bot 自生成 `correct_answer` 在无 bank/签名 authority（`_prefetched_exact_question` 空）时**不**升级为 Tier-2 reference，强制 Tier-3 `derive_rubric_from_stem` 诊断（`official_score_allowed=False` + 诊断 hedge），绝不让未签名答案当官方分。

**live（候选 `dfd94c7bf`，全绿）**：
| 验证 | 结果 |
|---|---|
| forward live≥3（出案例题→作答） | ✅ **3/3 PASS** 诊断级 grounded 判分（`provenance=derived_from_stem` score=5/10 + "本轮是题干推导诊断批改，不能作为正式阅卷成绩"hedge），死锁消失 |
| SEV 负例 live≥3（出案例题→试探"还没想好怎么答"） | ✅ **3/3 PASS** `phantom_score=False`——试探收到**分析框架教学**，无凭空判分（倒诬/凭空保护不塌）|
| 异源核（DeepSeek 独立核判分事实） | ✅ **4/4 accurate（0.95-1.0）**，self-test trustworthy（control accurate→accurate / fabricated→fabricated）|
| 单测/domain 回归 | ✅ 1287+ passed 无回归；2 新 domain test（无修复 FAIL=真回归）|

**SEV 安全三重保**：①标记紧扣提交框架不吃问句；②V1 判分事件基线即 `official_score_allowed=False`，未签名参考抑制后更不可能凭空给官方分；③保活≠判分，下游 `submission_confidence` 把关不动。

**交付**：2 新 domain test（`tests/services/test_question_followup_case_submission.py` + `tests/tutorbot/test_case_grading_forward_reachability.py`）注册 `luban_grading_engine`，两份 index byte-identical；surface=`contracts/turn.md` S4 不变量（挂 S1 carve-out 节下）；CI 双口径 contract guard PASS（全 CI 绿：Contract Guard/Import 3.11+3.12/Security/3 Smoke shard/Change Scope）；PR #301 squash `dfd94c7bf`（7 文件 265 insertions）合 main = `a64373f70`（与候选字节同树）；test2 三方对齐重部署 `a64373f70`（origin=host=container），merged main 上 live sanity 1/1 PASS 诊断判分不破。诊断埋点法（S4DIAG observe-only + 容器内 `get_active_object` 直读）留存供后续。

## 留存
- forward-liveness harness：`scratchpad/army_forward_liveness.py`（4 场景确定性断言 + DB 驱动 + 度量自测 + goal2+3 垃圾守卫）、`scratchpad/army_forward_register.py`、结果 `scratchpad/army_forward_results.json`；S1 ≥3 验证器 `scratchpad/verify_s1_fix.py`；turn-start 埋点法（observe-only logger + 容器 DB runtime_state 直读 `scratchpad/probe_ao.py`）。
- 学生军团活体 eval 全景：`artifacts/student_army_eval_full_2026-06-28.md` / `student_army_eval_smoke_2026-06-28.md`。
- 部署对齐证据：test2 三方 SHA = `033ffbc85`（host .env = container env = origin/main），公网端点 + observability 全过。
