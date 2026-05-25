Page({
  data: {
    qrcodePath: 'https://www.yousenjiaoyu.com/static/default/wxcss/images/%E4%BA%8C%E5%BB%BA.png',
    wxqrcodeurl: 'https://work.weixin.qq.com/gm/5308564de1d9534384aa5187a308fc3d'
  },

  onLoad(options) {
    void options;
  },

  onReady() {},
  onShow() {},
  onHide() {},
  onUnload() {},
  onPullDownRefresh() {},
  onReachBottom() {},
  copyGroupLink() {
    wx.setClipboardData({
      data: this.data.wxqrcodeurl,
      success() {
        wx.showToast({ title: '已复制入群链接', icon: 'none' });
      }
    });
  },
  onShareAppMessage() {}
});
