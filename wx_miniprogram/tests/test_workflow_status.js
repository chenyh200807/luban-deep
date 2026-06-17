// test_workflow_status.js — regression tests for workflow summary dedupe
// Run: node wx_miniprogram/tests/test_workflow_status.js

var workflowStatus = require("../utils/workflow-status");

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

var entries = [
  {
    id: "wf_1",
    badge: "知识召回",
    title: "正在查找教材和规范依据",
    detail: "优先核对教材表述、规范条文和相关考点。",
    tone: "search",
    toolLabel: "知识库检索",
  },
  {
    id: "wf_2",
    badge: "深度推演",
    title: "正在补做关键推导和交叉验证",
    detail: "会换角度复核条件冲突、边界和结论可靠性。",
    tone: "compose",
    toolLabel: "深度推演",
  },
];

var activeSummary = workflowStatus.summarizeWorkflow(entries, true);
assert(
  activeSummary.countText === "",
  "active summary should not expose backend record counts",
);
assert(
  activeSummary.meta === "",
  "active summary meta should not expose tool or capability lists",
);

var completedSummary = workflowStatus.summarizeWorkflow(entries, false);
assert(
  completedSummary.countText === "已核对：知识库检索、深度推演",
  "completed summary should expose a learner-facing reliability cue",
);
assert(
  completedSummary.meta === "",
  "completed summary meta should not expose tool or capability lists",
);
assert(
  completedSummary.toggleText === "查看处理摘要",
  "completed summary should invite users to inspect a readable processing summary",
);

var internalToolEntry = workflowStatus.buildWorkflowEntry({
  eventType: "tool_call",
  content: "read_file",
  seq: 3,
  metadata: {
    tool: "read_file",
    args: { path: "/app/data/HEARTBEAT.md" },
  },
});
var internalResultEntry = workflowStatus.buildWorkflowEntry({
  eventType: "tool_result",
  content: "exec",
  seq: 4,
  metadata: { tool: "exec" },
});
var internalSummary = workflowStatus.summarizeWorkflow(
  [internalToolEntry, internalResultEntry],
  false,
);
var internalSurface = JSON.stringify([internalToolEntry, internalResultEntry, internalSummary]);
assert(
  internalSurface.indexOf("read_file") === -1 && internalSurface.indexOf("exec") === -1,
  "workflow entries should never expose internal tool names",
);
assert(
  internalSurface.indexOf("HEARTBEAT") === -1 && internalSurface.indexOf("/app/data") === -1,
  "workflow entries should never expose file paths or internal plan files",
);

var internalStatus = workflowStatus.normalizeWorkflowStatus(
  'HTTP_500: {"detail":"Internal Server Error","path":"/app/data/HEARTBEAT.md"}',
);
var internalStatusSurface = JSON.stringify(internalStatus);
assert(
  internalStatusSurface.indexOf("HTTP_500") === -1 &&
    internalStatusSurface.indexOf("Internal Server Error") === -1 &&
    internalStatusSurface.indexOf("HEARTBEAT") === -1,
  "workflow status should sanitize raw terminal/internal error strings",
);

var caseToolEntry = workflowStatus.buildWorkflowEntry({
  eventType: "tool_call",
  toolName: "grade_answer",
  seq: 5,
  metadata: { args: { question: "建筑实务案例题背景资料很长" } },
});
assert(
  caseToolEntry.badge === "案例批改",
  "case grading should use a learner-facing progress badge",
);
assert(
  caseToolEntry.title === "正在逐项匹配采分点",
  "case grading should explain the concrete grading step",
);
assert(
  caseToolEntry.detail.indexOf("资料较多") >= 0 &&
    caseToolEntry.detail.indexOf("请稍等") >= 0,
  "case grading should set patient expectations for longer analysis",
);

var slowStatus = workflowStatus.normalizeWorkflowStatus({ data: "slow_response" });
assert(
  slowStatus.headline === "资料较多，正在继续深度核对",
  "slow response should explain that deep checking is still happening",
);
assert(
  slowStatus.subline.indexOf("查依据") >= 0 &&
    slowStatus.subline.indexOf("对采分点") >= 0,
  "slow response should make system work visible without raw internals",
);

var unknownCaseStatus = workflowStatus.normalizeWorkflowStatus(
  "请批改这道案例题，材料比较长",
);
assert(
  unknownCaseStatus.headline === "正在拆解案例资料和作答结构",
  "case-like free text status should map to case workflow wording",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_workflow_status.js (" + pass + " assertions)");
