// test_package_history_tombstone.js — package tombstone helper should be the single authority for deleted history ids
// Run: node yousenwebview/tests/test_package_history_tombstone.js

var storage = { auth_user_id: "student_a" };
global.wx = {
  getStorageSync: function (key) {
    return storage[key] || "";
  },
  setStorageSync: function (key, value) {
    storage[key] = value;
  },
  removeStorageSync: function (key) {
    delete storage[key];
  },
};

var tombstone = require("../packageDeeptutor/utils/history-tombstone");
var ownerStorage = require("../packageDeeptutor/utils/owner-storage");
var tombstoneKey = ownerStorage.keyFor("history_deleted_conversation_ids", "student_a");

tombstone.rememberDeletedConversationIds(["deleted_a"]);

if (!storage[tombstoneKey].value.deleted_a) {
  console.error("FAIL: rememberDeletedConversationIds should write canonical object map");
  process.exit(1);
}

storage[tombstoneKey] = { ownerId: "student_a", value: ["legacy_deleted"] };
var migrated = tombstone.readDeletedConversationIds();

if (!migrated.legacy_deleted || Array.isArray(storage[tombstoneKey].value)) {
  console.error("FAIL: readDeletedConversationIds should migrate legacy array tombstones");
  process.exit(1);
}

var visible = tombstone.filterDeletedConversations([
  { id: "legacy_deleted" },
  { id: "visible" },
]);

if (visible.length !== 1 || visible[0].id !== "visible") {
  console.error("FAIL: filterDeletedConversations should hide tombstoned conversations");
  process.exit(1);
}

console.log("PASS test_package_history_tombstone.js");
