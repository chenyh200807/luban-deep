// pages/history/history.js — 历史对话列表（SWR 缓存 + 日期分组 + 批量管理）

var api = require("../../utils/api");
var helpers = require("../../utils/helpers");

var CACHE_KEY = "history_cache";
var CACHE_KEY_ARCHIVED = "history_cache_archived";
var CACHE_TTL = 60 * 1000; // 60s 内直接用缓存

function _clipText(value, limit) {
  var text = String(value || "").trim();
  if (!text) return "";
  return text.length > limit ? text.slice(0, limit) + "..." : text;
}

function _normalizePreview(raw) {
  return String(raw || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/gm, " ")
    .replace(/-{3,}/g, " ")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*\d+\.\s+/gm, "")
    .replace(/\|/g, " ")
    .replace(/\n+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function _deriveConversationTitle(rawTitle, preview) {
  var title = String(rawTitle || "").trim();
  var snippet = _normalizePreview(preview);
  if (title && title !== "New conversation" && title !== "新对话") {
    return title;
  }
  if (!snippet) return "新对话";
  return snippet.length > 26 ? snippet.slice(0, 26) + "..." : snippet;
}

function _capabilityLabel(capability) {
  var key = String(capability || "").trim().toLowerCase();
  if (!key || key === "chat" || key === "tutorbot") return "智能对话";
  if (key === "solve" || key === "deep_solve") return "深度解题";
  if (key === "question" || key === "deep_question") return "组题训练";
  if (key === "research" || key === "deep_research") return "深度研究";
  if (key === "guide") return "导学陪练";
  return "专题对话";
}

function _statusMeta(status) {
  var key = String(status || "").trim().toLowerCase();
  if (key === "running") {
    return { label: "进行中", tone: "blue" };
  }
  if (key === "failed") {
    return { label: "异常", tone: "rose" };
  }
  if (key === "cancelled" || key === "rejected") {
    return { label: "已中断", tone: "amber" };
  }
  return { label: "", tone: "" };
}

function _sourceMeta(source) {
  var key = String(source || "").trim().toLowerCase();
  if (key === "wx_miniprogram") {
    return { label: "小程序", tone: "sky" };
  }
  if (!key) {
    return { label: "主端", tone: "slate" };
  }
  return { label: "跨端", tone: "violet" };
}

function _joinMeta(parts) {
  return parts.filter(Boolean).join(" · ");
}

function _coerceTimestampMs(value) {
  if (value === undefined || value === null || value === "") return 0;
  if (typeof value === "number") {
    if (!isFinite(value) || value <= 0) return 0;
    return value < 100000000000 ? Math.round(value * 1000) : Math.round(value);
  }

  var raw = String(value || "").trim();
  if (!raw) return 0;
  if (/^\d+(\.\d+)?$/.test(raw)) {
    return _coerceTimestampMs(Number(raw));
  }

  var normalized = raw.replace(
    /^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2}(?:\.\d+)?)$/,
    "$1T$2",
  );
  var ts = new Date(normalized).getTime();
  return isNaN(ts) ? 0 : ts;
}

function _conversationTimestamp(c) {
  c = c || {};
  return (
    _coerceTimestampMs(c.updated_at_ms) ||
    _coerceTimestampMs(c.updated_at) ||
    _coerceTimestampMs(c.rawTime) ||
    _coerceTimestampMs(c.created_at_ms) ||
    _coerceTimestampMs(c.created_at) ||
    _coerceTimestampMs(c.ts)
  );
}

function _buildConversationItem(c) {
  var updatedAt = c.updated_at || c.created_at || "";
  var preview = _normalizePreview(c.last_message || c.preview || "");
  var status = _statusMeta(c.status);
  var source = _sourceMeta(c.source);
  var capabilityLabel = _capabilityLabel(c.capability);
  var messageCount = Number(c.message_count || 0);

  return {
    id: c.id,
    title: _deriveConversationTitle(c.title, preview),
    preview: _clipText(preview, 72),
    time: helpers.formatTime(updatedAt),
    rawTime: updatedAt,
    ts: _conversationTimestamp(c),
    archived: !!c.archived,
    statusLabel: status.label,
    statusTone: status.tone,
    sourceLabel: source.label,
    sourceTone: source.tone,
    capabilityLabel: capabilityLabel,
    messageCount: messageCount,
    metaLine: _joinMeta([messageCount > 0 ? messageCount + " 条消息" : ""]),
  };
}

