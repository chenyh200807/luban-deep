# 双轮 spike 判据预登记：真实 D1 基线 + 提升阈值提案（PENDING_OWNER）

> 双轮 v3.2 §12 阶段1 spike 的「判据预登记防挪门柱」交付物（P0-⑥/F 项）。
> 铁律：基线只用**拉取时刻已存在的真实数据**，本文写定后 spike 期间不得回改基线口径。

## 1. 数据源裁决（如实上报）

| 候选源 | 现状 | 裁决 |
|---|---|---|
| BI 行为库 | 0 行（历史已知） | 不可用 |
| 客户端埋点 `product_behavior.db` | 生产仅 **16 行**事件 | 不可用（埋点未接） |
| **服务端 turn 活动**（`chat_history.db`: sessions 3981 / turns 6120 / turn_events 633070） | 真实、连续、带 owner_key | **采用（替代度量）** |

**D1 定义（替代度量）**：以 `sessions.owner_key`（`user:<uuid>`）为用户，`turns.created_at`（unixepoch，UTC+8 取日）为活动日；用户首个活动日为 D0，D0+1 当天有任意 turn 即 D1 留存。首访=当天的用户不入 cohort（窗口未过）。

## 2. 实测基线（2026-07-02 拉取，生产容器 `deeptutor` 直查）

| 口径 | cohort | D1 留存 | **D1** |
|---|---|---|---|
| 全部 owner_key 用户 | 421 | 26 | **6.2%** |
| 剔除疑似内部账号（turns>50，共 13 个） | 409 | 19 | **4.6%** |

- 用户总数 436，首访分布集中在 2026-06（421 人），峰值日 06-29（139 人，疑似投放/分享脉冲）。
- **诚实声明**：本地库无法区分 QA/内部账号（owner_key 是 uuid，qa_ 用户名映射在 Supabase member 侧），故给双口径；重度账号剔除是启发式非 ground truth。复算脚本口径固定为本文 §1 定义，任何人可在容器内重跑核对。

## 3. spike 成功阈值提案（PENDING_OWNER，未拍板前不生效）

以「剔除疑似内部」口径 D1=4.6% 为基线 B：

- **方案甲（相对提升）**：spike 参与用户（走完 ≥1 个站点闭环者）D1 ≥ 2×B（≈9.2%），且 cohort ≥ 30 人方可读数（防小样本假阳）。
- **方案乙（绝对下限）**：spike 参与用户 D1 ≥ 15%（对标工具类小程序次留中位），同样 cohort ≥ 30。
- 共同护栏：读数窗口 ≥ 7 天；QA/内部账号进 allowlist 剔除（需先把 qa_ 映射表从 member 侧导出）；不达 cohort 门槛只报「未达读数条件」不报成败。

**留给 owner 的一句话拍板**：选甲/乙/自定阈值。

## 4. 复算命令（独立可证伪）

```bash
scp scratchpad/d1_baseline.py Aliyun-ECS-2:/tmp/ \
  && ssh Aliyun-ECS-2 'docker cp /tmp/d1_baseline.py deeptutor:/tmp/ && docker exec deeptutor python3 /tmp/d1_baseline.py'
```

（脚本逻辑即 §1 定义的直译：join sessions×turns → 按用户聚合活动日 → D0+1 命中率。）
