# 鲁班 R8 解药 / R6 精确挖空 内容 bank 生产计划

> Status: **执行计划（调研已完成，待 owner/教研批准进入阶段化生产）**
> Author: 供给侧调研 agent · 2026-07-05
> 消费端 already shipped（main `4daaaf6d1`，PR #379）：错因银行 R8 解药位 = `antidote_state=pending`「解药整理中」诚实占位；实务闯关 R6 = 「精确挖空准备中」降级为自由默写。**本计划只解决供给侧：这两个 bank 一喂，两处占位零改动点亮。**

---

## 0. 一句话结论（先说坏消息也先说好消息）

**好消息**：两个 bank 都能像考点卡一样**零 LLM、确定性、可重跑、过签发闸地产**——因为 R8 的「误区→error_code→解药」绑定和 R6 的「答案骨架 + required_terms」**都已经作为结构化章节写死在 signed 成品 pack 里**（A01 §6 / §5），教研 + 4 源异源 jury 已经把语义活干完了。builder 只做「解析 + 锚核验 + fail-closed 过滤」，和 `build_luban_concept_card_bank.py` 逐条同构。

**你没问但我必须说的坏消息 / 前提质疑**：
1. **R8 解药正文是教研 authored 的「🔵 讲懂用语」，不是逐字教材 quote**。所以 R8 的忠实门比考点卡**弱一档**——考点卡能做「quote 逐字命中 compiled_source」硬门，R8 做不到。R8 的 grounding = error_code ∈ registry + 锚 resolve + 三色门（🔴待验证的解药整条挡掉）+ 禁审视词。权威级别 = **signed pack 本身**（已过 jury），不是教材逐字。这是诚实的能力边界，不是 bug——但要 owner 知道 R8「不会错」的护城河口径比考点卡薄。
2. **R6 精确挖空的「挖哪个 span」不是凭空判断，而是挖 `required_terms`**（R5 表格里已 slash 分隔机器可读）。但要求 required_term **字面出现在**答案骨架句子里才能挖；对不上的采分点 fail-closed 丢弃。个别 pack 的骨架是模板缩写（`【标签】(id) 内容`），需要一个稳定的行解析器。
3. **不需要新 promote authority、不需要新 loader**。`promote_variant_bank.py` 的 `_BANK_KINDS` 表已经是「variant / concept_cards」两 kind 的收敛点，`_load_signed_bank` 已经 `filename_template` 参数化。R8/R6 各加一个 kind + 一个 runtime 读服务即可，**禁分叉第二套签发/加载**。

---

## 1. 目标与验收口径

| # | 目标 | 验收（活体，非 unit 绿） |
|---|---|---|
| G1 | R8 解药 bank 生产：`{pack_id, error_code}` → 解药 | 对一个 signed+green pack 跑 builder → promote signed → runtime 服务按 `{pack_id:"A01", error_code:"E07"}` 返回 `{mental_model, textbook_ref}` 非空；错因银行 detail 页占位「解药整理中」翻成真解药，**errorbank vm 零改动**（vm head note 已钉死此形状） |
| G2 | R6 精确挖空 bank 生产：`{pack_id}` → 挖空骨架 | 同 pack promote signed → runtime 按 `{pack_id:"A01"}` 返回 `{skeleton_sentences:[{text_before,blank_hint,text_after}], recall_prompt}`；实务闯关②「精确挖空准备中」自由默写翻成精确挖空，**gauntlet vm 零改动** |
| G3 | fail-closed 复用 | 未签发 / sha 漂移 / 文件缺失 = 与「无 bank」同形，占位保持诚实（复用 `_load_signed_bank` 双闸） |

**消费端接口形状（已被 vm head note 钉死，供给必须逐字对齐）**：
- R8：请求 `{ pack_id, error_code }`；响应 `{ mental_model, textbook_ref }`（见 `yousenwebview/packageDeeptutor/utils/errorbank-view-model.js` 头注）
- R6：请求 `{ pack_id }`；响应 `{ skeleton_sentences:[{text_before,blank_hint,text_after}], recall_prompt }`（见 `gauntlet-view-model.js` 头注）

---

## 2. 数据结构定义

### 2.1 R8 解药 bank（`_{pack_id}_antidote_bank.v0.json`）

来源权威 = signed 成品 pack `## 6 · R8 误区 → error_code → 解药`。每条 R8 已含：`error_code：` 行（可多码，如 `E10＋M08`）、`现象`、`错误心智模型`、`解药`、`🟢/🟡/🔴 锚`；末尾还有「误区一览」汇总表可交叉校验。

