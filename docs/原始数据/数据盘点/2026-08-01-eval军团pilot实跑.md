# Eval 军团 pilot 实跑(claude_code 棒)

> 上一棒(codex)因沙箱 DNS 不可达全程 BLOCKED、零数据。本棒环境有网络,pilot **已真实跑完**:
> 6 轮 live(test2 真实入口)+ 12 次 offline 判分 + 公平基线 SHA 实测 + 指标正反自测 + 身份四字段查库核验。
>
> **本文订正上一棒 `2026-08-01-eval军团三臂判分质量.md` 的 BLOCKED 结论**(该文的"未执行"状态在本棒被真实执行取代),
> 但**保留**其 4-gram 泄漏预检结论(本棒复算一致)。

- RUN_ID:`eval_army_pilot_20260731163753`
- `DEEPTUTOR_EVAL_RUNNER_AGENT=claude_code`
- 靶场:`https://test2.yousenjiaoyu.com`(`/readyz` 200)
- 原始产物:`<scratchpad>/eval_army/`(脚本 01–08 + `identity*.json` / `live_turns.jsonl` /
  `offline_grades.jsonl` / `fairness_baseline.json` / `metrics.json` / `live_metrics.json`)

---

## 1. 范围与方法

严格 pilot,未放全量。

| 项 | 值 |
|---|---|
| 金标 | `student_army_grading_gold.v1.json`(15 题 × 10 学生 = 150 样本) |
| pilot 队列 | **2 题 × 3 学生**(干净题筛选后) |
| live 臂 | 军团账号驱动 test2 真实入口(login/new/turn 三段式),**6 轮** |
| offline 臂 | 直接 import `_grade_one_case_v1` + `rubric_grader_v1`,**12 次**(A/B 各 6) |
| 生产写操作 | 仅军团账号自身的注册/登录/发 turn;**未碰任何生产 env / flag / slot** |

### 1.1 干净题筛选(C1–C5)

对 15 题逐题打分(脚本 `01_cohort_select.py`,产物 `screen.json` / `leakage.json`):

- **C1** alignment status = `full`
- **C2** `source_chunk` 在 15 题内唯一
- **C3** legacy 编译 bank 采分点 ≥ 4
- **C4** 无缺图/缺表小问
- **C5** 4-gram 泄漏度中等(避开 S01–S03 天花板探针)

| 题 | alignment | chunk唯一 | bank采分点 | E索引/小问数 | 缺图 | 中位Jaccard | 干净 |
|---|---|---|---|---|---|---|---|
| Q2023-01 | full | ❌ 3年共用 | 19 | E1–E3 / 4 | 图1-1 | 0.771 | ❌ |
| Q2023-02 | partial | ❌ 2年共用 | 40 | E0–E3 / 4 | 图2,表2-1 | 0.747 | ❌ |
| **Q2023-03** | full | ✅ | 23 | **E0–E3 / 4** | 无 | 0.632 | ✅ **选中** |
| Q2023-04 | partial | ✅ | 35 | E0–E4 / 6 | 表4-1 | 0.044 | ❌ |
| **Q2023-05** | full | ✅ | 34 | **E0–E4 / 5** | 表内联 | 0.668 | ✅ **选中** |
| Q2024-01 | full | ❌ | 19 | E1–E3 / 5 | 图1 | 0.750 | ❌ |
| Q2024-02 | full | ❌ | 40 | E0–E3 / 5 | 图2,表2 | 0.870 | ❌ |
| Q2024-03 | full | ✅ | 20 | **E0 only / 5** | 无 | 0.847 | ❌(E覆盖) |
| Q2024-04 | full | ❌ | 56 | E0–E4 / 5 | 无 | 0.628 | ❌ |
| Q2024-05 | full | ❌ | 38 | E0–E4 / 5 | 无 | **0.018** | ❌ |
| Q2025-01 | full | ✅ | 14 | **E0 only / 4** | 图1 | 0.748 | ❌ |
| Q2025-02 | full | ❌ | 19 | E1–E3 / 5 | 图2 | 0.704 | ❌ |
| Q2025-03 | full | ✅ | 27 | **E0 only / 4** | 无 | 0.851 | ❌(E覆盖) |
| Q2025-04 | full | ❌ | 56 | E0–E4 / 5 | 无 | 0.532 | ❌ |
| Q2025-05 | full | ❌ | 38 | E0–E4 / 5 | 表5 | 0.658 | ❌ |

