# 编译资产 × 判分接线地图（薄索引 · 防"又不知道"）

- **日期**: 2026-07-08
- **状态**: `Reference / thin-index`（不是新 authority、不新建第二套清单）
- **为什么有这份**: 编译资产（RAG/教材/真题/采分点库）真实存在且**判分链路正在消费它**，但事实散落在数据盘点 + 各引擎计划 + skill reference 里，导致排查判分时容易忘记、甚至绕到薄的关键词 shadow 路径去下错结论（2026-07-08 就发生过一次）。本文只做一件事：**把"我们有什么编译资产 + 判分怎么消费它 + 现在卡在哪"钉在一页纸上，指向胖源，不复制内容。**

> 单一权威纪律：本文是**薄指针**。真正的资产盘点归 `docs/原始数据/数据盘点/`；判分 authority 链归 `deeptutor/tutorbot/skills/construction-case-grading/references/data-authority.md` 与各引擎执行计划。任何冲突以那些胖源为准。

---

## 1. 我们有哪些编译资产（胖源在数据盘点，勿在此扩写）

| 资产 | 是什么 | runtime 消费口 / 权威 | 胖源 |
|---|---|---|---|
| **编译采分点库 `v_case_rubric_scored`** | 案例题逐采分点编译库（RichLeaf v3.2 ~5705 采分点 + per_question ~482 + 313 深编译叶，MAE 判分器 ~0.0749） | `case_rubric_full`（**4 个 published + hash-gated runtime pointer 之一**）→ `rubric_grader_v1.load_rubric(qid)` | `数据盘点/2026-06-16-编译资产盘点.md`、`…/2026-06-19-编译资产AuthorityMap-v1.md` |
| **RAG 教材 chunk `kb_v5_chunks_full`** | 教材逐字 chunk（kb_v5） | published + hash-gated pointer；RAG grounding | 同上 AuthorityMap |
| **`lecture_teaching_cards`** | 讲义教学卡 | published + hash-gated pointer | 同上 |
| **`topic_waterproof`** 等 topic pack | 主题覆盖包 | published + hash-gated pointer | 同上 |
| **深母题包 ~40** | R1–R8 深编译层（情境/意图/判别/答案键/换皮变体/错因解药…） | `docs/原始数据/考点原料/成品/`；双轮 v3 投影门消费 | `2026-06-16-luban-deep-archetype-asset-schema-v2.md`、双轮 v3 |
| **真题编译** | 2015–2025 一建建筑实务（案例 218 / 选择 337） | golden eval / rubric 源 | `数据盘点/2026-06-16-真题考点实证频次.md` |

> AuthorityMap v1 结论重申：`artifacts/*` 直读 runtime 允许数 = **0**；真正 runtime supply 只认 `deeptutor/services/construction_grading/runtime_supply/` 根下 15 条指针，其中 **4 条 published + hash-gated**（上表）。`published=true` ≠ official score ≠ 可写 LearnerState。

---

## 2. 判分怎么消费它（关键接线 · 防再绕 shadow）

案例判分有**两条平行链**（详见 `data-authority.md`）：

1. **V1 编译链（Nexus-like，主链）** — `capabilities/deep_question._grade_one_case_v1` → `rubric_grader_v1.load_rubric(qid)` 取**你的编译采分点库** → 逐点 LLM 裁决（`grade_with_batch_judge_async`）+ 反编造门（evidence_span 必须在作答原文）。**case 题先走这条。**
2. **kernel 四级链（关键词内核，legacy 回落）** — `construction_grading/case_kernel.grade`，V1 degraded/无采分点时回落。

