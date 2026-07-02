# spike 点火包（一页纸）——PENDING_OWNER：点火拍板

> Status: **Ready / 万事俱备只差点火**（点火=P7 硬闸，本文是拍板的全部依据）
> Date: 2026-07-02 · 执行计划: [spike-execution-plan](2026-07-02-luban-spike-execution-plan.md) · 判据: [d1-baseline-preregistration](2026-07-02-luban-spike-d1-baseline-preregistration.md)

## 一、判据（乙案 owner-approved，已预登记防挪门柱）

> **活体基线重述（QA allowlist 权威口径，2026-07-02 生产直查）**：`report_luban_spike_d1` 实跑——allowlist=883 个内部键位，剔除 414/436 个历史 owner_key；**真实用户 cohort=22、D1=27.3%、未达 cohort≥30 读数条件**。即预登记 §2 的 4.6% 启发式基线被证明重度污染（历史流量大头是 QA/学生军团/eval 探针）；spike 的第一意义就是把真实 cohort 做到 ≥30 完成首次可读数。QA 口径端到端闭环已实证：true-entry 三轮产生的全部 D15 事件（retest_item_answered=30/handoff_rendered=16/module_viewed=16/subscribe_prompt_result=15/learning_action_started=14/learning_action_completed=6，2 日窗）被 `report_luban_spike_events` 全部正确归入 qa_excluded、real=0——测试流量污染不进读数。

- **正式判据**：spike 参与用户（走完 ≥1 站闭环）D1 ≥ **15%**，cohort ≥ 30 方可读数，窗口 ≥ 7 天。
- 观察指标：相对基线倍数（B=4.6% 剔内部 / 6.2% 全量；2×B≈9.2% 参考线），只披露不裁决。
- 读数硬前置已备：QA/内部账号 allowlist（member 权威导出 + `report_luban_spike_d1`/`report_luban_spike_events` 双脚本）已合 main。

## 二、已就绪件清单（全部独立终态核验，2026-07-02）

| 件 | 核验数字 |
|---|---|
| 内容弹药 | 绿灯 5 包（S05/N01/J01/A01/C02）；锚校验 8/8+5/5+9/9+5/5+11/11 零漂移；签发出处 owner 批准+机器核验（#333/#337/#339/#345） |
| 生产部署 | test2 容器=host .env=main=**7d33f905b**（GIT_DIRTY=false）；readyz 200；容器内 manifest+变体池文件实存、`grep build_retest_items`=1 |
| 学习卡链路 | `/api/v1/luban/lessons` 线上实返 5 站；讲懂卡公网 200/76.9KB（nginx gzip）；投影门 fail-closed（镜像缺 manifest 时线上全空的事故即其工作实证，#344/#345 治本） |
| 变体复测 | 池 75 个（一致性门 100%）；`retest-items` 线上实返题面；**同日幂等活体实证**（三轮同切片 S05-B-send-022）；服务端 UTC+8 折日（day_index=2026183） |
| 真机三轮 | automator true-entry **3/3 ALL PASS**：登录（隐私勾选+密码）→5 站列表→讲懂（线上卡）→交接时刻→订阅红点降级→复测 5 题本地判分 |
| D15 埋点 | 生产库真数据全事件族：`retest_item_answered=15`（逐变体×3 全 correct）/`handoff_rendered=13`/`module_viewed=13`/`subscribe_prompt_result=12`/`learning_action_started=11`/`learning_action_completed=3` |
| 订阅消息 | 红点降级契约 7 tests + 真机路径实走；模板 ID 到位后填两处即升级为推送形态 |

## 三、剩余风险（如实，不影响点火的标注影响面）

1. **station 页原生按钮 vs web-view 层级**：DevTools 三轮通过；**真手机**上 web-view 可能盖住原生按钮——点火前建议 owner 真手机预览一次（分钟级）；备选方案已留（卡内 navigateTo 桥接）。
2. **静态样张人眼核未做**（执行计划 Task 5）：三站卡+交接/复测文案需你或教研过目（文案禁词机器扫描已 0 命中，但内容正确性人眼未核）。
3. 变体池判分内核全回路（语义门）未跑：结构门 100%；如需可在点火后补跑（billable）。
4. N01/C02/J01 闯关薄（单题）；变体复测仅 S05——spike 度量主体在 S05 旗舰站，计划已如实分层。
5. 订阅消息为红点形态（模板 ID 未到），次日回访钩子弱一档——D1 读数请对照此背景。

## 四、点火动作（你拍板后，分钟级）

① 你真手机预览 + 样张人眼核（风险 1/2 消除）→ ② 招募真实一建在职考生小样本（cohort ≥30 才读数）→ ③ 开始 7 天窗口，D1/D15 由 `report_luban_spike_d1`/`report_luban_spike_events` 按预登记口径出数。