```jsonc
{
  "schema_version": "luban-antidote-bank",     // dash 命名空间=脚本产物，非 runtime schema（同变体/考点卡惯例）
  "pack_id": "A01",
  "status": "candidate",                        // 签发唯一入口 = promote_variant_bank.py --kind antidote（人闸）
  "source_pack_sha256": "<sha256(pack 正文)>",
  "gate": { "total": 7, "passed": 7, "code_unregistered": [], "anchor_unresolved": [], "forbidden_words": [], "amber_red_dropped": ["A01:R8-1"] },
  "dropped_rows": [{ "r8_id": "R8-1", "reason": "antidote_has_red_unverified_clause" }],
  "antidotes": {                                // 键 = error_code；一码可映射多条 R8（E06 命中 R8-2/R8-5）
    "E07": [
      {
        "r8_id": "A01:R8-4",
        "mental_model": "监理单位组织、施工单位实施、监理见证全过程；施工单位编制专项方案报监理审批。",  // = pack 的「解药」正文，逐字
        "textbook_ref": "kc:1A434020_085_0136:1",   // = pack 的 🟢锚（教材），逐字
        "phenomenon": "答\"实体检验由施工单位组织实施\"或\"由建设单位组织\"。",  // 呈现层可选用
        "wrong_model": "\"谁施工谁验收\"。"
      }
    ],
    "E02": [{ "r8_id": "A01:R8-3", "mental_model": "固定四件套：①混凝土强度 ②钢筋保护层厚度 ③结构位置与尺寸偏差 ④合同约定项目。", "textbook_ref": "kc:1A434020_085_0136:0", ... }]
  }
}
```

runtime 响应投影：`antidotes[error_code][0]`（或全列表由 vm 决定）→ `{ mental_model, textbook_ref }`。**多码 R8**（`E10＋M08`）按每个码各挂一份。

### 2.2 R6 精确挖空 bank（`_{pack_id}_cloze_bank.v0.json`）

来源权威 = signed 成品 pack `## 5 · R5 采分点 + R6 答案骨架`。R5 表格每行有 `采分点` + `锚 point_id` + `required_terms`（slash 分隔，机器可读，且与 `compiled_source` 逐字一致）；R6 §5.2 给答案骨架句。

```jsonc
{
  "schema_version": "luban-cloze-bank",
  "pack_id": "A01",
  "status": "candidate",                        // 签发入口 = promote --kind cloze
  "source_pack_sha256": "<sha256>",
  "gate": { "total": 18, "passed": 18, "term_not_in_sentence": [], "anchor_unresolved": [], "forbidden_words": [] },
  "recall_prompt": "想一想：每个采分点的关键词，你能默写全吗？",   // 模板常量，非 LLM 生成
  "skeleton_sentences": [
    {
      "cloze_id": "A01:C4-1",
      "point_id": "kc:1A434020_085_0136:0",     // 锚，供 fail-closed 核验 + 溯源
      "text_before": "实体检验四内容：",
      "blank_hint": "混凝土强度 / 钢筋保护层 / 尺寸偏差",   // = required_terms（被挖的关键词本身即提示颗粒）
      "text_after": "、合同约定项目"
    }
  ]
}
```

挖空派生规则：取 R5 采分点 statement（或 §5.2 骨架句），把 `required_terms` 里**字面命中**的关键词整块替成 blank，前后残句进 `text_before/text_after`，`blank_hint` = 被挖的 required_terms。多关键词句 → 优先挖首个命中的核心词，其余 required_terms 进 hint。

---

## 3. 生产路径：确定性 vs LLM/教研（给理由）

| 维度 | R8 解药 | R6 精确挖空 |
|---|---|---|
| 语义活谁干了 | 误区→error_code 绑定 + 解药正文，**已由教研 + 4源 jury 写死在 signed pack §6** | required_terms 选定 + 骨架句，**已在 signed pack §5 + compiled_source** |
| builder 该干什么 | 纯解析 §6 结构块 + 锚核验 + 三色 fail-closed | 纯解析 §5 表 + required_terms 字面挖空 + 锚核验 |
| **零 LLM 可行？** | ✅ 可（解析 authored 内容，不生成） | ✅ 可（挖空 = 确定性字符串操作） |
| 忠实门强度 | **中**：解药是🔵 authored 文，做不了「逐字教材命中」；门 = 码∈registry + 锚 resolve + 🔴/🟡门 + 禁词 | **强**：required_terms 与 compiled_source 逐字一致，可做「关键词逐字命中」硬门（同考点卡） |
| grounding 够不够 | 够到 **signed pack 级**（非教材逐字级）——诚实标注，不冒充「答案不会错」 | 够到 **compiled_source 逐字级** |

