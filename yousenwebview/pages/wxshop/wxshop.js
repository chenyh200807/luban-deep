// pages/wxshop/wxshop.js
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

  },

  gotoshop(){
    console.log('ssss')
    wx.navigateToMiniProgram({
      appId: 'wx70b10f0bee143b8e', // 替换为你的微小店的 AppID
      path: 'pages/index/index', // 可选，默认打开小程序首页
      extraData: {
        from: 'your-mini-program' // 可选，传递给小程序的数据
      },
      envVersion: 'release', // 可选，要打开的小程序版本（develop、trial、release）
      success(res) {
        // 跳转成功
        console.log('跳转成功', res);
      },
      fail(res) {
        // 跳转失败
        console.log('跳转失败', res);
      }
    });
  }

})