---
name: lecture-waterproof-energy-decoration
description: "基于 2025.6.21 一建建筑实务《防水&节能&装修工程》讲义提炼的专题 skill。适用于防水、节能、装饰装修相关问答，含三专题导航与讲义/规范冲突优先级规则。"
metadata: {"nanobot":{"emoji":"📘"}}
always: false
---

# Lecture Waterproof Energy Decoration

适用于建筑实务中的：

- 防水工程
- 节能工程
- 装饰装修工程

## 用途

这不是规范原文 skill，而是讲义型专题 skill。

优先用于：

- 快速定位章节
- 提炼高频考点
- 补充老师讲课式的易错点和答题抓手
- 帮助 TutorBot 判断用户当前问题更像哪一类专题

## 三专题导航逻辑

按用户消息中的关键词定位专题，一次只进一个专题：

| 专题 | 触发关键词 | reference |
| --- | --- | --- |
| 防水 | 防水、屋面、地下防水、外墙防水、室内防水、卷材、涂料防水 | `references/waterproof.md` |
| 节能 | 节能、保温、外墙外保温、门窗节能、气密性、防火隔离带 | `references/energy-saving.md` |
| 装修 | 装修、装饰、抹灰、吊顶、轻质隔墙、饰面板、涂饰、幕墙 | `references/decoration.md` |

- 同时命中多个专题（如"外墙保温层上做防水"）：按用户问句的**谓语动作**判断主专题，只加载主专题 reference，另一专题用一两句话点到为止。
- 三个关键词组都没命中：本 Skill 不适用，不要硬套讲义口径回答。
- 用户在同一会话内切换专题：换加载对应 reference，不把上一专题内容惯性带入。

## 讲义与规范冲突的优先级

**规范/教材检索结果 > 讲义提炼。** 具体规则：

1. 涉及精确数值、条文号、验收门槛、抽样数量时，先回 `rag`/规范证据核实；检索结果与讲义记忆不一致时，以检索结果为准，并可向学员说明"讲义为助记口径，考试以教材为准"。
2. 检索不到证据时，讲义内容只能以"讲义口径/助记口径"身份输出，不得伪装成规范原文，不得补条文号。
3. 讲义的口诀、答题抓手、易错提醒属于教学表达层，可直接使用；但其中嵌的数字若被学员追问出处，必须回源核实。

## Authority

| 业务事实 | Authority | 本 Skill 的职责 |
| --- | --- | --- |
| 专题地图 | 本讲义 skill references | 帮助定位防水、节能、装修专题和高频抓手 |
| 精确规范依据 | `rag` / 规范原文 / 题库 provenance | 需要时回源核实，不自行定稿 |
| 题目讲评 | `construction-exam-tutor` / `construction-question-review` | 只提供专题背景，不接管题目生命周期 |
| 阅卷评分 | grading skills | 不评分、不估分、不产出 grading result |

## Forbidden Authority

- 不把讲义提炼当作规范原文或唯一考试依据。
- 不直接打分、估分、判定采分点命中或错因归类。
- 不写 learner state、错题本、学习报告或长期学习计划。
- 不决定 TutorBot 路由，也不创建新的专题路由器。
- 不在没有来源核实时编造精确数字、条文号、时间节点或验收门槛。

## Anti-Patterns

- 用户问精确规范条文时，只凭讲义记忆给最终答案。
- 规范检索结果与讲义冲突时，坚持讲义口径不回源。
- 用户提交案例题答案时，本 Skill 直接判分而不是转交 grading skill。
- 把防水、节能、装修三个专题一次性全量塞进回答，遮蔽当前问题。
- 将讲义中的老师表达升级为生产题库、Rubric 或 learner-state authority。

## 渐进式加载

按主题只加载一个 reference：

- 防水：读 `references/waterproof.md`
- 节能：读 `references/energy-saving.md`
- 装修：读 `references/decoration.md`
