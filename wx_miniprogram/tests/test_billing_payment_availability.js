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
  var calls = { modal: [], toast: [], payments: [], checkouts: [] };
  var sandbox = {
    console: console,
    getApp: function () {
      return { checkAuth: function (cb) { cb(); }, globalData: {} };
    },
    wx: {
      showModal: function (payload) { calls.modal.push(payload); },
      showToast: function (payload) { calls.toast.push(payload); },
      requestPayment: function (payload) {
        calls.payments.push(payload);
        if (payload && typeof payload.success === "function") payload.success({ ok: true });
      },
      previewImage: function () {},
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
          createBillingCheckout: function (payload) {
            calls.checkouts.push(payload);
            return Promise.resolve({
              status: "pending_payment",
              order_id: "order_1",
              channel: payload.channel,
              payment: {
                type: "wechat_mp",
                params: {
                  timeStamp: "1770000000",
                  nonceStr: "nonce",
                  package: "prepay_id=wx123",
                  signType: "RSA",
                  paySign: "sign",
                },
              },
            });
          },
          unwrapResponse: function (raw) { return raw; },
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
    loaded.page.data.usageRows.map(function (item) { return item.key; }).join(",") === "weekly",
    "billing should expose only the weekly percentage row to users",
  );
  assert(loaded.page.data.selectedPkg === "sprint", "billing should default to the recommended pass plan");

  loaded.page.onRecharge();
  assert(loaded.page.data.checkoutVisible === true, "billing should open a payment checkout sheet");
  assert(
    loaded.page.data.payChannels.map(function (item) { return item.id; }).join(",") === "wechat,alipay",
    "billing should expose both WeChat Pay and Alipay channels",
  );
  assert(loaded.calls.modal.length === 0, "billing should not show unavailable payment copy before checkout");

  await loaded.page.onConfirmPay();
  assert(loaded.calls.checkouts.length === 1, "billing should create a checkout order");
  assert(loaded.calls.checkouts[0].package_id === "sprint", "checkout should use the selected package");
  assert(loaded.calls.checkouts[0].channel === "wechat", "checkout should use selected payment channel");
  assert(loaded.calls.payments.length === 1, "billing should invoke wx.requestPayment for WeChat orders");
  assert(loaded.calls.toast.length === 1 && loaded.calls.toast[0].title === "支付完成", "successful payment should toast completion");

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }
  console.log("PASS test_billing_payment_availability.js (" + pass + " assertions)");
})().catch(function (err) {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
