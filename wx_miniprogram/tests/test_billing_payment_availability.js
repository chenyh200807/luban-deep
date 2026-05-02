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

function loadBillingPage(walletPayload) {
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
          getWallet: function () { return Promise.resolve(walletPayload || { balance: 0 }); },
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
  var loaded = loadBillingPage({
    balance: 42,
    packages: [
      { id: "trial", label: "轻量体验", points: 100, price: "9" },
      { id: "advance", label: "进阶主力", points: 1200, price: "99" },
      { id: "sprint", label: "冲刺强化", points: 2600, price: "199" },
    ],
  });
  await loaded.page._loadWallet();

  assert(loaded.page.data.balance === 42, "billing should hydrate wallet balance");
  assert(
    loaded.page.data.packages.map(function (item) { return item.id; }).join(",") === "trial,advance,sprint",
    "billing should hydrate packages from wallet authority",
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
