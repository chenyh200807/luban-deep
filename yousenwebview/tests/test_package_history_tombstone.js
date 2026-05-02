// test_package_history_tombstone.js — package tombstone helper should be the single authority for deleted history ids
// Run: node yousenwebview/tests/test_package_history_tombstone.js

var storage = {};
global.wx = {
  getStorageSync: function (key) {
    return storage[key] || "";
  },
  setStorageSync: function (key, value) {
    storage[key] = value;
  },
};

var tombstone = require("../packageDeeptutor/utils/history-tombstone");

tombstone.rememberDeletedConversationIds(["deleted_a"]);

if (!storage.history_deleted_conversation_ids.deleted_a) {
  console.error("FAIL: rememberDeletedConversationIds should write canonical object map");
  process.exit(1);
}

storage.history_deleted_conversation_ids = ["legacy_deleted"];
var migrated = tombstone.readDeletedConversationIds();

if (!migrated.legacy_deleted || Array.isArray(storage.history_deleted_conversation_ids)) {
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
