# 案例题轻练能力 · 落地计划(点选/认→写 + 运行时生成 + 确定性判分)

- **日期**: 2026-07-08
- **状态**: `Proposed v1.3`(治本版;**进代码前先落 §2.5 P-1 数据契约**)。v1.1 吸收调研报告;v1.2 = Codex 一次红队后纠"新造 vs 接线"+ 切分上提 P-1;**v1.3 = Codex 二次红队后再修 6 处**:①运行时门 `G1-G8`→`RTG1-RTG8`(去和 `compiler_pipeline` 签发门 G 编号撞名);②`exam_reference_answer` 只禁用在 `authority_source`、**保留 `answer_key_authority`/`source_ref.kind` 的合法用法**(v1.2 一刀切错了);③`common_wrong_expressions` 等字段注册**上提 P-1**(消除 P0 依赖倒置);④`flaw_correction` 合取门、`case_family→scoring_point→轻练源` resolver **明确标新造**(代码现把 flaw_correction 降成 qualitative、丢 pairing);⑤白名单红线**下沉为代码级 gate**(非文档红线);⑥补 **§2.5 可执行 P-1 数据契约**(Codex 点名的"缺的最后一块")。**Codex 二次结论:v1.2 只能进 P-1 准备、不能直接批量开工;v1.3 补上数据契约后方可。**
- **定位**: 让鲁班具备"任意**已原子化的**案例题当场变成一道轻练、马上能练"的能力——教学动画之后的重要补充。核心=**丝滑少打字交互 + 判分确定性 + 已原子化题的运行时生成**。产品一句话定位(采纳报告):**不是题库、不是 AI 问答,而是"帮一建建筑实务考生把案例题拆成可练采分点、看清为什么丢分"的教练**。
- **权威边界(thin,不造第二 authority)**: 采分点真值归 Nexus 编译库 / 母题作答层 signed;判分归 `rubric_grader_v1` + 确定性通道;错因归 `ERROR_CODE_REGISTRY`;学情归 `LearnerStateService`。本计划**部分是接线(判分稳定/单权威门/签发流水线/错因码/sub_no 消费端),部分是明确新造(轻练生成器/Post-gen 门/CPM 校验器/DAG+ECF/切分自动化/OCR 闭环)——见 §3 诚实拆分**。
- **上位契约**: PRD v1.3(留存主菜)+ 双轮 v3(消费层"投影不生成")+ `2026-07-08-luban-compiled-asset-grading-wiring-map`(判分接线地图)。冲突以上位为准。

---

## §0 背景与结论(5 席调查 + 4 席解法)

**5 席专家组调查结论**:判分不稳只是最表层(temp=0.7 采样,已修);更深是判分体系(覆盖率×整题分四谬误)、采分点切分(23 大题欠切分、100% 未校准)、以及方向盲区(用户第一需求是"先学哪块",判分是最脆地基)。**owner 已拍板方向(案例题轻练=教学动画后的重要补充),本计划执行技术侧;需求验证并行(见 §5)。**

**核心设计决断(把血的教训焊进架构)**:
1. **判分不交给不稳的 LLM 判官** —— 交互本身零打字、判分是**确定性集合/数值/图算**;LLM 只干"出题措辞 + 反馈讲解"两件活。
2. **"会写"只由产出兑现,永不由点选正确率判定**(点选=再认,会造虚假信心)。
3. **计算类绝不做点选 MCQ**(用错题型容器=撞车根因)。
4. **采分点是唯一真值**,任何 LLM(出题/判分/裁判)不得改写或越权当 ground truth。
5. **【v1.2 治本核心】切分/原子化是运行时生成的前置(P-1),不是后置。** 采分点未按小问原子化前**不许对该 qid 出轻练**——因为"LLM 只出题+确定性判分"**不是安全边界**:LLM 若生成了错的正确项/干扰项/`source_scoring_point_id`,确定性判分只会**稳定地按错题判**。所以运行时生成只在**白名单(已原子化 + 有 sub_no + 通道① source + 过一致性闸)**的 qid 上开。

**已实证**:temp=0 后同题连跑 5 次判分 5/5 一致;运行时管线(Nexus load_rubric + LLM 生成)对**已干净的**判断改正/列举类当场出好题(泛水/进度计划/安全员);计算类(荷载组合)崩、欠切分 qid(起鼓割补 22 点、Codex 实测 **22 个大题 qid 全缺小问维度**)出错小问——这四个正是本计划要解的限制,而切分是它们共同的前置。

---

## §1 四个限制 × 解法

### 限制① 计算类会糊 → 换题型容器 + 确定性判分
根因:把矩阵/数值/图算硬压成单选点选。解:每子类换低打字交互 + 确定性判分器,**LLM 只写措辞/讲解、绝不碰数值**(讲解里数字必须回填生成器算的)。

| 计算子类 | 低打字交互 | 确定性判分 | 新造/接线(诚实) |
|---|---|---|---|
| 荷载组合(整体稳定/立杆/底模各算哪些 G/Q) | 矩阵勾选(行=计算项、列=荷载 chip) | 每计算项**集合精确匹配**;干扰=别计算项的荷载(不撞车) | 采分点存 `{计算项:[荷载集合]}`;**止血最轻,改容器+集合判分,不需新引擎(~1-2周)** |
| 关键线路/总工期 | 图上点选连关键路径 | **CPM solver 新造**(算 ES/EF/LS/LF/TF,关键=TF=0),集合/路径匹配+数值容差 | ⚠️ **Codex 核实:仓库无独立 CPM 校验器,必须新造**(只有 N01 静态变体脚本)。生成 ground truth 与判分同一份;结构存网络(工序/历时/紧前)。**关键路径/总工期 2-4 周新造** |
| 时差/工期索赔 | 数值填空 + 责任归属勾选 | CPM solver(时差)+ 责任规则表 + 天数容差 | 依赖上面 CPM solver,**再 +2-3 周** |
| 造价链式 | 表格式分步填空(单位固定、费率下拉) | 每行数值容差 + **链式 ECF**(用学员上游实填值重算下游期望) | 费用构成公式树 + 费率表;**依赖 DAG+ECF 引擎(新造)** |
| 挣值 EVM | 数值填空 + 结论勾选 | 数值容差 + 结论按符号规则(用学员自己算的 SV/CV) | 依赖 DAG+ECF 引擎(新造) |
| 工序排序 | 拖拽重排 | 唯一序=精确匹配;多合法拓扑序=校验紧前约束满足 | 依赖 CPM 依赖图(新造) |

