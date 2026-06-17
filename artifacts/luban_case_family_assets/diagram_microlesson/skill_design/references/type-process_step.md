# type-process_step · ① 时序/工序原型

- **何时选**:考点本质是"有先后顺序的过程"——错一步/漏前置就出问题。
- **代表考点**:施工流程、工序、起鼓割补、浇筑养护、防水施工顺序、验收流程。
- **展现形式**:分步 step-reveal(一步一屏,逐步揭示)。**手机优先=tab/点"下一步"逐步,不是长滚 scrollytelling**(390px 长滚易迷失、丢上下文)。
- **语义色**(引用 style-guide):`--progress` 蓝=当前步,`--correct` 绿=完成;关键质量/安全控制点用 `--partial` 琥珀停顿提醒。
- **交互**:点"下一步" / 自动旁白逐步推进;步骤指示器(1/n)常驻;可暂停/回看(抗 transient information)。
- **祖师爷参照**:**移动端步骤式向导**——IKEA 装配图(一步一图、前置清晰)、Khan Academy 分步讲解、Duolingo 单屏一题逐步推进。**桌面端 scrollytelling(NYT《Snow Fall》sticky 图区 + 滚动揭示)只借"一屏一步 + before/after 过渡"的叙事拆分,不照搬长滚交互**——手机用点击翻步 + 步骤指示器替代滚动驱动。
- **schema body**:`steps[]`(每步 `id/no/action/brief/why/scoring_expression/common_loss/svg/scoring_point/source_refs`)。
- **验收点(原型专属)**:工序顺序不可颠倒;每步对应一个 why + 采分表达;关键控制点有停顿;漏前置=high_risk 提示。
- **现状**:✅ 已有 `../F16_qigu.json`(起鼓割补)。可增"滚动驱动 + sticky"。
