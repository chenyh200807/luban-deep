# Battle2 配对基线批 — PRE 臂结果（部署#2 前对照组）

- 生产入口: https://test2.yousenjiaoyu.com (SHA 08dc27eb)
- 批窗口 (UTC): **2026-07-12T07:21:42.577Z → 2026-07-12T07:28:52.073Z** (wall 429.5s)
- 身份: 前缀 `qa_claude_b2pre_`（原定 `claude_b2pre_` 因服务器 eval-bypass cohort 只认 qa_/test_/operator_ 前缀而加 qa_ 前缀；X-Eval-Bypass 已验证生效——单用户4连发超 free_trial=3 不被拦）
- 用户池: qa_claude_b2pre_1783840875_0, qa_claude_b2pre_1783840885_1, qa_claude_b2pre_1783840894_2（注册限流 3/60s，故 3 用户池 login 复用，每会话新建独立 conversation）

## 通过率
- 主 turn: **32/32** passed（8 会话×4 turn，全 completed）
- 哨兵 turn: **10/10** passed
- 失败清单: （空）

## 客户端墙钟 (wall_ms, start-turn 发出→done)
- 主 32 turn: p50 **9578.2** / p95 **17201.0** / min 1776.2 / max 21750.0
- 哨兵前5: [7576.2, 8281.3, 7579.5, 4253.2, 6640.9]
- 哨兵后5: [8397.2, 4035.1, 6391.4, 4274.1, 3640.5]
- 哨兵10合并: p50 **6391.4** / p95 **8397.2**

## Prometheus TTFVT 差分（服务器 turn start→首个有用内容; prom_pre_before 07:21:04Z / prom_pre_after 07:29:13Z）
- content.delta: count Δ=**41**, sum Δ=217371ms, 均值 **5302ms**
- 桶累计分布 Δ: ≤500ms:0 ≤1s:2 ≤2s:6 ≤4s:22 ≤8s:34 ≤16s:38 ≤32s:41 ≤64s:41
- result.response 兜底: count Δ=1, sum Δ=562ms
- summary_maintainer 计数器: **Δ=0**（批中无任何 summary-maintainer 决策计数）

## Langfuse 读数（窗口 2026-07-12T07:20:42.000Z → 2026-07-12T07:33:52.000Z）
- traces: 43; GENERATION 观测: 105（主区间 79 / 哨兵区间 20）
- 每 trace LLM generation 数: avg **2.39** / p50 2 / p95 4 / max 4 (n=44)
- summary_maintainer generation: **0 次 / 0 tokens**
- heartbeat generation: **0 次 / 0 tokens**
- 全批 token: 输入 **622,870** / 输出 **35,847** / 合计 **658,717**
- 全批成本 (Langfuse cost 字段): **$0.681147**
- TTFT (completionStartTime−startTime): tutorbot.llm.stream p50 **1378.0** / p95 **2216.0** (n=31); llm.stream p50 **5399.0** / p95 **10219.0** (n=50)
- TTFT 哨兵区间单列: p50 **1539.0** / p95 **3931.0** (n=18); 主区间: p50 **4524.0** / p95 **9845.0** (n=58)
- trace 总时长(含异步尾巴): 全部 p50 **19655.0** / p95 **34750.0** (n=44); 主 p50 **23159.0** / p95 **34750.0** (n=32); 哨兵 p50 **13233.0** / p95 **17046.0** (n=10)
- generation 名称集合: ['llm.complete', 'llm.stream', 'rerank.dashscope', 'tutorbot.llm.stream']

## 结果文件
- /private/tmp/claude-501/-Users-yehongchen-Developer-CYH-2-Markzuo-deeptutor/dbad531a-c339-49d0-b98c-18e3ad279523/scratchpad/batch_driver/pre_arm_results.json
- /private/tmp/claude-501/-Users-yehongchen-Developer-CYH-2-Markzuo-deeptutor/dbad531a-c339-49d0-b98c-18e3ad279523/scratchpad/batch_driver/langfuse_pre_readout.json
- /private/tmp/claude-501/-Users-yehongchen-Developer-CYH-2-Markzuo-deeptutor/dbad531a-c339-49d0-b98c-18e3ad279523/scratchpad/batch_driver/prom_pre_before.txt
- /private/tmp/claude-501/-Users-yehongchen-Developer-CYH-2-Markzuo-deeptutor/dbad531a-c339-49d0-b98c-18e3ad279523/scratchpad/batch_driver/prom_pre_after.txt
- /private/tmp/claude-501/-Users-yehongchen-Developer-CYH-2-Markzuo-deeptutor/dbad531a-c339-49d0-b98c-18e3ad279523/scratchpad/batch_driver/prom_pre_diff.json
- /private/tmp/claude-501/-Users-yehongchen-Developer-CYH-2-Markzuo-deeptutor/dbad531a-c339-49d0-b98c-18e3ad279523/scratchpad/batch_driver/pre_batch3.log

## 备注（POST 臂需保持一致）
- 驱动: run_arm.py + session_driver.py（同目录），POST 臂命令: `--prefix qa_claude_b2post_ --out post_arm_results.json`
- 会话全部保留未删（--keep-conversation 语义）
- 本批前有两次夭折批(claude_b2pre_ 前缀 429):批1 4哨兵turn+批2 9turn 落在 07:10-07:20Z,已通过重拍批前快照(07:21:04Z)隔离,不污染本批差分;但它们留在生产 DB/Langfuse 中(用户名 claude_b2pre_*)
- summary_maintainer/heartbeat 两个口径(Prometheus 计数器差分 + Langfuse generation 名匹配)均为 0,是 PRE 臂基线的真实读数
