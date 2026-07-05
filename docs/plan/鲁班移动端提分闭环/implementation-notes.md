# 五模块改造 · Implementation Notes（活账本）

> 维护规则（owner 2026-07-05 指令）：执行中撞上 edge case 偏离计划时，**选保守方案，在 Deviations 记一笔，接着干**——复盘全靠它。
> 由主控会话集中维护；实施 agent 在隔离 worktree 工作，其报告中的偏离由主控收录。按日期倒序追加，不删旧条目。
> 关联计划：`2026-07-04-luban-ai-adjudication-pipeline-plan.md`（裁决流水线）、五模块 IA Brief、双轮 v3.2、融合计划 v1.1。

## Deviations

### 2026-07-05（D4 重尾批收官）
- **[模式反转] 重尾批 92% 条目需真实裁决**（前两批约半数只缺凭据）——"重尾"的重是真的；预算内消化（123 处编辑）。
- **[整包体检首触发] S01 Tier-2 需求 10>8 触发 §5.5**：GLM 全包诊断=repair（同型机械截断病）而非系统性烂，按诊断批修复而非逐条——触发器语义按设计工作。
- **[计划预判未发生] S06"坠落半径 5m/6m 教材查不到需升 owner"**：教材 P124 逐字全命中，全批 30+ 数值族检索命中率 100%——8 包共同病灶实为编译 quote ~90 字均匀截断（切片管道问题，非教材缺口），是未来重编译轮的确定性修复对象。
- **[超 jury 深度的实质错误 ×3] 裁决中发现 jury 没抓到的事实错**：S02 两处"150mm 落 200~500mm 区间"算术假陈述、S02/S01"300kN/200m"误归吊装总重（实属安拆条款）、C04 不实"🟢已验证"声明——面板真实增值的证据。
- **[红旗纪律 vs 效率] K01#0/Q02#7 两案 GLM 判"教材+真题双锚证据已足可升🟢"**，按"升色=0"红旗纪律保🔵+可升级说明，升级权留 owner——纪律优先于单案最优。

