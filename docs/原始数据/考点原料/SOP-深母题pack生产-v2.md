# 深母题 pack 生产 SOP v2（带闸·可复跑）

> **一句话**：炼一个考点的深母题 pack = 挖矿 → v2 工作流(Codex异源入环) → 两道确定性闸 → 冲突回考卷裁定。
> 本 SOP 是生产引擎（造说明书）的标准流程，不是导航（运行时用说明书辅导）。pack 默认 `candidate_teaching_prototype`，不授权 runtime。
> 对齐既有权威：知识身份→canonical taxonomy node_code；错因→`ERROR_CODE_REGISTRY`；判分/学情→signed artifact / `LearnerStateService`；结构→`case_family_structure` L0-L7。**不立第二套 authority。**

## 0. 核心原则（来自 v1→v2 三炉 + 裁判互错的提炼）

1. **按验证类型分工**：结构化事实（题号/point_id/error_code 存不存在）= 确定性代码穷举核；语义判断（examiner_intent 成不成立、推理有没有编、主题对不对）= LLM 异源裁判。**别让 LLM 查事实（它抽样+猜会错），别让代码判语义。**
2. **AI 共识 ≠ ground truth，连自己写的脚本也 ≠**。三层裁判（产出 AI / 异源 judge / 确定性脚本）都可能错——v2 真题锚被 Codex 错杀 8 个、被脚本 bug 错杀 1 个，真相只在**真考卷文件 + 反复核对 + 层间冲突回源裁定**。
3. **异源裁判中立取证，不当检察官**：问"第N题是什么+证据"，不要命令"去抓造假"（对抗 priming 诱发过度定罪）。
4. **结构化数据键重名必穷举**：单选第5/多选第5 同名，first-match 必错，枚举全部匹配。
5. **真题锚只能来自"真题取证相"读到的真考卷**，禁凭记忆写"某年第N题"（题号漂移之源）。

## 1. 可复跑流程（炼一个新考点）

### Step 1 · 挖矿（确定性，跨章聚拢去重）
按考点关键词从 RichLeaf v3.2 编译库筛+去重，产 `_{ID}_compiled_source.json`：
```bash
# 改 kw 关键词 + 输出文件名即可；模式见 _Q02/_S01 的抽取脚本
python3 抽取脚本.py  # 输出 docs/原始数据/考点原料/_{ID}_compiled_source.json
```
判丰度：紧关键词（去掉"工期"这类泛词）命中单元 ≥ ~30、去重采分点 ≥ ~90 才够锚。**计算型考点（网络/索赔）编译库覆盖弱，需改挖真题例题（另一条源料管线，待建）。**

### Step 2 · v2 生产工作流（Codex 异源入环）
复用脚本（改 4 处考点变量 + 镜头 role 即可）：
```
Workflow({scriptPath: ".../workflows/scripts/s01-v2-codex-in-loop-*.js"})
```
四相：① **真题取证**（强制读真考卷 FINAL_CLEANED_EXAM_V20XX.json 抽逐字证据=唯一允许真题锚源）→ ② **4 Opus 镜头**（聚拢原理/出题人/采分边界/误区动画，真题锚只能引证据包）→ ③ **Codex 异源对抗**（agentType: codex:codex-rescue，证伪+出 binding 修正指令）→ ④ **汇编修订**（照 Codex 指令 binding 改 + 写盘）。
成本：~7-9 agent / ~70-85 万 token / ~20 分钟。

### Step 3 · 两道确定性闸（每个 pack 必过，零 token）
```bash
python3 docs/原始数据/考点原料/verify_pack.py <pack.md>          # 闸1 结构
python3 docs/原始数据/考点原料/verify_exam_anchors.py <pack.md>   # 闸2 真题
```
- **闸1 机器闸**：point_id 真在源料？error_code 真在注册表？三色完整？fail-closed。
- **闸2 真题核验**：题号真存在（穷举处理单选/多选重名）+ 主题关键词命中。粗错可抓；案例"第几问"级仅松核到"该年有相关案例"，非逐问坐实（待精化）。