function _normalizeCachedConversationItem(item) {
  var normalized = Object.assign({}, item || {});
  var preview = _normalizePreview(normalized.preview || normalized.last_message || "");
  var cachedLabel = String(normalized.capabilityLabel || "").trim();
  var cachedLabelKey = cachedLabel.toLowerCase();

  normalized.preview = _clipText(preview, 72);
  normalized.title = _deriveConversationTitle(normalized.title, preview);
  normalized.ts = _conversationTimestamp(normalized);
  if (normalized.capability) {
    normalized.capabilityLabel = _capabilityLabel(normalized.capability);
  } else if (!cachedLabel || cachedLabelKey === "tutorbot" || cachedLabelKey === "chat") {
    normalized.capabilityLabel = "智能对话";
  }
  return normalized;
}

function _normalizeCachedConversations(convs) {
  return (Array.isArray(convs) ? convs : []).map(_normalizeCachedConversationItem);
}

function _flattenGroups(groups) {
  var items = [];
  (groups || []).forEach(function (group) {
    (group.items || []).forEach(function (item) {
      items.push(item);
    });
  });
  return items;
}

function _monthLabel(ts) {
  var d = new Date(ts);
  return d.getFullYear() + "年" + (d.getMonth() + 1) + "月";
}

function _buildStats(convs) {
  var now = Date.now();
  var weekAgo = now - 7 * 86400000;
  var runningCount = 0;
  var weekCount = 0;

  (convs || []).forEach(function (item) {
    if (item.ts >= weekAgo) weekCount += 1;
    if (item.statusLabel === "进行中") runningCount += 1;
  });

  return {
    total: (convs || []).length,
    weekCount: weekCount,
    runningCount: runningCount,
  };
}

