# 2026-06-11 上线前根因加固 + 部署 + 并发撞车 复盘

> 一句话：一次"上线前系统性代码审查 → 根因修复 → 合并 main → 部署阿里云"的完整复盘。
> 真正坏掉的不是某个 bug，而是**几类被掩盖的系统性缺陷**（无 Python CI 门、fail-open 安全默认、import 期副作用、并发发布无协调）。
> 配套沉淀见 [aliyun-deploy.md](../zh/guide/aliyun-deploy.md) 已知坑 **#11 / #12**。

## 背景

上线前做系统性代码审查，发现一批问题。本次把它们收敛成 **6 个根因簇**修复，而不是逐条打补丁。修复过程中又因为推到 `main`、部署阿里云、与并发进程撞车，暴露出更多"被前一个门遮住"的问题。本文按"做了什么 → CI 门连锁 → 部署事件 → 可迁移教训"四段记录。

## 一、根因修复（6 簇，治本不治标）

| 簇 | 一等业务事实 | 修法类型 | 阻断性 |
|---|---|---|---|
| 1 NameError 整类（F821） | 冷/死代码路径能进 main，因为**Python 没有任何 CI lint 门**（`tests.yml` 只跑 `npm run lint`，ruff 只在本地 pre-commit） | 加**一个** CI 门 `ruff --select F821,F811`（举一反三防整类）+ 修 `cloud_provider.py` 缺 `import os` 等真实实例 | 非阻断但是地雷 |
| 2 semantic_router 重复死权威 | `apply_question_object_transition` 是 live 函数 `apply_active_object_transition` 的**从未接线副本**，引用 3 个从未定义的 helper，零调用方 | **删除（收权）**，不是补全——补全会造第二套 authority（违反 §5.7） | 死代码，删之 |
| 3 WS 边界 | `/api/v1/ws` wrapper 擅自枚举"哪些异常算致命"，其余逃逸 → 杀整条连接 | thin wrapper 只做边界：单 turn 错误→error 事件+continue；`CancelledError` 重抛不吞 | **是**（瞬时错误断连） |
| 4 photo_answer | 外部边界缺输入上限；崩溃恢复裸 SQL 绕过 store 守卫；付费 OCR 端点无限流 | Pydantic `max_length`；`recover_stale_job` + `status='running'` 守卫；复用既有 `route_rate_limit` | flag OFF，灰度前修 |
| 5 生产环境 fail-open 后门 | "本进程是否被授权用危险能力"被错编码为"production 检测的反面"，而 production 检测 `default="local"` 默认 fail-**open**；attempt_refs/deploy 脚本还各维护一套漂移的 production 定义 | `is_production_environment()` 反转为 **fail-closed**（未知/拼错/staging→生产）+ 统一三套定义 + `tests/conftest.py` 钉测试默认 `local` 保 §264 QA | 高（需用户拍板） |
| 6 杂项治本 | 打包 contract index 落后于权威 repo 根（运行时加载 stale）；`loop.py` `dict.get(k,{})` 在值为 None 时崩 | re-mirror；对齐周边正确写法 `(get(k) or {})` | 真 bug，修之 |

### 测试地基分诊（关键方法）

全量 `pytest` 109 failed。**不要直接信全量红**——逐个 `pytest <file> -q` 单独跑：

- **107/109 = 隔离污染 / 环境依赖**（66 个 orchestrator 测试单文件全绿；共享单例 / `env_store` 读 `.env` / LLM config cache 跨用例不重置）。非阻断，属测试 infra 债。
- **真问题极少**：contract index mirror 漂移、`loop.py` None 崩；外加 2 个**测试债**（canonical `active_object` 形状是 `{object_type,object_id,state_snapshot}`，测试用了过时形状；billing 默认走 internal-beta 路径而测试只 mock 了 wallet ledger）——**没有为迁就错测试去改对代码**。

详见记忆 `full-pytest-suite-has-isolation-pollution` 与 `env-store-reads-dotenv-monkeypatch-delenv-cannot-clear`。

