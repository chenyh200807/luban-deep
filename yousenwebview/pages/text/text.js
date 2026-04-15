// pages/text/text.js
Page({
  data: {
    url:''
  },

  normalizeTargetUrl(options = {}) {
    if (options.url) {
      try {
        return decodeURIComponent(options.url);
      } catch (_) {
        return options.url;
      }
    }

    if (options.urlname) {
      if (options.urlname.indexOf('.yousenjiaoyu.com') !== -1) {
        return options.urlname;
      }

      const baseUrl = options.online === 'true'
        ? 'https://www.yousenjiaoyu.com'
        : 'https://test2.yousenjiaoyu.com';

      return `${baseUrl}/getwx/urlname/${options.urlname}`;
    }

    if (options.cid) {
      return `https://www.yousenjiaoyu.com/checkxcx?cid=${options.cid}`;
    }

    return 'https://www.yousenjiaoyu.com';
  },

  onLoad(options) {
      this.setData({
        url: this.normalizeTargetUrl(options)
      });
  }
})
