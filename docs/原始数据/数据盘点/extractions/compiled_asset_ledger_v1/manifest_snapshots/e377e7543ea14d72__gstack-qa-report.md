# gstack qa-only Report — WeChat Harness Shadow Surface (R3, 2026-06-06)

- Tool: gstack qa-only (report-only; no source edits/commits) + gstack browse (playwright headless).
- Target: http://localhost:3782/wechat-harness（Next.js dev，NEXT_PUBLIC_API_BASE=http://localhost:8001）。
- Backend: 本地 LOCAL TEST MODE :8001（worktree @ origin/main cc00daef）。
- **Evidence surface: `wechat_harness_shadow`** —— WeChat 渲染器/parity 闭环 harness，NOT 真实微信容器，
  NOT 自由文本 TutorBot 聊天输入。authority 抢权类测试由 near-real 链路覆盖。

## 能测 / 不能测
- 能测：渲染器把 TutorBot 答案渲成小程序气泡的正确性、golden case parity、MCQ 卡片选项+提交、
  实时流式 vs 最终态 vs 历史恢复一致性、案例闭环可见行为、console 健康。
- 不能测：自由学员真题对话、答案 authority 抢权（无自由输入框）。

## 结果（health: 健康 ~95/100）
| 检查 | 结果 |
|---|---|
| 页面加载 | 200，无应用级 console error |
| Renderer parity | **16/16 CASES PARITY** |
| golden case 渲染（Old City Case Terminal / Structured Table Formula Mcq Combo） | 正确渲染：标题/段落/callout/公式块/表格/MCQ block |
| MCQ 卡片交互 | 选 A → "已记录选择：A" → 提交正常 |
| 实时/最终/历史 parity | "实时最终态与历史恢复态一致" |
| 案例闭环（运行闭环） | 触发无 console error |
| console 错误 | 0（仅 playwright 安装提示噪音） |

## 截图证据
screenshots/r3_harness_case_render.png, r3_harness_structured.png, r3_harness_mcq_submit.png, r3_harness_closed_loop.png

## 结论
WeChat 可见渲染层健康。真实学员真题 authority 正确性由 near_real_http_ws（35 轮）评估。
不把本 shadow 面 PASS 当作真实微信 closure。
