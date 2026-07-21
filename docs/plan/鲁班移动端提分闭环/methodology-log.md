# 方法志（发现 → 分析 → 解决 的完整叙事）

> **本文档是什么**：与 `implementation-notes.md`（结果账本：做了什么、验证数字）互补的**方法层记录**——
> 每个重要问题一节，写清"怎么发现的、走过哪些歧路、为什么这条修法赢了"。
> 结论会过期，方法不会；失败的尝试是最值钱的一栏。
> **写作纪律**（owner 2026-07-12 立）：五段式 = ①现象 ②发现路径（含走错的岔路）
> ③分析（root cause + shared failure shape）④修法与理由 ⑤验证与教训。倒序追加，新在顶。

> 战役级完整编年另见各战役 ops-log(如 `docs/plan/观测发布与生产上线/2026-07-12-battle2-compressed-train-operations-log.md`)。
---

## 2026-07-21 · webview 留白"时有时无" + 供给错误卡第 4 修:两个都是"不变量挂在偶然路径上"

**①现象**:owner 真机反馈两症状:(a) 讲解卡/随堂练两侧留白,同一手机时有时无;(b)「教学内容没有加载成功/连接服务器失败」错误卡反复出现,"上次修过但没根治"。

**②发现路径(含岔路)**:双专家并行只读测绘。岔路一:留白最初怀疑机型/viewport 玄学——117/117 工件 viewport 全同,排除;真判别子是 CSS 宽 >390px 机型 × 进的是哪代工件。岔路二:错误卡若按"网络问题"去加重试,就会成为第 4 个无效补丁——git 考古发现 07-14/07-18/07-19 已修 3 次(呈现层/准入层/telemetry 退避),各修一个 decider,全没触碰断点,这正是 patch-spiral 实锤信号。

**③分析**:(a) 留白根因=发布器 fit 注入排在 ctrlHidden/S07 early-return **之后**,62/74 讲解卡+40/40 练习页零自适应;已修的 12 卡还依赖 componentDidMount 运行时 JS(首帧竞态)。shared shape=呈现不变量无单一权威,挂在偶然分支上。(b) 错误卡断点=learn.js catch 把单次 HTTP 瞬时失败直接提升为"供给不存在"终态(transport 冒充 terminal truth);放大器=noRetry 单发×单域名×telemetry 首轮 21 并发抢槽(07-19 只修一半:退避挡不住首轮,且 wx.request 无 timeout 默认 60s 占槽)×每次 onShow 重抽。全量测绘出 13 个各自为政的客户端 decider。

**④修法与理由**:(a) 收权单一发布权威 `_inject_width_fit`:head 级同步内联,对每张发布页无条件注入(zoom var --lz-fit,首帧即生效);practice 壳打标 lz-fitwrap——踩过一坑:fixed 覆层 DOM 嵌套在外壳内,双打标=zoom 相乘 1.21 过放,改为只标非嵌套顶层。30 站 teach 源不在仓(bus factor=1 旧患),加 `--apply-width-fit` source-independent 托管调和(照抄 reachability-gate 的 sha 重钉纪律)。(b) 显示仲裁收权:错误终态只在"从未有任何已知供给"时合法;瞬时失败静默保供给(已在屏 vm → 7 天 last-known-good 快照,纯 reader 策略复用 report-cache,零新 writer 零新存储);telemetry in-flight≤2+显式 10s timeout。**不加**lessons 重试——那是第 N+1 个 decider。

**⑤验证与教训**:74/74 lesson+43/43 practice 含 lz-fit-boot;`--practice-only --check` 绿;publisher pytest 46 passed;`--apply-width-fit` 幂等 0 改动;yousenwebview 全量 JS 测试 0 失败(supply authority 新增 3 仲裁案例;telemetry"10 并发=10 请求"旧不变量按收权重写为"≤2 封顶+最终全投递")。教训:同一 bug 类修到第 3 次还复发,必须停手先测绘全 decider 再收权;确定性发布不变量必须放在 early-return 够不着的位置;zoom 类缩放在嵌套节点上会相乘,打标只能标顶层。**未完成**:生产未部署(web/public 烘焙镜像需全量 rebuild+容器内 grep lz-fit-boot 反自证)、小程序需 DevTools 上传、>390px 真机人眼验收未做——未做前不宣称"线上已修好"。

**①现象**:owner 要求对 07-15 计划做对抗评审并按"现有能力先上一版"收尾。评审发现计划自身工程事实全部属实(633/17/1899 等数字可精确复现、A01 变形缝有文件级铁证),但 §6 建了一套 7 日 A/A + powered A/B 统计体制;同时工作区躺着 ~3000 行未提交改动,来源不明。

**②发现路径(含走错的岔路)**:三路并行取证(代码真值/关联计划一致性/第一性原理对抗)交叉出三个 SEV-0——§6 与 owner 07-10 在册拍板"撤销 spike 统计路线改逐人回放"直接冲突且零引用;考试日历(9 月,T-60)全文缺席,与历史审计批评的"考试日历盲区"原样复发;B1 教研签名是幽灵资源而 fail-closed 设计把人力缺口自动转成永久零供给。岔路:一度以为工作区改动是遗留脏改,直到读取 Codex 会话 rollout 才确认是另一个 AI 军团按同一计划执行到半程(B3 完整/B2 半截/B5 已改),且**仍在活跃写文件**(mtime 13:42 vs 审计 13:38,红测试被它中途自愈)——任何"直接接管"都会互相覆盖。

**③分析**:root cause 两条。(a) 计划作者(AI)在无流量约束的真空里优化测量严谨性,没有 join 真实基线(D1≈0-6%、2-3 新用户/天)和在册拍板——**计划纪律缺一道"对照已有预注册与拍板"的机械检查**。(b) 多 AI 共享工作区没有交接协议,"谁在写、写到哪、何时冻结"无 authority——与"并行提交者扫走未提交工作"是同一 failure shape 的 AI 版。

**④修法与理由**:(a) §6 整体降级为确定性发布检查表 + 逐人回放,与 07-10 拍板对齐;考试日历倒排(8/1 送达窗)、owner 本人签发 + 机器预填锚(候选覆盖 100%,签发耗时减半)。(b) 交接协议 = owner 对源窗口下停止令 → mtime 静默核验 → 只读取证确认半截活边界(B2 服务端回路) → 按纵切窄提交落盘(commit+push 即防扫走护栏) → 再动一行代码。疑属其他在飞窗口的文件(数据盘点 260 个)宁可不提交也不隔离提交。

**⑤验证与教训**:接管后六个窄提交全部推送,合流回归 835 passed + Node 106/106,B2 断链(receipt 服务端不收不回显 → 桥接 100% 死路)以 RED→GREEN 收口,顺带消灭裸 items 泄 `is_correct` 的第二题面形状。教训:一,评审计划先 grep 它引用了谁、**漏引了谁**(在册拍板/预注册/真实基线是最常被漏的);二,发现另一个 agent 的半截活,最有价值的动作不是替它写完,而是先找到"它写了但没人消费"的断链(resolve_projection_receipt 零调用方)——consumption 断链是半截活的标准指纹;三,多 AI 协作的冻结令必须由 owner 在源窗口下达,旁路 kill 进程或抢写都会制造血统事故。

---

## 2026-07-16 · HOLD 不是关闭路径，首批验证也不能变成 F16 特权

**①现象**：上版计划识别了内容资格、H5 exact identity、多端 probe 并发和真微信/A/A 四项风险，却把它们都压成一句 `Product P0A HOLD`；同时要求先审完 633 道 candidates，才进入一个 Pack 纵切。第一次修正又把 F16 写成唯一首发主角，把“窄切片”误做成“特定 Pack 特权”。结果是判断安全，但计划仍然对单 Pack 过拟合。