**选中 Q2023-03 / Q2023-05**;学生取 **S03(upper_mid→粗档高)/ S04(mid→中)/ S06(low→低)**。

泄漏度(4-gram Jaccard vs 官方答案):

| | S03 | S04 | S06 |
|---|---|---|---|
| Q2023-03 | 0.869 | 0.655 | 0.394 |
| Q2023-05 | 0.853 | 0.777 | 0.386 |

S01/S02(0.93/0.88)作为天花板探针被排除。**但注意:高档样本本身仍高度泄漏**,粗档"高"这一臂近似白送。

---

## 2. 身份纪律:四字段查库输出原文

三个专用账号,**未复用** `qa_owner_view_0705`:

```
qa_eval_army_claude_code_s03_1785487073   uid=auth_5daffd87c10e43c2a0d4f9fc
qa_eval_army_claude_code_s04_1785487073   uid=auth_eeca11ac959142e3be6af758
qa_eval_army_claude_code_s06_1785487073   uid=auth_00babd2e183b416eb14e57dd
```

### 2.1 服务端 profile 核验(`GET /api/v1/auth/profile`,`verify_eval_runner_identity`)

三账号全部 `verified=True`、`mismatched_fields=[]`:

```
[s03] verified=True mismatch=[] profile={'account_kind': 'eval_runner', 'actor_type': 'machine', 'created_by': 'eval_runner', 'is_internal_test': True}
[s04] verified=True mismatch=[] profile={'account_kind': 'eval_runner', 'actor_type': 'machine', 'created_by': 'eval_runner', 'is_internal_test': True}
[s06] verified=True mismatch=[] profile={'account_kind': 'eval_runner', 'actor_type': 'machine', 'created_by': 'eval_runner', 'is_internal_test': True}
```

### 2.2 Supabase 查库原文(`public.user_identity_aliases`)

```sql
SELECT alias_type, alias_value, user_id::text, source,
       metadata->>'account_kind', metadata->>'actor_type',
       metadata->>'created_by',   metadata->>'is_internal_test'
FROM public.user_identity_aliases
WHERE alias_value = ANY(:phones) OR user_id::text = ANY(:uids);
```

```json
[
 {"alias_type":"phone","alias_value":"13985487073","user_id":"5daffd87-c10e-43c2-a0d4-f9fc97f138f5",
  "source":"phone_verification","account_kind":"eval_runner","actor_type":"machine",
  "created_by":"eval_runner","is_internal_test":"true"},
 {"alias_type":"phone","alias_value":"13985487080","user_id":"eeca11ac-9591-42e3-be6a-f75856a42ecd",
  "source":"phone_verification","account_kind":"eval_runner","actor_type":"machine",
  "created_by":"eval_runner","is_internal_test":"true"},
 {"alias_type":"phone","alias_value":"13985487087","user_id":"00babd2e-183b-416e-b14e-57dd7f5d36b3",
  "source":"phone_verification","account_kind":"eval_runner","actor_type":"machine",
  "created_by":"eval_runner","is_internal_test":"true"}
]
```

### 2.3 `public.users` 查库原文 —— **发现账号裂成两行,其中一行 BI 可见**

```json
[
 {"id":"auth_5daffd87c10e43c2a0d4f9fc","identifier":"auth_5daffd87c10e43c2a0d4f9fc",
  "account_kind":null,"actor_type":null,"created_by":null,"is_internal_test":null,"runner":null},
 {"id":"5daffd87-c10e-43c2-a0d4-f9fc97f138f5","identifier":"5daffd87-c10e-43c2-a0d4-f9fc97f138f5",
  "account_kind":"eval_runner","actor_type":"machine","created_by":"eval_runner",
  "is_internal_test":"true","runner":"claude_code","eval_run_id":null}
]
```

(三个账号形态相同,共 6 行。)

---

## 3. BI 零混入核查(canonical 谓词,非只看名字)

谓词镜像 `member_console._has_explicit_non_human_identity` + `bi.py:48` 前缀 cohort
(`("qa_eval_", "eval_", "qa_")`),逐行判定:

| users.id | field_excluded | prefix_excluded |
|---|---|---|
| `auth_5daffd87c10e43c2a0d4f9fc` | **false** | **false** |
| `auth_eeca11ac959142e3be6af758` | **false** | **false** |
| `auth_00babd2e183b416eb14e57dd` | **false** | **false** |
| `5daffd87-c10e-43c2-a0d4-f9fc97f138f5` | true | false |
| `eeca11ac-9591-42e3-be6a-f75856a42ecd` | true | false |
| `00babd2e-183b-416e-b14e-57dd7f5d36b3` | true | false |

