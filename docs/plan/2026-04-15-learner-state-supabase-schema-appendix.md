# 附录：Learner State 的 Supabase Schema 与迁移方案

## 1. 文档信息

- 文档名称：Learner State Supabase Schema 附录
- 文档路径：`/docs/plan/2026-04-15-learner-state-supabase-schema-appendix.md`
- 创建日期：2026-04-15
- 关联主文档：
  - [2026-04-15-learner-state-memory-guided-learning-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-15-learner-state-memory-guided-learning-prd.md)
  - [2026-04-15-learner-state-service-design.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-15-learner-state-service-design.md)
  - [2026-04-15-bot-learner-overlay-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-15-bot-learner-overlay-prd.md)
  - [2026-04-15-bot-learner-overlay-service-design.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-15-bot-learner-overlay-service-design.md)
- 状态：Implemented foundation v1（migration in repo；生产实例执行仍未验收）

## 1.1 Repo-side 完成状态（2026-04-24）

本附录对应的 repo-side schema 已落到：

- `supabase/migrations/20260415000100_learner_state_core.sql`
- `supabase/migrations/20260415000200_bot_learner_overlay.sql`
- `supabase/migrations/20260419000100_learner_state_rls.sql`

生产级 Supabase 的真实执行、回滚演练、权限配置与数据规模压测不在本地 repo closure 中伪装完成，继续归入部署 gate。

## 2. 目标

本附录只回答三个问题：

1. 现有 Supabase 表哪些继续用
2. 哪些必须新增
3. 实施时怎么迁移，才能真正用起来，而不是摆设

## 3. 当前已验证的可复用表

基于当前真实 Supabase 实例，已确认存在并有数据的核心表：

### `users`

用途：

- 身份主表
- 学员唯一 `user_id` 来源

### `user_profiles`

当前字段：

- `user_id`
- `summary`
- `attributes`
- `last_updated`

当前规模：

- 约 1620 条

结论：

- 继续复用为 learner profile 主表
- 不再新建同义的 `learner_profiles`

### `user_stats`

当前字段：

- `user_id`
- `mastery_level`
- `knowledge_map`
- `current_question_context`
- `radar_history`
- `total_attempts`
- `error_count`
- `last_practiced_at`
- `last_updated`
- `tag`

当前规模：

- 约 1603 条

结论：

- 继续复用为 learner progress 主表
- 不再新建同义的 `learner_progress`

### `user_goals`

当前字段：

- `id`
- `user_id`
- `goal_type`
- `title`
- `target_node_codes`
- `target_question_count`
- `progress`
- `deadline`
- `created_at`
- `completed_at`

结论：

- 继续复用为 learner goals 主表

## 4. 复用表的精确职责

## 4.1 `user_profiles`

### 必须承载

- 学员长期画像
- 稳定偏好
- 心跳偏好
- 学习目标基础信息
- 来源信息

### 建议 `attributes` 结构

```json
{
  "display_name": "小陈",
  "timezone": "Asia/Shanghai",
  "source": "wx_miniprogram",
  "plan": "free",
  "exam_target": "一级建造师·建筑工程",
  "knowledge_level": "intermediate",
  "communication_style": "concise",
  "learning_preferences": {
    "difficulty_preference": "adaptive",
    "explanation_style": "detailed"
  },
  "support_preferences": {
    "teaching_mode": "smart"
  },
  "heartbeat_preferences": {
    "enabled": true,
    "quiet_hours": ["22:00", "08:00"],
    "cadence": "adaptive"
  },
  "consent": {
    "heartbeat": true
  }
}
```

### 第一阶段读写映射

- 读：
  - TutorBot runtime
  - Guided Learning
  - Heartbeat
  - profile/settings 页
- 写：
  - onboarding
  - 用户显式设置
  - 受控 profile refinement

## 4.2 `user_stats`

### 必须承载

- 学员知识掌握状态
- 学员薄弱点
- 练习行为统计
- 最近学习活跃度

### 保留与收敛

- `knowledge_map`
  - 保留，并作为 mastery / diagnosis 主结构
- `mastery_level`
  - 保留
- `total_attempts / error_count / last_practiced_at`
  - 保留
- `current_question_context`
  - 第一阶段兼容保留
  - 中期应迁回 session state

### 第一阶段读写映射

- 读：
  - TutorBot runtime
  - quiz/review
  - Guided Learning
  - Heartbeat
- 写：
  - grading/review 归并
  - guide completion 归并

## 4.3 `user_goals`

### 必须承载

