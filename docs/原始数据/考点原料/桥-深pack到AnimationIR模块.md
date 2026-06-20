# 桥·深 pack（弹药）→ Animation IR 视频模块（终端形态）

> **架构定位**：深 pack（`考点原料/成品/*.md`，R1-R8 文本）**不是终点，是弹药源**。终端学员看到的是 **Animation IR 视频模块**（讲懂→闯关→看穿一镜到底，过 `gate.sh`）。**成品存在的目的就是喂给 Animation IR Workflow。**
> **视频造法唯一通路**：[[teaching-animation-only-via-animation-ir-gate-workflow]]——做任何教学动画/视频一律且只走 Luban OpenMAIC-style Animation IR Workflow（v0 lesson.json 加 `animation_action[]` → `gate.sh` 确定性门链 → manifest）。
> **首个端到端验证**：Q02（2026-06-20，过 gate.sh 全绿），证明这座桥通。本文把 Q02 走通的映射固化成标准配方。

## 1. 两层 + 服务关系

```
深 pack(弹药·考点原料/成品/<ID>.md, R1-R8)
   │  服务于 ↓（每节喂 IR 模块一个字段）
Animation IR 视频模块(diagram_microlesson/)
   ├─ <ID>.master.json   ← 深 pack 的 R2/examiner_intent/R5/R8/R3/R4
   ├─ <ID>.lesson.json   ← 深 pack §7 动画分镜 + §2 因果链(+ typed animation_action[])
   └─ <ID>.journey.html  ← render_archetype_journey 渲, 过 gate.sh
```

## 2. 字段级映射（深 pack §节 → IR 模块字段）

| IR 模块字段 | 来自深 pack 哪一节 | 转换动作 |
|---|---|---|
| `master.exam_point` / `taxonomy_ref` | §0 考点身份 + 注册表对齐块 | 取 primary_taxonomy_ref |
| `master.R2_invariant` | **§3 R2 不变量** | 直取一句话不变量 |
| `master.examiner_intent` | **§4.1 examiner_intent** | 直取 |
| `master.R5_scoring_point_refs` | **§5 R5 采分点** | 引用真实 point_id（只引用，终判归 grading artifact） |
| `master.R8_misconception` | **§6 R8 误区→error_code** | 引用真实 error_code |
| `master.variants[]`（闯关：上限/边界陷阱/下限/迁移） | **§4 R3 场景 + R4 变量规则** + **§6 R8 误区** | 分档题←R4 换数值；迁移题←R4 换工程；关键鉴别←R8 最易翻车；每题挂 basis_ref |
| `master.mastery_discrimination`（看穿） | **§4 examiner_intent 易漏点** + **§6 R8** | key_discriminator=中间边界+迁移；真懂/差一层/背过信号 + 暖反馈三档 |
| `lesson.teach.beats[]`（讲懂逐点） | **§7 动画分镜** + **§2 原理因果链** | 每 beat = 一句旁白(§2 因果) + stage + keycard |
| `lesson.beats[].animation_action[]`（typed） | §7 分镜的图元 + §2 因果步骤 | camera/highlight/reveal/keycard，target=`data-id:<舞台节点>` |
| 舞台 SVG 的 `data-*` 节点 | §7 分镜里的图形元素 | 渲染器/lesson.stage 暴露 data-id 供 action target 解析 |

> **铁律**：转换只把 pack 事实**搬进** IR 字段，**绝不改母题事实/采分/error_code/边界**（plan §9 Stop Conditions）。变题/鉴别题标准答案必锚 R5/R8，不凭空设。

## 3. 一个深 pack 变 IR 模块 · 操作步骤（复刻 Q02）

1. **建 master.json**：按 §2 映射，从 pack §3/§4/§5/§6 填 R2/examiner_intent/R5/R8/variants/mastery（variants 含分档+迁移、每题 basis_ref；mastery key_discriminator=边界+迁移）。`schema_version=*.sample.v0`，`official_score_allowed=false`。
2. **建/接 lesson.json**：从 §7 分镜 + §2 因果写 teach.beats（PPT 逐点 + keycard + 先讲后问 qa）；给每 beat 加 typed `animation_action[]`，target 写 `data-id:`；舞台暴露对应 data-id；加迁移铺垫 beat（anchor `master:R2_invariant`）。
3. **配音**：`build_lesson_narration.mjs --print` 过防漂移 anchor 闸 → 去 --print 配音（mp3+timing）。**控时 ~120s**（gate timing 门，>150s REVISE）。
4. **渲染**：`render_archetype_journey.py <ID>.master.json` → journey.html。
5. **过门**：`gate.sh <ID>`（schema/animation_action/data-id/timing-sync/layout/practice/manifest 全 blocking）。红→绿只改表现层。
6. **出 manifest**：card_bundle_manifest（资产 sha256 + authority 标 candidate）。

## 4. 对续产的含义（弹药与视频一条流）

- **续产目标不是"文本 pack"，是"深 pack → IR 视频模块"一条流**。产 B02/C07/S05 等新 slot 时，深 pack 产完即按 §3 转 IR 模块过 gate.sh。
- **深 pack 结构已天然服务 IR**：R1-R8 + §7 动画分镜就是 IR 模块的料；§7 是关键喂入（13 个已产 pack 全有 §7）。
- **已产 12 个 = 12 份待转弹药**：Q02 已转（过门）；其余 11 个按注册表 priority 排队转 IR 模块。
- **coarse_review pack**（Q03/C06/S07）：弹药可转 IR 但 IR 模块同样**不进学员默认入口**，直到 leaf review 通过。

## 5. 状态
- [x] 桥确立 + Q02 端到端过 gate.sh（首验）。
- [ ] 11 个已产成品 → IR 模块（按注册表 priority：S06/S02/C04/C05/A01/Q01/C02/K01/N02/S01/Q03）。
- [ ] 续产新 slot（B02/C07/S05…）= 深 pack + IR 模块一条流。
