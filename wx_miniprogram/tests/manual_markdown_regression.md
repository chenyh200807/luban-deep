# 微信小程序 Markdown 排版回归清单

适用场景：检查历史上出现过的“内容缺失”“冒号单独换行”“箭头后的重点内容漂移”“加粗标签和正文被拆开”等问题。

## 开发者工具注入方式

1. 打开微信开发者工具并进入聊天页。
2. 在 Console 执行：

```js
const pages = getCurrentPages();
const chat = pages[pages.length - 1];
chat.debugListMarkdownRegressionSamples();
```

3. 按需加载固定样例：

```js
chat.debugLoadMarkdownRegressionSample("expert_argument_full_answer");
chat.debugLoadMarkdownRegressionSample("waterproof_layers_mixed_inline");
chat.debugLoadMarkdownRegressionSample("bolt_points_colon_wrap");
```

## 核对项

### 1. `expert_argument_full_answer`

- 顶部必须先看到 `第一题的答案：`，不能只剩题目或后半段。
- `需要专家论证。` 与后面的 `判断依据：` 必须完整显示。
- `踩分点` 下的 5 条有序列表必须全部可见，不能截断。

### 2. `waterproof_layers_mixed_inline`

- `屋面一级防水 → 不应少于3道防水层` 这一句要保持在同一个列表语义里，不能把 `→` 或加粗答案拆飞。
- `选择题常考…… → 3道` 里的 `3道` 不能单独漂到下一段或脱离该条目。
- `定义/特点/举例` 后面的冒号和正文不能错位。

### 3. `bolt_points_colon_wrap`

- `1. 时间限制：必须记住……` 中的 `：` 不能单独挂到下一行。
- `2. 顺序要求：初拧→复拧→终拧……` 中箭头前后内容不能拆成孤立片段。
- `易错点提醒：` 必须显示完整标题，且下面 3 条 bullet 正常渲染。

## 模拟器与真机

- 模拟器：先执行以上 3 个样例，逐条截图确认。
- 真机：通过开发者工具预览二维码进入同一页面，重复以上 3 个样例检查。
- 判定标准：只要出现“标题还在但前文丢失”“冒号单独换行”“箭头后的答案漂移”，就视为未通过。
