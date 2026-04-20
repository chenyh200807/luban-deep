// utils/auth.js — Token 管理
const TOKEN_KEY = "auth_token";
const USER_ID_KEY = "auth_user_id";

const auth = {
  extractUserIdFromAuthPayload(payload) {
    var raw = payload || {};
    var inner = (raw && raw.data) || raw || {};
    var user = inner.user || raw.user || {};
    return (
      raw.user_id ||
      inner.user_id ||
      user.user_id ||
      user.id ||
      inner.id ||
      raw.id ||
      null
    );
  },

  getToken() {
    return wx.getStorageSync(TOKEN_KEY) || null;
  },

  setToken(token, userId) {
    wx.setStorageSync(TOKEN_KEY, token);
    if (userId) wx.setStorageSync(USER_ID_KEY, userId);
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
