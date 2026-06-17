// test_freeCourseDetails_polyv_secret_boundary.js — Polyv signing secret must not live in client code.

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

var files = [
  "../pages/freeCourseDetails/freeCourseDetails.js",
  "../freeCourseDetails/freeCourseDetails.js",
  "../packageHost/pages/freeCourseDetails/freeCourseDetails.js",
];

files.forEach(function (relativePath) {
  var source = fs.readFileSync(path.join(__dirname, relativePath), "utf8");
  assert(
    source.indexOf("mnABa9XMn8") === -1,
    relativePath + " should not contain the legacy Polyv signing secret",
  );
  assert(
    source.indexOf("secretKey + vid + ts") === -1,
    relativePath + " should not build Polyv signatures from a client-side secret",
  );
});

if (fail > 0) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_freeCourseDetails_polyv_secret_boundary.js (" + pass + " assertions)");
