// test_freeCourse_legacy_cleanup.js — regression checks for freeCourse legacy state cleanup

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

function loadFreeCoursePage(storageSeed) {
  var source = fs.readFileSync(
    path.join(__dirname, "../pages/freeCourse/freeCourse.js"),
    "utf8",
  );
  var storage = Object.assign({}, storageSeed || {});
  var setDataCalls = [];
  var pageDef = null;
  var defaultEntryConfig = {
    title: "鲁班AI智考",
    subtitle: "智能答疑入口",
    tip: "点击进入",
    badge: "AI",
    variant: "blue",
  };

  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    getApp: function () {
      return {
        globalData: {
          deeptutorEntryEnabled: true,
        },
        getDeeptutorEntryEnabled: function () {
          return true;
        },
        getDeeptutorEntryConfig: function () {
          return defaultEntryConfig;
        },
        syncDeeptutorEntryFlagFromPayload: function () {},
      };
    },
    require: function (request) {
      if (request === "../../utils/analytics") {
        return { track: function () {} };
      }
      if (request === "../../api/baseApi") {
        return {
          GetGratisCourse: "Action=GetGratisCourse",
        };
      }
      if (request === "../../utils/config") {
        return {
          baseUrl3: "https://www.yousenjiaoyu.com/",
        };
      }
      if (request === "../../utils/function") {
        return { linkTo: function () {} };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      createAnimation: function () {
        var actions = [];
        return {
          rotate: function (value) {
            actions.push(["rotate", value]);
            return this;
          },
          step: function () {
            actions.push(["step"]);
            return this;
          },
          export: function () {
            return actions.slice();
          },
        };
      },
      getStorageSync: function (key) {
        return storage[key];
      },
      setStorageSync: function (key, value) {
        storage[key] = value;
      },
      showLoading: function () {},
      hideLoading: function () {},
      request: function () {
        return Promise.resolve({ data: { status: 1, data: [] } });
      },
      stopPullDownRefresh: function () {},
      showToast: function () {},
      navigateTo: function () {},
      reLaunch: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "pages/freeCourse/freeCourse.js",
  });

  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}),
    setData: function (next) {
      setDataCalls.push(Object.assign({}, next || {}));
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
    setDataCalls: setDataCalls,
  };
}

run("onLoad should hydrate major_id through setData and keep it stable for share links", function () {
  var setup = loadFreeCoursePage({
    major_id: 18,
    major_title: "旧存储标题",
    members: { pk_id: 77 },
  });

  setup.page.onLoad({});

  assert(setup.page.data.major_id === 18, "stored major_id should win over the default");
  assert(
    setup.setDataCalls.some(function (call) {
      return call && call.major_id === 18;
    }),
    "onLoad should publish major_id through setData",
  );

  setup.storage.major_id = 99;
  setup.storage.major_title = "被篡改的旧标题";
  var share = setup.page.onShareAppMessage();

  assert(
    share.path.indexOf("major_id=18") >= 0,
    "share path should use hydrated major_id instead of live storage",
  );
  assert(
    share.path.indexOf("top_id=77") >= 0,
    "share path should keep member pk_id when present",
  );
  assert(
    share.path.indexOf("major_title=一级建造师") >= 0,
    "share path should prefer hydrated page-state major title over live storage",
  );
});

run("onLoad should default major_id to 10 and expose it through setData when storage is empty", function () {
  var setup = loadFreeCoursePage({});

  setup.page.onLoad({});

  assert(setup.page.data.major_id === 10, "major_id should fall back to 10");
  assert(
    setup.setDataCalls.some(function (call) {
      return call && call.major_id === 10;
    }),
    "onLoad should set the default major_id through setData",
  );
});

run("onShareAppMessage should not crash when members are missing", function () {
  var setup = loadFreeCoursePage({
    major_id: 18,
    major_title: "一级建造师",
  });

  setup.page.onLoad({});

  var share = setup.page.onShareAppMessage();

  assert(
    share.path.indexOf("top_id=0") >= 0,
    "share path should fall back to top_id=0 when members are absent",
  );
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_freeCourse_legacy_cleanup.js (" + pass + " assertions)");
