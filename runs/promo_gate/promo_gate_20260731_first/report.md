# 可宣传质量门 v1 — 运行报告

- run_id: `promo_gate_20260731_first`
- base_url: https://test2.yousenjiaoyu.com
- 部署 SHA(test2): `DEEPTUTOR_GIT_SHA=17286eeb45d0eb165ee1f8ab6399f4448679523e
DEEPTUTOR_RELEASE_ID=1.0.0+17286eeb45d0eb165ee1f8ab6399f4448679523e+production
DEEPTUTOR_GIT_DIRTY=false`
- 开始: 2026-07-31T00:14:38  结束: 2026-07-31T00:17:35
- 结果: **5 PASS / 16 FAIL / 21 场景**(全绿 = 可宣传态)

| 场景 | 标题 | 判定 | 失败断言 | 断言明细 |
|---|---|---|---|---|
| t1_full | 题库内案例(合同价款,qid=8817)·全答 | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t1_half | 题库内案例(qid=8817)·半答(只答问1-2,其余小问按规范补充) | **PASS** | - | A0:PASS A1:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t1_question_only | 题库内案例(qid=8817)·只发题不作答 | **PASS** | - | A0:PASS A3:PASS A5:PASS L1:PASS |
| t1_wrong | 题库内案例(qid=8817)·答错(数值与顺序均错) | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t2_full | 题库内案例(2023质量检测,qid=17357)·全答 | **PASS** | - | A0:PASS A2:PASS A3:PASS A5:PASS A6:PASS A7:PASS |
| t2_half | 题库内案例(qid=17357)·半答(只答不妥之处,其余小问按规范补充) | **FAIL** | A0,A1,A6,A7 | A0:FAIL A1:FAIL A2:PASS A3:PASS A5:PASS A6:FAIL A7:FAIL |
| t2_question_only | 题库内案例(qid=17357)·只发题不作答 | **FAIL** | A0,L1 | A0:FAIL A3:PASS A5:PASS L1:FAIL |
| t2_wrong | 题库内案例(qid=17357)·答错(不妥点判断全错) | **FAIL** | A0,A6,A7 | A0:FAIL A2:PASS A3:PASS A5:PASS A6:FAIL A7:FAIL |
| t3_full | 题库外长案例(2022案例一改写)·全答 | **FAIL** | A0,A6,A7,A4 | A0:FAIL A2:PASS A3:PASS A5:PASS A6:FAIL A7:FAIL A4:FAIL |
| t3_half | 题库外长案例·半答(只答问1-2,其余小问按规范补充) | **FAIL** | A0,A1,A6,A7,A4 | A0:FAIL A1:FAIL A2:PASS A3:PASS A5:PASS A6:FAIL A7:FAIL A4:FAIL |
| t3_question_only | 题库外长案例·只发题不作答 | **FAIL** | A0,L1 | A0:FAIL A3:PASS A5:PASS L1:FAIL |
| t3_wrong | 题库外长案例·答错(等效龄期与评定结论均错) | **FAIL** | A0,A6,A7,A4 | A0:FAIL A2:PASS A3:PASS A5:PASS A6:FAIL A7:FAIL A4:FAIL |
| t4_g1_asis | 历史事故原文·判分死亡事故原题(碳排放案例,带完整作答) | **FAIL** | A0,A6,A7 | A0:FAIL A2:PASS A3:PASS A5:PASS A6:FAIL A7:FAIL |
| t4_g1_wrong | 历史事故原题·答错版(机具/顺序/结论均改错) | **FAIL** | A0,A6,A7 | A0:FAIL A2:PASS A3:PASS A5:PASS A6:FAIL A7:FAIL |
| t4_q1_asis | 历史事故原文·#583拒答事故原题(办公楼5小问,只发题) | **FAIL** | A0,L1 | A0:FAIL A3:PASS A5:PASS L1:FAIL |
| t4_q1_half | 历史事故原题·半答(只答问1-2,其余小问按规范补充) | **FAIL** | A0,A1,A6,A7 | A0:FAIL A1:FAIL A2:PASS A3:PASS A5:PASS A6:FAIL A7:FAIL |
| t5_correct | MCQ(qid=8731 氯离子复试)·答对并给理由 | **FAIL** | A0,M1,L1 | A0:FAIL A5:PASS M1:FAIL L1:FAIL |
| t5_question_only | MCQ(qid=8731)·只发题不作答(答题必有解析) | **FAIL** | A0,M1,L1 | A0:FAIL A5:PASS M1:FAIL L1:FAIL |
| t5_wrong | MCQ(qid=8731)·答错(选D河砂) | **FAIL** | A0,M1,M2,L1 | A0:FAIL A5:PASS M1:FAIL M2:FAIL L1:FAIL |
| t6_edge_ask | KB边界偏门题(金属幕墙板材/气密性)·只问 | **FAIL** | A0,L1 | A0:FAIL A3:PASS A5:PASS L1:FAIL |
| t6_edge_full | KB边界偏门题·带自己的理解求核对 | **FAIL** | A0,L1 | A0:FAIL A3:PASS A5:PASS L1:FAIL |

