# 鲁班 生产 / Canonical 激活授权决策包（M33-ACT）

> **Status: `Authorization decision package` — 零写、零不可逆动作。本文不执行任何 flip / publish / canonical write / 远端写。**
> 它把"生产 / canonical 激活门"这一类从"待办"变成"一授权即可执行、且可秒退"的状态：逐门列**前置状态、精确 flip 机制、rollback 命令、观测信号、stop conditions、所需授权**。
>
> 父计划：[2026-06-04-luban-grading-engine-master-control-plan.md](2026-06-04-luban-grading-engine-master-control-plan.md) §0.18/§0.19/§0.20（M19B/C/D 生产 default 决策）+ §0.C / §0.26。
> 硬纪律：AGENTS §3.5 Main Merge / §3.7 Aliyun 写边界（唯一可写根 `/root/deeptutor`）/ Single Authority；**production default flip / published registry / canonical learner-truth write / 远端·DB 写永远需用户逐门显式授权**。

## 0. 当前生产态（已核实，2026-06-08）

| 门 | 现状 | verdict |
|---|---|---|
| limited default（`qa_`/`operator_`） | M19C 已授权 + **本地** ON + `/api/v1/ws` TestClient 验证；**未写远端 Aliyun** | local GO / remote 未执行 |
| broad production default | 未开 | **NO-GO** |
| published registry v1 | 仍 `release_candidate`，正式发布未完成 | **NO-GO** |
| canonical learner-truth write | dry-run / preview（`canonical_truth_written=false` 全程） | **NO-GO** |
| 远端 / Aliyun / DB 写 | 仅 M19E 授权包评审，未执行 | 需逐次授权 |

> 全程安全不变量基线（M19C/D + M26/M28/M32）：`production_write_count=0`、`canonical_truth_written=false`、`false_positive=0`、`legacy_equal_rate=1.0`、`non_cohort_default_leak=0`。

---

## 1. 门 G1 — limited default 远端部署（`qa_`/`operator_`）

| 项 | 内容 |
|---|---|
| **前置** | ✅ **已满足**（M19C local GO + 100/300 TestClient drill 全安全）。唯一差：远端写授权 + 目标环境确认 |
| **影响面** | 仅 `qa_`/`operator_` cohort（**非真实学员**）；真实学员仍 legacy |
| **flip 机制** | 在 `/root/deeptutor` 的 compose/.env 设：`LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=true`、`LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_COHORT=qa_,operator_`；`bash scripts/redeploy_aliyun_fast.sh` |
| **rollback（秒退）** | 设 `LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=false` → redeploy；或 env kill；legacy 立即恢复，字节不变 |
| **观测信号** | `fallback_rate`、`failclosed_rate`、p95 latency、`production_write_count`、`canonical_truth_written`、`non_cohort_default_leak` |
| **stop conditions** | 任一 safety invariant ≠ 0 / non-cohort 泄漏 / p95 异常 → 立即 env kill 回 legacy |
| **所需授权** | ①远端写授权（§3.7，仅 `/root/deeptutor`）②**确认目标是 test2 还是真实生产环境** |
| **可逆性** | ✅ 完全可逆（env kill） |
| **执行状态** | ✅ **已在 test2 执行（2026-06-08）**：`/root/deeptutor/.env` 追加 `LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=true` + `_COHORT=qa_,operator_`（备份 `.env.bak.g1`），redeploy 后容器内行为验证：`qa_alice/operator_bob→默认开`、`real_student_42/test_x→不受影响`，contract_guard PASS。**仅 test2，真实生产环境未动。** 回退：设 ENABLED=false 重部署 |

---

## 2. 门 G2 — broad production default（全量真实学员）

| 项 | 内容 |
|---|---|
| **前置** | ❌ **未满足**：①大样本 **LLM-vs-ground-truth 准确率 eval**（当前是 council calibration，非绝对准确率）②GPT5.5 全量 council ③生产**异步/超时/限流**硬化 ④真人 teacher 复核闭环 |
| **影响面** | **所有真实学员**（高风险、广暴露面） |
| **flip 机制** | 需去除 cohort 限制（broad）——**当前不存在安全的 broad flag，前置未满足下不应设置** |
| **rollback** | 同 G1 env kill，但广暴露面下"已发生的错误判分体验"不可完全召回 |
| **所需授权** | 全部前置就绪 + **独立 broad-default go/no-go** + 你显式授权 |
| **建议** | **不做**，直到 G1 远端 soak 稳定 + 准确率 eval 通过 + 独立门评审 |

