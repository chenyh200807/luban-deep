# 未答题「隐式求助」答案泄露 — 确定性结构化提示收口（reveal 权威 reachability/consumption）

- 日期: 2026-06-30
- 分支: `fix/persistent-suppress-state`（起点 origin/main `5c2654814`，止血后）
- 性质: 安全 SEV — 真治本。撤销「持久 suppress flag」误方向（3 专家独立证伪：anti-peek 已覆盖跨轮，新 state 违 less-is-more）。
- 前置: Prompt1 止血已合（X+Y/#314 回退，detect 保留，PR #315）。

## 真根因（4 专家 + 指挥官 ground-truth）

单一 reveal/anti-peek 权威（`resolve_reveal_decision` / `should_block_unanswered_reference_reveal`）**本身健康**。病是 **reachability/consumption**：该权威没在泄露出口被消费（同 memory [[reachability-consumption-is-the-real-control-plane-disease]]）。

- **主病（live-dominant，48 会话红队 2/2 复现）**：隐式求助轮（「还是不会 / 给点提示 / 这题选哪个 / 再多说点」）**不被识别为 follow-up → fall-through 到通用 `tutorbot_kb_first` KB 教学策略，该策略不读 anti-peek** → 自由 LLM 用建造师知识**自己推出答案**（泄露轮 metadata 全 `reveal_answers=False`、无 correct_answer 结构字段 → 非结构喂、是 LLM 推 → 软指令/遮蔽已证伪无效）。最强复现：`出题先别告诉 → 给点提示 → 还是不会` → 第3轮 2/2 吐「## 结论 选A」+采分点。
- **次病（bank-anchor 题才触发，传输层经验干净 0/48）**：generation-anchor「题库参考答案（仅内部生成锚点）」被 coordinator 持久进 runtime `knowledge_context`（通道 A/D/I）；reveal 门绕过 E（targeted-brief 短路在 should_reveal 之前）/H（review_mode 渲染整段不读 reveal 权威）/G（deep_question:4266 is_unanswered_block 硬编码 False）。

## 统一边界（owner 拍板 2026-06-30）

> **anti-peek 只压「未答 + 隐式求助」；任何显式要答案一律放行。**

- 隐式求助（还是不会/给点提示/这题怎么想/再多说点）→ 抑制 → 确定性结构化提示。
- 显式要答案（公布答案/直接告诉我答案/把答案给我/直接说哪个对/出题带答案）→ 放行（reveal）。尊重「不能不输出」。
- 作答后判分给答案、concession（认输）→ 现状放行（不动）。

## 收口方案（接通已有件，零新 state，净减 decider；三大原则）

### 边界修（先做，P1 依赖它）
- `detect_answer_reveal_preference`：补认显式 reveal 措辞 → True（直接说哪个对 / 把答案给我 / 把正确答案标出来 / 直接给答案）。同时修 #314 止血遗留的反向过度收口。
- `should_block_unanswered_reference_reveal`：`detect==True`（显式 reveal）→ 返回 **False**（显式放行，anti-peek 只压隐式）。当前只对 concession 放行，漏了显式 reveal。

### P1 主病（优先）：确定性结构化提示短路
- 扩 `_build_unanswered_reference_response`（tutorbot.py:1137）：`should_block=True`（未答 + 隐式求助）且**无 requested_index（通用求助）**时，不再返回 None，而是产**确定性结构化提示**并经 `_emit_lifecycle_terminal_response` 短路（**结构上不走自由 LLM**，动作1 proven 治本）。
- **结构化提示内容（确定性拼，绝不含答案/选项评价）**：考点（`concentration`）+ 通用解题思路模板（审题干关键词 → 回顾该考点规范/数值/原则 → 逐项对照）+ nudge（「先试着作答，提交后我帮你逐项详细讲解；想直接看答案可以说『公布答案』」）。**只用保证无答案的字段**（concentration / stem / difficulty）；P2a 清洗后再可加 knowledge_context 作知识点。
- gate 收窄（避免对一般知识问题/off-topic 误触发）：复用既有 relation/switch 权威——仅当本轮非 topic-switch、非 submission、非显式 reveal 且存在活跃未答题时触发。残留（与考点重叠的一般知识问题）由 live 红队核，over-fire 则收窄、miss 则补。

### P2 次病（紧跟）
- **P2a**：coordinator.py:1279/1307/1381 把「题库参考答案（仅内部生成锚点）」移出 runtime `knowledge_context`（generation 期保留，runtime 字段清洁）→ 同时关 A/D/I。
- **P2b**：E（deep_question.py:1567 targeted-brief 短路移到 should_reveal 之后）/H（deep_question.py:6002 review_mode 渲染消费 resolve_reveal_decision）/G（deep_question.py:4266 传 should_block 真值）。
- **P2c**：`knowledge_context` 加入 `PUBLIC_HIDDEN_PAYLOAD_KEYS`（question_followup.py:581，防御纵深；P2a 后若仍要给学员当背景需先确保无答案）。

## 撤销
- 「持久 suppress flag」方案否决：anti-peek 已覆盖跨轮（未答每轮重判 block），加 flag 会在学员已答后错误续压（违「不能不输出」）+ 这些不消费 anti-peek 的出口同样会无视新 flag = 治症状留根因 + 新 state 争权。

## 验证（确定性主裁，GLM/DeepSeek 仅附加）
- TDD 先 RED：边界（detect 显式/should_block 显式放行）+ P1（隐式求助 → 结构化提示无答案）+ P2（各通道）。
- live≥3 红队：`出题先别告诉 → 给点提示 → 还是不会`（最强复现）连跑 ≥3，可见输出**无答案/无逐项排除**；显式「公布答案」放行有答案（反向不误伤）；不破 3-SEV（control_plane/reveal authority baseline）/A #308。
- 确定性 marker 主裁；GLM-4.6/DeepSeek 异源附加。

## 不确定性（诚实）
- P1 gate 精度：隐式求助 vs 一般知识问题（与考点重叠时仍可能 LLM 推出答案）边界靠 live 红队收敛，非一次到位。
- 结构化提示有用性：纯确定性提示弱于 LLM 启发（owner 已接受此 trade-off，安全优先）。
- by-design：concession（认输）→ 现状放行，未改。
