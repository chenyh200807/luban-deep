---
name: luban-diagram-microlesson-production
description: 把一建建筑实务考点造成"图解微课卡"的量产线。先把考点归到 6 个展现原型之一,再套该原型的 UI/SVG/交互 + 锚 authority 填 schema + 渲染 + 验收门 + 学员验证门。用于造卡 / 评审卡 / 扩展原型时。
---

# 鲁班图解微课 · 量产 skill(v0 骨架)

> 本目录是 **skill 设计骨架**(暂放 artifacts;ready 后提升到 `agent-skills/luban-diagram-microlesson-production/`)。
> 配套实现:同级 `../SCHEMA.md`(schema 脊柱)、`../render_card.py` / `../render_network_card.py`(渲染器)、`../validate_schema_drafts.py`(校验门)、`../F16_qigu.json` / `../N01_network_keypath.json`(脚手架)。

## 这套 skill 解决什么

建筑实务考点很多,但**认知结构只有 6+1 种**。任何考点先归一个**展现原型**,再套该原型的 UI/SVG/交互 + 锚 authority 填 schema。**展现层站在成熟手艺的肩膀上(每原型有"祖师爷"),护城河在内容层(采分点/错因/authority)。**

## Phase 流程(每造一张卡走一遍)

```
Phase 0  选考点 → 归原型(7 选 1,见下表)→ 混合考点走兜底(见下)→ 查 authority 覆盖(采分点签发/候选?)
Phase 1  锚 authority:采分点→已签发/候选(诚实标非官方,每个 scoring_point 必带 kind + 候选 source_ref 加"(教研草拟·候选·未签发)"后缀)、
         错因→ERROR_CODE_REGISTRY、知识→canonical taxonomy、前置/易混→从 live knowledge graph 拉(见 [[knowledge-graph-already-wired-no-db-needed]])
         采分点只在 scoring_points[] 定义一次,正误/诊断 body 用 *_binding 引用,不复制(reference-not-duplicate)
Phase 2  读 references/style-guide.md + 对应 references/type-<原型>.md → 填 schema(luban_diagram_microlesson.v1)+ 旁白脚本
Phase 3  渲染:数据驱动型(graph/diagnosis)参数→自动 SVG;构造/工序型用图元/手作 SVG
Phase 4  验收门:validate_schema_drafts.py 过 + 手机 390px 无横滚 + student-safe(不漏 source_ref/P编号/schema/candidate)+ 采分点绑定对 + 不文生图构造图
Phase 5  学员验证门:复用 ../F16_qigu_product_validation_plan.md,KPI=同类题正确率提升;不过不铺量
```

## 原型选择指南(7 选 1,按"难在哪"而非章节)

| 原型 | 何时选(认知结构) | reference 文件 | schema body |
|---|---|---|---|
| ① 时序/工序 | 有先后顺序的流程/工序/验收 | `references/type-process_step.md` | `steps[]` |
| ② 构造/空间 | 节点/剖面/层次/空间关系 | `references/type-section.md` | `layers[]`(待定) |
| ③ 计算/图结构 | 可计算的图/网络/时间约束 | `references/type-graph.md` | `question_data{activities,dependencies,expected}` |
| ④ 判断/分支 | 条件→分支→结论的判断 | `references/type-decision.md` | `decision[]`(待定) |
| ⑤ 对比/正误 | 对错做法/规范vs非规范/通病 | `references/type-contrast.md` | `contrast_items[]`(草稿,见 ../C01) |
| ⑥ 采分点/诊断 | 答案×采分点逐点判读 | `references/type-diagnosis.md` | `diagnosis[]` |
| (七) 数值/记忆 | 定义/规范数值/参数辨析 | `references/type-value_memory.md` | **不动画化**:静态卡/表格 |

**懒加载**:每次只读 `style-guide.md` + 当前原型那一个 `type-*.md`,不读全部(规模化不变慢,借 diagram-design 范式)。

## 红线(违反即返工)

1. **不文生图画构造图**(构造正确性必须确定性 SVG/图元库,LLM 不画构造)。
2. **采分点候选不冒充签发**:每个 `scoring_points[]` 必带 `kind`(`candidate_teaching_prototype` / 签发后才升),候选 `source_ref` 加"(教研草拟·候选·未签发)"后缀,`official_score_allowed` 不得 true。**`diagram_microlesson_compile::` 这类 ID 看着像签发,必须靠 kind + 后缀拆穿**。
3. **student-safe 靠白名单,不靠自觉**:卡内显式列 `rendering_contract.student_safe_fields` / `internal_only_fields`;学生端只渲染白名单,内部字段(`source_ref` / `error_code`(E03/E06) / `scoring_point` id / `kind` / `P10`/`P11` / `schema` / `candidate` / 母题包)只进 HTML 注释或后台。错因给学生看 `loss_display` 汉语名(如"位置判据缺失"),**绝不露 E-code**。(参考实现:`../C01_construction_joint_contrast.schema_draft.json`)
4. **不上运行时图谱 DB**(前置/易混查 live adjacency 表,O(1);见记忆)。
5. **先讲后测**:讲解(①–⑥步)在前,小练/复测在后,对新生友好。
6. **不接 TTS / 不写 learner_state / 不接生产判分**,直到学员验证门过。
7. **每条动效通向一次练习/反馈**,否则只是"看爽了"非"学会了"。
8. **不分裂 schema_version**:body 待定的原型先用 `<原型>_draft` 的 `template_type` 收口,沿用 `luban_diagram_microlesson.v1`,绝不为草稿另起版本号(同 D01/C01 模式)。

