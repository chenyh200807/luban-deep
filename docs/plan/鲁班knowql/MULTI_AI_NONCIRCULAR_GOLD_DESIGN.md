# 多-AI 非循环 scaled gold 设计 — 替代真人 IRR 做 Stage 4 生产门

> 挂靠 `CASE_RUBRIC_SOURCE_MIGRATION_PLAN.md` Stage 4(golden 回归门)。本文回答一个问题:**没有人类专家时,
> 能否用多-AI 造出一个"非循环到足以当生产判分门"的 gold,替代 redline 要求的真人 IRR?**
> Status:`Designed + calibration-validated`。生产采用仍需 owner 授权。三原则:thin wrappers / first principles / less is more。

## 0. 核心难题(为什么不能随便用 AI 当 gold)

用来**度量 AI 判分**的 gold,本身**不能是同源 AI 判分**——否则是循环(tautology),"X 赢"是构造出来的假绿。`golden_v1` 其 redline 自承"两者皆 AI、非人类真相、PO 签待定、顶级 IRR=v1 待真人",正是这个陷阱。`four-arm-ab-judge` 的"同源循环"、`m35` 的"额度墙伪 NO-GO" 都是同一病。

## 1. 第一性原理:非循环来自两个独立支柱,不来自"labeler 是人"

**关键洞察:gold 的非循环性,来自 ANCHOR 与 INDEPENDENCE,而不是"标注者必须是人类"。**

| 支柱 | 内容 | 为什么破循环 |
|---|---|---|
| **① 外部锚** | 判定锚定**官方答案逐字 + 踩字规则**(已发布、不可变、外部权威),不是 AI 的"主观印象" | 真值来自题库外部权威,不是模型生成 |
| **② ensemble 独立于生产判分器** | 造 gold 的模型/流程**与生产 grader 不同**(不同家族、加对抗、Opus 终裁);**生产用哪个模型,gold ensemble 就排除哪个** | 度量对象 ≠ 度量工具,二者不同源 |

人类 IRR 的价值也正是这两条(人独立于系统 + 锚官方答案)。**多-AI 若同时满足这两条,就是人类 IRR 的可校准代理**——不声称"是人类真相",声称"对人类标签校准过的非循环代理"。

## 2. 校准证据(本设计已实证,非纸面)

对 **po_slice 131 个真人工 point-label**(`po_labels_filled.csv`,唯一非循环人工 gold,24 对全覆盖)跑三模型独立判分(各自只锚官方答案+踩字,互不看):

| ensemble | vs 人工 per-point 一致率 |
|---|---|
| 单模型 | DeepSeek 93.9% / Qwen 94.7% / Opus 94.7% |
| **{Qwen,Opus}(排 DeepSeek)** | **94.7%** |
| **{DeepSeek,Opus}(排 Qwen)** | **95.4%** |
| {DeepSeek,Qwen}(排 Opus) | 93.9% |
| **3-model 多数票** | **96.2%** |

**决定性发现:任意"排除一个模型(=潜在生产模型)"的独立子集,仍 ≈ 人工 ≥94.7%;3-model 多数票 96.2%。** 这经验性证明:**一个独立于生产 grader 的 ensemble + 外部锚,是 ≥94.7% 的有效人工代理**。driver:`phase1_blind_graders.py` + Opus 校准 `opus_calib_*`。

## 3. 设计:scaled gold 生产流程

```
官方答案(外部锚) + 采分点 label/official_basis + 学生作答
   │
   ├─ ① 跨家族独立提议(≥2 模型,排除生产 grader 的模型;各自只锚官方答案+踩字,盲标互不看)
   ├─ ② 对抗层(Codex/GPT-5.5 反驳 consensus,挑过给/过严)        ← 已验证逮便宜模型共识误判
   ├─ ③ Opus 锚验+终裁(争议项按官方答案结构+踩字裁定)            ← 已验证
   └─ ④ 分层置信落库:
        • consensus(ensemble 一致)        → high-confidence gold(可当门)
        • arbiter-resolved(Opus 裁定)      → medium(可当门,标来源)
        • contested(裁后仍分歧)            → **escalation 队列,不强造假标**(诚实不确定)
```

**must-not-mint / 锚定纪律**:命中判定必须能 cite 学生作答逐字依据 + 锚官方答案要点;近义/错位按踩字铁律=miss。

## 4. 非循环性论证(显式,防自欺)

1. **度量工具 ≠ 度量对象**:生产 grader 用模型 M_prod;gold ensemble 强制 `exclude(M_prod)`。measure(M_prod) vs gold(¬M_prod) 不同源。
2. **真值锚外部**:hit/miss 锚官方答案逐字+踩字(外部已发布),非 ensemble 的自由意见;ensemble 只做"学生作答是否体现官方要点"的对照。
3. **对抗压试**:Codex 主动反驳 consensus,暴露同源盲点(过度原子化/过给),非 redundant 投票。
4. **校准锚人类**:全流程对 131 人工标签校准(§2),代理有效性是**实测的**不是假设的。
5. **诚实不确定**:contested 不强标 → gold 不在判不准处假装有真值(避免 `four-arm` 的 fail-open 回归)。

## 5. 分层置信 → 分层用法(eval-design)

| gold 层 | 来源 | Stage-4 用法 |
|---|---|---|
| high(ensemble consensus) | 多模型一致 + 锚官方 | 直接进 MAE/over-credit 门 |
| medium(Opus arbiter) | 争议经终裁 | 进门但标来源,敏感结论看 high-only 复核 |
| contested(escalation) | 裁后仍分歧 | **不进门**;按 cluster 抽样送 PO 人类抽查(唯一人类锚省到刀刃上) |

**功效诚实(接红队 S2)**:scaled gold 仍按题/班型聚类非独立;**high 层做门、contested 送人审**,不假装全覆盖认证。

## 6. 与真人 IRR 的关系(诚实定位)

- 本 gold **不取代** PO 人类抽查;它把人类抽查从"标全部"压到"只抽 contested + 分层抽 high 层复核"——**人类锚省到刀刃**。
- redline 的"顶级 IRR=v1 待真人"仍成立:high-confidence gold 是 **v0.9 校准代理**,真 v1 = 本 gold + PO 抽样背书。
- **flip 生产门**:用 high+medium gold 跑 MAE-not-worse + over-credit-not-higher;contested 送人审;PO 对分层抽样背书 = 准生产门。

## 7. 落地次序

1. **定生产 grader 模型 M_prod** → gold ensemble `exclude(M_prod)`(否则循环)。
2. **跑 scaled gold**:200 候选案例 × ensemble 提议→Codex 对抗→Opus 终裁→分层落库(复用 `phase5_*` factory 同架构)。
3. **门**:high+medium 跑双臂回归(new vs legacy,接 `phase11`);contested 送 PO 抽样。
4. **修 3 错标节点**(已做,`83506e817`)+ 规模化时校验每案例 chunk_id 身份(content-match,防 po_slice 同类标注错)。

## 8. 不做什么(减法)

- 不把 AI gold 当人类真相用(只当校准代理,标层)。
- 不在 contested 处强造标(假绿源头)。
- 不让生产模型进 gold ensemble(循环源头)。
- 不跳过 PO 对分层抽样的人类背书(redline 的真人锚不可省,只可省到刀刃)。
