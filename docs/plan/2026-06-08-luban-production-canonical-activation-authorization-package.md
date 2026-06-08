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
| **所需授权** | owner/用户授权 publish + 独立 release gate 通过 |
| **建议** | 先补 source-backed ≥50（C 类编译工作），再跑 formal release gate |

---

## 4. 门 G4 — canonical learner-truth write（写真实掌握度）

| 项 | 内容 |
|---|---|
| **前置** | ❌ **未满足**：需 **teacher-final 终审** 或 **真实 retest proof** 作为 promotion 权威；独立 truth-write release gate。M32 已证 candidate/simulated 正确**不晋升**，但 canonical 晋升的正向权威不存在 |
| **影响面** | 写真实学员 canonical 掌握度（**近不可逆**，污染学情数据） |
| **flip 机制** | 独立 canonical claim gate（teacher-final / real_retest_proof → 升 claim）；当前全程 `canonical_truth_written=false` |
| **rollback** | claim 版本回退；但已写的 canonical truth 对下游画像的影响难完全召回 |
| **所需授权** | 显式 canonical-write 授权 + teacher-final/real-retest 闭环就绪 |
| **建议** | 最后做；必须独立门 + 真实教师/复测证据 |

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
