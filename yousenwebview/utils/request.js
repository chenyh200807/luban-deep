import url from "../api/baseApi"
import { baseUrl,baseUrl2,baseUrl3 } from "../utils/config"
//获取接口路径
const getUrl = (urlName) => {
	return url[urlName]
}
function requestByBaseUrl(baseUrlName, urlName, data = {}, isLoading = false, method = "GET") {
  return new Promise(function (resolve, reject) {
    let shouldHideLoading = false
    if (isLoading) {
      shouldHideLoading = true
      wx.showLoading({
        title: "加载中",
        mask: false
      })
    }
    wx.request({
      url: baseUrlName + getUrl(urlName),
      data: data,
      header: {
        "content-type": "application/json"
      },
      method: method,
      success: function (res) {
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
//post请求
function postrq(urlName,data={},isLoading=false) {
  return requestByBaseUrl(baseUrl3, urlName, data, isLoading, "POST")
}
function postrq2(urlName,data={},isLoading=false) {
  return requestByBaseUrl(baseUrl2, urlName, data, isLoading, "POST")
}
// get请求
function getrq(urlName, data,isLoading=false) {
  return requestByBaseUrl(baseUrl, urlName, data, isLoading, "GET")
}
module.exports={
  postrq:postrq,
  getrq:getrq,
  postrq2:postrq2
};
