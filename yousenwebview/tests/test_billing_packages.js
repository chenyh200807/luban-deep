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
    var packages = page.data.packages;

    assert(Array.isArray(packages), "billing packages should be an array");
    assert(packages.length === 2, "billing page should expose exactly two packages");
    assert(
      packages.map(function (item) { return item.price; }).join(",") === "99,199",
      "billing page should keep the 99,199 package prices",
    );
    assert(
      packages.map(function (item) { return item.points; }).join(",") === "4400,9000",
      "billing page should keep the approved weekly allowance mapping",
    );
    assert(page.data.selectedPkg === "sprint", "billing page should default to the recommended pass package");

    page.onSelectPkg({ currentTarget: { dataset: { id: "advance" } } });
    assert(page.data.selectedPkg === "advance", "billing page should update selection from tap dataset");

    page.onRecharge();
    assert(page.data.checkoutVisible === true, "billing recharge should open checkout sheet");
    await page.onConfirmPay();
    assert(loaded.checkoutCalls.length === 1, "billing should create checkout order");
    assert(loaded.paymentCalls.length === 1, "billing should invoke WeChat payment request");
    assert(loaded.modalCalls.length === 0, "billing should not show unavailable payment copy");
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
