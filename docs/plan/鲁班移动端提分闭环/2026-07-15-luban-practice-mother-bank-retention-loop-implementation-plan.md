# 鲁班视频 Practice × 母题库留存闭环改造计划

> 状态：`S0 本地实现并加固 / 产品 P0A HOLD / 未部署`
> 日期：2026-07-15
> 父级产品 authority：[鲁班移动端提分闭环产品 PRD v1.3](./2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)
> 本文定位：父级 P0A 的供给与证据 implementation slice；不新建复习模块、不新建题库或学情 authority。父级 `P0A/P0B` 是唯一产品阶段名，本文只用 `S0–S4` 表示工程闸。

## 0. 总裁决

方向正确，但现在不能把“编译成功”写成“内容安全可上线”。当前 checkout 已具备题目编译、精确签发、服务端重判和 terminal writeback 的骨架；仍有三项发布阻断：

1. 633 道是**结构可判的 compiled candidates**，不是 633 道已完成教研签发的安全正式题；已发现 A01、F03、G03 等旧口径/事实冲突进入 compiled/public Practice。
2. 视频 WebView 主链仍固定回传 `practice_surface + answer_indexes`，实际取同 surface 的 public 五题；它没有把用户看到的 exact question IDs / projection digest 带到服务端，存在页面缓存与供应重签之间的 TOCTOU。
3. 当场同规则换题、精确 D+1、章节题 fallback 仍是目标能力，不是当前能力；`rule_group` 还是自由文本，不能冒充稳定的复测事实主键。

因此：保持功能开关关闭，先完成内容资格和真入口身份闭包；首发只做父级定义的 **F16 单 Pack 留存纵切**。它通过 GO 后，才扩到 3–5 个 Pack。

面向用户的首版承诺必须缩成一句：

> 看完就做五题，错了告诉你差在哪；有安全题就马上换一道确认，明天再用一题验证。

“实时”只表示实时选择、编排和反馈。正式题目的事实、答案、诊断和评分依据必须在送达前完成编译、校验、签发；运行时 LLM 只允许异步产出 candidate。

## 1. 一等业务事实与单一 authority

每次练习只有一个不可拆散的业务事实：

```text
用户实际看到并提交了哪一组题（exact IDs + projection/supply digest）；
每题的答案、来源和诊断是什么；
服务端如何重判；
哪一个 terminal 精确封存了哪些 item events；
哪些证据可以进入 LearnerState、到期复测和学情展示。
```

唯一链路：

```text
finished Practice / 母题 Pack / canonical questions_bank
  → build-time fat compiler
  → source/fact eligibility gate + 教研/规则签发
  → manifest-pinned compiled pool / signed variant bank
  → exact selection（题目集合 + supply/projection digest）
  → RetestWritebackService server-rescore
  → terminal closure（request hash + exact item refs + score reconciliation）
  → LearnerState / revalidation queue / 学情 read model
```

边界：

- WebView/小程序只呈现、收答案和提交 exact receipt，不解释内容政策、不判断掌握。
- HTML 本地逐题反馈是 teaching feedback；五题完成后的 server receipt 才是 canonical completion。
- `completion_id` 只是关联键，不是提交证书；只有 terminal closure 引用的 item 可以晋升。
- 母题、错因解药、挖空和章节题只提供候选，不直接写“已掌握”。
- `source_error_code` 未完成 canonical mapping 前只是 source diagnostic。

### 1.1 已发现的 authority 争夺

- HTML 本地选题/判分与服务端签发并存；
- completion 曾可重新选题，而不是解析 issued set；
- terminal 只证明 completion ID，reader 却可吸收同 ID 的孤儿 item；
- blocklist 缺失/损坏时 fail-open，且摘要、选题、解析、digest 分别计算 active supply；
- 视频 surface 回传与动态私有题池并存，产品计划把后者误写成视频主链已接通；
- serve-side variant blocklist 不能撤销同一错误事实派生的 compiled Practice、public H5、cloze、antidote、concept card、answer layer 和 questions_bank projection。

