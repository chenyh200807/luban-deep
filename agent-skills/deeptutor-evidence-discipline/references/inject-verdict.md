# 注入片段 · 判断类

**用于**:GO / NO-GO 裁决、内容签发、质量评级、A/B 择优、「这个能不能放行」。

**主要封死**:S1 弱证据升级、S3 局部冒充全量。

---

## 可粘贴片段

```text
本任务要产出一个可机器消费的裁决,不是一段评价。

【裁决纪律】
- 先写下这个裁决需要的证据级别,再写你手上证据的级别。两者不匹配时,
  裁决降级,不要给证据升级解释。
- "未被当前证据推翻" ≠ "已获授权"。前者写 pending / zero-signature,
  后者需要 evidence + identity + human gate 三者独立闭环。
- 覆盖率不抵消单项 FATAL。多数项通过 + 单项决定性事实无锚 = 整包 NO-GO。
- 多个候选/多模型一致,不构成权威。回到 canonical 源(教材/真题/账本/契约)
  仲裁;证据不足时保守判负,不要用一致性冒充正确性。

【判据纪律】
- factual correctness ≠ provenance completeness。事实看起来对,不等于有直接锚。
  逐子断言检查:每个决定性事实是否有单一候选锚直接覆盖。
- 复合结论不能跨多个弱锚拼出一个伪造的单一 provenance。
- 数字、对象、触发条件、宜/应/必须、以及被删掉的限定维度,单独核验——
  它们改变题义。

【输出契约】
逐项输出,每项含:
  verdict:      PASS | REJECT | BLOCKED
  severity:     FATAL | MAJOR | MINOR   (仅 REJECT 时)
  anchor:       支撑该裁决的直接证据(file:line / 原文引用 / 命令)
  limits:       本裁决未覆盖什么
最后给整包 verdict,并显式写出它由哪几条单项决定。

【tripwire — 命中即停并报告】
- 你要靠"综合来看/整体感觉"才能给出裁决
- 决定性事实找不到直接锚,而你想用邻近材料替代
- 你发现判据本身有歧义(先报告歧义,不要自行择一)
```

---

## 这份片段封死了什么(实录)

| 逃逸路径 | 实录原文 |
|---|---|
| 未推翻当成已授权 | 「候选 survived 或 CI 绿就被写成 ready / human signoff。原因:把未被当前证据推翻误写成已获授权」 |
| 事实对就签发 | 「事实看似正确就签发。原因:把 factual correctness 和 provenance completeness 混为一门」 |
| 覆盖率抵消 FATAL | 「大多数修复项通过就 combined GO……任何 field-level mismatch 保持 package NO-GO」 |
| 多模型一致冒充权威 | 「用多模型或候选资产夸大权威。修复:强调回教材/真题、证据不足保守处理」 |
| 候选当正式 | 「把候选 renderer / prototype / skill 当成正式 authority。原因:没有区分 candidate 与 official boundary」 |
| 跨弱锚拼 provenance | 「复合答案不能跨弱锚拼出伪造的单一 provenance」 |
| 禁词扫描冒充语义审查 | 「把固定禁词扫描当语义审查……禁词测试外还做语义/类别级核证」 |

**注**:eval / A-B 类判断另有专门约束(leakage、arm fairness、metric validity),
先过 `eval-design` skill,本片段不覆盖那一层。
