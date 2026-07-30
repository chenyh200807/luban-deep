# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260801_od004_final_r10`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=edc52b5ead795ef658ad754271ca6ab20e4fa566
DEEPTUTOR_RELEASE_ID=1.0.0+edc52b5ead795ef658ad754271ca6ab20e4fa566+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T03:03:58  结束: 2026-07-31T03:05:18
- 结果: **0 PASS / 1 FAIL / 1 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t4_q1_half | 历史事故原题·半答(只答问1-2,其余小问按规范补充) | **FAIL** | A6 | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:FAIL A7:PASS |

## 逐场景证据摘录

### t4_q1_half — FAIL
- 历史事故原题·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785438241063_b444762fd0`; status=completed; latency=75047ms)
  - A0 **PASS** — turn status=completed; visible_len=2621(入口必须完成且回复非空)
  - A1 **PASS** — miss用语['未作答', '漏点'] + 点名漏点['第3问', '问题3', '问题4']
  - A2 **PASS** — 回复中未出现 X/Y 型得分表述(无可违反面)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — score_authority='v1_unavailable:no_reference'; grading_rubric_provenance=''(必须均非空)
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。## 结论  这道题我按你提交的答案逐问批改。**总评：第1问有命中也有漏点，第2问方向对但缺关键项，第3问未作答，第4、5问未作答。** 下面按小问拆。  ---  ## 问题1：安全事故类型 + 安全控制主要内容  **你的答案：** - 安全事故类型：高处坠落、物体打击、机械伤害、触电 - 安全控制主要内容：模板拆除安全控制、泵送混凝土管路固定与作业安全、临边洞口防护  **判定：** 部分正确，有命中，但漏了关键项。  ### 采分点  | 采分点 | 你的答案 | 判定 | |--

完整回复与 metadata 见 `evidence/<场景id>.md`。
