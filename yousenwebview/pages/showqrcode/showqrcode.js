// pages/showqrcode/showqrcode.js
Page({
  data: {
    title: '一建全阶段备考资料',
    title1: '一级建造师',
    title2: '一建全阶段备考资料',
    wxqrcodeurl: 'https://work.weixin.qq.com/gm/8106a93d48e58ff10b9d3f54fb8421d6',
    arraydesc: [],
    descstring: '保姆级全程规划备考指导攻略！群内福利资料均为免费！'
  },

  onLoad(options) {
    const id = options && options.id !== undefined ? options.id : 1;
    this.getdatafromapi(id);
  },

  getdatafromapi(id) {
    wx.request({
      url: `https://www.yousenjiaoyu.com/getdatabyidzm/id/${id}`,
      method: 'GET',
      success: (res) => {
        this.setData({
          title: res.data.xcxData.title,
          title1: res.data.xcxData.title1,
          title2: res.data.xcxData.title2,
          wxqrcodeurl: res.data.xcxData.wxqrcodeurl,
          arraydesc: res.data.arraydesc,
          descstring: res.data.descstring
        });
      },
      fail() {}
    });
  }
})
