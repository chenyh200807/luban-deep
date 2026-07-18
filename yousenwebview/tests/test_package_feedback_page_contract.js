// test_package_feedback_page_contract.js — package feedback page should collect structured feedback evidence
// Run: node yousenwebview/tests/test_package_feedback_page_contract.js

var fs = require("fs");
var path = require("path");
var vm = require("vm");

var pagePath = path.join(__dirname, "../packageDeeptutor/pages/feedback/feedback.js");
var wxmlPath = path.join(__dirname, "../packageDeeptutor/pages/feedback/feedback.wxml");
var wxssPath = path.join(__dirname, "../packageDeeptutor/pages/feedback/feedback.wxss");
var appJsonPath = path.join(__dirname, "../app.json");
var routePath = path.join(__dirname, "../packageDeeptutor/utils/route.js");

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exit(1);
  }
}

assert(fs.existsSync(pagePath), "package feedback page js should exist");
assert(fs.existsSync(wxmlPath), "package feedback page wxml should exist");
assert(fs.existsSync(wxssPath), "package feedback page wxss should exist");

var pageSource = fs.readFileSync(pagePath, "utf8");
var wxml = fs.readFileSync(wxmlPath, "utf8");
var wxss = fs.readFileSync(wxssPath, "utf8");
var appJson = fs.readFileSync(appJsonPath, "utf8");
var routeSource = fs.readFileSync(routePath, "utf8");

assert(appJson.indexOf('"pages/feedback/feedback"') >= 0, "package app.json should register the feedback page");
assert(routeSource.indexOf("feedback:") >= 0, "route helper should expose the package feedback page");
assert(wxml.indexOf("问题定位") >= 0, "package feedback page should ask for a precise product module");
assert(wxml.indexOf("item.selected") >= 0, "package feedback page should render issue selection from explicit item state");
assert(wxml.indexOf("indexOf(") < 0, "package feedback page should not rely on WXML array method calls for selected state");
assert(wxml.indexOf("截图或录屏") >= 0, "package feedback page should expose screenshot/video attachments");
assert(wxml.indexOf("自动附带的信息") >= 0, "package feedback page should explain automatic context");
assert(wxss.indexOf(".feedback-page") >= 0, "package feedback page should define its own page shell");
assert(wxss.indexOf("glass-card") >= 0, "package feedback page should keep the shared card shell class");
assert(wxss.indexOf("var(--text-primary)") < 0, "package feedback page should not depend on external text-primary tokens");
assert(wxss.indexOf("var(--text-muted)") < 0, "package feedback page should not depend on external text-muted tokens");
// 视觉权威 = 五模块第10轮纸墨定稿：palette 单一来源是 paper-ink 的 --pk-* token，
// 页面不得再自带第二套明暗配色（旧断言锁死深色玻璃版 #f8fafc/#cbd5e1，已过时）。
assert(wxss.indexOf("paper-ink.wxss") >= 0, "package feedback page should import the paper-ink token authority");
assert(wxss.indexOf(".type-title") >= 0 && wxss.indexOf("var(--pk-t1)") >= 0, "package module titles should use the paper-ink primary text token");
assert(wxss.indexOf(".type-desc") >= 0 && wxss.indexOf("var(--pk-t2)") >= 0, "package module descriptions should use the paper-ink secondary text token");
assert(wxss.indexOf("#f8fafc") < 0 && wxss.indexOf("#cbd5e1") < 0, "package feedback page should not carry legacy dark-glass palette literals");
assert(pageSource.indexOf("submitFeedback") >= 0, "package feedback page should submit through existing api.submitFeedback authority");
assert(pageSource.indexOf("chooseMedia") >= 0, "package feedback page should use wx.chooseMedia for attachments");
assert(pageSource.indexOf("syncIssueOptions") >= 0, "package feedback page should keep issue option state in page data");

function flush() {
  return Promise.resolve()
    .then(function () {
      return Promise.resolve();
    })
    .then(function () {
      return Promise.resolve();
    });
}

