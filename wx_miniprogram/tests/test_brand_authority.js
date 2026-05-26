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

var wxLogin = read("pages/login/login.wxml");
var wxManual = read("pages/login/manual.wxml");
var yousenLogin = readYousen("pages/login/login.wxml");
var yousenManual = readYousen("pages/login/manual.wxml");

assert(
  wxLogin.indexOf("Luban AI Tutor") < 0,
  "wx login should not expose the stale Luban AI Tutor brand",
);
assert(
  wxManual.indexOf("Luban AI Tutor") < 0,
  "wx manual login should not expose the stale Luban AI Tutor brand",
);
assert(
  yousenLogin.indexOf("Luban AI Tutor") < 0,
  "yousen login should not expose the stale Luban AI Tutor brand",
);
assert(
  yousenManual.indexOf("Luban AI Tutor") < 0,
  "yousen manual login should not expose the stale Luban AI Tutor brand",
);

assert(
  read("utils/brand.js") === readYousen("utils/brand.js"),
  "wx and yousen should share the same mini-program brand authority module",
);

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_brand_authority.js (" + pass + " assertions)");
