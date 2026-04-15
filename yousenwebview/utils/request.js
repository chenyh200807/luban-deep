import url from "../api/baseApi"
import { baseUrl,baseUrl2,baseUrl3 } from "../utils/config"
import { wxToast } from "../utils/wxPromise"
//获取接口路径
const getUrl = (urlName) => {
	return url[urlName]
}
//post请求
function postrq(urlName,data={},isLoading=false) {
  return new Promise(function (resolve, reject) {
    if(isLoading){
      wx.showLoading({
        title: '加载中',
        mask:false
      })
    }
    // debugger;
    wx.request({
      url: baseUrl3 + getUrl(urlName),
      data: data,
      header: {
        'content-type': 'application/json'
      },
      method: "POST",
      success: function (res) {
        if(res.data.code==200){
          resolve(res.data)
          wx.hideLoading()
        }else{
          resolve(res.data)
          wx.hideLoading()
        }
      },
      fail: (err) => {
        reject(err)
      }
    })
    
  })
}
function postrq2(urlName,data={},isLoading=false) {
  return new Promise(function (resolve, reject) {
    if(isLoading){
      wx.showLoading({
        title: '加载中',
        mask:false
      })
    }
    wx.request({
      url: baseUrl2 + getUrl(urlName),
      data: data,
      header: {
        'content-type': 'application/json'
      },
      method: "POST",
      success: function (res) {
        if(res.data.code==200){
          resolve(res.data)
          wx.hideLoading()
        }else{
          resolve(res.data)
          wx.hideLoading()
        }
      },
      fail: (err) => {
        reject(err)
      }
    })
    
  })
}
// get请求
function getrq(urlName, data,isLoading=false) {
  return new Promise(function (resolve, reject) {
    if(isLoading){
      wx.showLoading({
        title: '加载中',
        mask:false
      })
    }
    setTimeout(() => {
      wx.request({
        url:baseUrl + getUrl(urlName),
        data: data,
        header: {
          'content-type': 'application/json'
        },
        method: "GET",
        success: function (res) {
          resolve(res.data)
        },
        fail: (err) => {
          reject(err)
        }
      })
    }, 1000);
  })
}
module.exports={
  postrq:postrq,
  getrq:getrq,
  postrq2:postrq2
};
