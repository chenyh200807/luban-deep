// test_chat_next_best_action_contract.js — 「下一步训练」卡片行动闭环契约
// Run: node wx_miniprogram/tests/test_chat_next_best_action_contract.js
//
// 钉住三件事（防回退）：
//   1) chat.js 存在 onNextBestActionTap，且经既有 _send 管线发定向练题请求
//      （端上不出题、不造第二处方权威）；
//   2) 注入面收口：组装进消息的 target 必须截长（slice(0, 80)），流式中禁点；
//   3) chat.wxml 卡片绑定 bindtap="onNextBestActionTap" 并携带 data-msgid。

var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) {
    pass += 1;
    return;
  }
  fail += 1;
  errors.push("FAIL: " + message);
}

var chatJs = fs.readFileSync(path.join(__dirname, "../pages/chat/chat.js"), "utf8");
var chatWxml = fs.readFileSync(path.join(__dirname, "../pages/chat/chat.wxml"), "utf8");

// 1) handler 存在且走既有发送管线
assert(
  /onNextBestActionTap:\s*function/.test(chatJs),
  "[handler] chat.js 必须定义 onNextBestActionTap",
);
var handlerMatch = chatJs.match(/onNextBestActionTap:\s*function[\s\S]*?\n  \},/);
assert(!!handlerMatch, "[handler] 能截取 handler 体");
var handler = handlerMatch ? handlerMatch[0] : "";
assert(
  handler.indexOf("this._send(") !== -1,
  "[handler] 必须经既有 _send 管线发送（不得新建发送通道）",
);
assert(
  handler.indexOf("针对我的薄弱点出一道练习题") !== -1,
  "[handler] 定向练题文案前缀不得丢失",
);

// 2) 注入面与状态守卫
assert(
  handler.indexOf(".slice(0, 80)") !== -1,
  "[guard] 组装进消息的 target 必须截长 80",
);
assert(
  handler.indexOf("isStreaming") !== -1,
  "[guard] 流式进行中必须禁点",
);
assert(
  handler.indexOf("nextBestAction") !== -1,
  "[guard] handler 必须从消息上的 nextBestAction 取数，不得另引权威",
);

// 3) wxml 绑定
assert(
  /class="nba-go"[^>]*bindtap="onNextBestActionTap"/.test(chatWxml) ||
    /bindtap="onNextBestActionTap"[^>]*class="nba-go"/.test(chatWxml),
  "[wxml] nba-go 必须绑定 onNextBestActionTap",
);
assert(
  /class="nba-go"[\s\S]{0,120}data-msgid="\{\{item\.id\}\}"/.test(chatWxml) ||
    /data-msgid="\{\{item\.id\}\}"[\s\S]{0,120}class="nba-go"/.test(chatWxml),
  "[wxml] nba-go 必须携带 data-msgid",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("PASS test_chat_next_best_action_contract.js (" + pass + " assertions)");
process.exit(0);
