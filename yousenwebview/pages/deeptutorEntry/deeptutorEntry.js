const DEEPTUTOR_SUBPACKAGE_ROOT = "packageDeeptutor";

function decodeParam(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    return decodeURIComponent(raw);
  } catch (error) {
    return raw;
  }
}

function buildDeeptutorLoginUrl(entrySource, returnTo) {
  return (
    "/packageDeeptutor/pages/login/login?entrySource=" +
    encodeURIComponent(String(entrySource || "").trim()) +
    "&returnTo=" +
    encodeURIComponent(String(returnTo || "").trim())
  );
}

function scheduleAfterReady(task) {
  if (typeof task !== "function") return;
  if (typeof wx.nextTick === "function") {
    wx.nextTick(task);
    return;
  }
  setTimeout(task, 16);
}

Page({
  data: {
    loading: true,
    errorMsg: "",
  },

  onLoad(options) {
    this._entrySource = decodeParam(
      options && (options.entrySource || options.entry_source || options.source)
    );
    this._returnTo = decodeParam(options && options.returnTo);
  },

  onReady() {
    this.openTarget();
  },

  openTarget() {
    if (this._opening) {
      return;
    }
    this._opening = true;
    this.setData({
      loading: true,
      errorMsg: "",
    });
    const targetUrl = buildDeeptutorLoginUrl(this._entrySource, this._returnTo);
    const handleFailure = (err) => {
      this._opening = false;
      console.error("[deeptutor.bridge] unable to open login page", err);
      this.setData({
        loading: false,
        errorMsg:
          (err && err.errMsg) || "鲁班AI智考入口暂时无法打开，请稍后重试",
      });
    };
    const routeToTarget = () => {
      scheduleAfterReady(() => {
        wx.redirectTo({
          url: targetUrl,
          fail: (err) => {
            console.warn(
              "[deeptutor.bridge] redirectTo login failed, fallback to reLaunch",
              err
            );
            wx.reLaunch({
              url: targetUrl,
              fail: (fallbackErr) => {
                handleFailure(fallbackErr || err);
              },
            });
          },
        });
      });
    };

    if (typeof wx.loadSubpackage === "function") {
      wx.loadSubpackage({
        name: DEEPTUTOR_SUBPACKAGE_ROOT,
        success: routeToTarget,
        fail: (err) => {
          console.error("[deeptutor.bridge] load deeptutor subpackage failed", err);
          handleFailure(err);
        },
      });
      return;
    }

    routeToTarget();
  },

  handleRetry() {
    this.openTarget();
  },
});