`public.bi_internal_accounts` 对这 6 个 id 均 **0 行**。

**结论(诚实版,不是"零混入"):**

1. ✅ **会员计数臂安全**:`member_console` 读的是 external_auth 身份元数据,profile API 已证四字段齐全,
   `_has_explicit_non_human_identity` → True → 排除。
2. ✅ **alias 投影安全**:`user_identity_aliases.metadata` 四字段齐全。
3. ❌ **`public.users` 的 `auth_<24hex>` 那一行是 BI 可见孤儿**:metadata 为空、
   id/identifier 是 `auth_*` 而非 `qa_eval_army_*`,**三条排除臂全部落空**。
   每个军团账号留一行。这属于既有的"member 合并/钱包分裂"病族在 eval 账号上的复现。
4. ⚠️ **未验证**:`product_behavior_store`(SQLite,服务器侧)的 `user_id` 到底存
   `auth_*` 还是 `qa_eval_army_*`。前缀排除只有在存后者时才生效。
   BI 端点 `/api/v1/bi/learning-preference`、`/api/v1/bi/overview` 用军团 token 返回
   **403 Admin access required**——我**没有提权**去看,所以这条留作 NOT VERIFIED。

---

## 4. billing bypass:证据说"未能证明",不说"生效"

原计划"跑一轮真实 turn,对比钱包/额度未被扣"。**这个设计本身是假成功陷阱**:
军团账号 `balance_micros = 0`,若 test2 根本不计费,"没扣"什么也证明不了。

改做**正负对照**(`04_bypass_control.py`):同账号、同 conversation、同一句 probe,只差 `X-Eval-Bypass` 头。

```
bypass header present locally: ['X-Eval-Bypass']
NO_BYPASS -> {"bypass_header_sent": false, "http_status": 200, "turn_id": "turn_1785487321536_4a1af1168c"}
BYPASS    -> {"bypass_header_sent": true,  "http_status": 200, "turn_id": "turn_1785487322290_05f1d72cbf"}
```

全部 8 轮 turn(2 对照 + 6 live)跑完后:

```
wallets:       balance_micros = 0, frozen_micros = 0, version = 1   (三账号,与跑前完全一致)
wallet_ledger: 0 行                                                  (三账号)
```

**判定:`NOT_DISCRIMINATING`。** 两臂都 200、账本都 0 行 ⇒ test2 上根本没有发生计费,
bypass 头**格式正确且确实发出**,但**其效力在 test2 上不可观测,不能宣称"已验证生效"**。
连带结论:test2 跑 eval **不消耗会员额度**,所以全量的风险不在钱,在 BI 混入。

---

## 5. 公平基线:SHA-256 实测(不是引用 docstring)

拦截 `derive_rubric_from_stem_async` 实际组装的 prompt(stub `complete_fn` 捕获后中止,
零 LLM 花费;并置 `LUBAN_RUBRIC_EXTRACTION_CACHE_TTL_SECONDS=0` 防缓存短路):

| 变体 | system SHA-256 | prompt SHA-256 | prompt 字符 |
|---|---|---|---|
| `base_no_kwarg`(不传 kb_evidence) | `a335de93…cf11` | `31fd6c80…08e2` | 780 |
| `empty_list`(`kb_evidence=[]`) | `a335de93…cf11` | `31fd6c80…08e2` | 780 |
| `none_explicit`(`kb_evidence=None`) | `a335de93…cf11` | `31fd6c80…08e2` | 780 |
| `grounded`(真实 chunk) | `a335de93…cf11` | `f5e2239a…ebbe` | 1021 |

```
VERDICT: {"empty_equals_base": true, "grounded_differs_from_base": true, "FAIR": true}
```

**空证据与基线字节等价成立 ⇒ 公平,未触发 STOP。**

---

## 6. offline 臂设计被证伪:kb_evidence 在本金标上不可达

`_grade_one_case_v1`(`deep_question.py:2473+`)三层:

1. **tier-1** `load_rubric(qid)` 命中编译 bank → 直接判分;
2. **tier-2** 有 `correct_answer` / `reference_answer` → `extract_rubric_from_reference_async`;
3. **tier-3** 既无编译 rubric 又无官方答案 → `derive_rubric_from_stem_async`
   ——**这是唯一消费 `kb_evidence` 的分支**(`deep_question.py:2552-2556`)。

