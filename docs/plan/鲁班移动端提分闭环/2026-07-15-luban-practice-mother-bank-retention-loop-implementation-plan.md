# 鲁班视频 Practice × 母题库留存闭环改造计划

> 状态：`S0 本地已加固 / 五项关闭路径已定义但未排期 / 功能开关关闭 / 未部署`
> 日期：2026-07-15；2026-07-16 闭环路径纠偏
> 父级产品 authority：[鲁班移动端提分闭环产品 PRD v1.3](./2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)
> 本文定位：父级 P0A 的供给与证据 implementation slice；不新建复习模块、不新建题库或学情 authority。父级 `P0A/P0B` 是唯一产品阶段名，本文只用 `S0–S4` 表示工程闸。

## 0. 总裁决：五项都有关闭路径，不再用 HOLD 代替执行计划

上版的问题不是判断“还不能对真人放量”错了，而是只写了 HOLD，没有把 HOLD 拆成关闭路径；还错误地把“633 道全库治理”绑成首发前置。第一次纠偏又把 F16 写成了特殊主角，仍然过拟合一个 Pack。

纠偏后的发布原则是：

> 不要先洗完整个仓库；只允许通过同一资格门的首发 Pack 切片进入真入口，其余候选题默认不可选。首发门是“已发题目 0 不安全”，不是“633 道候选全部完美”。

本计划的最小发布检查视图不是 F16，而是 Pack-agnostic 「首发合格 Pack 切片」：

```text
pack_id + practice_surface
  + signed anchor set
  + eligible fact triad(s)
  + exact H5 identity
  + probe/cycle semantics
  + experiment/telemetry contract
```

首批准备 2–3 个合格 Pack 切片，用同一硬门槛公平选入：内容/来源安全、至少 1 个完整 fact 三件套、诊断完整、真入口可接。多个同时达标时，再用考频/用户需求、内容类型多样性和实施成本作 tie-breaker。Treatment 默认只进 2 个 Pack；第 3 个只有在 A/A 中能自然贡献至少 20% primary denominator、可达预注册样本且不需强行导向无关内容时才进入；否则停在 R1 internal QA。入选是一次 cohort 选择，不是 Pack 等级；未入选不等于低质量，下一 cohort 按同门槛轮入。F16 仅是候选/历史回归样例，可入选也可不入选；不享有任何专属 schema、路由、签发或学情逻辑。

「首发合格 Pack 切片」只是计划/发布检查视图，不得产生 `release_cell_id`、新 schema、表、store、route 或 lifecycle。runtime 仍只读现有 pack manifest + per-Pack signed artifact，并经唯一 active supply resolver 发题；现有 blocklist 在 fact-level build gate 完成后必须降为编译输入并最终失去 runtime 决策权。

当前五项不是五个“修不了”，而是五个尚未满足的 release gate：

