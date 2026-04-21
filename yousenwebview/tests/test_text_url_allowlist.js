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

function loadTextPage() {
  var source = fs.readFileSync(
    path.join(__dirname, "../pages/text/text.js"),
    "utf8",
  );
  var pageDef = null;

  var sandbox = {
    console: console,
    Page: function (def) {
      pageDef = def;
    },
  };

  vm.runInNewContext(source, sandbox, {
    filename: "pages/text/text.js",
  });

  var page = {
    data: Object.assign({}, (pageDef && pageDef.data) || {}),
    setData: function (next) {
      this.data = Object.assign({}, this.data, next || {});
    },
  };

  Object.keys(pageDef || {}).forEach(function (key) {
    if (key === "data") return;
    page[key] = pageDef[key];
  });

  return page;
}

run("normalizeTargetUrl keeps allowed yousen absolute urls", function () {
  var page = loadTextPage();
  var url = page.normalizeTargetUrl({
    url: encodeURIComponent("https://user.yousenjiaoyu.com/user/index.html"),
  });
  assert(
    url === "https://user.yousenjiaoyu.com/user/index.html",
    "allowed yousen absolute urls should pass through",
  );
});

run("normalizeTargetUrl falls back for disallowed external absolute urls", function () {
  var page = loadTextPage();
  var url = page.normalizeTargetUrl({
    url: encodeURIComponent("https://evil.example.com/phish"),
  });
  assert(
    url === "https://www.yousenjiaoyu.com",
    "disallowed external absolute urls should fall back to the safe host home",
  );
});

run("normalizeTargetUrl rejects javascript scheme and falls back safely", function () {
  var page = loadTextPage();
  var url = page.normalizeTargetUrl({
    url: encodeURIComponent("javascript:alert(1)"),
  });
  assert(
    url === "https://www.yousenjiaoyu.com",
    "javascript scheme should never be forwarded into the web-view page",
  );
});

run("normalizeTargetUrl still builds known urlname route on yousen domains", function () {
  var page = loadTextPage();
  var url = page.normalizeTargetUrl({
    urlname: "review/258.html",
    online: "true",
  });
  assert(
    url === "https://www.yousenjiaoyu.com/getwx/urlname/review/258.html",
    "known urlname payload should still resolve through the yousen route builder",
  );
});

if (fail) {
  console.error(errors.join("\n"));
  process.exit(1);
}

console.log("PASS test_text_url_allowlist.js (" + pass + " assertions)");