金标 15 题 **既在 legacy bank 内(tier-1)又有 `official_answer`(tier-2)**,永远到不了 tier-3。
所以任务书原定的 offline (a) `kb_evidence=[]` vs (b) 真实检索,在这份金标上是**空设计**——
两臂不是"公平",是同一条路径跑两遍。

**处置**:保留 6+6,把 B 臂如实改标为**重复性探针**(同配置第二遍),换取一个全量前必须知道的量。

---

## 7. 指标与自测

三个指标(照命题,未自创;**禁用细粒度秩相关**,金标循环性):

- **① 官方 key 采分点 P/R**:precision = 抽出的采分点能 4-gram 溯回官方答案的比例;
  recall = 官方答案 key 单元被至少一个采分点覆盖的比例。
- **② 粗三档排序一致性**:高/中/低 三档间成对比较,同档不计。
- **③ 编造引用率**:命中点的 `evidence_span` 必须**机械回指**学生原文(4-gram containment ≥0.8);
  另外零 kb_evidence 下任何 `textbook_ref` 一律判为幽灵引用。

### 自测(正反例,9/9 全过)

```
-- metric (1) scoring-point P/R --
  [PASS] clean sample judged clean (precision==1.0): 1.0
  [PASS] clean sample recall high (>=0.5): 0.5
  [PASS] invented point IS flagged (precision<1.0): 0.5
-- metric (2) coarse ordering --
  [PASS] correct ordering scores 1.0: 1.0
  [PASS] inverted ordering IS flagged (<1.0): 0.0
  [PASS] all-ties IS flagged (0.0): 0.0
-- metric (3) fabricated citation --
  [PASS] clean spans -> 0 fabrication: 0.0
  [PASS] fabricated span IS caught (>0): 0.5
  [PASS] phantom textbook_ref IS caught: ['P1']

SELF-TEST PASSED
```

---

## 8. 逐轮结果

### 8.1 offline 臂(12 次,`on_the_fly_reference` = tier-2)

| arm | 题 | 学生 | 能力 | 得分率 | 小问覆盖 | ①P | ①R | ③编造率 |
|---|---|---|---|---|---|---|---|---|
| A | Q2023-03 | S03 | upper_mid | **1.000** | **3/4** | 0.400 | 0.313 | 0.0 |
| A | Q2023-03 | S04 | mid | 0.846 | 4/4 | 0.111 | 0.625 | 0.0 |
| A | Q2023-03 | S06 | low | 0.520 | 4/4 | 0.550 | 0.625 | 0.0 |
| A | Q2023-05 | S03 | upper_mid | **1.000** | 5/5 | 0.452 | 0.733 | 0.0 |
| A | Q2023-05 | S04 | mid | 0.889 | 5/5 | 0.600 | 0.800 | 0.0 |
| A | Q2023-05 | S06 | low | 0.345 | 5/5 | 0.524 | 0.800 | 0.0 |
| B | Q2023-03 | S03 | upper_mid | **1.000** | **4/4** | 0.308 | 0.500 | 0.0 |
| B | Q2023-03 | S04 | mid | 0.864 | 4/4 | 0.650 | 0.625 | 0.0 |
| B | Q2023-03 | S06 | low | 0.575 | 4/4 | 0.550 | 0.625 | 0.0 |
| B | Q2023-05 | S03 | upper_mid | **1.000** | 5/5 | 0.900 | 0.800 | 0.0 |
| B | Q2023-05 | S04 | mid | 0.896 | 5/5 | 0.700 | 0.800 | 0.0 |
| B | Q2023-05 | S06 | low | 0.538 | 5/5 | 0.600 | 0.800 | 0.0 |

**② 粗三档排序一致性 = 1.000(4 组 × 3 对 = 12/12 全对)。**

**重复性(A vs B,同配置)**:

| 题\|学生 | A | B | Δ | Δ/满分 |
|---|---|---|---|---|
| Q2023-03\|S03 | 20.00 | 20.00 | 0.00 | 0% |
| Q2023-03\|S04 | 16.92 | 17.28 | +0.36 | 1.8% |
| Q2023-03\|S06 | 10.40 | 11.50 | +1.10 | 5.5% |
| Q2023-05\|S03 | 20.00 | 20.00 | 0.00 | 0% |
| Q2023-05\|S04 | 17.78 | 17.93 | +0.15 | 0.8% |
| Q2023-05\|S06 | **6.90** | **10.76** | **+3.86** | **19.3%** |