- 学员考试目标
- 节点目标
- 题量目标
- 截止时间

### 第一阶段读写映射

- 读：
  - study plan generator
  - TutorBot planning
  - Heartbeat
- 写：
  - onboarding
  - 计划调整
  - 完成状态更新

## 5. 第一阶段必须新增的表

## 5.1 `learner_summaries`

建议 DDL：

```sql
create table if not exists learner_summaries (
  user_id uuid primary key references users(id) on delete cascade,
  summary_md text not null default '',
  summary_structured_json jsonb not null default '{}'::jsonb,
  last_refreshed_from_turn_id text,
  last_refreshed_from_feature text,
  updated_at timestamptz not null default now()
);

create index if not exists idx_learner_summaries_updated_at
  on learner_summaries(updated_at desc);
```

用途：

- `Summary` 单一真相

## 5.2 `learner_memory_events`

建议 DDL：

```sql
create table if not exists learner_memory_events (
  event_id uuid primary key,
  user_id uuid not null references users(id) on delete cascade,
  source_feature text not null,
  source_id text not null,
  source_bot_id text,
  memory_kind text not null,
  payload_json jsonb not null,
  dedupe_key text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists idx_learner_memory_events_dedupe
  on learner_memory_events(dedupe_key);

create index if not exists idx_learner_memory_events_user_created
  on learner_memory_events(user_id, created_at desc);
```

用途：

- 长期 writeback 的统一事件流

## 5.3 `learning_plans`

建议 DDL：

```sql
create table if not exists learning_plans (
  plan_id uuid primary key,
  user_id uuid not null references users(id) on delete cascade,
  source_bot_id text,
  source_material_refs_json jsonb not null default '[]'::jsonb,
  knowledge_points_json jsonb not null default '[]'::jsonb,
  status text not null,
  current_index int not null default 0,
  completion_summary_md text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_learning_plans_user_updated
  on learning_plans(user_id, updated_at desc);
```

## 5.4 `learning_plan_pages`

建议 DDL：

```sql
create table if not exists learning_plan_pages (
  plan_id uuid not null references learning_plans(plan_id) on delete cascade,
  page_index int not null,
  page_status text not null,
  html_content text,
  error_message text,
  generated_at timestamptz,
  primary key (plan_id, page_index)
);
```

## 5.5 `heartbeat_jobs`

建议 DDL：

```sql
create table if not exists heartbeat_jobs (
  job_id uuid primary key,
  user_id uuid not null references users(id) on delete cascade,
  bot_id text not null,
  channel text not null,
  policy_json jsonb not null default '{}'::jsonb,
  next_run_at timestamptz not null,
  last_run_at timestamptz,
  last_result_json jsonb,
  failure_count int not null default 0,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_heartbeat_jobs_due
  on heartbeat_jobs(status, next_run_at);

create unique index if not exists idx_heartbeat_jobs_user_bot_channel
  on heartbeat_jobs(user_id, bot_id, channel);
```

## 6. 为什么不新建 `learner_profiles / learner_progress / learner_goals`

因为现在已有：

- `user_profiles`
- `user_stats`
- `user_goals`

它们的语义已经足够接近目标主模型。

如果第一阶段再新建：

- `learner_profiles`
- `learner_progress`
- `learner_goals`

会立刻产生：

1. 同义双表
2. 迁移不清
3. 运营后台不知道看哪张
4. 代码读写再次分叉

所以第一阶段必须坚持：

- 复用老表
- 增量新增缺失表

## 7. 可靠性：DB 真相 + 本地 Durable Outbox

## 7.1 原则

- DB 是最终真相
- 本地 SQLite outbox 是网络抖动与短暂故障兜底

## 7.2 建议 outbox 表

本地 SQLite `outbox.db`：

```sql
create table if not exists learner_state_outbox (
  id text primary key,
  user_id text not null,
  event_type text not null,
  payload_json text not null,
  dedupe_key text not null,
  status text not null default 'pending',
  retry_count int not null default 0,
  created_at text not null,
  last_error text
);

create unique index if not exists idx_learner_state_outbox_dedupe
  on learner_state_outbox(dedupe_key);

create index if not exists idx_learner_state_outbox_status_created
  on learner_state_outbox(status, created_at);
```

## 7.3 哪些必须同步写

- profile / preferences 显式修改
- goals 显式修改
- heartbeat 开关修改
- 关键 plan 创建/调整

## 7.4 哪些可以走 outbox

- summary 刷新
- memory events
- guide completion writeback
- heartbeat delivery logs

## 8. 迁移顺序

