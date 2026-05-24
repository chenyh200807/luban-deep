---
name: lecture-waterproof-energy-decoration
description: "基于 2025.6.21 一建建筑实务《防水&节能&装修工程》讲义提炼的专题 skill。适用于防水、节能、装饰装修相关问答。"
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

## 约束

- 涉及精确数值、条文号、验收门槛时，优先回知识库或规范证据核实
- 本 skill 更适合提供“专题地图、易错点、复习抓手”，不应单独作为唯一权威来源

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
- 用户提交案例题答案时，本 Skill 直接判分而不是转交 grading skill。
- 把防水、节能、装修三个专题一次性全量塞进回答，遮蔽当前问题。
- 将讲义中的老师表达升级为生产题库、Rubric 或 learner-state authority。

## 渐进式加载

按主题只加载一个 reference：

- 防水：读 `references/waterproof.md`
- 节能：读 `references/energy-saving.md`
- 装修：读 `references/decoration.md`
