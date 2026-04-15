// pages/wxshopview/wxshopview.js
Page({

  /**
   * 页面的初始数据
   */
  data: {
    searchstr : '黄皮书',
    shopappid : '',
    shopproductList : [],
    shoptokendata : '',
  },

  /**
   * 生命周期函数--监听页面加载
   */
  onLoad(options) {
    //获取shoptoken
    let _this = this;
    wx.request({
      url: 'https://www.yousenjiaoyu.com/wxshoptoken',
      header: {
        'content-type': 'application/json'
      },
      method: "POST",
      success: function (res) {
        // debugger;
        console.log(res)
        if(res.data.code==200){
          _this.setData({
            shopappid : res.data.shopappid,
            shopproductList : res.data.shopproductList.products
          })
          // _this.getshopproduct(res.data.tokendata);
        }else{
 
        }
      },
      fail: (err) => {
        reject(err)
      }
    })
  },

  /**
   * 生命周期函数--监听页面初次渲染完成
   */
  onReady() {
    console.log('sss'+this.data.searchstr)
    this.setData({
      searchstr:this.data.searchstr
    })
    //获取shoptoken

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

  onSearchInput:function(e){
    console.log(e)
    this.setData({
      keyword:e.detail.value
    })
  },
  handleSearch : function(e){
    // const keyword = e.detail;
    console.log('开始搜索1'+this.data.keyword)
    wx.request({
      url: baseUrl3 + getUrl(urlName),
      data: data,
      header: {
        'content-type': 'application/json'
      },
      method: "POST",
      success: function (res) {
        if(res.data.code==200){
          resolve(res.data)
          wx.hideLoading()
        }else{
          resolve(res.data)
          wx.hideLoading()
        }
      },
      fail: (err) => {
        reject(err)
      }
    })
  },

  //获取小店数据
  getshopproduct:function(tokendata){
      console.log(tokendata)
      var _this = this;
      // 开始获取商品列表
      // https://api.weixin.qq.com/channels/ec/store/window/product/list/get?access_token=ACCESS_TOKEN
      var data = {
        page_size : 10
      }
      debugger
      wx.request({
        url: 'https://api.weixin.qq.com/channels/ec/store/window/product/list/get?access_token=' + tokendata.access_token,
        data: data,
        header: {
          'content-type': 'application/json'
        },
        method: "POST",
        success: function (res) {
          if(res.data.errcode== 0){
             //请求成功
             _this.setData({
               shopproductList : res.data.products
             })
          }else{
             //请求失败
          }
        },
        fail: (err) => {
          reject(err)
        }
      })
  }

})