// components/tabTop/tabTop.js
let app=getApp();
Component({
  /**
   * 组件的属性列表
   */
  properties: {
    tabTopTitle:{
      type:String,
      value:''
    },
    tabTopColor:{
      type:String,
      value:'#fff'
    },
    bg:{
      type:String,
      value:''
    }
  },
  pageLifetimes: {
    // 组件所在页面的生命周期函数
    show: function () {
      this.setData({
        isHome:getCurrentPages().length>1?false:true,
        navHeight:getApp().globalData.navHeight,
        titleHeight:getApp().globalData.titleHeight,
        fontSizeSetting:getApp().globalData.fontSizeSetting,
      })
    },
    hide: function () { },
    resize: function () { },
  },
  /**
   * 组件的初始数据
   */
  data: {

  },

  /**
   * 组件的方法列表
   */
  methods: {
    navigateBack(){
      wx.navigateBack({
        delta: 1
      })
    }
  }
})