### Step 3.5 · Layer-2 四源异源团语义审（每个 pack 必过；**量产品质核心**）

确定性闸只验"结构化事实"；语义判断（🟢数值/quote 真匹配、examiner_intent 逻辑、R8 错因映射、本体 vs 噪声）交 **4 源异源团**，各自独立审、**禁互相看**：

| 源 | 模型 | 调用 |
|---|---|---|
| 1 | Opus 4.8（产出方自审，最弱，仅兜底，**绝不能单靠它**） | workflow 内 |
| 2 | Codex / GPT-5 | `codex exec --sandbox read-only` 或同步 Agent（**别走后台模式，两次实测会断线/卡死**） |
| 3 | **DeepSeek V4 Pro** | `deepseek-v4-pro` @ `https://api.deepseek.com`（OpenAI 兼容，`DEEPSEEK_API_KEY`） |
| 4 | **Qwen 3.7 Max** | `qwen-max-latest` @ `https://dashscope.aliyuncs.com/compatible-mode/v1`（`DASHSCOPE_API_KEY`） |

**一条命令(已自动化)**：`python jury_audit.py <pack.md>` —— 3 源并发审 + DeepSeek 自动合成收敛 JSON。

**收敛判读（核心规则 · 2026-06-20 自动化实测校正）**：
- **别 prime 陪审团**：prompt **禁点名**疑似问题（如"重点查防火章 quote 合不合理"）——那是**领着证人走、制造假收敛**。中立 prompt（只给 4 类检查方向）才得独立判断。〔实证：我手动跑"4 源收敛防火章"是 prime 出来的；自动化中立 prompt 后 3 源**散开**，各抓不同真问题、**0 收敛**。〕
- **收敛是稀有红利，不是主指标**：独立中立的 judge **天然发散**。陪审团真价值 = **广度**（N 源各扫一遍 = 真问题**并集**；A01 自动跑出 **11 个不同真问题**）。
- **count≥2 = 极高可信**（罕见，立即改）；**count=1 = 单源真 catch → 回真源核验**（**不是丢弃**——旧"单源=存疑可忽略"会丢掉 11 个真问题）。
- 各源**中立取证**（不当检察官，宁标存疑别凑数）。喂料 = pack 全文 + 引用 point_id 的 quote（紧凑）+ "结构化事实已闸验、你只做语义"。
- 自动化去掉**操作者的 priming 偏见** = 比人手动更诚实。

### Step 4 · 冲突裁定
任一闸 / Codex / 产出 AI 互相打架 → **回真源文件（考卷 JSON / 教材 chunk / error_codes.py）逐项核**，不信任何单层。

## 2. 进 active 还差（candidate → active）
- **R7 真人边界**：仍 🔴。teaching tier 用"AI 合成 near-miss + 异源团验证合理"够；official 判分才需真人作答（你拍板的 tier）。
- **案例锚逐问精核**：闸2 待加"案例第几问"级确定性核。
- **签发质检线**：source 白名单 + 版本号 + 签发门（6-18 判断文档 §六 Pass Criteria）。

## 3. 引擎下一代（待做）
- **考点无关参数化**：把镜头 role 抽象成考点无关（"建本考点该有的原理因果层"），用 `args` 传考点，让"炼一个考点"变成真正一条命令，不用每次改脚本。
- ~~多异源~~ **已接通(2026-06-20)**：4 源异源团已实跑收敛，见 §1 Step 3.5。DeepSeek-v4-pro / Qwen-max 通路已验。

## 4. 现状
- 已产：Q02 大体积混凝土温控（计算型，已清 overclaim）、S01 脚手架模板支架验收（判断型，v2，两闸全过）。方法跨领域+跨题型通。
- 工具：`verify_pack.py` `verify_exam_anchors.py`（确定性闸）；workflow 脚本（生产）。
