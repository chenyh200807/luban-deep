var helpers = require("../../utils/helpers");

Page({
  data: {
    statusBarHeight: 0,
    navHeight: 0,
    isDark: true,
    updatedAt: "2026-04-14",
    sections: [
      {
        title: "1. 服务说明",
        paragraphs: [
          "鲁班智考为备考学习辅助工具，提供 AI 对话答疑、练习推荐、学情分析与学习提醒等功能。",
          "系统输出用于学习参考，不构成执业建议、工程签章意见或任何形式的官方结论。",
        ],
      },
      {
        title: "2. 账号与使用",
        paragraphs: [
          "你应保证注册、绑定手机号和微信登录信息真实、有效，并妥善保管自己的登录凭证。",
          "不得利用本服务批量抓取、恶意压测、逆向接口、传播违法违规内容，或影响其他用户正常使用。",
        ],
      },
      {
        title: "3. AI 内容边界",
        paragraphs: [
          "AI 讲解、题目、解析与学习建议，可能存在滞后、遗漏或表达偏差，你应结合教材、规范和官方资料自行判断。",
          "涉及规范条文、施工方案、考试政策等高风险内容时，请以最新版官方文件为准。",
        ],
      },
      {
        title: "4. 数据与隐私",
        paragraphs: [
          "为提供连续学习体验，系统会保存必要的账号信息、学习记录、积分流水、对话内容和诊断结果。",
          "仅在实现登录、学情分析、练习推荐和服务改进所必需的范围内使用相关数据。",
        ],
      },
      {
        title: "5. 会员与积分",
        paragraphs: [
          "积分、会员状态和对应权益以系统实际展示为准；如遇活动赠送、扣减或有效期变更，以活动规则和系统账本记录为准。",
          "若因异常调用、系统故障或违规使用产生错误积分，平台有权进行更正。",
        ],
      },
      {
        title: "6. 免责与变更",
        paragraphs: [
          "在法律允许范围内，平台可根据产品迭代、监管要求或安全需要，对服务功能、规则和条款内容进行调整。",
          "重大调整会通过页面公告、站内提示或其他合理方式通知。",
        ],
      },
    ],
  },

  onLoad: function () {
    var info = helpers.getWindowInfo();
    this.setData({
      statusBarHeight: info.statusBarHeight,
      navHeight: info.statusBarHeight + 44,
      isDark: helpers.isDark(),
    });
  },

  onShow: function () {
    this.setData({ isDark: helpers.isDark() });
  },

  goBack: function () {
    wx.navigateBack({
      fail: function () {
        wx.switchTab({ url: "/pages/profile/profile" });
      },
    });
  },
});
