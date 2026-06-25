# TutorBot 判分/路由单一权威收口 + 出题科目门 + grounding 收权修复计划

- **状态**: Draft（Step1 待实施）
- **日期**: 2026-06-23
- **触发**: 当日真实生产对话评审（150 sessions / 618 msgs，sqlite session store）+ 9-agent Workflow 系统性根因（总指挥官裁决 + 专家团队 root-cause + Nexus 评估 + 异源对抗验证，对抗验证三簇全部 `refuted=False`）。
- **Owner 决策（2026-06-23）**: 现阶段**只服务一建建筑工程实务**，其他科目**诚实拒答**（`subject_unavailable`），**不为 5 门预建空 KB**（避免为未确认需求建权威=过度设计）。
- **关联 task**: #20（簇1 主病）、#23（簇3 grounding 编造）、#24/#8（簇2 出题科目）。
- **关联 memory**: `single-authority-collapse-playbook`、`mcq-grading-routing-gap-answer-always-invariant`、`v1-grading-must-be-open-world-nexus-not-lookup`、`scoring-point-truth-is-grading-compile-pipeline-not-deep-pack`、`cross-capability-context-continuity-invariant`。

## 目标
治本三簇真实生产问题（不治标）：判分非确定/凭空判分/追问拒答死循环、grounding 编造、出题科目跑偏。修法以**收权（单一权威）+ 净删除（less is more）**为主，不新增第 N+1 个闸。

## 非目标
- 不为建筑以外科目预建 KB / taxonomy（owner 决策：他科诚实拒答）。
- 不新增确定性闸/正则翻案/编造探测器/真题黑名单（那是把语义降级成模式匹配 = 主病同款错）。
- 不改 `loop.py` 的 `_degraded_mcq_grading_response`（误改会重现 MCQ 编造 SEV-1）。

## 单一 authority
- **作答态/判哪题/回指**：`turn_semantic_decision`（`semantic_router.py:519/594` 在 turn 开头产一次），下游 orchestrator→deep_question→followup→turn_runtime **只读不重判**。
- **MCQ 判分真值**：①题库 answer-key（命中即用）> ②Nexus-like 按 `question_id` 取 `scoring_point_compile` 采分点+rubric（镜像已有 `build_grading_packet`+`packet_hash`）> ③open-world 兜底（标 `OPEN_WORLD`，不冒充真值）。**禁** RAG 即时生成的 `qa_pair.correct_answer` 当判分真值。
- **学生可见文本 grounding**：单一共享 grounding clause 常量，A（question agents）+ B（chat/TutorBot）两套入口同时引用。
- **出题科目**：出口校验门——生成题考点必须 ⊆ 建筑（唯一有真相的科目），否则 `subject_unavailable` 诚实拒答。

## 三簇根因（Workflow 9-agent + 对抗验证 refuted=False）

### 簇1 — P0 答题态/判哪题 单一权威碎片化（主病，最高杠杆，~22+ 条）
- **一等业务事实**：学生这一句是不是在对此刻面前的某道题作答、是哪一道——全系统只能认定一次。
- **根因**：`turn_semantic_decision` thin-wrapper 迁移只迁一半。canonical 名义权威，但 (a) `_default_turn_semantic_decision`（`deep_question.py:5052`，原作者注释自承 "a second-authority path the migration will remove"）在 canonical 缺失时凭空捏造第二决策、硬钉 `confidence=1.0`，下游无法区分捏造与真权威（9+ 处 `or self._default(...)`）；(b) D1-D13 共 13 个 decider 在 canonical 之后各自正则/启发式翻案（D2 `turn_runtime.py:1140` qid 不匹配静默按位置回退判到错题、D9 `:3792` legacy 覆写 `route_to_grading`、D11 `question_followup.py:939` `should_block_unanswered_reference_reveal` 正则翻案回作答态=死循环产出点）；(c) reveal-intent/回指保活语义判定被放确定性短路层，落不进窄模式就 fail-closed 成罐头（`loop.py:758-800`，夹带内部独白）。
- **failure shape**: authority drift + dormant second authority + duplicate decision + fail-soft-to-fabrication。
- **修法（净删除为主）**: 删 `_default_turn_semantic_decision`（80 行）+ 8 处 `or self._default(...)` 捏造点（deep_question.py:3661/3704/4021/4074/4224/4328/4673/4939/5052）+ D9 覆写 + D11 正则翻案 + D2 位置回退/单 item 无条件绑（turn_runtime.py:1140/1162）。**唯一新增** = reveal-intent 上移 `semantic_router` 成 canonical 子状态 `reveal_allowed`（本身是收权）。
- **最高风险**：删 `_default` 前必须离线全量生产 `route_to_grading` turn 跑 `semantic_router` 断言 **100% 仍判 answer relation**，否则删=误判退化成漏判（打穿判分）。

