// utils/auth.js — Token 管理
const TOKEN_KEY = "auth_token";
const TOKEN_EXP_KEY = "auth_token_exp";
const USER_ID_KEY = "auth_user_id";

function clearReportCache(userId) {
  // Kept lazy so auth's pure VM contract remains usable outside the mini-app
  // module loader; production still delegates the key/envelope to its owner.
  if (typeof require !== "function") return;
  try {
    require("./report-cache").clear(userId);
  } catch (_err) {}
}

function normalizeExpiry(value) {
  if (typeof value === "string" && !/^\d+$/.test(value.trim())) {
    return 0;
  }
  var parsed = parseInt(value, 10);
  return parsed > 0 ? parsed : 0;
}

function normalizeText(value) {
  if (value === undefined || value === null) return "";
  return String(value).trim();
}

function isUuidLike(value) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    normalizeText(value),
  );
}

function collectCandidates(source, canonical, fallback) {
  if (!source) return;
  if (typeof source === "string" || typeof source === "number") {
    var text = normalizeText(source);
    if (text) fallback.push(text);
    return;
  }
  if (typeof source !== "object") return;
  [
    source.canonical_uid,
    source.canonicalUid,
    source.canonicalUserId,
  ].forEach(function (value) {
    var text = normalizeText(value);
    if (text) canonical.push(text);
  });
  [
    source.user_id,
    source.userId,
    source.id,
    source.uid,
    source.sub,
    source.external_auth_user_id,
    source.externalAuthUserId,
  ].forEach(function (value) {
    var text = normalizeText(value);
    if (text) fallback.push(text);
  });
  if (source.user && typeof source.user === "object") {
    collectCandidates(source.user, canonical, fallback);
  }
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

  selectUserId() {
    var canonical = [];
    var fallback = [];
    for (var i = 0; i < arguments.length; i += 1) {
      collectCandidates(arguments[i], canonical, fallback);
    }
    for (var j = 0; j < canonical.length; j += 1) {
      if (isUuidLike(canonical[j])) return canonical[j];
    }
    for (var k = 0; k < fallback.length; k += 1) {
      if (isUuidLike(fallback[k])) return fallback[k];
    }
    return canonical[0] || fallback[0] || null;
  },

  setToken(token, expiresAt, userSource) {
    wx.setStorageSync(TOKEN_KEY, token);
    var selectedUserId = null;
    var normalizedExpiry = normalizeExpiry(expiresAt);
    if (typeof expiresAt === "object" && expiresAt !== null) {
      userSource = expiresAt;
      normalizedExpiry = normalizeExpiry(expiresAt.expires_at || expiresAt.expiresAt || expiresAt.exp);
    }
    if (normalizedExpiry) {
      wx.setStorageSync(TOKEN_EXP_KEY, normalizedExpiry);
    } else {
      wx.removeStorageSync(TOKEN_EXP_KEY);
    }
    selectedUserId = this.selectUserId(userSource);
    if (!selectedUserId && !normalizedExpiry) {
      selectedUserId = this.selectUserId(expiresAt);
    }
    var existingUserId = normalizeText(wx.getStorageSync(USER_ID_KEY));
    if (isUuidLike(existingUserId) && !isUuidLike(selectedUserId)) {
      selectedUserId = existingUserId;
    }
    if (selectedUserId) {
      wx.setStorageSync(USER_ID_KEY, selectedUserId);
    } else {
      wx.removeStorageSync(USER_ID_KEY);
    }
  },

  getUserId() {
    return wx.getStorageSync(USER_ID_KEY) || null;
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
    // Identity authority owns invalidation.  This covers logout, token expiry,
    // 401 refresh failure and forced re-login without duplicating purge logic.
    clearReportCache(this.getUserId());
    wx.removeStorageSync(TOKEN_KEY);
    wx.removeStorageSync(TOKEN_EXP_KEY);
    wx.removeStorageSync(USER_ID_KEY);
  },

  isLoggedIn() {
    if (!this.getToken()) return false;
    var expiresAt = this.getTokenExpiry();
    if (expiresAt && expiresAt <= Math.floor(Date.now() / 1000)) {
      this.clearToken();
      return false;
    }
    return true;
  },
};

module.exports = auth;
