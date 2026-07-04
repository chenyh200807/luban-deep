# 深 pack AI 专家团裁决签发流水线 · 执行计划

> **Status: Approved（owner 2026-07-04 拍板"设计稿我看过了没问题，开工 D1"）**
> **目标**：2 周内把 35 个未签发深 pack 全部推过 `jury_clean`，owner 批次抽检 + override 签发，40 站内容供给到位。
> **非目标**：不裁存疑 320 条（透明留痕）；不建第二 issue 账本/新 schema；不自动翻 published（结构上也翻不了）。
> **单一 authority**：签发权=`_pack_manifest.overrides.json`（owner 人闸）；事实权威=教材原文（阶梯：教材>跨厂面板>异源>同源）；错因码=`ERROR_CODE_REGISTRY`；"已裁决"唯一凭据=`recheck_resolutions.py` exit 0（反自证）。
> **验收标准**：manifest `--check` 全绿 + 40/40 override + 每批 owner 抽检红旗清单（升色数/新🟢数/not_applicable>25%）为零异常。
> **相关代码入口**：`scripts/build_luban_pack_manifest.py`、`docs/原始数据/考点原料/{jury_audit,autofix_v2,verify_pack,verify_exam_anchors}.py`。
> **配套硬约束（owner 2026-07-04 同日拍板）**：随签发量产的动画教学卡一律用"视频2类"新风格（纸墨朱竹深母题动画学习卡，P40 世代 teach.dc.html 同款视觉），"视频1类"深蓝旧风格全面弃用；存量卡上线前须按此审计。


> 目标：2 周内把 35 个未签发深 pack 全部推过 `jury_clean` 并交 owner 批次签发。
> 设计原则：接通已有件（verify_pack / verify_exam_anchors / autofix_v2 / manifest builder / batch1 resolution 先例），新增 ≤2 个薄脚本。
> 调研基线（2026-07-04 实测）：40 包 / jury sidecar 共 503 条 issue（高可信 183 + 存疑 320）；
> **真正挡门的只有「高可信且无 resolution」≈165 条**（manifest builder `jury_clean = 高可信 unresolved == 0`，存疑不挡门）。
> 已签发 5 包（A01/C02/J01/N01/S05）的 18 条高可信已全部按 resolution 协议解决——先例流程完全可复制。

---

## 0. 调研发现的关键事实（设计的地基）

| # | 事实 | 出处 | 对设计的影响 |
|---|---|---|---|
| 1 | `jury_clean` 只看**高可信 unresolved==0**，存疑 320 条不挡门 | `scripts/build_luban_pack_manifest.py:116` + 测试 `tests/scripts/test_build_luban_pack_manifest.py:51` | 工作量从 485 → **~165**；存疑走"透明留痕不硬清"政策 |
| 2 | `published` 恒 False，唯一翻转 = `_pack_manifest.overrides.json` 人工置 true（只允许 `published`/`note` 两字段） | builder `_apply_overrides` | 签发权在 owner 手里是结构保证，AI 团不可能代签 |
| 3 | **G03 已经 jury_clean=true**（0 高可信），只差 owner 翻 override | manifest 实测 | Day1 用 G03 做签发路径 dry-run，零裁决成本 |
| 4 | **F04 jury sidecar 已损坏**（NUL 字节 + 双 JSON 文档 + 尾部散文），manifest 计 -1 → 永久 fail-closed | `_F04_jury.json:82` 实测 | 必须先做一次性修复（归一成单 JSON 数组），否则 F04 永远签不了 |
| 5 | batch1 先例中 **18 条已解决 issue 里有 2-3 条是 jury 自身幻觉**（J01 #2/#3 "无 quote 支持" 被 point_id 直读证伪，qwen+codex 同源幻觉） | `_J01_jury.json` resolution 原文 | 铁律：**改 pack 前必须先确定性复核 jury 断言本身**，jury ≠ ground truth |
| 6 | resolution 协议已定型且被域测试锁死：`{status: fixed\|not_applicable, fixed_in, verified}`，形状不合法一律计未解决 | builder `_is_resolved` + 测试 :69-74 | 裁决产物 = 往 sidecar 行内写这个 JSON，无需发明新 schema |
| 7 | 生产谱系：镜头 A=DeepSeek / B=Opus / C=GPT-5.5(Codex) / D=Qwen，**Opus 汇编**；jury 三源 = DeepSeek + Qwen + GPT-5.5 | ENGINE-OVERVIEW §1、jury_audit.py | **GLM-5.2 是唯一既没生产也没审过任何 pack 的家族** → 天然终审锚 |
| 8 | flagged_by 命名脏（GPT-5.5(Codex)/GPT-5.5-Codex/gpt-5.5-codex/Qwen/Qwen-Max 混用） | 全量统计 | Tier-0 归一化，别让收敛计数被命名割裂 |
| 9 | N02 有一条元 issue："§5 全表 error_code 尚未与 ERROR_CODE_REGISTRY 对账" —— 错因码类可以**整表确定性对账**一次清一族 | `_N02_jury.json` | 错因码 43 条别逐条裁，先跑 registry 对账脚本 |