| # | 具体意思 | 能否修 | 关闭动作 | 唯一 Pass | Owner / 估算 |
|---|---|---|---|---|---|
| B1 首批 Pack 内容资格 | `compiled` 只证明结构可判，不证明事实和来源已签发 | **可修；工程可收口，人审签名不得伪造** | 以 default-deny 为每个候选 Pack 构建同构小集合：5 道首轮 anchor 全部签发。R1 至少 1 个完整 fact 三件套（7 题）；R3 treatment 至少 2 个独立 fact，标准为 9 题。无签发 verdict/source SHA/fact identity 即不可选 | 真入口只能送达该 Pack manifest 中的已签发题；各 Pack 送达冲突数 = 0；treatment Pack 有 2 个非轻微改写的独立 fact | 内容编译 + 教研；工程模板 0.5 天，首批 2–3 Pack 人审约 1–3 天（可并行，取决于 reviewer） |
| B5 产品表面收权 | 旧前端/旧计划仍有独立复习、多 CTA 和 F16 专属入口，R2 的 UI 前置原本没有 owner | **可工程修复** | 五 Tab 收权为「学习 / 历史 / 问鲁班 / 学情 / 我的」；复测进学习任务状态；首屏唯一 CTA；历史只管对话；删除 Pack 专属入口和前端 mastery 决策 | 真微信首屏只有 1 个主动作；无独立复习 Tab/卡；任意合格 Pack 同路由；五 Tab 职责不串台 | 移动端/产品；2–3 工程日 + 真机验收 |
| B2 H5 exact identity | H5 只传 surface + 选项位置，旧页缓存可能被新题集重解释 | **可完全工程修复** | fat compiler 在 H5 固化 exact variant IDs + source/projection digest；bridge 提交该 receipt；服务端复用现有 signed selection resolver 只解析该集合，旧供给明示 `content_updated_retake`，禁止按 index 重映射 | 旧 H5 × 新供给错位接受 = 0；客户所见 = 服务端重判集合 100% | lesson/compiler + 小程序；1–2 工程日 |
| B3 同 probe 多端双完成 | 现在 review 按客户端随机 `completion_id` 去重，两台设备可以用不同 completion 竞争同一到期 probe | **可完全后端修复** | selection 绑定服务端解析的 `probe_id + cycle_anchor`；持久层原子 claim 以 `user + probe/cycle` 唯一。`semantic_request_hash = signed exact selection identity + normalized answers`，明确排除客户端随机 completion ID；同 hash 读回赢家 terminal，不同 hash 冲突 | 跨两个 service instance/transaction 并发只形成 1 个 probe terminal；只有 claim 赢家能写 item/terminal | LearnerState/writeback；1–2 工程日 + 持久层并发对抗测试 |
| B4 真微信 + A/A | 前三项只能证明候选实现；不能证明真微信 auth-chain 和生产事件 join 可靠 | **真微信可验；测量链可修；7 日时间窗不可压缩或伪造** | 先做真 package/auth/server-terminal 验收；再完成 A/A 分流、去重、eval 排除和 join audit，开 A/A-only 小 cohort 跑满 7 日；达标后才开 treatment | 真入口 terminal 证据齐全；A/A join ≥ 99%，两组无系统漂移，eval/machine = 0 | QA + 数据；真微信 0.5–1 天，测量预检 1 天，再需 7 个日历日 |

上述工期是排程估算，不是脱离人审和真人数据的交付承诺。B1、B2、B3 可并行；B4 的真微信验收紧随三路合流，7 日 A/A 只阻断 treatment/产品 GO，**不阻断工程开发和内部 QA**。

A01/F03/G03 等已知冲突继续作为全链必失败回归并默认隔离；它们只阻断对应未签发 Pack 切片，不阻断其他已达标 Pack。冲突修正、重编、重签后，这些 Pack 也按同一门槛恢复候选，不被永久降级。

因此：保持对外功能开关关闭，并行关闭 B1/B2/B3/B5，再分层完成 B4；首批准备 **2–3 个同门槛 Pack 切片**，treatment 默认 2 个、第 3 个由 A/A 真实流量门决定，避免既过拟合单 Pack，又把小样本拆碎。它们通过 GO 后，才扩到 3–5 个 Pack。

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
| 错项诊断元数据 | 1899 个错误选项；1827 个有完整 temptation/loss_reason/fix，缺失 72 个集中在 A02 | 当前 checkout 数据盘点 | 足以候选多个 Pack 小切片；必须逐 Pack 过门，文案只能说“这个选项的常见陷阱是…” |
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
- `历史`：对话历史与继续对话，不混练习流水、复测队列或成绩单。
- `问鲁班`：当前 TutorBot 会话；只做提问与追问，不复制历史列表或学习任务。
- `学情`：只留最近进步、当前 1–3 个盲点、唯一下一步；证据不足显示 `insufficient_evidence`。
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

### S1a：Pack-agnostic eligible issued set（产品 P0A 阻断，首批 2–3 Pack）

Owner：内容编译/数据资产；Reviewer：教研 + scoring authority owner。