**②发现路径（含走错的岔路）**：红队先从全库中找到 A01/F03/G03 反例，由此提出“内容冲突不清零不发布”。这个安全结论本身没错，错的岔路是把“不安全的题不得被发出”等同为“所有题都必须先变安全”。随后又因旧父级 PRD 把 F16 当历史默认，就直接把它升格为首发概念；用户指出后回到 first principles：要验证的是留存链路能否跨内容成立，不是 F16 本身。再从 H5 bridge 的 `surface + answer_indexes`、selection digest 不绑 probe、review claim 按 completion 去重的代码路径，将另三项分别定性为通用身份缺口、幂等键缺口和验收/时间证据。第二轮再追 INDEX、旧 P0A/M0 与五模块 IA，发现旧 authority 仍会把 F16、独立复习 Tab、半写/AI 批改重新带回执行面。

**③分析**：root cause 是**把仓库完整性当成发布集合完整性，又把发布样本名当成产品概念，并把不同成熟度的证据压成一个 HOLD**。一等事实应是“某个 Pack 这次允许发哪些 exact items”，唯一 authority 应是现有 pack manifest + SHA-pinned per-Pack signed artifacts 所表达的 Pack-agnostic default-deny eligible issued set；“首发 Pack 切片”只是检查视图，不能长成新的 `release_cell_id`/schema/store。633 compiled inventory 只是候选原料，F16 只是其中一个 pack_id。同理，7 日 A/A 不能在当天“修完”，但它只阻断 treatment 和产品 GO，不应阻断代码和内部 QA。

**④修法与理由**：把计划改为 Pack-agnostic 首发 Pack 切片、B1–B5 关闭表和 R0–R4 release ladder。B1 从同一资格池准备 2–3 个代表性 Pack，每个只签发 5 道 anchor + 1–2 个 fact 三件套，其余默认不可选；treatment 默认 2 个，第 3 个由自然流量门决定。B2 将 H5 收权到 exact IDs + digest；B3 将 review 幂等从 completion 收权到 user + probe/cycle；B4 分为真微信验收、测量预检和不可压缩的 7 日 A/A；B5 将产品表面收权到五 Tab、学习首页唯一 CTA。父 PRD 拆为 P0A-0 Practice 留存切片与 P0A-1 半写/AI 批改深度层，旧 F16/复习 IA authority 顶部标记 superseded。禁止 Pack ID 专属分支；未入选只代表本 cohort 未轮到，不是资产降级。

**⑤验证与教训**：计划反例必须同时成立：“仓库仍有 A01/F03/G03 冲突”与“另外 2–3 个 Pack issued set 全部已签发”可以并存，此时合格 Pack 内部 QA 应通过，有冲突 Pack 仍不可发。实现测试必须参数化覆盖可发/冲突/供给不足三种 Pack，且搜索不得出现 `pack_id == F16` 专属路径；文档一致性检查必须证明当前 IA 只有 `学习 / 历史 / 问鲁班 / 学情 / 我的`，旧文档不再自称执行 authority。后续任何计划发现 blocker，必须同时写明 owner、输入、产出、Pass、估算、并行关系和只阻断哪一层；不再用一句 HOLD 冒充计划，也不再用一个样板 Pack 冒充产品。

---

## 2026-07-15 · completion ID 不是提交证书，compiled 数量也不是内容签发

**①现象**：计划写成“633 道 Practice 已释放、错后可同组换题、D+1 可精确复测”，但代码与数据出现三组反例：视频 H5 仍只传 surface/index；同 completion ID 的孤儿 item 可以在 terminal 后进入弱点和图谱；撤题清单缺失或损坏时，signed variant 会在部分读路径复活。内容侧还存在 A01/F03/G03 已知冲突进入 compiled/public Practice。

**②发现路径（含走错的岔路）**：先把 generic learning home 的无-surface 路径当成视频主链已接通，逐跳追 H5 bridge→retest page→read model 后才发现视频显式带 surface，所以仍固定 public 五题。又用真实 writeback 先产生合法 terminal，再追加一个同 completion、同 request hash、但不在 `item_event_refs` 的错题；旧 synthesis 把它晋升为 confirmed weak point，证明 replay 的闭包校验没有被其他 reader 共用。最后分别比较 variant summary、selection、resolve、supply digest 与 pool meta，发现它们各自重算 active set，而 blocklist 异常默认空集。最危险的岔路是继续加一个 compiled runtime blocklist；它只能遮住已知字符串，仍没有事实级撤销。

**③分析**：shared failure shape 是“相关键/派生物冒充 authority”。`completion_id` 只能关联事件，不能证明哪些 item 已提交；compiled/manifest 只证明结构和可重建，不能证明事实正确；serve-side blocklist 只影响一个 projection，不能撤销同一 source fact 的其他派生面。三个问题的共同根因不是少 if，而是缺少唯一 closure 与内容资格层。

**④修法与理由**：把 retest commit authority 收到 `evidence_lifecycle.committed_retest_closure`：canonical terminal 必须精确引用 item，并重核 completion/request/pack/mode、题数和分数；synthesis、typed graph、三层学情、report、pack lifecycle、prescription outcome 和 replay 统一消费它。remote evidence reader 复用 canonical classifier，控制 claim 不再泄漏。signed variant 由一个 active resolver 同时服务摘要、选题、解析、digest 和 meta，撤题 authority 缺失/损坏全链 fail-closed。计划则把原 P0-A 改成 S0 事务基础设施，把 S1 内容资格和 S2 F16 产品纵切设为 release blockers；不在本轮脏前端上补 UI，也不假装已完成真微信链路。

**⑤验证与教训**：孤儿 item 与 partial typed graph 先 RED 后转绿；remote claim 泄漏测试先准确失败后通过；撤题 authority missing/corrupt 对 summary/select/identity/meta 全部 fail-close。Claude Code 对抗再抓出 NaN/Infinity 读侧崩溃、损坏 item score 被当 0 和远端 terminal 穿透测试盲区，补成非有限/损坏分数 fail-close 与 remote closure 回归；Git 追溯确认 terminal 从首次引入就携带 request hash/item refs/逐题分数，未凭猜测添加危险 legacy fallback。教训：①关联键不等于 commit certificate；②一个 reader 有 closure 不等于全系统有 closure；③结构可判不等于内容可签发；④动态池代码可达不等于目标入口已接通；⑤less is more 要减少裁决点和产品承诺，而不是少做发布真相核验。

---

## 2026-07-14 · “生成物都在”仍不可交付：用干净 checkout 反证练习 authority 闭环

**①现象**：全量 37 pack / 39 surface 在当前 worktree 能跑，但独立专家按 PR diff 复核时发现，分支只包含少量 finished practice 源，其余 sidecar/public 是从别处生成后带入；另有跨账号缓存、lesson/practice 共用缓存版本、sidecar 只验结构不验自身字节三类潜伏问题。

**②发现路径（含走错的岔路）**：首轮验证集中在“运行时能加载 195 题”，没有先问“全新 clone 能否从唯一源重建 195 题”。hostile review 逐一反查 sidecar 的 `source_path/source_html_sha256` 才抓到缺源；把两个选项的 `correct` 对调且不破坏 schema，又证明形状校验不能防合法形状篡改。缓存审计则从退出登录场景反推所有 storage reader，发现只修 dashboard 会留下 history、pending turn、闯关草稿等同形漏洞；最后从 source-only PR 反推 CI 外层 paths，又发现重建闸虽存在但根本不会被题源改动触发，Windows `autocrlf` 还会在 checkout 时改坏 authority 字节。

**③分析**：共同 failure shape 是派生物或缓存开始替代 source/learner authority。sidecar/public 可以是运行时优化，但必须由 tracked finished 源确定性重建并被 manifest 钉住；本地缓存可以加速投影，但 owner 不匹配时必须视为不存在。lesson 内容版本与 practice 答案版本是两个不同事实，硬塞进一个 SHA 会造成无关缓存失效，也掩盖真正改变的是哪一层。

