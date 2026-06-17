// INTERNAL PROTOTYPE ONLY — diagram_microlesson webview 沙盒验证页。
// 用途: 在 DevTools / 内测里手动验证 F16/N01 图解卡静态 HTML 的 webview 表现。
// 边界: 只渲染 web-view; 不接业务接口、不写数据库、不写 learning evidence、
//       不挂正式导航、不接评分/learner state。
// 默认直接加载本地服务的 F16; 看 N01 加 query ?card=n01; 也支持 ?url=<完整地址>。
var BASE = 'http://127.0.0.1:8799';
var CARDS = {
  f16: BASE + '/F16_qigu.rendered.html',
  n01: BASE + '/N01_network_keypath.rendered.html'
};
Page({
  data: { url: CARDS.f16 },
  onLoad: function (query) {
    if (query && query.url) {
      var u = query.url;
      try { u = decodeURIComponent(query.url); } catch (e) { u = query.url; }
      this.setData({ url: u });
      return;
    }
    var card = (query && query.card) || 'f16';
    this.setData({ url: CARDS[card] || CARDS.f16 });
  }
});
