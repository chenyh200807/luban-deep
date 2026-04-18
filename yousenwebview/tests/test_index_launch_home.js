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
  var reLaunchCalls = [];
  var removedKeys = [];
  var pageDef = null;

  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
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
    setup.reLaunchCalls.length === 1,
    "cached launch target should still relaunch by default",
  );
  assert(
    setup.reLaunchCalls[0] && setup.reLaunchCalls[0].url === "/pages/freeCourse/freeCourse",
    "cached launch target should remain unchanged for normal app launch",
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

run("freeCourse AI entry should use guarded cross-home navigation", function () {
  var freeCourseSource = fs.readFileSync(
    path.join(__dirname, "../pages/freeCourse/freeCourse.js"),
    "utf8",
  );

  assert(
    freeCourseSource.indexOf("app.openDeeptutorLogin(") >= 0,
    "freeCourse entry should go through guarded cross-home navigation",
  );
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_index_launch_home.js (" + pass + " assertions)");
