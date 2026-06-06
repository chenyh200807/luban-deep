# 鲁班智考 P0 微信开发者工具验收脚本

| 字段 | 值 |
|---|---|
| **Plan** | [docs/plan/2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md](../plan/2026-05-20-luban-lightweight-practice-deep-grading-execution-plan.md) §7.7 |
| **回归矩阵** | [docs/plan/2026-05-13-luban-grading-chain-regression-matrix.md](../plan/2026-05-13-luban-grading-chain-regression-matrix.md) G1-G9 |
| **承接 HEAD** | `862f80fa fix: redact public ws grading authority` |
| **本地后端** | `scripts/start_local_learning_brain.sh start --no-web` → `http://127.0.0.1:8001` |
| **预计耗时** | 4 × 5 min = 20 min |
| **回滚阈值** | 任一脚本中出现 ✗ 即 NO-GO（plan §6.3） |
| **主验收面** | `yousenwebview/packageDeeptutor`；`wx_miniprogram` 只作为 shadow / render-contract 辅助面 |

---

## 通用配置

优先用 CLI 完成登录态、打开项目和自动化端口预检：

```bash
WX_DEVTOOLS_CLI=/Applications/wechatwebdevtools.app/Contents/MacOS/cli
$WX_DEVTOOLS_CLI islogin
$WX_DEVTOOLS_CLI open --project /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview/packageDeeptutor --lang zh
$WX_DEVTOOLS_CLI auto --project /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/yousenwebview/packageDeeptutor --auto-port 9420
```

`islogin` 只算环境预检；`open --project` 只算项目打开预检。必须完成下方 A-D 场景或自动化脚本输出，才能写 `real_wechat_package` PASS。若只跑到 `/wechat-harness`、node contract、`islogin` 或 `open --project`，结论必须写 `partial / true-entry pending`。

1. 微信开发者工具 → 项目 → `yousenwebview/packageDeeptutor/`
2. 详情 → 本地设置 → 启用「不校验合法域名」
3. 在 app/config 把 ws 入口指向 `ws://127.0.0.1:8001/api/v1/ws`
4. 编译并点开聊天页

> 每条 ✗ 都必须截图保存到 `.gstack/qa-reports/screenshots-2026-05-21-luban-p0-wx/` 并在末尾备注。

> 不默认执行 `upload`。发布、预览包或 CI 流水线另走明确授权的发布步骤，不能混入本 P0 验收。

---

## 脚本 A — 新用户第一次练题（plan §7.7 #1）

| # | 操作 | 期望 | 实际 |
|---|---|---|---|
| A1 | 聊天输入「给我3道安全管理题」回车 | 5 s 内出现 3 张可点选题卡 | ☐ ✓ / ☐ ✗ |
| A2 | 题卡 UI | 题干 + 选项可见；**无**「正确答案 / 解析 / scoring_points / grading_key / explanation」文字 | ☐ ✓ / ☐ ✗ |
| A3 | 任选一题，故意选错 | 2 s 内出现判分结论（对 / 错 / 部分） | ☐ ✓ / ☐ ✗ |
| A4 | 展开解析 | 包含：为什么错 / 知识点 / 易错点 / 记忆口诀 / 下一步建议 5 段 | ☐ ✓ / ☐ ✗ |
| A5 | 解析末尾按钮 | 至少 1 个 action chip 可点（再练3题 / 讲透这个点 / 看记忆口诀） | ☐ ✓ / ☐ ✗ |
| A6 | 控制台 Network → ws → frames | 出库 frame 中不出现 `"correct_answer"`、`"grading_key"`、`"scoring_points"`、`"explanation"` 4 个 hidden key 名（任一出现 = ✗）| ☐ ✓ / ☐ ✗ |

**Gate：A2 / A6 任一 ✗ 即 P0 NO-GO（plan §6.3 #1「答案泄露任意一次 = 0 容忍」）**

---

## 脚本 B — 连续学习闭环（plan §7.7 #2 / §5.1 场景 D）

