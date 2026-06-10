# 鲁班智考拍照识题 OCR 输入层实施计划

- 日期：2026-06-10
- 状态：`Implemented locally (M1+M2 code) / M0 blocked-on-user`（2026-06-10：服务端 photo_answer 包 + REST 六端点 + 小程序 capture/confirm 子包已实现并 81 测全绿、contract guards PASS、feature flag 默认 off；M0 实测需用户开通四家 API key + 组织三分法样本；provenance schema contract 评审与小程序真机回归待办——见 §14 实施落地记录）
- 类型：Implementation Plan
- 上游调研：用户提供的两份外部深度调研（拍照识字功能深度调研与落地方案 / 手写试卷识别路线深度研究），已于 2026-06-10 逐条核实厂商现行能力与定价（核实记录见本文 §3）
- 关联主线：鲁班评分引擎总控（master plan §0.26）、学习事实编译 / Evidence-first Memory、微信小程序、官方 provider 账单对账（2026-06-03）、钱包/会员 authority（产品定价归属）

---

## 0.0 修订记录

- **v3.2（2026-06-10，Codex 终审（清晰度/可执行性镜头）12 项小修全采纳，终审裁决"需小修"→已修）**：
  - G1 [A] §11 retention 时点与 Task 0a 矛盾 → 统一为 M1 上线前生效、M3 运营化复盘。
  - G2 [A] §1 成本承诺与 §3.4 换防分支矛盾 → §1 显式声明承诺以锁定百度 L0 为前提。
  - G3 [B] 题干折叠语义钉死：默认不计入 confirmed_text、折叠展示、一键恢复、绝不物理删除。
  - G4 [B] `/retry` 补预算/硬顶通道/job_version 规则；G5 [B] 存储拍板为 M1 Task 0b（默认 SQLite 提案）。
  - G6 [C] M0 阈值预注册补"采样后跑数前由用户确认冻结"；G7 [C] P50 ≤5s 补完整测量口径；G8 [C] M0 前置 annotation guideline（数字 token/结构单位/TP-FP-FN 口径）。
  - G9 [D] Task 0a 补 photo-answer 专属授权与图片 URL 策略；G10 [E] 转录真值双录/仲裁协议；G11 [E] 测试 key 完成定义与责任人；G12 [E] M1 QA fixture 固定（baseURL/账号/样题/flag/入口）。
- **v3.1（2026-06-10，终审一致性收口——全文重读修复 v1 残留与 v3 修正的互相矛盾）**：
  - F1 §0 一句话定位"硬顶 0.1 元"改为与 §3.3 一致的"软顶 0.1 / 硬顶 0.3"双顶表述。
  - F2 §3.4 删除"200 张真实学员试卷照片"残留（与 §9"真实样本不存在"矛盾），改引 §9 三分法冒烟集。
  - F3 §3.4 达标判据从单一"人均修改 ≤8 字"改为 **§9 质量门指标①③④⑥ + 阈值预注册**（跑数前写进 M0 FINDING，先定靶再射箭）；M2 验收同步对齐。
  - F4 §5 worker 流程图两处 v1 残留修正：词典行（曾写 rubric required_terms，违反 C8）、L2 行（补双通道引用）。
  - F5 §8 代码落点补 `cost_ledger.py`、`jobs.py` 两个模块行，routing.py 职责改"先 reserve 再调用"；reconcile.py 职责对齐行级风险评分设计。
  - F6 §7 补两条交互边界：session 的 question_id 不可变（换题=新 session）、iOS HEIC 服务端转码；§6 confirmations 补 job_version + ack_flags_json。
  - F7 M0 工期 2–3 天改为诚实的 3–5 天（样本组织是工期主项）；M0 验证清单补百炼 qwen-vl-ocr RPM/TPM 限额。
- **v3（2026-06-10，Codex 对抗审查后吸收，20 findings / 9×P1 全部裁决，见 §13）**：
  - C1 预算闸重做：单位从 cents 改 **micros（微元）**；成本账本升级为 `reserve → provider_call → settle/refund` 状态机；**一切付费动作**（L0/L1/L2/重试/内容检测）走同一 reservation；加 user/day 级限额防刷（§3.3）。
  - C2 qwen-vl-ocr 页价降级为"待实证估算"，M0 新增**账单回放**任务用 provider usage 明细反推真实每页计费公式（§3.2、§10 M0）。
  - C3 OCR job 从纯 BackgroundTasks 升级为 **durable job rows + 幂等键 + 启动恢复扫描**（执行器仍可用 BackgroundTasks，状态在盘上）（§5、§10 M1）。
  - C4 新增 M1 前置任务：定义 photo OCR provenance 在 grading writeback / `learning_evidence` payload 的 **canonical schema**——`image_refs/suspicion_spans/is_possible_ocr_error` 此前没有接缝，违反 learner-state contract 的"router 不得自建 writer"纪律（§4、§10 M1）。
  - C5 题干剔除默认从"勾选剔除"改为**折叠保留**——学生复述题干条件作答是常态，文本相似度默认删除会误删有效答案（§5）。
  - C6 reconcile 降级为**行级风险评分**：只有能稳定锚回 L0 字符 box 的差异才进确认页 span，L1 无坐标的生成式输出不做字符级硬对齐（§5）。
  - C7 图形区域诚实化：现有批改内核是文本匹配，**不会消费图片**——图形内容明示"暂不计入自动批改"，删除"原图参与批改"的暗示（§5）。
  - C8 词典建议收紧为**仅形近字 OCR 字形错误**，禁止展示 rubric 采分点术语级建议——否则确认页变成答案润色器，批改公平性崩塌（§5）。
  - C9 confirm 分级拦截：普通疑点不拦截；**关键疑点**（数字/金额/工期类未确认、疑点密度超阈、页质检差）fail-closed 降级为 provisional 批改 + 不写长期学习证据（§7）。
  - C10 M0 样本协议改三分法（誊抄 1/3 + 限时自由作答 1/3 + 征集真实 1/3）；验收指标弃用"编辑字数"单一指标，加盲转录 CER、**未高亮错误漏检率**、确认后批改分差（§9）。
  - C11 API 全端点加 ownership 校验（user+session+question+job_version）与状态机约束；新增"疑似拍错题"stem-mismatch 分支；数据模型补 provider 审计字段（model_version/preprocess_version/request_hash/provider_usage_id/billing_reconciliation_id）（§6、§7、§11）。
  - C12 隐私前置：EXIF 清理、retention policy、provider 数据使用条款核查从 M3 提前到 **M1 上线前**（§11）。