## 元规律(为什么这套成立)

所有成熟范例底层同一模式:**结构化 spec → 标注揭示参数 → 交互式逐步揭示**(爆炸图层参数 / 算法步进 / Grammarly span 标注 / scrollytelling step)。我们的 `schema → 确定性渲染 → reveal` 就是这个模式套到建筑实务。**别重新发明展现,重金投内容层。**

## 混合考点兜底(Phase 0 引用)

很多考点不是干净的单原型(如"基坑支护"=构造②+判断④;"质量通病"=对比⑤+诊断⑥)。**不要为了凑 7 选 1 把考点硬切碎。** 规则:

1. **定主原型**:看"这题最难的那一步靠什么认知结构过"——它定 body(`steps[]` / `contrast_items[]` / `diagnosis[]` 三选一,互斥)。
2. **次结构降级嵌入**:次要结构进辅助字段(如对比卡里嵌一句判断依据),不另开一套 body。
3. **真跨两类且都重**:拆成**卡组**("主卡 + 对比卡"按 `card_id` 串联),每张仍是单 body 的合法 v1 卡,而不是一张卡塞两套 body。

判据:一张卡 = 一个主 body。塞不下就拆卡,不是分裂 schema。

## 专家 panel 加固(2026-06-17)

三路只读专家(学习科学 / 单一权威+root-cause / 红队+生产边界)系统评审后,收敛出 6 个**真问题**(已按 less-is-more 过滤掉伪需求),修法已落到上面的 Phase / 红线,并由 `../C01_construction_joint_contrast.schema_draft.json` 作为参考实现:

| # | 真问题(shared failure shape) | 修法落点 |
|---|---|---|
| ① | 混合原型无兜底——7 选 1 逼着把混合考点切碎 | Phase 0 + 上节"混合考点兜底"(主 body / 降级嵌入 / 拆卡组) |
| ② | student-safe 没机制保障(`dormant authority`:红线在,但无白名单兜它,renderer 照样漏 E-code) | 红线 3 改"白名单不靠自觉" + `rendering_contract` 双名单 |
| ③ | candidate 冒充签发(`source_ref` 像已签发;scoring_points 缺 kind) | 红线 2 + Phase 1:kind 必填 + 候选后缀 |
| ④ | 草稿 body 风险分裂 schema_version | 红线 8:`*_draft` template_type 收口,版本不动 |
| ⑤ | 采分点被 body / exam_binding 复制(第二份 truth) | Phase 1:scoring_points[] 定义一次,body 用 `*_binding` 引用 |
| ⑥ | ① 祖师爷 scrollytelling 水土不服(手机是 tab 不是长滚) | `references/type-process_step.md` 祖师爷已改 |

**代码 backlog 状态(把"纸面不变量"变成"运行时 fail-closed"):**

- ✅ **校验门去 dormant**:`../validate_schema_drafts.py` 改**按 schema_version 内容自动发现**所有卡(删手维护清单),C01 不再被静默跳过——之前是 "3/3 OK" 假绿,现 4/4 真校验。
- ✅ **contrast 路径已 fail-closed**(对抗测试验证会咬):`detect_body` 认 `contrast_items` + body 四选一互斥;`check_contrast` 强制 `scoring_points[].kind` 必填 + `scoring_point_binding` 引用闭合(指向不存在的 id 即 FAIL)+ candidate 不得 `official_score_allowed`。
- ⏳ **render_card.py 学生端白名单**(接 renderer/接生产前必须清):学生端按 `rendering_contract.student_safe_fields` 渲染,错因输出 `loss_display` 汉语名而非裸 `error_code`(当前 F16 渲染路径会把 E-code 直渲到学生 HTML)。**无 contrast renderer 前不阻塞造卡**;在它落地前 student-safe 靠**人工对照 C01 的 `rendering_contract` 双名单**保障。
- ⏳ **kind/binding 校验推广到其它原型**(当前只在 contrast 路径强制;steps/network 仍按旧规则,避免误伤已绿的 F16/N01)。