### 挡门 issue 的实测分布（165 条，按关键词分类，首匹配优先）

| 类型 | 高可信条数 | 占比 | 典型样例 |
|---|---|---|---|
| point_id 锚 / quote 覆盖不足 / 回源核对 | ~79 | **48%** | "侧模 1N/mm² 数值 quote 未包含完整数值 → 补 quote 或降级"（C04） |
| 错因码映射（E/M 码语义贴合） | ~43 | **26%** | "湿贴花岗岩不做防碱统一判 E10 过粗 → 拆 E02/E10"（D12） |
| 三色标注（降级/升级/剔除） | ~20 | 12% | "坑底有人禁回填标🔵过严且缺逐字 quote"（G02） |
| 措辞升级/语气（宜→应 等） | ~8 | 5% | "阴阳角'圆弧或45度'措辞升级且 45 度无教材 quote"（F04） |
| 数值/参数事实 | ~3 | 2% | "6240<5340 算术错误"（N 系） |
| 结构/本体 vs 邻接边界 | ~3 | 2% | "板钢筋绑扎工法列本体过宽应降邻接"（C05） |
| 真题证据引用 | ~3 | 2% | "{2023,第2题} analysis 含冲突表述未区分"（C05/N 系） |
| 内部自洽冲突 | 混在上述 | — | "S7 采分锚与 8.2 C2 自身修正冲突"（C05） |

> 注意：分类是关键词首匹配的近似值；point_id/quote 类和三色类高度重叠（quote 不足的标准处置就是降色）。
> 实际操作中两类合并为同一条 Tier-1 处置路径。

---

## 1. 流水线分级（四层，从零 LLM 到 owner）

```
Tier-0 确定性预裁（零 LLM，先证伪 jury 本身）
   ↓ 未决
Tier-1 确定性驱动的手术编辑（autofix_v2 机制，LLM 只当打字员）
   ↓ 未决
Tier-2 异源 AI 面板裁决（GLM-5.2 锚 + 双签 + 教材原文仲裁）
   ↓ 分歧 / 设计级
Tier-3 owner 升级（预计 ~10-13 条）
```

### Tier-0 · 确定性预裁（预计覆盖 ~35-40% 挡门条目的**定向**，其中 ~10% 直接 not_applicable 结案）

对每条高可信 issue，先用零 LLM 脚本回答"jury 说的现象是否为真"：

1. **point_id 存在性 + quote 子串核**：issue 声称 "无 quote 支持 / quote 未含数值 X" → 直读
   `_<ID>_compiled_source.json` 对应 point_id 的 quote，子串匹配声称缺失的数值/关键词。
   - 命中 → jury 断言被证伪 → `resolution: {status: not_applicable, verified: "确定性核验：<point_id> quote 直读含 <X>，jury 断言系幻觉，机器闸凌驾 LLM 共识"}`（J01 #3 先例原样复用）。
   - 未命中 → 现象为真，进 Tier-1（默认处置=降色）或 Tier-2（若 fix 要求保🟢）。
