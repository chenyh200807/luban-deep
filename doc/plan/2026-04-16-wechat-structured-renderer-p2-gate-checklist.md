# 微信结构化渲染器 P2 Gate 真机清单

## 1. 目的

这份清单用于关闭 [2026-04-16-wechat-structured-teaching-renderer-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/plan/2026-04-16-wechat-structured-teaching-renderer-prd.md) 中的 P2 gate。

它不是新方案文档，只是执行清单。所有样例统一复用：

- [wechat_structured_renderer_cases.json](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/tests/fixtures/wechat_structured_renderer_cases.json)

## 2. 设备矩阵

至少覆盖以下四组：

1. iPhone 主流机型一台
2. Android 中端机一台
3. Android 低端机一台
4. 弱网场景一轮

## 3. 样例清单

### 3.1 `structured_table_formula_mcq_combo`

检查项：

1. 正文说明可见，不遮挡结构化 block
2. `compact_cards` 视图可读，不出现横向裁切
3. 表格重点单元格高亮可见
4. 公式 SVG 若可加载，则图片与文本都可见
5. MCQ 仍可点击，不被表格/公式覆盖
6. 弱网下即使 SVG 加载慢，公式文本仍可见

### 3.2 `structured_formula_fallback_text_only`

检查项：

1. 无 SVG 时，`display_text` 直接可见
2. `copy_text` 可长按复制
3. 不出现空白公式卡
4. 中文正文与公式块间距自然

### 3.3 `structured_inline_formula_and_scroll_table`

检查项：

1. 行内公式块可见且不乱码
2. 横滑策略文案可见
3. 表格横滑流畅，不出现内容被静默裁切
4. 窄屏下最后一列仍可到达

## 4. 失败判定

任一项出现以下问题，P2 gate 不能关闭：

1. 结构化 block 不显示，只剩正文
2. 公式区域空白或只显示 broken image
3. 表格内容被裁切但用户感知不到
4. MCQ 被正文或其他 block 覆盖导致不可点击
5. wx 与宿主分包表现明显不一致

## 5. 通过条件

同时满足以下条件，才允许把 P2 标记为完成：

1. 样例集对应的 node / pytest 回归全绿
2. iPhone 与 Android 抽样都通过
3. 弱网场景下公式与表格的回退行为符合预期
4. 至少留存一轮截图或录屏证据