**两个公共引擎(均为新造,非接线)**:
- **A. 计算图(DAG)+ ECF 重算引擎【新造,严重不可小看】**:采分点每步存 `{step_id, formula, depends_on[], expected_expr, unit, tolerance, rounding, points, role: process|result, ecf}`;判分对每步**用学员本步依赖的上游实填值现算期望**再容差比对 → 上游错、下游自洽即给分。⚠️ **Codex 核实:当前只有窄的 `formula_step`/expected-value 判定(`per_question_grading_object.py:450-471`)+ offline POC(`scripts/calculation_validator_poc.py`),不是表达式图/依赖图/ECF。真实工期:单题型 2-3 周;通用 DAG+ECF 6-8 周起。**
- **B. 采分点 schema 升级**:计算类废弃 `hit/coverage` 二值,显式化 `type=calculation` + `steps[] + result_points + process_points + unit_penalty`;组合类用 `set_membership:{bin:[correct_set]} + per_bin_points`。**⚠️ 这些新 schema 全走 register-before-use,且不在现有 T1 canonical grading object 里(见 §1.5C 修正)。**

### 限制② 欠切分 23 大题 + 采分点源冲突 →【本计划的 P-1 前置门,不是后置】
> **⚠️ Codex 核实**:消费端 grader 会读 `sub_no`(`rubric_grader_v1.py:1245-1274/1580-1590`),但**"补写即用"是夸大**——`sub_no` 是**丢失的源事实,消费端只能 opportunistic 读、不能凭空恢复**;补写它=**生产一份新事实,必须先切分**。这不是 UI/schema 问题,是 source authority 问题。**所以本限制是运行时生成的前置(P-1),不是与之并行的补丁。**
- **半自动切分流程(新造)**:LLM 辅助检测小问边界(题干结构 + 官方答案分段)→ 生成 `sub_no`/子题 qid 候选 → **人工确认(教研)** → 过切分质量闸 → 才进白名单。⚠️ **Codex 核实:22 个大题 qid 全缺小问维度;真实工期 3-5 周,且必须在 runtime generation 之前。**
- **原子采分点判据**:两名人工无需知道其它点即可独立标 hit/miss(独立可判 + 互斥 + 可证伪 + 教材/真题锚)。**非平点显式化**:顺序敏感(工序题)、合取门(判断改正=找错∧改正)、列举封顶(答 N 给 M)。⚠️ **新造(Codex 二次指出)**:这三种"非平点确定性判分"**当前都没实现**——`flaw_correction` 现被映射成 `qualitative`(`per_question_grading_judge.py:35-41`),转 runtime 时**丢掉 `pairing/flaw_span/correction_span`**(`:163-198`)、最后按 coverage 给分(`:201-257`),即"找错∧改正必须同时"的合取约束**丢失**。所以判断改正/排序/封顶题型的确定性判分是**新造**,不是现成;`sub_no` 缺失还会让 batch judge 退回 `_split_points_evenly` 按点数平均切块(`rubric_grader_v1.py:1580-1645`)=**判分正确性问题**,不只是显示。
- **源优先级 resolver 挂已有 G2 单权威门**(`enforce_official_scoring_authority`,`rubric_grader_v1.py:1396-1464`;deep_question.py:2377-2395 调用):
  - 通道①(计分)= `authority_source == official_answer` 的原子编译点。⚠️ **Codex 二次修正(v1.2 我一刀切错了)**:要**区分两个字段**——`authority_source`(判分权威枚举,registry `schema_registry.yaml:333-336`/`unified_grading_object.py:44-50` 只认 `official_answer/textbook_cited/owner/pending_calibration`,**这里禁用 `exam_reference_answer`**)vs `answer_key_authority`/`source_ref.kind`(**"答案来源=真题参考答案"的合法标注,`rubric_grader_v1.py:201-204`、`test_rubric_compiler.py:52-56` 现就在用 `exam_reference_answer`,保留不动**)。即:**判分权威用 `official_answer`;溯源"这答案来自真题"仍标 `exam_reference_answer`,两者不冲突、不改现有代码/测试。**
  - 通道②(支撑)= `textbook_cited/pending_calibration`(rich-leaf ~50×)降级 `supporting_only`、排除计分。
  - 优先级:**母题作答层 signed > 编译库切干净(通道①)> 开放世界现抽**。⚠️ **新造(Codex 二次指出)**:`case_family→scoring_point→轻练源` 的 resolver **当前不存在**——`read_model._load_signed_bank` 只返回 `variant_retests`(`read_model.py:228-245`),把它升成轻练采分点源要**新造 resolver**,不是"挂 G2 门即可"(G2 门本身是接线)。
- **母题 R5 作答层升运行时源复用已有签发流水线**(非第二 authority):`promote_variant_bank.py`(candidate→signed,三向 sha:pack 正文==manifest.content_sha256==bank.source_pack_sha256)+ `read_model._load_signed_bank`(双重 fail-closed:status=="signed" 且 sha 对)+ `verify_answer_layer.py`(逐行核锚)。