## 2. 当前 checkout 的能力真值

| 能力 | 当前状态 | authority / 证据 | 发布裁决 |
|---|---|---|---|
| compiled Practice inventory | 40 Pack、43 surface、633 道结构可判候选 | compiler 校验解析、SHA、单选形状与唯一正确项 | `HOLD`：未完成事实/来源/教研资格签发 |
| public Practice | 每 surface 5 题，共 215 展示位 | 原 finished H5 | 可保留原视觉与本地 teaching feedback，不是全部库存 |
| 私有动态池 | generic learning home 不传 surface 时可确定性选题 | `project_compiled_practice` | 代码可达；视频 wrong-answer 主链未接通 |
| 视频 H5 主链 | 回传 surface + answer indexes，再读取该 surface public 五题 | H5 bridge → retest page → read model | `HOLD`：缺 exact IDs/projection digest，有 TOCTOU |
| exact selection / server rescore | v2 selection 绑定 supply kind、digest、exact variants；completion 精确解析 | selection + `RetestWritebackService` | 本地实现；旧 v1 client 必须重新取题，禁止服务端兼容猜测 |
| terminal learning truth | request hash、精确 item refs、题数与分数闭包；reader 共用 closure | `evidence_lifecycle` | 本次根治；孤儿/partial item 不得进入画像或复测时钟 |
| signed variant supply | 17 signed bank；当前盘点 979 active variants | signed bank + mandatory revocation authority | 缺失/损坏撤题 authority 时全链 fail-closed |
| 错项诊断元数据 | 1899 个错误选项；1827 个有完整 temptation/loss_reason/fix，缺失 72 个集中在 A02 | 当前 checkout 数据盘点 | 可做 F16 小切片；文案只能说“这个选项的常见陷阱是…” |
| 当场同规则换题 | 未实现 | 尚无稳定 fact/rule identity 与服务端二次选择事务 | `BLOCKED S2` |
| 精确 D+1 | 未实现 | 当前复测主要到 pack；`rule_group` 599 个自由文本，只有 61/633 候选处于有替代题的组 | `BLOCKED S2` |
| 章节题 fallback | 1033 道原料、981 个标准化唯一题干；52 组重复、9 组答案字母冲突 | raw docs 数据，不是线上 authority | `BLOCKED S3` |
| cloze / 半写 / 完整作答阶梯 | 不完整 | A01 cloze、部分答案层与个别看穿题 | 延期；事实撤销、answer oracle、模板泄露与服务端重判未闭合 |

补充真值：当前选择器的 7 日合成盘点平均重叠约 45.1%，零重叠约 1.4%。所以“跨日轮换”只能承诺确定性变化，不能承诺每天都不重复。

### 2.1 内容红线

结构校验不等于内容正确。当前盘点至少存在：

- A01 blocklist 明确记录“检验批划分不含变形缝”，compiled Practice 却仍把“变形缝”判为正确；
- A01 仍有 88%/80% 口径问题；
- F03 地下防水等级、G03 超灌高度等旧口径问题可进入候选或公开面。

因此 S1 必须把撤销范围扩成：

```text
source fact
  → signed variant
  → compiled Practice / public H5
  → private pool
  → cloze / antidote / concept card / answer layer
  → questions_bank projection
```

任一 source conflict 命中，全部派生物必须在同一次 build gate 中不可见。现有 runtime blocklist 只作为过渡止血；S1 完成后，资格真相应收回 build-time fact gate，不能再叠一层长期政策。

## 3. 产品形态：一条任务路，不是功能菜单

### 3.1 学习首页驾驶舱

只显示一个最高优先动作：

1. 有到期验证：`用 2 分钟验证昨天的盲点`；
2. 有未闭合课后练：`完成刚学内容的 5 题检验`；
3. 有推荐微课：`学这一小节，随后做 5 题`；
4. 都没有：`继续最需要提分的考点`。

