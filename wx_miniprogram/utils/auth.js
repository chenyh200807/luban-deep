// utils/auth.js — Token 管理
const TOKEN_KEY = "auth_token";
const USER_ID_KEY = "auth_user_id";

const auth = {
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