function loadPage(submitFeedback, uploadFeedbackAttachment) {
  var pageDef = null;
  var toasts = [];
  var navigations = [];
  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    getCurrentPages: function () {
      return [{ route: "packageDeeptutor/pages/profile/profile" }];
    },
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          submitFeedback: submitFeedback,
          uploadFeedbackAttachment: uploadFeedbackAttachment,
        };
      }
      if (request === "../../utils/helpers") {
        return {
          vibrate: function () {},
          getWindowInfo: function () {
            return { statusBarHeight: 20 };
          },
          isDark: function () {
            return true;
          },
        };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getSystemInfoSync: function () {
        return { model: "iPhone", platform: "ios", system: "iOS 17", version: "8.0.0" };
      },
      getNetworkType: function (payload) {
        payload.success({ networkType: "wifi" });
      },
      chooseMedia: function (payload) {
        payload.success({
          tempFiles: [
            { tempFilePath: "tmp/a.png", fileType: "image", size: 1200 },
            { tempFilePath: "tmp/b.mp4", fileType: "video", size: 3400 },
          ],
        });
      },
      showToast: function (payload) {
        toasts.push(payload);
      },
      navigateBack: function () {
        navigations.push("back");
      },
    },
    Page: function (def) {
      pageDef = def;
    },
  };
  vm.runInNewContext(pageSource, sandbox, { filename: pagePath });
  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };
  Object.keys(pageDef || {}).forEach(function (key) {
    if (key !== "data") page[key] = pageDef[key];
  });
  return { page: page, toasts: toasts, navigations: navigations };
}

(async function run() {
  var calls = [];
  var uploads = [];
  var loaded = loadPage(function (payload) {
    calls.push(payload);
    return Promise.resolve({ ok: true });
  }, function (attachment) {
    uploads.push(attachment);
    return Promise.resolve({
      id: "fb-" + uploads.length,
      url: "/api/attachments/feedback-student_demo/fb-" + uploads.length + "/screen.png",
      filename: "screen.png",
      mime_type: attachment.kind === "video" ? "video/mp4" : "image/png",
    });
  });
  loaded.page.onLoad({ source: "profile" });
  loaded.page.onProblemTypeTap({ currentTarget: { dataset: { key: "learning_report" } } });
  loaded.page.onSymptomTap({ currentTarget: { dataset: { key: "data_wrong" } } });
  assert(
    loaded.page.data.issueOptions.some(function (item) {
      return item.key === "data_wrong" && item.selected === true;
    }),
    "selected issue chip should be reflected in render data",
  );
  loaded.page.onFeedbackInput({ detail: { value: "  页面显示错乱，按钮点了没反应  " } });
  loaded.page.onChooseMedia();
  await flush();
  loaded.page.onSubmitFeedback();
  await flush();

  assert(pageSource.indexOf("uploadFeedbackAttachment") >= 0, "package feedback page should upload attachments before submit");
  assert(uploads.length === 2, "selected media should be uploaded before feedback submit");
  assert(calls.length === 1, "package feedback page should submit once");
  assert(calls[0].rating === -1, "package feedback page should submit actionable negative feedback");
  assert(calls[0].feedback_source === "yousenwebview_profile_feedback", "package profile source should be preserved");
  assert(calls[0].problem_type === "learning_report", "selected module should be submitted structurally");
  assert(calls[0].symptom_tags.indexOf("data_wrong") >= 0, "selected issue should be submitted structurally");
  assert(calls[0].comment === "页面显示错乱，按钮点了没反应", "comment should be trimmed");
  assert(calls[0].attachments.length === 2, "selected media should be included as attachment metadata");
  assert(calls[0].attachments[0].url.indexOf("/api/attachments/") === 0, "package feedback should submit BI-visible attachment url");
  assert(calls[0].context_snapshot.route === "packageDeeptutor/pages/profile/profile", "context snapshot should include the current route");
  assert(loaded.toasts[0].title === "反馈已提交", "successful submit should acknowledge feedback");
  console.log("PASS test_package_feedback_page_contract.js");
})();
