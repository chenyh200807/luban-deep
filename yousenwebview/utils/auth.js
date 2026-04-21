import hostApiMap from "../api/baseApi"
import { baseUrl3 } from "../utils/config"
import { wxLogin,wxHide,wxToast} from "../utils/wxPromise"

function postHostRequest(urlName, data = {}, isLoading = false) {
  return new Promise((resolve, reject) => {
    let shouldHideLoading = false
    if (isLoading) {
      shouldHideLoading = true
      wx.showLoading({
        title: "加载中",
        mask: false
      })
    }
    wx.request({
      url: baseUrl3 + hostApiMap[urlName],
      data: data,
      header: {
        "content-type": "application/json"
      },
      method: "POST",
      success: (res) => {
        resolve(res.data)
      },
      fail: (err) => {
        reject(err)
      },
      complete: () => {
        if (shouldHideLoading) {
          wx.hideLoading()
        }
      }
    })
  })
}

const login = ()=>{
  return new Promise((resolve, reject) => {
      wx.getUserProfile({
        lang: "zh_CN",
        desc: '用于完善会员资料',
        success: function (res) {
          let userInfo = res.userInfo
          wx.showLoading({
            title: "授权中...",
            mask: true,
          });
          wxLogin().then((res)=>{   //获取到code
            return postHostRequest('GetOpenid',{js_code:res.code},true)
          }).then((res)=>{
            var top_id = wx.getStorageSync('top_id');
            var active_id=wx.getStorageSync('active_id');
            let data={
              headimgurl: userInfo.avatarUrl,
              city: userInfo.city,
              gender: userInfo.gender,
              language: userInfo.language,
              nickname: userInfo.nickName,
              province: userInfo.province,
              openid: res.data.openid,
              fk_user_id: top_id ? top_id:0,
              from_type:active_id?active_id:1
              }
              return postHostRequest('UpdateUser',data,true)
          }).then((res)=>{
            resolve(res)
            wxHide()
            wxToast('授权成功','success')
          }).catch(()=>{
            reject()
            wxHide()
          })
        }
      })
  })
}

module.exports={
  login
}
