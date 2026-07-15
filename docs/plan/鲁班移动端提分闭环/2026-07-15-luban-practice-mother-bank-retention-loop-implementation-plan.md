# 鲁班视频 Practice × 母题库留存闭环改造计划

> 状态：`P0-A Implemented / P0-B+ Proposed`
> 日期：2026-07-15
> 父级产品 authority：[鲁班移动端提分闭环产品 PRD v1.3](./2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)
> 本文定位：已有主线的 implementation slice；不新建复习模块、不新建题库 authority、不重定义学情真值。

## 0. 总裁决

当前最优路线不是“让 LLM 在用户等待时无限出题”，而是把已经存在但没有连起来的四类资产接成可信供给链：

1. 视频后 633 道原生 Practice 单选题；
2. 979 道当前未被停发的 signed 母题变体；
3. 247 条 signed 错因解药；
4. 1033 道可审核补入现有题库的章节候选题。

产品承诺应是：

> 学完马上做一轮，系统说明为什么会错；当场换一种问法确认；明天再用另一道题验证。题不够时从已签发母题规则确定性实例化，绝不在正式作答链临场造答案。

“实时”的准确含义是实时选择、实时编排、实时反馈。正式题目的事实、答案与评分依据必须在送达前完成编译、校验和签发。运行时 LLM 只允许异步提出 candidate，不能直达考生、正式得分或学情结论。

## 1. 根因，不是表面症状

### 1.1 一等业务事实

每次练习只有一个必须保持完整的事实：

```text
这个用户在这个时间，被正式发了哪五题；
每题的正确答案和错项诊断是什么；
服务端如何重判；
结果是否形成短期练习证据、待复测任务或已验证掌握。
```

### 1.2 曾经争夺 authority 的位置

- finished HTML 自己选题和即时判分；
- 服务端只保存固定五题，丢掉源页面其余题目；
- completion 再运行一次选题算法，可能与签发集合漂移；
- 客户端反馈文案可能自行解释错因；
- variant blocklist 只停发变体，没有停发同一错误事实派生的 cloze、antidote、concept card；
- D+1 只知道 pack，不知道本次真正错的是哪个 `rule_group`。

### 1.3 单一 authority

```text
finished Practice / 母题 Pack / canonical questions_bank
  ↓ build-time fat compiler
可追溯 candidate
  ↓ 质量门 + 教研/规则签发
manifest-pinned compiled pool / signed variant bank
  ↓ Retest selection（精确题集 + supply digest）
题面投影
  ↓ RetestWritebackService server-rescore
learning_evidence / LearnerState / revalidation queue
```

- 前端只呈现、收答案、提交签发凭证。
- HTML 的即时反馈不是正式学习记录。
- 母题、解药、挖空和章节题只能提供候选，不写“已掌握”。
- `source_error_code` 在完成 canonical 映射评审前保持 source diagnostic，不直接升格为 LearnerState 错因权威。

## 2. 2026-07-15 数据盘点真值