首发删除/延期：独立复习 Tab/条带、并列多 CTA、伪精确掌握百分比、雷达图、同龄排名、章节自动出题、实时 LLM 出题、通用 cloze/半写/完整书写阶梯。

### 3.2 视频后首版闭环

```text
动画讲解
  → 五题（一次一题）
  → 本地最短 teaching feedback
  → 五题完成后 canonical server receipt
  → 错项的常见陷阱 + 失分原因 + 一句修正
  → 有签发替代题才当场确认
  → D+1 唯一 CTA 验证同一事实
```

交互规则：

- 先答再解释；一页一题；错后最多一个主错因和一个动作。
- 不声称“你就是因为……”，只说“这个选项的常见陷阱是……”。
- 完场只说“本次已记录”，不说“已经掌握”。
- 无安全替代题时显示：`暂时没有新的安全题；本次结果已记录，内容补齐后再验证。`
- 连错两次回微课关键帧/教材原句，不无限刷题。

### 3.3 模块边界

- `学习`：今日唯一任务、微课、Practice、当场确认与到期验证。
- `学情`：只留最近进步、当前 1–3 个盲点、唯一下一步；证据不足显示 `insufficient_evidence`。
- `历史`：对话历史与继续对话，不混练习流水、复测队列或成绩单。
- `我的`：账户、会员、设置、反馈、隐私。

当前前端仍有多 CTA、独立复习呈现和 mastery 百分比，这是 implementation gap，不是本文已经交付的能力。本次不触碰已有脏前端，也没有完成微信真入口 QA。

## 4. 分阶段实施与 owner

### S0：供应事务基础设施（本地已实现并加固，非上线 GO）

Owner：lesson supply + LearnerState。

- compiled sidecar 保留全部结构可判单选，public H5 仍保持五题；
- v2 selection 绑定 `supply_kind + supply_digest + exact variant set`；
- completion 精确解析，不重跑选题；claim 先绑定 request hash；
- terminal closure 校验 exact item refs、同 completion/request/pack/mode、题数和分数；
- 所有画像、图谱、报告、pack lifecycle、prescription outcome 和 replay 共用 closure；
- remote learning-evidence reader 过滤 durable control claim；
- signed variant 的摘要、选题、解析、digest、pool meta 共用一个 active resolver；撤题 authority 缺失/损坏全链停发。

Pass：partial/孤儿 item 零晋升；控制 claim 零泄漏；任一读路径不得复活 revoked variant。注意：这只证明事务基础设施，不证明 633 道内容可上线。

### S1：内容资格与跨派生撤销（产品 P0A 的第一发布阻断）

Owner：内容编译/数据资产；Reviewer：教研 + scoring authority owner。

- 建立稳定 `fact_id + source_anchor + source SHA + review verdict`；
- compiler 同时覆盖 variant、compiled/public/private Practice、cloze、antidote、concept card、answer layer、questions_bank projection；
- 对 633 candidates 做 source、答案、旧规范、最长选项偏置、模板泄露、重复与诊断质量审核；
- A01/F03/G03 已知冲突必须成为必失败回归；
- `has_answer_layer` 从布尔改为 canonical path + SHA；C02/G03 双副本裁决 superseded。

Pass：已知冲突 0 送达；任一 fact revoke 后所有派生面一次 gate 100% 不可见；每个正式题有稳定身份、source/pack SHA、review verdict 和独立答案依据。

### S2：F16 产品纵切（父级产品 P0A）

Owner：学习体验 + LearnerState；依赖 S1。

- 视频 H5 提交 exact question IDs + projection/supply digest，服务端只接受所见集合；
- v1 client 遇到供应变化必须 re-fetch；仅 exact set 不变时才保留本地答案；
- 首轮五题 server receipt 后，展示已有错项诊断；
- 引入稳定 `fact_id/skeleton_id`，不以自由文本 `rule_group` 作 canonical identity；
- 错后最多一题同 fact、不同 variant/骨架确认；D+1 同 fact 再验证；
- selection 绑定 probe/cycle；多端同一 probe 只有一个 terminal claim；
- 学习首页只有一个 CTA，复习不再单独成模块。