### 8.2 live 臂(6 轮,test2 真实入口,全部 `status=completed`)

| 题 | 学生 | 能力 | 得分 | 得分率 | 落到 tier-3 诊断? | 覆盖告警 | 「未核到教材出处」次数 | 延迟 |
|---|---|---|---|---|---|---|---|---|
| Q2023-03 | S03 | upper_mid | 5.69/10 | **0.569** | ✅ | ✅ | 13 | 125s |
| Q2023-03 | S04 | mid | 10.0/10 | **1.000** | ❌ | ✅ | 0 | 50s |
| Q2023-03 | S06 | low | 10.0/10 | **1.000** | ❌ | ✅ | 0 | 31s |
| Q2023-05 | S03 | upper_mid | 10.0/10 | 1.000 | ❌ | ❌ | 0 | 37s |
| Q2023-05 | S04 | mid | 7.65/10 | 0.765 | ✅ | ❌ | 15 | 64s |
| Q2023-05 | S06 | low | 10.0/10 | **1.000** | ❌ | ❌ | 0 | 30s |

**② 粗三档排序一致性:Q2023-03 = 0.000(0/3)、Q2023-05 = 0.333(1/3),合计 1/6。**

---

## 9. 关键发现

1. **live 与 offline 根本不是同一台判分机。** offline 走 tier-2(官方答案作 rubric 权威),
   排序一致性 **12/12**;live 走 **tier-3 题干推导诊断**,自带
   「未命中题库原题/标准答案,本轮是题干推导诊断批改,**不能作为正式阅卷成绩**」,
   排序一致性 **1/6**。同一批学生、同一批题,结论相反。
   **推论:任何只跑 offline 的判分质量结论,都不能外推到用户真实看到的批改。**

2. **live 臂满分泛滥:6 轮里 4 轮给 10/10,包含两次 low 档学生。**
   低分作答(S06,Jaccard 0.386–0.394,309/294 字)在 live 拿满分,这是 reachability/兜底
   导致的分数虚高,不是判分尺度松。这是 pilot 最该上报的产品级病。

3. **kb_evidence 在 live 是可达的,在本金标 offline 不可达。** live 落 tier-3 ⇒
   `LUBAN_STEM_RUBRIC_KB_GROUNDING` 的 A/B **只能在 live 臂做**。
   而且 live 输出里 13/15 处「未核到教材出处」直接证明:test2 当前这条路
   **跑的是无教材接地的 tier-3**,这正是该 flag 关闭态的可观测判别位。

4. **判分覆盖不足却给满分(offline)。** A 臂 Q2023-03/S03 `case_subq_coverage = "3/4"`,
   第 4 问未纳入判分,**得分仍归一化到 20.0/20.0 满分**。虽有文案免责,
   但分数本身对上层消费者是"满分"。同一输入 B 臂又变 4/4 ⇒ **覆盖范围本身不稳定**。

5. **重复性在弱答案上崩。** 高档学生 Δ=0(都钉死在满分,天花板效应),
   低档学生 Δ 最大 **3.86/20 = 19.3%**。`n=1` 对低档格子不成立。

6. **③ 编造引用率 = 0.0(12/12)。** 所有命中点的 `evidence_span` 都能逐字回指学生原文,
   零幽灵 `textbook_ref`。这是本轮唯一干净通过的指标,且反例自测证明它会触发。

7. **① P/R 指标当前不可信(校准缺口)。** precision 落在 0.111–0.900,方差极大。
   根因是我的实现用 4-gram 逐字溯源,而 LLM 抽出的采分点是**改写**而非逐字,
   合法改写被误判为"不可溯源"。自测能过是因为正例样本用了逐字文本——**自测太容易**。
   ⇒ **① 在全量前必须换成语义级溯源(异源判官或 embedding),现在的数字不能用来下结论。**

8. **金标 tier-1 键碰撞面广。** 8/15 题的 `source_chunk` 被 2–3 个年份共用,
   legacy bank 以裸 chunk 为 key ⇒ 这些题最多一个年份能拿到正确 rubric
   (与 `2026-07-30-复合qid唯一性与E索引权威审计.md` 的结论一致,本棒在金标侧复现)。

---

## 10. 诚实边界(未做/未证)

- ❌ **BI 聚合端到端未验**:`/api/v1/bi/*` 403 Admin,未提权;
  `product_behavior_store.user_id` 存 `auth_*` 还是 `qa_eval_army_*` **未知**。
