function serializeQuery(options) {
  var source = options && typeof options === "object" ? options : {};
  return Object.keys(source)
    .filter(function (key) {
      return (
        key &&
        source[key] !== undefined &&
        source[key] !== null &&
        source[key] !== ""
      );
    })
    .map(function (key) {
      return (
        encodeURIComponent(key) +
        "=" +
        encodeURIComponent(String(source[key]))
      );
    })
    .join("&");
}

function redirectToSubpackage(pagePath, options) {
  if (!pagePath) return;
  var query = serializeQuery(options);
  var url = query ? pagePath + "?" + query : pagePath;
  wx.redirectTo({
    url: url,
    fail: function () {
      wx.reLaunch({
        url: url,
      });
    },
  });
}

module.exports = {
  redirectToSubpackage: redirectToSubpackage,
};
