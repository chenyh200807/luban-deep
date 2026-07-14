const assert = require("assert");

var storage = {};
global.wx = {
  getStorageSync: function (key) { return storage[key]; },
  setStorageSync: function (key, value) { storage[key] = value; },
  removeStorageSync: function (key) { delete storage[key]; },
};

const ownerStorage = require("../packageDeeptutor/utils/owner-storage");

assert.strictEqual(ownerStorage.write("history_cache", "student_a", { title: "A的对话" }), true);
assert.deepStrictEqual(ownerStorage.read("history_cache", "student_a"), { title: "A的对话" });
assert.strictEqual(ownerStorage.read("history_cache", "student_b"), null);
assert.notStrictEqual(
  ownerStorage.keyFor("history_cache", "student_a"),
  ownerStorage.keyFor("history_cache", "student_b"),
);

var keyA = ownerStorage.keyFor("history_cache", "student_a");
storage[keyA] = { ownerId: "student_b", value: { title: "伪造" } };
assert.strictEqual(ownerStorage.read("history_cache", "student_a"), null);
assert.strictEqual(ownerStorage.write("chat_pending_turn_v1", "", { query: "敏感问题" }), false);

ownerStorage.write("luban_retest_seen:F16", "student_a", { ids: ["q1"] });
ownerStorage.write("luban_retest_seen:F16", "student_b", { ids: ["q2"] });
assert.deepStrictEqual(ownerStorage.read("luban_retest_seen:F16", "student_a").ids, ["q1"]);
assert.deepStrictEqual(ownerStorage.read("luban_retest_seen:F16", "student_b").ids, ["q2"]);

console.log("PASS test_owner_scoped_storage.js");
