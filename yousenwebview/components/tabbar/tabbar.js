// components/tabbar/tabbar.js
import {phoneSafeArea} from "../../utils/system"
var behavior = require('../../utils/behavior')
let Function = require("../../utils/function")
const app = getApp()
Component({
  /**
   * 组件的属性列表
   */
  properties: {
    index:{
      type:Number,
      value:'',
      observer: function(newVal) {
        this.setData({
          active:newVal
        })
      }
    }
  },
  behaviors: [behavior],
  pageLifetimes: {
    // 组件所在页面的生命周期函数
    show: function () {
      phoneSafeArea().then((res)=>{
        this.setData({
          "isIphoneX":res
        })
      }).catch()
      // setTimeout(() => {
      //   this.setData({
      //     sysInfo:app.globalData.sysInfo
      //   })
      //   console.log(app.globalData.sysInfo,"sysInfosysInfosysInfo")
      // }, 1000);
      this.getSysInfo()
    },
  },
  attached: function () {
    console.log(111)
    this.setData({
      sysInfo:app.globalData.sysInfo
    })
  },
  options: {
    styleIsolation: 'shared',
  },
  /**
   * 组件的初始数据
   */
  data: {
    isIphoneX:false,
    active:0,
    // sysInfo:{},
    tabBar:[
      {
        iconPath:"/images/tabber/tab_11.png",
        selectedIconPath:"/images/tabber/tab_1.png",
        text:"首页",
        url:"/pages/index/index"
      },
      {
        iconPath:"/images/tabber/tab_22.png",
        selectedIconPath:"/images/tabber/tab_2.png",
        text:"购课",
        url:"/pages/qualityCourses/qualityCourses"
      },
      {
        iconPath:"/images/tabber/tab_33.png",
        selectedIconPath:"/images/tabber/tab_3.png",
        text:"名师答疑",
        url:"/pages/teacherQuestion/teacherQuestion"
      },
      {
        iconPath:"/images/tabber/tab_44.png",
        selectedIconPath:"/images/tabber/tab_4.png",
        text:"领取福利",
        url:"/pages/activityCenter/activityCenter"
      },
      {
        iconPath:"/images/tabber/tab_55.png",
        selectedIconPath:"/images/tabber/tab_5.png",
        text:"我的",
        url:"/pages/my/my"
      }
    ],
    tabBar2:[
      {
        iconPath:"/images/tabber/tab_11.png",
        selectedIconPath:"/images/tabber/tab_1.png",
        text:"首页",
        url:"/pages/index/index"
      },
      {
        iconPath:"/images/tabber/tab_44.png",
        selectedIconPath:"/images/tabber/tab_4.png",
        text:"领取福利",
        url:"/pages/activityCenter/activityCenter"
      },
      {
        iconPath:"/images/tabber/tab_55.png",
        selectedIconPath:"/images/tabber/tab_5.png",
        text:"我的",
        url:"/pages/my/my"
      }
    ],
  },

  /**
   * 组件的方法列表
   */
  methods: {
    linkTo(e){
      let url = Function.getDataSet(e,'url')
      let index = Function.getDataSet(e,"index")
      Function.linkTo(url)
    },
    onChange(event) {
      let index=event.currentTarget.dataset.index;
      if(this.data.active==index){
        return;
      }else{
        if(this.data.sysInfo.is_audit == 1){
          wx.redirectTo({
            url: this.data.tabBar[index].url
          })
        }else{
          wx.redirectTo({
            url: this.data.tabBar2[index].url
          })
        }
        this.setData({ active: index });
      }
    },
  }
  
})