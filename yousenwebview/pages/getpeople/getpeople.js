// pages/getpeople/getpeople.js
Page({

  /**
   * 页面的初始数据
   */
  data: {
    imageUrl: 'https://cnd.yousenjiaoyu.com/e1/69fc86507b31f310f3b5a66d31c685.png'
  },
  previewImage: function() {
    wx.openUrl({
      url: 'https://work.weixin.qq.com/apph5/external_room/join/group_mng?plg_id=f16ac75968906daa8d4b78253a2e047d&'
      })
    // wx.previewImage({
    //   urls: [this.data.imageUrl]
    // })
  },

  show:function(){
    console.log('ss');
    wx.openUrl({
      url: 'https://work.weixin.qq.com/gm/e94fe429a2159d6326260f292b4d98d5'
      })
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

  }
})