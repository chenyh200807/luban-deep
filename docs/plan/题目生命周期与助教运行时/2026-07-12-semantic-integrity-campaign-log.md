# 语义完整性修复战役全程记录(2026-07-12)

> 本文是给后来者的**方法论日志**:问题怎么被发现、怎么分析、怎么裁决、怎么修、踩了什么坑。
> 逐修复的操作级条目在 `artifacts/tutorbot_fix_test_journal.md`(倒序,已跟踪)。
> 诊断阶段完整报告为本地 artifacts(仓库政策 review artifacts 不进 git):
> 六专家 eval 根因面板 `artifacts/student_army_eval/root_cause_panel_2026-07-12.md`、
> 五家族根因报告 `artifacts/semantic_integrity_campaign_reports/I1..I5-*.md`;其结论已浓缩进本文 §1-§3。
> 分支:**调和版** `fix/semantic-answering-reconciled-20260712`(重放到 origin/main 47b04eab,#456 后)。
> 原始施工分支 `fix/semantic-answering-rootcause-20260712` 基线 1e9f6a40;因 origin/main 并行推进 54 commit
> (Battle2 速度战役 #447-#456 + 五模块闭环 #454),**WP0(泄露测试翻转)已被 main 的 9533adb1/PR#452 独立landed → 丢弃**;
> WP1-WP4 病在 main 仍全活,重放调和(WP1 手工解 supabase.py 双RPC结构 2 块冲突,WP2/WP3/WP4 干净应用)。
> 调和后 commit:WP1 `5fc1c276` / WP2 `3e9aba6d` / WP3 `3c2da4dc` / WP4 `84d1efc5`。

## 0.1 战役终裁(指挥官 2026-07-12)

**GO(本地封板)**。五包治本、减 decider、三 SEV hold 零弱化、4 个预存在红已在基线独立复跑证非本战役引入、诚实边界守住(未宣称"修好",live 复验划归部署里程碑)。无 NO-GO 项。本地 8 commit 完整;push 待 owner 补 workflow-scope 凭证;`DEEPTUTOR_ANTIPEEK_CANONICAL_FACET_ENABLED` 默认关随包上线,live 抽样对账通过后再开。GO 指"可进部署里程碑做 live 终裁",非"生产已愈"。

## 0. 战役目标(owner 原话级)

系统具备完整语义理解和回答能力:学员问一个问题,**不答非所问、不拒答简单合理的问题**。
既往诊断反复指向:没有统一路由/context 管理/状态机/单一权威。
三大原则:thin wrappers fat skills / first principles / less is more,不治标。

## 1. 问题是怎么被发现的(发现方法论)

### 1.1 三层证据漏斗
1. **eval 军团日志纵向深读**(6 位专家并行,各持一个切面):不是重读结论,而是重读**原始数据**
   (20260625_full.json 逐 turn、langfuse 435 turn 审计、quality gate 账本、SKILL.md §7 模式库 47 行)。
   关键手法:同尺可比性检查(三维分只有 36 小时 3 个测点可比)、复发矩阵(标"✅已修"后多久复现)、
   修复半衰期分类(stick vs 不 stick 的本质区别)。
2. **真实学员活体取证**(生产 chat_history.db 只读):合成军团(≥10 轮长对话)与真实用户
   (中位 2 条消息/人)是**两个不相交的人群**——真正摧毁体验的失败要到真实数据里找。
   五大活体杀手全部由此浮出:题库假命中、英文报错裸奔、守卫劫持口诀、承接断裂、一问双答。
3. **对既往"✅已修"的证伪测试**:每个家族先问"为什么修了没 hold"。实测发现 #417 白名单只赦免了
   "口诀"一个词("总结考点/换话题"仍被拒答)、#422 只补了计算类切片(非计算同域相似题 cov 0.36 仍放行)。
   **教训:检查修复是否 hold,必须用邻近变体实测,不能信状态标记。**

### 1.2 发现阶段的三个反直觉结论
- **"宏观分不动"主要是尺子问题**:维度均值 delta<std、测的人群不存在、监测 07-01 后死亡 11 天。
  修复其实在确定性口径上真实收敛(SEV 家族 6 维 5/6 全绿)。
- **真实用户里 LLM 走通的轮次质量是好的**,摧毁体验的全是**非 LLM 路径**(确定性短路/错误处理/守卫)。
  "快的恰是错的"(0-2 秒轮几乎全是错误短路或 canned 守卫)。
- **监测器无人监测**:持续 eval 静默死亡本身没有信号(launchd 服务消失、SKIP 被设计成"好事")。

## 2. 问题是怎么分析的(分析方法论)

### 2.1 强制框架(root-cause-debugging + deeptutor-authority-debugging)
每个家族专家必须产出:
- **9 字段 root-cause frame**(one business fact / one authority / competing authorities / canonical path /
  last correct point / first wrong point / delete or demote / deterministic vs LLM boundary / verification target)
- **全生命周期 decider/writer 测绘表**(patch-spiral 退出法:同一事实修 ≥2 次复发=先测绘全再动手;
  实测"本轮考点"有 ≥9 个 decider、"是否隐式求助"有 ≥6 处重判、"是否原题"有 4 个铸章点)
- **shared failure shape 分类**(authority drift / duplicate decision / terminal truth / mirror state /
  dormant authority / multi-writer / producer-consumer granularity mismatch)
- **先活体取证再看代码**(铁律:dump 真实 turn 的 events_json/metadata_json 看"哪条路径判的",
  不许 grep 假设)

### 2.2 宏观指挥官裁决(故障成簇时强制升一层)
五个家族不逐个修,先派**一个指挥官 agent** 回答"是不是同一个架构病":
- **病因命名(第一性,一句话)**:终端执行点不消费系统已算出的 canonical 裁决,而用本地廉价代理判据
  (关键词/相似度/默认值/字符串形状)自铸真值,并在不确定或失败时把它洗白成一个"合法身份"的
  确定性产出(模板、假命中章、假回答、假完成态)——**"裁决权威旁置 + 身份洗白"**。
- 病数:1 主病(I1/I2/I3/I4-A/B)+ 2 正交病(并发幂等 I4-C、测试镜像治理 I5)。
- **全局律**(落 contracts/turn.md"终端产出纪律"节):①确定性短路只许高置信可证伪快路径或 SEV 窄拦截;
  ②短路开火前必须消费 canonical 裁决;③不确定一律 fall-through 主 LLM,禁模板兜底;
  ④失败保型(typed failure)+唯一 terminal mapper+禁 completed 假绿。
- **右尺寸**:逐家终审砍过度设计(declared_subject 新字段=有罪推定成立不做;client_turn_id 幂等键=
  前端不配套则无用;墓碑消息=噪音);LLM prompt 变更强制 flag 灰度;推迟项全部带触发条件。

### 2.3 指挥官在线复审(每包 diff 终审)
指挥官不解散,每个施工包完成后独立核验(不信施工报告自证):重点核短路点是否真降级为消费者、
SEV 测试是否被弱化、"decider 为什么变少"答不出就打回。实战中指挥官三次抓住真问题:
- WP1:12-18 字符短窗对抗缺口(构造"一级/二级"单字差对实测误判)→ 判别面抬 ≥20;
- WP1:选项佐证扩展的算术漏洞(options-only 粘贴可过合并覆盖率)→ 题干独立覆盖 ≥0.90;
  数词变题穿透(≥20 窗口"一级→二级"变题 0.95 覆盖率仍过)→ 数词事实 rejector;
- WP2:多 worker lifespan 双通知竞态 → 逐 turn CAS 通知所有权。

## 3. 问题是怎么解决的(施工包与修法)

### WP0 `2f5fe487` — 测试契约对齐+CI 登记(I5)
- **病**:PR#317 按 owner 拍板翻转 anti-peek 边界,同 commit 翻了 3 份镜像测试漏了 CI 暗区第 4 份,红 12 天。
- **裁决**:契约漂移非真泄露回归(读 owner 拍板文档+diff+互斥断言证明)。
- **修**:翻转断言但**保留隐式不泄 SEV 护栏断言**(翻转≠删除);FailingFollowupAgent 钉死"揭示不走自由 LLM";
  文件登进 runtime-capability CI shard。
- **shape**:契约反转未清点全部镜像副本 × CI 暗测试。

### WP1 `5fc1c276` — exact-identity 铸章收权(I1)
- **病**:RPC 模糊检索把 relevance 命中铸成 identity 权威(`score=max(text_score,0.98)` 人为抬置信),
  终端跳过 LLM 直出"命中题库原题。标准答案:C"。4 铸章点各带 3-4 层闸=whack-a-mole。
- **修**:单一可证伪 adjudicator(NFKC 归一化互相包含[≥12]+有序覆盖率 ≥0.90[≥20]+数词事实全覆盖
  +选项佐证合并判别面[题干独立覆盖 ≥0.90]);删 0.98 floor;4 铸章点降级候选供给;不匹配 fail-open
  回主 LLM(复用既有 fallthrough,消费层零改动)。
- **为什么修铸章层不修消费层**:D15 的"必须严格服从"prompt 注入使假章连开放世界 LLM 都会被劫持——
  修消费层=给每个消费者配测谎仪,修铸章层=让契约恢复诚实。
- **decider**:4 铸章点 ~14 判定位 → 1 adjudicator。
- **坑**:指挥官预案(判别面 ≥20)过杀了"短题干带错字+选项近逐字一致"的真原题——选项一致本身是
  强 identity 证据,把它收进**同一个** adjudicator(证据面变宽,decider 不变),而不是给 option 路径开例外。

### WP2 `3e9aba6d` — 失败保型+唯一 terminal mapper+turn FSM(I4)
- **病**:错误在出生处被洗白成合法答案身份(loop.py:2311 把预算耗尽现编成英文"最终回答",无 error 标记,
  两处测试还把它断言为预期=bug 被测试制度化;provider 把错误体写进 content 通道);turn 存活性双真值
  (per-worker 内存 vs DB),无守卫 UPDATE 使 cancelled 被复活成 completed。
- **修**:LLMResponse 加 failure_kind/error_detail 出生保型;唯一 mapper `map_turn_failure_to_public_text`
  (三个终端面共用);失败一律 status=failed+error_code 公开+不可计费+不进学情;update_turn_status 改 CAS
  (running 唯一可写前态);终态 commit 重排序=先 CAS 后 add_message+billing;孤儿恢复逐 turn CAS 决定
  通知所有权+mapper 中文交代。
- **decider**:错误可见面 5 类决策点→1 mapper;turn 存活性 4 真值→1 DB FSM。
- **边界裁决**:ProviderErrorStreamGate(200-SSE 错误体无类型可保,窄前缀形状闸)被指挥官裁定为
  薄闸而非第二 decider——"保型律管的是类型存在处不得丢,管不了类型根本不存在的注入面"。

### WP3 `3c2da4dc` — anti-peek 短路收权+幽灵提交(I2+I1)
- **病**:canonical 裁决两轮全对(LLM 判定器 conf 0.85"要求讲解知识点"/确定性降级"temporary_detour"),
  terminal 短路不读它,用默认-block 关键词谓词翻案;#417 白名单=第 N+1 补丁;
  幽灵提交:`re.findall(r"[A-E]")` 从"计算CV和SV"抠出 user_answer=C。
- **修(两段式)**:Stage A default-on 纯确定性(窄隐式求助兜底表命中→无条件拦[SEV+LLM-down 兜底];
  canonical 判 detour→放行+redact);Stage B flag 默认关(`DEEPTUTOR_ANTIPEEK_CANONICAL_FACET_ENABLED`,
  判定器输出 facet `seeks_active_answer_help`,LLM prompt 变更必须灰度)。

### WP4 `84d1efc5` — 出题承接收权+科目薄切(I3)
- **病**:锚点在 session state 一寸之遥没被消费,"本轮有没有考点"被 ≥9 个 regex decider 互相矛盾地重判,
  fall-through 提取器被"考情权重"劫持→罐头拒答还被打包成 q_1 污染 active_object;
  "用户声明科目"在系统里 0 个 writer,4 个静态"建筑实务"权威压场反向纠正用户。
- **修**:resolver 唯一 topic decider+最新优先;删 coordinator 重复域门+第二套提取器;罐头撤除→
  带对话尾部 grounding fall-through 到 generator(它有科目锁);真冷启动澄清一次不写 active_object;
  科目薄切(title 降权+指令行,诚实标注为缓解;declared_subject 全字段被指挥官有罪推定砍掉,
  触发条件=薄切后 live 仍复现或接入第二科目 KB)。

## 4. Deviations 账本(全战役,含指挥官裁决)

| # | 偏离 | 理由/触发条件 |
|---|---|---|
| D1 | I1 case 型命中直通保留 | case 家族收权推迟;触发=case 型假命中 live 证据或案例家族战役开工 |
| D2 | I1 检索→active_object 写入降级推迟 | 与对象连续性家族纠缠;幽灵提交修掉后毒化链可执行伤害已断 |
| D3 | I2 白名单物理保留 | flag OFF 时是口诀场景唯一活路;flag 毕业后下一 PR 删 |
| D4 | I2 历史注入过滤不做 | 先 live 红队测"总结考点"轮是否实际泄底,有证据再立项 |
| D5 | I3 declared_subject 新字段砍掉 | 有罪推定成立(字段仍只喂 prompt 非 terminal;单科目产品现实);薄切先行 |
| D6 | I4 client_turn_id 幂等键推迟 | chat.js 每次发送生成新 id,服务端单边加无用;与前端修复配对时做 |
| D7 | I4 被取代 turn 中文墓碑不做 | 取代者的回答本身就是交代(less is more) |
| D8 | WP1 对称 ratio→有序覆盖率 | 对称 ratio 被口语前后缀稀释会过杀真原题(0.807 vs 0.958 实测) |
| D9 | WP1 已知残留:非数词类单字变题(做法正确↔错误)字符容差不可判 | 部署里程碑 live 标定+题库变题家族抽样对抗 |
| D10 | WP2 loop 2290/3013/3027/4168 EMPTY 兜底未收编 | 指挥官收薄版明示范围;行为 bit 不变 |
| D11 | WP2 security-guardrail 终态 commit 不重排序 | CAS 已防复活;残留=毫秒窗 guardrail 消息落库,触发=live 双消息证据 |
| D12 | WP2 失败 turn 跳过 mobile learning 写入 | 失败文案进学情=污染学习证据(写入侧断环先例) |
| D13 | WP2 孤儿通知"至多一条"优先于"至少一条" | CAS 赢家 add_message 失败不补发,与终态 CAS 语义一致 |
| D14 | I5 observe-guard(deep_question.py:3854) fail-loud 收口推迟 | 待生产 window hits 证据 |
| D15 | test_capabilities_runtime.py 22 慢性红不修 | main 预存在,归 Battle2 战役收尾(stub async 化) |
| D16 | WP3 semantic_router.py 超施工包文件清单 | 必要接线:normalize 不保留 facet 键则每跳静默丢(observe-only 旗标教训);纯附加 |
| D17 | WP3 Stage A 已知范围界限 | lifecycle 模式(advisory 裁决未驱动路由)的知识请求维持 canned,至 facet flag 毕业——拿非权威裁决放行=把 advisory 升格,拒 |
| D18 | WP3 过程事故:复合命令夹带 git stash | pop 带入他分支快照,已 git restore 还原、stash 栈无损;再验证"禁复合命令夹带 git stash" |

## 5. 可迁移教训(给后来者)

1. **修复 hold 与否要用邻近变体实测证伪**,不能信"✅已修"标记——#417/#422 都只赦免了事发的那一个词/切片。
2. **canonical 裁决存在≠被消费**。本战役主病的最纯形态:系统自己判对了(detour/讲解),terminal 用
   关键词谓词翻案。修法永远是"让 terminal 变成消费者",不是"让谓词更聪明"。
3. **relevance 与 identity 是两种判断**,前者不许铸后者的章;置信 floor(0.98)是身份洗白的签名。
4. **错误必须保型**:错误一旦被格式化成字符串进 content 通道,下游只剩 regex 猜测(必漏+打地鼠)。
5. **指挥官预案也会过杀**:每次收紧判据,都要有反向 SEV 反例(真原题必须命中)同步钉死。
6. **并发病与语义病正交**:任何语义修复都消解不了双真值+无 FSM;先收 FSM 再谈其他。
7. **测试镜像是第二权威**:契约翻转必须清点全部镜像副本;CI 暗测试让红 12 天无人见。
8. **对新增层有罪推定实战有效**:declared_subject(新字段)、墓碑(新消息)、幂等键(新列)都被砍/推迟,
   每一条都省了一层未来的 patch anchor。

## 6. 验证台账(随战役更新)

- WP0:56/56(先 1f/55p);邻居 184 passed;指挥官独立复跑一致。
- WP1:263 rag passed(先 21 RED);对抗对 5+2+2 组全拒;真原题 6 变体全命中;contract guard [rag] PASS。
- WP2:新 27 用例(先 23 RED);验收 345 passed;辐射面 193+158+26+20+33;counterexample 四层
  byte-identical;竞态修复 34 passed+151 passed;指挥官独立复跑 138+183 passed。
- WP3:16 RED→229 passed(44 新用例);SEV 反例逐条全绿;回归 248+334+84+183;指挥官打回一次
  (facet=False 早退真洞:不得降级显式 reveal/不得绕过序数 handler)修复后条件 PASS;
  正典开火层序=显式格式/解锁→窄 SEV 兜底表→facet(flag)→canonical detour→legacy。
- WP4:目标+相关套件 354 passed;12 条旧契约 pin 翻转;belt 证伪通过;contract guard PASS;双 index PARITY OK。
- **战役级收口(五包全落地,2026-07-12)**:跨包联跑 1246 passed 0 failed(turn_runtime 被 WP2/WP3/WP4 各改一块互不踩);
  三 SEV hold 单独核全绿——泄露 `test_tutorbot_unanswered_reference_short_circuit`+WP0 隐式分支 33 passed、
  回指幽灵 `test_question_followup`+`test_turn_start_demote_canonical_pipeline` 197 passed、
  倒诬题库假命中 `test_supabase_strategy`+`test_rag_pipelines` 126 passed。
- **预存在红取证(确非本战役引入)**:`test_capabilities_runtime.py` 22 红=在战役基线 1e9f6a40 独立复跑同样 22 failed
  (签名 `SimpleNamespace can't be used in await`=Battle2 W1 async 化 stub 债),归 Battle2 收尾;
  `test_tutorbot_guardrails.py` 3 红=隔离污染(单独跑 20 passed)。release-gate 只 attest 真实跑绿的域,预存在红标 not_exercised。
- **push 阻塞(待 owner)**:WP0 commit 改了 `.github/workflows/tests.yml`,当前 OAuth token 无 workflow scope,远端拒推。
  6 个运行时 commit+2 docs 完整在本地分支;CI shard 登记 patch 已导出为本地文件(artifacts 按仓库政策不进 git),owner 有 workflow scope 后 apply 或直接 push 完整分支。
- 分支基于 1e9f6a40;origin/main 已前进(#454 84909343),PR 时需 rebase(按里程碑做)。live ≥3 轮复验属部署里程碑,未在本地宣称。

## 7. 诚实边界

- 本战役宣称面=分支上 commit+全量相关域测试绿;**live ≥3 轮复验属部署里程碑**,未做前不得宣称"修好"。
- 军团 eval 尺子问题(construct 错位/监测死亡)是独立战役,本战役只修被它发现的运行时病。
- 生产主机 121.41.204.57 不可达未取证;E6 残留文件 /tmp/realstats.py 待 owner 授权清理。