### 2026-07-05（局外人审计轮）
- **[主控过度声称自纠 ×2]** ①"答疑吃 Nexus/KnowQL 颗粒"不实：TutorBot loop 无该工具，KnowQL 仅在判分 shadow；答疑对深 pack 内容供给=0。②"教学吃卡"生产上假：`LUBAN_LESSON_CARD_BASE` 全 repo 无处设置→20 绿灯站 card_url 全空降级，托管卡仅 6 站。教训：架构应然≠生产实然，回答 owner 架构问题必须以生产终态为准。
- **[skills 提案裁决=不做]** owner"pack 做成 skills"提案经局外人核实：13 天前已被 L0 路由卡设计文档显式评估并回撤（skill=行为装载器非知识库；整包进 context 比编译投影贵 20-30 倍；语义自选=人为引入不确定性）。正解=给已裁决管道合闸，非新形态。
- **[系统性病：供给跑赢消费 21:1]** 三道 dormant 电闸：①变体池无签发门（candidate 直通生产消费端，status 零过滤+sha 不比对）②卡供给 env 缺失+14 站无卡 ③pack 锚定真题 ~80% 判分仍 open-world 现编（live 编译库源头=真题参考答案管道非 pack R5，R5 promotion 未执行）。已启动修复①（luban/variant-signoff-gate 分支：runtime 双 fail-closed+promotion 薄工具，作 wave1 合并前置）。
- **[已合闸①] 变体签发门落地**（分支 luban/variant-signoff-gate）：runtime 唯一入口 `_load_signed_bank`（status==signed ∧ source_pack_sha256==manifest content_sha256 双 fail-closed）+ `promote_variant_bank.py` 人闸工具（四关校验含 gate 重跑）。**发现**：F16/S05 也是 candidate（"signed 先例"不存在），故 wave1 合 main 前必须先做首批 promote，否则全站复测空窗。29 tests（主控复核 13 luban_lesson 绿）。
- **[新雷登记] 裁决 resolution 无 sha pin**：用章节号+散文锚定，pack 正文修订后 jury_clean 不自动失效；recheck 只在签发瞬间跑。收口方向待定（resolution 加 content sha / CI 定期 recheck），先记账。
- **[次雷] 复测 expected_ok+correct_statement 下发客户端本地判分**：现仅进 telemetry 半径小，但接学情前必须收口（防刷分面）。**[次雷] 上级目录 13 个旧 jury 副本**且 manifest/recheck 有回落查找逻辑——旧副本可能静默顶替真值，清理待办。
- **[变体池] R01/F05 两站如实跳过不建池**（计划=18 绿灯站全补）。根因=两 pack 的 R4 封闭性自检**自己**把机械扣分判断收归 R7 🔴（jury 裁决后的新文体），变体池所需的 expected_ok 二值判定恰是被降级的那层——建池=冒充 pack 已拒绝的机械红线。X02 同型病但有两处真题明锚，抢救出 20 变体限缩池。**续产预筛惯例**：先 grep pack 的"收归 R7"自检声明，零成本判断可否建池。（分支 luban/variant-pool-production-wave1，887 变体 16 站 gate 100%）
- **[签发人审提示] E05 整池零真题锚**（pack 真题侧空窗，全挂教材锚）——16 站中唯一，教研签发时优先人审。
- **[摘取排雷] #351 的 api.js diff 会整函数替换掉 main 的 `postLessonProgress`（lesson_viewed 唯一 writer）**——盲 cherry-pick 会静默 regress PR#353 融合基座。"先逐文件 diff 再摘"纪律救下的最大一颗雷。同批对账结论：cfa515e0d 摘增量、4e956ccb5 整页重铺（main 无其假设的占位页/5-tab壳/--lb-token）、749964b52 仅按 §6.1 重写 exam_date 消费其余弃。（分支 luban/review-module-wiring）
- **[产品语义如实保留] revalidation_queue 日容量=1（ARRS max_active=1）**：复习到期清单每日最多 1 站，为既有引擎语义（v3.2 §6.1 每日上限）非 bug；页面文案不承诺多站。**产品问题待 owner**：复习 tab 的"今日到期 5 个"设计稿预期 vs 引擎日容量 1 的张力，通电前需拍板。
- **[agent 终态纪律] 变体池 agent 首次收尾把"等子 agent 报告"当终态交付**——自证陷阱变体（用过程状态替代磁盘终态）。纠正：责令以磁盘+亲跑 gate 实测收尾。派单惯例追加：最终回复必须基于终态实测，不接受"等待中"作为完成态。
- **[签发范围] C06/S07 从 Batch A 批量签发中撤回**。计划表把两包排进信心批，但签发时撞 `explicitly_barred_default_entry`（coarse_review 粗粒包，需先 leaf review 的既有设计门）。保守处置：不绕闸、撤回 override、只签 13/15；C06/F04/Q03/S07 四粗粒包 leaf review 列为独立待办等 owner 拍板。（PR#365）
- **[红旗口径] D3 批 agent 自报 Q03 🟢 delta=−3，主控独立复测=0**。方向一致（均为"未升色"），判定不构成红旗违规；差异原因未深究（疑为计数口径含作答层/括注文本）。保守处置：以主控复测数为准记录，红旗判定标准保持"delta>0 才违规"。
- **[流程韧性] D3 中量批 agent 中途 API 断线**。靠"每包 recheck exit 0 才 commit"的粒度无损续接（仅 A02 半成品重收口）。经验固化：批处理任务的 commit 粒度=断点保护，不是仪式。
- **[裁决方向反转-保守側] G02"虚铺依据"条：jury fix 要求降🔵，但教材 P85 逐字实存该句** → 按事实权威阶梯（教材>面板>jury），保🟢补出处而非机械执行降级。同型先例 C01#0（教材 P103）。"保守"在本项目=服从教材原文，不是服从 jury。
- **[跨包红线新增] 同一 chunk_id 跨 pack 的 quote 切片不同**（0123 在 D12=防治要点、在 Q03=仅原因）→ 禁止跨包借 quote，各包只认自己 compiled_source 的切片。

