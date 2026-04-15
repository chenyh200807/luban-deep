// pages/wxshopview/wxshopview.js
Page({
  onLoad() {
    wx.redirectTo({
      url: '/pages/wxshop/wxshop',
      fail: () => {
        wx.reLaunch({
          url: '/pages/wxshop/wxshop'
        });
      }
    });
  }
})