- 不修改 `compiled` 的含义；它继续只表示结构可重建。item-level eligibility 只演进现有 `_pack_manifest.json` 已引用并钉 SHA 的 **per-Pack Practice artifact**：该 artifact 原位增加逐题 `fact/source/content/review/eligible/revoked` 签发信息；manifest 只保存 pointer/hash 与聚合状态，不保存第二份逐题真相，不新建 release-cell artifact；
- 每个候选 Pack 的首轮 5 道 anchor 全部完成 `fact_id + source_anchor + source SHA + content SHA + review verdict`；
- R1 至少 1 个 eligible fact 三件套；R3 treatment 至少 2 个独立 eligible facts，每个备齐“首题/当场确认/D+1”三件套；后两题必须不同 variant 且不同 skeleton，两个 fact 不得只是同一数字/句子的轻微改写；
- compiler 使用同一通用路径，按 Pack 只向 runtime 投影 per-Pack Practice artifact 中已签发且未撤销的集合；artifact、manifest pointer/hash 缺失、破损或 SHA 不匹配必须 fail-close；
- 禁止 `pack_id == "F16"` 类专属分支；选择器、签发、writeback、诊断、复测和埋点必须对任意合格 Pack 同构；
- agent 可生成审核包、差异报告和机械校验，不代替教研/scoring owner 签名。

Eligibility authority：唯一 writer 是 build-time pack compiler；item-level 唯一存储是现有成品树内、由 `_pack_manifest.json` pointer/hash 引用的 SHA-pinned per-Pack Practice artifact，manifest 只承担 pointer/hash 与 Pack 聚合状态；不新建线上资格库、平行 manifest 或 release-cell artifact。签发者是教研 + scoring owner；撤销者是同一 build-time fact gate；runtime 唯一 reader 是 lesson supply resolver。任一人审状态、artifact SHA、manifest pointer/hash 或撤销关系不一致，整个 Pack 切片 fail-close。

Pass：对每个首批 Pack，真入口可选集合恰好等于 per-Pack Practice artifact 的 eligible/non-revoked item set，manifest pointer/hash 与 artifact 完全一致；每个可选题有完整事实/来源/版本身份；送达冲突数 = 0；最长选项、答案位置和模板泄露有逐题 verdict；同一套参数化测试至少覆盖“可发、有冲突、供给不足”三种 Pack，不以 F16 为固定快照。

### S1b：全库事实资格与跨派生撤销（后台治理，逐 Pack 进入同一候选池）

Owner：内容编译/数据资产。

- compiler 逐步覆盖 variant、compiled/public/private Practice、cloze、antidote、concept card、answer layer、questions_bank projection；
- 按 Pack 审核 633 candidates 的 source、答案、旧规范、提示泄露、重复与诊断质量，每完成一个就进入同一合格 Pack 候选池，不等全库完成；
- A01/F03/G03 已知冲突作为必失败回归，对应未裁决派生物持续隔离；
- `has_answer_layer` 从布尔改为 canonical path + SHA；C02/G03 双副本裁决 superseded。

Pass：任一 fact revoke 后所有已登记派生面一次 gate 100% 不可见；只有通过该 Pack 资格门的题才能随后续 3–5 Pack 扩面进入真人 cohort。

### S2：首批 2–3 Pack 产品纵切（父级产品 P0A，与 S1a 并行开发）

Owner：学习体验 + LearnerState；真人送达依赖 S1a，工程开发不等待 S1b。

- fat compiler 把 exact question IDs + source/projection digest 固化成静态 `projection_receipt`；H5 bridge 提交 receipt 后，服务端必须重核当前 eligibility，再换发绑定 user/mode/day/exact set 的 `signed selection token`；completion 只接受 token，禁止根据 surface + indexes 猜题；
- 旧 client/H5 遇到供应变化必须显式 re-fetch；仅 exact set 和 digest 都不变时才保留本地答案；
- 首轮五题 server receipt 后，展示已有错项诊断；
- 引入稳定 `fact_id/skeleton_id`，不以自由文本 `rule_group` 作 canonical identity；
- 错后最多一题同 fact、不同 variant/骨架确认；D+1 同 fact 再验证；
- `probe_id + cycle_anchor` 只能由服务端 canonical revalidation queue 解析并签入 selection；多端同一 probe 以持久层原子 `user + probe/cycle` 唯一约束仲裁；同 payload 重放 terminal，不同 payload 返回冲突；并发测试必须跨两个 service instance/transaction，不能只测单进程 pre-check；
- 学习首页只有一个 CTA，复习不再单独成模块。

