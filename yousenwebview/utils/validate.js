
/**
 * 邮箱
 * @param {*} s
 */
function isEmail (s) {
  return /^([a-zA-Z0-9_-])+@([a-zA-Z0-9_-])+((.[a-zA-Z0-9_-]{2,3}){1,2})$/.test(s)
}

/**
 * 手机号码
 * @param {*} s
 */
function isMobile (s) {
  return /^1[3456789]\d{9}$/.test(s)
}

/**
 * 电话号码
 * @param {*} s
 */
function isPhone (s) {
  return /^([0-9]{3,4}-)?[0-9]{7,8}$/.test(s)
}

/**
 * URL地址
 * @param {*} s
 */
function isURL (s) {
  return /^http[s]?:\/\/.*/.test(s)
}

/**
 * 验证身份证号
 * @param {*} s
 */
function isCard (s) {
  return /^([1-9]{1})(\d{15}|\d{18})$/.test(s)
}

/**
 * 验证是否是中文
 */
function isChinese(str) {
  return /^([\u4E00-\u9FA5])*$/.test(str);
}


module.exports= {
  isPhone,
  isEmail,
  isMobile,
  isURL,
  isCard,
  isChinese
}