## 二、CI 门连锁（push 后才暴露的连环，容易打地鼠）

改了 protected 文件后，CI 的 `Contract Guard` job 里多道门**逐个被前一个遮住**，修好一个才暴露下一个：

1. **`contract_guard`**：改 `unified_ws.py` / `attempt_refs.py` 这类 protected 文件，commit 必须同时含该 domain **已登记的**测试。新测试要先登记进 `contracts/index.yaml` 的 `domains.<域>.test_files` 并 re-mirror 到 `deeptutor/contracts/index.yaml`。**本地必须带 changed files 跑**：`check_contract_guard.py $(git show --name-only HEAD)`，不带参数测不出 protected/domain 关系。
2. **`Secure router fail-on-new`**：新增 import 会**移动** bare `APIRouter()` 行号，门按 `file:line` 精确比对基线 → 误报为"新"。刷新 `scripts/ci/baselines/secure_routers_baseline.txt`。
3. **`Import Check`**：裸 `python -c "import ..."`（无 `.env`、无 secret）。fail-closed 把"未设环境"判成生产，于是 `attempt_refs` 在 **import 期**跑的 `_secret()` 直接 `RuntimeError` 崩。

**教训**：改 protected 文件后，push 前按顺序本地跑全套门（见 [aliyun-deploy.md 已知坑 #11](../zh/guide/aliyun-deploy.md)），别等 push 上去逐个红。

### import 期副作用 + fail-closed（最隐蔽的一处）

`attempt_refs.py` 在 import 时跑 `_log_secret_fingerprint() -> _secret()`。这在旧逻辑下没事（旧 `_is_prod_runtime` 只看 2 个 env，CI 里都没设 → 非生产 → 不 raise）。fail-closed 改完后，未设环境=生产+无 secret → **import 就炸**，连带任何裸 import 该模块的 CLI/脚本/CI 都炸。
**根因是"import 期可 raise 的副作用"，不是 fail-closed 本身。** 修法：把强制**延迟到使用时**——import 期诊断容忍缺 secret（只告警），`_secret()` 真正签名/校验时仍 fail-closed。本地能蒙混是因为开发机 `.env` 带 `SERVICE_ENV=development`，`env_store.load()` 把它 `setdefault` 进 `os.environ`，让 `runtime_environment()` 误判非生产。

## 三、部署 + 并发撞车事件

时间线（同一台 `Aliyun-ECS-2:/root/deeptutor`，公网 `test2.yousenjiaoyu.com`）：

1. **04:34** 部署 `f19c1d54`（本次根因修复），公网 `front/healthz/readyz` 全 200，`validate_aliyun_release_env.sh` 确认 `SERVICE_ENV=production`，成功。
2. **后续** 应"部署最新 main"。`main` 已被**并发 codex 进程**推进到更新的 `be971a14`（领先 4 个 commit：安全加固 / docs / msgpack pin / readme），且工作区有大量**外部未提交 WIP**（含 Dockerfile、compose、capabilities）。
3. 按 §发布硬护栏 §19 用**干净 worktree** 发布，避免脏 `main` 把外部 WIP 带上生产。
   - `git worktree add --detach <sha>` → 被脚本拒：**`无法识别当前分支；禁止在 detached HEAD 直接发布`**（见 #12）。
   - 改用具名分支 worktree → 进到 docker build → **build 中途 SSH 断**（`Connection reset by peer` / `Broken pipe`，`EXIT 255`）。
4. 期间**并发 codex 进程**也在部署 `be971a14`（`docker compose up --force-recreate` 真正生效的是它）。两条发布同时对同一台机器发布，互相覆盖磁盘、抢 SSH。
5. 我中断的部署一度把磁盘 rsync 回**旧** `d59cd37c`，留下"磁盘旧、容器新"的隐患；随后被 codex **06:49 的 `be971a14` 重新同步自愈**。
6. **核实最终状态**（不能假设"我发的就是最后生效的"）：
   - 最新 release manifest `20260611T064907Z_main_be971a14`（晚于我的 06:38）。
   - 磁盘 sentinel（`README.md` md5）= `be971a14` 版本。
   - 运行容器 / `.env` lineage / origin/main = `be971a14`，全部一致。
   - 公网探针全程 200，**零停机、零回退**。

结论：**"最新 main 上生产"已达成**——由并发 codex 部署完成，我的 `d59cd37c` 尝试被正确取代，无残留危害。

## 四、可迁移教训（按 AGENTS §5.5 提炼）

### 1. 这次真正的一等业务事实

不是"修几个 bug"，而是**几条"默认就错"的系统性事实**：
- 没有 Python CI 门 → 整类 NameError 能进 main。
- 安全开关默认 **fail-open** → env 漏设就敞开后门。
- 用 import 期副作用做强制 → 一改默认就炸所有裸 import 路径。
- 并发发布**无协调机制** → 撞车靠运气自愈。

### 2. 之前为什么把问题想窄了

- 把"全量测试红"当成"系统坏了"，差点漏掉藏在污染里的真 bug，也差点把测试债当真 bug 去改代码。
- 把 fail-closed 当成"只改一个函数"，没预见到它会经 import 链炸 CI Import Check（code-reviewer 其实标了 MEDIUM，被低估）。
- 默认"我发的就是最终生效的"，忽略了同一台机器有并发发布。

### 3. 更符合 first-principles / less-is-more 的通用思路

- **用一个门防一整类**，别逐个修实例（F821 CI 门 > 逐个补 import）。
- **危险能力授权要 fail-closed + 显式**，别用"环境检测的反面"做隐式开关；同一事实只留一套 authority（消灭 attempt_refs / deploy 脚本的漂移定义）。
- **强制放在使用时，不放在 import 时**；import 期只做无副作用的纯定义。
- **同一时间只允许一条发布**；多 agent/多人协作时，发布前确认无其他发布在跑，发布后用 **manifest 时间戳 + 磁盘 sentinel md5** 核对最终落到哪个版本。
- **改对的代码 ≠ 让错的测试变绿**；预存在失败先判"真 bug / 测试债 / 环境"，再修对的那一层。

### Actionable 清单（下次照做）

- [ ] 改 protected 文件 → push 前本地跑：`check_contract_guard.py $(git show --name-only HEAD)`、`FAIL_ON_NEW=1 check_secure_routers.sh`、`ruff --select F821,F811`、`DEEPTUTOR_ENV=production python -c "import <顶层模块>"`。
- [ ] 任何非 `local/dev/test/ci/eval` 环境（含 env 漏设）= 生产；生产 `.env` 必须有 `DEEPTUTOR_AUTH_SECRET` + `DEEPTUTOR_ATTEMPT_REF_SECRET`。
- [ ] 发布只从**干净具名分支 / worktree**，不用脏 `main` + `ALLOW_DIRTY_DEPLOY` 夹带 WIP，不用 detached HEAD。
- [ ] 发布前确认没有其他发布在跑；发布后用 manifest 时间戳 + sentinel md5 核对最终状态。
- [ ] 全量测试红先分诊（单文件隔离跑），别直接当回归。

## 五、最终状态

- `origin/main`：`f9db1cce`（本复盘文档）；生产运行 `be971a14`（最新 main，健康），磁盘/容器/lineage 一致。
- 本次共 5 个加固 commit 上 `main`：`f19c1d54`（根因修复，已部署）→ `4d672d13`（contract 登记）→ `f33c8329`（secure-router 基线）→ `bbc03d7f`（import-safety）→ runbook 文档（`6feee55c` #11 / `f9db1cce` #12）。
- 未解决（非本次 scope）：`Yousen Checks::test_package_chat_longpress_selectable`（`loadSubpackage:fail` harness 问题，pre-existing，基线 commit 即红）、`Deploy Gate`（长期 9–10s 快速失败，pre-existing）。
