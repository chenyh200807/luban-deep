// Run: node yousenwebview/tests/test_pass_readiness_login_lane.js
// 过线体检落地页 §5.1 登录 UI 合同(验收级):
// 1. 入口唯一按钮 = open-type=getPhoneNumber(未登录且已勾隐私分支);
// 2. 拒绝路径: 同一 handler 内直接走 login-basic 继续进测评——
//    零二次弹窗、零挽留文案、零 toast, tap 数与授权路径相同(各一次手势→各一次导航);
// 3. 授权路径: 同 handler 走既有 /wechat/mp/login(phone_code);
// 4. 隐私协议中断 ≠ 拒绝: 不静默登录、不导航;
// 5. 登录失败(API 错误): 内联可重试, 埋点 objectType=login_failed 与拒绝可区分。
var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");

var pageDir = path.join(
  __dirname,
  "../packageDeeptutor/pages/luban/pass-readiness/landing",
);
var source = fs.readFileSync(path.join(pageDir, "landing.js"), "utf8");
var wxml = fs.readFileSync(path.join(pageDir, "landing.wxml"), "utf8");

// ── 1. 唯一 getPhoneNumber 按钮 + 六要素绑定 ────────────────
var phoneButtons = wxml.match(/open-type="getPhoneNumber"/g) || [];
assert.strictEqual(phoneButtons.length, 1, "入口必须恰好一个 getPhoneNumber 按钮");
assert.ok(wxml.indexOf('bindgetphonenumber="handlePhoneNumber"') >= 0);
["copy.productName", "copy.h1", "copy.subtitle", "copy.antiQuizLine", "copy.sampleReportCaption", "copy.ctaLogin", "copy.phoneAuthReason"].forEach(
  function (binding) {
    assert.ok(wxml.indexOf(binding) >= 0, "落地页六要素缺绑定: " + binding);
  },
);
// 拒绝路径零挽留: 页面不含任何二次说服/挽留词
["再想想", "确定放弃", "错过", "仅需一步"].forEach(function (word) {
  assert.strictEqual(wxml.indexOf(word), -1, "落地页含挽留文案: " + word);
});

function flushPromises() {
  return new Promise(function (resolve) {
    setTimeout(resolve, 0);
  });
}

