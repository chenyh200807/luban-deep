# 微信结构化渲染器开发者工具验证 Runbook

## 1. 目的

这份 runbook 用于把 P2 / P3 的剩余验证变成可执行流程，减少“靠口述复现”与“临时手工构造消息”的不确定性。

它服务于以下文档：

1. [2026-04-16-wechat-structured-teaching-renderer-prd.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/plan/2026-04-16-wechat-structured-teaching-renderer-prd.md)
2. [2026-04-16-wechat-structured-renderer-p2-gate-checklist.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/plan/2026-04-16-wechat-structured-renderer-p2-gate-checklist.md)
3. [2026-04-16-wechat-structured-renderer-p3-gate-checklist.md](/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/doc/plan/2026-04-16-wechat-structured-renderer-p3-gate-checklist.md)

## 2. 前置条件

1. 先跑自动回归：
   - `.venv/bin/pytest tests/services/test_render_presentation.py -q`
   - `/tmp/deeptutor-nodeenv/bin/node wx_miniprogram/tests/test_render_schema.js`
   - `/tmp/deeptutor-nodeenv/bin/node wx_miniprogram/tests/test_ai_message_state.js`
   - `/tmp/deeptutor-nodeenv/bin/node wx_miniprogram/tests/test_renderer_parity.js`
   - `/tmp/deeptutor-nodeenv/bin/node wx_miniprogram/tests/test_structured_block_layout.js`
2. 微信开发者工具导入：
   - `wx_miniprogram/`
   - `yousenwebview/`
3. 打开聊天页，确保当前页实例存在

## 3. Fixture 注入方式

聊天页已提供 devtools 调试入口：

1. `debugReplaceMessagesWithStructuredSample(sample)`

它只在开发者工具环境使用，用于把当前聊天页替换成一条结构化 AI 消息，不依赖后端接口。

### 3.1 生成 console 片段

在终端执行：

```bash
python scripts/print_wechat_renderer_fixture_snippet.py structured_steps_recap_chart_combo
```

或：

```bash
python scripts/print_wechat_renderer_fixture_snippet.py structured_table_formula_mcq_combo
```

脚本会输出可直接粘贴到开发者工具 console 的片段。

### 3.2 在开发者工具执行

在聊天页 console 粘贴脚本输出内容，例如：

```js
const page = getCurrentPages().slice(-1)[0];
page.debugReplaceMessagesWithStructuredSample({
  content: "步骤、总结和图表一起出现时都必须可读。",
  presentation: {
    blocks: [
      { type: "steps", title: "解题步骤", steps: [{ index: 1, title: "审题" }] },
      { type: "recap", title: "本节课总结", summary: "先结构化，再渲染。" }
    ],
    fallback_text: "步骤、总结和图表一起出现时都必须可读。",
    meta: { streamingMode: "block_finalized" }
  }
});
```

执行成功后，当前聊天页会只保留这条结构化消息，便于截图和样式检查。

## 4. 建议执行顺序

1. 先在 `wx_miniprogram/` 执行 P2 样例
2. 再在 `wx_miniprogram/` 执行 P3 样例
3. 再在 `yousenwebview/` 的聊天页重复同样注入
4. 最后按 P2 / P3 checklist 做截图或录屏留证

## 5. 推荐样例

P2：

1. `structured_table_formula_mcq_combo`
2. `structured_formula_fallback_text_only`
3. `structured_inline_formula_and_scroll_table`

P3：

1. `structured_steps_recap_chart_combo`
2. `structured_chart_fallback_table_only`

## 6. 通过证据

每个端至少保留以下证据：

1. P2 一张截图或一段录屏
2. P3 一张截图或一段录屏
3. 弱网或资源失败场景一轮证据
4. 对应 checklist 的勾选结果