**纪律（钉死，防 2026-07-08 那次绕路复发）**：
- 测/建/评估**案例判分，必须走 V1 Nexus 链（`load_rubric` grounded）**；**不要**用 `m35_artifact_shadow` / `artifact_first_llm_judge` 那条薄关键词 shadow 路径下"判分准不准"的结论——它不加载编译库，会误判成"引擎不行"。
- 任何"AI 判不了采分点 / 要不要用 RAG-Nexus"的讨论，**先读本文 + 数据盘点 + data-authority.md**，再动手。
- V1 结果带 `official_score_allowed=false`：是候选证据，正式成绩仍须治理/教师门提升（金标）。

---

## 3. 2026-07-08 live 实证：编译库在用，但卡在"采分点切分"（非引擎、非形式）

拿 Q18 屋面卷材起鼓割补，走**真 V1 Nexus 编译判分**（阿里云容器只读跑），实测：

- ✅ **编译库确实加载了、且含关键知识**：编译 qid `2017::EXAM_1A434000_P0010_02::E0` 的采分点里有原文 `sp_c4e4…`「再用喷灯烘烤旧卷材槎口，**并分层剥开**，除去旧胶结材料后，重新粘贴新卷材」——"分层剥开"在库里。
- ❌ **硬伤① 欠切分（大题级 qid，多小问揉一起）**：该 qid 底下塞了 **22 个采分点**，是同一道**大题**里起鼓割补 + 材料送检参数 + 施工记录清单 + 施工组织设计审批等**多个小问**的采分点全挂在一个 qid（缺 `sub_no` 小问号维度）。只答起鼓割补，覆盖率仅 **2/22 = 9%**，结构上判不对。
- ❌ **硬伤② 粒度太粗**：「分层剥开」被打包进一个大采分点，整体判 hit/miss。实测**漏了分层剥开（答案A）与写了分层剥开（答案B）得分完全相同（都 1.36 / coverage 2/22）**——那个"就差分层剥开"的关键漏点根本没被单独计分（"虚高"根因）。

**术语更正（2026-07-08 全库扫描后）**：早前口头称"污染"是**过度陈述、已更正**。全库 179 qid / 1384 采分点按 `source_qid` 判定，**跨题脏数据混入 = 0（编译资产没被污染）**。真正的结构问题是：**① 逐点分值全库 100% 未校准（`per_point_score_authority=pending`，唯一真"系统性"）；② 欠切分（大题级 qid 揉多小问）集中在 23 道高采分点题（≥12 点，其中 16 道在 ≤12 分大题），非全库系统性；③ 近重复零星（2 qid/3 对）**。详见 `docs/原始数据/数据盘点/2026-07-08-采分点原子化切分修复样板v0.md` §1。

**结论**：判分"虚高/不准"的根因 = **采分点欠切分（大题级、缺小问号）+ 逐点分值未校准**（判分靠整题分×覆盖率），即数据盘点已登记的 **per-question 切分器 SEV-1 + 缺逐点分值**，今天在 Q18 上被实证。**病在"编译切分/校准"（可修的数据问题，属编译资产层），不在判分引擎、不在"半写案例"形式，也不是"脏数据污染"。**

关联既有登记：`数据盘点` 编译资产盘点"~80% 卡 shadow / 缺逐点分值 / 缺真人签字 / 缺真实作答"；`Gate−1 per_question 切分器 SEV-1`；`R5 promotion 收入闸 blocked on governed gold（kappa 负）`。

---

## 4. 下一步（与 owner 待议，未开工）

1. 拿 **3–5 道真题**（起鼓割补 + owner 关心的案例）走 V1 Nexus 判分，确认"污染 + 粒度粗"是普遍还是个别。
2. 出 **采分点原子化切分修复方案**：一个小问一个 qid、一个关键动作一个原子采分点；手工切一道样板题，验证"漏分层剥开(A) vs 写了(B)"能判出不同分。
3. 与"半写案例 + AI 采分点"这条主线绑定：卡点从"引擎能不能信"收敛为"采分点切分好不好"——后者清晰、可控、在编译资产层可修。

> 红线不变：不写 canonical / LearnerState、不生成 answer key、不做官方判分；V1 结果仍是候选证据。
