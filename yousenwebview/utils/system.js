const AutoUpdate = () => {
  if (wx.canIUse('getUpdateManager')) {
    const updateManager = wx.getUpdateManager()
    updateManager.onCheckForUpdate(function (res) {
      if (res.hasUpdate) {
        updateManager.onUpdateReady(function () {
          wx.showModal({
            title: '更新提示',
            content: '新版本已经准备好，是否重启应用？',
            success: function (res) {
              if (res.confirm) {
                updateManager.applyUpdate()
              }
            }
          })
        })
        updateManager.onUpdateFailed(function () {
          wx.showModal({
            title: '已经有新版本了哟~',
            content: '新版本已经上线啦~，请您删除当前小程序，重新搜索打开哟~'
          })
        })
      }
    })
  }
}

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
