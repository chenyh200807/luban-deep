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
        if (payload && typeof payload.success === "function") payload.success({});
      },
      previewImage: function () {},
      navigateBack: function () {},
      reLaunch: function () {},
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
          unwrapResponse: function (raw) { return raw; },
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
    assert(!("packages" in page.data), "billing page should not expose package list while pricing is hidden");
    assert(!("selectedPkg" in page.data), "billing page should not default to a package while pricing is hidden");
    assert(!("selectedPkgPrice" in page.data), "billing page should not expose a default price while pricing is hidden");
    assert(typeof page.onSelectPkg === "undefined", "billing page should not expose package selection while pricing is hidden");
    assert(typeof page.onRecharge === "undefined", "billing page should not expose recharge action while pricing is hidden");
    assert(typeof page.onConfirmPay === "undefined", "billing page should not expose payment action while pricing is hidden");
    assert(loaded.checkoutCalls.length === 0, "billing should not create checkout order while pricing is hidden");
    assert(loaded.paymentCalls.length === 0, "billing should not invoke WeChat payment while pricing is hidden");
    assert(loaded.modalCalls.length === 0, "billing should not show unavailable payment copy while pricing is hidden");
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
