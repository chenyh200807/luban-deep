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
  activeSummary.countText === "共 2 条后台记录",
  "active summary should keep the count in countText",
);
assert(
  activeSummary.meta === "调用了 知识库检索 · 深度推演",
  "active summary meta should only carry tool labels instead of duplicating count",
);

var completedSummary = workflowStatus.summarizeWorkflow(entries, false);
assert(
  completedSummary.countText === "共 2 条后台记录",
  "completed summary should keep the count in countText",
);
assert(
  completedSummary.meta === "调用了 知识库检索 · 深度推演",
  "completed summary meta should only carry tool labels instead of duplicating count",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_workflow_status.js (" + pass + " assertions)");
