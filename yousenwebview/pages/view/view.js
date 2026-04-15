// pages/view/view.js
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
        //开始获取id
        if (options) {
          console.log(options.urlname)
         
          //请求地址，上线前要切换，在获取小程序链接的php文件里面获取
          var geturl = 'https://test2.yousenjiaoyu.com';

          if(options.urlname.indexOf('.yousenjiaoyu.com')!=-1){
            this.setData({
              url:  options.urlname
            });
          }else{
            
            //判断是不是正式服，如果为true，则为正式服
            if(options.online == 'true'){
                geturl = 'https://www.yousenjiaoyu.com';
            }
          
            this.setData({
              url: geturl+'/getwx/urlname/' + options.urlname
            });
            console.log(geturl+'/getwx/urlname/' + options.urlname);
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
        //获取id

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