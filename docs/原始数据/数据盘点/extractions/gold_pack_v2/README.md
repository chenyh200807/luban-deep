# 判分金标 v2（pilot）— 能测「答错」的金标

生成日期：2026-07-31
产物：`student_army_gold.v2.pilot.json`、`leakage_check.json`、`build_v2.py`、`_draft_Q*.json`（人工撰写的作答源）

---

## 1. 为什么要有 v2

v1（`../gold_pack/student_army_grading_gold.v1.json`）的 10 份「不同水平学生答卷」**实为官方答案的逐字截断**：
S03 = 答案全文 + 一句尾巴，S06 = 答案前缀。同一批题上实测 4-gram 泄漏 **precision 最高 0.993、recall 最高 1.000、Jaccard 最高 0.993**；
30 份 v1 作答里只有 9 份能通过 v2 的泄漏闸（见 `leakage_check.json.v1_baseline_same_questions`）。

后果有三条，全部是「假绿」：

1. 判分器在 v1 上「排序 12/12 全对」是**恒等式**——排序由截断长度决定，不是判分能力的证据。
2. v1 只能测**漏没漏**（omission）。真实考生的主要失分形态是**答错、术语不精确、张冠李戴、数值记错**，v1 一条都测不到。
3. 逐字重合让「命中采分点」退化成字符串匹配，掩盖了判分器是否真的在做语义判定。

v2 的设计目标只有一个：**让金标能区分四类失分形态**，并且每一条失分都有客观真值。

## 2. 金标定义（重要：作答文本不是金标）

```
金标 = (a) 官方采分点骨架  +  (b) 每份作答的 expected_failures
```

- **(a) 采分点骨架**取自 `docs/原始数据/数据盘点/extractions/{year}_jianzhu_case_rubric.jsonl`，
  `point_id = "{sub_q_no}.{point_seq}"`，含 `point_score` / `point_type` / `point_text`。
- **(b) expected_failures** 是该卷**刻意植入、必须拿不到**的采分点清单。
- **未列入 expected_failures 的采分点，一律应当被判为命中**（`expected_full_credit_points` 字段已展开）。

`answer_text` 只是承载失分形态的载体，不是被比对的对象。这一条是 v2 与 v1 最根本的差别：
v1 把「答卷长得像官方答案」当成了金标，v2 把「哪些采分点该扣、为什么扣」当成金标。

### expected_failures 条目结构

| 字段 | 含义 |
|---|---|
| `target_point` | 对应的官方采分点 `point_id` |
| `type` | `omission` / `wrong` / `imprecise_term` / `numeric` |
| `expected_credit` | `none`（该点 0 分）或 `partial`（列举型点部分命中） |
| `expected_items_hit` / `expected_items_total` | 仅 partial：命中几项 / 共几项 |
| `injected_text` | 答卷中造成失分的原文片段（omission 型为空串） |
| `adjudication_rule` | **判定规则**：为什么这一分不该给。这是可判性的载体 |

## 3. 四类失分形态定义

| type | 定义 | 例（本 pilot 中的实例） |
|---|---|---|
| `omission` | 少答小问或少答采分点。**正确的部分必须用自己的话重写**，不得用截断官方答案的方式制造 | Q2023-03 mid 未提「隐蔽工程验收」；Q2024-03 mid 实体检验只写 2/4 项 |
| `wrong` | 给出与官方采分点**相矛盾**的做法/结论，含张冠李戴（把成立项判为不妥、把 A 的方法安到 B 上） | Q2025-03 low「先次梁后主梁，先高后低」（官方完全相反）；Q2025-03 mid 把钉钉子法安给严重流淌 |
| `imprecise_term` | 意思接近但用词不规范：口语化、近义替换、规范名称写错 | Q2024-03 low「自检、交叉检查、公司检查」（官方：自检、互检、专检）；Q2025-03 low「大流淌/小流淌」（官方：严重/轻微流淌） |
| `numeric` | 数字、天数、比例、根数、限值记错 | Q2024-03 high「砌完 7 天后再砌」（官方 14d）；Q2023-03 low 照抄题干被否定的「离屋脊 200~300mm、一排、20mm 圆钉」（官方 300~450mm、三排、50mm） |

## 4. 规模与结果（pilot）

