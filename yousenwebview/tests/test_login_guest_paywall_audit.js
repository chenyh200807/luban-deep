// test_login_guest_paywall_audit.js — audit-safe login copy and guest/paywall flow
// Run: node yousenwebview/tests/test_login_guest_paywall_audit.js

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

function read(relativePath) {
  return fs.readFileSync(path.join(__dirname, "..", relativePath), "utf8");
}

var loginWxml = read("packageDeeptutor/pages/login/login.wxml");
var loginJs = read("packageDeeptutor/pages/login/login.js");
var appJson = read("app.json");
var routeJs = read("packageDeeptutor/utils/route.js");
var onboardingJs = read("packageDeeptutor/pages/onboarding/onboarding.js");
var onboardingWxml = read("packageDeeptutor/pages/onboarding/onboarding.wxml");
var onboardingWxss = read("packageDeeptutor/pages/onboarding/onboarding.wxss");
var motionScript = read("packageDeeptutor/pages/onboarding/motion-script.js");
var chatJs = read("packageDeeptutor/pages/chat/chat.js");
var chatWxml = read("packageDeeptutor/pages/chat/chat.wxml");
var billingJs = read("packageDeeptutor/pages/billing/billing.js");
var billingWxml = read("packageDeeptutor/pages/billing/billing.wxml");
var historyJs = read("packageDeeptutor/pages/history/history.js");
var historyWxml = read("packageDeeptutor/pages/history/history.wxml");
var reportJs = read("packageDeeptutor/pages/report/report.js");
var reportWxml = read("packageDeeptutor/pages/report/report.wxml");
var profileJs = read("packageDeeptutor/pages/profile/profile.js");
var profileWxml = read("packageDeeptutor/pages/profile/profile.wxml");
var wsStream = read("packageDeeptutor/utils/ws-stream.js");

[
  "微信一键登录",
  "微信授权中",
  "必须授权",
  "授权手机号才能继续",
  "登录鲁班智考账号",
].forEach(function (riskyText) {
  assert(
    loginWxml.indexOf(riskyText) === -1,
    "primary login page should not use audit-risk copy: " + riskyText,
  );
});