**④修法与理由**：精确纳入注册表消费的 39 个 practice 源，不把整套 teach/audio 资产扩进本 PR；publisher 增加 practice-only 重建/字节检查，full publish 与它复用同一 compiler。manifest 增加 sidecar digest，运行时在 JSON 解析前先验字节，再做内部 source/public 交叉校验。所有小程序 owner-sensitive storage 只经 auth 暴露的统一 adapter；页面 wrapper 不再各自拼 key。read model 分别使用 published lesson SHA 与 practice source bundle SHA。

**⑤验证与教训**：机械闸必须同时覆盖 clean-source completeness、deterministic rebuild、shape-valid tamper、exact unavailable set、schema registry 字段闭合、跨账号读写隔离、source-only CI 触发和 autocrlf byte-exact。教训：①“生成物可加载”不等于“仓库可重建”；②schema-valid 不等于 authority-valid，派生物本身也要内容寻址；③缓存不是无害实现细节，它是 reader，必须服从身份 authority；④闸写出来不等于接上 CI，必须用最小变更反推触发面；⑤less is more 不是少提交必要源，而是只提交被注册能力真实消费的最小完整源集合。

---

## 2026-07-14 · 从 F16 到全量不是复制特判，而是把供给与学情收进两个 authority

**①现象**：F16 链路打通后，其他 finished 卡仍只在 HTML 内本地判分，客户端只对 F16 识别成品练习。表面上是“再加 36 个包”，实际上同一能力被 pack-id 特判、目录 glob、public HTML 和签发变体库四种供给选择争夺。

**②发现路径（含走错的岔路）**：专家组先从 finished 注册表盘点，而不是 glob 目录，得到 37 pack / 39 surface。样本实读发现并非一种 JS 形状：常规 Q 有随机 ord 和直接顺序两型，S07 用 POOL/buildDeck，A02 由 bank() 返回 A/Dg。“一个 regex 扫所有卡”会把多选降格成单选；“按文件名全收”又会把未登记旧卡上线，两条捷径都被否决。hostile 遍历还抓到 ord 页的选项会随机打乱：页内存的是展示位次，服务端 sidecar 要的是源位次，直传 index 会静默判错。

**③分析**：一等业务事实有且只有两个：“这道题的正确答案是什么”由当前 finished HTML 决定；“这个学生这次做了什么、是否形成学习证据”由 canonical terminal/LearnerState 决定。public HTML、sidecar、manifest 都只能是可验证投影，不能成为第三个答案或掌握度 authority。

**④修法与理由**：把编译、格式适配、五题选择、identity 和 SHA 校验下沉到 `practice_html` fat service；publisher、API、web-view bridge 只做登记、投影和传输。manifest 显式声明哪个 pack 有 compiled practice，前端不再猜 URL；取题与 writeback 共读同一 sidecar，S01 用 `practice_surface` 在同一 authority 内区分三面。发现问鲁班 dashboard 的本地缓存未按用户分区，一并改成 user-scoped envelope，因为这是“全模块共享 LearnerState”后必须封住的跨账号读侧漏洞。

**⑤验证与教训**：全量编译要同时证明数量（37/39/195）、适配器形状、展示位次→源选项 identity 还原、未登记文件拒绝、无答案泄漏、public/source SHA 漂移 fail-close、一个非 F16 的真实五 item + 一 terminal 写回，以及五模块返回刷新。可迁移教训：①泛化要从业务形状开分支，不从 ID 开分支；②显式注册比目录存在更接近发布 authority；③内容全量接入不等于 mastery 全量升级，forward 仍必须 L0/non-promoting；④缓存也是 reader，共享学情后必须按 canonical user 隔离；⑤用户点了哪个可见选项与 authoring 数组第几项是两个 identity，必须显式还原。

---

## 2026-07-14 · 写进 LearnerState 不等于用户能感知：terminal 消费者必须共用同一裁决

**①现象**：F16 五题完成接口返回 terminal 和正式分数，但学习路线仍可能显示未学、复习页没有次日任务、今日进度从 0 变 6；用户还会先看 HTML 本地成绩，再点一次“保存”看原生正式成绩。代码看起来每一段都存在，产品上却感知不到闭环。

**②发现路径（含走错的岔路）**：专家组先从真实 `RetestWritebackService` 输出反向追消费者，而不是继续看手写 fixture。直接把 compiled terminal 喂给 `project_pack_lifecycle`，得到 `unlearned + last_completion_at=""`；再聚合 5 item + terminal 得到 6。旧绿测手造的是 signed authority，恰好绕过真实 F16。最诱人的捷径是给 item 的 `payload.pack_id` 加 fallback，但它会让 partial append 在没有 terminal 时也点亮，重新造出第二完成权威，因此被否决。第二轮 hostile review 又发现 dormant replay 会信任任意 `completion_terminal=true`，独立网页还用“稳了 / 满分手”抢先下掌握结论；第三轮沿所有 terminal reader 追踪，继续发现 prescription outcome 旁路可把伪 terminal 投影成“验证通过”，旧 boolean 题也会在 terminal 前显示“真懂”。这些反例说明不能只修 F16 happy path。

**③分析**：shared failure shape 是 authority drift + producer/consumer 粒度不一致。writer 说 compiled terminal 已提交，lifecycle 只认 signed terminal；进度聚合把“提交边界”当成“第六题”；HTML 又把客户端结果当最终结果。真正的一等事实不是某条 item，也不是某个页面状态，而是“这次 completion 是否被 canonical terminal 封口”。所有下游必须消费同一个严格裁决。

**④修法与理由**：建立 mode-authority-confidence-level-promotion 严格矩阵，并让 completion ids、生命周期时钟、item promotion、existing/replay terminal 校验及 prescription outcome reader 共用它；reader 再以 verification source allowlist fail-close 删除字段攻击：只放行合法 construction grading，assessment testset 必须是 canonical terminal，foreign/unknown 一律不验证。item 通过 terminal completion map 归包，terminal 自身从题目循环与进度计数中移除。UI 做减法：第五题自动提交，HTML 与旧 boolean 题都只描述本轮作答、不宣判掌握；原生 terminal receipt 是小程序唯一正式结果。路线/复习 onShow 只重新读取既有 projection，不新增 done cache、状态表或前端调度器。compiled forward 仍为 L0，不进入 mastery authority。

**⑤验证与教训**：真实 compiled terminal 测试先 3 RED 后转绿，hostile review 补出的 forged replay、旁路 prescription reader（伪字段、删字段、foreign source）与预览越权文案都有反例回归；相关 Python 321 PASS，4 个 Node 行为合同、3 个页面脚本 syntax check、publisher determinism、contract guard、Ruff 与 diff check 全绿。DevTools 真实页面确认本 worktree 路线可渲染、F16 receipt route 在 test2 后端 404 时诚实失败且不出收据。教训：①writer 有字段不等于 consumer 认字段；②测试必须用生产 producer 产物，手造相似 payload 会制造假绿；③terminal 是 commit boundary，不是一次作答；④“让用户感知”要同时检查唯一结果、持续投影和刷新时机；⑤replay、旁路 reader 和预览同样受 authority 边界约束；⑥只按字段存在做校验可被删除字段绕过，业务类型还需 fail-close source allowlist；⑦未部署的本地闭环必须与线上 true-entry 分层汇报。

---

## 2026-07-13 · 先确认你接的是哪一版，再谈如何利用视频尾练习

**①现象**：第一次试点误把旧 worktree 的 F16 成品当最终版，又手改 public 生成物并让服务端反向读取它。表面上链路和测试都能跑，实际上用户看到的 teach/practice、选项反馈与 6 段音频都落后一版；若继续完成 writeback，会把“答了旧题”记成当前 F16 学习证据。

