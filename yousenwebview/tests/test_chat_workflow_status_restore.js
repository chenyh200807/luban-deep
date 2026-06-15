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
  var pageDef = null;
  var sandbox = {
    console: console,
    Date: Date,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    require: function (request) {
      if (request === "../../utils/auth") return { getToken: function () { return "token"; } };
      if (request === "../../utils/api") return { unwrapResponse: function (raw) { return raw; } };
      if (request === "../../utils/ai-message-state") {
        return {
          coerceUserVisibleContent: function (value) { return String(value || ""); },
          sanitizePresentationForState: function (presentation) { return presentation || null; },
          deriveAiMessageRenderState: function (payload) {
            var content = String((payload && payload.content) || "");
            var presentation = payload && payload.presentation;
            return {
              renderableContent: content,
              blocks: content ? [{ type: "markdown", content: content }] : [],
              mcqCards: null,
              mcqHint: "",
              mcqReceipt: "",
              mcqInteractiveReady: false,
              mcqReviewMode: false,
              originalContent: "",
              originalCollapsed: true,
              hasStructuredContent: !!presentation,
            };
          },
        };
      }
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
        };
      }
      if (request === "../../utils/logger") return { warn: function () {}, error: function () {} };
      if (request === "../../utils/workflow-status") {
        return require(path.join(__dirname, "../packageDeeptutor/utils/workflow-status.js"));
      }
      if (request === "../../utils/citation-format") return {};
      if (request === "../../utils/chat-turn-recovery") {
        return {
          getAssistantDisplayText: function (message) {
            return message && message.content ? String(message.content) : "";
          },
        };
      }
      if (request === "../../utils/devtools-markdown-fixtures") return {};
      if (request === "../../utils/surface-telemetry") return { trackOnce: function () {} };
      if (request === "../../utils/history-tombstone") return {};
      if (request === "../../utils/runtime") return {};
      if (request === "../../utils/route") return {};
      if (request === "../../utils/flags") {
        return {
          shouldShowWorkspaceShell: function () { return false; },
          isFeatureEnabled: function () { return true; },
        };
      }
      if (request === "../../utils/analytics") return { track: function () {} };
      return {};
    },
    wx: {
      getStorageSync: function () { return ""; },
      removeStorageSync: function () {},
    },
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/pages/chat/chat.js",
  });

  return pageDef;
}

function applySetData(page, patch) {
  Object.keys(patch || {}).forEach(function (key) {
    var match = /^messages\[(\d+)\]\.(.+)$/.exec(key);
    if (match) {
      var idx = Number(match[1]);
      var field = match[2];
      page.data.messages[idx][field] = patch[key];
      return;
    }
    page.data[key] = patch[key];
  });
}

function loadChatSource() {
  return fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/pages/chat/chat.js"),
    "utf8",
  );
}

function loadWorkflowSource() {
  return fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/utils/workflow-status.js"),
    "utf8",
  );
}

function loadWsStream() {
  var source = fs.readFileSync(
    path.join(__dirname, "../packageDeeptutor/utils/ws-stream.js"),
    "utf8",
  );
  var module = { exports: {} };
  var sandbox = {
    module: module,
    exports: module.exports,
    require: function (request) {
      if (request === "./auth") return { getToken: function () { return "token"; } };
      if (request === "./api") return {};
      if (request === "./endpoints") return {};
      if (request === "./host-runtime") return {};
      throw new Error("unexpected require: " + request);
    },
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
  };
  vm.runInNewContext(source, sandbox, {
    filename: "packageDeeptutor/utils/ws-stream.js",
  });
  return module.exports;
}

run("chat page should show workflow status by default", function () {
  var pageDef = loadChatPage();
  assert(pageDef && pageDef.data && pageDef.data.showInternalStatus === true, "showInternalStatus should default to true");
});

run("chat page should label workflow as processing summary", function () {
  var source = loadChatSource();

  assert(source.indexOf("查看处理摘要") !== -1, "chat page should use processing summary wording");
  assert(source.indexOf("查看完整后台过程") === -1, "chat page should not mention full backend process");
  assert(source.indexOf("展开后台过程") === -1, "chat page should not mention expanding backend process");
  assert(source.indexOf("收起后台过程") === -1, "chat page should not mention collapsing backend process");
});

