// utils/logger.js — 生产可控日志（替代裸 console 调用）
// 生产环境只输出 error 级别；开发环境输出全部

var _envVersion =
  (typeof __wxConfig !== "undefined" && __wxConfig.envVersion) || "release";
var _IS_DEV = _envVersion === "develop";

var logger = {
  debug: function (tag, msg) {
    if (_IS_DEV) console.log("[" + tag + "]", msg || "");
  },
  info: function (tag, msg) {
    if (_IS_DEV) console.log("[" + tag + "]", msg || "");
  },
  warn: function (tag, msg) {
    if (_IS_DEV) console.warn("[" + tag + "]", msg || "");
  },
  error: function (tag, msg) {
    // error 始终输出（生产环境也需要看到严重错误）
    console.error("[" + tag + "]", msg || "");
  },
};

module.exports = logger;
