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

  return { page: page, toastCalls: toastCalls };
}

(function main() {
  try {
    var loaded = loadBillingPage();
    var page = loaded.page;
    var packages = page.data.packages;

    assert(Array.isArray(packages), "billing packages should be an array");
    assert(packages.length === 3, "billing page should expose exactly three packages");
    assert(
      packages.map(function (item) { return item.price; }).join(",") === "9,99,199",
      "billing page should keep the 9,99,199 package prices",
    );
    assert(
      packages.map(function (item) { return item.points; }).join(",") === "100,1200,2600",
      "billing page should keep the approved 100,1200,2600 point mapping",
    );
    assert(page.data.selectedPkg === "advance", "billing page should default to the 99 yuan package");

    page.onSelectPkg({ currentTarget: { dataset: { id: "sprint" } } });
    assert(page.data.selectedPkg === "sprint", "billing page should update selection from tap dataset");

    page.onRecharge();
    assert(loaded.toastCalls.length === 1, "billing recharge should show demo toast");
    assert(
      loaded.toastCalls[0] && loaded.toastCalls[0].title === "充值功能即将上线",
      "billing recharge toast title should stay stable",
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
})();
