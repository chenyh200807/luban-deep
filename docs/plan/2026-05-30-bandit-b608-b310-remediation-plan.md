# Bandit B608 (SQL 注入) / B310 (SSRF) 逐 finding 修复计划

> **本文档是只读核验产物**——它记录裁定结论与逐 finding 的处置方案，但**不在本次提交内对任何源码落地修改**。
> **日期**：2026-05-30
> **状态**：v1（裁定已完成，处置待人工执行）
> **范围**：Bandit 静态扫描 B608（SQL injection）14 条 + B310（urllib urlopen / SSRF）4 条
> **纪律**：AGENTS §3 Surgical Changes、§5 Fix Root Causes、单一权威；本批**不进入自主 workflow 自动改**（理由见 §4）。

---

## 0. 为什么单独立这份文档

Bandit 的 B608/B310 全部命中**数据访问层与外部 HTTP 出口**——是系统里最敏感的两类边界：

- B608 命中的是 SQL 文本拼接点（哪怕只拼常量列名，静态扫描也无法证伪）。
- B310 命中的是 `urllib.request.urlopen`（静态扫描无法判断目标 host 是否用户可控）。

这两类问题的修复风险**不在改动量，而在"误把安全改成不安全"或"把可信常量误判为用户输入而过度防御导致行为漂移"**。因此本文档先把每一条 finding 的**数据流来源**写清楚、给出**裁定**，再给出**最小处置**（绝大多数是 `# nosec` + 理由注释，零行为改动）。

---

## 1. 裁定方法论（怎么判 false positive）

对每一条 finding，沿数据流回答三个问题：

1. **进入 SQL 文本 / URL host·path 的是什么？** 是模块常量 / 字面量，还是来自请求的用户值？
2. **用户值走的是绑定参数（`%s` / `?` / params 序列）还是字符串拼接？**
3. **列名 / 表名 / SET key 是否经白名单约束？** 若 key 可被用户控制且直接拼进 SQL，则**真阳性**，必须改；若 key 取自硬编码集合或 validator 产出的字面量，则**假阳性**。

裁定口径：**SQL 文本 / URL 目标中没有任何外部数据**即判 `false_positive`，处置为加 `# nosec <规则号>` + 单行理由，**不改逻辑**。这与 §5 根因一致：根因是"Bandit 无法静态证明拼接安全"，治本手段是**就地标注证据**而非引入新的转义层/包装函数（那会制造第二权威，违反单一权威约束）。

---

## 2. B608（SQL 注入）逐 finding 处置

> 共 14 条，**全部裁定 `false_positive`，sensitive=true**。处置统一为：在拼接行加 `# nosec B608` 并补一行中文理由注释，**零逻辑改动**。

### 2.1 `deeptutor/services/invite_test_applications.py`（6 条）

| 行 | 裁定 | 数据流证据 | 处置 |
| --- | --- | --- | --- |
| 681 | FP | f-string 仅插入模块常量 `_SELECT_COLUMNS`（固定列名）；`WHERE/LIMIT` 经 `%s` 绑定（`created_after`, `2000`）。无用户输入进入 SQL 文本。 | `# nosec B608` + 理由 |
| 703 | FP | psycopg2 分支，同 681——只插入常量 `_SELECT_COLUMNS`，过滤值 `%s` 绑定。 | `# nosec B608` + 理由 |
| 767 | FP | `SELECT` 只插入常量 `_SELECT_COLUMNS`，`WHERE id = %s` 绑定 `application_id`。 | `# nosec B608` + 理由 |
| 783 | FP | `UPDATE` 的 `SET` 子句 key 仅取自白名单 `_EDITABLE_COLUMN_FIELDS`（外加字面量 `raw_payload`），values 全 `%s` 绑定。列名非用户可控，值已参数化。 | `# nosec B608` + 理由 |
| 811 | FP | psycopg2 分支，同 767——常量列 + `id=%s` 绑定。 | `# nosec B608` + 理由 |
| 827 | FP | psycopg2 分支，同 783——`SET` key 受 `_EDITABLE_COLUMN_FIELDS` 白名单约束，values `%s` 绑定。 | `# nosec B608` + 理由 |