### 簇2 — P1 出题科目定向缺失（内容真相；owner=只建筑）
- **根因**：宣称 6 门只有建筑 1 门有真相。3 处建筑-only 假权威：`learning_topic_resolver.py:298`（system_prompt 硬编码"建筑实务考点分类器"）、`coordinator.py:1308` `_structured_anchor_matches_topic`（known_terms 全建筑词）、单一建筑 KB。fail-open → 他科 fallback 到建筑 GB50300/汉字拼音题/巴黎常识题。
- **修法（owner=只建筑）**：①**出口校验门**（`coordinator.py:153` generate_from_topic 生成后，无条件）——生成题考点/题面必须 ⊆ 建筑，否则丢弃并诚实拒答 `subject_unavailable`，**禁跨科/无关题库 fallback**；同门顺带题型校验（单选恰好 1 正确项）。②删 `_structured_anchor_matches_topic`（建筑-only 第二科目权威）。③`teaching_modes` block_decision/白名单**降级为仅明确非考试拒答**（入口放宽）。④`subject_id` 收紧为单值 + 诚实 `subject_unavailable`；**不建空 KB**。
- ⚠️ 修正：取代我先前（未提交工作树）"他科开放 LLM 出题+非专项标注"——放行后出题侧无真相会出垃圾题，改为出口门拦 + 诚实拒。

### 簇3 — P1 grounding 编造（同源幻觉，内容真相）
- **根因（对抗验证精化）**：结构化判分真值已收权，但"结构化真值→学生可见文本"这一跳裂成**两套并列 authority**——A=question agents（`_anchor_terms.py`）、B=chat/TutorBot（`teaching_modes.py:81/113` + loop final），各携带互不一致的 9+ 处散碎反编造句 + 2 份 anchor 正则副本。"1.7亿→working_memory 回灌"在 B 路径。
- **修法**：grounding clause **单点收权为一个共享常量**（"学生可见的每个事实主张只能引用题面实际给出的内容/检索证据/系统记录的真实学情；题面与证据都没有的数字/背景/统计一律不写"），`submission_grader_agent.yaml` / `followup_agent.yaml`（当前零约束）/ `generator.yaml` / chat responding+observing / loop final 全部引用同一常量；删 9 散碎 + 2 anchor 正则副本。
- **边界**：grounding/Nexus 只解决"真值来源"，不解决"真值本身错（编译进去的就是编造）"——后者需异源核+register-before-use+溯源门（另一条战线，投产前必过）。

## Nexus 决策：YES，分层围栏
54例4判法机制级根因 = **真值供给非确定**（同一 stem 走 RAG 生成路径每轮重新召回+生成 answer-key/题型→漂移；`answers_match` 是确定性纯函数不漂移）。三层权威如"单一 authority"节所列。新增确定性不变量测试：同一 `question_id` 多次构造 context 断言 `correct_answer+question_type+multi_select` 逐字稳定；判分前断言 `source∈{bank,nexus_compiled}` 拒绝 `rag_generated`。判型（multi_select/answer_kind）随确定性真值取，删 RAG 分支 `len(options)>=5 即多选` 启发式。

