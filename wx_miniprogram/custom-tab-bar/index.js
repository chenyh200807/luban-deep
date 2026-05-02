Component({
  data: {
    selected: 0,
    hidden: false,
    isDark: true,
    list: [
      {
        pagePath: "/pages/chat/chat",
        text: "对话",
        icon: "tab-chat",
        activeIcon: "tab-chat-active",
      },
      {
        pagePath: "/pages/history/history",
        text: "历史",
        icon: "tab-history",
        activeIcon: "tab-history-active",
      },
      {
        pagePath: "/pages/report/report",
        text: "学情",
        icon: "tab-report",
        activeIcon: "tab-report-active",
      },
      {
        pagePath: "/pages/profile/profile",
        text: "我的",
        icon: "tab-profile",
        activeIcon: "tab-profile-active",
      },
    ],
  },
  methods: {
    switchTab(e) {
      var idx = Number(e.currentTarget.dataset.index);
      if (idx === this.data.selected) return;
      var item = this.data.list[idx];
      if (!item || !item.pagePath) return;
      var previousSelected = this.data.selected;
      this.setData({ selected: idx });
      var self = this;
      wx.switchTab({
        url: item.pagePath,
        fail: function () {
          self.setData({ selected: previousSelected });
          console.warn("[TabBar] switchTab failed:", item.pagePath);
        },
      });
    },
  },
});
