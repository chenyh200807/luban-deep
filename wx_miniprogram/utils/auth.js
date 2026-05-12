// utils/auth.js — Token 管理
const TOKEN_KEY = "auth_token";
const USER_ID_KEY = "auth_user_id";

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

const auth = {
  getToken() {
    return wx.getStorageSync(TOKEN_KEY) || null;
  },

  selectUserId() {
    var canonical = [];
    var fallback = [];
    for (var i = 0; i < arguments.length; i++) {
      collectCandidates(arguments[i], canonical, fallback);
    }
    for (var j = 0; j < canonical.length; j++) {
      if (isUuidLike(canonical[j])) return canonical[j];
    }
    for (var k = 0; k < fallback.length; k++) {
      if (isUuidLike(fallback[k])) return fallback[k];
    }
    return canonical[0] || fallback[0] || null;
  },

  setToken(token, userId) {
    wx.setStorageSync(TOKEN_KEY, token);
    var selectedUserId = this.selectUserId(userId);
    var existingUserId = normalizeText(wx.getStorageSync(USER_ID_KEY));
    if (isUuidLike(existingUserId) && !isUuidLike(selectedUserId)) {
      selectedUserId = existingUserId;
    }
    if (selectedUserId) wx.setStorageSync(USER_ID_KEY, selectedUserId);
  },

  getUserId() {
    return wx.getStorageSync(USER_ID_KEY) || null;
  },

  clearToken() {
    wx.removeStorageSync(TOKEN_KEY);
    wx.removeStorageSync(USER_ID_KEY);
  },

  isLoggedIn() {
    return !!this.getToken();
  },
};

module.exports = auth;