2. **错因码整表对账**：拉 pack 全部 E/M 码引用 × `deeptutor/contracts/error_codes.py` ERROR_CODE_REGISTRY 语义定义直读，产出对账表。N02 那类"全表未对账"元 issue 一次清；单条映射争议（E02 vs E10）带着 registry 原文语义进 Tier-2 单审。
3. **真题锚复核**：`verify_exam_anchors.py <pack>`（已有，8/8 式确定性命中先例）。
4. **内部自洽冲突检测**：issue 指出的两处正文（如 C05 S7 vs §8.2 C2）字符串定位，确认冲突仍存在（可能已被前轮 autofix 修掉）。
5. **flagged_by 归一化 + F04 sidecar 修复**（一次性）。

### Tier-1 · 手术编辑（预计 ~40-45%；LLM 无裁决权）

Tier-0 判"现象为真"且 fix 方向是**降级/加注/剔除**的（quote 不足→降🔴/🔵+括注、措辞还原宜/应、邻接降级、冲突处收敛到已修正一侧）：

- 复用 `autofix_v2.py` 的机制：LLM 产 `{old_string 唯一定位, new_string}`，脚本验证唯一才应用，改后复跑两闸。
- **与现 autofix_v2 的唯一差别**：裁决方向来自 Tier-0 结论 + issue.fix，reviser 不许自选方向；且 reviser 换成对该节**非生产源**模型（见 §2 矩阵），不再固定 DeepSeek。
- 安全性来自方向本身：**降级永远合法**（三色铁律禁🔴洗🟢，不禁🟢降🔴）。禁止 Tier-1 做任何升色或新造教材锚。
- 每条改完写 `resolution: {status: fixed, fixed_in: "<pack>.md §x（改了什么）", verified: "<确定性复核语句，可重跑>"}`。

### Tier-2 · 异源面板裁决（预计 ~15-20%）

需要**语义判断且方向不显然**的：错因码 E/M 重映射、本体 vs 邻接、examiner_intent 逻辑覆盖、以及"fix 想保🟢需要找新教材锚"的事实类。

- **事实类**（要保🟢/升色/换锚）：先确定性教材检索（讲义 `docs/原始数据/2026_副本/讲义/*_v8` chunk 全文 python 检索，带页码；教材 `2026教材/` 全文）。
  - 找到逐字 quote → 新锚带页码溯源写入 + 面板 2/3 通过（含 GLM-5.2）才生效；
  - **找不到 → 如实降级🔴/🔵，绝不硬清**；内容 load-bearing（判分眼级）的升 owner。
- **语义类**（错因码/邻接/措辞语义）：双签 = GLM-5.2（必选，全程未涉源）+ 1 个非该节生产源模型。一致 → 结案；分歧 → 取更保守方向（错因码保多码并注/内容降色）或升 owner。
- **投票规则总表**见 §2。

### Tier-3 · owner 升级（预计 ~10-13 条，5-8%）

硬升级触发条件（白名单，不许 AI 团自由裁量扩大）：
1. 设计级拆分/重组（C02"设计级拆分追认"先例——batch1 就是 owner 追认的）；
2. 跨 pack 本体边界移动（如 F02/F04 檐口满粘归属）；
3. 教材检索不到但判分 load-bearing 的数值（如 S06 坠落半径 5m/6m 族）；
4. Tier-2 面板分歧且保守方向会实质削弱 pack 判分能力；
5. 任何想把🔴洗成🟢的冲动。

owner 处置选项固定三个：批准降级上线 / 提供人工出处 / 该 pack 延期。

### 存疑 320 条的政策（明确不做什么）

不挡门、**本轮不裁**。保持 sidecar 透明留痕（append-only 审计记录已有 §9/§10 机制）；Tier-0 跑批时若顺手确定性证伪则免费结案；其余排上线后回扫。理由：less is more，2 周窗口的唯一目标是签发，存疑硬清 = 320 次不必要的 LLM 裁决 + 引新错风险。

---

## 2. AI 面板：角色 × 模型分配矩阵