| 资产 | 当前真实规模 | 现在能做什么 | 不能冒充什么 |
|---|---:|---|---|
| 正式 Pack | 41 个 | 提供不变量、场景、封闭变量、采分点、答案骨架、误区 | 不等于 41 个都已有安全动态题池 |
| 视频 Practice | 40 个 pack、43 个 surface、633 道合法单选 | 视频后五题轮换、服务端重判、错项诊断 | 不能把 HTML 本地得分当学情终判 |
| Public Practice | 每 surface 精选 5 题，共 215 个展示位 | 保持原稿体验与 WebView 回传桥 | 不再代表全部库存 |
| 母题 variant bank | 18 份、17 signed、1 candidate | signed 且未停发的变体可用于换皮复测 | candidate 与 blocklisted 内容不可送达 |
| Active signed variants | 979 道、134 个考法组、173 个事实锚、约 548 种题面骨架 | 当场换问法、D+1 复测 | 979 不是 979 个独立知识点 |
| 无 active signed 池 | 24 个 Pack（含 E05 candidate） | 可先消费视频 Practice 或审核章节题 | 不得运行时 LLM 补空 |
| 错因解药 | 247 条 signed，覆盖 23 Pack | 错后给一条可执行修正 | 不能独立决定 canonical 错因 |
| 章节题 | 1033 道，981 个标准化唯一题干 | 同考点换题、答案核验、普通解析 | 无 `logic_chain` / `option_reasoning` / `pitfalls`，不能直接做选项级心理诊断 |
| 章节题冲突 | 52 组重复题干、9 组答案字母差异 | 进入编译期复核队列 | 未裁决前不能自动合池 |
| 题目到 Pack 映射 | 38 Pack、258 个唯一真题、680 个歧义候选 | 作为学情 join 候选 | 不能把 provisional mapping 当正式路由 |
| R6 cloze | 仅 A01 signed 16 句 | 完成事实撤销门后可做小规模验证 | 目前不能横向扩张 |
| 看穿题 | 仅 F16 5 题 | 作为诊断深挖 | 不是通用供给 |
| 案例作答层 | 35 Pack、70 份文件 | 支撑深度作答候选 | C02/G03 存双副本漂移，不能按“文件存在”判权威 |

### 2.1 最严重的数据红线

`_variant_blocklist.json` 已停发 40 个存在事实冲突的变体，但 A01 signed cloze 仍包含相同争议答案，例如“变形缝”和“80%”。这证明当前停发只作用于某个文件，不作用于一等知识事实的全部派生物。

因此：

- 关键词填空、半写训练现在不得直接量产或默认发布；
- 先建立 `source fact → variant / cloze / antidote / concept card / answer layer` 派生依赖；
- 任一 source conflict 或 blocklist 命中，所有派生物必须同一次 gate fail-close；
- 修源、重编、重验、重签后才能恢复；
- 禁止再增加一个运行时 blocklist 作为补丁。

## 3. 理想用户体验：一条路，不是七个功能入口

### 3.1 学习首页驾驶舱

首页只给一个最高优先动作，按以下顺序裁决：

1. 有到期 D+1：`用 2 分钟验证昨天的盲点`；
2. 有未闭合课后练：`完成刚学内容的 5 题检验`；
3. 有推荐微课：`学这一小节，随后做 5 题`；
4. 都没有：`继续最需要提分的考点`。

不并列摆“学习、练习、复习、错题、测试”让用户自己规划。复习是学习任务的一种状态，不再拥有独立 Tab。

### 3.2 视频后 Practice 主链

```text
动画讲解
  → 5 题单题聚焦练习
  → 每题即时“对/差一步”
  → 错项诱因 + 失分原因 + 一句修正
  → 当场换一种问法二次确认
  → 服务端收据：今天补了什么
  → 生成次日精确复测
```

交互约束：

- 一页一题，下一题不和解释争夺注意力；
- 先作答再展示解释，不提前泄露；
- 错后最多展示一个主错因和一个修正动作；
- “再来一道”必须同 `rule_group`、不同题面骨架；
- 完场只说“本轮证据”，不说“已经掌握”；
- 没有安全换题时诚实显示“这个考法今天已练透”，不临场造题。

### 3.3 关键词填空与半写的正确位置

它们不是两个新模块，而是系统根据错误类型选用的脚手架：

- 概念边界/数字阈值遗漏：关键词填空；
- 结构会认不会写：给首句或骨架的半写；
- 已能回忆：完整作答；
- 连续失败：回到微课关键帧或教材原句，不继续堆题。

上线前置条件：事实级撤销门、signed answer oracle、模板泄露审计、二次作答服务端重判四项全部通过。条件不齐时只用当前可靠的单选 Practice。

### 3.4 模块边界

- `学习`：承载今日任务、视频、Practice、当场二次作答、到期复测。
- `学情`：只回答“最近补了什么、仍卡哪里、证据是否足够、下一步是什么”，不再造一个任务中心。
- `历史`：只保留对话历史与继续对话；不混入练习流水、复测队列或成绩单。
- `我的`：账户、会员、设置、反馈与隐私。

