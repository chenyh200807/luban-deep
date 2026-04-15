// pages/getpeople/getpeople.js
Page({
  data: {
    imageUrl: 'https://cnd.yousenjiaoyu.com/e1/69fc86507b31f310f3b5a66d31c685.png'
  },

  previewImage() {
    wx.openUrl({
      url: 'https://work.weixin.qq.com/apph5/external_room/join/group_mng?plg_id=f16ac75968906daa8d4b78253a2e047d&'
    })
  },

  show() {
    wx.openUrl({
      url: 'https://work.weixin.qq.com/gm/e94fe429a2159d6326260f292b4d98d5'
    })
  }
})
