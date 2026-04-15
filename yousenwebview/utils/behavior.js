import { resUrl } from "./config"
import { postrq,getrq,postrq2 } from "./request"
import {phoneSafeArea} from "./system"
import {wxModel} from "./wxPromise" 
let Function = require("./function")
const app = getApp()
module.exports = Behavior({
  behaviors: [],
  data: {
    url:resUrl,
    navHeight:app.globalData.navHeight,
    isIphoneX:false,
    sysInfo:{}
  },
  methods:{
    linkTo(e){
      let url = e.currentTarget.dataset.url
      let urlList = ['/pages/index/index','/pages/qualityCourses/qualityCourses','/pages/teacherQuestion/teacherQuestion','/pages/activityCenter/activityCenter','/pages/my/my']
      if(urlList.includes(url)){
        wx.reLaunch({
          url: url
        })
      }else{
        Function.linkTo(url)
      }
    },
    //跳转需要验证授权
    checkLinkTo(e){
      let url = e.currentTarget.dataset.url
      this.checkLogin().then(res=>{
        Function.linkTo(url)
      }).catch()
    },
    isPostHttp(urlName,data={},isLoading=false){
      return postrq(urlName,data,isLoading)
    },
    isPostHttp2(urlName,data={},isLoading=false){
      return postrq2(urlName,data,isLoading)
    },
    isGetHttp(urlName,data={},isLoading=false){
      return getrq(urlName,data,isLoading)
    },
    //获取系统信息
    getSysInfo(){
      this.isGetHttp('GetSysInfo').then(res=>{
        if(res.status == 1){
          app.globalData.sysInfo = res.data
          this.setData({
            sysInfo:res.data
          })
        }
      }).catch()
    },
    //获取用户信息
    getUserInfo(){
      postrq('GetUserDetail',{fk_user_id:wx.getStorageSync('members').pk_id},false).then(res=>{
        if(res.status==1){
          app.globalData.userInfo = res.data
          wx.setStorageSync('members', res.data)
          this.setData({
            membersInfo:res.data
          })
        }
      }).catch()
    },
    //判断有无授权
    checkLogin(){
      return new Promise((resolve,reject)=>{
        if(wx.getStorageSync('members')){
          resolve();
        }else{
          wxModel({content:'你还未授权是否前往授权'}).then(()=>{
            wx.navigateTo({
              url: '/pages/auth/auth',
            })
          }).catch()
        }
      })
    },
    getSystemInfo(){
      phoneSafeArea().then((res)=>{
        this.setData({
          "isIphoneX":res
        })
      }).catch()
    },
    //获取同级分类
    getBrotherMajor(){
      let data = {
        fk_major_id:wx.getStorageSync('major_id')?wx.getStorageSync('major_id'):0
      }
      this.isPostHttp('GetBrotherMajor',data).then(res=>{
        if(res.status == 1){
          res.data.forEach((item)=>{
            if(item.pk_id == wx.getStorageSync('major_id')){
              item.flag = true
            }else{
              item.flag = false
            }
            
          })
          this.setData({
            majorList:res.data
          })
        }
      }).catch()
    },
  }
})