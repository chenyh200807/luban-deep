// pages/text/text.js
Page({

  buildQuery(options = {}) {
    const query = Object.keys(options)
      .filter(key => options[key] !== undefined && options[key] !== null && options[key] !== '')
      .map(key => `${encodeURIComponent(key)}=${encodeURIComponent(options[key])}`)
      .join('&');
    return query;
  },

  onLoad(options) {
    const query = this.buildQuery(options);
    wx.redirectTo({
      url: query ? `/pages/text/text?${query}` : '/pages/text/text'
    });
  }
})
