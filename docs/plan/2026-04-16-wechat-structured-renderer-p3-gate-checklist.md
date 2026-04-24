# 微信结构化渲染器 P3 Gate 真机清单

## 1. 目的

这份清单用于关闭 [2026-04-16-wechat-structured-teaching-renderer-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/docs/plan/2026-04-16-wechat-structured-teaching-renderer-prd.md) 中的 P3 gate。

它不是新方案文档，只是执行清单。所有样例统一复用：

- [wechat_structured_renderer_cases.json](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/tests/fixtures/wechat_structured_renderer_cases.json)

## 2. 设备矩阵

至少覆盖以下五组：

1. 微信开发者工具一轮
2. iPhone 主流机型一台
3. Android 中端机一台
4. Android 低端机一台
5. 弱网场景一轮

## 3. 样例清单

### 3.1 `structured_steps_recap_chart_combo`

检查项：

1. `steps` 按 `index` 稳定显示，不乱序、不丢步
2. 步骤标题与详情都可见，不被正文覆盖
3. `recap` 显示为“教学总结”语义卡，而不是旧 `summary` 文本块
4. `chart` 标题、摘要、series 概览可见
5. `fallback_table` 在图形不可用时仍可读
6. block 顺序保持 `steps -> recap -> chart`

### 3.2 `structured_chart_fallback_table_only`

检查项：

1. 没有正式图形时不出现空白区域
2. 图表标题与摘要仍可读
3. `fallback_table` 横滑可达，不出现静默裁切
4. 用户能从数据卡理解主结论，不依赖图形本体

## 4. 失败判定

任一项出现以下问题，P3 gate 不能关闭：

1. `steps` 被当成普通 Markdown 列表或纯文本显示
2. `recap` 被旧 `summary` 文本样式替代，或标题/摘要缺失
3. `chart` 区域空白，只剩容器但没有数据内容
4. `fallback_table` 不可滑动、不可达或被裁切
5. wx 与宿主分包在 block 顺序、可见性或样式上明显不一致

## 5. 通过条件

同时满足以下条件，才允许把 P3 标记为完成：

1. 样例集对应的 node / pytest 回归全绿
2. 微信开发者工具、iPhone 与 Android 抽样都通过
3. 弱网场景下 `chart` 的数据卡回退行为符合预期
4. 至少留存一轮截图或录屏证据
