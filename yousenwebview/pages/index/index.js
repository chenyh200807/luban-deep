// pages/index1/index1.js
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
        
        if(res.data == 1){
          wx.reLaunch({
            url: '/pages/freeCourse/freeCourse'
          })
        }else{
          if(res.data.indexOf('pages/') != -1 ){
            wx.reLaunch({
              url: res.data
            })
          }

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