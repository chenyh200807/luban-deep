# 鲁班母题能力覆盖审计 v1

> 口径：60-slot 母题能力注册表，不是 2116 个 taxonomy 节点的教材全覆盖。
> 真题命中为候选检索证据，不是官方考频；taxonomy ref 不是判分 authority。

## 总览

- 能力槽：**60**
- 已有母题：**41**
- 未建能力槽：**19**
- 注册表内共享 taxonomy ref：**40**

## 未建能力裁决

| Slot | 能力点 | 覆盖强度 | 重叠能力槽（已有/规划） | 缺失能力 | 是否值得新增 | 动作 |
|---:|---|---|---|---|---|---|
| 42 | E02 预付款、起扣点、进度款细分 | missing | C02 / — | 工程预付款的支付 | no | enrich_existing_instead |
| 43 | E03 措施费、暂列金额、暂估价判断 | missing | — / E04/K04 | 合同价款确定与调整；调整合同价款的事项；施工成本管理 | conditional | evidence_first |
| 44 | E04 竣工结算与价款调整 | missing | — / E03/K04 | 竣工结算申请与支付；竣工结算确定与调整；合同价款确定与调整；调整合同价款的事项 | yes_candidate | add_after_exam_evidence |
| 45 | K03 工程变更与签证 | missing | — / — | 工程变更；索赔的管理；索赔的证据 | conditional | evidence_first |
| 46 | K05 工期顺延与费用补偿边界 | missing | K01 / K06 | — | no | enrich_existing_instead |
| 47 | K06 合同责任事件归属矩阵 | missing | K01 / K02/K05 | 不可抗力事件的索赔；发包人可提出的索赔事项；履约事件的索赔 | conditional | candidate_after_boundary_review |
| 48 | R02/R03 耐火等级、疏散距离、防火分区基础数值判断 | missing | — / — | 防火、防烟、疏散的要求；表 1.2-1 室内疏散楼梯的最小净宽度（m）；防火门、防火窗和防火卷帘构造的基本要求 | conditional | evidence_first |
| 49 | R04 防火封堵与幕墙层间防火 | missing | D13 / — | 防火堵料 | no | enrich_existing_instead |
| 50 | N04 时标网络计划与前锋线判断 | missing | N01/N02 / — | 实际进度前锋线比较法 | no | enrich_existing_instead |
| 51 | G05 支护结构监测报警与处置 | missing | B02 / — | 基坑开挖过程中的测量与监测 | no | enrich_existing_instead |
| 52 | K04 合同价款调整触发与计算边界 | missing | — / E03/E04 | 合同价款确定与调整；合同价款计算与调整；调整合同价款的事项 | conditional | hold_until_parent_boundary |
| 53 | K02 不可抗力责任划分 | missing | — / K06 | 不可抗力事件的索赔 | no | merge_into_planned_parent |
| 54 | R05 消防验收流程 | missing | R01 / — | — | conditional | split_only_with_evidence |
| 55 | X05 季节性施工措施: 雨期/冬期/高温 | missing | — / — | 季节性施工技术；冬期施工技术；雨期施工技术；高温天气施工技术；表 3.8-1 防水工程冬期施工环境气温要求 | conditional | split_only_with_evidence |
| 56 | F06 防水材料性能与进场复验 | missing | A02 / D17 | 建筑防水材料的特性与应用；建筑防水材料的特性与应用；防水卷材；防水卷材的主要性能 | no | merge_into_existing |
| 57 | D17 装饰材料进场复验与见证取样 | missing | A02 / D15/F06 | 门窗（包括天窗）节能施工材料复验要求；装饰装修工程主要隐蔽验收项目 | no | merge_into_existing |
| 58 | X04 绿色施工措施 | missing | X03 / — | 绿色施工技术应用；绿色施工评价 | no | merge_into_existing |
| 59 | D15 门窗安装、防渗漏质量控制细分候选 | missing | D14 / D17 | 门窗安装要求；门窗（包括天窗）节能施工材料复验要求；门窗节能工程常见问题治理 | conditional | split_only_with_evidence |
| 60 | D16 地面基层与面层质量细分候选 | missing | D14/Q03 / — | 地面工程施工；建筑地面工程分类 | conditional | split_only_with_evidence |

## 当前裁决

1. **不把 19 个空槽等同于 19 个应新增母题。**
2. **E04 是当前唯一 `yes_candidate`**：独立残差是竣工结算申请/支付与结算确定/调整；补真题证据后再立项。
3. E02、G05、K05、R04、N04 与现有母题共享多数能力锚，优先扩充现有包，不新造平行母题。
4. F06、D17、X04 并入现有母题；K02 并入规划中的 K06，不独立新增；R05、X05、D15、D16 仅保留条件拆分。
5. E03、K03、R02/R03 先补精确 leaf/source；K06 先完成责任事件边界审查；K04 等 E04/K05 边界稳定。

## 全量矩阵

详见 `matrix.csv`（便于筛选）与 `matrix.json`（保留全部 refs、计数和 source SHA）。
