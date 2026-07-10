var fs = require("fs");
var path = require("path");

var pass = 0;
var fail = 0;
var errors = [];

function assertIncludes(source, token, message) {
  if (source.indexOf(token) >= 0) pass++;
  else {
    fail++;
    errors.push("FAIL: " + message + " missing " + token);
  }
}

function read(relativePath) {
  return fs.readFileSync(path.join(__dirname, "../packageDeeptutor", relativePath), "utf8");
}

var login = read("pages/login/login.js");
var chat = read("pages/chat/chat.js");
var assessment = read("pages/assessment/assessment.js");

["module_viewed", "auth_authorize_clicked", "auth_result"].forEach(function (eventName) {
  assertIncludes(login, '"' + eventName + '"', "login funnel");
});
[
  "module_viewed",
  "chat_message_sent",
  "chat_first_answer_rendered",
  "section_viewed",
  "assessment_prompt_result",
].forEach(function (eventName) {
  assertIncludes(chat, '"' + eventName + '"', "chat funnel");
});
[
  "module_viewed",
  "learning_action_started",
  "learning_action_completed",
  "module_exited",
  "event_error",
].forEach(function (eventName) {
  assertIncludes(assessment, '"' + eventName + '"', "assessment funnel");
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log("PASS test_first_experience_funnel_telemetry.js (" + pass + " assertions)");
