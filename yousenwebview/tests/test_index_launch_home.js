// test_index_launch_home.js — regression checks for explicit host-home navigation
// Run: /Applications/Codex.app/Contents/Resources/node yousenwebview/tests/test_index_launch_home.js

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

function run(name, fn) {
  try {
    fn();
  } catch (err) {
    fail++;
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
  }
}

function loadIndexPage(storageSeed) {
  var source = fs.readFileSync(
    path.join(__dirname, "../pages/index/index.js"),
    "utf8",
  );
  var storage = Object.assign({}, storageSeed || {});
  var requestCalls = [];
  var redirectToCalls = [];
  var reLaunchCalls = [];
  var removedKeys = [];
  var pageDef = null;

  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: function (task) {
      if (typeof task === "function") task();
      return 1;
    },
    clearTimeout: clearTimeout,
    wx: {
      getStorageSync: function (key) {
        return storage[key];
      },
      setStorageSync: function (key, value) {
        storage[key] = value;
      },
      removeStorageSync: function (key) {
        removedKeys.push(key);
        delete storage[key];
      },
      request: function (options) {
        requestCalls.push(options);
      },
      redirectTo: function (options) {
        redirectToCalls.push(options);
      },
      nextTick: function (task) {
        task();
      },
      reLaunch: function (options) {
        reLaunchCalls.push(options);
      },
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "pages/index/index.js",
  });

  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };

  Object.keys(pageDef || {}).forEach(function (key) {
    if (key === "data") return;
    page[key] = pageDef[key];
  });

  return {
    page: page,
    storage: storage,
    requestCalls: requestCalls,
    redirectToCalls: redirectToCalls,
    reLaunchCalls: reLaunchCalls,
    removedKeys: removedKeys,
  };
}

run("cached launch redirect still works without explicit home intent", function () {
  var setup = loadIndexPage({
    yousen_launch_cache: {
      payload: { route: "/pages/freeCourse/freeCourse" },
      target: "/pages/freeCourse/freeCourse",
      updatedAt: Date.now(),
    },
  });

  setup.page.onLoad({});

  assert(
    setup.redirectToCalls.length === 1,
    "cached launch target should still replace the launch guard by default",
  );
  assert(
    setup.redirectToCalls[0] && setup.redirectToCalls[0].url === "/pages/freeCourse/freeCourse",
    "cached launch target should remain unchanged for normal app launch",
  );
});

run("cold launch should go directly to freeCourse without legacy gettopzm request", function () {
  var setup = loadIndexPage();

  setup.page.onLoad({});

  assert(
    setup.requestCalls.length === 0,
    "cold launch should no longer depend on legacy gettopzm",
  );
  assert(
    setup.redirectToCalls.length === 1,
    "cold launch should replace the launch guard directly with freeCourse",
  );
  assert(
    setup.redirectToCalls[0] && setup.redirectToCalls[0].url === "/pages/freeCourse/freeCourse",
    "cold launch should target freeCourse as the single host home",
  );
});

run("chat home button should target index with explicit forceHome flag", function () {
  var appSource = fs.readFileSync(
    path.join(__dirname, "../app.js"),
    "utf8",
  );

  assert(
    appSource.indexOf('const HOST_HOME_URL = "/pages/freeCourse/freeCourse";') >= 0,
    "host-home navigation should point directly at freeCourse",
  );
});

run("devtools normal compile should launch from the host home authority", function () {
  var appConfig = JSON.parse(
    fs.readFileSync(path.join(__dirname, "../app.json"), "utf8"),
  );

  assert(
    appConfig.pages && appConfig.pages[0] === "pages/freeCourse/freeCourse",
    "app.json first page should start from the host home instead of a launch wrapper",
  );
  assert(
    appConfig.lazyCodeLoading === "requiredComponents",
    "app.json should enable required-components lazy code loading so DevTools code quality passes",
  );

  [
    "../project.config.json",
    "../project.private.config.json",
  ].forEach(function (configPath) {
    var config = JSON.parse(
      fs.readFileSync(path.join(__dirname, configPath), "utf8"),
    );
    var miniProgram = config.condition && config.condition.miniprogram;
    var current = miniProgram && miniProgram.list && miniProgram.list[miniProgram.current];

    assert(
      config.setting && config.setting.condition === true,
      configPath + " should enable DevTools compile conditions",
    );
    assert(
      current && current.pathName === "pages/freeCourse/freeCourse",
      configPath + " should launch the host home directly for normal compile",
    );
    assert(
      current && current.query === "",
      configPath + " should not need launch-wrapper query flags",
    );
  });
});

run("freeCourse AI entry should use guarded cross-home navigation", function () {
  var freeCourseSource = fs.readFileSync(
    path.join(__dirname, "../pages/freeCourse/freeCourse.js"),
    "utf8",
  );

  // 2026-06-13 稳定性修订：入口仍先播导学动效，但宿主页必须先显式
  // loadSubpackage；DevTools/真机在冷缓存下直接 navigateTo 分包页会偶发 fail。
  assert(
    freeCourseSource.indexOf("_deeptutorNavLockUntil") >= 0 &&
      freeCourseSource.indexOf("wx.loadSubpackage") >= 0 &&
      freeCourseSource.indexOf("name: 'packageDeeptutor'") >= 0 &&
      freeCourseSource.indexOf("pages/onboarding/onboarding") >= 0,
    "freeCourse entry should preload packageDeeptutor before guarded onboarding navigation",
  );
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_index_launch_home.js (" + pass + " assertions)");
