// pages/index1/index1.js
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

Page({

  /**
   * 页面的初始数据
   */
  data: {

  },

  /**
   * 生命周期函数--监听页面加载
   */
  onLoad(options) {

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
        console.log(res);
        //debugger;
        syncDeeptutorEntryFlag(res.data);
        var launchTarget = resolveLaunchTarget(res.data);
        if (launchTarget) {
          wx.reLaunch({
            url: launchTarget
          });
        }
      },
    })

  },

  /**
   * 生命周期函数--监听页面初次渲染完成
   */
  onReady() {

  },

  /**
   * 生命周期函数--监听页面显示
   */
  onShow() {

  },

  /**
   * 生命周期函数--监听页面隐藏
   */
  onHide() {

  },

  /**
   * 生命周期函数--监听页面卸载
   */
  onUnload() {

  },

  /**
   * 页面相关事件处理函数--监听用户下拉动作
   */
  onPullDownRefresh() {

  },

  /**
   * 页面上拉触底事件的处理函数
   */
  onReachBottom() {

  },

  /**
   * 用户点击右上角分享
   */
  onShareAppMessage() {

  }
})