**裁决：两个都走确定性 builder（零 LLM），拒绝 LLM 现编。** 理由（与双轮 v3 §8「投影不生成」一致）：
- R8 若用 LLM 把误区分类到 error_code = **二次 LLM 归因 = 第二 authority + 全新幻觉源**（v3 §8 明令禁止）。而 pack §6 已经把绑定做完了，LLM 是纯多余。
- R6 若用 LLM 决定挖哪个 span = 隐蔽生成口（「排版时静默改写 required_terms」，v3 §8 红队采信）。required_terms 已 signed，字面挖空即可。
- **例外/缺口**（下方 §7 诚实标注）：R8-1 类「解药含🔴待验证子句」的行、R6「required_term 字面对不上骨架句」的采分点——**不是 LLM 补，是 fail-closed 丢**（无出处不成卡的惯例平移）。

---

## 4. Builder 设计（模板 = `build_luban_concept_card_bank.py`，逐条同构）

两个新脚本，与考点卡 builder 同骨架（`derive_* → run_gate → build_payload → --check 一致性比对`，恒写 `status:"candidate"`，禁代签）：

### 4.1 `scripts/build_luban_antidote_bank.py`
- `derive_antidotes(pack_id)`：定位 signed pack §6，正则切 `**R8-N ｜ ...**` 块；每块抽 `error_code：`（拆多码 `E10＋M08` / `M10＋E05`）、`解药：`（→ mental_model）、`🟢锚`（→ textbook_ref）、`现象/错误心智模型`（可选呈现层）。交叉核验「误区一览」汇总表 error_code 与正文一致。
- `run_gate`：① 每个 error_code ∈ `ERROR_CODE_REGISTRY`（`deeptutor/contracts/error_codes.py`，硬门）；② 锚 resolve 到 `_{pack}_compiled_source.json` 或 pack 真题锚白名单（未 resolve 丢）；③ **三色门**：解药整条含 `🔴待验证`/纯🟡无教材锚 → `amber_red_dropped`（fail-closed，宁缺毋滥）；④ 禁审视词（看穿/识破/揭穿/露馅）；⑤ 去重（同 r8_id）。100% clean 才写。
- `--check`：零写入，重派生 + 重跑门 + 与磁盘 bank 逐条比对（builder 升版/pack 改动现形）。

### 4.2 `scripts/build_luban_cloze_bank.py`
- `derive_cloze(pack_id)`：定位 signed pack §5.1 R5 表 + §5.2 骨架；每采分点取 statement + required_terms + 锚；required_terms 逐字命中 statement → 切 `text_before/blank_hint/text_after`。
- `run_gate`：① required_terms 与 compiled_source point 逐字一致（硬门，同考点卡 quote 门）；② 被挖词字面命中 statement（`term_not_in_sentence` 丢）；③ 锚 resolve；④ 禁审视词。
- `recall_prompt` = 模块常量（非生成）。

> ⚠️ **本项目纪律**：两脚本禁「顺手清理/顺手重构」既有 builder；scope 收窄到只加这两个文件 + promote/loader 的最小 kind 扩展（AGENTS §3 Surgical Changes）。

---

## 5. 签发闸方案（复用优先，禁第二 authority）

**不新建 promote / loader**。已有基座恰好参数化好了：

1. **promote 人闸**：`docs/原始数据/考点原料/promote_variant_bank.py` 的 `_BANK_KINDS` 表已收敛 variant/concept_cards 两 kind。**加两行**：
   ```python
   "antidote": {"template": "_{pack_id}_antidote_bank.v0.json",
                "builder": ("scripts/build_luban_antidote_bank.py", "{pid}", "--check"),
                "violation_keys": ("code_unregistered", "anchor_unresolved", "forbidden_words"),
                "label": "解药 bank"},
   "cloze":    {"template": "_{pack_id}_cloze_bank.v0.json",
                "builder": ("scripts/build_luban_cloze_bank.py", "{pid}", "--check"),
                "violation_keys": ("term_not_in_sentence", "anchor_unresolved", "forbidden_words"),
                "label": "挖空 bank"},
   ```
   校验语义（candidate→signed、sha 三方一致、gate 数字干净、builder --check 重跑）逐条同构，`--kind antidote|cloze` 即用。签发 = 教研/owner 运行本工具（人闸留痕 who/when/basis）。
2. **runtime 加载闸**：`deeptutor/services/luban_lesson/read_model._load_signed_bank` 已 `filename_template` 参数化、双 fail-closed（signed + sha）。**零改动**，两个新读服务各传自己的 template 复用。
3. **runtime 读服务**（镜像 `concept_cards.py`，各 ~80 行）：
   - `deeptutor/services/luban_lesson/antidotes.py`：`build_antidote(pack_id, error_code)` → 只投影 manifest 绿灯 ∧ signed+sha 通过 → `{mental_model, textbook_ref}`；不过任一闸 = 与缺失同形。
   - `deeptutor/services/luban_lesson/cloze.py`：`build_cloze(pack_id)` → 同门 → `{skeleton_sentences, recall_prompt}`。
