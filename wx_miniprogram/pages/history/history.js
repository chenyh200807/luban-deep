// pages/history/history.js — 历史对话列表（SWR 缓存 + 日期分组 + 批量管理）

var api = require("../../utils/api");
var helpers = require("../../utils/helpers");

var CACHE_KEY = "history_cache";
var CACHE_KEY_ARCHIVED = "history_cache_archived";
var CACHE_TTL = 60 * 1000; // 60s 内直接用缓存

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    loading: true,
    refreshing: false,
    error: false,
    groups: [], // [{label, items}]
    totalCount: 0,
    userPoints: 0,
    isDark: true,

    // ── 管理模式 ──
    editMode: false,
    selectedIds: {}, // {convId: true}
    selectedCount: 0,
    allSelected: false,

    // ── 归档切换 ──
    tab: "active", // "active" | "archived"
  },

  _lastFetch: 0,

  onLoad: function () {
    var info = helpers.getWindowInfo();
    var statusBarHeight = info.statusBarHeight;
    var navContentHeight = 44;
    var navContentPaddingTop = 0;
    // 用胶囊按钮精确计算，避免与小程序右上角控制按钮重叠
    if (wx.getMenuButtonBoundingClientRect) {
      var rect = wx.getMenuButtonBoundingClientRect();
      navContentPaddingTop = rect.top - statusBarHeight;
      navContentHeight = rect.height + navContentPaddingTop * 2;
    }
    this.setData({
      statusBarHeight: statusBarHeight,
      navHeight: statusBarHeight + navContentHeight,
      navContentHeight: navContentHeight,
      navContentPaddingTop: navContentPaddingTop,
    });
  },

  onShow: function () {
    this.setData({ isDark: helpers.isDark() });
    helpers.syncTabBar(this, 1);
    var self = this;
    getApp().checkAuth(function () {
      self._loadWithCache();
    });
  },

  // ── SWR: 先展示缓存，后台刷新 ─────────────────
  _loadWithCache: function () {
    var cacheKey =
      this.data.tab === "archived" ? CACHE_KEY_ARCHIVED : CACHE_KEY;
    var cached = wx.getStorageSync(cacheKey);
    var now = Date.now();

    if (cached && cached.groups && cached.ts && now - cached.ts < CACHE_TTL) {
      this.setData({
        groups: cached.groups,
        totalCount: cached.totalCount || 0,
        loading: false,
      });
      return;
    }

    if (cached && cached.groups) {
      this.setData({
        groups: cached.groups,
        totalCount: cached.totalCount || 0,
        loading: false,
      });
      this._fetchFromServer(true);
    } else {
      this.setData({ loading: true });
      this._fetchFromServer(false);
    }
  },

  _fetchFromServer: function (silent) {
    var self = this;
    if (!silent) self.setData({ error: false });

    var isArchived = self.data.tab === "archived";

    api
      .getConversations(isArchived ? true : undefined)
      .then(function (raw) {
        // [FIX 2026-04-01] 统一 unwrap ApiResponse {code,data:{conversations}}
        var unwrapped = api.unwrapResponse(raw);
        var list = unwrapped.conversations || [];
        if (!Array.isArray(list)) list = [];
        var convs = list.map(function (c) {
          var updatedAt = c.updated_at || c.created_at || "";
          return {
            id: c.id,
            title: c.title || "新对话",
            preview: c.last_message || c.preview || "",
            time: helpers.formatTime(updatedAt),
            rawTime: updatedAt,
            ts: updatedAt ? new Date(updatedAt).getTime() : 0,
            archived: !!c.archived,
          };
        });
        convs.sort(function (a, b) {
          return b.ts - a.ts;
        });

        var groups = _groupByDate(convs);
        self.setData({
          groups: groups,
          totalCount: convs.length,
          loading: false,
          refreshing: false,
        });

        var cacheKey = isArchived ? CACHE_KEY_ARCHIVED : CACHE_KEY;
        wx.setStorageSync(cacheKey, {
          groups: groups,
          totalCount: convs.length,
          ts: Date.now(),
        });
        self._lastFetch = Date.now();
      })
      .catch(function (e) {
        if (!silent)
          self.setData({ loading: false, error: true, refreshing: false });
        else self.setData({ refreshing: false });
      });
  },

  // ── 下拉刷新 ─────────────────────────────────
  onRefresh: function () {
    helpers.vibrate("light");
    this.setData({ refreshing: true });
    this._fetchFromServer(false);
  },

  retry: function () {
    this.setData({ loading: true });
    this._fetchFromServer(false);
  },

  // ── Tab 切换（全部 / 已归档） ─────────────────
  switchTab: function (e) {
    var tab = e.currentTarget.dataset.tab;
    if (tab === this.data.tab) return;
    helpers.vibrate("light");
    this._exitEditMode();
    this.setData({ tab: tab, loading: true, groups: [], totalCount: 0 });
    this._fetchFromServer(false);
  },

  // ── 打开对话 ─────────────────────────────────
  openConversation: function (e) {
    if (this.data.editMode) {
      this._toggleSelect(e);
      return;
    }
    helpers.vibrate("light");
    var convId = e.currentTarget.dataset.id;
    getApp().globalData.pendingConversationId = convId;
    wx.switchTab({ url: "/pages/chat/chat" });
  },

  // ── 单条删除 ─────────────────────────────────
  deleteConversation: function (e) {
    if (this.data.editMode) return;
    helpers.vibrate("medium");
    var convId = e.currentTarget.dataset.id;
    var self = this;
    wx.showModal({
      title: "删除对话",
      content: "确定要删除这条对话记录吗？",
      confirmColor: "#ef4444",
      success: function (res) {
        if (res.confirm) self._doDelete(convId);
      },
    });
  },

  _doDelete: function (convId) {
    var self = this;
    api
      .deleteConversation(convId)
      .then(function () {
        self._removeFromGroups([convId]);
        wx.showToast({ title: "已删除", icon: "success" });
      })
      .catch(function () {
        wx.showToast({ title: "删除失败", icon: "none" });
      });
  },

  // ── 单条归档 ─────────────────────────────────
  archiveConversation: function (e) {
    if (this.data.editMode) return;
    helpers.vibrate("light");
    var convId = e.currentTarget.dataset.id;
    var self = this;
    wx.showModal({
      title: "归档对话",
      content: "归档后可在「已归档」中查看和恢复。",
      confirmText: "归档",
      success: function (res) {
        if (!res.confirm) return;
        wx.showLoading({ title: "归档中..." });
        api
          .batchConversations("archive", [convId])
          .then(function () {
            wx.hideLoading();
            self._removeFromGroups([convId]);
            wx.removeStorageSync(CACHE_KEY);
            wx.removeStorageSync(CACHE_KEY_ARCHIVED);
            wx.showToast({ title: "已归档", icon: "success" });
          })
          .catch(function () {
            wx.hideLoading();
            wx.showToast({ title: "归档失败", icon: "none" });
          });
      },
    });
  },

  // ── 编辑模式 ─────────────────────────────────
  enterEditMode: function () {
    helpers.vibrate("light");
    this.setData({
      editMode: true,
      selectedIds: {},
      selectedCount: 0,
      allSelected: false,
    });
  },

  exitEditMode: function () {
    helpers.vibrate("light");
    this._exitEditMode();
  },

  _exitEditMode: function () {
    this.setData({
      editMode: false,
      selectedIds: {},
      selectedCount: 0,
      allSelected: false,
    });
  },

  // ── 选择 ─────────────────────────────────────
  _toggleSelect: function (e) {
    var convId = e.currentTarget.dataset.id;
    var selected = Object.assign({}, this.data.selectedIds);
    if (selected[convId]) {
      delete selected[convId];
    } else {
      selected[convId] = true;
    }
    var count = Object.keys(selected).length;
    this.setData({
      selectedIds: selected,
      selectedCount: count,
      allSelected: count > 0 && count === this._getTotalItems(),
    });
  },

  toggleSelectAll: function () {
    helpers.vibrate("light");
    var self = this;
    if (this.data.allSelected) {
      // 取消全选
      this.setData({ selectedIds: {}, selectedCount: 0, allSelected: false });
    } else {
      // 全选
      var selected = {};
      this.data.groups.forEach(function (g) {
        g.items.forEach(function (c) {
          selected[c.id] = true;
        });
      });
      var count = Object.keys(selected).length;
      self.setData({
        selectedIds: selected,
        selectedCount: count,
        allSelected: true,
      });
    }
  },

  _getTotalItems: function () {
    var count = 0;
    this.data.groups.forEach(function (g) {
      count += g.items.length;
    });
    return count;
  },

  // ── 批量删除 ─────────────────────────────────
  batchDelete: function () {
    var ids = Object.keys(this.data.selectedIds);
    if (!ids.length) return;
    helpers.vibrate("medium");
    var self = this;
    wx.showModal({
      title: "批量删除",
      content: "确定要删除选中的 " + ids.length + " 条对话吗？删除后不可恢复。",
      confirmColor: "#ef4444",
      success: function (res) {
        if (res.confirm) self._doBatchAction("delete", ids);
      },
    });
  },

  // ── 批量归档 ─────────────────────────────────
  batchArchive: function () {
    var ids = Object.keys(this.data.selectedIds);
    if (!ids.length) return;
    helpers.vibrate("light");
    var self = this;
    self._doBatchAction("archive", ids);
  },

  // ── 批量取消归档 ─────────────────────────────
  batchUnarchive: function () {
    var ids = Object.keys(this.data.selectedIds);
    if (!ids.length) return;
    helpers.vibrate("light");
    var self = this;
    self._doBatchAction("unarchive", ids);
  },

  _doBatchAction: function (action, ids) {
    var self = this;
    wx.showLoading({ title: "处理中..." });
    api
      .batchConversations(action, ids)
      .then(function (res) {
        wx.hideLoading();
        self._removeFromGroups(ids);
        self._exitEditMode();
        // 清除两个缓存使数据刷新
        wx.removeStorageSync(CACHE_KEY);
        wx.removeStorageSync(CACHE_KEY_ARCHIVED);
        var msg =
          action === "delete"
            ? "已删除 " + ids.length + " 条"
            : action === "archive"
              ? "已归档 " + ids.length + " 条"
              : "已恢复 " + ids.length + " 条";
        wx.showToast({ title: msg, icon: "success" });
      })
      .catch(function () {
        wx.hideLoading();
        wx.showToast({ title: "操作失败", icon: "none" });
      });
  },

  // ── 从 groups 中移除指定 IDs ─────────────────
  _removeFromGroups: function (ids) {
    var idSet = {};
    ids.forEach(function (id) {
      idSet[id] = true;
    });
    var removed = 0;
    var newGroups = this.data.groups
      .map(function (g) {
        var filtered = g.items.filter(function (c) {
          if (idSet[c.id]) {
            removed++;
            return false;
          }
          return true;
        });
        return { label: g.label, items: filtered };
      })
      .filter(function (g) {
        return g.items.length > 0;
      });
    this.setData({
      groups: newGroups,
      totalCount: Math.max(0, this.data.totalCount - removed),
    });
    // 同步缓存
    var cacheKey =
      this.data.tab === "archived" ? CACHE_KEY_ARCHIVED : CACHE_KEY;
    wx.setStorageSync(cacheKey, {
      groups: newGroups,
      totalCount: this.data.totalCount,
      ts: Date.now(),
    });
  },

  goHome: function () {
    getApp().globalData.goHomeFlag = true;
    wx.switchTab({ url: "/pages/chat/chat" });
  },
});

// ── 日期分组 ──────────────────────────────────
function _groupByDate(convs) {
  var now = new Date();
  var today = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  var yesterday = today - 86400000;
  var weekAgo = today - 7 * 86400000;

  var todayItems = [];
  var yesterdayItems = [];
  var weekItems = [];
  var olderItems = [];

  convs.forEach(function (c) {
    if (c.ts >= today) todayItems.push(c);
    else if (c.ts >= yesterday) yesterdayItems.push(c);
    else if (c.ts >= weekAgo) weekItems.push(c);
    else olderItems.push(c);
  });

  var groups = [];
  if (todayItems.length) groups.push({ label: "今天", items: todayItems });
  if (yesterdayItems.length)
    groups.push({ label: "昨天", items: yesterdayItems });
  if (weekItems.length) groups.push({ label: "近 7 天", items: weekItems });
  if (olderItems.length) groups.push({ label: "更早", items: olderItems });

  return groups;
}