- **v2（2026-06-10，全场景深挖 + 自我对抗后强化）**：
  - R1 修复 v1 预算闸与 L2 的数学矛盾（起步档阿里 0.225 元/页 > 0.1 元软顶 ⇒ 自动 L2 在起步期永不可达）：预算闸改为软顶/硬顶双层，L2 起步期只保留"用户主动重识别"通道（§3.3）。
  - R2 新增题干自动剔除：用户必然拍进印刷题干，用题库 `question_stem` 文本对齐零成本标记"疑似题干"段落（§5）。
  - R3 诚实化 M0 样本来源：真实纸面样本当前不存在，首轮用半合成（真实学员答案文本 × 多人手抄），上线后 30 天真实数据强制重跑（§9）。
  - R4 reconcile 跨引擎对齐列为显式工程风险，M2 验收新增伪分歧率指标（§5、§10）。
  - R5 新增微信小程序图片内容安全合规验证项、厂商调价对账（接 official provider billing reconciliation 主线）、手写内容指令注入三项风险（§11）。
  - R6 新增多子问判分接缝注记（§5）、疑点未处理二次确认（§7）、总变动成本与定价归属声明（§1）、M0 验证清单扩充（百度 QPS、印刷混排、L0/L1 转写范围一致性）（§10）。
- v1（2026-06-10）：初版。

## 0. 一句话定位

把"纸上手写的案例题答案"变成现有批改链路可消费的高质量 `confirmed_text`，**单题 OCR 成本：自动路由软顶 0.1 元、含用户主动重识别硬顶 0.3 元（代码层强制，见 §3.3）**，不新建任何第二套批改/记忆/入口 authority。

拍照识题不是 OCR 工具，是**纸面答案进入 AI 学习闭环的入口层**。本计划的所有取舍都服从三个排序后的目标：成本控制 > 体验性能 > 识别能力上限（能力不足用"确认页 + 双引擎分歧信号"兜，成本超标没有兜法）。

## 1. 目标

1. 学员在小程序案例题详情页内：选题 → 扫描式连拍 1–3 页手写答案 → 确认页轻修 → 提交批改，全程不离开小程序。
2. 单题 OCR 直接成本软顶 **0.1 元（自动路由预算闸强制）**，典型 0.03–0.07 元；从拍完到确认页可见 P50 ≤ 5 秒。**此承诺以 M0 锁定百度为 L0 为前提**——若触发 §3.4 换防（L0 升阿里），计划暂停、回用户重批预算，0.1 元承诺随之失效，不存在"静默涨成本继续干"的路径。
   - 总账声明：OCR（≤0.1）+ 既有批改 LLM（≈0.2）⇒ 拍照批改单题总变动成本 ≈ 0.25–0.3 元。**对用户怎么收费/扣点不归本计划**，归钱包/会员 authority 主线（Supabase wallet PRD）决策；本计划只承诺把 OCR 这一段钉死在预算内并把成本数据如实上报对账。
3. OCR 错误与学生真实错误**制度性分离**：原图、原始 OCR、确认稿、修订差异、低置信定位五件套全量落盘，杜绝 OCR 误识别污染 `learning_evidence`。
4. 从第一天起沉淀可训练数据资产（用户修订对、误识别标注），为远期 PaddleOCR 私有化迁移留弹药。

## 2. 非目标（红线）

- **不做**整卷自动分题（题号先行，单题为批改单元，与现有按题批改结构对齐）。
- **不做**识别后无确认直接批改（OCR 错误会被用户理解为"你批错了"，直接摧毁批改可信度）。
- **不用**通用多模态大模型（GPT/Gemini/通用 Qwen-VL）当主 OCR——生成式"悄悄改对"对采分点判分是灾难；文档专项 VLM（qwen-vl-ocr）只做交叉校验器，**永不作为权威文本源**。
- **不改** `CaseGradingSkillKernel` / `rubric_grader_v1` 任何一行——批改内核吃 `user_answer: str`，OCR 层是纯上游。
- **不新增** WebSocket 路由——`/api/v1/ws` 是唯一流式入口，OCR 任务状态走 REST 轮询。
- **现阶段不自部署** PaddleOCR——月识别量 < 5 万页时 GPU（约 1500–3500 元/月）+ 运维比 API 更贵；迁移触发条件见 §10 M4。
- **不让** OCR 层写 `learning_evidence` / learner memory / canonical 任何东西。

## 3. 引擎选型与成本模型（已核实，2026-06-10 现行牌价）

### 3.1 计费单位澄清

图片 OCR API 一律 **1 次调用 = 1 张图片 = 1 页**，"按次"与"按页"是同一件事；只有 PDF 文档解析类才另行按页拆分。**单题成本 = 页数 × 每页成本之和**，按平均 2 页/题做预算（实测后校准）。

### 3.2 核实后的价格事实（计算依据，不得凭记忆改写）