Pass：真微信 package/auth-chain 完成；所见题集与服务端重判 100% 同一；旧缓存题不能错位提交；原题/同骨架误重复 0；D+1 完成有 signed selection + due probe + terminal 三证。

### S3：章节题进入既有 questions_bank

Owner：题库/教研。禁止 lesson service 线上直读 `docs/原始数据`。

```text
raw JSON
  → 52 组去重 + 9 组答案冲突裁决
  → canonical node / pack binding review
  → 680 条歧义候选人工复核
  → source review
  → questions_bank 补录/绑定
```

Pass：重复和答案冲突都有裁决；歧义绑定不自动投产；线上只消费现有题库 authority。

### S4：母题 fat compiler（仅被真实供给瓶颈触发）

Owner：母题引擎；启动门：S2 留存实验已证明 signed 库耗尽是瓶颈。

- Pack 只声明封闭变量与约束；通用 compiler 统一枚举、oracle、锚验证、去重、答案分布、句式泄露与旧规范冲突；
- 输出复用现有 signed variant bank，不新建平行题库；
- LLM 只异步提 candidate，经独立规则/模型对抗或人审后下一版本签发，不得请求期自出自证。

## 5. 场景矩阵：当前与目标分开

| 场景 | 当前真实行为 | S2 目标行为 |
|---|---|---|
| 5/5 全对 | server terminal 可形成 L0 short-term evidence | 短收据；D+1 一题确认，绝不立刻 mastered |
| 错 1–2 题 | 数据已有诊断字段，前端未完整消费 | 展示一个主错因；有安全题才当场确认；建 exact fact probe |
| 错 4–5 题 | 可形成 struggle evidence | 停止堆题，回关键帧；不推断永久薄弱 |
| 中途退出（同页面） | 原 selection 可重试 | 保持 exact set，不写 terminal |
| 强退/重启 | 未可靠保存 selection/completion/answers | 恢复 exact receipt；若供应变化则 re-fetch |
| 网络断开 | 同页面重试可用，强退恢复不完整 | 仅 terminal 成功入账；本地答案只在 exact set 不变时恢复 |
| 题池重签/停发 | v2 token fail-close；旧客户端无安全 re-fetch 闭环 | 明示题目已更新并重新取题，不服务端兼容猜题 |
| 视频缓存旧 H5 | 只传 indexes，可能与新供应错位 | 提交 exact IDs + projection digest，错位请求拒绝 |
| 多端同时作答 | completion 去重，但不同 completion 可争同 probe | probe/cycle 唯一 claim；只有一个 terminal |
| 无安全替代题 | 尚无正式同 fact fallback | 诚实告知待补内容，不说“已练透”、不造题 |
| 章节映射歧义 | 原料存在但未接线上 authority | 不送达、不归因，进入 S3 审核 |

## 6. 留存实验与发布门

### 6.1 先 A/A，再 A/B

先跑 7 日 A/A 验证埋点与 join。按 `user_id` 稳定随机，按 Pack、入口渠道、历史活跃与考试日期分层；join completeness < 99% 时禁止读 A/B 结论。

- Control：当前 F16 视频后五题 + canonical server receipt。
- Treatment：Control + 最多一题 exact 当场确认 + D+1 唯一 CTA。
- 主分母：真实用户中完成 canonical forward terminal 且至少错一个 eligible fact 的去重用户。
- 主分子：在 D+1 窗口内完成、并可追溯到 parent fact/probe 的 canonical review terminal 用户。
- 同时报告全体用户 D1 有效动作率，避免只看“错题用户”造成选择偏差。
- 排除 eval/machine/internal、quarantine、无 exact H5 identity 的旧 client、服务/迁移窗口；按用户去重。

