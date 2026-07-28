// 注册/登录完成后的落点权威测试。
//
// 2026-07-28 新手单一漏斗改版：新账号（且无深链）不再中转「学习」首页等用户自己发现
// 首跑卡，而是直接 reLaunch 到 first-run 页，第一屏就是真题。
// 这条落点是本次改版的核心行为，但它此前**零测试覆盖**：register/login 的 5 个测试
// 全部把 reLaunchAfterAuth mock 掉了，只断言 target 透传。本文件补上这道网。
//
// 落点判定的单一权威 = utils/first-run-entry.js 的 reLaunchAfterAuth，
// register.js / login.js / login/manual.js 三个入口共用它，所以这里测一处即三处。

var fs = require("fs");
var path = require("path");
var vm = require("vm");

var repoRoot = path.join(__dirname, "..");
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

var FIRST_RUN_URL = "/packageDeeptutor/pages/first-run/first-run";
var LEARN_URL = "/packageDeeptutor/pages/learn/learn";

function loadEntry() {
  var source = fs.readFileSync(
    path.join(repoRoot, "packageDeeptutor/utils/first-run-entry.js"),
    "utf8",
  );
  var reLaunchCalls = [];
  var moduleObj = { exports: {} };
  var sandbox = {
    console: console,
    Date: Date,
    module: moduleObj,
    exports: moduleObj.exports,
    require: function (request) {
      if (request === "./route") {
        // 用真 route.js，不手搓 URL —— 手搓会把 ROOT 前缀写错也测不出来。
        var routeSource = fs.readFileSync(
          path.join(repoRoot, "packageDeeptutor/utils/route.js"),
          "utf8",
        );
        var routeModule = { exports: {} };
        vm.runInNewContext(
          routeSource,
          {
            console: console,
            module: routeModule,
            exports: routeModule.exports,
            require: function () {
              throw new Error("route.js should not require anything");
            },
          },
          { filename: "packageDeeptutor/utils/route.js" },
        );
        return routeModule.exports;
      }
      if (request === "./owner-storage") {
        return {
          read: function () { return null; },
          write: function () {},
          remove: function () {},
        };
      }
      if (request === "./api") return {};
      if (request === "./auth") return { getUserId: function () { return "user-1"; } };
      if (request === "./logger") return { warn: function () {} };
      throw new Error("unexpected require: " + request);
    },
    wx: {
      reLaunch: function (options) {
        reLaunchCalls.push(options && options.url);
      },
      getStorageSync: function () { return undefined; },
      setStorageSync: function () {},
      removeStorageSync: function () {},
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/utils/first-run-entry.js",
  });

  return {
    entry: moduleObj.exports,
    reLaunchCalls: reLaunchCalls,
  };
}

// ── 1. 新账号 + 无深链 → 直接进首跑（本次改版的核心行为）────────────
(function () {
  var loaded = loadEntry();
  loaded.entry.reLaunchAfterAuth(LEARN_URL, { isNewAccount: true, hasDeepLink: false });
  assert(
    loaded.reLaunchCalls.length === 1 && loaded.reLaunchCalls[0] === FIRST_RUN_URL,
    "new account without deep link must land directly on first-run, got " +
      JSON.stringify(loaded.reLaunchCalls),
  );
})();

// ── 2. 深链优先级不变 ─────────────────────────────────────
(function () {
  var loaded = loadEntry();
  var deepLink = "/packageDeeptutor/pages/luban/station/station?pack=C01";
  loaded.entry.reLaunchAfterAuth(deepLink, { isNewAccount: true, hasDeepLink: true });
  assert(
    loaded.reLaunchCalls.length === 1 && loaded.reLaunchCalls[0] === deepLink,
    "deep link must still win over the first-run landing, got " +
      JSON.stringify(loaded.reLaunchCalls),
  );
})();

// ── 3. 老用户行为完全不变 ──────────────────────────────────
(function () {
  var loaded = loadEntry();
  loaded.entry.reLaunchAfterAuth(LEARN_URL, { isNewAccount: false, hasDeepLink: false });
  assert(
    loaded.reLaunchCalls.length === 1 && loaded.reLaunchCalls[0] === LEARN_URL,
    "returning users must keep landing on the passed target, got " +
      JSON.stringify(loaded.reLaunchCalls),
  );
})();

// ── 4. 缺省 opts 不能把老用户误判成新账号 ────────────────────────
(function () {
  var loaded = loadEntry();
  loaded.entry.reLaunchAfterAuth(LEARN_URL);
  assert(
    loaded.reLaunchCalls.length === 1 && loaded.reLaunchCalls[0] === LEARN_URL,
    "missing opts must fall through to the target, not to first-run, got " +
      JSON.stringify(loaded.reLaunchCalls),
  );
})();