### 限制③ LLM 生成不可信 → "选不造" +【新造】8 道确定性门(`RTG1-RTG8`)+ 1 道异源分流门(`RTG9`)
> **⚠️ Codex 核实:轻练运行时生成器 + Post-gen 门当前无实现,是新造。** 命名一律用 **`RTG*`(runtime-generation-gate)**,**不得沿用 `G1-G8`**——那与 `compiler_pipeline.py:139-197/161/168/189` 的 **artifact 签发门 G 编号撞名**,排查必串线(Codex 二次红队指出)。也不要与 `deterministic_prescreen`(**学生答案判分前置**,`artifact_first_llm_judge.py:104-127`)混。本节整套新造(P0 若 source 已干净,最小闭环 2-3 周)。
- **Pre-gen**:①**前置一致性闸**(单独一次便宜判别:"这堆采分点是否同一小问?" 不一致→拒绝出题、回切分队列)。⚠️ **张力(Codex 指出)**:这条本身是"第二判别 LLM",与决断 4"LLM 不得越权当 ground truth"有张力——**它只能拒(reject)不能修(repair)**;一旦误放行,后续确定性门也救不了。**所以它是兜底、不是切分的替代——真正的解是 P-1 先把 23 题切干净,一致性闸只拦漏网的。** ②**错因码给白名单让 LLM 选**(按主题预筛 5-12 个候选 + 定义 + 正例),填不出标 `NEEDS_REVIEW` 走人工 ③干扰项正负定义(必须采分点可辨识变形;禁字面同/禁"其实也对"/计算类禁复用正确项符号)④结构化 JSON 契约 + 让它自报 `self_consistency_check` 供对账。
- **Post-gen 确定性门【新造,命名 `RTG*`】**(不调 LLM,先便宜后贵、先硬拒后软处理;任一 BLOCK→重生成≤2→降级/人工队列):

| 门 | 规则 | 处置 |
|---|---|---|
| RTG1 | 干扰项归一化(NFKC/去空格标点/符号等价)后 **≠ 任何正确项** | BLOCK(**撞车 bug 确定性根除**) |
| RTG2 | 干扰项彼此不重复 | BLOCK |
| RTG3 | error_code ∈ ERROR_CODE_REGISTRY(`NEEDS_REVIEW` 例外→人工) | BLOCK/人工 |
| RTG4 | error_code ∈ 本题预筛候选子集 | 软 FAIL→可疑队列 |
| RTG5 | 结构:1 正确+N 干扰、字段非空、`source_scoring_point_id` 指向本题真采分点 | BLOCK |
| RTG6 | 长度/形态(0.3×–3×、非正确项子串、非廉价加"不"反转) | 软 FAIL→可疑 |
| RTG7 | 题干/正确项引用的采分点全落在一致性闸判 `consistent` 的同一组 | BLOCK(兜欠切分) |
| RTG8 | 反编造:正确项文本须忠实采分点原文(子串/高重叠) | BLOCK |
| RTG9 | 干扰"其实也对/语义等价"——**确定性判不了**:仅对相似度过阈的触发**异源模型(非 DeepSeek)批量判别**,只分流不当真值 | 命中→可疑队列 |

- **异源裁判**:生成器 DeepSeek、校验器换厂(GLM 等);只跑疑似(RTG9 相似度过阈 / RTG4 软 FAIL / 抽样批);**只做分流不做 ground truth**,采分点原文才是真值。
- **最省人力度量**:门通过率趋势(零人力告警,某考点 RTG1 飙高=计算撞车、RTG7 飙高=上游欠切分)+ **小样本分层抽检漏检率**(唯一证明门没假绿,来自人工独立判)+ 教研只审窄可疑队列 + 高风险题(付费主路径/首页/诊断依据)灰度人工首发。

### 限制④ 点选是"认"不是"写" → 铁律 + 认→写阶梯
**铁律**:**"会写"只能由产出兑现,永远不能由点选正确率判定**(点选=再认,迁移只到再认;点选流畅=虚假信心)。

- **4 档阶梯**(升档由"隔 3-7 天延时空手产出"兑现,不由点选分):
  1. **竞争性点选**(认·底座):识别踩哪几点 + 对≥1 干扰项标"错在哪/哪种误解"(把再认掺进提取);顺序考点加拖拽排序。**零打字**。
  2. **半写关键词**(cued recall·认→写真正跨越点):空手写/说出每个采分点**术语原字**(填空不给选项),专抓虚假信心。**低打字:语音输入 + 术语原字快捷键**。
  3. **句式积木拼句**:句架("因为…/根据(规范)…/应…")+ 槽位填术语原字,练点→句/分条/按序。**中·脚手架化**。
  4. **成段书写**(唯一同构考场):**首选形态=纸笔 + 拍照诊断**(采纳报告——一建"实务必须动笔",纸笔天然贴考试媒介 + 手写习惯,同时解掉"手机打字不便"与"点选是认不是写"两个死结);语音转文字为备选。只对高频大分开放,低频阶段测验,不做高精度判分承诺(见 §1.5 拍照流水线)。
- **降打字三件套**:语音转文字(消打字痛点、组织力照练)+ 句式积木(生成降为填槽)+ 术语原字快捷键(阅卷只认原词,防近义失分)。
- **防虚假信心 6 机制**:①点选后强制"一句话串起来"(语音)②竞争性说因 ③延时用**高一档**复测同一考点 ④自评校准("闭卷能默写吗"→产出后对照"你以为会/实际差 X")⑤顺序单独设门(空手按序说/写)⑥掌握态只由产出×延时复测双通过才写入。
- **成人分层**(考频×分值×"认-写 gap"):A 高频大分×gap 大→逼到档4;B→停档2 术语默写;C→停档1 脸熟;**默认每考点到档2,只有 A 类付档4 成本**(省成人时间)。