样本量按 baseline、MDE、显著性和 power 预注册计算；同时保留父级 Decision Sample Gate：至少 20 位真实用户、100 次 attempt、30 次 retry/review entry 才进入决策。

### 6.2 北极星与 guardrails

北极星：完成视频后练习的用户，是否知道自己差在哪，并在 D+1 回来完成同一事实的精确验证。

Guardrails：

- 内容冲突送达 = 0；mastered 误晋升 = 0；旧 H5 身份错位接受 = 0；
- terminal completion 非劣于 Control，4xx 不突增，P95 选题/解析 < 300ms；
- 观察作答时长、强退率、诊断展开率、题目重复/像换皮反馈；
- D7 只在成熟窗口后读取，不拿未成熟 cohort 冒充改善。

### 6.3 Release GO 必备证据

1. S1 内容资格报告，不是 compiled count；
2. terminal closure、撤题 fail-closed、v2 re-fetch/old-cache、multi-device probe race 的对抗测试；
3. release image/container 内 manifest 同目录存在可解析的 `_variant_blocklist.json`，缺失时有 error telemetry 且供给为 0；
4. F16 真微信 package + auth-chain + server terminal 证据，不能用 page-level 或 shadow harness 代替；
5. A/A join completeness ≥ 99%，eval runner 排除可证明；
6. 当前 UI 的多 CTA、独立复习与 mastery 百分比已按父级产品边界收敛。

任一缺失：`HOLD`。不得因为 schema、文件、测试或编译器存在就宣布产品闭环完成。

## 7. 红线、假进展与 stop conditions

### 红线

- 不恢复独立复习 Tab，不把历史页变成练习流水账；
- 不让前端、HTML、LLM 或 completion ID 自报掌握；
- 不从 raw docs JSON 直接线上出题；
- 不在事实撤销门完成前量产 cloze/半写；
- 不把 633 compiled candidates、979 variants 宣传成同等数量的安全题或知识点；
- 不为修一个错题继续叠运行时 blocklist、regex 或 Pack 专属 wrapper。

### 假进展

- 私有池能被 generic home 调到，就宣称视频 Practice 已接入；
- 题量变多，但来源、答案、旧规范和撤销没有 gate；
- 有 terminal bool，却不核 exact item closure；
- UI 多一个“再练一次”，实际仍抽固定五题或同骨架；
- D1 上升，但来自机器账号、答案位置泄露、重复进入或埋点 join 漂移。

### Stop conditions

- S1 内容冲突未清零：不得进入真实 cohort；
- exact H5 identity 未闭合：不得打开 light-practice/review flags；
- A/A join < 99%：停止 A/B 解读，先修测量；
- S2 未证明供给耗尽影响留存：不启动 S4/实时 AI candidate 扩张；
- 强退恢复、多端 race 或旧 token 仍能错位入账：保持 HOLD。

## 8. 盲区与最小下一步

我们的共同盲区：把“更多题”默认成留存瓶颈。当前更可能影响复访的是入口不唯一、错后没有可信反馈、明天没有明确理由回来。个性化的核心不是临场生成，而是选对下一题并能证明它为何被选。

最小下一步按顺序执行：

1. 内容 owner 完成 S1，并用 A01/F03/G03 作为必失败基准；
2. 客户端/lesson owner 完成 exact H5 question identity 与 v1 re-fetch，不先做复杂 UI；
3. LearnerState owner 把 selection 绑定 probe/cycle，关闭多端双 terminal；
4. 仅在 F16 接出一题确认 + 一题 D+1，做真微信验收和 7 日 A/A；
5. 达到父级 GO 后扩到 3–5 Pack；只有数据证明供给枯竭时才启动 S3/S4。

本次边界：只修后端 authority 与计划真相；不修改现有脏前端、不部署、不 push。前端行为均为静态代码路径判断，尚非微信真入口验收结论。
