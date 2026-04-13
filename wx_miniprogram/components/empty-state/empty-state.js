// components/empty-state/empty-state.js — 通用空状态卡片
Component({
  properties: {
    emoji: { type: String, value: "" },
    title: { type: String, value: "暂无内容" },
    desc: { type: String, value: "" },
    btnText: { type: String, value: "" },
    isDark: { type: Boolean, value: true },
  },
  methods: {
    onBtnTap: function () {
      this.triggerEvent("action");
    },
  },
});