---

## §1.5 吸收《鲁班智考深度调研报告》的产品/交互/商业增量

> 报告是外部市场/学习科学战略调研,与本计划专家组结论高度收敛(互证)。以下是它**补齐我们缺口**的部分,已折进排期。**注意**:报告是战略推断,60/30/10 比例、四周通过标准等均为建议值,须小样本验证;它不掌握我们的具体技术现实(欠切分/kappa/temp),不替代 §1 技术方案。

**A. 三层产品结构(采纳,比例待验证)**:`日常采分点轻练 60-70%(点选/补全/排序,零-低打字)+ 阶段纸笔拍照诊断 20-30%(会写兑现 + 迁移验证)+ 完整模拟 ~10%`。轻练=日活来源,拍照=认→写档4 的落地,模拟=少量。**这条把认→写阶梯(§1 限制④)落成了可执行的日常配比。**

**B. 轻练题型清单(扩充,全部零-低打字 + 确定性判分)**:
| 题型 | 练什么 | 数据依赖 |
|---|---|---|
| 采分点点选/多选 | 命中采分点 | scoring_points |
| **题干关键词点选** | 条件提取(审题) | **`condition_tags`(新字段)** |
| 漏点补全 | 为什么丢分 | scoring_points |
| 流程拖拽排序 | 顺序敏感工序 | 有序 scoring_points |
| **AI 错答挑错** | 把"泛泛而谈"变负面示例(直击"写一堆不得分") | **`common_wrong_expressions`(新字段)** |
| 判断改正/正确做法匹配 | 找错∧改正(合取门) | flaw_correction 采分点 |

**C. 采分点 schema 扩展字段(采纳报告 JSON 设计)——⚠️ register-before-use 硬门(v1.2 Codex 修正:写精确)**:
新增四个字段。**⚠️ Codex 核实**:这些字段**不在现行 T1 canonical grading object(`schema_registry.yaml:302-350` 的 `luban_grading_object.v1` 只允许 point_id/statement/authority_source/span_hash/max_score…)**;而**注册成 T2 并不给字段级保护**(`:421-437` 明说 T2 drift/authority 检查不触发,只认名字)——所以**若这些字段属于采分点/判分对象,必须扩 T1 或建独立 typed schema**,不能只塞进 dict + T2 注册充数(那是"注册绿灯假象")。
- **`acceptable_variants`(同义接受集)**——采分点/判分对象字段,**扩 T1 或建独立 typed schema**;解"换词命中/术语从宽",必带教材/规范溯源,不许 LLM 自由扩表。
- **`common_wrong_expressions`**——喂"AI 错答挑错"负面示例。
- **`condition_tags`**——题干触发条件,喂"关键词点选"。
- **`next_drill_recommendation` / `user_attempt`**——⚠️ **跨域**:触碰 `LearnerStateService`/复练调度,**不只是 construction_grading 本域 schema**;注册与写回边界须与学情域一起定,不新建第二调度权威。
> 计算类 `steps[]` / `set_membership` / 过程分-结果分同理。**统一硬门**:进代码前先在 schema_registry **正确层级**注册(采分点/判分对象→T1 或独立 typed schema,非仅 T2 挂名)+ 补 `contracts/index.yaml` domain 测试,过 `contract_guard`(CI 口径)。参见 [[schema-governance-campaign-state]] [[contract-guard-protected-files-need-registered-domain-test]] [[schema-naming-check-registries-before-design]]。

**D. 拍照纸笔诊断流水线(采纳,OCR 与判分解耦)**:`图片质量检查 → OCR/VLM 抽取文本(PaddleOCR 3.0 / 腾讯云/百度手写,准确率 85-90% 待核)→ 关键实体标准化(归一到规范术语 + acceptable_variants)→ 采分点确定性匹配 + 置信度 → LLM 生成短反馈 → 证据回显(识别文本 + 原图对应区域给用户纠错)`。红线:**读图与评分解耦**(识别错只修前链,不漂评分);诊断非评分、`official_score_allowed=false`;信任靠"识别哪几个词/漏哪几点 + 与用户自评偏差",不靠长解释黑箱。

**E. 首发人群精准定位(采纳)**:**二战/差几分/在职/跟过课但案例题写不出来**的考生(已知案例题是胜负手、更愿为"看清丢分原因"付费),非零基础小白。呼应 [[luban-feedback-validates-learning-path-demand]]。

**F. 商业化价值锚(采纳,写进并行轨)**:价值锚从"题库"移到**"诊断 + 复练方案 + 阶段报告"**;付费点写"解锁 7 天漏分点复练计划 / 相似题迁移 / 阶段拍照诊断 / 高频错因卡片",**不写"解锁全部功能"**。避开与低价题库(49.9 永久)正面比价。

---

## §2 落地排期(逐 P 门,标"接线/新造")

> **统一前置门(register-before-use,不可跳)**:本计划引入的**任何新 schema 字段/对象**(§1① 计算类 `steps[]`/`set_membership`/过程分-结果分;§1.5C `acceptable_variants`/`common_wrong_expressions`/`condition_tags`/`next_drill_recommendation`;`user_attempt` 结构)——**进代码前必须先注册 `contracts/schema_registry.yaml` + 补 `contracts/index.yaml` 对应 domain 测试,过 `contract_guard`**。违反 = CI FAIL(用 CI 口径 `check_contract_guard.py --base origin/main --head HEAD` 预判,非 file-list 口径)。参见 [[schema-governance-campaign-state]]、[[contract-guard-protected-files-need-registered-domain-test]]、[[schema-naming-check-registries-before-design]]。

