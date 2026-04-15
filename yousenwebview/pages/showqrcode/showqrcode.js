// pages/showqrcode/showqrcode.js
Page({

  /**
   * 页面的初始数据
   */
  data: {
      title:'一建全阶段备考资料',
      title1:'一级建造师',
      title2:'一建全阶段备考资料',
      wxqrcodeurl:'https://work.weixin.qq.com/gm/8106a93d48e58ff10b9d3f54fb8421d6',
      arraydesc:[],
      descstring:'保姆级全程规划备考指导攻略！群内福利资料均为免费！'
  },

  /**
   * 生命周期函数--监听页面加载
   */
  onLoad(options) {
    if (options) {
      console.log(options.id)
      if(options.id != undefined){
        console.log('ss');
        this.getdatafromapi(options.id );
      }else{
        console.log('ss1');
        this.getdatafromapi(1);
      }
    }
    
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

  getdatafromapi(id){
    var _this = this;
    var data = '';
    var url = 'https://www.yousenjiaoyu.com/getdatabyidzm/id/'+id;
    wx.request({
      url: url, // 请求的地址
      method: 'GET', // 请求方法为 GET
      success(res) {
        // 请求成功后的回调函数
        console.log(res.data); // 打印响应数据
        _this.setData({
          title: res.data.xcxData.title,
          title1:res.data.xcxData.title1,
          title2:res.data.xcxData.title2,
          wxqrcodeurl:res.data.xcxData.wxqrcodeurl,
          arraydesc:res.data.arraydesc,
          descstring:res.data.descstring
        });
        var arraydesc = res.data.arraydesc;
        console.log(arraydesc);

        // for (let index = 0; index < arraydesc.length; index++) {
        //   const element = arraydesc[index];
        //   console.log(element);
        // }
      },
      fail(error) {
        // 请求失败后的回调函数
        console.log(error); // 打印错误信息
      }
    });
  }
})