# type-decision · ④ 判断/分支原型

- **何时选**:考点本质是"条件→判断→结论",不是顺序(①)也不是对错并排(⑤)。学生丢分=记不清"什么情况该怎么判"。
- **代表考点**:危大工程是否需专家论证、安全事故等级判定、索赔是否成立、钢筋连接方式选用、专项方案审批责任链。
- **展现形式**:**条件卡逐条点亮**——给一个情形,沿判断点逐条判(满足绿/不满足灰/当前蓝),命中分支走向 → 落到结论卡;每个判断点挂依据 + 采分表达。

## 5 种使用场景(都用同一个 `decision` body 表达,不分裂 schema)

| mode | 场景 | 例子 | 怎么用 judgment_points + outcomes 表达 |
|---|---|---|---|
| `criteria_chain` | 线性判据链→单结论 | 危大是否需专家论证 | 判断点依次,每点 `next_on_met`/`next_on_unmet` 指向下一点或某 outcome |
| `classify` | 按区间分类→多结论 | 安全事故等级 | 判断点=区间判据,命中区间 → 对应 outcome(多个并列 outcome) |
| `all_conditions` | 全要件 AND→成立/否 | 索赔是否成立 | 所有判断点必须 `met` 才走 target outcome;任一 unmet → reject outcome |
| `select_one` | 条件择一 | 钢筋连接方式选用 | 判断点=选择条件,命中 → 选中的方案 outcome |
| `role_path` | 角色/审批责任链 | 专项方案审批流 | 判断点=各环节(谁负责),按序点亮,outcome=完整责任链结论 |

**渲染器统一处理**:5 种都是"判断点序列 → 命中走向 → 结论"。渲染器按 `judgment_points` 逐条点亮 + 高亮命中走向 + `reached_outcome` 结论卡;`mode` 只微调文案(如 `all_conditions` 提示"全部满足才成立"、`classify` 提示"看落在哪一档")。

## 语义色(引用 style-guide)
满足/命中分支 `--correct` 绿;不满足/被淘汰分支变暗灰;不成立条件/危险 `--wrong` 红;当前判断点 `--progress` 蓝;风险/告警 `--partial` 琥珀。

## 交互(克制——关键纪律)
**来自 COVID 决策工具 RCT:决策空间小时,静态逐条点亮 ≈ 交互式,且更透明更省。** 所以:
- 判断点少(≤6)→ **静态条件卡逐条点亮**(默认),点判断点看依据 drill-down,别强加对话式。
- 只有分支多、路径深(如复杂索赔多要件多例外)→ 才上"选分支逐步走"。

## schema body `decision`(沿用 luban_diagram_microlesson.v1,template_type=`decision_branch_reveal(_draft)`)

```
"decision": {
  "mode": "criteria_chain|classify|all_conditions|select_one|role_path",
  "scenario_given": "这道例题的情形(题干,给学生看)",
  "judgment_points": [{
    "id", "question",            // 这一步判什么(如"是危大工程吗?")
    "criterion",                 // 判据(含阈值,如"基坑开挖深度≥3m")
    "verdict": "met|unmet|na",   // 对本例题的判定(教研【预编译】,非 runtime 算)
    "verdict_reason",            // 为什么(如"本工程5.5m≥3m")
    "basis",                     // 依据(教材/规范溯源·candidate·未签发)
    "scoring_point_binding",     // 引用 scoring_points[].id(reference-not-duplicate)
    "next_on_met", "next_on_unmet" // 走向:下一点 id 或 "outcome:<id>"
  }],
  "outcomes": [{"id","label","kind":"target|reject|alt","scoring_point_binding"}],
  "reached_outcome": "<outcome id>"   // 本例题最终走到的结论
}
```

## 验收点(原型专属)
1. **判断渲染器只渲染教研预编译的例题判断示范,不 runtime 判断、不判分**(判分走 LLM 开放世界,见硬约束40;编译判据是弹药非门槛)。
2. `verdict`/`reached_outcome` 自洽:沿 `next_on_met`/`next_on_unmet` 从首点能走到 `reached_outcome`(渲染器校验)。
3. **判据/阈值必须教材原文溯源**(`basis` 带 provenance);candidate 不冒充签发。
4. 每判断点 + 结论经 `scoring_point_binding` 引用 `scoring_points[]`(不复制);采分表达就是"答题该怎么写"。
5. student-safe:`question`/`criterion`/`verdict_reason`/`basis`(人话依据)/采分表达上屏;`source_ref`/`scoring_point` id/内部词进 internal_only。
6. 简单判断用静态逐条点亮,不强加复杂交互(COVID RCT 纪律)。

## 祖师爷参照
**临床决策路径**(MedDM 临床指引树、yWorks 交互决策树)——条件→分支→结论的成熟可视化;但**移动端 + 决策空间小,优先静态逐条点亮而非交互树**。

## 现状
✅ 样板 `../J01_danger_work_expert_argumentation.schema_draft.json`(危大是否需专家论证,`criteria_chain`)+ `../render_decision_card.py`(逐条点亮 + 依据/采分 + 旁白同步,复用 C01 脊柱)。其它 mode(classify/all_conditions/select_one/role_path)schema 已就绪、渲染器统一处理,逐个考点扩。
