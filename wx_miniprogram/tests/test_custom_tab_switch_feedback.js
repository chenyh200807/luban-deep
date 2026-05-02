// test_custom_tab_switch_feedback.js — custom tab should give immediate selection feedback
// Run: node wx_miniprogram/tests/test_custom_tab_switch_feedback.js

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

function loadShell(options) {
  var source = fs.readFileSync(
    path.join(__dirname, "../custom-tab-bar/index.js"),
    "utf8",
  );
  var componentDef = null;
  var switchCalls = [];
  var opts = options || {};
  var sandbox = {
    console: console,
    wx: {
      switchTab: function (call) {
        switchCalls.push(call);
        if (opts.switchFails && call && typeof call.fail === "function") {
          call.fail(new Error("mock switch failure"));
        }
      },
    },
    Component: function (def) {
      componentDef = def;
    },
  };
  vm.runInNewContext(source, sandbox, { filename: "custom-tab-bar/index.js" });
  return {
    def: componentDef,
    switchCalls: switchCalls,
  };
}

function createInstance(def) {
  var instance = {
    data: JSON.parse(JSON.stringify(def.data || {})),
    setData: function (patch) {
      Object.keys(patch || {}).forEach(function (key) {
        instance.data[key] = patch[key];
      });
    },
  };
  Object.keys(def.methods || {}).forEach(function (name) {
    instance[name] = def.methods[name];
  });
  return instance;
}

run("custom tab switch updates selected state before native switch completes", function () {
  var loaded = loadShell();
  var shell = createInstance(loaded.def);

  shell.switchTab({ currentTarget: { dataset: { index: 2 } } });

  assert(shell.data.selected === 2, "selected tab should update immediately on tap");
  assert(loaded.switchCalls.length === 1, "switchTab should still be used for root tab pages");
  assert(
    loaded.switchCalls[0].url === "/pages/report/report",
    "switchTab should target the selected root tab page",
  );
});

run("custom tab switch restores selection if native switch fails", function () {
  var loaded = loadShell({ switchFails: true });
  var shell = createInstance(loaded.def);

  shell.switchTab({ currentTarget: { dataset: { index: 2 } } });

  assert(shell.data.selected === 0, "failed switch should restore previous selected tab");
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_custom_tab_switch_feedback.js (" + pass + " assertions)");