run("workflow copy should use student-facing learning progress wording", function () {
  var chatSource = loadChatSource();
  var workflowSource = loadWorkflowSource();
  var workflowStatus = require(path.join(__dirname, "../packageDeeptutor/utils/workflow-status.js"));
  var summary = workflowStatus.summarizeWorkflow([], true);

  assert(chatSource.indexOf("AI 正在准备") === -1, "chat page should not seed preparation wording");
  assert(chatSource.indexOf("AI 正在分析你的问题...") !== -1, "chat page should seed active analysis wording");
  assert(workflowSource.indexOf("后台") === -1, "workflow copy should not expose backend wording");
  assert(summary.badge === "AI 正在分析", "default workflow badge should feel already in progress");
  assert(summary.headline === "正在分析你的问题", "default workflow headline should be learner-facing");
});

run("internal thinking status should be sanitized before entering workflow trace", function () {
  var wsStream = loadWsStream();
  var workflowStatus = require(path.join(__dirname, "../packageDeeptutor/utils/workflow-status.js"));

  var payload = wsStream.buildStatusEvent({
    type: "thinking",
    content: "private chain of thought that should stay hidden",
    source: "chat",
    stage: "responding",
    metadata: { visibility: "internal" },
  });
  var entry = workflowStatus.buildWorkflowEntry(payload);

  assert(payload.content === "", "internal thinking payload content should be stripped");
  assert(payload.data === "responding", "internal thinking payload should fall back to stage name");
  assert(entry.title === "正在整理成考试作答结构", "workflow entry should use safe stage summary");
  assert(!entry.rawText, "workflow entry should not expose raw internal thinking text");
});

run("workflow trace should accept stage and tool events from ws stream", function () {
  var wsStream = loadWsStream();
  var workflowStatus = require(path.join(__dirname, "../packageDeeptutor/utils/workflow-status.js"));

  var stagePayload = wsStream.buildStatusEvent({
    type: "stage_start",
    stage: "responding",
    seq: 11,
    metadata: { visibility: "internal" },
  });
  var toolCallPayload = wsStream.buildStatusEvent({
    type: "tool_call",
    content: "rag",
    seq: 12,
    metadata: {
      visibility: "internal",
      args: { query: "流水节拍" },
    },
  });
  var toolResultPayload = wsStream.buildStatusEvent({
    type: "tool_result",
    content: "查到相关教材依据",
    seq: 13,
    metadata: {
      visibility: "internal",
      tool: "rag",
    },
  });

  var stageEntry = workflowStatus.buildWorkflowEntry(stagePayload);
  var toolCallEntry = workflowStatus.buildWorkflowEntry(toolCallPayload);
  var toolResultEntry = workflowStatus.buildWorkflowEntry(toolResultPayload);

  assert(stagePayload.seq === 11, "stage payload should keep server seq");
  assert(stageEntry.title === "正在整理成考试作答结构", "stage_start should restore responding stage wording");
  assert(toolCallEntry.title === "正在进行知识库检索", "tool_call should appear as workflow progress");
  assert(toolResultEntry.title === "知识库检索 已完成", "tool_result should appear as workflow progress");
  assert(!toolCallEntry.rawText, "tool_call should not expose JSON args in user-visible workflow");
  assert(!toolResultEntry.rawText, "tool_result should not expose raw backend returns in user-visible workflow");
  assert(JSON.stringify(toolCallEntry).indexOf('"query"') === -1, "workflow entry should omit raw arg keys");

  var internalEntry = workflowStatus.buildWorkflowEntry({
    eventType: "tool_call",
    content: "read_file",
    seq: 14,
    metadata: { visibility: "internal", tool: "read_file", args: { path: "/app/data/HEARTBEAT.md" } },
  });
  var internalSurface = JSON.stringify(internalEntry);
  assert(internalSurface.indexOf("read_file") === -1, "workflow should hide internal tool names");
  assert(internalSurface.indexOf("HEARTBEAT") === -1, "workflow should hide internal file names");

  var internalStatus = workflowStatus.normalizeWorkflowStatus(
    'HTTP_500: {"detail":"Internal Server Error","path":"/app/data/HEARTBEAT.md"}',
  );
  var internalStatusSurface = JSON.stringify(internalStatus);
  assert(internalStatusSurface.indexOf("HTTP_500") === -1, "workflow should hide raw HTTP errors");
  assert(internalStatusSurface.indexOf("HEARTBEAT") === -1, "workflow should hide internal file paths in status");
});

