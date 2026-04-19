var fs = require("fs");
var path = require("path");
var vm = require("vm");

var pass = 0;
var fail = 0;
var errors = [];

function assert(condition, message) {
  if (condition) {
    pass++;
    return;
  }
  fail++;
  errors.push("FAIL: " + message);
}

function run(name, fn) {
  try {
    fn();
  } catch (err) {
    fail++;
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
  }
}

function loadChatPage() {
var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
    "utf8",
  );
  var chatWxss = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/chat/chat.wxss"),
    "utf8",
  );
  var pageDef = null;
  var flagsState = {
    showWorkspaceShell: false,
  };
  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/auth") return { getToken: function () { return "token"; } };
      if (request === "../../utils/api") return { unwrapResponse: function (raw) { return raw; } };
      if (request === "../../utils/ai-message-state") return {};
      if (request === "../../utils/ws-stream") return {};
      if (request === "../../utils/helpers") {
        return {
          getAnimConfig: function () {
            return {
              flushThrottleMs: 16,
              mdParseInterval: 3,
              enableBreathingOrbs: false,
              enableMarquee: false,
              enableMsgAnimation: false,
              enableFocusPulse: false,
            };
          },
          getWindowInfo: function () {
            return {
              statusBarHeight: 20,
              windowWidth: 375,
              screenWidth: 375,
              windowHeight: 812,
              screenHeight: 812,
              safeArea: { bottom: 778 },
            };
          },
          isDark: function () { return true; },
          getTimeGreeting: function () { return "晚上好"; },
          syncTabBar: function () {},
        };
      }
      if (request === "../../utils/logger") return { warn: function () {}, error: function () {} };
      if (request === "../../utils/workflow-status") return {};
      if (request === "../../utils/citation-format") return {};
      if (request === "../../utils/chat-turn-recovery") return {};
      if (request === "../../utils/devtools-markdown-fixtures") return {};
      if (request === "../../utils/runtime") return {};
      if (request === "../../utils/route") return {};
      if (request === "../../utils/flags") {
        return {
          shouldShowWorkspaceShell: function () { return flagsState.showWorkspaceShell; },
          isFeatureEnabled: function () { return true; },
        };
      }
      if (request === "../../utils/analytics") return { track: function () {} };
      return {};
    },
    wx: {
      getStorageSync: function () { return ""; },
      removeStorageSync: function () {},
      nextTick: function (fn) {
        if (typeof fn === "function") fn();
      },
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/pages/chat/chat.js",
  });

  return {
    chatWxss: chatWxss,
    pageDef: pageDef,
    flagsState: flagsState,
  };
}

function createPageInstance(pageDef, data) {
  var page = Object.assign({}, pageDef);
  page.data = Object.assign({}, pageDef.data, data);
  page.setData = function (patch) {
    this.data = Object.assign({}, this.data, patch);
  };
  return page;
}

function unit(viewportWidth, rpx) {
  return Math.round((viewportWidth * rpx) / 750);
}

function createMeasuredQuery(height) {
  return {
    select: function () {
      return {
        boundingClientRect: function (callback) {
          if (typeof callback === "function") {
            callback({ height: height });
          }
          return this;
        },
      };
    },
    exec: function () {},
  };
}

run("workspace shell visible should pin composer flush to tab bar", function () {
  var loaded = loadChatPage();
  loaded.flagsState.showWorkspaceShell = true;
  var page = createPageInstance(loaded.pageDef, {
    viewportWidth: 375,
    safeBottom: 34,
    workspaceShellHeight: 104,
    workspaceShellHidden: false,
    hasMessages: true,
  });

  page._syncWorkspaceChrome({ hasMessages: true });

  assert(
    page.data.bottomBarStyle === "bottom:104px;padding-bottom:0px;",
    "workspace shell visible should not add extra bottom gap under the composer card",
  );
  assert(
    page.data.bottomBarCompact === true,
    "workspace shell visible should switch the chat composer into compact mode to preserve more reading space",
  );
  assert(
    page.data.chatBottomSpacer === unit(375, 236) + 104 + unit(375, 48),
    "chat bottom spacer should only reserve card height plus shell height when workspace shell is visible",
  );
});

run("bottom bar container should not keep its own bottom gap", function () {
  var loaded = loadChatPage();

  assert(
    /\.bottom-bar\s*\{[\s\S]*padding:\s*12rpx 20rpx 0;/.test(loaded.chatWxss),
    "bottom bar CSS should remove the fixed bottom padding so the composer card can sit flush on the tab bar",
  );
  assert(
    /bottom-input-card \{\{bottomBarCompact \? 'bottom-input-card-compact' : ''\}\}/.test(
      fs.readFileSync(
        path.join(__dirname, "../packageDeeptutor/pages/chat/chat.wxml"),
        "utf8",
      ),
    ),
    "chat bottom composer should expose a compact visual variant in WXML",
  );
  assert(
    /<view class="tool-row" wx:if="\{\{!bottomBarCompact\}\}">/.test(
      fs.readFileSync(
        path.join(__dirname, "../packageDeeptutor/pages/chat/chat.wxml"),
        "utf8",
      ),
    ),
    "compact composer should hide the extra tool row to save vertical space",
  );
});

run("measured bottom bar height should override fallback spacer", function () {
  var loaded = loadChatPage();
  loaded.flagsState.showWorkspaceShell = true;
  var page = createPageInstance(loaded.pageDef, {
    viewportWidth: 375,
    safeBottom: 34,
    workspaceShellHeight: 104,
    workspaceShellHidden: false,
    hasMessages: true,
  });
  page.createSelectorQuery = function () {
    return createMeasuredQuery(132);
  };

  page._syncWorkspaceChrome({ hasMessages: true });

  assert(
    page.data.chatBottomSpacer === 132 + 104 + unit(375, 12),
    "chat bottom spacer should follow the measured bottom bar height instead of a hard-coded estimate",
  );
});

run("workspace shell toggle should compensate scroll position when spacer grows", function () {
  var loaded = loadChatPage();
  loaded.flagsState.showWorkspaceShell = false;
  var page = createPageInstance(loaded.pageDef, {
    viewportWidth: 375,
    safeBottom: 34,
    workspaceShellHeight: 104,
    workspaceShellHidden: false,
    hasMessages: true,
    chatBottomSpacer: 144,
    chatScrollTop: 320,
  });
  page._lastScrollY = 320;

  loaded.flagsState.showWorkspaceShell = true;
  page._syncWorkspaceChrome({ hasMessages: true });

  assert(
    page.data.chatScrollTop === 422,
    "showing the workspace shell should preserve the visible message position by compensating scrollTop with the spacer delta",
  );
});

run("workspace shell hidden should still keep safe-area padding", function () {
  var loaded = loadChatPage();
  loaded.flagsState.showWorkspaceShell = false;
  var page = createPageInstance(loaded.pageDef, {
    viewportWidth: 375,
    safeBottom: 34,
    workspaceShellHeight: 104,
    workspaceShellHidden: false,
    hasMessages: true,
  });

  page._syncWorkspaceChrome({ hasMessages: true });

  assert(
    page.data.bottomBarStyle === "bottom:0px;padding-bottom:40px;",
    "standalone mode should keep the safe-area inset under the composer card",
  );
  assert(
    page.data.bottomBarCompact === false,
    "standalone mode should keep the full chat composer",
  );
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_chat_workspace_shell_layout.js (" + pass + " assertions)");
