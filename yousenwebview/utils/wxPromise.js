function wxPromise() {
  return new Promise((resolve, reject) => {
    resolve()
  })
}

function wxLogin() {
  return new Promise((resolve, reject) => {
    wx.login({
      success(res) {
        resolve(res)
      },
      fail() {
        reject('wx登录获取用户失败')
      }
    })
  })
}

function wxModel(params) {
  return new Promise((resolve, reject) => {
    wx.showModal({
      ...params,
      success(res) {
        if (res.confirm) {
          resolve()
        } else {
          reject()
        }
      },
      fail() {
        reject()
      }
    })
  })
}

function wxLoading(msg = '正在加载') {
  wx.showLoading({mask: true, title: msg})
}

function wxHide() {
  wx.hideLoading()
}

function wxToast(msg, type = 'none') {
  wx.showToast({
    title: msg,
    icon: type
  })
}

/**
 * 在拉取需要用户授权的接口时，先调取此方法
 * @param authStr 'scope.address'
 * @returns {Promise<unknown>}
 */
function checkSetting(authStr, msg = '是否去权限管理页打开授权') {
  return new Promise((resolve, reject) => {
    wx.getSetting({
      success: res => {
        if (res.authSetting[authStr] === undefined) {
          wx.authorize({
            scope: authStr,
            success: res1 => {
              resolve(res1)
            },
            fail: err1 => {
              reject(err1)
            }
          })
        } else if (res.authSetting[authStr] === false) {
          wx.showModal({
            title: '权限管理',
            content: msg,
            success: res => {
              if (res.confirm) {
                wx.openSetting({})
              }
            }
          })
        }else if (res.authSetting[authStr]) {
          resolve()
        }
      },
      fail: err => {
        reject(err)
      }
    })
  })
}

/**
 *获取图片信息
 * @param src
 */
function wxGetImageInfo(src) {
  return new Promise((resolve, reject) => {
    wx.getImageInfo({
      src,
      success(res) {
        resolve(res)
      },
      fail() {
        reject('获取图片信息失败')
      }
    })
  })
}

function wxGetLocation(){
  
}

function wxChooseAddress() {
  
}

function wxRequestPayment(params) {
  return new Promise((resolve, reject) => {
    wx.requestPayment({
      'timeStamp': params.timeStamp,
      'nonceStr': params.nonceStr,
      'package': params.package,
      'signType': params.signType,
      'paySign': params.paySign,
      'success': res => {
        resolve(params)
      },
      'fail': err => {
        reject(err)
      }
    })
  })
}

function wxRedirect(url) {
  wx.redirectTo({
    url,
    fail: function () {
      wx.switchTab({
        url,
      });
    }
  })
}

function wxNavigate(url) {
  wx.navigateTo({
    url,
    fail: function () {
      wx.switchTab({
        url,
      });
    }
  })
}

function wxUserInfo() {
  return new Promise((resolve, reject) => {
    checkSetting('scope.user-info').then(() => {
      wx.getUserInfo({
        success(res) {
          resolve(res.userInfo)
        },
        fail() {
          reject('获取用户信息失败')
        }
      })
    }).catch(() => {
      reject('用户未同意授权')
    })
  })
}

function wxPreview(current, urls) {
  wx.previewImage({
    current,
    urls
  })
}

/**
 * 复制内容到粘贴板
 * @param msg 需要复制的内容
 */
function wxCopy(msg) {
  return new Promise((resolve, reject) => {
    wx.setClipboardData({
      data: msg,
      success() {
        resolve()
      },
      fail() {
        reject()
      }
    })
  })
}

/**
 * 微信扫码
 */
function wxScanCode(params = {}) {
  return new Promise((resolve, reject) => {
    wx.scanCode({
      ...params,
      success(res) {
        resolve(res)
      },
      fail(err) {
        reject(err)
      }
    })
  })
}

/**
 * 获取页面节点信息
 * @param id 节点ID
 */
function wxGetRect(id, that = false) {
  return new Promise((resolve, reject) => {
    id = `#${id}`
    let query = null
    if(that) {
      query = that.createSelectorQuery()
    } else {
      query = wx.createSelectorQuery()
    }
    query.select(id).boundingClientRect((rect) => {
      if (rect) {
        resolve(rect)
      } else {
        reject('未获取到节点信息')
      }
    }).exec()
  })
}

/**
 * 保存图片到手机
 * @param url
 */
function wxSaveImageToPhotosAlbum(url) {
  return new Promise((resolve, reject) => {
    checkSetting('scope.writePhotosAlbum').then(() => {
      wx.saveImageToPhotosAlbum({
        filePath: url,
        success() {
          resolve()
        },
        fail() {
          reject()
        }
      })
    })
    .catch(() => {
      reject()
    })
  })
}

/**
 * 上传图片
 */
function wxChooseImage(params = {}) {
  return new Promise((resolve, reject) => {
    wx.chooseImage({
      ...params,
      success: res => {
        resolve(res)
      },
      fail: err => {
        reject(err)
      }
    });
  })
}

/**
 * 上传视频
 */
function wxChooseVideo(params = {}) {
  return new Promise((resolve, reject) => {
    wx.chooseVideo({
      ...params,
      success: res => {
        resolve(res)
      },
      fail: err => {
        reject(err)
      }
    })
  })
}

/**
 * 获取上一页或多页页面data中的参数
 */
function pageData(key, page = 1) {
  return new Promise((resolve, reject) => {
    let pages = getCurrentPages()
    let data = pages[pages.length - 1 - page].data[key]
    resolve(data)
  })
}

/**
 * 拨打电话
 */
function wxCall(phone) {
  wx.makePhoneCall({
    phoneNumber: phone //仅为示例，并非真实的电话号码
  })
}


module.exports = {
  wxLogin,
  wxModel,
  wxLoading,
  wxHide,
  wxToast,
  checkSetting,
  wxGetImageInfo,
  wxSaveImageToPhotosAlbum,
  wxChooseAddress,
  wxRequestPayment,
  wxRedirect,
  wxNavigate,
  wxPromise,
  wxUserInfo,
  wxPreview,
  wxScanCode,
  wxGetRect,
  wxChooseImage,
  wxChooseVideo,
  pageData,
  wxCopy,
  wxCall,
  wxGetLocation
}
