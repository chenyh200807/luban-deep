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

/* 五模块定版 IA（第10轮定稿）：学习/复习/问鲁班(中央红章)/学情/我的。
 * 「历史」不再是 tab（归对话 tab 顶栏二级页，T3）。 */
function getBaseList() {
  return [
    {
      key: "learn",
      pagePath: route.lubanStations(),
      text: "学习",
      icon: "tab-learn",
      activeIcon: "tab-learn-active",
    },
    {
      key: "review",
      pagePath: route.lubanReview(),
      text: "复习",
      icon: "tab-review",
      activeIcon: "tab-review-active",
    },
    {
      key: "ask",
      pagePath: route.chat(),
      text: "问鲁班",
      seal: true,
    },
    {
      key: "report",
      pagePath: route.report(),
      text: "学情",
      icon: "tab-report",
      activeIcon: "tab-report-active",
    },
    {
      key: "mine",
      pagePath: route.profile(),
      text: "我的",
      icon: "tab-profile",
      activeIcon: "tab-profile-active",
    },
  ];
}

function normalizePath(path) {
  var raw = String(path || "").split("?")[0];
  if (!raw) return "";
  return raw.charAt(0) === "/" ? raw : "/" + raw;
}

/* 高亮权威 = 当前页面路由（壳自己判定），页面传入的序号一律不采信。
 * 非 tab 页（如历史二级页）挂壳时不高亮任何 tab（-1）。 */
function resolveSelectedByRoute(list) {
  try {
    var pages =
      typeof getCurrentPages === "function" ? getCurrentPages() : [];
    if (!pages || !pages.length) return -1;
    var current = normalizePath(pages[pages.length - 1].route);
    if (!current) return -1;
    for (var i = 0; i < list.length; i++) {
      if (normalizePath(list[i].pagePath) === current) return i;
    }
  } catch (_e) {
    /* getCurrentPages 不可用时走兜底 */
  }
  return -1;
}

Component({
  data: {
    selected: -1,
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
      /* 页面老代码仍会传旧四 tab 序号（chat=0/history=1/...），
       * 五 tab 后一律以路由判定覆盖，防错位高亮。 */
      next.selected = resolveSelectedByRoute(next.list);
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
