# 03 · 计划 v1.1→v1.3 / Codex 三轮异源对抗

> 执行账本。产物 = [v1.3 计划](../2026-07-08-luban-case-question-light-practice-capability-plan.md) 本体。这里记"每轮 Codex 揪出什么假、怎么改"。

计划由 5 席专家解法起草(v1.1),经 Codex(异源)三轮红队核到 v1.3。

## Round 1(v1.1 → v1.2)
Codex 揪出**计划里的假声称**:
- "复用 CPM 校验器"——**不存在**(后来 C1 才真新造)。
- "Post-gen G1-G8" 与 `compiler_pipeline.py:139-197` 的 artifact 签发门 **G 编号撞名**。
- 切分应是 **P-1 前置门**(不是后置)——落为 §0#5 + §1限制②。
- register-before-use 写得机械。

## Round 2(v1.2 → v1.3)
- `sub_no` **不能凭空恢复**——它是教研切分验收才产生的真值,编译库缺它 = 欠切分。
- `exam_reference_answer` 被过度归一——**保留**(`answer_key_authority`/`source_ref.kind` 合法用它,见 `rubric_grader_v1.py:201-204/288`、`rubric_compiler.py:84`);评分权威字段才用 `official_answer`。
- P0 依赖倒置;`flaw_correction` 合取门当时**没实现**(后 C2 补);白名单必须**代码级**。
- 门改名 **`RTG*`**(runtime-generation-gate,RTG1-RTG9)避开 G 撞名。

## Round 3(→ 触发 §2.5)
- **NO-GO**:§2.5 P-1 数据契约不可执行,缺"最后一块 = 可执行代码契约骨架"。→ 直接催生 [04 P-1 契约骨架](./04-P1契约骨架-T2PINNED.md)。

## 方法沉淀
异源(Codex)对抗核对"计划里的假声称"极有效——同源自审放过的,异源一眼看穿(与记忆 `cross-model-judge-catches-fabrication-same-source-misses` 一致)。此后每个判分引擎都派 Codex 对抗核,见 [06](./06-七判分引擎-Codex对抗核.md)。
