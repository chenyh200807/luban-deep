# 系统成熟度 B 类项实现计划骨架

> **本文档是只读核验产物**——它提供 B 类项的实现计划**骨架**（目标 / 非目标 / 阶段 / 验收 / 碰不碰生产），不在本次提交内落地任何代码或基础设施改动。
> **日期**：2026-05-30
> **状态**：v1（骨架，待按项细化为独立 PRD/实施计划后排期）
> **来源**：2026-05-30 系统成熟度审计（12 维 0-5）backlog 中的 B 类项。
> **纪律**：AGENTS §3 Surgical Changes、§5 根因、单一权威；**绝不碰生产 / 不翻 flag / 不 apply 迁移**。B 类项普遍需要碰生产基础设施或跨域规划，故本文档只产出规划骨架。

---

## 0. B 类定义与共性

B 类 = **需要跨域 scope 定义或生产基础设施规划**的成熟度项。共性：

- 不是单文件能落地的代码改动；先要架构 / 容灾 / 监控规划。
- 多数最终会**触碰生产**（横扩、PITR、Prometheus sidecar、Aliyun 部署），因此**任何执行阶段进入生产前都必须单独授权**，不进入自主 workflow。
- 每一项最终应拆为独立 PRD + 实施计划文件，挂到 `docs/plan/INDEX.md` 对应主线后再排期。

本批覆盖 backlog 中三项 B 类：M11（M1-M4 横扩 / migration strategy + naming audit）、M12（Supabase PITR + 备份校验）、M13（Prometheus 真实实时指标）。

---

## 1. M11 — M1-M4 横向扩展（migration strategy + naming audit）

**klass**：B　**scope**：架构规划；多学科 roadmap（M5 nominal）

### 目标
- 把现有"安全迁移"能力（M1 测试策略 / M4 配置模式）扩展到**第二个学习领域**（鲁班 construction 之外的第二学科）。
- 产出可执行的跨域 scope 定义：哪些是领域无关的共享 spine，哪些必须按学科分叉。
- 完成命名审计（naming audit）：识别当前隐式绑死单一学科（"luban"/"construction"等）的命名，给出领域中性化或显式分层方案。

### 非目标
- 不在本计划内引入第二学科的真实数据 / 题库。
- 不重写现有 runtime 执行壳（保持 chat / tutorbot 两壳现状）。
- 不破坏现有单一权威（`QuestionLifecycleDecision` 等仍是唯一前门裁判）。

### 阶段
1. **盘点**：列出所有"学科耦合点"——schema 命名、配置 key、skill pack 命名、迁移脚本中的硬编码学科常量。
2. **scope 切分**：把耦合点分类为〔领域无关 spine / 必须分叉〕，输出决策表。
3. **命名审计与方案**：对绑死单一学科的命名给出中性化建议（不立即改，只规划），评估 blast radius。
4. **迁移策略**：定义第二领域接入时的 migration 顺序、向后兼容、回滚路径（沿用 M1 测试策略 + M4 配置模式）。
5. **拆分**：把上述输出落成独立第二学科 PRD + 实施计划，挂 INDEX 后排期。

### 验收
- 决策表覆盖全部已盘点耦合点，每点有〔共享/分叉〕裁定 + 理由。
- 命名审计给出 blast radius 与最小改动方案，不含实际改名 diff。
- 迁移策略含可回滚步骤与测试门（沿用既有 migration 测试模式）。

### 碰不碰生产
- **不碰**。M11 全程是架构规划 + 文档产物，不动 schema、不 apply 迁移、不部署。后续真实接入第二学科时才触及生产，届时单独立项 + 授权。

---

## 2. M12 — Supabase PITR 与备份校验

**klass**：B　**scope**：基础设施；容灾；Supabase provisioning

### 目标
- 把 INDEX.md 已记录的 roadmap 项（M5 nominal）落成可执行计划：启用 Supabase Point-In-Time Recovery（PITR）+ 建立**备份恢复演练**（restore drill）。
- 在启用前完成生产基础设施规划：保留窗口、成本、RPO/RTO 目标、演练 runbook。

### 非目标
- 不在本计划内**实际启用** PITR（涉及生产计费档位变更 + provisioning）。
- 不替换现有备份方案，只在其上叠加 PITR + 校验。
- 不把恢复演练接入自动 workflow（恢复操作必须人工指挥）。

