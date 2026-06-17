---
name: deep-question
description: "通用出题 Skill。调用 deep_question capability 生成任意主题的练习题；默认只给题目，用户明确要求才展示答案。"
metadata: {"nanobot":{"emoji":"❓","requires":{"bins":["deeptutor"]}}}
always: false
---

# Deep Question (Quiz Generation)

通过 `exec` 工具调用 DeepTutor 的出题流水线（ideation → evaluation → generation → validation）。

与 `construction-question-supply` 的分工一句话：本 Skill 是**通用出题的 capability 调用层**，supply 是**建筑实务场景的供题策略层**——建筑实务练题走 supply（它带训练意图、题库约束和显隐策略），supply 再调用本 Skill；其他主题的出题直接用本 Skill。

默认行为：

- 用户说“出题 / 考我 / 来一道 / 练习 / 下一题”时，只给题目，不主动公布答案或解析。
- 只有用户明确要求“带答案 / 附解析 / 公布答案”时，才展示答案或解析。

## Authority

| 业务事实 | Authority | 本 Skill 的职责 |
| --- | --- | --- |
| 出题流水线 | `deep_question` capability | 调用 ideation、evaluation、generation、validation |
| 主题与约束 | 用户请求 / runtime context | 传入 language、count、difficulty、type、grounding 配置 |
| 答案显隐 | `answer_reveal_policy` / 调用方策略 | 默认只输出题目 |
| 领域适配 | 调用方 skill（如 `construction-question-supply`） | 接受领域约束，不自行发明领域权威 |

## Forbidden Authority

- 不判分用户答案，不产出 grading result。
- 不写 learner state、错题本、报告或长期计划。
- 不决定 TutorBot 路由；何时调用由调用方决定。
- 不绕过 validation 或 answer-reveal 策略，默认不暴露隐藏答案。
- 不把生成题写成正式题库行。

## 何时使用

- 用户想要某主题的**练习题**或**测验**
- 用户备考或自测
- 用户说"生成几道题""考考我""出练习题"

## 命令

```bash
deeptutor run deep_question "<topic>" --format json -l <lang> [options]
```

### 参数与边界

| 参数 | 说明 | 边界与校验 |
|------|------|------|
| `-l <lang>` | 回复语言 | `en` 或 `zh`；建筑类主题默认 `zh` |
| `--config num_questions=N` | 题目数量 | 默认 1，最大 50；用户要超过 50 时按 50 调用并向用户说明 |
| `--config difficulty=<level>` | 难度 | 仅 `easy` / `medium` / `hard`；"简单点/难一点"等口语先归一到枚举值 |
| `--config question_type=<type>` | 题型 | `multiple_choice` / `open_ended` / `true_false` 等；不确定时默认 `multiple_choice` |
| `--config mode=<mode>` | 模式 | `custom`（默认）或 `mimic`（仿真题风格，需有样题输入） |
| `-t rag` | 知识库 grounding | 主题涉及精确条文/教材口径时必加 |
| `--kb <name>` | 指定知识库 | 仅在调用方/上下文明确给出 kb 名时使用，不要猜 kb 名 |

### 校验失败与异常处理

- 参数越界（数量、难度、题型不在枚举内）：先归一到合法值再调用，并在回复中说明实际采用的参数；不要带非法参数硬调。
- 调用失败或超时：重试一次；仍失败时如实告知用户出题暂时失败，不要手写一道题冒充 capability 输出。
- validation 阶段产出为空或题目残缺（缺选项、缺题干）：不展示残次题，改用更窄的 topic 重新调用一次。
- 指定的 `--kb` 不存在：去掉 `--kb` 降级为无 grounding 出题，并声明本批题未经知识库锚定，不含精确条文口径。

## 示例

基础出题：
```bash
deeptutor run deep_question "Calculus integration techniques" --format json -l en --config num_questions=5 --config difficulty=medium
```

基于教材知识库的选择题：
```bash
deeptutor run deep_question "Chapter 3: Linear Algebra" --format json -l zh -t rag --kb math-textbook --config question_type=multiple_choice --config num_questions=10
```

高难度开放题：
```bash
deeptutor run deep_question "Quantum mechanics fundamentals" --format json -l en --config difficulty=hard --config question_type=open_ended
```

## Anti-Patterns

- 用户说"考考我"，回复里没被要求就附上答案。
- 调用方已给领域约束（考点、题库、显隐策略），本 Skill 用通用假设覆盖它。
- 生成题跳过 validation 直接当作正式题库内容使用。
- 出题后顺手写学习进度或薄弱诊断。
- capability 调用失败后自己手写题目假装是流水线输出。

## 注意

- 多题生成可能耗时**超过一分钟**——`exec` 工具要带 `timeout=300`。
- 解析 NDJSON 事件流，`"type": "content"` 的事件才是生成的题目与答案。
