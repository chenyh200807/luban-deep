// test_deeptutor_flags_sync.js — app-level deeptutor flag sync regression checks

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

function loadAppDefinition(storageSeed) {
  var source = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
  var storage = Object.assign({}, storageSeed || {});
  var appDef = null;
  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "./api/baseApi") {
        return { GetSysInfo: "Action=GetSysInfo" };
      }
      if (request === "./utils/config") {
        return { baseUrl: "https://xytk.kailly.com/Api/Xytk.ashx?" };
      }
      throw new Error("unexpected require: " + request);
    },
    wx: {
      getStorageSync: function (key) {
        return storage[key];
      },
      setStorageSync: function (key, value) {
        storage[key] = value;
      },
      removeStorageSync: function (key) {
        delete storage[key];
      },
      login: function (opts) {
        if (opts && typeof opts.success === "function") {
          opts.success();
        }
      },
      onNetworkStatusChange: function () {},
      getNetworkType: function (opts) {
        if (opts && typeof opts.success === "function") {
          opts.success({ networkType: "wifi" });
        }
      },
      request: function (opts) {
        if (opts && typeof opts.success === "function") {
          opts.success({ data: { status: 1, data: {} } });
        }
      },
      getWindowInfo: function () {
        return { statusBarHeight: 20 };
      },
    },
    App: function (def) {
      appDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, { filename: "app.js" });

  var app = {
    globalData: JSON.parse(JSON.stringify((appDef && appDef.globalData) || {})),
  };
  Object.keys(appDef || {}).forEach(function (key) {
    if (key === "globalData") return;
    app[key] = appDef[key];
  });
  if (typeof app.onLaunch === "function") {
    app.onLaunch();
  }

  return {
    app: app,
    storage: storage,
  };
}

run("app syncs deeptutor entry config and workspace flags from nested payload", function () {
  var loaded = loadAppDefinition();
  var result = loaded.app.syncDeeptutorEntryFlagFromPayload({
    data: {
      deeptutor_entry_enabled: 0,
      deeptutor_entry: {
        title: "鲁班 AI 学习舱",
        subtitle: "原生工作区入口",
        tip: "立即进入",
        badge: "NEW",
        variant: "teal",
      },
      deeptutor_workspace: {
        workspace_enabled: 1,
        history_enabled: 0,
        report_enabled: 1,
        profile_enabled: 0,
        assessment_enabled: 1,
      },
    },
  });

  assert(result === false, "entry enabled flag should be normalized to false");
  assert(loaded.app.getDeeptutorEntryEnabled() === false, "app should persist entry enabled flag");
  assert(loaded.app.getDeeptutorEntryConfig().title === "鲁班 AI 学习舱", "entry config title should sync from payload");
  assert(
    loaded.app.getDeeptutorWorkspaceFlags().historyEnabled === false,
    "workspace history flag should sync from nested payload",
  );
  assert(
    loaded.app.getDeeptutorWorkspaceFlags().profileEnabled === false,
    "workspace profile flag should sync from nested payload",
  );
});

run("app sync keeps previous entry enabled when payload only updates workspace flags", function () {
  var loaded = loadAppDefinition();
  loaded.app.setDeeptutorEntryEnabled(true);

  var result = loaded.app.syncDeeptutorEntryFlagFromPayload({
    feature_flags: {
      deeptutorWorkspaceEnabled: true,
      deeptutorHistoryEnabled: true,
      deeptutorReportEnabled: false,
      deeptutorProfileEnabled: true,
      deeptutorAssessmentEnabled: false,
    },
  });

  assert(result === true, "entry flag should stay unchanged when payload omits entry enabled");
  assert(
    loaded.app.getDeeptutorWorkspaceFlags().reportEnabled === false,
    "camelCase workspace flag payload should be normalized",
  );
  assert(
    loaded.app.getDeeptutorWorkspaceFlags().assessmentEnabled === false,
    "assessment flag should sync from camelCase payload",
  );
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_deeptutor_flags_sync.js (" + pass + " assertions)");
