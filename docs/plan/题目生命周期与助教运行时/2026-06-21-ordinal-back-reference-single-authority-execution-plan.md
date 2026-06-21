# 序数/回指历史题 — 单一权威收口执行计划

- 状态:Draft(Stage A 实施中)
- 日期:2026-06-21
- 主线:挂 `2026-06-20-cross-capability-context-continuity-architecture.md`(同一"切链路丢上下文"根治主线)
- 关联:task#12(收 15+ 闸到单一 reader)、task#13(删伪造兜底)、契约 turn.md §硬约束24、memory `cross-capability-context-continuity-invariant`

## 背景:对抗 live eval 实证的三根因

2026-06-21 串行对抗 eval(9 场景)发现"用户用**序数/位置/属性**回指对话历史里**非当前 active** 的题"时复发 鸡同鸭讲/记忆漂移/失上下文。带 topic/内容判别词的回指(「刚才那道防水题」)正常,纯序数/位置/属性回指失败。专家团队(对抗子智能体)证伪初版"单一权威=LLM分类器"诊断后,锁定**三个独立缺陷**:

| # | 症状(cid) | 实证根因 | 类型 |
|---|---|---|---|
| R1 | E1「回到最开始做错的那道」讲错题(tb_f2483a1…) | `_PREVIOUS_OBJECT_MARKERS`(semantic_router.py:18)不含"最开始/做错的"→ 不识别回指 → 绑 active | 识别缺口 |
| R2 | E8「刚才第3题…讲讲」fail-closed(tb_2caf793…) | `_NUMBERED_SUBMISSION_RE` 数字非串首不匹配 → scene=question_review → 裸文本查题库 → `_render_missing_question_review_feedback` 拒答;**review 路径无序数→item 映射** | 解析缺口+fail-closed |
| R3 | E8「第1题我选A」判成Q2(SEV-1)(tb_2caf793…) | `_prepare_question_submission_context` 单题fallback(orchestrator.py:837-864)把批量集**塌成单题**,后续"第1题"→塌缩集items[0]=Q2 | object continuity 断裂 |

**已实证**:E8 events_json 显示「第1题我选A」判的是 Q2 题面(材料找坡 C=20mm),证实 R3 塌缩。

## 单一业务事实 / 权威

- **一等业务事实**:用户用序数/位置/属性引用历史某道题时,"指哪题"应由**单一 history-aware 解析器**对照对话历史定位被指对象;`active_object` 不是"指哪题"的权威。
- **真正的多头权威(task#12 抱怨实锤)**:`resolve_submission_attempt` 位置解析器、`derive_question_lifecycle_scene` 的 submission 探针、`_PREVIOUS_OBJECT_MARKERS`、review 路径、LLM 分类器 —— 各自独立判"指哪题"且全是 active-set-only / 历史盲。

## 硬约束(专家定,防止治标变更糟)

1. **判分/改答/出类似题轮绝不路由主LLM**:题库精确判分权威(grading_key/answers_match)只在 deep_question;主LLM 判分丢权威或被 degraded guard 拒答。这类必须**解析回结构化历史对象走原路径**,解析不出 → **fail-SAFE("把那道题发我")**,非 fail-closed 失忆、非造假判分。
2. **只有讲解类(prose)**解析不出时降级主LLM从历史讲(C1「刚才那道防水题」已证安全)。
3. **歧义优先澄清**(多道都"做错"、多道同topic)不硬猜;扩 `_decision_from_ambiguity_gate` 覆盖历史候选。
4. **跨 session 历史不在 conversation_context_text = 物理无解**,只能诚实"这次没看到",列后续工单,禁造。
5. **范围内序数绝不误判为切换**(active 批量3题时"第2题"正常走槽位)。
6. **单一 relation 权威**:确定性回指 marker 路径与 LLM"指别的题"路径必须收敛到同一 relation,不得双路径分叉(违 turn.md §24)。

## 分阶段(每阶段独立安全/可测/可上,按 严重度×安全度)

### Stage A(SEV-1·零LLM零正则·本计划首实现)
修 R3 批量题 object continuity:`resolve_submission_attempt` 单题 submission 加可选 `index`;`_prepare_question_submission_context` 在"批量集+numbered单题"时 apply 到**全集**+`preserve_other_answers`,不收窄重建。
- 验收:批量3题判「第2题」后 active_object 仍含3 items(item2 已答);后续「第1题」解析到 item1。回归:单题集判分不变、批量整体提交不变。

### Stage B
修 R2 fail-closed:review 路径序数/回指解析不到结构化对象时,**讲解类**落上下文连续主LLM(复用 orchestrator 现成 is_unresolved_switch→`_default_chat_capability` 路由,line 226/295/425),不再"请粘贴题干"。
- 验收:「刚才第3题讲讲」从历史讲第3题;不丢失结构化判分能力。

### Stage C(真单一权威收口 = task#12 核心)
一个 history-aware "被指对象解析器",所有"指哪题"闸统一 consult(submission解析器/scene分类器/marker/review)。解析回结构化对象→原路径;失败按动作:讲解→主LLM prose、判分/改答→fail-safe、歧义→澄清。扩 `_PREVIOUS_OBJECT_MARKERS` 语义或以 LLM relation 为准并收敛确定性路径。最大、需充分 TDD + characterization + live 复跑 E1-E9。

## 验证

- 单测/characterization:每 Stage 配 TDD red→green + dual-LLM-mock 路由矩阵回归。
- live 复跑:cc_seq2.py + cc_scn2/E1-E9 串行,确认 E1/E8 修复且 E2-E9 不回归。
- contract_guard:改 protected 文件(question_followup/orchestrator/semantic_router/deep_question)须更新对应 domain 测试。

## 不确定项

1. Stage C 的"解析回结构化对象"上界取决于 `conversation_context_text` 是否含历史题的结构化字段(选项/correct_answer)还是仅 prose — 待核写入端。
2. 跨 session(R1类)物理无解,本计划不覆盖,列工单。
3. A1 判分走 open-world 对题库 verified 历史题是否丢 authority,是产品/教研取舍。