学情首版只留三块：

1. `最近进步`：已完成并有 terminal evidence 的变化；
2. `当前盲点`：按影响排序的 1–3 个弱点，证据不足要明确写不足；
3. `下一步`：唯一 CTA，回到学习任务。

暂缓雷达图、复杂趋势预测、同龄排名、伪精确掌握百分比和大而全知识图谱。

## 4. 供给政策

### 4.1 当前正式路由

1. 视频结束优先从同 surface 的 compiled Practice 私有池取 5 题；
2. 同用户同日幂等，不同日可轮换；
3. 错后优先取同 `rule_group` 的另一道 signed/compiled 题；
4. D+1 优先不同题面骨架、不同场景或参数；
5. 该 Pack 供给不足时，退到已审核并绑定无歧义的 `questions_bank` 同考点题；
6. 都不可用则停止，不生成未经验证的正式题。

### 4.2 母题生成的三层含义

| 层 | 是否允许 | 说明 |
|---|---|---|
| 已签发池实时选择 | 现在允许 | 请求期只选择，不生成事实和答案 |
| 封闭变量确定性实例化 | P2 | fat compiler 按 signed generator spec 枚举，独立 oracle 校验后签发缓存 |
| LLM 自由生成后立即出给用户 | 禁止 | 同一模型出题又证明答案，形成循环自证 |

LLM 后续只进入异步 candidate 队列：绑定 source SHA、pack SHA、generator version、rule_group、scoring refs；通过重复、多解、旧规范冲突、答案、错因映射和人审后，下一次才可送达。

## 5. 分阶段实施

### P0-A：释放现有 Practice 库并收紧签发（本次已实现）

- `luban_compiled_practice.v2` 私有 authority 保存全部合法单选，public HTML 仍固定精选 5 题；
- 40 个包、43 个 surface 从 215 个固定展示位释放为 633 道服务端库存；
- 同用户/日期在同一签发面确定性选 5 题；
- 选择凭证 v2 绑定 `supply_kind + supply_digest + exact variant set`；
- completion 精确解析签发题集，不再重跑选题；
- item 写入前以唯一 completion claim 绑定 request hash；terminal replay 只读取其 `item_event_refs` 闭包；
- sidecar、manifest、schema registry 和 publisher check 同步升级；
- 不改前端、不新增运行时生成、不改变 LearnerState promotion 规则。

### P0-B：跨派生事实撤销门（下一阻断项）

Owner：内容编译/数据资产；Reviewer：教研 + 评分 authority owner。

- 建立稳定 `fact_id / source_anchor` 派生关系；
- compiler 统一消费 source conflicts 与现有 blocklist；
- variant、cloze、antidote、concept card、answer layer 同步 stale/revoked；
- 修复并重签 A01 争议事实前，cloze 不开放默认入口；
- manifest 从 `has_answer_layer` 布尔升级为 canonical path + SHA；C02/G03 副本裁决为 superseded。

Pass：任一事实停发后，所有派生物在一次 gate 中 100% 不可见；不存在第二套 serve-side 停发政策。

### P0-C：把错项诊断真正呈现出来

Owner：学习体验；依赖：前端安全窗口与微信真机 QA。

- 错项收据展示 `temptation → loss_reason → fix`，正确项只给最短强化；
- 一次只呈现一个主错因，保留“展开看完整解析”；
- 服务端字段直出，前端不得镜像错因政策；
- 错因到 canonical registry 映射未确认时，不写 canonical mistake tag。

Pass：错误选项有诊断元数据时展示率 100%；无字段时诚实降级普通解析；前端零自造错因。

### P1-A：rule_group 级当场二次作答与 D+1

Owner：LearnerState/revalidation；依赖：P0-B。