| 阶段 | 任务 | 新造/接线 | 验收门 |
|---|---|---|---|
| **P-1 前置(必须先做,不可跳;落 §2.5 数据契约)** | ①**注册全部新字段 schema**(正确层级:采分点字段扩 T1/独立 typed schema、`next_drill/user_attempt` 跨学情域;非 T2 挂名)过 contract_guard —— **上提到 P-1,消除 P0 依赖倒置** ②对**优先清单几道题**做**半自动切分/原子化**(LLM 辅助切小问→**两名教研独立确认**→切分质量闸→补 `sub_no`/子题 qid)③`authority_source` 用 `official_answer`(不碰 `answer_key_authority` 的 `exam_reference_answer`)④**代码级白名单 gate**:runtime 生成入口硬校验"已原子化+`sub_no`+通道①+过一致性闸",不在白名单的 qid **代码层拒绝出题**(非文档红线) | 切分自动化 + 白名单 gate + resolver = **新造**;G2 门/sub_no 消费/签发流水线 = 接线 | §2.5 数据契约齐全;schema 过 contract_guard;**只有过 P-1 的 qid 才允许进 P0**;起鼓割补按小问取到割补工序采分点(非"资料准备") |
| **P0 止血(P-1 白名单内,~2-3 周)** | ①temp=0 判分修复**部署**(接线,已改)②荷载组合改**矩阵勾选+集合判分**(轻,~1-2周)③**Post-gen `RTG1–RTG8` 门【新造】** ④**轻练运行时生成器【新造】**接点选 UI(仅白名单题)⑤采分点点选/漏点补全/**AI 错答挑错**(其 `common_wrong_expressions` 已在 P-1 注册,无依赖倒置) | 生成器+RTG门=**新造**;temp=0/集合判分/error_codes=接线 | RTG1 撞车 0 复现;**只在白名单题上**列举/点选不妥项类抽 20 题门通过率(判断改正的**合取判分**门在 P1,P0 只做点选层) + 抽检漏检率达标 |
| **P1 地基(2-4 周)** | ①扩大 P-1 切分覆盖 ②母题作答层 promote signed + **`case_family→scoring_point→轻练源` resolver【新造】** ③**关键线路 CPM solver【新造,非复用】** ④**`flaw_correction` 合取门判分【新造】**(保留 pairing/flaw_span/correction_span,找错∧改正同时才给分)⑤Pre-gen 一致性闸 + 错因码白名单 ⑥题干关键词点选/流程排序题型 | CPM solver / 合取门 / resolver = **新造(各 2-4 周)**;签发流水线=接线 | 关键线路确定性判分通过;flaw_correction 合取门:只找错不改正不得满分 |
| **P2 深化(4-8 周,含被低估项)** | ①注册计算类 schema → 建 **DAG+ECF 引擎【新造,通用版 6-8 周起】** + 过程/结果分 ②认→写档2 ③**拍照纸笔诊断流水线【新造】**(OCR 解耦+证据回显;"确认文本进 grader" 2-3 周,带证据回显+复练 4-8 周)④异源 RTG9 门 + 质量度量 ⑤**批量切完剩余 23 大题** | 全**新造** | ECF:上游错下游不连坐;档2 延时默写跑通;拍照识别文本+证据回显可纠错;23 题全过切分闸 |
| **P3 完整** | ①档3 句式积木 + 档4 成段(高频大分)②成人分层调度 ③全量灰度 + 门度量常态 | 新造 | 高频大分考点走到档4;分层调度按 gap 优先 |

> **v1.2 排期总修正(Codex)**:①**切分/原子化从 P2 上提为 P-1 前置**——它是运行时生成的地基,不做完就上 P0 = 在错误源上确定性出错。②**CPM/生成器/Post-gen门/DAG+ECF/OCR 全是新造**,不是"本周接线";真实工期 P0≈2-3 周、CPM 2-4 周、DAG+ECF 通用 6-8 周、OCR 全闭环 4-8 周。③**P0 只在 P-1 白名单题上开**,不铺全量。

---

## §2.5 P-1 数据契约(Codex 二次点名"缺的最后一块"——不落它,P-1 只是文档修补)

进 P-1 开工前,以下六件**先定义、先注册、先建测试**,缺一不可:

**① qid 白名单 + 代码级 gate**
- 载体:`runtime_supply/` 下一份 `case_light_practice_whitelist.v0.json`(register-before-use)+ runtime 生成入口的 `assert_qid_allowed(qid)` 硬校验。
- 入白名单条件(全满足):`已切小问(有子题 qid)∧ 每采分点带 sub_no ∧ authority_source==official_answer(通道①)∧ 过 Pre-gen 一致性闸`。
- 不在白名单 → 生成入口**抛错拒绝**,不降级、不"尽力出"。

**② 原子采分点 schema(id + 字段表,扩 T1 或独立 typed schema)**
- schema id 建议:`luban_case_scoring_point.v1`(采分点级,区别于整题 `luban_grading_object.v1`)。
- 必备字段:`point_id, sub_no, qid, sub_qid, statement, authority_source(=official_answer), point_type(程序/条件/记录/合取子/列举项/计算步), required_terms[], acceptable_variants[](带溯源), max_score, textbook_source_refs[], answer_key_authority(可=exam_reference_answer)`。
- 非平点结构:`ordering_group`(顺序敏感)、`conjunction_group`(判断改正找错∧改正)、`list_cap`(答 N 给 M 封顶)。

**③ `source_scoring_point_id` 规则(生成物→真值的绑定)**
- 每道生成的轻练题:`correct_options[].source_scoring_point_id` 必须 ∈ 本(子)题采分点集合;`distractors[]` 无 source_id 但必带 `error_code(∈registry)`。
- `RTG5/RTG8` 就是校验这条;违反 BLOCK。

**④ 双教研验收表(切分/原子化的人审 ground truth)**
- 每道 P-1 题:两名教研**独立**标 `{sub_no 划分是否正确, 每采分点是否原子(独立可判/互斥/可证伪), 锚是否到教材/真题, 合取/顺序/封顶结构是否正确}`;不一致→仲裁→consensus。
- 载体:`docs/原始数据/考点原料/segmentation_gold/<qid>.review.json`(记 who/when/verdict/仲裁)。

**⑤ contract/schema guard 测试路径**
- 新 schema 进 `contracts/schema_registry.yaml`(正确层级)+ 在 `contracts/index.yaml` 的 `luban_grading_engine` domain 补 protected files + required tests(否则 contract_guard 报 `protected files changed but no domain tests`)。
- 新增测试:`tests/services/construction_grading/test_case_light_practice_schema.py`(schema 形状)+ `test_whitelist_gate.py`(未原子化 qid 被拒)+ `test_conjunction_scoring.py`(找错不改正不得满分)。

**⑥ 教研产能 SLA(这是产能排期,不是工程排期)**
- 明确:owner、每日可切题吞吐(人天/题)、优先清单条数、排队与仲裁 SLA、与其它项目抢教研人力的冲突处置。**Codex 指出 v1.2 只写了"要教研确认"却没证明这批人力存在——不定 SLA,P-1 会无限期挂起。**

**验收门(P-1→P0 放行条件)**:上述六件齐全 + 优先清单 N 道题全部过双教研验收 + 白名单 gate 单测通过(未原子化 qid 100% 被拒)+ schema 过 contract_guard。**只有这样,P0 的"确定性点选+确定性判分"才真的站在干净、封闭、可溯源的源上。**

---

## §2.6 P-1 契约骨架落地状态(2026-07-09,代码侧已完成,分支 `feat/luban-case-light-practice-p-1`)

> Codex 二次结论点名"缺的最后一块 = 可执行代码契约骨架"。**该骨架现已落地并全绿**(worktree `deeptutor-p1-worktree`,off `spike/main-base-v2`,commit `a9f48b579`)。§2.5 六件里的**工程可执行部分**已兑现;剩下的是**教研人审 + owner 拍板**(§6 卡点)。

**已交付(代码,可验证)**:
- `deeptutor/services/construction_grading/case_light_practice_contract.py`:
  - `LubanCaseScoringPoint` frozen dataclass(15 字段 = §2.5② 全字段)+ `PointType` 6 型 + 非平点结构 `ordering_group`/`conjunction_group`/`list_cap`。
  - claim ceiling 结构性 False(`OFFICIAL_SCORE_ALLOWED`/`CANONICAL_WRITE_ALLOWED`/`RUNTIME_INSTALL_ALLOWED`)。构造期硬校验 `authority_source==official_answer`(通道①)、`answer_key_authority` 合法域(含 `exam_reference_answer`)。
  - `assert_qid_allowed`(§2.5① 代码级白名单门,fail-closed)、`validate_source_scoring_point_id`(RTG5 种子)、`score_conjunction_group`(找错∧改正,缺任一得 0)。
- `runtime_supply/case_light_practice/case_light_practice_whitelist.v0.json`:register-before-use 占位(**空**,fail-closed 拒一切 qid,待双教研验收后填)。
- schema 注册:`luban_case_scoring_point.v1` 进 `contracts/schema_registry.yaml` 的 **T2 runtime-canonical PINNED**(`canonical_fields` 内省对账 BLOCKING);闭包计数 212→213 / tier2 32→33,**CLOSED orphans=0**。
- `contracts/index.yaml`(根 + packaged mirror)`luban_grading_engine` domain 补 protected file + 3 required tests。
- 测试:`test_case_light_practice_schema.py` / `_whitelist_gate.py` / `_conjunction_scoring.py`。

**验证证据(反自证,真跑)**:3 测试 **17 passed**;`check_schema_registry.py --closure` = **CLOSED**(full_set=213 tier1=9 tier2=33 tier3=171 orphans=0);`test_schema_registry.py` **37 passed**;`check_contract_guard.py --base spike/main-base-v2 --head HEAD` = **passed**,且 `[luban_grading_engine] protected=case_light_practice_contract.py | tests=(3 域测试)` —— protected 域真触发、域测试满足(非 trivial skip)。

**第 2 轮(2026-07-09,同分支,已 push;教研-independent 工作推进)**:
- **第 0 件复核**:P-1 对真 `origin/main` base 全绿(diff 恰 8 文件 / 闭包 CLOSED / contract_guard `--base origin/main` 真门通过),**非 spike 特例**,合 main 计数正确。
- **RTG1–RTG8 Post-gen 门**(`case_light_practice_rtg.py`,commit 79cf9a222):纯确定性 8 门(撞车/去重/错因码/候选/结构/形态/一致性/反编造)+ RTG9 异源接口;未跑到的门显式 `NOT_EXERCISED`(反假绿)。12 测试。
- **运行时生成器**(`case_light_practice_generator.py`,commit 491e66924):LLM = **注入式 `complete_fn` seam**(单测 stub / 阿里云真 DeepSeek);correct 选项 = 采分点原文逐字(LLM 只造干扰项);出题过 RTG 门重生成 ≤2、仍 BLOCK→degraded。F16 起鼓割补 **dev fixture**(7 点,`dev_fixture=true` 不进 production whitelist)。7 测试。
- **静态 HTML demo**(`scripts/build_case_light_practice_demo.py`,commit 9d7f652dd,已交付 owner):真跑链路(真采分点→生成器→真 RTG 门→真确定性判分),复现 live 验证 **A 漏 a5 分层剥开=1.2 / B 写了=1.5(满分 1.5)**。唯一 stub = 干扰项来源。
- **块 A 切分 review 骨架**(`scripts/build_case_segmentation_review_skeletons.py`,commit 25ee67698):为 owner 已确认的 5 题各产一份 `docs/原始数据/考点原料/segmentation_gold/<qid>.review.json` 骨架(预填当前采分点 + 空 verdict 槽,教研**审而非写**)。
- **阻塞**:真 LLM 生成 / LLM 切分边界检测需 DeepSeek 凭据(本地无)或**部署阿里云**(§6 owner-stop)。**剩余教研-independent 纯工作 = 块 C 引擎**(CPM solver / DAG+ECF / OCR 骨架 / 认→写档2-4 / flaw_correction,均纯代码,可续)。

**T2-PINNED 裁断理由(单一权威 vs 字段保护,记录以备审)**:§1.5C 要求采分点 schema 有字段级保护、不许 T2 挂名。核查 `check_schema_registry.py:455` 后确认:本仓 guard 的 drift/authority 字段检查**硬编码只对 `luban_grading_object.v1` 跑**——真正的字段保护来自"frozen dataclass + 内省对账测试"(P2#9 给 context_pack/evidence_bundle 上 T2 PINNED 的同一手法),不来自 guard。故:**不往 T1"唯一 grading 对象"列表加第二个 canonical(守单一权威,不与 `luban_grading_object.v1` 竞争),改用 T2 PINNED(canonical_fields + `needs_field_canonicalization:false` + 内省对账)给字段保护。**这既满足 §1.5C(是"独立 typed schema"非"T2 挂名"),又不僭越成第二判分权威——采分点只读视图,判分权威仍归 `rubric_grader_v1`。

## §2.7 P-1 优先清单提案(证据版 · 待 owner + 双教研确认才切)

> **数据来源**:纯读扫描现行 published 编译库 `runtime_supply/v_case_rubric_scored/case_rubric_scored.json`(1221 采分点 / 174 qid,零 LLM/网络,确定性),复现 `2026-07-08-采分点原子化切分修复样板v0` 的"欠切分"结论:**≥12 点欠切分大题 = 22 道**(盘点记 23,差异=盘点含 rejected)。按 `policy` 分布 + 章节 + 已验证锚分级。**这是提案,不是定案——最终 N + 逐题切分归 §6 双教研人审 + owner 拍板。**

**筛选原则**(与 §1 已验证事实一致):
1. **P-1 排除计算重题**(`policy=calc` 占比高):`calc` 判分绝不走 LLM,需 CPM/DAG+ECF(P1/P2)。含少量 calc 的题可切分但轻练只开非计算小问。
2. **优先零-calc、判断/列举/程序型**(§0 已验证泛水/进度/安全员这类当场出好题)。
3. **锚定已 live 验证的起鼓割补**,同章优先(降切分风险)。
4. **章节聚焦 `1A434000`(建筑工程施工技术:防水/屋面/装饰)**——首发人群(二战/差几分)案例题胜负手集中章,呼应 §1.5E。

**建议首批 5 道(全零 calc,同章 1A434000,题型覆盖列举/程序/判断改正含合取门样板)**:

| 序 | qid | 点数 | 整题分 | policy 构成 | 为什么选它 |
|---|---|---:|---:|---|---|
| 1 | `EXAM_1A434000_P0011_01::E0` | 16 | 10 | 15 list + 1 judgment | **起鼓割补,已 live 验证(A/B 判出差异)** —— 切分风险最低的锚 |
| 2 | `EXAM_1A434000_P0010_02::E0` | 18 | 15 | 17 list + 1 judgment | 同章防水、高整题分、纯列举型,认→写档2 术语默写素材足 |
| 3 | `EXAM_1A434000_P0014_02::E0` | 20 | 5 | 15 list + 5 exact | 盘点点名的欠切分典型(20 点挤 5 分),原子化收益最大 |
| 4 | `EXAM_1A434000_P0013_01::E0` | 13 | 5.5 | 9 judgment + 2 list + 2 qual | 判断改正为主 —— **合取门(找错∧改正)判分样板** |
| 5 | `EXAM_1A434000_P0017_01::E1` | 12 | 6 | 9 judgment + 3 exact | 判断改正为主,验证合取门泛化 |

**明确排除出 P-1(计算重,入 P1/P2 计算引擎轨)**:`EXAM_1A432000_P0016_02`(13 calc/29)、`EXAM_1A434000_P0016_02`(8 calc/12)、`EXAM_1A432000_P0015_01`(7 calc/27)、`EXAM_1A432000_P0013_01`(3 calc)等。

**全部 22 道 ≥12 点欠切分 qid 清单**(供 owner 挑选,点数降序,已标 calc 占比):见本轮扫描输出;可按需扩批。**下一步待 owner**:①确认首批 N 与是否照此 5 道;②安排两名教研按 §2.5④ 独立验收(切分/原子/锚/合取结构),产出 `docs/原始数据/考点原料/segmentation_gold/<qid>.review.json`;③定 §2.5⑥ 教研产能 SLA。**owner 确认前不切、不填白名单、不出轻练。**

---

## §3 诚实拆分:真接线 vs 新造(v1.2/v1.3 Codex 核实后)

**✅ 真接线(存在且能干声称的活)**:
- 判官采样稳定:`rubric_grader_v1.py` batch judge(已加 temp=0,`:1533-1548/1555-1564/1986-2005`)。⚠️ 但 temp=0 只稳采样,**命中/漏判仍来自 LLM verdict,不等于"确定性判分"**。
- 单权威门:`enforce_official_scoring_authority`(通道①/②,`:1396-1464`;live path `deep_question.py:2377-2395`)。
- 签发流水线:`promote_variant_bank.py`(三向 sha)+ `read_model._load_signed_bank`(双重 fail-closed)+ `verify_answer_layer.py`(核锚)。
- 错因码:`error_codes.py` ERROR_CODE_REGISTRY + `validate_error_code`。
- `sub_no` **消费端**:grader 会读(`:1245-1274/1580-1590`)——但**源数据缺失,补写=先切分(见 P-1),不是"补写即用"**。
- 母题内容:`docs/原始数据/考点原料/成品/`(采分点、作答层样板、误解模型、句式库)。

**🔨 明确新造(v1.1 曾误标接线,Codex 纠正)**:
- ❌ **CPM solver / 校验器 —— 仓库不存在,必须新造**(只有 N01 静态变体脚本 `build_luban_n01_variant_bank.py`,无 ES/EF/LS/LF/TF solver)。
- ❌ **轻练运行时生成器 + Post-gen RTG 门 —— 不存在**(`compiler_pipeline.py:139-197` 的 G0-G8 是 artifact **签发候选门**,`deterministic_prescreen` 是**学生答案判分前置**,两者都不是运行时出题门,不能冒充)。
- 🔨 DAG+ECF 计算图引擎(当前只有窄 `formula_step` + offline POC)。
- 🔨 半自动切分/原子化流水线。
- 🔨 拍照 OCR→采分点匹配→证据回显闭环(photo_answer 有基础设施但未接轻练/长期证据,`photo_answer/service.py:388-391` provenance schema 未过前不写)。
- 🔨 认→写档2-4 交互 + 语音/术语快捷键。
- 🔨 **`flaw_correction` 合取门判分**(现映射成 qualitative、转 runtime 丢 pairing/flaw_span/correction_span,按 coverage 给分——合取约束丢失,`per_question_grading_judge.py:35-41/163-198/201-257`)。
- 🔨 **`case_family→scoring_point→轻练源` resolver**(`_load_signed_bank` 只返 `variant_retests`,升成轻练采分点源需新造)。
- 🔨 **代码级 whitelist gate**(未原子化 qid 拒绝出题)+ 原子采分点 typed schema(`luban_case_scoring_point.v1`,见 §2.5)。

## §4 红线(四席 + Codex 共同,不可越)
采分点是唯一真值,LLM(出题/判分/裁判)不得改写或越权当 ground truth · 计算类判分绝不走 LLM · error_code 只映射 registry 不自造 · "会写"只由产出兑现 · 质量只认独立可证伪的抽检漏检率(反假绿)· `official_score_allowed=false` 直到金标校准 · register-before-use(且注册在**正确层级**,不用 T2 挂名充数)+ 溯源不断链。
- **【v1.3】未原子化的 qid 不许出轻练——落成代码级 whitelist gate**:runtime 生成入口硬校验"已切小问 + `sub_no` + 通道① source + 过一致性闸";不在白名单**代码层拒绝**,不是文档红线(Codex 二次指出:文档红线挡不住接口开放)。
- **【v1.3】生成忠实采分点硬门**:LLM 生成的题必须过 `RTG5`(`source_scoring_point_id` 指向本题真采分点)+ `RTG8`(正确项忠实采分点原文),否则不许出。**"LLM 只出题+确定性判分"不是安全边界:生成错了,确定性判分只会稳定地按错题判。**

## §5 并行轨:需求验证(诚实边界,不阻塞技术)
本计划是技术解法,可落地;但**尚无真实成人复考生验证"要不要、能不能提分、愿不愿回来"**。点选题现已便宜到可验:**P0 期间并行拉 5 个真实一建复考生试 5 道、看付费/次日回访**,3 天出快信号。技术推进不等它,但真人验证越早越省;若信号为负,先停 P2/P3 的重投入。
- **人群**(采纳报告 §1.5E):优先二战/差几分/在职/跟过课但案例题写不出来的考生,非零基础。
- **报告的四周验证可作详细版**(建议值,须按流量微调):W1 痛点(≥60% 自发说"不会写/不知哪句得分")→ W2 点选价值感(完成率≥70%/价值≥4)→ W3 拍照上传率(≥35%)+ 报告复看(≥60%)→ W4 D3 留存≥25% + 首付费≥5%。**前三个假设(愿点选/觉得有用/愿提示渐退)错了,方向立即重做。**
- **商业化锚**(采纳报告 §1.5F):价值卖"诊断+复练+阶段报告",付费点写"7 天漏分复练/相似题迁移/阶段拍照诊断",不写"解锁全部功能"。

## §6 待核 / 风险
- 各计算子类容差阈值/取整规则须锚现行规范(荷载系数、GB50500 造价口径),属采分点数据不影响架构。
- RTG9"其实也对"确定性判不了,初期高抽样人审,积累标注后再评异源裁判漏检率是否可信。
- 认→写各档阈值(延时 3-7 天、点选稳定线)为工程默认,须产品内 A/B 校准。
- 判分"敢报的分"仍 gated on governed 金标(kappa 转正);本计划所有判分维持 `official_score_allowed=false`。
- 《鲁班智考深度调研报告》是**外部战略推断**(市场/学习科学/相邻产品,web 引证),非本项目实测:三层配比 60/30/10、四周通过标准、拍照 OCR 85-90% 准确率均标"待核",须小样本验证;它不掌握我们编译库欠切分/kappa/temp 等技术现实,只补产品/交互/商业战略,不替代 §1 技术方案。
- 拍照层继承 OCR 风险(潦草/涂改/术语/角度/阴影),故定位为**低频阶段测验 + 诊断参考**,识别文本与原图证据必须回显给用户纠错,不做高精度判分承诺。
