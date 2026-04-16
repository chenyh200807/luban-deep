// components/phoneBox/phoneBox.js
var behavior = require('../../utils/behavior')
import { wxToast } from "../../utils/wxPromise"
Component({
  /**
   * 组件的属性列表
   */
  properties: {
    phoneVisible:{
      type:Boolean,
      value:false,
      observer(newVal){
        this.setData({
          isPhoneVisible:newVal
        })
      }
    }
  },
  behaviors: [behavior],
  /**
   * 组件的初始数据
   */
  data: {
    isPhoneVisible:false
  },

  /**
   * 组件的方法列表
   */
  methods: {
    //绑定手机号
    getPhoneNumber(e){
      let that = this
      if(e.detail.errMsg=='getPhoneNumber:ok'){
        let {encryptedData,iv} = e.detail
        that.setData({ isPhoneVisible:false })
        wx.login({
          success: function (res) {
            let data = {
              iv: iv,
              encryptedData: encryptedData,
              js_code: res.code
            }
            that.isPostHttp('GetPhone',data,true).then(res=>{
              if (res.status==1){
                wxToast(res.msg)
                that.getUserInfo();
              }
            }).catch()
          }
        })
      }else{
        that.setData({
          isPhoneVisible:false
        })
      }
    }
  }
})