| 引擎 | 单价（现行牌价） | 关键能力 | 形态 |
| --- | --- | --- | --- |
| 百度手写文字识别（标准版） | 后付费 0.01 元/次起（月 30 万+ 降至 0.0045）；次数包 10 万次 740 元 ≈ 0.0074 元/次 | `recognize_granularity=small` 单字+候选字+置信度；`detect_alteration` 涂改检测；行/字坐标；**无段落语义** | 同步 ~1s |
| qwen-vl-ocr（百炼） | 输入 0.3 元/百万 token + 输出 0.5 元/百万 ≈ **0.002–0.005 元/页（公式推算，待 M0 账单回放实证**——真实成本含 prompt/重试/输出长度，M0 用 provider usage 明细反推每页计费公式后才可入成本模型） | 文档/试题/手写专项 VLM，认字强；**无词级坐标/置信度，生成式** | 同步秒级 |
| 阿里云 RecognizeHandwriting | 月≤1万 0.225 → 1–10万 0.09 → 10–50万 0.054 → 100万+ 0.036 元/次 | 段落输出+单字 prob+表格+自动旋转，QPS 10 | 同步 ~1s |
| 腾讯 HandwritingEssayOCR | 0.24 元/次（资源包折合 0.36→0.06）；免费 1000 次/月 | 教育专项、阅读顺序、词/行/段/标题坐标 | 同步，QPS 5 |
| 百度手写作文识别（多模态） | **未公开定价**，需商务询价 | 能力最对口（多页/分栏/标题坐标/抗涂抹） | 异步 5–10s，提交 QPS 仅 2 |
| 百度文档解析（PaddleOCR-VL 官方 API） | 0.18 元/页牌价（限时促销 0.09） | 版面解析强 | 异步，QPS 2，**比阿里量产价贵 5 倍，排除** |

### 3.3 三级成本路由（本计划的主选型）

预算约束下，主引擎从外部调研推荐的阿里（起步档 0.225 元/页 → 2 页就吃光 0.45 元，超预算 4.5 倍）改为**百度标准手写**，版面智能的缺口用规则 + 交叉校验补：

| 层 | 引擎 | 触发 | 每页成本 | 职责 |
| --- | --- | --- | --- | --- |
| **L0 主识别** | 百度手写文字识别（`small` 粒度 + `detect_alteration` + 置信度） | 所有页 | 0.0074–0.01 元 | 权威 raw_ocr_text、单字置信度、候选字、涂改标记、行/字坐标 |
| **L1 交叉校验** | qwen-vl-ocr | 所有页 | 0.002–0.005 元 | 独立第二份转写；与 L0 对齐 diff，**分歧片段 = 疑点高亮**（比单引擎置信度更准的错误信号）；只产生 suspicion span，绝不覆盖 L0 文本 |
| **L2 疑难升级** | 阿里 RecognizeHandwriting | 见下方双通道规则 | 0.054–0.225 元 | 复杂页重识别（段落+表格） |

**预算闸（硬机制，非约定，软/硬双顶）**——v2 修正了 v1 的数学矛盾：起步档阿里 0.225 元/页本身就超过 0.1 元软顶，"自动路由 + 单一预算"会让 L2 在起步期永不可达、形同虚设。修正后的规则：

- **软顶 0.10 元/题**：自动路由预算。L0+L1 全页 + （仅当阿里已进入 1–10 万档及以上、单页 ≤0.09 元时）信号触发的自动 L2。每次引擎调用前先扣减预估成本，余额不足直接跳过，降级为"疑点全部交确认页人工"。
- **硬顶 0.30 元/题**：唯一允许突破软顶的通道是**用户在确认页主动点"识别效果差，重新识别"**——每 session 限 1 次，触发 L2 阿里重识别。把最贵的引擎只花在用户明确表达不满的地方，成本可控且感知价值最大。
- 诚实结论：**起步期（阿里 0.225 档）不存在自动 L2**，L2 只有用户主动通道；阿里量产进档后自动 L2 才按信号（页质检差 / L0×L1 分歧率超阈 / 检出表格）生效。
- 兜底：双顶都由 session 级 `cost_ledger` 在代码层强制，超顶在代码上不可能发生；BI 成本看板只做事后观测复核。
- **cost_ledger 实现规格（v3，Codex C1）**：① 单位用 **micros（微元，1 元 = 1,000,000）**——cents 表达不了 0.0074 元/页；② 记账走 `reserve → provider_call → settle/refund` 三态：调用前预留预估额，成功按实结算，失败/超时退还预留，杜绝并发竞态下双扣或漏扣；③ **一切付费动作**（L0/L1/L2/页重试/内容安全检测）共用同一 reservation 通道，不存在"预算外"调用路径；④ 叠加 user/day 级限额（默认每用户每日 N 个 session，运营可调）防恶意刷量；⑤ 每笔 settle 记录 provider_usage_id，对接账单对账主线。

**单题成本账（2 页）**：

- 纯 L0+L1（预期 ≥85% 的题）：2×0.01 + 2×0.004 ≈ **0.03 元**
- 用户主动重识别（起步档最坏）：0.03 + 2×0.225 = 0.48 元，**受硬顶 0.3 约束 ⇒ 起步期主动重识别只重识别单页**（0.03+0.225=0.255 ≤ 0.3），UI 让用户选最差的那页
- 量产（百度次数包 + 阿里 10 万+档自动 L2 触发率 ≤10%）：2×0.0074 + 2×0.004 + 0.1×2×0.054 ≈ **0.034 元**

### 3.4 M0 实测换防条款

"百度标准手写认字够不够准"是本计划唯一未被公开资料回答的问题（没有任何公开评测直接测过中文手写试卷答案）。M0 用 200 张三分法冒烟集（构建协议见 §9——真实纸面样本当前不存在，不得宣称"真实学员试卷"）实测裁决，免费额度内成本≈0：

- **达标判据预注册（v3.1）**：以 §9 核心指标①盲转录 CER、③未高亮错误漏检率、④关键数字错误率、⑥确认后批改分差为质量门，**具体阈值必须在采样完成、跑引擎之前写进 M0 FINDING 的 pre-registration 段，由用户（交付负责人）确认冻结**（先定靶再射箭，禁止看完结果再画线）；"确认页人均修改 ≤8 字/题"仅作体验参考。达标 → 锁定 L0=百度，本成本模型生效；
- **不达标且阿里达标** → L0 升级为阿里，单题成本变为 ≈0.19 元（起步档 0.46 元），**超出 0.1 预算——此时必须回到用户重新批预算或重谈产品定价，不得静默超支**；
- **百度作文多模态实测断档领先** → 仅作为 L2 疑难引擎候选去谈商务价，QPS=2 + 异步决定它做不了主引擎。

## 4. 单一 Authority 声明

