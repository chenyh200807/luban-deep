// 共享五 tab 纸墨壳(单一壳权威,禁页面内联第二套 tabbar):
// 学习 / 学情 / 问鲁班(中央朱红章) / 历史 / 我的。
// 复测是学习任务状态，不再占一等模块位置；历史只承载对话列表。
var route = require("../utils/route");
var runtime = require("../utils/runtime");
var flags = require("../utils/flags");

function resolveIsDark() {
  try {
    var hostRuntime = require("../utils/host-runtime");
    // 主题单一权威:未显式选择=亮(与全包页面 isDarkOr("light") 同默认)
    return hostRuntime.getThemeOr("light") !== "light";
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
      pagePath: route.report(),
      text: "学情",
      icon: "tab-report",
    },
    {
      pagePath: route.chat(),
      text: "问鲁班",
      seal: true,
    },
    {
      pagePath: route.history(),
      text: "历史",
      // 复用现有“时间回转”图形；这是视觉 token，不再承载复习业务语义。
      icon: "tab-review",
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
        // 临时沉浸态（如历史批量编辑）没有来源 tab，清返回权威。
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
