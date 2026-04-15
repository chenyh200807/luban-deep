var route = require("../utils/route");
var runtime = require("../utils/runtime");
var flags = require("../utils/flags");

function getBaseList() {
  return [
    {
      pagePath: route.chat(),
      text: "对话",
      icon: "tab-chat",
      activeIcon: "tab-chat-active",
    },
    {
      pagePath: route.history(),
      text: "历史",
      icon: "tab-history",
      activeIcon: "tab-history-active",
    },
    {
      pagePath: route.report(),
      text: "学情",
      icon: "tab-report",
      activeIcon: "tab-report-active",
    },
    {
      pagePath: route.profile(),
      text: "我的",
      icon: "tab-profile",
      activeIcon: "tab-profile-active",
    },
  ];
}

Component({
  data: {
    selected: 0,
    hidden: false,
    isDark: true,
    list: flags.resolveShellList(getBaseList()),
  },
  lifetimes: {
    attached() {
      this.refreshState();
    },
  },
  methods: {
    refreshState(payload) {
      var next = payload && typeof payload === "object" ? Object.assign({}, payload) : {};
      next.list = flags.resolveShellList(getBaseList());
      if (!flags.shouldShowWorkspaceShell()) {
        next.hidden = true;
      }
      this.setData(next);
    },
    syncState(payload) {
      this.refreshState(payload);
    },
    switchTab(e) {
      var idx = e.currentTarget.dataset.index;
      if (idx === this.data.selected) return;
      var item = this.data.list[idx];
      if (!item || !item.pagePath) return;
      var current = this.data.list[this.data.selected];
      if (idx === 0 && current && current.pagePath) {
        runtime.setWorkspaceBack(current.pagePath, current.text);
      } else {
        runtime.clearWorkspaceBack();
      }
      wx.reLaunch({
        url: item.pagePath,
        fail: function () {
          console.warn("[TabBar] relaunch failed:", item.pagePath);
        },
      });
    },
  },
});