assert(
  loginWxml.indexOf("快速登录") >= 0,
  "primary login CTA should use concise audit-safe copy",
);
assert(
  loginWxml.indexOf('open-type="getPhoneNumber"') >= 0 &&
    loginWxml.indexOf('bindgetphonenumber="handleWechatPhoneNumber"') >= 0 &&
    loginWxml.indexOf('bindtap="handleWechatLogin"') === -1,
  "primary quick login must use mini-program phone authorization, not a plain tap",
);
assert(
  loginWxml.indexOf("handleGuestPreview") >= 0 &&
    loginWxml.indexOf("先体验导学") >= 0,
  "login page should provide a clear guest preview path",
);
// 2026-06-12 契约更新（产品决策）：登录页「先体验导学」直达游客 chat（不再二进导学动效，
// 避免 首页开始答疑→动效→登录→先体验导学→动效 的重复）；导学动效唯一入口是首页「开始答疑」(dest=login)。
assert(
  loginJs.indexOf("handleGuestPreview") >= 0 &&
    loginJs.indexOf('preview: "1"') >= 0 &&
    loginJs.indexOf("route.chat") >= 0,
  "guest preview should go straight to guest chat (no duplicate onboarding motion)",
);
assert(
  appJson.indexOf("pages/onboarding/onboarding") >= 0 &&
    appJson.indexOf('"preloadRule"') >= 0,
  "onboarding page should be registered and the subpackage preloaded from home",
);
[
  "题刷了很多，",
  "分数却不涨？",
  "案例题写了一大段，",
  "哪些话能得分？",
  "每天刷题，",
  "下一步到底练什么？",
  "上班太忙",
  "这次上岸",
  "鲁班智考 · AI 实务教练",
].forEach(function (text) {
  assert(
    onboardingJs.indexOf(text) >= 0 || onboardingWxml.indexOf(text) >= 0,
    "onboarding should include copy: " + text,
  );
});
["案例批改", "采分点", "易错点", "错因画像"].forEach(function (tag) {
  assert(
    onboardingJs.indexOf(tag) >= 0,
    "onboarding should include feature tag: " + tag,
  );
});
assert(
  onboardingWxml.indexOf("+12") >= 0 &&
    onboardingWxml.indexOf("-8") >= 0 &&
    motionScript.indexOf('"fx.scoreRoll": 12') >= 0,
  "onboarding grading demo numbers must stay self-consistent (12/20 = +12 - 8)",
);
assert(
  onboardingJs.indexOf("destLogin") >= 0 &&
    onboardingJs.indexOf("runtime.redirectToLogin") >= 0 &&
    onboardingJs.indexOf('preview: "1"') >= 0,
  "onboarding exit must route dest=login to login and guest mode to chat preview",
);
assert(
  onboardingJs.indexOf("auth.isLoggedIn()") >= 0,
  "already-authenticated users must skip the onboarding+login detour",
);
assert(
  onboardingJs.indexOf("clearTimeout(this._exitTimer)") >= 0,
  "exit timer must be cleared on unload to avoid ghost navigation",
);
assert(
  onboardingWxml.indexOf('open-type="getPhoneNumber"') === -1 &&
    onboardingWxml.indexOf("bindgetphonenumber") === -1,
  "onboarding must not request phone authorization",
);
assert(
  onboardingWxss.indexOf(".horizon") >= 0 &&
    onboardingWxss.indexOf(".dawn") >= 0 &&
    onboardingWxss.indexOf(".product-stage") >= 0 &&
    onboardingWxss.indexOf(".point-row") >= 0,
  "onboarding should keep the dawn-horizon diagnostic visual treatment",
);
assert(
  chatJs.indexOf("isGuestPreview: false") >= 0 &&
    chatJs.indexOf("self._ensureChatReady().catch") >
      chatJs.indexOf("if (hasUsableAuth)"),
  "chat page should not redirect guest preview during profile bootstrap",
);
assert(
  chatJs.indexOf("_showLoginGate") >= 0 &&
    chatJs.indexOf("runtime.setPendingChatIntent") >= 0,
  "guest send should preserve the intended query before redirecting to login",
);
assert(
  chatJs.indexOf("guestPendingIntent") >= 0 &&
    chatJs.indexOf("runtime.consumePendingChatIntent") >= 0 &&
    chatJs.indexOf("inputText: guestPendingIntent.query") >= 0,
  "onboarding examples should prefill chat input for guest users without auto-sending",
);
assert(
  chatWxml.indexOf("goQuickLogin") >= 0 && chatJs.indexOf("goQuickLogin") >= 0,
  "guest preview should expose a direct quick-login action from chat",
);
assert(
  chatWxml.indexOf("paywallVisible") >= 0 &&
    chatJs.indexOf("_isBillingBlockedMessage") >= 0,
  "billing quota errors should surface a paywall instead of a generic error",
);
assert(
  wsStream.indexOf("billing_quota_exceeded") >= 0 &&
    wsStream.indexOf("额度不足，请先开通或续费后继续使用") >= 0,
  "start-turn billing quota errors should normalize to user-facing paywall copy",
);
assert(
  billingWxml.indexOf("开通学习权益") >= 0 &&
    billingWxml.indexOf("小程序支付") >= 0,
  "billing page should expose a mini-program-native entitlement package flow",
);
assert(
  billingJs.indexOf("api.createBillingCheckout") >= 0 &&
    billingJs.indexOf('channel: "wechat"') >= 0,
  "billing checkout should use the backend checkout authority with a WeChat channel",
);
assert(
  billingJs.indexOf("payment_config_missing") >= 0 &&
    billingJs.indexOf("不会伪造支付成功") >= 0,
  "billing checkout should fail closed when payment config is missing",
);
[
  {
    name: "history",
    js: historyJs,
    wxml: historyWxml,
    marker: "登录后同步你的历史",
    wxmlMarker: "emptyState.showLogin",
  },
  {
    name: "report",
    js: reportJs,
    wxml: reportWxml,
    marker: "先看学情模块",
    wxmlMarker: "先看学情模块",
  },
  {
    name: "profile",
    js: profileJs,
    wxml: profileWxml,
    marker: "登录后同步你的权益和学习档案",
    wxmlMarker: "登录后同步你的权益和学习档案",
  },
].forEach(function (page) {
  assert(
    page.js.indexOf("runtime.checkAuth") === -1,
    page.name + " page should not force login just to browse the module",
  );
  assert(
    page.js.indexOf("isGuestPreview") >= 0 &&
      (page.js.indexOf(page.marker) >= 0 ||
        page.wxml.indexOf(page.marker) >= 0) &&
      page.wxml.indexOf(page.wxmlMarker) >= 0,
    page.name + " page should expose a guest preview state",
  );
  assert(
    page.js.indexOf("_requireLogin") >= 0 &&
      page.js.indexOf("route." + page.name) >= 0,
    page.name + " page formal actions should still route through quick login",
  );
});

// 2026-06-14 轻点/滑动加速 + 「下次不再显示导学」契约
var freeCourseJs = read("pages/freeCourse/freeCourse.js");
assert(
  onboardingJs.indexOf("skipSceneRest") >= 0 &&
    onboardingJs.indexOf("onTapAccelerate") >= 0 &&
    onboardingJs.indexOf("Math.abs(dy)") >= 0,
  "onboarding 轻点与上下滑动都应触发 skipSceneRest 加速",
);
assert(
  onboardingJs.indexOf("wx.showModal") >= 0 &&
    onboardingJs.indexOf("wx.setStorageSync") >= 0 &&
    onboardingJs.indexOf("deeptutor_onboarding_dismissed") >= 0,
  "点跳过应弹确认并可写入「不再显示」本地标记",
);
assert(
  freeCourseJs.indexOf("deeptutor_onboarding_dismissed") >= 0 &&
    freeCourseJs.indexOf("getStorageSync") >= 0 &&
    freeCourseJs.indexOf("openDeeptutorLogin") >= 0,
  "首页入口读同一标记，已 dismiss 时跳过动效直接走原登录桥接",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_login_guest_paywall_audit.js (" + pass + " assertions)");
