# PR-α Runbook — session.owner_key 回填

> **状态**: Implementation Ready / Production Run Pending
> **主线**: [Prelaunch readiness v2.1](../plan/2026-05-25-prelaunch-readiness-checklist.md) §3.7 PR-α / §3.8 跨 SR 关切 #1
> **依赖关系**: 必须在 **PR-1b SR1 行为切换之前** 完成；否则 SR1 把 unified_ws 的 "owner_key 缺失 + anon 放行" 旁路修掉后，真正遗留的老 session 会全部 PermissionError，普通用户也会撞 "Session not found"。

## 0. 目标 / 非目标

### 目标
- 为 SQLite `sessions` 表里 `owner_key IS NULL OR owner_key = ''` 的行补 `"user:{user_id}"`，user_id 来源是 `preferences_json` JSON
- 操作可 dry-run、idempotent、抽样可验证
- 给出在阿里云 prod 上跑的精确步骤 + rollback 路径

### 非目标
- 不修任何业务代码
- 不动 RLS（那是 PR-2 SR2）
- 不处理 orphan sessions（`preferences_json` 既无 owner_key 也无 user_id 的）—— 单独决策

## 1. 单一 Authority

- 回填逻辑权威：`scripts/migrations/pr_alpha_session_owner_key_backfill.py`
- 数据语义对齐 `deeptutor/services/session/sqlite_store.py` 的 `build_user_owner_key()` + `_derive_owner_key_from_preferences()`
- 任何变更必须先改 sqlite_store.py，再同步本脚本，不允许两份逻辑分叉

## 2. 数据语义快照

| 字段 | 类型 | 来源 |
|---|---|---|
| `sessions.id` | TEXT PK | session 创建时分配 |
| `sessions.owner_key` | TEXT DEFAULT `''` | 应为 `"user:{user_id}"`；可能为空（这是本 runbook 要修的） |
| `sessions.preferences_json` | TEXT DEFAULT `'{}'` | JSON 含 `user_id`（可能也含 `owner_key` 显式字段） |

回填优先级（与 `sqlite_store._derive_owner_key_from_preferences` 一致）：
1. `preferences.owner_key` 非空 → 直接用
2. `preferences.user_id` 非空 → `"user:" + user_id`
3. 否则 → **orphan**，跳过 + 记录

## 3. Local Unit Test 证据

```
$ .venv/bin/python -c "..."  # 见 scripts/migrations/_test_backfill.py 或 PR description 内的 inline test
ALL 6 TESTS PASS
  - dry-run 正常分类（already/backfillable/orphan）
  - apply 仅当 --apply 才执行 UPDATE
  - 重复跑 apply 是 idempotent（snap1 == snap2）
  - verify 对 sample 50 cross-check owner_key 与 preferences.user_id 一致
  - apply 没有 --apply 时 refuse 写（rc=1）
  - 50% orphan 触发 rc=2 警告阈值
```

## 4. Prod 执行步骤（阿里云 `Aliyun-ECS-2`）

> ⚠️ **每一步必须人工 confirm**。AGENTS.md §3.7 边界：所有写操作仅在 `/root/deeptutor/` 内。

### 4.1 备份

```bash
ssh Aliyun-ECS-2
cd /root/deeptutor
TS=$(date +%Y%m%d_%H%M%S)
cp data/chat_history.db "data/chat_history.db.bak-pr-alpha-${TS}"
ls -lh data/chat_history.db*
```

### 4.2 Dry-run

```bash
cd /root/deeptutor
.venv/bin/python scripts/migrations/pr_alpha_session_owner_key_backfill.py dry-run \
    --db data/chat_history.db
```

**Gate**：
- rc=0 + orphan ≤ 5%: **可以进 4.3**
- rc=2（orphan > 5%）: **停下来**，把 orphan sample 给开发评审，决定是 (a) 强制回填漏掉 orphan，(b) 单独脚本处理 orphan，(c) 接受 orphan 在 PR-1b 上线时 fail
- rc=1（DB not found）: 检查路径

### 4.3 Apply

```bash
cd /root/deeptutor
.venv/bin/python scripts/migrations/pr_alpha_session_owner_key_backfill.py apply \
    --db data/chat_history.db --apply
```

**期望输出**：
- "PRE-apply" 部分 backfillable=N
- "POST-apply" 部分 backfillable=0 + already_set 增加 N
- "Backfilled N sessions."

### 4.4 Verify

```bash
.venv/bin/python scripts/migrations/pr_alpha_session_owner_key_backfill.py verify \
    --db data/chat_history.db --sample 50
```

**Gate**：rc=0（mismatches=0）才能进 4.5。

### 4.5 Smoke Test（旧 session 仍可访问）

挑一个回填过的 session（从 4.3 输出里的 sample id 前缀拿一个真 id）：

```bash
sqlite3 /root/deeptutor/data/chat_history.db \
  "SELECT id, owner_key, json_extract(preferences_json,'$.user_id') AS pref_uid
   FROM sessions WHERE owner_key LIKE 'user:%' LIMIT 5;"
```

对每个 sample id，发一次 anon `GET /api/v1/sessions/{id}` 应返 401（说明 owner_key 起作用，没人能绕）；发一次带正确 user token 的 GET 应返 200。

## 5. Rollback

如果 4.4 / 4.5 失败：

```bash
ssh Aliyun-ECS-2
cd /root/deeptutor
# 停服务（避免 in-flight write）
docker compose stop backend
# 恢复
cp "data/chat_history.db.bak-pr-alpha-<TS>" data/chat_history.db
ls -lh data/chat_history.db
docker compose start backend
```

## 6. 跑完之后

- 在本 runbook 末尾贴：执行时间戳 / dry-run 输出 / apply 输出 / verify 输出 / smoke 结果
- 更新 [v2.1 计划 §3.8](../plan/2026-05-25-prelaunch-readiness-checklist.md) #1 状态为 Done
- 给 SR1 PR-1b 解除阻塞标记

## 7. Orphan 处理（如果 dry-run rc=2）

预期 orphan 是历史遗留的 anon session（用户没绑定）。两条路径：
- **保守路径**：在 SR1 PR-1b 把 `_authorize_session_access` 改成 strict 模式时，orphan 自然返 404，让客户端发现 + 创建新 session。**接受这条**就把 orphan ratio 写进 known issue。
- **激进路径**：写第二个脚本 `pr_alpha_orphan_purge.py`，把 orphan archive=1 + 给前端发"会话已过期"。**不推荐**，会触发用户感知断点。

## 8. 不确定性

- prod SQLite 实际行数：本机无 chat_history.db，未在 prod 跑过 dry-run。预期 dry-run 后 orphan ratio ≪ 5%。
- multi-replica 部署：当前 docker-compose 单 backend 容器单 SQLite 文件；如果未来多 replica + shared volume，apply 期间必须 stop 服务保 SQLite 写锁。本 runbook 假设 single-replica。