**②发现路径（含走错的岔路）**：用户直接指出给出的 F16 不是他认定的版本；专家组随后对 root finished、pilot finished、public、publisher 做逐文件 hash，确认 teach/practice SHA 不同，6 题 identity 0/6 重合，且整包音频与 audit 也发生变化。另一个盲区是 pack Markdown SHA 没变，如果 URL 仍只靠它缓存，即使重新发布，用户也可能继续看到旧卡。

**③分析**：一等事实仍分两类：内容事实归当前 finished HTML，学习事实归 LearnerState/RetestWritebackService。public 只是部署消费者，绝不能反过来成为答案 authority；“六道最终题”和“课后呈现五题”也不是同一事实，前者归内容源，后者归 selection policy。把两者拆开，才能既尊重最终成品又满足五题体验。

**④修法与理由**：只修 F16。把用户指定 bundle 完整同步进试点；publisher 单向生成 lesson/practice、复制全部音频，并从 raw finished HTML 生成后端非公开 answer projection。HTML 继续承担正确的成品作答体验，固定呈现 Q1/Q2/Q3/Q4/Q6 且保留选项随机化；练完后桥接稳定 option identity，原生页只显示服务端重判与 terminal 收据，不让学生重复答第二套。URL 用 bundle SHA 破缓存，source practice SHA 变化则 selection 编译 fail-close。

**⑤验证与教训**：Python 95 PASS，publisher 重跑字节稳定，public 六题块与 finished 完全一致，11/11 音频与 manifest 同 hash；Node 覆盖 bridge、服务端 authority 与 first-run 零回归。真实浏览器走完五题并看到正确结果页；微信 DevTools 真实 package 页完成 lesson→practice 切换，但无登录态/后端 terminal，因此仍只叫 local pilot。可迁移教训：①同名目录不是 authority，必须核 commit/hash/整包；②只同步 HTML 会制造音画漂移；③生成物可被运行时消费，但不能夺取 authoring authority；④缓存键必须跟真正变化的成品 bundle 走；⑤数量策略只选集合，不复制或改写答案。

---

## 2026-07-12 · 判定器优化闭环:同一 flag 两次相反决策都对(数据驱动非横跳)

**①现象**:判定器输出 token 三批 live 递进——flag 批(思考ON+verbose)p50=197 → nothink 批(思考OFF+verbose)105 → stack 批(思考OFF+slim)**59**,总降 70%,SEV=0/质量零回归。

**②发现路径(关键=一个 flag 被我先关后开)**:
- 第一次(开 flag 验证 B2 slim):p50=197 无收益 → **当场关 flag**(结论:slim 零收益)。
- 修好关思考后再测(nothink 批):p50=105,揭示剩余大头是 **verbose reason 字段**(50-80 字中文 rationale)——之前被思考 token 淹没看不出。
- 据此**重开 flag**(叠加 slim):stack 批 reason 空 11/13,p50 再降到 59。

**③分析**:shape=**前提依赖的收益评估**。同一个 slim schema flag:思考没关时,它砍的 verbose reason 被更大的思考 token 淹没=净零收益;思考关掉后,verbose reason 成了剩余输出的大头=slim 兑现(105→59)。**flag 的收益不是内禀属性,依赖前置条件(思考是否已关)。** 两次相反决策(先关后开)都由当时的 live 数据驱动,不是横跳。

**④修法与理由**:两杠杆正交叠加——①关思考(executors dormant authority 治本,不挂 flag,见下一条)②B2 slim(flag)。先上治本的关思考(确定收益),再据新数据重开 slim(叠加)。每一步都 live 验证再定去留,不靠离线推断。

**⑤验证与教训**:三批同题集串行 live,token 会计直证思考关(gap≈0)+ reason 空直证 slim 生效;SEV=0(试探/推迟终态非 submission,Step4.5 兜底不依赖思考)。**可迁移**:①一个优化"没效果"先查是不是被另一个更大的开销淹没(分层归因),别急着判死;②flag/开关的收益依赖前置条件,前提变了必须重估,别锚定"上次测过没用"的旧结论;③先关后开同一 flag 不丢人——只要每次都有当时的数据支撑,这是诚实迭代不是反复。

---

## 2026-07-12 · 判定器思考 token 真根因:dashscope 被 thinking 门漏掉(两次假设被实测证伪)

**①现象**:承接 followup flag 那条——判定器真瓶颈=输出 token 70-80% 是 deepseek 思考 token。要关思考,先定位"思考开关在哪、为什么判定器没关"。

**②发现路径(两次假设都被实测推翻,最值钱的部分)**:
- **假设A**:factory.complete 路径压根没 thinking 控制。**证伪**:grep 到 `executors.py:74 _apply_provider_thinking_mode` 已有 reasoning_effort→thinking 映射。
- **假设B**:executors 一刀切 `thinking.type=disabled`,而 dashscope 只认 `enable_thinking`,所以关法无效。**生产实测证伪**(base64 探针进容器打生产 dashscope):基线 42 tokens/reasoning 61;`thinking.type=disabled`→6/0;`enable_thinking=false`→6/0——**两参数 dashscope 都认,关法本身有效**。假设 B 错。
- **真根因(第三次才对)**:`executors.py:80-84` `if not spec or spec.name != "deepseek": return`。生产 binding=**dashscope**→`spec.name != "deepseek"`→**提前 return,thinking 控制整段被跳过**。config.reasoning_effort=None 也探针实读确认。

**③分析**:shape=**dormant authority**——关思考的门在 live 路径上,但 dashscope 走不到它(provider 判据 `!= "deepseek"` 太窄)。对比 tutorbot 路径 `openai_compat_provider.py:299` 判据 `spec.name in {"dashscope","deepseek"}`——**两条 provider 路径判据不对称,executors 漏了 dashscope**(同一逻辑各写一遍→判据漂移)。

**④修法与理由**:不在判定器加 provider 特例(泄 dashscope 参数进业务层+第三处决策)。修 authority:executors 加 dashscope 分支,**只在显式 disabled 时关**(空 effort 不动)——生产所有 dashscope 调用现都因此 bug 在思考,全局"空→关"会退化可能依赖思考的判分链。判定器用**通用语义** `reasoning_effort="disabled"` 表意图。影响面被"只关显式 disabled"限定=零回归。deepseek/其他 provider 字节不变。

**⑤验证与教训**:实施+eval 交 agent(歧义集思考 on/off 分类一致率≥90%,SEV 红线=试探/推迟不得误判 submission)。**可迁移**:①改 provider 行为前必实测该 provider 认哪个参数,别靠文档/直觉(假设 B 就错);②"门在但不生效"先查 provider 判据是否覆盖当前 binding,别急着改参数格式;③同一逻辑两条 provider 路径各写一遍→判据必漂移不一致,是收权信号(但收权有回归风险需单独测绘)。

---

## 2026-07-12 · 部署 agent 断线恢复（先勘察后续跑，不重跑已完成步骤）

**①现象**：合并 root-closure 的 Opus agent 因 API 断线中断，最后一句话停在"钩子 exit 3、还在查它要改什么"。

**②发现路径**：不盲目重启任务，先勘察现场四件事：`gh pr list`（PR #454 已开）、`git branch --contains` 孤儿提交（0587ad0d 只在临时 worktree、未上分支）、origin/main 位置（期间又被别的会话推进）、临时 worktree 清单。两分钟拼出"完成了什么/卡在哪/世界变了什么"。

**③分析**：断线 agent 的已完成工作（PR、部分冲突解决）都在远端/磁盘上可勘察——**中断不等于丢失**。风险点是双份真相：临时 worktree 里有未推提交，若重跑全流程会与之打架。

**④修法**：SendMessage 续跑同一 agent（它上下文里有钩子诊断），附上我勘察到的现场快照+剩余步骤清单——续跑比换人重查省一半时间。agent 恢复后又遇构建长跑其回合结束，我核实远端构建真在跑（防并发构建撞容器）后挂监视器等待，最终 agent 自行回归完成四门验收，我再独立抽查一发（容器 SHA/健康码）。

