import { postrq } from "../utils/request"
import { wxLogin,wxHide,wxToast} from "../utils/wxPromise"
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
            return postrq('GetOpenid',{js_code:res.code},true)
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
              return postrq('UpdateUser',data,true)
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