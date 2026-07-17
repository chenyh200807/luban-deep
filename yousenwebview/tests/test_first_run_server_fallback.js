// Run: node yousenwebview/tests/test_first_run_server_fallback.js
//
// 首跑完成态的 canonical 真值只在服务端 Learner State（投影
// /assessment/profile → diagnostic_sources.first_run.completed）。本地
// DONE_KEY 只是 UI 缓存：老用户清缓存/换设备后本地缓存丢失，首跑门会重新
// 出现。firstRunEntry.refreshFromServer 在本地无 DONE 时回读服务端完成态，
// 命中则把本地 DONE 补写回来（单一 writer 仍是服务端，本地只是 cache）。
var assert = require("assert");

// owner-storage 读写全局 wx.*StorageSync；用内存 storage 替身注入。
function installFakeStorage() {
  var store = {};
  global.wx = {
    getStorageSync: function (key) {
      return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : "";
    },
    setStorageSync: function (key, value) {
      store[key] = value;
    },
    removeStorageSync: function (key) {
      delete store[key];
    },
  };
  return store;
}

// 每个用例都拿到干净的模块（清 require 缓存，避免跨用例 storage 残留）。
function freshEntry() {
  delete require.cache[require.resolve("../packageDeeptutor/utils/first-run-entry")];
  delete require.cache[require.resolve("../packageDeeptutor/utils/owner-storage")];
  delete require.cache[require.resolve("../packageDeeptutor/utils/route")];
  return require("../packageDeeptutor/utils/first-run-entry");
}

function makeApi(behavior) {
  var calls = { getAssessmentProfile: 0, options: [] };
  return {
    calls: calls,
    module: {
      unwrapResponse: function (value) {
        return value;
      },
      getAssessmentProfile: function (opts) {
        calls.getAssessmentProfile++;
        calls.options.push(opts || null);
        return behavior();
      },
    },
  };
}

var COMPLETED_PROFILE = {
  diagnostic_sources: {
    first_run: {
      completed: true,
      script_version: "first_run_script.v1@abcdef",
      completed_at: "2026-07-01T00:00:00Z",
      source: "learner_state.learning_preferences.first_run",
    },
  },
};

var NOT_COMPLETED_PROFILE = {
  diagnostic_sources: {
    first_run: { completed: false, script_version: "", completed_at: "", source: "" },
  },
};

(async function main() {
  // 用例 1：本地空 + 服务端已完成 → hidden，且本地 DONE 被回写。
  await (function () {
    installFakeStorage();
    var entry = freshEntry();
    var api = makeApi(function () {
      return Promise.resolve(COMPLETED_PROFILE);
    });
    assert.strictEqual(entry.getState("user-1").state, "new", "baseline is new before readback");
    return entry.refreshFromServer("user-1", api.module).then(function (snapshot) {
      assert.strictEqual(snapshot.state, "hidden", "server completion resolves to hidden");
      assert.strictEqual(entry.isFirstRunDone("user-1"), true, "local DONE cache is rehydrated");
      assert.strictEqual(entry.getState("user-1").state, "hidden", "subsequent getState stays hidden");
      assert.strictEqual(api.calls.getAssessmentProfile, 1, "profile queried exactly once");
      // 读接口必须静默 + 不抢跳登录（页面拥有 returnTo 语义）。
      assert.strictEqual(api.calls.options[0] && api.calls.options[0].silent, true);
      assert.strictEqual(api.calls.options[0] && api.calls.options[0].suppressAuthRedirect, true);
    });
  })();

  // 用例 2：本地空 + 服务端未完成 → 维持 new，不回写 DONE。
  await (function () {
    installFakeStorage();
    var entry = freshEntry();
    var api = makeApi(function () {
      return Promise.resolve(NOT_COMPLETED_PROFILE);
    });
    return entry.refreshFromServer("user-1", api.module).then(function (snapshot) {
      assert.strictEqual(snapshot.state, "new", "not-completed keeps first-run gate");
      assert.strictEqual(entry.isFirstRunDone("user-1"), false, "no DONE written when not completed");
    });
  })();

  // 用例 3：接口失败 → 维持 new，不崩（fail-safe：多显示首跑门无害，首跑幂等）。
  await (function () {
    installFakeStorage();
    var entry = freshEntry();
    var api = makeApi(function () {
      return Promise.reject(new Error("network down"));
    });
    return entry.refreshFromServer("user-1", api.module).then(function (snapshot) {
      assert.strictEqual(snapshot.state, "new", "api failure keeps first-run gate, no crash");
      assert.strictEqual(entry.isFirstRunDone("user-1"), false);
    });
  })();

  // 用例 4：本地已有 DONE → 不打接口（避免每次冷启动打接口）。
  await (function () {
    installFakeStorage();
    var entry = freshEntry();
    entry.markDone("user-1", { completion_id: "c1", script_version: "first_run_script.v1@abcdef" });
    var api = makeApi(function () {
      return Promise.resolve(COMPLETED_PROFILE);
    });
    return entry.refreshFromServer("user-1", api.module).then(function (snapshot) {
      assert.strictEqual(snapshot.state, "hidden");
      assert.strictEqual(api.calls.getAssessmentProfile, 0, "local DONE short-circuits the readback");
    });
  })();

  // 用例 5：本地有 checkpoint（resume）→ 不打接口，维持 resume。
  await (function () {
    installFakeStorage();
    var entry = freshEntry();
    entry.writeCheckpoint("user-1", { qIndex: 2 });
    var api = makeApi(function () {
      return Promise.resolve(COMPLETED_PROFILE);
    });
    return entry.refreshFromServer("user-1", api.module).then(function (snapshot) {
      assert.strictEqual(snapshot.state, "resume", "resume checkpoint is not overridden");
      assert.strictEqual(api.calls.getAssessmentProfile, 0, "local checkpoint short-circuits the readback");
    });
  })();

  // 用例 6：无 userId / 无 api → 安全返回，不打接口，不崩。
  await (function () {
    installFakeStorage();
    var entry = freshEntry();
    return entry.refreshFromServer("", null).then(function (snapshot) {
      assert.ok(snapshot && typeof snapshot.state === "string", "missing deps resolve safely");
    });
  })();

  console.log("PASS test_first_run_server_fallback.js");
})().catch(function (error) {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