**⑤验证与教训**：终态 main=84909343 上生产，四门+md5 指纹全过，独立抽查一致。
**教训**：a) agent 断线先勘察（PR/孤儿提交/main 位移/临时目录）再决定续跑还是接手；b) 续跑时把"你断前世界又变了什么"喂给它，省它重发现；c) 远端有长跑构建时，主控只挂监视器绝不并发第二个构建。

---

## 2026-07-12 · .secrets.baseline 并行撞车（CI 扫的是合并树不是分支树）

**①现象**：PR #454 被 Security Scan 挡门；本地 pre-commit 钩子 exit 3 且反复重写 .secrets.baseline，行号改了还是不过。

**②发现路径**（执行 agent 的取证，值得入志）：非新密钥——是 contracts/learning-report.md 新增 11 行把既审计条目 `DEEPTUTOR_ATTEMPT_REF_SECRET` 的行号从 111 顶到 122。但按分支树算出的行号提交后 CI 仍红。

**③分析**：**CI Security Scan 扫的是 PR merge ref（与最新 main 合并后的树）**，而本地 hook 在分支树上跑——分支树里 battle2 改过的文件还是旧版，行号口径不一致。shape=**双树口径错位**（本地验证环境 ≠ CI 验证环境）。并行分支各自刷新 baseline 必然撞车。

**④修法**：取 main 的 baseline 原样为基底，仅把该条目行号改到合并树上的 122——在合并树上跑 hook exit 0 稳定不再重写。

**⑤教训**：a) 一切"行号敏感"的基线文件（secrets baseline 等），修复必须在**与最新 main 合并后的树**上核算；b) 多会话并行时 baseline 类共享文件是天然撞点，谁后合谁负责在合并树上重算。

---

---

## 2026-07-12 · 首跑"正在保存学情"永久卡死（三层根因的洋葱）

**①现象**：owner 截图——学习页首跑卡片长期停在"报告已生成，正在保存学情 / 网络恢复后会自动完成"，保存中转圈不止。

**②发现路径**：
- 第一线索：owner 更早一张截图的控制台里有 `POST /first-run/complete 422`——说明不是网络问题，是服务端拒绝。
- 顺 422 找到端点：`mobile.py` 的 first_run_complete 有五种 4xx（409 幂等冲突/409 未签发/409 版本冲突/422 答卷无效/422 请求无效）。
- **歧路**：先怀疑 payload 形状不匹配（pydantic `extra="forbid"`），逐字段核对前端 payload 与请求模型——全对齐，排除。
- 本地直打端点复现：返回的不是 422 而是 **409 `first_run_content_not_signed`**——原来 test2（旧后端）和本地（新后端）是两种病，但共享同一个呈现层症状。
- 追"为什么前端把 409/422 都显示成网络问题"：读 learn.js 重放逻辑，发现它解析 `error.payload.detail.error`——再对照 curl 实际响应，detail 是**字符串** `"{'error': 'first_run_content_not_signed'}"`（单引号！= Python `str(dict)` 的指纹）。

**③分析**：三层洋葱——
1. 最外层（呈现）：前端把一切非白名单错误当网络错，文案"会自动完成"在没有重放成功可能时是谎言；
2. 中层（**真 bug**）：HTTP 异常处理器 `_envelope(str(exc.detail), …)` 把结构化 detail 字符串化，前端永远解析不到错误码 → 治理性 409 被误判成网络错误无限转圈。shared failure shape = **terminal truth 被 transport 层改写**；
3. 最内层（真源头）：首跑内容清单 `release_status: blocked_pending_human_verdict`——**这是设计正确的人闸**（四题需双人签发），不是 bug。学情写入 fail-closed 挡得对。

**④修法与理由**：
- `runtime/safety.py`：detail 是 dict/list 就原样透传（契约 `{detail, request_id, error_code}` 形状不变，类型忠实 raise 方）——治 transport 改写；
- 前端 `api.errorCodeOf()`：对象与旧字符串双形态兼容（test2 未更新期间的 belt）；
- 人闸本身留给 owner 拍板；owner 说"签"后按人闸格式翻牌（双 reviewer 留痕）。
- **连锁坑**：签发会改变清单 sha → script_version 变 → 前端钉的版本常量若不同步，签完立刻变成"版本冲突 409"，白签。同步前端常量 + 给存量卡住的 pending payload 做版本自愈（题集与内容 sha 未变，仅签发元数据改版本，按新版本重放语义安全）。

**⑤验证与教训**：POST complete → 200 `sync_status=synced`，判分/学情事件/今日任务投影全量返回。
**教训**：a) 错误码走过几跳 transport，每一跳都可能把"结构化真相"降级成字符串——错误契约要测到消费端解析成功为止，不是测到 HTTP 状态码；b) "治理态"与"故障态"共享同一个用户症状时，先分诊再修——把人闸当 bug 修掉是最危险的方向；c) 版本号参与内容 sha 时，签发类操作必查所有钉版本的消费者。

---

## 2026-07-12 · 五大模块加载特别慢（一个数字问题的两级战场）

**①现象**：owner 反馈考点卡、复习、学情模块加载特别慢。

**②发现路径**：
- 不猜，先量化：curl 逐端点计时——`review-due` **3.45s**、`mistake-book` **1.0s**，其余全部毫秒级。慢是"两个端点慢"，不是"整体慢"。
- profile `review-due`：投影计算 6ms，**2.98s 在 `list_memory_events`**；再 cProfile 进去：`supabase_store._select_many` ×4 次串行 HTTPS 往返（每次 ~1s RTT）。
- **歧路**：一开始以为是签发 bank 的重复磁盘解析（37+ 个 JSON 每请求重读）——profile 显示它只占 6ms，本地不是主因；但它是**生产侧**的读放大源（生产 RTT 小、QPS 高时会浮出来），所以也修，但排序在后。

**③分析**：本地慢 = 开发机到远程 Supabase 的 4 次串行往返；生产慢 = 同构病（读扇出），只是 RTT 更小。shared failure shape = **dormant flag**：代码里早就建好了 `DEEPTUTOR_LEARNING_BRAIN_LOCAL_PROJECTION_FALLBACK` 和 `DEEPTUTOR_MISTAKE_BOOK_LOCAL_FALLBACK` 两个逃生旗标，从没人给本地开发环境通电。

**④修法与理由**：
- 本地：serve 脚本加两行 env 接通休眠旗标——**零代码修复**（接通已有件 > 写新码）；
- 生产：`_load_signed_bank` 加 (path, mtime) 键读缓存（文件一变即失效，语义与直读等价）+ 学情远程事件 20s TTL 缓存（`append_memory_event` 写侧即时失效，单进程写后读不吃旧值）。

**⑤验证与教训**：review-due 3.45s→0.04s（86×），mistake-book 1.0s→5ms；回归 26+551 全过。
**教训**：a) "慢"必须先分解成每端点数字再动手——三个模块的慢原来是两个端点的慢；b) 修性能先找休眠旗标/已有缓存位，别急着发明缓存；c) 开发机症状和生产症状同构不同因时，两级都要修，但注明各自的主战场。

---

## 2026-07-12 · 考点卡"没效果/太线性"（样本选择性验收的教训）

**①现象**：owner 翻到第 3/8 张卡（验收不合格/严禁验收红线），记忆面几乎空白，只有一条颗粒；批评"这些页面完全没效果，展示太 linear"。

**②发现路径**：
- 全库跑覆盖率（此前没做过！）：141 卡中链≥3段仅 12、双段 2、①②枚举 27——**约 100 张裸奔**。
- 看 owner 那张卡的数据：gist 是"条件→结果"双段（我的链解析器要求 ≥3 段）；quote 枚举是**（1）（2）式**（我只认①②式）。两个解析器双双 miss。