| # | 操作 | 期望 | 实际 |
|---|---|---|---|
| B1 | 接续脚本 A 的错题，点 action chip「再练3题」 | 新题组在 5 s 内出现 | ☐ ✓ / ☐ ✗ |
| B2 | 新题考点 | 命中刚才错题的 knowledge_point（不是随机换题） | ☐ ✓ / ☐ ✗ |
| B3 | 系统未追问 | **不**出现「请告诉我你想练什么方向」类澄清气泡 | ☐ ✓ / ☐ ✗ |
| B4 | 答其中 1 题（任意） | 判分 + 解析按 A3-A5 标准 | ☐ ✓ / ☐ ✗ |
| B5 | ws frames 复核 | 同 A6（持续 0 leak） | ☐ ✓ / ☐ ✗ |

**Gate：B2 ✗ 表示 plan §5.2 #5「继续同考点 / 薄弱点」未达 → blocker；B5 ✗ 同 A6 → blocker**

---

## 脚本 C — 中断恢复（plan §7.7 #3 / §7.4 中断恢复）

| # | 操作 | 期望 | 实际 |
|---|---|---|---|
| C1 | 出 3 题，答完第 1 题 | 题卡显示「1/3 已答 / 2/3 待答」类进度 | ☐ ✓ / ☐ ✗ |
| C2 | 切到首页或别的 tab，等 30 s | — | — |
| C3 | 返回聊天页 | 当前题组（含已答状态）**不丢** | ☐ ✓ / ☐ ✗ |
| C4 | 续答第 2 题 | 判分正常，server 端用同一 active_object（不出新题）| ☐ ✓ / ☐ ✗ |
| C5 | 控制台 Local Storage / Page data | 不含 `correct_answer / grading_key / scoring_points`（前端 state 也不能保存 hidden authority） | ☐ ✓ / ☐ ✗ |

**Gate：C3 / C5 ✗ 触发 plan §11 风险表「标准答案丢失 / 系统重启误判」对应防线 → blocker**

---

## 脚本 D — 挫败感保护（plan §7.7 #4 / §7.3 progressive disclosure）

| # | 操作 | 期望 | 实际 |
|---|---|---|---|
| D1 | 连续答错 2 题（同知识点） | 第 2 次解析末尾默认 action chip 是「讲透这个点」或「基础巩固」（**不**是「提高难度」） | ☐ ✓ / ☐ ✗ |
| D2 | 文案审 | 不出现「你基础薄弱 / 你又错了 / 这题很简单」等羞辱 / 否定人格 / 泛化画像句 | ☐ ✓ / ☐ ✗ |
| D3 | 首屏文字 | 解析首屏 ≤ 120 个中文字符，长解析需折叠 | ☐ ✓ / ☐ ✗ |
| D4 | 连续答对 3 题 | 第 3 次解析末尾默认 action 是「提高一点难度」或「换更难的考点」 | ☐ ✓ / ☐ ✗ |
| D5 | action chip 数量 | 每轮主行动 1 个 + 辅助 ≤ 2 个，**不超过 3 个**按钮 | ☐ ✓ / ☐ ✗ |

**Gate：D1 / D2 ✗ 直接命中 plan §7.6「禁止」清单 → blocker**

---

## 汇总

| 脚本 | 通过 | 备注（截图路径 / 偏差） |
|---|---|---|
| A 新用户练题 | ☐ ALL ✓ / ☐ 有 ✗ |  |
| B 错题闭环 | ☐ ALL ✓ / ☐ 有 ✗ |  |
| C 中断恢复 | ☐ ALL ✓ / ☐ 有 ✗ |  |
| D 挫败感保护 | ☐ ALL ✓ / ☐ 有 ✗ |  |

**判定**：4 个脚本中只要有 1 个 ✗（不论哪一条），按 plan §14 Done Definition 当条「未达」处理；汇报到本次 P0 GO/NO-GO 决策。

**完成签字**：________   **日期**：____ : ____
