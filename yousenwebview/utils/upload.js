import { baseUrl } from 'config.js';
import { wxLoading,wxHide } from "../utils/wxPromise"
/**
 * 上传
 * @param arr 要上传的文件列表,使用chooseImage:res.tempFilePaths 使用chooseVideo:[res.tempFilePath]
 * @returns {Promise<unknown>}
 */
const uploadFileGroup = (arr, prefix = false) => {
  let newA = []
  let num = 0
  return new Promise((resolve, reject) => {
    wxLoading()
    arr.forEach(item => {
      wx.uploadFile({
        url: baseUrl + 'Action=GetImageFile',
        filePath: item,
        name: 'fileUrl',
        success(res) {
          console.log(res,"res")
          num += 1
          const obj = JSON.parse(res.data)
          // if (prefix) obj.data = baseUrl + obj.data
          newA.push(obj.data.file_path)
          if (num == arr.length) {
            resolve(newA)
            wxHide()
          }
        },
        fail(err) {
          console.log(err,"err")
          reject(err)
          wxHide()
        }
      });
    });
  });
}
module.exports = {
  uploadFileGroup
}