### 阶段
1. **现状基线**：确认当前 Supabase 计划档位、是否已有自动备份、现有 RPO/RTO 实际值。
2. **目标设定**：定义 RPO/RTO 目标、PITR 保留窗口、成本预算。
3. **演练 runbook 草案**：写"从 PITR 恢复到隔离实例 → 校验数据完整性 → 比对关键表行数/校验和"的 dry-run 步骤（先在非生产实例验证）。
4. **启用前 gate**：列出启用 PITR 必须满足的前置条件（计费授权、回滚预案、监控接入）。
5. **拆分**：落成独立容灾 runbook + 实施计划，挂 INDEX。

### 验收
- RPO/RTO 目标明确且与成本预算匹配。
- 恢复演练 runbook 可在**隔离实例**上完整跑通一次（不动生产），有数据完整性校验步骤。
- 启用 gate 清单完备，含计费档位变更的人工授权项。

### 碰不碰生产
- **规划阶段不碰**。恢复演练必须在**隔离 / 非生产实例**上执行。
- **真实启用 PITR = 碰生产**：涉及计费档位与 provisioning 变更，**必须单独授权、单独 PR、不进入自主 workflow**。本骨架仅到"启用前 gate 就绪"为止。

---

## 3. M13 — Prometheus 真实实时指标埋点

**klass**：B　**scope**：可观测性；监控；基础设施

### 目标
- 把 INDEX.md roadmap 项（M1 real Prometheus）落成计划：从当前"非真实时"指标升级为**真实 Prometheus 实时埋点**。
- 完成设计 + sidecar 方案 + Aliyun 部署规划（Aliyun-specific deployment planning 是前置）。

### 非目标
- 不在本计划内部署 Prometheus / sidecar（涉及 Aliyun 生产部署）。
- 不新增第二套观测权威——必须复用现有 observability 主线（ARR/AAE/OA/OM、trace、launch-readiness 面板）的指标定义，只补"真实实时"采集后端。
- 不替换现有 launch-readiness 面板的指标语义。

### 阶段
1. **现状缺口**：明确当前指标"非真实时"的具体表现（采样延迟 / 聚合方式 / 缺失的实时指标）。
2. **指标对齐**：把要实时化的指标对齐到现有 observability 权威定义，避免重复定义。
3. **采集设计**：选型（Prometheus client 埋点 vs sidecar exporter），定义 metric 命名 / label 基数预算。
4. **Aliyun 部署规划**：sidecar / exporter 在 Aliyun 上的部署形态、网络、抓取间隔、存储；严守 `/root/deeptutor` 写边界。
5. **拆分**：落成独立 observability 实施计划，挂 INDEX。

### 验收
- 实时化指标清单逐项映射到现有 observability 权威定义（无新增第二权威）。
- 采集设计含 label 基数预算（防 cardinality 爆炸）与抓取间隔。
- Aliyun 部署规划明确写边界（仅 `/root/deeptutor`）与回滚路径。

### 碰不碰生产
- **设计 / 规划阶段不碰**。
- **真实埋点 + sidecar 部署 = 碰生产 / 碰 Aliyun**：必须严守 AGENTS §3.7 Aliyun SSH 写边界（只允许写 `/root/deeptutor`），单独授权、单独 PR，不进入自主 workflow。本骨架仅到"采集设计 + 部署规划就绪"为止。

---

## 4. 共同执行纪律（三项通用）

- 每一项最终拆为**独立** PRD + 实施计划文件，命名 `YYYY-MM-DD-<domain>-<topic>-<type>.md`，挂 INDEX 后排期。
- 任何"进入生产 / 翻 flag / apply 迁移 / 改计费档位 / Aliyun 部署"的阶段，**一律单独授权、单独 PR**，绝不在自主 workflow 内执行。
- 不新增第二权威：M11 沿用现有 lifecycle/单一权威，M13 沿用现有 observability 指标定义，M12 在现有备份方案之上叠加。
- 规划产物先在隔离环境 / 文档层验证，再谈生产。

---

*待挂 `docs/plan/INDEX.md`：M11 建议挂「生产部署」或新「多学科横扩」主线；M12 挂「生产部署」；M13 挂「Observability 与 release gate」主线；本文档不直接修改 INDEX 以避开并发冲突。*
