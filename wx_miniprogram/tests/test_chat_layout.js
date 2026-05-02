// test_chat_layout.js — regression checks for wx_miniprogram chat layout
// Run: node wx_miniprogram/tests/test_chat_layout.js

var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

var chatJs = fs.readFileSync(
  path.join(__dirname, "../pages/chat/chat.js"),
  "utf8",
);
var chatWxml = fs.readFileSync(
  path.join(__dirname, "../pages/chat/chat.wxml"),
  "utf8",
);
var chatWxss = fs.readFileSync(
  path.join(__dirname, "../pages/chat/chat.wxss"),
  "utf8",
);

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

function getCssRule(selector) {
  var escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  var match = chatWxss.match(new RegExp(escaped + "\\s*\\{([\\s\\S]*?)\\}"));
  return match ? match[1] : "";
}

function getRpxValue(rule, property) {
  if (!rule) return null;
  var escaped = property.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  var match = rule.match(new RegExp(escaped + "\\s*:\\s*([0-9.]+)rpx"));
  return match ? Number(match[1]) : null;
}

function getPaddingTopRpx(rule) {
  if (!rule) return null;
  var match = rule.match(/padding\s*:\s*([0-9.]+)rpx/);
  return match ? Number(match[1]) : null;
}

var navConstantMatch = chatJs.match(/var NAVBAR_INNER_HEIGHT_RPX = (\d+);/);
var navConstant = navConstantMatch ? Number(navConstantMatch[1]) : null;
var navInnerRule = getCssRule(".navbar-inner");
var navLogoRule = getCssRule(".nav-logo");
var navLogoChatRule = getCssRule(".nav-logo-chat");
var msgListRule = getCssRule(".msg-list");

assert(navConstant !== null, "chat.js should define NAVBAR_INNER_HEIGHT_RPX");
assert(
  /Math\.round\(\s*\(NAVBAR_INNER_HEIGHT_RPX \* windowWidth\) \/ 750,\s*\)/.test(
    chatJs,
  ),
  "chat.js should derive nav height from window width instead of hard-coded px",
);
assert(
  chatWxml.indexOf("navbar {{hasMessages ? 'navbar-chat' : ''}}") >= 0,
  "chat.wxml should enable a dedicated chat navbar style",
);
assert(
  chatWxml.indexOf("nav-logo {{hasMessages ? 'nav-logo-chat' : ''}}") >= 0,
  "chat.wxml should enable a compact logo in chat mode",
);
assert(
  chatWxml.indexOf("class=\"nav-logo {{hasMessages ? 'nav-logo-chat' : ''}}\"") <
    chatWxml.indexOf("class=\"nav-back-pill\""),
  "chat navbar should place the logo before the back-home pill",
);
assert(
  /showInternalStatus:\s*true/.test(chatJs),
  "chat.js should default workflow status panels to visible during streaming",
);
assert(
  chatWxml.indexOf('class="nav-points-pill" wx:if="{{!hasMessages}}"') >= 0 &&
    chatWxml.indexOf("{{userPoints}}") >= 0,
  "chat navbar should show points only before entering the message scene",
);
assert(
  chatWxml.indexOf('class="nav-chat-actions" wx:if="{{hasMessages}}"') >= 0 &&
    chatWxml.indexOf('bindtap="clearMessages" aria-role="button" aria-label="新建对话"') >= 0 &&
    chatWxml.indexOf('bindtap="onChatMoreActions" aria-role="button" aria-label="更多对话操作"') >= 0,
  "chat scene should expose a ChatGPT-like new-chat and more-actions pair",
);
assert(
  chatJs.indexOf('itemList: ["归档对话", "删除对话"]') >= 0 &&
    chatJs.indexOf('.batchConversations("archive", [convId])') >= 0 &&
    chatJs.indexOf(".deleteConversation(convId)") >= 0,
  "chat more menu should reuse existing archive and delete conversation APIs",
);
assert(
  (chatWxml.match(/class="nav-points-num">\{\{userPoints\}\}/g) || []).length === 1 &&
    chatWxml.indexOf("class=\"points-pill\"") < 0 &&
    chatWxml.indexOf("class=\"points-num\"") < 0,
  "chat home should render the points balance once, using the navbar as the single visible entry",
);
assert(
  chatWxml.indexOf("focus-label") >= 0 &&
    chatWxml.indexOf("focus-title") >= 0 &&
    chatWxml.indexOf("focus-meta") >= 0 &&
    /focusTitle:\s*""/.test(chatJs) &&
    /focusMeta:\s*""/.test(chatJs),
  "today focus should be structured into label, title, and meta instead of one crowded text string",
);
assert(
  chatJs.indexOf('focusText: "今日焦点') < 0 &&
    chatJs.indexOf('update.focusText = "今日焦点') < 0,
  "today focus copy should not bake the section label into the action title",
);
assert(
  chatJs.indexOf("d.today_focus || today.focus") >= 0 &&
    chatJs.indexOf("var weakNodes = mastery.weak_nodes") < 0 &&
    chatJs.indexOf("buildFocusQuery(focus, update.focusTitle)") >= 0 &&
    chatJs.indexOf("继续我的学习计划") < 0 &&
    chatJs.indexOf("给我安排5道高价值专项训练题") < 0 &&
    chatJs.indexOf("5题快速摸底") < 0 &&
    chatJs.indexOf("入门导学") < 0 &&
    chatJs.indexOf("下一步学习推进") >= 0,
  "chat home should render backend today_focus and keep fallback focused on knowledge explanation",
);
assert(
  chatWxml.indexOf("class=\"hero-more-btn\"") >= 0 &&
    chatJs.indexOf("onHeroMoreActions") >= 0,
  "hero secondary actions should be consolidated behind a more menu",
);
assert(
  chatWxml.indexOf("class=\"row-icon-btn\" bindtap=\"onToggleTheme\"") < 0 &&
    chatWxml.indexOf("class=\"row-icon-btn\" bindtap=\"goRecharge\"") < 0 &&
    chatWxml.indexOf("class=\"avatar\" bindtap=\"goProfile\"") < 0,
  "hero should not expose ambiguous icon-only shortcuts beside the more menu",
);