**单一权威边界**：列名白名单的唯一 authority 是模块常量 `_EDITABLE_COLUMN_FIELDS` / `_SELECT_COLUMNS`。处置时**不得**新建第二份列名白名单或转义工具——只在原拼接点标注。

### 2.2 `deeptutor/services/learner_state/outbox.py`（1 条）

| 行 | 裁定 | 数据流证据 | 处置 |
| --- | --- | --- | --- |
| 139 | FP | `IN` 子句仅按 `ids` 数量拼入 `'?'` 占位符串，`ids` 作为参数序列绑定。SQL 文本中无用户数据。 | `# nosec B608` + 理由 |

### 2.3 `deeptutor/services/luban_feedback_store.py`（4 条）

| 行 | 裁定 | 数据流证据 | 处置 |
| --- | --- | --- | --- |
| 335 | FP | 仅插入模块常量 `_SELECT_COLUMNS` 与 `_TABLE`，`created_at>=%s` / `limit %s` 绑定。 | `# nosec B608` + 理由 |
| 357 | FP | psycopg2 分支，同 335——常量列名 + 表名，值 `%s` 绑定。 | `# nosec B608` + 理由 |
| 402 | FP | `SET` assignments 的 key 来自 `patch`，而 `patch` 由 `validate_luban_feedback_patch` 产出，key 只能是字面量 `'status'`/`'operator_note'`（硬编码，非用户可控）；`_TABLE`/`_SELECT_COLUMNS` 常量，values 与 `id` 均 `%s` 绑定。 | `# nosec B608` + 理由 |
| 424 | FP | psycopg2 分支，同 402——`patch` key 受 `validate_luban_feedback_patch` 限定为 `status`/`operator_note`，值参数化。 | `# nosec B608` + 理由 |

**单一权威边界**：feedback patch 的 key 白名单唯一 authority 是 `validate_luban_feedback_patch`。处置**不得**在拼接点重新校验 key（那会复制权威）；只标注"key 已被 validator 约束"。

### 2.4 `deeptutor/services/observability/usage_ledger.py`（1 条）

| 行 | 裁定 | 数据流证据 | 处置 |
| --- | --- | --- | --- |
| 261 | FP | `where_sql` 由内部字面量 clause 拼成（`'created_at >= ?'`/`'provider_name = ?'`/`'model = ?'`），`provider`/`model` 等用户值全部进 `params` 以 `?` 绑定。SQL 文本无外部数据。 | `# nosec B608` + 理由 |

### 2.5 `deeptutor/services/session/sqlite_store.py`（3 条）

| 行 | 裁定 | 数据流证据 | 处置 |
| --- | --- | --- | --- |
| 1223 | FP | `placeholders` 仅为 `'?,?...'` 占位串，`resolved_session_ids` 作为 tuple 参数绑定。 | `# nosec B608` + 理由 |
| 1933 | FP | `where_clause` 由 `query_conditions` join 而成，所有 condition 字符串均为调用方硬编码字面量（如 `'s.owner_key = ?'`、`'s.source = ?'`、游标比较），用户值进 `query_params` 以 `?` 绑定。SQL 文本无用户输入。 | `# nosec B608` + 理由 |
| 2794 | FP | `set_clause` 的列名 key 经 `allowed={bookmarked,followup_session_id,user_answer,is_correct}` 白名单过滤（`updated_at` 为字面量），values 全部 `?` 绑定，`WHERE id=?` 绑定。 | `# nosec B608` + 理由 |

**单一权威边界**：session 列白名单的唯一 authority 是 `sqlite_store.py` 内 `allowed` 集合 / `query_conditions` 字面量列表。**不得**外提为共享白名单模块（无第二消费者，YAGNI，违反 §2.5 Less Is More）。

---

## 3. B310（SSRF / urlopen）逐 finding 处置

> 共 4 条，**全部裁定 `false_positive`，sensitive=true**。处置统一为：在 `urlopen(...)` 行加 `# nosec B310` + 理由注释，**零逻辑改动**。

