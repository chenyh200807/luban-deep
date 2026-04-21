// utils/auth.js — Token 管理
const TOKEN_KEY = "auth_token";
const TOKEN_EXP_KEY = "auth_token_exp";
const LEGACY_USER_ID_KEY = "auth_user_id";

function normalizeExpiry(value) {
  var parsed = parseInt(value, 10);
  return parsed > 0 ? parsed : 0;
}

function decodeBase64UrlToUtf8(value) {
  var normalized = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
  while (normalized.length % 4) {
    normalized += "=";
  }
  if (typeof Buffer !== "undefined") {
    return Buffer.from(normalized, "base64").toString("utf8");
  }
  if (typeof atob === "function") {
    try {
      return decodeURIComponent(
        atob(normalized)
          .split("")
          .map(function (ch) {
            return "%" + ("00" + ch.charCodeAt(0).toString(16)).slice(-2);
          })
          .join(""),
      );
    } catch (_err) {
      return "";
    }
  }
  if (
    typeof wx !== "undefined" &&
    wx &&
    typeof wx.base64ToArrayBuffer === "function" &&
    typeof Uint8Array !== "undefined"
  ) {
    try {
      var bytes = new Uint8Array(wx.base64ToArrayBuffer(normalized));
      var raw = "";
      var i;
      for (i = 0; i < bytes.length; i += 1) {
        raw += String.fromCharCode(bytes[i]);
      }
      return decodeURIComponent(
        raw
          .split("")
          .map(function (ch) {
            return "%" + ("00" + ch.charCodeAt(0).toString(16)).slice(-2);
          })
          .join(""),
      );
    } catch (_err2) {
      return "";
    }
  }
  return "";
}

function parseTokenExpiry(token) {
  var parts = String(token || "").split(".");
  if (parts.length !== 3 || parts[0] !== "dtm") {
    return 0;
  }
  try {
    return normalizeExpiry(JSON.parse(decodeBase64UrlToUtf8(parts[1])).exp);
  } catch (_err) {
    return 0;
  }
}

const auth = {
  getToken() {
    return wx.getStorageSync(TOKEN_KEY) || null;
  },

  setToken(token, expiresAt) {
    wx.setStorageSync(TOKEN_KEY, token);
    var normalizedExpiry = normalizeExpiry(expiresAt);
    if (normalizedExpiry) {
      wx.setStorageSync(TOKEN_EXP_KEY, normalizedExpiry);
    } else {
      wx.removeStorageSync(TOKEN_EXP_KEY);
    }
    wx.removeStorageSync(LEGACY_USER_ID_KEY);
  },

  getTokenExpiry() {
    var storedExpiry = normalizeExpiry(wx.getStorageSync(TOKEN_EXP_KEY));
    if (storedExpiry) {
      return storedExpiry;
    }
    var parsedExpiry = parseTokenExpiry(this.getToken());
    if (parsedExpiry) {
      wx.setStorageSync(TOKEN_EXP_KEY, parsedExpiry);
    }
    return parsedExpiry;
  },

  shouldRefreshToken(bufferSeconds) {
    var expiresAt = this.getTokenExpiry();
    var threshold = Math.max(60, parseInt(bufferSeconds, 10) || 0);
    if (!expiresAt) {
      return false;
    }
    return expiresAt - Math.floor(Date.now() / 1000) <= threshold;
  },

  clearToken() {
    wx.removeStorageSync(TOKEN_KEY);
    wx.removeStorageSync(TOKEN_EXP_KEY);
    wx.removeStorageSync(LEGACY_USER_ID_KEY);
  },

  isLoggedIn() {
    return !!this.getToken();
  },
};

module.exports = auth;
