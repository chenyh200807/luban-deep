# N01 网络计划 video-first 深母题原型

## Teaching Spine

- Topic: 网络计划关键线路判断。
- Target learner: 会背概念，但做题时容易把“最长单项工作”当关键线路、漏写总工期或漏写判断依据的建造师考生。
- Wrong idea: `C 工作 4 天最长，所以关键线路就是 C。`
- Visual correction: 关键线路是一条从开始到结束、总时差为 0 的连续线路。
- Exam phrase: `关键线路为 开始-A-C-E-结束，总工期 10 天；理由是 A、C、E 的总时差均为 0。`
- Warm correction: 你不是不会算，是第一眼看错了对象：别找最长的工作，要找没有缓冲的路。
- Authority: candidate teaching prototype, not official scoring truth.

## Beat Sheet

| Beat | Visual action | Spoken/subtitle sentence | What disappears before next beat |
| --- | --- | --- | --- |
| 1 trap | 点亮 C，划掉“最长单项=关键线路” | “C 最长，所以关键线路是 C”这句话会丢分，因为关键线路不是一个工作。 | 擦掉错误等式，保留网络图。 |
| 2 logic | 描粗紧前紧后箭线 | 先看紧前紧后：A、B 先做，C、D 等 A，D 还等 B，E 等 C 和 D。 | 淡出错误提示，只留下逻辑箭线。 |
| 3 forward | 写 ES-EF | 顺推时，遇到多个紧前工作，取完成最晚的那个。 | 保留早时间，准备叠加迟时间。 |
| 4 backward | 写 LS-LF | 逆推不是再算一遍工期，而是在找不拖总工期的最晚时间。 | 淡化早迟时间，突出总时差。 |
| 5 float | 贴总时差标签 | 判断关键线路看总时差：B 有 3 天，D 有 2 天，它们有缓冲，不控制总工期。 | 擦掉非关键工作强调，只留下 0 时差链。 |
| 6 critical | 红线贯通 A-C-E | 把总时差为 0 的工作连起来，就是 开始-A-C-E-结束，总工期 10 天。 | 清理计算痕迹，准备写答案句。 |
| 7 score | 写完整采分句 | 考试不要只写 A-C-E，要把线路、总工期、判断依据放进同一句。 | 最终板只保留关键线路和采分句。 |

## Acceptance

- 首屏必须是白板视频讲解，不是题卡列表。
- 第 1 幕不能提前给出正确关键线路。
- 第 6/7 幕才出现红色关键线路和采分句。
- 三连问必须覆盖：路径判断、采分表达、总时差迁移。
- JSON 里的关键线路、总工期、总时差必须通过 deterministic CPM 校验。
