// test_package_chat_home_actions.js — package chat hero should keep secondary actions discoverable but not noisy
// Run: node yousenwebview/tests/test_package_chat_home_actions.js

var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

var chatJs = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
  "utf8",
);
var chatWxml = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.wxml"),
  "utf8",
);
var chatWxss = fs.readFileSync(
  path.join(__dirname, "../packageDeeptutor/pages/chat/chat.wxss"),
  "utf8",
);

assert(
  chatWxml.indexOf('class="nav-usage-pill"') < 0 &&
    chatWxml.indexOf("{{usagePrimaryLabel}}") < 0,
  "navbar should not show usage percentage; usage belongs on the profile page",
);
assert(
  chatWxml.indexOf('class="nav-chat-actions" wx:if="{{hasMessages}}"') >= 0 &&
    chatWxml.indexOf('bindtap="clearMessages" aria-role="button" aria-label="新建对话"') >= 0 &&
    chatWxml.indexOf('bindtap="onChatMoreActions" aria-role="button" aria-label="更多对话操作"') >= 0,
  "package chat scene should expose a ChatGPT-like new-chat and more-actions pair",
);
assert(
  chatWxml.indexOf('<view class="nav-compose-icon"></view>') >= 0 &&
    chatWxml.indexOf("✎") < 0 &&
    chatWxss.indexOf("background-image: url(\"data:image/svg+xml") >= 0 &&
    chatWxss.indexOf("M18.375 2.625") >= 0,
  "package chat new-conversation button should use a ChatGPT-like square-pen SVG instead of a text glyph",
);
assert(
  chatWxml.indexOf('class="navbar-inner" style="padding-right:{{navRightInset}}px"') >= 0 &&
    chatJs.indexOf("wx.getMenuButtonBoundingClientRect") >= 0 &&
    chatJs.indexOf("navRightInset: navRightInset") >= 0,
  "package chat navbar actions should reserve the WeChat system capsule area",
);
assert(
  chatJs.indexOf('itemList: ["归档对话", "删除对话"]') >= 0 &&
    chatJs.indexOf('.batchConversations("archive", [convId])') >= 0 &&
    chatJs.indexOf(".deleteConversation(convId)") >= 0,
  "package chat more menu should reuse existing archive and delete conversation APIs",
);
assert(
  chatWxml.indexOf("class=\"nav-logo {{hasMessages ? 'nav-logo-chat' : ''}}\"") <
    chatWxml.indexOf("class=\"nav-back-pill\""),
  "package chat navbar should place the logo before the back-home pill",
);
assert(
  chatWxml.indexOf('class="nav-back-pill" wx:if="{{hasMessages}}"') >= 0 &&
    chatWxml.indexOf("workspaceBackLabel") < 0 &&
    chatWxml.indexOf("workspaceBackVisible || hasMessages") < 0 &&
    chatWxml.indexOf("<text class=\"nav-back-label\">返回首页</text>") >= 0,
  "package chat hero should not show a contextual workspace-back pill such as 我的",
);
assert(
  /\.nav-brand-stack\s*\{[\s\S]*flex-direction:\s*row;[\s\S]*align-items:\s*center;/.test(chatWxss),
  "package chat navbar should keep logo and back-home pill in one left-aligned row",
);
assert(
  chatWxml.indexOf("{{userPoints}}") < 0 &&
    chatWxml.indexOf("class=\"points-pill\"") < 0 &&
    chatWxml.indexOf("class=\"points-num\"") < 0 &&
    chatWxml.indexOf("class=\"billing-drawer\"") < 0,
  "package chat home should not render balances, usage percentages, or billing drawers",
);
assert(
  chatWxml.indexOf("focus-label") >= 0 &&
    chatWxml.indexOf("{{focusLabel}}：") >= 0 &&
    chatWxml.indexOf("focus-title") >= 0 &&
    chatWxml.indexOf("focus-meta") >= 0 &&
    /focusTitle:\s*""/.test(chatJs) &&
    /focusMeta:\s*""/.test(chatJs),
  "today focus should keep separate label, title, and meta nodes for stable styling",
);
assert(
  chatJs.indexOf('focusText: "今日焦点') < 0 &&
    chatJs.indexOf('update.focusText = "今日焦点') < 0,
  "today focus copy should not bake the section label into the action title",
);
assert(
  chatJs.indexOf("d.today_focus || today.focus") >= 0 &&
    chatJs.indexOf("var weakNodes = mastery.weak_nodes") < 0 &&
    chatJs.indexOf("buildFocusQuery(focus, rawFocusTitle)") >= 0 &&
    chatJs.indexOf("buildFocusDisplayTitle(focus, rawFocusTitle)") >= 0 &&
    chatJs.indexOf("buildFocusDisplayMeta(focus, rawFocusMeta)") >= 0 &&
    chatJs.indexOf("继续我的学习计划") < 0 &&
    chatJs.indexOf("给我安排5道高价值专项训练题") < 0 &&
    chatJs.indexOf("5题快速摸底") < 0 &&
    chatJs.indexOf("入门导学") < 0 &&
    chatJs.indexOf("安排下一步学习推进：") < 0 &&
    chatJs.indexOf("先判断我当前更适合知识讲解") < 0 &&
    chatJs.indexOf("建筑实务微课") >= 0 &&
    chatJs.indexOf("考试场景例子") >= 0,
  "package chat home should render backend today_focus and keep fallback focused on micro-lesson explanation",
);
assert(
  chatJs.indexOf('function buildFocusDisplayMeta(focus, meta)') >= 0 &&
    chatJs.indexOf('return "";') >= 0 &&
    chatWxss.indexOf(".focus-copy {\n  flex: 1; min-width: 0; display: flex; align-items: center; gap: 0;") >= 0 &&
    chatWxss.indexOf("font-size: 26rpx; color: rgba(251,191,36,0.92);") >= 0 &&
    chatWxss.indexOf("font-size: 26rpx; line-height: 1.2;") >= 0 &&
    chatWxss.indexOf("flex: 1; min-width: 0;") >= 0 &&
    chatWxss.indexOf("color: #fbbf24") >= 0 &&
    chatWxss.indexOf("rgba(251,191,36,0.92)") >= 0,
  "package today focus card should read as one sentence with consistent yellow typography",
);
assert(
  chatWxml.indexOf("class=\"hero-more-btn\"") >= 0 &&
    chatJs.indexOf("onHeroMoreActions") >= 0,
  "hero secondary actions should be consolidated behind a more menu",
);
assert(
  chatWxml.indexOf('class="example-scroll" wx:if="{{enableMarquee}}" scroll-x') >= 0 &&
    chatWxml.indexOf('class="example-scroll-track"') >= 0 &&
    chatWxml.indexOf('class="example-scroll-group"') >= 0 &&
    chatWxss.indexOf(".example-scroll") >= 0 &&
    chatWxss.indexOf(".example-scroll-track") >= 0 &&
    chatWxss.indexOf("@keyframes exampleMarquee") >= 0,
  "package example suggestions should keep marquee motion inside a native horizontal scroll-view",
);
assert(
  chatWxss.indexOf(".example-scroll:active .example-scroll-track") >= 0 &&
    chatWxss.indexOf("animation-play-state: paused") >= 0,
  "package example suggestions should pause marquee motion during touch so users can drag directly",
);
assert(
  chatWxml.indexOf("class=\"home-entry-btn\"") < 0 &&
    chatWxml.indexOf("class=\"row-icon-btn\" bindtap=\"onToggleTheme\"") < 0 &&
    chatWxml.indexOf("class=\"row-icon-btn\" bindtap=\"goRecharge\"") < 0 &&
    chatWxml.indexOf("class=\"avatar\" wx:if=\"{{profileEnabled}}\"") < 0,
  "hero should not expose ambiguous same-weight icon shortcuts",
);
assert(
  chatJs.indexOf("返回佑森首页") >= 0 &&
    chatJs.indexOf("充值中心") >= 0 &&
    chatJs.indexOf("个人中心") >= 0,
  "more menu should preserve the previous secondary destinations",
);
assert(
  chatWxss.indexOf(".hero-more-btn") >= 0 &&
    chatWxss.indexOf(".hero-more-dot") >= 0,
  "more menu should have an explicit touch target style",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_package_chat_home_actions.js (" + pass + " assertions)");
