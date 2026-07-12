# Battle2 配对基线批 — POST 臂结果（部署#2 后,生产 SHA 34707970）

- 批窗口 (UTC): **2026-07-12T07:42:55.686Z → 2026-07-12T07:49:38.357Z** (wall 402.7s)
- 身份: 前缀 `qa_claude_b2post_`; 用户池: qa_claude_b2post_1783842145_0, qa_claude_b2post_1783842155_1, qa_claude_b2post_1783842164_2

## 通过率
- 主 turn: **32/32** passed; 哨兵: **10/10** passed; 失败清单: 空

## 客户端墙钟
- 主 32 turn: p50 **8903.4** / p95 **15477.7** / min 1492.0 / max 19948.9
- 哨兵前5: [12413.2, 9184.6, 7568.7, 4286.4, 5113.6]
- 哨兵后5: [4356.1, 4066.5, 4398.7, 3405.0, 5421.2]
- 哨兵10合并: p50 **4398.7** / p95 **12413.2**

## Prometheus 差分 (prom_post_before 07:42:08Z / prom_post_after 07:49:59Z; 部署后容器计数器从零起)
- TTFVT content.delta: count Δ=**41**, 均值 **4602ms**; result.response: Δ=1 (624ms)
- 桶累计 Δ: ≤1s:3 ≤2s:8 ≤4s:27 ≤8s:35 ≤16s:39 ≤32s:41
- **summary_maintainer 计数器 (部署#2 新增,首次有真数据):**
  - `decision="run_evidence",outcome="changed"` = 14
  - `decision="run_evidence",outcome="no_change"` = 11
  - `decision="run_fail_open",outcome="changed"` = 2
  - `decision="run_fail_open",outcome="no_change"` = 4
  - `decision="skip_throttled",outcome="skipped"` = 11
  - 合计决策 42 次 (= 42 turn 全覆盖); 实跑 31 次, throttle 跳过 11 次
- **response_mode 计数器 (新增):**
  - `mode="fast",model_tier="primary"` = 30

## Langfuse 读数（窗口 2026-07-12T07:41:55.000Z → 2026-07-12T07:54:38.000Z）
- traces: 45; GENERATION: 88（主 66 / 哨兵 16）
- 每 trace generation: avg **2.1** / p50 2 / p95 3 / max 4 (n=42)
- token: 输入 **443,341** / 输出 **30,907** / 合计 **474,248**; 成本 **$0.492321**
- TTFT: tutorbot.llm.stream p50 **1293.0** / p95 **3518.0** (n=30); llm.stream p50 **5453.0** / p95 **9459.0** (n=36)
- TTFT 哨兵单列: p50 **1816.0** / p95 **4925.0** (n=16); 主区间 p50 **3301.0** / p95 **9459.0** (n=45)
- trace 总时长: 主 p50 **15409.0** / p95 **27114.0**; 哨兵 p50 **11817.0** / p95 **16367.0**
- 注: Langfuse 名匹配 'summary'/'heartbeat' 两臂均为 0——summary maintainer 的 LLM 调用不以 summary 命名(混在 llm.complete),其权威读数是上方 Prometheus 计数器

## 结果文件
- /private/tmp/claude-501/-Users-yehongchen-Developer-CYH-2-Markzuo-deeptutor/dbad531a-c339-49d0-b98c-18e3ad279523/scratchpad/batch_driver/post_arm_results.json
- /private/tmp/claude-501/-Users-yehongchen-Developer-CYH-2-Markzuo-deeptutor/dbad531a-c339-49d0-b98c-18e3ad279523/scratchpad/batch_driver/langfuse_post_readout.json
- /private/tmp/claude-501/-Users-yehongchen-Developer-CYH-2-Markzuo-deeptutor/dbad531a-c339-49d0-b98c-18e3ad279523/scratchpad/batch_driver/prom_post_before.txt
- /private/tmp/claude-501/-Users-yehongchen-Developer-CYH-2-Markzuo-deeptutor/dbad531a-c339-49d0-b98c-18e3ad279523/scratchpad/batch_driver/prom_post_after.txt
- /private/tmp/claude-501/-Users-yehongchen-Developer-CYH-2-Markzuo-deeptutor/dbad531a-c339-49d0-b98c-18e3ad279523/scratchpad/batch_driver/prom_post_diff.json
- /private/tmp/claude-501/-Users-yehongchen-Developer-CYH-2-Markzuo-deeptutor/dbad531a-c339-49d0-b98c-18e3ad279523/scratchpad/batch_driver/post_batch.log
- /private/tmp/claude-501/-Users-yehongchen-Developer-CYH-2-Markzuo-deeptutor/dbad531a-c339-49d0-b98c-18e3ad279523/scratchpad/batch_driver/pre_post_comparison.md