Engineering Pass：所见题集与服务端重判 100% 同一；旧缓存题不能错位提交；并发多端只形成一个 probe terminal；原题/同骨架误重复 0；D+1 完成有 signed selection + due probe + terminal 三证。真微信与测量证据由下文分层 release gate 裁决，不和代码完成度混写。

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

内容资格与实验资格分开：

```text
content eligible
  = source / answer / fact / diagnosis / exact identity 全通过

experiment eligible
  = content eligible
  + A/A 期间有足够 eligible D0 forward terminals
  + 能在预注册 enrollment window 达到 powered sample
  + 不需强行推荐与学员需求无关的 Pack
```

- Control：当前所属 Pack 视频后五题 + canonical server receipt。分流按 `user_id` 稳定，并按 `pack_id` 分层；同时报告总体与 per-Pack 结果，禁止一个 Pack 的异常被总体平均掩盖。
- Treatment：Control + 最多一题 exact 当场确认 + D+1 唯一 CTA。
- 主分母：真实用户中完成 canonical forward terminal 且至少错一个 eligible fact 的去重用户。
- 主分子：在 D+1 窗口内完成、并可追溯到 parent fact/probe 的 canonical review terminal 用户。
- 同时报告全体用户 D1 有效动作率，避免只看“错题用户”造成选择偏差。
- 排除 eval/machine/internal、quarantine、无 exact H5 identity 的旧 client、服务/迁移窗口；按用户去重。

唯一 primary estimand（主估计对象）：随机单元是 `user_id`，用户跨 Pack 始终保持同一实验臂；primary index episode 是入组后第一个 eligible D0 forward terminal，其 Pack 记为 `index_pack`；primary outcome 是 D+1 窗口内完成与该 parent fact/probe 对应的 canonical review terminal。同用户后续 Pack 行为只进 secondary repeated-episode analysis，并按 user 聚类。

join completeness 分母 = 所有 content-eligible primary index episodes；分子 = 能唯一 join 到 experiment assignment、exact selection、canonical forward terminal、`user_id/pack_id`、账号排除字段和 D+1 outcome window 的 episodes。A/A 启动前必须冻结 assignment ratio、baseline covariate SMD 和 outcome equivalence margin；未有 baseline 无法设 margin 时不得用“无系统漂移”作事后解释。

必须同时报告：按 Pack 等权标准化的 pooled ITT（primary）、按真实流量加权的 pooled ITT（sensitivity）、per-Pack 效果与置信区间（未单独 powered 时只作异质性/安全判断）。预注册模型至少包含 Pack fixed effect 和 `Pack × treatment` interaction。

样本量按 baseline、MDE、显著性和 power 预注册计算；R4 要求是 `max(power-calculated N, 父级 Decision Sample Gate)`，而不是用 20 真人 / 100 attempt / 30 retry-review 的底线替代 power calculation。

### 6.2 北极星与 guardrails

北极星：完成视频后练习的用户，是否知道自己差在哪，并在 D+1 回来完成同一事实的精确验证。

Guardrails：

- 内容冲突送达 = 0；mastered 误晋升 = 0；旧 H5 身份错位接受 = 0；
- terminal completion 非劣于 Control，4xx 不突增，P95 选题/解析 < 300ms；
- 观察作答时长、强退率、诊断展开率、题目重复/像换皮反馈；
- D7 只在成熟窗口后读取，不拿未成熟 cohort 冒充改善。

### 6.3 分层 Release Ladder：不再用一个 HOLD 混住开发、QA 和产品证据

