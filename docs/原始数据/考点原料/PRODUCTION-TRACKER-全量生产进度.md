# 全量生产进度追踪器（开全量·marathon · 已对齐 60-slot 注册表）

> **清单权威**: `docs/plan/鲁班移动端提分闭环/2026-06-19-luban-animation-pack-taxonomy-alignment-registry.md`（60-slot）+ 上游 `2026-06-18-master-plan`。**本追踪器按注册表 priority slot 排产，不再用自排 wave。**
> 流水线: 挖矿→真题取证→4谱系生产→两闸→jury→autofix→**注册表对齐(taxonomy resolve+挂字段)**。
> 状态: ✅两闸全绿+已对齐注册表 / ⚠️coarse_review(不进学员默认入口) / ⏳待产。
> 引擎/工具/SOP 见 ENGINE-OVERVIEW；收口对账见 `收口-注册表对齐对账台账.md`。

## 已产并已收口对齐（12，两闸全绿 + 注册表 code 全 resolve · 2026-06-20）
| Slot | pack | primary_taxonomy_ref | 对齐状态 |
|---:|---|---|---|
| 2 | S01 脚手架/模板支架验收 | `1A436032` | composite ✅ |
| 3 | S02 起重吊装安全 | `1A436000-B006` | direct ✅ |
| 4 | C02 进度款/计量计价 | `1A432000-C17` | direct ✅ |
| 6 | Q01 养护与裂缝防治 | `1A413040-R28` | direct ✅ |
| 7 | A01 检验批/分部分项验收 | `1A434020-B018` | direct ✅ |
| 9 | K01 索赔成立与计算 | `1A432000-B001` | composite ✅ |
| 10 | Q03 质量通病(+v4model) | `1A434032` | ⚠️ coarse_review·needs_leaf_review |
| 11 | C04 模板拆除顺序与条件 | `1A413040-R25` | direct ✅ |
| 12 | Q02 大体积温控裂缝 | `1A413074` | direct ✅ |
| 14 | C05 钢筋连接选用 | `1A413040-R44` | direct ✅ |
| 18 | S06 高处作业/临边洞口防护 | `1A436035` | direct ✅ |
| 20 | N02 网络计划工期优化 | `1A433000-B042` | direct ✅ |

> 全部已挂「## 注册表对齐」块；Q02 另已过 Animation IR gate.sh（首个模块化样板）。

## 待产（按注册表 priority slot，不按旧 wave）
- **P0/P1 剩余直产**: B02(5·基坑支护composite) / C07(16·钢结构连接) / S05(17·三级配电) + N01(8)/C01(13) 深pack化(现仅动画原型)
- **P0/P1 coarse_review(先 leaf review 再产)**: C06(15·砌体留槎) / S07(19·事故等级)；已产 Q03(10) 同此类
- **P2(21-60)**: 按注册表状态排——`direct/composite` 可产；`merged_child`(K02/F06/D17/X04)不独立排产；`conditional_split`(R05/X05/D15/D16)需 source_ref 证据
- 目标 60-slot 全覆盖（近期里程碑 ~40）。**续产每个 pack 必带 taxonomy resolve + 挂对齐字段。**

## 节奏
每波: ①挖矿+取证(确定性) ②4谱系produce(并发) ③两闸 ④jury+autofix。
codex并发多会卡——best-effort,汇编fallback兜底。
成本: ~350k token + ~$0.7/pack。40个 ≈ 1400万token + ~$30。

## 遗留(不阻断量产,40卡产完集中清)
- **🔴排版债(用户2026-06-20指出)**: IR视频模块文字排版差(超长窄列/墙状文字/层次弱/讲懂舞台被压小)。根因=gate.sh布局门只查溢出不查排版质量+VLM视觉judge未接线(plan M5仍report-only)=排版无门管。**修法=改共享渲染器render_archetype_journey CSS一次→re-render全部+VLM judge接gate当blocking,别逐卡手改。先做完40卡再开"排版统一升级"批次。**
- **🔴源库债(C07暴露)**: RichLeaf编译库标签污染(leaf名实不符错挂旁系chunk如R33焊接挂灌浆/防水),pack内绕开未越权改源;攒多了影响大,找点集中修源库。
- 闸2按考点取词需补全(per考点keywords)
- autofix_v2自动改后宜再jury(v3)
- R7 active六阶(B已验核心,r7_construct.py待扩红队/异源终审)
