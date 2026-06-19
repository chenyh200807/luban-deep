// INTERNAL PROTOTYPE ONLY — diagram_microlesson webview 沙盒验证页。
// 用途: 在 DevTools / 内测里手动验证 F16/N01 图解卡静态 HTML 的 webview 表现。
// 边界: 只渲染 web-view; 不接业务接口、不写数据库、不写 learning evidence、
//       不挂正式导航、不接评分/learner state。
// 默认直接加载本地服务的 F16; 看 N01 加 query ?card=n01; 也支持 ?url=<完整地址>。
// 真机预览时 127.0.0.1 是手机自己; 可用 ?card=n01&host=192.168.x.x:8799
// 或 ?base=http%3A%2F%2F192.168.x.x%3A8799 覆盖本地静态服务地址。
var BASE = "http://127.0.0.1:8799";

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
    n01: base + "/N01_network_video_first.rendered.html",
    n01_old: base + "/N01_network_keypath.rendered.html",
    c01: base + "/C01_construction_joint_contrast.schema_draft.rendered.html",
    j01:
      base + "/J01_danger_work_expert_argumentation.schema_draft.rendered.html",
    master: base + "/M_danger_work_expert_argumentation.master.view.html",
  };
}
Page({
  data: { url: cards(BASE).f16 },
  onLoad: function (query) {
    if (query && query.url) {
      this.setData({ url: decodeMaybe(query.url) });
      return;
    }
    var CARDS = cards(baseFromQuery(query));
    var card = (query && query.card) || "f16";
    this.setData({ url: CARDS[card] || CARDS.f16 });
  },
});
