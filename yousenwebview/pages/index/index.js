// pages/index1/index1.js
const LAUNCH_CACHE_KEY = "yousen_launch_cache";
const LAUNCH_CACHE_TTL = 12 * 60 * 60 * 1000;
const WEB_VIEW_FALLBACK = "__WEB_VIEW__";

function normalizeBooleanFlag(value) {
  if (value === undefined || value === null || value === "") {
    return false;
  }
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    var normalized = value.trim().toLowerCase();
    return ["1", "true", "yes", "on"].indexOf(normalized) >= 0;
  }
  return Boolean(value);
}

function shouldForceHome(options) {
  var source = options && typeof options === "object" ? options : {};
  return normalizeBooleanFlag(
    source.forceHome !== undefined ? source.forceHome : source.force_home,
  );
}

function syncDeeptutorEntryFlag(payload) {
  try {
    var app = getApp();
    if (app && typeof app.syncDeeptutorEntryFlagFromPayload === "function") {
      app.syncDeeptutorEntryFlagFromPayload(payload);
    }
  } catch (_) {}
}

function resolveLaunchTarget(payload) {
  if (payload === 1 || payload === "1") {
    return "/pages/freeCourse/freeCourse";
  }
  if (typeof payload === "string") {
    return payload.indexOf("pages/") !== -1 ? payload : "";
  }
  if (!payload || typeof payload !== "object") {
    return "";
  }
  var candidates = [
    payload.route,
    payload.path,
    payload.url,
    payload.target_path,
    payload.targetPath,
    payload.page,
    payload.data,
  ];
  for (var i = 0; i < candidates.length; i++) {
    var item = candidates[i];
    if (typeof item !== "string") continue;
    if (item === "1") return "/pages/freeCourse/freeCourse";
    if (item.indexOf("pages/") !== -1) return item;
  }
  return "";
}

function readCachedLaunchState(allowExpired) {
  try {
    var cache = wx.getStorageSync(LAUNCH_CACHE_KEY);
    if (!cache || typeof cache !== "object") {
      return null;
    }
    if (
      !allowExpired &&
      Date.now() - (Number(cache.updatedAt) || 0) > LAUNCH_CACHE_TTL
    ) {
      return null;
    }
    return {
      payload: cache.payload,
      target:
        cache.target === WEB_VIEW_FALLBACK
          ? WEB_VIEW_FALLBACK
          : resolveLaunchTarget(cache.payload),
    };
  } catch (_) {
    return null;
  }
}

function writeCachedLaunchState(payload, target) {
  try {
    wx.setStorageSync(LAUNCH_CACHE_KEY, {
      payload: payload,
      target: target ? target : WEB_VIEW_FALLBACK,
      updatedAt: Date.now(),
    });
  } catch (_) {}
}

function clearCachedLaunchState() {
  try {
    wx.removeStorageSync(LAUNCH_CACHE_KEY);
  } catch (_) {}
}

Page({

  /**
   * 页面的初始数据
   */
  data: {
    showWebView: false,
    loadingLaunch: true
  },

  fallbackToWebView() {
    if (this._launchFinished) {
      return;
    }
    this._launchFinished = true;
    this.setData({
      showWebView: true,
      loadingLaunch: false
    });
  },

  resolveLaunchResponse(payload) {
    syncDeeptutorEntryFlag(payload);
    var launchTarget = resolveLaunchTarget(payload);
    writeCachedLaunchState(payload, launchTarget);
    if (launchTarget) {
      this.redirectToLaunchTarget(launchTarget);
      return;
    }
    this.fallbackToWebView();
  },

  redirectToLaunchTarget(target) {
    if (!target || this._launchFinished) {
      return;
    }
    this._launchFinished = true;
    wx.reLaunch({
      url: target,
      fail: () => {
        clearCachedLaunchState();
        this._launchFinished = false;
        this.fallbackToWebView();
      }
    });
  },

  /**
   * 生命周期函数--监听页面加载
  */
  onLoad(options) {
    this._launchFinished = false;
    if (shouldForceHome(options)) {
      clearCachedLaunchState();
      this.fallbackToWebView();
      return;
    }
    var cachedLaunchState = readCachedLaunchState(false);
    var staleLaunchState = cachedLaunchState || readCachedLaunchState(true);
    if (cachedLaunchState && cachedLaunchState.target) {
      syncDeeptutorEntryFlag(cachedLaunchState.payload);
      if (cachedLaunchState.target === WEB_VIEW_FALLBACK) {
        this.fallbackToWebView();
        return;
      }
      this.redirectToLaunchTarget(cachedLaunchState.target);
      return;
    }
    wx.request({
      url: 'https://www.yousenjiaoyu.com/gettopzm',
      method : 'POST',
      data:{
        act : '1'
      },
      header: {
        "Content-Type": "application/x-www-form-urlencoded"
      },
      success: (res) => {
        this.resolveLaunchResponse(res.data);
      },
      fail: () => {
        if (staleLaunchState && staleLaunchState.target) {
          syncDeeptutorEntryFlag(staleLaunchState.payload);
          if (staleLaunchState.target === WEB_VIEW_FALLBACK) {
            this.fallbackToWebView();
            return;
          }
          this.redirectToLaunchTarget(staleLaunchState.target);
          return;
        }
        this.fallbackToWebView();
      }
    })
  }
})