**③分析**：root cause = **用最佳样本验收了"通用"声称**——我拿"竣工验收 5 步链"这张最漂亮的卡验完就宣称 141 张自动适配。与错因银行那次"只看空态没走代表性数据"是同一个病的第二次发作：**供给侧自嗨，没做消费侧全量验收**。

**④修法与理由**：形态学 v2——新增规则牌（双段 gist，禁止词结果=红线章）、（1）式枚举兼容、红线句捞取、句读要点兜底；全部仍是逐字切分零改写（单一权威不破）。

**⑤验证与教训**：裸奔 100→19（86% 有结构），契约 +7 断言。
**教训**：**声称"通用"必须全量覆盖率实测，不许用最佳样本代表全体**——已连犯两次，此条升级为验收铁律：页面验收带代表性中间态数据，内容资产上线核消费字段覆盖率。

---

## 2026-07-12 · 错因银行二级页"信息非常有限"（三闸叠加饥饿 + 消费不足）

**①现象**：owner 点进错因详情，内容极少，问"是我早期对话的原因还是以后都这样"。

**②发现路径**：
- 读详情页数据流：富内容要**同时**过三道闸（pack 归属命中 × 错因码是注册码 × 该站解药池收录该码），任一 miss 退化占位。
- 审计后端解药投影：`build_antidote` 只返回 mental_model + textbook_ref——签发解药池里的 **phenomenon（现象）/wrong_model（旧地图）被整层丢弃，同码多条只取第一条**。付了钱的编译内容只消费了 1/3。
- 用真 ref 铸造（sign_attempt_ref）种 3 笔代表性数据（富/中/薄）实机走查——才第一次"以用户身份"看见这个页面。

**③分析**：两个 shared failure shape 叠加——**逐闸正确、整体饥饿**（每个 fail-closed 单独看都对，叠起来=体验荒漠）+ **供给消费缺口**（21:1 病在单页的缩影）。另发现：判分内核写"人话 diagnosis"的记账拿不到错因码 → 解药查询键永远缺失。

**④修法与理由**：后端全字段投影（items 数组，首条顶层键向后兼容）；vm 加**人话标签↔注册码逆映射**（同一注册表的双向镜像，非第二套归因——这是关键设计判断：镜像既有权威合法，新建归因非法）；解药卡三段递进（现象→✕旧地图→✓新地图）；无码早期记账给诚实说明行。

**⑤验证与教训**：三态截图验收；vm 契约+10 断言。
**教训**：a) 供给侧验收≠消费侧验收——资产上线必须核"消费端到底用了几个字段"；b) fail-closed 组合要算**联合命中率**，不能只证每闸单独正确；c) 归属/查询键的零命中要有遥测，饥饿不可见就永远不会被修。

---

## 2026-07-12 · "两个前端版本互相抢"（多会话并行的血缘测绘法）

**①现象**：owner 两个 DevTools 窗口显示不同界面、不同分支名，"乱死了"。

**②发现路径**：不看表象看血缘——`git worktree list` 全量列 checkout；对未知分支跑三件套：`git log 分支 | head`、`git merge-base 分支 origin/main`、`git merge-base --is-ancestor 已知SHA 分支`。两分钟出结论：另一分支=另一会话今早从我们分支**中途**（5fc9ccb5）拉出，仅 1 笔学情收口提交，不含我们下午 5 笔。

**③分析**：不是版本竞争，是**接力棒没交回**。多会话并行开发的常态病：症状吓人（两套 UI），本质是普通的分叉待合。

**④修法**：单笔合入 main + 工作分支对齐 main + 收敛到单窗口（委托 Opus agent 执行，给足红线：不动对方工作区、不提交本地调试文件、部署四门验收）。

**⑤教训**：a) 看到"版本乱"先测绘血缘再下结论——`worktree list + merge-base` 三件套两分钟给出拓扑真相，比对着 UI 猜快得多；b) 多会话并行时，**每次会话结束把分支推远端**是让别的会话能测绘你的前提（我们一直这么做，所以这次测得快）。

---

## 2026-07-12 · 部署红线发现：生产判分槽=pgo 已存活 3 周（agent 汇报纪律的价值）

**①现象**：部署 agent 按指令核对生产旗标，发现 `LUBAN_CASE_RUBRIC_BANK_SLOT=pgo`，与"禁拨 PGO"红线冲突。

**②发现路径**：agent 没有止步于"发现违规"，做了三步取证：本次 diff 未改任何 env 文件；sync 脚本只写 DEEPTUTOR_* 键从不碰 LUBAN_*；host .env 历史备份 06-19/07-05/07-06 全是 pgo——**存活 ~3 周，非本次引入**，且带金丝雀结构（canary 关、cohort 限 qa/operator）。

**③分析**：红线冲突 ≠ 本次事故。历史上某次变更（待查）把槽拨了过去。正确动作是**取证+上报+不擅动**——翻动一个已上线 3 周、属于别的活跃轨道的判分槽，超出部署授权且可能扰动生产判分。

**④处置**：原样保留，账本+记忆记录，列 owner 裁决项（回 legacy 还是追认 pgo/canary 轨道；裁决前先查这 3 周生产判分是否受 PGO score=null 隐式计分影响）。

**⑤教训**：a) 给执行 agent 的任务书里写"发现异常先取证归因再动"能防两种事故：擅自改（扰动生产）和视而不见（红线烂掉）；b) 红线巡检应该进部署 checklist——这次是顺手发现，下次未必有人顺手。

---


<!-- 以下条目来自 battle2 观测/性能战役线（merge origin/main@896cec7d 时合入，同日倒序并列） -->


## 2026-07-12 followup flag 上线即证伪核心假设(思考 token 砍不到)

1. **现象**:开生产 flag `LUBAN_FOLLOWUP_FAST_TIER_ENABLED=true`(B2 输出瘦身)后,打 followup 密集验证批(15 次判定器调用),输出 token p50=197,**远高于**离线差分预期的 40-54;flag 明明生效(容器 env=true、代码走 slim=True、reason 字段确已收空)。
2. **发现路径**:先按决策规则判"~100+=需排查",第一反应怀疑 flag 没生效→核容器 env 与运行代码路径,证实 slim 确实激活。矛盾即深挖:用 tiktoken 实测可见 JSON=32-51 token,而 Langfuse usage.output=134-245 token——**隐藏差额 93-194 token(70-80%)**。
3. **分析**:deepseek-v4-flash 的输出 token 大头是**隐藏 reasoning/thinking token**,不是可见 rationale。B2 的 schema 瘦身(reason 收成空)只砍可见字段,结构上砍不到思考 token。**团队原假设"followup 延迟主体=冗长可见 rationale"被证伪**。B4 换快档又因 LLM_FAST_MODEL 未配 fail-safe 回主模型=no-op。两杠杆叠加=零收益。shape=**测量代理与真实成本源错位**(把"输出长"归因于可见文本,真因是模型思考模式)。
4. **修法(当场)**:不等 14 天赎罪窗——当场已有零收益铁证,**立即回滚 flag 到 false**(回 bit-for-bit 默认),不留"看着开了其实没用"的认知债。真治本(独立下一刀,owner 待决)=(a)配 LLM_FAST_MODEL 指向非思考轻模型让 B4 生效,或(b)判定器显式关 deepseek 思考模式(enable_thinking=false)——判定器是 temperature=0 结构化分类,本就不需要思考,关掉直接砍 70-80% 输出。
5. **验证+教训**:验证批 32/32 passed、零 None/零 parse error(行为无损,可安全回滚)。**可迁移**:①离线差分乐观≠生产真收益,行为 flag 必须上线后独立验证真指标再宣称;②对带思考模式的模型,"输出 token"不等于"可见输出",省 token 要先分清可见/思考两部分;③当场有可证伪的零收益证据时,直接回滚比留 flag 等赎罪窗更诚实。

---

## 2026-07-12 部署「env 新代码旧」假绿(五层核验全绿仍是假的)

