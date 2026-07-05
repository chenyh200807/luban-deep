// 共享五 tab 纸墨壳(单一壳权威,禁页面内联第二套 tabbar):
// 学习 / 复习 / 问鲁班(中央朱红章) / 学情 / 我的。
// 历史不在壳中——历史入口收权到问鲁班顶栏时钟(chat 顶栏)。
var route = require("../utils/route");
var runtime = require("../utils/runtime");
var flags = require("../utils/flags");

function resolveIsDark() {
  try {
    var hostRuntime = require("../utils/host-runtime");
    return hostRuntime.getTheme() !== "light";
  } catch (_e) {
    return true;
  }
}

function getBaseList() {
  return [
    {
      pagePath: route.learn(),
      text: "学习",
      icon: "tab-learn",
    },
    {
      pagePath: route.lubanReview(),
      text: "复习",
      icon: "tab-review",
    },
    {
      pagePath: route.chat(),
      text: "问鲁班",
      seal: true,
    },
    {
      pagePath: route.report(),
      text: "学情",
      icon: "tab-report",
    },
    {
      pagePath: route.profile(),
      text: "我的",
      icon: "tab-profile",
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
      var next =
        payload && typeof payload === "object"
          ? Object.assign({}, payload)
          : {};
      next.list = flags.resolveShellList(getBaseList());
      if (typeof next.isDark !== "boolean") {
        next.isDark = resolveIsDark();
      }
      if (!flags.shouldShowWorkspaceShell()) {
        next.hidden = true;
      }
      this.setData(next);
    },
    syncState(payload) {
      this.refreshState(payload);
    },
    switchTab(e) {
      var idx = Number(e.currentTarget.dataset.index);
      if (idx === this.data.selected) return;
      var item = this.data.list[idx];
      if (!item || !item.pagePath) return;
      var current = this.data.list[this.data.selected];
      var previousSelected = this.data.selected;
      this.setData({ selected: idx });
      if (current && current.pagePath) {
        runtime.setWorkspaceBack(current.pagePath, current.text);
      } else {
        // selected=-1(如历史页挂壳但无选中态)时无来源 tab,清返回权威
        runtime.clearWorkspaceBack();
      }
      var self = this;
      wx.redirectTo({
        url: item.pagePath,
        fail: function () {
          wx.reLaunch({
            url: item.pagePath,
            fail: function () {
              self.setData({ selected: previousSelected });
              console.warn("[TabBar] navigation failed:", item.pagePath);
            },
          });
        },
      });
    },
  },
});
