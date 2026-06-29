# 观测体系生产化加固 — 执行记录（2026-06-29）

- **类型**：根因驱动的修复执行（4 家族专家 + 1 指挥官 root-cause，再 P0/P1 落地）
- **分支**：`feat/observability-production-hardening`（基线 origin/main `e58e36cb0`；clean-baseline 已对齐到前进后的 `9be4bde82`）
- **状态**：`P0 + P1 Done，clean-baseline 验证全绿，未合并`
- **关联**：评估见会话「鲁班智考 eval 观测体系评估」；方法论 `root-cause-debugging` + `eval-design`

## 1. 病因命名（指挥官终裁：1 主病 + 1 独立内容真相病）

- **主病（第一性，不含模块名）**：*观测体系有全部零件，从未通电成一个常驻自检的回路*——耐久落点没绑耐久介质、判定没被调度触发、判定的「绿」没有自证有效性。shared shape = `dormant authority` + `unconsumed island`。
- **独立内容真相病**：*正确性的 ground-truth 金标源结构上不存在*（RAG 召回 golden / 出题质量 / 判分真答案 / 客户端行为 inflow）——缺内容不是缺接线，不可 cron 化，**排期不可夹带**。
- 指挥官对「4 家族同源」的证伪：约 70% 真同源（主病），假绿（判定有效性病）与金标源缺失（内容真相病）是被强行套壳的两个不同病，已单列。

## 2. 本次治本（P0/P1，确定性 / 零新框架 / 接通已有件）

| 项 | 根因 | 治本（file） |
|---|---|---|
| **P0-b 持久化** | 唯三 ephemeral 落点 = 唯三绕过 `PathService` 的（dormant authority：插座 `data/runtime` 已挂载，writer 没插上） | `path_service.get_observability_dir()` + `turn_event_log` / `control_plane_store` / `failed_turn_promotion` 的 default 收口到它；删 `/app/tmp` 常量；零新 env/挂载 |
| **P0-a 假绿闸** | borrowed-coverage：闸盯已删的 `_select_legacy_capability`，借全局 marker 覆盖率背书 | 删 `legacy_production_decision_hits` 死指标 + 移除无 emit 的 `production_decider`；加 per-target 存活自检（从活 emit AST 派生 watch-set，任一被计数 role 零 emit → exit 2）。复用 `WRITER_MAP_FILES` AST；反向样板 `check_harness_authority.py:166` |
| **P1 eval 通电** | `run_eval_gate`+`gates.yaml` 0 workflow 消费（dormant authority） | `exam_quality_cross_model` 注册进 `gates.yaml`（已抓 4 起真实回归却没进 gate）；`run_eval_gate` 加 `--category`；`observability-cron.yml`（克隆 `wallet-consistency-cron.yml`，失败=红=GitHub 邮件）+ `process_registry` 登记 |
| **P1 防假红** | `rag_retrieval_quality` 标 quick 但 live-network，CI 无 egress 必 FAIL | 给 rag/web gate 加 `required_paths`（指向未就绪的 golden / node_modules）→ 无资源时自动 DEFER（诚实跳过），就绪后自动激活 |
| **P1 判分 eval 可信度** | 同源裁判 / N=4 / 臂共享金标 | 默认 judge 改异源（`_cross_source_of`）、`--limit` 默认 20、输出方差诚实标注。仅改默认，不建新框架 |
| **P1 部署观测** | shadow 测量手工无触发 | `redeploy_aliyun_fast.sh` 复用既有 SSH hook 追加 `report_control_plane_shadow_hits.py --days 7`，observe-only/non-fatal |
| **加固 C** | report 型 GO 闸无人观测（check_registries_meta 只发现 check_*.py） | `check_registries_meta` `_DISCOVERY` 纳入 shadow report；`registries.yaml` catalog 为 `release_gate` |

## 3. 验证（clean-baseline，最新 main `9be4bde82` + 本改动）

- 全核心测试套件 **88 passed**；治理闸 `registries_meta` / `control_plane_writer_allowlist` / `process_registry` **PASS**。
- P0-a 判别性反例复验：真源 liveness → `None`；删活符号 → **GHOST exit 2**（治本=变红，不再 green-by-omission）。
- P1 防假红硬证据：`run_eval_gate --category quick` 无 KB/无 egress → **exit 0**，rag/web gate **DEFERRED 非 FAIL**。
- 959 行改动**可干净合入最新 main 无冲突**（`#309` 改 TurnEventLog claims 但未碰本改动文件）。

## 4. 剩余（诚实边界）

**加固待办**：legacy 复活静态臂（需 AST 非 regex，否则 `orchestrator.py:451` tombstone 注释会被误报 + governance 测试联动）；`tests.yml` 每-PR `eval-gates` job（改现有 CI，需 CI 环境验证后接）。

**排期（内容真相病 / 大 blast radius）**：RAG 召回 golden 真集 + 出题质量 eval + 判分 held-out 真答案；Supabase 终态迁移（解锁 shadow 进 GitHub cron，退役 SSH hook 过渡）；多 worker 观测扇出（进程内单例，`workers>1` 系统性少计，与持久化正交）；成本对账官方账单 ingestion；客户端行为埋点 inflow（`product_behavior.db` 当前空库）；Langfuse 生产 liveness 门。

**不确定性**：GitHub Actions 真实运行未本地验证（YAML 解析 + 逻辑模拟过，镜像 prod-proven wallet-cron）；SSH hook 需真实部署验证；`construction_grading` 在 `e58e36cb0` 有 pre-existing red（并行 content-truth 重构中间态，非本次范围、非本改动引入）。