---

## 3. 门 G3 — published registry v1（生产答案权威）

| 项 | 内容 |
|---|---|
| **前置** | ❌ **未满足**：①source-backed 采分点 **≥50**（当前 counted ~70 但 textbook-verbatim source-backed 仅 ~23，spec 候选未经发布验证）②council-final action gate ③独立 **formal release gate** + rollback pointer |
| **flip 机制** | **不是单 flag**：LLM-assisted compiler → deterministic signer release gate 签发 `status=published`（非 `release_candidate`）的 registry。入口 `deeptutor/services/observability/release_gate.py::build_release_gate_report` |
| **rollback** | registry rollback pointer 回退到前一版本；runtime 经 manifest 指针切换 |
| **代码状态（M33 A 类，2026-06-08）** | ✅ **publish 编排已建，默认全关**：`release_gate.py::publish_canonical_registry` 三重 fail-closed 门（env `LUBAN_REGISTRY_PUBLISH_ENABLED` 默认 OFF + 显式 `authorized=True` + `release_gate_report` 为 PASS *且* TRUSTED）→ `canonical_knowledge_manifest.verify_manifest`（逐 shard 核 on-disk bytes）→ `promote_to_published`（content_hash 不变保 provenance、signature 重绑 `published`、记 `superseded_version`+`published_at`、保留 `rollback_pointer`）。任一门不满足即 refusal，manifest 仍 `release_candidate`。TDD 10 测试全绿（默认关/未授权/gate 非 PASS/STALE/tamper fail-closed/全授权签发 + promote 重复/非候选 raise）、contract_guard PASS。**门状态：「缺代码」→「待授权」**。source-backed 采分点 ≥50 前置已满足（70，见 §0.26.12 M30 / grounded-audit C#11，更正本表上方旧文的 ~23） |
| **所需授权** | owner/用户授权 publish（翻 `LUBAN_REGISTRY_PUBLISH_ENABLED`=true + 传 `authorized=True`）+ 独立 formal release gate 产出 PASS/TRUSTED |
| **建议** | 代码就绪；实际 publish 前仍需跑 formal release gate（产 PASS/TRUSTED report）+ 你逐门授权 |

---

## 4. 门 G4 — canonical learner-truth write（写真实掌握度）

| 项 | 内容 |
|---|---|
| **前置** | ❌ **未满足**：需 **teacher-final 终审** 或 **真实 retest proof** 作为 promotion 权威；独立 truth-write release gate。M32 已证 candidate/simulated 正确**不晋升**，但 canonical 晋升的正向权威不存在 |
| **影响面** | 写真实学员 canonical 掌握度（**近不可逆**，污染学情数据） |
| **flip 机制** | 独立 canonical claim gate（teacher-final / real_retest_proof → 升 claim）；当前全程 `canonical_truth_written=false` |
| **rollback** | claim 版本回退；但已写的 canonical truth 对下游画像的影响难完全召回 |
| **代码状态（M33 A 类，2026-06-08）** | ✅ **生产 override 已建，默认全关**：`learner_state/service.py::write_compiled_learning_truth` 加 env `LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_ENABLED`（默认 OFF）。生产环境默认仍硬挡为 dry-run/preview（`canonical_truth_written=false` 不变量保持），仅显式打开后才落盘；`env_flag` 对非法值 fail-closed 回 default=False；非生产路径不受影响。TDD 5 测试全绿（默认关/显式 false/garbage fail-closed/授权落盘/非生产回归）、contract_guard PASS（`contracts/learner-state.md` 同步登记契约边界）。**门状态：「生产硬挡缺 override」→「待授权」**。注：override 解除的是 write 的生产硬挡（落本地 artifact）；真正写 Supabase canonical 仍需 core-store 写接线 + G5 远端授权（见下） |
| **所需授权** | 显式 canonical-write 授权（翻 `LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_ENABLED`=true）+ teacher-final/real-retest 闭环就绪（**C 类外部依赖，我造不出**） |
| **建议** | 最后做；代码就绪但 promotion 正向权威（真实教师终审 / 真实学员跨时间复测）仍 blocked-on-external |

---

## 5. 门 G5 — 远端 / Aliyun / DB 写（横切）