- item evidence 保留 `pack_id + rule_group + source_anchor + variant_id + skeleton_id`；
- 错题后从同组另取一题，禁止重复原 variant 与同骨架；
- D+1 probe 精确指向未通过的 rule_group，不再只回到 pack；
- 通过只关闭对应 probe；其他弱点不被连带销账；
- 连错两次回微课关键帧/教材原句，不无限刷题。

Pass：D+1 target rule_group 覆盖率 100%；原题重复率 0；完成必须有 signed selection、due probe、server terminal 三证。

### P1-B：1033 章节题进入既有题库 authority

Owner：题库/教研；不是 lesson service 直读 JSON。

```text
raw JSON
  → 52 组去重 + 9 组答案冲突裁决
  → canonical node / pack binding candidate
  → 680 条歧义人工复核
  → source review
  → questions_bank 补录或绑定
  → 既有题目 authority 消费
```

Pass：所有重复和答案冲突有明确裁决；有歧义的 Pack 绑定不得自动投产；线上不直接读取 `docs/原始数据`。

### P2：通用母题 fat compiler

Owner：母题引擎；启动门：P0/P1 留存和质量指标达标。

- Pack 专属代码只声明封闭变量与约束；
- 通用 compiler 负责枚举、答案 oracle、锚验证、去重、答案分布、句式泄露、旧规范冲突和签发；
- 输出继续复用现有 variant bank，不新建平行题库；
- 先覆盖当前无 active signed 池的高价值 Pack，不按 41 包平均铺开。

### P3：异步 AI candidate（可选）

只有当“安全 signed 库耗尽”被真实使用数据证明是留存瓶颈时启动。AI 产物必须经独立规则/模型对抗审查或人审，不得由同一模型自证正确。

## 6. 场景矩阵

| 场景 | 产品行为 | 学情行为 |
|---|---|---|
| 5/5 全对 | 短收据，次日可抽一题确认 | 只记 short-term practice，不立即 mastered |
| 错 1–2 题 | 展示主错因并同组换题 | 建 1–2 个 rule_group probes |
| 错 4–5 题 | 停止堆题，回微课关键帧 | 标记 evidence of struggle，不推断永久薄弱 |
| 二次作答通过 | 说明“这次会了，明天再验证” | probe 仍待 D+1，不提前销账 |
| 中途退出 | 同日恢复同一签发题集 | 不写 completion terminal |
| 题池重签/停发 | 旧 selection fail-close，重新取题 | 不接受旧答案写入 |
| 没有安全换题 | 明示“今日已练透/内容准备中” | 不伪造任务、不写失败 |
| 网络断开 | 保留本地未提交答案，恢复后带原 token 提交 | 只有服务端 terminal 成功才形成记录 |
| 多端同时作答 | 同用户/同日题集幂等，completion 去重 | 单一 terminal；冲突请求拒绝 |
| 章节题映射歧义 | 不自动送达 | 不形成错误 Pack 归因 |

## 7. 指标与发布门

### 7.1 北极星

不是“生成了多少题”，而是：

> 完成一次视频后练习的用户，是否知道自己补了哪个盲点，并在 D+1 回来完成精确复测。

### 7.2 产品指标

- 视频完成 → Practice 开始率；
- Practice 开始 → server terminal 完成率；
- 错后 → 当场二次作答率；
- D+1 probe 送达 → 完成率；
- D1 / D7 留存，必须排除 eval runner；
- “解释有帮助”与“题目重复/像换皮”的反馈率。

### 7.3 机械质量门

- 0 个 blocklisted/revoked 派生物被送达；
- 100% 正式题有 source SHA、pack SHA、generator/compiler version、稳定 variant ID；
- 100% selection 绑定 exact variant set 与 supply digest；
- 100% completion 先 claim canonical request；partial retry 不得由另一请求接管；
- 0 次 completion 重跑选题；
- 同场题面骨架重复率 0（小池回填必须显式记录降级）；
- D+1 原 variant 重复率 0；
- 题目答案可由独立 oracle 或 signed artifact 重算；
- 正式供给路径无运行时 LLM 等待；
- P95 选题投影目标 < 300ms；
- 未签发内容不得写 mastered、正式得分或 progress_countable。