| Gate | 允许做什么 | 必备证据 | 不允许 |
|---|---|---|---|
| R0 Engineering Candidate | 合并候选代码，开关仍关闭 | S1a 首批 2–3 Pack 审核包已生成；无 Pack 专属逻辑；exact H5 old-cache 对抗测试；multi-device probe race 测试；terminal closure/撤题 fail-close 回归全绿 | 不得宣称真入口或留存成立 |
| R1 Internal WeChat QA | 仅内部 QA/eval 账号 | 每个首批 Pack 至少 7 题已完成人审签名；真 package + auth-chain + exact server terminal；release image 内 revocation/eligibility manifest 可解析，损坏时供给为 0 且有 telemetry | page-level/shadow harness 不能代替真微信 |
| R2 A/A-only Limited Cohort | 小流量只跑 Control/A/A，不开错后 treatment | 安全发题 = 0 冲突；分流、去重、事件 join、eval/machine/internal 排除和隐私边界通过预检；UI 已收敛为唯一 CTA/无独立复习 | 不读 treatment 效果，不扩 Pack |
| R3 Treatment Cohort GO | 默认在 2 Pack 小 cohort 开“一题确认 + D+1”；第 3 Pack 达 traffic gate 才加入 | A/A 跑满 7 个日历日；每个 `Pack × arm` join ≥ 99%；各 Pack assignment ratio 偏离目标 ≤ 5 个百分点；2 Pack 时任一 Pack 占 primary index cohort ≤ 60%；3 Pack 时任一 Pack 占 20%–60%；每个 treatment Pack 有 2 个独立 fact/标准 9 题；预注册平衡/等价门与总体/per-Pack guardrail 正常 | 不强行推荐无关 Pack 凑配额，不把小流量当作产品 GO |
| R4 Practice retention slice GO / 扩 3–5 Pack | 根据证据扩面或停止；不代表半写/AI 批改深度层已 GO | `max(power-calculated N, 父级 Decision Sample Gate)`；D1/D7 观察窗成熟；leave-one-Pack-out 后 pooled treatment 方向不翻转；逐 Pack 通过 S1b | 不因编译题数增长自动 GO；如改善主要来自单 Pack，只能宣布该 Pack 候选有效 |

缺少某一层证据，只阻断进入下一层，不倒推为“工程不能修”。任何层级都不得因为 schema、文件、测试或编译器存在就宣布产品闭环完成。

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

- 任一待发 Pack eligible issued set 内有未签发、冲突或 SHA 不匹配：只移出该 Pack 切片，不拖死其他已达标 Pack；
- exact H5 identity 未闭合：不得打开 light-practice/review flags；
- review probe/cycle 无唯一 claim：不得打开 D+1 treatment；
- A/A join < 99%：停止 A/B 解读，先修测量；
- S2 未证明供给耗尽影响留存：不启动 S4/实时 AI candidate 扩张；
- 强退恢复、多端 race 或旧 token 仍能错位入账：保持 HOLD。

## 8. 盲区与最小下一步

我们的共同盲区：把“更多题”默认成留存瓶颈。当前更可能影响复访的是入口不唯一、错后没有可信反馈、明天没有明确理由回来。个性化的核心不是临场生成，而是选对下一题并能证明它为何被选。

最小执行路径：

1. **并行 A（内容）**：用同一硬门槛盘点候选 Pack，准备 2–3 个首批 Pack 切片；每个先产出至少 7 题 R1 审核包，拟进 treatment 的 Pack 补齐 2 个独立 fact/标准 9 题，人审签发后回写现有 pack manifest/per-Pack signed artifacts；
2. **并行 B（所见题身份）**：把 H5 bridge 从 `surface + indexes` 收权到 exact IDs + digest，补 old-cache/re-sign/re-fetch 对抗测试；
3. **并行 C（复测事务）**：签发 selection 绑定 probe/cycle，建立持久层原子唯一 claim，semantic hash 排除随机 completion ID，补跨两 service instance/transaction 并发测试；
4. **并行 D（产品表面）**：收权五 Tab 和学习首页唯一 CTA，移除独立复习与 Pack 专属入口，真机核对历史/问鲁班/学情职责；
5. A/B/C/D 合流后在首批 2–3 Pack 上用同一通用链路接出一题确认 + 一题 D+1，通过 R0 和 R1 真微信验收；
6. 完成测量预检后开 A/A-only 小 cohort；跑满 7 日、每个 `Pack × arm` join ≥ 99% 后，用真实 eligible traffic 决定 treatment 是 2 Pack 还是 3 Pack；
7. 达到 Practice retention slice GO 后按 Pack 逐个通过 S1b 再扩到 3–5 Pack；半写/AI 批改仍走父级 P0A-1 独立门；只有数据证明供给枯竭时才启动 S3/S4。

本次纠偏边界：完善执行计划、阻断关闭表和 release ladder；不修改现有脏前端、不部署、不 push。前端行为均为静态代码路径判断，尚非微信真入口验收结论。
