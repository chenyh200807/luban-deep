var api = require("../../utils/api");
var auth = require("../../utils/auth");
var helpers = require("../../utils/helpers");

function showSmsSentFeedback(message) {
  wx.showToast({
    title: message || "验证码发送成功",
    icon: "none",
  });
}

Page({
  data: {
    statusBarHeight: 44,
    safeBottom: 0,
    loading: false,
    wechatLoading: false,
    errorMsg: "",
    username: "",
    password: "",
    showPassword: false,
    loginMode: "phone_code",
    phoneCode: "",
    codeCountdown: 0,
    isDark: true,
    orbStyle1: "",
    orbStyle2: "",
    orbStyle3: "",
    skyWashStyle: "",
    btnGlowStyle: "",
    activeHeroIndex: 0,
    subtitleTrackStyle: "",
    pageShellStyle: "",
    heroMessages: [
      {
        line1: "抓不住重点、越学越乱？",
        line2: "AI先帮你锁定当下最该突破的考点。",
      },
      {
        line1: "刷了很多题，分数还是起不来？",
        line2: "系统会盯住你的薄弱点，反复练到真正会做。",
      },
      {
        line1: "临考发慌，不知道该补哪里？",
        line2: "鲁班智考会把复习路径和题目节奏先替你排好。",
      },
    ],
  },
  onLoad: function () {
    try {
      var info = helpers.getWindowInfo();
      var sb = info.safeArea ? info.screenHeight - info.safeArea.bottom : 0;
      this.setData({
        statusBarHeight: info.statusBarHeight || 44,
        safeBottom: sb,
        isDark: helpers.isDark(),
      });
      this._initOrbScene(info);
      this._initSubtitleScene(info);
    } catch (_) {}
    if (auth.isLoggedIn()) {
      api
        .getUserInfo()
        .then(function () {
          wx.switchTab({ url: "/pages/chat/chat" });
        })
        .catch(function (err) {
          if (String((err && err.message) || "") === "AUTH_EXPIRED") {
            auth.clearToken();
          }
        });
    }
  },
  onShow: function () {
    if (this._orbScene && !this._orbTimer) this._startOrbMotion();
    if (!this._subtitleTimer) this._startSubtitleAutoPlay();
  },
  onHide: function () {
    this._stopOrbMotion();
    this._stopSubtitleAutoPlay();
  },
  onUnload: function () {
    this._stopOrbMotion();
    this._stopSubtitleAutoPlay();
  },
  onUsernameInput: function (e) {
    this.setData({ username: e.detail.value, errorMsg: "" });
  },
  onPasswordInput: function (e) {
    this.setData({ password: e.detail.value, errorMsg: "" });
  },
  togglePassword: function () {
    this.setData({ showPassword: !this.data.showPassword });
  },
  handlePasswordLogin: function () {
    if (this.data.loading) return;
    var self = this,
      u = self.data.username,
      p = self.data.password;
    if (!u || !u.trim()) return self.setData({ errorMsg: "请输入用户名" });
    if (!p) return self.setData({ errorMsg: "请输入密码" });
    if (p.length < 6) return self.setData({ errorMsg: "密码至少 6 位" });
    self.setData({ loading: true, errorMsg: "" });
    api
      .request({
        url: "/api/v1/auth/login",
        method: "POST",
        data: { username: u.trim(), password: p },
        noAuth: true,
      })
      .then(function (resp) {
        var inner = resp.data || resp,
          user = inner.user || resp.user || {};
        var token =
          inner.token ||
          inner._token ||
          resp.token ||
          resp._token ||
          user._token;
        if (!token) throw new Error(resp.error || resp.message || "登录失败");
        auth.setToken(token);
        wx.switchTab({ url: "/pages/chat/chat" });
      })
      .catch(function (err) {
        var m = String(err.message || ""),
          msg = "登录失败，请重试";
        if (m.includes("NETWORK_")) msg = "网络连接失败";
        else if (m.includes("401") || m.includes("密码"))
          msg = "用户名或密码错误";
        else if (m.includes("429")) msg = "登录过于频繁";
        else if (m.includes("token")) msg = "服务端未返回凭证";
        else if (m && !m.startsWith("HTTP_")) msg = m;
        self.setData({ errorMsg: msg });
      })
      .then(
        function () {
          self.setData({ loading: false });
        },
        function () {
          self.setData({ loading: false });
        },
      );
  },
  onPhoneCodeInput: function (e) {
    this.setData({ phoneCode: e.detail.value, errorMsg: "" });
  },
  switchLoginMode: function () {
    this.setData({
      loginMode: this.data.loginMode === "password" ? "phone_code" : "password",
      errorMsg: "",
    });
  },
  sendCode: function () {
    var self = this;
    if (self.data.codeCountdown > 0 || self.data.loading) return;
    var phone = (self.data.username || "").trim();
    if (!phone || phone.length < 11) {
      self.setData({ errorMsg: "请输入正确的手机号" });
      return;
    }
    self.setData({ loading: true, errorMsg: "" });
    api
      .request({
        url: "/api/v1/auth/send-code",
        method: "POST",
        data: { phone: phone },
        noAuth: true,
      })
      .then(function (resp) {
        var inner = resp.data || resp;
        // resp.code is the outer ApiResponse code; inner may be the nested data
        var outerCode = resp.code !== undefined ? resp.code : inner.code;
        var outerMsg = resp.message || inner.message || "发送失败";
        var dataObj = inner.data || inner;
        var retryAfter = (dataObj && dataObj.retry_after) || inner.retry_after || 60;
        var sent = inner.sent || (dataObj && dataObj.sent);

        if (outerCode === 0 || sent) {
          // Success: start countdown
          var debugCode = (dataObj && dataObj.debug_code) || inner.debug_code || "";
          var successMsg =
            (dataObj && dataObj.message) || inner.message || resp.message || "验证码发送成功";
          var nextData = { codeCountdown: retryAfter, loading: false };
          if (debugCode) nextData.phoneCode = debugCode;
          self.setData(nextData);
          self._startCountdown(retryAfter);
          showSmsSentFeedback(successMsg);
          if (debugCode) {
            wx.showModal({
              title: "测试验证码",
              content: "当前环境未接短信服务，验证码：" + debugCode,
              showCancel: false,
            });
          }
        } else {
          // Error: show message, do NOT start countdown
          self.setData({
            errorMsg: outerMsg,
            loading: false,
          });
        }
      })
      .catch(function (err) {
        var m = String(err.message || "");
        var msg = "发送失败，请重试";
        if (m.includes("NETWORK_")) msg = "网络连接失败";
        else if (m.includes("429")) msg = "发送过于频繁，请稍后再试";
        self.setData({ errorMsg: msg, loading: false });
      });
  },
  _startCountdown: function (seconds) {
    var self = this;
    if (self._codeTimer) clearInterval(self._codeTimer);
    var remaining = seconds;
    self._codeTimer = setInterval(function () {
      remaining--;
      if (remaining <= 0) {
        clearInterval(self._codeTimer);
        self._codeTimer = null;
      }
      self.setData({ codeCountdown: remaining });
    }, 1000);
  },
  verifyCode: function () {
    var self = this;
    var phone = (self.data.username || "").trim();
    var code = (self.data.phoneCode || "").trim();
    if (!phone || !code) {
      self.setData({ errorMsg: "请输入手机号和验证码" });
      return;
    }
    self.setData({ loading: true, errorMsg: "" });
    api
      .request({
        url: "/api/v1/auth/verify-code",
        method: "POST",
        data: { phone: phone, code: code },
        noAuth: true,
      })
      .then(function (resp) {
        var inner = resp.data || resp;
        var token = inner.token;
        if (!token) throw new Error(resp.error || resp.message || "验证失败");
        auth.setToken(token);
        wx.switchTab({ url: "/pages/chat/chat" });
      })
      .catch(function (err) {
        var m = String(err.message || ""),
          msg = "验证失败，请重试";
        if (m.includes("NETWORK_")) msg = "网络连接失败";
        else if (m.includes("400") || m.includes("验证码"))
          msg = "验证码错误或已过期";
        else if (m.includes("429")) msg = "操作过于频繁";
        else if (m && !m.startsWith("HTTP_")) msg = m;
        self.setData({ errorMsg: msg });
      })
      .then(
        function () {
          self.setData({ loading: false });
        },
        function () {
          self.setData({ loading: false });
        },
      );
  },
  goRegister: function () {
    wx.navigateTo({ url: "/pages/register/register" });
  },
  goManualLogin: function () {
    wx.navigateTo({ url: "/pages/login/manual" });
  },
  _completeWechatAuth: function (payload) {
    var inner = payload && (payload.data || payload);
    var token = inner && inner.token;
    if (!token) throw new Error("服务端未返回凭证");
    auth.setToken(token);
    return { token: token };
  },
  handleWechatLogin: function () {
    var self = this;
    if (self.data.wechatLoading || self.data.loading) return;
    self.setData({ wechatLoading: true, errorMsg: "" });
    wx.login({
      success: function (loginRes) {
        if (!loginRes.code) {
          self.setData({ wechatLoading: false, errorMsg: "微信登录失败，请重试" });
          return;
        }
        api
          .wxLogin(loginRes.code)
          .then(function (resp) {
            self._completeWechatAuth(resp);
          })
          .then(function () {
            wx.switchTab({ url: "/pages/chat/chat" });
          })
          .catch(function (err) {
            var m = String((err && err.message) || "");
            var msg = "微信登录失败，请重试";
            if (m.includes("credentials")) msg = "后端未配置微信小程序密钥";
            else if (m.includes("NETWORK_")) msg = "网络连接失败";
            else if (m && !m.startsWith("HTTP_")) msg = m;
            self.setData({ errorMsg: msg });
          })
          .then(
            function () {
              self.setData({ wechatLoading: false });
            },
            function () {
              self.setData({ wechatLoading: false });
            },
          );
      },
      fail: function () {
        self.setData({ wechatLoading: false, errorMsg: "无法获取微信登录凭证" });
      },
    });
  },
  handleWechatPhoneNumber: function (e) {
    var self = this;
    if (self.data.wechatLoading || self.data.loading) return;
    var phoneCode =
      e &&
      e.detail &&
      (e.detail.code || e.detail.phoneCode || "");
    if (!phoneCode) {
      self.setData({ errorMsg: "未获取到微信手机号授权" });
      return;
    }
    self.setData({ wechatLoading: true, errorMsg: "" });
    wx.login({
      success: function (loginRes) {
        if (!loginRes.code) {
          self.setData({ wechatLoading: false, errorMsg: "微信登录失败，请重试" });
          return;
        }
        api
          .wxLogin(loginRes.code)
          .then(function (resp) {
            self._completeWechatAuth(resp);
            return api.bindPhone(phoneCode);
          })
          .then(function (resp) {
            var inner = resp.data || resp;
            if (inner && inner.token) {
              auth.setToken(inner.token);
            }
            wx.switchTab({ url: "/pages/chat/chat" });
          })
          .catch(function (err) {
            var m = String((err && err.message) || "");
            var msg = "微信手机号登录失败，请重试";
            if (m.includes("credentials")) msg = "后端未配置微信小程序密钥";
            else if (m.includes("getuserphonenumber")) msg = "微信手机号授权失败";
            else if (m.includes("NETWORK_")) msg = "网络连接失败";
            else if (m && !m.startsWith("HTTP_")) msg = m;
            self.setData({ errorMsg: msg });
          })
          .then(
            function () {
              self.setData({ wechatLoading: false });
            },
            function () {
              self.setData({ wechatLoading: false });
            },
          );
      },
      fail: function () {
        self.setData({ wechatLoading: false, errorMsg: "无法获取微信登录凭证" });
      },
    });
  },
  _initSubtitleScene: function (info) {
    this._subtitleSlideWidth = info.windowWidth || 375;
    this._subtitleDragOffset = 0;
    this._pageDragOffset = 0;
    this._updatePageShell();
    this._updateSubtitleTrack();
    this._startSubtitleAutoPlay();
  },
  _startSubtitleAutoPlay: function () {
    if (this._subtitleTimer) return;
    var self = this;
    this._subtitleTimer = setInterval(function () {
      self._shiftSubtitle(1);
    }, 3200);
  },
  _stopSubtitleAutoPlay: function () {
    if (this._subtitleTimer) {
      clearInterval(this._subtitleTimer);
      this._subtitleTimer = null;
    }
  },
  _shiftSubtitle: function (step) {
    var t = this.data.heroMessages.length;
    this._subtitleDragOffset = 0;
    this.setData({
      activeHeroIndex: (this.data.activeHeroIndex + step + t) % t,
    });
    this._updateSubtitleTrack();
  },
  _updateSubtitleTrack: function () {
    var w = this._subtitleSlideWidth || 375;
    var off =
      -(this.data.activeHeroIndex * w) + (this._subtitleDragOffset || 0);
    var tr = this._subtitleDragging
      ? "none"
      : "transform 320ms cubic-bezier(0.22,1,0.36,1)";
    this.setData({
      subtitleTrackStyle:
        "transform:translateX(" + off.toFixed(1) + "px);transition:" + tr + ";",
    });
  },
  onSubtitleTouchStart: function (e) {
    this._stopSubtitleAutoPlay();
    this._subtitleDragging = true;
    this._subtitleTouchStartX = e.touches[0].clientX;
    this._subtitleDragOffset = 0;
    this._updateSubtitleTrack();
  },
  onSubtitleTouchMove: function (e) {
    if (!this._subtitleDragging) return;
    this._subtitleDragOffset = Math.max(
      -44,
      Math.min(44, (e.touches[0].clientX - this._subtitleTouchStartX) * 0.45),
    );
    this._updateSubtitleTrack();
  },
  onSubtitleTouchEnd: function () {
    if (!this._subtitleDragging) return;
    var o = this._subtitleDragOffset || 0;
    this._subtitleDragging = false;
    if (o <= -18) this._shiftSubtitle(1);
    else if (o >= 18) this._shiftSubtitle(-1);
    else {
      this._subtitleDragOffset = 0;
      this._updateSubtitleTrack();
    }
    this._startSubtitleAutoPlay();
  },
  _updatePageShell: function () {
    var o = this._pageDragOffset || 0;
    var tr = this._pageDragging
      ? "none"
      : "transform 320ms cubic-bezier(0.22,1,0.36,1)";
    this.setData({
      pageShellStyle:
        "transform:translateY(" + o.toFixed(1) + "px);transition:" + tr + ";",
    });
  },
  onPageTouchStart: function (e) {
    if (this._subtitleDragging) return;
    this._pageDragging = true;
    this._pageTouchStartY = e.touches[0].clientY;
    this._pageDragOffset = 0;
    this._updatePageShell();
  },
  onPageTouchMove: function (e) {
    if (!this._pageDragging || this._subtitleDragging) return;
    this._pageDragOffset = Math.max(
      -18,
      Math.min(22, (e.touches[0].clientY - this._pageTouchStartY) * 0.22),
    );
    this._updatePageShell();
  },
  onPageTouchEnd: function () {
    if (!this._pageDragging) return;
    this._pageDragging = false;
    this._pageDragOffset = 0;
    this._updatePageShell();
  },
  _initOrbScene: function (info) {
    var w = info.windowWidth || 375,
      h = info.windowHeight || 812;
    this._orbScene = {
      width: w,
      height: h,
      minX: w * 0.04,
      maxX: w * 0.96,
      minY: h * 0.02,
      maxY: h * 0.48,
    };
    // 三球散开分布在上半屏不同区域，各自带不同方向初速度
    this._orbs = [
      {
        x: w * 0.25,
        y: h * 0.12,
        vx: 0.8,
        vy: 0.5,
        mass: 1.2,
        phase: 0.2,
        opacity: 0.9,
        wanderAngle: 0,
        wanderSpeed: 0.6,
      },
      {
        x: w * 0.7,
        y: h * 0.28,
        vx: -0.5,
        vy: -0.3,
        mass: 1.0,
        phase: 1.7,
        opacity: 0.84,
        wanderAngle: 2.1,
        wanderSpeed: 0.5,
      },
      {
        x: w * 0.45,
        y: h * 0.4,
        vx: 0.3,
        vy: -0.6,
        mass: 0.9,
        phase: 3.1,
        opacity: 0.8,
        wanderAngle: 4.3,
        wanderSpeed: 0.55,
      },
    ];
    this._orbTick = 0;
    this._renderOrbScene();
    this._startOrbMotion();
  },
  _startOrbMotion: function () {
    if (this._orbTimer || !this._orbScene) return;
    var s = this;
    // 低端设备降低帧率（80ms），但不跳过动画
    var interval = helpers.isLowEnd() ? 100 : 60;
    this._orbTimer = setInterval(function () {
      s._stepOrbScene();
    }, interval);
  },
  _stopOrbMotion: function () {
    if (this._orbTimer) {
      clearInterval(this._orbTimer);
      this._orbTimer = null;
    }
  },
  _stepOrbScene: function () {
    if (!this._orbs || !this._orbScene) return;
    var sc = this._orbScene,
      orbs = this._orbs;
    this._orbTick += 0.18;

    var maxSpd = 1.6;
    var damping = 0.992;

    // ── 1) 独立漫游：每个球沿自己的 wanderAngle 缓慢转向 ──
    for (var i = 0; i < 3; i++) {
      var o = orbs[i];
      // wanderAngle 缓慢随机偏转（柏林噪声感）
      o.wanderAngle += (Math.random() - 0.5) * 0.3;
      o.vx += Math.cos(o.wanderAngle) * o.wanderSpeed * 0.08;
      o.vy += Math.sin(o.wanderAngle) * o.wanderSpeed * 0.08;
    }

    // ── 2) 锁链约束 + 近距斥力 ──
    var chainLen = 100; // 锁链最大长度
    var chainStiff = 0.006; // 锁链拉力（超出时）
    for (var i = 0; i < 3; i++) {
      for (var j = i + 1; j < 3; j++) {
        var a = orbs[i],
          b = orbs[j];
        var dx = b.x - a.x,
          dy = b.y - a.y;
        var dist = Math.sqrt(dx * dx + dy * dy) || 1;
        var nx = dx / dist,
          ny = dy / dist;

        // 锁链：超过 chainLen 时越拉越紧（二次方增长）
        var pull = 0;
        if (dist > chainLen) {
          var over = dist - chainLen;
          pull = over * over * chainStiff;
        }
        // 松散弱引力区（40 < dist < chainLen 时微弱吸引）
        var attract = 0;
        if (dist > 40 && dist <= chainLen) {
          attract = (dist - 40) * 0.00006;
        }

        // 近距斥力（< 40 推开）
        var push = 0;
        if (dist < 40) {
          push = (40 - dist) * 0.005;
        }

        var fx = (pull + attract - push) * nx;
        var fy = (pull + attract - push) * ny;
        a.vx += fx / a.mass;
        a.vy += fy / a.mass;
        b.vx -= fx / b.mass;
        b.vy -= fy / b.mass;
      }
    }

    // ── 3) 阻尼 + 限速 + 弹性碰壁 ──
    for (var i = 0; i < 3; i++) {
      var o = orbs[i];
      o.vx *= damping;
      o.vy *= damping;

      var spd = Math.sqrt(o.vx * o.vx + o.vy * o.vy);
      if (spd > maxSpd) {
        o.vx *= maxSpd / spd;
        o.vy *= maxSpd / spd;
      }

      o.x += o.vx;
      o.y += o.vy;

      // 弹性碰壁回弹（保留 70% 速度 + 随机偏转）
      if (o.x < sc.minX) {
        o.x = sc.minX;
        o.vx = Math.abs(o.vx) * 0.7 + 0.2;
        o.vy += (Math.random() - 0.5) * 0.5;
        o.wanderAngle = Math.random() * Math.PI - Math.PI * 0.5; // 朝右半圈
      } else if (o.x > sc.maxX) {
        o.x = sc.maxX;
        o.vx = -Math.abs(o.vx) * 0.7 - 0.2;
        o.vy += (Math.random() - 0.5) * 0.5;
        o.wanderAngle = Math.PI + (Math.random() - 0.5) * Math.PI; // 朝左半圈
      }
      if (o.y < sc.minY) {
        o.y = sc.minY;
        o.vy = Math.abs(o.vy) * 0.7 + 0.2;
        o.vx += (Math.random() - 0.5) * 0.5;
        o.wanderAngle = Math.PI * 0.5 + (Math.random() - 0.5) * Math.PI;
      } else if (o.y > sc.maxY) {
        o.y = sc.maxY;
        o.vy = -Math.abs(o.vy) * 0.7 - 0.2;
        o.vx += (Math.random() - 0.5) * 0.5;
        o.wanderAngle = -Math.PI * 0.5 + (Math.random() - 0.5) * Math.PI;
      }
    }

    this._renderOrbScene();
  },
  _renderOrbScene: function () {
    if (!this._orbs || !this._orbScene) return;
    var orbs = this._orbs,
      sc = this._orbScene,
      tk = this._orbTick || 0,
      ss = [];
    // 三球亮度各自独立呼吸：不同频率 + 不同振幅 + 不同基准
    var baseOp = [0.92, 0.62, 0.36]; // 基准亮度：亮 / 中 / 暗
    var ampOp = [0.08, 0.18, 0.24]; // 呼吸振幅：暗球波动更大
    var freqs = [0.41, 0.67, 0.53]; // 呼吸频率：各不相同
    for (var i = 0; i < orbs.length; i++) {
      var o = orbs[i];
      var breath = Math.sin(tk * freqs[i] + o.phase);
      var s = 1 + breath * 0.04;
      var op = Math.max(0.18, Math.min(1, baseOp[i] + breath * ampOp[i]));
      ss.push(
        "left:" +
          o.x.toFixed(1) +
          "px;top:" +
          o.y.toFixed(1) +
          "px;opacity:" +
          op.toFixed(3) +
          ";transform:translate(-50%,-50%) scale(" +
          s.toFixed(3) +
          ");",
      );
    }
    var gx =
      (orbs[0].x * 0.32 + orbs[1].x * 0.36 + orbs[2].x * 0.32) / sc.width;
    var gy =
      (orbs[0].y * 0.28 + orbs[1].y * 0.38 + orbs[2].y * 0.34) / sc.height;
    var sp =
      (Math.abs(orbs[0].x - orbs[2].x) + Math.abs(orbs[1].y - orbs[0].y)) /
      (sc.width * 0.9);
    var wo = Math.max(0.86, Math.min(1.04, 1.04 - sp * 0.18));
    var sky =
      "background:radial-gradient(circle at " +
      (gx * 100).toFixed(1) +
      "% " +
      Math.min(34, gy * 72).toFixed(1) +
      "%,rgba(245,249,255,0.54) 0%,rgba(164,201,255,0.34) 16%,rgba(70,128,255,0.16) 34%,transparent 62%),radial-gradient(circle at " +
      Math.max(22, gx * 80).toFixed(1) +
      "% 16%,rgba(72,128,255,0.42) 0%,rgba(72,128,255,0.14) 26%,transparent 58%),radial-gradient(circle at 86% 62%,rgba(67,124,255,0.24) 0%,rgba(67,124,255,0.1) 22%,transparent 46%),linear-gradient(180deg,rgba(27,64,158,0.12) 0%,rgba(7,12,24,0) 64%);opacity:" +
      wo.toFixed(3) +
      ";";
    var lo = orbs[0];
    for (var i = 1; i < orbs.length; i++) {
      if (orbs[i].y > lo.y) lo = orbs[i];
    }
    var bf = Math.max(12, Math.min(88, (lo.x / sc.width) * 100));
    var bs = Math.max(0.18, Math.min(0.46, 0.18 + (lo.y / sc.maxY) * 0.2));
    var btn =
      "left:" +
      bf.toFixed(1) +
      "%;opacity:" +
      bs.toFixed(3) +
      ";transform:translateX(-50%) scale(" +
      (0.98 + bs * 0.12).toFixed(3) +
      ");";
    this.setData({
      orbStyle1: ss[0],
      orbStyle2: ss[1],
      orbStyle3: ss[2],
      skyWashStyle: sky,
      btnGlowStyle: btn,
    });
  },
});