| 事实 | 唯一 authority | 本计划的纪律 |
| --- | --- | --- |
| 送批改的答案文本 | `confirmed_text`（用户确认稿） | 批改只读 confirmed_text；raw_ocr_text 仅作证据附件 |
| 批改结论 | `CaseGradingSkillKernel` / 既有评分链路 | OCR 层零侵入，不传"OCR 觉得学生想写什么" |
| 文本修改权 | 用户本人 | 词典/引擎只能"建议+高亮"，**自动替换在任何层都禁止** |
| 学习事实 | `learning_evidence` 既有链路 | OCR 层不直接写；**v3 修正（Codex C4）：`input_mode=photo_ocr` / `is_possible_ocr_error` / `image_refs` / `suspicion_spans` 当前在 grading writeback payload 里没有接缝**——learner-state contract 禁止 router 自建长期 writer，所以 M1 第一项任务是在既有 `learning_evidence` payload builder 中定义 photo OCR provenance 的 canonical schema（小而显式的字段扩展，走 contract 评审），schema 落定前 photo 路径的批改结果只准 preview，不准写长期证据 |
| 流式入口 | `/api/v1/ws` | OCR 不碰；任务状态 REST 轮询 |
| 图片资产 | `get_attachment_store()`（`mobile.py` 已用） | 复用，不新建第二套对象存储 |

## 5. 架构与数据流

```
小程序拍照页（扫描框/连拍/压缩/模糊反光提示）
  → POST 上传原图（复用 attachment store）
  → POST submit 创建 ocr_job（v3：**durable job row + 幂等键**先落盘，执行器用 FastAPI BackgroundTasks，
     启动时恢复扫描未完成 job——付费任务不允许只活在内存里；量级未到 Redis 队列）
      worker: 质检评分 → 透视矫正/增强 → L0 百度 → L1 qwen-vl-ocr 交叉
              → 对齐 diff 产 suspicion_spans → 规则段落/分点重建
              → 词典建议（taxonomy 形近字提示 only，禁 rubric 术语——见 §8 lexicon 行）
              → [双通道规则见 §3.3：量产档信号自动触发 / 用户主动重识别] L2 阿里重识别
  → 小程序轮询 GET job 状态 → 确认页（原图联动 + 仅疑点高亮 + 候选字快捷替换）
  → POST confirm（confirmed_text + diff）
  → 既有批改链路（confirmed_text 为主输入，原图引用与 suspicion_spans 作证据附件）
  → 五件套落盘：原图 / raw_ocr / confirmed / diff / 置信度+疑点
```

设计要点：

- **题干折叠（v2 新增，v3 按 Codex C5 收敛，v3.2 语义钉死）**：真实用户必然把印刷题干连同手写答案一起拍进来。session 已绑定 question_id ⇒ 我们持有 `question_stem` 原文，对 OCR 段落做文本相似度对齐，相似度超阈的段落标记"疑似题干"。精确规则：**疑似题干段落默认不计入 confirmed_text，但在确认页以折叠卡片展示全文，用户点一下即可整段恢复进 confirmed_text**；任何文本都不被物理删除（raw_ocr_text 永远完整）。学生复述题干条件、指出题干做法"不妥"是高分作答的常态——所以恢复入口必须显眼，且折叠卡片标题写明"已自动识别为题干，未计入作答，点击恢复"。
- **图文分流（v3 按 Codex C7 诚实化）**：表格/网络计划/横道图/简图区域不强行文本化，标记为"图形证据区域"并保留原图。**现有批改内核是文本采分点匹配，不消费图片**——所以确认页和报告必须明示"图形内容暂不计入自动批改"，原图仅用于人工复核与未来能力预留，不暗示模型会看图判分。
- **段落重建走规则不走贵引擎**：单题答案版面简单（题号已绑定），用行坐标 + 分点编号正则（`1）/①/（一）/1.`）+ 行距缩进合并即可，独立小模块可单测。
- **reconcile 是本计划最大的工程风险点（v2 显式化，v3 按 Codex C6 降级设计）**：L0（带坐标的行序文本）× L1（生成式整段文本）做字符级硬对齐不可行——L1 无坐标且会改写/合并/补全。v3 设计收敛为**行级风险评分**：L1 文本按归一化（去空白/全半角/同形字折叠）后与 L0 各行做模糊匹配，匹配差的行整行标"风险行"；**只有能稳定锚回 L0 字符 box 的差异才升级为字符级 span 进确认页**，锚不回去的只做行级高亮。span 的坐标 authority 永远是 L0。M0 即对该模块做真实样本验证，M2 验收设伪分歧率指标。前提一致性：**L0 与 L1 必须吃同一张预处理后的图**，题干折叠在 reconcile 之后做。
- **多子问接缝（v2 注记）**：一建案例题常含 4–5 个小问，批改链路是逐子问判分但可吃整题全文（`run_luban_ab_test_from_bank.py` 现行范式：同一份完整作答逐子问送判）。因此 confirmed_text 不强制用户按子问切分，只需分点结构保持完好；确认页按编号预切分段即可。
- **fail-closed**：任一引擎失败 → 切换重试 → 仍失败则降级为"手动录入 + 原图辅助批改"，不让用户死路一条。

## 6. 数据模型（五件套，新增独立存储，不挤现有表）

`photo_answer_sessions`：id, user_id, question_id, status（显式状态机：created→pages_uploaded→processing→awaiting_confirm→confirmed→submitted / failed）, page_count, cost_spent_micros, cost_reserved_micros, cost_budget_micros, daily_quota_key, created_at
`photo_answer_jobs`（v3 durable job，Codex C3）：id, session_id, idempotency_key, status, lease_until, attempt_count, created_at, finished_at
`photo_answer_pages`：id, session_id, page_index, image_ref, content_hash（重复页检测）, quality_score, blur/glare 标记
`photo_answer_ocr_results`：id, job_id, page_index, engine, **engine_model_version, preprocess_version, request_hash, provider_usage_id, billing_reconciliation_ref**（v3 审计字段，Codex C11/C19）, raw_text, line_boxes_json, char_confidences_json, alteration_marks_json, cost_micros
`photo_answer_suspicions`：id, session_id, span（页/行/字偏移）, source（low_conf/engine_diff/lexicon）, suggestion, resolved_by_user
`photo_answer_confirmations`：id, session_id, job_version, confirmed_text, diff_json, edited_char_count, ack_flags_json（needs_review_ack / critical_failclosed 等拦截行为记录）, confirmed_at
`photo_answer_error_feedback`：id, session_id, span_id, gold_text, reported_by（误识别标注闭环，M3）