### 8.0 migration 落点

当前仓库里还没有正式的 `supabase/migrations/` 目录。  
这意味着后续如果真的进入 schema 实施，不能假设“已有标准 migration 树”，而应该显式创建：

```text
supabase/
  migrations/
```

推荐命名策略：

1. `20260415xxxxxx_learner_state_core.sql`
   - `learner_summaries`
   - `learner_memory_events`
   - `learning_plans`
   - `learning_plan_pages`
   - `heartbeat_jobs`
2. `20260415xxxxxx_bot_learner_overlay.sql`
   - `bot_learner_overlays`
   - `bot_learner_overlay_events`
   - `bot_learner_overlay_audit`

这样第一阶段与第二阶段的控制面会保持清楚边界，不会把 overlay 提前混成第一阶段主真相。

当前已新增初稿文件：

1. [20260415000100_learner_state_core.sql](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/supabase/migrations/20260415000100_learner_state_core.sql)
2. [20260415000200_bot_learner_overlay.sql](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/supabase/migrations/20260415000200_bot_learner_overlay.sql)

### Phase A：无破坏增强

1. 给现有代码读路径统一包上 `LearnerStateService`
2. 先不删旧路径
3. 增加新表

### Phase B：写路径收口

1. profile 全部收口到 `user_profiles`
2. progress 全部收口到 `user_stats`
3. goals 全部收口到 `user_goals`
4. summary 收口到 `learner_summaries`
5. memory writeback 收口到 `learner_memory_events`

### Phase C：旧表/旧字段收边界

1. `user_profiles.summary` 从主真相降级为兼容字段或投影视图
2. `user_stats.current_question_context` 迁回 session state

## 9. 成功标准

复用现有表只有在以下条件同时满足时才算成功：

1. 代码中真实读写这张表
2. 运营后台真实展示/管理这张表
3. 没有再创建同义平行表
4. trace / audit 能看见这张表参与的读写

如果做不到这四条，就不算“复用成功”。

## 10. 第二阶段预留表

第二阶段 schema 只做预留设计，不提前进入第一阶段主真相。

### 10.1 `bot_learner_overlays`

建议 DDL：

```sql
create table if not exists bot_learner_overlays (
  bot_id text not null,
  user_id uuid not null references users(id) on delete cascade,
  local_focus_json jsonb not null default '{}'::jsonb,
  active_plan_id uuid,
  teaching_policy_override_json jsonb not null default '{}'::jsonb,
  heartbeat_override_json jsonb not null default '{}'::jsonb,
  channel_presence_override_json jsonb not null default '{}'::jsonb,
  local_notebook_scope_refs_json jsonb not null default '[]'::jsonb,
  engagement_state_json jsonb not null default '{}'::jsonb,
  promotion_candidates_json jsonb not null default '[]'::jsonb,
  working_memory_projection_md text not null default '',
  version int not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (bot_id, user_id)
);

create index if not exists idx_bot_learner_overlays_user
  on bot_learner_overlays(user_id);
```

用途：

- `bot_id + user_id` 局部差异主表

### 10.2 `bot_learner_overlay_events`

建议 DDL：

```sql
create table if not exists bot_learner_overlay_events (
  event_id uuid primary key,
  bot_id text not null,
  user_id uuid not null references users(id) on delete cascade,
  source_feature text not null,
  source_id text not null,
  patch_kind text not null,
  payload_json jsonb not null,
  dedupe_key text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists idx_bot_learner_overlay_events_dedupe
  on bot_learner_overlay_events(dedupe_key);

create index if not exists idx_bot_learner_overlay_events_user_created
  on bot_learner_overlay_events(bot_id, user_id, created_at desc);
```

用途：

- overlay 结构化 patch / promotion candidate 事件流

### 10.3 `bot_learner_overlay_audit`

建议 DDL：

```sql
create table if not exists bot_learner_overlay_audit (
  audit_id uuid primary key,
  bot_id text not null,
  user_id uuid not null references users(id) on delete cascade,
  actor text,
  action text not null,
  fields_json jsonb not null default '[]'::jsonb,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_bot_learner_overlay_audit_user_created
  on bot_learner_overlay_audit(bot_id, user_id, created_at desc);
```

用途：

- 人工调整、运营改动、关键 overlay 行为审计

### 10.4 第二阶段设计禁令

第二阶段即使新增 overlay 表，也不允许再新增：

- `bot_learner_profiles`
- `bot_learner_summaries`
- `bot_learner_progress`
- `bot_learner_goals`

否则会重新长出第二套 learner truth。