## 逐场景证据摘录

### t1_full — PASS
- 题库内案例(合同价款,qid=8817)·全答(form=full; turn_id=`turn_1785428082120_056b043c7a`; status=completed; latency=36643ms)
  - A0 **PASS** — turn status=completed; visible_len=3124(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(0.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 0 个采分点，部分命中 0 个，还有 17 个需要补。后面我按小问逐一拆。  ⚠️ **判分覆盖范围**：本次仅对 问题1、问题2、问题3 命中了采分点参考（题面共 5 问）；问题4、问题5 未匹配到采分点参考、**未纳入本次判分**——以上得分只代表已覆盖部分，不是整题成绩。未覆盖小问请补答后再判，或提供该问的标准答案。  **得分预估（仅已覆盖小问）：** 0 / 10 分。 **采分情况：** 命中 0 个，部分命中 0 个，漏/错 

### t1_half — PASS
- 题库内案例(qid=8817)·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=`turn_1785428122785_708725f317`; status=completed; latency=23434ms)
  - A0 **PASS** — turn status=completed; visible_len=1721(入口必须完成且回复非空)
  - A1 **PASS** — 命中「未纳入本次判分」
  - A2 **PASS** — 得分对 [(0.0, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 0 个采分点，部分命中 0 个，还有 3 个需要补。后面我按小问逐一拆。  ⚠️ **判分覆盖范围**：本次仅对 问题1 命中了采分点参考（题面共 5 问）；问题2、问题3、问题4、问题5 未匹配到采分点参考、**未纳入本次判分**——以上得分只代表已覆盖部分，不是整题成绩。未覆盖小问请补答后再判，或提供该问的标准答案。  **得分预估（仅已覆盖小问）：** 0 / 10 分。 **采分情况：** 命中 0 个，部分命中 0 个，漏/错 3

### t1_question_only — PASS
- 题库内案例(qid=8817)·只发题不作答(form=question_only; turn_id=`turn_1785428150443_8a2d1406e5`; status=completed; latency=35361ms)
  - A0 **PASS** — turn status=completed; visible_len=3397(入口必须完成且回复非空)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **PASS** — len=3397 (>=300)
  - 回复摘录: 这道案例题有 5 问，我先按小问逐一拆解，每问给结论、判定依据、采分点、易错点。  ---  ## 第 1 问 · 合同签订不妥与文件解释顺序  ### 结论 **不妥之处**：甲乙双方通过协商对合同协议书、专用条款、通用条款的修改意见达成一致后签订施工合同。  **正确做法**：保持待签合同与招标文件、投标文件的**一致性**。合同内容、承包范围、工期、造价、计价方式、质量要求等实质性内容不得随意修改。  **5 个合同文件解释优先顺序**（递减）： 1. ==合同协议书== 2. ==中标通知书== 3. ==投标函== 4. ==专用合同条款== 5. ==通用合同条款==  ### 判

### t1_wrong — PASS
- 题库内案例(qid=8817)·答错(数值与顺序均错)(form=wrong; turn_id=`turn_1785428189873_712879a654`; status=completed; latency=27097ms)
  - A0 **PASS** — turn status=completed; visible_len=1681(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(7.15, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 5 个采分点，部分命中 0 个，还有 2 个需要补。后面我按小问逐一拆。  ⚠️ **判分覆盖范围**：本次仅对 问题1 命中了采分点参考（题面共 5 问）；问题2、问题3、问题4、问题5 未匹配到采分点参考、**未纳入本次判分**——以上得分只代表已覆盖部分，不是整题成绩。未覆盖小问请补答后再判，或提供该问的标准答案。  **得分预估（仅已覆盖小问）：** 7.15 / 10 分。 **采分情况：** 命中 5 个，部分命中 0 个，漏/

### t2_full — PASS
- 题库内案例(2023质量检测,qid=17357)·全答(form=full; turn_id=`turn_1785428221037_99bde93dd4`; status=completed; latency=19664ms)
  - A0 **PASS** — turn status=completed; visible_len=1565(入口必须完成且回复非空)
  - A2 **PASS** — 得分对 [(5.01, 10.0)] 全部 X<=Y 且不超官方满分
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **PASS** — score_authority=rubric_scored_v1; grading_rubric_provenance=on_the_fly_reference
  - A7 **PASS** — selected_mode=deep
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。  ## 批改结论 这道题我先给你一个总判断：命中 3 个采分点，部分命中 0 个，还有 2 个需要补。后面我按小问逐一拆。  **得分预估：** 5.01 / 10 分。 **采分情况：** 命中 3 个，部分命中 0 个，漏/错 2 个。  **先看最该补的地方：** 1. 第1问：正确做法：建设单位应在编制工程概预算时合理核算检测费用，单独列支并按合同约定及时支付。 2. 第1问：见证记录内容还包括：取样、制样、标识、封志、送检、现场检测。  提示：本轮含高风险判分点，建议教师复核后作

### t2_half — FAIL
- 题库内案例(qid=17357)·半答(只答不妥之处,其余小问按规范补充)(form=half; turn_id=`turn_1785428244723_8bd07ed512`; status=ws_exception; latency=5937ms)
  - A0 **FAIL** — turn status=ws_exception; visible_len=52(入口必须完成且回复非空)
  - A1 **FAIL** — 半答卷未标记漏答:无「未纳入本次判分」;miss用语命中=[];漏点点名命中=[]
  - A2 **PASS** — 回复中未出现 X/Y 型得分表述(无可违反面)
  - A3 **PASS** — 口诀段无出处但非顿号拼接形态(按模板句放行)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — 未取到 result 事件 metadata(远端查询失败或无 result 事件)
  - A7 **FAIL** — 未取到 result 事件 metadata
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 这道案例题我已经进入逐采分点批改。  先拆题、再判命中/漏点，最后给得分、易错点、记忆口诀和下一步练习。

### t2_question_only — FAIL
- 题库内案例(qid=17357)·只发题不作答(form=question_only; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=136ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **FAIL** — len=0 (>=300)
  - 回复摘录: 

### t2_wrong — FAIL
- 题库内案例(qid=17357)·答错(不妥点判断全错)(form=wrong; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=157ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A2 **PASS** — 回复中未出现 X/Y 型得分表述(无可违反面)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — 未取到 result 事件 metadata(远端查询失败或无 result 事件)
  - A7 **FAIL** — 未取到 result 事件 metadata
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 

### t3_full — FAIL
- 题库外长案例(2022案例一改写)·全答(form=full; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=134ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A2 **PASS** — 回复中未出现 X/Y 型得分表述(无可违反面)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — 未取到 result 事件 metadata(远端查询失败或无 result 事件)
  - A7 **FAIL** — 未取到 result 事件 metadata
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **FAIL** — 库外题未见「诊断得分预估/不硬估标准分」类免责表述
  - 回复摘录: 

### t3_half — FAIL
- 题库外长案例·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=141ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A1 **FAIL** — 半答卷未标记漏答:无「未纳入本次判分」;miss用语命中=[];漏点点名命中=[]
  - A2 **PASS** — 回复中未出现 X/Y 型得分表述(无可违反面)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — 未取到 result 事件 metadata(远端查询失败或无 result 事件)
  - A7 **FAIL** — 未取到 result 事件 metadata
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **FAIL** — 库外题未见「诊断得分预估/不硬估标准分」类免责表述
  - 回复摘录: 

### t3_question_only — FAIL
- 题库外长案例·只发题不作答(form=question_only; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=151ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **FAIL** — len=0 (>=300)
  - 回复摘录: 

### t3_wrong — FAIL
- 题库外长案例·答错(等效龄期与评定结论均错)(form=wrong; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=151ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A2 **PASS** — 回复中未出现 X/Y 型得分表述(无可违反面)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — 未取到 result 事件 metadata(远端查询失败或无 result 事件)
  - A7 **FAIL** — 未取到 result 事件 metadata
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - A4 **FAIL** — 库外题未见「诊断得分预估/不硬估标准分」类免责表述
  - 回复摘录: 

### t4_g1_asis — FAIL
- 历史事故原文·判分死亡事故原题(碳排放案例,带完整作答)(form=full; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=147ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A2 **PASS** — 回复中未出现 X/Y 型得分表述(无可违反面)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — 未取到 result 事件 metadata(远端查询失败或无 result 事件)
  - A7 **FAIL** — 未取到 result 事件 metadata
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 

### t4_g1_wrong — FAIL
- 历史事故原题·答错版(机具/顺序/结论均改错)(form=wrong; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=159ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A2 **PASS** — 回复中未出现 X/Y 型得分表述(无可违反面)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — 未取到 result 事件 metadata(远端查询失败或无 result 事件)
  - A7 **FAIL** — 未取到 result 事件 metadata
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 

### t4_q1_asis — FAIL
- 历史事故原文·#583拒答事故原题(办公楼5小问,只发题)(form=question_only; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=138ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **FAIL** — len=0 (>=300)
  - 回复摘录: 

### t4_q1_half — FAIL
- 历史事故原题·半答(只答问1-2,其余小问按规范补充)(form=half; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=145ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A1 **FAIL** — 半答卷未标记漏答:无「未纳入本次判分」;miss用语命中=[];漏点点名命中=[]
  - A2 **PASS** — 回复中未出现 X/Y 型得分表述(无可违反面)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - A6 **FAIL** — 未取到 result 事件 metadata(远端查询失败或无 result 事件)
  - A7 **FAIL** — 未取到 result 事件 metadata
  - A8 **SKIP** — 错因码分布断言,拍板后启用
  - 回复摘录: 

### t5_correct — FAIL
- MCQ(qid=8731 氯离子复试)·答对并给理由(form=full; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=149ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A5 **PASS** — 无罐头拒答用语
  - M1 **FAIL** — contains_all['外加剂'] 缺 ['外加剂']
  - L1 **FAIL** — len=0 (>=60)
  - 回复摘录: 

### t5_question_only — FAIL
- MCQ(qid=8731)·只发题不作答(答题必有解析)(form=question_only; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=141ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A5 **PASS** — 无罐头拒答用语
  - M1 **FAIL** — contains_all['外加剂'] 缺 ['外加剂']
  - L1 **FAIL** — len=0 (>=60)
  - 回复摘录: 

### t5_wrong — FAIL
- MCQ(qid=8731)·答错(选D河砂)(form=wrong; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=118ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A5 **PASS** — 无罐头拒答用语
  - M1 **FAIL** — contains_all['外加剂'] 缺 ['外加剂']
  - M2 **FAIL** — contains_any['不正确', '不对', '错误', '误选', '不是', '并非'] 命中 []
  - L1 **FAIL** — len=0 (>=60)
  - 回复摘录: 

### t6_edge_ask — FAIL
- KB边界偏门题(金属幕墙板材/气密性)·只问(form=question_only; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=160ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **FAIL** — len=0 (>=150)
  - 回复摘录: 

### t6_edge_full — FAIL
- KB边界偏门题·带自己的理解求核对(form=full; turn_id=``; status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; latency=125ms)
  - A0 **FAIL** — turn status=driver_error:create_conversation_failed:502:{'raw_text': '<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n'}; visible_len=0(入口必须完成且回复非空)
  - A3 **PASS** — 无口诀段(N/A)
  - A5 **PASS** — 无罐头拒答用语
  - L1 **FAIL** — len=0 (>=150)
  - 回复摘录: 

完整回复与 metadata 见 `evidence/<场景id>.md`。