1. **现象**:部署#1 脚本 exit 0,五层核验全绿(host .env SHA=容器 env SHA=目标/healthy/公网/observability),但容器内 `grep completion_start_time`=0——观测基座实际没上线。
2. **发现路径**:靠"容器符号取证"这第六道非标准动作撞出来的;若只走标准五层就记成功了。歧路:一度怀疑并行部署者覆盖(查了 origin SHA 与构建进程,排除)、怀疑 grep 路径错(用容器内 python import __file__ 证实路径对)。
3. **分析**:SSH 在部署脚本中段(远端备份步)被断,某次构建以**旧源码上下文**完成镜像并 recreate 容器,而 .env 注入发生在断连前——env 是新的,镜像是旧的。shape=**自证陷阱**(脚本自报+SHA 标签都不是终态观测)。
4. **修法**:确认无并行构建后重跑完整部署(全量留日志);判据升级=md5 比对容器内文件 vs 宿主 `/root/deeptutor` 源码(`docker compose exec -T deeptutor md5sum <f>` vs `ssh md5sum`)。
5. **验证+教训**:重跑后 3 关键文件 md5 逐字一致;写回 memory(aliyun-deploy 防假成功)与 runbook。**可迁移**:「容器 just-now+SHA 对齐」仍可假绿,发布终极门=容器内文件指纹与源码逐字比对。

## 2026-07-12 eval-bypass 静默失效(前缀 cohort 坑)

1. **现象**:合成批跑 turn 到第 4 条撞 free_trial_daily=3 配额,X-Eval-Bypass 看似带上了却不生效。
2. **发现路径**:先怀疑 bypass key 错(核 ~/.deeptutor_eval_key,对);再单用户 4 连发做最小复现,读响应发现 `identity_out_of_scope`——bypass 是**静默**降级,不报错。
3. **分析**:服务端 eval cohort 白名单只认 `qa_/test_/operator_` 前缀,自拟的 `claude_` 前缀不在册。shape=**静默 fail-open**(越权身份不拒绝而是当普通用户)。
4. **修法**:前缀改 `qa_claude_*`;两次夭折批(13 turn)靠**重拍批前 Prometheus 快照**隔离出窗口,不污染差分。
5. **验证+教训**:改后单用户 4 连发全通过;42/42 turn 完成。**可迁移**:合成流量的身份/配额/限流失败都是静默的,每一步要独立验证"真生效",HTTP 200 不算数。

## 2026-07-12 Langfuse 名字口径陷阱(两臂 summary=0 之谜)

1. **现象**:配对批 PRE 臂按名字搜 "summary"/"heartbeat" 的 generation=0,一度得出"合成会话不触发摘要维护"的结论(主控自己误判,已留痕)。
2. **发现路径**:POST 臂部署了专用 Prometheus 计数器,读到 summary_maintainer **42 决策全覆盖**(实跑 31/skip 11)——与 Langfuse 名字口径矛盾,矛盾即线索。
3. **分析**:summary maintainer 的 LLM 调用在 Langfuse 里名叫 `llm.complete`,不含 "summary"。shape=**名字≠语义**(用命名模糊匹配做存在性断言)。
4. **修法**:观测断言一律锚定专用计数器/结构化字段;名字匹配只用于探索不用于结论。
5. **验证+教训**:计数器 42=42 turn 对账。**可迁移**:「按名字搜=0」永远不能证明"没发生",只能证明"没这么命名"。

## 2026-07-12 基线窗被 owner 挑战 → 实验重设计(假阴性风险)

1. **现象**:原计划采 24-48h 自然流量基线;owner 问"没会员,等有意义吗"。
2. **发现路径**:核对留存事实(42 注册/60% 零消息/D1≈0)——窗口期采样≈0,质疑成立。
3. **分析**:更深的坑是**指标错位**:本轮改动砍的是成本+异步尾巴,不是首字延迟;若只对比 TTFT 会得出"没效果"的假阴性。shape=**测量目标与干预目标错位**。
4. **修法**:压缩为部署前后同题配对批(间隔<25min 控时段),指标对准刀落点(LLM 调用数/token/成本/trace 总时长),TTFVT 只作回滚门;漂移哨兵×10;可证伪声明先写死再跑;过 eval-design 排雷。
5. **验证+教训**:结果成本 -27.7%/尾巴 -33.5%/TTFVT -13.2%,哨兵 +18%<30% 阈无混淆。**可迁移**:被质疑先判真伪,真则重构方案;实验设计第一问="这个指标测的是我改的东西吗"。

## 2026-07-12 能力分支融合审计(回答"你只看 tutorbot?")

1. **现象**:owner 质疑优化只覆盖 tutorbot,deep_question 等分支被忽略。
2. **发现路径**:不用记忆答,派只读测绘 agent 对 main 逐文件取证(capability 注册表→scene 分发→REST 旁路→底座矩阵)。
3. **分析**:orchestrator 真 capability 仅 7 个;mcq/case 判分、轻练出题是 scene **复用** deep_question(已融合,自动吃到全部 turn 底座);五模块是设计性 REST 旁路。"tutorbot.llm.stream" 只是 LLM 命名口径,不代表优化范围。
4. **修法**(产出):旁路×底座矩阵+残余优化点清单(followup flag 白拿项/memory_service 无门控双 LLM/JSONL 双次线性读/repair 全量重发/摸底直连 LLM 无观测),入档 `2026-07-12-capability-branch-fusion-audit.md`。
5. **验证+教训**:全部论断带 file:line,不确定项显式标"未证实"。**可迁移**:回答覆盖面质疑,用当前代码证据测绘,不用战役记忆;修完一个病灶要主动扫"同病兄弟"。

## 2026-07-18 五 tab 加载慢治本(学情快照 SWR 收权)

1. **现象**:owner 报五大模块版小程序每个 tab 进去都慢(3-5s loading)。
2. **发现路径**:三路并行只读审计(learn+history / chat / report+profile)+主控查壳与启动链。两个关键事实:①五 tab 切换是 `custom-tab-bar` 的 `wx.redirectTo`——每次切 tab 走 onLoad 冷启动,不是 onShow;②同一份最重的 `getLearningReport(100)`(后端 3-5s)被 learn/report/profile 三页独立裸拉,而 report-cache 缓存早已存在却只有 report 一个消费者。
3. **分析**:shape = `unconsumed island`(report-cache 孤岛)+ `duplicate decision`(三个独立拉取点)。真病不是"缺 loading 优化",是「最近一次已知快照」这一业务事实没有单一 authority。歧路三条:(a) 初判"onShow 无节流重拉"是主因——错,redirectTo 下 tab 切换走 onLoad,onShow 重拉大多是子页返回(刚发生学习动作,业务上**应该**刷新),不能一刀切节流;(b) learn 页 posters 瘦身——被 agent 按有罪推定核查证伪(stations.js:127 是真实渲染消费者),放弃;(c) **fresh-skip 门(age<60s 跳过网络)被对抗 review 证伪后整体删除**——它会把陈旧/降级/半残快照钉成终态、吞掉其他 tab 上 60s 内完成的学习动作且无后台纠正,外加时钟回拨负年龄永久压制刷新。四条 CONFIRMED 同根,修法不是打四个补丁,是删掉这个决策点:统一为「缓存秒渲染+始终静默刷新」,UX 收益全保留,服务端负载回到 main 现状不劣化。
4. **修法**:①快照组装收权:新建 `utils/report-snapshot.js` 唯一 builder(从 report.js 内联映射逐字提炼,settle 出的空对象源归一化为 null),report/learn 是仅有的两个合法写者,profile 只读(三元组不全禁写);②`report-cache` 收权年龄与写序语义(`readWithMeta` 拒负年龄+`SNAPSHOT_MAX_AGE_MS`30min 唯一阈值+`writeIfFresher` 以发起时刻竞争防孤儿响应 ABA);③统一策略=页面进入缓存秒渲染+始终静默刷新、子页返回照常刷新;④history 归档切换走既有 SWR,apply 前 re-check tab 防串台(review 抓获的最重竞态:在途归档响应盖到"全部"tab);⑤preloadRule wifi→all(蜂窝流量代价已向 owner 标出);⑥删 67K 零引用孤儿 canonical-taxonomy-members.js。中途拦截一次 agent 妥协:report 页曾因只读测试约束保留"逐字等价 fallback builder"(镜像 authority),主控修 dedupe harness 映射真模块后删净。
5. **验证+教训**:第一轮全量 116/116 node 测试 PASS;high 档对抗 review(21 agent,独立 verifier)抓出 6 CONFIRMED+2 PLAUSIBLE,修订后全量重验+DevTools 五页冒烟 PASS(编译/初始化/页面栈,owner 会话无扰)。**可迁移**:①"每页各自慢"成簇出现时先找共享缺失权威,不逐页补 loading;②缓存工具"造好没人用"=unconsumed island,接通已有件优先于新建;③节流类修法必须先分清"哪些重拉是业务正确的"(子页返回≠tab 切换),否则治标变引病;④**自己引入的优化门也要过有罪推定——fresh-skip 四病同根,删门优于补门**;⑤SWR 化会揭开"总是重拉"曾经掩蔽的无守卫异步路径(串台/孤儿写),上缓存必须同时上 apply-time 守卫。