- ❌ **bypass 效力未证**:test2 不计费,正负对照不可判别。生产侧未测(也不该测)。
- ❌ **legacy vs pgo 未比**:本轮只读确认 pgo `production_authorized:false`、
  legacy 179/174 qid、pgo 已带年份前缀;**未做 bank 文件逐点比对**(时间用在了 live/offline 主线)。
- ❌ **①P/R 未校准**(见 §9.7),数字仅作方差观察,不作质量结论。
- ⚠️ 样本量 = 2 题 × 3 学生;live 每格 n=1,offline 每格 n=2。**不做统计显著性声称。**
- ⚠️ 高档样本泄漏度 0.85+,粗档"高"这一臂天然易过。

---

## 11. 数据来源路径(可复查)

| 内容 | 路径 |
|---|---|
| 金标 | `<scratchpad>/gold_pack/student_army_grading_gold.v1.json` |
| 干净题筛选 | `<scratchpad>/eval_army/01_cohort_select.py` → `screen.json` / `leakage.json` |
| 账号开设 | `<scratchpad>/eval_army/02_provision_identity.py` → `identity.json` |
| 身份/钱包查库 | `<scratchpad>/eval_army/03_identity_db_evidence.py` → `identity_evidence_{before,after_bypass_control,after_all}.json` |
| bypass 对照 | `<scratchpad>/eval_army/04_bypass_control.py` → `bypass_control.json` |
| live 臂 | `<scratchpad>/eval_army/05_live_arm.py` → `live_turns.jsonl` / `live_arm.json` |
| offline 臂 + 公平 SHA | `<scratchpad>/eval_army/06_offline_arm.py` → `offline_grades.jsonl` / `fairness_baseline.json` |
| 指标 + 自测 | `<scratchpad>/eval_army/07_metrics.py`(`--self-test`)→ `metrics.json` |
| live 指标 | `<scratchpad>/eval_army/08_live_metrics.py` → `live_metrics.json` |
| 判分核心 | `deeptutor/capabilities/deep_question.py:2473-2681` |
| rubric 组装/判分 prompt | `deeptutor/services/construction_grading/rubric_grader_v1.py:1669`(`_batch_prompt`)、`:2140`(`derive_rubric_from_stem_async`) |
| 编译 bank(legacy) | `deeptutor/services/construction_grading/runtime_supply/v_case_rubric_scored/case_rubric_scored.json` |
| BI 排除谓词 | `deeptutor/api/routers/bi.py:48,230-250`;`deeptutor/services/member_console/service.py:2055-2169` |

`<scratchpad>` = `/private/tmp/claude-501/-Users-yehongchen-orca-workspaces-deeptutor-gar/40e1ec6d-a9a2-4eed-8a30-9e2df19c1493/scratchpad`

---

## 12. 结论:全量(15×10)**不建议现在放行**

**NO-GO,三条硬理由:**

1. **测的东西还没对准。** live 与 offline 走不同 tier,结论相反(排序一致性 12/12 vs 1/6)。
   全量前必须先决定**要评的是哪条路径**;若评的是用户真实体验,就得全部走 live,
   而 live 目前 4/6 满分兜底,**先修 reachability 再评,否则评的是 bug 不是质量**。
2. **主力指标 ① 未校准**(逐字 vs 改写),现在放全量 = 花 150 样本的钱买一个不可信的数。
3. **BI 混入未闭环**:`public.users` 每个军团账号留一行三臂皆不排除的孤儿行;
   150 样本要开的账号更多,孤儿行会成比例增加。

**放行前置(建议顺序):**

- P0 修 `auth_<24hex>` 孤儿行(或给 BI 加 alias 表 join),再跑一次 §3 谓词确认 0 可见行。
- P0 定位 live 臂 4/6 满分的兜底路径(为什么没落 tier-3 却给满分),这是产品级病。
- P1 指标 ① 换语义级溯源 + 用**改写过的**正例重做自测(现自测太容易)。
- P1 低档格子 n≥3(实测 Δ 达 19.3%);高档格子因天花板效应 n=1 即可。
- P2 若要评 KB grounding,**只能在 live 臂**做 `LUBAN_STEM_RUBRIC_KB_GROUNDING` A/B,
  判别位=「未核到教材出处」计数,且必须走灰度而不是直接翻生产 flag。

**可以先放的最小增量**:同队列 2 题扩到 **6 题 × 3 学生 = 18 live 轮**做 reachability 复现,
成本可控,不动全量。