| 项 | 内容 |
|---|---|
| **边界** | §3.7：唯一可写根 `/root/deeptutor`；任何 rsync/ssh/docker 写必须先证明落在此根内 |
| **机制** | `scripts/sync_to_aliyun.sh`（内置 `CANONICAL_REMOTE_DIR=/root/deeptutor` 护栏）+ `redeploy_aliyun_fast.sh`；本会话已用于 test2 |
| **所需授权** | 每次远端写授权；**生产环境**（非 test2）需单独确认 |
| **建议** | G1 远端部署即走此机制；生产目标必须显式区分 test2 vs prod |

---

## 6. 推荐激活顺序（最小可逆优先；每步独立授权）

```
G1 limited default 远端部署(qa_/operator_, 可逆)
  -> G1 远端 soak 监控(p95/fallback/failclosed/leak, 全 0)
  -> [C类] source-backed 采分点 ≥50 + [B类] live 接线(#6/#7)
  -> G3 published registry(formal release gate)
  -> 大样本准确率 eval + 生产异步/限流硬化
  -> G2 broad production default(独立 go/no-go + 授权)
  -> [独立] teacher-final / real-retest 闭环
  -> G4 canonical learner-truth write(独立 truth-write gate)
```

## 7. 我在未满足前置 + 未逐门授权前**不会做**的

- 不设 broad default、不去 cohort 限制（G2）
- 不签 published registry（G3）
- 不写 canonical learner truth（G4）
- 不写 `/root/deeptutor` 之外任何远端路径（§3.7）
- 不把 test2 验证当作生产已部署

## 8. 现在能立即推进的唯一门

**G1**（limited default 远端部署）——前置已满足、可逆、仅 qa_/operator_。只要你给出：①远端写授权 ②目标环境（test2 / 生产），我即可执行并跑 soak 监控。其余门按 §6 顺序，逐个补前置 + 逐个授权。

---

## 9. M33 A 类代码落地后的逐门就绪复盘（2026-06-08）

> 本会话只做 **A 类自主代码（默认全关、零不可逆动作）**：G3 `publish()` 编排 + G4 生产 override。两者都 TDD（RED→GREEN）、contract_guard PASS、在隔离分支 `feat/luban-g3-publish-g4-canonical-override`（base = 最新 `origin/main`）。**没有翻任何开关、没有 publish、没有 canonical write、没有远端写。** whole-plan verdict 仍 **WEAK-GO**——A 类代码消除了两个「缺代码」缺口，但实际激活仍 blocked-on-authorization / blocked-on-external。

### 9.1 逐门状态矩阵

| 门 | 本会话前 | 本会话后 | 还差什么才能「翻开关」 | 类别 |
|---|---|---|---|---|
| G1 limited default（qa_/operator_） | test2 已激活 | 不变 | 真实生产环境授权 + 目标确认（test2≠prod） | B（待授权） |
| G3 published registry | ❌ 缺代码 | ✅ **代码就绪、待授权** | formal release gate 产 PASS/TRUSTED + 翻 `LUBAN_REGISTRY_PUBLISH_ENABLED` + `authorized=True` + 你授权 | B（待授权） |
| G4 canonical learner-truth write | 🟡 生产硬挡、缺 override | ✅ **override 就绪、待授权** | teacher-final / real-retest 闭环（**外部**）+ 翻 `LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_ENABLED` + 你授权 | B 待授权 **且** C 外部 |
| G2 broad production default | ❌ NO-GO | 不变 | 大样本 LLM-vs-ground-truth 准确率 eval infra + GPT5.5 key + 生产异步/限流硬化（**全外部**）+ 独立 go/no-go + 你授权 | C（外部） |
| G5 远端 / Aliyun / DB 写 | 就绪（test2 用过） | 不变 | 每次远端写授权 + 生产目标确认（§3.7：唯一可写根 `/root/deeptutor`） | B（待授权） |

### 9.2 G3 翻开关精确机制 / rollback / 观测 / stop / 授权