## 8. 红线、假进展与取舍

### 红线

- 不恢复独立复习 Tab；
- 不把历史页变成练习流水账；
- 不让前端、HTML 或 LLM 自报掌握；
- 不从本地原始 JSON 直接线上出题；
- 不为每个 Pack 继续复制一套生成器政策；
- 不在事实级撤销完成前量产 cloze/半写；
- 不把 979 variants 宣传成 979 个知识点；
- 不以 schema/文件存在或 jury clean 冒充内容正确。

### 假进展

- UI 多了“再练一次”按钮，但仍然只抽固定五题；
- 题量变多，但答案冲突、模板泄露和旧规范问题没有 gate；
- 能写入事件，却没有 due probe + terminal + revalidation；
- 雷达图更漂亮，但证据不足仍给精确掌握百分比；
- LLM 出题很快，却没有独立答案与来源校验；
- D1 上升，但由答案位置、重复进入或机器账号污染造成。

### 取舍

- 先单选再半写：牺牲题型丰富度，换正式判分可信和更快闭环；
- public 仍 5 题、private 保存全池：保留原稿体验，同时释放库存；
- 暂不实时 LLM：牺牲“无限题”营销感，换稳定时延、可撤销与可复现；
- 学情只留三块：牺牲图表数量，换用户能立即做下一步。

## 9. 我们双方容易忽略的盲区

### 产品方盲区

- 题不够未必是瓶颈；“不知道下一步做什么”和“错后没有精准反馈”更可能决定留存。
- 实时生成不等于个性化；个性化的核心是选对下一题。
- 原始题多不等于可诊断。1033 章节题没有选项级心理诊断字段。
- 数据签发过不等于事实永远正确；教材升级需要跨派生撤销。

### 工程/专家组盲区

- 过去只数 public 五题，忽略源 HTML 中 418 道未进入私有 authority 的合法题。
- 签发和完成各自重跑选题，违背 exact issued set。
- 复测粒度停在 pack，无法真正验证具体错因。
- 内容 gate 擅长查结构，曾漏掉旧规范、句式泄露和派生副本漂移。
- 容易过早设计完整认写阶梯；当前更稳健的是先让单选闭环跑出 D1 证据。

## 10. 本次交付边界与剩余不确定性

本次只完成 P0-A 后端/资产收权，不触碰现有脏工作区中的前端文件，不部署。前端错项诊断、rule_group 级 D+1、跨派生撤销与章节题审核仍是后续任务。

剩余不确定性及验证：

1. **633 道是否足以显著改善新鲜感**：对 10% cohort 记录 7 天重复题面率与二次作答率；不足再启 P2。
2. **错项三段式是否过载**：A/B 比较默认一条修正 vs 全解析展开率，不凭专家偏好拍板。
3. **D+1 最佳题量**：先固定 1–3 道精确 probe，用完成率和次周正确率决定，不上来做 10 题卷。
4. **章节题 Pack 映射质量**：先复核歧义最高的 3 个高流量 Pack，再决定自动化阈值。
5. **cloze/半写的留存价值**：只有 P0-B 事实撤销门通过后，在 A01 单 Pack 做小 cohort 验证。

## 11. 最小下一步

1. 内容编译 owner 先交付 P0-B 跨派生事实撤销 gate，并用 A01 冲突做必失败回归；
2. LearnerState owner 设计 `rule_group + skeleton_id` due probe，不新建复习状态库；
3. 等前端工作区与微信 helper 安全后，学习体验 owner 只接一项：显示已有 `temptation/loss_reason/fix`；
4. 数据 owner 审核 52 组重复、9 组答案差异，结果进入现有 `questions_bank` 管线；
5. 真实 cohort 验证 D0→D1，未证明 signed 库耗尽前不启动运行时 AI 出题。