var navInnerHeight = getRpxValue(navInnerRule, "height");
var navLogoHeight = getRpxValue(navLogoRule, "height");
var navLogoChatHeight = getRpxValue(navLogoChatRule, "height");
var msgListPaddingTop = getPaddingTopRpx(msgListRule);

assert(navInnerHeight === navConstant, "navbar inner height should match JS nav constant");
assert(navLogoHeight !== null && navLogoHeight < navInnerHeight, "default logo height should fit inside navbar");
assert(
  navLogoChatHeight !== null && navLogoChatHeight < navLogoHeight,
  "chat logo height should be smaller than default logo height",
);
assert(
  msgListPaddingTop !== null && msgListPaddingTop >= 24,
  "message list should reserve extra top padding below navbar",
);
assert(
  getCssRule(".navbar-chat").indexOf("backdrop-filter") >= 0,
  "chat navbar should provide a visual separation layer",
);
assert(
  chatWxml.indexOf(
    "thinking-inline\" wx:elif=\"{{showInternalStatus && item.thinkingStatus && !(item.mcqCards && item.mcqCards.length) && !(item.workflowEntries.length && (item.renderableContent || item.blocks.length || (item.mcqCards && item.mcqCards.length)))}}\"",
  ) >= 0,
  "inline thinking hint should stay hidden once workflow card is visible, avoiding duplicate progress summaries",
);
assert(
  chatWxml.indexOf("workflow-card workflow-card-{{item.workflowTone ? item.workflowTone : 'compose'}}\" wx:if=\"{{showInternalStatus && item.workflowEntries.length && (item.renderableContent || item.blocks.length || (item.mcqCards && item.mcqCards.length))}}\"") >= 0,
  "workflow card should stay behind the internal-status visibility gate",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_chat_layout.js (" + pass + " assertions)");
