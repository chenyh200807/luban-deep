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

function readYousen(relativePath) {
  return fs.readFileSync(
    path.join(__dirname, "../../yousenwebview/packageDeeptutor", relativePath),
    "utf8",
  );
}

[
  "utils/host-runtime.js",
  "utils/endpoints.js",
  "utils/ws-stream.js",
  "utils/report-sync-authority.js",
].forEach(function (relativePath) {
  assert(
    read(relativePath) === readYousen(relativePath),
    relativePath + " should stay byte-identical across wx_miniprogram and packageDeeptutor",
  );
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_surface_sync_authority.js (" + pass + " assertions)");