### 3.1 `deeptutor/services/assessment/blueprint_service.py`（3 条）

| 行 | 裁定 | 数据流证据 | 处置 |
| --- | --- | --- | --- |
| 276 | FP | `urlopen` 的 `base_url` 仅来自 `_supabase_config()`（env / 本地 `.env`），`table` 硬编码 `'questions_bank'`，`filters` 仅是 query 参数，不构成用户可控目标 host。无 SSRF。 | `# nosec B310` + 理由 |
| 305 | FP | `_rest_upsert` 的 `base_url` 同样来自 `_supabase_config()`（可信配置），`table` 硬编码，POST 目标 host 固定，不接受用户控制 URL。 | `# nosec B310` + 理由 |
| 384 | FP | `question_bank_size` 向 `{base_url}/rest/v1/questions_bank` 固定路径发 GET，`base_url` 来自 `_supabase_config()`，无用户输入进入 URL host/path。 | `# nosec B310` + 理由 |

**单一权威边界**：Supabase 连接配置的唯一 authority 是 `_supabase_config()`（读 env / 本地 `.env`）。处置**不得**新增 URL 白名单校验层（host 已由可信配置固定，再加校验是冗余防御 + 第二权威）。

### 3.2 `deeptutor/services/member_console/service.py`（1 条）

| 行 | 裁定 | 数据流证据 | 处置 |
| --- | --- | --- | --- |
| 2483 | FP | `urlopen` 目标为硬编码常量 `'https://dysmsapi.aliyuncs.com/'`（阿里云短信 API），URL 完全固定；`phone`/`code` 仅作为已签名表单字段，无 SSRF 可控面。 | `# nosec B310` + 理由 |

---

## 4. 为什么本批不进入自主 workflow 自动改

1. **敏感边界**：18 条全部落在 SQL 数据访问层与外部 HTTP 出口。任何"顺手"的转义包装、URL 校验注入都可能**改变查询语义或外呼行为**，属于 §3 Surgical Changes 明令收窄的高风险区。
2. **跨子系统纠缠**：涉及 invite 测试申请、learner_state outbox、luban feedback、observability usage ledger、session store、assessment blueprint、member console 短信——7 个互不相关的子系统。把它们塞进一个自动 PR 会让 diff 横跨多权威，违反"diff 收窄到本项直接相关"。
3. **裁定本身是结论而非改动**：本批 100% 是 `false_positive`，正确动作是**就地标注证据注释（`# nosec` + 理由）**，每个文件单独、独立审阅、独立 commit。这类"安全证据落地"必须由人工逐文件确认数据流后手动加注释，不能由自主循环批量写入——一旦某处常量未来被改成用户可控，注释会变成误导。
4. **单一权威红线**：每一条的安全性都依赖既有 authority（列白名单 / validator / `_supabase_config()`）。自动改有诱因引入"统一安全工具"，那恰恰会制造第二权威，与项目硬约束冲突。

**结论**：本文档作为只读核验产物归档裁定；实际加 `# nosec` 注释的落地，留给后续**逐文件、窄 scope、独立 commit** 的人工执行（每个文件一个 commit，PR 描述引用本文档对应小节）。落地时**只加注释、不改任何 SQL/URL 构造逻辑**，并跑现有测试确认零行为漂移。

---

## 5. 落地执行清单（人工，后续）

- [ ] 逐文件加 `# nosec B608` / `# nosec B310` + 单行中文理由，行号见 §2/§3。
- [ ] 每个文件独立 commit，commit message 引用本文档小节号。
- [ ] 加注释后重跑该文件相关单测 + `bandit` 复扫，确认对应 finding 消失且无新增。
- [ ] 不修改任何 SQL 文本构造、参数绑定方式、URL host/path 构造。
- [ ] 若复查发现任何一条实为真阳性（如列名 key 来源可被用户控制），**立即停止标注**，改走根因修复（白名单收口）并单独立项。

---

*待挂 `docs/plan/INDEX.md`：建议挂在「生产部署」或新「安全静态扫描裁定」主线下；本文档不直接修改 INDEX 以避开并发冲突。*