持久化形态：**默认提案 = 单一 SQLite 文件 `photo_answer.db`（项目现行轻存储模式），不引入新基础设施**；最终拍板列入 M1 Task 0b（与 provenance schema 同批决策），定了就写 migration，不在实现中途漂移。

## 7. API 设计（REST，鉴权与 `mobile.py` 现行 `_resolve_authenticated_user_id` 一致）

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/v1/photo-answer/sessions` | POST | 创建拍题会话（绑定 question_id；**question_id 不可变，换题=新 session**，避免半程换绑导致题干折叠/批改错位） |
| `/api/v1/photo-answer/sessions/{id}/pages` | POST | 上传单页（multipart，复用 attachment store；限制大小/格式，**iOS HEIC 服务端转码为 JPEG 后再入预处理**） |
| `/api/v1/photo-answer/sessions/{id}/submit` | POST | 触发 OCR 任务 |
| `/api/v1/photo-answer/sessions/{id}` | GET | 轮询状态 + 结果摘要（文本/疑点/候选字） |
| `/api/v1/photo-answer/sessions/{id}/confirm` | POST | 提交确认稿 + diff → 返回可送批改的 answer payload。**v3 分级拦截（Codex C9）**：普通疑点未处理 → `needs_review_ack` 二次确认，用户坚持可提交（ack 落盘归因）；**关键疑点**（数字/金额/工期类未确认、疑点密度超阈、页质检差）→ fail-closed：批改结果降级为 `provisional`，**不写长期学习证据**——"不硬拦截"与"OCR 错误不得污染学情"的矛盾以学情优先解决 |
| `/api/v1/photo-answer/sessions/{id}/retry` | POST | 失败页重试（可换引擎）。**retry 是付费动作**：必须先过 cost_ledger.reserve；系统失败重试走软顶预算，用户主动 L2 重识别计入每 session 1 次的硬顶通道；每次 retry 生成新 job_version，旧 version 的 confirm 被 409 拒绝 |

**全端点 ownership 与状态机约束（v3，Codex C13）**：每个端点校验 `user_id`（鉴权）+ session 归属 + question 可访问性 + `job_version`（防 confirm 旧版本结果）；非法状态转移（如对 processing 中的 session confirm）显式 409 拒绝；submit 幂等（同 idempotency_key 重复提交返回同一 job）。

确认后的提交走**现有**答案提交/批改入口，答案对象多带 `input_mode=photo_ocr`、`photo_session_id`、`image_refs`、`suspicion_spans`——这些字段在批改 writeback 中的 canonical schema 是 M1 第一项任务（§4）。

## 8. 代码落点

| 模块 | 文件 | 职责 |
| --- | --- | --- |
| 引擎客户端 | `deeptutor/services/photo_answer/engines/{baidu_handwriting,qwen_vl_ocr,aliyun_handwriting}.py` | 各自薄客户端；密钥走环境变量，启动校验，缺 key fail-closed |
| 成本账本 | `deeptutor/services/photo_answer/cost_ledger.py` | micros 单位、reserve→settle/refund 状态机、软/硬双顶、user/day 限额（§3.3 规格的唯一实现处） |
| 成本路由 | `deeptutor/services/photo_answer/routing.py` | L0/L1/L2 双通道路由决策；一切付费调用先过 cost_ledger.reserve |
| durable job | `deeptutor/services/photo_answer/jobs.py` | job rows、idempotency_key、lease、启动恢复扫描 |
| 交叉对齐 | `deeptutor/services/photo_answer/reconcile.py` | L0×L1 行级风险评分、可锚回 L0 box 的差异升级为字符 span |
| 段落重建 | `deeptutor/services/photo_answer/paragraphs.py` | 行坐标 → 段落/分点结构 |
| 词典建议 | `deeptutor/services/photo_answer/lexicon.py` | 从 canonical taxonomy（FINAL_CLEANED_TAXONOMY2026 keywords）构建领域词表；**v3 按 Codex C8 收紧：只标"疑似 OCR 形近字错误"（候选字与词表项字形距离近才提示），禁止展示 rubric `required_terms` 级术语建议**——否则确认页变成采分点润色器，学生没写对的术语被系统喂出来，批改公平性崩塌 |
| 编排 | `deeptutor/services/photo_answer/service.py` | 质检→识别→交叉→后处理→落盘 |
| 路由 | `deeptutor/api/routers/photo_answer.py` | §7 六个端点 |
| 小程序 | `wx_miniprogram/pages/photo-answer/`（拍摄+处理中）、`wx_miniprogram/pages/ocr-confirm/`、`utils/api.js` 增量 | 入口放案例题详情页"拍照作答"按钮 |
| 评测 | `scripts/run_photo_ocr_engine_bakeoff.py` | M0 多引擎对比 + M3 回归 |
| 测试 | `tests/services/photo_answer/`、`tests/api/test_photo_answer_router.py` | 见 §10 各阶段验收 |

Feature flag：`DEEPTUTOR_PHOTO_ANSWER_ENABLED`（默认 off），秒级回滚 = 翻 flag，无数据迁移负担。

## 9. 评测设计（双层：识别本身 + 对批改的影响）

- **冒烟集（M0，v2 诚实化）**：拍照功能尚未上线，**当前不存在 200 张真实学员纸面样本**——这是 v1 的隐藏假设错误。修正方案：
  - 首轮 200 张采用**三分法**（v3 按 Codex C10 强化，纯誊抄会系统性美化结果）：1/3 誊抄（真实学员答案文本 × ≥10 位书写者手抄）+ 1/3 **限时自由作答**（给题目让人真实限时作答，产生跳写/插入/涂改/划改的自然分布）+ 1/3 尽力征集真实用户纸面作答（运营渠道，收不满则前两类补足并如实记录配比）。阈值按严：确认页人均修改 ≤8 字在该集合上要求 ≤6 字。
  - 切片必须覆盖：含印刷题干的整页 / 纯答案区 / 横线笔记本 / 计算数字密集（工期/金额——数字错一个就翻判，疑点权重上调）/ 涂改箭头 / 弱光歪斜（≥25% 脏图）。
  - **上线后 30 天强制用真实用户图片重跑 M0 回归**；§3.4 换防条款在真实数据回归前保持有效，主引擎裁决标记为 `provisional`。
- **核心指标**（v3 按 Codex C10 修正：编辑字数是坏的单一北极星——用户没发现的漏字/整行丢失/数字错读不会体现在编辑量里）：① 盲转录字符错误率 CER（对人工真值）；② 分点结构保持率；③ **未高亮错误漏检率**（确认页没标红但实际错的字符占比——这是"用户只改疑点"假设的直接检验）；④ **关键数字错误率**（工期/金额/规范编号单列）；⑤ 疑点召回率；⑥ **确认后批改分差**（OCR 确认稿批改分 vs 人工转录批改分，分差 ≤1 分占比）；⑦ 确认页人均修改字符数与放弃率（产品体验指标，非质量指标）；⑧ 单题实际成本（账单回放核对）；⑨ 拍照→确认页耗时。
- **A/B（M3）**：A=纯 L0+确认页；B=L0+L1 交叉高亮；C=L0+L1+L2 路由。主看确认页编辑量、放弃率、批改一致率、单题成本——直接回答"L1/L2 是真增益还是账单变大"。

## 10. 实施阶段

### M0 引擎实测选型（3–5 天，免费额度内，先于一切编码承诺；样本组织——约 10 位书写者誊抄 + 限时作答 + 征集——是工期主项，引擎跑数只占 1 天）

1. 申请百度/阿里/腾讯/百炼测试 key——**完成定义**：四家 key 可调用、quota 确认、usage 明细导出路径（控制台或 API）跑通、责任人明确（默认：用户本人开通账号，工程侧验证调通）。收集并人工转录 200 张冒烟集——**最小标注协议**：关键切片（数字密集/潦草）双人转录、冲突由评分负责人仲裁，其余单录+10% 抽检；跑引擎前先冻结一份 annotation guideline（定义数字 token、结构单位、疑点 TP/FP/FN 口径），否则 CER/召回率口径会因人而异。
2. `scripts/run_photo_ocr_engine_bakeoff.py` 跑四引擎，产出 FINDING artifact（写入 `artifacts/`，仓库主目录而非临时 worktree）。
3. 按 §3.4 换防条款裁决 L0；裁决结果回写本计划 §3.4 并更新状态。

3a. M0 同时核销以下**验证清单**（v2 新增，均为公开资料查不到、必须实测的事实）：
   - 百度标准手写**实际 QPS 配额**（仅作文多模态的 QPS=2 已核实，标准版未核实）；百炼 qwen-vl-ocr 的 **RPM/TPM 限额**（决定 L1 全页并行的可行并发）；
   - 百度手写接口对**印刷题干+手写答案混排整页**的行为（题干识别质量影响题干剔除策略）；
   - qwen-vl-ocr 对整页的**转写范围**是否与 L0 一致（决定 reconcile 前是否需要统一裁剪）；
   - reconcile 原型在冒烟集上的**伪分歧率**（目标 < 分歧总数的 30%，超出则对齐算法回炉）；
   - **qwen-vl-ocr 账单回放**（v3，Codex C2）：用真实压缩参数跑 ≥50 页，取 provider usage 明细反推每页计费公式（prompt+重试+输出全计入），替换 §3.2 的推算值。

**验收**：FINDING 报告含四引擎 CER/结构保持率/成本/时延对照 + 验证清单核销 + 明确 L0 裁决（标记 `provisional` 直至真实数据回归）；若触发"预算重谈"分支，停止后续阶段直至用户决策。

### M1 最小纵切（1 周）：单题单页全链路

0. **（前置，v3 Codex C4）photo OCR provenance schema**：在既有 grading writeback / `learning_evidence` payload builder 中定义 `input_mode/photo_session_id/image_refs/suspicion_spans/is_possible_ocr_error` 的 canonical 字段，走 contract 评审；schema 落定前 photo 路径批改只准 preview。
0a. **（前置，v3 Codex C12，v3.2 扩充）隐私与资产边界基线**：上传即剥离 EXIF（含 GPS）；明确**最小 retention/deletion policy 与删除入口（M1 上线前生效，M3 只做运营化复盘）**；定义 photo-answer 专属的附件授权规则与图片访问 URL 策略（签名/过期，不复用 feedback session 的授权语义）；核查百度/阿里/百炼三家"API 输入数据是否用于训练"条款并留档。
0b. **（前置，v3.2）存储拍板**：确认 §6 默认提案（单一 SQLite `photo_answer.db`）或替代，写 migration，与 0 的 provenance schema 同批评审。
1. engines/baidu + 上传/submit/轮询/confirm 四端点 + 最简确认页（全文可见、低置信高亮）；**durable job rows + idempotency_key + 启动恢复扫描**（v3 Codex C3）。
2. confirmed_text 走现有批改入口；五件套落盘；feature flag 包裹；cost_ledger（micros + reserve/settle/refund）随 M1 落地，不延后。
3. 测试：引擎客户端（mock HTTP）、cost_ledger 状态机单测（并发预留/失败退款/幂等重放）、router ownership 校验测试、确认稿→批改 e2e（hermetic）。

**验收**：test2 上 qa_ 账号真机完成"拍 1 页→确认→批改报告"——**QA fixture 固定**：test2 baseURL + qa_ 测试账号 + 题库指定样题（case 题型，含已编译 rubric）+ `DEEPTUTOR_PHOTO_ANSWER_ENABLED` 开启方式 + 案例题详情页入口路径，写进验收脚本/手册，不靠口口相传；五件套可回查；进程重启后未完成 job 可恢复且不双扣；flag off 时零影响。

### M2 完整体验（2 周）：多页 + 交叉 + 路由

1. 连拍多页、页序调整、质检即时提示（太暗/太糊/反光建议重拍）。
2. L1 qwen-vl-ocr 交叉 + reconcile 行级风险评分高亮；题干折叠（默认保留，剔除需用户确认）；软/硬双顶 cost_ledger 全规格生效；段落重建；词典形近字提示（禁 rubric 术语）；失败重试/换引擎/手动兜底。
3. 确认页升级：原图局部裁片联动、候选字一键替换、疑点导航、**"识别效果差，重新识别"主动升级按钮（每 session 限 1 次，起步期限单页）**、未处理疑点二次确认。

**验收**：冒烟集回归过 M0 预注册质量门（§9 指标①③④⑥，阈值以 M0 FINDING pre-registration 段为准）；体验参考人均修改 ≤8 字/题（三分法集 ≤6 字）；伪分歧率 < 30%；自动路由成本 P95 ≤0.1 元、含主动重识别 ≤0.3 元（cost_ledger 日志证明）；拍→确认页 P50 ≤5s——**测量口径（v3.2）**：test2 环境、qa_ 账号、2 页 session、Wi-Fi，从服务端收到 submit 到 GET 首次返回 `awaiting_confirm`（或含 partial result 的首个可交互状态）的服务端耗时，L1 超时降级的样本单独统计不剔除；contract_guard PASS（若触及 protected 文件，新测试登记进 `contracts/index.yaml` domain test_files）。

### M3 数据闭环与 A/B（1 个月内）

1. 误识别反馈标注、修订对沉淀；成本/质量指标接 BI 观测（复用 surface-telemetry 模式，不另起 SDK）。
2. §9 A/B 跑通并出结论；复盘页"原图/OCR/确认稿/批改结果"联动卡片。

**验收**：A/B FINDING 报告 + L1/L2 净收益裁决；误识别反馈数据开始累积。

### M4 私有化迁移门（不排期，仅定触发条件）

触发任一即**评估**（不是自动启动）PaddleOCR/PP-OCRv5 自部署或自研纠错器：① 月识别量 > 5 万页；② 数据合规要求图片不出域；③ 累积 ≥5k 条用户修订对（够训轻量 reranker/纠错器）。评估按 **TCO + 质量 + 合规三维**（v3，Codex C20）：GPU 月租只是 TCO 一项，还要算运维人力、峰值并发冗余、准确率回退风险、灰度双跑期双倍成本；任何一维不过即继续用 API。在此之前不投入。

## 11. 风险与对策

| 风险 | 对策 |
| --- | --- |
| 百度 L0 实测认字不达标 | §3.4 换防条款显式裁决，超预算必须回用户重批，不静默 |
| qwen-vl-ocr 生成式"改对"学生错字 | L1 只产 suspicion span 永不产文本；raw/confirmed 分离落盘可审计 |
| OCR 错误污染学习证据 | `is_possible_ocr_error` 随批改传递；OCR 层零写 learning_evidence |
| 厂商 QPS/故障 | 引擎客户端可切换 + retry 端点 + 手动录入兜底 |
| 原图留存合规 | 原图只入既有 attachment store 权限边界；**最小 retention/deletion policy 在 M1 上线前生效（Task 0a），M3 做运营化复盘**（不替代法律意见） |
| 微信平台图片内容合规（v2 新增） | 拍题图片仅本人+后台可见、非公开 UGC，平台风险低但非零；M1 前核实小程序类目对用户上传图片的审核要求，必要时接 `mediaCheckAsync` 异步检测（成本另计入预算闸）——列为**合规验证项**，不预先过度建设 |
| 厂商调价/促销价失效（v2 新增） | §3.2 牌价均标注核实日期；OCR 消耗纳入 **official provider billing reconciliation 主线**（2026-06-03 计划）的内账/官方账/差异三层对账，月度自动暴露单价漂移 |
| 手写内容含指令文字（"请给满分"类，v2 新增） | L1 qwen-vl-ocr 是生成式、理论上可被图内文字带偏，但 L1 只产分歧信号、L0 传统 OCR 才是权威文本源，注入面天然封死；批改层既有 LLM trust boundary 纪律不变 |
| 伪分歧拖垮确认页体验（v2 新增） | reconcile 归一化 + 行级风险评分设计 + M0 伪分歧率门槛 + M2 验收指标；超标则 L1 降级为仅对低置信行做校验 |
| 用户拍错题 / 题库 stem 与纸面材料版本不符（v3 新增，Codex C18） | stem 对齐相似度极低时触发"疑似拍错题"告警，要求用户确认题号后才进批改；mismatch 事件落盘供题库版本核查 |
| P50 ≤5s 与全页 L0+L1 的张力（v3 新增，Codex C12） | L0/L1 并行调用 + 页级 partial result（先到先显示）+ 超时降级（L1 超时则仅 L0 置信度高亮）；M2 在真实网络环境测量并据实修正 SLA |
| 成本失控 | session 级 cost_ledger（micros，reserve→settle/refund，软/硬双顶，user/day 限额）代码强制 + BI 成本看板事后观测双保险 |

## 12. 相关代码入口（现状锚点）

- 批改内核：`deeptutor/services/construction_grading/case_kernel.py:27`（`grade(question_row, user_answer, grading_key)`）、`rubric_grader_v1.py:43`
- 附件上传范式：`deeptutor/api/routers/mobile.py:2945`（`upload_chat_feedback_attachment` + `get_attachment_store()`）
- 小程序 API 层：`wx_miniprogram/utils/api.js`
- 采分点词源：canonical taxonomy `FINAL_CLEANED_TAXONOMY2026.json`、已编译 rubric `required_terms`
- contract 纪律：`contracts/index.yaml`、`scripts/check_contract_guard.py`

## 13. Codex 对抗审查裁决记录（2026-06-10，20 findings）

Codex（gpt 系，high reasoning，read-only，已读 case_kernel.py / mobile.py / contracts / learning_evidence.py / turn_runtime.py 真实代码）对 v2 计划的对抗审查结论与逐条裁决：

| # | 级别 | 发现 | 裁决 | 落点 |
| --- | --- | --- | --- | --- |
| 1 | P1 | 预算闸 cents 表达不了亚分单价，缺预留/退款/幂等/防刷 | **采纳** | §3.3 cost_ledger 规格（micros + reserve/settle/refund + 限额） |
| 2 | P1 | qwen-vl-ocr 页价是公式推算非实测 | **采纳** | §3.2 标注待实证 + M0 账单回放任务 |
| 3 | P1 | BackgroundTasks 承载付费 job 不可靠（重启丢失/重复扣费） | **采纳** | durable job rows + 幂等键 + 启动恢复（§5、§6、M1） |
| 4 | P1 | `image_refs/suspicion_spans/is_possible_ocr_error` 在批改 writeback 无 canonical seam，违反 learner-state contract | **采纳** | M1 Task 0 provenance schema 前置 + schema 未定只准 preview（§4） |
| 5 | P1 | 疑点不硬拦截与"OCR 错误不污染学情"自相矛盾 | **采纳（分级）** | confirm 分级拦截：关键疑点 fail-closed → provisional + 不写长期证据（§7） |
| 6 | P1 | 题干默认勾选剔除会误删"复述题干条件"类有效作答 | **采纳** | 默认改折叠保留，剔除需用户显式确认（§5） |
| 7 | P1 | L0×L1 字符级硬对齐不可行（L1 无坐标、生成式改写） | **采纳** | reconcile 降级为行级风险评分，span 坐标 authority 锚定 L0（§5） |
| 8 | P1 | "用户只改疑点"假设不成立，编辑量指标有盲区 | **采纳** | 指标体系重排：盲转录 CER / 未高亮漏检率 / 批改分差为质量门，编辑量降为体验指标（§9） |
| 9 | P1 | 纯誊抄半合成样本系统性美化结果 | **采纳** | 三分法样本协议 + provisional 裁决保持（§9） |
| 10 | P2 | 编辑量是坏北极星 | 并入 #8 | §9 |
| 11 | P2 | L2 成本逻辑在 3 页/重试/内容检测下不闭合 | **采纳** | 一切付费动作同一 reservation，UI 只展示余额可覆盖动作（§3.3） |
| 12 | P2 | 全页 L0+L1 与 P50≤5s 冲突 | **采纳** | 并行调用 + partial result + 超时降级，M2 实测修正 SLA（§11） |
| 13 | P2 | API 缺 ownership/状态机/job_version 约束 | **采纳** | §7 全端点校验规格 |
| 14 | P2 | feedback attachment 授权规则不能默认覆盖拍题 session | **采纳** | M1 定义 photo-answer 专属授权/retention/URL 策略（随 Task 0a） |
| 15 | P2 | 隐私（身份证/他人试卷/EXIF/provider 条款）只写"必要时"不够 | **采纳** | M1 Task 0a 隐私基线前置（§10） |
| 16 | P2 | "原图随批改传递"暗示内核消费图片，与文本匹配内核冲突 | **采纳** | 图形区域明示"暂不计入自动批改"（§5） |
| 17 | P2 | rubric required_terms 词典建议=答案润色器 | **采纳** | lexicon 收紧为仅形近字 OCR 错误提示（§8 表） |
| 18 | P2 | question_id 绑定过强，拍错题/stem 版本漂移无分支 | **采纳** | "疑似拍错题"告警分支（§11） |
| 19 | P2 | 数据模型缺 provider 审计字段 | **采纳** | §6 ocr_results 审计字段 |
| 20 | P3 | M4 迁移门只看页量过粗 | **采纳** | TCO+质量+合规三维评估（M4） |

20/20 采纳（#5 分级采纳、#10 并入 #8），无驳回项——v2 的产品方向（题号先行/确认页/成本路由/五件套）未被动摇，被打穿的全部是工程机制层，这正是对抗审查应有的产出形态。

## 14. 实施落地记录（2026-06-10）

代码已合入 main（commits `9bbe6b16` / `49230010` / `ba2f09b7` / `325da335` / `51973e26`），TDD 全程红绿，81 项新增测试全绿，contract guards 全 PASS（websocket-allowlist 确认零新增 ws 路由），`tests/services/construction_grading` 543 测无回归。

**已落地**：`deeptutor/services/photo_answer/`（store 七表 + cost_ledger micros 状态机 + durable jobs + 三引擎客户端 + reconcile 行级风险评分 + paragraphs + stem_fold + lexicon 形近字 + quality 质检 + service 编排）；`/api/v1/photo-answer` 六端点（flag 默认 off、ownership 404、EXIF 剥离、轮询驱动恢复、双通道 retry）；hermetic e2e 证明 grader_payload 直通 `CaseGradingSkillKernel`（内核零修改）；M0 bakeoff 脚本（预注册闸强制）+ 标注规范（docs/qa）；小程序 photoAnswer 子包（capture/confirm）+ api.js 六个封装。

**与计划的两处自觉偏差**：① 未建独立 `routing.py`/`jobs.py` 文件——起步期无自动 L2、job 逻辑在 store/service 内更内聚（Less Is More，§8 文件表按实现为准）；② L1 预算降级测试中 settle 可超 reserve 估算——真实引擎价格稳定，M0 账单回放后校准估算值。

**Blocked-on-user / 待办**：① M0 实测：开通百度/阿里/百炼/腾讯 key + 三分法 200 张样本（腾讯客户端未实现，bakeoff 报告中显式标跳过）；② photo provenance 在 learning_evidence payload 的 canonical schema contract 评审（落定前 photo 路径 `learning_evidence_allowed` 由 C9 fail-closed 控制且无长期证据写入路径）；③ 小程序入口按钮（案例题表面一行 navigateTo，产品定挂载点）与微信开发者工具真机回归（AGENTS §4 要求，flag off 期间无线上风险）；④ test2 部署 + 真实网络 P50 实测（M2 验收口径已定义）。