- **精确机制**：调用 `publish_canonical_registry(manifest, supply_root, release_gate_report=<PASS/TRUSTED report>, authorized=True, published_at=<iso>, superseded_version=<prev>)`，并设 env `LUBAN_REGISTRY_PUBLISH_ENABLED=true`。三门 + verify_manifest 全过才返回 `{published: True, manifest: <published>}`。
- **rollback（秒退）**：设 `LUBAN_REGISTRY_PUBLISH_ENABLED=false`（后续 publish 立即 refusal）；已签 published manifest 经其 `rollback_pointer` 回退到前一版本，runtime 经 manifest 指针切换；`superseded_version` 提供 supersession 审计链。
- **观测信号**：`published`(bool)、`reason`、`manifest.content_hash`（须 == release_candidate 的 hash）、`manifest.signature`（须重绑 published）、`superseded_version`。
- **stop conditions**：verify_manifest 任一 shard hash 不符 → refusal；release gate 非 PASS/TRUSTED → refusal；任一安全不变量异常 → 不 publish。
- **所需授权**：①formal release gate 跑出 PASS/TRUSTED ②你显式授权翻 flag + 传 `authorized=True`。

### 9.3 G4 翻开关精确机制 / rollback / 观测 / stop / 授权

- **精确机制**：生产环境设 env `LUBAN_CANONICAL_LEARNER_TRUTH_PRODUCTION_WRITE_ENABLED=true`，则 `write_compiled_learning_truth`（经 `synthesize_learning_truth(dry_run=False)`）落盘 canonical truth；否则默认 preview 不落盘。
- **rollback（秒退）**：设 flag=false / 删除该 env → 立即回 dry-run/preview，`canonical_truth_written` 不变量恢复。
- **观测信号**：`canonical_truth_written`、`production_write_count`、`COMPILED_TRUTH.json` 是否生成。
- **stop conditions**：`canonical_truth_written` 在未授权前必须恒为 false；false_positive ≠ 0 / 画像异常 → 立即 flag=false。
- **所需授权**：①teacher-final 终审 / 真实学员跨时间复测证据链就绪（**C 类外部，我造不出**）②你显式授权翻 flag。真正写 Supabase canonical 还需 core-store 写接线 + G5 远端授权。

### 9.4 诚实 go/no-go

- **已到「待授权」（代码一翻即可执行、可秒退）**：G1（生产目标确认）、G3（+ formal release gate）、G5。
- **仍 blocked-on-external（我造不出，不得伪造凑 GO）**：G2（准确率 eval infra + ground-truth 标注 + GPT5.5 key + 生产异步/限流硬化）、G4 的 promotion 正向权威（真实教师终审 / 真实学员跨时间复测证据）。
- **whole-plan verdict：仍 WEAK-GO**。本会话改善的是 WEAK-GO 的构成（消除 G3/G4 两个「缺代码」缺口），不抬升整体裁决——任何 GO 都需先补外部依赖 + 逐门授权实际执行，且本会话 `production_write=0 / remote_write=0 / default_flip=0 / published=false / canonical_truth_written=false` 全部保持。

### 9.5 codex 对抗审查（独立第二意见，2026-06-08）

对 G3/G4 commit 跑 codex 独立对抗审查（fail-closed / 默认全关标准），发现并已修复 3 项缺口：

- **[已修 CRITICAL]** `verify_manifest` 只比对 shard 自报 content_hash、不重算 records bytes（docstring 称 "against live bytes" 与实现不符）→ `publish_canonical_registry` 加 defense-in-depth：对每个 records-based shard 调既有 `verify_lane_bundle`（重算 records hash + 验签名），records 篡改即 refusal `shard_content_tamper`。新增真实 records-tamper 测试（原 tamper 测试只改自报 hash，是 false-green）。
- **[已修 HIGH]** publish 授权用真值性判断（truthy 字符串如 `"false"` 会通过）→ 改严格 `authorized is not True`，新增非 bool 授权负向测试。
- **[已修 HIGH]** `promote_to_published` 用常量 `NAMESPACE` 重签但保留 caller namespace → 加 `namespace == NAMESPACE` 校验，foreign namespace raise，新增测试。
- **[设计边界，不扩散]** `promote_to_published` 是纯确定性函数（不碰 env/disk），公开供编排 + 测试调用；授权门在 `publish_canonical_registry`，且 published manifest 落盘 / 被 runtime 消费仍需 G5 远端写授权——单独调 promote 得到 dict 无法激活。
- **[既有债，待独立处理]** manifest signature 只绑定 content_hash/namespace/status，不覆盖 rollback_pointer/version 等元数据（既有 `build_manifest` 设计）；属 ops 风险（回退指向错误）非签发绕过，扩大 signature 覆盖面需改 build/verify + 既有测试，单独任务处理。

复验：G3/G4 共 23 测试全绿（含新增 records-tamper / 非 bool 授权 / foreign namespace 负向）、contract_guard PASS。
