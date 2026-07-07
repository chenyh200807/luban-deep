// test_billing_payment_availability.js — test build billing exposes wallet entitlements, not payment flow
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

function loadBillingPage(walletPayload, ledgerPayload, usagePayload) {
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
          getWallet: function () {
            return Promise.resolve(walletPayload || {
              balance: 8980,
              plan_id: "vip",
              entitlement: { reference_points: 9000 },
            });
          },
          getLedger: function () {
            return Promise.resolve(
              ledgerPayload || {
                entries: [
                  {
                    id: "ledger_1",
                    event_type: "debit",
                    reason: "capture",
                    delta: -20,
                    balance_after: 8980,
                    reference_type: "ai_usage",
                    created_at: "2026-06-01T10:20:00+08:00",
                  },
                ],
                has_more: false,
              },
            );
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

  assert(loaded.page.data.usagePrimaryLabel === "剩余 99.8%", "billing should hydrate wallet entitlement percent label");
  assert(
    loaded.page.data.usageRows.map(function (item) { return item.key; }).join(",") === "wallet_percent,usage_record",
    "billing should expose wallet percent and usage record rows",
  );
  assert(
    loaded.page.data.ledgerRows.length === 1 &&
      loaded.page.data.ledgerRows[0].title === "AI 学习消耗" &&
      loaded.page.data.ledgerRows[0].usageLabel === "-0.22%",
    "billing should normalize wallet ledger rows to percent-only records",
  );
  assert(!("selectedPkg" in loaded.page.data), "billing should not keep a default package while pricing is hidden");
  assert(!("selectedPkgPrice" in loaded.page.data), "billing should not keep a default price while pricing is hidden");
  assert(typeof loaded.page.onRecharge === "undefined", "billing should not expose recharge action while pricing is hidden");
  assert(typeof loaded.page.onConfirmPay === "undefined", "billing should not expose payment action while pricing is hidden");
  assert(loaded.calls.checkouts.length === 0, "billing should not create checkout orders while pricing is hidden");
  assert(loaded.calls.payments.length === 0, "billing should not invoke payment while pricing is hidden");
  assert(loaded.calls.modal.length === 0, "billing should not show unavailable payment copy while pricing is hidden");

  var degraded = loadBillingPage({
    balance: 0,
  }, { entries: [] }, {
    status: "degraded",
    display: { primary_label: "权益暂不可用", primary_percent: 100 },
    quota: { rows: [] },
  });
  await degraded.page._loadUsage();
  assert(
    degraded.page.data.usagePrimaryLabel === "权益暂不可用",
    "billing degraded terminal state should not look like active syncing",
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