生产谱系（所有 pack 同构）：§1/§2 聚拢原理=DeepSeek(A镜头)、§4 出题人=Opus(B)、§5 采分边界=GPT-5.5(C)、§6 误区动画=Qwen(D)、全文汇编=Opus。jury 三源=DeepSeek/Qwen/GPT-5.5。

**（2026-07-05 owner 二次修订）用模准则**：异源主力=Codex/GPT-5.5（能力最强），GLM-5.2 降为辅助（仅 ①需 4+ 专家大面板 ②回避补位 时出场）。**不可让步的例外=利益回避**：Codex 是生产镜头(§5)+jury 源，凡裁决"Codex 自己生产/自己 flag 的条目"由非 Codex 模型补位；Claude 系与汇编者 Opus 同厂，对 B 镜头（§4）内容回避表决。三批裁决（D2-D4）按原矩阵执行完毕，本准则自粗粒包 leaf review 起生效。原矩阵背景：GLM-5.2 曾为唯一既非生产源也非 jury 源的家族。

| 角色 | 职责 | 模型 | 异源依据 |
|---|---|---|---|
| 回源核对员 | Tier-0 全部确定性检查 | **零 LLM**（python 脚本） | 机器闸凌驾一切 LLM 共识（J01 先例） |
| 教材检索员 | 讲义 *_v8 / 教材全文检索，产出候选 quote+页码 | **零 LLM 检索** + Fable 5 摘选段落 | 检索确定性；摘选不裁决 |
| 手术编辑员 | Tier-1 old/new 编辑对生成 | 按节轮换：§1/§2→Qwen 或 GLM；§4→GLM/DeepSeek；§5→GLM/Qwen；§6→GLM/DeepSeek | 非该节生产源 |
| 教材仲裁员（终审锚） | "quote 是否支持论断"判读、错因码语义贴合 | **GLM-5.2（每案必到）** | 全程未涉源 |
| 对抗证伪员（第二签） | 独立复核仲裁结论，专职找反例 | Fable 5（默认）；§4/B 镜头案改用 DeepSeek 或 Qwen 中**未 flag 本条**者 | 非生产源 + 尽量非 flagger |
| 终审汇签员 | 每包收口：全部 resolution 形状/证据链核验 + 复跑两闸 + manifest --check | Fable 5 驱动脚本（判定权在脚本 exit code） | 自证陷阱禁令：汇签员只组织，不自报成功 |
| owner | 批次抽检 + override 翻转 | 人 | 结构保证（builder 恒 False） |

**投票规则**：
- 事实类（涉教材数值/规范）：**教材原文 quote 命中是必要条件**（铁律1，29% 分歧率的面板不是 ground truth）；quote 在手后 GLM+第二签 2/2 通过；1/2 → owner。
- 错因码类：ERROR_CODE_REGISTRY 原文语义为准，GLM 单审 + Fable 复签；分歧 → 保守方向（拆码/并注）。
- 结构/措辞/邻接类：GLM 单审即可（方向=降级/收窄时甚至可直接 Tier-1）。
- **flagger 不得裁决自己 flag 的条目**（防自我确认）；但可作为"再确认"参考票，不计入 2 签。

---

## 3. 反自证设计（每条 resolution 的可证伪工件）

自证陷阱禁令的落地：**写 resolution 的进程 ≠ 判 resolution 有效的进程**。

1. **resolution JSON 三字段硬约束**（已有域测试锁形状）：
   - `fixed_in`：精确到 §/行的正文位置 + 改动摘要；
   - `verified`：必须含**可独立重跑的确定性证据语句**——point_id 直读命中文本、`verify_exam_anchors N/N`、`ERROR_CODE_REGISTRY 直读 <码>=<语义>`、教材 quote+页码。禁止出现"面板一致认为"作为唯一证据。
