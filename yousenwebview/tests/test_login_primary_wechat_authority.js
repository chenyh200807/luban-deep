// test_login_primary_wechat_authority.js — primary login must not invoke getPhoneNumber
// Run: node yousenwebview/tests/test_login_primary_wechat_authority.js

var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

function read(relativePath) {
  return fs.readFileSync(path.join(__dirname, "..", relativePath), "utf8");
}

[
  "packageDeeptutor/pages/login/login.wxml",
  "../wx_miniprogram/pages/login/login.wxml",
].forEach(function (relativePath) {
  var content = read(relativePath);
  assert(
    content.indexOf('bindtap="handleWechatLogin"') >= 0,
    relativePath + " primary WeChat login should call plain wx.login handler",
  );
  assert(
    content.indexOf('open-type="getPhoneNumber"') === -1,
    relativePath + " primary WeChat login should not trigger getPhoneNumber quota",
  );
  assert(
    content.indexOf('bindgetphonenumber="handleWechatPhoneNumber"') === -1,
    relativePath + " primary WeChat login should keep phone binding off the entry button",
  );
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_login_primary_wechat_authority.js (" + pass + " assertions)");