题目取自 `../eval_army/screen.json` 中 `clean=true` 的三道（C1 对齐完整 + C2 chunk 唯一 + 无图表依赖）：
**Q2023-03 / Q2024-03 / Q2025-03**，每题 high / mid / low 各 1 份，共 **9 份**。

| 题 | 采分点数 | 采分总分 | high | mid | low |
|---|---|---|---|---|---|
| Q2023-03 | 19 | 20.0 | 16.8 (0.840) | 12.5 (0.625) | 4.20 (0.210) |
| Q2024-03 | 11 | 22.0 | 19.0 (0.864) | 15.0 (0.682) | 6.00 (0.273) |
| Q2025-03 | 13 | 20.0 | 18.0 (0.900) | 13.5 (0.675) | 3.83 (0.192) |

`expected_point_score` 由 expected_failures 推导（踩点累加、不封顶），**不是**独立标注的分数，
只作一致性自检信号：三题的 high > mid > low 单调，且档位间隔明显（≈0.87 / ≈0.66 / ≈0.22）。

失分形态覆盖（共 65 条 expected_failures）：

| type | 条数 | 分布 |
|---|---|---|
| omission | 36 | Q2023-03: 15、Q2024-03: 10、Q2025-03: 11 |
| wrong | 16 | Q2023-03: 7、Q2024-03: 3、Q2025-03: 6 |
| imprecise_term | 7 | Q2023-03: 1、Q2024-03: 3、Q2025-03: 3 |
| numeric | 6 | Q2023-03: 4、Q2024-03: 2、Q2025-03: 0 |

## 5. 泄漏闸（准入硬条件）

指标与 `../eval_army/01_cohort_select.py` **逐字节相同**（字符级 4-gram 多重集，剥标点/空白），
因此 v1 与 v2 数值可直接对比。准入规则：**precision / recall / Jaccard 三项全部 < 0.60**。

```
                     P       R       J
Q2023-03::high     0.137   0.194   0.087
Q2023-03::mid      0.225   0.194   0.116
Q2023-03::low      0.095   0.048   0.033
Q2024-03::high     0.245   0.306   0.157
Q2024-03::mid      0.372   0.281   0.191   <- 全场最高 precision
Q2024-03::low      0.260   0.139   0.100
Q2025-03::high     0.166   0.285   0.117
Q2025-03::mid      0.192   0.230   0.117
Q2025-03::low      0.136   0.095   0.059
```

9/9 通过，最大值 P=0.372 / R=0.306 / J=0.191，距闸门 0.60 有充足余量。
同三题的 v1 对照：max P=0.993 / max R=1.000 / max J=0.993，30 份里 21 份**过不了**这道闸。

降低重合度的手法：整段改写、句式重排、把「300~450mm / 50mm」这类高信息量数字写成中文数字、
用同义但不同字面的连接词。这些手法不改变语义，只打断字面 n-gram。

## 6. 怎么用它算指标

对每份作答跑判分器，拿到它对每个采分点的命中判定 `pred_hit[point_id]`，与金标对照：

```
真值：point_id ∈ expected_failures 且 expected_credit == "none"   -> 该点应判「未命中」
     point_id ∈ expected_full_credit_points                      -> 该点应判「命中」
     point_id ∈ expected_failures 且 expected_credit == "partial" -> 部分命中，
        用 expected_items_hit / expected_items_total 与判分器给出的部分分比例对齐
```

推荐三组指标：

1. **点级混淆矩阵**：以「应判命中」为正类，算 precision / recall / F1。
   这是 v1 拿不到的——v1 的正类几乎恒等于「答卷里出现了官方原文」。
2. **按失分形态分层的漏扣率**：`missed_deduction_rate[type] = 判分器给了分但金标说不该给的条数 / 该 type 总条数`。
   预期发现：`omission` 最好（判分器擅长找缺失），`imprecise_term` 与 `numeric` 最差（需要语义/数值核对）。
   **这一分层是 v2 存在的全部理由**——若判分器在四类上表现一致，说明它确实在做语义判定；
   若 omission 远好于其余三类，说明它只是在做覆盖度匹配。
3. **档位排序**：用 `expected_point_score` 做参考序。
   注意：排序指标在 v2 上仍然是**弱证据**，因为档位间隔是设计出来的；**主指标必须是第 1、2 组**。

`build_v2.py` 可重跑（幂等），改 `_draft_Q*.json` 后重跑即可重新校验 point_id 合法性 + 泄漏闸。