4. **API 位**：错因银行 detail 端点补 antidote 字段（喂 `buildErrorbankDetail` 的 antidote 参数）；retest/gauntlet 端点补 halfWrite 字段（喂 `buildGauntletViewModel`）。这是 vm head note 承诺的「一喂即亮」的最后一根线——backend only，前端零改。

---

## 6. 阶段化步骤

- **阶段 0（半天，零风险）**：本计划挂 INDEX；对 1 个 spike pack（**A01**，已 green+published+concept-card-signed，§5/§6 结构完整）人工核对 §6/§5 可解析性，锁死解析器边界 case（多码、🔴子句、模板缩写句）。
- **阶段 1（builder）**：TDD 写 `build_luban_antidote_bank.py` + `build_luban_cloze_bank.py`（fixture = A01 signed pack）；跑出 A01 两个 candidate bank + gate 报告。**验收：gate 100%，dropped 行有据可查。**
- **阶段 2（签发闸）**：promote `_BANK_KINDS` 加 antidote/cloze 两 kind + 测试（镜像 `test_promote_variant_bank.py`）；`antidotes.py`/`cloze.py` 读服务 + 测试（镜像 `test_concept_cards.py`）。
- **阶段 3（人闸签发）**：教研/owner 逐条过目 A01 解药与挖空 → `promote_variant_bank.py A01 --kind antidote --basis "..." --who 教研X`（cloze 同）。
- **阶段 4（活体点亮 + API 线）**：补错因银行/gauntlet 端点的 antidote/halfWrite 字段；真机核 A01 错因银行「解药整理中」翻真解药、实务闯关「精确挖空准备中」翻精确挖空。**这是唯一算数的验收——占位点亮 = live 终态，非 unit 绿**（memory：别停在交接态）。
- **阶段 5（批量）**：A01 通后按 green 集（28 pack）逐包重复 builder→人闸；每包解药/挖空可独立签发独立点亮。

---

## 7. 诚实缺口标注（哪些自动、哪些卡教研/锚缺口）

| 项 | 能否自动 | 卡点 / 处置 |
|---|---|---|
| R8 error_code→解药 绑定 | ✅ 全自动 | pack §6 已 authored，builder 纯解析 |
| R8 解药「不会错」的护城河口径 | ⚠️ 只到 signed-pack 级 | 解药是🔵 authored 文非教材逐字——**对外不拿它当「答案绝对正确」**（v3 §6 护城河口径钉死）；🔴待验证子句 fail-closed 丢 |
| R8-1 类含🔴子句的行 | ❌ 丢 | 三色门挡掉；要点亮须教研把该子句核 🟢 后重跑 |
| R6 挖空 span 选定 | ✅ 全自动 | required_terms 已 signed；字面挖空 |
| R6 required_term 对不上骨架句 | ❌ 丢 | `term_not_in_sentence` fail-closed；覆盖率不足的 pack 靠教研补骨架句而非 LLM 造 |
| R7 边界裁决层 | ❌ 不投影 | 全 🔴 待教研裁决（pack §5.3 明示）——**不进任何 bank**，与 v3 §7 一致 |
| 未签发 answer-layer（`candidate_answer_layer_prototype`）| ❌ 不用作源 | 只从 signed 成品 pack §5/§6 取；answer-layer 是候选层，不是签发 authority |
| 覆盖率 | 部分 | §6 全 published pack 有；§5 R6 骨架 green 集齐备；个别 pack 骨架为模板缩写需解析器兜底 |

**无出处不成卡惯例平移**：两 bank 均恒 candidate、缺锚/缺注册码/缺 required_terms 命中一律 fail-closed 丢行，宁少勿错——与考点卡「无 quote 不成卡」同纪律。

---

## 8. 挂 INDEX.md 哪条主线

挂 **`鲁班移动端提分闭环/`** 主线（INDEX §21）——本计划是复习闭环（双轮 v3 `2026-07-02-luban-learn-review-double-wheel-design.md`）的**供给侧生产计划**，与已上线消费端（PR #379）配对，接续 `build_luban_concept_card_bank.py` 确立的「signed pack → 确定性 builder → 人闸签发 → fail-closed runtime 投影」量产范式。建议 INDEX 条目一句话：本文件定义 R8 解药 / R6 精确挖空两 bank 的确定性生产 + 签发 + 点亮路径，是复习闭环两处诚实占位（错因银行解药位 / 实务闯关半写）的落地供给。
