var fs = require("fs");
var path = require("path");

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

function read(relativePath) {
  return fs.readFileSync(path.join(__dirname, "..", relativePath), "utf8");
}

function exists(relativePath) {
  return fs.existsSync(path.join(__dirname, "..", relativePath));
}

function run(name, fn) {
  try {
    fn();
  } catch (err) {
    fail++;
    errors.push("ERROR: " + name + " -> " + (err && err.stack ? err.stack : err));
  }
}

run("host app.wxss should not import deeptutor theme globally", function () {
  var source = read("app.wxss");
  assert(
    source.indexOf("deeptutor-theme.wxss") === -1,
    "app.wxss should not keep Deeptutor theme in the host global layer",
  );
});

run("deeptutor themed pages should import subpackage theme locally", function () {
  [
    "packageDeeptutor/pages/practice/practice.wxss",
    "packageDeeptutor/pages/report/report.wxss",
    "packageDeeptutor/pages/profile/profile.wxss",
  ].forEach(function (relativePath) {
    var source = read(relativePath);
    assert(
      source.indexOf('@import "/packageDeeptutor/theme.wxss";') === 0,
      relativePath + " should import /packageDeeptutor/theme.wxss from packageDeeptutor",
    );
  });
});

run("deeptutor pages should use subpackage analytics helper", function () {
  [
    "packageDeeptutor/pages/login/login.js",
    "packageDeeptutor/pages/login/manual.js",
    "packageDeeptutor/pages/register/register.js",
    "packageDeeptutor/pages/chat/chat.js",
  ].forEach(function (relativePath) {
    var source = read(relativePath);
    assert(
      source.indexOf('require("../../utils/analytics")') >= 0,
      relativePath + " should require analytics from packageDeeptutor/utils",
    );
    assert(
      source.indexOf('require("../../../utils/analytics")') === -1,
      relativePath + " should not require analytics from host utils",
    );
  });
});

run("deeptutor subpackage should not depend on host legacy request helper", function () {
  [
    "packageDeeptutor/pages/login/login.js",
    "packageDeeptutor/pages/login/manual.js",
    "packageDeeptutor/pages/register/register.js",
    "packageDeeptutor/pages/chat/chat.js",
    "packageDeeptutor/pages/history/history.js",
    "packageDeeptutor/pages/report/report.js",
    "packageDeeptutor/pages/profile/profile.js",
    "packageDeeptutor/utils/runtime.js",
    "packageDeeptutor/utils/api.js",
  ].forEach(function (relativePath) {
    var source = read(relativePath);
    assert(
      source.indexOf('utils/request') === -1,
      relativePath + " should not depend on host legacy request helper",
    );
  });
});

run("host root should not keep duplicated deeptutor theme copy", function () {
  assert(
    exists("deeptutor-theme.wxss") === false,
    "deeptutor-theme.wxss should not remain duplicated in the host root",
  );
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_deeptutor_package_placement.js (" + pass + " assertions)");