---

## 2026-07-18 随堂练选择题反可猜性全量战役(40 包 633 题)

1. **现象**:owner 发现随堂练单选题"最长选项就是答案,或者答案是 A";此前 Codex 烧了海量 token 也没修好。
2. **发现路径**:先量化——扫 40 个 practice authority:633 题中 78% 正确项严格最长、**100% 存储在第 0 位**、8% 干扰项带口语破绽词;再读 Codex 最后三段会话吸取失败教训(它自判 BLOCKED:机械批改把 B02 题干改坏、40/40 发布校验全灭);再测绘供应链:源 HTML→compile(variant_id=内容哈希)→authority(签名 fail-closed)→公开页,发现渲染层 41/43 已有洗牌(所以截图正确项在 D),真正要治的是存储层数据(后期练习模块复用)。
3. **分析**:Codex 之败有两个根:①用正则机械改语义内容;②不懂 variant_id 是内容哈希——改文本→id 变→fact_id/probe_role/签名全按 id 挂载→整包 fail-closed 熄灯。歧路:曾考虑主控写 JS-数组解析器做机械重排,弃(脆);曾考虑只靠运行时洗牌,弃(存储数据要复用+"最长"缺陷洗牌治不了)。定法:**语义活给 agent(逐包一 agent,契约冻结题干/正确项/解析字段),机械信给断言(快照逐字节比对+扫描器门禁+签名迁移工具)**。
4. **修法**:①`scan_luban_practice_option_defects.py`:与发布器同 compile 路径的缺陷扫描器+确定性目标位分配(surface 内四位均衡);②C01 试点全链跑通后 5 波 fan-out(简单包 Opus/高危包 Fable,断点续做应对限额与流式抖动,增量落盘防丢工);③`migrate_luban_practice_review_packets.py`:签名按 (surface,source_index) 稳定键迁移,机械断言 stem/model/正确项逐字节不变+supply_ready 不降级,pending 保持 pending 机器不代签;④publish 全量重编译+--check;⑤141 签发题异模型对抗核验。
5. **验证+教训**:longest 78%→9%、pos0 100%→25%(160/156/158/159)、口语破绽清零、长度带 100%;不变量 633 题零违反;--check exit 0;pytest 301 绿。**可迁移**:①内容哈希做身份的资产,改内容=换身份,必须先设计身份迁移再动笔;②大规模语义改写的质量结构=逐单元冻结面契约+中央机械断言+对抗核验,三层缺一不可;③agent 大战役必须增量落盘+断点续做,限额/流式抖动是常态不是意外;④"渲染层已修"≠"数据层没病",复用面决定治哪层。

---

## 附：本志与其他沉淀层的分工

| 层 | 载体 | 写什么 | 频率 |
|---|---|---|---|
| **方法志**（本文档） | repo 内，随 commit | 发现→分析→解决叙事，含歧路 | 每个非平凡问题 |
| 结果账本 | implementation-notes.md | 做了什么+验证数字 | 每次落地 |
| 项目记忆 | Claude memory | 可复用 playbook/事实 | 反复出现的模式 |
| 跨项目 skill | ~/.claude/skills | 方法论 | 极少数普适规律 |

---

## 2026-07-21 学习模块偏好埋点 + BI 驾驶舱(功能完整管线丢弃消费粒度)

1. **现象**:owner 要"看学员喜欢学习模块的哪些功能/哪几个教学视频反复看/练习做了多少",同步到 BI 一个一目了然的独立驾驶舱看板,用于判断产品进化方向。
2. **发现路径**:4 专家 panel 并行深读真实代码(数据权威/BI可视化+创始人决策/埋点完整性/一等怀疑者)+指挥官裁决。两次歧路:(a) 初判"学习模块=主包 freeCourse polyv 公开课",owner 纠正"不用接"——真靶=packageDeeptutor 鲁班 learn/luban 学习模块(微课/考点卡/看穿/复测);(b) owner 选了"完播率"信号,专家 C 实证证伪:微课在 web-view 内 H5 播放,station.wxml 无 bindmessage、H5 卡从不 postMessage 进度、微信 web-view 消息非实时——完播率架构拿不到,动画卡更无"完播"语义。
3. **分析**:shape = `producer/consumer granularity mismatch` + `dormant/unregistered dimension`。数据早在管线里——`object_type` 已进聚合 SQL 的 group by(store.py:422)、`visible_ms/duration_ms` 已进表,却在两处被压平:后端 Python fold 只按 module 折叠丢了 object 粒度、前端 producer 把 episode 压成 pack;同时 object_type 用了 14 个值从未收成注册表。90% 是"捞回丢弃的粒度+收权维度+补断头 producer",不是加数据源。专家 A↔D 冲突(逻辑放 service.py 还是新 endpoint)裁决:新切面经薄 bi.py 读 store(不碰受保护的 learner_state 域 service.py),两 caller 读同一 store 函数≠第二 authority。
4. **修法**:①store 单一参数化 `get_engagement_breakdown(group_dim=object_id|object_type|action)` 一函数多切面(非三聚合)+idx_pbe_object;②薄 bi.py `/api/v1/bi/learning-preference`;③catalog object_type 软注册表(Deviation D1:不翻硬400,全产品 fail-closed 迁移 blast radius 超本需求,留 follow-up);④完播率→停留时长(completion_source=dwell,绝不显示假完播%);⑤前端补 4 处断头 producer(全复用 trackProductBehavior,teaching_point_id 取不到退化为<pack>:tp:<episode> 恢复 episode 粒度);⑥BI 独立 tab 复用 bi-cockpit 零新原语,题眼=触达×深度错位(泡沫vs金矿);⑦demo 走 eval 前缀隔离。**独立对抗 review 抓 3 SEV-2**:submodule 无过滤致 login/password 碾压榜首、停留时长与对象脱钩生产恒0、seeder 不忠实=假绿——全修+回归测试。
5. **验证+教训**:81 后端测试绿+tsc/eslint exit0+contract_guard 未触受保护域+demo 端到端(默认排除0行/include_demo后96题64.6%正确率+题眼可见)。**可迁移**:①owner 说"视频/功能"先确认是哪个同名模块(两个"学习"靶),别押;②owner 选的信号也要过可行性证伪(完播率架构拿不到就诚实降级,别硬做);③"加聚合"冲动先查数据是否已在管线里(object_type 早在 group by,是消费粒度丢了不是缺数据);④自己写的特性必过独立对抗 review——旗舰面板"漏一个 module 过滤"就把 login 排到"学习子模块"榜首,自审最易漏这种"看着跑得通其实测错东西"。