2. **新增薄脚本 `recheck_resolutions.py`（本方案仅有的必要新件之一）**：独立于裁决进程，重放每条 resolution 的机器可核部分——
   - status=not_applicable 的：重跑 point_id/quote 子串核，必须仍命中；
   - status=fixed 的：`fixed_in` 声称的正文改动串真实存在于 pack 当前内容；引用的新教材锚 quote 逐字在 *_v8 chunk / 教材全文中命中；
   - 全 pack：`verify_pack.py` + `verify_exam_anchors.py` 双闸绿 + `build_luban_pack_manifest.py --check` 零漂移。
   - **exit 0 才允许把该 pack 报给 owner**。任何"已裁决"声明以此 exit code 为唯一凭据。
3. **owner 抽检看什么**（每批 10-15 分钟）：
   - 跑一条命令：`python3 recheck_resolutions.py <批次包列表>` 亲眼看 exit 0；
   - 每批随机抽 2-3 条 resolution，人肉打开 `verified` 里引用的 point_id/页码对原文（教材原文是唯一事实权威，owner 抽检就是抽这一层）；
   - 看 Tier-3 升级清单是否为空/已拍板；
   - 看 diff 统计：本批 pack 正文改动是否只有降级/括注/错因码（出现升色/新🟢即红旗）。
4. **裁决记录 sidecar 化**：面板对话原文落 `_<ID>_adjudication_log.json`（谁投了什么票、教材检索命中/未命中），append-only，供事后审计；但**权威只在 resolution + recheck exit code**，log 是留痕不是 authority（防第二权威）。

---

## 4. 批次节奏与 2 周排期

排序原则：先把签发路径本身走通（零裁决成本的 G03）→ 低 issue 包建立流程信心 + 凑首发 → 中量包 → 重尾包（S01/C04/N02/Q01/S02/Q02/K01/S06 共 8 包占 99 条=60%）。首发 10 站（owner 已拍板：已签 5 + F16 + 再签 4）中的 F16（2 条）排最前批。

| 批 | 日程 | 包 | 挡门条数 | 动作 |
|---|---|---|---|---|
| 0 基建 | D1-D2 | 基建 + G03 | 0 | F04 sidecar 修复；flagged_by 归一；`adjudicate.py`+`recheck_resolutions.py` 就位；**G03 直接报 owner 签发 = 签发路径 dry-run** |
| A 信心批 | D2-D4 | D11 E01 E05 F02 F03 N03（各1）+ **F16** C01 C06 D13 F05 S07 X01 X02 X03 R01（各2） | ~26 | Tier-0/1 为主；D4 晚报 owner 抽检 → 第一次批量 override（含首发缺口的 4 包从本批挑） |
| B 中量批 | D5-D8 | B02 G01 A02 C07 D12 G04 Q03 C05 G02 + F04（修复后重计） | ~40 | Tier-2 开始上量；D8 晚第二次 owner 抽检 |
| C 重尾批 | D9-D12 | K01 S06 Q02 C04 N02 Q01 S02 S01 | ~99 | 先跑错因码整表对账（N02/S01 类元 issue 一次清一族）；每包裁完即 recheck；D12 晚第三次抽检 |
| 收口 | D13-D14 | 全量 | — | Tier-3 残留 owner 拍板；manifest --check 全绿；40/40 override；缓冲 |

吞吐核算：165 条 ÷ 10 个工作日 ≈ 17 条/天；Tier-0/1 高度可批处理（每包一次跑完），真正逐条的 Tier-2 仅 ~30-40 条，约 4 条/天，宽裕。重尾包若单包裁决揭示系统性问题（如错因码全表），按"一个系统性修复"处理而非 13 条独立裁决。

---

## 5. 成本与风险

### 成本（量级估算，按已有实测 jury/autofix ~$0.5/pack 外推）

| 项 | 量 | 估算 |
|---|---|---|
| Tier-0 确定性脚本 | 35 包全量 | $0（零 LLM） |
| Tier-1 手术编辑 | ~70 条，按包批处理（每包 1-2 次 reviser 调用 × 30-60k token 上下文） | ~$20-40（GLM/Qwen/DeepSeek API 便宜） |
| Tier-2 面板 | ~35 条 × 2-3 模型 × 上下文（pack 节选+quote 包，非全文） | ~$30-60 |
| 教材检索 | 零 LLM（python 全文） | $0 |
| 复跑两闸 + recheck | 全量多轮 | $0 |
| Fable 5 / Opus 4.8 | 走本平台会话 | 订阅内 |
| **合计** | | **< $100 API + 2 周 agent 时间**；对比 60 包生产成本 ~3000 万 token + $30，裁决是零头 |

