const AutoUpdate = () => {
  if (wx.canIUse('getUpdateManager')) {
    const updateManager = wx.getUpdateManager()
    updateManager.onCheckForUpdate(function (res) {
      // 请求完新版本信息的回调
      if (res.hasUpdate) {
        console.log('res.hasUpdate====')
        updateManager.onUpdateReady(function () {
          wx.showModal({
            title: '更新提示',
            content: '新版本已经准备好，是否重启应用？',
            success: function (res) {
              console.log('success====', res)
              // res: {errMsg: "showModal: ok", cancel: false, confirm: true}
              if (res.confirm) {
                // 新的版本已经下载好，调用 applyUpdate 应用新版本并重启
                updateManager.applyUpdate()
              }
            }
          })
        })
        updateManager.onUpdateFailed(function () {
          // 新的版本下载失败
          wx.showModal({
            title: '已经有新版本了哟~',
            content: '新版本已经上线啦~，请您删除当前小程序，重新搜索打开哟~'
          })
        })
      }
    })
  }
}

/**
 * iphone手机底部适配
 */
function phoneSafeArea() {
  return new Promise((resolve, reject) => {
    wx.getSystemInfo({
      success: (res) => {
        let val = ['iPhone X', 'iPhone 11', 'iPhone 11 Pro Max','iPhone 11<iPhone12,1>'].includes(res.model)
        resolve(val)
      },
      fail: () => {
        reject()
      }
    })
  })
}

//获取系统信息
function getPhoneInfo() {
  return new Promise((resolve, reject) => {
    wx.getSystemInfo({
      success: (res) => {
        resolve(res)
      },
      fail: () => {
        reject()
      }
    })
  })
}

module.exports = {
  AutoUpdate,
  phoneSafeArea,
  getPhoneInfo
}
