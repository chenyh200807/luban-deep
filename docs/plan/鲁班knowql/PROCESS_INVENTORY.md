# 长驻进程 / 定时任务 盘点 (PROCESS INVENTORY)

> Date: 2026-06-13  Scope: **Layer 3 · P2 任务A** —— RESOURCE_GOVERNANCE_FIX_PLAN
> §Layer 3 + INFRA_REGISTRATION_COVERAGE_AUDIT §4。
> 这是**只读盘点**(read-only 盘点),为 `contracts/process_registry.yaml` 的
> grandfather 名单 + `scripts/check_process_registry.py` 扫描器提供依据。
>
> 根因锚点(blast radius):**2026-06-06 的 Next 201.6 GB 事故**——只有 `next dev`
> 有守护(`agent-owned-next-guard.sh`),其余任何长驻 task 一旦泄漏(heartbeat /
> cron / channel sync loop / team worker 不断 `create_task` 不回收)同样能拖垮内存/
> 句柄,且**无登记可审计"现在跑着哪些 daemon、各自归谁、出事怎么停"**。

判别口径:**有机器信号的登记并由扫描器机器确认;拿不准 owner/stop 的标 `needs_verification`。**

---

## 分类(两类机器信号 + 两类可见/受管,共四类)

### 1. GHA cron(可见、版本受控、可审)—— 已登记 scheduled_tasks[]

扫描信号:`.github/workflows/*.yml` 里的 `- cron:` 行。

| workflow | cron | owner | lifecycle | supervised_by |
|---|---|---|---|---|
| `wallet-consistency-cron.yml` | `0 4 * * *` | commerce | 每日钱包投影一致性审计(只读) | GitHub Actions |
| `runtime-drill.yml` | `0 2 * * 1` | platform | 每周备份/恢复演练 | GitHub Actions |
| `hermes-upstream.yml` | `23 3 * * 1` | platform | 每周 Hermes upstream 漂移检查 | GitHub Actions |
| `runtime-ops.yml` | `0 3 * * 1` | platform | 每周运行时资产校验(也跑 push/PR) | GitHub Actions |

### 2. 应用内 always-on daemon(201.6 GB blast-radius 类)—— 已登记 daemons[]

扫描信号(精确,零误报边界):`create_task(...)` 的**结果被存进持久 holder**——
`self._<...>task<...> = create_task(...)` 或 `<obj>.worker_tasks[...] = ... create_task`。
**fire-and-forget(结果丢弃)的 per-request `create_task` 不是 daemon,刻意不在 scope 内。**

| file | type | 信号 | owner | supervised_by |
|---|---|---|---|---|
| `tutorbot/heartbeat/service.py` | daemon | `self._task = create_task(_run_loop())` | tutorbot ⚠️ | TutorBot runtime(`stop()` cancel) |
| `tutorbot/cron/service.py` | scheduler | `self._timer_task = create_task(tick())` croniter | tutorbot ⚠️ | TutorBot runtime |
| `tutorbot/channels/matrix.py` | daemon | `self._sync_task = create_task(_sync_loop())` | tutorbot-channels ⚠️ | channel manager |
| `tutorbot/channels/discord.py` | daemon | `self._heartbeat_task = create_task(heartbeat_loop())` | tutorbot-channels ⚠️ | channel manager |
| `tutorbot/channels/mochat.py` | daemon | `self._refresh_task` + `self._cursor_save_task` | tutorbot-channels ⚠️ | channel manager |
| `tutorbot/channels/manager.py` | daemon | `self._dispatch_task = create_task(_dispatch_outbound())` | tutorbot-channels ⚠️ | channel manager |
| `events/event_bus.py` | daemon | `self._processor_task = create_task(_process_events())` | platform ⚠️ | event bus(stop cancel) |
| `tutorbot/agent/team/__init__.py` | worker | `runtime.worker_tasks[name] = create_task(_run_worker(...))` | tutorbot-team ⚠️ | team runtime(worker_tasks dict) |

⚠️ = `needs_verification`:**SITE 存在性由全仓扫描机器确认(零误报);owner/stop 待 maintainer 确认。**

### 3. 受管 compose 服务(可见、受容器运行时管理)—— 记录于 compose_services,不扫描

`deeptutor` / `searxng` / `valkey`(`restart: unless-stopped`)。无源码信号,运行时受管,
仅为盘点完整性记录,扫描器不查。

### 4. 已知盲区(诚实标 needs_verification + 替代方案)—— registry needs_verification[]

| 信号 | 为何不扫 | 替代方案 |
|---|---|---|
| `agent/loop.py` self-restart `create_task(_do_restart())` | fire-and-forget restart trampoline(结果丢弃,非持久 holder),不匹配 daemon 信号 | 由内存守护(`agent-owned-next-guard.sh` 类)+ 本盘点覆盖,非静态信号 |
| AI-agent-owned python/worker 进程树(201.6 GB 真实形态) | **运行时内存条件,非源码信号**——静态扫描器看不到泄漏的进程树 | plan §4.2:把 `agent-owned-next-guard.sh` 泛化到 python/worker 树。超出本次最小收权 scope;本 registry 让 daemon SITES 可枚举,供这类泛化守护知道"什么是合法长驻" |

---

## 闸门(machine gate)

- **registry**:`contracts/process_registry.yaml`(单一 canonical 清单,同构于
  `schema/db/env/provider_registry.yaml`)。
- **scanner**:`scripts/check_process_registry.py`(挂同一 contract-guard runner;
  pending hunk 待 `check_contract_guard.py` WIP 清干净后并入 main())。
- **CI**:`.github/workflows/tests.yml` 独立步骤 "process registry guard"(在 provider 步骤后)。
- **fail 条件**:(a) 新增未登记 GHA cron;(b) 新增未登记持久 daemon task。
- **实测**:全仓扫描 `cron_lines=4 daemon_sites=9 exit 0`(8 daemon 文件,mochat 含 2 行);
  对合成的新 daemon / 新 cron **真 fail**(负向证明已跑)。零误报。

---

## 一句话总结

> 长驻进程登记 = **收权**(把现状盘进唯一清单 grandfather)+ **同一 contract-guard
> runner**(防新增未登记长驻进程),**绝不建新治理系统**。两类机器信号(GHA cron /
> 持久 daemon task)精确可判、零误报;fire-and-forget per-request task 与运行时内存
> 泄漏诚实标为盲区 + 给替代。
