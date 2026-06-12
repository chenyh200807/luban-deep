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
    path.join(__dirname, "../packageDeeptutor/pages/billing/billing.js"),
    "utf8",
  );
  var pageDef = null;
  var toastCalls = [];
  var modalCalls = [];
  var paymentCalls = [];
  var checkoutCalls = [];
  var sandbox = {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    Page: function (def) {
      pageDef = def;
    },
    wx: {
      showToast: function (payload) {
        toastCalls.push(payload);
      },
      showModal: function (payload) {
        modalCalls.push(payload);
      },
      requestPayment: function (payload) {
        paymentCalls.push(payload);
        if (payload && typeof payload.success === "function")
          payload.success({});
      },
      previewImage: function () {},
      navigateBack: function () {},
      reLaunch: function () {},
    },
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          getUsage: function () {
            return Promise.resolve(
              usagePayload || {
                display: { primary_label: "剩余 75%", primary_percent: 75 },
                quota: {
                  rows: [
                    {
                      key: "weekly",
                      label: "每周使用限额",
                      remaining_percent: 75,
                    },
                  ],
                },
              },
            );
          },
          getWallet: function () {
            return Promise.resolve({ balance: 0 });
          },
          getLedger: function () {
            return Promise.resolve({ entries: [], has_more: false });
          },
          createBillingCheckout: function (payload) {
            checkoutCalls.push(payload);
            return Promise.resolve({
              status: "pending_payment",
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
          unwrapResponse: function (raw) {
            return raw;
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
      if (request === "../../utils/runtime") {
        return {
          checkAuth: function (cb) {
            cb();
          },
          markGoHome: function () {},
        };
      }
      if (request === "../../utils/route") {
        return {
          chat: function () {
            return "/packageDeeptutor/pages/chat/chat";
          },
        };
      }
      throw new Error("unexpected require: " + request);
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/pages/billing/billing.js",
  });

  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}),
    setData: function (patch) {
      this.data = Object.assign({}, this.data, patch || {});
    },
  };

  Object.keys(pageDef || {}).forEach(function (key) {
    if (key === "data") return;
    page[key] = pageDef[key];
  });

  return {
    page: page,
    toastCalls: toastCalls,
    modalCalls: modalCalls,
    paymentCalls: paymentCalls,
    checkoutCalls: checkoutCalls,
  };
}

(async function main() {
  try {
    var loaded = loadBillingPage();
    var page = loaded.page;
    // 2026-06-12 契约演进（paywall）：付费墙功能上线后，billing 页面现在公开展示套餐列表、
    // 选中套餐和支付入口。旧的"pricing is hidden"断言全部更新为 pin 新行为。
    assert(
      "packages" in page.data,
      "billing page should expose package list for paywall selection",
    );
    assert(
      Array.isArray(page.data.packages),
      "billing page packages should be an array",
    );
    assert(
      !("selectedPkg" in page.data),
      "billing page uses selectedPackageId/selectedPackage, not legacy selectedPkg",
    );
    assert(
      !("selectedPkgPrice" in page.data),
      "billing page uses selectedPackage.price, not legacy selectedPkgPrice",
    );
    assert(
      typeof page.selectPackage === "function",
      "billing page should expose selectPackage for paywall UI",
    );
    assert(
      typeof page.openCheckout === "function",
      "billing page should expose openCheckout for initiating payment",
    );
    assert(
      typeof page.submitCheckout === "function",
      "billing page should expose submitCheckout for confirming payment",
    );
    // Before _loadUsage() is called, no checkout or payment should have been triggered
    assert(
      loaded.checkoutCalls.length === 0,
      "billing should not create checkout order on initial render before user action",
    );
    assert(
      loaded.paymentCalls.length === 0,
      "billing should not invoke WeChat payment on initial render before user action",
    );
    assert(
      loaded.modalCalls.length === 0,
      "billing should not show modal on initial render before user action",
    );

    var degraded = loadBillingPage({
      status: "degraded",
      display: { primary_label: "额度暂不可用", primary_percent: 100 },
      quota: { rows: [] },
    });
    await degraded.page._loadUsage();
    assert(
      degraded.page.data.usagePrimaryLabel === "额度暂不可用",
      "billing degraded terminal state should not look like active syncing",
    );
  } catch (err) {
    fail++;
    errors.push("ERROR: " + (err && err.stack ? err.stack : err));
  }

  if (fail) {
    console.error(errors.join("\n"));
    process.exit(1);
  }

  console.log("PASS test_billing_packages.js (" + pass + " assertions)");
})().catch(function (err) {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
