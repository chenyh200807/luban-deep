# Registry v1 — AI Expert Council Policy Update (M5D)

## 1. 结论：AI 专家组终裁后，9 个 source dispute **无一**可原样入库 Registry v1

- council_approved（可原样 publish）：**0 / 9**
- council_not_publish：**9 / 9**
- 这与 M5B live jury 的下调结论一致：M5A 的 `published_candidate` 短碎片锚普遍过度给分。

## 2. 25 个争议采分点的终裁分布

| council_action | 数量 | 处置 |
|---|---|---|
| `approve_with_repaired_anchor` | 6 | 单点单锚 verbatim 全覆盖，可自动认证（修复锚已记录） |
| `split_point` | 5 | list 部分覆盖：命中项自动认证，余项需教师/外部源 |
| `require_external_source` | 5 | 0 verbatim 锚，真实 source gap |
| `rewrite_point` | 4 | 复合句碎片锚 / 表头-条目错位，需改写 |
| `drop_point` | 4 | 作答提示 / 错误情形复述，非采分点 |
| `keep_draft` | 1 | verbatim 达标但 council <3/4，留 draft |

> 6 个 `approve_with_repaired_anchor` 全部来自"改错题正确做法句"与"逐条情形句"
> （M2-2015-34-01 的 P2/P3/P5/P7/P8、M2-2016-30-01 的 P3/P4），它们是单点单锚 verbatim 全覆盖，
> 是这批数据里**唯一**真正达到自动认证门槛的采分点形态。

## 3. 对 Registry v1 入库策略的更新（建议，不在本轮执行）

1. **list_rule 入库新硬门**：`auto_certifiable` 仅当 `coverage==1.0`（逐项 verbatim 命中）。
   M5A 把 `denominator=N、命中=1` 直接标 published 是过度给分的根因，必须在编译期堵死。
2. **denominator 必须来自真实条目数**，不能用官方答案按标点切碎的伪计数（本批多处 denom 被噪声放大）。
3. **改错题（不妥之处/正确做法）只认"正确做法句"为采分点**，错误情形复述一律 drop。
4. **semantic_allowed / figure_label 永不进入 auto_certifiable**，只能 draft 或改写为 verbatim 小点。
5. **approve_with_repaired_anchor 的 6 个点**可作为 Registry v1 的**第一批 council 级候选**，
   但仍需在正式编译时复跑确定性 verbatim 复验（本协议已留 `source_court_summary_m5d.json` 作输入）。

## 4. 不做的事（红线）

- 本轮**不**生成正式 Registry v1，**不**写 `auto_certifiable=true` 到任何运行时可见产物。
- `ai_expert_council_final` 是终裁**建议 + 证据**，source authority 依旧只认教材 verbatim。
- 不覆盖 M3/M4/M5A 原始 packet；6 个 approve 的修复锚仅记录在 M5D 产物内。