### 最大风险点与处置

1. **jury 断言本身是幻觉**（实测 batch1 占 2-3/18 ≈ 15%）→ 结构性防护：Tier-0 先证伪 jury 再动 pack，改前必有确定性复核。
2. **教材检索不到**（讲义 chunk 覆盖缺口，全量编译已知 88 原子化/91 散文塌）→ **如实降级🔴/🔵 或升 owner，绝不硬清**。降级是产品诚实（"每分怎么扣都有教材出处"的反面承诺就是"没出处的不装有"）。
3. **F04 sidecar 修复引入语义漂移** → 修复=机械归一（取最后一个可解析数组，autofix.py `extract_findings` 同款逻辑），修复 diff 单独给 owner 过目。
4. **手术编辑 old_string 不唯一/漂移** → autofix_v2 已内建跳过+留人工队列；跳过条目回 Tier-2 出更精确定位。
5. **重尾包系统性烂**（S01 15条+85🔴、N02 23条+53🔴）→ 若 Tier-0 后仍有 >8 条需 Tier-2，触发"整包体检"而非逐条：面板一次读全包给系统性诊断，owner 决定修 vs 延期（40 包不必然 40/40，首发 10 站保住即产品可上）。
6. **额度墙/429**（M35 金标先例：订阅弃票>50% 是额度墙伪信号）→ 全部走纯 API key（DEEPSEEK_API_KEY/DashScope/GLM），Codex 用 `codex exec --sandbox read-only` 同步模式（rescue 后台已知卡死）。
7. **并行污染** → 每包裁决串行落盘；不开并行提交者（先例：并行 agent 会扫走未提交工作）；工作分支单一。
8. **裁决质量漂移（越裁越松）** → 每批 owner 抽检红旗清单固定：升色数、新增🟢数、not_applicable 占比异常升高（>25% 说明面板在偷懒证伪 jury）。

---

## 6. 与现有工具的复用关系（thin wrapper 盘点）

### 直接复用（不改）
- `verify_pack.py`（闸1：point_id/error_code/三色）
- `verify_exam_anchors.py`（闸2：真题锚，注意用源料 keywords 免固定词漏判）
- `build_luban_pack_manifest.py` + `--check` + overrides 机制 + 域测试（签发权威闭环）
- resolution 协议（`{status, fixed_in, verified}`，S05/batch1 先例格式照抄）
- `deeptutor/contracts/error_codes.py` ERROR_CODE_REGISTRY（错因唯一权威）
- 讲义 `*_v8` chunk（页码溯源）+ `2026教材/` 全文（事实唯一权威）
- batch1 owner note 格式（override note 里写机器核验数字）

### 改造复用（小改）
- `autofix_v2.py` 的**编辑应用器**（unique-match + 复跑两闸）：剥离其"DeepSeek 自选方向"的 reviser，方向改由 Tier-0/2 结论注入；reviser 模型按 §2 矩阵轮换。
- `jury_audit.py` 的模型调用件（key 加载 / codex exec / DashScope）直接搬进面板调用。

### 新增（仅 2 个薄脚本 + 1 次性修复）
1. `adjudicate.py`：Tier-0 确定性预裁 + 面板调度 + resolution 写入（组合已有件，无新概念、无新 authority）。
2. `recheck_resolutions.py`：独立重放核验器（反自证的物理载体，exit code 是唯一"已裁决"凭据）。
3. 一次性：`_F04_jury.json` 归一修复 + flagged_by 命名归一（可并入 adjudicate.py --repair）。

### 明确不新增
- 不建第二套 issue 数据库/看板（sidecar 就是账本）
- 不建新 schema（resolution v0 够用）
- 不给存疑 320 条建清理流水线（本轮政策=不裁）
- 不自动翻 published（结构上也翻不了）
