// components/msg-actions/msg-actions.js — AI 消息操作栏（赞/踩/复制/重试）
var helpers = require("../../utils/helpers");
Component({
  properties: {
    msgid: { type: String, value: "" },
    feedback: { type: String, value: "" }, // "up" | "down" | ""
    role: { type: String, value: "ai" }, // "user" | "ai"
  },
  methods: {
    onThumbUp: function () {
      helpers.vibrate("light");
      this.triggerEvent("thumbup", { msgid: this.data.msgid });
    },
    onThumbDown: function () {
      helpers.vibrate("light");
      this.triggerEvent("thumbdown", { msgid: this.data.msgid });
    },
    onCopy: function () {
      helpers.vibrate("light");
      this.triggerEvent("copy", { msgid: this.data.msgid });
    },
    onRetry: function () {
      helpers.vibrate("medium");
      this.triggerEvent("retry", { msgid: this.data.msgid });
    },
    onEdit: function () {
      helpers.vibrate("light");
      this.triggerEvent("edit", { msgid: this.data.msgid });
    },
  },
});