## 实施阶段（风险升序、杠杆降序）
- **Step 1（零路由风险，先行）**：簇1 reveal 上移 canonical + 唯一公开投影 sink 去毒；簇2 出题出口校验门（纯增门拒答，不动既有路由）。可独立上。
- **Step 2（中风险）**：簇1 D2 qid 必匹配/删 D9 + 簇3 grounding clause 单点收权。
- **Step 3（最高风险，压阵）**：删 `_default_turn_semantic_decision` —— 先离线反向不变量全绿（生产 `route_to_grading` 100% 仍判 answer）再删。
- **Step 4（供给真相）**：Nexus-like MCQ 真值供给收口（禁 rag_generated 当真值）；簇2 `subject_id` 收紧（owner=只建筑，不建空 KB）。

## 验收标准
- 簇1 live≥3 一致：①原 54 例答对判错样本→答对判对 ②非作答（投诉/逃逸词/纯知识追问/讲解请求）不拒答 ③"都选A"返回 ambiguous 不凭空判分 ④回指刚生成题不拒答（不死循环）。确定性不变量：同 question_id 多次构造 context，`turn_semantic_decision/correct_answer/question_type` 逐字稳定。
- 簇2 live：建筑出题正常；市政/机电等 → 诚实 `subject_unavailable`，绝不出建筑题/汉字题/常识题。
- 簇3 异源核（Codex/DeepSeek）：编造触发 turn（招标背景题/学情汇总轮）判分讲评，异源断言无题面外数字/无未核验真题/学情=系统记录。
- contract_guard PASS（deep_question/coordinator/question_followup protected，同 commit 更新 domain test + contract surface）。

## 不确定性 + 验证/替代
1. **semantic_router 对全量 route_to_grading 覆盖率未知** = 删 `_default` 安全性唯一决定性证据 → 离线取生产 trace 全量 `route_to_grading` turn 跑 `resolve_turn_semantic_decision` 断言 100% answer relation；不达则先补 router 再删。
2. reveal_allowed 上移后泄题边界（序数/回指/显式 reveal）未全验 → 跑泄题对抗集断言未作答题任何路径不出 `correct_answer`。
3. p10 meta-quiz 把非作答输入当出题素材的 sibling decider 落点未定位 → 实施前 grep 确认。
4. Nexus 删 RAG 判型启发式前确认 RAG-MCQ 是否有合法"教学示例"（非 submit-able）用途，避免误删教学路径。

## 相关代码入口
- 簇1：`deeptutor/capabilities/deep_question.py:5052`(+3661/3704/4021/4074/4224/4328/4673/4906/4939/3792)、`deeptutor/services/question_followup.py:939`、`deeptutor/services/session/turn_runtime.py:1140/1162`、`deeptutor/services/semantic_router.py:519/594`、`deeptutor/runtime/orchestrator.py:227`、`artifacts/a_answering_authority_diagnosis_2026-06-22.md`。
- 簇2：`deeptutor/agents/question/coordinator.py:153/196/1308`、`deeptutor/tutorbot/teaching_modes.py:500/617/653`、`deeptutor/services/taxonomy/learning_topic_resolver.py:298`、`deeptutor/agents/question/prompts/zh/generator.yaml`。
- 簇3：`deeptutor/agents/question/prompts/zh/{submission_grader_agent,followup_agent,generator}.yaml`、`deeptutor/agents/question/agents/_anchor_terms.py`、`deeptutor/tutorbot/teaching_modes.py:81/113`、`deeptutor/tutorbot/agent/loop.py`。
- Nexus：`runtime_llm_adjudicator` / `build_grading_packet`（packet_hash 样板）、`scoring_point_compile`。

## 三大原则体现
- **thin wrappers fat skills**：turn_semantic_decision 是 thin 单一权威，下游只读；判分真值 thin 分流到 Nexus 编译资产。
- **first principles**：每簇先还原"坏掉的一等业务事实"再定 authority，不从模块/字段症状入手。
- **less is more**：簇1 净删除 ~5 类 decider + 80 行第二权威，唯一新增是收权式 canonical 子状态；簇3 收敛 9 散碎+2 副本为 1 常量；簇2 出口门+删除是减法。概念/状态/decider 数下降。

## 来源
- Workflow run `wf_3d1545a3-bba`（9 agents / 708k tokens）；日志 `artifacts/tutorbot_fix_test_journal.md` 阶段5；真实对话 `artifacts/today_dialogs_20260623.json`。
