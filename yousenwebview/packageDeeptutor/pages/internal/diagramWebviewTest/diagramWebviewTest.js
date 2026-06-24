// INTERNAL PROTOTYPE ONLY — diagram_microlesson webview 沙盒验证页。
// 用途: 在 DevTools / 内测里手动验证 F16/N01 图解卡静态 HTML 的 webview 表现。
// 边界: 只渲染 web-view; 不接业务接口、不写数据库、不写 learning evidence、
//       不挂正式导航、不接评分/learner state。
// 默认直接加载当前 Luban Animation IR smoke 卡 C02; 也支持 ?url=<完整地址>。
// 真机 web-view 不接受 127.0.0.1 / 192.168.x.x 这类本地 HTTP 地址。
// 默认走 HTTPS 预览目录; DevTools 模拟器调试时仍可用 ?base=... 覆盖。
var BASE = "https://test2.yousenjiaoyu.com/luban-preview/c02";
var DEFAULT_CARD = "c02";

function decodeMaybe(value) {
  try {
    return decodeURIComponent(value);
  } catch (e) {
    return value;
  }
}

function baseFromQuery(query) {
  if (query && query.base) return decodeMaybe(query.base).replace(/\/$/, "");
  if (query && query.host) {
    var host = decodeMaybe(query.host).replace(/\/$/, "");
    return /^https?:\/\//.test(host) ? host : "http://" + host;
  }
  return BASE;
}

function cards(base) {
  return {
    f16: base + "/F16_qigu.rendered.html",
    c02: base + "/C02_progress_payment.animation_ir_preview.html",
    n01: base + "/N01_network_video_first.rendered.html",
    n01_old: base + "/N01_network_keypath.rendered.html",
    c01: base + "/C01_construction_joint_contrast.schema_draft.rendered.html",
    j01:
      base + "/J01_danger_work_expert_argumentation.schema_draft.rendered.html",
    master: base + "/M_danger_work_expert_argumentation.master.view.html",
  };
}
Page({
  data: { url: cards(BASE)[DEFAULT_CARD] },
  onLoad: function (query) {
    if (query && query.url) {
      this.setData({ url: decodeMaybe(query.url) });
      return;
    }
    var CARDS = cards(baseFromQuery(query));
    var card = (query && query.card) || DEFAULT_CARD;
    this.setData({ url: CARDS[card] || CARDS[DEFAULT_CARD] });
  },
});
