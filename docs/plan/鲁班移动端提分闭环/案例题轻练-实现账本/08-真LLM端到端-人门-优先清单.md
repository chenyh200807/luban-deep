# 08 · 真 LLM 端到端验证 / 人门前准备 / 剩余人门 / 优先清单提案

> 执行账本。设计见 [v1.3 计划](../2026-07-08-luban-case-question-light-practice-capability-plan.md) §2/§3/§6。分支 `feat/luban-case-light-practice-p-1`。

## 真 LLM 端到端 probe 固化(commit `3dd150bbb`)
`scripts/aliyun_probes/case_e2e_real_llm_probe.py`:真 DeepSeek 生成 → 真 RTG1-8 → 真 Qwen 异源 RTG9 → 确定性判分**一条命令跑通**。阿里云容器只读实测 EXIT=0(生成 3 好干扰项无撞正确项 / RTG 全过 / 异源队列空 / A漏 1.20 B 1.50)。可复现真链路证据落盘,不是一次性 harness。
- 一键眼见为实脚本 `8fc9733f8`(每引擎 vs 真题金标 + F16 全链路)。

## "一填 verdict 整条链就亮"端到端证明(commit `2a25ab924`)
**人门前最后一块**:模拟教研 verdict passed → 白名单门**打开** → `resolve_scoring_points`[白名单门入口]出真采分点 → 合取门判分(漏关键点 0.2 < 满分 0.5)。与 fail-closed 空白名单测试**配对**,证明白名单门两侧都对。**从"声称"升为"证明"(反自证)**。
- 拍照真数据反自证 `964f0ca75`:真 F16 采分点(非玩具)+ 模拟 OCR 误差,a5「剥开」误识「剥离」→ fail-closed 不假阳;前链纠错重跑 a5 命中、评分逻辑一字未改。

## 人门前准备(全备齐,让 owner 一动手门就开)
- `segmentation_gold/_教研验收指南.md`(`0c2ab84da`):教两名教研怎么填 review.json 一页纸。
- `scripts/fill_case_whitelist_from_review.py`:教研 consensus=passed 一键灌白名单(现 0 条 fail-closed)。
- 5 题 `segmentation_gold/<qid>.review.json` 骨架 + `proposed_sub_no` 候选(DeepSeek 只读真跑,`e0a4a6c92`):P0011_01→7 小问 / P0010_02→6 / P0014_02→8 / P0013_01→4 / P0017_01_E1→2。**verdict/is_atomic/consensus 仍空——教研 verdict 才是真值**。

## §3「接线进生产判官」状态(显式化,别误判为缺口)
准备侧**已备齐**(`dispatch_grade` 每 kind 单测 + `resolve_scoring_points` 白名单门 + `contracts/index.yaml` domain 脚手架)。**未写的是接线适配本身,且故意不写**:提案 §4 三点(落点/灰度/policy→kind 映射)是 owner 架构决策,拍板前写 = 猜落点 = 越 §3 review-only 红线("不改生产判分逻辑")+ 违 Less Is More。**这不是被跳过的缺口,是被红线正确挡住的门**;owner 一拍,接线是窄改动(judge 前加 policy 分发 + 补 domain 测试)。

## 剩余人门(§6,只有人能做,撞到就停)
1. **双教研填 review.json verdict**(唯一真阻塞,准备全备齐)。
2. **优先清单最终确认**(见下提案)。
3. **接线进生产判官**(需 owner 拍架构:落点/灰度/映射)。
4. **小程序 UI**(前端,且未过教研 verdict 不出给学员)。
5. **部署 test2 / 里程碑 PR 合 main / 3 天 5 人需求验证**。

## §2.7 优先清单提案(证据版,待 owner + 双教研确认才切)
纯读扫描 published 编译库(1221 采分点/174 qid,零 LLM)复现"欠切分"。筛选原则:P-1 排除计算重题(calc 判分不走 LLM,归 P1/P2)、优先零-calc 判断/列举/程序型、锚定已 live 验证的起鼓割补、章节聚焦 `1A434000`(建筑施工技术:防水/屋面/装饰,首发人群胜负手章)。

**建议首批 5 道(全零 calc,同章 1A434000,覆盖列举/程序/判断改正含合取门样板)**:

| 序 | qid | 点数 | 整题分 | 为什么选 |
|---|---|---:|---:|---|
| 1 | `EXAM_1A434000_P0011_01::E0` | 16 | 10 | 起鼓割补,已 live 验证(A/B 判出差异),切分风险最低的锚 |
| 2 | `EXAM_1A434000_P0010_02::E0` | 18 | 15 | 同章防水、高整题分、纯列举型,认→写档2 术语默写素材足 |
| 3 | `EXAM_1A434000_P0014_02::E0` | 20 | — | 同章,题型覆盖 |
| 4 | `EXAM_1A434000_P0013_01::E0` | 13 | — | 同章 |
| 5 | `EXAM_1A434000_P0017_01::E1` | 12 | — | 含判断改正(合取门样板) |

> 最终 N + 逐题切分归 §6 双教研人审 + owner 拍板。