run("result final answer should settle visible workflow before done", function () {
  var page = loadChatPage();
  page.data = {
    messages: [
      {
        id: "a1",
        role: "ai",
        content: "",
        renderableContent: "",
        streaming: true,
        blocks: [],
        hasStructuredContent: false,
        presentation: null,
        mcqCards: null,
        workflowEntries: [{ id: "wf1", title: "资料较多，正在继续深度核对" }],
        workflowActive: true,
        workflowBadge: "稍等片刻",
        workflowTitle: "资料较多，正在继续深度核对",
        workflowSub: "系统还在拆题干、查依据、对采分点",
        workflowMeta: "",
        workflowCountText: "",
        workflowToggleText: "查看处理摘要",
        workflowTone: "analyze",
        thinkingStatus: "资料较多，正在继续深度核对",
        thinkingBadge: "稍等片刻",
        thinkingSub: "系统还在拆题干、查依据、对采分点",
        thinkingTone: "analyze",
      },
    ],
    isStreaming: true,
    canStopStream: true,
  };
  page._streamId = "a1";
  page._messageIndexMap = { a1: 0 };
  page._buf = "";
  page.setData = function (patch) {
    applySetData(page, patch);
  };

  page._onFinal({ response: "## 批改结论\n最终批改答案", engine_turn_id: "turn_1" });

  assert(page.data.messages[0].content.indexOf("最终批改答案") >= 0, "final response should render");
  assert(page.data.messages[0].workflowActive === false, "visible answer should stop active workflow");
  assert(page.data.messages[0].streaming === false, "visible answer should stop message streaming");
  assert(page.data.messages[0].thinkingStatus === "", "visible answer should clear active thinking copy");
  assert(page.data.isStreaming === false, "visible answer should unlock the input before done replay");
  assert(page.data.canStopStream === false, "visible answer should hide stop control before done replay");
});

run("workflow trace should stay compact and show reliability summary", function () {
  var workflowStatus = require(path.join(__dirname, "../packageDeeptutor/utils/workflow-status.js"));
  var entries = [];
  for (var i = 0; i < 8; i++) {
    entries = workflowStatus.appendWorkflowEntry(entries, {
      eventType: i % 2 ? "tool_result" : "tool_call",
      toolName: i % 2 ? "grade_answer" : "rag",
      seq: i + 1,
      metadata: { args: { query: "建筑实务案例题第" + i + "步" } },
    });
  }
  var summary = workflowStatus.summarizeWorkflow(entries, false);

  assert(entries.length <= 5, "workflow trace should compact to at most five visible learning steps");
  assert(summary.subline.indexOf("题型识别") >= 0, "completed summary should explain learning progress");
  assert(summary.countText.indexOf("已核对：") === 0, "completed summary should include a reliability cue");
});

run("case grading workflow should make long analysis visible", function () {
  var workflowStatus = require(path.join(__dirname, "../packageDeeptutor/utils/workflow-status.js"));

  var caseEntry = workflowStatus.buildWorkflowEntry({
    eventType: "tool_call",
    toolName: "grade_answer",
    seq: 31,
    metadata: { args: { question: "建筑实务案例题背景资料很长" } },
  });
  var slowStatus = workflowStatus.normalizeWorkflowStatus({ data: "slow_response" });
  var unknownCaseStatus = workflowStatus.normalizeWorkflowStatus(
    "请批改这道案例题，材料比较长",
  );

  assert(caseEntry.badge === "案例批改", "case grading should use visible grading progress");
  assert(caseEntry.title === "正在逐项匹配采分点", "case grading should name the scoring-point step");
  assert(caseEntry.detail.indexOf("资料较多") >= 0, "case grading should explain why it may take longer");
  assert(slowStatus.headline === "资料较多，正在继续深度核对", "slow status should avoid generic waiting copy");
  assert(slowStatus.subline.indexOf("查依据") >= 0, "slow status should show real analysis work");
  assert(
    unknownCaseStatus.headline === "正在拆解案例资料和作答结构",
    "free text case status should still map to case analysis wording",
  );
});

run("workflow summary should use active analysis wording by default", function () {
  var workflowStatus = require(path.join(__dirname, "../packageDeeptutor/utils/workflow-status.js"));
  var summary = workflowStatus.summarizeWorkflow([], true);

  assert(summary.badge === "AI 正在分析", "default workflow badge should feel already in progress");
  assert(summary.headline === "正在分析你的问题", "default workflow headline should avoid preparation wording");
});

run("chat page should not seed preparation wording for first-frame thinking status", function () {
  var source = loadChatSource();

  assert(source.indexOf("AI 正在准备") === -1, "chat page should not contain preparation wording");
  assert(source.indexOf("AI 正在分析你的问题...") !== -1, "chat page should seed active analysis wording");
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_chat_workflow_status_restore.js (" + pass + " assertions)");
