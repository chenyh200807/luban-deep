# 2026-05-30 系统成熟度审计报告

- **类型**: Maturity Audit（operational/production maturity，非 bug 审查）
- **方法**: workflow 36 agent，12 维 × 0-5 等级 + 2-lens 对抗验证（默认质疑高估），纯只读
- **HEAD**: `3075c243`
- **状态**: `Done`（审计完成）；接线实施批见 PR #85（CI 门禁 W2/W3/W6）+ #86（runtime W4/W5）

---

## 执行摘要

> **整体 ≈ L1.67/5（5 个 L1、6 个 L2、1 个 L3）——"能跑，但运维成熟度低"。** 功能正确性已被上一轮质量审计修到位；本审计评的是生产/运维成熟度，结论是：**基础设施"建好了但没接线"，纪律"写成文档/脚本但无强制门"。** 好消息——地基（埋点/脚本/契约/备份原语/幂等 RPC）都在，成熟化主要是"接线"而非"重建"，ROI 高。

最拖后腿 3 维：**M6 发布安全 / M9 测试网 / M11 事故就绪（均 L1）**。唯一强项：**M3 幂等一致性（L3，扣费 DB 层原子 RPC+唯一索引+CHECK 教科书级）**。

## 成熟度记分卡

| # | 维度 | 当前 | 目标 | 一句话证据 |
|---|---|:--:|:--:|---|
| M1 | 可观测性 | L2 | L4 | /metrics 体系完整但 readiness/release 控制面**永不接线**(NOT_RUN)、告警仅 `.example.yml`、Langfuse 生产 OFF |
| M2 | 依赖韧性 | L2 | L4 | 熔断/冷却只在 LLM 一链；supabase/embedding/rerank 只 try/except→空；breaker 进程内不跨 worker |
| M3 | 幂等一致性 | **L3** | L4 | 扣费 DB 层原子 RPC+唯一索引+CHECK，但 FF OFF 生产零验证、Σdelta 对账未接 CI |
| M4 | 容量扩展 | L1 | L3 | 瓶颈写成 2 份好文档但缓解代码 0 行；单 worker+单 asyncio.Lock 串行化全部 DB 写；无压测基线 |
| M5 | 数据可恢复 | L2 | L4 | 文件态 SQLite 有 CI backup/restore；Supabase 权威数据(钱包/学情)无备份/PITR/演练；migration 无 down |
| M6 | 发布安全 | **L1** | L4 | prod 走笔记本 SSH，无 'deploy needs green CI' 关卡，CI 红也能发；docs/** 直推绕过门禁 |
| M7 | flag 治理 | L2 | L4 | 有分级 cohort 机器+默认安全，但灰度无强制门(_STAGE 可越级)、FF 快照漏最高杠杆 flag |
| M8 | 配置密钥 | L2 | L4 | EnvStore 单读取层好，但 283 处 os.getenv 散落、必填 env 断言是孤儿脚本、.env.example 漂移 51 键 |
| M9 | 测试网 | **L1** | L4 | 334 测试文件但 CI 只跑手挑 smoke、无覆盖率门禁、RAG golden 占位假绿、~280 test 不在 CI |
| M10 | 安全运维 | L1 | L4 | 非 root+SHA-pin 不错，但无 lockfile/hash、base 镜像可变 tag、漏扫只本地、audit 表可自篡改 |
| M11 | 事故就绪 | **L1** | L4 | 只有计费 runbook；告警/on-call/SLO 全停在 example+计划；backup/restore drill 可长期 NOT_RUN |
| M12 | 架构成熟 | L2 | L4 | 单入口契约确立，但第二实现**"隐藏而非回收"**(legacy chat.py 死传输、双 utils drift、两端前端复制)、无 drift 门禁 |

## 5 大系统性根因

1. **"控制面建好但没接线"**（M1/M5/M6/M11）：`run_readiness_check.py`/`run_release_gate.py`/`run_observability_daily.py` 功能完整但 `.github/` 零调用、生产 `control_plane_store` 永空、`launch_readiness` 恒 NOT_RUN；告警只有 `.example.yml`。闭环没有一段是自动的。
2. **"纪律靠自觉、无强制门"**（M6/M7/M9）：发布不被 CI gate、flag `_STAGE` 可越级跳全量、无覆盖率门禁。规则以文档/脚本存在，但没有不可绕过的执行点。
3. **"最有价值的数据最没守护"**（M5/M3）：文件态 SQLite 有 CI backup/restore；但 Supabase 钱包/学情/测评（权威数据）无备份/PITR/恢复演练，唯一的 Σdelta 不变式还是只读手动工具未接 CI。保护力度与数据价值倒挂。
4. **"第二实现隐藏而非物理回收"**（M12）：legacy chat.py 仍被 import 触发模块级副作用、research/solve 双 token_tracker 已 fork drift、两端小程序 utils 复制漂移——用 flag/不挂载藏，没删。成熟=清理不是藏。
5. **"单实例假设贯穿全栈"**（M1/M2/M4）：进程内 metrics（重启清零）、进程内 circuit breaker（每 worker 各自 trip）、单 asyncio.Lock、无全局 admission。为单实例而建，横向扩展时全部失效。

## 成熟化路线图（三段）

### 🟢 低成本快速提级（本周，接线/补门 → 多维 +1）— 实施中
| 动作 | 维度 | 落点 | 状态 |
|---|---|---|---|
| smoke 改 `pytest tests` 全目录 + test-summary 补 needs.yousen + bandit/pip-audit job + paths 加 docs/** | M9/M10 | tests.yml | W1 待补（workflow schema 失败） |
| deploy-gate workflow（main 必须 CI 绿才可部署） | M6 | deploy-gate.yml | ✅ PR #85 (W2) |
| 钱包 Σdelta audit 每日 cron（drift>0 红） | M3/M5 | wallet-consistency-cron.yml | ✅ PR #85 (W3) |
| flag 快照补全最高杠杆 flag | M7 | release_lineage.py | ✅ PR #85 (W6) |
| 部署后 readiness hook 写 control_plane | M1/M11 | redeploy_aliyun_fast.sh | ✅ PR #86 (W4) |
| 启动期 env fail-fast | M8 | main.py lifespan | ✅ PR #86 (W5) |
| 删 legacy chat.py 死传输 | M12 | routers/chat.py | ⏳ 待做（W5 跳过 part b） |

### 🟡 结构性投资（需排期）
- **M4 容量**：active-turn-capacity 计划落地（全局 admission gate + Postgres session store + 多 worker）+ 混载压测取真实 p95。
- **M1 可观测**：`deployment/observability/*.example.yml` 落成真实 Prometheus+Alertmanager + 直方图分位 + 持久后端 + 生产开 Langfuse + shutdown flush。
- **M5 数据**：Supabase PITR 文档化 + 恢复演练（RTO/RPO）+ migration down 脚本。
- **M2 韧性**：熔断/冷却推广到 supabase/embedding/rerank + Redis 跨-worker breaker。
- **M11 事故**：on-call/SLO/错误预算 + 数据恢复/依赖故障/扩容 runbook + 真跑回滚演练。
- **M10 供应链**：lockfile+hash + base 镜像 @sha256 digest + audit 表 append-only。
- **M12 架构**：双 utils 收敛 shared + 两端前端 codegen 单源 + frontend-parity CI。

### ✅ 已是生产级 / 保持
- **M3 扣费幂等 DB 层**（原子 RPC + 唯一索引 + CHECK 不变式，唯一 L3）。
- 文件态 SQLite backup/restore CI 闭环。
- 非 root 容器(uid 10001) + SHA-pin GitHub Actions。

## 与"全球顶尖产品运维成熟度"的差距

最关键缺的不是代码，是**"强制执行、不可绕过的控制面"**：顶尖产品的 readiness/release gate、observability、flag 灰度、依赖扫描全部是 CI/自动门禁强制的。本系统 infrastructure 全建好了，却停在"脚本 + 文档 + `.example.yml`"。**从"能跑"到"成熟"，差的是把已建好的控制面接进强制流水线（本周可做大半）+ 落地横向扩展假设（需排期）。**

---

*审计 workflow run: `wf_436134f7-724`；接线实施 batch: `wf_928dd0e9-e7f`。*