// ── 5. 落点页必须在 app.json 里注册，否则 reLaunch 就是白屏 ──────────
(function () {
  var appJson = JSON.parse(
    fs.readFileSync(path.join(repoRoot, "app.json"), "utf8"),
  );
  var pkg = (appJson.subPackages || appJson.subpackages || []).filter(function (p) {
    return p.root === "packageDeeptutor";
  })[0];
  var registered =
    !!pkg && (pkg.pages || []).indexOf("pages/first-run/first-run") >= 0;
  assert(registered, "pages/first-run/first-run must be registered in app.json subPackage packageDeeptutor");
})();

// ── 6. 接线（不是函数）：register.js 真的会把 hasDeepLink 算成 false ──────
// 2026-07-28 对抗审查抓到的 BLOCKER：上面 1-4 测的是 reLaunchAfterAuth 本身，
// 而 register.js 曾用 `!!this.data.returnTo` 当深链判据；returnTo 会被
// route.resolveInternalUrl 用 route.chat() 兜底填满 → 恒非空 → hasDeepLink 恒 true
// → 新账号分支永远走不到。函数一直是对的，接线一直是断的。本段跑真 register.js
// + 真 route.js，断言调用方实际传出去的 opts。
(function () {
  function probeRegister(onLoadOptions) {
    var captured = null;
    var pageDef = null;
    var routeModule = { exports: {} };
    vm.runInNewContext(
      fs.readFileSync(path.join(repoRoot, "packageDeeptutor/utils/route.js"), "utf8"),
      {
        console: console,
        module: routeModule,
        exports: routeModule.exports,
        require: function () {
          throw new Error("route.js should not require anything");
        },
      },
      { filename: "route.js" },
    );
    var sandbox = {
      console: console,
      setTimeout: setTimeout,
      clearTimeout: clearTimeout,
      require: function (request) {
        if (request === "../../utils/api") {
          return {
            request: function () {
              return Promise.resolve({});
            },
            describeRequestError: function () {
              return "";
            },
            regAttribution: function () {
              return { channel: "", scene: "" };
            },
          };
        }
        if (request === "../../utils/auth") {
          return {
            isLoggedIn: function () {
              return false;
            },
            setToken: function () {},
          };
        }
        if (request === "../../utils/helpers") {
          return {
            getWindowInfo: function () {
              return { statusBarHeight: 20, screenHeight: 812, safeArea: { bottom: 778 } };
            },
            isDarkOr: function () {
              return false;
            },
            isDark: function () {
              return false;
            },
          };
        }
        if (request === "../../utils/route") return routeModule.exports;
        if (request === "../../utils/analytics") return { track: function () {} };
        if (request === "../../utils/first-run-entry") {
          return {
            reLaunchAfterAuth: function (target, opts) {
              captured = { target: target, opts: opts || {} };
            },
          };
        }
        throw new Error("unexpected require: " + request);
      },
      wx: { reLaunch: function () {}, navigateBack: function () {}, showToast: function () {} },
      Page: function (def) {
        pageDef = def;
      },
    };
    vm.runInNewContext(
      fs.readFileSync(path.join(repoRoot, "packageDeeptutor/pages/register/register.js"), "utf8"),
      sandbox,
      { filename: "register.js" },
    );
    var page = {
      data: Object.assign({}, pageDef.data),
      setData: function (next) {
        this.data = Object.assign({}, this.data, next || {});
      },
    };
    Object.keys(pageDef).forEach(function (key) {
      if (key !== "data") page[key] = pageDef[key];
    });
    page.onLoad(onLoadOptions);
    page._reLaunchAfterAuth(true); // 模拟「注册成功 = 新账号」
    return captured;
  }

  var cold = probeRegister({});
  assert(
    cold && cold.opts.isNewAccount === true && cold.opts.hasDeepLink === false,
    "cold register (no params) must report hasDeepLink=false so new accounts reach first-run, got " +
      JSON.stringify(cold && cold.opts),
  );

  var fromLogin = probeRegister({ returnTo: "/packageDeeptutor/pages/chat/chat" });
  assert(
    fromLogin && fromLogin.opts.hasDeepLink === false,
    "a returnTo that merely equals the chat fallback is not a deep link, got " +
      JSON.stringify(fromLogin && fromLogin.opts),
  );

  var deep = probeRegister({ returnTo: "pages/learn/learn" });
  assert(
    deep && deep.opts.hasDeepLink === true && deep.target === LEARN_URL,
    "a real deep link must still be reported as one, got " + JSON.stringify(deep),
  );
})();

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("PASS test_first_run_entry_landing.js (" + pass + " assertions)");
