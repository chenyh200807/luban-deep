// test_billing_payment_availability.js — billing must not expose a fake payment flow
// Run: node wx_miniprogram/tests/test_billing_payment_availability.js

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

function loadBillingPage(usagePayload) {
  var source = fs.readFileSync(
    path.join(__dirname, "../pages/billing/billing.js"),
    "utf8",
  );
  var pageDef = null;
  var calls = { modal: [], toast: [] };
  var sandbox = {
    console: console,
    getApp: function () {
      return { checkAuth: function (cb) { cb(); }, globalData: {} };
    },
    wx: {
      showModal: function (payload) { calls.modal.push(payload); },
      showToast: function (payload) { calls.toast.push(payload); },
      navigateBack: function () {},
      switchTab: function () {},
    },
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          getUsage: function () {
            return Promise.resolve(usagePayload || {
              display: { primary_label: "剩余 75%", primary_percent: 75 },
              quota: {
                rows: [
                  { key: "five_hour", label: "5 小时使用限额", remaining_percent: 75 },
                  { key: "weekly", label: "每周使用限额", remaining_percent: 88 },
                ],
              },
            });
          },
          getLedger: function () { return Promise.resolve({ entries: [], has_more: false }); },
        };
      }
      if (request === "../../utils/helpers") {
        return {
          getWindowInfo: function () { return { statusBarHeight: 20 }; },
          isDark: function () { return true; },
        };
      }
      throw new Error("unexpected require: " + request);
    },
    Page: function (def) { pageDef = def; },
  };
  vm.runInNewContext(source, sandbox, { filename: "pages/billing/billing.js" });
  var page = {
    data: Object.assign({}, pageDef.data),
    setData: function (patch) { this.data = Object.assign({}, this.data, patch || {}); },
  };
  Object.keys(pageDef).forEach(function (key) {
    if (key !== "data") page[key] = pageDef[key];
  });
  return { page: page, calls: calls };
}

(async function main() {
  var loaded = loadBillingPage();
  await loaded.page._loadUsage();

  assert(loaded.page.data.usagePrimaryLabel === "剩余 75%", "billing should hydrate percent usage label");
  assert(
    loaded.page.data.usageRows.map(function (item) { return item.key; }).join(",") === "five_hour,weekly",
    "billing should hydrate quota rows from usage authority",
  );
  assert(loaded.page.data.selectedPkg === "advance", "billing should keep approved default package");

  loaded.page.onRecharge();
  assert(loaded.calls.toast.length === 0, "billing should not show fake payment toast");
  assert(
    loaded.calls.modal.length === 1 && loaded.calls.modal[0].content.indexOf("微信支付") >= 0,
    "billing should show unavailable payment reason",
  );

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_billing_payment_availability.js (" + pass + " assertions)");
})().catch(function (err) {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