function _emptyState(tab, query) {
  if (query) {
    return {
      emoji: "搜索",
      title: "没有找到匹配对话",
      desc: "试试换个关键词，或清空搜索后查看全部会话",
      showClear: true,
      showStart: false,
    };
  }
  if (tab === "archived") {
    return {
      emoji: "归档",
      title: "暂无归档对话",
      desc: "归档的对话会保存在这里",
      showClear: false,
      showStart: false,
    };
  }
  return {
    emoji: "对话",
    title: "暂无历史对话",
    desc: "开始一次对话后，记录会自动保存在这里",
    showClear: false,
    showStart: true,
  };
}

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    navRightInset: 24,
    loading: true,
    refreshing: false,
    error: false,
    query: "",
    conversations: [],
    groups: [], // [{label, items}]
    totalCount: 0,
    stats: { total: 0, weekCount: 0, runningCount: 0 },
    emptyState: _emptyState("active", ""),
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
    var navActionRowHeight = 36;
    // 用胶囊按钮精确计算，避免与小程序右上角控制按钮重叠
    if (wx.getMenuButtonBoundingClientRect) {
      var rect = wx.getMenuButtonBoundingClientRect();
      navContentPaddingTop = rect.top - statusBarHeight;
      navContentHeight = rect.height + navContentPaddingTop * 2 + navActionRowHeight;
      var windowWidth = info.windowWidth || info.screenWidth || 375;
      var rightInset = Math.max(24, windowWidth - rect.left + 8);
    } else {
      navContentHeight += navActionRowHeight;
    }
    this.setData({
      statusBarHeight: statusBarHeight,
      navHeight: statusBarHeight + navContentHeight,
      navContentHeight: navContentHeight,
      navContentPaddingTop: navContentPaddingTop,
      navRightInset: rightInset || 24,
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
      this._applyConversationState(_normalizeCachedConversations(cached.conversations || _flattenGroups(cached.groups)), false);
      return;
    }

    if (cached && cached.groups) {
      this._applyConversationState(_normalizeCachedConversations(cached.conversations || _flattenGroups(cached.groups)), false);
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
        var convs = list.map(_buildConversationItem);
        convs.sort(function (a, b) {
          return b.ts - a.ts;
        });
        self._applyConversationState(convs, true);

        var cacheKey = isArchived ? CACHE_KEY_ARCHIVED : CACHE_KEY;
        wx.setStorageSync(cacheKey, {
          conversations: convs,
          groups: _groupByDate(convs),
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

  _applyConversationState: function (convs, fromFetch) {
    var list = Array.isArray(convs) ? convs : [];
    var groups = _groupByDate(_filterConversations(list, this.data.query));
    this.setData({
      conversations: list,
      groups: groups,
      totalCount: list.length,
      stats: _buildStats(list),
      emptyState: _emptyState(this.data.tab, this.data.query),
      loading: false,
      refreshing: false,
    });
    if (fromFetch) {
      this._lastFetch = Date.now();
    }
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

  onSearchInput: function (e) {
    var query = String((e.detail && e.detail.value) || "");
    this.setData({
      query: query,
      groups: _groupByDate(_filterConversations(this.data.conversations, query)),
      emptyState: _emptyState(this.data.tab, query),
    });
  },

  clearSearch: function () {
    this.setData({
      query: "",
      groups: _groupByDate(this.data.conversations),
      emptyState: _emptyState(this.data.tab, ""),
    });
  },

  // ── Tab 切换（全部 / 已归档） ─────────────────
  switchTab: function (e) {
    var tab = e.currentTarget.dataset.tab;
    if (tab === this.data.tab) return;
    helpers.vibrate("light");
    this._exitEditMode();
    this.setData({
      tab: tab,
      loading: true,
      groups: [],
      totalCount: 0,
      emptyState: _emptyState(tab, this.data.query),
    });
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
    var newConversations = this.data.conversations.filter(function (item) {
      return !idSet[item.id];
    });
    var newGroups = _groupByDate(
      _filterConversations(newConversations, this.data.query),
    );
    this.setData({
      conversations: newConversations,
      groups: newGroups,
      totalCount: newConversations.length,
      stats: _buildStats(newConversations),
    });
    // 同步缓存
    var cacheKey =
      this.data.tab === "archived" ? CACHE_KEY_ARCHIVED : CACHE_KEY;
    wx.setStorageSync(cacheKey, {
      conversations: newConversations,
      groups: newGroups,
      totalCount: newConversations.length,
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
  convs = Array.isArray(convs) ? convs : [];
  var now = new Date();
  var today = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  var yesterday = today - 86400000;
  var weekAgo = today - 7 * 86400000;
  var monthStart = new Date(now.getFullYear(), now.getMonth(), 1).getTime();

  var todayItems = [];
  var yesterdayItems = [];
  var weekItems = [];
  var monthItems = [];
  var olderBuckets = {};

  convs.forEach(function (c) {
    if (c.ts >= today) todayItems.push(c);
    else if (c.ts >= yesterday) yesterdayItems.push(c);
    else if (c.ts >= weekAgo) weekItems.push(c);
    else if (c.ts >= monthStart) monthItems.push(c);
    else {
      var key = _monthLabel(c.ts || 0);
      if (!olderBuckets[key]) olderBuckets[key] = [];
      olderBuckets[key].push(c);
    }
  });

  var groups = [];
  if (todayItems.length) groups.push({ label: "今天", items: todayItems });
  if (yesterdayItems.length)
    groups.push({ label: "昨天", items: yesterdayItems });
  if (weekItems.length) groups.push({ label: "近 7 天", items: weekItems });
  if (monthItems.length) groups.push({ label: "本月更早", items: monthItems });
  Object.keys(olderBuckets)
    .sort(function (a, b) {
      return olderBuckets[b][0].ts - olderBuckets[a][0].ts;
    })
    .forEach(function (label) {
      groups.push({ label: label, items: olderBuckets[label] });
    });

  return groups;
}

function _filterConversations(convs, query) {
  convs = Array.isArray(convs) ? convs : [];
  var keyword = String(query || "").trim().toLowerCase();
  if (!keyword) return convs;
  return convs.filter(function (item) {
    return [
      item.title,
      item.preview,
      item.sourceLabel,
      item.capabilityLabel,
      item.metaLine,
    ].some(function (part) {
      return String(part || "").toLowerCase().indexOf(keyword) !== -1;
    });
  });
}