function loadPage(overrides) {
  var calls = {
    loginBasic: [],
    loginWithPhone: [],
    navigateTo: [],
    showToast: [],
    showModal: [],
    tokens: [],
    behaviors: [],
  };
  var apiMock = Object.assign(
    {
      wxLoginBasic: function (code) {
        calls.loginBasic.push(code);
        return Promise.resolve({ token: "tok-basic", expires_at: 0, user_id: "u1", openid: "o1" });
      },
      wxLoginWithPhone: function (code, phoneCode) {
        calls.loginWithPhone.push({ code: code, phoneCode: phoneCode });
        return Promise.resolve({ token: "tok-phone", expires_at: 0, user_id: "u1", openid: "o1" });
      },
      getAssessmentProfile: function () {
        return Promise.resolve({ diagnostic_sources: {} });
      },
      describeRequestError: function (err, fallback) {
        return fallback;
      },
    },
    (overrides && overrides.api) || {},
  );
  var pageDef = null;
  var sandbox = {
    console: console,
    Promise: Promise,
    setTimeout: setTimeout,
    Date: Date,
    require: function (request) {
      if (request === "../../../../utils/api") return apiMock;
      if (request === "../../../../utils/auth") {
        return {
          isLoggedIn: function () {
            return !!(overrides && overrides.loggedIn);
          },
          setToken: function (token) {
            calls.tokens.push(token);
          },
        };
      }
      if (request === "../../../../utils/helpers") {
        return {
          getWindowInfo: function () {
            return { statusBarHeight: 20, screenHeight: 800, safeArea: { bottom: 780 } };
          },
          isDarkOr: function () {
            return false;
          },
        };
      }
      if (request === "../../../../utils/route") {
        return {
          lubanPassReadinessExam: function () {
            return "/packageDeeptutor/pages/luban/pass-readiness/exam/exam";
          },
          lubanPassReadinessReport: function () {
            return "/packageDeeptutor/pages/luban/pass-readiness/report/report";
          },
          terms: function () {
            return "/packageDeeptutor/pages/legal/terms";
          },
          chat: function () {
            return "/packageDeeptutor/pages/chat/chat";
          },
        };
      }
      if (request === "../../../../utils/surface-telemetry") {
        return {
          trackProductBehavior: function (name, payload) {
            calls.behaviors.push({ name: name, payload: payload || {} });
          },
          trackModuleView: function () {},
          trackModuleExit: function () {},
        };
      }
      if (request === "../../../../utils/pass-readiness-view-model") {
        return require(path.join(__dirname, "../packageDeeptutor/utils/pass-readiness-view-model"));
      }
      if (request === "../../../../utils/pass-readiness-report-view-model") {
        return require(path.join(__dirname, "../packageDeeptutor/utils/pass-readiness-report-view-model"));
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      login: function (opts) {
        if (overrides && overrides.wxLoginFails) {
          opts.fail && opts.fail();
          return;
        }
        opts.success({ code: "wx-code-1" });
      },
      getPrivacySetting: function (opts) {
        opts.success && opts.success({ needAuthorization: false });
      },
      navigateTo: function (opts) {
        calls.navigateTo.push(opts.url);
      },
      reLaunch: function () {},
      navigateBack: function () {},
      showToast: function (opts) {
        calls.showToast.push(opts);
      },
      showModal: function (opts) {
        calls.showModal.push(opts);
      },
    },
    Page: function (def) {
      pageDef = def;
    },
  };
  vm.runInNewContext(source, sandbox, { filename: "landing.js" });
  var page = {
    data: Object.assign({}, pageDef.data),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };
  Object.keys(pageDef).forEach(function (key) {
    if (key !== "data") page[key] = pageDef[key];
  });
  return { page: page, calls: calls };
}

(async function main() {
  // ── 2. 拒绝路径: 同 handler → login-basic, 零弹窗零 toast, 一次手势一次导航 ──
  var declined = loadPage();
  declined.page.onLoad({});
  declined.page.handlePhoneNumber({ detail: { errMsg: "getPhoneNumber:fail user deny" } });
  await flushPromises();
  assert.deepStrictEqual(declined.calls.loginBasic, ["wx-code-1"], "拒绝必须走 login-basic {code}");
  assert.strictEqual(declined.calls.loginWithPhone.length, 0);
  assert.strictEqual(declined.calls.showModal.length, 0, "拒绝路径零二次弹窗");
  assert.strictEqual(declined.calls.showToast.length, 0, "拒绝路径零 toast");
  assert.strictEqual(declined.calls.navigateTo.length, 1, "拒绝后直接进测评");
  assert.ok(declined.calls.navigateTo[0].indexOf("pass-readiness/exam") >= 0);
  assert.strictEqual(declined.calls.tokens[0], "tok-basic");
  assert.strictEqual(declined.page.data.errorMsg, "", "拒绝路径零挽留文案");

  // ── 3. 授权路径: 同 handler → phone 车道, 同样一次手势一次导航(tap 平权) ──
  var granted = loadPage();
  granted.page.onLoad({});
  granted.page.handlePhoneNumber({ detail: { code: "phone-code-9" } });
  await flushPromises();
  assert.strictEqual(granted.calls.loginWithPhone.length, 1);
  assert.deepStrictEqual(granted.calls.loginWithPhone[0], { code: "wx-code-1", phoneCode: "phone-code-9" });
  assert.strictEqual(granted.calls.loginBasic.length, 0);
  assert.strictEqual(granted.calls.showModal.length, 0);
  assert.strictEqual(granted.calls.navigateTo.length, 1, "授权后同样直接进测评");
  assert.strictEqual(
    granted.calls.navigateTo[0],
    declined.calls.navigateTo[0],
    "拒绝与授权落点一致, tap 数相同",
  );

  // 专名埋点(catalog 已登记) + identity_state 验证维度
  function loginCompleted(calls) {
    return calls.behaviors.find(function (item) {
      return item.name === "pass_readiness_login_completed";
    });
  }
  assert.strictEqual(
    loginCompleted(declined.calls).payload.identityState,
    "openid_only",
    "拒绝车道 identity_state=openid_only",
  );
  assert.strictEqual(
    loginCompleted(granted.calls).payload.identityState,
    "phone_granted",
    "授权车道 identity_state=phone_granted",
  );
  [declined, granted].forEach(function (flow) {
    assert.ok(
      flow.calls.behaviors.some(function (item) {
        return item.name === "pass_readiness_landing_view";
      }),
      "落地曝光走专名事件",
    );
    assert.ok(
      flow.calls.behaviors.some(function (item) {
        return item.name === "pass_readiness_login_prompt_viewed";
      }),
      "登录提示曝光走专名事件",
    );
  });

  // ── 4. 隐私中断: 不登录不导航 ──
  var privacy = loadPage();
  privacy.page.onLoad({});
  privacy.page.handlePhoneNumber({
    detail: { errMsg: "getPhoneNumber:fail privacy permission is not authorized" },
  });
  await flushPromises();
  assert.strictEqual(privacy.calls.loginBasic.length, 0, "隐私中断禁静默登录");
  assert.strictEqual(privacy.calls.navigateTo.length, 0);
  assert.ok(privacy.page.data.errorMsg.indexOf("隐私") >= 0);

  // ── 5. 登录失败(API 错误): 内联重试 + login_failed 埋点 ──
  var failed = loadPage({
    api: {
      wxLoginBasic: function () {
        return Promise.reject(new Error("ECONNRESET"));
      },
    },
  });
  failed.page.onLoad({});
  failed.page.handlePhoneNumber({ detail: { errMsg: "getPhoneNumber:fail user deny" } });
  await flushPromises();
  assert.strictEqual(failed.calls.navigateTo.length, 0);
  assert.ok(failed.page.data.errorMsg.length > 0, "登录失败必须给内联重试提示");
  var failEvent = failed.calls.behaviors.find(function (item) {
    return (
      item.name === "pass_readiness_login_completed" &&
      item.payload.result === "login_failed"
    );
  });
  assert.ok(failEvent, "失败埋点 result=login_failed, 与拒绝(openid_only 成功)可区分");

  // ── 6. 已登录: 单按钮直接进测评, 不再曝光登录提示 ──
  var logged = loadPage({ loggedIn: true });
  logged.page.onLoad({});
  logged.page.onStartTap();
  await flushPromises();
  assert.strictEqual(logged.calls.navigateTo.length, 1);
  assert.strictEqual(logged.calls.loginBasic.length, 0);
  assert.ok(
    !logged.calls.behaviors.some(function (item) {
      return item.name === "pass_readiness_login_prompt_viewed";
    }),
    "已登录不发 login_prompt_viewed",
  );

  console.log("PASS test_pass_readiness_login_lane.js");
})().catch(function (err) {
  console.error(err);
  process.exit(1);
});