## 7. 诚实边界（不要越过这几条说话）

1. **作答由 LLM（Claude Opus 5）按采分点骨架撰写，不是真实考生语料。** 它复现的是失分的*类型*，
   不是真人答卷的*分布*：缺少书写混乱、跳题、错别字、半截句、无关废话、字迹不清导致的歧义。
   用 v2 得到的绝对数值不能外推到真实考场表现。
2. **采分点来自佑森教育解析的视觉抽取**（`_meta.NOT_official = true`、`source_authority = training_org_analysis_yousen`），
   本身带转录误差，且不等于官方评分标准。v2 只对齐它，不对齐官方口径。
   若日后拿到官方 rubric，v2 的 `target_point` 需重新映射。
3. **expected_failures 的判定规则是单一作者（本 agent）写的**，未经第二人复核。
   `imprecise_term` 类最主观——「交叉检查」算不算「互检」，是我在 `adjudication_rule` 里裁的，
   一个宽松的人类阅卷人可能给分。用它算指标时，建议把 `imprecise_term` 单列，不与其他三类混算总分。
4. **numeric 覆盖不均**：Q2025-03 的 13 个采分点里没有任何含数值的点，因此该题 numeric 条数为 0。
   这是采分点本身的性质，不是造卷偷懒；但也意味着 pilot 的 numeric 样本量只有 6 条，统计力弱。
5. **规模不足以做显著性判断**：9 份作答 / 43 个采分点 / 65 条失分。它是**判分器缺陷的探针**，
   不是可发布的 benchmark。发现差异后必须在扩量版本上复现才算数。
6. **未跑过任何判分器**。本次产出是纯数据，没有生产 turn、没有 LLM 判分调用，
   所以「v2 能测出 v1 测不出的问题」目前是**设计论证**，不是实测结论。
   实测前不得宣称判分器有/没有某类缺陷。

## 8. 扩量前的建议顺序

1. 先在 pilot 9 份上跑一遍现行判分器，看第 2 组分层指标是否真的分化。分化 → v2 设计成立，再扩量。
2. 扩量时优先补 `imprecise_term` 与 `numeric`（当前各 7/6 条，最弱），并挑含数值采分点的题。
3. `screen.json` 里 `clean=true` 的题只有这三道；扩量要么放宽 clean 判据（接受 chunk 共享/图表依赖，
   并在金标里显式标注该风险），要么先修 C1/C2 对齐问题。
4. 真人语料是唯一能消除边界 1 的办法——LLM 造卷再精细也换不来分布真实性。

## 9. 文件与复现

| 文件 | 作用 |
|---|---|
| `student_army_gold.v2.pilot.json` | **金标本体**。3 题 × 3 档 = 9 份，含 stem / official_answer / rubric_points / answers[] |
| `leakage_check.json` | 9 份的 4-gram 三指标 + 同三题 v1 的 30 份对照基线 |
| `_draft_Q2023-03.json` / `_draft_Q2024-03.json` / `_draft_Q2025-03.json` | 人工撰写的作答与 expected_failures 源文件（唯一需要手改的地方） |
| `build_v2.py` | 组装 + 校验脚本：校 point_id 合法性、查重、跑泄漏闸（不过闸直接 assert 失败）、推导 expected_point_score |
| `README.md` | 本文件 |

**入库位置**：`docs/原始数据/数据盘点/extractions/gold_pack_v2/`（按盘点纪律，抽取产物入 docs 下；
`artifacts/*` 被 gitignore 不可用）。同一份在生成时的工作副本位于会话 scratchpad 的 `gold_pack_v2/`。

**重跑注意**：`build_v2.py` 的 `GOLD_V1` 默认指向会话 scratchpad 下的
`gold_pack/student_army_grading_gold.v1.json`（v1 金标，用于取 stem / official_answer / v1 对照基线）。
该路径是临时目录，换机或换会话后用环境变量覆盖：`GOLD_V1=/path/to/v1.json python3 build_v2.py`
（仓库路径同理用 `DEEPTUTOR_REPO`）。`RUBRIC_DIR` 指向仓库内
`docs/原始数据/数据盘点/extractions/`，是稳定的。
v1 金标本身不在本仓库内（它由上一棒生成在 scratchpad），这是本产物的一个可复现性缺口。

**本产物不改任何生产代码/数据，不含任何生产 turn 调用。**
