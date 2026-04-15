const formatTime = timestamp => {
  var date = new Date(parseInt(timestamp))
  const year = date.getFullYear()
  const month = date.getMonth() + 1
  const day = date.getDate()
  const hour = date.getHours()
  const minute = date.getMinutes()
  const second = date.getSeconds()

  return `${[year, month, day].map(formatNumber).join('-')} ${[hour, minute, second].map(formatNumber).join(':')}`
}
const formatTime2 = timestamp => {
  var date = new Date(parseInt(timestamp))
  const year = date.getFullYear()
  const month = date.getMonth() + 1
  const day = date.getDate()
  return `${[year, month, day].map(formatNumber).join('月')}`
}

const formatNumber = n => {
  n = n.toString()
  return n[1] ? n : `0${n}`
}
/**
 * 一维数组转二维
 * @param arr 数据列表
 * @param num 二维数组每行长度
 */
function fmtArrToTwo(arr, num) {
  let len = arr.length
  let lineNum = len % num === 0 ? len / num : Math.floor((len / num) + 1); //二维数组长度
  let res = []
  for (let i = 0; i < lineNum; i++) {
    // slice() 方法返回一个从开始到结束（不包括结束）选择的数组的一部分浅拷贝到一个新数组对象。且原始数组不会被修改。
    let temp = arr.slice(i * num, (i + 1) * num);
    res.push(temp);
  }
  return res
}
//把秒转为分钟
  /**
 * 格式化秒
 * @param int  value 总秒数
 * @return string result 格式化后的字符串
 */
function formatSeconds(value) {
  var theTime = parseInt(value);// 需要转换的时间秒 
  var theTime1 = 0;// 分 
  var theTime2 = 0;// 小时 
  var theTime3 = 0;// 天
  if(theTime > 60) {
    theTime1 = parseInt(theTime / 60);
    theTime = parseInt(theTime % 60);
    if (theTime1 > 60) {
      theTime2 = parseInt(theTime1 / 60);
      theTime1 = parseInt(theTime1 % 60);
      if (theTime2 > 24) {
        //大于24小时
        theTime3 = parseInt(theTime2 / 24);
        theTime2 = parseInt(theTime2 % 24);
      }
    }
  }
  var result = '';
  if (theTime >= 0) {
    result = "" + parseInt(theTime) < 10 ? '0' + parseInt(theTime) : parseInt(theTime);
  }
  if (theTime1 >= 0) {
    result = "" + (parseInt(theTime1) < 10 ? '0' + parseInt(theTime1) :parseInt(theTime1)) + ":" + result;
  }
  // if (theTime2 >= 0) {
  //   result = "" + (parseInt(theTime2) < 10 ? '0' + parseInt(theTime2) : parseInt(theTime2)) + ":" + result;
  // }
  // if (theTime3 >= 0) {
  //   result = "" + (parseInt(theTime3) < 10 ? '0' + parseInt(theTime3) : parseInt(theTime3)) + ":" + result;
  // }
    return result; 
}

module.exports = {
  formatTime,
  fmtArrToTwo,
  formatSeconds,
  formatTime2
}
