import { resUrl } from "./config"
import { postrq,getrq,postrq2 } from "./request"
import {phoneSafeArea} from "./system"
import {wxModel} from "./wxPromise"
let Function = require("./function")
const app = getApp()
const BROTHER_MAJOR_CACHE_KEY = "yousen_brother_major_cache"
const BROTHER_MAJOR_CACHE_TTL = 12 * 60 * 60 * 1000
const brotherMajorPromiseMap = {}

function getBrotherMajorCacheKey(majorId) {
  return `${BROTHER_MAJOR_CACHE_KEY}:${majorId}`
}

function readBrotherMajorCacheList(majorId, allowExpired) {
  try {
    const cache = wx.getStorageSync(getBrotherMajorCacheKey(majorId))
    if (!cache || typeof cache !== "object") {
      return null
    }
    if (
      !allowExpired &&
      Date.now() - (Number(cache.updatedAt) || 0) > BROTHER_MAJOR_CACHE_TTL
    ) {
      return null
    }
    return Array.isArray(cache.majorList) ? cache.majorList : null
  } catch (_) {
    return null
  }
}

function writeBrotherMajorCacheList(majorId, majorList) {
  try {
    wx.setStorageSync(getBrotherMajorCacheKey(majorId), {
      majorList: majorList,
      updatedAt: Date.now(),
    })
  } catch (_) {}
}

function normalizeBrotherMajorList(list, majorId) {
  const source = Array.isArray(list) ? list : []
  return source.map((item) => {
    return Object.assign({}, item, {
      flag: item && item.pk_id == majorId,
    })
  })
}
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
      if (app && typeof app.getHostSysInfo === "function") {
        return app.getHostSysInfo().then((sysInfo) => {
          this.setData({
            sysInfo: sysInfo
          })
          return sysInfo
        }).catch(() => {
          const fallback = app.globalData.sysInfo || { is_audit: 0 }
          app.globalData.sysInfo = fallback
          this.setData({
            sysInfo: fallback
          })
          return fallback
        })
      }
      return this.isGetHttp('GetSysInfo').then(res=>{
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
      const members = wx.getStorageSync('members')
      if (!members || !members.pk_id) {
        return Promise.resolve(null)
      }
      return postrq('GetUserDetail',{fk_user_id:members.pk_id},false).then(res=>{
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
        const members = wx.getStorageSync('members')
        if(members && members.pk_id){
          resolve(members);
        }else{
          wxModel({content:'你还未授权是否前往授权'}).then(()=>{
            wx.navigateTo({
              url: '/pages/auth/auth',
              complete: () => {
                reject(new Error('unauthorized'))
              }
            })
          }).catch((err) => {
            reject(err || new Error('unauthorized'))
          })
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
      const majorId = wx.getStorageSync('major_id') ? wx.getStorageSync('major_id') : 0
      const cachedList = readBrotherMajorCacheList(majorId, false)
      if (cachedList) {
        if (this && typeof this.setData === "function") {
          this.setData({
            majorList: cachedList
          })
        }
        return Promise.resolve(cachedList)
      }
      if (!brotherMajorPromiseMap[majorId]) {
        let data = {
          fk_major_id: majorId
        }
        brotherMajorPromiseMap[majorId] = this.isPostHttp('GetBrotherMajor',data).then(res=>{
          if(res.status == 1){
            const majorList = normalizeBrotherMajorList(res.data, majorId)
            writeBrotherMajorCacheList(majorId, majorList)
            return majorList
          }
          return readBrotherMajorCacheList(majorId, true) || []
        }).catch(()=>{
          const fallbackList = readBrotherMajorCacheList(majorId, true)
          return fallbackList || []
        }).finally(()=>{
          delete brotherMajorPromiseMap[majorId]
        })
      }
      return brotherMajorPromiseMap[majorId].then(majorList => {
        if (this && typeof this.setData === "function") {
          this.setData({
            majorList:majorList
          })
        }
        return majorList
      })
    },
  }
})