### 2026-07-04
- **[Tier-0 预期落空] 设计估 Tier-0 可直接证伪 ~10% jury 断言，实测 0/164**——J01 型 jury 幻觉已被 batch1 人工消化。策略调整：Tier-0 从"批量结案器"降级为"改前证伪闸"，Tier-1/2 实际占比上调；排期仍守住（信心批+中量批各提前约两天完成）。
- **[实施发现] ~17/24（D2 批）与 ~22/40（D3 批）条目属"前轮已实质修复、只缺 resolution 凭据"**。流程相应前置一步"先核正文现状再决定补凭据 vs 真编辑"，避免重复编辑。
- **[schema 登记位错] fusion stage0 把两个新 schema 登记进 `content_asset_contracts` 区块，但闭包只认 schemas/tier2/tier3** → 迁入 `tier2_canonical_contracts` 并补 canonical_fields pin（闭包 210→212）。教训：登记前先看闭包脚本认哪个区块，不是 yaml 里有名字就算登记。
- **[冲突裁决] F16 摘取的 docker 通配 COPY commit 与 main 上 #353 的逐文件 COPY 冲突** → 采纳整目录通配（新站补池零 Dockerfile 改动=治本），保留 #353 的 join 映射反选与 degraded 注释，deploy 测试合并双方断言。
- **[计数 pin 有意识 bump] D14 入仓使 evidence 文件 37→38、manifest 全集 40→41**，两个钉死计数的测试按设计意图（逼有意识确认）bump 并注明原因。
- **[生成物治理] F16 托管卡（web/public/luban-preview/f16/）撞 secret-scan 基线与 eslint** → 治本选前缀排除 `web/public/luban-preview/`（40 包量产会持续新增卡，逐个 baseline 会无限 churn）+ eslint ignore（vendored 运行时非应用源码），而非逐文件 baseline。
- **[F04 修复幸运面] 损坏 sidecar 的双 JSON 文档逐条比对全等** → 机械归一无需并集裁决，修复零语义风险（原方案备了并集+人工比对路径）。
- **[声称漂移修正] round11 Brief 把 PR#353（draft/flag 关/未部署）字段写成"已上线 read-model 背书"** → 入仓前改为显式状态口径。教训归档：'已上线/已就绪'表述必须核部署终态。
- **[风格拍板] owner 定版动画卡只用"视频2类"**（纸墨朱竹深母题动画学习卡，P40 世代），视频1类深蓝旧风格弃用；存量卡上线前须风格审计。
- **[并行工作区纪律] fusion worktree 领先 origin 15 个未推送 commit 且有脏文件** → 不碰其工作区，基于其 HEAD 另开 worktree 推进，脏改动原样留给其主人。

## 惯例沉淀（复盘时升格为规则的候选）
- （2026-07-05 owner 拍板）常设"局外人观察者"agent：每里程碑从第一性原理审视消费链/断链/系统性隐患，防头痛医头；机械批处理活分层给 Opus 4.8，判断密集活留 Fable+异源面板。
- （2026-07-05 owner 二次修订用模准则）异源主力=Codex/GPT-5.5，GLM-5.2 降辅助（仅 4+大面板或回避补位）；**保留的例外=利益回避**：Codex 生产/flag 的条目由非 Codex 补位裁决。重尾批按原矩阵收尾（批内一致），新准则自粗粒包 leaf review 起。入仓计划文档的面板矩阵随下个里程碑 PR 修订。
- （2026-07-05 owner 确认）UI 权威=《微信小程序前端设计》第10轮定稿；缺失屏（复习 3 流程屏/批改结果页/OCR 校对屏/变体挑战流/空态）后续按同风格补，不另起炉灶。
- （2026-07-05 owner 拍板）过程中只 commit+push 分支留痕，不逐个 PR；PR+合 main+部署留给"需要上阿里云真测"的里程碑一次性做。动机：branch protection 的 BEHIND→update→CI 重跑循环在多 PR 串行时节拍成本过高。
- 批量签发 override note 必带逐包机器核验数字（verify_pack / 真题锚 / recheck 三闸 exit code）。
- 主控对 agent 交付一律独立复跑关键声称（recheck 联跑、🟢 delta、published 未动）再报 owner。
- "已裁决"唯一凭据=recheck_resolutions.py exit 0；"已合并"唯一凭据=origin/main 终态核查。

## 未决观察（尚未定性，先记着）
- verify_pack.py / verify_exam_anchors.py 硬编码主 repo 绝对路径（可移植性债，D1 范围外）。
- jury sidecar 在 考点原料/ 上级目录有 13 个旧副本（权威只在 成品/），未清理。
- 多个 PR 合并被 branch protection "BEHIND" 反复卡住 → update-branch+重跑 CI 的节拍成本高，若持续可考虑 merge queue。
