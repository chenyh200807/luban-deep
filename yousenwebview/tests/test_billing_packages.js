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

function loadBillingPage(usagePayload, walletPayload, ledgerPayload) {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/billing/billing.js"),
    "utf8",
  );
  var pageDef = null;
  var toastCalls = [];
  var modalCalls = [];
  var paymentCalls = [];
  var previewImageCalls = [];
  var checkoutCalls = [];
  var usageCalls = 0;
  var walletCalls = 0;
  var ledgerCalls = 0;
  var sandbox = {
    console: console,
    setTimeout: function (callback) {
      if (typeof callback === "function") callback();
      return 1;
    },
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
      previewImage: function (payload) {
        previewImageCalls.push(payload || {});
      },
      navigateBack: function () {},
      reLaunch: function () {},
    },
    require: function (request) {
      if (request === "../../utils/api") {
        return {
          getUsage: function () {
            usageCalls++;
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
            walletCalls++;
            return Promise.resolve(walletPayload || {
              balance: 8980,
              plan_id: "vip",
              entitlement: { reference_points: 9000 },
            });
          },
          getLedger: function () {
            ledgerCalls++;
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
    previewImageCalls: previewImageCalls,
    checkoutCalls: checkoutCalls,
    usageCalls: function () { return usageCalls; },
    walletCalls: function () { return walletCalls; },
    ledgerCalls: function () { return ledgerCalls; },
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
      "billing page should expose openCheckout for WeChat payment",
    );
    assert(
      !("submitCheckout" in page),
      "billing page should not expose a separate legacy checkout submission",
    );
    var billingWxml = fs.readFileSync(
      path.join(__dirname, "../packageDeeptutor/pages/billing/billing.wxml"),
      "utf8",
    );
    var billingJs = fs.readFileSync(
      path.join(__dirname, "../packageDeeptutor/pages/billing/billing.js"),
      "utf8",
    );
    var profileWxml = fs.readFileSync(
      path.join(__dirname, "../packageDeeptutor/pages/profile/profile.wxml"),
      "utf8",
    );
    var profileJs = fs.readFileSync(
      path.join(__dirname, "../packageDeeptutor/pages/profile/profile.js"),
      "utf8",
    );
    assert(
      billingWxml.indexOf("item.originalPrice") >= 0,
      "billing package cards should render original price",
    );
    assert(
      billingWxml.indexOf("sales-contact-qr.png") === -1 &&
        billingWxml.indexOf("二维码") === -1 &&
        billingWxml.indexOf("联系销售") === -1,
      "billing direct payment page should not render sales QR checkout",
    );
    assert(
      billingWxml.indexOf("item.turns") >= 0 &&
        billingWxml.indexOf("{{item.points}}") === -1 &&
        billingWxml.indexOf("selectedPackage.points") === -1,
      "billing package cards and payment dock should expose promised usage counts, not internal points",
    );
    var staleWeeklyCopy =
      billingWxml + billingJs + profileWxml + profileJs;
    assert(
      staleWeeklyCopy.indexOf("本周额度") === -1 &&
        staleWeeklyCopy.indexOf("按周更新") === -1 &&
        staleWeeklyCopy.indexOf("重置时间") === -1 &&
        staleWeeklyCopy.indexOf("每周使用限额") === -1 &&
        staleWeeklyCopy.indexOf("一次购买，固定点数") === -1,
      "billing/profile surfaces should not expose weekly quota or reset wording after fixed-point package launch",
    );
    assert(
      billingWxml.indexOf("使用记录") >= 0 &&
        billingWxml.indexOf("ledgerRows") >= 0 &&
        billingWxml.indexOf("ledger-time") >= 0 &&
        billingWxml.indexOf("ledger-usage") >= 0 &&
        billingWxml.indexOf("ledger-balance") >= 0,
      "billing should render timestamp, usage percent, and remaining percent for usage records",
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
    await page._loadUsage();
    assert(
      page.data.usagePrimaryLabel === "剩余 99.8%",
      "billing should show remaining percent instead of internal wallet points",
    );
    assert(
      page.data.ledgerRows.length === 1,
      "billing should render one wallet debit ledger row",
    );
    assert(
      page.data.ledgerRows[0].title === "AI 学习消耗",
      "billing should normalize wallet debit ledger reason",
    );
    assert(
      page.data.ledgerRows[0].usageLabel === "-0.22%",
      "billing should render wallet debit as percent-only usage",
    );
    assert(
      page.data.ledgerRows[0].balanceLabel === "剩余 99.8%",
      "billing should render remaining wallet percent after debit",
    );
    assert(
      /^[0-9]{1,2}月[0-9]{1,2}日 [0-9]{2}:[0-9]{2}$/.test(page.data.ledgerRows[0].timeLabel),
      "billing should render a stable ledger timestamp label",
    );
    assert(
      page.data.selectedPackageId === "vip",
      "billing fallback should keep VIP as the default selection for stable usage display",
    );
    assert(
      page.data.packages.length === 5,
      "billing fallback should expose the new starter/light packages plus existing launch packages",
    );
    assert(
      page.data.packages.map(function (pkg) { return pkg.id; }).join(",") === "starter_19,light_98,vip,svip,supreme_svip",
      "billing fallback package ids should match backend canonical packages",
    );
    assert(
      page.data.packages.map(function (pkg) { return pkg.name; }).join(",") === "体验包,轻量包,VIP,SVIP,至尊SVIP",
      "billing fallback package names should use public labels",
    );
    assert(
      page.data.packages.map(function (pkg) { return pkg.price; }).join(",") === "19,98,198,598,998",
      "billing fallback prices should match canonical package pricing",
    );
    page.selectPackage({ currentTarget: { dataset: { id: "starter_19" } } });
    assert(
      page.data.selectedPackageId === "starter_19",
      "billing should allow selecting the 19 yuan starter package",
    );
    await page.openCheckout();
    assert(
      !("contactSalesVisible" in page.data),
      "billing direct payment flow should not keep legacy contact sales state",
    );
    assert(
      loaded.checkoutCalls.length === 1,
      "billing open action should create one checkout order after user action",
    );
    assert(
      loaded.checkoutCalls[0].package_id === "starter_19" &&
        loaded.checkoutCalls[0].channel === "wechat",
      "billing open action should submit the selected starter package to WeChat checkout",
    );
    assert(
      loaded.paymentCalls.length === 1,
      "billing open action should invoke WeChat payment after checkout order is created",
    );
    assert(
      loaded.paymentCalls[0].package === "prepay_id=wx123" &&
        loaded.paymentCalls[0].signType === "RSA",
      "billing payment payload should be forwarded to wx.requestPayment",
    );
    assert(
      loaded.toastCalls.some(function (item) { return item && item.title === "支付成功"; }),
      "billing should show a success toast after requestPayment succeeds",
    );
    assert(
      page.data.checkoutLoading === false,
      "billing should clear checkout loading after payment returns",
    );
    assert(
      loaded.previewImageCalls.length === 0,
      "billing open action should not preview or display a QR image",
    );
    assert(
      loaded.usageCalls() === 4 && loaded.walletCalls() === 4 && loaded.ledgerCalls() === 4,
      "billing should refresh usage, wallet, and ledger repeatedly after requestPayment succeeds",
    );
    assert(
      loaded.checkoutCalls.length === 1,
      "billing direct payment flow should submit only once for one user action",
    );
    var staleWallet = loadBillingPage(null, {
      balance: 0,
      packages: [
        {
          id: "light_99",
          name: "轻量包旧价",
          price: "99",
          points: 4400,
          turns: 220,
        },
        {
          id: "sprint",
          name: "通关版",
          price: "199",
          points: 9000,
        },
      ],
    });
    await staleWallet.page._loadUsage();
    assert(
      staleWallet.page.data.packages.map(function (pkg) { return pkg.id; }).join(",") === "starter_19,light_98,vip,svip,supreme_svip",
      "billing should ignore stale backend package ids and keep canonical packages",
    );
    assert(
      staleWallet.page.data.packages.map(function (pkg) { return pkg.price; }).join(",") === "19,98,198,598,998",
      "billing should not show stale backend alias prices",
    );

    var degraded = loadBillingPage({
      status: "degraded",
      display: { primary_label: "权益暂不可用", primary_percent: 100 },
      quota: { rows: [] },
    });
    await degraded.page._loadUsage();
    assert(
      degraded.page.data.usagePrimaryLabel === "权益暂不可用",
      "billing degraded terminal state should normalize stale quota wording",
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
