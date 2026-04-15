import { Config } from 'config.js';

// 跳转链接
function linkTo(url,type=false) {
  if (type =="redirectTo"){
    wx.redirectTo({
      url: url,
    })
  }else{
    wx.navigateTo({
      url: url,
      fail: function (rs) {
        wx.switchTab({
          url: url
        })
      }
    })
  }
}

// 弹出提示框
function layer(msg){
  wx.showToast({
    title: msg,
    icon: "none",
    duration: 1500
  })
}

// 判断后台是否登陆
function isLogin(){
  var admin = wx.getStorageSync("admin");
  if (!admin){
    linkTo("/pages/Admin/login/login");
  }
}

/*获得元素上的绑定的值*/
function getDataSet(e, key) {
  return e.currentTarget.dataset[key];
}

// 获取服务端配置数据
function getBase(field, callback) {
  if (field){
    var data = {
      field: field
    };
  }
  wx.request({
    url: Config.restUrl + 'Common/getConfig',
    data: data,
    method: "post",
    header: {
      'content-type': 'application/json'
    },
    success: function (res) {
      if (res.data.code==6){
        callback && callback(res.data.data);
      }
    }
  });
}
// 根据坐标获取当前地址
function getAddress(data,callback){
  wx.request({
    url: Config.restUrl + 'System/GetAddress',
    data: data,
    method: "post",
    header: {
      'content-type': 'application/json'
    },
    success: function (res) {
      callback && callback(res.data);
    }
  });
}
//根据坐标返回最近门店
function getLocateStore(data,callback){
  wx.request({
    url: Config.restUrl + 'System/LocateStore',
    data: data,
    method: "post",
    header: {
      'content-type': 'application/json'
    },
    success: function (res) {
      callback && callback(res.data);
    }
  });
}
//判断有无授权
function isAuth(){
  return new Promise((resolve,reject)=>{
    if(wx.getStorageSync('members')){
      resolve();
    }else{
      wx.showModal({
        title: '提示',
        content: '你还未授权是否前往授权',
        success (res) {
          if (res.confirm) {
            wx.navigateTo({
              url: '/pages/auth/auth',
            })
          } else if (res.cancel) {
            console.log('用户点击取消')
          }
        }
      })
      reject();
    }
  })
}
//获取系统基础信息
function getSysInfo(callback){
  wx.request({
    url: Config.restUrl + 'System/SysInfo',
    data: {},
    method: "get",
    header: {
      'content-type': 'application/json'
    },
    success: function (res) {
      callback && callback(res.data);
    }
  });
}

function getUserDetail(data,callback){
  data.fk_store_id=wx.getStorageSync('storeInfo').fk_store_id;
  wx.request({
    url: Config.restUrl +'System/UserDetail',
    data: data,
    method: "post",
    header: {
      'content-type': 'application/json'
    },
    success: function (res) {
      callback && callback(res.data);
    }
  });
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

//获取用户信息
// function getUserInfo(members_id, callback){
//   wx.request({
//     url: Config.restUrl + 'Action=GetUserDetail',
//     data: {
//       fk_user_id: members_id
//     },
//     method: "post",
//     header: {
//       'content-type': 'application/json'
//     },
//     success: function (res) {
//       callback && callback(res.data);
//     }
//   });
// }

module.exports={
  linkTo: linkTo,
  layer: layer,
  isLogin: isLogin,
  getDataSet: getDataSet,
  getBase: getBase,
  getAddress:getAddress,
  getLocateStore:getLocateStore,
  isAuth:isAuth,
  getSysInfo:getSysInfo,
  getUserDetail:getUserDetail,
  wxGetImageInfo:wxGetImageInfo
};
