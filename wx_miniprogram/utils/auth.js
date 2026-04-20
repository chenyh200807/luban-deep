// utils/auth.js — Token 管理
const TOKEN_KEY = "auth_token";
const LEGACY_USER_ID_KEY = "auth_user_id";

const auth = {
  getToken() {
    return wx.getStorageSync(TOKEN_KEY) || null;
  },

  setToken(token) {
    wx.setStorageSync(TOKEN_KEY, token);
    wx.removeStorageSync(LEGACY_USER_ID_KEY);
  },

  clearToken() {
    wx.removeStorageSync(TOKEN_KEY);
    wx.removeStorageSync(LEGACY_USER_ID_KEY);
  },

  isLoggedIn() {
    return !!this.getToken();
  },
};

module.exports = auth;
