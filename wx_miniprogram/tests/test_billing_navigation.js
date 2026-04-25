// test_billing_navigation.js — billing back button should recover when opened directly
// Run: node wx_miniprogram/tests/test_billing_navigation.js

var fs = require("fs");
var path = require("path");
var vm = require("vm");

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

function loadBillingPage() {
  var source = fs.readFileSync(
    path.join(__dirname, "../pages/billing/billing.js"),
    "utf8",
  );
  var pageDef = null;
  var calls = {
    navigateBack: [],
    switchTab: [],
  };
  var sandbox = {
    console: console,
    getApp: function () {
      return {
        globalData: {},
        checkAuth: function (cb) {
          cb();
        },
      };
    },
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          getWallet: function () {
            return Promise.resolve({ balance: 0 });
          },
          getLedger: function () {
            return Promise.resolve({ entries: [], has_more: false });
          },
        };
      }
      if (request === "../../utils/helpers") {
        return {
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
      navigateBack: function (payload) {
        calls.navigateBack.push(payload || {});
        if (payload && typeof payload.fail === "function") {
          payload.fail(new Error("no previous page"));
        }
      },
      switchTab: function (payload) {
        calls.switchTab.push(payload || {});
      },
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "wx_miniprogram/pages/billing/billing.js",
  });

  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };
  Object.keys(pageDef || {}).forEach(function (key) {
    if (key === "data") return;
    page[key] = pageDef[key];
  });
  return { page: page, calls: calls };
}

var loaded = loadBillingPage();
loaded.page.goBack();

assert(loaded.calls.navigateBack.length === 1, "billing goBack should try native back first");
assert(
  loaded.calls.switchTab.length === 1 &&
    loaded.calls.switchTab[0].url === "/pages/chat/chat",
  "billing goBack should fall back to chat tab when there is no previous page",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_billing_navigation.js (" + pass + " assertions)");
